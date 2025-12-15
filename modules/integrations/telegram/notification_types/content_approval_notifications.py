# modules/integrations/telegram/notification_types/content_approval_notifications.py
"""
Content Approval Notification Handler
Monitors content_recommendation_queue and sends rich approval notifications
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
import json
import html

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

class ContentApprovalNotificationHandler:
    """
    Handles content approval notifications from queue
    
    Monitors content_recommendation_queue table every 30 seconds and sends
    rich notifications with full preview and approval buttons.
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        self._sent_queue_ids = set()  # Track what we've already sent
    
    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def check_and_notify(self) -> bool:
        """
        Check for pending content in queue and send approval notifications
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get pending items from queue
            pending_items = await self._get_pending_content()
            
            if not pending_items:
                return False
            
            # Send notification for each new item
            sent_count = 0
            for item in pending_items:
                queue_id = str(item['id'])
                
                # Skip if already sent
                if queue_id in self._sent_queue_ids:
                    continue
                
                # Send approval notification
                success = await self._send_approval_notification(item)
                
                if success:
                    self._sent_queue_ids.add(queue_id)
                    sent_count += 1
            
            if sent_count > 0:
                logger.info(f"✅ Sent {sent_count} content approval notifications")
            
            return sent_count > 0
            
        except Exception as e:
            logger.error(f"Failed to check content approvals: {e}", exc_info=True)
            return False
    
    async def _get_pending_content(self) -> List[Dict[str, Any]]:
        """Get pending content from recommendation queue"""
        query = """
            SELECT 
                id,
                content_type,
                business_area,
                generated_content,
                recommendation_score,
                created_at
            FROM content_recommendation_queue
            WHERE status = 'pending'
            AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY recommendation_score DESC, created_at DESC
            LIMIT 5
        """
        
        try:
            results = await self.db.fetch_all(query)
            
            if not results:
                return []
            
            return [dict(r) for r in results]
            
        except Exception as e:
            logger.error(f"Failed to get pending content: {e}")
            return []
    
    async def _send_approval_notification(self, item: Dict[str, Any]) -> bool:
        """Send approval notification for a content item"""
        try:
            queue_id = str(item['id'])
            content_type = item['content_type']
            business_area = item['business_area']
            confidence = int(item['recommendation_score'] * 100)
            
            # Parse generated content
            content_data = item['generated_content']
            if isinstance(content_data, str):
                content_data = json.loads(content_data)
            
            # Build notification based on content type
            if content_type == 'bluesky_post':
                message = await self._format_bluesky_approval(
                    content_data, business_area, confidence
                )
                buttons = self._create_bluesky_buttons(queue_id, business_area)
            
            elif content_type == 'blog_post':
                message = await self._format_blog_approval(
                    content_data, business_area, confidence
                )
                buttons = self._create_blog_buttons(queue_id)
            
            else:
                logger.warning(f"Unknown content type: {content_type}")
                return False
            
            # Send notification
            result = await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='content_approval',
                notification_subtype=content_type,
                message_text=message,
                buttons=buttons,
                message_data={
                    'queue_id': queue_id,
                    'content_type': content_type,
                    'business_area': business_area
                }
            )
            
            return result.get('success', False)
            
        except Exception as e:
            logger.error(f"Failed to send approval notification: {e}", exc_info=True)
            return False
    
    async def _format_bluesky_approval(
        self,
        content_data: Dict,
        business_area: str,
        confidence: int
    ) -> str:
        """Format Bluesky post approval notification using HTML"""
        
        # Extract post content and escape HTML special characters
        post_text = html.escape(content_data.get('post_text', 'No content'))
        account = html.escape(content_data.get('account_id', business_area))
        keyword = html.escape(content_data.get('keyword', 'topic'))
        
        # Use HTML formatting (more forgiving than Markdown)
        message = f"📱 <b>Bluesky Draft Ready</b>\n\n"
        message += f"<b>Account:</b> @{account}\n"
        message += f"<b>Topic:</b> {keyword}\n"
        message += f"<b>Confidence:</b> {confidence}%\n\n"
        message += f"<b>Preview:</b>\n"
        message += f"<i>{post_text[:280]}</i>\n\n"
        
        char_count = len(content_data.get('post_text', ''))
        message += f"📊 {char_count}/300 characters"
        
        return message
    
    async def _format_blog_approval(
        self,
        content_data: Dict,
        business_area: str,
        confidence: int
    ) -> str:
        """Format blog post approval notification using HTML"""
        
        # Escape HTML special characters in user content
        title = html.escape(content_data.get('title', 'Untitled'))
        business_area_escaped = html.escape(business_area)
        word_count = content_data.get('word_count', 0)
        
        message = f"📝 <b>Blog Post Draft Ready</b>\n\n"
        message += f"<b>Title:</b> {title}\n"
        message += f"<b>Business:</b> {business_area_escaped}\n"
        message += f"<b>Confidence:</b> {confidence}%\n\n"
        message += f"📊 {word_count} words"
        
        return message
    
    def _create_bluesky_buttons(self, queue_id: str, account: str) -> list:
        """Create approval buttons for Bluesky post"""
        return [
            [
                {'text': '✅ Post Now', 'callback_data': f"content:post_now:{queue_id}:{account}"},
                {'text': '✏️ Edit', 'callback_data': f"content:edit:{queue_id}"}
            ],
            [
                {'text': '💾 Save for Later', 'callback_data': f"content:save:{queue_id}"},
                {'text': '❌ Dismiss', 'callback_data': f"content:dismiss:{queue_id}"}
            ]
        ]
    
    def _create_blog_buttons(self, queue_id: str) -> list:
        """Create approval buttons for blog post"""
        return [
            [
                {'text': '📄 View Full Post', 'callback_data': f"content:view:{queue_id}"},
                {'text': '✏️ Edit', 'callback_data': f"content:edit:{queue_id}"}
            ],
            [
                {'text': '💾 Save Draft', 'callback_data': f"content:save:{queue_id}"},
                {'text': '❌ Dismiss', 'callback_data': f"content:dismiss:{queue_id}"}
            ]
        ]
