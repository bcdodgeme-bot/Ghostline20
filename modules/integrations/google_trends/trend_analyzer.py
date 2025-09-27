#!/usr/bin/env python3
"""
Trend Analyzer for Google Trends Integration
Advanced analysis of trend data with pattern detection and relevance scoring

Key Features:
- Pattern recognition across 51,474 monitored keywords
- Business relevance scoring for each trend
- Momentum analysis and volatility detection
- Cross-business trend correlation
- Content timing optimization
- Historical pattern learning
"""

import asyncio
import asyncpg
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, date
import statistics
import logging
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class TrendPattern:
    """Container for trend pattern analysis"""
    keyword: str
    business_area: str
    pattern_type: str  # 'growth', 'decline', 'spike', 'seasonal', 'stable'
    confidence: float  # 0.0 to 1.0
    strength: float    # Pattern strength
    duration_days: int
    peak_score: int
    volatility: float
    business_relevance: float
    content_opportunity: float

@dataclass
class BusinessTrendCorrelation:
    """Cross-business trend correlation analysis"""
    primary_keyword: str
    primary_business: str
    correlated_keywords: List[Tuple[str, str, float]]  # keyword, business, correlation
    correlation_strength: float
    shared_momentum: str

class TrendAnalyzer:
    """Advanced trend analysis and pattern detection"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        
        # Analysis configuration
        self.min_data_points = 3  # Minimum data points for pattern analysis
        self.volatility_threshold = 25  # High volatility if score range > 25
        self.correlation_threshold = 0.7  # Strong correlation threshold
        
        # Business context scoring weights
        self.business_context_weights = {
            'amcf': {
                'charity': 0.9, 'donation': 0.9, 'nonprofit': 0.8, 'zakat': 0.9,
                'islamic': 0.8, 'giving': 0.8, 'fundraising': 0.7
            },
            'bcdodge': {
                'marketing': 0.9, 'digital': 0.8, 'strategy': 0.8, 'campaign': 0.7,
                'advertising': 0.7, 'brand': 0.7, 'growth': 0.6
            },
            'damnitcarl': {
                'cat': 0.9, 'emotional': 0.8, 'support': 0.8, 'pet': 0.7,
                'feline': 0.8, 'tuxedo': 0.6, 'therapy': 0.7
            },
            'mealsnfeelz': {
                'food': 0.9, 'pantry': 0.9, 'meal': 0.8, 'ramadan': 0.8,
                'fidya': 0.8, 'hunger': 0.7, 'donation': 0.8
            },
            'roseandangel': {
                'marketing': 0.9, 'consultant': 0.9, 'business': 0.8, 'strategy': 0.7,
                'nonprofit': 0.6, 'small business': 0.8, 'expert': 0.7
            },
            'tvsignals': {
                'tv': 0.9, 'streaming': 0.9, 'show': 0.8, 'series': 0.8,
                'netflix': 0.7, 'binge': 0.7, 'watch': 0.8
            }
        }
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    # ============================================================================
    # TREND PATTERN ANALYSIS
    # ============================================================================
    
    async def analyze_keyword_pattern(self, keyword: str, business_area: str,
                                    days: int = 14) -> Optional[TrendPattern]:
        """Analyze trend pattern for a specific keyword"""
        conn = await self.get_connection()
        
        try:
            # Get historical trend data
            query = '''
                SELECT trend_date, trend_score, trend_momentum, regional_score
                FROM trend_monitoring 
                WHERE keyword = $1 AND business_area = $2 
                AND trend_date >= $3
                AND trend_score IS NOT NULL
                ORDER BY trend_date ASC
            '''
            
            rows = await conn.fetch(
                query, keyword, business_area,
                date.today() - timedelta(days=days)
            )
            
            if len(rows) < self.min_data_points:
                return None
            
            # Extract scores and analyze patterns
            scores = [row['trend_score'] for row in rows]
            dates = [row['trend_date'] for row in rows]
            
            # Pattern detection
            pattern_type, confidence, strength = self._detect_pattern(scores)
            
            # Calculate metrics
            peak_score = max(scores)
            volatility = max(scores) - min(scores)
            duration_days = (dates[-1] - dates[0]).days if len(dates) > 1 else 0
            
            # Business relevance scoring
            business_relevance = self._calculate_business_relevance(keyword, business_area)
            
            # Content opportunity scoring
            content_opportunity = self._calculate_content_opportunity(
                pattern_type, peak_score, volatility, business_relevance
            )
            
            return TrendPattern(
                keyword=keyword,
                business_area=business_area,
                pattern_type=pattern_type,
                confidence=confidence,
                strength=strength,
                duration_days=duration_days,
                peak_score=peak_score,
                volatility=volatility,
                business_relevance=business_relevance,
                content_opportunity=content_opportunity
            )
            
        finally:
            await conn.close()
    
    def _detect_pattern(self, scores: List[int]) -> Tuple[str, float, float]:
        """Detect trend pattern from score history"""
        if len(scores) < 2:
            return 'insufficient_data', 0.0, 0.0
        
        # Calculate trend direction
        recent_avg = statistics.mean(scores[-3:]) if len(scores) >= 3 else scores[-1]
        older_avg = statistics.mean(scores[:3]) if len(scores) >= 3 else scores[0]
        
        change_percent = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
        
        # Detect spikes (sudden jumps)
        max_jump = 0
        for i in range(1, len(scores)):
            jump = scores[i] - scores[i-1]
            max_jump = max(max_jump, jump)
        
        # Pattern classification
        if max_jump >= 30:  # Large spike
            pattern_type = 'spike'
            confidence = min(0.9, max_jump / 50)
            strength = max_jump
        elif change_percent > 50:  # Strong growth
            pattern_type = 'growth'
            confidence = min(0.9, abs(change_percent) / 100)
            strength = change_percent
        elif change_percent < -50:  # Strong decline
            pattern_type = 'decline'
            confidence = min(0.9, abs(change_percent) / 100)
            strength = abs(change_percent)
        elif self._detect_seasonal_pattern(scores):
            pattern_type = 'seasonal'
            confidence = 0.6  # Seasonal patterns need more data for high confidence
            strength = statistics.stdev(scores) if len(scores) > 2 else 0
        elif max(scores) - min(scores) <= 10:  # Low volatility
            pattern_type = 'stable'
            confidence = 0.8
            strength = statistics.mean(scores)
        else:
            pattern_type = 'irregular'
            confidence = 0.4
            strength = statistics.stdev(scores) if len(scores) > 2 else 0
        
        return pattern_type, confidence, strength
    
    def _detect_seasonal_pattern(self, scores: List[int]) -> bool:
        """Detect if scores show seasonal pattern"""
        if len(scores) < 7:  # Need at least a week of data
            return False
        
        # Simple seasonal detection: look for recurring peaks/valleys
        # This is a simplified version - could be enhanced with FFT analysis
        try:
            mid_point = statistics.median(scores)
            above_median = [1 if s > mid_point else 0 for s in scores]
            
            # Look for alternating patterns
            pattern_changes = sum(1 for i in range(1, len(above_median))
                                if above_median[i] != above_median[i-1])
            
            # If we have regular changes, might be seasonal
            return pattern_changes >= len(scores) * 0.3
        except:
            return False
    
    def _calculate_business_relevance(self, keyword: str, business_area: str) -> float:
        """Calculate how relevant a keyword is to the business area"""
        keyword_lower = keyword.lower()
        context_weights = self.business_context_weights.get(business_area, {})
        
        relevance_score = 0.0
        matches = 0
        
        for context_term, weight in context_weights.items():
            if context_term in keyword_lower:
                relevance_score += weight
                matches += 1
        
        # Base relevance for any keyword in the business area
        base_relevance = 0.3
        
        if matches == 0:
            return base_relevance
        
        # Average the matched terms and add base relevance
        avg_relevance = relevance_score / matches
        final_relevance = min(1.0, base_relevance + (avg_relevance * 0.7))
        
        return round(final_relevance, 3)
    
    def _calculate_content_opportunity(self, pattern_type: str, peak_score: int,
                                     volatility: float, business_relevance: float) -> float:
        """Calculate content creation opportunity score"""
        base_score = 0.0
        
        # Pattern type scoring
        pattern_scores = {
            'spike': 0.9,     # High opportunity for trending content
            'growth': 0.8,    # Good opportunity for growing trends
            'stable': 0.4,    # Moderate opportunity for established topics
            'decline': 0.2,   # Low opportunity for declining trends
            'seasonal': 0.6,  # Good opportunity if timed right
            'irregular': 0.3  # Unpredictable opportunity
        }
        
        base_score = pattern_scores.get(pattern_type, 0.3)
        
        # Peak score multiplier (higher scores = more interest)
        score_multiplier = min(1.5, 1.0 + (peak_score / 100))
        
        # Volatility factor (some volatility is good, too much is risky)
        if volatility < 10:
            volatility_factor = 0.8  # Too stable might be boring
        elif volatility < 30:
            volatility_factor = 1.2  # Good volatility
        elif volatility < 50:
            volatility_factor = 1.0  # Moderate volatility
        else:
            volatility_factor = 0.7  # Too volatile might be risky
        
        # Business relevance multiplier
        relevance_multiplier = 0.5 + (business_relevance * 1.5)
        
        # Calculate final opportunity score
        opportunity = base_score * score_multiplier * volatility_factor * relevance_multiplier
        
        return min(1.0, round(opportunity, 3))
    
    # ============================================================================
    # BUSINESS AREA ANALYSIS
    # ============================================================================
    
    async def analyze_business_area_trends(self, business_area: str,
                                         days: int = 7, limit: int = 20) -> Dict[str, Any]:
        """Comprehensive trend analysis for a business area"""
        conn = await self.get_connection()
        
        try:
            # Get top trending keywords for the business area
            cutoff_date = date.today() - timedelta(days=days)
            
            trending_keywords = await conn.fetch('''
                SELECT keyword, MAX(trend_score) as max_score, 
                       COUNT(*) as data_points, AVG(trend_score) as avg_score
                FROM trend_monitoring 
                WHERE business_area = $1 AND trend_date >= $2
                GROUP BY keyword
                HAVING COUNT(*) >= $3
                ORDER BY max_score DESC, avg_score DESC
                LIMIT $4
            ''', business_area, cutoff_date, self.min_data_points, limit)
            
            # Analyze patterns for each keyword
            patterns = []
            for row in trending_keywords:
                pattern = await self.analyze_keyword_pattern(
                    row['keyword'], business_area, days
                )
                if pattern:
                    patterns.append(pattern)
            
            # Business area statistics
            total_keywords = len(patterns)
            
            if not patterns:
                return {
                    'business_area': business_area,
                    'analysis_period_days': days,
                    'total_keywords_analyzed': 0,
                    'patterns': [],
                    'summary': {'message': 'No trend patterns found'}
                }
            
            # Pattern distribution
            pattern_counts = defaultdict(int)
            for pattern in patterns:
                pattern_counts[pattern.pattern_type] += 1
            
            # Top opportunities
            top_opportunities = sorted(
                patterns,
                key=lambda p: p.content_opportunity,
                reverse=True
            )[:5]
            
            # Average metrics
            avg_relevance = statistics.mean([p.business_relevance for p in patterns])
            avg_opportunity = statistics.mean([p.content_opportunity for p in patterns])
            avg_peak_score = statistics.mean([p.peak_score for p in patterns])
            
            return {
                'business_area': business_area,
                'analysis_period_days': days,
                'total_keywords_analyzed': total_keywords,
                'patterns': [
                    {
                        'keyword': p.keyword,
                        'pattern_type': p.pattern_type,
                        'confidence': p.confidence,
                        'peak_score': p.peak_score,
                        'business_relevance': p.business_relevance,
                        'content_opportunity': p.content_opportunity,
                        'volatility': p.volatility
                    }
                    for p in patterns
                ],
                'pattern_distribution': dict(pattern_counts),
                'top_opportunities': [
                    {
                        'keyword': p.keyword,
                        'opportunity_score': p.content_opportunity,
                        'pattern_type': p.pattern_type,
                        'peak_score': p.peak_score
                    }
                    for p in top_opportunities
                ],
                'summary': {
                    'avg_business_relevance': round(avg_relevance, 3),
                    'avg_content_opportunity': round(avg_opportunity, 3),
                    'avg_peak_score': round(avg_peak_score, 1),
                    'dominant_pattern': max(pattern_counts.items(), key=lambda x: x[1])[0] if pattern_counts else 'none'
                }
            }
            
        finally:
            await conn.close()
    
    # ============================================================================
    # CROSS-BUSINESS CORRELATION ANALYSIS
    # ============================================================================
    
    async def find_cross_business_correlations(self, days: int = 14,
                                             min_correlation: float = 0.6) -> List[BusinessTrendCorrelation]:
        """Find trending keywords that correlate across business areas"""
        conn = await self.get_connection()
        
        try:
            cutoff_date = date.today() - timedelta(days=days)
            
            # Get trend data for all business areas
            all_trends = await conn.fetch('''
                SELECT keyword, business_area, trend_date, trend_score
                FROM trend_monitoring 
                WHERE trend_date >= $1 AND trend_score IS NOT NULL
                ORDER BY keyword, business_area, trend_date
            ''', cutoff_date)
            
            # Group by keyword and business area
            keyword_trends = defaultdict(lambda: defaultdict(list))
            
            for row in all_trends:
                keyword_trends[row['keyword']][row['business_area']].append(row['trend_score'])
            
            correlations = []
            
            # Find keywords that appear in multiple business areas
            for keyword, business_data in keyword_trends.items():
                if len(business_data) < 2:  # Need at least 2 business areas
                    continue
                
                business_areas = list(business_data.keys())
                
                for i, primary_business in enumerate(business_areas):
                    primary_scores = business_data[primary_business]
                    
                    if len(primary_scores) < 3:  # Need enough data points
                        continue
                    
                    correlated_keywords = []
                    
                    for j, other_business in enumerate(business_areas):
                        if i >= j:  # Avoid duplicates
                            continue
                        
                        other_scores = business_data[other_business]
                        
                        if len(other_scores) < 3:
                            continue
                        
                        # Calculate correlation between score patterns
                        correlation = self._calculate_correlation(primary_scores, other_scores)
                        
                        if correlation >= min_correlation:
                            correlated_keywords.append((keyword, other_business, correlation))
                    
                    if correlated_keywords:
                        # Determine shared momentum
                        avg_primary = statistics.mean(primary_scores[-3:]) if len(primary_scores) >= 3 else primary_scores[-1]
                        recent_primary = statistics.mean(primary_scores[:3]) if len(primary_scores) >= 3 else primary_scores[0]
                        
                        if avg_primary > recent_primary * 1.2:
                            momentum = 'rising'
                        elif avg_primary < recent_primary * 0.8:
                            momentum = 'declining'
                        else:
                            momentum = 'stable'
                        
                        correlation_strength = max([corr for _, _, corr in correlated_keywords])
                        
                        correlations.append(BusinessTrendCorrelation(
                            primary_keyword=keyword,
                            primary_business=primary_business,
                            correlated_keywords=correlated_keywords,
                            correlation_strength=correlation_strength,
                            shared_momentum=momentum
                        ))
            
            # Sort by correlation strength
            correlations.sort(key=lambda x: x.correlation_strength, reverse=True)
            
            return correlations[:10]  # Return top 10 correlations
            
        finally:
            await conn.close()
    
    def _calculate_correlation(self, scores1: List[int], scores2: List[int]) -> float:
        """Calculate correlation between two score series"""
        try:
            # Normalize series to same length
            min_length = min(len(scores1), len(scores2))
            s1 = scores1[-min_length:]
            s2 = scores2[-min_length:]
            
            if min_length < 2:
                return 0.0
            
            # Calculate Pearson correlation coefficient
            mean1 = statistics.mean(s1)
            mean2 = statistics.mean(s2)
            
            numerator = sum((s1[i] - mean1) * (s2[i] - mean2) for i in range(min_length))
            
            sum_sq1 = sum((s1[i] - mean1) ** 2 for i in range(min_length))
            sum_sq2 = sum((s2[i] - mean2) ** 2 for i in range(min_length))
            
            denominator = (sum_sq1 * sum_sq2) ** 0.5
            
            if denominator == 0:
                return 0.0
            
            correlation = numerator / denominator
            return abs(correlation)  # Return absolute correlation
            
        except Exception:
            return 0.0
    
    # ============================================================================
    # CONTENT TIMING OPTIMIZATION
    # ============================================================================
    
    async def optimize_content_timing(self, keyword: str, business_area: str) -> Dict[str, Any]:
        """Analyze optimal timing for content creation based on trend patterns"""
        pattern = await self.analyze_keyword_pattern(keyword, business_area, days=21)
        
        if not pattern:
            return {
                'keyword': keyword,
                'business_area': business_area,
                'timing_recommendation': 'insufficient_data',
                'confidence': 0.0
            }
        
        # Timing recommendations based on pattern
        timing_recommendations = {
            'spike': {
                'timing': 'immediate',
                'window_hours': 24,
                'rationale': 'Trending spike detected - create content immediately',
                'confidence': 0.9
            },
            'growth': {
                'timing': 'within_48h',
                'window_hours': 48,
                'rationale': 'Growing trend - good opportunity for timely content',
                'confidence': 0.8
            },
            'stable': {
                'timing': 'within_week',
                'window_hours': 168,
                'rationale': 'Stable interest - evergreen content opportunity',
                'confidence': 0.6
            },
            'seasonal': {
                'timing': 'pattern_based',
                'window_hours': 72,
                'rationale': 'Seasonal pattern - time content with pattern peaks',
                'confidence': 0.7
            },
            'decline': {
                'timing': 'avoid',
                'window_hours': 0,
                'rationale': 'Declining interest - consider different keywords',
                'confidence': 0.8
            }
        }
        
        recommendation = timing_recommendations.get(pattern.pattern_type, {
            'timing': 'evaluate',
            'window_hours': 72,
            'rationale': 'Irregular pattern - monitor before creating content',
            'confidence': 0.4
        })
        
        # Adjust confidence based on pattern confidence and business relevance
        final_confidence = recommendation['confidence'] * pattern.confidence * pattern.business_relevance
        
        return {
            'keyword': keyword,
            'business_area': business_area,
            'pattern_type': pattern.pattern_type,
            'timing_recommendation': recommendation['timing'],
            'optimal_window_hours': recommendation['window_hours'],
            'rationale': recommendation['rationale'],
            'confidence': round(final_confidence, 3),
            'content_opportunity_score': pattern.content_opportunity,
            'peak_score': pattern.peak_score,
            'business_relevance': pattern.business_relevance
        }

# ============================================================================
# TESTING AND UTILITIES
# ============================================================================

async def test_trend_analyzer():
    """Test the trend analyzer functionality"""
    import os
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
    
    analyzer = TrendAnalyzer(database_url)
    
    print("🧪 TESTING TREND ANALYZER")
    print("=" * 40)
    
    # Test business area analysis
    print("\n📊 Business area analysis for 'tvsignals'...")
    analysis = await analyzer.analyze_business_area_trends('tvsignals', days=7)
    
    print(f"   Keywords analyzed: {analysis['total_keywords_analyzed']}")
    
    # Handle missing keys gracefully
    pattern_dist = analysis.get('pattern_distribution', {})
    print(f"   Pattern distribution: {pattern_dist}")
    
    summary = analysis.get('summary', {})
    avg_opportunity = summary.get('avg_content_opportunity', 'N/A')
    print(f"   Average opportunity score: {avg_opportunity}")
    
    top_opps = analysis.get('top_opportunities', [])
    if top_opps:
        print(f"   Top opportunities:")
        for i, opp in enumerate(top_opps[:3], 1):
            print(f"      {i}. {opp['keyword']}: {opp['opportunity_score']} ({opp['pattern_type']})")
    else:
        print(f"   No opportunities found")
    
    # Show any message from summary
    if 'message' in summary:
        print(f"   Note: {summary['message']}")
    
    # Test cross-business correlations
    print(f"\n🔗 Cross-business correlations...")
    correlations = await analyzer.find_cross_business_correlations(days=7)
    
    if correlations:
        print(f"   Found {len(correlations)} correlations")
        for corr in correlations[:3]:
            print(f"   • {corr.primary_keyword} ({corr.primary_business}) correlates with {len(corr.correlated_keywords)} other areas")
    else:
        print("   No significant correlations found")
    
    # Test content timing
    if analysis['patterns']:
        test_keyword = analysis['patterns'][0]['keyword']
        print(f"\n⏰ Content timing for '{test_keyword}'...")
        timing = await analyzer.optimize_content_timing(test_keyword, 'tvsignals')
        print(f"   Recommendation: {timing['timing_recommendation']}")
        print(f"   Window: {timing['optimal_window_hours']} hours")
        print(f"   Confidence: {timing['confidence']}")
        print(f"   Rationale: {timing['rationale']}")
    
    print("\n✅ Trend analyzer test complete!")

if __name__ == "__main__":
    asyncio.run(test_trend_analyzer())
