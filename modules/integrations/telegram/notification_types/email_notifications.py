# modules/integrations/telegram/notification_types/email_notifications.py
"""
Email Notification Handler
Sends PROACTIVE notifications for important emails with AI-drafted replies

UPDATED: 2025-12-19 - Now uses unified_engine for AI draft generation
Instead of just notifying "you have an email", we now:
1. Detect important email
2. Generate AI draft reply BEFORE notification
3. Send rich notification with draft + one-tap actions
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from modules.core.database import db_manager

logger = logging.getLogger(__name__)


class EmailNotificationHandler:
    """
    Handles email notifications with AI-powered draft replies
    
    Flow:
    1. Check for important/urgent emails (hourly)
    2. For each, generate AI draft reply via unified_engine
    3. Send rich notification with draft + action buttons
    4. User taps once → reply sent
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None  # Lazy initialization
        self._unified_engine = None  # Lazy initialization
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    @property
    def unified_engine(self):
        """Lazy-load UnifiedProactiveEngine"""
        if self._unified_engine is None:
            from modules.proactive.unified_engine import get_unified_engine
            self._unified_engine = get_unified_engine()
        return self._unified_engine
    
    async def check_and_notify(self) -> bool:
        """
        Check for important unread emails and send proactive notifications
        
        Now uses unified_engine to generate AI draft replies before notification.
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get important unread emails (with full body for AI)
            important_emails = await self._get_important_emails()
            
            if not important_emails:
                logger.debug("No important emails to process")
                return False
            
            logger.info(f"📧 Processing {len(important_emails)} important emails for proactive drafts")
            
            # Process each email through unified engine
            processed_count = 0
            for email in important_emails:
                try:
                    queue_id = await self._process_email_proactively(email)
                    if queue_id:
                        processed_count += 1
                        logger.info(f"✅ Processed email: {email.get('subject_line', 'No subject')[:50]}")
                except Exception as e:
                    logger.error(f"Failed to process email {email.get('message_id')}: {e}")
                    continue
            
            logger.info(f"📧 Processed {processed_count}/{len(important_emails)} emails")
            return processed_count > 0
            
        except Exception as e:
            logger.error(f"Error checking email notifications: {e}")
            return False
    
    async def _get_important_emails(self) -> List[Dict[str, Any]]:
        """
        Get important emails from the last hour WITH full body for AI drafting
        
        Important = high priority OR requires response
        """
        query = """
        SELECT id, message_id, thread_id, subject_line, sender_email, sender_name,
               snippet, body, email_date, priority_level, category, requires_response
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
        # Check telegram_notifications table
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'email'
        AND metadata->>'message_id' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, message_id)
        if result and result['count'] > 0:
            return True
        
        # Also check unified_proactive_queue (may have been processed by engine)
        query2 = """
        SELECT COUNT(*) as count
        FROM unified_proactive_queue
        WHERE source_type = 'email'
        AND source_id = $1
        """
        
        result2 = await self.db.fetch_one(query2, message_id)
        return result2['count'] > 0 if result2 else False
    
    async def _process_email_proactively(self, email: Dict[str, Any]) -> Optional[str]:
        """
        Process email through unified engine for AI draft generation
        
        Args:
            email: Email data from database
            
        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            # Transform database row to format expected by unified_engine
            email_data = {
                'message_id': email['message_id'],
                'thread_id': email.get('thread_id'),
                'subject': email.get('subject_line', 'No subject'),
                'sender_email': email.get('sender_email', 'Unknown'),
                'sender_name': email.get('sender_name'),
                'snippet': email.get('snippet', ''),
                'body': email.get('body', ''),
                'received_at': email.get('email_date'),
                'priority_level': email.get('priority_level', 'normal'),
                'requires_response': email.get('requires_response', False),
            }
            
            # If no body, we can still try with snippet
            if not email_data['body'] and email_data['snippet']:
                email_data['body'] = email_data['snippet']
                logger.warning(f"⚠️ No body for email {email['message_id']}, using snippet")
            
            # Process through unified engine - this handles:
            # 1. AI draft generation
            # 2. Storage in unified_proactive_queue
            # 3. Sending Telegram notification with action buttons
            queue_id = await self.unified_engine.process_email(email_data)
            
            return queue_id
            
        except Exception as e:
            logger.error(f"Failed to process email proactively: {e}")
            return None
    
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
                COUNT(*) FILTER (WHERE category = 'inbox') as inbox_count,
                COUNT(*) FILTER (WHERE priority_level IN ('high', 'urgent')) as important_count,
                COUNT(*) FILTER (WHERE requires_response = true) as needs_response,
                COUNT(*) as total_today
            FROM google_gmail_analysis
            WHERE user_id = $1
            AND DATE(email_date) = CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result:
                return False
            
            inbox = result['inbox_count'] or 0
            important = result['important_count'] or 0
            needs_response = result['needs_response'] or 0
            total = result['total_today'] or 0
            
            # Build summary message
            message = f"📬 *Daily Email Summary*\n\n"
            message += f"*Received Today:* {total} email{'s' if total != 1 else ''}\n"
            message += f"*Inbox:* {inbox}\n"
            
            if important > 0:
                message += f"*Important:* {important} ⚠️\n"
            
            if needs_response > 0:
                message += f"*Needs Response:* {needs_response} 📝\n"
            
            if needs_response == 0 and important == 0:
                message += "\n✅ Nothing urgent today!"
            elif needs_response > 0:
                message += f"\n_You have {needs_response} email{'s' if needs_response != 1 else ''} waiting for a reply._"
            
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
        Mark email as read in database (called from callback handler)
        
        Note: This doesn't mark it read in Gmail - that would require
        an API call. This just updates our local tracking.
        
        Args:
            email_db_id: Database ID of email
        
        Returns:
            True if successful
        """
        try:
            query = """
            UPDATE google_gmail_analysis
            SET requires_response = false
            WHERE id = $1 AND user_id = $2
            """
            
            await self.db.execute(query, email_db_id, self.user_id)
            logger.info(f"Marked email {email_db_id} as read")
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return False
    
    async def archive_email(self, email_db_id: int) -> bool:
        """
        Archive email in database (called from callback handler)
        
        Note: This doesn't archive in Gmail - that would require
        an API call. This just updates our local tracking.
        
        Args:
            email_db_id: Database ID of email
        
        Returns:
            True if successful
        """
        try:
            query = """
            UPDATE google_gmail_analysis
            SET category = 'archived', requires_response = false
            WHERE id = $1 AND user_id = $2
            """
            
            await self.db.execute(query, email_db_id, self.user_id)
            logger.info(f"Archived email {email_db_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to archive email: {e}")
            return False
