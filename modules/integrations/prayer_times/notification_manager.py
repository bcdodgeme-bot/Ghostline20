# modules/integrations/prayer_times/notification_manager.py
"""
Prayer Notification Manager - Automatic Prayer Time Reminders
Handles 15-minute advance notifications with personality integration
"""

import asyncio
from datetime import datetime, timedelta, time, date
from typing import Dict, List, Any, Optional
import logging

from ...core.database import db_manager
from .database_manager import get_prayer_database_manager

logger = logging.getLogger(__name__)

class PrayerNotificationManager:
    """Manages automatic prayer time notifications with personality"""
    
    def __init__(self):
        self.running = False
        self.background_task: Optional[asyncio.Task] = None
        self.check_interval = 60  # Check every minute
        self.notification_advance = 15  # 15 minutes before prayer
        
        # Track sent notifications to avoid duplicates
        self.sent_notifications = set()
        
        # User preferences (can be expanded later)
        self.user_preferences = {
            'enabled': True,
            'advance_minutes': 15,
            'personality_enabled': False,
            'prayers_to_notify': ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha']
        }
    
    async def start_notification_service(self):
        """Start the background prayer notification service"""
        if self.running:
            logger.warning("Prayer notification service already running")
            return
        
        self.running = True
        self.background_task = asyncio.create_task(self._notification_loop())
        logger.info("🕌 Prayer notification service started (15-minute advance alerts)")
    
    async def stop_notification_service(self):
        """Stop the background notification service"""
        self.running = False
        
        if self.background_task:
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🕌 Prayer notification service stopped")
    
    async def _notification_loop(self):
        """Main notification loop - checks every minute for upcoming prayers"""
        logger.info("🔄 Starting prayer notification loop")
        
        while self.running:
            try:
                await self._check_and_send_notifications()
                
                # Wait for next check
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in prayer notification loop: {e}")
                # Continue running even if there's an error
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_send_notifications(self):
        """Check if any prayers need notifications and send them"""
        try:
            # Get prayer database manager
            prayer_manager = await get_prayer_database_manager()
            
            # Get today's prayer times
            prayer_data = await prayer_manager.get_todays_prayer_times()
            if not prayer_data:
                logger.warning("Could not get prayer times for notification check")
                return
            
            prayer_times = prayer_data['prayer_times']
            now = datetime.now()
            today = date.today()
            
            # Check each prayer
            for prayer_name, prayer_time in prayer_times.items():
                if prayer_name not in self.user_preferences['prayers_to_notify']:
                    continue
                
                # Convert prayer time to datetime
                prayer_datetime = datetime.combine(today, prayer_time)
                
                # Calculate notification time (15 minutes before)
                notification_time = prayer_datetime - timedelta(minutes=self.notification_advance)
                
                # Check if we should send notification now
                if self._should_send_notification(now, notification_time, prayer_name, today):
                    await self._send_prayer_notification(prayer_name, prayer_time, prayer_datetime)
            
        except Exception as e:
            logger.error(f"Error checking prayer notifications: {e}")
    
    def _should_send_notification(self, now: datetime, notification_time: datetime, 
                                prayer_name: str, prayer_date: date) -> bool:
        """Determine if we should send a notification now"""
        
        # Create unique key for this notification
        notification_key = f"{prayer_date}_{prayer_name}"
        
        # Check if already sent
        if notification_key in self.sent_notifications:
            return False
        
        # Check if notification time has passed but prayer hasn't happened yet
        time_diff = abs((now - notification_time).total_seconds())
        
        # Send if we're within 1 minute of notification time
        if time_diff <= 60:
            return True
        
        return False
    
    async def _send_prayer_notification(self, prayer_name: str, prayer_time: time, 
                                      prayer_datetime: datetime):
        """Send a prayer notification to the chat system"""
        try:
            # Mark as sent first to avoid duplicates
            today = date.today()
            notification_key = f"{today}_{prayer_name}"
            self.sent_notifications.add(notification_key)
            
            # Calculate time until prayer
            now = datetime.now()
            time_until = prayer_datetime - now
            minutes_until = int(time_until.total_seconds() / 60)
            
            # Generate notification message with personality
            message = await self._generate_notification_message(prayer_name, prayer_time, minutes_until)
            
            # Send to chat system
            await self._post_to_chat(message)
            
            logger.info(f"✅ Sent prayer notification for {prayer_name} at {prayer_time}")
            
        except Exception as e:
            logger.error(f"Failed to send prayer notification for {prayer_name}: {e}")
            # Remove from sent set so we can try again
            notification_key = f"{date.today()}_{prayer_name}"
            self.sent_notifications.discard(notification_key)
    
    async def _generate_notification_message(self, prayer_name: str, prayer_time: time, 
                                           minutes_until: int) -> str:
        """Generate a notification message, optionally with personality"""
        
        prayer_display = prayer_name.title()
        time_display = prayer_time.strftime("%I:%M %p").lstrip('0')
        
        if self.user_preferences['personality_enabled']:
            # Use personality system for more natural messages
            try:
                from ...ai.personality_engine import get_personality_engine
                
                personality_engine = get_personality_engine()
                
                # Create context for personality
                context = {
                    'prayer_name': prayer_display,
                    'prayer_time': time_display,
                    'minutes_until': minutes_until,
                    'is_urgent': minutes_until <= 5
                }
                
                # Generate personalized message
                message = await self._generate_personality_message(personality_engine, context)
                if message:
                    return message
                    
            except Exception as e:
                logger.warning(f"Failed to generate personality message, using default: {e}")
        
        # Default notification format
        return f"""🕌 **Prayer Reminder**

{prayer_display} prayer is in {minutes_until} minutes ({time_display})

⏰ Time to prepare for prayer"""
    
    async def _generate_personality_message(self, personality_engine, context: Dict) -> Optional[str]:
        """Generate a prayer notification using the personality system"""
        try:
            # Create a prayer reminder prompt
            prompt = f"""Generate a brief, respectful prayer reminder message. The user needs to be notified that {context['prayer_name']} prayer is in {context['minutes_until']} minutes at {context['prayer_time']}.

Keep it:
- Brief (2-3 lines max)
- Respectful and appropriate for Islamic prayer
- Include the 🕌 emoji
- Mention the prayer name and time
- Encourage preparation

Context: This is an automatic reminder system."""
            
            # Use personality engine to generate response
            response = await personality_engine.generate_response(
                prompt=prompt,
                context={'type': 'prayer_notification', **context},
                max_length=200
            )
            
            if response and len(response.strip()) > 10:
                return response.strip()
                
        except Exception as e:
            logger.error(f"Error generating personality prayer message: {e}")
        
        return None
    
    async def _post_to_chat(self, message: str):
        """Post notification message to the chat system"""
        try:
            # Import the new system message posting function
            from ...ai.chat import post_system_message_to_chat
            
            # Post the prayer notification as a system message
            success = await post_system_message_to_chat(message, "prayer_notification")
            
            if success:
                logger.info(f"📢 Prayer notification posted to chat successfully")
            else:
                logger.error(f"❌ Failed to post prayer notification to chat")
                
        except Exception as e:
            logger.error(f"Failed to post prayer notification to chat: {e}")
    
    def clear_daily_notifications(self):
        """Clear sent notifications for a new day"""
        current_date = date.today().isoformat()
        # Remove notifications from previous days
        self.sent_notifications = {
            key for key in self.sent_notifications 
            if key.startswith(current_date)
        }
        logger.info("🗑️ Cleared old prayer notifications for new day")
    
    async def test_notification(self, prayer_name: str = "Test") -> str:
        """Test the notification system"""
        test_time = time(12, 0)  # 12:00 PM
        message = await self._generate_notification_message(prayer_name, test_time, 15)
        logger.info(f"🧪 Test notification: {message}")
        return message
    
    def get_notification_status(self) -> Dict[str, Any]:
        """Get current status of notification service"""
        return {
            'running': self.running,
            'check_interval_seconds': self.check_interval,
            'advance_minutes': self.notification_advance,
            'sent_today': len(self.sent_notifications),
            'preferences': self.user_preferences
        }

# Global notification manager instance
_prayer_notification_manager = None

def get_prayer_notification_manager() -> PrayerNotificationManager:
    """Get the global prayer notification manager"""
    global _prayer_notification_manager
    if _prayer_notification_manager is None:
        _prayer_notification_manager = PrayerNotificationManager()
    return _prayer_notification_manager

# Convenience functions
async def start_prayer_notifications():
    """Start the prayer notification service"""
    manager = get_prayer_notification_manager()
    await manager.start_notification_service()

async def stop_prayer_notifications():
    """Stop the prayer notification service"""
    manager = get_prayer_notification_manager()
    await manager.stop_notification_service()

async def test_prayer_notification():
    """Test the prayer notification system"""
    manager = get_prayer_notification_manager()
    return await manager.test_notification()
