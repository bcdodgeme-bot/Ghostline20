# modules/integrations/telegram/notification_types/clickup_notifications.py
"""
ClickUp Notification Handler
Sends proactive notifications for ClickUp tasks and updates
"""

import logging
from datetime import datetime, timedelta
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
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
    
    async def check_and_notify(self) -> bool:
        """
        Check for ClickUp tasks that need attention
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get tasks needing attention
            tasks = await self._get_tasks_needing_attention()
            
            if not tasks:
                return False
            
            # Group tasks by urgency
            overdue = [t for t in tasks if t['is_overdue']]
            due_soon = [t for t in tasks if t['due_soon'] and not t['is_overdue']]
            high_priority = [t for t in tasks if t['priority'] == 'urgent' and not t['is_overdue']]
            
            # Send appropriate notification
            if overdue:
                await self._send_overdue_notification(overdue)
            elif due_soon:
                await self._send_due_soon_notification(due_soon)
            elif high_priority:
                await self._send_priority_notification(high_priority)
            
            return len(tasks) > 0
            
        except Exception as e:
            logger.error(f"Error checking ClickUp notifications: {e}")
            return False
    
    async def _get_tasks_needing_attention(self) -> List[Dict[str, Any]]:
        """Get tasks that need attention"""
        query = """
        SELECT id, task_id, name, description, status, priority,
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
        AND status NOT IN ('complete', 'closed')
        AND (
            due_date < NOW() + INTERVAL '24 hours'  -- Due in next 24 hours or overdue
            OR priority = 'urgent'
        )
        ORDER BY 
            CASE WHEN due_date < NOW() THEN 0 ELSE 1 END,  -- Overdue first
            due_date ASC NULLS LAST,
            CASE priority
                WHEN 'urgent' THEN 0
                WHEN 'high' THEN 1
                WHEN 'normal' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END
        LIMIT 10
        """
        
        results = await self.db.fetch_all(query, self.user_id)
        
        if not results:
            return []
        
        return [dict(r) for r in results]
    
    async def _send_overdue_notification(self, tasks: List[Dict[str, Any]]) -> None:
        """Send notification for overdue tasks"""
        count = len(tasks)
        
        message = f"⚠️ *ClickUp: {count} Overdue Task{'s' if count != 1 else ''}*\n\n"
        
        for i, task in enumerate(tasks[:5], 1):  # Show max 5 tasks
            name = task['name']
            due_date = task['due_date']
            if isinstance(due_date, str):
                due_date = datetime.fromisoformat(due_date)
            
            days_overdue = (datetime.now() - due_date).days
            
            message += f"{i}. *{name}*\n"
            message += f"   📍 {task['list_name']}\n"
            message += f"   ⏰ Overdue by {days_overdue} day{'s' if days_overdue != 1 else ''}\n\n"
        
        if count > 5:
            message += f"_...and {count - 5} more overdue task{'s' if count - 5 != 1 else ''}_\n\n"
        
        message += "🔥 Time to catch up!"
        
        # Metadata
        metadata = {
            'task_count': count,
            'notification_type': 'overdue',
            'task_ids': [t['task_id'] for t in tasks[:5]]
        }
        
        await self.notification_manager.send_notification(
            notification_type='clickup',
            message=message,
            metadata=metadata
        )
        
        logger.info(f"✅ Sent ClickUp overdue notification: {count} tasks")
    
    async def _send_due_soon_notification(self, tasks: List[Dict[str, Any]]) -> None:
        """Send notification for tasks due soon"""
        count = len(tasks)
        
        message = f"⏰ *ClickUp: {count} Task{'s' if count != 1 else ''} Due Soon*\n\n"
        
        for i, task in enumerate(tasks[:5], 1):
            name = task['name']
            due_date = task['due_date']
            if isinstance(due_date, str):
                due_date = datetime.fromisoformat(due_date)
            
            hours_until = int((due_date - datetime.now()).total_seconds() / 3600)
            
            message += f"{i}. *{name}*\n"
            message += f"   📍 {task['list_name']}\n"
            
            if hours_until < 24:
                message += f"   ⏰ Due in {hours_until} hour{'s' if hours_until != 1 else ''}\n\n"
            else:
                message += f"   ⏰ Due tomorrow\n\n"
        
        if count > 5:
            message += f"_...and {count - 5} more task{'s' if count - 5 != 1 else ''}_"
        
        # Metadata
        metadata = {
            'task_count': count,
            'notification_type': 'due_soon',
            'task_ids': [t['task_id'] for t in tasks[:5]]
        }
        
        await self.notification_manager.send_notification(
            notification_type='clickup',
            message=message,
            metadata=metadata
        )
        
        logger.info(f"✅ Sent ClickUp due soon notification: {count} tasks")
    
    async def _send_priority_notification(self, tasks: List[Dict[str, Any]]) -> None:
        """Send notification for urgent priority tasks"""
        count = len(tasks)
        
        message = f"🔴 *ClickUp: {count} Urgent Task{'s' if count != 1 else ''}*\n\n"
        
        for i, task in enumerate(tasks[:5], 1):
            name = task['name']
            
            message += f"{i}. *{name}*\n"
            message += f"   📍 {task['list_name']}\n"
            message += f"   🔥 Priority: URGENT\n\n"
        
        if count > 5:
            message += f"_...and {count - 5} more urgent task{'s' if count - 5 != 1 else ''}_"
        
        # Metadata
        metadata = {
            'task_count': count,
            'notification_type': 'urgent_priority',
            'task_ids': [t['task_id'] for t in tasks[:5]]
        }
        
        await self.notification_manager.send_notification(
            notification_type='clickup',
            message=message,
            metadata=metadata
        )
        
        logger.info(f"✅ Sent ClickUp priority notification: {count} tasks")
    
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
                COUNT(*) FILTER (WHERE priority = 'urgent' AND status NOT IN ('complete', 'closed')) as urgent_count
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
                notification_type='clickup',
                message=message,
                metadata={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent ClickUp daily summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send ClickUp daily summary: {e}")
            return False
