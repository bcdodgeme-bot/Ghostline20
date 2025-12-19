# modules/integrations/telegram/notification_types/trends_notifications.py
"""
Trends Notification Handler
Sends PROACTIVE notifications for trending topics with AI-generated content

UPDATED: 2025-12-19 - Now uses unified_engine for content generation
Instead of just notifying "trend detected", we now:
1. Detect trending opportunity
2. Fetch RSS context for relevant industry insights
3. Generate AI blog outline WITH RSS context
4. Generate AI Bluesky post
5. Send rich notification with drafts + one-tap actions

FIXED: 2025-12-15 - Fixed empty insights {} display, added html.escape for user content
FIXED: 2025-12-16 - Converted HTML to Markdown for Telegram compatibility
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

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
    Handles Google Trends notifications with AI-powered content generation
    
    Flow:
    1. Detect trending opportunities (every 4 hours)
    2. For each, generate blog outline + Bluesky post via unified_engine
    3. Send rich notification with drafts + action buttons
    4. User taps once → content created/posted
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
        Check for new trending opportunities and send proactive notifications
        
        Now uses unified_engine to generate AI content before notification.
        
        Returns:
            True if any notifications were sent
        """
        try:
            # Get high-opportunity trends from last 4 hours
            trending_opportunities = await self._get_trending_opportunities()
            
            if not trending_opportunities:
                logger.debug("No trending opportunities to process")
                return False
            
            logger.info(f"📊 Processing {len(trending_opportunities)} trend opportunities for proactive content")
            
            # Process each trend through unified engine
            processed_count = 0
            for trend in trending_opportunities:
                try:
                    queue_id = await self._process_trend_proactively(trend)
                    if queue_id:
                        processed_count += 1
                        # Mark as processed in database
                        await self._mark_trend_processed(trend['id'])
                        logger.info(f"✅ Processed trend: {trend.get('keyword', 'Unknown')}")
                except Exception as e:
                    logger.error(f"Failed to process trend {trend.get('id')}: {e}")
                    continue
            
            logger.info(f"📊 Processed {processed_count}/{len(trending_opportunities)} trends")
            return processed_count > 0
            
        except Exception as e:
            logger.error(f"Error checking trends notifications: {e}")
            return False
    
    async def _get_trending_opportunities(self) -> List[Dict[str, Any]]:
        """Get high-opportunity trending topics"""
        query = """
        SELECT id, keyword, business_area, opportunity_type,
               urgency_level, trend_momentum, trend_score_at_alert,
               momentum_change_percent, created_at, processed,
               related_rss_insights, bluesky_engagement_potential,
               content_angle, target_audience, suggested_action
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
    
    async def _check_if_notified(self, trend_id) -> bool:
        """Check if we already sent notification for this trend"""
        # Check telegram_notifications table
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'trends'
        AND metadata->>'trend_id' = $2
        """
        
        result = await self.db.fetch_one(query, self.user_id, str(trend_id))
        if result and result['count'] > 0:
            return True
        
        # Also check unified_proactive_queue (may have been processed by engine)
        query2 = """
        SELECT COUNT(*) as count
        FROM unified_proactive_queue
        WHERE source_type = 'trend'
        AND source_id = $1
        """
        
        result2 = await self.db.fetch_one(query2, str(trend_id))
        return result2['count'] > 0 if result2 else False
    
    async def _process_trend_proactively(self, trend: Dict[str, Any]) -> Optional[str]:
        """
        Process trend through unified engine for AI content generation
        
        Args:
            trend: Trend data from database
            
        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            # Transform database row to format expected by unified_engine
            trend_data = {
                'id': trend['id'],
                'keyword': trend.get('keyword', ''),
                'business_area': trend.get('business_area', ''),
                'opportunity_type': trend.get('opportunity_type', ''),
                'urgency_level': trend.get('urgency_level', 'medium'),
                'trend_momentum': trend.get('trend_momentum', 'STABLE'),
                'trend_score_at_alert': trend.get('trend_score_at_alert', 0),
                'momentum_change_percent': trend.get('momentum_change_percent'),
                'related_rss_insights': trend.get('related_rss_insights'),
                'bluesky_engagement_potential': trend.get('bluesky_engagement_potential'),
                'content_angle': trend.get('content_angle'),
                'target_audience': trend.get('target_audience'),
                'suggested_action': trend.get('suggested_action'),
            }
            
            # Process through unified engine - this handles:
            # 1. Fetching RSS context
            # 2. AI blog outline generation with RSS context
            # 3. AI Bluesky post generation
            # 4. Storage in unified_proactive_queue
            # 5. Sending Telegram notification with action buttons
            queue_id = await self.unified_engine.process_trend(trend_data)
            
            return queue_id
            
        except Exception as e:
            logger.error(f"Failed to process trend proactively: {e}")
            return None
    
    async def _mark_trend_processed(self, trend_id) -> None:
        """Mark trend opportunity as processed"""
        try:
            query = """
            UPDATE trend_opportunities
            SET processed = true
            WHERE id = $1
            """
            await self.db.execute(query, trend_id)
            logger.debug(f"Marked trend {trend_id} as processed")
        except Exception as e:
            logger.error(f"Failed to mark trend as processed: {e}")
        
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
                COUNT(*) FILTER (WHERE trend_momentum = 'RISING' OR trend_momentum = 'BREAKOUT') as rising_trends,
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
        
        This bypasses the normal check_and_notify flow for urgent trends.
        Still uses unified_engine for content generation.
        
        Args:
            trend_id: Trend database ID
            keyword: Trending keyword
            score: Opportunity score
        
        Returns:
            True if successful
        """
        try:
            logger.info(f"🔥 Breaking trend detected: {keyword} (Score: {score})")
            
            # Fetch full trend data
            query = """
            SELECT id, keyword, business_area, opportunity_type,
                   urgency_level, trend_momentum, trend_score_at_alert,
                   momentum_change_percent, related_rss_insights,
                   bluesky_engagement_potential
            FROM trend_opportunities
            WHERE id = $1
            """
            
            result = await self.db.fetch_one(query, trend_id)
            
            if result:
                # Process through unified engine for full AI treatment
                queue_id = await self._process_trend_proactively(dict(result))
                
                if queue_id:
                    await self._mark_trend_processed(trend_id)
                    logger.info(f"✅ Breaking trend processed: {keyword}")
                    return True
            
            # Fallback: send simple notification if engine fails
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
