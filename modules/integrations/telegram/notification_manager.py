"""
Telegram Notification Manager - Central Routing and Rate Limiting
All notifications flow through here for safety checks and logging
"""

import logging
import os  # ← ADD THIS LINE
from typing import Dict, Optional, Any
from datetime import datetime, time as dt_time

from .bot_client import TelegramBotClient
from .kill_switch import KillSwitch

logger = logging.getLogger(__name__)

# Rate limits per notification type (per day)
RATE_LIMITS = {
    'prayer': 10,      # 5 prayers + follow-ups
    'weather': 8,
    'reminders': 20,
    'calendar': 50,    # High limit for events
    'email': 10,
    'clickup': 15,
    'bluesky': 15,
    'trends': 15,
    'analytics': 3
}

class NotificationManager:
    """Central manager for all Telegram notifications"""
    
    def __init__(self, bot_client=None, kill_switch=None):
        self.bot_client = bot_client
        self.kill_switch = kill_switch
        self.db_manager = TelegramDatabaseManager() # ← Lazy initialization
        
        # Cache chat_id from environment as fallback  # ← ADD THIS LINE
        self._default_chat_id = os.getenv('TELEGRAM_CHAT_ID')  # ← ADD THIS LINE

    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from .database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def send_notification(
        self,
        user_id: str,
        notification_type: str,
        notification_subtype: str,
        message_text: str,
        buttons: Optional[list] = None,
        message_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a notification through all safety checks
        
        Args:
            user_id: User UUID
            notification_type: 'prayer', 'weather', 'reminders', etc.
            notification_subtype: 'initial', 'follow_up', 'uv_alert', etc.
            message_text: The notification message
            buttons: Optional inline keyboard buttons
            message_data: Optional metadata to store
        
        Returns:
            Result dict with success status and notification_id
        """
        
        # SAFETY CHECK 1: Kill switch
        if not await self.kill_switch.can_send_notification(user_id, notification_type):
            logger.info(f"Notification blocked by kill switch: {notification_type}")
            return {
                "success": False,
                "error": "Kill switch active",
                "blocked_by": "kill_switch"
            }
        
        # SAFETY CHECK 2: Type enabled in preferences
        if not await self.db_manager.is_notification_type_enabled(user_id, notification_type):
            logger.info(f"Notification type disabled: {notification_type}")
            return {
                "success": False,
                "error": "Notification type disabled",
                "blocked_by": "preferences"
            }
        
        # SAFETY CHECK 3: Quiet hours
        if await self._is_quiet_hours(user_id, notification_type):
            logger.info(f"Notification blocked by quiet hours: {notification_type}")
            return {
                "success": False,
                "error": "Quiet hours active",
                "blocked_by": "quiet_hours"
            }
        
        # SAFETY CHECK 4: Rate limiting
        if not await self._check_rate_limit(user_id, notification_type):
            logger.warning(f"Rate limit exceeded for {notification_type}")
            return {
                "success": False,
                "error": "Rate limit exceeded",
                "blocked_by": "rate_limit"
            }
        
        # All checks passed - send notification
        try:
            
            # Get chat_id from preferences
            prefs = await self.db_manager.get_user_preferences(user_id)
            if not prefs or not prefs.get('telegram_chat_id'):
                # Fallback to environment variable
                if self._default_chat_id:
                    chat_id = self._default_chat_id
                    logger.warning(f"Using default chat_id from env for user {user_id}")
                else:
                    logger.error(f"No telegram_chat_id for user {user_id}")
                    return {
                        "success": False,
                        "error": "No chat_id configured",
                        "blocked_by": "configuration"
                    }
            else:
                chat_id = str(prefs['telegram_chat_id'])
            
            # All checks passed - send notification
            try:
                # Create inline keyboard if buttons provided
                reply_markup = None
                if buttons:
                    reply_markup = self.bot_client.create_inline_keyboard(buttons)
                
                # Send via Telegram
                result = await self.bot_client.send_message(
                    chat_id=chat_id,  # ← CRITICAL: Added chat_id parameter
                    text=message_text,
                    reply_markup=reply_markup
                )
            
            if result.get('message_id')
                # Log to database
                notification_id = await self.db_manager.log_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    notification_subtype=notification_subtype,
                    message_data=message_data or {},
                    telegram_message_id=result.get('message_id')
                )
                
                logger.info(
                    f"Notification sent: {notification_type}/{notification_subtype} "
                    f"(ID: {notification_id})"
                )
                
                return {
                    "success": True,
                    "notification_id": notification_id,
                    "telegram_message_id": result.get('message_id')
                }
            else:
                logger.error(f"Failed to send notification: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get('error')
                }
        
        except Exception as e:
            logger.error(f"Exception sending notification: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _is_quiet_hours(
        self,
        user_id: str,
        notification_type: str
    ) -> bool:
        """
        Check if current time is within user's quiet hours
        
        Emergency weather notifications bypass quiet hours
        """
        # Emergency weather always allowed
        if notification_type == 'weather':
            return False
        
        prefs = await self.db_manager.get_user_preferences(user_id)
        if not prefs:
            return False
        
        quiet_start = prefs.get('quiet_hours_start')
        quiet_end = prefs.get('quiet_hours_end')
        
        if not quiet_start or not quiet_end:
            return False
        
        now = datetime.now().time()
        
        # Handle overnight quiet hours (e.g., 23:00 to 07:00)
        if quiet_start > quiet_end:
            return now >= quiet_start or now <= quiet_end
        else:
            return quiet_start <= now <= quiet_end
    
    async def _check_rate_limit(
        self,
        user_id: str,
        notification_type: str
    ) -> bool:
        """
        Check if notification type is under rate limit
        
        Returns:
            True if under limit (can send), False if over limit
        """
        # Get daily limit for this type
        daily_limit = RATE_LIMITS.get(notification_type, 20)
        
        # Get count from last 24 hours
        count = await self.db_manager.get_notification_count(
            user_id=user_id,
            notification_type=notification_type,
            hours=24
        )
        
        return count < daily_limit
    
    async def acknowledge_notification(
        self,
        notification_id: str,
        user_response: str
    ) -> bool:
        """
        Mark notification as acknowledged
        
        Args:
            notification_id: UUID from database
            user_response: 'prayed', 'snoozed', 'dismissed', etc.
        
        Returns:
            True if successful
        """
        return await self.db_manager.acknowledge_notification(
            notification_id,
            user_response
        )
    
    async def get_rate_limit_status(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get current rate limit status for all notification types
        
        Returns:
            Dict mapping notification_type -> count/limit
        """
        status = {}
        
        for notif_type, limit in RATE_LIMITS.items():
            count = await self.db_manager.get_notification_count(
                user_id=user_id,
                notification_type=notif_type,
                hours=24
            )
            status[notif_type] = {
                "count": count,
                "limit": limit,
                "remaining": max(0, limit - count),
                "percentage": int((count / limit) * 100) if limit > 0 else 0
            }
        
        return status


# Global instance
_notification_manager = None

def get_notification_manager() -> NotificationManager:
    """Get the global notification manager instance"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
