#===============================================================================
# SYNTAX PRIME V2 - MAIN APPLICATION FILE (app.py)
# Personal AI Assistant with Advanced Chat, File Processing, Authentication
# Created: 9/23/25 | Last Updated: 9/28/25
#
# This is the core FastAPI application that orchestrates all integrations:
# - Authentication & Session Management
# - AI Brain & Multi-Personality Chat System
# - Weather, Bluesky, RSS, Marketing Scraper, Prayer Times, Google Trends
# - Voice Synthesis & Image Generation (NEW 9/28/25)
# - Web Interface & API Endpoints
#===============================================================================

#-- Section 1: Core Imports - 9/23/25
import os
import logging
from fastapi import FastAPI, HTTPException, Cookie, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from datetime import datetime

import time  # Add this with your other imports

import asyncio

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

#-- NEW Section 2i: Intelligence Hub Integration - added 10/22/25
from modules.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
from zoneinfo import ZoneInfo

#-- NEW Section 2c: RSS Learning Integration - added 9/25/25
from modules.integrations.rss_learning import router as rss_learning_router
from modules.integrations.rss_learning import get_integration_info as rss_learning_integration_info, check_module_health as rss_learning_module_health, start_rss_service

#-- NEW Section 2d: Marketing Scraper Integration - added 9/25/25
from modules.integrations.marketing_scraper import router as marketing_scraper_router
from modules.integrations.marketing_scraper import get_integration_info as marketing_scraper_integration_info, check_module_health as marketing_scraper_module_health

#-- NEW Section 2e: Prayer Times Integration - added 9/26/25
from modules.integrations.prayer_times import router as prayer_times_router
from modules.integrations.prayer_times import get_integration_info as prayer_times_integration_info, check_module_health as prayer_times_module_health

#-- NEW Section 2f: Google Trends Integration - added 9/27/25
from modules.integrations.google_trends.router import router as trends_router
from modules.integrations.google_trends.integration_info import check_module_health as trends_module_health, get_system_statistics as trends_system_statistics

#-- NEW Section 2g: Voice Synthesis Integration - added 9/28/25
from modules.integrations.voice_synthesis import voice_synthesis_router
from modules.integrations.voice_synthesis import get_integration_info as voice_integration_info, check_module_health as voice_module_health

#-- NEW Section 2h: Image Generation Integration - added 9/28/25
from modules.integrations.image_generation import router as image_generation_router
from modules.integrations.image_generation.integration_info import get_integration_info as image_integration_info, check_module_health as image_module_health

#-- NEW Section 2i: Google Workspace Integration - added 9/30/25
from modules.integrations.google_workspace import router as google_workspace_router
from modules.integrations.google_workspace import get_integration_info as google_workspace_integration_info, check_module_health as google_workspace_module_health

#-- NEW Section 2j: Telegram Notification System - added 10/12/25
from modules.integrations.telegram.router import router as telegram_router
from modules.integrations.telegram.notification_manager import NotificationManager
from modules.integrations.telegram.bot_client import TelegramBotClient
from modules.integrations.telegram.kill_switch import KillSwitch
from modules.integrations.telegram.notification_types.prayer_notifications import PrayerNotificationHandler
from modules.integrations.telegram.notification_types.reminder_notifications import ReminderNotificationHandler
from modules.integrations.telegram.notification_types.calendar_notifications import CalendarNotificationHandler
from modules.integrations.telegram.notification_types.weather_notifications import WeatherNotificationHandler
from modules.integrations.telegram.notification_types.email_notifications import EmailNotificationHandler
from modules.integrations.telegram.notification_types.clickup_notifications import ClickUpNotificationHandler
from modules.integrations.telegram.notification_types.bluesky_notifications import BlueskyNotificationHandler
from modules.integrations.telegram.notification_types.trends_notifications import TrendsNotificationHandler
from modules.integrations.telegram.notification_types.analytics_notifications import AnalyticsNotificationHandler

#-- NEW Section 2k: Fathom Meeting Integration - added 10/16/25
from modules.integrations.fathom import router as fathom_router
from modules.integrations.fathom import get_integration_info as fathom_integration_info, check_module_health as fathom_module_health

#-- Section 3: AI Brain Module Imports - 9/23/25
from modules.ai import router as ai_router
from modules.ai import get_integration_info as ai_integration_info, check_module_health as ai_module_health

#-- Section 4: FIXED Chat Module Imports - 9/26/25
# FIXED: Import helper functions from chat.py, but not router (router handles endpoints)
from modules.ai.chat import get_integration_info as chat_integration_info, check_module_health as chat_module_health

#-- Section 5: Authentication Module Imports - 9/23/25
from modules.core.auth import AuthManager, get_current_user

#-- Section 5.5: Enhanced Logging Configuration - 9/30/25
# Configure root logger to DEBUG level to capture all router.py debug messages
import logging

# Set up logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Outputs to console/Railway logs
    ]
)

# Setup app logger
logger = logging.getLogger(__name__)
logger.info("🔧 DEBUG logging enabled for chat diagnostics")

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

#-- Section 10: Application Lifecycle Events - updated 9/28/25 with Voice & Image
@app.on_event("startup")
async def startup_event():
    """Initialize database connection and integrations on startup."""
    print("🚀 Starting Syntax Prime V2...")
    
    # Connect to database
    await db_manager.connect()
    print("✅ Database connected")
    
    # Initialize Telegram notification system - added 10/12/25
    logger.info("🤖 Initializing Telegram notification system...")
    try:
        telegram_bot = TelegramBotClient(os.getenv('TELEGRAM_BOT_TOKEN'))
        telegram_kill_switch = KillSwitch()
        telegram_notification_manager = NotificationManager(telegram_bot, telegram_kill_switch)
        
        
        prayer_handler = PrayerNotificationHandler(telegram_notification_manager)
        reminder_handler = ReminderNotificationHandler(telegram_notification_manager)
        calendar_handler = CalendarNotificationHandler(telegram_notification_manager)
        weather_handler = WeatherNotificationHandler(telegram_notification_manager)
        email_handler = EmailNotificationHandler(telegram_notification_manager)
        clickup_handler = ClickUpNotificationHandler(telegram_notification_manager)
        bluesky_handler = BlueskyNotificationHandler(telegram_notification_manager)  # lowercase "s"
        trends_handler = TrendsNotificationHandler(telegram_notification_manager)
        analytics_handler = AnalyticsNotificationHandler(telegram_notification_manager)
    
        
        # Store in app state for access throughout the app
        app.state.telegram_notification_manager = telegram_notification_manager
        app.state.telegram_prayer_handler = prayer_handler
        app.state.telegram_reminder_handler = reminder_handler
        app.state.telegram_calendar_handler = calendar_handler
        app.state.telegram_weather_handler = weather_handler
        app.state.telegram_email_handler = email_handler
        app.state.telegram_clickup_handler = clickup_handler
        app.state.telegram_bluesky_handler = bluesky_handler
        app.state.telegram_trends_handler = trends_handler
        app.state.telegram_analytics_handler = analytics_handler
        app.state.telegram_kill_switch = telegram_kill_switch
        app.state.telegram_kill_switch = telegram_kill_switch
        
        # Verify bot connection
        bot_info = await telegram_bot.get_me()
        logger.info(f"✅ Telegram bot connected: @{bot_info.get('username')}")
        
        logger.info("✅ Telegram notification system initialized")
        
        # Start background notification tasks
        asyncio.create_task(prayer_notification_task())
        asyncio.create_task(reminder_notification_task())
        asyncio.create_task(calendar_notification_task())
        asyncio.create_task(weather_notification_task())
        asyncio.create_task(email_notification_task())
        asyncio.create_task(clickup_notification_task())
        asyncio.create_task(bluesky_notification_task())
        asyncio.create_task(trends_notification_task())
        asyncio.create_task(analytics_notification_task())
        asyncio.create_task(intelligence_cycle_task())
        asyncio.create_task(daily_intelligence_digest_task())

        
    except Exception as e:
        import traceback
        logger.error(f"❌ Failed to initialize Telegram: {e}")
        logger.error(traceback.format_exc())
        
    # Check Slack-ClickUp integration health
    integration_health = check_module_health()
    if integration_health['healthy']:
        print("✅ Slack-ClickUp integration loaded successfully")
    else:
        print("⚠️ Slack-ClickUp integration loaded with warnings")
        print(f"   Missing vars: {integration_health['missing_vars']}")
    
    # Check AI Brain health
    ai_health = ai_module_health()
    if ai_health['healthy']:
        print("🧠 AI Brain loaded successfully")
    else:
        print("⚠️ AI Brain loaded with warnings")
        print(f"   Missing vars: {ai_health['missing_vars']}")
    
    # Check Chat system health
    try:
        chat_health = chat_module_health()
        if chat_health['healthy']:
            print("💬 Chat system loaded successfully")
            print(f"   🔎 File upload support: {chat_health.get('file_upload_support', True)}")
            print(f"   📄 Max file size: {chat_health.get('max_file_size', '10MB')}")
        else:
            print("⚠️ Chat system loaded with warnings")
            print(f"   Missing vars: {chat_health.get('missing_vars', [])}")
    except Exception as e:
        print(f"⚠️ Chat system health check failed: {e}")
    
    # Check Weather integration health
    try:
        weather_health = weather_module_health()
        if weather_health['healthy']:
            print("🌦️ Weather integration loaded successfully")
            print("   📊 Pressure tracking for headache prediction active")
            print("   ☀️ UV monitoring for sun sensitivity enabled")
        else:
            print("⚠️ Weather integration loaded with warnings")
            print(f"   Missing vars: {weather_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Weather integration health check failed: {e}")
    
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
            print("⚠️ Bluesky integration loaded with warnings")
            print(f"   Missing vars: {bluesky_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Bluesky integration health check failed: {e}")
    
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
            print("⚠️ RSS Learning integration loaded with warnings")
            print(f"   Missing vars: {rss_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ RSS Learning integration health check failed: {e}")
    
    # Check Marketing Scraper integration health
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
            print("⚠️ Marketing Scraper integration loaded with warnings")
            print(f"   Missing vars: {scraper_health['missing_vars']}")
            if scraper_health.get('warnings'):
                for warning in scraper_health['warnings']:
                    print(f"   ⚠️ {warning}")
    except Exception as e:
        print(f"⚠️ Marketing Scraper integration health check failed: {e}")
    
    # Check Prayer Times integration health
    try:
        prayer_health = prayer_times_module_health()
        if prayer_health['healthy']:
            print("🕌 Prayer Times integration loaded successfully")
            print("   📅 Daily prayer schedule calculation")
            print("   🌙 Islamic calendar integration")
            print("   💬 Chat commands: prayer times, how long till prayer")
            print("   🕰️ Real-time prayer countdown")
        else:
            print("⚠️ Prayer Times integration loaded with warnings")
            print(f"   Missing vars: {prayer_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Prayer Times integration health check failed: {e}")
    
    # Check Google Trends integration health
    try:
        trends_health = trends_module_health()
        if trends_health['healthy']:
            print("📈 Google Trends integration loaded successfully")
            print("   🔍 Trending keyword analysis enabled")
            print("   📊 Real-time search trend monitoring")
            print("   💬 Chat commands: trends [keyword], trending topics")
            print("   🎯 Market research and content planning insights")
        else:
            print("⚠️ Google Trends integration loaded with warnings")
            print(f"   Missing vars: {trends_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Google Trends integration health check failed: {e}")
    
    # Check Voice Synthesis integration health - NEW 9/28/25
    try:
        voice_health = voice_module_health()
        if voice_health['healthy']:
            print("🎤 Voice Synthesis integration loaded successfully")
            print("   🗣️ ElevenLabs text-to-speech enabled")
            print("   🎭 Personality-specific voice selection")
            print("   💾 Database audio caching with compression")
            print("   💬 Chat commands: voice synthesize [text], voice history")
            print("   🔊 Inline audio playback ready")
        else:
            print("⚠️ Voice Synthesis integration loaded with warnings")
            print(f"   Missing vars: {voice_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Voice Synthesis integration health check failed: {e}")
    
    # Check Image Generation integration health - NEW 9/28/25
    try:
        image_health = image_module_health()
        if image_health['healthy']:
            print("🎨 Image Generation integration loaded successfully")
            print("   🖼️ Replicate AI image generation enabled")
            print("   💡 Smart model selection for content types")
            print("   📱 Inline base64 display ready")
            print("   💬 Chat commands: image create [prompt], image history")
            print("   📥 Multiple format downloads available")
        else:
            print("⚠️ Image Generation integration loaded with warnings")
            print(f"   Missing vars: {image_health['missing_vars']}")
    except Exception as e:
        print(f"⚠️ Image Generation integration health check failed: {e}")
    
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
    print("   🔍 Marketing Scraper: http://localhost:8000/integrations/marketing-scraper")
    print("   🕌 Prayer Times: http://localhost:8000/integrations/prayer-times")
    print("   📈 Google Trends: http://localhost:8000/api/trends")
    print("   🎤 Voice Synthesis: http://localhost:8000/api/voice")  # NEW
    print("   🎨 Image Generation: http://localhost:8000/integrations/image-generation")  # NEW
    print("   🔗 API Docs: http://localhost:8000/docs")
    print("   🏥 Health Check: http://localhost:8000/health")
    print("   🔐 Authentication: /auth/login, /auth/logout")
    print("=" * 50)
    print("\n💡 Don't forget to create a user account with:")
    print("   python standalone_create_user.py")
    print()

#-- Section 10a: Telegram Background Tasks - added 10/12/25
USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

async def prayer_notification_task():
    """Check for prayer notifications every 5 minutes"""
    logger.info("🕌 Prayer notification task started")
    while True:
        try:
            # CHECK FIRST (like reminders do)
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_prayer_handler.check_and_notify()
            
            # THEN SLEEP (not before)
            await asyncio.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"Prayer notification error: {e}")
            await asyncio.sleep(60)

async def reminder_notification_task():
    """Monitor reminders continuously"""
    logger.info("⏰ Reminder notification task started")
    try:
        await app.state.telegram_reminder_handler.monitor_reminders()
    except Exception as e:
        logger.error(f"Reminder monitor error: {e}")

async def calendar_notification_task():
    """Check for calendar notifications every 30 minutes"""
    logger.info("📅 Calendar notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_calendar_handler.check_and_notify()
            await asyncio.sleep(1800)  # 30 minutes
        except Exception as e:
            logger.error(f"Calendar notification error: {e}")
            await asyncio.sleep(60)

async def weather_notification_task():
    """Check for weather notifications every 2 hours"""
    logger.info("🌤️ Weather notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_weather_handler.check_and_notify()
            await asyncio.sleep(7200)  # 2 hours
        except Exception as e:
            logger.error(f"Weather notification error: {e}")
            await asyncio.sleep(60)

async def email_notification_task():
    """Check for email notifications every hour"""
    logger.info("📧 Email notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_email_handler.check_and_notify()
            await asyncio.sleep(3600)  # 1 hour
        except Exception as e:
            logger.error(f"Email notification error: {e}")
            await asyncio.sleep(60)

async def clickup_notification_task():
    """Check for ClickUp notifications every 4 hours"""
    logger.info("📋 ClickUp notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_clickup_handler.check_and_notify()
            await asyncio.sleep(14400)  # 4 hours
        except Exception as e:
            logger.error(f"ClickUp notification error: {e}")
            await asyncio.sleep(60)

async def bluesky_notification_task():
    """Check for Bluesky notifications every 4 hours"""
    logger.info("🦋 Bluesky notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_bluesky_handler.check_and_notify()
            await asyncio.sleep(14400)  # 4 hours
        except Exception as e:
            logger.error(f"Bluesky notification error: {e}")
            await asyncio.sleep(60)

async def trends_notification_task():
    """Check for trending topics every 4 hours"""
    logger.info("📈 Trends notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_trends_handler.check_and_notify()
            await asyncio.sleep(14400)  # 4 hours
        except Exception as e:
            logger.error(f"Trends notification error: {e}")
            await asyncio.sleep(60)

async def analytics_notification_task():
    """Check for analytics notifications (morning/evening summaries)"""
    logger.info("📊 Analytics notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                await app.state.telegram_analytics_handler.check_and_notify()
            # Check every hour to catch 8 AM and 8 PM windows
            await asyncio.sleep(3600)  # 1 hour
        except Exception as e:
            logger.error(f"Analytics notification error: {e}")
            await asyncio.sleep(60)

async def intelligence_cycle_task():
    """
    Run complete intelligence cycle every 4 hours
    Collects signals, detects situations, sends notifications
    """
    logger.info("🧠 Intelligence cycle task started")
    
    while True:
        try:
            # Check kill switch
            if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                logger.info("🧠 Running intelligence cycle...")
                
                # Initialize orchestrator
                orchestrator = IntelligenceOrchestrator(USER_ID)
                
                # Run the cycle
                result = await orchestrator.run_intelligence_cycle()
                
                logger.info(f"✅ Intelligence cycle complete: {result['signals_collected']} signals, "
                          f"{result['situations_detected']} situations, "
                          f"{result['notifications_sent']} notifications sent")
            else:
                logger.info("🧠 Intelligence cycle skipped (kill switch disabled)")
            
            # Wait 4 hours
            await asyncio.sleep(14400)  # 4 hours = 14400 seconds
            
        except Exception as e:
            logger.error(f"Intelligence cycle error: {e}")
            await asyncio.sleep(300)  # Retry after 5 minutes on error


async def daily_intelligence_digest_task():
    """
    Send daily intelligence digest at 8 AM Eastern Time
    Summary of situations, user responses, and learnings
    """
    logger.info("📊 Daily intelligence digest task started")
    
    while True:
        try:
            # Get current time in Eastern timezone
            eastern = ZoneInfo('America/New_York')
            now = datetime.now(eastern)
            
            # Check if it's 8 AM (with 5-minute window)
            if now.hour == 8 and now.minute < 5:
                # Check kill switch
                if await app.state.telegram_kill_switch.is_enabled(USER_ID):
                    logger.info("📊 Sending daily intelligence digest...")
                    
                    # Initialize orchestrator
                    orchestrator = IntelligenceOrchestrator(USER_ID)
                    
                    # Generate and send digest
                    await orchestrator.generate_and_send_daily_digest()
                    
                    logger.info("✅ Daily digest sent successfully")
                    
                    # Sleep until next day (23 hours to ensure we catch tomorrow's window)
                    await asyncio.sleep(82800)  # 23 hours
                else:
                    logger.info("📊 Daily digest skipped (kill switch disabled)")
                    await asyncio.sleep(82800)  # Sleep until tomorrow
            else:
                # Not 8 AM yet, check again in 5 minutes
                await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Daily digest error: {e}")
            await asyncio.sleep(300)  # Retry after 5 minutes on error

#-- Section 11: API Status and Health Endpoints - updated 9/28/25 with Voice & Image
@app.get("/health")
async def health_check():
    """System health check endpoint - THE MISSING PIECE!"""
    return await get_health_status()

# NEW: Voice Synthesis health check endpoint - added 9/28/25
@app.get("/api/health/voice")
async def voice_health():
    """Voice Synthesis integration health check"""
    return voice_module_health()

# NEW: Image Generation health check endpoint - added 9/28/25
@app.get("/api/health/image")
async def image_health():
    """Image Generation integration health check"""
    return image_module_health()

# Google Trends health check endpoint - added 9/27/25
@app.get("/api/health/trends")
async def trends_health():
    """Google Trends integration health check"""
    return await trends_module_health()

# Google Trends statistics endpoint - added 9/27/25
@app.get("/api/statistics/trends")
async def trends_statistics():
    """Google Trends system statistics"""
    return await trends_system_statistics()

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
            "🕌 Islamic prayer times with intelligent scheduling",
            "📈 Google Trends analysis for market research",
            "🎙️ Fathom meeting integration with AI summaries",
            "🎤 Voice synthesis with ElevenLabs (4 personality voices)",  # NEW 9/28/25
            "🎨 AI image generation with Replicate (inline display)",  # NEW 9/28/25
            "📱 Mobile-responsive web interface",
            "⏰ Timezone-aware user management"
        ],
        "integrations": ["slack-clickup", "ai-brain", "chat-system", "weather", "bluesky-multi-account", "rss-learning", "marketing-scraper", "prayer-times", "google-trends", "voice-synthesis", "image-generation", "fathom-meetings", "authentication"],  # UPDATED
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
            "prayer_times_status": "/integrations/prayer-times/status",
            "prayer_times_health": "/integrations/prayer-times/health",
            "google_trends_main": "/api/trends",
            "google_trends_health": "/api/health/trends",
            "google_trends_stats": "/api/statistics/trends",
            "voice_synthesize": "/api/voice/synthesize",  # NEW 9/28/25
            "voice_audio": "/api/voice/audio",  # NEW 9/28/25
            "voice_health": "/api/health/voice",  # NEW 9/28/25
            "image_generate": "/integrations/image-generation/generate",  # NEW 9/28/25
            "image_quick": "/integrations/image-generation/quick-generate",  # NEW 9/28/25
            "image_health": "/api/health/image",  # NEW 9/28/25
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
        "prayer_times_system": {
            "features": ["daily_prayer_scheduling", "islamic_calendar_integration", "chat_commands", "aladhan_api"],
            "commands": ["How long till [prayer]?", "What are prayer times today?", "Islamic date"],
            "calculation_method": "ISNA",
            "location": "Merrifield, Virginia",
            "cache_system": "midnight_refresh",
            "api_configured": True  # AlAdhan API is free, no key needed
        },
        "google_trends_system": {
            "features": ["trending_keyword_analysis", "real_time_search_monitoring", "market_research_insights", "content_planning"],
            "commands": ["trends [keyword]", "trending topics", "search volume"],
            "data_sources": "google_trends_api",
            "analysis_types": ["regional", "temporal", "related_queries", "rising_searches"],
            "api_configured": trends_module_health()['healthy']
        },
        "voice_synthesis_system": {  # NEW 9/28/25
            "features": ["elevenlabs_text_to_speech", "personality_voice_mapping", "database_audio_caching", "inline_playback"],
            "commands": ["voice synthesize [text]", "voice history", "voice personalities"],
            "voices_configured": 4,
            "personalities": {"syntaxprime": "Adam", "syntaxbot": "Josh", "nil_exe": "Daniel", "ggpt": "Sam"},
            "audio_format": "MP3",
            "caching": "database_with_compression",
            "api_configured": voice_module_health()['healthy']
        },
        "image_generation_system": {  # NEW 9/28/25
            "features": ["replicate_ai_generation", "inline_base64_display", "smart_model_selection", "multiple_format_downloads"],
            "commands": ["image create [prompt]", "image blog [topic]", "image social [content]", "image history"],
            "models_supported": ["Stable Diffusion XL", "SDXL Lightning", "Realistic Vision"],
            "formats": ["PNG", "JPG", "WebP"],
            "content_types": ["blog", "social", "marketing", "illustration"],
            "api_configured": image_module_health()['healthy']
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
    
    # Prayer Times integration
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
    
    # Google Trends integration
    try:
        integrations['google_trends'] = {
            'info': {
                "name": "Google Trends Integration",
                "version": "1.0.0",
                "features": [
                    "trending keyword analysis",
                    "real-time search monitoring",
                    "market research insights",
                    "content planning assistance"
                ]
            },
            'health': trends_module_health()
        }
    except Exception as e:
        integrations['google_trends'] = {
            'info': {'module': 'google_trends', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Voice Synthesis integration - NEW 9/28/25
    try:
        integrations['voice_synthesis'] = {
            'info': voice_integration_info(),
            'health': voice_module_health()
        }
    except Exception as e:
        integrations['voice_synthesis'] = {
            'info': {'module': 'voice_synthesis', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Image Generation integration - NEW 9/28/25
    try:
        integrations['image_generation'] = {
            'info': image_integration_info(),
            'health': image_module_health()
        }
    except Exception as e:
        integrations['image_generation'] = {
            'info': {'module': 'image_generation', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Google Workspace integration - added 9/30/25
    try:
        integrations['google_workspace'] = {
            'info': google_workspace_integration_info(),
            'health': google_workspace_module_health()
        }
    except Exception as e:
        integrations['google_workspace'] = {
            'info': {'module': 'google_workspace', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Fathom Meeting integration
    try:
        integrations['fathom_meetings'] = {
            'info': fathom_integration_info(),
            'health': fathom_module_health()
        }
    except Exception as e:
        integrations['fathom_meetings'] = {
            'info': {'module': 'fathom_meetings', 'status': 'failed'},
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

#-- Section 12: Integration Module Routers - updated 9/28/25 with Voice & Image
#-- Section 12: Integration Module Routers - updated 9/30/25 with Google Workspace
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

# Include Google Trends integration router - added 9/27/25
app.include_router(trends_router, prefix="/api/trends", tags=["Google Trends"])

# Include Voice Synthesis integration router - added 9/28/25
app.include_router(voice_synthesis_router)

# Include Image Generation integration router - added 9/28/25
app.include_router(image_generation_router)

# Include Google Workspace integration router - added 9/30/25
app.include_router(google_workspace_router)

# Include Telegram notification router - added 10/12/25
app.include_router(telegram_router, prefix="/integrations", tags=["telegram"])

# Include Fathom meeting integration router - added 10/16/25
app.include_router(fathom_router)

#-- Section 13: Development Server and Periodic Tasks - updated 9/27/25 with Prayer Notifications
# Periodic cleanup of expired sessions (every hour) + Prayer notification service
@app.on_event("startup")
async def setup_periodic_tasks():
    """Set up periodic maintenance tasks and background services"""
    import asyncio
    
    async def session_cleanup():
        while True:
            await asyncio.sleep(3600)  # Wait 1 hour
            AuthManager.cleanup_expired_sessions()
    
    # Start the cleanup task in the background
    asyncio.create_task(session_cleanup())
    
    # Start prayer notification service - added 9/27/25
    try:
        from modules.integrations.prayer_times.notification_manager import start_prayer_notifications
        await start_prayer_notifications()
        print("🕌 Prayer notification service started successfully")
    except Exception as e:
        print(f"⚠️ Failed to start prayer notification service: {e}")
        # Continue without prayer notifications rather than crash the app

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
