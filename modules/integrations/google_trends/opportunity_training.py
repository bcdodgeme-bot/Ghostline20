#!/usr/bin/env python3
"""
Opportunity Training Interface for Google Trends
Presents unprocessed opportunities for Good Match/Bad Match feedback

This creates the training loop for improving trend detection accuracy.
"""

import asyncio
import asyncpg
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class OpportunityTraining:
    """Manages the training interface for opportunity feedback"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
    
    def _make_timezone_aware(self, dt: datetime) -> datetime:
        """Make a datetime timezone-aware if it isn't already"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    async def get_pending_opportunities(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get opportunities waiting for training feedback"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            query = '''
                SELECT id, keyword, business_area, opportunity_type, urgency_level,
                       trend_score_at_alert, optimal_content_window_end,
                       created_at
                FROM trend_opportunities 
                WHERE user_feedback IS NULL 
                AND processed = FALSE
                ORDER BY 
                    CASE urgency_level 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    created_at DESC
                LIMIT $1
            '''
            
            rows = await conn.fetch(query, limit)
            
            opportunities = []
            now = datetime.now(timezone.utc)
            
            for row in rows:
                # Make both datetimes timezone-aware for comparison
                window_end = self._make_timezone_aware(row['optimal_content_window_end'])
                
                # Check if window is still active
                window_active = window_end > now
                
                opportunities.append({
                    'id': str(row['id']),
                    'keyword': row['keyword'],
                    'business_area': row['business_area'],
                    'opportunity_type': row['opportunity_type'],
                    'urgency_level': row['urgency_level'],
                    'trend_score': row['trend_score_at_alert'],
                    'created_at': row['created_at'],
                    'window_active': window_active,
                    'time_left': (window_end - now).total_seconds() / 3600 if window_active else 0
                })
            
            return opportunities
            
        finally:
            await conn.close()
    
    async def submit_feedback(self, opportunity_id: str, feedback: str,
                            feedback_details: Optional[str] = None) -> bool:
        """Submit Good Match/Bad Match feedback"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Validate feedback
            valid_feedback = ['good_match', 'bad_match']
            if feedback not in valid_feedback:
                return False
            
            # Update the opportunity with feedback
            await conn.execute('''
                UPDATE trend_opportunities 
                SET user_feedback = $2,
                    feedback_at = NOW(),
                    processed = TRUE
                WHERE id = $1
            ''', opportunity_id, feedback)
            
            # Store detailed feedback if provided
            if feedback_details:
                await conn.execute('''
                    INSERT INTO trend_feedback_training 
                    (alert_id, feedback_type, feedback_details, created_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT DO NOTHING
                ''', opportunity_id, feedback, feedback_details)
            
            logger.info(f"Recorded {feedback} feedback for opportunity {opportunity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")
            return False
        finally:
            await conn.close()
    
    async def get_training_stats(self) -> Dict[str, Any]:
        """Get training statistics"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Overall feedback counts
            feedback_stats = await conn.fetch('''
                SELECT user_feedback, COUNT(*) as count
                FROM trend_opportunities 
                WHERE user_feedback IS NOT NULL
                GROUP BY user_feedback
            ''')
            
            # Pending training count
            pending_count = await conn.fetchval('''
                SELECT COUNT(*) FROM trend_opportunities 
                WHERE user_feedback IS NULL AND processed = FALSE
            ''') or 0
            
            # Business area breakdown
            business_stats = await conn.fetch('''
                SELECT business_area, user_feedback, COUNT(*) as count
                FROM trend_opportunities 
                WHERE user_feedback IS NOT NULL
                GROUP BY business_area, user_feedback
                ORDER BY business_area, user_feedback
            ''')
            
            return {
                'feedback_distribution': {row['user_feedback']: row['count'] for row in feedback_stats},
                'pending_training': pending_count,
                'business_area_feedback': [dict(row) for row in business_stats],
                'total_trained': sum(row['count'] for row in feedback_stats)
            }
            
        finally:
            await conn.close()

# Create feedback training table if it doesn't exist
async def ensure_training_table_exists(database_url: str):
    """Ensure the feedback training table exists"""
    conn = await asyncpg.connect(database_url)
    
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS trend_feedback_training (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                alert_id UUID NOT NULL,
                feedback_type VARCHAR(20) NOT NULL,
                feedback_details TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        ''')
    finally:
        await conn.close()

async def test_training_interface():
    """Test the training interface"""
    import os
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
    
    # Ensure training table exists
    await ensure_training_table_exists(database_url)
    
    trainer = OpportunityTraining(database_url)
    
    print("🎯 TRAINING INTERFACE TEST")
    print("=" * 30)
    
    # Get pending opportunities
    opportunities = await trainer.get_pending_opportunities(limit=3)
    print(f"\nPending opportunities: {len(opportunities)}")
    
    for i, opp in enumerate(opportunities, 1):
        print(f"\n{i}. {opp['keyword']} ({opp['business_area']})")
        print(f"   Type: {opp['opportunity_type']}, Urgency: {opp['urgency_level']}")
        print(f"   Score: {opp['trend_score']}")
        print(f"   Window: {'Active' if opp['window_active'] else 'Expired'}")
        if opp['window_active']:
            print(f"   Time left: {opp['time_left']:.1f} hours")
    
    # Get training stats
    stats = await trainer.get_training_stats()
    print(f"\nTraining stats:")
    print(f"   Total trained: {stats['total_trained']}")
    print(f"   Pending: {stats['pending_training']}")
    print(f"   Feedback distribution: {stats['feedback_distribution']}")

if __name__ == "__main__":
    asyncio.run(test_training_interface())
