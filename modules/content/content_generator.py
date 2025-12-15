# modules/content/content_generator.py
"""
Content Generator Module
Generates Bluesky posts and blog content from trend opportunities

Created: 2025-XX-XX
Updated: 2025-01-XX - Added singleton pattern, fixed db_manager usage, fixed SQL column names
"""

import asyncio
import sys
import os
import json
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta

# Add parent path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from modules.ai.openrouter_client import get_openrouter_client
from modules.core.database import get_db_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(stream=sys.stdout)]
)
logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS
#===============================================================================

USER_ID = UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")

#===============================================================================
# SINGLETON INSTANCE
#===============================================================================

_generator_instance: Optional['ContentGenerator'] = None


def get_content_generator(db_manager=None) -> 'ContentGenerator':
    """
    Get or create the singleton ContentGenerator instance.
    
    Args:
        db_manager: Database manager (optional, will use singleton if not provided)
        
    Returns:
        ContentGenerator singleton instance
    """
    global _generator_instance
    
    if _generator_instance is None:
        _generator_instance = ContentGenerator(db_manager=db_manager)
    
    return _generator_instance


#===============================================================================
# CONTENT GENERATOR
#===============================================================================

class ContentGenerator:
    """Generate content drafts from trend opportunities"""
    
    def __init__(self, db_manager=None):
        """
        Initialize ContentGenerator.
        
        Args:
            db_manager: Database manager instance (optional, will use singleton)
        """
        self.db = db_manager
        self.openrouter_client = None
        logger.info("📝 Content Generator initialized")
    
    async def _get_db(self):
        """Get database manager, initializing if needed"""
        if self.db is None:
            self.db = await get_db_manager()
        return self.db
    
    async def _get_client(self):
        """Get or create OpenRouter client"""
        if not self.openrouter_client:
            self.openrouter_client = await get_openrouter_client()
        return self.openrouter_client
    
    # ========================================================================
    # BLUESKY POST GENERATION
    # ========================================================================
    
    async def generate_bluesky_post(
        self,
        opportunity_id: UUID,
        account_id: str
    ) -> Dict[str, Any]:
        """
        Generate a Bluesky post from a trend opportunity
        
        Args:
            opportunity_id: UUID of trend_opportunity record
            account_id: Bluesky account to generate for (bcdodge, damnitcarl, etc.)
        
        Returns:
            {
                'success': bool,
                'queue_id': UUID (if successful),
                'preview': str (generated post text),
                'error': str (if failed)
            }
        """
        db = await self._get_db()
        
        try:
            # Get opportunity details - FIXED column names to match actual schema
            opportunity = await db.fetch_one('''
                SELECT 
                    id,
                    keyword,
                    business_area,
                    opportunity_type,
                    urgency_level,
                    trend_score_at_alert as trend_score,
                    trend_momentum,
                    opportunity_score as business_relevance,
                    content_angle as reasoning,
                    suggested_action,
                    optimal_content_window_start as content_window_start,
                    optimal_content_window_end as content_window_end
                FROM trend_opportunities
                WHERE id = $1
            ''', opportunity_id)
            
            if not opportunity:
                return {
                    'success': False,
                    'error': f'Opportunity {opportunity_id} not found'
                }
            
            # Convert to dict for easier access
            opp_dict = dict(opportunity)
            
            # Get account personality
            personality = self._get_account_personality(account_id)
            
            # Get context: RSS correlations
            rss_context = await self._get_rss_context(
                opp_dict['keyword'],
                opp_dict['business_area'],
                db
            )
            
            # Get past successful posts for this account
            past_posts = await self._get_successful_posts(account_id, db)
            
            # Build AI prompt
            prompt = self._build_bluesky_post_prompt(
                opportunity=opp_dict,
                personality=personality,
                rss_context=rss_context,
                past_posts=past_posts
            )
            
            # Generate post with OpenRouter
            client = await self._get_client()
            response = await client.chat_completion(
                messages=[
                    {'role': 'system', 'content': 'You are an expert social media content creator.'},
                    {'role': 'user', 'content': prompt}
                ],
                model='anthropic/claude-sonnet-4-5-20250929',
                max_tokens=500,
                temperature=0.8
            )
            
            generated_text = response['choices'][0]['message']['content'].strip()
            
            # Parse response (extract just the post text, remove any meta-commentary)
            post_text = self._extract_post_text(generated_text)
            
            # Calculate recommendation score
            rec_score = self._calculate_recommendation_score(
                opp_dict.get('trend_score') or 0,
                opp_dict.get('business_relevance') or 0.5,
                opp_dict.get('urgency_level') or 'medium'
            )
            
            # Store in content_recommendation_queue
            queue_id = await db.fetch_val('''
                INSERT INTO content_recommendation_queue (
                    trend_opportunity_id,
                    content_type,
                    business_area,
                    generated_content,
                    recommendation_score,
                    expires_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            ''',
                opportunity_id,
                'bluesky_post',
                opp_dict['business_area'],
                json.dumps({
                    'text': post_text,
                    'account_id': account_id,
                    'keyword': opp_dict['keyword'],
                    'trend_score': opp_dict.get('trend_score'),
                    'reasoning': opp_dict.get('reasoning')
                }),
                rec_score,
                opp_dict.get('content_window_end')
            )
            
            logger.info(f"Generated Bluesky post for {account_id}: {post_text[:50]}...")
            
            return {
                'success': True,
                'queue_id': queue_id,
                'preview': post_text,
                'account_id': account_id,
                'recommendation_score': float(rec_score)
            }
            
        except Exception as e:
            logger.error(f"Failed to generate Bluesky post: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_account_personality(self, account_id: str) -> Dict[str, Any]:
        """Get personality traits for a Bluesky account"""
        personalities = {
            'bcdodge': {
                'name': 'BC Dodge',
                'tone': 'Personal, thoughtful, slightly sarcastic',
                'style': 'Casual but informative',
                'topics': 'Marketing, business strategy, personal growth',
                'pg13': True
            },
            'damnitcarl': {
                'name': 'Damnit Carl',
                'tone': 'Warm, playful, compassionate',
                'style': 'Emotional support and cat humor',
                'topics': 'Emotional support animals, cat care, mental health',
                'pg13': True
            },
            'tvsignals': {
                'name': 'TV Signals',
                'tone': 'Enthusiastic, analytical, pop culture savvy',
                'style': 'Engaging TV/streaming commentary',
                'topics': 'TV shows, streaming content, entertainment',
                'pg13': True
            },
            'roseandangel': {
                'name': 'Rose & Angel',
                'tone': 'Professional, empathetic, expert',
                'style': 'Consulting expertise with warmth',
                'topics': 'Nonprofit consulting, small business marketing',
                'pg13': False,
                'sensitive': True
            },
            'mealsnfeelz': {
                'name': 'Meals n Feelz',
                'tone': 'Compassionate, community-focused, respectful',
                'style': 'Faith-based food security advocacy',
                'topics': 'Food pantries, Islamic giving, community support',
                'pg13': False,
                'sensitive': True,
                'religious': True
            },
            'amcf': {
                'name': 'AMCF',
                'tone': 'Professional, inspiring, community-focused',
                'style': 'Nonprofit leadership and fundraising',
                'topics': 'Muslim nonprofits, community building, philanthropy',
                'pg13': False,
                'sensitive': True,
                'religious': True
            }
        }
        
        return personalities.get(account_id, personalities['bcdodge'])
    
    async def _get_rss_context(
        self,
        keyword: str,
        business_area: str,
        db
    ) -> List[Dict[str, Any]]:
        """Get related RSS feed insights"""
        try:
            correlations = await db.fetch_all('''
                SELECT 
                    insight_text,
                    actionable_idea,
                    correlation_type
                FROM content_correlation_insights
                WHERE trend_keyword = $1
                AND business_area = $2
                AND created_at >= NOW() - INTERVAL '7 days'
                ORDER BY urgency_score DESC
                LIMIT 3
            ''', keyword, business_area)
            
            return [dict(r) for r in correlations] if correlations else []
        except Exception as e:
            logger.warning(f"Could not fetch RSS context: {e}")
            return []
    
    async def _get_successful_posts(
        self,
        account_id: str,
        db
    ) -> List[Dict[str, Any]]:
        """Get past successful posts for learning"""
        try:
            posts = await db.fetch_all('''
                SELECT 
                    post_text,
                    engagement_score,
                    likes_count,
                    replies_count,
                    reposts_count
                FROM bluesky_post_analytics
                WHERE account_id = $1
                AND engagement_score > 10
                ORDER BY engagement_score DESC
                LIMIT 5
            ''', account_id)
            
            return [dict(p) for p in posts] if posts else []
        except Exception as e:
            logger.warning(f"Could not fetch past posts: {e}")
            return []
    
    def _build_bluesky_post_prompt(
        self,
        opportunity: Dict,
        personality: Dict,
        rss_context: List[Dict],
        past_posts: List[Dict]
    ) -> str:
        """Build AI prompt for Bluesky post generation"""
        
        prompt = f"""Generate a Bluesky post about the trending topic: "{opportunity['keyword']}"

**Account Personality:**
- Name: {personality['name']}
- Tone: {personality['tone']}
- Style: {personality['style']}
- Topics: {personality['topics']}

**Trend Context:**
- Trend Score: {opportunity.get('trend_score', 'N/A')}/100
- Momentum: {opportunity.get('trend_momentum', 'unknown')}
- Urgency: {opportunity.get('urgency_level', 'medium')}
- Content Angle: {opportunity.get('reasoning', 'N/A')}

**Constraints:**
- Maximum 300 characters
- Must be engaging and authentic to the account's voice
- Include relevant hashtags if appropriate (max 2)
- PG-13 appropriate: {personality.get('pg13', True)}
"""
        
        if rss_context:
            prompt += f"\n**Related Insights:**\n"
            for insight in rss_context:
                prompt += f"- {insight['insight_text']}\n"
        
        if past_posts:
            prompt += f"\n**Style Reference (successful past posts):**\n"
            for i, post in enumerate(past_posts[:2], 1):
                prompt += f"{i}. \"{post['post_text'][:100]}...\" (engagement: {post['engagement_score']})\n"
        
        prompt += """\n**Output Format:**
Return ONLY the post text, nothing else. No quotation marks, no explanations, no meta-commentary.
The post should be ready to publish as-is."""
        
        return prompt
    
    def _extract_post_text(self, generated_text: str) -> str:
        """Extract just the post text from AI response"""
        # Remove common AI wrapper phrases
        text = generated_text.strip()
        
        # Remove quotation marks if the entire text is wrapped
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if text.startswith("'") and text.endswith("'"):
            text = text[1:-1]
        
        # Remove meta-commentary lines
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            # Skip lines that look like meta-commentary
            if line.startswith('Here') or line.startswith('This post') or line.startswith('Note:'):
                continue
            if clean_lines or line:  # Skip leading empty lines
                clean_lines.append(line)
        
        return ' '.join(clean_lines).strip()[:300]  # Enforce 300 char limit
    
    def _calculate_recommendation_score(
        self,
        trend_score: float,
        business_relevance: float,
        urgency_level: str
    ) -> float:
        """Calculate 0.0-1.0 recommendation score"""
        
        # Handle None values
        trend_score = trend_score or 0
        business_relevance = business_relevance or 0.5
        
        # Base score from trend strength (0-0.4)
        base = min(0.4, trend_score / 250)
        
        # Business relevance (0-0.4)
        relevance = float(business_relevance) * 0.4
        
        # Urgency bonus (0-0.2)
        urgency_map = {
            'critical': 0.2,
            'high': 0.15,
            'medium': 0.1,
            'low': 0.05
        }
        urgency = urgency_map.get(urgency_level, 0.05)
        
        return min(1.0, base + relevance + urgency)
    
    # ========================================================================
    # BLOG POST GENERATION
    # ========================================================================
    
    async def generate_blog_outline(
        self,
        keyword: str,
        business_area: str
    ) -> Dict[str, Any]:
        """
        Generate a blog post outline (actually generates full post)
        
        Args:
            keyword: Main topic/keyword
            business_area: Which business this is for
        
        Returns:
            {
                'title': str,
                'content': str,
                'word_count': int,
                'success': bool
            }
        """
        db = await self._get_db()
        
        try:
            # Get trend context - FIXED column name
            trend_data = await db.fetch_one('''
                SELECT 
                    trend_score,
                    trend_momentum,
                    created_at
                FROM trend_monitoring
                WHERE keyword = $1 AND business_area = $2
                ORDER BY trend_date DESC
                LIMIT 1
            ''', keyword, business_area)
            
            # Get RSS insights
            rss_insights = await db.fetch_all('''
                SELECT 
                    insight_text,
                    actionable_idea,
                    correlation_type
                FROM content_correlation_insights
                WHERE trend_keyword = $1 AND business_area = $2
                ORDER BY created_at DESC
                LIMIT 5
            ''', keyword, business_area)
            
            # Build prompt
            trend_score = trend_data['trend_score'] if trend_data else 'N/A'
            trend_momentum = trend_data['trend_momentum'] if trend_data else 'unknown'
            
            prompt = f"""Create a blog post outline about: "{keyword}"

**Context:**
- Business: {business_area}
- Current trend score: {trend_score}
- Trend momentum: {trend_momentum}

**CRITICAL REQUIREMENTS:**
- MINIMUM 1200 words (this is NON-NEGOTIABLE)
- Target range: 1200-1800 words
- Write in full paragraphs with complete sentences
- Include compelling, SEO-friendly title
- Strong introduction with hook
- 3-5 detailed content sections with subheadings
- Conclusion with clear call-to-action
- Natural keyword integration throughout

"""
            
            if rss_insights:
                prompt += "**Related Industry Insights:**\n"
                for insight in rss_insights:
                    insight_dict = dict(insight)
                    prompt += f"- {insight_dict['insight_text']}\n"
            
            prompt += """\n**Output Format:**
Write the complete blog post as formatted markdown with:

# [Your SEO-Optimized Title Here]

[Introduction paragraphs - 200-300 words with engaging hook]

## [First Main Section Heading]

[Full paragraphs explaining this section - 300-400 words]

## [Second Main Section Heading]

[Full paragraphs explaining this section - 300-400 words]

[Continue for 3-5 main sections...]

## [Conclusion Heading]

[Conclusion paragraphs with clear CTA - 150-200 words]

---
SEO Keywords: keyword1, keyword2, keyword3, etc.

REMINDER: This must be a COMPLETE blog post with full paragraphs, not an outline. Minimum 1200 words."""
            
            # Generate blog post
            client = await self._get_client()
            response = await client.chat_completion(
                messages=[
                    {'role': 'system', 'content': 'You are an expert blog writer who creates comprehensive, SEO-optimized content. You ALWAYS meet word count requirements and write in full paragraphs, never outlines.'},
                    {'role': 'user', 'content': prompt}
                ],
                model='anthropic/claude-sonnet-4-5-20250929',
                max_tokens=4000,
                temperature=0.7
            )
            
            blog_content = response['choices'][0]['message']['content'].strip()

            # Extract word count for verification
            word_count = len(blog_content.split())

            logger.info(f"Generated blog post: {word_count} words")

            if word_count < 1000:
                logger.warning(f"⚠️ Blog post only {word_count} words - below minimum!")

            return {
                'content': blog_content,
                'word_count': word_count,
                'success': word_count >= 1000
            }
            
        except Exception as e:
            logger.error(f"Failed to generate blog outline: {e}", exc_info=True)
            raise
    
    async def generate_blog_post(
        self,
        outline: Dict[str, Any],
        business_area: str,
        keyword: str
    ) -> Dict[str, Any]:
        """
        Generate full blog post from outline
        
        Args:
            outline: Blog outline from generate_blog_outline()
            business_area: Which business this is for
            keyword: Main keyword/topic
        
        Returns:
            {
                'success': bool,
                'queue_id': UUID,
                'full_text': str,
                'word_count': int,
                'seo_metadata': dict
            }
        """
        db = await self._get_db()
        
        try:
            # Generate each section
            sections_content = []
            client = await self._get_client()
            
            # Introduction
            intro_prompt = f"""Write the introduction section for this blog post:

**Title:** {outline['title']}
**Hook:** {outline['introduction']['hook']}
**Overview:** {outline['introduction']['overview']}

Write 2-3 paragraphs (150-200 words) that:
1. Start with an engaging hook
2. Establish why this topic matters
3. Preview what the reader will learn

Output only the introduction paragraphs, no headings or meta-commentary."""
            
            intro_response = await client.chat_completion(
                messages=[{'role': 'user', 'content': intro_prompt}],
                model='anthropic/claude-sonnet-4-5-20250929',
                max_tokens=500,
                temperature=0.7
            )
            
            introduction = intro_response['choices'][0]['message']['content'].strip()
            sections_content.append(f"## Introduction\n\n{introduction}")
            
            # Main sections
            for section in outline['sections']:
                section_prompt = f"""Write the content for this blog section:

**Section Heading:** {section['heading']}
**Key Points to Cover:**
{chr(10).join(f'- {point}' for point in section['points'])}

Write 250-300 words that:
1. Explain each key point clearly
2. Provide examples or details
3. Keep the tone professional but engaging

Output only the section content, no heading (I'll add that)."""
                
                section_response = await client.chat_completion(
                    messages=[{'role': 'user', 'content': section_prompt}],
                    model='anthropic/claude-sonnet-4-5-20250929',
                    max_tokens=600,
                    temperature=0.7
                )
                
                section_content = section_response['choices'][0]['message']['content'].strip()
                sections_content.append(f"## {section['heading']}\n\n{section_content}")
                
                # Rate limiting
                await asyncio.sleep(1)
            
            # Conclusion
            conclusion_prompt = f"""Write the conclusion for this blog post:

**Summary:** {outline['conclusion']['summary']}
**Call to Action:** {outline['conclusion']['cta']}

Write 2 paragraphs (100-150 words) that:
1. Recap the main takeaways
2. Include a clear, actionable CTA

Output only the conclusion paragraphs."""
            
            conclusion_response = await client.chat_completion(
                messages=[{'role': 'user', 'content': conclusion_prompt}],
                model='anthropic/claude-sonnet-4-5-20250929',
                max_tokens=400,
                temperature=0.7
            )
            
            conclusion = conclusion_response['choices'][0]['message']['content'].strip()
            sections_content.append(f"## Conclusion\n\n{conclusion}")
            
            # Assemble full post
            full_text = f"# {outline['title']}\n\n" + "\n\n".join(sections_content)
            word_count = len(full_text.split())
            
            # Generate SEO metadata
            seo_metadata = {
                'title_tag': outline['title'][:60],
                'meta_description': outline['introduction']['overview'][:155],
                'keywords': outline['seo_keywords'],
                'slug': keyword.lower().replace(' ', '-')
            }
            
            # Calculate recommendation score
            rec_score = 0.85  # High confidence for blog posts
            
            # Store in content_recommendation_queue
            queue_id = await db.fetch_val('''
                INSERT INTO content_recommendation_queue (
                    content_type,
                    business_area,
                    generated_content,
                    recommendation_score
                ) VALUES ($1, $2, $3, $4)
                RETURNING id
            ''',
                'blog_post',
                business_area,
                json.dumps({
                    'title': outline['title'],
                    'full_text': full_text,
                    'word_count': word_count,
                    'seo_metadata': seo_metadata,
                    'outline': outline
                }),
                rec_score
            )
            
            logger.info(f"Generated blog post: {outline['title']} ({word_count} words)")
            
            return {
                'success': True,
                'queue_id': queue_id,
                'full_text': full_text,
                'word_count': word_count,
                'seo_metadata': seo_metadata
            }
            
        except Exception as e:
            logger.error(f"Failed to generate blog post: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


#===============================================================================
# MODULE EXPORTS
#===============================================================================

__all__ = [
    'ContentGenerator',
    'get_content_generator',
    'USER_ID'
]


# Test script
if __name__ == "__main__":
    async def test():
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not set")
            return
        
        generator = get_content_generator()
        
        print("🧪 Testing blog outline generation...")
        outline = await generator.generate_blog_outline(
            keyword="emotional support cats",
            business_area="damnitcarl"
        )
        
        print(f"\n✅ Generated outline")
        print(f"Word count: {outline['word_count']}")
        print(f"Success: {outline['success']}")
    
    asyncio.run(test())
