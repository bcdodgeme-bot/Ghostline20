# modules/integrations/rss_learning/content_analyzer.py
"""
Content Analyzer - AI-powered analysis of RSS content
Extracts marketing insights, trends, and actionable tips from RSS feed items

UPDATED: Session 15 - Added singleton pattern
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

# AI imports
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# Singleton instance
_content_analyzer_instance: Optional['ContentAnalyzer'] = None


def get_content_analyzer() -> 'ContentAnalyzer':
    """Get singleton ContentAnalyzer instance"""
    global _content_analyzer_instance
    if _content_analyzer_instance is None:
        _content_analyzer_instance = ContentAnalyzer()
    return _content_analyzer_instance


class ContentAnalyzer:
    """Analyzes RSS content for marketing insights and trends"""
    
    def __init__(self):
        self.openai_client = self._init_openai()
        
        # Content categorization patterns
        self.category_patterns = {
            'seo': [
                'search engine optimization', 'SEO', 'SERP', 'keyword research', 'backlink',
                'organic search', 'google algorithm', 'page rank', 'meta description',
                'title tag', 'schema markup', 'technical seo', 'local seo', 'rank math',
                'google updates', 'search ranking', 'indexing', 'crawling'
            ],
            'content_marketing': [
                'content marketing', 'content strategy', 'blog writing', 'storytelling',
                'editorial calendar', 'content creation', 'brand voice', 'copywriting',
                'content optimization', 'content distribution', 'content planning',
                'thought leadership', 'brand storytelling'
            ],
            'social_media': [
                'social media', 'facebook marketing', 'instagram', 'twitter', 'linkedin',
                'social media strategy', 'social engagement', 'influencer marketing',
                'social analytics', 'social media calendar', 'community management',
                'tiktok', 'youtube', 'social content', 'viral marketing'
            ],
            'email_marketing': [
                'email marketing', 'email campaign', 'newsletter', 'email automation',
                'email list', 'drip campaign', 'email design', 'deliverability',
                'open rates', 'click rates', 'email segmentation'
            ],
            'analytics': [
                'google analytics', 'marketing analytics', 'conversion tracking', 'KPIs',
                'marketing metrics', 'ROI measurement', 'attribution modeling',
                'data analysis', 'marketing dashboard', 'performance tracking',
                'conversion rate', 'funnel analysis'
            ]
        }
        
        # Content type patterns
        self.content_type_patterns = {
            'guide': ['guide', 'how to', 'step by step', 'complete guide', 'ultimate guide'],
            'tutorial': ['tutorial', 'walkthrough', 'how-to', 'instructions'],
            'case_study': ['case study', 'success story', 'real world example'],
            'news': ['news', 'update', 'announcement', 'breaking', 'latest'],
            'tips': ['tips', 'best practices', 'tricks', 'hacks', 'strategies'],
            'analysis': ['analysis', 'research', 'study', 'report', 'findings'],
            'opinion': ['opinion', 'perspective', 'thoughts', 'commentary']
        }
    
    def _init_openai(self):
        """Initialize OpenAI client if available"""
        if OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY'):
            return AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        return None
    
    async def analyze_content(self, title: str, content: str, category: str) -> Dict[str, Any]:
        """Analyze RSS content and extract marketing insights"""
        
        # Start with basic analysis
        analysis = {
            'keywords': self._extract_keywords(title, content),
            'content_type': self._determine_content_type(title, content),
            'relevance_score': self._calculate_relevance_score(title, content, category),
            'trend_score': self._calculate_trend_score(title, content),
            'sentiment_score': self._basic_sentiment_analysis(content)
        }
        
        # Add AI analysis if available
        if self.openai_client:
            try:
                ai_analysis = await self._ai_analyze_content(title, content, category)
                analysis.update(ai_analysis)
            except Exception as e:
                logger.warning(f"AI analysis failed, using basic analysis: {e}")
                analysis.update(self._fallback_analysis(title, content, category))
        else:
            # Use fallback analysis without AI
            analysis.update(self._fallback_analysis(title, content, category))
        
        return analysis
    
    async def _ai_analyze_content(self, title: str, content: str, category: str) -> Dict[str, Any]:
        """AI-powered content analysis using OpenAI"""
        
        # Truncate content for API limits
        content_excerpt = content[:3000] if len(content) > 3000 else content
        
        prompt = f"""
        Analyze this marketing content for actionable insights:
        
        Title: {title}
        Category: {category}
        Content: {content_excerpt}
        
        Provide a JSON response with:
        1. "insights" - 2-3 sentence summary of key marketing insights
        2. "actionable_tips" - array of 3-5 specific actionable tips for marketers
        3. "trending_topics" - array of trending topics/themes mentioned
        4. "target_audience" - who this content is most relevant for
        5. "marketing_angle" - how this could be applied to marketing campaigns
        
        Focus on practical, actionable insights that can help with SEO, content marketing, social media, or email marketing.
        """
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a marketing expert analyzing content for actionable insights. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Try to parse JSON response
            try:
                ai_data = json.loads(ai_response)
                return {
                    'insights': ai_data.get('insights', ''),
                    'actionable_tips': ai_data.get('actionable_tips', []),
                    'trending_topics': ai_data.get('trending_topics', []),
                    'target_audience': ai_data.get('target_audience', ''),
                    'marketing_angle': ai_data.get('marketing_angle', '')
                }
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return {
                    'insights': ai_response[:500],  # Use raw response as insights
                    'actionable_tips': [],
                    'trending_topics': [],
                    'target_audience': '',
                    'marketing_angle': ''
                }
                
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            raise
    
    def _fallback_analysis(self, title: str, content: str, category: str) -> Dict[str, Any]:
        """Fallback analysis without AI"""
        
        # Extract basic insights based on patterns
        insights = self._extract_basic_insights(title, content, category)
        actionable_tips = self._extract_actionable_tips(content)
        trending_topics = self._extract_trending_topics(title, content)
        
        return {
            'insights': insights,
            'actionable_tips': actionable_tips,
            'trending_topics': trending_topics,
            'target_audience': self._determine_target_audience(category, content),
            'marketing_angle': self._suggest_marketing_angle(category, title, content)
        }
    
    def _extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract relevant keywords from content"""
        text = f"{title} {content}".lower()
        
        # Common marketing keywords to look for
        marketing_keywords = [
            'seo', 'content', 'marketing', 'strategy', 'campaign', 'conversion',
            'engagement', 'analytics', 'social media', 'email', 'optimization',
            'traffic', 'audience', 'brand', 'digital', 'advertising', 'roi',
            'keyword', 'backlink', 'ranking', 'google', 'search', 'organic'
        ]
        
        found_keywords = []
        for keyword in marketing_keywords:
            if keyword in text:
                found_keywords.append(keyword)
        
        # Also extract from category patterns
        for category, patterns in self.category_patterns.items():
            for pattern in patterns:
                if pattern.lower() in text and pattern not in found_keywords:
                    found_keywords.append(pattern)
        
        return found_keywords[:10]  # Limit to 10 keywords
    
    def _determine_content_type(self, title: str, content: str) -> str:
        """Determine the type of content"""
        title_lower = title.lower()
        content_lower = content.lower()[:500]
        
        for content_type, patterns in self.content_type_patterns.items():
            for pattern in patterns:
                if pattern in title_lower or pattern in content_lower:
                    return content_type
        
        return 'article'
    
    def _calculate_relevance_score(self, title: str, content: str, category: str) -> float:
        """Calculate relevance score (1-10) based on content quality indicators"""
        score = 5.0  # Base score
        
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Boost for actionable content
        actionable_terms = ['how to', 'guide', 'tutorial', 'step by step', 'best practices', 'tips', 'strategies']
        score += sum(0.5 for term in actionable_terms if term in title_lower or term in content_lower)
        
        # Boost for current year content
        current_year = str(datetime.now().year)
        if current_year in title or current_year in content:
            score += 1.0
        
        # Boost for comprehensive content
        if len(content) > 2000:
            score += 1.0
        elif len(content) > 1000:
            score += 0.5
        
        # Boost for category-specific terms
        category_terms = self.category_patterns.get(category, [])
        term_count = sum(1 for term in category_terms if term.lower() in content_lower)
        score += min(term_count * 0.2, 2.0)  # Max 2 point boost
        
        # Penalty for very short content
        if len(content) < 200:
            score -= 2.0
        
        return max(1.0, min(9.99, score))
    
    def _calculate_trend_score(self, title: str, content: str) -> float:
        """Calculate trend score based on trending topics and recency indicators"""
        score = 5.0
        
        text = f"{title} {content}".lower()
        
        # Trending topics in 2025
        trending_topics = [
            'ai', 'artificial intelligence', 'chatgpt', 'automation',
            'personalization', 'zero-click', 'voice search', 'video marketing',
            'sustainability', 'privacy', 'first-party data', 'attribution',
            'llm', 'generative ai', 'machine learning'
        ]
        
        for topic in trending_topics:
            if topic in text:
                score += 0.5
        
        # Current year/month references
        current_year = str(datetime.now().year)
        current_month = datetime.now().strftime('%B')
        
        if current_year in text:
            score += 1.0
        if current_month.lower() in text:
            score += 0.5
        
        # Time-sensitive indicators
        timely_terms = ['latest', 'new', 'updated', 'recent', '2025', 'now', 'current']
        score += sum(0.3 for term in timely_terms if term in text)
        
        return max(1.0, min(9.99, score))
    
    def _basic_sentiment_analysis(self, content: str) -> float:
        """Basic sentiment analysis (-1 to 1)"""
        positive_words = [
            'excellent', 'amazing', 'best', 'great', 'fantastic', 'success',
            'improve', 'boost', 'increase', 'effective', 'proven', 'results'
        ]
        
        negative_words = [
            'terrible', 'worst', 'failed', 'decrease', 'decline', 'problem',
            'issue', 'challenge', 'difficult', 'struggle', 'mistake'
        ]
        
        content_lower = content.lower()
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        total_words = len(content.split())
        if total_words == 0:
            return 0.0
        
        sentiment = (positive_count - negative_count) / max(total_words / 100, 1)
        return max(-1.0, min(1.0, sentiment))
    
    def _extract_basic_insights(self, title: str, content: str, category: str) -> str:
        """Extract basic insights without AI"""
        insights = []
        
        # Category-specific insights
        if category == 'seo':
            insights.append("Focus on search engine optimization strategies and ranking factors.")
        elif category == 'content_marketing':
            insights.append("Emphasize content creation, distribution, and engagement tactics.")
        elif category == 'social_media':
            insights.append("Leverage social platform features and community building approaches.")
        
        # Content type insights
        if 'how to' in title.lower():
            insights.append("Provides step-by-step guidance for implementation.")
        if any(term in content.lower() for term in ['case study', 'example', 'results']):
            insights.append("Includes real-world examples and measurable results.")
        
        return " ".join(insights) if insights else f"Marketing insights related to {category} strategy and best practices."
    
    def _extract_actionable_tips(self, content: str) -> List[str]:
        """Extract actionable tips from content"""
        tips = []
        
        # Look for numbered lists or bullet points
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.', line) or line.startswith('•') or line.startswith('-'):
                if len(line) > 20 and len(line) < 200:  # Reasonable tip length
                    tips.append(line)
        
        # Generic actionable advice if no specific tips found
        if not tips:
            if 'optimize' in content.lower():
                tips.append("Focus on optimization strategies mentioned in the content")
            if 'strategy' in content.lower():
                tips.append("Apply the strategic approaches discussed")
            if 'test' in content.lower():
                tips.append("Implement testing methodologies described")
        
        return tips[:5]  # Limit to 5 tips
    
    def _extract_trending_topics(self, title: str, content: str) -> List[str]:
        """Extract trending topics mentioned"""
        text = f"{title} {content}".lower()
        trending = []
        
        # AI and technology trends
        tech_trends = ['ai', 'artificial intelligence', 'automation', 'machine learning', 'chatgpt']
        trending.extend([trend for trend in tech_trends if trend in text])
        
        # Marketing trends
        marketing_trends = ['personalization', 'video marketing', 'voice search', 'zero-click', 'first-party data']
        trending.extend([trend for trend in marketing_trends if trend in text])
        
        return list(set(trending))[:5]
    
    def _determine_target_audience(self, category: str, content: str) -> str:
        """Determine target audience based on category and content"""
        audience_map = {
            'seo': 'SEO specialists, digital marketers, content creators',
            'content_marketing': 'Content marketers, brand managers, marketing teams',
            'social_media': 'Social media managers, community managers, influencers',
            'email_marketing': 'Email marketers, CRM managers, marketing automation specialists',
            'analytics': 'Marketing analysts, data specialists, performance marketers'
        }
        
        return audience_map.get(category, 'Digital marketers and business owners')
    
    def _suggest_marketing_angle(self, category: str, title: str, content: str) -> str:
        """Suggest marketing angle for the content"""
        if 'strategy' in title.lower():
            return "Use as strategic framework for campaign planning"
        elif 'tips' in title.lower() or 'best practices' in title.lower():
            return "Implement tactical recommendations for immediate improvements"
        elif 'case study' in title.lower():
            return "Reference as proof point and social proof in marketing materials"
        elif 'trend' in title.lower():
            return "Position brand as industry thought leader by addressing trending topics"
        else:
            return f"Apply insights to improve {category} performance and results"
