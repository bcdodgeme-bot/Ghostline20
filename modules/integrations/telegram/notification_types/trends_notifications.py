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
        self.db_manager = TelegramDatabaseManager() 
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
    
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
        SELECT id, trend_keyword, trend_traffic, opportunity_score,
               relevance_reason, content_angles, search_volume,
               competition_level, trend_status, detected_at
        FROM google_trends_analysis
        WHERE user_id = $1
        AND opportunity_score > 70
        AND detected_at > NOW() - INTERVAL '4 hours'
        AND trend_status = 'rising'
        ORDER BY opportunity_score DESC, trend_traffic DESC
        LIMIT 5
        """
        
        results = await self.db.fetch_all(query, self.user_id)
        
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
            # Single high-value trend
            trend = trends[0]
            
            message = f"📈 *Trending Opportunity*\n\n"
            message += f"*Keyword:* {trend['trend_keyword']}\n"
            message += f"*Score:* {trend['opportunity_score']}/100 🎯\n"
            message += f"*Traffic:* {trend['trend_traffic']}\n"
            message += f"*Status:* 🚀 {trend['trend_status'].upper()}\n\n"
            
            if trend.get('relevance_reason'):
                message += f"*Why This Matters:*\n{trend['relevance_reason']}\n\n"
            
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
            
            for i, trend in enumerate(trends, 1):
                message += f"{i}. *{trend['trend_keyword']}* - Score: {trend['opportunity_score']}/100\n"
                message += f"   Traffic: {trend['trend_traffic']} | {trend['trend_status'].upper()}\n\n"
            
            message += "_Check the trends dashboard for detailed analysis._"
            
            buttons = None
            
            metadata = {
                'trend_count': count,
                'trend_ids': [t['id'] for t in trends],
                'notification_type': 'digest'
            }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            notification_type='trends',
            message=message,
            metadata=metadata,
            reply_markup=buttons
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
                COUNT(*) as total_trends,
                COUNT(*) FILTER (WHERE opportunity_score > 70) as high_opportunity,
                COUNT(*) FILTER (WHERE trend_status = 'rising') as rising_trends,
                MAX(opportunity_score) as top_score,
                (SELECT trend_keyword FROM google_trends_analysis 
                 WHERE user_id = $1 AND DATE(detected_at) = CURRENT_DATE 
                 ORDER BY opportunity_score DESC LIMIT 1) as top_trend
            FROM google_trends_analysis
            WHERE user_id = $1
            AND DATE(detected_at) = CURRENT_DATE
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
                notification_type='trends',
                message=message,
                metadata={'summary_type': 'daily'}
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
                notification_type='trends',
                message=message,
                metadata={
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
