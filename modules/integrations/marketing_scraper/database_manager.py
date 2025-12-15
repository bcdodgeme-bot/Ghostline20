# modules/integrations/marketing_scraper/database_manager.py
"""
Database Manager for Marketing Scraper
Handles storage and retrieval of scraped content and analysis results
Includes competitive analysis and cross-competitor insights
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Singleton instance
_scraped_content_db: Optional['ScrapedContentDatabase'] = None


def get_scraped_content_database() -> 'ScrapedContentDatabase':
    """Get singleton ScrapedContentDatabase instance"""
    global _scraped_content_db
    if _scraped_content_db is None:
        _scraped_content_db = ScrapedContentDatabase()
    return _scraped_content_db


class ScrapedContentDatabase:
    """
    Manages database operations for scraped content and analysis results
    Provides competitive analysis and cross-competitor insights
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
            
            results = await self.db.fetch_all(query, user_id, limit)
            
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
            results = await self.db.fetch_all(query, user_id, search_term, limit)
            
            formatted_results = []
            for row in results:
                # Parse JSON fields
                competitive_insights = self._safe_json_parse(row['competitive_insights'])
                marketing_angles = self._safe_json_parse(row['marketing_angles'])
                
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
            
            top_domains = await self.db.fetch_all(domains_query, user_id)
            
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
    
    # =========================================================================
    # COMPETITIVE ANALYSIS METHODS
    # =========================================================================
    
    async def compare_competitors(
        self,
        user_id: str,
        content_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Compare multiple scraped competitors side-by-side
        
        Args:
            user_id: User ID for authorization
            content_ids: List of scraped_content IDs to compare
            
        Returns:
            Structured comparison with similarities, differences, and insights
        """
        try:
            if len(content_ids) < 2:
                return {
                    'error': 'Need at least 2 competitors to compare',
                    'comparison': None
                }
            
            # Fetch all requested content
            placeholders = ', '.join(f'${i+2}' for i in range(len(content_ids)))
            query = f"""
            SELECT id, url, domain, title, 
                   competitive_insights, marketing_angles, 
                   cta_analysis, tone_analysis, technical_details,
                   word_count, created_at
            FROM scraped_content 
            WHERE user_id = $1 
            AND id IN ({placeholders})
            AND scrape_status = 'completed'
            ORDER BY created_at DESC
            """
            
            results = await self.db.fetch_all(query, user_id, *content_ids)
            
            if len(results) < 2:
                return {
                    'error': 'Could not find enough valid competitors to compare',
                    'found': len(results),
                    'requested': len(content_ids)
                }
            
            # Parse and structure competitor data
            competitors = []
            all_value_props = []
            all_target_markets = []
            all_tone_traits = []
            all_cta_tactics = []
            
            for row in results:
                competitive = self._safe_json_parse(row['competitive_insights'])
                marketing = self._safe_json_parse(row['marketing_angles'])
                tone = self._safe_json_parse(row['tone_analysis'])
                cta = self._safe_json_parse(row['cta_analysis'])
                technical = self._safe_json_parse(row['technical_details'])
                
                competitor_data = {
                    'id': str(row['id']),
                    'domain': row['domain'],
                    'title': row['title'],
                    'url': row['url'],
                    'word_count': row['word_count'],
                    'value_proposition': competitive.get('value_proposition', ''),
                    'target_market': competitive.get('target_market', ''),
                    'key_messaging': competitive.get('key_messaging', []),
                    'competitive_advantages': competitive.get('competitive_advantages', []),
                    'content_strategy': marketing.get('content_strategy', ''),
                    'emotional_appeals': marketing.get('emotional_appeals', []),
                    'brand_voice': tone.get('brand_voice_description', ''),
                    'tone_characteristics': tone.get('tone_characteristics', []),
                    'cta_strategy': cta.get('cta_placement_strategy', ''),
                    'urgency_tactics': cta.get('urgency_tactics', []),
                    'ux_patterns': technical.get('ux_patterns', [])
                }
                competitors.append(competitor_data)
                
                # Collect for pattern analysis
                if competitor_data['value_proposition']:
                    all_value_props.append(competitor_data['value_proposition'])
                if competitor_data['target_market']:
                    all_target_markets.append(competitor_data['target_market'])
                all_tone_traits.extend(competitor_data['tone_characteristics'])
                all_cta_tactics.extend(competitor_data['urgency_tactics'])
            
            # Analyze patterns across competitors
            comparison = {
                'competitors_compared': len(competitors),
                'competitors': competitors,
                'patterns': {
                    'common_tone_traits': self._find_common_items(all_tone_traits),
                    'common_cta_tactics': self._find_common_items(all_cta_tactics),
                    'value_prop_themes': all_value_props,
                    'target_market_overlap': all_target_markets
                },
                'insights': self._generate_comparison_insights(competitors),
                'compared_at': datetime.now().isoformat()
            }
            
            return comparison
            
        except Exception as e:
            logger.error(f"Failed to compare competitors: {e}")
            return {'error': str(e), 'comparison': None}
    
    async def get_domain_insights(self, user_id: str, domain: str) -> Dict[str, Any]:
        """
        Get aggregated insights for a specific domain across all scrapes
        Useful when multiple pages from same competitor have been analyzed
        
        Args:
            user_id: User ID
            domain: Domain to analyze (e.g., 'competitor.com')
            
        Returns:
            Aggregated insights across all pages from this domain
        """
        try:
            query = """
            SELECT id, url, title, 
                   competitive_insights, marketing_angles, 
                   cta_analysis, tone_analysis, technical_details,
                   word_count, created_at
            FROM scraped_content 
            WHERE user_id = $1 
            AND domain = $2
            AND scrape_status = 'completed'
            ORDER BY created_at DESC
            """
            
            results = await self.db.fetch_all(query, user_id, domain)
            
            if not results:
                return {
                    'domain': domain,
                    'pages_analyzed': 0,
                    'message': 'No scraped content found for this domain'
                }
            
            # Aggregate insights across all pages
            all_value_props = []
            all_messaging = []
            all_advantages = []
            all_emotional_appeals = []
            all_tone_traits = []
            all_cta_tactics = []
            all_ux_patterns = []
            pages = []
            total_words = 0
            
            for row in results:
                competitive = self._safe_json_parse(row['competitive_insights'])
                marketing = self._safe_json_parse(row['marketing_angles'])
                tone = self._safe_json_parse(row['tone_analysis'])
                cta = self._safe_json_parse(row['cta_analysis'])
                technical = self._safe_json_parse(row['technical_details'])
                
                pages.append({
                    'id': str(row['id']),
                    'url': row['url'],
                    'title': row['title'],
                    'word_count': row['word_count'],
                    'scraped_at': row['created_at'].isoformat()
                })
                
                total_words += row['word_count'] or 0
                
                # Collect all insights
                if competitive.get('value_proposition'):
                    all_value_props.append(competitive['value_proposition'])
                all_messaging.extend(competitive.get('key_messaging', []))
                all_advantages.extend(competitive.get('competitive_advantages', []))
                all_emotional_appeals.extend(marketing.get('emotional_appeals', []))
                all_tone_traits.extend(tone.get('tone_characteristics', []))
                all_cta_tactics.extend(cta.get('urgency_tactics', []))
                all_ux_patterns.extend(technical.get('ux_patterns', []))
            
            return {
                'domain': domain,
                'pages_analyzed': len(results),
                'total_words_analyzed': total_words,
                'pages': pages,
                'aggregated_insights': {
                    'value_propositions': all_value_props,
                    'key_messaging_themes': self._find_common_items(all_messaging),
                    'competitive_advantages': self._find_common_items(all_advantages),
                    'emotional_appeals': self._find_common_items(all_emotional_appeals),
                    'tone_characteristics': self._find_common_items(all_tone_traits),
                    'cta_tactics': self._find_common_items(all_cta_tactics),
                    'ux_patterns': self._find_common_items(all_ux_patterns)
                },
                'analysis_summary': {
                    'primary_value_prop': all_value_props[0] if all_value_props else '',
                    'dominant_tone': self._find_common_items(all_tone_traits)[:3],
                    'main_cta_approach': self._find_common_items(all_cta_tactics)[:3]
                },
                'analyzed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get domain insights for {domain}: {e}")
            return {'domain': domain, 'error': str(e)}
    
    async def get_competitive_summary(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        Get cross-competitor analysis patterns from recent scrapes
        Identifies common patterns and unique differentiators
        
        Args:
            user_id: User ID
            limit: Number of recent scrapes to analyze
            
        Returns:
            Summary of competitive patterns and market insights
        """
        try:
            query = """
            SELECT id, domain, title, url,
                   competitive_insights, marketing_angles, 
                   cta_analysis, tone_analysis,
                   created_at
            FROM scraped_content 
            WHERE user_id = $1 
            AND scrape_status = 'completed'
            ORDER BY created_at DESC
            LIMIT $2
            """
            
            results = await self.db.fetch_all(query, user_id, limit)
            
            if not results:
                return {
                    'competitors_analyzed': 0,
                    'message': 'No scraped content found'
                }
            
            # Collect patterns across all competitors
            domains_analyzed = set()
            all_value_props = {}
            all_target_markets = {}
            all_tone_traits = []
            all_emotional_appeals = []
            all_cta_tactics = []
            all_advantages = []
            
            for row in results:
                domain = row['domain']
                domains_analyzed.add(domain)
                
                competitive = self._safe_json_parse(row['competitive_insights'])
                marketing = self._safe_json_parse(row['marketing_angles'])
                tone = self._safe_json_parse(row['tone_analysis'])
                cta = self._safe_json_parse(row['cta_analysis'])
                
                # Track by domain for uniqueness analysis
                if competitive.get('value_proposition'):
                    all_value_props[domain] = competitive['value_proposition']
                if competitive.get('target_market'):
                    all_target_markets[domain] = competitive['target_market']
                
                # Collect for pattern analysis
                all_tone_traits.extend(tone.get('tone_characteristics', []))
                all_emotional_appeals.extend(marketing.get('emotional_appeals', []))
                all_cta_tactics.extend(cta.get('urgency_tactics', []))
                all_advantages.extend(competitive.get('competitive_advantages', []))
            
            # Analyze common patterns
            common_tone = self._find_common_items(all_tone_traits)
            common_emotions = self._find_common_items(all_emotional_appeals)
            common_cta = self._find_common_items(all_cta_tactics)
            common_advantages = self._find_common_items(all_advantages)
            
            return {
                'competitors_analyzed': len(results),
                'unique_domains': len(domains_analyzed),
                'domains': list(domains_analyzed),
                'market_patterns': {
                    'common_tone_traits': common_tone[:5],
                    'common_emotional_appeals': common_emotions[:5],
                    'common_cta_tactics': common_cta[:5],
                    'common_claimed_advantages': common_advantages[:5]
                },
                'positioning_landscape': {
                    'value_propositions_by_competitor': all_value_props,
                    'target_markets_by_competitor': all_target_markets
                },
                'opportunity_gaps': self._identify_opportunity_gaps(
                    common_tone, common_emotions, common_cta
                ),
                'differentiation_opportunities': {
                    'overused_tactics': common_cta[:3] if len(common_cta) >= 3 else common_cta,
                    'saturated_tones': common_tone[:3] if len(common_tone) >= 3 else common_tone,
                    'recommendation': 'Consider approaches not heavily used by competitors'
                },
                'analyzed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get competitive summary: {e}")
            return {'error': str(e)}
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
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
                'page_structure': self._safe_json_parse(row['page_structure']),
                'analysis': {
                    'competitive_insights': self._safe_json_parse(row['competitive_insights']),
                    'marketing_angles': self._safe_json_parse(row['marketing_angles']),
                    'technical_details': self._safe_json_parse(row['technical_details']),
                    'cta_analysis': self._safe_json_parse(row['cta_analysis']),
                    'tone_analysis': self._safe_json_parse(row['tone_analysis']),
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
    
    def _safe_json_parse(self, value) -> Dict[str, Any]:
        """Safely parse JSON from database field"""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _find_common_items(self, items: List[str], min_count: int = 1) -> List[str]:
        """Find commonly occurring items in a list, sorted by frequency"""
        if not items:
            return []
        
        # Count occurrences
        counts = {}
        for item in items:
            if item:  # Skip empty strings
                item_lower = item.lower().strip()
                counts[item_lower] = counts.get(item_lower, 0) + 1
        
        # Sort by frequency and return items meeting minimum threshold
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [item for item, count in sorted_items if count >= min_count]
    
    def _generate_comparison_insights(self, competitors: List[Dict]) -> List[str]:
        """Generate actionable insights from competitor comparison"""
        insights = []
        
        if len(competitors) < 2:
            return insights
        
        # Compare word counts
        word_counts = [c['word_count'] for c in competitors if c.get('word_count')]
        if word_counts:
            avg_words = sum(word_counts) / len(word_counts)
            insights.append(f"Average content length: {int(avg_words)} words")
        
        # Check for tone diversity
        all_tones = []
        for c in competitors:
            all_tones.extend(c.get('tone_characteristics', []))
        if all_tones:
            unique_tones = len(set(all_tones))
            insights.append(f"Tone diversity: {unique_tones} unique characteristics across competitors")
        
        # Check CTA patterns
        all_ctas = []
        for c in competitors:
            all_ctas.extend(c.get('urgency_tactics', []))
        if all_ctas:
            common_ctas = self._find_common_items(all_ctas)
            if common_ctas:
                insights.append(f"Most common CTA tactic: {common_ctas[0]}")
        
        return insights
    
    def _identify_opportunity_gaps(
        self,
        common_tones: List[str],
        common_emotions: List[str],
        common_ctas: List[str]
    ) -> List[str]:
        """Identify potential opportunity gaps based on market saturation"""
        gaps = []
        
        # Suggest alternatives to overused approaches
        if common_tones:
            gaps.append(f"Most competitors use '{common_tones[0]}' tone - consider differentiation")
        
        if common_emotions:
            gaps.append(f"'{common_emotions[0]}' is the most targeted emotion - explore underserved emotions")
        
        if common_ctas:
            gaps.append(f"'{common_ctas[0]}' is overused in CTAs - test alternative approaches")
        
        if not gaps:
            gaps.append("Insufficient data to identify opportunity gaps - scrape more competitors")
        
        return gaps
