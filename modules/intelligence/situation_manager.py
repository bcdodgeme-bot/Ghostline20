# modules/intelligence/situation_manager.py
"""
Situation Manager for Syntax Prime V2 Intelligence Hub
Handles database operations, lifecycle management, and learning from user responses

Responsibilities:
- Store detected situations in database
- Track user responses (acted, dismissed, snoozed)
- Expire old situations
- Generate daily digests
- Learn from patterns in user responses
- Check if patterns qualify for auto-execution

Created: 10/22/25
Updated: 12/11/25 - Added singleton pattern, auto-execution support
"""

import logging
from uuid import UUID
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json

from ...core.database import db_manager

logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS
#===============================================================================

# Auto-execution thresholds - pattern must meet ALL of these
AUTO_EXECUTE_MIN_APPROVALS = 5      # Minimum times user must have approved
AUTO_EXECUTE_MIN_ACTION_RATE = 0.8  # 80% action rate required
AUTO_EXECUTE_MIN_CONFIDENCE = 0.6   # Minimum average confidence score


#===============================================================================
# SINGLETON INSTANCE
#===============================================================================

_manager_instance: Optional['SituationManager'] = None


def get_situation_manager() -> 'SituationManager':
    """Get singleton SituationManager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SituationManager()
    return _manager_instance


#===============================================================================
# SITUATION MANAGER - Database operations and lifecycle management
#===============================================================================

class SituationManager:
    """
    Manages the full lifecycle of situations from creation to expiry.
    
    This is the "memory" of the intelligence system - it remembers what
    situations were detected, how you responded, and learns from patterns.
    """
    
    def __init__(self):
        """Initialize with centralized db_manager"""
        self.db = db_manager
        self.manager_name = "SituationManager"
    
    #===========================================================================
    # AUTO-EXECUTION CHECK - New proactive feature
    #===========================================================================
    
    async def should_auto_execute(
        self,
        situation_type: str,
        situation_context: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if this situation pattern qualifies for automatic execution.
        
        A pattern qualifies when:
        - User has acted on it 5+ times
        - Action rate is 80%+
        - Average confidence is 60%+
        - can_act_on flag is True
        
        Args:
            situation_type: Type of situation
            situation_context: Context data for pattern extraction
            
        Returns:
            Tuple of (should_auto_execute: bool, learning_record: dict or None)
        """
        try:
            # Extract the pattern key for this situation
            pattern_key = self._extract_pattern_key(situation_type, situation_context)
            
            # Query the learning record
            query = """
                SELECT 
                    id,
                    pattern_key,
                    total_occurrences,
                    acted_count,
                    dismissed_count,
                    action_rate,
                    avg_confidence,
                    can_act_on,
                    last_occurrence
                FROM contextual_learnings
                WHERE situation_type = $1
                AND pattern_key = $2
            """
            
            result = await self.db.fetch_one(query, situation_type, pattern_key)
            
            if not result:
                logger.debug(f"No learning record for {situation_type}/{pattern_key} - cannot auto-execute")
                return False, None
            
            # Check if it meets auto-execute criteria
            acted_count = result['acted_count'] or 0
            action_rate = float(result['action_rate']) if result['action_rate'] else 0
            avg_confidence = float(result['avg_confidence']) if result['avg_confidence'] else 0
            can_act_on = result['can_act_on']
            
            learning_record = {
                'pattern_key': pattern_key,
                'acted_count': acted_count,
                'action_rate': action_rate,
                'avg_confidence': avg_confidence,
                'can_act_on': can_act_on
            }
            
            # All conditions must be met
            if (can_act_on and 
                acted_count >= AUTO_EXECUTE_MIN_APPROVALS and
                action_rate >= AUTO_EXECUTE_MIN_ACTION_RATE and
                avg_confidence >= AUTO_EXECUTE_MIN_CONFIDENCE):
                
                logger.info(f"✅ Pattern qualifies for auto-execute: {situation_type}/{pattern_key} "
                           f"(acted {acted_count}x, {action_rate:.0%} rate, {avg_confidence:.0%} confidence)")
                return True, learning_record
            
            # Log why it didn't qualify
            reasons = []
            if not can_act_on:
                reasons.append("can_act_on=False")
            if acted_count < AUTO_EXECUTE_MIN_APPROVALS:
                reasons.append(f"acted_count={acted_count} < {AUTO_EXECUTE_MIN_APPROVALS}")
            if action_rate < AUTO_EXECUTE_MIN_ACTION_RATE:
                reasons.append(f"action_rate={action_rate:.0%} < {AUTO_EXECUTE_MIN_ACTION_RATE:.0%}")
            if avg_confidence < AUTO_EXECUTE_MIN_CONFIDENCE:
                reasons.append(f"avg_confidence={avg_confidence:.0%} < {AUTO_EXECUTE_MIN_CONFIDENCE:.0%}")
            
            logger.debug(f"Pattern {pattern_key} doesn't qualify for auto-execute: {', '.join(reasons)}")
            return False, learning_record
            
        except Exception as e:
            logger.error(f"Error checking auto-execute eligibility: {e}", exc_info=True)
            return False, None
    
    async def get_auto_executable_patterns(self) -> List[Dict[str, Any]]:
        """
        Get all patterns that are eligible for auto-execution.
        
        Useful for showing user what actions Syntax will take automatically.
        
        Returns:
            List of learning records that have can_act_on=True
        """
        try:
            query = """
                SELECT 
                    situation_type,
                    pattern_key,
                    total_occurrences,
                    acted_count,
                    action_rate,
                    avg_confidence,
                    last_occurrence
                FROM contextual_learnings
                WHERE can_act_on = true
                AND acted_count >= $1
                AND action_rate >= $2
                AND avg_confidence >= $3
                ORDER BY acted_count DESC, action_rate DESC
            """
            
            results = await self.db.fetch_all(
                query,
                AUTO_EXECUTE_MIN_APPROVALS,
                AUTO_EXECUTE_MIN_ACTION_RATE,
                AUTO_EXECUTE_MIN_CONFIDENCE
            )
            
            patterns = []
            for row in results:
                patterns.append({
                    'situation_type': row['situation_type'],
                    'pattern_key': row['pattern_key'],
                    'total_occurrences': row['total_occurrences'],
                    'acted_count': row['acted_count'],
                    'action_rate': float(row['action_rate']),
                    'avg_confidence': float(row['avg_confidence']),
                    'last_occurrence': row['last_occurrence'].isoformat() if row['last_occurrence'] else None
                })
            
            logger.info(f"Found {len(patterns)} patterns eligible for auto-execution")
            return patterns
            
        except Exception as e:
            logger.error(f"Error getting auto-executable patterns: {e}", exc_info=True)
            return []
    
    #===========================================================================
    # CORE DATABASE OPERATIONS
    #===========================================================================
    
    async def create_situation(
        self, 
        situation,
        user_id: UUID
    ) -> Optional[UUID]:
        """
        Store a new situation in the database.
        
        Checks for duplicates first (same type + similar context within 24h)
        to avoid spamming the user with the same situation repeatedly.
        
        Args:
            situation: Situation object to store
            user_id: User this situation belongs to
            
        Returns:
            UUID of created situation, or None if duplicate/error
        """
        try:
            # Check for duplicate situations
            is_duplicate = await self._check_duplicate_situation(
                user_id=user_id,
                situation_type=situation.situation_type,
                context=situation.situation_context,
                lookback_hours=24
            )
            
            if is_duplicate:
                logger.debug(f"Skipping duplicate situation: {situation.situation_type}")
                return None
            
            # Insert into database
            query = """
                INSERT INTO contextual_situations (
                    id,
                    user_id,
                    situation_type,
                    situation_context,
                    confidence_score,
                    priority_score,
                    requires_action,
                    suggested_actions,
                    expires_at,
                    related_signal_ids,
                    detected_at,
                    user_response,
                    response_timestamp,
                    created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                )
                RETURNING id
            """
            
            # Convert related_signal_ids to string array
            signal_ids = [str(sid) for sid in situation.related_signal_ids]
            
            result = await self.db.fetch_one(
                query,
                situation.situation_id,
                user_id,
                situation.situation_type,
                json.dumps(situation.situation_context),
                situation.confidence_score,
                situation.priority_score,
                situation.requires_action,
                json.dumps(situation.suggested_actions),
                situation.expires_at,
                signal_ids,
                situation.detected_at,
                None,  # user_response initially null
                None,  # response_timestamp initially null
                datetime.utcnow()
            )
            
            logger.info(f"✅ Created situation: {situation.situation_type} (priority {situation.priority_score})")
            
            return result['id'] if result else None
            
        except Exception as e:
            logger.error(f"Error creating situation: {e}", exc_info=True)
            return None
    
    async def _check_duplicate_situation(
        self,
        user_id: UUID,
        situation_type: str,
        context: Dict[str, Any],
        lookback_hours: int = 24
    ) -> bool:
        """
        Check if a similar situation already exists recently.
        
        Compares situation type and key context fields to detect duplicates.
        
        Args:
            user_id: User ID
            situation_type: Type of situation
            context: Situation context dict
            lookback_hours: How far back to check for duplicates
            
        Returns:
            True if duplicate found, False otherwise
        """
        try:
            lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
            
            # Query for recent situations of same type
            query = """
                SELECT id, situation_context
                FROM contextual_situations
                WHERE user_id = $1
                AND situation_type = $2
                AND created_at >= $3
                ORDER BY created_at DESC
            """
            
            recent_situations = await self.db.fetch_all(
                query,
                user_id,
                situation_type,
                lookback_time
            )
            
            if not recent_situations:
                return False
            
            # Check if any of these are similar enough to be considered duplicates
            for existing in recent_situations:
                existing_context = json.loads(existing['situation_context']) if isinstance(existing['situation_context'], str) else existing['situation_context']
                
                # Compare key fields based on situation type
                if self._contexts_are_similar(situation_type, context, existing_context):
                    logger.debug(f"Found duplicate situation of type {situation_type}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking duplicate situation: {e}")
            return False  # On error, don't block creation
    
    def _contexts_are_similar(
        self,
        situation_type: str,
        context1: Dict[str, Any],
        context2: Dict[str, Any]
    ) -> bool:
        """
        Compare two situation contexts to determine if they're duplicates.
        
        Different situation types compare different fields.
        
        Args:
            situation_type: Type of situation being compared
            context1: First context
            context2: Second context
            
        Returns:
            True if contexts are similar enough to be duplicates
        """
        # Define key fields to compare for each situation type
        comparison_fields = {
            'post_meeting_action_required': ['meeting_id'],
            'deadline_approaching_prep_needed': ['event_id'],
            'trend_content_opportunity': ['keyword'],
            'email_priority_meeting_context': ['email_id', 'event_id'],
            'email_meeting_followup': ['email_id', 'meeting_id'],
            'conversation_trend_alignment': ['conversation_topic', 'trend_keyword'],
            'weather_impact_calendar': ['weather_condition'],
            'weather_health_impact': ['weather_condition'],
            'weather_emergency_alert': ['alert_description']
        }
        
        fields = comparison_fields.get(situation_type, [])
        
        if not fields:
            # If we don't know what to compare, be conservative and say they're different
            return False
        
        # Check if all key fields match
        for field in fields:
            val1 = context1.get(field)
            val2 = context2.get(field)
            
            # If either value is None/empty, NOT a duplicate
            if not val1 or not val2:
                return False
            
            # Compare actual values
            if val1 != val2:
                return False
        
        return True
    
    
    async def get_active_situations(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all active situations for a user (not expired, no response yet).
        
        Returns situations ordered by priority (highest first), then by
        detected time (newest first).
        
        Args:
            user_id: User to get situations for
            limit: Maximum number of situations to return
            
        Returns:
            List of situation dictionaries
        """
        try:
            query = """
                SELECT 
                    id,
                    situation_type,
                    situation_context,
                    confidence_score,
                    priority_score,
                    requires_action,
                    suggested_actions,
                    expires_at,
                    detected_at,
                    created_at
                FROM contextual_situations
                WHERE user_id = $1
                AND user_response IS NULL
                AND expires_at > NOW()
                ORDER BY priority_score DESC, detected_at DESC
                LIMIT $2
            """
            
            results = await self.db.fetch_all(query, user_id, limit)
            
            # Convert to list of dicts with parsed JSON
            situations = []
            for row in results:
                situation = {
                    'id': str(row['id']),
                    'situation_type': row['situation_type'],
                    'situation_context': json.loads(row['situation_context']) if isinstance(row['situation_context'], str) else row['situation_context'],
                    'confidence_score': float(row['confidence_score']),
                    'priority_score': row['priority_score'],
                    'requires_action': row['requires_action'],
                    'suggested_actions': json.loads(row['suggested_actions']) if isinstance(row['suggested_actions'], str) else row['suggested_actions'],
                    'expires_at': row['expires_at'].isoformat(),
                    'detected_at': row['detected_at'].isoformat(),
                    'created_at': row['created_at'].isoformat()
                }
                situations.append(situation)
            
            logger.info(f"Retrieved {len(situations)} active situations for user")
            return situations
            
        except Exception as e:
            logger.error(f"Error getting active situations: {e}", exc_info=True)
            return []
    
    
    async def record_user_response(
        self,
        situation_id: UUID,
        response: str,
        response_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record how the user responded to a situation.
        
        Response options:
        - 'acted': User took action on the situation
        - 'dismissed': User explicitly dismissed/ignored
        - 'snoozed': User postponed action
        - 'saved_for_later': User bookmarked for future reference
        - 'auto_executed': System automatically executed (new)
        
        This also triggers learning updates to improve future detections.
        
        Args:
            situation_id: UUID of the situation
            response: User's response type
            response_data: Optional additional data about the response
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate response type
            valid_responses = ['acted', 'dismissed', 'snoozed', 'saved_for_later', 'auto_executed']
            if response not in valid_responses:
                logger.error(f"Invalid response type: {response}")
                return False
            
            # Update the situation record
            query = """
                UPDATE contextual_situations
                SET 
                    user_response = $1,
                    response_timestamp = $2,
                    response_data = $3
                WHERE id = $4
                RETURNING situation_type, situation_context, confidence_score, priority_score
            """
            
            result = await self.db.fetch_one(
                query,
                response,
                datetime.utcnow(),
                json.dumps(response_data) if response_data else None,
                situation_id
            )
            
            if not result:
                logger.error(f"Situation {situation_id} not found")
                return False
            
            logger.info(f"✅ Recorded response '{response}' for situation {result['situation_type']}")
            
            # Update learning based on this response
            # Note: auto_executed counts as 'acted' for learning purposes
            learning_response = 'acted' if response == 'auto_executed' else response
            
            await self.update_learning_from_response(
                situation_type=result['situation_type'],
                situation_context=json.loads(result['situation_context']) if isinstance(result['situation_context'], str) else result['situation_context'],
                confidence_score=float(result['confidence_score']),
                priority_score=result['priority_score'],
                user_response=learning_response
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording user response: {e}", exc_info=True)
            return False
    
    
    async def get_situation_by_id(
        self,
        situation_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single situation by its ID.
        
        Useful for retrieving situation details when user clicks on notification.
        
        Args:
            situation_id: UUID of the situation
            
        Returns:
            Situation dictionary or None if not found
        """
        try:
            query = """
                SELECT 
                    id,
                    user_id,
                    situation_type,
                    situation_context,
                    confidence_score,
                    priority_score,
                    requires_action,
                    suggested_actions,
                    expires_at,
                    detected_at,
                    user_response,
                    response_timestamp,
                    response_data,
                    created_at
                FROM contextual_situations
                WHERE id = $1
            """
            
            result = await self.db.fetch_one(query, situation_id)
            
            if not result:
                return None
            
            # Convert to dict with parsed JSON
            situation = {
                'id': str(result['id']),
                'user_id': str(result['user_id']),
                'situation_type': result['situation_type'],
                'situation_context': json.loads(result['situation_context']) if isinstance(result['situation_context'], str) else result['situation_context'],
                'confidence_score': float(result['confidence_score']),
                'priority_score': result['priority_score'],
                'requires_action': result['requires_action'],
                'suggested_actions': json.loads(result['suggested_actions']) if isinstance(result['suggested_actions'], str) else result['suggested_actions'],
                'expires_at': result['expires_at'].isoformat(),
                'detected_at': result['detected_at'].isoformat(),
                'user_response': result['user_response'],
                'response_timestamp': result['response_timestamp'].isoformat() if result['response_timestamp'] else None,
                'response_data': json.loads(result['response_data']) if result['response_data'] else None,
                'created_at': result['created_at'].isoformat()
            }
            
            return situation
            
        except Exception as e:
            logger.error(f"Error getting situation by ID: {e}", exc_info=True)
            return None
    
    
    #===========================================================================
    # LIFECYCLE MANAGEMENT
    #===========================================================================
    
    async def expire_old_situations(self) -> int:
        """
        Mark situations as expired when they're past their expiry time.
        
        This doesn't DELETE data - it just marks situations that are no longer
        actionable (e.g., meeting already happened, UV alert is outdated) so they
        don't show in the active queue.
        
        All data is preserved in database for learning and historical analysis.
        
        Returns:
            Count of situations marked as expired
        """
        try:
            query = """
                UPDATE contextual_situations
                SET user_response = 'expired'
                WHERE user_response IS NULL
                AND expires_at < NOW()
                RETURNING id, situation_type
            """
            
            results = await self.db.fetch_all(query)
            
            expired_count = len(results)
            
            if expired_count > 0:
                logger.info(f"⏰ Marked {expired_count} situations as expired")
                
                # Log details for monitoring
                type_counts = {}
                for row in results:
                    situation_type = row['situation_type']
                    type_counts[situation_type] = type_counts.get(situation_type, 0) + 1
                
                logger.debug(f"Expired by type: {type_counts}")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Error expiring old situations: {e}", exc_info=True)
            return 0
    
    
    async def generate_daily_digest(
        self,
        user_id: UUID
    ) -> str:
        """
        Generate a daily digest of situations from the last 24 hours.
        
        Returns a formatted text summary suitable for Telegram notification.
        Shows:
        - Count of situations detected by type
        - Count of actions taken vs dismissed
        - Auto-executed actions
        - Trending patterns
        
        Args:
            user_id: User to generate digest for
            
        Returns:
            Formatted digest string
        """
        try:
            # Get all situations from last 24 hours
            query = """
                SELECT 
                    situation_type,
                    priority_score,
                    user_response,
                    detected_at
                FROM contextual_situations
                WHERE user_id = $1
                AND created_at >= NOW() - INTERVAL '24 hours'
                ORDER BY detected_at DESC
            """
            
            situations = await self.db.fetch_all(query, user_id)
            
            if not situations:
                return "📊 **Daily Intelligence Digest**\n\nNo situations detected in the last 24 hours.\nYour digital life is quiet! 🌙"
            
            # Count situations by type
            type_counts = {}
            response_counts = {
                'acted': 0,
                'dismissed': 0,
                'snoozed': 0,
                'saved_for_later': 0,
                'auto_executed': 0,
                'expired': 0,
                'pending': 0
            }
            priority_distribution = {
                'critical': 0,  # 9-10
                'high': 0,      # 7-8
                'medium': 0,    # 5-6
                'low': 0        # 1-4
            }
            
            for situation in situations:
                # Count by type
                situation_type = situation['situation_type']
                type_counts[situation_type] = type_counts.get(situation_type, 0) + 1
                
                # Count by response
                response = situation['user_response']
                if response:
                    response_counts[response] = response_counts.get(response, 0) + 1
                else:
                    response_counts['pending'] += 1
                
                # Count by priority
                priority = situation['priority_score']
                if priority >= 9:
                    priority_distribution['critical'] += 1
                elif priority >= 7:
                    priority_distribution['high'] += 1
                elif priority >= 5:
                    priority_distribution['medium'] += 1
                else:
                    priority_distribution['low'] += 1
            
            # Build digest message
            digest = "📊 **Daily Intelligence Digest**\n"
            digest += f"*{len(situations)} situations detected in the last 24 hours*\n\n"
            
            # Situations by type
            digest += "**Detected Situations:**\n"
            type_names = {
                'post_meeting_action_required': '📋 Meeting Actions',
                'deadline_approaching_prep_needed': '📅 Deadline Prep',
                'trend_content_opportunity': '📈 Trend Opportunities',
                'email_priority_meeting_context': '📧 Email-Meeting Links',
                'email_meeting_followup': '📧 Meeting Follow-ups',
                'conversation_trend_alignment': '💡 Topic Alignments',
                'weather_impact_calendar': '☀️ Weather Calendar Impact',
                'weather_health_impact': '⚠️ Weather Health Impact',
                'weather_emergency_alert': '🚨 Weather Emergencies'
            }
            
            for situation_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                friendly_name = type_names.get(situation_type, situation_type)
                digest += f"  • {friendly_name}: {count}\n"
            
            # Response summary
            digest += "\n**Your Actions:**\n"
            total_responded = response_counts['acted'] + response_counts['dismissed'] + response_counts['snoozed'] + response_counts['saved_for_later'] + response_counts['auto_executed']
            
            if total_responded > 0:
                digest += f"  • ✅ Acted on: {response_counts['acted']}\n"
                if response_counts['auto_executed'] > 0:
                    digest += f"  • 🤖 Auto-executed: {response_counts['auto_executed']}\n"
                if response_counts['dismissed'] > 0:
                    digest += f"  • ⏭️ Dismissed: {response_counts['dismissed']}\n"
                if response_counts['snoozed'] > 0:
                    digest += f"  • ⏰ Snoozed: {response_counts['snoozed']}\n"
                if response_counts['saved_for_later'] > 0:
                    digest += f"  • 🔖 Saved: {response_counts['saved_for_later']}\n"
            else:
                digest += "  • No actions taken yet\n"
            
            if response_counts['pending'] > 0:
                digest += f"  • ⏳ Still pending: {response_counts['pending']}\n"
            
            if response_counts['expired'] > 0:
                digest += f"  • ⏰ Expired: {response_counts['expired']}\n"
            
            # Priority breakdown
            digest += "\n**Priority Breakdown:**\n"
            if priority_distribution['critical'] > 0:
                digest += f"  • 🔴 Critical (9-10): {priority_distribution['critical']}\n"
            if priority_distribution['high'] > 0:
                digest += f"  • 🟠 High (7-8): {priority_distribution['high']}\n"
            if priority_distribution['medium'] > 0:
                digest += f"  • 🟡 Medium (5-6): {priority_distribution['medium']}\n"
            if priority_distribution['low'] > 0:
                digest += f"  • 🟢 Low (1-4): {priority_distribution['low']}\n"
            
            # Action rate (including auto-executed)
            if len(situations) > 0:
                total_actions = response_counts['acted'] + response_counts['auto_executed']
                action_rate = (total_actions / len(situations)) * 100
                digest += f"\n**Action Rate:** {action_rate:.0f}%"
                if action_rate >= 80:
                    digest += " 🌟 (Highly engaged!)"
                elif action_rate >= 50:
                    digest += " 👍 (Good engagement)"
                
                if response_counts['auto_executed'] > 0:
                    digest += f"\n_({response_counts['auto_executed']} handled automatically by Syntax)_"
            
            logger.info(f"Generated daily digest with {len(situations)} situations")
            
            return digest
            
        except Exception as e:
            logger.error(f"Error generating daily digest: {e}", exc_info=True)
            return "📊 **Daily Intelligence Digest**\n\nError generating digest. Please try again later."
    
    
    #===========================================================================
    # LEARNING SYSTEM - Get smarter from user responses
    #===========================================================================
    
    async def update_learning_from_response(
        self,
        situation_type: str,
        situation_context: Dict[str, Any],
        confidence_score: float,
        priority_score: int,
        user_response: str
    ) -> bool:
        """
        Update the learning system based on user response to a situation.
        
        This builds intelligence over time by tracking:
        - Which situation types you act on vs dismiss
        - What contexts lead to action
        - Confidence calibration (were we right to flag this?)
        
        Over time, this allows the system to:
        - Boost confidence for patterns you consistently act on
        - Lower confidence for patterns you consistently dismiss
        - Eventually auto-act on high-confidence patterns (5+ approvals)
        
        Args:
            situation_type: Type of situation
            situation_context: Context data
            confidence_score: Our confidence in detecting this
            priority_score: Our priority assessment
            user_response: How user responded (acted/dismissed/etc)
            
        Returns:
            True if learning updated successfully
        """
        try:
            # Extract key pattern indicators from context
            pattern_key = self._extract_pattern_key(situation_type, situation_context)
            
            # Check if we already have a learning record for this pattern
            existing_query = """
                SELECT 
                    id,
                    total_occurrences,
                    acted_count,
                    dismissed_count,
                    confidence_sum,
                    last_occurrence
                FROM contextual_learnings
                WHERE situation_type = $1
                AND pattern_key = $2
            """
            
            existing = await self.db.fetch_one(
                existing_query,
                situation_type,
                pattern_key
            )
            
            if existing:
                # Update existing learning record
                total_occurrences = existing['total_occurrences'] + 1
                acted_count = existing['acted_count'] + (1 if user_response == 'acted' else 0)
                dismissed_count = existing['dismissed_count'] + (1 if user_response == 'dismissed' else 0)
                confidence_sum = float(existing['confidence_sum']) + confidence_score
                
                # Calculate new metrics
                action_rate = acted_count / total_occurrences if total_occurrences > 0 else 0
                avg_confidence = confidence_sum / total_occurrences
                
                # Determine if we can auto-act on this pattern
                # Require: 5+ acted, 80%+ action rate, 60%+ avg confidence
                can_act_on = (
                    acted_count >= AUTO_EXECUTE_MIN_APPROVALS and
                    action_rate >= AUTO_EXECUTE_MIN_ACTION_RATE and
                    avg_confidence >= AUTO_EXECUTE_MIN_CONFIDENCE
                )
                
                update_query = """
                    UPDATE contextual_learnings
                    SET 
                        total_occurrences = $1,
                        acted_count = $2,
                        dismissed_count = $3,
                        confidence_sum = $4,
                        action_rate = $5,
                        avg_confidence = $6,
                        can_act_on = $7,
                        last_occurrence = $8
                    WHERE id = $9
                """
                
                await self.db.execute(
                    update_query,
                    total_occurrences,
                    acted_count,
                    dismissed_count,
                    confidence_sum,
                    action_rate,
                    avg_confidence,
                    can_act_on,
                    datetime.utcnow(),
                    existing['id']
                )
                
                # Log if pattern just became auto-executable
                if can_act_on and acted_count == AUTO_EXECUTE_MIN_APPROVALS:
                    logger.info(f"🎉 NEW AUTO-EXECUTE PATTERN: {situation_type}/{pattern_key} - Will auto-execute next time!")
                else:
                    logger.info(f"📚 Updated learning: {situation_type}/{pattern_key} (acted: {acted_count}, rate: {action_rate:.0%}, can_act_on: {can_act_on})")
                
            else:
                # Create new learning record
                acted_count = 1 if user_response == 'acted' else 0
                dismissed_count = 1 if user_response == 'dismissed' else 0
                
                insert_query = """
                    INSERT INTO contextual_learnings (
                        situation_type,
                        pattern_key,
                        pattern_context,
                        total_occurrences,
                        acted_count,
                        dismissed_count,
                        confidence_sum,
                        action_rate,
                        avg_confidence,
                        can_act_on,
                        last_occurrence,
                        created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                    )
                """
                
                await self.db.execute(
                    insert_query,
                    situation_type,
                    pattern_key,
                    json.dumps(situation_context),
                    1,  # total_occurrences
                    acted_count,
                    dismissed_count,
                    confidence_score,  # confidence_sum
                    float(acted_count),  # action_rate (0.0 or 1.0 for first occurrence)
                    confidence_score,  # avg_confidence
                    False,  # can_act_on (needs 5 approvals)
                    datetime.utcnow(),
                    datetime.utcnow()
                )
                
                logger.info(f"📚 Created learning record: {situation_type}/{pattern_key}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating learning from response: {e}", exc_info=True)
            return False
    
    
    def _extract_pattern_key(
        self,
        situation_type: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Extract a pattern key from situation context for learning.
        
        This identifies what "pattern" this situation represents so we can
        learn if you consistently act on similar situations.
        
        Args:
            situation_type: Type of situation
            context: Situation context
            
        Returns:
            Pattern key string (e.g., "meeting_actions", "uv_alert", "trend_tech")
        """
        # Define pattern extraction logic for each situation type
        
        if situation_type == 'post_meeting_action_required':
            # Pattern: meetings with action items (general)
            return 'meeting_actions'
        
        elif situation_type == 'deadline_approaching_prep_needed':
            # Pattern: events needing prep
            prep_required = context.get('prep_required', False)
            return 'deadline_prep' if prep_required else 'deadline_basic'
        
        elif situation_type == 'trend_content_opportunity':
            # Pattern: trends by business area
            business_area = context.get('business_area', 'general')
            trend_type = context.get('trend_type', 'unknown')
            return f"trend_{business_area}_{trend_type}"
        
        elif situation_type == 'email_priority_meeting_context':
            # Pattern: email-meeting correlations
            correlation = context.get('correlation_strength', 'moderate')
            return f"email_meeting_{correlation}"
        
        elif situation_type == 'email_meeting_followup':
            # Pattern: post-meeting email follow-ups
            return 'email_followup'
        
        elif situation_type == 'conversation_trend_alignment':
            # Pattern: conversation-trend alignments by category
            category = context.get('conversation_category', 'general')
            return f"conversation_trend_{category}"
        
        elif situation_type == 'weather_impact_calendar':
            # Pattern: weather impacts by condition
            condition = context.get('weather_condition', 'unknown')
            return f"weather_calendar_{condition}"
        
        elif situation_type == 'weather_health_impact':
            # Pattern: weather health impacts by condition
            condition = context.get('weather_condition', 'unknown')
            return f"weather_health_{condition}"
        
        elif situation_type == 'weather_emergency_alert':
            # Pattern: severe weather alerts
            return 'weather_emergency'
        
        else:
            # Unknown type - use generic pattern
            return f"unknown_{situation_type}"
    
    
    async def get_learning_insights(self) -> Dict[str, Any]:
        """
        Get insights about what patterns the system has learned.
        
        Useful for showing the user what the system knows about their preferences.
        
        Returns:
            Dictionary with learning insights
        """
        try:
            # Get top patterns you act on
            high_action_query = """
                SELECT 
                    situation_type,
                    pattern_key,
                    total_occurrences,
                    acted_count,
                    action_rate,
                    avg_confidence,
                    can_act_on
                FROM contextual_learnings
                WHERE action_rate >= 0.7
                AND total_occurrences >= 3
                ORDER BY action_rate DESC, total_occurrences DESC
                LIMIT 10
            """
            
            high_action_patterns = await self.db.fetch_all(high_action_query)
            
            # Get patterns you consistently dismiss
            low_action_query = """
                SELECT 
                    situation_type,
                    pattern_key,
                    total_occurrences,
                    action_rate,
                    dismissed_count
                FROM contextual_learnings
                WHERE action_rate <= 0.3
                AND total_occurrences >= 3
                ORDER BY dismissed_count DESC
                LIMIT 10
            """
            
            low_action_patterns = await self.db.fetch_all(low_action_query)
            
            # Get patterns ready for auto-action
            auto_action_query = """
                SELECT 
                    situation_type,
                    pattern_key,
                    total_occurrences,
                    acted_count,
                    action_rate,
                    avg_confidence
                FROM contextual_learnings
                WHERE can_act_on = true
                ORDER BY avg_confidence DESC
            """
            
            auto_action_patterns = await self.db.fetch_all(auto_action_query)
            
            # Get patterns close to auto-action (4 acted, need 1 more)
            almost_auto_query = """
                SELECT 
                    situation_type,
                    pattern_key,
                    acted_count,
                    action_rate,
                    avg_confidence
                FROM contextual_learnings
                WHERE acted_count >= 3
                AND acted_count < $1
                AND action_rate >= $2
                ORDER BY acted_count DESC
            """
            
            almost_auto_patterns = await self.db.fetch_all(
                almost_auto_query,
                AUTO_EXECUTE_MIN_APPROVALS,
                AUTO_EXECUTE_MIN_ACTION_RATE
            )
            
            # Get overall stats
            stats_query = """
                SELECT 
                    COUNT(*) as total_patterns,
                    SUM(total_occurrences) as total_situations,
                    SUM(acted_count) as total_acted,
                    SUM(dismissed_count) as total_dismissed,
                    AVG(action_rate) as avg_action_rate,
                    SUM(CASE WHEN can_act_on THEN 1 ELSE 0 END) as auto_executable_count
                FROM contextual_learnings
            """
            
            stats = await self.db.fetch_one(stats_query)
            
            return {
                'high_action_patterns': [dict(row) for row in high_action_patterns],
                'low_action_patterns': [dict(row) for row in low_action_patterns],
                'auto_action_patterns': [dict(row) for row in auto_action_patterns],
                'almost_auto_patterns': [dict(row) for row in almost_auto_patterns],
                'overall_stats': {
                    'total_patterns': stats['total_patterns'] if stats else 0,
                    'total_situations': stats['total_situations'] if stats else 0,
                    'total_acted': stats['total_acted'] if stats else 0,
                    'total_dismissed': stats['total_dismissed'] if stats else 0,
                    'avg_action_rate': float(stats['avg_action_rate']) if stats and stats['avg_action_rate'] else 0.0,
                    'auto_executable_count': stats['auto_executable_count'] if stats else 0
                },
                'thresholds': {
                    'min_approvals': AUTO_EXECUTE_MIN_APPROVALS,
                    'min_action_rate': AUTO_EXECUTE_MIN_ACTION_RATE,
                    'min_confidence': AUTO_EXECUTE_MIN_CONFIDENCE
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting learning insights: {e}", exc_info=True)
            return {
                'high_action_patterns': [],
                'low_action_patterns': [],
                'auto_action_patterns': [],
                'almost_auto_patterns': [],
                'overall_stats': {},
                'thresholds': {
                    'min_approvals': AUTO_EXECUTE_MIN_APPROVALS,
                    'min_action_rate': AUTO_EXECUTE_MIN_ACTION_RATE,
                    'min_confidence': AUTO_EXECUTE_MIN_CONFIDENCE
                }
            }


#===============================================================================
# MODULE EXPORTS
#===============================================================================

__all__ = [
    'SituationManager',
    'get_situation_manager',
    'AUTO_EXECUTE_MIN_APPROVALS',
    'AUTO_EXECUTE_MIN_ACTION_RATE',
    'AUTO_EXECUTE_MIN_CONFIDENCE',
]
