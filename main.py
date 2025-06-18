from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
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

# Configure logging
os.makedirs('logs', exist_ok=True)  # Create logs directory if it doesn't exist

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log')  # Write to logs directory
    ]
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

    def add_session(self, user_id: str, session_id: str):
        """Add new session with 50-user limit enforcement"""
        # Remove old session if user already has one
        if user_id in self.user_to_session:
            old_session_id = self.user_to_session[user_id]
            if old_session_id in self.active_sessions:
                del self.active_sessions[old_session_id]

        # Add new session
        self.active_sessions[session_id] = time.time()
        self.user_to_session[user_id] = session_id

        # Move to end (most recently used)
        self.active_sessions.move_to_end(session_id)

        # Evict oldest sessions if over limit
        while len(self.active_sessions) > self.max_users:
            oldest_session_id = next(iter(self.active_sessions))
            self._remove_session_by_id(oldest_session_id)
            logger.info(f"Evicted oldest session: {oldest_session_id}")

        logger.info(f"Active sessions: {len(self.active_sessions)}/{self.max_users}")
        return True

    def update_session_access(self, session_id: str):
        """Update session access time and move to end"""
        if session_id in self.active_sessions:
            self.active_sessions[session_id] = time.time()
            self.active_sessions.move_to_end(session_id)
            return True
        return False

    def is_session_active(self, session_id: str):
        """Check if session is in active sessions"""
        return session_id in self.active_sessions

    def remove_session(self, session_id: str):
        """Remove session by session ID"""
        return self._remove_session_by_id(session_id)

    def _remove_session_by_id(self, session_id: str):
        """Internal method to remove session"""
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
            return True
        return False

    def get_stats(self):
        """Get session statistics"""
        return {
            "active_sessions": len(self.active_sessions),
            "max_users": self.max_users,
            "session_ids": list(self.active_sessions.keys())
        }

    def cleanup_expired_sessions(self, max_age_hours=24):
        """Clean up sessions older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        expired_sessions = []
        for session_id, last_access in self.active_sessions.items():
            if current_time - last_access > max_age_seconds:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self._remove_session_by_id(session_id)
            logger.info(f"Cleaned up expired session: {session_id}")

        return len(expired_sessions)

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
    """Validate that browser characteristics haven't changed"""
    current_cache = extract_browser_cache_info(request)
    logger.info(f"   Current cache: {current_cache}")
    logger.info(f"   Stored cache: {stored_cache}")
    logger.info(f"   User agent match: {current_cache['user_agent']} {stored_cache['user_agent']} {current_cache['user_agent'] == stored_cache['user_agent']}")
    logger.info(f"   Client IP match: {current_cache['client_ip']} {stored_cache['client_ip']} {current_cache['client_ip'] == stored_cache['client_ip']}")
    logger.info(f"   Accept language match: {current_cache['accept_language']} {stored_cache['accept_language']} {current_cache['accept_language'] == stored_cache['accept_language']}")
    logger.info(f"   X-Forwarded-For header: {request.headers.get('x-forwarded-for', 'Not present')}")
    logger.info(f"   X-Real-IP header: {request.headers.get('x-real-ip', 'Not present')}")
    logger.info(f"   Remote address: {request.client.host if request.client else 'Unknown'}")

    # Check critical browser characteristics
    return (
        current_cache["user_agent"] == stored_cache.get("user_agent", "") and
        current_cache["client_ip"] == stored_cache.get("client_ip", "") and
        current_cache["accept_language"] == stored_cache.get("accept_language", "")
    )

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

app = FastAPI(title="Roambee MCP Demo", lifespan=lifespan)

# Add session middleware with new secret key (clears all existing sessions)
app.add_middleware(SessionMiddleware, secret_key=session_secret)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

def check_session_valid(request: Request):
    """Check if user has valid session using pure cookie-based approach"""
    # Check basic session data from cookies
    authenticated = request.session.get("authenticated", False)
    session_start_time = request.session.get("server_start_time", 0)
    session_id = request.session.get("session_id", "")
    stored_browser_cache = request.session.get("browser_cache", {})
    logger.info(f"Checking session validity for user")
    logger.info(f"   Session authenticated: {authenticated}")
    logger.info(f"   Session start time: {session_start_time}")
    logger.info(f"   Server start time: {server_start_time}")
    logger.info(f"   Session ID: {session_id}")
    
    # Invalidate session if it's from a previous server instance
    if authenticated and session_start_time != server_start_time:
        logger.info(f"Session from previous server instance - clearing cookie {session_start_time} != {server_start_time}")
        request.session.clear()
        logger.info(f"Session cleared")
        logger.info(f"Session ID: {session_id}")
        if session_id:
            logger.info(f"Removing session from tracker {session_id}")
            session_tracker.remove_session(session_id)
        return False
    
    # Check if session is in active sessions tracker
    if authenticated and session_id:
        if session_tracker.is_session_active(session_id):
            # Validate browser fingerprint
            if validate_browser_fingerprint(request, stored_browser_cache):
                # Update access time in tracker and session
                logger.info(f"Session {session_id} is active - updating access time")
                session_tracker.update_session_access(session_id)
                request.session["last_access"] = time.time()
                return True
            else:
                logger.warning(f"Browser fingerprint changed for session {session_id}")
                request.session.clear()
                session_tracker.remove_session(session_id)
                return False
        else:
            # Session not in active tracker (evicted or expired)
            logger.info(f"Session {session_id} not in active sessions - clearing cookie")
            request.session.clear()
            return False
    
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
        request.session["chat_history"] = []

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

async def chat_with_agent(message: str, openai_key: str, roambee_key: str):
    """Chat with agent using MCP tools"""
    try:
        res_json = False
        now = datetime.now()
        day, month, year = now.day, now.strftime("%B"), now.year

        logger.info("Connecting to Roambee MCP server...")
        mcp_tools = await validate_roambee_sse_connection(roambee_key)
        if not mcp_tools:
            logger.error("Failed to connect to Roambee MCP server")
            return None

        logger.info(f"Successfully connected to MCP server. Found {len(mcp_tools)} tools.")
        logger.info(f"Today's date is {day} {month} {year}")

        model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_key)
        agent = AssistantAgent(
                name="Roambee_MCP_Agent",
                model_client=model_client,
                tools=mcp_tools,
                reflect_on_tool_use=True,
                system_message=f"You are a helpful assistant. If you get dates or datetime in seconds or milliseconds then\
                      show always in human readable format. Today's date is {day} {month} {year}.")

        logger.info("Running agent with message...")
        result = await agent.run(task=message, cancellation_token=CancellationToken())

        if result and result.messages:
            res_json = result.messages[-1].content
            logger.info("Successfully got response from agent")
            return res_json
        else:
            logger.warning("No messages in agent result")
            return None

    except Exception as e:
        logger.error(f"Error in chat_with_agent: {e}")
        return f"Sorry, an error occurred while processing your request.\n{e}"

@app.post("/send-message")
async def send_message(
    request: Request,
    message: str = Form(...)
):
    """Send message and get AI response - all data from cookies"""
    try:
        user_id = generate_user_id(request)
        session_id = request.session.get("session_id", "")

        logger.info(f"🔍 Processing message for user {user_id} with session {session_id}")
        logger.debug("🔍 Checking session validity (cookie-based):")
        logger.debug(f"   User ID: {user_id}")
        logger.debug(f"   Session ID: {session_id}")
        logger.debug(f"   Session authenticated: {request.session.get('authenticated', False)}")
        logger.debug(f"   Session valid: {check_session_valid(request)}")

        if not check_session_valid(request):
            logger.warning(f"❌ Invalid session for user {user_id}")
            raise HTTPException(status_code=401, detail="Unauthorized")

        # All data comes from cookies - no server-side storage needed
        chat_history = request.session.get("chat_history", [])
        openai_key = request.session.get("openai_key")
        roambee_key = request.session.get("roambee_key")

        if not openai_key or not roambee_key:
            logger.error(f"Missing API keys for user {user_id}")
            raise HTTPException(status_code=400, detail="API keys not found in session")

        # Add user message
        chat_history.append({"role": "user", "content": message})

        # Get AI response
        logger.info(f"Question asked by user {user_id}: {message}")
        try:
            agent_response = await chat_with_agent(message, openai_key, roambee_key)
            if agent_response:
                chat_history.append({"role": "assistant", "content": agent_response})
            else:
                logger.warning(f"No agent response for user {user_id}, falling back to OpenAI")
                ai_response = await get_ai_response(message, openai_key)
                chat_history.append({"role": "assistant", "content": ai_response})
        except Exception as e:
            logger.error(f"Error getting AI response for user {user_id}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error getting AI response: {str(e)}")

        # Update session cookie with new chat history
        request.session["chat_history"] = chat_history
        request.session["last_access"] = time.time()

        return {"response": chat_history[-1]["content"], "chat_history": chat_history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_message for user {user_id if 'user_id' in locals() else 'unknown'}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@app.get("/chat-history")
async def get_chat_history(request: Request):
    """Get chat history for current session"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"chat_history": request.session.get("chat_history", [])}

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
    request.session["chat_history"] = []
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
            "chat_history_length": len(request.session.get("chat_history", [])),
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

async def get_ai_response(message: str, openai_key: str) -> str:
    """Get AI response using OpenAI API"""
    try:
        client = OpenAI(
            # This is the default and can be omitted
            api_key=openai_key,
        )

        response = client.responses.create(
            model="gpt-4o",
            instructions="You are a helpful assistant",
            input=message,
        )

        return response.output_text


    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Sorry, I'm having trouble connecting to the AI service. Please try again."

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
