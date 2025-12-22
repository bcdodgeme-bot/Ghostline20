# modules/integrations/rss_learning/database_manager.py
"""
RSS Database Manager - Handles all database operations for RSS learning system
Integrates with existing Syntax Prime V2 database architecture

UPDATED: Session 15 - Added knowledge base integration for AI brain access
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import json

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

# Singleton instance
_rss_database_instance: Optional['RSSDatabase'] = None


def get_rss_database() -> 'RSSDatabase':
    """Get singleton RSSDatabase instance"""
    global _rss_database_instance
    if _rss_database_instance is None:
        _rss_database_instance = RSSDatabase()
    return _rss_database_instance


class RSSDatabase:
    """Manages RSS-related database operations"""
    
    def __init__(self):
        self.db = db_manager
        self._rss_source_id: Optional[int] = None  # Cache for knowledge_sources ID
    
    # =========================================================================
    # KNOWLEDGE BASE INTEGRATION - NEW IN SESSION 15
    # =========================================================================
    
    async def _ensure_rss_knowledge_source(self) -> int:
        """Ensure RSS knowledge source exists and return its ID"""
        if self._rss_source_id is not None:
            return self._rss_source_id
        
        # Check if RSS source exists
        query = "SELECT id FROM knowledge_sources WHERE source_type = 'rss_feed'"
        result = await self.db.fetch_one(query)
        
        if result:
            self._rss_source_id = result[0]
            return self._rss_source_id
        
        # Create RSS knowledge source
        insert_query = '''
            INSERT INTO knowledge_sources (name, source_type, description, is_active)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        '''
        result = await self.db.fetch_one(
            insert_query,
            'RSS Marketing Feeds',
            'rss_feed',
            'Marketing insights and trends from curated RSS feeds including Moz, HubSpot, Neil Patel, Semrush, and others',
            True
        )
        
        if result:
            self._rss_source_id = result[0]
            logger.info(f"Created RSS knowledge source with ID: {self._rss_source_id}")
            return self._rss_source_id
        
        raise RuntimeError("Failed to create RSS knowledge source")
    
    async def _inject_to_knowledge_base(self, rss_entry_id: str, item_data: Dict[str, Any]) -> bool:
        """
        Inject RSS entry into knowledge_entries for AI brain access.
        Creates searchable knowledge entry with full-text search vector.
        """
        try:
            source_id = await self._ensure_rss_knowledge_source()
            
            # Build comprehensive content for knowledge base
            # Combine title, insights, and full content for maximum searchability
            title = item_data.get('title', 'Untitled RSS Entry')
            insights = item_data.get('marketing_insights', '')
            full_content = item_data.get('full_content', item_data.get('description', ''))
            
            # Create rich content block for knowledge base
            content_parts = []
            if title:
                content_parts.append(f"Title: {title}")
            if insights:
                content_parts.append(f"Marketing Insights: {insights}")
            if full_content:
                content_parts.append(f"Content: {full_content}")
            
            knowledge_content = "\n\n".join(content_parts)
            
            # Extract key topics from keywords
            keywords = item_data.get('keywords', [])
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except json.JSONDecodeError:
                    keywords = []
            
            # Build summary from insights or truncated content
            summary = insights if insights else (full_content[:500] + '...' if len(full_content) > 500 else full_content)
            
            # Calculate word count
            word_count = len(knowledge_content.split())
            
            # Insert into knowledge_entries with search_vector
            insert_query = '''
                INSERT INTO knowledge_entries (
                    source_id, title, content, content_type, summary,
                    key_topics, word_count, relevance_score, processed,
                    created_at, updated_at, search_vector
                ) VALUES (
                    $1, $2::text, $3::text, $4, $5::text,
                    $6, $7, $8, $9,
                    NOW(), NOW(),
                    setweight(to_tsvector('english', COALESCE($2::text, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE($5::text, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE($3::text, '')), 'C')
                )
                ON CONFLICT DO NOTHING
            '''
            
            await self.db.execute(
                insert_query,
                source_id,
                title[:255] if title else None,  # Truncate title to varchar limit
                knowledge_content,
                item_data.get('content_type', 'rss_article'),
                summary[:1000] if summary else None,  # Truncate summary
                json.dumps(keywords[:10]) if keywords else '[]',  # Limit topics
                word_count,
                item_data.get('relevance_score', 5.0),
                True  # Mark as processed
            )
            
            logger.debug(f"Injected RSS entry to knowledge base: {title[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject RSS entry to knowledge base: {e}")
            return False
    
    async def _get_rss_entry_id(self, guid: str, link: str) -> Optional[str]:
        """Get the UUID of an RSS entry by guid or link"""
        query = "SELECT id FROM rss_feed_entries WHERE guid = $1 OR link = $2 LIMIT 1"
        result = await self.db.fetch_one(query, guid, link)
        return str(result[0]) if result else None
    
    # =========================================================================
    # EXISTING RSS FEED OPERATIONS (Updated)
    # =========================================================================
    
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
            result = [dict(row) for row in rows]
            return self.make_json_serializable(result)
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
        """Insert new RSS feed item and sync to knowledge base"""
        
        # NUCLEAR SAFETY: Clamp ALL numeric values to DECIMAL(3,2) range
        if 'sentiment_score' in item_data:
            old_val = item_data['sentiment_score']
            item_data['sentiment_score'] = max(-9.99, min(9.99, float(item_data['sentiment_score'] or 0)))
            if old_val != item_data['sentiment_score']:
                logger.warning(f"CLAMPED sentiment_score from {old_val} to {item_data['sentiment_score']}")
                
        if 'trend_score' in item_data:
            old_val = item_data['trend_score']
            item_data['trend_score'] = max(-9.99, min(9.99, float(item_data['trend_score'] or 5.0)))
            if old_val != item_data['trend_score']:
                logger.warning(f"CLAMPED trend_score from {old_val} to {item_data['trend_score']}")
                
        if 'relevance_score' in item_data:
            old_val = item_data['relevance_score']
            item_data['relevance_score'] = max(-9.99, min(9.99, float(item_data['relevance_score'] or 5.0)))
            if old_val != item_data['relevance_score']:
                logger.warning(f"CLAMPED relevance_score from {old_val} to {item_data['relevance_score']}")
                
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
            
            # NEW: Inject into knowledge base for AI brain access
            rss_entry_id = await self._get_rss_entry_id(
                item_data.get('guid', ''),
                item_data.get('link', '')
            )
            
            if rss_entry_id:
                await self._inject_to_knowledge_base(rss_entry_id, item_data)
            else:
                logger.warning(f"Could not find RSS entry ID for knowledge injection: {item_data.get('title', '')[:50]}")
            
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
        # Also clean up corresponding knowledge entries
        cleanup_knowledge_query = '''
            DELETE FROM knowledge_entries 
            WHERE source_id = (SELECT id FROM knowledge_sources WHERE source_type = 'rss_feed')
            AND created_at < NOW() - make_interval(days => $1)
        '''
        
        cleanup_rss_query = '''
            DELETE FROM rss_feed_entries 
            WHERE created_at < NOW() - make_interval(days => $1)
            RETURNING id
        '''
        
        try:
            # Clean knowledge entries first
            await self.db.execute(cleanup_knowledge_query, days_old)
            
            # Then clean RSS entries
            result = await self.db.fetch_all(cleanup_rss_query, days_old)
            deleted_count = len(result) if result else 0
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old RSS items and related knowledge entries")
            
            return deleted_count
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
            result = [dict(row) for row in rows]
            return self.make_json_serializable(result)
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
            result = [dict(row) for row in rows]
            return self.make_json_serializable(result)
        except Exception as e:
            logger.error(f"Failed to search content by keywords: {e}")
            return []
    
    async def get_trending_topics(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """Get trending topics from recent RSS content"""
        # FIXED: Use parameterized query with make_interval() instead of string formatting
        query = '''
            SELECT 
                jsonb_array_elements_text(keywords) as keyword,
                COUNT(*) as frequency,
                AVG(trend_score) as avg_trend_score,
                MAX(pub_date) as latest_mention
            FROM rss_feed_entries
            WHERE pub_date > NOW() - make_interval(days => $1)
            AND ai_processed = true
            GROUP BY jsonb_array_elements_text(keywords)
            HAVING COUNT(*) > 1
            ORDER BY frequency DESC, avg_trend_score DESC
            LIMIT $2
        '''
        
        try:
            rows = await self.db.fetch_all(query, days, limit)
            result = [dict(row) for row in rows]
            return self.make_json_serializable(result)
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
            result = [dict(row) for row in rows]
            return self.make_json_serializable(result)
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
            'avg_trend_score': 'SELECT ROUND(AVG(trend_score)::numeric, 2) FROM rss_feed_entries WHERE ai_processed = true',
            'knowledge_entries': 'SELECT COUNT(*) FROM knowledge_entries WHERE source_id = (SELECT id FROM knowledge_sources WHERE source_type = \'rss_feed\')'
        }
        
        stats = {}
        
        try:
            for key, query in queries.items():
                result = await self.db.fetch_one(query)
                stats[key] = result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get RSS statistics: {e}")
            stats = {key: 0 for key in queries.keys()}
        
        return self.make_json_serializable(stats)
    
    # =========================================================================
    # BACKFILL: Sync existing RSS entries to knowledge base
    # =========================================================================
    
    async def backfill_knowledge_base(self) -> Dict[str, Any]:
        """
        One-time backfill of existing RSS entries to knowledge base.
        Call this manually after deploying the update.
        """
        query = '''
            SELECT id, title, description, full_content, marketing_insights,
                   keywords, content_type, relevance_score, guid, link
            FROM rss_feed_entries
            WHERE ai_processed = true
            ORDER BY created_at DESC
        '''
        
        try:
            rows = await self.db.fetch_all(query)
            
            success_count = 0
            error_count = 0
            
            for row in rows:
                item_data = {
                    'title': row['title'],
                    'description': row['description'],
                    'full_content': row['full_content'],
                    'marketing_insights': row['marketing_insights'],
                    'keywords': row['keywords'],
                    'content_type': row['content_type'],
                    'relevance_score': row['relevance_score']
                }
                
                result = await self._inject_to_knowledge_base(str(row['id']), item_data)
                
                if result:
                    success_count += 1
                else:
                    error_count += 1
            
            logger.info(f"Backfill complete: {success_count} entries synced, {error_count} errors")
            
            return {
                'total_processed': len(rows),
                'success': success_count,
                'errors': error_count
            }
            
        except Exception as e:
            logger.error(f"Backfill failed: {e}")
            return {'error': str(e)}

    def make_json_serializable(self, obj):
        """
        Convert ALL non-JSON-serializable objects to JSON-safe types.
        Handles: Decimal, UUID, datetime, date, time objects.
        """
        from uuid import UUID
        from datetime import datetime, date, time
        from decimal import Decimal
        
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, UUID):
            return str(obj)
        elif isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: self.make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.make_json_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self.make_json_serializable(item) for item in obj)
        else:
            return obj
