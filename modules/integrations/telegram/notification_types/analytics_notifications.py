# modules/integrations/telegram/notification_types/analytics_notifications.py
"""
Analytics Notification Handler
Sends proactive notifications for system analytics and insights
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class AnalyticsNotificationHandler:
    """
    Handles analytics notifications
    
    Checks every 12 hours for:
    - Daily/weekly system usage summaries
    - Performance insights
    - Notable achievements or milestones
    - System health alerts
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None  # Lazy initialization
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

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
        Check if it's time to send analytics summary
        
        Returns:
            True if notification was sent
        """
        try:
            # Check if we should send morning or evening summary
            now = datetime.now()
            
            # Morning summary (8 AM)
            if 8 <= now.hour <= 9:
                already_sent = await self._check_if_sent_today('morning')
                if not already_sent:
                    await self.send_morning_summary()
                    return True
            
            # Evening summary (8 PM)
            elif 20 <= now.hour <= 21:
                already_sent = await self._check_if_sent_today('evening')
                if not already_sent:
                    await self.send_evening_summary()
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking analytics notifications: {e}")
            return False
    
    async def _check_if_sent_today(self, summary_type: str) -> bool:
        """Check if summary was already sent today"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'analytics'
        AND DATE(sent_at) = CURRENT_DATE
        AND metadata->>'summary_type' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, summary_type)
        return result['count'] > 0 if result else False
    
    async def _get_analytics_summary(self, days: int = 1) -> Dict[str, Any]:
        """Get website analytics summary from google_analytics_data"""
        query = """
        SELECT 
            site_name,
            metrics,
            dimensions,
            audience_insights,
            content_performance,
            traffic_patterns,
            date_range_start,
            date_range_end
        FROM google_analytics_data
        WHERE user_id = $1
        AND date_range_end >= CURRENT_DATE - $2
        ORDER BY date_range_end DESC
        LIMIT 1
        """
        
        result = await self.db.fetch_one(query, self.user_id, days)
        
        if not result:
            return {}
        
        import json
        
        # Parse JSONB fields
        metrics = result['metrics'] if isinstance(result['metrics'], dict) else json.loads(result['metrics'])
        dimensions = result['dimensions'] if isinstance(result['dimensions'], dict) else json.loads(result['dimensions'])
        
        return {
            'site_name': result['site_name'],
            'metrics': metrics,
            'dimensions': dimensions,
            'date_range': f"{result['date_range_start']} to {result['date_range_end']}"
        }
    
    async def send_morning_summary(self) -> bool:
        """
        Send morning analytics summary
        
        Returns:
            True if successful
        """
        try:
            # Get yesterday's stats
            stats = await self._get_daily_stats()
            
            message = f"☀️ *Good Morning! Daily Summary*\n\n"
            message += f"📊 *Yesterday's Activity*\n\n"
            
            # AI Interactions
            if stats.get('ai_messages'):
                message += f"💬 *AI Conversations:* {stats['ai_messages']} messages\n"
            
            # Telegram notifications
            if stats.get('notifications_sent'):
                message += f"🔔 *Notifications Sent:* {stats['notifications_sent']}\n"
            
            # Prayer times
            if stats.get('prayers_tracked'):
                message += f"🕌 *Prayers Tracked:* {stats['prayers_tracked']}\n"
            
            # Tasks/Productivity
            if stats.get('tasks_completed'):
                message += f"✅ *Tasks Completed:* {stats['tasks_completed']}\n"
            
            # Calendar events
            if stats.get('events_today'):
                message += f"\n📅 *Today's Schedule:* {stats['events_today']} event{'s' if stats['events_today'] != 1 else ''}\n"

            # Website Analytics (if available)
            if stats.get('website_sessions'):
                message += f"\n📊 *Yesterday's Website:*\n"
                message += f"   Sessions: {stats['website_sessions']}\n"
                message += f"   Users: {stats['website_users']}\n"
                message += f"   Pageviews: {stats['website_pageviews']}\n"

            # Motivational close
            message += f"\n💪 Have a productive day!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='analytics',
                notification_subtype='morning_summary',
                message_text=message,
                message_data={'summary_type': 'morning'}
            )
            
            logger.info("✅ Sent morning analytics summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send morning summary: {e}")
            return False
    
    async def send_evening_summary(self) -> bool:
        """
        Send evening analytics summary
        
        Returns:
            True if successful
        """
        try:
            # Get today's stats
            stats = await self._get_daily_stats(current_day=True)
            
            message = f"🌙 *Good Evening! Daily Recap*\n\n"
            message += f"📊 *Today's Highlights*\n\n"
            
            # AI Interactions
            if stats.get('ai_messages'):
                message += f"💬 *Conversations:* {stats['ai_messages']} messages\n"
            
            # Productivity
            if stats.get('tasks_completed'):
                message += f"✅ *Tasks Completed:* {stats['tasks_completed']}\n"
            
            if stats.get('events_attended'):
                message += f"📅 *Events Attended:* {stats['events_attended']}\n"
            
            # Emails
            if stats.get('emails_processed'):
                message += f"📧 *Emails Processed:* {stats['emails_processed']}\n"
            
            # Social media
            if stats.get('bluesky_engagements'):
                message += f"🦋 *Bluesky Engagements:* {stats['bluesky_engagements']}\n"
            
            # Achievements
            if stats.get('achievement'):
                message += f"\n🏆 *Achievement:* {stats['achievement']}\n"
            
            # Tomorrow preview
            if stats.get('events_tomorrow'):
                message += f"\n📅 *Tomorrow:* {stats['events_tomorrow']} event{'s' if stats['events_tomorrow'] != 1 else ''} scheduled\n"

            # Website Analytics (if available)
            if stats.get('website_sessions'):
                message += f"\n📊 *Today's Website Performance:*\n"
                message += f"   Sessions: {stats['website_sessions']}\n"
                message += f"   Users: {stats['website_users']}\n"

            message += f"\n🌟 Great work today!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='analytics',
                notification_subtype='evening_summary',
                message_text=message,
                message_data={'summary_type': 'evening'}

            )
            
            logger.info("✅ Sent evening analytics summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send evening summary: {e}")
            return False
    
    async def send_weekly_summary(self) -> bool:
        """
        Send weekly analytics summary (call on Sunday evening)
        
        Returns:
            True if successful
        """
        try:
            # Get this week's stats
            stats = await self._get_weekly_stats()
            
            message = f"📊 *Weekly Summary*\n\n"
            message += f"🗓️ Week of {datetime.now().strftime('%b %d, %Y')}\n\n"
            
            # Key metrics
            message += f"*Productivity*\n"
            message += f"• Tasks Completed: {stats.get('tasks_completed', 0)}\n"
            message += f"• Events Attended: {stats.get('events_attended', 0)}\n"
            message += f"• Emails Processed: {stats.get('emails_processed', 0)}\n\n"
            
            message += f"*AI Assistant*\n"
            message += f"• Conversations: {stats.get('ai_conversations', 0)}\n"
            message += f"• Messages: {stats.get('ai_messages', 0)}\n\n"
            
            message += f"*Spiritual*\n"
            message += f"• Prayers Tracked: {stats.get('prayers_tracked', 0)}\n\n"
            
            # Trends
            if stats.get('top_activity'):
                message += f"📈 *Most Active Day:* {stats['top_activity']}\n"
            
            # Website Analytics
            if stats.get('weekly_sessions'):
                message += f"\n📊 *Website Performance:*\n"
                message += f"• Sessions: {stats['weekly_sessions']}\n"
                message += f"• Users: {stats['weekly_users']}\n"
                message += f"• Pageviews: {stats['weekly_pageviews']}\n\n"

            # Looking ahead
            message += f"🎯 *Next Week:*\n"
            message += f"• {stats.get('events_next_week', 0)} events scheduled\n"
            message += f"• {stats.get('tasks_due_next_week', 0)} tasks due\n"

            message += f"\n✨ Keep up the great work!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='analytics',
                notification_subtype='weekly_summary',
                message_text=message,
                message_data={'summary_type': 'weekly'}

            )
            
            logger.info("✅ Sent weekly analytics summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send weekly summary: {e}")
            return False
    
    async def _get_daily_stats(self, current_day: bool = False) -> Dict[str, Any]:
        """Get daily statistics - personal activity + website analytics"""
        target_date = 'CURRENT_DATE' if current_day else 'CURRENT_DATE - INTERVAL \'1 day\''
        
        stats = {}
        
        # Personal Activity Stats
        # AI messages
        query = f"""
        SELECT COUNT(*) as count
        FROM conversation_messages
        WHERE user_id = $1
        AND DATE(created_at) = {target_date}
        """
        result = await self.db.fetch_one(query, self.user_id)
        stats['ai_messages'] = result['count'] if result else 0
        
        # Notifications sent
        query = f"""
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND DATE(sent_at) = {target_date}
        """
        result = await self.db.fetch_one(query, self.user_id)
        stats['notifications_sent'] = result['count'] if result else 0
        
        # Tasks completed
        # Tasks completed - using status column instead of completed_at
        query = f"""
        SELECT COUNT(*) as count
        FROM telegram_reminders
        WHERE user_id = $1
        AND status = 'completed'
        AND DATE(updated_at) = {target_date}
        """
        try:
            result = await self.db.fetch_one(query, self.user_id)
            stats['tasks_completed'] = result['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not fetch completed tasks: {e}")
            stats['tasks_completed'] = 0
        
        # Calendar events
        if current_day:
            query = """
            SELECT COUNT(*) as count
            FROM google_calendar_events
            WHERE user_id = $1
            AND DATE(start_time) = CURRENT_DATE + INTERVAL '1 day'
            """
            result = await self.db.fetch_one(query, self.user_id)
            stats['events_tomorrow'] = result['count'] if result else 0
        else:
            query = """
            SELECT COUNT(*) as count
            FROM google_calendar_events
            WHERE user_id = $1
            AND DATE(start_time) = CURRENT_DATE
            """
            result = await self.db.fetch_one(query, self.user_id)
            stats['events_today'] = result['count'] if result else 0
        
        # Website Analytics (if available)
        analytics = await self._get_analytics_summary(days=1)
        if analytics and analytics.get('metrics'):
            metrics = analytics['metrics']
            stats['website_sessions'] = metrics.get('sessions', 0)
            stats['website_users'] = metrics.get('users', 0)
            stats['website_pageviews'] = metrics.get('pageviews', 0)
        
        return stats
    
    async def _get_weekly_stats(self) -> Dict[str, Any]:
        """Get weekly statistics - personal + website"""
        stats = {}
        
        # Personal Activity
        # Tasks completed this week
        query = """
        SELECT COUNT(*) as count
        FROM telegram_reminders
        WHERE user_id = $1
        AND status = 'completed'
        AND updated_at >= DATE_TRUNC('week', CURRENT_DATE)
        """
        try:
            result = await self.db.fetch_one(query, self.user_id)
            stats['tasks_completed'] = result['count'] if result else 0
        except Exception as e:
            logger.warning(f"Could not fetch weekly completed tasks: {e}")
            stats['tasks_completed'] = 0
        
        # AI conversations this week
        query = """
        SELECT COUNT(DISTINCT thread_id) as count
        FROM conversation_messages
        WHERE user_id = $1
        AND created_at >= DATE_TRUNC('week', CURRENT_DATE)
        """
        result = await self.db.fetch_one(query, self.user_id)
        stats['ai_conversations'] = result['count'] if result else 0
        
        # Events next week
        query = """
        SELECT COUNT(*) as count
        FROM google_calendar_events
        WHERE user_id = $1
        AND start_time >= CURRENT_DATE + INTERVAL '1 day'
        AND start_time < CURRENT_DATE + INTERVAL '8 days'
        """
        result = await self.db.fetch_one(query, self.user_id)
        stats['events_next_week'] = result['count'] if result else 0
        
        # Website Analytics (last 7 days)
        analytics = await self._get_analytics_summary(days=7)
        if analytics and analytics.get('metrics'):
            metrics = analytics['metrics']
            stats['weekly_sessions'] = metrics.get('sessions', 0)
            stats['weekly_users'] = metrics.get('users', 0)
            stats['weekly_pageviews'] = metrics.get('pageviews', 0)
        
        return stats
