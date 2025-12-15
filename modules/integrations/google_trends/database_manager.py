#!/usr/bin/env python3
"""
Google Trends Database Manager
Handles all database operations for trend monitoring system

Key Features:
- Trend data storage and retrieval
- Opportunity alert management
- User feedback processing (good/bad match training)
- Cross-system data integration (RSS correlation)
- Analytics and reporting queries

FIXED: Now uses centralized db_manager instead of direct asyncpg.connect()
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, date
import logging
from dataclasses import dataclass

from ...core.database import db_manager

logger = logging.getLogger(__name__)


@dataclass
class TrendAlert:
    """Container for trend opportunity alerts"""
    id: str
    keyword: str
    business_area: str
    opportunity_type: str
    urgency_level: str
    trend_score: int
    created_at: datetime
    processed: bool = False
    user_feedback: Optional[str] = None


@dataclass
class TrendSummary:
    """Summary of trend activity for a business area"""
    business_area: str
    total_keywords_monitored: int
    trending_keywords: int
    high_priority_alerts: int
    recent_opportunities: int
    avg_trend_score: float
    top_keywords: List[Tuple[str, int]]


class TrendsDatabase:
    """Manages all database operations for Google Trends system"""
    
    def __init__(self):
        """Initialize TrendsDatabase - uses centralized db_manager"""
        # No database_url needed - we use the centralized db_manager
        pass
    
    # ============================================================================
    # TREND DATA MANAGEMENT
    # ============================================================================
    
    async def save_trend_data(self, keyword: str, business_area: str,
                            trend_score: int, trend_momentum: str,
                            regional_score: Optional[int] = None,
                            trend_date: Optional[date] = None) -> bool:
        """Save trend data to database"""
        try:
            if trend_date is None:
                trend_date = date.today()
            
            await db_manager.execute('''
                INSERT INTO trend_monitoring 
                (keyword, business_area, trend_score, trend_date, trend_momentum,
                 regional_score, region, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                ON CONFLICT (keyword, business_area, trend_date, region) 
                DO UPDATE SET 
                    trend_score = EXCLUDED.trend_score,
                    trend_momentum = EXCLUDED.trend_momentum,
                    regional_score = EXCLUDED.regional_score,
                    updated_at = NOW()
            ''',
                keyword, business_area, trend_score, trend_date,
                trend_momentum, regional_score, 'US'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save trend data for {keyword}: {e}")
            return False
    
    async def get_recent_trends(self, business_area: Optional[str] = None,
                              days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trend data"""
        try:
            if business_area:
                query = '''
                    SELECT keyword, business_area, trend_score, trend_date, 
                           trend_momentum, regional_score, created_at
                    FROM trend_monitoring 
                    WHERE trend_date >= $1 AND business_area = $2
                    ORDER BY trend_score DESC, created_at DESC
                    LIMIT $3
                '''
                rows = await db_manager.fetch_all(
                    query,
                    date.today() - timedelta(days=days),
                    business_area,
                    limit
                )
            else:
                query = '''
                    SELECT keyword, business_area, trend_score, trend_date, 
                           trend_momentum, regional_score, created_at
                    FROM trend_monitoring 
                    WHERE trend_date >= $1
                    ORDER BY trend_score DESC, created_at DESC
                    LIMIT $2
                '''
                rows = await db_manager.fetch_all(
                    query,
                    date.today() - timedelta(days=days),
                    limit
                )
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get recent trends: {e}")
            return []
    
    async def get_trending_keywords(self, business_area: str,
                                  min_score: int = 20, days: int = 3) -> List[Dict[str, Any]]:
        """Get currently trending keywords for a business area"""
        try:
            query = '''
                SELECT keyword, trend_score, trend_momentum, trend_date,
                       regional_score, created_at
                FROM trend_monitoring 
                WHERE business_area = $1 
                AND trend_date >= $2
                AND trend_score >= $3
                ORDER BY trend_score DESC, created_at DESC
                LIMIT 20
            '''
            
            rows = await db_manager.fetch_all(
                query,
                business_area,
                date.today() - timedelta(days=days),
                min_score
            )
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get trending keywords: {e}")
            return []
    
    # ============================================================================
    # OPPORTUNITY ALERTS MANAGEMENT
    # ============================================================================
    
    async def create_opportunity_alert(self, keyword: str, business_area: str,
                                     opportunity_type: str, urgency_level: str,
                                     trend_momentum: str, trend_score: int,
                                     content_window_hours: int = 48) -> str:
        """Create a new trend opportunity alert"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            window_start = datetime.now()
            window_end = window_start + timedelta(hours=content_window_hours)
            
            # Calculate momentum change if we have historical data
            momentum_change = await self._calculate_momentum_change(conn, keyword, business_area)
            
            query = '''
                INSERT INTO trend_opportunities 
                (keyword, business_area, opportunity_type, urgency_level, trend_momentum,
                 alert_threshold_met, trend_score_at_alert, momentum_change_percent,
                 optimal_content_window_start, optimal_content_window_end, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                RETURNING id
            '''
            
            alert_id = await conn.fetchval(
                query, keyword, business_area, opportunity_type, urgency_level,
                trend_momentum, True, trend_score, momentum_change,
                window_start, window_end
            )
            
            logger.info(f"Created opportunity alert {alert_id} for {keyword} ({business_area})")
            return str(alert_id)
            
        except Exception as e:
            logger.error(f"Failed to create opportunity alert: {e}")
            return ""
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_unprocessed_alerts(self, urgency_level: Optional[str] = None) -> List[TrendAlert]:
        """Get unprocessed opportunity alerts"""
        try:
            if urgency_level:
                query = '''
                    SELECT id, keyword, business_area, opportunity_type, urgency_level,
                           trend_score_at_alert, created_at, processed, user_feedback
                    FROM trend_opportunities 
                    WHERE processed = FALSE AND urgency_level = $1
                    ORDER BY 
                        CASE urgency_level 
                            WHEN 'high' THEN 1 
                            WHEN 'medium' THEN 2 
                            ELSE 3 
                        END,
                        created_at DESC
                    LIMIT 50
                '''
                rows = await db_manager.fetch_all(query, urgency_level)
            else:
                query = '''
                    SELECT id, keyword, business_area, opportunity_type, urgency_level,
                           trend_score_at_alert, created_at, processed, user_feedback
                    FROM trend_opportunities 
                    WHERE processed = FALSE
                    ORDER BY 
                        CASE urgency_level 
                            WHEN 'high' THEN 1 
                            WHEN 'medium' THEN 2 
                            ELSE 3 
                        END,
                        created_at DESC
                    LIMIT 50
                '''
                rows = await db_manager.fetch_all(query)
            
            alerts = []
            for row in rows:
                alerts.append(TrendAlert(
                    id=str(row['id']),
                    keyword=row['keyword'],
                    business_area=row['business_area'],
                    opportunity_type=row['opportunity_type'],
                    urgency_level=row['urgency_level'],
                    trend_score=row['trend_score_at_alert'],
                    created_at=row['created_at'],
                    processed=row['processed'],
                    user_feedback=row['user_feedback']
                ))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get unprocessed alerts: {e}")
            return []
    
    async def mark_alert_processed(self, alert_id: str, user_feedback: Optional[str] = None) -> bool:
        """Mark an alert as processed with optional user feedback"""
        try:
            await db_manager.execute('''
                UPDATE trend_opportunities 
                SET processed = TRUE, 
                    user_feedback = $2,
                    feedback_at = NOW()
                WHERE id = $1
            ''', alert_id, user_feedback)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark alert {alert_id} as processed: {e}")
            return False
    
    # ============================================================================
    # ANALYTICS AND REPORTING
    # ============================================================================
    
    async def get_business_area_summary(self, business_area: str, days: int = 7) -> TrendSummary:
        """Get comprehensive summary for a business area"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            cutoff_date = date.today() - timedelta(days=days)
            
            # Total keywords monitored
            total_keywords = await conn.fetchval('''
                SELECT COUNT(DISTINCT keyword) 
                FROM trend_monitoring 
                WHERE business_area = $1 AND trend_date >= $2
            ''', business_area, cutoff_date)
            
            # Trending keywords (score >= 20)
            trending_count = await conn.fetchval('''
                SELECT COUNT(DISTINCT keyword) 
                FROM trend_monitoring 
                WHERE business_area = $1 AND trend_date >= $2 AND trend_score >= 20
            ''', business_area, cutoff_date)
            
            # High priority alerts
            high_priority_alerts = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM trend_opportunities 
                WHERE business_area = $1 AND urgency_level = 'high' 
                AND created_at >= $2
            ''', business_area, datetime.now() - timedelta(days=days))
            
            # Recent opportunities
            recent_opportunities = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM trend_opportunities 
                WHERE business_area = $1 AND created_at >= $2
            ''', business_area, datetime.now() - timedelta(days=days))
            
            # Average trend score
            avg_score = await conn.fetchval('''
                SELECT COALESCE(AVG(trend_score), 0) 
                FROM trend_monitoring 
                WHERE business_area = $1 AND trend_date >= $2
            ''', business_area, cutoff_date) or 0.0
            
            # Top keywords
            top_keywords_rows = await conn.fetch('''
                SELECT keyword, MAX(trend_score) as max_score
                FROM trend_monitoring 
                WHERE business_area = $1 AND trend_date >= $2
                GROUP BY keyword
                ORDER BY max_score DESC
                LIMIT 10
            ''', business_area, cutoff_date)
            
            top_keywords = [(row['keyword'], row['max_score']) for row in top_keywords_rows]
            
            return TrendSummary(
                business_area=business_area,
                total_keywords_monitored=total_keywords or 0,
                trending_keywords=trending_count or 0,
                high_priority_alerts=high_priority_alerts or 0,
                recent_opportunities=recent_opportunities or 0,
                avg_trend_score=float(avg_score),
                top_keywords=top_keywords
            )
            
        except Exception as e:
            logger.error(f"Failed to get business area summary: {e}")
            return TrendSummary(
                business_area=business_area,
                total_keywords_monitored=0,
                trending_keywords=0,
                high_priority_alerts=0,
                recent_opportunities=0,
                avg_trend_score=0.0,
                top_keywords=[]
            )
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_trend_momentum_analysis(self, keyword: str, business_area: str,
                                        days: int = 14) -> Dict[str, Any]:
        """Analyze trend momentum for a specific keyword"""
        try:
            query = '''
                SELECT trend_date, trend_score, trend_momentum, regional_score
                FROM trend_monitoring 
                WHERE keyword = $1 AND business_area = $2 
                AND trend_date >= $3
                ORDER BY trend_date ASC
            '''
            
            rows = await db_manager.fetch_all(
                query, keyword, business_area,
                date.today() - timedelta(days=days)
            )
            
            if not rows:
                return {}
            
            # Calculate momentum metrics
            scores = [row['trend_score'] for row in rows if row['trend_score'] is not None]
            
            if len(scores) < 2:
                return {
                    'keyword': keyword,
                    'data_points': len(rows),
                    'trend': 'insufficient_data'
                }
            
            # Calculate trend direction
            recent_avg = sum(scores[-3:]) / len(scores[-3:]) if len(scores) >= 3 else scores[-1]
            older_avg = sum(scores[:3]) / len(scores[:3]) if len(scores) >= 3 else scores[0]
            
            change_percent = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
            
            if change_percent > 25:
                trend_direction = 'strong_growth'
            elif change_percent > 10:
                trend_direction = 'growth'
            elif change_percent < -25:
                trend_direction = 'strong_decline'
            elif change_percent < -10:
                trend_direction = 'decline'
            else:
                trend_direction = 'stable'
            
            return {
                'keyword': keyword,
                'business_area': business_area,
                'data_points': len(rows),
                'max_score': max(scores),
                'min_score': min(scores),
                'current_score': scores[-1],
                'trend_direction': trend_direction,
                'change_percent': round(change_percent, 2),
                'recent_average': round(recent_avg, 2),
                'volatility': round(max(scores) - min(scores), 2),
                'momentum_history': [
                    {
                        'date': row['trend_date'].isoformat(),
                        'score': row['trend_score'],
                        'momentum': row['trend_momentum']
                    }
                    for row in rows
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get trend momentum analysis: {e}")
            return {}
    
    # ============================================================================
    # USER FEEDBACK AND TRAINING
    # ============================================================================
    
    async def record_user_feedback(self, alert_id: str, feedback: str,
                                 feedback_details: Optional[str] = None) -> bool:
        """Record user feedback for training the system"""
        conn = None
        try:
            # Validate feedback
            valid_feedback = ['good_match', 'bad_match', 'relevant', 'irrelevant']
            if feedback not in valid_feedback:
                logger.warning(f"Invalid feedback value: {feedback}")
                return False
            
            conn = await db_manager.get_connection()
            
            await conn.execute('''
                UPDATE trend_opportunities 
                SET user_feedback = $2,
                    feedback_at = NOW(),
                    processed = TRUE
                WHERE id = $1
            ''', alert_id, feedback)
            
            # Optionally store detailed feedback in a separate training table
            if feedback_details:
                await conn.execute('''
                    INSERT INTO trend_feedback_training 
                    (alert_id, feedback_type, feedback_details, created_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT DO NOTHING
                ''', alert_id, feedback, feedback_details)
            
            logger.info(f"Recorded {feedback} feedback for alert {alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return False
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_feedback_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics for system improvement"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Overall feedback counts
            feedback_counts = await conn.fetch('''
                SELECT user_feedback, COUNT(*) as count
                FROM trend_opportunities 
                WHERE user_feedback IS NOT NULL AND created_at >= $1
                GROUP BY user_feedback
            ''', cutoff_date)
            
            # Feedback by business area
            business_feedback = await conn.fetch('''
                SELECT business_area, user_feedback, COUNT(*) as count
                FROM trend_opportunities 
                WHERE user_feedback IS NOT NULL AND created_at >= $1
                GROUP BY business_area, user_feedback
                ORDER BY business_area, user_feedback
            ''', cutoff_date)
            
            # Accuracy by urgency level
            urgency_feedback = await conn.fetch('''
                SELECT urgency_level, user_feedback, COUNT(*) as count
                FROM trend_opportunities 
                WHERE user_feedback IS NOT NULL AND created_at >= $1
                GROUP BY urgency_level, user_feedback
                ORDER BY urgency_level, user_feedback
            ''', cutoff_date)
            
            return {
                'feedback_period_days': days,
                'overall_feedback': {row['user_feedback']: row['count'] for row in feedback_counts},
                'business_area_feedback': [dict(row) for row in business_feedback],
                'urgency_level_feedback': [dict(row) for row in urgency_feedback]
            }
            
        except Exception as e:
            logger.error(f"Failed to get feedback statistics: {e}")
            return {
                'feedback_period_days': days,
                'overall_feedback': {},
                'business_area_feedback': [],
                'urgency_level_feedback': []
            }
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    async def _calculate_momentum_change(self, conn,
                                       keyword: str, business_area: str) -> Optional[float]:
        """Calculate momentum change percentage (uses passed connection)"""
        try:
            # Get last two trend scores
            rows = await conn.fetch('''
                SELECT trend_score 
                FROM trend_monitoring 
                WHERE keyword = $1 AND business_area = $2 
                AND trend_score IS NOT NULL
                ORDER BY trend_date DESC, created_at DESC
                LIMIT 2
            ''', keyword, business_area)
            
            if len(rows) >= 2:
                current = rows[0]['trend_score']
                previous = rows[1]['trend_score']
                
                if previous > 0:
                    return round((current - previous) / previous * 100, 2)
            
            return None
            
        except Exception:
            return None
    
    async def cleanup_old_data(self, days_to_keep: int = 90) -> int:
        """Clean up old trend data to manage database size"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            cutoff_date = date.today() - timedelta(days=days_to_keep)
            
            # Delete old trend monitoring data
            deleted_trends = await conn.fetchval('''
                WITH deleted AS (
                    DELETE FROM trend_monitoring 
                    WHERE trend_date < $1
                    RETURNING 1
                )
                SELECT COUNT(*) FROM deleted
            ''', cutoff_date)
            
            # Keep opportunity alerts longer (1 year)
            alert_cutoff = datetime.now() - timedelta(days=365)
            deleted_alerts = await conn.fetchval('''
                WITH deleted AS (
                    DELETE FROM trend_opportunities 
                    WHERE created_at < $1 AND processed = TRUE
                    RETURNING 1
                )
                SELECT COUNT(*) FROM deleted
            ''', alert_cutoff)
            
            total_deleted = (deleted_trends or 0) + (deleted_alerts or 0)
            logger.info(f"Cleaned up {total_deleted} old records")
            
            return total_deleted
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return 0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health and system status"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Check table existence and basic stats
            tables_check = await conn.fetch('''
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name IN ('trend_monitoring', 'trend_opportunities')
                AND table_schema = 'public'
            ''')
            
            # Get recent activity
            recent_trends = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM trend_monitoring 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            ''')
            
            recent_alerts = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM trend_opportunities 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            ''')
            
            unprocessed_alerts = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM trend_opportunities 
                WHERE processed = FALSE
            ''')
            
            return {
                'database_connected': True,
                'tables_exist': len(tables_check) == 2,
                'recent_trends_24h': recent_trends or 0,
                'recent_alerts_24h': recent_alerts or 0,
                'unprocessed_alerts': unprocessed_alerts or 0,
                'last_check': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'database_connected': False,
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }
        finally:
            if conn:
                await db_manager.release_connection(conn)


# ============================================================================
# SINGLETON GETTER
# ============================================================================

_trends_database: Optional[TrendsDatabase] = None


def get_trends_database() -> TrendsDatabase:
    """Get or create the TrendsDatabase singleton instance"""
    global _trends_database
    if _trends_database is None:
        _trends_database = TrendsDatabase()
    return _trends_database
