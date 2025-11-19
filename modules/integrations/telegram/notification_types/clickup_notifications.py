# modules/integrations/telegram/notification_types/clickup_notifications.py
"""
ClickUp Notification Handler
Sends proactive notifications for ClickUp tasks and updates
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class ClickUpNotificationHandler:
    """
    Handles ClickUp task notifications
    
    Checks every 4 hours for:
    - Tasks due soon
    - Overdue tasks
    - High priority tasks assigned to you
    - Tasks with new comments
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
        Check ClickUp tasks (DISABLED - broken and not useful)
        """
        logger.info("⏭️ ClickUp task notifications disabled")
        return
    
    async def _get_tasks_needing_attention(self) -> List[Dict[str, Any]]:
        """Get tasks that need attention"""
        query = """
        SELECT id, clickup_task_id as task_id, task_name as name, 
               task_description as description, status, priority,
               due_date, list_name, space_name, url,
               CASE 
                   WHEN due_date < NOW() THEN true 
                   ELSE false 
               END as is_overdue,
               CASE 
                   WHEN due_date BETWEEN NOW() AND NOW() + INTERVAL '24 hours' THEN true
                   ELSE false
               END as due_soon
        FROM clickup_tasks
        WHERE user_id = $1
        AND LOWER(status) NOT IN ('complete', 'closed')
        AND (
            due_date < NOW() + INTERVAL '24 hours'  -- Due in next 24 hours or overdue
            OR priority = 1  -- Urgent priority
        )
        ORDER BY 
            CASE WHEN due_date < NOW() THEN 0 ELSE 1 END,  -- Overdue first
            due_date ASC NULLS LAST,
            priority ASC NULLS LAST
        LIMIT 10
        """
        
        try:
            results = await self.db.fetch_all(query, self.user_id)
            
            if not results:
                logger.info("No ClickUp tasks need attention")
                return []
            
            logger.info(f"Found {len(results)} ClickUp tasks needing attention")
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error fetching ClickUp tasks: {e}")
            return []
    
    async def send_daily_summary(self) -> bool:
        """
        Send daily ClickUp task summary
        
        Returns:
            True if successful
        """
        try:
            # Get task counts
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE status NOT IN ('complete', 'closed')) as active_count,
                COUNT(*) FILTER (WHERE due_date < NOW() AND status NOT IN ('complete', 'closed')) as overdue_count,
                COUNT(*) FILTER (WHERE due_date::date = CURRENT_DATE AND status NOT IN ('complete', 'closed')) as due_today_count,
                COUNT(*) FILTER (WHERE priority = 1 AND status NOT IN ('complete', 'closed')) as urgent_count
            FROM clickup_tasks
            WHERE user_id = $1
            """
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result:
                return False
            
            active = result['active_count']
            overdue = result['overdue_count']
            due_today = result['due_today_count']
            urgent = result['urgent_count']
            
            message = f"📋 *ClickUp Daily Summary*\n\n"
            message += f"*Active Tasks:* {active}\n"
            
            if due_today > 0:
                message += f"*Due Today:* {due_today} 📅\n"
            
            if overdue > 0:
                message += f"*Overdue:* {overdue} ⚠️\n"
            
            if urgent > 0:
                message += f"*Urgent:* {urgent} 🔴\n"
            
            if active == 0:
                message += "\n✅ No active tasks - time to plan!"
            elif overdue == 0 and urgent == 0:
                message += "\n🎯 On track - keep going!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='clickup',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent ClickUp daily summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send ClickUp daily summary: {e}")
            return False
