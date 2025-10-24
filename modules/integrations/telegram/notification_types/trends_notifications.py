# modules/integrations/telegram/notification_types/trends_notifications.py
"""
Trends Notification Handler
Sends proactive notifications for trending topics and opportunities
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from ....core.database import db_manager

logger = logging.getLogger(__name__)

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
        """Send notification for trending opportunities"""
        count = len(trends)
        
        if count == 1:
            # Single high-priority trend
            trend = trends[0]
            
            # Urgency emoji
            urgency_emoji = "🔴" if trend['urgency_level'] == 'high' else "🟡"
            
            message = f"{urgency_emoji} *Trending Opportunity*\n\n"
            message += f"*Keyword:* {trend['keyword']}\n"
            message += f"*Business Area:* {trend['business_area']}\n"
            message += f"*Trend Score:* {trend['trend_score_at_alert']}\n"
            message += f"*Momentum:* {trend['trend_momentum'].upper()}\n"
            message += f"*Urgency:* {trend['urgency_level'].upper()}\n\n"
            
            # Show momentum change if significant
            if trend.get('momentum_change_percent'):
                change = float(trend['momentum_change_percent'])
                if change > 0:
                    message += f"📊 Momentum increased by {change:.1f}%\n\n"
            
            # Add RSS insights if available
            rss_insights = trend.get('related_rss_insights', {})
            if rss_insights and isinstance(rss_insights, dict):
                if rss_insights.get('summary'):
                    message += f"💡 *Market Insight:*\n{rss_insights['summary'][:200]}\n\n"
            
            # Show Bluesky potential if high
            bluesky_potential = trend.get('bluesky_engagement_potential', 0)
            if bluesky_potential > 0.25:
                pct = int(bluesky_potential * 100)
                message += f"🦋 Bluesky engagement potential: {pct}%\n\n"
            
            message += f"*Opportunity Type:* {trend['opportunity_type']}\n"
            message += f"Perfect timing to create content! 🚀"
            
            if trend.get('content_angles'):
                angles = trend['content_angles']
                if isinstance(angles, list) and len(angles) > 0:
                    message += f"*Content Ideas:*\n"
                    for angle in angles[:3]:
                        message += f"• {angle}\n"
                    message += "\n"
            
            message += f"*Competition:* {trend.get('competition_level', 'Unknown')}\n"
            
            # Create action buttons
            buttons = {
                "inline_keyboard": [
                    [
                        {
                            "text": "🔍 Research More",
                            "callback_data": f"trend_research:{trend['id']}"
                        },
                        {
                            "text": "✍️ Create Content",
                            "callback_data": f"trend_content:{trend['id']}"
                        }
                    ]
                ]
            }
            
            metadata = {
                'trend_id': trend['id'],
                'keyword': trend['trend_keyword'],
                'opportunity_score': trend['opportunity_score'],
                'trend_traffic': trend['trend_traffic']
            }
            
        else:
            # Multiple trends - digest
            message = f"📈 *{count} Trending Opportunities*\n\n"
        
            for i, trend in enumerate(trends[:5], 1):
                urgency_emoji = "🔴" if trend['urgency_level'] == 'high' else "🟡"
                message += f"{i}. {urgency_emoji} *{trend['keyword']}*\n"
                message += f"   {trend['business_area']} | Score: {trend['trend_score_at_alert']}\n"
                message += f"   Momentum: {trend['trend_momentum'].upper()}\n\n"
            
            if count > 5:
                message += f"_...and {count - 5} more opportunities_\n\n"
            
            message += "Multiple trending opportunities detected! 🚀"
            
            buttons = None
            
            metadata = {
                'opportunity_count': count,
                'opportunity_ids': [str(t['id']) for t in trends[:5]],
                'notification_type': 'trending_opportunity',
                'urgency_levels': [t['urgency_level'] for t in trends[:5]]
            }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='trends',
            notification_subtype='opportunity_alert',
            message_text=message,
            buttons=buttons,  # Note: convert reply_markup to simple list format
            message_data=metadata
        )
        
        logger.info(f"✅ Sent trends notification: {count} opportunities")
    
    async def send_daily_summary(self) -> bool:
        """
        Send daily trends summary
        
        Returns:
            True if successful
        """
        try:
            # Get today's trend stats
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
            
            result = await self.db.fetch_one(query, self.user_id)
            
            if not result or result['total_trends'] == 0:
                message = f"📈 *Daily Trends Summary*\n\n"
                message += "No new trends detected today.\n"
                message += "Keep monitoring for opportunities!"
            else:
                total = result['total_trends']
                high_opp = result['high_opportunity']
                rising = result['rising_trends']
                top_score = result['top_score']
                top_trend = result['top_trend']
                
                message = f"📈 *Daily Trends Summary*\n\n"
                message += f"*Trends Detected:* {total}\n"
                
                if rising > 0:
                    message += f"*Rising:* {rising} 🚀\n"
                
                if high_opp > 0:
                    message += f"*High Opportunity:* {high_opp} 🎯\n"
                
                if top_trend and top_score:
                    message += f"\n*Top Trend:*\n"
                    message += f"{top_trend} (Score: {top_score}/100)"
            
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
            message = f"🔥 *BREAKING TREND ALERT*\n\n"
            message += f"*{keyword}* is going viral!\n\n"
            message += f"Opportunity Score: {score}/100 🎯\n"
            message += f"Status: 🚀 RAPIDLY RISING\n\n"
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
