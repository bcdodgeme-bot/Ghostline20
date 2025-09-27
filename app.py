#-- Section 1: Core Imports - 9/23/25
import os
import logging
from fastapi import FastAPI, HTTPException, Cookie, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from datetime import datetime

import time  # Add this with your other imports

from modules.core.health import get_health_status
from modules.core.database import db_manager

#-- Section 2: Integration Module Imports - 9/23/25
from modules.integrations.slack_clickup import router as slack_clickup_router
from modules.integrations.slack_clickup import get_integration_info, check_module_health

#-- NEW Section 2a: Weather Module Imports - added 9/24/25
from modules.integrations.weather import router as weather_router
from modules.integrations.weather import get_integration_info as weather_integration_info, check_module_health as weather_module_health

#-- NEW Section 2b: Bluesky Multi-Account Integration - added 9/24/25
from modules.integrations.bluesky import router as bluesky_router
from modules.integrations.bluesky import get_integration_info as bluesky_integration_info, check_module_health as bluesky_module_health

#-- NEW Section 2c: RSS Learning Integration - added 9/25/25
from modules.integrations.rss_learning import router as rss_learning_router
from modules.integrations.rss_learning import get_integration_info as rss_learning_integration_info, check_module_health as rss_learning_module_health, start_rss_service

#-- NEW Section 2d: Marketing Scraper Integration - added 9/25/25
from modules.integrations.marketing_scraper import router as marketing_scraper_router
from modules.integrations.marketing_scraper import get_integration_info as marketing_scraper_integration_info, check_module_health as marketing_scraper_module_health

#-- NEW Section 2e: Prayer Times Integration - added 9/26/25
from modules.integrations.prayer_times import router as prayer_times_router
from modules.integrations.prayer_times import get_integration_info as prayer_times_integration_info, check_module_health as prayer_times_module_health

#-- Section 3: AI Brain Module Imports - 9/23/25
from modules.ai import router as ai_router
from modules.ai import get_integration_info as ai_integration_info, check_module_health as ai_module_health

#-- Section 4: FIXED Chat Module Imports - 9/26/25
# FIXED: Import helper functions from chat.py, but not router (router handles endpoints)
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

#-- Section 10: Application Lifecycle Events - updated 9/25/25 with Marketing Scraper
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
            print(f"   📁 File upload support: {chat_health.get('file_upload_support', True)}")
            print(f"   📏 Max file size: {chat_health.get('max_file_size', '10MB')}")
        else:
            print("⚠️  Chat system loaded with warnings")
            print(f"   Missing vars: {chat_health.get('missing_vars', [])}")
    except Exception as e:
        print(f"⚠️  Chat system health check failed: {e}")
    
    # Check Weather integration health
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
    
    # Check Bluesky integration health
    try:
        bluesky_health = bluesky_module_health()
        if bluesky_health['healthy']:
            print("🔵 Bluesky integration loaded successfully")
            configured_accounts = bluesky_health.get('configured_accounts', 0)
            print(f"   📱 {configured_accounts}/5 accounts configured")
            print("   🤖 Multi-account AI assistant army ready")
            print("   ⏰ 3.5-hour scan intervals with approval-first workflow")
        else:
            print("⚠️  Bluesky integration loaded with warnings")
            print(f"   Missing vars: {bluesky_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️  Bluesky integration health check failed: {e}")
    
    # Check RSS Learning integration health
    try:
        rss_health = rss_learning_module_health()
        if rss_health['healthy']:
            print("📰 RSS Learning integration loaded successfully")
            source_count = rss_health.get('total_sources', 8)
            print(f"   🌐 {source_count} RSS sources configured")
            print("   🧠 AI-powered content analysis active")
            print("   📈 Weekly background processing enabled")
            print("   🎯 Marketing insights for AI brain integration")
            
            # Start RSS background service
            await start_rss_service()
            print("   ⚡ RSS background processor started")
        else:
            print("⚠️  RSS Learning integration loaded with warnings")
            print(f"   Missing vars: {rss_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️  RSS Learning integration health check failed: {e}")
    
    # NEW: Check Marketing Scraper integration health - added 9/25/25
    try:
        scraper_health = marketing_scraper_module_health()
        if scraper_health['healthy']:
            print("🔍 Marketing Scraper integration loaded successfully")
            print("   🌐 Website content extraction enabled")
            print("   🧠 AI-powered competitive analysis with SyntaxPrime")
            print("   💾 Permanent storage for scraped insights")
            print("   💬 Chat commands: scrape [URL], scrape history, scrape insights")
            print("   🔗 Integration with existing AI brain and memory system")
        else:
            print("⚠️  Marketing Scraper integration loaded with warnings")
            print(f"   Missing vars: {scraper_health['missing_vars']}")
            if scraper_health.get('warnings'):
                for warning in scraper_health['warnings']:
                    print(f"   ⚠️  {warning}")
    except Exception as e:
        print(f"⚠️  Marketing Scraper integration health check failed: {e}")
    
    # Check Prayer Times integration health - NEW 9/26/25
    try:
        prayer_health = prayer_times_module_health()
        if prayer_health['healthy']:
            print("🕌 Prayer Times integration loaded successfully")
            print("   📅 Daily prayer schedule calculation")
            print("   🌙 Islamic calendar integration")
            print("   💬 Chat commands: prayer times, how long till prayer")
            print("   🕰️ Real-time prayer countdown")
        else:
            print("⚠️  Prayer Times integration loaded with warnings")
            print(f"   Missing vars: {prayer_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️  Prayer Times integration health check failed: {e}")
    
    # Clean up any expired sessions on startup
    AuthManager.cleanup_expired_sessions()
    print("🔐 Authentication system initialized")
    
    # Startup summary
    print("\n🌟 Syntax Prime V2 - System Ready!")
    print("=" * 50)
    print("   📱 Web Interface: http://localhost:8000/ (login)")
    print("   💬 Chat Interface: http://localhost:8000/chat")
    print("   🌦️ Weather API: http://localhost:8000/integrations/weather")
    print("   🔵 Bluesky API: http://localhost:8000/bluesky")
    print("   📰 RSS Learning: http://localhost:8000/integrations/rss")
    print("   🔍 Marketing Scraper: http://localhost:8000/integrations/marketing-scraper")  # NEW
    print("   🕌 Prayer Times: http://localhost:8000/integrations/prayer-times")  # NEW
    print("   🔗 API Docs: http://localhost:8000/docs")
    print("   🏥 Health Check: http://localhost:8000/health")
    print("   🔐 Authentication: /auth/login, /auth/logout")
    print("=" * 50)
    print("\n💡 Don't forget to create a user account with:")
    print("   python standalone_create_user.py")
    print()

#-- Section 11: API Status and Health Endpoints - updated 9/26/25 with Prayer Times
@app.get("/health")
async def health_check():
    """System health check endpoint - THE MISSING PIECE!"""
    return await get_health_status()

@app.get("/api/status")
async def api_status():
    """Comprehensive API status endpoint with system information."""
    return {
        "message": "Syntax Prime V2 - Personal AI Assistant",
        "version": "2.0.0",
        "architecture": "modular_chat_system_with_auth",
        "features": [
            "🔐 Secure user authentication with bcrypt",
            "📄 Advanced file processing (images, PDFs, CSVs, text)",
            "🧠 250K context memory system",
            "🎭 Multi-personality AI chat (4 personalities)",
            "📖 Smart bookmark system with conversation navigation",
            "📚 21K knowledge base integration",
            "🌊 Real-time conversation streaming",
            "🌦️ Health-focused weather monitoring with Tomorrow.io",
            "🔵 Multi-account Bluesky social media assistant (5 accounts)",
            "📰 RSS Learning system with AI-powered marketing insights",
            "🔍 AI-powered marketing scraper for competitive analysis",
            "🕌 Islamic prayer times with intelligent scheduling",  # NEW 9/26/25
            "📱 Mobile-responsive web interface",
            "⏰ Timezone-aware user management"
        ],
        "integrations": ["slack-clickup", "ai-brain", "chat-system", "weather", "bluesky-multi-account", "rss-learning", "marketing-scraper", "prayer-times", "authentication"],  # UPDATED
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
            "bluesky_scan": "/bluesky/scan",
            "bluesky_opportunities": "/bluesky/opportunities",
            "bluesky_approve": "/bluesky/approve",
            "bluesky_post": "/bluesky/post",
            "bluesky_accounts": "/bluesky/accounts/status",
            "rss_status": "/integrations/rss/status",
            "rss_insights": "/integrations/rss/insights",
            "rss_trends": "/integrations/rss/trends",
            "rss_writing_inspiration": "/integrations/rss/writing-inspiration",
            "marketing_scraper_health": "/integrations/marketing-scraper/health",
            "marketing_scraper_stats": "/integrations/marketing-scraper/stats",
            "marketing_scraper_history": "/integrations/marketing-scraper/history",
            "prayer_times_status": "/integrations/prayer-times/status",  # NEW 9/26/25
            "prayer_times_health": "/integrations/prayer-times/health",  # NEW 9/26/25
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
        },
        "bluesky_social_management": {
            "accounts_supported": 5,
            "features": ["keyword_intelligence", "engagement_suggestions", "approval_workflow", "cross_account_opportunities"],
            "scan_interval": "3.5 hours",
            "personalities": ["syntaxprime", "professional", "compassionate"],
            "api_configured": bluesky_module_health()['healthy']
        },
        "rss_learning_system": {
            "sources_configured": 8,
            "features": ["ai_content_analysis", "marketing_insights", "trend_identification", "writing_assistance"],
            "processing_interval": "weekly",
            "categories": ["seo", "content_marketing", "social_media", "analytics"],
            "api_configured": rss_learning_module_health()['healthy']
        },
        "marketing_scraper_system": {
            "features": ["website_content_extraction", "ai_competitive_analysis", "permanent_insight_storage", "chat_integration"],
            "commands": ["scrape [URL]", "scrape history", "scrape insights"],
            "storage": "postgresql_scraped_content_table",
            "ai_integration": "syntaxprime_personality",
            "api_configured": marketing_scraper_module_health()['healthy']
        },
        "prayer_times_system": {  # NEW 9/26/25
            "features": ["daily_prayer_scheduling", "islamic_calendar_integration", "chat_commands", "aladhan_api"],
            "commands": ["How long till [prayer]?", "What are prayer times today?", "Islamic date"],
            "calculation_method": "ISNA",
            "location": "Merrifield, Virginia",
            "cache_system": "midnight_refresh",
            "api_configured": True  # AlAdhan API is free, no key needed
        }
    }

@app.get("/integrations")
async def integrations_info():
    """Get information about loaded integrations."""
    integrations = {}
    
    # Slack-ClickUp integration
    try:
        integrations['slack_clickup'] = {
            'info': get_integration_info(),
            'health': check_module_health()
        }
    except Exception as e:
        integrations['slack_clickup'] = {
            'info': {'module': 'slack_clickup', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Weather integration
    try:
        integrations['weather'] = {
            'info': weather_integration_info(),
            'health': weather_module_health()
        }
    except Exception as e:
        integrations['weather'] = {
            'info': {'module': 'weather', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Bluesky integration
    try:
        integrations['bluesky'] = {
            'info': bluesky_integration_info(),
            'health': bluesky_module_health()
        }
    except Exception as e:
        integrations['bluesky'] = {
            'info': {'module': 'bluesky', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # RSS Learning integration
    try:
        integrations['rss_learning'] = {
            'info': rss_learning_integration_info(),
            'health': rss_learning_module_health()
        }
    except Exception as e:
        integrations['rss_learning'] = {
            'info': {'module': 'rss_learning', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Marketing Scraper integration
    try:
        integrations['marketing_scraper'] = {
            'info': marketing_scraper_integration_info(),
            'health': marketing_scraper_module_health()
        }
    except Exception as e:
        integrations['marketing_scraper'] = {
            'info': {'module': 'marketing_scraper', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Prayer Times integration - NEW 9/26/25
    try:
        integrations['prayer_times'] = {
            'info': prayer_times_integration_info(),
            'health': prayer_times_module_health()
        }
    except Exception as e:
        integrations['prayer_times'] = {
            'info': {'module': 'prayer_times', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # AI Brain integration
    try:
        integrations['ai_brain'] = {
            'info': ai_integration_info(),
            'health': ai_module_health()
        }
    except Exception as e:
        integrations['ai_brain'] = {
            'info': {'module': 'ai_brain', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Chat integration
    try:
        integrations['chat'] = {
            'info': chat_integration_info(),
            'health': chat_module_health()
        }
    except Exception as e:
        integrations['chat'] = {
            'info': {'module': 'chat', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Authentication system info
    integrations['authentication'] = {
        'info': {
            "name": "User Authentication System",
            "version": "1.0.0",
            "features": [
                "bcrypt password hashing",
                "session management",
                "timezone support",
                "secure cookies"
            ]
        },
        'health': {
            'healthy': True,
            'active_sessions': AuthManager.get_session_info()["active_sessions"]
        }
    }
    
    return {
        'integrations': integrations,
        'total_modules': len(integrations),
        'healthy_modules': sum(1 for module in integrations.values() if module['health'].get('healthy', False)),
        'timestamp': datetime.now().isoformat()
    }

#-- Section 12: Integration Module Routers - updated 9/26/25 with Prayer Times
# Include Slack-ClickUp integration router
app.include_router(slack_clickup_router)

# Include AI Brain router (this includes the chat endpoints now)
app.include_router(ai_router)

# REMOVED: Chat router inclusion (it's now handled by ai_router)
# The chat.py file is now a helper module, not a router

# Include Weather integration router - added 9/24/25
app.include_router(weather_router)

# Include Bluesky Multi-Account integration router - added 9/24/25
app.include_router(bluesky_router)

# Include RSS Learning integration router - added 9/25/25
app.include_router(rss_learning_router)

# Include Marketing Scraper integration router - added 9/25/25
app.include_router(marketing_scraper_router)

# Include Prayer Times integration router - added 9/26/25
app.include_router(prayer_times_router)

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
