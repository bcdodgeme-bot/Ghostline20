#-- Section 1: Core Imports - 9/23/25
import os
import logging
from fastapi import FastAPI, HTTPException, Cookie, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import time  # Add this with your other imports

from modules.core.health import get_health_status
from modules.core.database import db_manager

#-- Section 2: Integration Module Imports - 9/23/25
from modules.integrations.slack_clickup import router as slack_clickup_router
from modules.integrations.slack_clickup import get_integration_info, check_module_health

#-- NEW Section 2a: Weather Module Imports - added 9/24/25
from modules.integrations.weather import router as weather_router
from modules.integrations.weather import get_integration_info as weather_integration_info, check_module_health as weather_module_health


#-- Section 3: AI Brain Module Imports - 9/23/25
from modules.ai import router as ai_router
from modules.ai import get_integration_info as ai_integration_info, check_module_health as ai_module_health

#-- Section 4: Chat Module Imports - 9/23/25
from modules.ai.chat import router as chat_router
from modules.ai.chat import get_integration_info as chat_integration_info, check_module_health as chat_module_health

#-- Section 5: Authentication Module Imports - 9/23/25
from modules.core.auth import AuthManager, get_current_user

# Setup logging
logger = logging.getLogger(__name__)

#-- Section 6: FastAPI App Configuration - 9/23/25
app = FastAPI(
    title="Syntax Prime V2",
    description="Personal AI Assistant with Advanced Chat, File Processing, Authentication, and Memory System",
    version="2.0.0"
)

#-- Section 7: Request/Response Models for Authentication - 9/23/25
class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    message: str
    user: dict = None
    session_token: str = None

#-- Section 8: Static Files and Web Interface - 9/23/25
# Mount static files (CSS, JS, images, favicon)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Serve the main web interface
@app.get("/", response_class=HTMLResponse)
async def serve_login():
    """Serve the login page as the main entry point."""
    try:
        with open("web/login.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Syntax Prime V2</h1><p>Web interface not found. Please ensure web/ directory exists.</p>",
            status_code=404
        )

@app.get("/chat", response_class=HTMLResponse)
async def serve_chat():
    """Serve the main chat interface."""
    try:
        with open("web/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Chat interface not found</h1>",
            status_code=404
        )

@app.get("/style.css")
async def serve_css():
    """Serve the CSS file."""
    try:
        return FileResponse("web/style.css", media_type="text/css")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="CSS file not found")

@app.get("/script.js")
async def serve_js():
    """Serve the JavaScript file."""
    try:
        return FileResponse("web/script.js", media_type="application/javascript")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="JavaScript file not found")

# Alternative routes for direct access
@app.get("/login.html", response_class=HTMLResponse)
async def serve_login_direct():
    """Direct access to login page."""
    return await serve_login()

@app.get("/index.html", response_class=HTMLResponse)
async def serve_chat_direct():
    """Direct access to chat interface."""
    return await serve_chat()

#-- Section 9: Authentication Endpoints - 9/23/25
@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, response: Response):
    """
    Authenticate user and create session
    """
    try:
        # Authenticate user
        user_info = await AuthManager.authenticate_user(request.email, request.password)
        
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Create session
        session_token = AuthManager.create_session(user_info)
        
        # Set session cookie (httpOnly for security)
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=86400,  # 24 hours
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
        
        logger.info(f"User logged in: {user_info['email']}")
        
        return AuthResponse(
            success=True,
            message="Login successful",
            user=user_info,
            session_token=session_token
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.post("/auth/logout")
async def logout(response: Response, session_token: str = Cookie(None)):
    """
    Logout user and destroy session
    """
    if session_token:
        destroyed = AuthManager.destroy_session(session_token)
        if destroyed:
            logger.info("User logged out successfully")
    
    # Clear session cookie
    response.delete_cookie(key="session_token")
    
    return {"success": True, "message": "Logged out successfully"}

@app.get("/auth/me")
async def get_current_user_info(session_token: str = Cookie(None)):
    """
    Get current authenticated user information
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return {"user": user}

@app.get("/auth/sessions")
async def get_session_info(session_token: str = Cookie(None)):
    """
    Get session information (admin endpoint)
    """
    # Verify admin access (for now, just check if user is authenticated)
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return AuthManager.get_session_info()

# Updated dependency function for chat endpoints
async def get_current_user_id(session_token: str = Cookie(None)) -> str:
    """Get current user ID from session - used by chat endpoints"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user = AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return user['id']

#-- Section 10: Application Lifecycle Events - 9/23/25
#-- Section 10: Application Lifecycle Events - updated 9/24/25
@app.on_event("startup")
async def startup_event():
    """Initialize database connection and integrations on startup."""
    print("🚀 Starting Syntax Prime V2...")
    
    # Connect to database
    await db_manager.connect()
    print("✅ Database connected")
    
    # Check Slack-ClickUp integration health
    integration_health = check_module_health()
    if integration_health['healthy']:
        print("✅ Slack-ClickUp integration loaded successfully")
    else:
        print("⚠️  Slack-ClickUp integration loaded with warnings")
        print(f"   Missing vars: {integration_health['missing_vars']}")
    
    # Check AI Brain health
    ai_health = ai_module_health()
    if ai_health['healthy']:
        print("🧠 AI Brain loaded successfully")
    else:
        print("⚠️  AI Brain loaded with warnings")
        print(f"   Missing vars: {ai_health['missing_vars']}")
    
    # Check Chat system health
    try:
        chat_health = chat_module_health()
        if chat_health['healthy']:
            print("💬 Chat system loaded successfully")
            print(f"   📎 File upload support: {chat_health.get('file_upload_support', True)}")
            print(f"   📏 Max file size: {chat_health.get('max_file_size', '10MB')}")
        else:
            print("⚠️  Chat system loaded with warnings")
            print(f"   Missing vars: {chat_health.get('missing_vars', [])}")
    except Exception as e:
        print(f"⚠️  Chat system health check failed: {e}")
    
    # NEW: Check Weather integration health - added 9/24/25
    try:
        weather_health = weather_module_health()
        if weather_health['healthy']:
            print("🌦️ Weather integration loaded successfully")
            print("   📊 Pressure tracking for headache prediction active")
            print("   ☀️ UV monitoring for sun sensitivity enabled")
        else:
            print("⚠️  Weather integration loaded with warnings")
            print(f"   Missing vars: {weather_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️  Weather integration health check failed: {e}")
    
    # Clean up any expired sessions on startup
    AuthManager.cleanup_expired_sessions()
    print("🔐 Authentication system initialized")
    
    # Startup summary
    print("\n🌟 Syntax Prime V2 - System Ready!")
    print("=" * 50)
    print("   📱 Web Interface: http://localhost:8000/ (login)")
    print("   💬 Chat Interface: http://localhost:8000/chat")
    print("   🌦️ Weather API: http://localhost:8000/integrations/weather")  # NEW
    print("   🔗 API Docs: http://localhost:8000/docs")
    print("   🏥 Health Check: http://localhost:8000/health")
    print("   🔐 Authentication: /auth/login, /auth/logout")
    print("=" * 50)
    print("\n💡 Don't forget to create a user account with:")
    print("   python standalone_create_user.py")
    print()

#-- Section 11: API Status and Info Endpoints - updated 9/24/25
#-- Section 11: API Status, Info, and Health Check Endpoints - updated 9/24/25
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration and system monitoring"""
    try:
        health_status = await get_health_status()
        
        # Return 200 OK if healthy, 503 if unhealthy
        if health_status["status"] == "healthy":
            return health_status
        else:
            raise HTTPException(status_code=503, detail=health_status)
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
        )

@app.get("/api/status")
async def api_status():
    """Comprehensive API status endpoint with system information."""
    return {
        "message": "Syntax Prime V2 - Personal AI Assistant",
        "version": "2.0.0",
        "architecture": "modular_chat_system_with_auth",
        "features": [
            "🔐 Secure user authentication with bcrypt",
            "📁 Advanced file processing (images, PDFs, CSVs, text)",
            "🧠 250K context memory system",
            "🎭 Multi-personality AI chat (4 personalities)",
            "📖 Smart bookmark system with conversation navigation",
            "📚 21K knowledge base integration",
            "🌊 Real-time conversation streaming",
            "🌦️ Health-focused weather monitoring with Tomorrow.io",
            "📱 Mobile-responsive web interface",
            "⏰ Timezone-aware user management"
        ],
        "integrations": ["slack-clickup", "ai-brain", "chat-system", "weather", "authentication"],
        "endpoints": {
            "web_interface": "/",
            "chat_interface": "/chat",
            "health": "/health",
            "integrations": "/integrations",
            "api_docs": "/docs",
            "auth_login": "/auth/login",
            "auth_logout": "/auth/logout",
            "auth_me": "/auth/me",
            "ai_chat": "/ai/chat",
            "ai_chat_stream": "/ai/chat/stream",
            "ai_bookmarks": "/ai/bookmarks",
            "ai_conversations": "/ai/conversations",
            "ai_personalities": "/ai/personalities",
            "ai_stats": "/ai/stats",
            "weather_current": "/integrations/weather/current",
            "weather_alerts": "/integrations/weather/alerts",
            "weather_status": "/integrations/weather/status",
            "slack_webhooks": "/integrations/slack-clickup/slack/events"
        },
        "file_processing": {
            "supported_types": ["images", "pdfs", "text", "csv", "markdown"],
            "max_file_size": "10MB",
            "features": ["OCR", "computer_vision", "data_analysis", "text_extraction"]
        },
        "weather_monitoring": {
            "provider": "tomorrow.io",
            "health_features": ["pressure_tracking", "uv_monitoring", "headache_prediction"],
            "thresholds": {"pressure_drop": "3.0 mbar", "uv_protection": "4.0 index"},
            "api_configured": weather_module_health()['healthy']
        }
    }

@app.get("/integrations")
async def integrations_info():
    """Get information about loaded integrations."""
    return {
        "integrations": {
            "slack_clickup": get_integration_info(),
            "ai_brain": ai_integration_info(),
            "chat_system": chat_integration_info(),
            "weather": weather_integration_info(),
            "authentication": {
                "name": "User Authentication System",
                "version": "1.0.0",
                "features": [
                    "bcrypt password hashing",
                    "session management",
                    "timezone support",
                    "secure cookies"
                ],
                "active_sessions": AuthManager.get_session_info()["active_sessions"]
            }
        }
    }

#-- Section 12: Integration Module Routers - 9/23/25
#-- Section 12: Integration Module Routers - updated 9/24/25
# Include Slack-ClickUp integration router
app.include_router(slack_clickup_router)

# Include AI Brain router
app.include_router(ai_router)

# Include Chat router with file upload support
# Need to patch the dependency in chat router to use our session-based auth
import modules.ai.chat as chat_module
chat_module.get_current_user_id = get_current_user_id
app.include_router(chat_router)

# NEW: Include Weather integration router - added 9/24/25
app.include_router(weather_router)

#-- Section 13: Development Server and Periodic Tasks - 9/23/25
# Periodic cleanup of expired sessions (every hour)
@app.on_event("startup")
async def setup_periodic_tasks():
    """Set up periodic maintenance tasks"""
    import asyncio
    
    async def session_cleanup():
        while True:
            await asyncio.sleep(3600)  # Wait 1 hour
            AuthManager.cleanup_expired_sessions()
    
    # Start the cleanup task in the background
    asyncio.create_task(session_cleanup())

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    
    print("🚀 Starting Syntax Prime V2 Development Server...")
    print(f"   Server: http://localhost:{port}")
    print(f"   Login: http://localhost:{port}/")
    print(f"   Chat: http://localhost:{port}/chat")
    print(f"   API Docs: http://localhost:{port}/docs")
    print(f"   Health: http://localhost:{port}/health")
    print()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        reload=False  # Set to True for development
    )
