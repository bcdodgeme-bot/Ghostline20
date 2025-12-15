#!/usr/bin/env python3
"""
RSS Cross-Reference for Google Trends Integration
Correlates trending keywords with RSS marketing insights for strategic intelligence

Key Features:
- Cross-references trend opportunities with RSS feed content
- Identifies when trending topics align with industry discussions
- Provides strategic timing insights for content creation
- Amplifies trend opportunities with industry context
- Detects market sentiment alignment
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, date, timezone
import re
import logging
from dataclasses import dataclass
from collections import defaultdict

from ...core.database import db_manager

logger = logging.getLogger(__name__)

@dataclass
class TrendRSSCorrelation:
    """Container for trend-RSS correlation analysis"""
    keyword: str
    business_area: str
    trend_score: int
    
    # RSS correlation data
    related_rss_entries: List[Dict[str, Any]]
    correlation_strength: float  # 0.0 to 1.0
    sentiment_alignment: str     # 'positive', 'negative', 'neutral', 'mixed'
    
    # Strategic insights
    market_timing: str          # 'early', 'peak', 'late', 'contrarian'
    competitive_advantage: float # 0.0 to 1.0
    content_amplification: float # 0.0 to 1.0
    
    # Recommendations
    strategic_recommendation: str
    optimal_content_angle: str
    timing_advantage: bool


# Singleton instance
_rss_cross_reference_instance: Optional['RSSCrossReference'] = None


def get_rss_cross_reference() -> 'RSSCrossReference':
    """Get singleton RSSCrossReference instance"""
    global _rss_cross_reference_instance
    if _rss_cross_reference_instance is None:
        _rss_cross_reference_instance = RSSCrossReference()
    return _rss_cross_reference_instance


class RSSCrossReference:
    """Cross-references Google Trends with RSS marketing insights"""
    
    def __init__(self):
        # Correlation scoring weights
        self.scoring_weights = {
            'exact_keyword_match': 1.0,
            'partial_keyword_match': 0.7,
            'semantic_similarity': 0.5,
            'business_context_match': 0.6,
            'recency_boost': 0.3
        }
        
        # Business area RSS relevance
        self.business_rss_relevance = {
            'amcf': ['nonprofit', 'charity', 'donation', 'fundraising', 'philanthropy'],
            'bcdodge': ['marketing', 'automotive', 'dealership', 'digital marketing'],
            'damnitcarl': ['pets', 'content creation', 'social media', 'emotional support'],
            'mealsnfeelz': ['food', 'nutrition', 'hunger relief', 'community'],
            'roseandangel': ['consulting', 'small business', 'marketing strategy'],
            'tvsignals': ['entertainment', 'streaming', 'television', 'media']
        }
        
        # Sentiment keywords for analysis
        self.sentiment_keywords = {
            'positive': [
                'growth', 'success', 'increase', 'popular', 'trending', 'rising',
                'opportunity', 'breakthrough', 'innovative', 'effective', 'boost'
            ],
            'negative': [
                'decline', 'decrease', 'falling', 'crisis', 'problem', 'challenge',
                'controversy', 'scandal', 'failure', 'drop', 'concern'
            ],
            'neutral': [
                'analysis', 'report', 'study', 'research', 'data', 'statistics',
                'overview', 'summary', 'update', 'news', 'information'
            ]
        }
    
    def _make_timezone_aware(self, dt: datetime) -> datetime:
        """Make a datetime timezone-aware if it isn't already"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    # ============================================================================
    # TREND-RSS CORRELATION ANALYSIS
    # ============================================================================
    
    async def correlate_trends_with_rss(self, hours_lookback: int = 72) -> List[TrendRSSCorrelation]:
        """Find correlations between trending keywords and RSS content"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
            
            # Get recent trending keywords
            trending_keywords = await conn.fetch('''
                SELECT DISTINCT ON (keyword, business_area)
                       keyword, business_area, trend_score, created_at
                FROM trend_monitoring 
                WHERE created_at >= $1 
                AND trend_score >= 15  -- Low threshold for correlation analysis
                ORDER BY keyword, business_area, created_at DESC
            ''', cutoff_time)
            
            # Release connection before calling other async methods
            await db_manager.release_connection(conn)
            conn = None
            
            correlations = []
            
            for trend_row in trending_keywords:
                correlation = await self._analyze_keyword_rss_correlation(
                    keyword=trend_row['keyword'],
                    business_area=trend_row['business_area'],
                    trend_score=trend_row['trend_score'],
                    hours_lookback=hours_lookback
                )
                
                if correlation and correlation.correlation_strength >= 0.3:
                    correlations.append(correlation)
            
            # Sort by correlation strength and strategic value
            correlations.sort(key=lambda x: (
                x.correlation_strength * x.content_amplification
            ), reverse=True)
            
            return correlations
            
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _analyze_keyword_rss_correlation(self, keyword: str, business_area: str,
                                             trend_score: int, hours_lookback: int) -> Optional[TrendRSSCorrelation]:
        """Analyze correlation between a specific keyword and RSS content"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
            
            # Get relevant RSS entries
            related_entries = await self._find_related_rss_entries(
                conn, keyword, business_area, cutoff_time
            )
            
            if not related_entries:
                return None
            
            # Calculate correlation strength
            correlation_strength = self._calculate_correlation_strength(
                keyword, related_entries
            )
            
            if correlation_strength < 0.3:
                return None
            
            # Analyze sentiment alignment
            sentiment_alignment = self._analyze_sentiment_alignment(related_entries)
            
            # Determine market timing
            market_timing = self._determine_market_timing(
                keyword, trend_score, related_entries
            )
            
            # Calculate strategic metrics
            competitive_advantage = self._calculate_competitive_advantage(
                keyword, business_area, related_entries
            )
            
            content_amplification = self._calculate_content_amplification(
                correlation_strength, sentiment_alignment, len(related_entries)
            )
            
            # Generate strategic insights
            strategic_recommendation = self._generate_strategic_recommendation(
                keyword, market_timing, sentiment_alignment, competitive_advantage
            )
            
            optimal_content_angle = self._suggest_content_angle(
                keyword, business_area, related_entries, sentiment_alignment
            )
            
            timing_advantage = self._assess_timing_advantage(
                market_timing, sentiment_alignment, trend_score
            )
            
            return TrendRSSCorrelation(
                keyword=keyword,
                business_area=business_area,
                trend_score=trend_score,
                related_rss_entries=[dict(entry) for entry in related_entries],
                correlation_strength=correlation_strength,
                sentiment_alignment=sentiment_alignment,
                market_timing=market_timing,
                competitive_advantage=competitive_advantage,
                content_amplification=content_amplification,
                strategic_recommendation=strategic_recommendation,
                optimal_content_angle=optimal_content_angle,
                timing_advantage=timing_advantage
            )
            
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _find_related_rss_entries(self, conn: Any, keyword: str,
                                      business_area: str, cutoff_time: datetime) -> List[Dict[str, Any]]:
        """Find RSS entries related to the trending keyword"""
        
        keyword_lower = keyword.lower()
        keyword_words = set(re.findall(r'\b\w+\b', keyword_lower))
        
        # Get business-relevant RSS categories
        business_relevance = self.business_rss_relevance.get(business_area, [])
        
        # Build search query for RSS content
        # Search in title, description, full_content, and marketing_insights
        search_conditions = []
        params = [cutoff_time]
        
        # Exact keyword match (highest priority)
        search_conditions.append("(LOWER(title) LIKE $2 OR LOWER(description) LIKE $2 OR LOWER(full_content) LIKE $2)")
        params.append(f'%{keyword_lower}%')
        
        # Individual word matches
        for i, word in enumerate(keyword_words):
            if len(word) >= 3:  # Skip very short words
                param_num = len(params) + 1
                search_conditions.append(f"(LOWER(title) LIKE ${param_num} OR LOWER(description) LIKE ${param_num})")
                params.append(f'%{word}%')
        
        # Business relevance terms
        for term in business_relevance:
            param_num = len(params) + 1
            search_conditions.append(f"(LOWER(category) LIKE ${param_num} OR LOWER(tags::text) LIKE ${param_num})")
            params.append(f'%{term}%')
        
        if not search_conditions:
            return []
        
        query = f'''
            SELECT title, description, full_content, category, tags, 
                   marketing_insights, sentiment_score, pub_date, created_at
            FROM rss_feed_entries 
            WHERE created_at >= $1 
            AND ({' OR '.join(search_conditions)})
            ORDER BY created_at DESC
            LIMIT 20
        '''
        
        try:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error finding related RSS entries: {e}")
            return []
    
    def _calculate_correlation_strength(self, keyword: str, rss_entries: List[Dict[str, Any]]) -> float:
        """Calculate correlation strength between keyword and RSS entries"""
        if not rss_entries:
            return 0.0
        
        keyword_lower = keyword.lower()
        keyword_words = set(re.findall(r'\b\w+\b', keyword_lower))
        
        total_score = 0.0
        now = datetime.now(timezone.utc)
        
        for entry in rss_entries:
            entry_score = 0.0
            
            # Check for exact keyword matches
            text_fields = [
                entry.get('title', ''),
                entry.get('description', ''),
                entry.get('full_content', '')[:500]  # First 500 chars only
            ]
            
            combined_text = ' '.join(text_fields).lower()
            
            # Exact keyword match
            if keyword_lower in combined_text:
                entry_score += self.scoring_weights['exact_keyword_match']
            
            # Partial word matches
            words_matched = sum(1 for word in keyword_words if word in combined_text)
            if words_matched > 0:
                match_ratio = words_matched / len(keyword_words)
                entry_score += match_ratio * self.scoring_weights['partial_keyword_match']
            
            # Recency boost (more recent entries get higher scores)
            if entry.get('created_at'):
                # Make both datetimes timezone-aware for comparison
                entry_created_at = self._make_timezone_aware(entry['created_at'])
                hours_old = (now - entry_created_at).total_seconds() / 3600
                
                if hours_old <= 24:
                    entry_score += self.scoring_weights['recency_boost']
                elif hours_old <= 48:
                    entry_score += self.scoring_weights['recency_boost'] * 0.5
            
            total_score += entry_score
        
        # Normalize by number of entries and maximum possible score
        max_possible_score = len(rss_entries) * (
            self.scoring_weights['exact_keyword_match'] +
            self.scoring_weights['partial_keyword_match'] +
            self.scoring_weights['recency_boost']
        )
        
        correlation_strength = total_score / max_possible_score if max_possible_score > 0 else 0.0
        
        return min(1.0, correlation_strength)
    
    def _analyze_sentiment_alignment(self, rss_entries: List[Dict[str, Any]]) -> str:
        """Analyze overall sentiment from RSS entries"""
        if not rss_entries:
            return 'neutral'
        
        sentiment_scores = {'positive': 0, 'negative': 0, 'neutral': 0}
        
        for entry in rss_entries:
            # Use stored sentiment score if available
            stored_sentiment = entry.get('sentiment_score')
            if stored_sentiment is not None:
                if stored_sentiment > 0.1:
                    sentiment_scores['positive'] += abs(stored_sentiment)
                elif stored_sentiment < -0.1:
                    sentiment_scores['negative'] += abs(stored_sentiment)
                else:
                    sentiment_scores['neutral'] += 1
                continue
            
            # Fallback to keyword-based sentiment analysis
            text_content = ' '.join([
                entry.get('title', ''),
                entry.get('description', ''),
                entry.get('marketing_insights', '')
            ]).lower()
            
            for sentiment, keywords in self.sentiment_keywords.items():
                matches = sum(1 for keyword in keywords if keyword in text_content)
                sentiment_scores[sentiment] += matches
        
        # Determine dominant sentiment
        if not any(sentiment_scores.values()):
            return 'neutral'
        
        dominant_sentiment = max(sentiment_scores.items(), key=lambda x: x[1])[0]
        
        # Check for mixed sentiment
        total_sentiment = sum(sentiment_scores.values())
        if total_sentiment > 0:
            dominant_ratio = sentiment_scores[dominant_sentiment] / total_sentiment
            if dominant_ratio < 0.6:  # No clear dominant sentiment
                return 'mixed'
        
        return dominant_sentiment
    
    def _determine_market_timing(self, keyword: str, trend_score: int,
                               rss_entries: List[Dict[str, Any]]) -> str:
        """Determine market timing based on trend score and RSS discussion"""
        
        now = datetime.now(timezone.utc)
        
        # Check RSS entry recency and frequency
        recent_entries = 0
        for entry in rss_entries:
            if entry.get('created_at'):
                entry_created_at = self._make_timezone_aware(entry['created_at'])
                if (now - entry_created_at).total_seconds() <= 86400:  # 24 hours
                    recent_entries += 1
        
        total_entries = len(rss_entries)
        
        # Market timing logic
        if trend_score >= 60 and recent_entries >= 2:
            return 'peak'  # High trend score with recent RSS discussion
        elif trend_score >= 30 and recent_entries <= 1:
            return 'early'  # Moderate trend score but little RSS discussion yet
        elif trend_score <= 20 and total_entries >= 3:
            return 'late'   # Low trend score but lots of RSS discussion
        elif trend_score <= 30 and total_entries <= 1:
            return 'contrarian'  # Low trend score and little discussion - contrarian opportunity
        else:
            return 'peak'  # Default to peak timing
    
    def _calculate_competitive_advantage(self, keyword: str, business_area: str,
                                       rss_entries: List[Dict[str, Any]]) -> float:
        """Calculate potential competitive advantage"""
        
        # Base advantage from business relevance
        keyword_lower = keyword.lower()
        business_terms = self.business_rss_relevance.get(business_area, [])
        
        business_relevance = sum(1 for term in business_terms if term in keyword_lower)
        base_advantage = min(0.5, business_relevance * 0.2)
        
        # RSS discussion frequency (less discussion = more advantage)
        discussion_penalty = min(0.3, len(rss_entries) * 0.05)
        
        # Recency advantage (being early to trend)
        now = datetime.now(timezone.utc)
        recent_entries = 0
        for entry in rss_entries:
            if entry.get('created_at'):
                entry_created_at = self._make_timezone_aware(entry['created_at'])
                if (now - entry_created_at).total_seconds() <= 86400:  # 24 hours
                    recent_entries += 1
        
        recency_advantage = 0.4 if recent_entries <= 1 else 0.2 if recent_entries <= 2 else 0.0
        
        total_advantage = base_advantage + recency_advantage - discussion_penalty
        
        return max(0.0, min(1.0, total_advantage))
    
    def _calculate_content_amplification(self, correlation_strength: float,
                                       sentiment_alignment: str, entry_count: int) -> float:
        """Calculate content amplification potential"""
        
        # Base amplification from correlation strength
        base_amplification = correlation_strength
        
        # Sentiment multiplier
        sentiment_multipliers = {
            'positive': 1.2,
            'neutral': 1.0,
            'mixed': 0.9,
            'negative': 0.8
        }
        
        sentiment_multiplier = sentiment_multipliers.get(sentiment_alignment, 1.0)
        
        # Entry count boost (more RSS discussion = more amplification potential)
        entry_boost = min(0.3, entry_count * 0.05)
        
        amplification = (base_amplification * sentiment_multiplier) + entry_boost
        
        return min(1.0, amplification)
    
    def _generate_strategic_recommendation(self, keyword: str, market_timing: str,
                                         sentiment_alignment: str, competitive_advantage: float) -> str:
        """Generate strategic recommendation"""
        
        recommendations = {
            ('early', 'positive'): "Create content immediately to capitalize on emerging positive trend",
            ('early', 'neutral'): "Develop thought leadership content to shape the narrative",
            ('early', 'negative'): "Consider contrarian content or wait for sentiment shift",
            ('peak', 'positive'): "Create high-volume content to ride the wave",
            ('peak', 'neutral'): "Focus on differentiated angles and unique perspectives",
            ('peak', 'negative'): "Address concerns or provide solutions-focused content",
            ('late', 'positive'): "Create evergreen content or find new angles",
            ('late', 'neutral'): "Focus on comprehensive guides and expert analysis",
            ('late', 'negative'): "Opportunity for corrective or alternative perspectives",
            ('contrarian', 'positive'): "Investigate why trend is low despite positive sentiment",
            ('contrarian', 'neutral'): "Consider early investment in emerging topic",
            ('contrarian', 'negative'): "Avoid or wait for sentiment improvement"
        }
        
        key = (market_timing, sentiment_alignment)
        base_recommendation = recommendations.get(key, "Monitor trend development")
        
        # Add competitive advantage context
        if competitive_advantage >= 0.7:
            return f"{base_recommendation}. High competitive advantage - prioritize this opportunity."
        elif competitive_advantage >= 0.4:
            return f"{base_recommendation}. Moderate competitive advantage."
        else:
            return f"{base_recommendation}. Consider competitive landscape carefully."
    
    def _suggest_content_angle(self, keyword: str, business_area: str,
                             rss_entries: List[Dict[str, Any]], sentiment: str) -> str:
        """Suggest optimal content angle based on RSS insights"""
        
        # Extract common themes from RSS entries
        themes = defaultdict(int)
        for entry in rss_entries:
            title = entry.get('title', '').lower()
            description = entry.get('description', '').lower()
            
            # Look for common content angle keywords
            angle_keywords = [
                'how to', 'guide', 'tips', 'best practices', 'strategy',
                'analysis', 'review', 'comparison', 'trends', 'forecast',
                'case study', 'example', 'success', 'failure', 'lessons'
            ]
            
            for angle in angle_keywords:
                if angle in title or angle in description:
                    themes[angle] += 1
        
        # Business-specific angle suggestions
        business_angles = {
            'amcf': 'donation impact analysis',
            'bcdodge': 'marketing strategy deep-dive',
            'damnitcarl': 'emotional support guide',
            'mealsnfeelz': 'community impact story',
            'roseandangel': 'small business case study',
            'tvsignals': 'viewing recommendation guide'
        }
        
        # Choose angle based on themes and business area
        if themes:
            popular_theme = max(themes.items(), key=lambda x: x[1])[0]
            return f"{popular_theme.title()} focused on {keyword}"
        else:
            default_angle = business_angles.get(business_area, 'comprehensive guide')
            return f"{default_angle.title()} about {keyword}"
    
    def _assess_timing_advantage(self, market_timing: str, sentiment: str, trend_score: int) -> bool:
        """Assess if there's a timing advantage"""
        
        # Timing advantage conditions
        advantage_conditions = [
            market_timing == 'early' and sentiment in ['positive', 'neutral'],
            market_timing == 'peak' and sentiment == 'positive' and trend_score >= 50,
            market_timing == 'contrarian' and sentiment != 'negative'
        ]
        
        return any(advantage_conditions)
    
    # ============================================================================
    # STRATEGIC INTELLIGENCE REPORTING
    # ============================================================================
    
    async def generate_strategic_intelligence_report(self, business_area: Optional[str] = None,
                                                   hours_lookback: int = 72) -> Dict[str, Any]:
        """Generate comprehensive strategic intelligence report"""
        
        correlations = await self.correlate_trends_with_rss(hours_lookback)
        
        # Filter by business area if specified
        if business_area:
            correlations = [c for c in correlations if c.business_area == business_area]
        
        if not correlations:
            return {
                'business_area': business_area or 'all',
                'analysis_period_hours': hours_lookback,
                'correlations_found': 0,
                'high_correlation_opportunities': 0,
                'timing_advantage_opportunities': 0,
                'high_amplification_opportunities': 0,
                'business_breakdown': {},
                'sentiment_distribution': {},
                'timing_distribution': {},
                'top_opportunities': [],
                'strategic_insights': {'message': 'No trend-RSS correlations found'}
            }
        
        # Analyze correlations
        high_correlation = [c for c in correlations if c.correlation_strength >= 0.7]
        timing_advantages = [c for c in correlations if c.timing_advantage]
        high_amplification = [c for c in correlations if c.content_amplification >= 0.7]
        
        # Business area breakdown
        business_breakdown = defaultdict(list)
        for corr in correlations:
            business_breakdown[corr.business_area].append(corr)
        
        # Sentiment analysis
        sentiment_distribution = defaultdict(int)
        for corr in correlations:
            sentiment_distribution[corr.sentiment_alignment] += 1
        
        # Market timing analysis
        timing_distribution = defaultdict(int)
        for corr in correlations:
            timing_distribution[corr.market_timing] += 1
        
        return {
            'business_area': business_area or 'all',
            'analysis_period_hours': hours_lookback,
            'correlations_found': len(correlations),
            'high_correlation_opportunities': len(high_correlation),
            'timing_advantage_opportunities': len(timing_advantages),
            'high_amplification_opportunities': len(high_amplification),
            'business_breakdown': {
                area: len(corrs) for area, corrs in business_breakdown.items()
            },
            'sentiment_distribution': dict(sentiment_distribution),
            'timing_distribution': dict(timing_distribution),
            'top_opportunities': [
                {
                    'keyword': c.keyword,
                    'business_area': c.business_area,
                    'correlation_strength': c.correlation_strength,
                    'market_timing': c.market_timing,
                    'sentiment_alignment': c.sentiment_alignment,
                    'strategic_recommendation': c.strategic_recommendation,
                    'content_angle': c.optimal_content_angle,
                    'timing_advantage': c.timing_advantage
                }
                for c in correlations[:10]
            ]
        }


# ============================================================================
# TESTING AND UTILITIES
# ============================================================================

async def test_rss_cross_reference():
    """Test the RSS cross-reference functionality"""
    cross_ref = get_rss_cross_reference()
    
    print("🧪 TESTING RSS CROSS-REFERENCE")
    print("=" * 40)
    
    # Test trend-RSS correlations
    print("\n🔗 Finding trend-RSS correlations...")
    correlations = await cross_ref.correlate_trends_with_rss(hours_lookback=168)  # 1 week
    
    print(f"   Found {len(correlations)} correlations")
    
    if correlations:
        print(f"\n📈 Top correlations:")
        for i, corr in enumerate(correlations[:3], 1):
            print(f"   {i}. {corr.keyword} ({corr.business_area})")
            print(f"      Correlation: {corr.correlation_strength:.2f}")
            print(f"      Timing: {corr.market_timing}, Sentiment: {corr.sentiment_alignment}")
            print(f"      RSS entries: {len(corr.related_rss_entries)}")
            print(f"      Recommendation: {corr.strategic_recommendation}")
            print(f"      Content angle: {corr.optimal_content_angle}")
            print()
    
    # Test strategic intelligence report
    print(f"\n📊 Strategic intelligence report...")
    report = await cross_ref.generate_strategic_intelligence_report(hours_lookback=168)
    
    print(f"   Analysis period: {report['analysis_period_hours']} hours")
    print(f"   Correlations found: {report['correlations_found']}")
    print(f"   High correlation opportunities: {report['high_correlation_opportunities']}")
    print(f"   Timing advantage opportunities: {report['timing_advantage_opportunities']}")
    
    if report.get('business_breakdown'):
        print(f"   Business breakdown: {report['business_breakdown']}")
    
    if report.get('sentiment_distribution'):
        print(f"   Sentiment distribution: {report['sentiment_distribution']}")
    
    print("\n✅ RSS cross-reference test complete!")


if __name__ == "__main__":
    asyncio.run(test_rss_cross_reference())
