# modules/integrations/telegram/notification_types/email_notifications.py
"""
Email Notification Handler
Sends proactive notifications for important emails
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class EmailNotificationHandler:
    """
    Handles email notifications
    
    Checks every hour for important/urgent emails
    Only notifies for high-priority emails to avoid spam
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
        Check for important unread emails and send notifications
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get important unread emails
            important_emails = await self._get_important_emails()
            
            if not important_emails:
                return False
            
            # Send notification for each important email
            for email in important_emails:
                await self._send_email_notification(email)
            
            return len(important_emails) > 0
            
        except Exception as e:
            logger.error(f"Error checking email notifications: {e}")
            return False
    
    async def _get_important_emails(self) -> List[Dict[str, Any]]:
        """
        Get important emails from the last hour
        
        Important = high priority OR requires response
        """
        query = """
        SELECT id, message_id, subject_line, sender_email, 
               email_date, priority_level, category, requires_response
        FROM google_gmail_analysis
        WHERE user_id = $1
        AND email_date > NOW() - INTERVAL '1 hour'
        AND (
            priority_level IN ('high', 'urgent')
            OR requires_response = true
        )
        ORDER BY email_date DESC
        LIMIT 5
        """
        
        results = await self.db.fetch_all(query, self.user_id)
        
        if not results:
            return []
        
        # Filter out emails we already notified about
        filtered = []
        for email in results:
            already_notified = await self._check_if_notified(email['message_id'])
            if not already_notified:
                filtered.append(dict(email))
        
    return filtered
    
    async def _check_if_notified(self, message_id: str) -> bool:
        """Check if we already sent notification for this email"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'email'
        AND metadata->>'message_id' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, message_id)
        return result['count'] > 0 if result else False
    
    async def _send_email_notification(self, email: Dict[str, Any]) -> None:
        """Send email notification"""
        subject = email['subject_line']
        sender_email = email['sender_email']
        priority = email.get('priority_level', 'normal')
        requires_response = email.get('requires_response', False)
        email_date = email['email_date']
        
        if isinstance(email_date, str):
            email_date = datetime.fromisoformat(email_date)
        
        # Calculate time ago
        time_ago = datetime.now() - email_date
        if time_ago.total_seconds() < 60:
            time_str = "Just now"
        elif time_ago.total_seconds() < 3600:
            mins = int(time_ago.total_seconds() / 60)
            time_str = f"{mins} minute{'s' if mins != 1 else ''} ago"
        else:
            hours = int(time_ago.total_seconds() / 3600)
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
        
        # Priority emoji
        priority_emoji = "🔴" if priority == "urgent" else "🟡" if priority == "high" else "📧"
        
        # Build message
        message = f"{priority_emoji} *New Important Email*\n\n"
        message += f"*From:* {sender_email}\n"
        message += f"*Subject:* {subject}\n"
        message += f"*Received:* {time_str}\n"
        
        if priority in ['high', 'urgent']:
            message += f"*Priority:* {priority.upper()}\n"
        
        if requires_response:
            message += f"\n⚠️ *Requires Response*"
        
        # Create action buttons
        buttons = {
            "inline_keyboard": [
                [
                    {
                        "text": "📖 Mark as Read",
                        "callback_data": f"email_read:{email['id']}"
                    },
                    {
                        "text": "🗑️ Archive",
                        "callback_data": f"email_archive:{email['id']}"
                    }
                ]
            ]
        }
        
        # Metadata
        metadata = {
            'message_id': email['message_id'],
            'subject': subject,
            'sender': sender_email,
            'received_at': email_date.isoformat(),
            'priority': priority,
            'requires_response': requires_response
        }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='email',
            notification_subtype='important_email',
            message_text=message,
            buttons=buttons,  # Note: convert reply_markup to simple list format
            message_data=metadata
        )
        
        logger.info(f"✅ Sent email notification: {subject}")
    
    async def send_daily_summary(self) -> bool:
        """
        Send daily email summary
        
        Returns:
            True if successful
        """
        try:
            # Get today's email stats
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE is_read = false) as unread_count,
                COUNT(*) FILTER (WHERE is_important = true AND is_read = false) as important_count,
                COUNT(*) as total_today
            FROM gmail_messages
            WHERE user_id = $1
            AND DATE(received_date) = CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result:
                return False
            
            unread = result['unread_count']
            important = result['important_count']
            total = result['total_today']
            
            # Build summary message
            message = f"📬 *Daily Email Summary*\n\n"
            message += f"*Received Today:* {total} email{'s' if total != 1 else ''}\n"
            message += f"*Unread:* {unread}\n"
            
            if important > 0:
                message += f"*Important Unread:* {important} ⚠️\n"
            
            if unread == 0:
                message += "\n✅ Inbox Zero! Great job!"
            elif important > 0:
                message += f"\n_You have {important} important email{'s' if important != 1 else ''} waiting._"
            
            # Send summary
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='email',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent daily email summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily email summary: {e}")
            return False
    
    async def mark_as_read(self, email_db_id: int) -> bool:
        """
        Mark email as read (called from callback handler)
        
        Args:
            email_db_id: Database ID of email
        
        Returns:
            True if successful
        """
        query = """
        UPDATE gmail_messages
        SET is_read = true, read_at = NOW()
        WHERE id = $1 AND user_id = $2
        """
        
        await self.db.execute(query, email_db_id, self.user_id)
        logger.info(f"Marked email {email_db_id} as read")
        return True
    
    async def archive_email(self, email_db_id: int) -> bool:
        """
        Archive email (called from callback handler)
        
        Args:
            email_db_id: Database ID of email
        
        Returns:
            True if successful
        """
        query = """
        UPDATE gmail_messages
        SET archived = true, archived_at = NOW()
        WHERE id = $1 AND user_id = $2
        """
        
        await self.db.execute(query, email_db_id, self.user_id)
        logger.info(f"Archived email {email_db_id}")
        return True
