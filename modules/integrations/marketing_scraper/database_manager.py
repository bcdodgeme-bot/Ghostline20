# modules/integrations/marketing_scraper/database_manager.py
"""
Database Manager for Marketing Scraper
Handles storage and retrieval of scraped content and analysis results
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

class ScrapedContentDatabase:
    """
    Manages database operations for scraped content and analysis results
    """
    
    def __init__(self):
        self.db = db_manager
    
    async def store_scraped_content(
        self, 
        user_id: str, 
        scraped_data: Dict[str, Any], 
        analysis_results: Dict[str, Any]
    ) -> str:
        """
        Store scraped content and analysis results in database
        
        Args:
            user_id: User who requested the scrape
            scraped_data: Output from MarketingScraperClient
            analysis_results: Output from ContentAnalyzer
            
        Returns:
            UUID of stored record
        """
        try:
            insert_query = """
            INSERT INTO scraped_content (
                user_id, url, domain, title, meta_description,
                raw_content, cleaned_content, page_structure,
                competitive_insights, marketing_angles, technical_details,
                cta_analysis, tone_analysis,
                analysis_personality, processing_time_ms, content_length, word_count,
                scrape_status, error_message
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
            ) RETURNING id
            """
            
            # Extract data from scraped_data
            url = scraped_data.get('url', '')
            domain = scraped_data.get('domain', '')
            title = scraped_data.get('title', '')
            meta_description = scraped_data.get('meta_description', '')
            raw_content = scraped_data.get('raw_content', '')
            cleaned_content = scraped_data.get('cleaned_content', '')
            page_structure = json.dumps(scraped_data.get('page_structure', {}))
            processing_time_ms = scraped_data.get('processing_time_ms', 0)
            content_length = scraped_data.get('content_length', 0)
            word_count = scraped_data.get('word_count', 0)
            scrape_status = scraped_data.get('scrape_status', 'completed')
            error_message = scraped_data.get('error_message')
            
            # Extract analysis data
            competitive_insights = json.dumps(analysis_results.get('competitive_insights', {}))
            marketing_angles = json.dumps(analysis_results.get('marketing_angles', {}))
            technical_details = json.dumps(analysis_results.get('technical_details', {}))
            cta_analysis = json.dumps(analysis_results.get('cta_analysis', {}))
            tone_analysis = json.dumps(analysis_results.get('tone_analysis', {}))
            
            result = await self.db.fetch_one(
                insert_query,
                user_id, url, domain, title, meta_description,
                raw_content, cleaned_content, page_structure,
                competitive_insights, marketing_angles, technical_details,
                cta_analysis, tone_analysis,
                'syntaxprime', processing_time_ms, content_length, word_count,
                scrape_status, error_message
            )
            
            content_id = str(result['id'])
            logger.info(f"Stored scraped content: {content_id} for URL: {url}")
            
            return content_id
            
        except Exception as e:
            logger.error(f"Failed to store scraped content: {e}")
            raise
    
    async def get_user_scrape_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's recent scraping activity"""
        try:
            query = """
            SELECT id, url, domain, title, scrape_status, created_at, last_accessed_at,
                   processing_time_ms, word_count
            FROM scraped_content 
            WHERE user_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2
            """
            
            results = await self.db.fetch(query, user_id, limit)
            
            return [
                {
                    'id': str(row['id']),
                    'url': row['url'],
                    'domain': row['domain'],
                    'title': row['title'],
                    'status': row['scrape_status'],
                    'created_at': row['created_at'].isoformat(),
                    'last_accessed_at': row['last_accessed_at'].isoformat() if row['last_accessed_at'] else None,
                    'processing_time_ms': row['processing_time_ms'],
                    'word_count': row['word_count']
                }
                for row in results
            ]
            
        except Exception as e:
            logger.error(f"Failed to get scrape history for user {user_id}: {e}")
            return []
    
    async def search_scraped_insights(self, user_id: str, topic: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search stored insights by topic/keyword"""
        try:
            # Search in title, cleaned_content, and analysis results
            query = """
            SELECT id, url, domain, title, created_at, word_count,
                   competitive_insights, marketing_angles, technical_details, 
                   cta_analysis, tone_analysis
            FROM scraped_content 
            WHERE user_id = $1 
            AND scrape_status = 'completed'
            AND (
                LOWER(title) LIKE LOWER($2) OR
                LOWER(cleaned_content) LIKE LOWER($2) OR
                LOWER(competitive_insights::text) LIKE LOWER($2) OR
                LOWER(marketing_angles::text) LIKE LOWER($2)
            )
            ORDER BY created_at DESC
            LIMIT $3
            """
            
            search_term = f"%{topic}%"
            results = await self.db.fetch(query, user_id, search_term, limit)
            
            formatted_results = []
            for row in results:
                # Parse JSON fields
                competitive_insights = json.loads(row['competitive_insights'] or '{}')
                marketing_angles = json.loads(row['marketing_angles'] or '{}')
                
                formatted_results.append({
                    'id': str(row['id']),
                    'url': row['url'],
                    'domain': row['domain'],
                    'title': row['title'],
                    'created_at': row['created_at'].isoformat(),
                    'word_count': row['word_count'],
                    'key_insights': {
                        'value_proposition': competitive_insights.get('value_proposition', ''),
                        'content_strategy': marketing_angles.get('content_strategy', ''),
                        'target_market': competitive_insights.get('target_market', '')
                    }
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search insights for topic '{topic}': {e}")
            return []
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user's scraping statistics"""
        try:
            stats_query = """
            SELECT 
                COUNT(*) as total_scrapes,
                COUNT(CASE WHEN scrape_status = 'completed' THEN 1 END) as successful_scrapes,
                COUNT(CASE WHEN scrape_status = 'failed' THEN 1 END) as failed_scrapes,
                COUNT(DISTINCT domain) as unique_domains,
                AVG(processing_time_ms) as avg_processing_time,
                SUM(word_count) as total_words_analyzed,
                MAX(created_at) as last_scrape_at,
                MIN(created_at) as first_scrape_at
            FROM scraped_content 
            WHERE user_id = $1
            """
            
            result = await self.db.fetch_one(stats_query, user_id)
            
            # Get top domains
            domains_query = """
            SELECT domain, COUNT(*) as scrape_count
            FROM scraped_content 
            WHERE user_id = $1 AND scrape_status = 'completed'
            GROUP BY domain
            ORDER BY scrape_count DESC
            LIMIT 5
            """
            
            top_domains = await self.db.fetch(domains_query, user_id)
            
            return {
                'total_scrapes': result['total_scrapes'] or 0,
                'successful_scrapes': result['successful_scrapes'] or 0,
                'failed_scrapes': result['failed_scrapes'] or 0,
                'success_rate': (result['successful_scrapes'] / max(result['total_scrapes'], 1)) * 100,
                'unique_domains': result['unique_domains'] or 0,
                'avg_processing_time_ms': float(result['avg_processing_time']) if result['avg_processing_time'] else 0,
                'total_words_analyzed': result['total_words_analyzed'] or 0,
                'last_scrape_at': result['last_scrape_at'].isoformat() if result['last_scrape_at'] else None,
                'first_scrape_at': result['first_scrape_at'].isoformat() if result['first_scrape_at'] else None,
                'top_domains': [
                    {'domain': row['domain'], 'count': row['scrape_count']}
                    for row in top_domains
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
            return {
                'total_scrapes': 0,
                'successful_scrapes': 0, 
                'failed_scrapes': 0,
                'success_rate': 0.0,
                'unique_domains': 0,
                'avg_processing_time_ms': 0.0,
                'total_words_analyzed': 0,
                'last_scrape_at': None,
                'first_scrape_at': None,
                'top_domains': []
            }
    
    async def check_url_exists(self, user_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Check if URL has already been scraped recently"""
        try:
            # Check for same URL scraped in last 24 hours
            query = """
            SELECT id, created_at, scrape_status
            FROM scraped_content 
            WHERE user_id = $1 AND url = $2 
            AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 1
            """
            
            result = await self.db.fetch_one(query, user_id, url)
            
            if result:
                return {
                    'exists': True,
                    'id': str(result['id']),
                    'created_at': result['created_at'].isoformat(),
                    'status': result['scrape_status']
                }
            
            return {'exists': False}
            
        except Exception as e:
            logger.error(f"Failed to check URL exists: {e}")
            return {'exists': False}
    
    async def get_scraped_content(self, content_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get specific scraped content by ID"""
        try:
            query = """
            SELECT * FROM scraped_content 
            WHERE id = $1 AND user_id = $2
            """
            
            result = await self.db.fetch_one(query, content_id, user_id)
            
            if result:
                # Update last_accessed_at
                await self.db.execute(
                    "UPDATE scraped_content SET last_accessed_at = NOW() WHERE id = $1",
                    content_id
                )
                
                return self._format_scraped_content(result)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get scraped content {content_id}: {e}")
            return None
    
    def _format_scraped_content(self, row) -> Dict[str, Any]:
        """Format database row into structured dict"""
        try:
            return {
                'id': str(row['id']),
                'user_id': str(row['user_id']),
                'url': row['url'],
                'domain': row['domain'],
                'title': row['title'],
                'meta_description': row['meta_description'],
                'raw_content': row['raw_content'],
                'cleaned_content': row['cleaned_content'],
                'page_structure': json.loads(row['page_structure'] or '{}'),
                'analysis': {
                    'competitive_insights': json.loads(row['competitive_insights'] or '{}'),
                    'marketing_angles': json.loads(row['marketing_angles'] or '{}'),
                    'technical_details': json.loads(row['technical_details'] or '{}'),
                    'cta_analysis': json.loads(row['cta_analysis'] or '{}'),
                    'tone_analysis': json.loads(row['tone_analysis'] or '{}'),
                },
                'metadata': {
                    'analysis_personality': row['analysis_personality'],
                    'processing_time_ms': row['processing_time_ms'],
                    'content_length': row['content_length'],
                    'word_count': row['word_count'],
                    'scrape_status': row['scrape_status'],
                    'error_message': row['error_message']
                },
                'timestamps': {
                    'created_at': row['created_at'].isoformat(),
                    'updated_at': row['updated_at'].isoformat(),
                    'last_accessed_at': row['last_accessed_at'].isoformat() if row['last_accessed_at'] else None
                }
            }
        except Exception as e:
            logger.error(f"Failed to format scraped content: {e}")
            return {}