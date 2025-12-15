"""
Telegram Database Manager - All Database Operations
Handles reading preferences, logging notifications, tracking responses
FIXED: Uses correct db_manager methods (fetch_one, fetch_all, execute)
FIXED: SQL injection protection via allowlist validation
"""

import json
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, time
from uuid import UUID

from ...core.database import db_manager

logger = logging.getLogger(__name__)


# Valid notification types - must match columns in telegram_preferences table
# Each type corresponds to a {type}_enabled column
VALID_NOTIFICATION_TYPES = frozenset({
    'prayer',
    'weather',
    'reminders',
    'calendar',
    'email',
    'clickup',
    'bluesky',
    'trends',
    'analytics',
    'fathom',
    'intelligence'
})


class TelegramDatabaseManager:
    """Manages all Telegram-related database operations"""
    
    def __init__(self):
        self.db = db_manager
    
    # ========================================================================
    # VALIDATION HELPERS
    # ========================================================================
    
    def _validate_notification_type(self, notification_type: str) -> bool:
        """
        Validate notification type against allowlist to prevent SQL injection
        
        Args:
            notification_type: Type to validate
            
        Returns:
            True if valid, raises ValueError if invalid
        """
        if notification_type not in VALID_NOTIFICATION_TYPES:
            raise ValueError(
                f"Invalid notification type: {notification_type}. "
                f"Must be one of: {', '.join(sorted(VALID_NOTIFICATION_TYPES))}"
            )
        return True
    
    def _validate_hours(self, hours: Any) -> int:
        """
        Validate and convert hours parameter to prevent SQL injection
        
        Args:
            hours: Hours value to validate
            
        Returns:
            Validated integer hours value
            
        Raises:
            ValueError: If hours is not a valid positive integer
        """
        try:
            hours_int = int(hours)
            if hours_int <= 0:
                raise ValueError("Hours must be positive")
            if hours_int > 168:  # Max 1 week
                raise ValueError("Hours cannot exceed 168 (1 week)")
            return hours_int
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid hours value: {hours}. Must be a positive integer.") from e
    
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
                fathom_enabled,
                intelligence_enabled,
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
        # Validate notification_type against allowlist to prevent SQL injection
        try:
            self._validate_notification_type(notification_type)
        except ValueError as e:
            logger.error(f"Invalid notification type: {e}")
            return False
        
        # Safe to use in query since we validated against allowlist
        column_name = f"{notification_type}_enabled"
        query = f"""
            SELECT {column_name}, notifications_enabled
            FROM telegram_preferences
            WHERE user_id = $1;
        """
        
        try:
            result = await self.db.fetch_one(query, user_id)
            if result:
                return result['notifications_enabled'] and result[column_name]
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
        # Validate hours to prevent SQL injection
        try:
            validated_hours = self._validate_hours(hours)
        except ValueError as e:
            logger.error(f"Invalid hours parameter: {e}")
            return 0
        
        if notification_type == 'all':
            query = f"""
                SELECT COUNT(*) as count
                FROM telegram_notifications
                WHERE user_id = $1
                AND sent_at > NOW() - INTERVAL '{validated_hours} hours';
            """
            params = [user_id]
        else:
            # Validate notification_type if not 'all'
            try:
                self._validate_notification_type(notification_type)
            except ValueError as e:
                logger.error(f"Invalid notification type: {e}")
                return 0
            
            query = f"""
                SELECT COUNT(*) as count
                FROM telegram_notifications
                WHERE user_id = $1
                AND notification_type = $2
                AND sent_at > NOW() - INTERVAL '{validated_hours} hours';
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
    
    async def get_all_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get ALL pending reminders for user (not just due ones)
        Used for listing reminders
        
        Returns reminders ordered by scheduled time
        """
        query = """
            SELECT 
                id,
                reminder_text,
                scheduled_for,
                created_at,
                notification_sent
            FROM telegram_reminders
            WHERE user_id = $1
            AND notification_sent = false
            ORDER BY scheduled_for ASC;
        """
        
        try:
            results = await self.db.fetch_all(query, user_id)
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to get all reminders: {e}")
            return []
    
    async def delete_reminder(self, reminder_id: str, user_id: str) -> bool:
        """
        Delete a specific reminder by ID
        
        Args:
            reminder_id: UUID of the reminder
            user_id: User ID for security (ensures user owns the reminder)
        
        Returns:
            True if deleted, False if not found or error
        """
        query = """
            DELETE FROM telegram_reminders
            WHERE id = $1
            AND user_id = $2
            AND notification_sent = false
            RETURNING id;
        """
        
        try:
            result = await self.db.fetch_one(query, reminder_id, user_id)
            if result:
                logger.info(f"Deleted reminder {reminder_id}")
                return True
            else:
                logger.warning(f"Reminder {reminder_id} not found or already sent")
                return False
        except Exception as e:
            logger.error(f"Failed to delete reminder: {e}")
            return False
    
    async def delete_all_reminders(self, user_id: str) -> int:
        """
        KILL SWITCH - Delete ALL pending reminders for user
        
        Returns:
            Number of reminders deleted
        """
        query = """
            DELETE FROM telegram_reminders
            WHERE user_id = $1
            AND notification_sent = false
            RETURNING id;
        """
        
        try:
            results = await self.db.fetch_all(query, user_id)
            count = len(results)
            logger.info(f"🔥 KILL SWITCH: Deleted {count} reminders for user {user_id}")
            return count
        except Exception as e:
            logger.error(f"Failed to delete all reminders: {e}")
            return 0
    
    
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
