from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import uvicorn
import httpx
import asyncio
import secrets
import argparse
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from openai import OpenAI
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import mcp_server_tools, SseServerParams
from autogen_core import CancellationToken
from autogen_agentchat.agents import AssistantAgent
from mcp.types import TextContent
import json
import hashlib
from collections import OrderedDict
import time
from typing import Optional
import threading
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Configure logging with more detailed format
os.makedirs('logs', exist_ok=True)  # Create logs directory if it doesn't exist

# Create a custom formatter for better debugging
class DetailedFormatter(logging.Formatter):
    def format(self, record):
        # Add thread info for debugging concurrency issues
        record.thread_name = threading.current_thread().name
        record.thread_id = threading.get_ident()
        return super().format(record)

detailed_formatter = DetailedFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - [Thread:%(thread_name)s-%(thread_id)d] - %(message)s'
)

# Setup handlers with detailed formatter
console_handler = logging.StreamHandler()
console_handler.setFormatter(detailed_formatter)

file_handler = logging.FileHandler('logs/app.log')
file_handler.setFormatter(detailed_formatter)

# Error-specific log file
error_handler = logging.FileHandler('logs/errors.log')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler, error_handler]
)
logger = logging.getLogger(__name__)

# Generate a new secret key on each restart to clear all existing sessions
session_secret = secrets.token_urlsafe(32)
server_start_time = datetime.now().timestamp()

# Lightweight session tracker - only tracks active session IDs for 50-user limit
class ActiveSessionTracker:
    def __init__(self, max_users=50):
        self.max_users = max_users
        self.active_sessions = OrderedDict()  # session_id -> last_access_time
        self.user_to_session = {}  # user_id -> session_id (prevent duplicate logins)
        self._lock = threading.RLock()  # Thread-safe operations

    def add_session(self, user_id: str, session_id: str):
        """Add new session with 50-user limit enforcement (thread-safe)"""
        with self._lock:
            try:
                # Remove old session if user already has one
                if user_id in self.user_to_session:
                    old_session_id = self.user_to_session[user_id]
                    if old_session_id in self.active_sessions:
                        del self.active_sessions[old_session_id]
                        logger.info(f"Removed old session {old_session_id} for user {user_id}")

                # Add new session
                self.active_sessions[session_id] = time.time()
                self.user_to_session[user_id] = session_id

                # Move to end (most recently used)
                self.active_sessions.move_to_end(session_id)

                # Evict oldest sessions if over limit
                evicted_count = 0
                while len(self.active_sessions) > self.max_users:
                    oldest_session_id = next(iter(self.active_sessions))
                    self._remove_session_by_id_unsafe(oldest_session_id)
                    evicted_count += 1
                    logger.info(f"Evicted oldest session: {oldest_session_id}")

                if evicted_count > 0:
                    logger.info(f"Evicted {evicted_count} sessions due to user limit")

                logger.info(f"Added session {session_id} for user {user_id}. Active sessions: {len(self.active_sessions)}/{self.max_users}")
                return True
                
            except Exception as e:
                logger.error(f"Error adding session {session_id} for user {user_id}: {str(e)}", exc_info=True)
                return False

    def update_session_access(self, session_id: str):
        """Update session access time and move to end (thread-safe)"""
        with self._lock:
            try:
                if session_id in self.active_sessions:
                    self.active_sessions[session_id] = time.time()
                    self.active_sessions.move_to_end(session_id)
                    return True
                return False
            except Exception as e:
                logger.error(f"Error updating session access for {session_id}: {str(e)}", exc_info=True)
                return False

    def is_session_active(self, session_id: str):
        """Check if session is in active sessions (thread-safe)"""
        with self._lock:
            return session_id in self.active_sessions

    def remove_session(self, session_id: str):
        """Remove session by session ID (thread-safe)"""
        with self._lock:
            return self._remove_session_by_id_unsafe(session_id)

    def _remove_session_by_id_unsafe(self, session_id: str):
        """Internal method to remove session (NOT thread-safe - use with lock)"""
        try:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                # Remove from user mapping
                user_to_remove = None
                for user_id, sess_id in self.user_to_session.items():
                    if sess_id == session_id:
                        user_to_remove = user_id
                        break
                if user_to_remove:
                    del self.user_to_session[user_to_remove]
                logger.info(f"Removed session {session_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing session {session_id}: {str(e)}", exc_info=True)
            return False

    def get_stats(self):
        """Get session statistics (thread-safe)"""
        with self._lock:
            return {
                "active_sessions": len(self.active_sessions),
                "max_users": self.max_users,
                "session_ids": list(self.active_sessions.keys())
            }

    def cleanup_expired_sessions(self, max_age_hours=24):
        """Clean up sessions older than max_age_hours (thread-safe)"""
        with self._lock:
            try:
                current_time = time.time()
                max_age_seconds = max_age_hours * 3600

                expired_sessions = []
                for session_id, last_access in self.active_sessions.items():
                    if current_time - last_access > max_age_seconds:
                        expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    self._remove_session_by_id_unsafe(session_id)

                if expired_sessions:
                    logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

                return len(expired_sessions)
            except Exception as e:
                logger.error(f"Error cleaning up expired sessions: {str(e)}", exc_info=True)
                return 0

# Global session tracker - only tracks session IDs, not data
session_tracker = ActiveSessionTracker(max_users=50)

def generate_user_id(request: Request):
    """Generate a unique user ID based on request headers and IP"""
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else "unknown"
    accept_language = request.headers.get("accept-language", "")

    # Create a unique identifier from browser characteristics
    browser_fingerprint = f"{user_agent}:{client_ip}:{accept_language}"
    user_id = hashlib.sha256(browser_fingerprint.encode()).hexdigest()[:16]
    return user_id

def extract_browser_cache_info(request: Request):
    """Extract browser cache and session information"""
    # Get client IP considering proxy headers
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() if request.headers.get("x-forwarded-for") else request.client.host if request.client else "unknown"

    cache_info = {
        "user_agent": request.headers.get("user-agent", ""),
        "accept_language": request.headers.get("accept-language", ""),
        "accept_encoding": request.headers.get("accept-encoding", ""),
        "client_ip": client_ip,
        "referer": request.headers.get("referer", ""),
        "cache_control": request.headers.get("cache-control", ""),
        "if_none_match": request.headers.get("if-none-match", ""),
        "if_modified_since": request.headers.get("if-modified-since", ""),
        "timestamp": time.time()
    }
    return cache_info

def validate_browser_fingerprint(request: Request, stored_cache: dict):
    """Validate that browser characteristics haven't changed with improved multi-user handling"""
    try:
        current_cache = extract_browser_cache_info(request)
        
        # More lenient validation for multi-user environments
        # Some proxy configurations might change IPs dynamically
        logger.debug(f"🔍 Validating browser fingerprint:")
        logger.debug(f"   Current cache: {current_cache}")
        logger.debug(f"   Stored cache: {stored_cache}")
        
        # Essential checks that should remain consistent
        user_agent_match = current_cache["user_agent"] == stored_cache.get("user_agent", "")
        accept_language_match = current_cache["accept_language"] == stored_cache.get("accept_language", "")
        
        # IP validation - more flexible for proxy environments
        ip_match = current_cache["client_ip"] == stored_cache.get("client_ip", "")
        
        # Log detailed comparison for debugging
        logger.debug(f"   User agent match: {user_agent_match}")
        logger.debug(f"   Accept language match: {accept_language_match}")
        logger.debug(f"   Client IP match: {ip_match}")
        logger.debug(f"   X-Forwarded-For header: {request.headers.get('x-forwarded-for', 'Not present')}")
        logger.debug(f"   X-Real-IP header: {request.headers.get('x-real-ip', 'Not present')}")
        logger.debug(f"   Remote address: {request.client.host if request.client else 'Unknown'}")
        
        # Core validation - user agent and language must match
        # IP can be more flexible in proxy environments
        if user_agent_match and accept_language_match:
            if not ip_match:
                logger.warning(f"⚠️  Client IP changed but other fingerprints match - allowing (proxy scenario)")
            return True
        else:
            logger.warning(f"⚠️  Critical browser fingerprint mismatch detected")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error validating browser fingerprint: {str(e)}", exc_info=True)
        return False

def create_secure_session_cookie(user_id: str, browser_cache: dict) -> str:
    """Create a secure session cookie with browser fingerprint"""
    session_data = {
        "user_id": user_id,
        "browser_fingerprint": {
            "user_agent": browser_cache.get("user_agent", ""),
            "client_ip": browser_cache.get("client_ip", ""),
            "accept_language": browser_cache.get("accept_language", "")
        },
        "created_at": time.time(),
        "expires_at": time.time() + (24 * 60 * 60)  # 24 hours
    }

    # Create secure token
    session_token = secrets.token_urlsafe(32)
    return session_token

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info(f"🚀 Server starting at {datetime.fromtimestamp(server_start_time)}")
    logger.info(f"🔐 New session secret generated - all existing sessions cleared")

    yield

    # Shutdown (if needed)
    logger.info("👋 Server shutting down...")

class MultiUserErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            # Log the error with detailed context
            user_id = "unknown"
            try:
                user_id = generate_user_id(request)
            except:
                pass
            
            logger.error(f"❌ Unhandled error for user {user_id} on {request.url.path}: {str(exc)}", exc_info=True)
            
            # For API endpoints, always return JSON
            if request.url.path.startswith('/send-message') or \
               request.url.path.startswith('/validate-keys') or \
               request.url.path.startswith('/log-client-error') or \
               request.url.path.startswith('/session-info') or \
               request.url.path.startswith('/chat-history'):
                
                error_response = {
                    "status": "error",
                    "detail": "An unexpected server error occurred. Please try again.",
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "timestamp": time.time()
                }
                
                return JSONResponse(
                    status_code=500,
                    content=error_response,
                    headers={"Content-Type": "application/json"}
                )
            
            # For other endpoints, return appropriate response
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={"Content-Type": "application/json"}
            )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with proper JSON response"""
    user_id = "unknown"
    try:
        user_id = generate_user_id(request)
    except:
        pass
    
    logger.warning(f"⚠️  Validation error for user {user_id}: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "detail": "Invalid request data",
            "errors": exc.errors(),
            "error_code": "VALIDATION_ERROR"
        },
        headers={
            "Content-Type": "application/json",
            "X-Content-Type-Options": "nosniff"
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with proper JSON response for API endpoints"""
    user_id = "unknown"
    try:
        user_id = generate_user_id(request)
    except:
        pass
    
    logger.warning(f"⚠️  HTTP {exc.status_code} error for user {user_id} on {request.url.path}: {exc.detail}")
    
    if request.url.path.startswith('/send-message') or \
       request.url.path.startswith('/validate-keys') or \
       request.url.path.startswith('/log-client-error') or \
       request.url.path.startswith('/session-info') or \
       request.url.path.startswith('/chat-history'):
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "detail": exc.detail,
                "error_code": f"HTTP_{exc.status_code}",
                "timestamp": time.time(),
            },
            headers={
                "Content-Type": "application/json",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    
    # For HTML endpoints, return HTML redirect or error page
    if exc.status_code == 401:
        return RedirectResponse(url="/", status_code=302)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail
        },
        headers={
            "Content-Type": "application/json"
        }
    )

# Create FastAPI app
app = FastAPI(title="Roambee MCP Demo", description="Multi-user chat application with enhanced error handling")

# Add session middleware with new secret key (clears all existing sessions)
app.add_middleware(SessionMiddleware, secret_key=session_secret)

# Add middleware for multi-user error handling
app.add_middleware(MultiUserErrorHandlerMiddleware)

# Add custom exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

def check_session_valid(request: Request):
    """Check if user has valid session using pure cookie-based approach with enhanced logging"""
    try:
        # Generate user ID for logging
        user_id = generate_user_id(request)
        
        # Check basic session data from cookies
        authenticated = request.session.get("authenticated", False)
        session_start_time = request.session.get("server_start_time", 0)
        session_id = request.session.get("session_id", "")
        stored_browser_cache = request.session.get("browser_cache", {})
        
        logger.info(f"🔍 Checking session validity for user {user_id}")
        logger.info(f"   Session authenticated: {authenticated}")
        logger.info(f"   Session start time: {session_start_time}")
        logger.info(f"   Server start time: {server_start_time}")
        logger.info(f"   Session ID: {session_id}")
        
        # Invalidate session if it's from a previous server instance
        if authenticated and session_start_time != server_start_time:
            logger.warning(f"⚠️  Session from previous server instance - clearing cookie for user {user_id}")
            logger.info(f"   Session start time: {session_start_time} != Server start time: {server_start_time}")
            request.session.clear()
            if session_id:
                logger.info(f"   Removing session {session_id} from tracker")
                session_tracker.remove_session(session_id)
            return False
        
        # Check if session is in active sessions tracker
        if authenticated and session_id:
            if session_tracker.is_session_active(session_id):
                # Validate browser fingerprint
                try:
                    if validate_browser_fingerprint(request, stored_browser_cache):
                        # Update access time in tracker and session
                        logger.debug(f"✅ Session {session_id} is valid - updating access time for user {user_id}")
                        session_tracker.update_session_access(session_id)
                        request.session["last_access"] = time.time()
                        return True
                    else:
                        logger.warning(f"⚠️  Browser fingerprint changed for session {session_id}, user {user_id}")
                        request.session.clear()
                        session_tracker.remove_session(session_id)
                        return False
                except Exception as e:
                    logger.error(f"❌ Error validating browser fingerprint for user {user_id}: {str(e)}", exc_info=True)
                    request.session.clear()
                    session_tracker.remove_session(session_id)
                    return False
            else:
                # Session not in active tracker (evicted or expired)
                logger.warning(f"⚠️  Session {session_id} not in active sessions - clearing cookie for user {user_id}")
                request.session.clear()
                return False
        
        logger.info(f"❌ Session validation failed for user {user_id} - not authenticated or missing session ID")
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error in session validation: {str(e)}", exc_info=True)
        try:
            request.session.clear()
        except:
            pass
        return False

@app.get("/", response_class=HTMLResponse)
async def config_page(request: Request):
    """Initial configuration page for API keys"""
    return templates.TemplateResponse("config.html", {"request": request})

async def validate_roambee_sse_connection(roambee_key: str):
    """Validate Roambee SSE connection"""
    try:
        fetch_mcp_server = SseServerParams(
            url="https://mcp-server.roambee.com/sse",
            headers = {"content-type":"text/event-stream; charset=utf-8",
                       "roambee-apikey": roambee_key}
        )
        tools = await mcp_server_tools(fetch_mcp_server)
        logger.info(f"Successfully connected to Roambee MCP server. Found {len(tools) if tools else 0} tools.")
        return tools
    except Exception as e:
        logger.error(f"Error connecting to Roambee MCP server: {e}")
        return None

@app.post("/validate-keys")
async def validate_keys(
    request: Request,
    openai_key: str = Form(...),
    roambee_key: str = Form(...)
):
    """Validate OpenAI and Roambee API keys and create cookie session"""
    # Generate user ID and extract browser cache info
    user_id = generate_user_id(request)
    browser_cache_info = extract_browser_cache_info(request)

    logger.info(f"Validating keys for user: {user_id}")

    # Check if we can accept new users (50 limit)
    current_stats = session_tracker.get_stats()
    if current_stats["active_sessions"] >= session_tracker.max_users:
        # Check if this user already has a session
        existing_session_id = request.session.get("session_id", "")
        if not (existing_session_id and session_tracker.is_session_active(existing_session_id)):
            return {"status": "error", "message": "Maximum number of users (50) reached. Please try again later."}

    # Validate API keys
    openai_valid = await validate_openai_key(openai_key)
    roambee_valid = await validate_roambee_key(roambee_key)

    logger.info(f"OpenAI valid: {openai_valid}")
    logger.info(f"Roambee valid: {roambee_valid}")
    if openai_valid and roambee_valid:
        # Validate MCP connection
        mcp_tools = await validate_roambee_sse_connection(roambee_key)
        if not mcp_tools:
            return {"status": "error", "message": "Failed to connect to Roambee MCP server"}

        # Create unique session ID
        session_id = secrets.token_urlsafe(32)

        # Store ALL data in FastAPI session cookies (no server-side duplication)
        request.session.clear()  # Clear any existing session
        request.session["authenticated"] = True
        request.session["openai_key"] = openai_key
        request.session["roambee_key"] = roambee_key
        request.session["server_start_time"] = server_start_time
        request.session["user_id"] = user_id
        request.session["session_id"] = session_id
        request.session["created_at"] = time.time()
        request.session["last_access"] = time.time()
        request.session["browser_cache"] = browser_cache_info
        request.session["user_chats"] = {}

        # Only track session ID in server memory (for 50-user limit)
        session_tracker.add_session(user_id, session_id)

        logger.info(f"User {user_id} authenticated successfully. Session stats: {session_tracker.get_stats()}")
        return {"status": "success", "redirect": "/chat"}
    else:
        error_msg = []
        if not openai_valid:
            error_msg.append("Invalid OpenAI API key")
        if not roambee_valid:
            error_msg.append("Invalid Roambee API key")
        return {"status": "error", "message": "; ".join(error_msg)}

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat application page - requires valid session"""
    session_start_time = request.session.get("server_start_time", 0)
    logger.debug(f"🔍 Checking session validity:")
    logger.debug(f"   Session authenticated: {request.session.get('authenticated', False)}")
    logger.debug(f"   Session start time: {session_start_time}")
    logger.debug(f"   Server start time: {server_start_time}")
    logger.debug(f"   Session valid: {check_session_valid(request)}")

    if not check_session_valid(request):
        logger.warning("❌ Invalid session - redirecting to config page")
        return RedirectResponse(url="/", status_code=302)

    logger.debug("✅ Valid session - serving chat page")
    return templates.TemplateResponse("chat.html", {"request": request})

async def chat_with_agent(message: str, openai_key: str, roambee_key: str, user_id: str = "unknown"):
    """Chat with agent using MCP tools with enhanced error handling"""
    try:
        logger.info(f"🤖 Starting agent chat for user {user_id}")
        
        now = datetime.now()
        day, month, year = now.day, now.strftime("%B"), now.year

        logger.info(f"   Connecting to Roambee MCP server for user {user_id}...")
        mcp_tools = await validate_roambee_sse_connection(roambee_key)
        if not mcp_tools:
            logger.error(f"❌ Failed to connect to Roambee MCP server for user {user_id}")
            return None

        logger.info(f"✅ Connected to MCP server for user {user_id}. Found {len(mcp_tools)} tools.")

        model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_key)
        agent = AssistantAgent(
                name="Roambee_MCP_Agent",
                model_client=model_client,
                tools=mcp_tools,
                reflect_on_tool_use=True,
                system_message=f"You are a helpful assistant. If you get dates or datetime in seconds or milliseconds then\
                      show always in human readable format. Today's date is {day} {month} {year}.")

        logger.info(f"🚀 Running agent for user {user_id}...")
        result = await agent.run(task=message, cancellation_token=CancellationToken())

        if result and result.messages:
            res_json = result.messages[-1].content
            logger.info(f"✅ Agent response generated successfully for user {user_id}")
            return res_json
        else:
            logger.warning(f"⚠️  No messages in agent result for user {user_id}")
            return None

    except Exception as e:
        logger.error(f"❌ Error in chat_with_agent for user {user_id}: {str(e)}", exc_info=True)
        return f"Sorry, an error occurred while processing your request: {str(e)}"

@app.post("/send-message")
async def send_message(
    request: Request,
    message: str = Form(...)
):
    """Enhanced send message endpoint with robust multi-user error handling"""
    user_id = generate_user_id(request)
    start_time = time.time()
    
    try:
        # Enhanced logging for multi-user debugging
        logger.info(f"🚀 Message request from user {user_id[:8]}...")
        logger.debug(f"📝 Message content: {message[:100]}{'...' if len(message) > 100 else ''}")
        
        # Validate session with better error handling
        try:
            if not check_session_valid(request):
                logger.warning(f"⚠️  Invalid session for user {user_id}")
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "detail": "Session expired. Please refresh the page and try again.",
                        "error_code": "INVALID_SESSION",
                        "requires_refresh": True
                    },
                    headers={"Content-Type": "application/json"}
                )
            
        except Exception as session_error:
            logger.error(f"❌ Session validation error for user {user_id}: {str(session_error)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "detail": "Session validation failed. Please refresh the page and try again.",
                    "error_code": "SESSION_VALIDATION_ERROR",
                    "requires_refresh": True
                },
                headers={"Content-Type": "application/json"}
            )
        
        # Enhanced rate limiting for multi-user environments
        try:
            if not check_rate_limit(user_id):
                logger.warning(f"⚠️  Rate limit exceeded for user {user_id}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": "error",
                        "detail": "Too many requests. Please wait a moment before sending another message.",
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "retry_after": 60
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Retry-After": "60"
                    }
                )
        except Exception as rate_error:
            logger.error(f"❌ Rate limiting error for user {user_id}: {str(rate_error)}", exc_info=True)
            # Continue processing - don't fail on rate limiting errors
        
        # Validate message content
        if not message or not message.strip():
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "detail": "Message cannot be empty.",
                    "error_code": "EMPTY_MESSAGE"
                },
                headers={"Content-Type": "application/json"}
            )
        
        if len(message) > 10000:  # Reasonable message length limit
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "detail": "Message is too long. Please keep it under 10,000 characters.",
                    "error_code": "MESSAGE_TOO_LONG"
                },
                headers={"Content-Type": "application/json"}
            )
        
        # Get session data
        openai_key = request.session.get("openai_key")
        roambee_key = request.session.get("roambee_key")
        
        if not openai_key or not roambee_key:
            logger.error(f"❌ Missing API keys for user {user_id}")
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "detail": "API keys not found. Please refresh the page and log in again.",
                    "error_code": "MISSING_API_KEYS",
                    "requires_refresh": True
                },
                headers={"Content-Type": "application/json"}
            )
        
        # Get AI response with enhanced error handling
        try:
            ai_response = await chat_with_agent(message, openai_key, roambee_key, user_id)
            
            if not ai_response:
                logger.error(f"❌ Empty AI response for user {user_id}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "detail": "Unable to generate response. Please try again.",
                        "error_code": "EMPTY_AI_RESPONSE"
                    },
                    headers={"Content-Type": "application/json"}
                )
            
        except Exception as ai_error:
            logger.error(f"❌ AI response error for user {user_id}: {str(ai_error)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "detail": "AI service temporarily unavailable. Please try again in a moment.",
                    "error_code": "AI_SERVICE_ERROR",
                    "retry_suggested": True
                },
                headers={"Content-Type": "application/json"}
            )
        
        # Store conversation with error handling
        try:
            user_chats = request.session.get("user_chats", {})
            session_id = request.session.get("session_id", "default")
            
            if session_id not in user_chats:
                user_chats[session_id] = []
            
            # Add messages to history
            user_chats[session_id].append({
                'role': 'user',
                'content': message,
                'timestamp': time.time()
            })
            user_chats[session_id].append({
                'role': 'assistant', 
                'content': ai_response,
                'timestamp': time.time()
            })
            
            # Trim history to prevent memory issues in multi-user environment
            max_history = 100  # Keep last 100 messages
            if len(user_chats[session_id]) > max_history:
                user_chats[session_id] = user_chats[session_id][-max_history:]
                logger.info(f"🧹 Trimmed chat history for user {user_id}")
            
            # Update session
            request.session["user_chats"] = user_chats
            request.session["last_access"] = time.time()
            
        except Exception as storage_error:
            logger.error(f"❌ Chat storage error for user {user_id}: {str(storage_error)}", exc_info=True)
            # Continue - don't fail the response due to storage issues
        
        # Calculate response time
        response_time = time.time() - start_time
        logger.info(f"✅ Message processed for user {user_id[:8]}... in {response_time:.2f}s")
        
        # Return successful response
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "response": ai_response,
                "timestamp": time.time()
                "response_time": response_time
            },
            headers={"Content-Type": "application/json"}
        )
        
    except Exception as e:
        # Final catch-all error handler
        response_time = time.time() - start_time
        logger.error(f"❌ Unexpected error in send_message for user {user_id}: {str(e)}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "detail": "An unexpected error occurred. Please try again.",
                "error_code": "UNEXPECTED_ERROR",
                "response_time": response_time,
                "timestamp": time.time()
            },
            headers={"Content-Type": "application/json"}
        )

@app.get("/chat-history")
async def get_chat_history(request: Request):
    """Get chat history for current session"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_chats = request.session.get("user_chats", {})
    # Return the most recent chat history if available
    if user_chats:
        latest_chat_id = max(user_chats.keys(), key=lambda x: int(x))
        return {"chat_history": user_chats[latest_chat_id]}
    return {"chat_history": []}

@app.post("/clear-session")
async def clear_session(request: Request):
    """Clear session cookie and remove from active sessions"""
    session_id = request.session.get("session_id", "")
    user_id = generate_user_id(request)

    # Clear cookie session
    request.session.clear()

    # Remove from active sessions tracker
    if session_id:
        session_tracker.remove_session(session_id)

    logger.info(f"Session cleared for user {user_id}")
    return {"status": "success"}

@app.post("/reset-config")
async def reset_config(request: Request):
    """Reset to configuration page"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Keep authentication but clear chat history in cookie
    request.session["user_chats"] = {}
    request.session["last_access"] = time.time()

    return {"status": "success", "redirect": "/"}

@app.get("/session-info")
async def get_session_info(request: Request):
    """Get session information for debugging"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    session_id = request.session.get("session_id", "")

    return {
        "session_stats": session_tracker.get_stats(),
        "current_user": generate_user_id(request),
        "session_id": session_id,
        "session_data": {
            "authenticated": request.session.get("authenticated", False),
            "created_at": request.session.get("created_at", 0),
            "last_access": request.session.get("last_access", 0),
            "chat_history_length": len(request.session.get("user_chats", {}).get(session_id, [])),
            "has_api_keys": bool(request.session.get("openai_key")) and bool(request.session.get("roambee_key"))
        },
        "is_session_active": session_tracker.is_session_active(session_id)
    }

@app.get("/cleanup-sessions")
async def cleanup_expired_sessions():
    """Manual cleanup of expired sessions (admin endpoint)"""
    cleaned_count = session_tracker.cleanup_expired_sessions(max_age_hours=24)
    return {
        "status": "success",
        "cleaned_sessions": cleaned_count,
        "current_stats": session_tracker.get_stats()
    }

# Placeholder functions - user will provide validation logic
async def validate_openai_key(key: str) -> bool:
    """Validate OpenAI API key by making a test request to OpenAI API"""
    if not key or len(key) < 20 or not key.startswith('sk-'):
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            return response.status_code == 200
    except Exception as e:
        logger.error(f"OpenAI API validation error: {e}")
        return False

async def validate_roambee_key(key: str) -> bool:
    """Validate Roambee API key by making a test request to Roambee API"""
    if not key or len(key) < 10:
        return False

    url = "https://api.roambee.com/services/user/me"
    headers = {'apikey': key}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                logger.info("Roambee API key validated successfully.")
                return True
            else:
                logger.error(f"Roambee API key validation failed: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error validating Roambee API key: {e}")
        return False

@app.post("/send-feedback")
async def send_feedback(
    request: Request,
    feedback: str = Form(...),
    message: str = Form(...)
):

    # You can log/store the feedback however you want
    logger.info(f"Received feedback: {feedback} for message: {message}")
    # Example: store feedback in session or database here

    return {"status": "success", "feedback_received": feedback, "message": message}

def is_kubernetes_environment():
    """Detect if running in Kubernetes environment"""
    try:
        # Check for Kubernetes environment variables
        k8s_indicators = [
            'KUBERNETES_SERVICE_HOST',
            'KUBERNETES_SERVICE_PORT',
            'KUBERNETES_PORT',
            'K8S_NODE_NAME',
            'POD_NAME',
            'POD_NAMESPACE'
        ]
        
        for indicator in k8s_indicators:
            if os.getenv(indicator):
                return True
        
        # Check for Kubernetes service account
        if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount'):
            return True
            
        # Check for common container/orchestration indicators
        if os.path.exists('/.dockerenv') or os.getenv('container'):
            return True
            
        return False
    except:
        return False

# Add endpoint for client-side error logging
@app.post("/log-client-error")
async def log_client_error(request: Request):
    """Log client-side errors for debugging"""
    try:
        error_data = await request.json()
        user_id = generate_user_id(request)
        
        logger.error(f"🌐 Client-side error from user {user_id}:")
        logger.error(f"   Context: {error_data.get('context', 'Unknown')}")
        logger.error(f"   Error: {error_data.get('error', {}).get('message', 'Unknown error')}")
        logger.error(f"   URL: {error_data.get('url', 'Unknown')}")
        logger.error(f"   User Agent: {error_data.get('userAgent', 'Unknown')}")
        logger.error(f"   Additional Info: {error_data.get('additionalInfo', {})}")
        
        return {"status": "logged"}
    except Exception as e:
        logger.error(f"❌ Error logging client error: {str(e)}")
        return {"status": "error"}

# Add comprehensive error monitoring
@app.get("/health-check")
async def health_check():
    """Health check endpoint with system status"""
    try:
        current_time = time.time()
        uptime = current_time - server_start_time
        
        # Check session tracker health
        session_stats = session_tracker.get_stats()
        
        # Check if we can connect to external services
        openai_status = "Unknown"
        roambee_status = "Unknown"
        
        response_data = {
            "status": "healthy",
            "timestamp": current_time,
            "uptime_seconds": uptime,
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "session_stats": session_stats,
            "services": {
                "openai": openai_status,
                "roambee": roambee_status
            },
            "memory_usage": {
                "active_sessions": len(session_tracker.active_sessions),
                "user_mappings": len(session_tracker.user_to_session)
            },
        }
        
        return JSONResponse(
            status_code=200,
            content=response_data,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            },
            headers={
                "Content-Type": "application/json"
            }
        )

@app.get("/debug-session/{session_id}")
async def debug_session(session_id: str, request: Request):
    """Debug endpoint for session issues (admin use)"""
    try:
        user_id = generate_user_id(request)
        current_session_id = request.session.get("session_id", "")
        
        # Only allow debugging own session for security
        if session_id != current_session_id:
            raise HTTPException(status_code=403, detail="Can only debug your own session")
        
        session_info = {
            "session_id": session_id,
            "user_id": user_id,
            "is_active": session_tracker.is_session_active(session_id),
            "session_data": {
                "authenticated": request.session.get("authenticated", False),
                "server_start_time": request.session.get("server_start_time", 0),
                "created_at": request.session.get("created_at", 0),
                "last_access": request.session.get("last_access", 0),
                "has_openai_key": bool(request.session.get("openai_key")),
                "has_roambee_key": bool(request.session.get("roambee_key")),
                "chat_count": len(request.session.get("user_chats", {}))
            },
            "browser_info": extract_browser_cache_info(request),
            "tracker_stats": session_tracker.get_stats()
        }
        
        return session_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error debugging session {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Debug session failed")

# Add rate limiting for send-message endpoint
request_counts = {}
rate_limit_lock = threading.Lock()

def check_rate_limit(user_id: str, max_requests: int = 10, window_seconds: int = 60):
    """Check if user is within rate limits"""
    with rate_limit_lock:
        current_time = time.time()
        
        # Clean old entries
        expired_users = []
        for uid, requests in request_counts.items():
            request_counts[uid] = [req_time for req_time in requests if current_time - req_time < window_seconds]
            if not request_counts[uid]:
                expired_users.append(uid)
        
        for uid in expired_users:
            del request_counts[uid]
        
        # Check current user
        user_requests = request_counts.get(user_id, [])
        if len(user_requests) >= max_requests:
            return False
        
        # Add current request
        user_requests.append(current_time)
        request_counts[user_id] = user_requests
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Roambee Chat App')
    parser.add_argument('--host', default='localhost', help='Host to bind to (default: localhost)')
    parser.add_argument('--port', type=int, default=4444, help='Port to bind to (default: 4444)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       help='Set the logging level (default: INFO)')

    args = parser.parse_args()

    # Set logging level based on command line argument
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    host = args.host
    port = args.port

    logger.info(f"✅ Server ready to start at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
