"""
Telegram Reminder Notifications - Custom User Reminders
Natural language parsing and scheduled reminder delivery
"""

import logging
import asyncio
import dateparser
from datetime import datetime, timedelta
from typing import Dict, Optional

from ....core.database import db_manager
from ..database_manager import TelegramDatabaseManager
from ..notification_manager import NotificationManager

logger = logging.getLogger(__name__)

class ReminderNotificationHandler:
    """Handles custom user reminders with natural language parsing"""
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self.db_manager = db_manager 
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
    
    async def create_reminder_from_text(
        self,
        reminder_text: str,
        original_message: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Parse natural language and create a reminder
        
        Examples:
            - "remind me to debug in 30 minutes"
            - "remind me to call mom tomorrow at 2pm"
            - "remind me about the meeting on Friday"
        
        Args:
            reminder_text: The reminder text including timing
            original_message: Full original command for reference
        
        Returns:
            Result dict with reminder_id if successful
        """
        try:
            # Extract the actual reminder text and time phrase
            parsed = self._parse_reminder_command(reminder_text)
            
            if not parsed['scheduled_for']:
                return {
                    "success": False,
                    "error": "Could not parse time from reminder text",
                    "suggestion": "Try: 'in 30 minutes', 'tomorrow at 2pm', 'Friday at 3pm'"
                }
            
            # Create reminder in database
            reminder_id = await self.db_manager.create_reminder(
                user_id=self.user_id,
                reminder_text=parsed['reminder_text'],
                scheduled_for=parsed['scheduled_for'],
                created_from_message=original_message
            )
            
            if reminder_id:
                logger.info(f"Created reminder {reminder_id} for {parsed['scheduled_for']}")
                return {
                    "success": True,
                    "reminder_id": reminder_id,
                    "reminder_text": parsed['reminder_text'],
                    "scheduled_for": parsed['scheduled_for']
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create reminder in database"
                }
        
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _parse_reminder_command(self, text: str) -> Dict:
        """
        Parse reminder command to extract text and time
        
        Args:
            text: Full reminder text
        
        Returns:
            Dict with reminder_text and scheduled_for datetime
        """
        # Common patterns
        text_lower = text.lower()
        
        # Remove "remind me to" prefix if present
        if text_lower.startswith('remind me to '):
            text = text[13:]
        elif text_lower.startswith('remind me '):
            text = text[10:]
        
        # Try to find time-related keywords
        time_keywords = [
            'in ', 'at ', 'on ', 'tomorrow', 'today', 'tonight',
            'next week', 'next month', 'monday', 'tuesday', 'wednesday',
            'thursday', 'friday', 'saturday', 'sunday'
        ]
        
        # Find where time phrase starts
        time_start_idx = -1
        for keyword in time_keywords:
            idx = text_lower.find(keyword)
            if idx != -1:
                if time_start_idx == -1 or idx < time_start_idx:
                    time_start_idx = idx
        
        if time_start_idx == -1:
            # No time keyword found, try parsing the whole thing
            parsed_time = dateparser.parse(text)
            if parsed_time:
                return {
                    "reminder_text": text,
                    "scheduled_for": parsed_time
                }
            return {
                "reminder_text": text,
                "scheduled_for": None
            }
        
        # Split into reminder text and time phrase
        reminder_text = text[:time_start_idx].strip()
        time_phrase = text[time_start_idx:].strip()
        
        # Parse the time phrase
        parsed_time = dateparser.parse(
            time_phrase,
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now()
            }
        )
        
        return {
            "reminder_text": reminder_text or text,
            "scheduled_for": parsed_time
        }
    
    async def monitor_reminders(self):
        """
        Background task to check for due reminders every minute
        Called by background task in app.py
        """
        while True:
            try:
                await self._check_and_send_due_reminders()
                
                # Check every 60 seconds
                await asyncio.sleep(60)
            
            except asyncio.CancelledError:
                logger.info("Reminder monitor stopped")
                break
            
            except Exception as e:
                logger.error(f"Error in reminder monitor: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_send_due_reminders(self):
        """Check for reminders that are due and send notifications"""
        try:
            # Get all pending reminders that are due
            pending_reminders = await self.db_manager.get_pending_reminders(self.user_id)
            
            for reminder in pending_reminders:
                await self._send_reminder_notification(reminder)
        
        except Exception as e:
            logger.error(f"Error checking due reminders: {e}")
    
    async def _send_reminder_notification(self, reminder: Dict):
        """Send a reminder notification"""
        try:
            # Format message
            message = self.message_formatter.format_reminder(
                reminder_text=reminder['reminder_text'],
                scheduled_time=reminder['scheduled_for']
            )
            
            # Create button
            buttons = [
                [
                    {"text": "✅ Done", "callback_data": f"reminder:done:{reminder['id']}"}
                ]
            ]
            
            # Send notification
            result = await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type="reminders",
                notification_subtype="scheduled",
                message_text=message,
                buttons=buttons,
                message_data={
                    "reminder_id": str(reminder['id']),
                    "reminder_text": reminder['reminder_text'],
                    "scheduled_for": reminder['scheduled_for'].isoformat()
                }
            )
            
            if result['success']:
                # Mark reminder as sent
                await self.db_manager.mark_reminder_sent(str(reminder['id']))
                logger.info(f"Sent reminder notification: {reminder['id']}")
            else:
                logger.error(f"Failed to send reminder: {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")


# Global instance
_reminder_handler = None

def get_reminder_notification_handler() -> ReminderNotificationHandler:
    """Get the global reminder notification handler"""
    global _reminder_handler
    if _reminder_handler is None:
        _reminder_handler = ReminderNotificationHandler()
    return _reminder_handler

async def start_reminder_notifications():
    """Start the reminder notification background monitor"""
    handler = get_reminder_notification_handler()
    await handler.monitor_reminders()
