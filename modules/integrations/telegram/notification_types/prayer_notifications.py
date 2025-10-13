# modules/integrations/telegram/notification_types/prayer_notifications.py
"""
Prayer Times Notification Handler
Sends proactive prayer time reminders via Telegram
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class PrayerNotificationHandler:
    """
    Handles prayer time notifications
    
    Checks every 5 minutes for upcoming prayer times
    Sends notification 15 minutes before each prayer
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None  # Lazy initialization
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
        
        # Prayer names for display
        self.prayer_names = {
            'fajr': 'Fajr',
            'dhuhr': 'Dhuhr',
            'asr': 'Asr',
            'maghrib': 'Maghrib',
            'isha': 'Isha'
        }
    
    async def check_and_notify(self) -> bool:
        """
        Check if any prayer is coming up soon and send notification
        
        Returns:
            True if notification was sent, False otherwise
        """
        try:
            # Get today's prayer times from cache
            prayer_times = await self._get_todays_prayer_times()
            
            if not prayer_times:
                logger.warning("No prayer times found in cache for today")
                return False
            
            # Check each prayer
            now = datetime.now()
            current_time = now.time()
            
            for prayer_name, prayer_time in prayer_times.items():
                if prayer_name not in self.prayer_names:
                    continue
                
                # Calculate notification time (15 minutes before prayer)
                notification_time = self._subtract_minutes(prayer_time, 15)
                
                # Check if we should send notification now
                # (within 5 minute window from notification time)
                if self._is_within_window(current_time, notification_time, window_minutes=5):
                    # Check if we already sent notification today
                    already_sent = await self._check_if_sent_today(prayer_name)
                    
                    if not already_sent:
                        # Send notification
                        await self._send_prayer_notification(prayer_name, prayer_time)
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking prayer notifications: {e}")
            return False
    
    async def _get_todays_prayer_times(self) -> Optional[Dict[str, time]]:
        """Get today's prayer times from database cache"""
        query = """
        SELECT fajr_time, dhuhr_time, asr_time, maghrib_time, isha_time
        FROM prayer_times_cache
        WHERE user_id = $1 AND date = CURRENT_DATE
        """
        
        result = await self.db.fetch_one(query, self.user_id)
        
        if not result:
            return None
        
        return {
            'fajr': result['fajr_time'],
            'dhuhr': result['dhuhr_time'],
            'asr': result['asr_time'],
            'maghrib': result['maghrib_time'],
            'isha': result['isha_time']
        }
    
    async def _check_if_sent_today(self, prayer_name: str) -> bool:
        """Check if notification was already sent today for this prayer"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1 
        AND notification_type = 'prayer'
        AND DATE(sent_at) = CURRENT_DATE
        AND metadata->>'prayer_name' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, prayer_name)
        
        if result and result['count'] > 0:
            return True
        
        return False
    
    def _subtract_minutes(self, t: time, minutes: int) -> time:
        """Subtract minutes from a time object"""
        dt = datetime.combine(datetime.today(), t)
        dt = dt - timedelta(minutes=minutes)
        return dt.time()
    
    def _is_within_window(self, current: time, target: time, window_minutes: int = 5) -> bool:
        """Check if current time is within window of target time"""
        current_dt = datetime.combine(datetime.today(), current)
        target_dt = datetime.combine(datetime.today(), target)
        
        # Check if current is between target and target + window
        upper_bound = target_dt + timedelta(minutes=window_minutes)
        
        return target_dt <= current_dt < upper_bound
    
    async def _send_prayer_notification(self, prayer_name: str, prayer_time: time) -> None:
        """Send prayer time notification"""
        # Format time nicely
        formatted_time = prayer_time.strftime("%I:%M %p").lstrip('0')
        display_name = self.prayer_names[prayer_name]
        
        # Create message
        message = f"🕌 *{display_name} Prayer Reminder*\n\n"
        message += f"Prayer time is at *{formatted_time}*\n"
        message += f"_15 minutes from now_\n\n"
        message += "May Allah accept your prayers 🤲"
        
        # Metadata for tracking
        metadata = {
            'prayer_name': prayer_name,
            'prayer_time': prayer_time.isoformat(),
            'notification_time': datetime.now().isoformat()
        }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            notification_type='prayer',
            message=message,
            metadata=metadata
        )
        
        logger.info(f"✅ Sent {display_name} prayer notification for {formatted_time}")
    
    async def send_daily_schedule(self) -> bool:
        """Send complete daily prayer schedule (can be called manually)"""
        try:
            prayer_times = await self._get_todays_prayer_times()
            
            if not prayer_times:
                return False
            
            # Build schedule message
            message = "🕌 *Today's Prayer Times*\n\n"
            
            for prayer_name in ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha']:
                prayer_time = prayer_times.get(prayer_name)
                if prayer_time:
                    display_name = self.prayer_names[prayer_name]
                    formatted_time = prayer_time.strftime("%I:%M %p").lstrip('0')
                    message += f"• *{display_name}*: {formatted_time}\n"
            
            message += "\n_You'll receive reminders 15 minutes before each prayer_ 🔔"
            
            # Send schedule
            await self.notification_manager.send_notification(
                notification_type='prayer',
                message=message,
                metadata={'schedule_type': 'daily'}
            )
            
            logger.info("✅ Sent daily prayer schedule")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily prayer schedule: {e}")
            return False
