"""
Telegram Database Manager - All Database Operations
Handles reading preferences, logging notifications, tracking responses
FIXED: Uses correct db_manager methods (fetch_one, fetch_all, execute)
"""

import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, time
from uuid import UUID

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class TelegramDatabaseManager:
    """Manages all Telegram-related database operations"""
    
    def __init__(self):
        self.db = db_manager
    
    # ========================================================================
    # PREFERENCES
    # ========================================================================
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's Telegram notification preferences
        
        Returns:
            Dict with all preference settings or None if not found
        """
        query = """
            SELECT 
                telegram_chat_id,
                notifications_enabled,
                quiet_hours_start,
                quiet_hours_end,
                timezone,
                prayer_enabled,
                weather_enabled,
                reminders_enabled,
                calendar_enabled,
                email_enabled,
                clickup_enabled,
                bluesky_enabled,
                trends_enabled,
                analytics_enabled,
                max_notifications_per_hour,
                max_notifications_per_day
            FROM telegram_preferences
            WHERE user_id = $1;
        """
        
        try:
            result = await self.db.fetch_one(query, user_id)
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Failed to get preferences: {e}")
            return None
    
    async def is_notification_type_enabled(
        self,
        user_id: str,
        notification_type: str
    ) -> bool:
        """
        Check if a specific notification type is enabled
        
        Args:
            user_id: User UUID
            notification_type: 'prayer', 'weather', 'reminders', etc.
        
        Returns:
            True if enabled, False otherwise
        """
        query = f"""
            SELECT {notification_type}_enabled, notifications_enabled
            FROM telegram_preferences
            WHERE user_id = $1;
        """
        
        try:
            result = await self.db.fetch_one(query, user_id)
            if result:
                return result['notifications_enabled'] and result[f'{notification_type}_enabled']
            return False
        except Exception as e:
            logger.error(f"Failed to check if {notification_type} enabled: {e}")
            return False
    
    # ========================================================================
    # NOTIFICATION LOGGING
    # ========================================================================
    
    async def log_notification(
        self,
        user_id: str,
        notification_type: str,
        notification_subtype: str,
        message_data: Dict[str, Any],
        telegram_message_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Log a sent notification to database
        
        Returns:
            Notification ID (UUID) if successful
        """
        query = """
            INSERT INTO telegram_notifications (
                user_id,
                notification_type,
                notification_subtype,
                message_data,
                telegram_message_id,
                sent_at
            ) VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id;
        """
        
        try:
            import json
            result = await self.db.fetch_one(
                query,
                user_id,
                notification_type,
                notification_subtype,
                json.dumps(message_data),
                telegram_message_id
            )
            return str(result['id']) if result else None
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")
            return None
    
    async def acknowledge_notification(
        self,
        notification_id: str,
        user_response: str
    ) -> bool:
        """
        Mark notification as acknowledged with user's response
        
        Args:
            notification_id: UUID of notification
            user_response: 'prayed', 'snoozed', 'dismissed', etc.
        
        Returns:
            True if successful
        """
        query = """
            UPDATE telegram_notifications
            SET 
                acknowledged_at = NOW(),
                user_response = $2
            WHERE id = $1;
        """
        
        try:
            await self.db.execute(query, notification_id, user_response)
            return True
        except Exception as e:
            logger.error(f"Failed to acknowledge notification: {e}")
            return False
    
    async def increment_follow_up_count(self, notification_id: str) -> bool:
        """Increment follow-up counter for persistent notifications"""
        query = """
            UPDATE telegram_notifications
            SET follow_up_count = follow_up_count + 1
            WHERE id = $1;
        """
        
        try:
            await self.db.execute(query, notification_id)
            return True
        except Exception as e:
            logger.error(f"Failed to increment follow-up: {e}")
            return False
    
    # ========================================================================
    # RATE LIMITING
    # ========================================================================
    
    async def get_notification_count(
        self,
        user_id: str,
        notification_type: str,
        hours: int = 1
    ) -> int:
        """
        Get count of notifications sent in last N hours
        
        Args:
            user_id: User UUID
            notification_type: Specific type or 'all'
            hours: Time window (1 for hourly, 24 for daily)
        
        Returns:
            Count of notifications sent
        """
        if notification_type == 'all':
            query = f"""
                SELECT COUNT(*) as count
                FROM telegram_notifications
                WHERE user_id = $1
                AND sent_at > NOW() - INTERVAL '{hours} hours';
            """
            params = [user_id]
        else:
            query = f"""
                SELECT COUNT(*) as count
                FROM telegram_notifications
                WHERE user_id = $1
                AND notification_type = $2
                AND sent_at > NOW() - INTERVAL '{hours} hours';
            """
            params = [user_id, notification_type]
        
        try:
            result = await self.db.fetch_one(query, *params)
            return int(result['count']) if result else 0
        except Exception as e:
            logger.error(f"Failed to get notification count: {e}")
            return 0
    
    # ========================================================================
    # REMINDERS
    # ========================================================================
    
    async def create_reminder(
        self,
        user_id: str,
        reminder_text: str,
        scheduled_for: datetime,
        created_from_message: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a custom reminder
        
        Returns:
            Reminder ID (UUID) if successful
        """
        query = """
            INSERT INTO telegram_reminders (
                user_id,
                reminder_text,
                scheduled_for,
                created_from_message
            ) VALUES ($1, $2, $3, $4)
            RETURNING id;
        """
        
        try:
            result = await self.db.fetch_one(
                query,
                user_id,
                reminder_text,
                scheduled_for,
                created_from_message
            )
            return str(result['id']) if result else None
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            return None
    
    async def get_pending_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all unsent reminders that are due"""
        query = """
            SELECT id, reminder_text, scheduled_for
            FROM telegram_reminders
            WHERE user_id = $1
            AND notification_sent = false
            AND scheduled_for <= NOW()
            ORDER BY scheduled_for;
        """
        
        try:
            results = await self.db.fetch_all(query, user_id)
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to get pending reminders: {e}")
            return []
    
    async def mark_reminder_sent(self, reminder_id: str) -> bool:
        """Mark reminder as sent"""
        query = """
            UPDATE telegram_reminders
            SET notification_sent = true
            WHERE id = $1;
        """
        
        try:
            await self.db.execute(query, reminder_id)
            return True
        except Exception as e:
            logger.error(f"Failed to mark reminder sent: {e}")
            return False
    
    # ========================================================================
    # TRAINING FEEDBACK
    # ========================================================================
    
    async def store_training_feedback(
        self,
        user_id: str,
        feedback_type: str,
        opportunity_id: str,
        user_response: str,
        opportunity_data: Dict[str, Any],
        response_time_seconds: Optional[int] = None
    ) -> Optional[str]:
        """
        Store training feedback for Bluesky/Trends learning
        
        Args:
            feedback_type: 'bluesky_engagement' or 'trends_keyword'
            user_response: 'good_match', 'bad_match', 'ignore'
        
        Returns:
            Feedback ID if successful
        """
        query = """
            INSERT INTO telegram_training_feedback (
                user_id,
                feedback_type,
                opportunity_id,
                user_response,
                opportunity_data,
                response_time_seconds
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id;
        """
        
        try:
            import json
            result = await self.db.fetch_one(
                query,
                user_id,
                feedback_type,
                opportunity_id,
                user_response,
                json.dumps(opportunity_data),
                response_time_seconds
            )
            return str(result['id']) if result else None
        except Exception as e:
            logger.error(f"Failed to store training feedback: {e}")
            return None


# Global instance
_db_manager = None

def get_telegram_db_manager() -> TelegramDatabaseManager:
    """Get the global Telegram database manager instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = TelegramDatabaseManager()
    return _db_manager