# modules/integrations/rss_learning/database_manager.py
"""
RSS Database Manager - Handles all database operations for RSS learning system
Integrates with existing Syntax Prime V2 database architecture
"""

import asyncpg
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import json

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class RSSDatabase:
    """Manages RSS-related database operations"""
    
    def __init__(self):
        self.db = db_manager
    
    async def get_sources_to_fetch(self) -> List[Dict[str, Any]]:
        """Get RSS sources that need fetching (weekly interval)"""
        query = '''
            SELECT id, name, feed_url, category, fetch_interval, error_count
            FROM rss_sources 
            WHERE active = true 
            AND (last_fetched IS NULL OR 
                 last_fetched < NOW() - INTERVAL '1 second' * fetch_interval)
            AND error_count < 5
            ORDER BY last_fetched ASC NULLS FIRST
        '''
        
        try:
            rows = await self.db.fetch_all(query)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get sources to fetch: {e}")
            return []
    
    async def update_source_status(self, source_id: int, success: bool, 
                                 error: str = None, items_count: int = 0):
        """Update RSS source fetch status"""
        try:
            if success:
                query = '''
                    UPDATE rss_sources 
                    SET last_fetched = NOW(), 
                        error_count = 0, 
                        last_error = NULL,
                        items_fetched = COALESCE(items_fetched, 0) + $2,
                        updated_at = NOW()
                    WHERE id = $1
                '''
                await self.db.execute(query, source_id, items_count)
            else:
                query = '''
                    UPDATE rss_sources 
                    SET error_count = error_count + 1, 
                        last_error = $2,
                        updated_at = NOW()
                    WHERE id = $1
                '''
                await self.db.execute(query, source_id, error)
        except Exception as e:
            logger.error(f"Failed to update source status: {e}")
    
    async def find_existing_item(self, guid: str, link: str) -> Optional[Dict[str, Any]]:
        """Find existing RSS item by GUID or link"""
        query = '''
            SELECT id, title, updated_at
            FROM rss_feed_entries 
            WHERE guid = $1 OR link = $2
        '''
        
        try:
            row = await self.db.fetch_one(query, guid, link)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to find existing item: {e}")
            return None
    
    async def update_existing_item(self, item_id: str, item_data: Dict[str, Any]):
        """Update existing RSS item with new data"""
        query = '''
            UPDATE rss_feed_entries 
            SET title = $2,
                description = $3,
                full_content = $4,
                updated_at = NOW()
            WHERE id = $1
        '''
        
        try:
            await self.db.execute(
                query, 
                item_id,
                item_data['title'],
                item_data.get('description', ''),
                item_data.get('full_content', '')
            )
        except Exception as e:
            logger.error(f"Failed to update existing item: {e}")
    
    async def insert_feed_item(self, item_data: Dict[str, Any]) -> bool:
        """Insert new RSS feed item"""
        query = '''
            INSERT INTO rss_feed_entries (
                source_id, title, description, link, pub_date, guid,
                full_content, summary, category, keywords, tags,
                campaign_type, target_audience, processed, sentiment_score,
                marketing_insights, actionable_tips, trend_score, content_type,
                relevance_score, ai_processed, fetch_date, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                $16, $17, $18, $19, $20, $21, NOW(), NOW(), NOW()
            )
        '''
        
        try:
            # Prepare tags and other JSONB fields
            tags = item_data.get('keywords', [])[:5]  # Use keywords as tags
            actionable_tips_json = json.dumps(item_data.get('actionable_tips', []))
            keywords_json = json.dumps(item_data.get('keywords', []))
            
            await self.db.execute(
                query,
                item_data.get('source_id'),
                item_data.get('title', '')[:500],
                item_data.get('description', '')[:1000],
                item_data.get('link', ''),
                item_data.get('published_date'),
                item_data.get('guid', ''),
                item_data.get('full_content', ''),
                item_data.get('marketing_insights', '')[:500],  # Use insights as summary
                item_data.get('category', 'marketing'),
                keywords_json,
                json.dumps(tags),
                self._determine_campaign_type(item_data.get('category', '')),
                item_data.get('target_audience', 'digital marketers'),
                item_data.get('processed', True),
                item_data.get('sentiment_score', 0.0),
                item_data.get('marketing_insights', ''),
                actionable_tips_json,
                item_data.get('trend_score', 5.0),
                item_data.get('content_type', 'article'),
                item_data.get('relevance_score', 5.0),
                item_data.get('ai_processed', False)
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert feed item: {e}")
            return False
    
    def _determine_campaign_type(self, category: str) -> str:
        """Map category to campaign type"""
        campaign_map = {
            'seo': 'organic',
            'content_marketing': 'content',
            'social_media': 'social',
            'email_marketing': 'email',
            'analytics': 'performance'
        }
        return campaign_map.get(category, 'content')
    
    async def cleanup_old_content(self, days_old: int = 120) -> int:
        """Remove old RSS content to prevent database bloat"""
        query = '''
            DELETE FROM rss_feed_entries 
            WHERE pub_date < NOW() - INTERVAL '%s days'
            AND relevance_score < 3.0
            AND trend_score < 3.0
        '''
        
        try:
            result = await self.db.execute(query % days_old)
            # Extract number from result string like "DELETE 5"
            if hasattr(result, 'split'):
                return int(result.split()[-1]) if result.split() else 0
            return 0
        except Exception as e:
            logger.error(f"Failed to cleanup old content: {e}")
            return 0
    
    async def get_marketing_insights(self, category: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get marketing insights for AI brain integration"""
        if category:
            query = '''
                SELECT title, summary, marketing_insights, actionable_tips, 
                       keywords, trend_score, pub_date, link, category
                FROM rss_feed_entries
                WHERE category = $1 
                AND ai_processed = true
                AND marketing_insights IS NOT NULL
                ORDER BY trend_score DESC, pub_date DESC
                LIMIT $2
            '''
            params = [category, limit]
        else:
            query = '''
                SELECT title, summary, marketing_insights, actionable_tips,
                       keywords, trend_score, pub_date, link, category
                FROM rss_feed_entries
                WHERE ai_processed = true
                AND marketing_insights IS NOT NULL
                ORDER BY trend_score DESC, pub_date DESC
                LIMIT $1
            '''
            params = [limit]
        
        try:
            rows = await self.db.fetch_all(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get marketing insights: {e}")
            return []
    
    async def search_content_by_keywords(self, keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """Search RSS content by keywords for AI brain"""
        # Create search condition for keywords JSONB array
        keyword_conditions = []
        params = []
        
        for i, keyword in enumerate(keywords, 1):
            keyword_conditions.append(f'keywords::text ILIKE ${i}')
            params.append(f'%{keyword}%')
        
        if not keyword_conditions:
            return []
        
        query = f'''
            SELECT title, marketing_insights, actionable_tips, link, 
                   category, trend_score, pub_date
            FROM rss_feed_entries
            WHERE ({" OR ".join(keyword_conditions)})
            AND ai_processed = true
            AND marketing_insights IS NOT NULL
            ORDER BY trend_score DESC, pub_date DESC
            LIMIT ${len(params) + 1}
        '''
        
        params.append(limit)
        
        try:
            rows = await self.db.fetch_all(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search content by keywords: {e}")
            return []
    
    async def get_trending_topics(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Get trending topics from recent RSS content"""
        query = '''
            SELECT 
                jsonb_array_elements_text(keywords) as keyword,
                COUNT(*) as frequency,
                AVG(trend_score) as avg_trend_score,
                MAX(pub_date) as latest_mention
            FROM rss_feed_entries
            WHERE pub_date > NOW() - INTERVAL '%s days'
            AND ai_processed = true
            GROUP BY jsonb_array_elements_text(keywords)
            HAVING COUNT(*) > 1
            ORDER BY frequency DESC, avg_trend_score DESC
            LIMIT %s
        '''
        
        try:
            rows = await self.db.fetch_all(query % (days, limit))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get trending topics: {e}")
            return []
    
    async def get_content_for_writing_assistance(self, content_type: str, 
                                               topic: str = None) -> List[Dict[str, Any]]:
        """Get relevant content for AI writing assistance"""
        if topic:
            query = '''
                SELECT title, marketing_insights, actionable_tips, category,
                       trend_score, link
                FROM rss_feed_entries
                WHERE (title ILIKE $1 OR full_content ILIKE $1 OR keywords::text ILIKE $1)
                AND ai_processed = true
                AND marketing_insights IS NOT NULL
                ORDER BY relevance_score DESC, trend_score DESC
                LIMIT 5
            '''
            params = [f'%{topic}%']
        else:
            # Get recent high-quality content
            query = '''
                SELECT title, marketing_insights, actionable_tips, category,
                       trend_score, link
                FROM rss_feed_entries
                WHERE ai_processed = true
                AND marketing_insights IS NOT NULL
                AND pub_date > NOW() - INTERVAL '60 days'
                ORDER BY relevance_score DESC, trend_score DESC
                LIMIT 8
            '''
            params = []
        
        try:
            rows = await self.db.fetch_all(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get content for writing assistance: {e}")
            return []
    
    async def execute_function(self, function_name: str, *args):
        """Execute a PostgreSQL function"""
        if args:
            placeholders = ', '.join(f'${i+1}' for i in range(len(args)))
            query = f'SELECT {function_name}({placeholders})'
            return await self.db.fetch_one(query, *args)
        else:
            query = f'SELECT {function_name}()'
            return await self.db.fetch_one(query)
    
    async def get_rss_statistics(self) -> Dict[str, Any]:
        """Get RSS system statistics"""
        queries = {
            'total_sources': 'SELECT COUNT(*) FROM rss_sources',
            'active_sources': 'SELECT COUNT(*) FROM rss_sources WHERE active = true',
            'total_items': 'SELECT COUNT(*) FROM rss_feed_entries',
            'processed_items': 'SELECT COUNT(*) FROM rss_feed_entries WHERE ai_processed = true',
            'recent_items': 'SELECT COUNT(*) FROM rss_feed_entries WHERE pub_date > NOW() - INTERVAL \'7 days\'',
            'avg_relevance': 'SELECT ROUND(AVG(relevance_score)::numeric, 2) FROM rss_feed_entries WHERE ai_processed = true',
            'avg_trend_score': 'SELECT ROUND(AVG(trend_score)::numeric, 2) FROM rss_feed_entries WHERE ai_processed = true'
        }
        
        stats = {}
        
        try:
            for key, query in queries.items():
                result = await self.db.fetch_one(query)
                stats[key] = result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get RSS statistics: {e}")
            stats = {key: 0 for key in queries.keys()}
        
        return stats