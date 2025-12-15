#!/usr/bin/env python3
"""
Opportunity Detector for Google Trends Integration
Identifies immediate content creation opportunities from trend data

Key Features:
- Works with current trend data (no historical patterns required)
- Low threshold detection for catching opportunities early
- Business-specific opportunity scoring
- Content timing recommendations
- User feedback integration for training
- Cross-system opportunity identification

FIXED: Now uses centralized db_manager instead of direct asyncpg.connect()
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import Enum

from ...core.database import db_manager

logger = logging.getLogger(__name__)


class OpportunityType(Enum):
    """Types of content opportunities"""
    BREAKING_NEWS = "breaking_news"    # Sudden spike, immediate action needed
    TRENDING_TOPIC = "trending_topic"  # Rising interest, good timing
    EVERGREEN = "evergreen"           # Stable interest, good for content
    SEASONAL = "seasonal"             # Recurring pattern opportunity
    CROSS_PROMOTION = "cross_promotion" # Opportunity across business areas


class UrgencyLevel(Enum):
    """Urgency levels for opportunities"""
    CRITICAL = "critical"  # Act within hours
    HIGH = "high"         # Act within 1-2 days
    MEDIUM = "medium"     # Act within a week
    LOW = "low"          # Consider for future content


@dataclass
class ContentOpportunity:
    """Container for content creation opportunities"""
    id: Optional[str]
    keyword: str
    business_area: str
    opportunity_type: OpportunityType
    urgency_level: UrgencyLevel
    
    # Scoring
    trend_score: int
    opportunity_score: float  # 0.0 to 1.0
    business_relevance: float # 0.0 to 1.0
    
    # Timing
    content_window_start: datetime
    content_window_end: datetime
    
    # Context
    reasoning: str
    suggested_content_types: List[str]
    competitor_advantage: bool
    
    # Metadata
    created_at: datetime
    processed: bool = False
    user_feedback: Optional[str] = None


class OpportunityDetector:
    """Detects content creation opportunities from trend data"""
    
    def __init__(self):
        """Initialize OpportunityDetector - uses centralized db_manager"""
        # No database_url needed - we use the centralized db_manager
        
        # Low threshold configuration (learned from TV signals issue)
        self.thresholds = {
            'critical_spike': 60,     # Score 60+ = immediate content needed
            'high_interest': 40,      # Score 40+ = high priority content
            'medium_interest': 25,    # Score 25+ = medium priority
            'low_interest': 15,       # Score 15+ = consider content
            'momentum_change': 10     # Score change 10+ = rising opportunity
        }
        
        # Business-specific content types
        self.business_content_types = {
            'amcf': [
                'donation campaign', 'charity spotlight', 'giving guide',
                'nonprofit tips', 'zakat calculator', 'impact story'
            ],
            'bcdodge': [
                'marketing strategy guide', 'campaign case study', 'digital trends analysis',
                'growth tactics', 'brand positioning', 'advertising tips'
            ],
            'damnitcarl': [
                'cat care tips', 'emotional support guide', 'cat behavior analysis',
                'pet therapy content', 'cat product review', 'funny cat content'
            ],
            'mealsnfeelz': [
                'food drive guide', 'ramadan giving tips', 'pantry spotlight',
                'hunger awareness', 'community support', 'volunteer guide'
            ],
            'roseandangel': [
                'consulting insights', 'small business guide', 'marketing tutorial',
                'nonprofit strategy', 'business growth tips', 'expert interview'
            ],
            'tvsignals': [
                'show review', 'streaming guide', 'episode recap',
                'series analysis', 'viewing recommendations', 'tv news update'
            ]
        }
    
    # ============================================================================
    # OPPORTUNITY DETECTION
    # ============================================================================
    
    async def detect_current_opportunities(self, business_area: Optional[str] = None,
                                         hours_lookback: int = 24) -> List[ContentOpportunity]:
        """Detect current content opportunities from recent trend data"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
            
            # Build query based on business area filter
            if business_area:
                query = '''
                    SELECT DISTINCT ON (keyword, business_area) 
                           keyword, business_area, trend_score, trend_momentum, 
                           trend_date, regional_score, created_at
                    FROM trend_monitoring 
                    WHERE business_area = $1 
                    AND created_at >= $2
                    AND trend_score IS NOT NULL
                    ORDER BY keyword, business_area, created_at DESC
                '''
                params = [business_area, cutoff_time]
            else:
                query = '''
                    SELECT DISTINCT ON (keyword, business_area) 
                           keyword, business_area, trend_score, trend_momentum, 
                           trend_date, regional_score, created_at
                    FROM trend_monitoring 
                    WHERE created_at >= $1
                    AND trend_score IS NOT NULL
                    ORDER BY keyword, business_area, created_at DESC
                '''
                params = [cutoff_time]
            
            rows = await conn.fetch(query, *params)
            
            opportunities = []
            
            for row in rows:
                opportunity = self._evaluate_trend_opportunity(
                    keyword=row['keyword'],
                    business_area=row['business_area'],
                    trend_score=row['trend_score'],
                    trend_momentum=row['trend_momentum'],
                    regional_score=row['regional_score']
                )
                
                if opportunity:
                    opportunities.append(opportunity)
            
            # Sort by opportunity score and urgency
            opportunities.sort(key=lambda x: (
                x.urgency_level.value == 'critical',
                x.urgency_level.value == 'high',
                x.opportunity_score
            ), reverse=True)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Failed to detect current opportunities: {e}")
            return []
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    def _evaluate_trend_opportunity(self, keyword: str, business_area: str,
                                    trend_score: int, trend_momentum: str,
                                    regional_score: Optional[int]) -> Optional[ContentOpportunity]:
        """Evaluate if a trend represents a content opportunity"""
        
        # Calculate business relevance
        business_relevance = self._calculate_business_relevance(keyword, business_area)
        
        # Determine opportunity type and urgency
        opportunity_type, urgency_level = self._classify_opportunity(
            trend_score, trend_momentum, business_relevance
        )
        
        # Skip low-relevance opportunities below threshold
        if business_relevance < 0.3 and trend_score < self.thresholds['medium_interest']:
            return None
        
        # Calculate opportunity score
        opportunity_score = self._calculate_opportunity_score(
            trend_score, business_relevance, regional_score, trend_momentum
        )
        
        # Skip very low opportunity scores
        if opportunity_score < 0.2:
            return None
        
        # Generate content timing window
        window_start, window_end = self._calculate_content_window(urgency_level)
        
        # Generate reasoning and content suggestions
        reasoning = self._generate_reasoning(
            keyword, trend_score, trend_momentum, business_relevance, opportunity_score
        )
        
        suggested_content = self.business_content_types.get(business_area, ['general content'])
        
        # Check for competitive advantage
        competitor_advantage = self._assess_competitive_advantage(
            keyword, business_area, trend_score
        )
        
        return ContentOpportunity(
            id=None,  # Will be set when saved to database
            keyword=keyword,
            business_area=business_area,
            opportunity_type=opportunity_type,
            urgency_level=urgency_level,
            trend_score=trend_score,
            opportunity_score=opportunity_score,
            business_relevance=business_relevance,
            content_window_start=window_start,
            content_window_end=window_end,
            reasoning=reasoning,
            suggested_content_types=suggested_content[:3],  # Top 3 suggestions
            competitor_advantage=competitor_advantage,
            created_at=datetime.now(timezone.utc)
        )
    
    def _calculate_business_relevance(self, keyword: str, business_area: str) -> float:
        """Calculate how relevant a keyword is to the business area"""
        keyword_lower = keyword.lower()
        
        # Business-specific relevance keywords
        relevance_keywords = {
            'amcf': {
                'charity': 0.9, 'donation': 0.9, 'nonprofit': 0.8, 'zakat': 0.9,
                'islamic': 0.7, 'muslim': 0.7, 'giving': 0.8, 'fundraising': 0.7,
                'philanthropy': 0.6, 'volunteer': 0.6
            },
            'bcdodge': {
                'marketing': 0.9, 'digital': 0.8, 'strategy': 0.8, 'campaign': 0.8,
                'advertising': 0.7, 'brand': 0.7, 'growth': 0.7, 'social media': 0.8,
                'seo': 0.6, 'content': 0.6
            },
            'damnitcarl': {
                'cat': 0.9, 'emotional': 0.8, 'support': 0.7, 'pet': 0.8,
                'feline': 0.9, 'kitten': 0.8, 'therapy': 0.7, 'tuxedo': 0.7,
                'animal': 0.6
            },
            'mealsnfeelz': {
                'food': 0.9, 'pantry': 0.9, 'meal': 0.8, 'ramadan': 0.8,
                'fidya': 0.9, 'hunger': 0.8, 'feeding': 0.7, 'nutrition': 0.6,
                'cooking': 0.5
            },
            'roseandangel': {
                'marketing': 0.9, 'consultant': 0.9, 'business': 0.8, 'strategy': 0.7,
                'small business': 0.8, 'nonprofit': 0.6, 'consulting': 0.9,
                'expert': 0.7, 'advisor': 0.7
            },
            'tvsignals': {
                'tv': 0.9, 'streaming': 0.9, 'show': 0.8, 'series': 0.8,
                'netflix': 0.7, 'watch': 0.7, 'episode': 0.8, 'season': 0.7,
                'binge': 0.7, 'television': 0.9
            }
        }
        
        business_keywords = relevance_keywords.get(business_area, {})
        
        # Calculate relevance based on keyword matches
        max_relevance = 0.0
        for term, relevance in business_keywords.items():
            if term in keyword_lower:
                max_relevance = max(max_relevance, relevance)
        
        # Base relevance for any keyword in the business area
        base_relevance = 0.3
        
        return max(base_relevance, max_relevance)
    
    def _classify_opportunity(self, trend_score: int, trend_momentum: str,
                            business_relevance: float) -> Tuple[OpportunityType, UrgencyLevel]:
        """Classify the type and urgency of the opportunity"""
        
        # Determine opportunity type
        if trend_momentum == 'breakout' or trend_score >= self.thresholds['critical_spike']:
            opp_type = OpportunityType.BREAKING_NEWS
        elif trend_momentum in ['rising', 'growing'] or trend_score >= self.thresholds['high_interest']:
            opp_type = OpportunityType.TRENDING_TOPIC
        elif trend_momentum == 'stable' and trend_score >= self.thresholds['medium_interest']:
            opp_type = OpportunityType.EVERGREEN
        elif trend_momentum == 'seasonal':
            opp_type = OpportunityType.SEASONAL
        else:
            opp_type = OpportunityType.TRENDING_TOPIC
        
        # Determine urgency level
        if opp_type == OpportunityType.BREAKING_NEWS:
            urgency = UrgencyLevel.CRITICAL
        elif trend_score >= self.thresholds['critical_spike'] or business_relevance >= 0.8:
            urgency = UrgencyLevel.HIGH
        elif trend_score >= self.thresholds['high_interest'] or business_relevance >= 0.6:
            urgency = UrgencyLevel.MEDIUM
        else:
            urgency = UrgencyLevel.LOW
        
        return opp_type, urgency
    
    def _calculate_opportunity_score(self, trend_score: int, business_relevance: float,
                                   regional_score: Optional[int], trend_momentum: str) -> float:
        """Calculate overall opportunity score (0.0 to 1.0)"""
        
        # Base score from trend score (normalized)
        trend_component = min(1.0, trend_score / 100.0)
        
        # Business relevance component
        relevance_component = business_relevance
        
        # Regional interest boost
        regional_component = 0.0
        if regional_score:
            regional_component = min(0.2, regional_score / 100.0 * 0.2)
        
        # Momentum multiplier
        momentum_multipliers = {
            'breakout': 1.3,
            'rising': 1.2,
            'growing': 1.1,
            'stable': 1.0,
            'declining': 0.7,
            'unknown': 0.9
        }
        
        momentum_multiplier = momentum_multipliers.get(trend_momentum, 1.0)
        
        # Calculate weighted score
        base_score = (trend_component * 0.4 + relevance_component * 0.5 + regional_component)
        final_score = base_score * momentum_multiplier
        
        return min(1.0, round(final_score, 3))
    
    def _calculate_content_window(self, urgency_level: UrgencyLevel) -> Tuple[datetime, datetime]:
        """Calculate optimal content creation window"""
        now = datetime.now(timezone.utc)
        
        window_durations = {
            UrgencyLevel.CRITICAL: timedelta(hours=6),   # Act within 6 hours
            UrgencyLevel.HIGH: timedelta(hours=24),      # Act within 24 hours
            UrgencyLevel.MEDIUM: timedelta(days=3),      # Act within 3 days
            UrgencyLevel.LOW: timedelta(days=7)          # Act within a week
        }
        
        duration = window_durations.get(urgency_level, timedelta(days=3))
        
        return now, now + duration
    
    def _generate_reasoning(self, keyword: str, trend_score: int, trend_momentum: str,
                          business_relevance: float, opportunity_score: float) -> str:
        """Generate human-readable reasoning for the opportunity"""
        
        reasons = []
        
        # Trend score reasoning
        if trend_score >= 60:
            reasons.append(f"High search volume ({trend_score} points)")
        elif trend_score >= 40:
            reasons.append(f"Moderate search volume ({trend_score} points)")
        elif trend_score >= 20:
            reasons.append(f"Growing search interest ({trend_score} points)")
        
        # Momentum reasoning
        momentum_descriptions = {
            'breakout': "Sudden spike in interest",
            'rising': "Steadily increasing interest",
            'growing': "Growing trend momentum",
            'stable': "Consistent search interest",
            'declining': "Declining but still active"
        }
        
        if trend_momentum in momentum_descriptions:
            reasons.append(momentum_descriptions[trend_momentum])
        
        # Business relevance reasoning
        if business_relevance >= 0.8:
            reasons.append("Highly relevant to business focus")
        elif business_relevance >= 0.6:
            reasons.append("Good business relevance")
        elif business_relevance >= 0.4:
            reasons.append("Moderate business relevance")
        
        # Opportunity score reasoning
        if opportunity_score >= 0.8:
            reasons.append("Excellent content opportunity")
        elif opportunity_score >= 0.6:
            reasons.append("Good content potential")
        elif opportunity_score >= 0.4:
            reasons.append("Moderate content opportunity")
        
        return ". ".join(reasons) + "."
    
    def _assess_competitive_advantage(self, keyword: str, business_area: str,
                                    trend_score: int) -> bool:
        """Assess if this represents a competitive advantage opportunity"""
        
        # Simple heuristic: trending keywords in your business area
        # that aren't oversaturated (score < 80) represent good opportunities
        
        keyword_lower = keyword.lower()
        
        # Business-specific advantage keywords (less competitive terms)
        advantage_terms = {
            'amcf': ['zakat', 'islamic charity', 'fidya', 'donor advised'],
            'bcdodge': ['dodge marketing', 'automotive marketing', 'car dealership'],
            'damnitcarl': ['emotional support cat', 'tuxedo cat', 'cat therapy'],
            'mealsnfeelz': ['ramadan food', 'fidya donation', 'islamic food'],
            'roseandangel': ['nonprofit marketing', 'small business consultant'],
            'tvsignals': ['streaming recommendations', 'tv signals', 'show analysis']
        }
        
        business_terms = advantage_terms.get(business_area, [])
        
        # Check for business-specific terms that might have less competition
        for term in business_terms:
            if term in keyword_lower:
                return True
        
        # Trending but not oversaturated
        return 20 <= trend_score <= 70
    
    # ============================================================================
    # OPPORTUNITY MANAGEMENT
    # ============================================================================
    
    async def save_opportunity(self, opportunity: ContentOpportunity) -> str:
        """Save opportunity to database and return ID"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            query = '''
                INSERT INTO trend_opportunities 
                (keyword, business_area, opportunity_type, urgency_level, trend_momentum,
                 alert_threshold_met, trend_score_at_alert, optimal_content_window_start,
                 optimal_content_window_end, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            '''
            
            opportunity_id = await conn.fetchval(
                query,
                opportunity.keyword,
                opportunity.business_area,
                opportunity.opportunity_type.value,
                opportunity.urgency_level.value,
                'detected',  # Simple momentum for compatibility
                True,
                opportunity.trend_score,
                opportunity.content_window_start,
                opportunity.content_window_end,
                opportunity.created_at
            )
            
            logger.info(f"Saved opportunity {opportunity_id} for keyword '{opportunity.keyword}'")
            return str(opportunity_id)
            
        except Exception as e:
            logger.error(f"Failed to save opportunity: {e}")
            return ""
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_active_opportunities(self, business_area: Optional[str] = None,
                                     urgency_filter: Optional[UrgencyLevel] = None) -> List[ContentOpportunity]:
        """Get active opportunities that haven't expired"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Build query with filters
            where_conditions = ["processed = FALSE", "optimal_content_window_end > NOW()"]
            params = []
            
            if business_area:
                where_conditions.append(f"business_area = ${len(params) + 1}")
                params.append(business_area)
            
            if urgency_filter:
                where_conditions.append(f"urgency_level = ${len(params) + 1}")
                params.append(urgency_filter.value)
            
            query = f'''
                SELECT id, keyword, business_area, opportunity_type, urgency_level,
                       trend_score_at_alert, optimal_content_window_start,
                       optimal_content_window_end, created_at, processed, user_feedback
                FROM trend_opportunities 
                WHERE {" AND ".join(where_conditions)}
                ORDER BY 
                    CASE urgency_level 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    created_at DESC
                LIMIT 50
            '''
            
            rows = await conn.fetch(query, *params)
            
            opportunities = []
            for row in rows:
                # Create opportunity object from database data
                opp = ContentOpportunity(
                    id=str(row['id']),
                    keyword=row['keyword'],
                    business_area=row['business_area'],
                    opportunity_type=OpportunityType(row['opportunity_type']),
                    urgency_level=UrgencyLevel(row['urgency_level']),
                    trend_score=row['trend_score_at_alert'],
                    opportunity_score=0.0,  # Would need to recalculate
                    business_relevance=0.0,  # Would need to recalculate
                    content_window_start=row['optimal_content_window_start'],
                    content_window_end=row['optimal_content_window_end'],
                    reasoning="",  # Would need to regenerate
                    suggested_content_types=[],  # Would need to regenerate
                    competitor_advantage=False,  # Would need to recalculate
                    created_at=row['created_at'],
                    processed=row['processed'],
                    user_feedback=row['user_feedback']
                )
                opportunities.append(opp)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Failed to get active opportunities: {e}")
            return []
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def process_opportunities_batch(self, limit: int = 20) -> List[ContentOpportunity]:
        """Detect and save a batch of new opportunities"""
        
        # Detect current opportunities
        opportunities = await self.detect_current_opportunities()
        
        if not opportunities:
            return []
        
        # Save top opportunities to database
        saved_opportunities = []
        
        for opportunity in opportunities[:limit]:
            try:
                opportunity_id = await self.save_opportunity(opportunity)
                opportunity.id = opportunity_id
                saved_opportunities.append(opportunity)
            except Exception as e:
                logger.error(f"Failed to save opportunity for {opportunity.keyword}: {e}")
        
        logger.info(f"Processed and saved {len(saved_opportunities)} opportunities")
        return saved_opportunities


# ============================================================================
# SINGLETON GETTER
# ============================================================================

_opportunity_detector: Optional[OpportunityDetector] = None


def get_opportunity_detector() -> OpportunityDetector:
    """Get or create the OpportunityDetector singleton instance"""
    global _opportunity_detector
    if _opportunity_detector is None:
        _opportunity_detector = OpportunityDetector()
    return _opportunity_detector
