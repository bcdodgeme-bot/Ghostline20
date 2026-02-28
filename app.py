#===============================================================================
# SYNTAX PRIME V2 - MAIN APPLICATION FILE (app.py)
# Personal AI Assistant with Advanced Chat, File Processing, Authentication
# Created: 9/23/25 | Last Updated: 12/09/25
#
# This is the core FastAPI application that orchestrates all integrations:
# - Authentication & Session Management
# - AI Brain & Multi-Personality Chat System
# - Weather, Bluesky, RSS, Marketing Scraper, Prayer Times, Google Trends
# - Voice Synthesis & Image Generation
# - Telegram Notifications & Intelligence System
# - Web Interface & API Endpoints
#
# CHANGELOG 12/09/25:
# - FIXED: Merged duplicate @app.on_event("startup") handlers
# - FIXED: Removed duplicate state assignments
# - FIXED: Removed duplicate imports
# - FIXED: Section numbering collision
# - ADDED: Proper shutdown handler
# - ADDED: Named constants for background task intervals
# - ADDED: Google Workspace background tasks (token refresh, auto-sync)
#===============================================================================

#-- Section 1: Core Imports - 9/23/25
import os
import sys
import logging
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Cookie, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from modules.core.health import get_health_status
from modules.core.database import db_manager

#-- Section 2: Integration Module Imports - 9/23/25
from modules.integrations.slack_clickup import router as slack_clickup_router
from modules.integrations.slack_clickup import get_integration_info, check_module_health

#-- Section 2a: Weather Module Imports - added 9/24/25
from modules.integrations.weather import router as weather_router
from modules.integrations.weather import get_integration_info as weather_integration_info, check_module_health as weather_module_health

#-- Section 2b: Bluesky Multi-Account Integration - added 9/24/25
from modules.integrations.bluesky import router as bluesky_router
from modules.integrations.bluesky import get_integration_info as bluesky_integration_info, check_module_health as bluesky_module_health

#-- Section 2c: RSS Learning Integration - added 9/25/25
from modules.integrations.rss_learning import router as rss_learning_router
from modules.integrations.rss_learning import get_integration_info as rss_learning_integration_info, check_module_health as rss_learning_module_health, start_rss_service

#-- Section 2d: Marketing Scraper Integration - added 9/25/25
from modules.integrations.marketing_scraper import router as marketing_scraper_router
from modules.integrations.marketing_scraper import get_integration_info as marketing_scraper_integration_info, check_module_health as marketing_scraper_module_health

#-- Section 2e: Prayer Times Integration - added 9/26/25
from modules.integrations.prayer_times import router as prayer_times_router
from modules.integrations.prayer_times import get_integration_info as prayer_times_integration_info, check_module_health as prayer_times_module_health

#-- Section 2f: Google Trends Integration - added 9/27/25
from modules.integrations.google_trends.router import router as trends_router
from modules.integrations.google_trends.integration_info import check_module_health as trends_module_health, get_system_statistics as trends_system_statistics

#-- Section 2g: Voice Synthesis Integration - added 9/28/25
from modules.integrations.voice_synthesis import voice_synthesis_router
from modules.integrations.voice_synthesis import get_integration_info as voice_integration_info, check_module_health as voice_module_health

#-- Section 2h: Image Generation Integration - added 9/28/25
from modules.integrations.image_generation import router as image_generation_router
from modules.integrations.image_generation.integration_info import get_integration_info as image_integration_info, check_module_health as image_module_health

#-- Section 2i: Google Workspace Integration - added 9/30/25
from modules.integrations.google_workspace import router as google_workspace_router
from modules.integrations.google_workspace import get_integration_info as google_workspace_integration_info, check_module_health as google_workspace_module_health
from modules.integrations.google_workspace.background_tasks import start_background_tasks as start_google_background_tasks, stop_background_tasks as stop_google_background_tasks

#-- Section 2j: Telegram Notification System - added 10/12/25
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
from modules.integrations.telegram.notification_types.content_approval_notifications import ContentApprovalNotificationHandler

#-- Section 2k: Fathom Meeting Integration - added 10/16/25
from modules.integrations.fathom import router as fathom_router
from modules.integrations.fathom import get_integration_info as fathom_integration_info, check_module_health as fathom_module_health

#-- Section 2l: Intelligence Hub Integration - added 10/22/25
from modules.intelligence.intelligence_orchestrator import get_intelligence_orchestrator

#-- Section 2m: iOS Integration - added 12/16/25
from modules.integrations.ios import router as ios_router
from modules.integrations.ios import get_integration_info as ios_integration_info, check_module_health as ios_module_health

#-- Section 2n: Job Radar Integration - added 02/23/26
from modules.integrations.job_radar import router as job_radar_router
from modules.integrations.job_radar import get_integration_info as job_radar_integration_info, check_module_health as job_radar_module_health
from modules.integrations.job_radar.router import run_job_scan

#-- Section 3: AI Brain Module Imports - 9/23/25
from modules.ai import router as ai_router
from modules.ai import get_integration_info as ai_integration_info, check_module_health as ai_module_health

#-- Section 4: Chat Module Imports - 9/26/25
from modules.ai.chat import get_integration_info as chat_integration_info, check_module_health as chat_module_health

#-- Section 5: Authentication Module Imports - 9/23/25
from modules.core.auth import AuthManager, get_current_user

#-- Section 5a: Safe Logging Module Import - 01/13/26
from modules.core.safe_logger import init_safe_logging, get_safe_logger, log_summary

#-- Section 2L: Projects Router - added 2/4/26
from modules.ai.projects_router import router as projects_router

#-- Section 6: Logging Configuration - 9/30/25 (Updated 01/13/26 for thread-safe logging)
# Initialize thread-safe logging to prevent log interleaving from concurrent async operations
# This fixes the "stream of consciousness" log issue where multiple chat requests,
# intelligence collectors, and background tasks write multi-line content simultaneously
init_safe_logging(
    level=logging.DEBUG,
    format_string='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    use_structured=False  # Set to True for JSON logging (better for log aggregation)
)

logger = get_safe_logger(__name__)
logger.info("🔒 Thread-safe logging initialized for chat diagnostics")

#-- Section 7: Configuration Constants - 12/09/25
# Background task intervals (in seconds)
TASK_INTERVALS = {
    'session_cleanup': 3600,           # 1 hour
    'prayer_check': 300,               # 5 minutes
    'reminder_check': 60,              # 1 minute (internal to monitor_reminders)
    'calendar_check': 1800,            # 30 minutes
    'weather_collection': 7200,        # 2 hours
    'weather_notification': 1800,      # 30 minutes
    'email_check': 3600,               # 1 hour
    'clickup_check': 14400,            # 4 hours
    'clickup_sync': 14400,             # 4 hours
    'bluesky_notification': 14400,     # 4 hours
    'bluesky_scan': 5400,              # 90 minutes
    'trends_notification': 14400,      # 4 hours
    'trends_monitoring': 14400,        # 4 hours
    'analytics_check': 3600,           # 1 hour
    'content_approval': 30,            # 30 seconds
    'intelligence_cycle': 14400,       # 4 hours
    'daily_digest_check': 300,         # 5 minutes
    'startup_delay_trends': 600,       # 10 minutes
    'startup_delay_bluesky': 900,      # 15 minutes
    'startup_delay_clickup': 1200,     # 20 minutes
    'error_retry': 60,                 # 1 minute
    'error_retry_short': 300,          # 5 minutes
    'job_radar_scan': 14400,           # 4 hours
    'startup_delay_job_radar': 1500,   # 25 minutes
}

# Single user ID (intentionally hardcoded for single-user system)
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

#-- Section 8: FastAPI App Configuration - 9/23/25
app = FastAPI(
    title="Syntax Prime V2",
    description="Personal AI Assistant with Advanced Chat, File Processing, Authentication, and Memory System",
    version="2.0.0"
)

#-- Section 9: Request/Response Models for Authentication - 9/23/25
class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    message: str
    user: dict = None
    session_token: str = None

#-- Section 10: Static Files and Web Interface - 9/23/25
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Generated file downloads (CSVs, exports, etc.)
os.makedirs("web/downloads", exist_ok=True)
app.mount("/downloads", StaticFiles(directory="web/downloads"), name="downloads")

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

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login_direct():
    """Direct access to login page."""
    return await serve_login()

@app.get("/index.html", response_class=HTMLResponse)
async def serve_chat_direct():
    """Direct access to chat interface."""
    return await serve_chat()

#-- Section 11: Authentication Endpoints - 9/23/25
@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, response: Response):
    """Authenticate user and create session"""
    try:
        user_info = await AuthManager.authenticate_user(request.email, request.password)
        
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        session_token = await AuthManager.create_session(user_info)
        
        # Set session cookie (httpOnly for security)
        # NOTE: secure=True recommended for production with HTTPS (Railway uses HTTPS)
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=86400,  # 24 hours
            httponly=True,
            secure=os.getenv("ENVIRONMENT", "development") == "production",
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
    """Logout user and destroy session"""
    if session_token:
        destroyed = await AuthManager.destroy_session(session_token)
        if destroyed:
            logger.info("User logged out successfully")
    
    response.delete_cookie(key="session_token")
    return {"success": True, "message": "Logged out successfully"}

@app.get("/auth/me")
async def get_current_user_info(session_token: str = Cookie(None)):
    """Get current authenticated user information"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = await AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return {"user": user}

@app.get("/auth/sessions")
async def get_session_info(session_token: str = Cookie(None)):
    """Get session information (admin endpoint)"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = await AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return await AuthManager.get_session_info()

async def get_current_user_id(session_token: str = Cookie(None)) -> str:
    """Get current user ID from session - used by chat endpoints"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user = await AuthManager.validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return user['id']

#-- Section 12: Background Task Definitions - 10/12/25
# These are defined before startup so they can be referenced

async def session_cleanup_task():
    """Periodic cleanup of expired sessions"""
    logger.info("🔐 Session cleanup task started")
    while True:
        await asyncio.sleep(TASK_INTERVALS['session_cleanup'])
        await AuthManager.cleanup_expired_sessions()
        logger.debug("Session cleanup completed")

async def prayer_notification_task():
    """Check for prayer notifications every 5 minutes"""
    logger.info("🕌 Prayer notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_prayer_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['prayer_check'])
        except Exception as e:
            logger.error(f"Prayer notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

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
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_calendar_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['calendar_check'])
        except Exception as e:
            logger.error(f"Calendar notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def weather_collection_task():
    """Collect weather data from Tomorrow.io every 2 hours"""
    logger.info("🌡️ Weather collection task started")
    while True:
        try:
            from modules.integrations.weather.tomorrow_client import TomorrowClient
            from modules.integrations.weather.weather_processor import WeatherProcessor
            
            client = TomorrowClient()
            processor = WeatherProcessor()
            
            weather_data = await client.get_current_weather()
            reading_id = await processor.store_weather_reading(
                user_id=DEFAULT_USER_ID,
                weather_data=weather_data,
                location=None
            )
            
            logger.info(f"✅ Weather data collected and stored (reading_id: {reading_id})")
            await asyncio.sleep(TASK_INTERVALS['weather_collection'])
            
        except Exception as e:
            logger.error(f"Weather collection error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry_short'])

async def weather_notification_task():
    """Check for weather notifications every 30 minutes"""
    logger.info("🌤️ Weather notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_weather_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['weather_notification'])
        except Exception as e:
            logger.error(f"Weather notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def email_notification_task():
    """Check for email notifications every hour"""
    logger.info("📧 Email notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_email_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['email_check'])
        except Exception as e:
            logger.error(f"Email notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def clickup_notification_task():
    """Check for ClickUp notifications every 4 hours"""
    logger.info("📋 ClickUp notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_clickup_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['clickup_check'])
        except Exception as e:
            logger.error(f"ClickUp notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def bluesky_notification_task():
    """Check for Bluesky notifications every 4 hours"""
    logger.info("🦋 Bluesky notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_bluesky_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['bluesky_notification'])
        except Exception as e:
            logger.error(f"Bluesky notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def trends_notification_task():
    """Check for trending topics every 4 hours"""
    logger.info("📈 Trends notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_trends_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['trends_notification'])
        except Exception as e:
            logger.error(f"Trends notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def analytics_notification_task():
    """Check for analytics notifications (morning/evening summaries)"""
    logger.info("📊 Analytics notification task started")
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_analytics_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['analytics_check'])
        except Exception as e:
            logger.error(f"Analytics notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry'])

async def content_approval_notification_task():
    """Check content recommendation queue every 30 seconds"""
    logger.info("📝 Content approval notification task started")
    await asyncio.sleep(TASK_INTERVALS['content_approval'])  # Initial delay
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                await app.state.telegram_content_approval_handler.check_and_notify()
            await asyncio.sleep(TASK_INTERVALS['content_approval'])
        except Exception as e:
            logger.error(f"Content approval notification error: {e}")
            await asyncio.sleep(TASK_INTERVALS['content_approval'])

async def trends_monitoring_cycle_task():
    """Scan Google Trends and populate trend_opportunities every 4 hours"""
    logger.info("📈 Trends monitoring cycle task started")
    await asyncio.sleep(TASK_INTERVALS['startup_delay_trends'])  # Startup delay
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                logger.info("🔍 Running Google Trends monitoring cycle...")
                
                from modules.integrations.google_trends.keyword_monitor import KeywordMonitor
                
                monitor = KeywordMonitor(mode='normal')
                result = await monitor.run_monitoring_cycle()
                
                if result.get('success'):
                    logger.info(f"✅ Trends cycle complete: {result.get('keywords_monitored', 0)} keywords, "
                              f"{result.get('trends_fetched', 0)} trends, {result.get('alerts_created', 0)} opportunities created")
                else:
                    logger.error(f"❌ Trends cycle failed: {result.get('error', 'Unknown error')}")
            else:
                logger.info("📈 Trends monitoring cycle skipped (kill switch disabled)")
            
            await asyncio.sleep(TASK_INTERVALS['trends_monitoring'])
            
        except Exception as e:
            logger.error(f"Trends monitoring cycle error: {e}")
            await asyncio.sleep(TASK_INTERVALS['startup_delay_trends'])

async def bluesky_scanning_cycle_task():
    """Scan all 5 Bluesky accounts for engagement opportunities every 90 minutes"""
    logger.info("🦋 Bluesky scanning cycle task started")
    await asyncio.sleep(TASK_INTERVALS['startup_delay_bluesky'])  # Startup delay
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                logger.info("🔍 Scanning Bluesky accounts for engagement opportunities...")
                
                try:
                    import importlib
                    engagement_detector_module = importlib.import_module('modules.integrations.bluesky.engagement_detector')
                    EngagementDetector = getattr(engagement_detector_module, 'BlueskyEngagementDetector')
                    
                    detector = EngagementDetector()
                    results = await detector.scan_all_accounts()
                    
                except AttributeError:
                    logger.error("⚠️ EngagementDetector class not found in engagement_detector.py")
                    results = {}
                except Exception as scan_error:
                    logger.error(f"⚠️ Bluesky scanning failed: {scan_error}")
                    results = {}
                
                total_opportunities = sum(results.values())
                logger.info(f"✅ Bluesky scan complete: {total_opportunities} opportunities found across {len(results)} accounts")
                
                for account_id, count in results.items():
                    if count > 0:
                        logger.info(f"   🦋 {account_id}: {count} opportunities")
            else:
                logger.info("🦋 Bluesky scanning cycle skipped (kill switch disabled)")
            
            await asyncio.sleep(TASK_INTERVALS['bluesky_scan'])
            
        except Exception as e:
            logger.error(f"Bluesky scanning cycle error: {e}")
            await asyncio.sleep(TASK_INTERVALS['startup_delay_trends'])

async def clickup_sync_cycle_task():
    """Sync ClickUp tasks from API to database every 4 hours"""
    logger.info("📋 ClickUp sync cycle task started")
    await asyncio.sleep(TASK_INTERVALS['startup_delay_clickup'])  # Startup delay
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                logger.info("🔄 Syncing ClickUp tasks from API...")
                
                from modules.integrations.slack_clickup.clickup_sync_manager import ClickUpSyncManager
                
                sync_manager = ClickUpSyncManager()
                result = await sync_manager.sync_all_tasks()
                
                logger.info(f"✅ ClickUp sync complete: {result['tasks_synced']} tasks total "
                          f"({result['amcf_tasks']} AMCF, {result['personal_tasks']} Personal)")
                
                if result['errors']:
                    logger.error(f"⚠️ ClickUp sync had errors: {result['errors']}")
            else:
                logger.info("📋 ClickUp sync cycle skipped (kill switch disabled)")
            
            await asyncio.sleep(TASK_INTERVALS['clickup_sync'])
            
        except Exception as e:
            logger.error(f"ClickUp sync cycle error: {e}")
            await asyncio.sleep(TASK_INTERVALS['startup_delay_trends'])

async def intelligence_cycle_task():
    """Run complete intelligence cycle every 4 hours"""
    logger.info("🧠 Intelligence cycle task started")
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                logger.info("🧠 Running intelligence cycle...")
                
                orchestrator = get_intelligence_orchestrator(
                    db_manager=db_manager,
                    telegram_service=app.state.telegram_notification_manager,
                    user_id=DEFAULT_USER_ID
                )
                
                result = await orchestrator.run_intelligence_cycle()
                
                logger.info(f"✅ Intelligence cycle complete: {result['signals_collected']} signals, "
                          f"{result['situations_detected']} situations, "
                          f"{result['notifications_sent']} notifications sent")
            else:
                logger.info("🧠 Intelligence cycle skipped (kill switch disabled)")
            
            await asyncio.sleep(TASK_INTERVALS['intelligence_cycle'])
            
        except Exception as e:
            logger.error(f"Intelligence cycle error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry_short'])

async def job_radar_scan_task():
    """Run job radar scan every 4 hours"""
    await asyncio.sleep(TASK_INTERVALS['startup_delay_job_radar'])
    logger.info("🔍 Job Radar scan task started")
    
    while True:
        try:
            if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                logger.info("🔍 Running Job Radar scan...")
                
                # Get Gmail client for email notifications
                from modules.integrations.google_workspace.gmail_client import get_gmail_client
                gmail = get_gmail_client(DEFAULT_USER_ID)
                await gmail.initialize(DEFAULT_USER_ID)
                
                result = await run_job_scan(
                    telegram_service=app.state.telegram_notification_manager,
                )
                logger.info(
                    f"✅ Job Radar scan complete: "
                    f"{result.get('total_results', 0)} found, "
                    f"{result.get('ai_scored', 0)} scored, "
                    f"{result.get('high_matches', 0)} high matches"
                )
            else:
                logger.info("🔍 Job Radar scan skipped (kill switch disabled)")
            
            await asyncio.sleep(TASK_INTERVALS['job_radar_scan'])
        except Exception as e:
            logger.error(f"Job Radar scan error: {e}")
            await asyncio.sleep(TASK_INTERVALS['error_retry_short'])

async def daily_intelligence_digest_task():
    """Send daily intelligence digest at 8 AM Eastern Time"""
    logger.info("📊 Daily intelligence digest task started")
    
    while True:
        try:
            eastern = ZoneInfo('America/New_York')
            now = datetime.now(eastern)
            
            # Check if it's 8 AM (with 5-minute window)
            if now.hour == 8 and now.minute < 5:
                if await app.state.telegram_kill_switch.is_enabled(DEFAULT_USER_ID):
                    logger.info("📊 Sending daily intelligence digest...")
                    
                    orchestrator = get_intelligence_orchestrator(
                        db_manager=db_manager,
                        user_id=DEFAULT_USER_ID
                    )
                    
                    await orchestrator.run_daily_digest()
                    logger.info("✅ Daily digest sent successfully")
                    
                    # Sleep until next day (23 hours)
                    await asyncio.sleep(82800)
                else:
                    logger.info("📊 Daily digest skipped (kill switch disabled)")
                    await asyncio.sleep(82800)
            else:
                await asyncio.sleep(TASK_INTERVALS['daily_digest_check'])
            
        except Exception as e:
            logger.error(f"Daily digest error: {e}")
            await asyncio.sleep(TASK_INTERVALS['daily_digest_check'])

#-- Section 13: Application Lifecycle Events - MERGED 12/09/25
@app.on_event("startup")
async def startup_event():
    """
    Initialize database connection, integrations, and background services on startup.
    
    FIXED 12/09/25: Merged two separate startup handlers into one.
    ADDED 12/09/25: Google Workspace background tasks (token refresh, auto-sync).
    """
    print("🚀 Starting Syntax Prime V2...")
    
    # =========================================================================
    # PHASE 1: Core Infrastructure
    # =========================================================================
    
    # Connect to database
    await db_manager.connect()
    print("✅ Database connected")
    
    # =========================================================================
    # PHASE 2: Telegram Notification System
    # =========================================================================
    logger.info("🤖 Initializing Telegram notification system...")
    try:
        telegram_bot = TelegramBotClient(os.getenv('TELEGRAM_BOT_TOKEN'))
        telegram_kill_switch = KillSwitch()
        telegram_notification_manager = NotificationManager(telegram_bot, telegram_kill_switch)
        
        # Initialize all notification handlers
        prayer_handler = PrayerNotificationHandler(telegram_notification_manager)
        reminder_handler = ReminderNotificationHandler(telegram_notification_manager)
        calendar_handler = CalendarNotificationHandler(telegram_notification_manager)
        weather_handler = WeatherNotificationHandler(telegram_notification_manager)
        email_handler = EmailNotificationHandler(telegram_notification_manager)
        clickup_handler = ClickUpNotificationHandler(telegram_notification_manager)
        bluesky_handler = BlueskyNotificationHandler(telegram_notification_manager)
        trends_handler = TrendsNotificationHandler(telegram_notification_manager)
        analytics_handler = AnalyticsNotificationHandler(telegram_notification_manager)
        content_approval_handler = ContentApprovalNotificationHandler(telegram_notification_manager)
        
        # Store in app state (FIXED: no more duplicate assignments)
        app.state.telegram_notification_manager = telegram_notification_manager
        app.state.telegram_kill_switch = telegram_kill_switch
        app.state.telegram_prayer_handler = prayer_handler
        app.state.telegram_reminder_handler = reminder_handler
        app.state.telegram_calendar_handler = calendar_handler
        app.state.telegram_weather_handler = weather_handler
        app.state.telegram_email_handler = email_handler
        app.state.telegram_clickup_handler = clickup_handler
        app.state.telegram_bluesky_handler = bluesky_handler
        app.state.telegram_trends_handler = trends_handler
        app.state.telegram_analytics_handler = analytics_handler
        app.state.telegram_content_approval_handler = content_approval_handler
        
        # Verify bot connection
        bot_info = await telegram_bot.get_me()
        logger.info(f"✅ Telegram bot connected: @{bot_info.get('username')}")
        logger.info("✅ Telegram notification system initialized")
        
        # =====================================================================
        # PHASE 3: Start Background Tasks
        # =====================================================================
        asyncio.create_task(session_cleanup_task())
        asyncio.create_task(weather_collection_task())
        asyncio.create_task(prayer_notification_task())
        asyncio.create_task(reminder_notification_task())
        asyncio.create_task(calendar_notification_task())
        asyncio.create_task(weather_notification_task())
        asyncio.create_task(email_notification_task())
        asyncio.create_task(clickup_notification_task())
        asyncio.create_task(bluesky_notification_task())
        asyncio.create_task(trends_notification_task())
        asyncio.create_task(analytics_notification_task())
        asyncio.create_task(content_approval_notification_task())
        asyncio.create_task(trends_monitoring_cycle_task())
        asyncio.create_task(bluesky_scanning_cycle_task())
        asyncio.create_task(clickup_sync_cycle_task())
        asyncio.create_task(intelligence_cycle_task())
        asyncio.create_task(daily_intelligence_digest_task())
        asyncio.create_task(job_radar_scan_task())
        logger.info("🔍 Job Radar background scan task scheduled")
        
        # Google Workspace background tasks (token refresh, email/analytics/calendar sync)
        await start_google_background_tasks()
        
        logger.info("✅ All background tasks started")
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Failed to initialize Telegram: {e}")
        logger.error(traceback.format_exc())
    
    # =========================================================================
    # PHASE 4: Integration Health Checks
    # =========================================================================
    
    # Check Slack-ClickUp integration health
    try:
        integration_health = check_module_health()
        if integration_health['healthy']:
            logger.info("✅ Slack-ClickUp integration loaded successfully")
        else:
            logger.warning("⚠️ Slack-ClickUp integration loaded with warnings")
            logger.warning(f"   Missing vars: {integration_health['missing_vars']}")
    except Exception as e:
        logger.error(f"❌ Slack-ClickUp health check failed: {e}")
    
    # Check AI Brain health
    try:
        ai_health = ai_module_health()
        if ai_health['healthy']:
            logger.info("🧠 AI Brain loaded successfully")
        else:
            logger.warning("⚠️ AI Brain loaded with warnings")
            logger.warning(f"   Missing vars: {ai_health['missing_vars']}")
    except Exception as e:
        logger.error(f"❌ AI Brain health check failed: {e}")
    
    # Check Chat system health
    try:
        chat_health = chat_module_health()
        if chat_health['healthy']:
            logger.info("💬 Chat system loaded successfully")
            logger.info(f"   🔎 File upload support: {chat_health.get('file_upload_support', True)}")
            logger.info(f"   📄 Max file size: {chat_health.get('max_file_size', '10MB')}")
        else:
            logger.warning("⚠️ Chat system loaded with warnings")
            logger.warning(f"   Missing vars: {chat_health.get('missing_vars', [])}")
    except Exception as e:
        logger.error(f"❌ Chat system health check failed: {e}")
    
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
        trends_health = await trends_module_health()
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
    
    # Check Voice Synthesis integration health
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
    
    # Check Image Generation integration health
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
    
    # =========================================================================
    # PHASE 5: Final Setup
    # =========================================================================
    
    # Clean up any expired sessions on startup
    await AuthManager.cleanup_expired_sessions()
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
    print("   🎤 Voice Synthesis: http://localhost:8000/api/voice")
    print("   🎨 Image Generation: http://localhost:8000/integrations/image-generation")
    print("   🔗 API Docs: http://localhost:8000/docs")
    print("   🏥 Health Check: http://localhost:8000/health")
    print("   🔐 Authentication: /auth/login, /auth/logout")
    print("=" * 50)
    print("\n💡 Don't forget to create a user account with:")
    print("   python standalone_create_user.py")
    print()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup on application shutdown.
    ADDED 12/09/25: Proper shutdown handler.
    ADDED 12/09/25: Google Workspace background tasks shutdown.
    """
    logger.info("🛑 Shutting down Syntax Prime V2...")
    
    # Stop Google Workspace background tasks
    try:
        await stop_google_background_tasks()
        logger.info("✅ Google Workspace background tasks stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping Google background tasks: {e}")
    
    # Close database connection
    try:
        await db_manager.disconnect()
        logger.info("✅ Database disconnected")
    except Exception as e:
        logger.error(f"❌ Error disconnecting database: {e}")
    
    # Note: Background tasks will be cancelled automatically by asyncio
    # when the event loop shuts down
    
    logger.info("✅ Shutdown complete")

#-- Section 14: API Status and Health Endpoints - 9/28/25
@app.get("/health")
async def health_check():
    """System health check endpoint"""
    return await get_health_status()

@app.get("/api/health/voice")
async def voice_health():
    """Voice Synthesis integration health check"""
    return await voice_module_health()

@app.get("/api/health/image")
async def image_health():
    """Image Generation integration health check"""
    return await image_module_health()

@app.get("/api/health/trends")
async def trends_health():
    """Google Trends integration health check"""
    return await trends_module_health()

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
            "🎤 Voice synthesis with ElevenLabs (4 personality voices)",
            "🎨 AI image generation with Replicate (inline display)",
            "📱 Mobile-responsive web interface",
            "⏰ Timezone-aware user management"
        ],
        "integrations": [
            "slack-clickup", "ai-brain", "chat-system", "weather",
            "bluesky-multi-account", "rss-learning", "marketing-scraper",
            "prayer-times", "google-trends", "voice-synthesis",
            "image-generation", "fathom-meetings", "authentication"
        ],
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
            "voice_synthesize": "/api/voice/synthesize",
            "voice_audio": "/api/voice/audio",
            "voice_health": "/api/health/voice",
            "image_generate": "/integrations/image-generation/generate",
            "image_quick": "/integrations/image-generation/quick-generate",
            "image_health": "/api/health/image",
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
            "api_configured": True
        },
        "google_trends_system": {
            "features": ["trending_keyword_analysis", "real_time_search_monitoring", "market_research_insights", "content_planning"],
            "commands": ["trends [keyword]", "trending topics", "search volume"],
            "data_sources": "google_trends_api",
            "analysis_types": ["regional", "temporal", "related_queries", "rising_searches"],
            "api_configured": trends_module_health()['healthy']
        },
        "voice_synthesis_system": {
            "features": ["elevenlabs_text_to_speech", "personality_voice_mapping", "database_audio_caching", "inline_playback"],
            "commands": ["voice synthesize [text]", "voice history", "voice personalities"],
            "voices_configured": 4,
            "personalities": {"syntaxprime": "Adam", "syntaxbot": "Josh", "nil_exe": "Daniel", "ggpt": "Sam"},
            "audio_format": "MP3",
            "caching": "database_with_compression",
            "api_configured": voice_module_health()['healthy']
        },
        "image_generation_system": {
            "features": ["replicate_ai_generation", "inline_base64_display", "smart_model_selection", "multiple_format_downloads"],
            "commands": ["image create [prompt]", "image blog [topic]", "image social [content]", "image history"],
            "models_supported": ["Stable Diffusion XL", "SDXL Lightning", "Realistic Vision"],
            "formats": ["PNG", "JPG", "WebP"],
            "content_types": ["blog", "social", "marketing", "illustration"],
            "api_configured": image_module_health()['healthy']
        }
    }

#-- Section 15: Integrations Info Endpoint - 9/30/25
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
            'health': await trends_module_health()
        }
    except Exception as e:
        integrations['google_trends'] = {
            'info': {'module': 'google_trends', 'status': 'failed'},
            'health': {'healthy': False, 'error': str(e)}
        }
    
    # Voice Synthesis integration
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
    
    # Image Generation integration
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
    
    # Google Workspace integration
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
    try:
        session_info = await AuthManager.get_session_info()
        auth_health = {
            'healthy': True,
            'active_sessions': session_info.get("active_sessions", 0)
        }
    except Exception as e:
        auth_health = {
            'healthy': False,
            'error': str(e)
        }
    
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
        'health': auth_health
    }
    
    return {
        'integrations': integrations,
        'total_modules': len(integrations),
        'healthy_modules': sum(1 for module in integrations.values() if module['health'].get('healthy', False)),
        'timestamp': datetime.now().isoformat()
    }

#-- Section 16: Integration Module Routers - 9/30/25
app.include_router(slack_clickup_router)
app.include_router(ai_router)
app.include_router(weather_router)
app.include_router(bluesky_router)
app.include_router(rss_learning_router)
app.include_router(marketing_scraper_router)
app.include_router(prayer_times_router)
app.include_router(trends_router, prefix="/api/trends", tags=["Google Trends"])
app.include_router(voice_synthesis_router)
app.include_router(image_generation_router)
app.include_router(google_workspace_router)
app.include_router(telegram_router, prefix="/integrations", tags=["telegram"])
app.include_router(fathom_router)
app.include_router(ios_router)
app.include_router(projects_router)
app.include_router(job_radar_router, tags=["Job Radar"])

#-- Section 17: Development Server - 9/23/25
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
