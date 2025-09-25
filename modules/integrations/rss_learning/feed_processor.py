# modules/integrations/rss_learning/feed_processor.py
"""
RSS Feed Processor - Fetches and processes marketing RSS feeds
Handles weekly RSS collection with error handling and status tracking
"""

import asyncio
import aiohttp
import feedparser
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from .database_manager import RSSDatabase
from .content_analyzer import ContentAnalyzer

logger = logging.getLogger(__name__)

class RSSFeedProcessor:
    """Processes RSS feeds for marketing content analysis"""
    
    def __init__(self):
        self.db = RSSDatabase()
        self.analyzer = ContentAnalyzer()
        self.session: Optional[aiohttp.ClientSession] = None
        self.background_task: Optional[asyncio.Task] = None
        self.running = False
        
        # Request configuration
        self.headers = {
            'User-Agent': 'Syntax Prime V2 RSS Learning Bot 1.0 (+https://syntaxprime.ai/bot)',
            'Accept': 'application/rss+xml, application/xml, text/xml',
            'Cache-Control': 'no-cache'
        }
        
        self.timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
    async def start_background_processing(self):
        """Start weekly RSS processing in background"""
        if self.running:
            logger.warning("RSS processor already running")
            return
            
        self.running = True
        self.background_task = asyncio.create_task(self._weekly_processing_loop())
        logger.info("RSS background processing started (weekly schedule)")
        
    async def stop_background_processing(self):
        """Stop background processing"""
        self.running = False
        
        if self.background_task:
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            
        logger.info("RSS background processing stopped")
        
    async def _weekly_processing_loop(self):
        """Main weekly processing loop"""
        logger.info("Starting RSS weekly processing loop")
        
        while self.running:
            try:
                # Process all RSS feeds
                await self.process_all_feeds()
                
                # Clean up old content
                await self.cleanup_old_content()
                
                # Update content freshness scores
                await self.db.execute_function('update_rss_content_freshness')
                
                logger.info("Weekly RSS processing completed successfully")
                
                # Sleep for 1 week (604800 seconds)
                sleep_duration = 604800  # 7 days
                
                # Break sleep into smaller chunks to allow for graceful shutdown
                for _ in range(sleep_duration):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"RSS processing loop error: {e}")
                # Sleep for 1 hour on error before retrying
                for _ in range(3600):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
    
    async def process_all_feeds(self) -> Dict[str, Any]:
        """Process all active RSS sources"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=self.timeout
            )
        
        # Get active RSS sources that need fetching
        sources = await self.db.get_sources_to_fetch()
        
        if not sources:
            logger.info("No RSS sources need updating")
            return {'processed': 0, 'sources': 0}
        
        logger.info(f"Processing {len(sources)} RSS sources")
        
        results = {
            'processed': 0,
            'sources': len(sources),
            'success': 0,
            'errors': 0,
            'details': []
        }
        
        for source in sources:
            try:
                result = await self._process_single_source(source)
                results['details'].append(result)
                
                if result['success']:
                    results['success'] += 1
                    results['processed'] += result.get('items_processed', 0)
                else:
                    results['errors'] += 1
                    
                # Small delay between sources
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to process source {source['name']}: {e}")
                results['errors'] += 1
                results['details'].append({
                    'source': source['name'],
                    'success': False,
                    'error': str(e),
                    'items_processed': 0
                })
        
        logger.info(f"RSS processing complete: {results['success']}/{results['sources']} sources successful")
        return results
    
    async def _process_single_source(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single RSS source"""
        source_name = source['name']
        source_url = source['feed_url']
        source_id = source['id']
        
        logger.info(f"Processing: {source_name}")
        
        try:
            # Fetch RSS feed
            feed_data = await self._fetch_rss_feed(source_url)
            
            if not feed_data:
                await self.db.update_source_status(source_id, success=False, error="Failed to fetch feed")
                return {
                    'source': source_name,
                    'success': False,
                    'error': 'Failed to fetch RSS feed',
                    'items_processed': 0
                }
            
            # Parse feed items
            items = self._parse_feed_items(feed_data, source_name)
            
            if not items:
                await self.db.update_source_status(source_id, success=False, error="No items found in feed")
                return {
                    'source': source_name,
                    'success': False,
                    'error': 'No valid items found',
                    'items_processed': 0
                }
            
            # Process and store items
            processed_count = 0
            for item in items:
                if await self._process_feed_item(item, source_id, source['category']):
                    processed_count += 1
            
            # Update source status
            await self.db.update_source_status(source_id, success=True, items_count=processed_count)
            
            logger.info(f"Processed {processed_count}/{len(items)} items from {source_name}")
            
            return {
                'source': source_name,
                'success': True,
                'items_found': len(items),
                'items_processed': processed_count
            }
            
        except Exception as e:
            logger.error(f"Error processing {source_name}: {e}")
            await self.db.update_source_status(source_id, success=False, error=str(e))
            
            return {
                'source': source_name,
                'success': False,
                'error': str(e),
                'items_processed': 0
            }
    
    async def _fetch_rss_feed(self, feed_url: str) -> Optional[str]:
        """Fetch RSS feed content with proper encoding handling"""
        try:
            async with self.session.get(feed_url) as response:
                if response.status == 200:
                    # Read as bytes first to handle encoding properly
                    content_bytes = await response.read()
                    
                    # Try to decode with proper encoding
                    try:
                        # First try the declared encoding from response
                        encoding = response.charset or 'utf-8'
                        content = content_bytes.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        # Fallback to utf-8 with error handling
                        content = content_bytes.decode('utf-8', errors='replace')
                    
                    # Clean up problematic characters that XML parsers dislike
                    # Remove null bytes, backspace, and vertical tab characters
                    content = content.replace('\x00', '').replace('\x08', '').replace('\x0b', '')
                    
                    # Remove other control characters except newlines, tabs, and carriage returns
                    content = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
                    
                    return content
                else:
                    logger.warning(f"HTTP {response.status} for {feed_url}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {feed_url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {feed_url}: {e}")
            return None
    
    def _parse_feed_items(self, feed_content: str, source_name: str) -> List[Dict[str, Any]]:
        """Parse RSS feed and extract items"""
        try:
            feed = feedparser.parse(feed_content)
            
            if feed.bozo:
                logger.warning(f"Feed parsing warning for {source_name}: {feed.bozo_exception}")
            
            items = []
            
            for entry in feed.entries[:20]:  # Limit to 20 most recent items
                try:
                    # Extract content
                    content = ""
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value if isinstance(entry.content, list) else str(entry.content)
                    elif hasattr(entry, 'description'):
                        content = entry.description
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    
                    # Clean HTML tags
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s+', ' ', content).strip()
                    
                    # Skip if content too short
                    if len(content) < 100:
                        continue
                    
                    # Extract published date
                    published_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_date = datetime(*entry.updated_parsed[:6])
                    else:
                        # Use current time if no date available
                        published_date = datetime.now()
                    
                    # Create unique GUID
                    guid = getattr(entry, 'id', getattr(entry, 'link', ''))
                    if not guid:
                        guid = hashlib.md5(f"{entry.title}{published_date}".encode()).hexdigest()
                    
                    items.append({
                        'title': getattr(entry, 'title', 'No Title')[:500],
                        'description': content[:1000],  # Summary for description
                        'full_content': content,
                        'link': getattr(entry, 'link', ''),
                        'author': getattr(entry, 'author', ''),
                        'published_date': published_date,
                        'guid': guid
                    })
                    
                except Exception as e:
                    logger.warning(f"Error parsing entry from {source_name}: {e}")
                    continue
            
            return items
            
        except Exception as e:
            logger.error(f"Feed parsing failed for {source_name}: {e}")
            return []
    
    async def _process_feed_item(self, item: Dict[str, Any], source_id: int, category: str) -> bool:
        """Process and analyze a single feed item"""
        try:
            # Check if item already exists
            existing = await self.db.find_existing_item(item['guid'], item['link'])
            
            if existing:
                # Update existing item if needed
                await self.db.update_existing_item(existing['id'], item)
                return True
            
            # Analyze content with AI
            analysis = await self.analyzer.analyze_content(
                title=item['title'],
                content=item['full_content'],
                category=category
            )
            
            # Clamp sentiment score to valid database range (-1.00 to 1.00)
            sentiment_score = analysis.get('sentiment_score', 0.0)
            sentiment_score = max(-9.99, min(9.99, float(sentiment_score)))
            
            # ADD THESE TWO LINES HERE:
            trend_score = max(1.0, min(9.99, analysis.get('trend_score', 5.0)))
            relevance_score = max(1.0, min(9.99, analysis.get('relevance_score', 5.0)))
            
            # Prepare item for database
            db_item = {
                **item,
                'source_id': source_id,
                'category': category,
                'keywords': analysis.get('keywords', []),
                'marketing_insights': analysis.get('insights', ''),
                'actionable_tips': analysis.get('actionable_tips', []),
                'content_type': analysis.get('content_type', 'article'),
                'relevance_score': relevance_score,  # ← CHANGE THIS
                'trend_score': trend_score,
                'sentiment_score': sentiment_score,  # Now properly clamped
                'ai_processed': True,
                'processed': True
            }
            
            # DEBUG: Log the values being inserted - ADD THESE 3 LINES
            print(f"DEBUG - sentiment_score: {db_item['sentiment_score']}")
            print(f"DEBUG - trend_score: {db_item['trend_score']}")
            print(f"DEBUG - relevance_score: {db_item['relevance_score']}")
            
            # Store in database
            await self.db.insert_feed_item(db_item)
            
            logger.debug(f"Processed: {item['title'][:50]}... (Score: {db_item['relevance_score']:.1f})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process feed item: {e}")
            return False
    
    async def cleanup_old_content(self, days_old: int = 120):
        """Clean up old content to prevent database bloat"""
        try:
            deleted_count = await self.db.cleanup_old_content(days_old)
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old RSS items")
                
        except Exception as e:
            logger.error(f"Content cleanup failed: {e}")
    
    async def force_fetch_all(self) -> Dict[str, Any]:
        """Force immediate fetch of all RSS sources (for manual triggering)"""
        logger.info("Force fetching all RSS sources")
        return await self.process_all_feeds()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current processor status"""
        return {
            'running': self.running,
            'has_session': self.session is not None,
            'background_task_active': self.background_task is not None and not self.background_task.done()
        }
