"""
Bluesky Engagement Detector
Scans timelines for conversations matching keywords
"""

import asyncio
import asyncpg
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
import json
import logging
import os

import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(stream=sys.stdout)]
)
logger = logging.getLogger(__name__)


class BlueskyEngagementDetector:
    """Detect Bluesky conversations matching user's keywords"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.bluesky_client = None
        self.telegram_manager = None
    
    async def _get_bluesky_client(self):
        """Get or create Bluesky multi-account client"""
        if not self.bluesky_client:
            from modules.integrations.bluesky.multi_account_client import get_bluesky_multi_client
            self.bluesky_client = get_bluesky_multi_client()
        return self.bluesky_client
    
    async def _get_telegram_manager(self):
        """Get or create Telegram notification manager"""
        if not self.telegram_manager:
            from modules.integrations.telegram.notification_manager import get_notification_manager
            self.telegram_manager = get_notification_manager()
        return self.telegram_manager
    
    async def get_connection(self):
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    # ========================================================================
    # KEYWORD MATCHING
    # ========================================================================
    
    async def _get_account_keywords(
        self,
        account_id: str,
        conn: asyncpg.Connection
    ) -> List[str]:
        """Get keywords for a Bluesky account"""
        
        # Get the keywords table from multi_account_client config
        from .multi_account_client import get_bluesky_multi_client
        multi_client = get_bluesky_multi_client()
        account_info = multi_client.get_account_info(account_id)
        
        table_name = account_info.get('keywords_table')
        if not table_name:
            logger.warning(f"No keywords table for account: {account_id}")
            return []
        
        try:
            query = f'''
                SELECT keyword
                FROM {table_name}
                WHERE is_active = true
                ORDER BY created_at DESC
            '''
            
            rows = await conn.fetch(query)
            keywords = [row['keyword'].lower() for row in rows]
            
            logger.info(f"✅ Loaded {len(keywords)} keywords for {account_id} from {table_name}")
            return keywords
        
        except Exception as e:
            logger.error(f"Failed to load keywords for {account_id}: {e}")
            return []
    
    def _match_keywords(
        self,
        post_text: str,
        keywords: List[str]
    ) -> List[str]:
        """
        Match keywords against post text
        
        Returns:
            List of matched keywords
        """
        post_text_lower = post_text.lower()
        matched = []
        
        for keyword in keywords:
            if keyword in post_text_lower:
                matched.append(keyword)
        
        return matched
    
    # ========================================================================
    # ENGAGEMENT SCORING
    # ========================================================================
    
    def calculate_engagement_score(
        self,
        post: Dict[str, Any],
        matched_keywords: List[str]
    ) -> float:
        """
        Calculate engagement score (0-100)
        
        Factors:
        - Number of keyword matches (40 points max)
        - Recency of post (30 points max)
        - Engagement metrics (30 points max)
        """
        
        score = 0.0
        
        # Factor 1: Keyword matches (40 points)
        keyword_score = min(40, len(matched_keywords) * 10)
        score += keyword_score
        
        # Factor 2: Recency (30 points)
        try:
            post_data = post.get('post', {})
            created_at_str = post_data.get('record', {}).get('createdAt')
            
            if created_at_str:
                # Parse ISO timestamp
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                age_hours = (datetime.now(created_at.tzinfo) - created_at).total_seconds() / 3600
                
                # More recent = higher score
                if age_hours < 1:
                    recency_score = 30
                elif age_hours < 6:
                    recency_score = 25
                elif age_hours < 12:
                    recency_score = 20
                elif age_hours < 24:
                    recency_score = 15
                else:
                    recency_score = 10
                
                score += recency_score
        except Exception as e:
            logger.warning(f"Error calculating recency: {e}")
            score += 15  # Default mid-range score
        
        # Factor 3: Engagement metrics (30 points)
        try:
            post_data = post.get('post', {})
            like_count = post_data.get('likeCount', 0)
            reply_count = post_data.get('replyCount', 0)
            repost_count = post_data.get('repostCount', 0)
            
            total_engagement = like_count + (reply_count * 2) + (repost_count * 3)
            
            # Scale engagement score
            if total_engagement >= 50:
                engagement_score = 30
            elif total_engagement >= 20:
                engagement_score = 25
            elif total_engagement >= 10:
                engagement_score = 20
            elif total_engagement >= 5:
                engagement_score = 15
            else:
                engagement_score = 10
            
            score += engagement_score
        except Exception as e:
            logger.warning(f"Error calculating engagement: {e}")
            score += 15  # Default mid-range score
        
        return round(score, 2)
    
    # ========================================================================
    # OPPORTUNITY DETECTION
    # ========================================================================
    
    async def scan_for_opportunities(
        self,
        account_id: str
    ) -> List[Dict[str, Any]]:
        """
        Scan timeline for engagement opportunities
        
        Args:
            account_id: Bluesky account to scan (bcdodge, damnitcarl, etc.)
        
        Returns:
            List of opportunity dicts
        """
        # ADD DEBUG LOGGING HERE
        logger.info(f"📊 Starting scan for {account_id}...")
        
        # Get keywords info from multi_account_client
        from .multi_account_client import get_bluesky_multi_client
        multi_client = get_bluesky_multi_client()
        account_info = multi_client.get_account_info(account_id)
        keywords_table = account_info.get('keywords_table')
        logger.info(f"   Using keywords table: {keywords_table}")
        
        conn = await self.get_connection()
        
        try:
            # Get keyword count
            try:
                keyword_count = await conn.fetchval(f'SELECT COUNT(*) FROM {keywords_table}')
                logger.info(f"   📝 {keyword_count} keywords loaded for matching")
            except Exception as e:
                logger.error(f"   ❌ Failed to load keywords: {e}")
                
            # Get Bluesky client
            client = await self._get_bluesky_client()
            
            # Authenticate account
            authenticated = await client.authenticate_account(account_id)
            if not authenticated:
                logger.error(f"Failed to authenticate {account_id}")
                return []
            
            # Get timeline
            logger.info(f"Fetching timeline for {account_id}...")
            timeline = await client.get_timeline(account_id, limit=50)
            
            if not timeline:
                logger.warning(f"No timeline posts for {account_id}")
                return []
            
            # Get keywords for this account
            keywords = await self._get_account_keywords(account_id, conn)
            
            if not keywords:
                logger.warning(f"No keywords configured for {account_id}")
                return []
            
            # Analyze each post
            opportunities = []
            
            for post in timeline:
                try:
                    # Extract post data
                    post_data = post.get('post', {})
                    record = post_data.get('record', {})
                    post_text = record.get('text', '')
                    post_uri = post_data.get('uri', '')
                    author = post_data.get('author', {})
                    author_handle = author.get('handle', 'unknown')
                    author_did = author.get('did', '')
                    created_at = record.get('createdAt', '')
                    
                    if not post_text or not post_uri:
                        continue
                    
                    # Match keywords
                    matched_keywords = self._match_keywords(post_text, keywords)
                    
                    if not matched_keywords:
                        continue
                    
                    # Calculate engagement score
                    engagement_score = self.calculate_engagement_score(
                        post,
                        matched_keywords
                    )
                    
                    # Only create opportunities for high-scoring posts
                    if engagement_score < 40:
                        continue
                    
                    # Determine opportunity type
                    opportunity_type = 'reply'  # Default
                    if engagement_score >= 70:
                        opportunity_type = 'quote_post'
                    elif engagement_score >= 50:
                        opportunity_type = 'reply'
                    else:
                        opportunity_type = 'like'
                    
                    # Build opportunity
                    opportunity = {
                        'post_uri': post_uri,
                        'author_handle': author_handle,
                        'author_did': author_did,
                        'detected_by_account': account_id,
                        'post_text': post_text,
                        'matched_keywords': matched_keywords,
                        'engagement_score': engagement_score,
                        'opportunity_type': opportunity_type,
                        'post_created_at': created_at,
                        'post_context': {
                            'like_count': post_data.get('likeCount', 0),
                            'reply_count': post_data.get('replyCount', 0),
                            'repost_count': post_data.get('repostCount', 0)
                        }
                    }
                    
                    opportunities.append(opportunity)
                
                except Exception as e:
                    logger.warning(f"Error analyzing post: {e}")
                    continue
            
            logger.info(f"Found {len(opportunities)} opportunities for {account_id}")
            
            # Store opportunities in database
            stored_count = 0
            for opp in opportunities:
                stored = await self._store_opportunity(opp, conn)
                if stored:
                    stored_count += 1
            
            logger.info(f"Stored {stored_count} new opportunities")
            
            return opportunities
        
        except Exception as e:
            logger.error(f"Scan failed for {account_id}: {e}")
            return []
        finally:
            await conn.close()
    
    async def _store_opportunity(
        self,
        opportunity: Dict[str, Any],
        conn: asyncpg.Connection
    ) -> bool:
        """Store opportunity in database"""
        try:
            # Check if already exists
            existing = await conn.fetchval('''
                SELECT id FROM bluesky_engagement_opportunities
                WHERE post_uri = $1 AND detected_by_account = $2
            ''', opportunity['post_uri'], opportunity['detected_by_account'])
            
            if existing:
                logger.debug(f"Opportunity already exists: {opportunity['post_uri']}")
                return False
            
            # Calculate expires_at (48 hours from now)
            expires_at = datetime.utcnow() + timedelta(hours=48)
            
            # Parse post_created_at
            post_created_at = None
            if opportunity.get('post_created_at'):
                try:
                    post_created_at = datetime.fromisoformat(
                        opportunity['post_created_at'].replace('Z', '+00:00')
                    )
                except Exception:
                    pass
            
            # Insert opportunity
            await conn.execute('''
                INSERT INTO bluesky_engagement_opportunities (
                    post_uri,
                    author_handle,
                    author_did,
                    detected_by_account,
                    post_text,
                    matched_keywords,
                    engagement_score,
                    opportunity_type,
                    post_context,
                    post_created_at,
                    expires_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ''',
                opportunity['post_uri'],
                opportunity['author_handle'],
                opportunity['author_did'],
                opportunity['detected_by_account'],
                opportunity['post_text'],
                json.dumps(opportunity['matched_keywords']),
                opportunity['engagement_score'],
                opportunity['opportunity_type'],
                json.dumps(opportunity['post_context']),
                post_created_at,
                expires_at
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to store opportunity: {e}")
            return False
    
    # ========================================================================
    # TELEGRAM NOTIFICATIONS
    # ========================================================================
    
    async def notify_about_opportunity(
        self,
        opportunity_id: UUID,
        user_id: str = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
    ) -> bool:
        """
        Send Telegram notification about an engagement opportunity
        
        Args:
            opportunity_id: UUID of bluesky_engagement_opportunities record
            user_id: User UUID to notify
        
        Returns:
            True if notification sent successfully
        """
        conn = await self.get_connection()
        
        try:
            # Get opportunity details
            opportunity = await conn.fetchrow('''
                SELECT 
                    id,
                    post_uri,
                    author_handle,
                    detected_by_account,
                    post_text,
                    matched_keywords,
                    engagement_score,
                    opportunity_type
                FROM bluesky_engagement_opportunities
                WHERE id = $1
            ''', opportunity_id)
            
            if not opportunity:
                logger.error(f"Opportunity {opportunity_id} not found")
                return False
            
            # Parse matched keywords
            matched_keywords = json.loads(opportunity['matched_keywords'])
            
            # Build notification message
            message = f"🔵 *Bluesky Engagement Opportunity*\n\n"
            message += f"**Account:** @{opportunity['detected_by_account']}\n"
            message += f"**Author:** @{opportunity['author_handle']}\n"
            message += f"**Score:** {int(opportunity['engagement_score'])}/100\n\n"
            message += f"**Matched Keywords:** {', '.join(matched_keywords[:5])}\n\n"
            message += f"*Post Preview:*\n{opportunity['post_text'][:200]}"
            
            if len(opportunity['post_text']) > 200:
                message += "..."
            
            # Create action buttons
            buttons = [
                [
                    {'text': '👀 View', 'callback_data': f"engagement:view:{opportunity['post_uri']}"},
                    {'text': '💬 Draft Reply', 'callback_data': f"engagement:draft_reply:{opportunity['id']}"}
                ],
                [
                    {'text': '❤️ Like', 'callback_data': f"engagement:like:{opportunity['post_uri']}"},
                    {'text': '⏭️ Skip', 'callback_data': f"engagement:skip:{opportunity['id']}"}
                ]
            ]
            
            # Send notification
            telegram_manager = await self._get_telegram_manager()
            
            result = await telegram_manager.send_notification(
                user_id=user_id,
                notification_type='engagement',
                notification_subtype='opportunity',
                message_text=message,
                buttons=buttons,
                message_data={
                    'opportunity_id': str(opportunity['id']),
                    'post_uri': opportunity['post_uri'],
                    'account': opportunity['detected_by_account'],
                    'score': float(opportunity['engagement_score'])
                }
            )
            
            logger.info(f"Sent notification for opportunity {opportunity_id}")
            return result.get('success', False)
        
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
        finally:
            await conn.close()
    
    # ========================================================================
    # BATCH SCANNING
    # ========================================================================
    
    async def scan_all_accounts(self) -> Dict[str, int]:
        """
        Scan all configured Bluesky accounts
        
        Returns:
            Dict with opportunity counts per account
        """
        accounts = ['personal', 'damn_it_carl', 'binge_tv', 'rose_angel', 'meals_feelz']
        results = {}
        
        for account_id in accounts:
            logger.info(f"\n📊 Scanning {account_id}...")
            opportunities = await self.scan_for_opportunities(account_id)
            results[account_id] = len(opportunities)
            
            # Notify about top opportunities
            # Sort by score and notify about top 3
            if opportunities:
                sorted_opps = sorted(
                    opportunities,
                    key=lambda x: x['engagement_score'],
                    reverse=True
                )
                
                # Get IDs from database for notifications
                conn = await self.get_connection()
                try:
                    for opp in sorted_opps[:3]:
                        opp_record = await conn.fetchrow('''
                            SELECT id FROM bluesky_engagement_opportunities
                            WHERE post_uri = $1 AND detected_by_account = $2
                        ''', opp['post_uri'], account_id)
                        
                        if opp_record:
                            await self.notify_about_opportunity(opp_record['id'])
                            await asyncio.sleep(2)  # Rate limit notifications
                finally:
                    await conn.close()
            
            # Rate limit between accounts
            await asyncio.sleep(5)
        
        return results


# Convenience function
async def get_engagement_detector(database_url: str = None) -> BlueskyEngagementDetector:
    """Get engagement detector instance"""
    if not database_url:
        database_url = os.getenv('DATABASE_URL')
    return BlueskyEngagementDetector(database_url)


# Test script
if __name__ == "__main__":
    async def test():
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not set")
            return
        
        detector = await get_engagement_detector(database_url)
        
        print("🧪 Testing engagement detection for bcdodge...")
        opportunities = await detector.scan_for_opportunities('bcdodge')
        
        print(f"\n✅ Found {len(opportunities)} opportunities")
        
        if opportunities:
            top = opportunities[0]
            print(f"\nTop opportunity:")
            print(f"  Author: @{top['author_handle']}")
            print(f"  Score: {top['engagement_score']}")
            print(f"  Keywords: {', '.join(top['matched_keywords'][:3])}")
    
    asyncio.run(test())
