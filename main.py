from fastapi import FastAPI, Request, Form, HTTPException, Depends
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
from datetime import datetime
from contextlib import asynccontextmanager
from openai import OpenAI
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import mcp_server_tools, SseServerParams
from autogen_core import CancellationToken
from autogen_agentchat.agents import AssistantAgent
from mcp.types import TextContent
import json

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info(f"🚀 Server starting at {datetime.fromtimestamp(server_start_time)}")
    logger.info(f"🔐 New session secret generated - all existing sessions cleared")

    yield

    # Shutdown (if needed)
    logger.info("👋 Server shutting down...")

app = FastAPI(title="Roambee Chat App", lifespan=lifespan)

# Add session middleware with new secret key (clears all existing sessions)
app.add_middleware(SessionMiddleware, secret_key=session_secret)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

def check_session_valid(request: Request):
    """Check if user has valid session (came from config page)"""
    # Check if session exists and is from current server instance
    authenticated = request.session.get("authenticated", False)
    session_start_time = request.session.get("server_start_time", 0)

    # Invalidate session if it's from a previous server instance
    if authenticated and session_start_time != server_start_time:
        request.session.clear()
        return False

    return authenticated

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
    """Validate OpenAI and Roambee API keys"""
    # Placeholder for validation logic - user will provide this 
    openai_valid = await validate_openai_key(openai_key)
    roambee_valid = await validate_roambee_key(roambee_key)

    if openai_valid and roambee_valid:
        # Store keys in session with server start time
        request.session["authenticated"] = True
        request.session["openai_key"] = openai_key
        request.session["roambee_key"] = roambee_key
        request.session["server_start_time"] = server_start_time

        # Validate MCP connection
        mcp_tools = await validate_roambee_sse_connection(roambee_key)
        if not mcp_tools:
            return {"status": "error", "message": "Failed to connect to Roambee MCP server"}

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
    response = False
    try:
        mcp_tools = await validate_roambee_sse_connection(roambee_key)
        model_client = OpenAIChatCompletionClient(model="o4-mini-2025-04-16", api_key=openai_key)
        agent = AssistantAgent(
                name="Roambee_MCP_Agent",
                model_client=model_client,
                tools=mcp_tools,
                reflect_on_tool_use=True)

        result = await agent.run(task=message, cancellation_token=CancellationToken())
        if result and result.messages:
            # for msg in result.messages:
            #     response = msg.content
            res_json = result.messages[-1].content
        return res_json
    except Exception as e:
        logger.error(f"Error in chat_with_agent: {e}")
        return f"Sorry, an error occurred while processing your request.\n{e}"

@app.post("/send-message")
async def send_message(
    request: Request,
    message: str = Form(...)
):
    """Send message and get AI response"""
    logger.debug("🔍 Checking session validity:")
    logger.debug(f"   Session authenticated: {request.session.get('authenticated', False)}")
    logger.debug(f"   Session start time: {request.session.get('server_start_time', 0)}")
    logger.debug(f"   Server start time: {server_start_time}")
    logger.debug(f"   Session valid: {check_session_valid(request)}")

    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get chat history from session
    chat_history = request.session.get("chat_history", [])

    # Add user message
    chat_history.append({"role": "user", "content": message})

    # Placeholder for AI response - integrate with OpenAI API

    # Use MCP tools with agent if available
    agent_response = await chat_with_agent(message, request.session.get("openai_key"), request.session.get("roambee_key"))
    if agent_response:
        chat_history.append({"role": "assistant", "content": agent_response})
    else:
        ai_response = await get_ai_response(message, request.session.get("openai_key"))
        chat_history.append({"role": "assistant", "content": ai_response})

    # Update session
    request.session["chat_history"] = chat_history

    return {"response": chat_history[-1]["content"], "chat_history": chat_history}

@app.get("/chat-history")
async def get_chat_history(request: Request):
    """Get chat history for current session"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"chat_history": request.session.get("chat_history", [])}

@app.post("/clear-session")
async def clear_session(request: Request):
    """Clear session data"""
    request.session.clear()
    return {"status": "success"}

@app.post("/reset-config")
async def reset_config(request: Request):
    """Reset to configuration page"""
    if not check_session_valid(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    clear_session(request)

    # Keep authentication but clear chat history
    request.session["chat_history"] = []
    return {"status": "success", "redirect": "/"}

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
            model="o4-mini-2025-04-16",
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
