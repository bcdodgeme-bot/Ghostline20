# modules/integrations/telegram/notification_types/bluesky_notifications.py
"""
Bluesky Notification Handler
Sends proactive notifications for Bluesky engagement opportunities
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class BlueskyNotificationHandler:
    """
    Handles Bluesky engagement notifications
    
    Event-driven notifications for:
    - High-value engagement opportunities
    - Posts awaiting approval
    - Successful engagements
    - Trending topics matching keywords
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def check_and_notify(self) -> bool:
        """
        Check for Bluesky engagement opportunities
        
        Returns:
            True if any notifications were sent
        """
        try:
            pending_approvals = await self._get_pending_approvals()
            
            if not pending_approvals:
                logger.info("No pending Bluesky opportunities to notify about")
                return False
            
            logger.info(f"Sending notification for {len(pending_approvals)} Bluesky opportunities")
            await self._send_approval_notification(pending_approvals)
            return True
            
        except Exception as e:
            logger.error(f"Error checking Bluesky notifications: {e}", exc_info=True)
            return False
    
    async def _get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get high-potential Bluesky engagement opportunities"""
        query = """
        SELECT 
            id,
            detected_by_account,
            author_handle,
            post_text,
            matched_keywords,
            engagement_score,
            opportunity_type,
            post_context,
            already_engaged,
            detected_at,
            expires_at
        FROM bluesky_engagement_opportunities
        WHERE user_response IS NULL
          AND already_engaged = false
          AND (expires_at IS NULL OR expires_at > NOW())
          AND engagement_score >= 50
        ORDER BY engagement_score DESC
        LIMIT 10
        """
        
        try:
            results = await self.db.fetch_all(query)
            
            if not results:
                logger.info("No pending Bluesky opportunities found")
                return []
            
            logger.info(f"Found {len(results)} pending Bluesky opportunities")
            return [dict(r) for r in results]
            
        except Exception as e:
            logger.error(f"Failed to get Bluesky opportunities: {e}")
            return []
    
    async def _send_approval_notification(self, opportunities: List[Dict[str, Any]]) -> None:
        """Send individual notification for each Bluesky engagement opportunity"""
        if not opportunities:
            return
        
        logger.info(f"Sending {len(opportunities)} individual Bluesky notifications")
        
        # Send individual notification for each opportunity
        for opp in opportunities:
            try:
                await self._send_individual_opportunity(opp)
            except Exception as e:
                logger.error(f"Failed to send notification for opportunity {opp.get('id')}: {e}")
                continue
    
    async def _send_individual_opportunity(self, opp: Dict[str, Any]) -> None:
        """Send a single engagement opportunity notification with action buttons"""
        
        # Format account and author info
        account = opp['detected_by_account'].replace('_', ' ').title()
        author = opp['author_handle']
        score = int(opp['engagement_score'])
        post_text = opp['post_text']
        
        # Truncate post preview for readability
        post_preview = post_text[:200] + "..." if len(post_text) > 200 else post_text
        
        # Determine suggested action
        action_emoji = {'reply': '💬', 'quote_post': '🔁', 'like': '❤️'}
        opp_type = opp.get('opportunity_type', 'reply')
        emoji = action_emoji.get(opp_type, '💬')
        
        # Build message
        message = f"🦋 *Bluesky Engagement Opportunity*\n\n"
        message += f"*Account:* {account}\n"
        message += f"*Author:* @{author}\n"
        message += f"*Score:* {score}/100\n"
        message += f"*Confidence:* {score}% | *Priority:* {min(10, (score // 10) + 1)}/10\n\n"
        message += f"💡 *Suggested Action:*\n"
        message += f"{emoji} {opp_type.replace('_', ' ').title()} to this post\n\n"
        message += f"*Post Preview:*\n{post_preview}\n"
        
        # Add expiry
        if opp.get('expires_at'):
            expires = opp['expires_at']
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires.replace('Z', '+00:00'))
            message += f"\n⏰ Expires: {expires.strftime('%I:%M %p %m/%d')}"
        
        # Create action buttons
        button_rows = [
            [
                {"text": f"{emoji} Generate {opp_type.replace('_', ' ').title()}", "callback_data": f"bluesky:draft:{opp['id']}"},
                {"text": "👀 View Post", "callback_data": f"bluesky:view:{opp['id']}"}
            ],
            [
                {"text": "⏭️ Dismiss", "callback_data": f"bluesky:dismiss:{opp['id']}"},
                {"text": "⏰ Snooze", "callback_data": f"bluesky:snooze:{opp['id']}"}
            ],
            [
                {"text": "ℹ️ More Details", "callback_data": f"bluesky:details:{opp['id']}"}
            ]
        ]
        
        # Send notification
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='bluesky',
            notification_subtype='engagement_opportunity',
            message_text=message,
            buttons=button_rows,
            message_data={
                'opportunity_id': str(opp['id']),
                'account': opp['detected_by_account'],
                'author': author,
                'score': score,
                'opportunity_type': opp_type
            }
        )
    
    async def send_daily_summary(self) -> bool:
        """Send daily Bluesky activity summary"""
        try:
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE user_response = 'approved') as approved_count,
                COUNT(*) FILTER (WHERE user_response = 'rejected') as rejected_count,
                COUNT(*) FILTER (WHERE user_response IS NULL) as pending_count
            FROM bluesky_engagement_opportunities
            WHERE detected_at >= CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query)
            
            if not result:
                return False
            
            pending = result['pending_count']
            approved = result['approved_count']
            rejected = result['rejected_count']
            
            message = f"🦋 *Bluesky Daily Summary*\n\n"
            message += f"*Opportunities Today:* {pending + approved + rejected}\n"
            
            if pending > 0:
                message += f"*Pending Review:* {pending} ⏳\n"
            
            if approved > 0:
                message += f"*Approved:* {approved} ✅\n"
            
            if rejected > 0:
                message += f"*Rejected:* {rejected} ❌\n"
            
            if pending > 0:
                message += f"\n_You have {pending} opportunit{'ies' if pending != 1 else 'y'} awaiting review._"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='bluesky',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent Bluesky daily summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Bluesky daily summary: {e}")
            return False
