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
        Check for Bluesky engagement opportunities
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get pending approvals
            pending_approvals = await self._get_pending_approvals()
            
            if not pending_approvals:
                return False
            
            # Group by priority
            high_priority = [a for a in pending_approvals if a.get('relevance_score', 0) > 80]
            
            if high_priority:
                await self._send_approval_notification(high_priority)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking Bluesky notifications: {e}")
            return False
    
    async def _get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get high-potential Bluesky engagement opportunities from trends"""
        query = """
        SELECT id, keyword, business_area, opportunity_type, 
               urgency_level, trend_momentum, trend_score_at_alert,
               bluesky_engagement_potential, created_at,
               related_rss_insights
        FROM trend_opportunities
        WHERE bluesky_engagement_potential > 0.25
        AND processed = false
        AND created_at > NOW() - INTERVAL '4 hours'
        ORDER BY bluesky_engagement_potential DESC, trend_score_at_alert DESC
        LIMIT 10
        """
        
        results = await self.db.fetch_all(query)
        
        if not results:
            return []
        
        # Filter out ones we already notified about
        filtered = []
        for opportunity in results:
            already_notified = await self._check_if_notified(opportunity['id'])
            if not already_notified:
                filtered.append(dict(opportunity))
        
        return filtered
    
    async def _check_if_notified(self, opportunity_id) -> bool:
        """Check if we already sent notification for this opportunity"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'bluesky'
        AND metadata->>'opportunity_id' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, str(opportunity_id))
        return result['count'] > 0 if result else False
    
    async def _send_approval_notification(self, opportunities: List[Dict[str, Any]]) -> None:
        """Send notification for engagement opportunities"""
        count = len(opportunities)
        
        if count == 1:
            # Single high-priority opportunity
            opp = opportunities[0]
            
            engagement_pct = int(opp['bluesky_engagement_potential'] * 100)
            
            message = f"🦋 *Bluesky Engagement Opportunity*\n\n"
            message += f"*Keyword:* {opp['keyword']}\n"
            message += f"*Business Area:* {opp['business_area']}\n"
            message += f"*Engagement Potential:* {engagement_pct}% 🎯\n"
            message += f"*Trend Score:* {opp['trend_score_at_alert']}\n"
            message += f"*Momentum:* {opp['trend_momentum'].upper()}\n\n"
            
            message += f"*Opportunity Type:* {opp['opportunity_type']}\n"
            message += f"*Urgency:* {opp['urgency_level'].upper()}\n\n"
            
            # Add RSS insights if available
            rss_insights = opp.get('related_rss_insights', {})
            if rss_insights and isinstance(rss_insights, dict):
                if rss_insights.get('summary'):
                    message += f"💡 *Insight:* {rss_insights['summary'][:150]}\n\n"
            
            message += f"Perfect timing to create content or engage on Bluesky! 🚀"
            
            # Create approval buttons
            buttons = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Approve",
                            "callback_data": f"bluesky_approve:{approval['id']}"
                        },
                        {
                            "text": "❌ Reject",
                            "callback_data": f"bluesky_reject:{approval['id']}"
                        }
                    ]
                ]
            }
            
            metadata = {
                'approval_id': approval['id'],
                'account_id': approval['account_id'],
                'relevance_score': approval['relevance_score'],
                'engagement_type': approval['engagement_type']
            }
            
        else:
            # Multiple opportunities - digest
            message = f"🦋 *Bluesky: {count} Engagement Opportunities*\n\n"
        
            for i, opp in enumerate(opportunities[:5], 1):
                engagement_pct = int(opp['bluesky_engagement_potential'] * 100)
                message += f"{i}. *{opp['keyword']}* ({opp['business_area']})\n"
                message += f"   Engagement: {engagement_pct}% | Trend: {opp['trend_score_at_alert']}\n\n"
            
            if count > 5:
                message += f"_...and {count - 5} more opportunities_\n\n"
            
            message += "High potential for Bluesky engagement right now! 🚀"
            
            buttons = None
            
            metadata = {
                 'opportunity_count': count,
                 'opportunity_ids': [str(o['id']) for o in opportunities[:5]],
                 'notification_type': 'engagement_opportunity'
            }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='bluesky',
            notification_subtype='approval_request',
            message_text=message,
            buttons=buttons,  # Note: convert the reply_markup format to simple list
            message_data=metadata
        )
        
        logger.info(f"✅ Sent Bluesky notification: {count} opportunities")
    
    async def send_daily_summary(self) -> bool:
        """
        Send daily Bluesky activity summary
        
        Returns:
            True if successful
        """
        try:
            # Get today's stats
            query = """
            SELECT 
                COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
                COUNT(*) FILTER (WHERE status = 'rejected') as rejected_count,
                AVG(relevance_score) FILTER (WHERE status = 'approved') as avg_approved_score
            FROM bluesky_approval_queue
            WHERE user_id = $1
            AND DATE(created_at) = CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result:
                return False
            
            pending = result['pending_count']
            approved = result['approved_count']
            rejected = result['rejected_count']
            avg_score = result['avg_approved_score']
            
            message = f"🦋 *Bluesky Daily Summary*\n\n"
            message += f"*Opportunities Today:* {pending + approved + rejected}\n"
            
            if pending > 0:
                message += f"*Pending Review:* {pending} ⏳\n"
            
            if approved > 0:
                message += f"*Approved:* {approved} ✅\n"
                if avg_score:
                    message += f"*Avg Score:* {int(avg_score)}/100\n"
            
            if rejected > 0:
                message += f"*Rejected:* {rejected} ❌\n"
            
            if pending > 0:
                message += f"\n_You have {pending} opportunity{'ies' if pending != 1 else 'y'} awaiting review._"
            
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
    
    async def notify_engagement_success(self, approval_id: int, engagement_type: str) -> bool:
        """
        Send notification when engagement is successfully posted
        
        Args:
            approval_id: Approval ID that was executed
            engagement_type: Type of engagement (like, reply, repost)
        
        Returns:
            True if successful
        """
        try:
            message = f"✅ *Bluesky Engagement Posted*\n\n"
            message += f"Your {engagement_type} was successfully posted!\n"
            message += f"Engagement ID: {approval_id}"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='bluesky',
                notification_subtype='engagement_success',
                message_text=message,
                message_data={
                    'approval_id': approval_id,
                    'engagement_type': engagement_type,
                    'notification_type': 'success'
                }
            )
            
            logger.info(f"✅ Sent Bluesky success notification for approval {approval_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Bluesky success notification: {e}")
            return False
