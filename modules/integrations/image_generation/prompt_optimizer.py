# modules/integrations/image_generation/prompt_optimizer.py
"""
Content Intelligence Prompt Optimizer for Syntax Prime V2
Enhances image generation prompts using RSS learning, Google Trends, and marketing insights

Key Features:
- Integrates RSS marketing intelligence for trending context
- Uses current trend data to enhance visual relevance
- Applies marketing best practices to prompt optimization
- Adapts style based on content intelligence insights
- Provides context-aware prompt enhancements
"""

import asyncio
import asyncpg
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class PromptOptimizer:
    """
    Intelligent prompt optimization using content intelligence
    Transforms basic prompts into marketing-aware, trend-conscious image descriptions
    """
    
    def __init__(self, database_url: str = None):
        import os
        self.database_url = database_url or os.getenv('DATABASE_URL')
        
        # Content type mappings for visual optimization
        self.content_type_enhancements = {
            'blog': {
                'style_keywords': ['professional', 'clean', 'informative', 'trustworthy'],
                'visual_elements': ['header-suitable', 'readable text space', 'brand-friendly'],
                'color_preferences': ['corporate', 'professional blue', 'clean white'],
                'composition': 'landscape orientation, text overlay space'
            },
            'social': {
                'style_keywords': ['eye-catching', 'vibrant', 'engaging', 'shareable'],
                'visual_elements': ['mobile-optimized', 'high contrast', 'bold graphics'],
                'color_preferences': ['bright', 'saturated', 'attention-grabbing'],
                'composition': 'square or vertical, mobile-first design'
            },
            'marketing': {
                'style_keywords': ['polished', 'premium', 'conversion-focused', 'persuasive'],
                'visual_elements': ['call-to-action space', 'benefit-focused', 'aspirational'],
                'color_preferences': ['brand colors', 'trust-building', 'premium feel'],
                'composition': 'clear focal point, action-oriented layout'
            },
            'illustration': {
                'style_keywords': ['artistic', 'creative', 'detailed', 'expressive'],
                'visual_elements': ['hand-drawn feel', 'unique perspective', 'storytelling'],
                'color_preferences': ['artistic palette', 'creative expression', 'mood-appropriate'],
                'composition': 'creative composition, artistic interpretation'
            }
        }
        
        # Marketing trend keywords to boost based on RSS data
        self.trending_modifiers = {
            'ai': ['AI-powered', 'intelligent', 'automated', 'smart technology'],
            'automation': ['streamlined', 'efficient', 'seamless', 'optimized workflow'],
            'personalization': ['customized', 'tailored', 'individual-focused', 'personal touch'],
            'video': ['dynamic', 'motion-inspired', 'video-style', 'animated feel'],
            'sustainability': ['eco-friendly', 'green', 'sustainable', 'environmentally conscious'],
            'privacy': ['secure', 'trusted', 'privacy-focused', 'confidential'],
            'mobile': ['mobile-first', 'thumb-friendly', 'touch-optimized', 'responsive'],
            'voice': ['conversational', 'natural', 'human-centered', 'approachable']
        }
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    async def optimize_prompt(self, original_prompt: str, content_type: str = 'general',
                            business_context: str = None, style_template: Dict = None) -> Dict[str, Any]:
        """
        Optimize a prompt using current marketing intelligence
        
        Args:
            original_prompt: User's original prompt
            content_type: Type of content ('blog', 'social', 'marketing', etc.)
            business_context: Optional business area context
            style_template: Optional style template data
            
        Returns:
            Dict with optimized prompt and enhancement metadata
        """
        try:
            # Get current marketing intelligence
            marketing_context = await self._get_marketing_intelligence(original_prompt, content_type)
            
            # Get trending keywords relevant to the prompt
            trending_keywords = await self._get_trending_keywords(original_prompt)
            
            # Build enhanced prompt
            enhanced_prompt = await self._build_enhanced_prompt(
                original_prompt, content_type, marketing_context, 
                trending_keywords, style_template
            )
            
            # Generate enhancement metadata
            enhancement_metadata = {
                'marketing_insights_applied': len(marketing_context.get('insights', [])),
                'trending_keywords_used': trending_keywords,
                'content_type_enhancements': self.content_type_enhancements.get(content_type, {}),
                'rss_context_found': bool(marketing_context.get('rss_matches')),
                'optimization_confidence': self._calculate_optimization_confidence(
                    marketing_context, trending_keywords, content_type
                )
            }
            
            return {
                'original_prompt': original_prompt,
                'enhanced_prompt': enhanced_prompt,
                'enhancement_metadata': enhancement_metadata,
                'marketing_context': marketing_context,
                'trending_elements': trending_keywords
            }
            
        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}")
            # Fallback to basic enhancement
            return self._fallback_enhancement(original_prompt, content_type, style_template)
    
    async def _get_marketing_intelligence(self, prompt: str, content_type: str) -> Dict[str, Any]:
        """Get relevant marketing intelligence from RSS learning system"""
        conn = await self.get_connection()
        
        try:
            # Extract keywords from the prompt for RSS matching
            prompt_keywords = self._extract_prompt_keywords(prompt)
            
            if not prompt_keywords:
                return {'insights': [], 'rss_matches': [], 'trends': []}
            
            # Search RSS content for relevant marketing insights
            rss_query = '''
                SELECT title, marketing_insights, actionable_tips, keywords, 
                       trend_score, category, sentiment_score
                FROM rss_feed_entries
                WHERE ai_processed = true
                AND marketing_insights IS NOT NULL
                AND (
                    title ILIKE ANY($1) OR 
                    marketing_insights ILIKE ANY($1) OR
                    keywords::text ILIKE ANY($1)
                )
                AND pub_date > NOW() - INTERVAL '90 days'
                ORDER BY trend_score DESC, pub_date DESC
                LIMIT 5
            '''
            
            search_patterns = [f'%{keyword}%' for keyword in prompt_keywords]
            rss_matches = await conn.fetch(rss_query, search_patterns)
            
            # Get general trending insights for the content type
            trending_query = '''
                SELECT marketing_insights, actionable_tips, keywords, trend_score
                FROM rss_feed_entries
                WHERE category ILIKE $1
                AND ai_processed = true
                AND trend_score > 6.0
                AND pub_date > NOW() - INTERVAL '30 days'
                ORDER BY trend_score DESC
                LIMIT 3
            '''
            
            content_category = self._map_content_type_to_rss_category(content_type)
            trending_insights = await conn.fetch(trending_query, f'%{content_category}%')
            
            # Process and extract actionable insights
            insights = []
            for row in list(rss_matches) + list(trending_insights):
                if row['marketing_insights']:
                    insights.append({
                        'insight': row['marketing_insights'][:200],  # Truncate for prompt use
                        'trend_score': float(row['trend_score']),
                        'category': row.get('category', ''),
                        'sentiment': float(row['sentiment_score']) if row['sentiment_score'] else 0.0
                    })
            
            return {
                'insights': insights,
                'rss_matches': [dict(row) for row in rss_matches],
                'trending_insights': [dict(row) for row in trending_insights],
                'prompt_keywords': prompt_keywords
            }
            
        finally:
            await conn.close()
    
    async def _get_trending_keywords(self, prompt: str) -> List[str]:
        """Get trending keywords relevant to the prompt from RSS data"""
        conn = await self.get_connection()
        
        try:
            # Get trending keywords from recent high-scoring RSS entries
            trending_query = '''
                SELECT 
                    jsonb_array_elements_text(keywords) as keyword,
                    COUNT(*) as frequency,
                    AVG(trend_score) as avg_score
                FROM rss_feed_entries
                WHERE pub_date > NOW() - INTERVAL '45 days'
                AND trend_score > 5.0
                AND ai_processed = true
                GROUP BY jsonb_array_elements_text(keywords)
                HAVING COUNT(*) >= 2
                ORDER BY avg_score DESC, frequency DESC
                LIMIT 15
            '''
            
            trending_data = await conn.fetch(trending_query)
            
            # Filter keywords relevant to the prompt
            prompt_lower = prompt.lower()
            relevant_keywords = []
            
            for row in trending_data:
                keyword = row['keyword'].lower()
                # Check if keyword is semantically related to prompt
                if (self._keywords_are_related(keyword, prompt_lower) or 
                    keyword in self.trending_modifiers):
                    relevant_keywords.append(keyword)
            
            return relevant_keywords[:5]  # Limit to top 5 most relevant
            
        finally:
            await conn.close()
    
    async def _build_enhanced_prompt(self, original_prompt: str, content_type: str,
                                   marketing_context: Dict, trending_keywords: List[str],
                                   style_template: Dict = None) -> str:
        """Build the enhanced prompt with all intelligence integrated"""
        
        enhanced_parts = [original_prompt]
        
        # Add content type specific enhancements
        if content_type in self.content_type_enhancements:
            type_config = self.content_type_enhancements[content_type]
            
            # Add style keywords
            style_keywords = type_config['style_keywords'][:2]  # Use top 2 to avoid overcrowding
            enhanced_parts.extend(style_keywords)
            
            # Add composition guidance
            if type_config['composition']:
                enhanced_parts.append(type_config['composition'])
        
        # Add trending modifier keywords
        for trending_keyword in trending_keywords[:3]:  # Limit to 3 trending elements
            if trending_keyword in self.trending_modifiers:
                modifier = self.trending_modifiers[trending_keyword][0]  # Use first modifier
                enhanced_parts.append(modifier)
        
        # Add marketing insights context (carefully to avoid prompt pollution)
        high_value_insights = [
            insight for insight in marketing_context.get('insights', [])
            if insight.get('trend_score', 0) > 7.0
        ]
        
        if high_value_insights:
            # Extract visual cues from top marketing insight
            top_insight = high_value_insights[0]['insight']
            visual_cues = self._extract_visual_cues_from_insight(top_insight)
            if visual_cues:
                enhanced_parts.extend(visual_cues[:2])  # Add max 2 visual cues
        
        # Add style template elements if provided
        if style_template and 'style_prompt' in style_template:
            template_elements = style_template['style_prompt'].split(', ')[:3]
            enhanced_parts.extend(template_elements)
        
        # Quality and format modifiers
        enhanced_parts.extend([
            'high quality', 'professional', 'detailed', 'sharp focus'
        ])
        
        # Clean up and join
        enhanced_prompt = ', '.join(self._clean_prompt_parts(enhanced_parts))
        
        # Ensure prompt isn't too long (most models have limits)
        if len(enhanced_prompt) > 500:
            # Prioritize: original + content type + quality
            essential_parts = [
                original_prompt,
                *self.content_type_enhancements.get(content_type, {}).get('style_keywords', [])[:2],
                'high quality', 'professional'
            ]
            enhanced_prompt = ', '.join(self._clean_prompt_parts(essential_parts))
        
        return enhanced_prompt
    
    def _extract_prompt_keywords(self, prompt: str) -> List[str]:
        """Extract meaningful keywords from user prompt"""
        # Remove common words and extract meaningful terms
        stop_words = {
            'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'create', 'make', 'generate', 'image', 'picture'
        }
        
        # Split and clean
        words = re.findall(r'\b\w+\b', prompt.lower())
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        
        return keywords[:8]  # Limit to 8 most relevant words
    
    def _map_content_type_to_rss_category(self, content_type: str) -> str:
        """Map image content type to RSS categories"""
        mapping = {
            'blog': 'content_marketing',
            'social': 'social_media',
            'marketing': 'marketing',
            'illustration': 'content_marketing',
            'professional': 'marketing',
            'general': 'marketing'
        }
        return mapping.get(content_type, 'marketing')
    
    def _keywords_are_related(self, keyword: str, prompt: str) -> bool:
        """Check if a keyword is semantically related to the prompt"""
        # Simple semantic matching - could be enhanced with word embeddings
        keyword_words = set(keyword.split())
        prompt_words = set(prompt.split())
        
        # Check for overlap or common themes
        if keyword_words.intersection(prompt_words):
            return True
        
        # Check for common themes
        themes = {
            'business': ['marketing', 'corporate', 'professional', 'strategy'],
            'technology': ['ai', 'automation', 'digital', 'tech', 'software'],
            'creative': ['design', 'art', 'creative', 'visual', 'artistic'],
            'social': ['social', 'community', 'sharing', 'engagement']
        }
        
        for theme_keywords in themes.values():
            if (keyword in theme_keywords and 
                any(theme_word in prompt for theme_word in theme_keywords)):
                return True
        
        return False
    
    def _extract_visual_cues_from_insight(self, insight: str) -> List[str]:
        """Extract visual design cues from marketing insights"""
        visual_cues = []
        insight_lower = insight.lower()
        
        # Visual style indicators
        if 'video' in insight_lower:
            visual_cues.append('dynamic composition')
        if 'personal' in insight_lower:
            visual_cues.append('human-centered')
        if 'mobile' in insight_lower:
            visual_cues.append('mobile-optimized')
        if 'trust' in insight_lower:
            visual_cues.append('trustworthy aesthetic')
        if 'engage' in insight_lower:
            visual_cues.append('engaging visual design')
        if 'convert' in insight_lower:
            visual_cues.append('conversion-focused layout')
        
        return visual_cues
    
    def _clean_prompt_parts(self, parts: List[str]) -> List[str]:
        """Clean and deduplicate prompt parts"""
        seen = set()
        cleaned_parts = []
        
        for part in parts:
            if isinstance(part, str):
                part = part.strip().lower()
                if part and part not in seen and len(part) > 1:
                    seen.add(part)
                    cleaned_parts.append(part)
        
        return cleaned_parts
    
    def _calculate_optimization_confidence(self, marketing_context: Dict,
                                         trending_keywords: List[str], 
                                         content_type: str) -> float:
        """Calculate confidence score for the optimization (0.0 to 1.0)"""
        confidence = 0.3  # Base confidence
        
        # Boost for marketing insights
        if marketing_context.get('insights'):
            confidence += 0.2 * min(len(marketing_context['insights']), 3)
        
        # Boost for trending keywords
        if trending_keywords:
            confidence += 0.1 * min(len(trending_keywords), 3)
        
        # Boost for RSS matches
        if marketing_context.get('rss_matches'):
            confidence += 0.2
        
        # Boost for recognized content type
        if content_type in self.content_type_enhancements:
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _fallback_enhancement(self, original_prompt: str, content_type: str,
                            style_template: Dict = None) -> Dict[str, Any]:
        """Fallback enhancement when intelligence gathering fails"""
        enhanced_parts = [original_prompt]
        
        # Add basic content type enhancements
        if content_type in self.content_type_enhancements:
            type_config = self.content_type_enhancements[content_type]
            enhanced_parts.extend(type_config['style_keywords'][:2])
        
        # Add style template if provided
        if style_template and 'style_prompt' in style_template:
            enhanced_parts.append(style_template['style_prompt'])
        
        # Basic quality modifiers
        enhanced_parts.extend(['high quality', 'professional', 'detailed'])
        
        enhanced_prompt = ', '.join(self._clean_prompt_parts(enhanced_parts))
        
        return {
            'original_prompt': original_prompt,
            'enhanced_prompt': enhanced_prompt,
            'enhancement_metadata': {
                'fallback_mode': True,
                'optimization_confidence': 0.3
            },
            'marketing_context': {},
            'trending_elements': []
        }
    
    async def get_optimization_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics about prompt optimizations"""
        conn = await self.get_connection()
        
        try:
            # Get trending keywords stats
            trending_stats = await conn.fetch('''
                SELECT 
                    jsonb_array_elements_text(keywords) as keyword,
                    COUNT(*) as frequency,
                    AVG(trend_score) as avg_score
                FROM rss_feed_entries
                WHERE pub_date > NOW() - INTERVAL '%s days'
                AND ai_processed = true
                GROUP BY jsonb_array_elements_text(keywords)
                ORDER BY frequency DESC
                LIMIT 10
            ''' % days)
            
            # Get content categories
            category_stats = await conn.fetch('''
                SELECT category, COUNT(*) as count, AVG(trend_score) as avg_score
                FROM rss_feed_entries
                WHERE pub_date > NOW() - INTERVAL '%s days'
                AND ai_processed = true
                GROUP BY category
                ORDER BY count DESC
            ''' % days)
            
            return {
                'trending_keywords': [dict(row) for row in trending_stats],
                'content_categories': [dict(row) for row in category_stats],
                'total_insights_available': len(trending_stats),
                'optimization_sources': ['RSS Learning', 'Content Intelligence', 'Style Templates']
            }
            
        finally:
            await conn.close()

# Test function for development
async def test_prompt_optimizer():
    """Test the prompt optimizer with sample prompts"""
    optimizer = PromptOptimizer()
    
    print("🧪 TESTING PROMPT OPTIMIZER")
    print("=" * 40)
    
    test_cases = [
        ("a business meeting", "marketing"),
        ("social media post design", "social"),
        ("blog header image about AI", "blog"),
        ("creative illustration", "illustration")
    ]
    
    for prompt, content_type in test_cases:
        print(f"\n📝 Testing: '{prompt}' ({content_type})")
        
        result = await optimizer.optimize_prompt(prompt, content_type)
        
        print(f"Original: {result['original_prompt']}")
        print(f"Enhanced: {result['enhanced_prompt']}")
        print(f"Confidence: {result['enhancement_metadata']['optimization_confidence']:.2f}")
        print(f"Trending elements: {result['trending_elements']}")
        
        if result['marketing_context'].get('insights'):
            print(f"Marketing insights applied: {len(result['marketing_context']['insights'])}")

if __name__ == "__main__":
    asyncio.run(test_prompt_optimizer())