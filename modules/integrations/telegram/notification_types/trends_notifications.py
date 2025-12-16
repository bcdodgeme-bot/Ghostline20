# modules/integrations/telegram/notification_types/trends_notifications.py
"""
Trends Notification Handler
Sends proactive notifications for trending topics and opportunities

FIXED: 2025-12-15 - Fixed empty insights {} display, added html.escape for user content
FIXED: 2025-12-16 - Converted HTML to Markdown for Telegram compatibility
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from modules.core.database import db_manager

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters in user content"""
    if not text:
        return ""
    # Escape characters that have special meaning in Telegram Markdown
    for char in ['*', '_', '`', '[']:
        text = text.replace(char, '\\' + char)
    return text


class TrendsNotificationHandler:
    """
    Handles Google Trends notifications
    
    Event-driven notifications for:
    - Trending topics matching user interests
    - Breaking trends with high opportunity scores
    - Daily trend digest
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
    
    async def check_and_notify(self) -> bool:
        """
        Check for new trending opportunities
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get high-opportunity trends from last 4 hours
            trending_opportunities = await self._get_trending_opportunities()
            
            if not trending_opportunities:
                return False
            
            # Send notification for high-value trends
            await self._send_trend_notification(trending_opportunities)
            return True
            
        except Exception as e:
            logger.error(f"Error checking trends notifications: {e}")
            return False
    
    async def _get_trending_opportunities(self) -> List[Dict[str, Any]]:
        """Get high-opportunity trending topics"""
        query = """
        SELECT id, keyword, business_area, opportunity_type,
               urgency_level, trend_momentum, trend_score_at_alert,
               momentum_change_percent, created_at, processed,
               related_rss_insights, bluesky_engagement_potential
        FROM trend_opportunities
        WHERE urgency_level IN ('high', 'medium', 'low')
        AND processed = false
        AND created_at > NOW() - INTERVAL '4 hours'
        ORDER BY 
            CASE urgency_level 
                WHEN 'high' THEN 1 
                WHEN 'medium' THEN 2 
                ELSE 3 
            END,
            trend_score_at_alert DESC
        LIMIT 10
        """
        
        results = await self.db.fetch_all(query)
        
        if not results:
            return []
        
        # Filter out ones we already notified about
        filtered = []
        for trend in results:
            already_notified = await self._check_if_notified(trend['id'])
            if not already_notified:
                filtered.append(dict(trend))
        
        return filtered
    
    async def _check_if_notified(self, trend_id: int) -> bool:
        """Check if we already sent notification for this trend"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'trends'
        AND metadata->>'trend_id' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, str(trend_id))
        return result['count'] > 0 if result else False
    
    async def _send_trend_notification(self, trends: List[Dict[str, Any]]) -> None:
        """Send individual notification for each trending opportunity"""
        if not trends:
            return
        
        logger.info(f"Sending {len(trends)} individual trend notifications")
        
        # Send individual notification for each opportunity
        for trend in trends:
            try:
                await self._send_individual_trend(trend)
            except Exception as e:
                logger.error(f"Failed to send notification for trend {trend.get('keyword')}: {e}")
                continue

    async def _send_individual_trend(self, trend: Dict[str, Any]) -> None:
        """Send a single trend opportunity notification with action buttons"""
        
        # Format trend info - escape user content for Markdown
        keyword = escape_markdown(str(trend.get('keyword') or 'Topic'))
        business_area = escape_markdown(str(trend.get('business_area') or 'general'))
        score = int(trend.get('trend_score_at_alert') or 0)
        momentum = str(trend.get('trend_momentum') or 'STABLE').upper()
        urgency = str(trend.get('urgency_level') or 'low')
        
        # Urgency emoji
        urgency_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(urgency, "⚪")
        
        # Momentum emoji
        momentum_emoji = {
            "BREAKOUT": "🚀",
            "RISING": "📈",
            "STABLE_HIGH": "⭐",
            "STABLE": "➡️",
            "DECLINING": "📉"
        }.get(momentum, "📊")
        
        # Build message using Markdown (not HTML)
        message = f"{momentum_emoji} *Trending: {keyword}*\n\n"
        message += f"*Business:* {business_area}\n"
        message += f"*Score:* {score}/100 | {urgency_emoji} {urgency.upper()}\n"
        message += f"*Momentum:* {momentum}\n"
        
        if trend.get('momentum_change_percent') is not None:
            change = trend['momentum_change_percent']
            message += f"*Change:* {change:+.1f}%\n"
        
        # Only show insights if it's a non-empty string with actual content
        insights = trend.get('related_rss_insights')
        if insights and isinstance(insights, str) and insights.strip() and insights.strip() != '{}':
            escaped_insights = escape_markdown(insights[:100])
            message += f"\n💡 *Insights:* {escaped_insights}...\n"
        
        # Only show Bluesky potential if it's meaningful
        bluesky_potential = trend.get('bluesky_engagement_potential')
        if bluesky_potential and isinstance(bluesky_potential, str) and bluesky_potential.strip():
            escaped_potential = escape_markdown(bluesky_potential)
            message += f"🦋 *Bluesky Potential:* {escaped_potential}\n"
        
        # Action buttons - use list format
        buttons = [
            [
                {"text": "💬 Draft Post", "callback_data": f"trend:draft:{trend['id']}"},
                {"text": "🔍 Research", "callback_data": f"trend:research:{trend['id']}"}
            ],
            [
                {"text": "⏭️ Skip", "callback_data": f"trend:skip:{trend['id']}"},
                {"text": "📊 Details", "callback_data": f"trend:details:{trend['id']}"}
            ]
        ]
        
        # Send notification
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='trends',
            notification_subtype='opportunity_alert',
            message_text=message,
            buttons=buttons,
            message_data={
                'trend_id': str(trend['id']),
                'keyword': keyword,
                'business_area': business_area,
                'score': score,
                'urgency': urgency,
                'momentum': momentum
            }
        )
        
        logger.info(f"✅ Sent individual trend notification: {keyword} (Score: {score})")
        
    async def send_daily_summary(self) -> bool:
        """
        Send daily trends summary
        
        Returns:
            True if successful
        """
        try:
            # Get today's trend stats
            # Note: This query doesn't filter by user since trend_opportunities
            # is a global table (not user-specific)
            query = """
            SELECT 
                COUNT(*) as total_opportunities,
                COUNT(*) FILTER (WHERE urgency_level = 'high') as high_urgency,
                COUNT(*) FILTER (WHERE trend_momentum = 'rising') as rising_trends,
                MAX(trend_score_at_alert) as top_score,
                (SELECT keyword FROM trend_opportunities 
                 WHERE DATE(created_at) = CURRENT_DATE 
                 ORDER BY trend_score_at_alert DESC LIMIT 1) as top_keyword
            FROM trend_opportunities
            WHERE DATE(created_at) = CURRENT_DATE
            """
            
            result = await self.db.fetch_one(query)
            
            if not result or result['total_opportunities'] == 0:
                message = "📈 *Daily Trends Summary*\n\n"
                message += "No new trends detected today.\n"
                message += "Keep monitoring for opportunities!"
            else:
                total = result['total_opportunities']
                high_urgency = result['high_urgency'] or 0
                rising = result['rising_trends'] or 0
                top_score = result['top_score'] or 0
                top_keyword = escape_markdown(str(result['top_keyword'] or 'N/A'))
                
                message = "📈 *Daily Trends Summary*\n\n"
                message += f"*Trends Detected:* {total}\n"
                
                if rising > 0:
                    message += f"*Rising:* {rising} 🚀\n"
                
                if high_urgency > 0:
                    message += f"*High Urgency:* {high_urgency} 🎯\n"
                
                if top_keyword and top_score:
                    message += f"\n*Top Trend:*\n"
                    message += f"{top_keyword} (Score: {top_score}/100)"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='trends',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent trends daily summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send trends daily summary: {e}")
            return False
    
    async def notify_breaking_trend(self, trend_id: int, keyword: str, score: int) -> bool:
        """
        Send immediate notification for breaking/viral trend
        
        Args:
            trend_id: Trend database ID
            keyword: Trending keyword
            score: Opportunity score
        
        Returns:
            True if successful
        """
        try:
            escaped_keyword = escape_markdown(str(keyword))
            
            message = "🔥 *BREAKING TREND ALERT*\n\n"
            message += f"*{escaped_keyword}* is going viral!\n\n"
            message += f"Opportunity Score: {score}/100 🎯\n"
            message += "Status: 🚀 RAPIDLY RISING\n\n"
            message += "Act fast to capitalize on this opportunity!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='trends',
                notification_subtype='breaking_trend',
                message_text=message,
                message_data={
                    'trend_id': trend_id,
                    'keyword': keyword,
                    'score': score,
                    'notification_type': 'breaking'
                }
            )
            
            logger.info(f"✅ Sent breaking trend notification: {keyword}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send breaking trend notification: {e}")
            return False
