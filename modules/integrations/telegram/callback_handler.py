"""
Telegram Callback Handler - Button Click Processing
Processes inline keyboard button clicks and updates notification state
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .bot_client import TelegramBotClient
from .database_manager import TelegramDatabaseManager
from .notification_manager import NotificationManager

logger = logging.getLogger(__name__)

class CallbackHandler:
    """Handles Telegram inline keyboard button callbacks"""
    
    def __init__(self, bot_client=None, notification_manager=None):
        self.bot_client = bot_client
        self.notification_manager = notification_manager
        # Note: db_manager will be initialized when needed
    
    async def edit_message(self, message_id: int, text: str, reply_markup=None):
        """Helper to edit message - wraps bot_client.edit_message_text"""
        # Get chat_id from the notification manager's default
        chat_id = self.notification_manager._default_chat_id or os.getenv('TELEGRAM_CHAT_ID')
        
        return await self.bot_client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
    
    @property
    def db_manager(self):
        """Lazy-load database manager"""
        if not hasattr(self, '_db_manager'):
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def process_callback(
        self,
        callback_query_id: str,
        callback_data: str,
        message_id: int
    ) -> Dict[str, Any]:
        """
        Process a button callback from Telegram
        
        Callback data format: {type}:{action}:{notification_id}:{optional_params}
        Examples:
            - "prayer:prayed:uuid"
            - "prayer:snooze:uuid:10"
            - "bluesky:good_match:uuid:account_id"
            - "reminder:done:uuid"
        
        Args:
            callback_query_id: Telegram callback query ID
            callback_data: Data from button click
            message_id: Telegram message ID
        
        Returns:
            Result dict with success status
        """
        try:
            # Parse callback data
            parts = callback_data.split(':')
            if len(parts) < 3:
                logger.error(f"Invalid callback data format: {callback_data}")
                return {"success": False, "error": "Invalid callback format"}
            
            notification_type = parts[0]
            action = parts[1]
            notification_id = parts[2]
            extra_params = parts[3:] if len(parts) > 3 else []
            
            logger.info(f"Processing callback: {notification_type}/{action} for {notification_id}")
            
            # Route to appropriate handler
            if notification_type == 'prayer':
                result = await self._handle_prayer_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'weather':
                result = await self._handle_weather_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'reminder':
                result = await self._handle_reminder_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'calendar':
                result = await self._handle_calendar_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'email':
                result = await self._handle_email_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'clickup':
                result = await self._handle_clickup_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'bluesky':
                result = await self._handle_bluesky_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'trends':
                result = await self._handle_trends_callback(
                    action, notification_id, message_id, extra_params
                )
            
            else:
                logger.error(f"Unknown notification type: {notification_type}")
                result = {"success": False, "error": "Unknown notification type"}
            
            # Acknowledge callback to remove loading state
            await self.bot_client.answer_callback_query(
                callback_query_id,
                text=result.get('ack_text', 'Acknowledged')
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Exception processing callback: {e}")
            await self.bot_client.answer_callback_query(
                callback_query_id,
                text="Error processing action"
            )
            return {"success": False, "error": str(e)}
    
    # ========================================================================
    # PRAYER CALLBACKS
    # ========================================================================
    
    async def _handle_prayer_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle prayer notification button clicks"""
        
        if action == 'prayed':
            # User acknowledged prayer
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'prayed'
            )
            
            # Update message to show acknowledgment
            await self.bot_client.edit_message(
                message_id,
                "✅ Prayer acknowledged",
                reply_markup=None  # Remove buttons
            )
            
            return {
                "success": True,
                "ack_text": "Prayer acknowledged"
            }
        
        elif action == 'snooze':
            minutes = int(params[0]) if params else 10
            
            await self.notification_manager.acknowledge_notification(
                notification_id,
                f'snoozed_{minutes}m'
            )
            
            await self.bot_client.edit_message(
                message_id,
                f"⏰ Snoozed for {minutes} minutes",
                reply_markup=None
            )
            
            return {
                "success": True,
                "ack_text": f"Snoozed {minutes} minutes"
            }
        
        elif action == 'next':
            # Skip this prayer, remind at next one
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'skip_to_next'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "⏭️ Will remind at next prayer",
                reply_markup=None
            )
            
            return {
                "success": True,
                "ack_text": "Will remind at next prayer"
            }
        
        return {"success": False, "error": "Unknown prayer action"}
    
    # ========================================================================
    # WEATHER CALLBACKS
    # ========================================================================
    
    async def _handle_weather_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle weather notification button clicks"""
        
        if action == 'got_it':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'acknowledged'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Weather alert acknowledged",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Acknowledged"}
        
        return {"success": False, "error": "Unknown weather action"}
    
    # ========================================================================
    # REMINDER CALLBACKS
    # ========================================================================
    
    async def _handle_reminder_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle reminder button clicks"""
        
        if action == 'done':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'completed'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Reminder completed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Completed"}
        
        return {"success": False, "error": "Unknown reminder action"}
    
    # ========================================================================
    # CALENDAR CALLBACKS
    # ========================================================================
    
    async def _handle_calendar_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle calendar event button clicks"""
        
        if action == 'ready':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ready'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Ready for event",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Ready"}
        
        elif action == 'snooze':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'snoozed_15m'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "⏰ Snoozed for 15 minutes",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Snoozed 15 minutes"}
        
        return {"success": False, "error": "Unknown calendar action"}
    
    # ========================================================================
    # EMAIL CALLBACKS
    # ========================================================================
    
    async def _handle_email_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle email notification button clicks"""
        
        if action == 'not_urgent':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'false_positive'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as not urgent (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Marked not urgent"}
        
        elif action == 'ignore':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ignored'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Dismissed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Dismissed"}
        
        return {"success": False, "error": "Unknown email action"}
    
    # ========================================================================
    # CLICKUP CALLBACKS
    # ========================================================================
    
    async def _handle_clickup_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle ClickUp task button clicks"""
        
        if action == 'done':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'marked_done'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Task marked complete",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Task completed"}
        
        elif action == 'got_it':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'acknowledged'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Acknowledged",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Acknowledged"}
        
        return {"success": False, "error": "Unknown ClickUp action"}
    
    # ========================================================================
    # BLUESKY TRAINING CALLBACKS
    # ========================================================================
    
    async def _handle_bluesky_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle Bluesky training button clicks"""
        
        opportunity_id = params[0] if params else None
        
        if action == 'good_match':
            # Store positive training feedback
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",  # Your user ID
                feedback_type='bluesky_engagement',
                opportunity_id=opportunity_id or notification_id,
                user_response='good_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as good match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Good match recorded"}
        
        elif action == 'bad_match':
            # Store negative training feedback
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='bluesky_engagement',
                opportunity_id=opportunity_id or notification_id,
                user_response='bad_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as bad match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Bad match recorded"}
        
        elif action == 'ignore':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ignored'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Dismissed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Dismissed"}
        
        return {"success": False, "error": "Unknown Bluesky action"}
    
    # ========================================================================
    # TRENDS TRAINING CALLBACKS
    # ========================================================================
    
    async def _handle_trends_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle Trends training button clicks"""
        
        opportunity_id = params[0] if params else None
        
        if action == 'good_match':
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='trends_keyword',
                opportunity_id=opportunity_id or notification_id,
                user_response='good_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as good match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Good match recorded"}
        
        elif action == 'bad_match':
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='trends_keyword',
                opportunity_id=opportunity_id or notification_id,
                user_response='bad_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as bad match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Bad match recorded"}
        
        elif action == 'ignore':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ignored'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Dismissed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Dismissed"}
        
        return {"success": False, "error": "Unknown Trends action"}


# Global instance
_callback_handler = None

def get_callback_handler() -> CallbackHandler:
    """Get the global callback handler instance"""
    global _callback_handler
    if _callback_handler is None:
        import os
        from .bot_client import TelegramBotClient
        from .notification_manager import get_notification_manager
        
        # Get bot token from environment
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
        bot_client = TelegramBotClient(bot_token)
        notification_manager = get_notification_manager()
        
        _callback_handler = CallbackHandler(
            bot_client=bot_client,
            notification_manager=notification_manager
        )
    return _callback_handler
