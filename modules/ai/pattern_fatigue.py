# modules/ai/pattern_fatigue.py
"""
Pattern Fatigue Detection and Filtering Module
The "Stop Being Annoying" system for Syntax Prime

This module tracks repetitive patterns in AI responses and suppresses them
when they become overused or when the user complains about them.
"""

import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json

from ..core.database import db_manager

logger = logging.getLogger(__name__)

class PatternFatigueTracker:
    """
    Tracks and manages repetitive patterns in AI responses to prevent annoyance
    """
    
    def __init__(self):
        self.duplicate_patterns = [
            # The exact annoying phrases Syntax uses
            r"I see you sent that twice",
            r"why are you posting.*same.*twice",
            r"Well, well, well.*if it isn't.*twice",
            r"Did.*did you just.*INTENTIONALLY.*twice",
            r"I see what you did there with.*double",
            r"I'm pretending not to notice",
            r"for someone who told me to ignore.*you're really testing",
            r"I have to appreciate the meta-humor",
            r"Hello.*ed.*twice",
            r"rapid succession",
            r"duplicate.*handling",
            r"seeing double",
        ]
        
        self.time_joke_patterns = [
            # 2am coding jokes that should check actual time
            r"2am.*cod(ing|e)",
            r"why.*2am",
            r"coding.*night",
            r"up so late",
            r"late.*night.*session",
            r"coding.*adventure.*2am",
            r"debugging.*2am",
            r"why did you do this at 2am",
        ]
        
        self.meta_humor_patterns = [
            # AI self-awareness patterns (allowed but track for novelty)
            r"I.*AI.*consciousness",
            r"digital.*being",
            r"I.*robot",
            r"my.*circuits",
            r"as an AI",
            r"artificial.*intelligence",
            r"I.*code",
        ]
        
    async def should_suppress_response(self, 
                                     response: str, 
                                     user_id: str, 
                                     current_timestamp: datetime = None) -> Tuple[bool, str]:
        """
        Check if response contains patterns that should be suppressed
        
        Returns:
            (should_suppress: bool, reason: str)
        """
        
        if current_timestamp is None:
            current_timestamp = datetime.now()
        
        # Check duplicate callouts (zero tolerance)
        if await self._contains_duplicate_callout(response):
            if await self._is_pattern_on_cooldown(user_id, 'duplicate_callouts'):
                return True, "duplicate_callouts_on_cooldown"
            
            # Check if user has complained about duplicates
            if await self._user_complained_about_pattern(user_id, 'duplicate_callouts'):
                return True, "user_complained_about_duplicates"
            
            # Always suppress duplicate callouts (zero tolerance policy)
            await self._record_pattern_usage(user_id, 'duplicate_callouts', response)
            return True, "duplicate_callouts_zero_tolerance"
        
        # Check 2am jokes with timestamp awareness
        if await self._contains_time_joke(response):
            current_hour = current_timestamp.hour
            
            # If it's actually normal business hours, suppress the 2am joke
            if 9 <= current_hour <= 21:  # 9am to 9pm
                await self._record_pattern_usage(user_id, '2am_jokes', response)
                return True, "2am_joke_during_business_hours"
            
            # Check if 2am jokes are on cooldown
            if await self._is_pattern_on_cooldown(user_id, '2am_jokes'):
                return True, "2am_jokes_on_cooldown"
            
            # Check weekly usage limit (max 2 per week)
            weekly_usage = await self._get_weekly_usage_count(user_id, '2am_jokes')
            if weekly_usage >= 2:
                # Put on cooldown for 15 days
                await self._set_pattern_cooldown(user_id, '2am_jokes', days=15)
                return True, "2am_jokes_weekly_limit_exceeded"
        
        # Check meta humor for novelty (unlimited but track for 10-day uniqueness)
        if await self._contains_meta_humor(response):
            # Check if this specific meta joke was used recently
            if await self._was_similar_joke_used_recently(user_id, 'meta_humor', response, days=10):
                return True, "meta_humor_not_novel_enough"
        
        return False, "pattern_check_passed"
    
    async def filter_response(self, 
                            response: str, 
                            user_id: str, 
                            current_timestamp: datetime = None) -> str:
        """
        Filter out annoying patterns from response and return cleaned version
        """
        
        should_suppress, reason = await self.should_suppress_response(
            response, user_id, current_timestamp
        )
        
        if not should_suppress:
            return response
        
        logger.info(f"Filtering response due to: {reason}")
        
        # Remove duplicate callout patterns
        filtered_response = response
        for pattern in self.duplicate_patterns:
            filtered_response = re.sub(pattern, "", filtered_response, flags=re.IGNORECASE)
        
        # Remove 2am joke patterns if during business hours
        if "2am_joke" in reason:
            for pattern in self.time_joke_patterns:
                filtered_response = re.sub(pattern, "", filtered_response, flags=re.IGNORECASE)
        
        # Clean up any resulting formatting issues
        filtered_response = self._clean_filtered_response(filtered_response)
        
        # If response becomes too short or empty, provide a minimal replacement
        if len(filtered_response.strip()) < 20:
            filtered_response = self._get_minimal_helpful_response()
        
        return filtered_response
    
    async def record_user_complaint(self, 
                                  user_id: str, 
                                  pattern_type: str, 
                                  complaint_text: str) -> bool:
        """
        Record when user complains about a specific pattern
        """
        
        try:
            # Set immediate cooldown when user complains
            cooldown_days = 14  # 2 weeks for user complaints
            cooldown_until = datetime.now() + timedelta(days=cooldown_days)
            
            query = """
            INSERT INTO pattern_fatigue_tracker 
            (user_id, pattern_type, pattern_content, user_complained, 
             complaint_timestamp, complaint_context, cooldown_until, occurrences)
            VALUES ($1, $2, $3, $4, NOW(), $5, $6, 1)
            ON CONFLICT (user_id, pattern_type, pattern_content) 
            DO UPDATE SET 
                user_complained = TRUE,
                complaint_timestamp = NOW(),
                complaint_context = $5,
                cooldown_until = $6,
                updated_at = NOW()
            """
            
            await db_manager.execute(query, 
                                   user_id, 
                                   pattern_type, 
                                   f"User complaint: {pattern_type}",
                                   True,
                                   complaint_text,
                                   cooldown_until)
            
            logger.info(f"Recorded user complaint about {pattern_type} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to record user complaint: {e}")
            return False
    
    # Private helper methods
    
    async def _contains_duplicate_callout(self, response: str) -> bool:
        """Check if response contains duplicate detection commentary"""
        response_lower = response.lower()
        
        for pattern in self.duplicate_patterns:
            if re.search(pattern, response_lower, re.IGNORECASE):
                return True
        return False
    
    async def _contains_time_joke(self, response: str) -> bool:
        """Check if response contains 2am/time-based coding jokes"""
        response_lower = response.lower()
        
        for pattern in self.time_joke_patterns:
            if re.search(pattern, response_lower, re.IGNORECASE):
                return True
        return False
    
    async def _contains_meta_humor(self, response: str) -> bool:
        """Check if response contains AI self-awareness humor"""
        response_lower = response.lower()
        
        for pattern in self.meta_humor_patterns:
            if re.search(pattern, response_lower, re.IGNORECASE):
                return True
        return False
    
    async def _is_pattern_on_cooldown(self, user_id: str, pattern_type: str) -> bool:
        """Check if a pattern is currently on cooldown"""
        
        try:
            query = """
            SELECT EXISTS (
                SELECT 1 FROM pattern_fatigue_tracker
                WHERE user_id = $1
                AND pattern_type = $2
                AND cooldown_until IS NOT NULL 
                AND cooldown_until > NOW()
            )
            """
            
            result = await db_manager.fetch_one(query, user_id, pattern_type)
            return result['exists'] if result else False
            
        except Exception as e:
            logger.error(f"Failed to check pattern cooldown: {e}")
            return False
    
    async def _user_complained_about_pattern(self, user_id: str, pattern_type: str) -> bool:
        """Check if user has complained about this pattern recently"""
        
        try:
            query = """
            SELECT EXISTS (
                SELECT 1 FROM pattern_fatigue_tracker
                WHERE user_id = $1
                AND pattern_type = $2
                AND user_complained = TRUE
                AND complaint_timestamp > NOW() - INTERVAL '30 days'
            )
            """
            
            result = await db_manager.fetch_one(query, user_id, pattern_type)
            return result['exists'] if result else False
            
        except Exception as e:
            logger.error(f"Failed to check user complaints: {e}")
            return False
    
    async def _get_weekly_usage_count(self, user_id: str, pattern_type: str) -> int:
        """Get usage count for pattern in the last 7 days"""
        
        try:
            query = """
            SELECT COALESCE(SUM(occurrences), 0) as usage_count
            FROM pattern_fatigue_tracker
            WHERE user_id = $1
            AND pattern_type = $2
            AND last_used >= NOW() - INTERVAL '7 days'
            AND (cooldown_until IS NULL OR cooldown_until <= NOW())
            """
            
            result = await db_manager.fetch_one(query, user_id, pattern_type)
            return result['usage_count'] if result else 0
            
        except Exception as e:
            logger.error(f"Failed to get weekly usage count: {e}")
            return 0
    
    async def _record_pattern_usage(self, user_id: str, pattern_type: str, content: str):
        """Record usage of a pattern"""
        
        try:
            query = """
            INSERT INTO pattern_fatigue_tracker 
            (user_id, pattern_type, pattern_content, occurrences, last_used)
            VALUES ($1, $2, $3, 1, NOW())
            ON CONFLICT (user_id, pattern_type, pattern_content) 
            DO UPDATE SET 
                occurrences = pattern_fatigue_tracker.occurrences + 1,
                last_used = NOW(),
                updated_at = NOW()
            """
            
            # Truncate content for storage
            truncated_content = content[:200] + "..." if len(content) > 200 else content
            
            await db_manager.execute(query, user_id, pattern_type, truncated_content)
            
        except Exception as e:
            logger.error(f"Failed to record pattern usage: {e}")
    
    async def _set_pattern_cooldown(self, user_id: str, pattern_type: str, days: int):
        """Set a cooldown period for a pattern"""
        
        try:
            cooldown_until = datetime.now() + timedelta(days=days)
            
            query = """
            INSERT INTO pattern_fatigue_tracker 
            (user_id, pattern_type, pattern_content, cooldown_until, occurrences)
            VALUES ($1, $2, $3, $4, 0)
            ON CONFLICT (user_id, pattern_type, pattern_content) 
            DO UPDATE SET 
                cooldown_until = $4,
                updated_at = NOW()
            """
            
            await db_manager.execute(query, 
                                   user_id, 
                                   pattern_type, 
                                   f"Auto-cooldown: {pattern_type}",
                                   cooldown_until)
            
            logger.info(f"Set {days}-day cooldown for {pattern_type} for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to set pattern cooldown: {e}")
    
    async def _was_similar_joke_used_recently(self, 
                                            user_id: str, 
                                            pattern_type: str, 
                                            content: str, 
                                            days: int) -> bool:
        """Check if a similar joke was used recently (for novelty requirement)"""
        
        try:
            # Simple similarity check - could be enhanced with more sophisticated matching
            query = """
            SELECT EXISTS (
                SELECT 1 FROM pattern_fatigue_tracker
                WHERE user_id = $1
                AND pattern_type = $2
                AND last_used >= NOW() - INTERVAL '%s days'
                AND pattern_content ILIKE '%s'
            """ % (days, '%' + content[:50] + '%')
            
            result = await db_manager.fetch_one(query, user_id, pattern_type)
            return result['exists'] if result else False
            
        except Exception as e:
            logger.error(f"Failed to check joke novelty: {e}")
            return False
    
    def _clean_filtered_response(self, response: str) -> str:
        """Clean up response after filtering out patterns"""
        
        # Remove double spaces, fix punctuation, etc.
        cleaned = re.sub(r'\s+', ' ', response)  # Multiple spaces -> single space
        cleaned = re.sub(r'\s+([.!?])', r'\1', cleaned)  # Space before punctuation
        cleaned = re.sub(r'([.!?])\s*([.!?])', r'\1', cleaned)  # Double punctuation
        cleaned = cleaned.strip()
        
        return cleaned
    
    def _get_minimal_helpful_response(self) -> str:
        """Get a minimal helpful response when filtering makes response too short"""
        
        minimal_responses = [
            "Got it! Let me help with that.",
            "I understand. How can I assist?",
            "Sure thing! What do you need?",
            "I'm on it. What's the next step?",
            "Understood. Let's tackle this.",
        ]
        
        import random
        return random.choice(minimal_responses)

# Global pattern fatigue tracker
_pattern_fatigue_tracker = None

def get_pattern_fatigue_tracker() -> PatternFatigueTracker:
    """Get the global pattern fatigue tracker"""
    global _pattern_fatigue_tracker
    if _pattern_fatigue_tracker is None:
        _pattern_fatigue_tracker = PatternFatigueTracker()
    return _pattern_fatigue_tracker

# Chat command handlers for user complaints
async def handle_duplicate_complaint(user_id: str, complaint_text: str) -> str:
    """Handle user complaint about duplicate callouts"""
    
    tracker = get_pattern_fatigue_tracker()
    success = await tracker.record_user_complaint(user_id, 'duplicate_callouts', complaint_text)
    
    if success:
        return "✅ Got it! I'll stop mentioning duplicate messages for the next 2 weeks."
    else:
        return "❌ Sorry, I had trouble recording that. Can you try again?"

async def handle_time_joke_complaint(user_id: str, complaint_text: str) -> str:
    """Handle user complaint about 2am jokes"""
    
    tracker = get_pattern_fatigue_tracker()
    success = await tracker.record_user_complaint(user_id, '2am_jokes', complaint_text)
    
    if success:
        return "✅ Roger that! No more 2am coding jokes for the next 2 weeks."
    else:
        return "❌ Sorry, I had trouble recording that. Can you try again?"

# Debug and monitoring functions
async def get_pattern_stats(user_id: str) -> Dict[str, Any]:
    """Get pattern usage statistics for debugging"""
    
    try:
        query = """
        SELECT 
            pattern_type,
            COUNT(*) as total_occurrences,
            SUM(occurrences) as total_usage,
            MAX(last_used) as last_used,
            MAX(cooldown_until) as cooldown_until,
            BOOL_OR(user_complained) as user_has_complained
        FROM pattern_fatigue_tracker
        WHERE user_id = $1
        GROUP BY pattern_type
        ORDER BY pattern_type
        """
        
        results = await db_manager.fetch_all(query, user_id)
        
        stats = {}
        for row in results:
            stats[row['pattern_type']] = {
                'total_occurrences': row['total_occurrences'],
                'total_usage': row['total_usage'],
                'last_used': row['last_used'].isoformat() if row['last_used'] else None,
                'on_cooldown': row['cooldown_until'] and row['cooldown_until'] > datetime.now(),
                'cooldown_until': row['cooldown_until'].isoformat() if row['cooldown_until'] else None,
                'user_complained': row['user_has_complained']
            }
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get pattern stats: {e}")
        return {}

if __name__ == "__main__":
    # Test the pattern detection
    async def test_patterns():
        print("🧪 Testing Pattern Fatigue Detection")
        
        tracker = PatternFatigueTracker()
        test_user_id = "test-user-123"
        
        test_responses = [
            "I see you sent that twice - let me help anyway.",
            "Why are you coding at 2am again? Here's the solution.",
            "As an AI, I find your database errors fascinating.",
            "Let me help you debug this issue.",
        ]
        
        for response in test_responses:
            should_suppress, reason = await tracker.should_suppress_response(
                response, test_user_id
            )
            print(f"Response: {response[:50]}...")
            print(f"  Suppress: {should_suppress} ({reason})")
            
            if should_suppress:
                filtered = await tracker.filter_response(response, test_user_id)
                print(f"  Filtered: {filtered}")
            print()
    
    asyncio.run(test_patterns())