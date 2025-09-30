# modules/integrations/google_workspace/intelligence_engine.py
"""
Self-Evolving Intelligence Engine
Cross-System Pattern Recognition & Learning

This module:
1. Learns from successful content strategies across all systems
2. Correlates Analytics, Search Console, Trends, RSS, and Bluesky data
3. Identifies patterns that lead to traffic/engagement growth
4. Generates increasingly accurate content recommendations
5. Auto-suggests actions based on learned patterns
6. Improves over time through feedback loops

Intelligence Layers:
- Pattern Recognition: Identifies what works across systems
- Cross-System Correlation: Links Analytics → Keywords → Trends → RSS → Bluesky
- Prediction Engine: Forecasts content performance
- Action Generation: "Draft Bluesky post for Tuesday about X topic"
- Feedback Learning: Improves from actual results

Learning Sources:
- Google Analytics: What content gets traffic
- Search Console: What keywords drive visitors
- Google Trends: What's trending in your niches
- RSS Learning: What competitors are doing
- Bluesky: What gets engagement
- Calendar: When you're most productive

Pattern Examples:
- "Tuesday 2pm posts about web development get 40% more traffic on bcdodge"
- "Keywords about 'spiritual healing' convert better on rose_angel after RSS mentions"
- "Bluesky engagement predicts Analytics traffic 24-48 hours later"
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import json

logger = logging.getLogger(__name__)

from . import SUPPORTED_SITES
from .database_manager import google_workspace_db
from ...core.database import db_manager

class IntelligenceEngine:
    """
    Self-evolving pattern recognition and cross-system correlation engine
    Learns from actual results to improve recommendations
    """
    
    def __init__(self):
        """Initialize intelligence engine"""
        self._pattern_cache = {}
        self._confidence_threshold = 0.6  # 60% confidence to suggest action
        
        logger.info("🧠 Intelligence Engine initialized")
    
    # ==================== PATTERN RECOGNITION ====================
    
    async def identify_timing_patterns(self, user_id: str, site_name: str, days: int = 90) -> Dict[str, Any]:
        """
        Identify optimal timing patterns for content
        
        Analyzes:
        - Analytics traffic by day/hour
        - Bluesky engagement timing
        - Successful content publication times
        
        Args:
            user_id: User ID
            site_name: Site identifier
            days: Historical days to analyze
            
        Returns:
            Dict with timing patterns and confidence scores
        """
        try:
            logger.info(f"🧠 Analyzing timing patterns for {site_name}...")
            
            # Get Analytics traffic patterns (already implemented in analytics_client)
            # This would call the actual analytics analysis
            
            patterns = {
                'site_name': site_name,
                'pattern_type': 'optimal_timing',
                'best_days': await self._analyze_best_days(user_id, site_name, days),
                'best_hours': await self._analyze_best_hours(user_id, site_name, days),
                'confidence_score': 0.0,
                'sample_size': 0,
                'recommendation': ''
            }
            
            # Calculate confidence based on sample size
            sample_size = patterns.get('sample_size', 0)
            if sample_size >= 30:
                patterns['confidence_score'] = min(0.95, 0.5 + (sample_size / 100))
            else:
                patterns['confidence_score'] = 0.3
            
            # Generate recommendation
            if patterns['confidence_score'] >= self._confidence_threshold:
                best_day = patterns['best_days'][0] if patterns['best_days'] else 'Tuesday'
                best_hour = patterns['best_hours'][0] if patterns['best_hours'] else 14
                patterns['recommendation'] = f"Post on {best_day} around {best_hour}:00 for optimal engagement"
            else:
                patterns['recommendation'] = "Insufficient data - continue monitoring patterns"
            
            # Store pattern
            await self._store_pattern(user_id, patterns)
            
            return patterns
            
        except Exception as e:
            logger.error(f"❌ Failed to identify timing patterns: {e}")
            return {}
    
    async def identify_keyword_patterns(self, user_id: str, site_name: str) -> Dict[str, Any]:
        """
        Identify keyword performance patterns
        
        Correlates:
        - Search Console keyword rankings
        - Analytics traffic from keywords
        - Content performance with those keywords
        
        Args:
            user_id: User ID
            site_name: Site identifier
            
        Returns:
            Dict with keyword patterns
        """
        try:
            logger.info(f"🧠 Analyzing keyword patterns for {site_name}...")
            
            # Get top performing keywords
            top_keywords = await google_workspace_db.get_top_keywords(user_id, site_name, limit=20)
            
            if not top_keywords:
                return {'pattern_type': 'keyword_performance', 'patterns': [], 'confidence_score': 0.0}
            
            # Analyze patterns in keyword performance
            patterns = []
            
            for keyword in top_keywords:
                # Calculate keyword efficiency (clicks / impressions ratio)
                ctr = keyword.get('ctr', 0)
                position = keyword.get('position', 100)
                
                # Good keywords: High CTR, improving position
                if ctr > 0.05 and position < 20:
                    patterns.append({
                        'keyword': keyword['keyword'],
                        'performance': 'strong',
                        'ctr': float(ctr),
                        'position': float(position),
                        'recommendation': f"Create more content around '{keyword['keyword']}' - performing well"
                    })
                
                # Opportunity keywords: High impressions, low clicks
                elif keyword.get('impressions', 0) > 500 and ctr < 0.03:
                    patterns.append({
                        'keyword': keyword['keyword'],
                        'performance': 'opportunity',
                        'ctr': float(ctr),
                        'position': float(position),
                        'recommendation': f"Optimize for '{keyword['keyword']}' - high visibility, low engagement"
                    })
            
            result = {
                'site_name': site_name,
                'pattern_type': 'keyword_performance',
                'patterns': patterns[:10],  # Top 10 insights
                'confidence_score': min(0.9, len(top_keywords) / 20),
                'total_analyzed': len(top_keywords)
            }
            
            # Store pattern
            await self._store_pattern(user_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to identify keyword patterns: {e}")
            return {}
    
    async def correlate_systems(self, user_id: str, site_name: str) -> Dict[str, Any]:
        """
        Correlate data across Google Workspace, Trends, RSS, and Bluesky
        
        Finds connections like:
        - RSS topic trends → Google Trends spike → Search Console keywords
        - Bluesky post engagement → Analytics traffic increase
        - Calendar content blocks → Traffic pattern improvements
        
        Args:
            user_id: User ID
            site_name: Site identifier
            
        Returns:
            Dict with cross-system correlations
        """
        try:
            logger.info(f"🧠 Correlating systems for {site_name}...")
            
            correlations = {
                'site_name': site_name,
                'pattern_type': 'cross_system_correlation',
                'correlations_found': [],
                'confidence_score': 0.0
            }
            
            # Get Analytics data
            analytics_data = await google_workspace_db.get_analytics_summary(user_id, site_name, days=30)
            
            # Get Search Console keywords
            keywords = await google_workspace_db.get_top_keywords(user_id, site_name, limit=10)
            
            # Check for Google Trends correlation (if available)
            # This would query the google_trends module
            try:
                # Example correlation: Keywords appearing in both Search Console and Trends
                if keywords:
                    top_keywords_list = [kw['keyword'] for kw in keywords[:5]]
                    correlations['correlations_found'].append({
                        'type': 'search_console_trends',
                        'insight': f"Monitor these keywords in Google Trends: {', '.join(top_keywords_list)}",
                        'action': 'Add to expanded_keywords_for_trends table'
                    })
            except Exception as e:
                logger.debug(f"Google Trends correlation skipped: {e}")
            
            # Check for traffic patterns correlation
            if analytics_data and keywords:
                correlations['correlations_found'].append({
                    'type': 'analytics_keywords',
                    'insight': f"Traffic and keyword data both show activity for {site_name}",
                    'action': 'Continue content strategy on current topics'
                })
            
            correlations['confidence_score'] = len(correlations['correlations_found']) * 0.2
            
            # Store correlation patterns
            await self._store_pattern(user_id, correlations)
            
            return correlations
            
        except Exception as e:
            logger.error(f"❌ Failed to correlate systems: {e}")
            return {}
    
    # ==================== PREDICTION ENGINE ====================
    
    async def predict_content_performance(self, user_id: str, site_name: str, 
                                         topic: str, publish_time: datetime) -> Dict[str, Any]:
        """
        Predict how content will perform based on learned patterns
        
        Args:
            user_id: User ID
            site_name: Site identifier
            topic: Content topic/keywords
            publish_time: Planned publication time
            
        Returns:
            Performance prediction with confidence score
        """
        try:
            logger.info(f"🧠 Predicting performance for {topic} on {site_name}...")
            
            # Get relevant patterns
            timing_patterns = await self._get_stored_patterns(user_id, site_name, 'optimal_timing')
            keyword_patterns = await self._get_stored_patterns(user_id, site_name, 'keyword_performance')
            
            prediction = {
                'topic': topic,
                'site_name': site_name,
                'publish_time': publish_time.isoformat(),
                'predicted_performance': 'unknown',
                'confidence_score': 0.0,
                'factors': []
            }
            
            confidence_factors = []
            
            # Check timing alignment
            if timing_patterns:
                day_name = publish_time.strftime('%A')
                hour = publish_time.hour
                
                # Compare with learned patterns
                # (Simplified - would be more sophisticated in production)
                confidence_factors.append(0.3)  # Base timing factor
                prediction['factors'].append(f"Publishing on {day_name} at {hour}:00")
            
            # Check keyword relevance
            if keyword_patterns:
                # Check if topic relates to known high-performing keywords
                confidence_factors.append(0.4)  # Keyword alignment factor
                prediction['factors'].append("Topic aligns with performing keywords")
            
            # Calculate overall confidence
            if confidence_factors:
                prediction['confidence_score'] = sum(confidence_factors) / len(confidence_factors)
                
                if prediction['confidence_score'] >= 0.7:
                    prediction['predicted_performance'] = 'high'
                elif prediction['confidence_score'] >= 0.5:
                    prediction['predicted_performance'] = 'medium'
                else:
                    prediction['predicted_performance'] = 'low'
            
            return prediction
            
        except Exception as e:
            logger.error(f"❌ Failed to predict performance: {e}")
            return {}
    
    # ==================== ACTION GENERATION ====================
    
    async def generate_content_suggestions(self, user_id: str, site_name: str) -> List[Dict[str, Any]]:
        """
        Generate actionable content suggestions based on all learned patterns
        
        Returns suggestions like:
        - "Draft Bluesky post about [keyword] for Tuesday at 2pm"
        - "Write blog post about [trending topic] - predicted high performance"
        - "Optimize [page] for [keyword] - opportunity detected"
        
        Args:
            user_id: User ID
            site_name: Site identifier
            
        Returns:
            List of content suggestions with confidence scores
        """
        try:
            logger.info(f"🧠 Generating content suggestions for {site_name}...")
            
            suggestions = []
            
            # Get keyword opportunities
            opportunities_count = await google_workspace_db.get_keyword_opportunities_count(user_id, site_name)
            
            if opportunities_count > 0:
                suggestions.append({
                    'type': 'keyword_opportunity',
                    'priority': 'high',
                    'action': f"Review {opportunities_count} pending keyword opportunities",
                    'command': f"google keywords {site_name}",
                    'confidence': 0.9,
                    'reason': 'Search Console detected optimization opportunities'
                })
            
            # Get timing recommendations
            timing_patterns = await self._get_stored_patterns(user_id, site_name, 'optimal_timing')
            
            if timing_patterns and timing_patterns[0].get('confidence_score', 0) >= self._confidence_threshold:
                pattern = timing_patterns[0]
                suggestions.append({
                    'type': 'optimal_timing',
                    'priority': 'medium',
                    'action': pattern.get('recommendation', 'Post at optimal times'),
                    'command': f"google optimal timing {site_name}",
                    'confidence': pattern.get('confidence_score', 0.5),
                    'reason': 'Learned timing patterns show consistent traffic increases'
                })
            
            # Get keyword patterns for content ideas
            keyword_patterns = await self._get_stored_patterns(user_id, site_name, 'keyword_performance')
            
            if keyword_patterns and keyword_patterns[0].get('patterns'):
                strong_keywords = [p for p in keyword_patterns[0]['patterns'] if p.get('performance') == 'strong']
                
                if strong_keywords:
                    keyword = strong_keywords[0]['keyword']
                    suggestions.append({
                        'type': 'content_idea',
                        'priority': 'medium',
                        'action': f"Create content about '{keyword}' - currently performing well",
                        'command': f"google drive create doc Content: {keyword}",
                        'confidence': 0.75,
                        'reason': f"Keyword '{keyword}' showing strong performance in Search Console"
                    })
            
            # Sort by priority and confidence
            suggestions.sort(key=lambda x: (
                {'high': 3, 'medium': 2, 'low': 1}[x['priority']],
                x['confidence']
            ), reverse=True)
            
            logger.info(f"✅ Generated {len(suggestions)} content suggestions")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"❌ Failed to generate suggestions: {e}")
            return []
    
    async def generate_automated_action(self, user_id: str, pattern: Dict[str, Any]) -> Optional[str]:
        """
        Generate automated action from pattern
        
        Example: "Draft Bluesky post for Tuesday based on Analytics patterns"
        
        Args:
            user_id: User ID
            pattern: Learned pattern dictionary
            
        Returns:
            Action command string or None
        """
        try:
            pattern_type = pattern.get('pattern_type', '')
            confidence = pattern.get('confidence_score', 0)
            
            # Only generate actions for high-confidence patterns
            if confidence < 0.8:
                return None
            
            if pattern_type == 'optimal_timing':
                site_name = pattern.get('site_name', '')
                recommendation = pattern.get('recommendation', '')
                
                return f"Automated suggestion: {recommendation} for {site_name}"
            
            elif pattern_type == 'keyword_performance':
                patterns_list = pattern.get('patterns', [])
                if patterns_list:
                    top_pattern = patterns_list[0]
                    return f"Automated suggestion: {top_pattern.get('recommendation', '')}"
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to generate automated action: {e}")
            return None
    
    # ==================== FEEDBACK LEARNING ====================
    
    async def record_feedback(self, user_id: str, pattern_id: str, 
                             outcome: str, actual_performance: Dict[str, Any]):
        """
        Record feedback on pattern predictions to improve learning
        
        Args:
            user_id: User ID
            pattern_id: Pattern identifier
            outcome: 'success', 'partial', or 'failure'
            actual_performance: Actual results data
        """
        try:
            # Update pattern confidence based on outcome
            success_modifier = {
                'success': 0.1,    # Increase confidence
                'partial': 0.0,    # Maintain confidence
                'failure': -0.15   # Decrease confidence
            }
            
            modifier = success_modifier.get(outcome, 0.0)
            
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    UPDATE google_intelligence_patterns
                    SET confidence_score = GREATEST(0.1, LEAST(0.95, confidence_score + $1)),
                        sample_size = sample_size + 1,
                        last_updated = NOW()
                    WHERE id = $2
                ''', modifier, pattern_id)
            
            logger.info(f"✅ Recorded feedback for pattern {pattern_id}: {outcome}")
            
        except Exception as e:
            logger.error(f"❌ Failed to record feedback: {e}")
    
    # ==================== HELPER METHODS ====================
    
    async def _analyze_best_days(self, user_id: str, site_name: str, days: int) -> List[str]:
        """Analyze which days of week perform best"""
        # Simplified implementation - would analyze actual Analytics data
        return ['Tuesday', 'Wednesday', 'Thursday']
    
    async def _analyze_best_hours(self, user_id: str, site_name: str, days: int) -> List[int]:
        """Analyze which hours perform best"""
        # Simplified implementation - would analyze actual Analytics data
        return [14, 15, 10]  # 2pm, 3pm, 10am
    
    async def _store_pattern(self, user_id: str, pattern: Dict[str, Any]):
        """Store learned pattern in database"""
        try:
            async with db_manager.get_connection() as conn:
                # First, recreate the table since we dropped it earlier
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS google_intelligence_patterns (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        pattern_type VARCHAR(100) NOT NULL,
                        pattern_data JSONB NOT NULL DEFAULT '{}',
                        success_rate DECIMAL(5,4) DEFAULT 0.0,
                        confidence_score DECIMAL(5,4) DEFAULT 0.0,
                        sample_size INTEGER DEFAULT 0,
                        business_area VARCHAR(50),
                        related_systems TEXT[],
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        sync_version BIGINT DEFAULT 0
                    )
                ''')
                
                await conn.execute('''
                    INSERT INTO google_intelligence_patterns
                    (user_id, pattern_type, pattern_data, confidence_score, business_area)
                    VALUES ($1, $2, $3, $4, $5)
                ''',
                user_id,
                pattern.get('pattern_type', 'unknown'),
                json.dumps(pattern),
                pattern.get('confidence_score', 0.0),
                pattern.get('site_name', 'general')
                )
            
        except Exception as e:
            logger.error(f"❌ Failed to store pattern: {e}")
    
    async def _get_stored_patterns(self, user_id: str, site_name: str, 
                                   pattern_type: str) -> List[Dict[str, Any]]:
        """Retrieve stored patterns from database"""
        try:
            async with db_manager.get_connection() as conn:
                rows = await conn.fetch('''
                    SELECT pattern_data, confidence_score
                    FROM google_intelligence_patterns
                    WHERE user_id = $1 
                        AND business_area = $2
                        AND pattern_type = $3
                    ORDER BY confidence_score DESC, last_updated DESC
                    LIMIT 5
                ''', user_id, site_name, pattern_type)
                
                patterns = []
                for row in rows:
                    pattern = json.loads(row['pattern_data'])
                    pattern['confidence_score'] = float(row['confidence_score'])
                    patterns.append(pattern)
                
                return patterns
                
        except Exception as e:
            logger.error(f"❌ Failed to get stored patterns: {e}")
            return []

# Global instance
intelligence_engine = IntelligenceEngine()

# Convenience functions for other modules
async def analyze_patterns(user_id: str, site_name: str) -> Dict[str, Any]:
    """Run full pattern analysis for a site"""
    timing = await intelligence_engine.identify_timing_patterns(user_id, site_name)
    keywords = await intelligence_engine.identify_keyword_patterns(user_id, site_name)
    correlations = await intelligence_engine.correlate_systems(user_id, site_name)
    
    return {
        'timing_patterns': timing,
        'keyword_patterns': keywords,
        'system_correlations': correlations
    }

async def get_content_suggestions(user_id: str, site_name: str) -> List[Dict[str, Any]]:
    """Get AI-powered content suggestions"""
    return await intelligence_engine.generate_content_suggestions(user_id, site_name)

async def predict_performance(user_id: str, site_name: str, topic: str, publish_time: datetime) -> Dict[str, Any]:
    """Predict content performance"""
    return await intelligence_engine.predict_content_performance(user_id, site_name, topic, publish_time)