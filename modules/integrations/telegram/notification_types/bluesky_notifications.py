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
                logger.info("No pending Bluesky opportunities to notify about")
                return False
            
            # Send notification for ALL opportunities (not just high priority)
            logger.info(f"Sending notification for {len(pending_approvals)} Bluesky opportunities")
            await self._send_approval_notification(pending_approvals)
            return True
            
        except Exception as e:
            logger.error(f"Error checking Bluesky notifications: {e}", exc_info=True)
            return False

**Before:**
- Only notified if `relevance_score > 80` (column doesn't exist!)
- Your scores: 45%, 55%, 60%, 70% - all rejected!

**After:**
- Notifies for ALL opportunities with `engagement_score >= 50`
- Your scores: 55%, 60%, 70% - will all trigger notifications!

---

## 🚀 AFTER YOU PUSH

Within **15 minutes** (or restart app), you'll get:
```
🦋 Bluesky: 10 Engagement Opportunities

1. Binge Tv (70% match)
   @azalben.bsky.social
   My biggest burning question about Netflix's...

2. Binge Tv (60% match)
   @bemorelikeharper.bsky.social
   People will urge you to procreate with no...
    
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
          AND engagement_score >= 50  -- Only notify for 50%+ matches
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
        """Send notification for Bluesky engagement opportunities"""
        count = len(opportunities)
        
        if count == 0:
            return
        
        # Build message
        message = f"🦋 *Bluesky: {count} Engagement Opportunit{'ies' if count != 1 else 'y'}*\n\n"
        
        for i, opp in enumerate(opportunities[:5], 1):  # Show max 5
            account = opp['detected_by_account'].replace('_', ' ').title()
            author = opp['author_handle']
            score = int(opp['engagement_score'])
            post_preview = opp['post_text'][:80] + "..." if len(opp['post_text']) > 80 else opp['post_text']
            
            message += f"{i}. *{account}* ({score}% match)\n"
            message += f"   @{author}\n"
            message += f"   {post_preview}\n\n"
        
        if count > 5:
            message += f"_...and {count - 5} more opportunit{'ies' if count - 5 != 1 else 'y'}_\n\n"
        
        message += "Check your Bluesky dashboard to engage!"
        
        # Metadata
        metadata = {
            'opportunity_count': count,
            'notification_type': 'engagement_opportunities',
            'opportunity_ids': [str(o['id']) for o in opportunities[:5]]
        }
        
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='bluesky',
            notification_subtype='engagement_opportunities',
            message_text=message,
            message_data=metadata
        )
        
        logger.info(f"✅ Sent Bluesky notification: {count} opportunities")

