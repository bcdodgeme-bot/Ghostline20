# modules/integrations/telegram/notification_types/calendar_notifications.py
"""
Calendar Notification Handler
Sends proactive calendar event reminders
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class CalendarNotificationHandler:
    """
    Handles calendar event notifications
    
    Checks every 30 minutes for upcoming events
    Sends reminders at configurable intervals before events
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None  # Lazy initialization
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        self.reminder_minutes = [15, 60]  # Remind 15 min and 1 hour before

# 2. ADD THIS PROPERTY RIGHT AFTER __init__:
    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def check_and_notify(self) -> bool:
        """
        Check for upcoming calendar events and send reminders
        
        Returns:
            True if any reminders were sent
        """
        try:
            # Get upcoming events that need reminders
            events = await self._get_upcoming_events()
            
            if not events:
                return False
            
            sent_count = 0
            for event in events:
                # Check if we should send reminder for this event
                should_send = await self._should_send_reminder(event)
                if should_send:
                    await self._send_calendar_notification(event)
                    sent_count += 1
            
            return sent_count > 0
            
        except Exception as e:
            logger.error(f"Error checking calendar notifications: {e}")
            return False
    
    async def _get_upcoming_events(self) -> List[Dict[str, Any]]:
        """Get calendar events in the next 2 hours"""
        query = """
        SELECT id, event_id, summary, description, start_time, end_time,
               location, attendees_count, calendar_id
        FROM google_calendar_events
        WHERE user_id = $1
        AND start_time > NOW()
        AND start_time < NOW() + INTERVAL '2 hours'
        ORDER BY start_time
        """
        
        results = await self.db.fetch_all(query, self.user_id)
        
        if not results:
            return []
        
        return [dict(r) for r in results]
    
    async def _should_send_reminder(self, event: Dict[str, Any]) -> bool:
        """
        Check if we should send reminder for this event
        
        Sends reminders at configured intervals (15 min, 1 hour before)
        """
        start_time = event['start_time']
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        
        # FIX: Use timezone-aware datetime
        now = datetime.now(timezone.utc)
        if start_time.tzinfo is None:
            # If start_time is naive, assume UTC
            start_time = start_time.replace(tzinfo=timezone.utc)
        
        minutes_until = (start_time - datetime.now(timezone.utc)).total_seconds() / 60
        
        # Check if we're within a reminder window
        for reminder_min in self.reminder_minutes:
            # Window is ±2 minutes around the reminder time
            if abs(minutes_until - reminder_min) <= 2:
                # Check if we already sent this reminder
                already_sent = await self._check_if_reminder_sent(
                    event['id'], 
                    reminder_min
                )
                if not already_sent:
                    return True
        
        return False
    
    async def _check_if_reminder_sent(self, event_db_id: int, reminder_minutes: int) -> bool:
        """Check if reminder was already sent for this event at this interval"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'calendar'
        AND metadata->>'event_db_id' = $2
        AND metadata->>'reminder_minutes' = $3
        AND sent_at > NOW() - INTERVAL '3 hours'
        """
        
        result = await self.db.fetch_one(
            query, 
            self.user_id, 
            str(event_db_id), 
            str(reminder_minutes)
        )
        
        return result['count'] > 0 if result else False
    
    async def _send_calendar_notification(self, event: Dict[str, Any]) -> None:
        """Send calendar event reminder"""
        summary = event['summary']
        start_time = event['start_time']
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
            
        # FIX: Use timezone-aware datetime
        now = datetime.now(timezone.utc)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
    
        
        description = event.get('description', '')
        location = event.get('location', '')
        attendees_count = event.get('attendees_count', 0)
        
        # Calculate time until event
        minutes_until = int((start_time - datetime.now(timezone.utc)).total_seconds() / 60)
        
        # Format time
        time_str = start_time.strftime("%I:%M %p").lstrip('0')
        
        # Build message
        message = f"📅 *Calendar Reminder*\n\n"
        message += f"*{summary}*\n\n"
        
        if minutes_until <= 15:
            message += f"⏰ Starting in {minutes_until} minutes ({time_str})\n"
        else:
            hours = minutes_until // 60
            message += f"⏰ Starting in {hours} hour(s) ({time_str})\n"
        
        if location:
            message += f"📍 {location}\n"
        
        if description:
            # Truncate long descriptions
            desc = description[:200] + "..." if len(description) > 200 else description
            message += f"\n{desc}\n"
        
        if attendees_count > 0:
            message += f"👥 *Attendees:* {attendees_count}\n"
        
        # Create quick action buttons (if meeting link exists)
        buttons = None
        if event.get('meeting_link'):
            buttons = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Join Meeting",
                            "url": event['meeting_link']
                        }
                    ]
                ]
            }
        elif location:
            buttons = {
                "inline_keyboard": [
                    [
                        {
                            "text": "📍 Get Directions",
                            "url": f"https://maps.google.com/?q={location}"
                        }
                    ]
                ]
            }
        
        # Metadata
        metadata = {
            'event_db_id': event['id'],
            'event_id': event['event_id'],
            'summary': summary,
            'start_time': start_time.isoformat(),
            'reminder_minutes': minutes_until,
            'calendar_id': event.get('calendar_id', 'primary')
        }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='calendar',
            notification_subtype='event_reminder',
            message_text=message,
            buttons=buttons,  # Note: simplified buttons format, not reply_markup
            message_data=metadata
        )
        
        logger.info(f"✅ Sent calendar reminder: {summary} in {minutes_until} min")
    
    async def send_daily_agenda(self) -> bool:
        """
        Send daily agenda summary (call at start of day)
        
        Returns:
            True if successful
        """
        try:
            # Get today's events
            query = """
            SELECT COUNT(*) as count, MIN(start_time) as first_event
            FROM google_calendar_events
            WHERE user_id = $1
            AND DATE(start_time) = CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result or result['count'] == 0:
                message = "📅 *Today's Schedule*\n\n"
                message += "No events scheduled for today.\n"
                message += "Enjoy your free day! 🎉"
            else:
                count = result['count']
                first_event = result['first_event']
                
                message = f"📅 *Today's Schedule*\n\n"
                message += f"You have {count} event{'s' if count != 1 else ''} today.\n"
                
                if first_event:
                    first_time = first_event.strftime("%I:%M %p").lstrip('0')
                    message += f"First event starts at {first_time}\n"
                
                message += "\n_You'll receive reminders before each event._"
            
            # Send summary
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='calendar',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'agenda_type': 'daily_summary'}
            )
            
            logger.info("✅ Sent daily agenda summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily agenda: {e}")
            return False
