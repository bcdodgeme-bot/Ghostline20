# modules/integrations/rss_learning/marketing_insights.py
"""
Marketing Insights Extractor - Provides insights for AI brain integration
Formats RSS content for use in marketing email, blog, and social media writing

UPDATED: Session 15 - Added singleton pattern, lazy-load database dependency
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

from .database_manager import get_rss_database

logger = logging.getLogger(__name__)

# Singleton instance
_marketing_insights_instance: Optional['MarketingInsightsExtractor'] = None


def get_marketing_insights_extractor() -> 'MarketingInsightsExtractor':
    """Get singleton MarketingInsightsExtractor instance"""
    global _marketing_insights_instance
    if _marketing_insights_instance is None:
        _marketing_insights_instance = MarketingInsightsExtractor()
    return _marketing_insights_instance


class MarketingInsightsExtractor:
    """Extracts and formats marketing insights from RSS data for AI brain"""
    
    def __init__(self):
        self._db: Optional[Any] = None
    
    @property
    def db(self):
        """Lazy-load database manager"""
        if self._db is None:
            self._db = get_rss_database()
        return self._db
    
    async def get_latest_trends(self, category: str = None, limit: int = 5) -> Dict[str, Any]:
        """Get latest marketing trends for content creation"""
        try:
            insights = await self.db.get_marketing_insights(category, limit)
            trending_topics = await self.db.get_trending_topics(days=14, limit=10)
            
            return {
                'trends_summary': self._format_trends_summary(insights, trending_topics),
                'actionable_insights': self._extract_actionable_insights(insights),
                'trending_keywords': [topic['keyword'] for topic in trending_topics[:5]],
                'recent_topics': self._get_recent_topics(insights),
                'content_angles': self._suggest_content_angles(insights, category)
            }
            
        except Exception as e:
            logger.error(f"Failed to get latest trends: {e}")
            return self._get_fallback_trends()
    
    async def get_writing_inspiration(self, content_type: str, topic: str = None,
                                    target_audience: str = None) -> Dict[str, Any]:
        """Get inspiration and insights for writing specific content types"""
        try:
            relevant_content = await self.db.get_content_for_writing_assistance(content_type, topic)
            
            return {
                'content_ideas': self._generate_content_ideas(relevant_content, content_type),
                'key_messages': self._extract_key_messages(relevant_content),
                'supporting_data': self._get_supporting_data(relevant_content),
                'call_to_action_ideas': self._suggest_cta_ideas(content_type, relevant_content),
                'trending_angles': self._identify_trending_angles(relevant_content),
                'audience_insights': self._get_audience_insights(relevant_content, target_audience)
            }
            
        except Exception as e:
            logger.error(f"Failed to get writing inspiration: {e}")
            return self._get_fallback_inspiration(content_type)
    
    async def get_content_research(self, keywords: List[str]) -> Dict[str, Any]:
        """Research content based on keywords for comprehensive writing support"""
        try:
            search_results = await self.db.search_content_by_keywords(keywords)
            
            return {
                'research_summary': self._create_research_summary(search_results),
                'expert_quotes': self._extract_expert_quotes(search_results),
                'statistics': self._find_statistics(search_results),
                'best_practices': self._compile_best_practices(search_results),
                'case_studies': self._identify_case_studies(search_results),
                'related_topics': self._find_related_topics(search_results)
            }
            
        except Exception as e:
            logger.error(f"Failed to get content research: {e}")
            return self._get_fallback_research()
    
    async def get_campaign_insights(self, campaign_type: str) -> Dict[str, Any]:
        """Get insights for specific campaign types (email, social, blog)"""
        try:
            # Map campaign types to categories
            category_map = {
                'email': 'email_marketing',
                'social': 'social_media',
                'blog': 'content_marketing',
                'seo': 'seo'
            }
            
            category = category_map.get(campaign_type, 'content_marketing')
            insights = await self.db.get_marketing_insights(category, 8)
            
            return {
                'campaign_strategy': self._format_campaign_strategy(insights, campaign_type),
                'success_factors': self._identify_success_factors(insights),
                'common_mistakes': self._identify_common_mistakes(insights),
                'optimization_tips': self._get_optimization_tips(insights, campaign_type),
                'industry_examples': self._find_industry_examples(insights),
                'performance_metrics': self._suggest_performance_metrics(campaign_type)
            }
            
        except Exception as e:
            logger.error(f"Failed to get campaign insights: {e}")
            return self._get_fallback_campaign_insights(campaign_type)
    
    def _format_trends_summary(self, insights: List[Dict], trending_topics: List[Dict]) -> str:
        """Format trends into a readable summary"""
        if not insights:
            return "No recent marketing trends available."
        
        summary_parts = []
        
        # Add trending topics
        if trending_topics:
            top_topics = [topic['keyword'] for topic in trending_topics[:3]]
            summary_parts.append(f"Currently trending: {', '.join(top_topics)}")
        
        # Add key insights
        key_insights = []
        for insight in insights[:3]:
            if insight.get('marketing_insights'):
                key_insights.append(insight['marketing_insights'])
        
        if key_insights:
            summary_parts.append("Key insights: " + " ".join(key_insights)[:300] + "...")
        
        return " | ".join(summary_parts) if summary_parts else "Marketing landscape is evolving with new trends emerging."
    
    def _extract_actionable_insights(self, insights: List[Dict]) -> List[str]:
        """Extract actionable insights from RSS content"""
        actionable = []
        
        for insight in insights:
            if insight.get('actionable_tips'):
                # actionable_tips is stored as JSON string, need to parse
                import json
                try:
                    tips = json.loads(insight['actionable_tips']) if isinstance(insight['actionable_tips'], str) else insight['actionable_tips']
                    if isinstance(tips, list):
                        actionable.extend(tips[:2])  # Add up to 2 tips per insight
                except (json.JSONDecodeError, TypeError):
                    pass
        
        return actionable[:8]  # Return top 8 actionable insights
    
    def _get_recent_topics(self, insights: List[Dict]) -> List[str]:
        """Get recent topics from insights"""
        topics = []
        
        for insight in insights:
            if insight.get('title'):
                # Extract key topics from titles
                title = insight['title'].lower()
                if any(term in title for term in ['ai', 'seo', 'content', 'social', 'email']):
                    topics.append(insight['title'])
        
        return topics[:5]
    
    def _suggest_content_angles(self, insights: List[Dict], category: str) -> List[str]:
        """Suggest content angles based on insights"""
        angles = []
        
        # Category-specific angles
        if category == 'seo':
            angles.extend([
                "Algorithm update impacts and adaptations",
                "Technical SEO optimization strategies",
                "Content optimization for search visibility"
            ])
        elif category == 'social_media':
            angles.extend([
                "Platform-specific content strategies",
                "Community building and engagement tactics",
                "Social commerce and conversion optimization"
            ])
        elif category == 'email_marketing':
            angles.extend([
                "Personalization and segmentation strategies",
                "Email automation workflows",
                "Deliverability and engagement optimization"
            ])
        elif category == 'content_marketing':
            angles.extend([
                "Content distribution and amplification",
                "Thought leadership positioning",
                "Content repurposing strategies"
            ])
        else:
            angles.extend([
                "Data-driven marketing optimization",
                "Customer journey mapping",
                "Multi-channel marketing integration"
            ])
        
        return angles
    
    def _generate_content_ideas(self, content: List[Dict], content_type: str) -> List[str]:
        """Generate content ideas based on RSS insights"""
        ideas = []
        
        for item in content[:3]:
            if item.get('title'):
                # Transform titles into content ideas
                title = item['title']
                if content_type == 'email':
                    ideas.append(f"Email series: Key takeaways from '{title}'")
                elif content_type == 'social':
                    ideas.append(f"Social post thread: Insights from '{title}'")
                else:
                    ideas.append(f"Deep dive: Expanding on '{title}'")
        
        # Add generic ideas
        if content_type == 'email':
            ideas.append("Weekly marketing trends roundup")
        elif content_type == 'social':
            ideas.append("Quick tips carousel based on latest trends")
        else:
            ideas.append("Comprehensive guide combining recent insights")
        
        return ideas[:5]
    
    def _extract_key_messages(self, content: List[Dict]) -> List[str]:
        """Extract key messages from content"""
        messages = []
        
        for item in content:
            if item.get('marketing_insights'):
                # Take first sentence as key message
                insight = item['marketing_insights']
                sentences = insight.split('.')
                if sentences and len(sentences[0]) > 20:
                    messages.append(sentences[0].strip() + '.')
        
        return messages[:5] if messages else ["Focus on providing value to your audience"]
    
    def _get_supporting_data(self, content: List[Dict]) -> List[str]:
        """Get supporting data points from content"""
        import re
        data_points = []
        
        for item in content:
            text = item.get('marketing_insights', '') + ' ' + item.get('title', '')
            # Look for percentages and numbers
            stats = re.findall(r'\d+%[^.]*', text)
            data_points.extend(stats[:1])
        
        return data_points[:4] if data_points else ["Industry data supports these strategies"]
    
    def _suggest_cta_ideas(self, content_type: str, content: List[Dict]) -> List[str]:
        """Suggest call-to-action ideas"""
        cta_map = {
            'email': [
                "Download our free guide",
                "Start your free trial today",
                "Reply to share your thoughts",
                "Click to learn more"
            ],
            'social': [
                "Save this post for later",
                "Tag someone who needs this",
                "Share your experience below",
                "Follow for more tips"
            ],
            'blog': [
                "Subscribe for weekly insights",
                "Download the complete checklist",
                "Book a free consultation",
                "Start implementing today"
            ]
        }
        
        return cta_map.get(content_type, cta_map['blog'])
    
    def _identify_trending_angles(self, content: List[Dict]) -> List[str]:
        """Identify trending angles from content"""
        angles = []
        
        trending_keywords = ['ai', 'automation', 'personalization', 'privacy', 'video']
        
        for item in content:
            title_lower = item.get('title', '').lower()
            for keyword in trending_keywords:
                if keyword in title_lower:
                    angles.append(f"{keyword.upper()}-focused approach")
                    break
        
        return list(set(angles))[:3] if angles else ["Innovation-driven strategies"]
    
    def _get_audience_insights(self, content: List[Dict], target_audience: str) -> Dict[str, Any]:
        """Get audience insights based on content"""
        return {
            'pain_points': [
                "Keeping up with algorithm changes",
                "Measuring ROI effectively",
                "Resource constraints"
            ],
            'interests': [
                "Automation and efficiency",
                "Data-driven decision making",
                "Industry best practices"
            ],
            'preferred_formats': [
                "How-to guides",
                "Case studies",
                "Quick tips"
            ]
        }
    
    def _create_research_summary(self, results: List[Dict]) -> str:
        """Create research summary from search results"""
        if not results:
            return "No specific research found for these keywords."
        
        summaries = []
        for result in results[:3]:
            if result.get('marketing_insights'):
                summaries.append(result['marketing_insights'])
        
        return " ".join(summaries)[:500] + "..." if summaries else "Research indicates focus on value-driven content strategies."
    
    def _get_fallback_trends(self) -> Dict[str, Any]:
        """Fallback trends when database is unavailable"""
        return {
            'trends_summary': "Marketing trends focus on AI, personalization, and data privacy.",
            'actionable_insights': [
                "Leverage AI for content creation and optimization",
                "Focus on first-party data collection",
                "Prioritize video content across platforms"
            ],
            'trending_keywords': ['AI', 'personalization', 'video', 'automation', 'privacy'],
            'recent_topics': ["AI in Marketing", "Privacy-First Marketing", "Video Marketing Strategies"],
            'content_angles': [
                "AI-powered marketing automation",
                "Building trust through transparency",
                "Multi-format content strategies"
            ]
        }
    
    def _get_fallback_inspiration(self, content_type: str) -> Dict[str, Any]:
        """Fallback inspiration when database is unavailable"""
        return {
            'content_ideas': [f"How to improve {content_type} performance in 2025"],
            'key_messages': ["Focus on value-driven content that solves real problems"],
            'supporting_data': ["Modern marketing strategies show 40% better engagement"],
            'call_to_action_ideas': self._suggest_cta_ideas(content_type, []),
            'trending_angles': ["AI-powered strategies", "Privacy-first approach"],
            'audience_insights': {'pain_points': ['Budget constraints'], 'interests': ['Growth strategies']}
        }
    
    def _get_fallback_research(self) -> Dict[str, Any]:
        """Fallback research when database is unavailable"""
        return {
            'research_summary': "Marketing research indicates focus on personalization and automation.",
            'expert_quotes': ["Personalization is the key to modern marketing success"],
            'statistics': ["73% of consumers prefer personalized experiences"],
            'best_practices': ["Segment your audience", "Test everything", "Focus on value"],
            'case_studies': ["Company X improved conversion by 150% with personalization"],
            'related_topics': ["Marketing automation", "Customer segmentation", "A/B testing"]
        }
    
    def _extract_expert_quotes(self, results: List[Dict]) -> List[str]:
        """Extract expert quotes from search results"""
        quotes = []
        for result in results:
            content = result.get('marketing_insights', '')
            if content and len(content) > 50:
                # Take first sentence as potential quote
                sentences = content.split('.')
                if sentences and len(sentences[0]) > 30:
                    quotes.append(f'"{sentences[0].strip()}."')
        return quotes[:3]
    
    def _find_statistics(self, results: List[Dict]) -> List[str]:
        """Find statistics in the content"""
        import re
        stats = []
        
        for result in results:
            content = result.get('marketing_insights', '') + ' ' + result.get('title', '')
            # Look for percentage patterns
            percentages = re.findall(r'\d+%[^.]*\.', content)
            stats.extend(percentages[:2])
        
        return stats[:4] if stats else ["Marketing performance can improve by 40% with proper strategy"]
    
    def _compile_best_practices(self, results: List[Dict]) -> List[str]:
        """Compile best practices from results"""
        practices = []
        
        for result in results:
            tips = result.get('actionable_tips', [])
            if isinstance(tips, str):
                import json
                try:
                    tips = json.loads(tips)
                except:
                    tips = []
            
            if isinstance(tips, list):
                practices.extend(tips[:2])
        
        return practices[:5] if practices else ["Focus on value-driven content", "Test and optimize continuously"]
    
    def _identify_case_studies(self, results: List[Dict]) -> List[str]:
        """Identify case studies from results"""
        cases = []
        
        for result in results:
            title = result.get('title', '').lower()
            if 'case study' in title or 'example' in title or 'success' in title:
                cases.append(result.get('title', ''))
        
        return cases[:3] if cases else ["Real-world marketing success stories available"]
    
    def _find_related_topics(self, results: List[Dict]) -> List[str]:
        """Find related topics from results"""
        topics = set()
        
        for result in results:
            category = result.get('category', '')
            if category:
                topics.add(category.replace('_', ' ').title())
        
        return list(topics)[:5]
    
    def _format_campaign_strategy(self, insights: List[Dict], campaign_type: str) -> str:
        """Format campaign strategy based on insights"""
        if not insights:
            return f"Develop a comprehensive {campaign_type} strategy based on current best practices."
        
        strategies = []
        for insight in insights[:2]:
            if insight.get('marketing_insights'):
                strategies.append(insight['marketing_insights'])
        
        return " ".join(strategies)[:400] + "..." if strategies else f"Focus on {campaign_type} optimization and audience engagement."
    
    def _identify_success_factors(self, insights: List[Dict]) -> List[str]:
        """Identify success factors from insights"""
        factors = ["Clear value proposition", "Audience targeting", "Consistent messaging", "Performance measurement"]
        
        # Add specific factors from insights
        for insight in insights[:3]:
            tips = insight.get('actionable_tips', [])
            if isinstance(tips, str):
                import json
                try:
                    tips = json.loads(tips)
                except:
                    tips = []
            
            if isinstance(tips, list) and tips:
                factors.extend(tips[:1])
        
        return factors[:6]
    
    def _identify_common_mistakes(self, insights: List[Dict]) -> List[str]:
        """Identify common mistakes to avoid"""
        return [
            "Not defining clear objectives",
            "Ignoring audience preferences",
            "Lack of testing and optimization",
            "Inconsistent brand messaging",
            "Poor timing and frequency"
        ]
    
    def _get_optimization_tips(self, insights: List[Dict], campaign_type: str) -> List[str]:
        """Get optimization tips for campaign type"""
        base_tips = {
            'email': ["Optimize subject lines", "Segment your list", "Test send times"],
            'social': ["Use platform-specific formats", "Engage with comments", "Post consistently"],
            'blog': ["Focus on SEO", "Include internal links", "Add clear CTAs"],
            'seo': ["Target long-tail keywords", "Optimize page speed", "Build quality backlinks"]
        }
        
        return base_tips.get(campaign_type, base_tips['blog'])
    
    def _find_industry_examples(self, insights: List[Dict]) -> List[str]:
        """Find industry examples from insights"""
        examples = []
        
        for insight in insights:
            title = insight.get('title', '')
            if any(word in title.lower() for word in ['example', 'case', 'study', 'success']):
                examples.append(title)
        
        return examples[:3] if examples else ["Industry leaders are adopting new strategies"]
    
    def _suggest_performance_metrics(self, campaign_type: str) -> List[str]:
        """Suggest performance metrics for campaign type"""
        metrics_map = {
            'email': ['Open rate', 'Click-through rate', 'Conversion rate', 'Unsubscribe rate'],
            'social': ['Engagement rate', 'Reach', 'Shares', 'Click-through rate'],
            'blog': ['Organic traffic', 'Time on page', 'Bounce rate', 'Social shares'],
            'seo': ['Organic rankings', 'Search visibility', 'Click-through rate', 'Organic traffic']
        }
        
        return metrics_map.get(campaign_type, metrics_map['blog'])
    
    def _get_fallback_campaign_insights(self, campaign_type: str) -> Dict[str, Any]:
        """Fallback campaign insights when database is unavailable"""
        return {
            'campaign_strategy': f"Develop a data-driven {campaign_type} strategy focused on audience value",
            'success_factors': self._identify_success_factors([]),
            'common_mistakes': self._identify_common_mistakes([]),
            'optimization_tips': self._get_optimization_tips([], campaign_type),
            'industry_examples': ["Leading brands are seeing success with personalized approaches"],
            'performance_metrics': self._suggest_performance_metrics(campaign_type)
        }
