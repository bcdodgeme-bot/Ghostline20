# modules/integrations/google_workspace/background_tasks.py
"""
Google Workspace Background Tasks
Proactive token refresh and automatic data synchronization

This module handles:
1. Proactive token refresh (every 45 min - before expiry)
2. Automatic email sync (every 30 min)
3. Automatic Analytics sync (every 8 hours)
4. Automatic Search Console sync (every 8 hours)
5. Automatic Calendar sync (every 1 hour)

All tasks run in the background without user intervention.

Usage:
    from modules.integrations.google_workspace.background_tasks import google_background_tasks
    
    # In your FastAPI startup:
    @app.on_event("startup")
    async def startup():
        await google_background_tasks.start()
    
    @app.on_event("shutdown")
    async def shutdown():
        await google_background_tasks.stop()
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

from . import SUPPORTED_SITES
from modules.core.database import db_manager

# Single user ID (intentionally hardcoded for single-user system)
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

# =============================================================================
# CONFIGURATION - Intervals in seconds
# =============================================================================

TOKEN_REFRESH_INTERVAL = 45 * 60      # 45 minutes
EMAIL_SYNC_INTERVAL = 30 * 60         # 30 minutes
ANALYTICS_SYNC_INTERVAL = 8 * 3600    # 8 hours
SEARCH_CONSOLE_SYNC_INTERVAL = 8 * 3600  # 8 hours
CALENDAR_SYNC_INTERVAL = 60 * 60      # 1 hour

# Initial delay before first run (let app fully start)
STARTUP_DELAY = 30  # 30 seconds

# Maximum consecutive errors before pausing a task
MAX_CONSECUTIVE_ERRORS = 5
ERROR_BACKOFF_MINUTES = 30  # Pause for 30 min after max errors


class GoogleWorkspaceBackgroundTasks:
    """
    Manages all background tasks for Google Workspace integration.
    
    Tasks:
    - Token refresh: Keeps OAuth tokens fresh before they expire
    - Email sync: Periodically fetches new emails
    - Analytics sync: Updates traffic data for all sites
    - Search Console sync: Updates keyword data for all sites
    - Calendar sync: Keeps calendar events current
    """
    
    def __init__(self):
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._last_run: Dict[str, datetime] = {}
        self._last_success: Dict[str, datetime] = {}
        self._error_counts: Dict[str, int] = {}
        self._paused_until: Dict[str, datetime] = {}
        self._user_id: Optional[str] = None
        
        logger.info("🔄 Google Workspace Background Tasks initialized")
    
    async def start(self):
        """Start all background tasks"""
        if self._running:
            logger.warning("⚠️ Background tasks already running")
            return
        
        logger.info("🚀 Starting Google Workspace background tasks...")
        
        # Get user_id (single user system)
        self._user_id = await self._get_user_id()
        if not self._user_id:
            logger.error("❌ No user found - background tasks will not start")
            return
        
        self._running = True
        
        # Start each task
        self._tasks['token_refresh'] = asyncio.create_task(
            self._run_periodic_task('token_refresh', TOKEN_REFRESH_INTERVAL, self._refresh_tokens)
        )
        
        self._tasks['email_sync'] = asyncio.create_task(
            self._run_periodic_task('email_sync', EMAIL_SYNC_INTERVAL, self._sync_emails)
        )
        
        self._tasks['analytics_sync'] = asyncio.create_task(
            self._run_periodic_task('analytics_sync', ANALYTICS_SYNC_INTERVAL, self._sync_analytics)
        )
        
        self._tasks['search_console_sync'] = asyncio.create_task(
            self._run_periodic_task('search_console_sync', SEARCH_CONSOLE_SYNC_INTERVAL, self._sync_search_console)
        )
        
        self._tasks['calendar_sync'] = asyncio.create_task(
            self._run_periodic_task('calendar_sync', CALENDAR_SYNC_INTERVAL, self._sync_calendar)
        )
        
        logger.info("✅ All background tasks started")
        logger.info(f"   📝 Token refresh: every {TOKEN_REFRESH_INTERVAL // 60} minutes")
        logger.info(f"   📧 Email sync: every {EMAIL_SYNC_INTERVAL // 60} minutes")
        logger.info(f"   📊 Analytics sync: every {ANALYTICS_SYNC_INTERVAL // 3600} hours")
        logger.info(f"   🔍 Search Console sync: every {SEARCH_CONSOLE_SYNC_INTERVAL // 3600} hours")
        logger.info(f"   📅 Calendar sync: every {CALENDAR_SYNC_INTERVAL // 60} minutes")
    
    async def stop(self):
        """Stop all background tasks gracefully"""
        if not self._running:
            return
        
        logger.info("🛑 Stopping Google Workspace background tasks...")
        self._running = False
        
        # Cancel all tasks
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.debug(f"   Stopped: {name}")
        
        self._tasks.clear()
        logger.info("✅ All background tasks stopped")
    
    async def _get_user_id(self) -> Optional[str]:
        """Get the user ID (single user system - hardcoded)"""
        # Single user system - use hardcoded ID to avoid database mismatch
        logger.info(f"📌 Background tasks will run for user: {DEFAULT_USER_ID}")
        return DEFAULT_USER_ID
    
    async def _run_periodic_task(self, task_name: str, interval: int, task_func):
        """
        Run a task periodically with error handling and backoff
        
        Args:
            task_name: Name for logging
            interval: Seconds between runs
            task_func: Async function to run
        """
        # Initial startup delay
        await asyncio.sleep(STARTUP_DELAY)
        
        # Initialize error tracking
        self._error_counts[task_name] = 0
        
        while self._running:
            try:
                # Check if task is paused due to errors
                if task_name in self._paused_until:
                    if datetime.now() < self._paused_until[task_name]:
                        wait_time = (self._paused_until[task_name] - datetime.now()).seconds
                        logger.debug(f"⏸️ {task_name} paused for {wait_time}s more")
                        await asyncio.sleep(60)  # Check again in 1 minute
                        continue
                    else:
                        # Pause expired, reset
                        del self._paused_until[task_name]
                        self._error_counts[task_name] = 0
                        logger.info(f"▶️ {task_name} resuming after pause")
                
                # Run the task
                self._last_run[task_name] = datetime.now()
                logger.info(f"🔄 Running: {task_name}")
                
                await task_func()
                
                # Success - reset error count
                self._error_counts[task_name] = 0
                self._last_success[task_name] = datetime.now()
                logger.info(f"✅ Completed: {task_name}")
                
            except asyncio.CancelledError:
                logger.debug(f"Task {task_name} cancelled")
                break
            except Exception as e:
                self._error_counts[task_name] += 1
                logger.error(f"❌ {task_name} failed (attempt {self._error_counts[task_name]}): {e}")
                
                # Check if we should pause
                if self._error_counts[task_name] >= MAX_CONSECUTIVE_ERRORS:
                    self._paused_until[task_name] = datetime.now() + timedelta(minutes=ERROR_BACKOFF_MINUTES)
                    logger.warning(
                        f"⏸️ {task_name} paused for {ERROR_BACKOFF_MINUTES} minutes "
                        f"after {MAX_CONSECUTIVE_ERRORS} consecutive errors"
                    )
            
            # Wait for next interval
            await asyncio.sleep(interval)
    
    # =========================================================================
    # TASK IMPLEMENTATIONS
    # =========================================================================
    
    async def _refresh_tokens(self):
        """Proactively refresh all Google OAuth tokens"""
        try:
            from .oauth_manager import google_auth_manager
            
            results = await google_auth_manager.refresh_all_tokens(self._user_id)
            
            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)
            
            if total_count > 0:
                logger.info(f"🔑 Token refresh: {success_count}/{total_count} accounts refreshed")
                
                # Log any failures
                for email, success in results.items():
                    if not success:
                        logger.warning(f"   ⚠️ Failed to refresh: {email}")
            else:
                logger.debug("🔑 No OAuth accounts to refresh")
                
        except Exception as e:
            logger.error(f"❌ Token refresh task failed: {e}")
            raise
    
    async def _sync_emails(self):
        """Sync emails from all connected Gmail accounts"""
        try:
            from .gmail_client import gmail_client
            from .oauth_manager import google_auth_manager
            
            # Get all connected email accounts
            accounts = await google_auth_manager.get_authenticated_accounts(self._user_id)
            
            # Filter to only OAuth accounts (not service account)
            oauth_accounts = [a for a in accounts if a.get('type') != 'service_account']
            
            if not oauth_accounts:
                logger.debug("📧 No email accounts to sync")
                return
            
            for account in oauth_accounts:
                email = account['email']
                try:
                    logger.debug(f"📧 Syncing emails for {email}...")
                    
                    # Initialize client for this account
                    await gmail_client.initialize(self._user_id, email)
                    
                    # Fetch recent messages (this stores them in the database)
                    messages = await gmail_client.get_recent_messages(
                        email=email,
                        max_results=50,
                        days=7
                    )
                    
                    logger.info(f"📧 Synced {len(messages)} emails from {email}")
                    
                except Exception as e:
                    logger.error(f"📧 Failed to sync {email}: {e}")
                    # Continue with other accounts
                    continue
            
        except Exception as e:
            logger.error(f"❌ Email sync task failed: {e}")
            raise
    
    async def _sync_analytics(self):
        """Sync Analytics data for all configured sites"""
        try:
            from .analytics_client import get_analytics_client
            
            # Get client instance (not the None module-level variable!)
            analytics_client = get_analytics_client(self._user_id)
            await analytics_client.initialize(self._user_id)
            
            synced_count = 0
            
            for site_name in SUPPORTED_SITES.keys():
                try:
                    logger.debug(f"📊 Syncing Analytics for {site_name}...")
                    
                    # Fetch and store analytics data
                    summary = await analytics_client.get_analytics_summary(site_name, days=30)
                    
                    if summary:
                        synced_count += 1
                        logger.debug(f"📊 Synced Analytics for {site_name}")
                    else:
                        logger.debug(f"📊 No Analytics data for {site_name}")
                        
                except Exception as e:
                    logger.error(f"📊 Failed to sync Analytics for {site_name}: {e}")
                    continue
            
            logger.info(f"📊 Analytics sync complete: {synced_count}/{len(SUPPORTED_SITES)} sites")
            
        except Exception as e:
            logger.error(f"❌ Analytics sync task failed: {e}")
            raise
    
    async def _sync_search_console(self):
        """Sync Search Console data for all configured sites"""
        try:
            from .search_console_client import search_console_client
            
            # Initialize client
            await search_console_client.initialize(self._user_id)
            
            synced_count = 0
            
            for site_name in SUPPORTED_SITES.keys():
                try:
                    logger.debug(f"🔍 Syncing Search Console for {site_name}...")
                    
                    # Fetch and store search data
                    data = await search_console_client.fetch_search_data_for_site(site_name, days=30)
                    
                    if data:
                        synced_count += 1
                        logger.debug(f"🔍 Synced {len(data)} keywords for {site_name}")
                    else:
                        logger.debug(f"🔍 No Search Console data for {site_name}")
                        
                except Exception as e:
                    logger.error(f"🔍 Failed to sync Search Console for {site_name}: {e}")
                    continue
            
            logger.info(f"🔍 Search Console sync complete: {synced_count}/{len(SUPPORTED_SITES)} sites")
            
        except Exception as e:
            logger.error(f"❌ Search Console sync task failed: {e}")
            raise
    
    async def _sync_calendar(self):
        """Sync Calendar events"""
        try:
            from .calendar_client import calendar_client
            
            # Initialize client
            await calendar_client.initialize(self._user_id)
            
            # Fetch events for next 14 days (stores them in database)
            events = await calendar_client.get_all_events(days=14)
            
            logger.info(f"📅 Calendar sync complete: {len(events)} events")
            
        except Exception as e:
            logger.error(f"❌ Calendar sync task failed: {e}")
            raise
    
    # =========================================================================
    # STATUS & HEALTH
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all background tasks"""
        status = {
            'running': self._running,
            'user_id': self._user_id,
            'tasks': {}
        }
        
        for task_name in ['token_refresh', 'email_sync', 'analytics_sync',
                          'search_console_sync', 'calendar_sync']:
            task_status = {
                'last_run': self._last_run.get(task_name),
                'last_success': self._last_success.get(task_name),
                'error_count': self._error_counts.get(task_name, 0),
                'paused_until': self._paused_until.get(task_name),
                'is_running': task_name in self._tasks and not self._tasks[task_name].done()
            }
            status['tasks'][task_name] = task_status
        
        return status
    
    async def run_task_now(self, task_name: str) -> bool:
        """
        Manually trigger a specific task to run immediately
        
        Args:
            task_name: One of 'token_refresh', 'email_sync', 'analytics_sync', 
                      'search_console_sync', 'calendar_sync'
        
        Returns:
            True if task ran successfully
        """
        task_map = {
            'token_refresh': self._refresh_tokens,
            'email_sync': self._sync_emails,
            'analytics_sync': self._sync_analytics,
            'search_console_sync': self._sync_search_console,
            'calendar_sync': self._sync_calendar
        }
        
        if task_name not in task_map:
            logger.error(f"Unknown task: {task_name}")
            return False
        
        if not self._user_id:
            self._user_id = await self._get_user_id()
            if not self._user_id:
                logger.error("No user found")
                return False
        
        try:
            logger.info(f"🔄 Manually running: {task_name}")
            await task_map[task_name]()
            logger.info(f"✅ Manual run complete: {task_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Manual run failed for {task_name}: {e}")
            return False


# Global instance
google_background_tasks = GoogleWorkspaceBackgroundTasks()


# Convenience functions
async def start_background_tasks():
    """Start all Google Workspace background tasks"""
    await google_background_tasks.start()


async def stop_background_tasks():
    """Stop all Google Workspace background tasks"""
    await google_background_tasks.stop()


def get_background_tasks_status() -> Dict[str, Any]:
    """Get status of background tasks"""
    return google_background_tasks.get_status()


async def trigger_sync(task_name: str) -> bool:
    """Manually trigger a sync task"""
    return await google_background_tasks.run_task_now(task_name)
