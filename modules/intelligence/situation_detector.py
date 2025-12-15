# modules/intelligence/situation_detector.py
"""
Situation Detector for Syntax Prime V2 Intelligence Hub
Analyzes signals from context collectors to detect meaningful situations

Takes raw ContextSignal objects and combines them into actionable Situation objects
that warrant user notification and suggested actions.

Created: 10/22/25
Updated: 12/11/25 - Added singleton pattern
Updated: 2025-12-15 - FIXED: Email classification too loose - added stop words, noreply filter
"""

import logging
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS - Stop words and automated email patterns
#===============================================================================

# Common words to exclude from keyword matching
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and',
    'but', 'if', 'or', 'because', 'until', 'while', 'about', 'against',
    'this', 'that', 'these', 'those', 'am', 'your', 'you', 'we', 'our',
    'i', 'me', 'my', 'myself', 'he', 'him', 'his', 'she', 'her', 'it',
    'its', 'they', 'them', 'their', 'what', 'which', 'who', 'whom',
    # Common email/business words
    'inc', 'inc.', 'llc', 'corp', 'corporation', 'company', 'co', 'co.',
    'new', 'now', 'today', 'meeting', 'call', 'update', 'reminder',
    'please', 're', 'fwd', 'fw', 'alert', 'notification', 'noreply',
}

# Patterns indicating automated/marketing emails (skip correlation)
AUTOMATED_EMAIL_PATTERNS = [
    'noreply@', 'no-reply@', 'donotreply@', 'notifications@',
    'alerts@', 'mailer@', 'newsletter@', 'marketing@', 'info@',
    'support@', 'help@', 'news@', 'updates@', 'team@',
    '@linkedin.com', '@ziprecruiter.com', '@indeed.com', '@glassdoor.com',
    '@careerbuilder.com', '@monster.com', '@dice.com', '@hired.com',
    '@angel.co', '@lever.co', '@greenhouse.io', '@workday.com',
    '@jobvite.com', '@taleo.net', '@icims.com', '@smartrecruiters.com',
]

#===============================================================================
# BASE CLASSES - Situation data structure
#===============================================================================

@dataclass
class Situation:
    """
    A detected situation that combines multiple signals into an actionable insight.
    
    Think of this as: "I noticed X, Y, and Z happening together - here's what you 
    should probably do about it."
    
    Example: "You have a meeting tomorrow about Project X, there's a trending topic
    related to it, and you have 3 action items due. Suggested actions: review notes,
    prep talking points, prioritize action items."
    """
    situation_id: UUID
    situation_type: str                    # Type: 'post_meeting_action_required', etc.
    situation_context: Dict[str, Any]      # All the data about this situation
    confidence_score: float                # 0.0-1.0: How confident are we this matters?
    priority_score: int                    # 1-10: How urgent is this?
    requires_action: bool                  # Does this need user action or just FYI?
    suggested_actions: List[Dict]          # List of action suggestions
    expires_at: datetime                   # When does this situation become irrelevant?
    related_signal_ids: List[UUID]         # Which signals led to detecting this?
    detected_at: datetime                  # When was this situation detected?
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/transmission"""
        result = asdict(self)
        # Convert UUIDs and datetimes to strings for JSON serialization
        result['situation_id'] = str(result['situation_id'])
        result['expires_at'] = result['expires_at'].isoformat()
        result['detected_at'] = result['detected_at'].isoformat()
        result['related_signal_ids'] = [str(sid) for sid in result['related_signal_ids']]
        return result


#===============================================================================
# SINGLETON INSTANCE
#===============================================================================

_detector_instance: Optional['SituationDetector'] = None


def get_situation_detector() -> 'SituationDetector':
    """Get singleton SituationDetector instance"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = SituationDetector()
    return _detector_instance


#===============================================================================
# SITUATION DETECTOR - Main pattern recognition engine
#===============================================================================

class SituationDetector:
    """
    Analyzes signals from all collectors and detects meaningful situations.
    
    This is the "intelligence" that connects dots across your data ecosystem.
    It looks for patterns like:
    - Meeting + action items + upcoming event = prep needed
    - Trend spike + past conversation + knowledge gap = content opportunity
    - High UV + headache risk + busy calendar = stay inside day
    """
    
    def __init__(self):
        """Initialize the situation detector"""
        self.detector_name = "SituationDetector"
        
    async def detect_all_situations(self, signals: List) -> List[Situation]:
        """
        Main entry point: analyze all signals and detect all situation types.
        
        Args:
            signals: List of ContextSignal objects from all collectors
            
        Returns:
            List of detected Situation objects
        """
        situations = []
        
        if not signals:
            logger.info("SituationDetector: No signals to analyze")
            return situations
        
        logger.info(f"SituationDetector: Analyzing {len(signals)} signals for patterns")
        
        try:
            # Run all situation detectors
            # Each detector looks for a specific pattern across the signals
            
            situations.extend(await self.detect_post_meeting_situations(signals))
            situations.extend(await self.detect_deadline_situations(signals))
            situations.extend(await self.detect_trend_content_situations(signals))
            situations.extend(await self.detect_email_meeting_correlation(signals))
            situations.extend(await self.detect_conversation_trend_correlation(signals))
            situations.extend(await self.detect_weather_impact(signals))
            
            logger.info(f"SituationDetector: Detected {len(situations)} situations")
            
        except Exception as e:
            logger.error(f"Error detecting situations: {e}", exc_info=True)
        
        return situations
    
    def _create_situation(
        self,
        situation_type: str,
        context: Dict[str, Any],
        related_signals: List,
        requires_action: bool = True,
        expires_hours: int = 48
    ) -> Situation:
        """
        Helper to create a Situation with calculated confidence and priority.
        
        Args:
            situation_type: Type of situation being created
            context: Situation-specific context data
            related_signals: List of ContextSignal objects that led to this
            requires_action: Whether user action is needed
            expires_hours: Hours until situation is no longer relevant
            
        Returns:
            New Situation object
        """
        now = datetime.utcnow()
        
        # Calculate confidence based on signal count and quality
        confidence = self._calculate_confidence(related_signals)
        
        # Calculate priority based on situation type and signal priorities
        priority = self._calculate_priority(situation_type, related_signals)
        
        return Situation(
            situation_id=uuid4(),
            situation_type=situation_type,
            situation_context=context,
            confidence_score=confidence,
            priority_score=priority,
            requires_action=requires_action,
            suggested_actions=[],  # Will be filled by ActionSuggester
            expires_at=now + timedelta(hours=expires_hours),
            related_signal_ids=[s.signal_id for s in related_signals],
            detected_at=now
        )
    
    def _calculate_confidence(self, signals: List) -> float:
        """
        Calculate confidence score based on signal quality.
        
        More signals = higher confidence
        Higher priority signals = higher confidence
        
        Returns float between 0.0 and 1.0
        """
        if not signals:
            return 0.0
        
        # Base confidence from signal count (more signals = more confident)
        signal_count_factor = min(len(signals) / 5.0, 0.6)  # Cap at 0.6 for count
        
        # Boost confidence based on signal priorities
        avg_priority = sum(s.priority for s in signals) / len(signals)
        priority_factor = min(avg_priority / 10.0, 0.4)  # Cap at 0.4 for priority
        
        confidence = signal_count_factor + priority_factor
        
        return round(min(confidence, 1.0), 2)  # Cap at 1.0
    
    def _calculate_priority(self, situation_type: str, signals: List) -> int:
        """
        Calculate priority score for a situation.
        
        Based on:
        - Situation type (some are inherently more urgent)
        - Signal priorities (higher signal priority = higher situation priority)
        
        Returns int between 1 and 10
        """
        if not signals:
            return 5  # Default medium priority
        
        # Get highest signal priority
        max_signal_priority = max(s.priority for s in signals)
        
        # Situation type modifiers
        urgent_types = [
            'deadline_approaching_prep_needed',
            'email_priority_meeting_context',
            'weather_impact_calendar',
            'weather_emergency_alert'
        ]
        
        if situation_type in urgent_types:
            # Boost priority by 1 for inherently urgent situations
            priority = min(max_signal_priority + 1, 10)
        else:
            priority = max_signal_priority
        
        return priority
    
    def _get_signals_by_type(self, signals: List, signal_types: List[str]) -> List:
        """
        Filter signals by type(s).
        
        Args:
            signals: List of all ContextSignal objects
            signal_types: List of signal types to filter for
            
        Returns:
            List of signals matching the specified types
        """
        return [s for s in signals if s.signal_type in signal_types]
    
    def _get_signals_by_source(self, signals: List, sources: List[str]) -> List:
        """
        Filter signals by source(s).
        
        Args:
            signals: List of all ContextSignal objects
            sources: List of sources to filter for (e.g., ['meeting', 'calendar'])
            
        Returns:
            List of signals matching the specified sources
        """
        return [s for s in signals if s.source in sources]
    
    
    #===========================================================================
    # SITUATION DETECTOR 1: Post-Meeting Action Required
    #===========================================================================
    
    async def detect_post_meeting_situations(self, signals: List) -> List[Situation]:
        """
        Detect situations where a meeting happened and has action items.
        
        Pattern: meeting_processed + action_item_pending/overdue + optional related events
        
        This creates a situation saying: "You had meeting X, here are the action items,
        and btw there's a follow-up meeting in 2 days - you should prep."
        """
        situations = []
        
        try:
            # Get all meeting-related signals
            meeting_signals = self._get_signals_by_type(signals, [
                'meeting_processed',
                'action_item_pending',
                'action_item_overdue',
                'meeting_upcoming'
            ])
            
            if not meeting_signals:
                logger.debug("No meeting signals found")
                return situations
            
            # Group signals by meeting_id to find related sets
            meetings_with_actions = {}
            
            for signal in meeting_signals:
                meeting_id = signal.data.get('meeting_id')
                
                if not meeting_id:
                    continue
                
                if meeting_id not in meetings_with_actions:
                    meetings_with_actions[meeting_id] = {
                        'meeting': None,
                        'action_items': [],
                        'upcoming_related': None
                    }
                
                # Categorize this signal
                if signal.signal_type == 'meeting_processed':
                    meetings_with_actions[meeting_id]['meeting'] = signal
                elif signal.signal_type in ['action_item_pending', 'action_item_overdue']:
                    meetings_with_actions[meeting_id]['action_items'].append(signal)
                elif signal.signal_type == 'meeting_upcoming':
                    # This might be a follow-up to a previous meeting
                    meetings_with_actions[meeting_id]['upcoming_related'] = signal
            
            # Create situations for meetings that have action items
            for meeting_id, data in meetings_with_actions.items():
                meeting_signal = data['meeting']
                action_signals = data['action_items']
                upcoming_signal = data['upcoming_related']
                
                # We need at least a meeting and action items
                if not meeting_signal or not action_signals:
                    continue
                
                # Check if any action items are overdue
                has_overdue = any(s.signal_type == 'action_item_overdue' for s in action_signals)
                
                # Build context for this situation
                context = {
                    'meeting_id': meeting_id,
                    'meeting_title': meeting_signal.data.get('meeting_title'),
                    'meeting_date': meeting_signal.data.get('meeting_date'),
                    'action_items': [
                        {
                            'id': s.data.get('action_item_id'),
                            'text': s.data.get('action_text'),
                            'due_date': s.data.get('due_date'),
                            'status': s.data.get('status'),
                            'overdue': s.signal_type == 'action_item_overdue',
                            'days_until_due': s.data.get('days_until_due'),
                            'days_overdue': s.data.get('days_overdue')
                        }
                        for s in action_signals
                    ],
                    'action_item_count': len(action_signals),
                    'overdue_count': sum(1 for s in action_signals if s.signal_type == 'action_item_overdue'),
                    'has_summary': meeting_signal.data.get('summary') is not None,
                    'has_transcript': meeting_signal.data.get('has_transcript', False)
                }
                
                # Add next meeting info if available
                if upcoming_signal:
                    context['next_meeting'] = {
                        'title': upcoming_signal.data.get('meeting_title'),
                        'date': upcoming_signal.data.get('meeting_date'),
                        'hours_until': upcoming_signal.data.get('hours_until')
                    }
                
                # Collect all related signals
                related_signals = [meeting_signal] + action_signals
                if upcoming_signal:
                    related_signals.append(upcoming_signal)
                
                # Determine expiry based on most urgent action item
                if has_overdue:
                    expires_hours = 12  # Overdue = handle ASAP
                else:
                    # Get soonest due date
                    soonest_due = min(
                        (s.data.get('days_until_due') for s in action_signals if s.data.get('days_until_due') is not None),
                        default=7
                    )
                    expires_hours = max(soonest_due * 24, 24)  # At least 24 hours
                
                # Create the situation
                situation = self._create_situation(
                    situation_type='post_meeting_action_required',
                    context=context,
                    related_signals=related_signals,
                    requires_action=True,
                    expires_hours=expires_hours
                )
                
                situations.append(situation)
                
                logger.info(f"📋 Detected post-meeting situation: {context['meeting_title']} with {len(action_signals)} action items")
        
        except Exception as e:
            logger.error(f"Error detecting post-meeting situations: {e}", exc_info=True)
        
        return situations
    
    
    #===========================================================================
    # SITUATION DETECTOR 2: Deadline Approaching - Prep Needed
    #===========================================================================
    
    async def detect_deadline_situations(self, signals: List) -> List[Situation]:
        """
        Detect situations where an upcoming event needs preparation.
        
        Pattern: event_upcoming_24h/48h + prep_time_needed + optional action_items
        
        This creates a situation saying: "You have a presentation tomorrow at 2 PM,
        you need 2 hours of prep, and you have 3 related action items to complete."
        """
        situations = []
        
        try:
            # Get calendar and meeting signals
            calendar_signals = self._get_signals_by_type(signals, [
                'event_upcoming_24h',
                'event_upcoming_48h',
                'prep_time_needed'
            ])
            
            action_signals = self._get_signals_by_type(signals, [
                'action_item_pending',
                'action_item_overdue'
            ])
            
            if not calendar_signals:
                logger.debug("No calendar signals found")
                return situations
            
            # Group events that need prep
            events_needing_prep = {}
            
            for signal in calendar_signals:
                event_id = signal.data.get('event_id')
                
                if not event_id:
                    continue
                
                if event_id not in events_needing_prep:
                    events_needing_prep[event_id] = {
                        'event': None,
                        'prep_signal': None,
                        'related_actions': []
                    }
                
                # Categorize this signal
                if signal.signal_type in ['event_upcoming_24h', 'event_upcoming_48h']:
                    events_needing_prep[event_id]['event'] = signal
                elif signal.signal_type == 'prep_time_needed':
                    events_needing_prep[event_id]['prep_signal'] = signal
            
            # Try to find related action items by matching event titles/topics
            for event_id, data in events_needing_prep.items():
                if not data['event']:
                    continue
                
                event_title = (data['event'].data.get('event_title') or '').lower()
                
                # Simple keyword matching to find related action items
                for action_signal in action_signals:
                    action_text = (action_signal.data.get('action_text') or '').lower()
                    meeting_title = (action_signal.data.get('meeting_title') or '').lower()
                    
                    # Check if action is related to this event
                    event_keywords = set(event_title.split())
                    action_keywords = set(action_text.split() + meeting_title.split())
                    
                    # If they share 2+ meaningful words (excluding common words)
                    common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']
                    meaningful_overlap = len(
                        (event_keywords - set(common_words)) & (action_keywords - set(common_words))
                    )
                    
                    if meaningful_overlap >= 2:
                        data['related_actions'].append(action_signal)
            
            # Create situations for events that need prep OR have upcoming deadlines
            for event_id, data in events_needing_prep.items():
                event_signal = data['event']
                prep_signal = data['prep_signal']
                action_signals_for_event = data['related_actions']
                
                if not event_signal:
                    continue
                
                # Only create situation if there's prep needed OR related action items
                if not prep_signal and not action_signals_for_event:
                    continue
                
                hours_until = event_signal.data.get('hours_until', 48)
                
                # Build context
                context = {
                    'event_id': event_id,
                    'event_title': event_signal.data.get('event_title'),
                    'event_time': event_signal.data.get('start_time'),
                    'hours_until': hours_until,
                    'location': event_signal.data.get('location'),
                    'attendees': event_signal.data.get('attendees'),
                    'calendar_name': event_signal.data.get('calendar_name')
                }
                
                # Add prep requirements if available
                if prep_signal:
                    context['prep_required'] = True
                    context['prep_reason'] = prep_signal.data.get('prep_reason')
                    context['suggested_prep_hours'] = prep_signal.data.get('suggested_prep_hours')
                else:
                    context['prep_required'] = False
                
                # Add related action items if found
                if action_signals_for_event:
                    context['related_action_items'] = [
                        {
                            'id': s.data.get('action_item_id'),
                            'text': s.data.get('action_text'),
                            'due_date': s.data.get('due_date'),
                            'overdue': s.signal_type == 'action_item_overdue',
                            'days_until_due': s.data.get('days_until_due')
                        }
                        for s in action_signals_for_event
                    ]
                    context['action_item_count'] = len(action_signals_for_event)
                else:
                    context['action_item_count'] = 0
                
                # Collect all related signals
                related_signals = [event_signal]
                if prep_signal:
                    related_signals.append(prep_signal)
                related_signals.extend(action_signals_for_event)
                
                # Determine expiry - expires when event happens
                expires_hours = max(int(hours_until), 2)
                
                # Create the situation
                situation = self._create_situation(
                    situation_type='deadline_approaching_prep_needed',
                    context=context,
                    related_signals=related_signals,
                    requires_action=True,
                    expires_hours=expires_hours
                )
                
                situations.append(situation)
                
                prep_note = f"with {context['suggested_prep_hours']}h prep needed" if prep_signal else "with related action items"
                logger.info(f"📅 Detected deadline situation: {context['event_title']} in {hours_until:.1f}h {prep_note}")
        
        except Exception as e:
            logger.error(f"Error detecting deadline situations: {e}", exc_info=True)
        
        return situations
    
    
    #===========================================================================
    # SITUATION DETECTOR 3: Trend Content Opportunity
    #===========================================================================
    
    async def detect_trend_content_situations(self, signals: List) -> List[Situation]:
        """
        Detect opportunities to create content based on trending topics.
        
        Pattern: trend_spike/rising/opportunity + optional conversation_topic + optional knowledge
        
        This creates a situation saying: "AI video tools is spiking, you've discussed
        this recently, and you have knowledge about it - perfect time to create content!"
        """
        situations = []
        
        try:
            # Get trend signals
            trend_signals = self._get_signals_by_type(signals, [
                'trend_spike',
                'trend_rising',
                'trend_high',
                'trend_opportunity'
            ])
            
            # Get conversation and knowledge signals
            conversation_signals = self._get_signals_by_type(signals, [
                'topic_discussed',
                'project_mentioned'
            ])
            
            knowledge_signals = self._get_signals_by_type(signals, [
                'knowledge_frequently_accessed',
                'knowledge_high_relevance',
                'knowledge_topic_match'
            ])
            
            if not trend_signals:
                logger.debug("No trend signals found")
                return situations
            
            # Process each trend signal
            for trend_signal in trend_signals:
                keyword = trend_signal.data.get('keyword', '').lower()
                business_area = trend_signal.data.get('business_area')
                
                if not keyword:
                    continue
                
                # Try to find related conversation signals
                related_conversations = []
                for conv_signal in conversation_signals:
                    conv_keyword = conv_signal.data.get('keyword', '').lower() if conv_signal.signal_type == 'topic_discussed' else ''
                    project_name = conv_signal.data.get('project_name', '').lower() if conv_signal.signal_type == 'project_mentioned' else ''
                    
                    # Check if conversation is about this trend
                    if keyword in conv_keyword or keyword in project_name:
                        related_conversations.append(conv_signal)
                    # Also check reverse - if trend keyword contains conversation topic
                    elif conv_keyword and conv_keyword in keyword:
                        related_conversations.append(conv_signal)
                
                # Try to find related knowledge
                related_knowledge = []
                for knowledge_signal in knowledge_signals:
                    knowledge_topics = knowledge_signal.data.get('topics', [])
                    knowledge_title = (knowledge_signal.data.get('title') or '').lower()
                    
                    # Check if knowledge exists about this trend
                    if keyword in knowledge_title:
                        related_knowledge.append(knowledge_signal)
                    elif any(keyword in str(t).lower() for t in knowledge_topics):
                        related_knowledge.append(knowledge_signal)
                
                # Build context for this situation
                context = {
                    'keyword': trend_signal.data.get('keyword'),
                    'business_area': business_area,
                    'trend_type': trend_signal.signal_type,
                    'trend_score': trend_signal.data.get('trend_score'),
                    'trend_momentum': trend_signal.data.get('momentum') or trend_signal.data.get('trend_momentum'),
                    'related_topics': trend_signal.data.get('related_topics', [])
                }
                
                # Add spike details if this is a spike
                if trend_signal.signal_type == 'trend_spike':
                    context['spike_details'] = {
                        'previous_score': trend_signal.data.get('previous_score'),
                        'score_change': trend_signal.data.get('score_change')
                    }
                
                # Add opportunity details if this came from trend_opportunities table
                if trend_signal.signal_type == 'trend_opportunity':
                    context['opportunity_details'] = {
                        'opportunity_id': trend_signal.data.get('opportunity_id'),
                        'opportunity_type': trend_signal.data.get('opportunity_type'),
                        'content_angle': trend_signal.data.get('content_angle'),
                        'target_audience': trend_signal.data.get('target_audience'),
                        'suggested_action': trend_signal.data.get('suggested_action')
                    }
                
                # Add conversation context if found
                if related_conversations:
                    context['past_discussions'] = [
                        {
                            'thread_id': s.data.get('thread_id'),
                            'keyword': s.data.get('keyword') or s.data.get('project_name'),
                            'relevance': s.data.get('relevance'),
                            'message_count': s.data.get('message_count')
                        }
                        for s in related_conversations
                    ]
                    context['discussed_recently'] = True
                else:
                    context['discussed_recently'] = False
                
                # Add knowledge context if found
                if related_knowledge:
                    context['related_knowledge'] = [
                        {
                            'entry_id': s.data.get('entry_id'),
                            'title': s.data.get('title'),
                            'content_type': s.data.get('content_type')
                        }
                        for s in related_knowledge
                    ]
                    context['knowledge_count'] = len(related_knowledge)
                else:
                    context['knowledge_count'] = 0
                
                # Determine which Bluesky account to use based on business_area
                account_mapping = {
                    'amcf': 'amcf_updates',
                    'nonprofit': 'amcf_updates',
                    'bcdodge': 'ghostlineco',
                    'damnitcarl': 'syntaxprime',
                    'mealsnfeelz': 'syntaxprime',
                    'roseandangel': 'ghostlineco',
                    'tvsignals': 'syntaxprime',
                    'tech': 'syntaxprime',
                    'business': 'ghostlineco'
                }
                context['suggested_account'] = account_mapping.get(business_area, 'syntaxprime')
                
                # Collect all related signals
                related_signals = [trend_signal] + related_conversations + related_knowledge
                
                # Determine expiry based on trend type
                if trend_signal.signal_type == 'trend_spike':
                    expires_hours = 48  # Act fast on spikes
                elif trend_signal.signal_type == 'trend_rising':
                    expires_hours = 72  # Rising trends give more time
                else:
                    expires_hours = 96  # Stable/opportunities last longer
                
                # Create the situation
                situation = self._create_situation(
                    situation_type='trend_content_opportunity',
                    context=context,
                    related_signals=related_signals,
                    requires_action=False,  # Opportunity, not requirement
                    expires_hours=expires_hours
                )
                
                situations.append(situation)
                
                discussion_note = "with past discussions" if related_conversations else "new topic"
                knowledge_note = f"and {context['knowledge_count']} knowledge entries" if related_knowledge else ""
                logger.info(f"📈 Detected trend opportunity: {keyword} ({discussion_note} {knowledge_note})")
        
        except Exception as e:
            logger.error(f"Error detecting trend content situations: {e}", exc_info=True)
        
        return situations
    
    
    #===========================================================================
    # SITUATION DETECTOR 4: Email-Meeting Correlation
    #===========================================================================
    
    async def detect_email_meeting_correlation(self, signals: List) -> List[Situation]:
        """
        Detect when high-priority emails are related to upcoming meetings.
        
        Pattern: email_priority_high/requires_response + event_upcoming + optional meeting_processed
        
        This creates a situation saying: "You got a high-priority email from Client X
        about the proposal, and you have a meeting with them tomorrow - review the
        email before the meeting!"
        """
        situations = []
        
        try:
            # Get email signals
            email_signals = self._get_signals_by_type(signals, [
                'email_priority_high',
                'email_requires_response',
                'email_follow_up'
            ])
            
            # Get calendar signals
            calendar_signals = self._get_signals_by_type(signals, [
                'event_upcoming_24h',
                'event_upcoming_48h'
            ])
            
            # Get meeting signals
            meeting_signals = self._get_signals_by_type(signals, [
                'meeting_processed',
                'meeting_upcoming'
            ])
            
            if not email_signals or not (calendar_signals or meeting_signals):
                logger.debug("Insufficient email/meeting signals for correlation")
                return situations
            
            # Try to correlate emails with events/meetings
            for email_signal in email_signals:
                sender_name = (email_signal.data.get('sender_name') or '').lower()
                sender_email = (email_signal.data.get('sender_email') or '').lower()
                subject = (email_signal.data.get('subject') or '').lower()
                
                # SKIP automated/marketing/job recruitment emails
                is_automated = any(pattern in sender_email for pattern in AUTOMATED_EMAIL_PATTERNS)
                if is_automated:
                    logger.debug(f"Skipping automated email from {sender_email}")
                    continue
                
                # Extract keywords from email, filtering out stop words
                raw_keywords = set(sender_name.split() + subject.split())
                email_keywords = {kw for kw in raw_keywords if kw and kw not in STOP_WORDS and len(kw) > 2}
                
                # Need meaningful keywords to correlate
                if len(email_keywords) < 2:
                    continue
                
                # Check calendar events
                for calendar_signal in calendar_signals:
                    event_title = (calendar_signal.data.get('event_title') or '').lower()
                    attendees = calendar_signal.data.get('attendees') or []
                    
                    # Check if sender is attending the meeting
                    attendee_emails = [str(a).lower() for a in attendees if a]
                    sender_attending = sender_email in ' '.join(attendee_emails)
                    
                    # Check if email keywords appear in event title (filter stop words)
                    raw_event_keywords = set(event_title.split())
                    event_keywords = {kw for kw in raw_event_keywords if kw and kw not in STOP_WORDS and len(kw) > 2}
                    keyword_overlap = len(email_keywords & event_keywords)
                    
                    # Correlation found if sender is attending OR strong keyword overlap (3+ meaningful words)
                    if sender_attending or keyword_overlap >= 3:
                        hours_until_event = calendar_signal.data.get('hours_until', 48)
                        
                        # Build context
                        context = {
                            'email_id': str(email_signal.data.get('email_id')),
                            'sender_name': email_signal.data.get('sender_name'),
                            'sender_email': email_signal.data.get('sender_email'),
                            'subject': email_signal.data.get('subject'),
                            'received_at': email_signal.data.get('received_at'),
                            'priority_level': email_signal.data.get('priority_level'),
                            'requires_response': email_signal.data.get('requires_response', False),
                            'event_id': calendar_signal.data.get('event_id'),
                            'event_title': calendar_signal.data.get('event_title'),
                            'event_time': calendar_signal.data.get('start_time'),
                            'hours_until_event': hours_until_event,
                            'correlation_reason': 'sender_attending' if sender_attending else 'keyword_match',
                            'correlation_strength': 'strong' if sender_attending else 'moderate'
                        }
                        
                        # Add action items if email has them
                        action_items = email_signal.data.get('action_items')
                        if action_items:
                            context['email_action_items'] = action_items
                        
                        # Collect related signals
                        related_signals = [email_signal, calendar_signal]
                        
                        # Determine expiry - before the meeting
                        expires_hours = max(int(hours_until_event) - 2, 6)
                        
                        # Create the situation
                        situation = self._create_situation(
                            situation_type='email_priority_meeting_context',
                            context=context,
                            related_signals=related_signals,
                            requires_action=True,
                            expires_hours=expires_hours
                        )
                        
                        situations.append(situation)
                        
                        logger.info(f"📧 Detected email-meeting correlation: {sender_name} → {event_title} in {hours_until_event:.1f}h")
                
                # Also check past meetings (if email is follow-up to a meeting)
                for meeting_signal in meeting_signals:
                    meeting_title = (meeting_signal.data.get('meeting_title') or '').lower()
                    attendees = meeting_signal.data.get('attendees') or []
                    
                    if not attendees:
                        continue
                    
                    # Check if sender was in the meeting
                    attendee_info = ' '.join([str(a).lower() for a in attendees])
                    sender_was_attendee = sender_email in attendee_info or sender_name in attendee_info
                    
                    # Check keyword overlap (filter stop words)
                    raw_meeting_keywords = set(meeting_title.split())
                    meeting_keywords = {kw for kw in raw_meeting_keywords if kw and kw not in STOP_WORDS and len(kw) > 2}
                    keyword_overlap = len(email_keywords & meeting_keywords)
                    
                    # Correlation if sender was attendee OR very strong keyword overlap (4+ meaningful words)
                    if sender_was_attendee or keyword_overlap >= 4:
                        # Build context
                        context = {
                            'email_id': str(email_signal.data.get('email_id')),
                            'sender_name': email_signal.data.get('sender_name'),
                            'sender_email': email_signal.data.get('sender_email'),
                            'subject': email_signal.data.get('subject'),
                            'received_at': email_signal.data.get('received_at'),
                            'priority_level': email_signal.data.get('priority_level'),
                            'requires_response': email_signal.data.get('requires_response', False),
                            'meeting_id': meeting_signal.data.get('meeting_id'),
                            'meeting_title': meeting_signal.data.get('meeting_title'),
                            'meeting_date': meeting_signal.data.get('meeting_date'),
                            'correlation_type': 'post_meeting_followup',
                            'correlation_reason': 'sender_was_attendee' if sender_was_attendee else 'keyword_match'
                        }
                        
                        # Collect related signals
                        related_signals = [email_signal, meeting_signal]
                        
                        # Create the situation
                        situation = self._create_situation(
                            situation_type='email_meeting_followup',
                            context=context,
                            related_signals=related_signals,
                            requires_action=True,
                            expires_hours=48
                        )
                        
                        situations.append(situation)
                        
                        logger.info(f"📧 Detected email-meeting followup: {sender_name} following up on {meeting_title}")
        
        except Exception as e:
            logger.error(f"Error detecting email-meeting correlations: {e}", exc_info=True)
        
        return situations
    
    
    #===========================================================================
    # SITUATION DETECTOR 5: Conversation-Trend Correlation
    #===========================================================================
    
    async def detect_conversation_trend_correlation(self, signals: List) -> List[Situation]:
        """
        Detect when topics you're discussing match trending topics.
        
        Pattern: topic_discussed/project_mentioned + trend_spike/rising + optional knowledge
        
        This creates a situation saying: "You've been discussing AI agents in 3 
        conversations, it's trending now with a score of 75, and you have 2 
        knowledge entries about it - this aligns perfectly for content!"
        """
        situations = []
        
        try:
            # Get conversation signals
            conversation_signals = self._get_signals_by_type(signals, [
                'topic_discussed',
                'project_mentioned'
            ])
            
            # Get trend signals
            trend_signals = self._get_signals_by_type(signals, [
                'trend_spike',
                'trend_rising',
                'trend_high'
            ])
            
            # Get knowledge signals
            knowledge_signals = self._get_signals_by_type(signals, [
                'knowledge_frequently_accessed',
                'knowledge_high_relevance',
                'knowledge_topic_match'
            ])
            
            if not conversation_signals or not trend_signals:
                logger.debug("Insufficient conversation/trend signals for correlation")
                return situations
            
            # Try to correlate conversations with trends
            for conversation_signal in conversation_signals:
                # Get conversation topic
                if conversation_signal.signal_type == 'topic_discussed':
                    conversation_topic = conversation_signal.data.get('keyword', '').lower()
                    conversation_relevance = conversation_signal.data.get('relevance', 5)
                else:  # project_mentioned
                    conversation_topic = conversation_signal.data.get('project_name', '').lower()
                    conversation_relevance = 7  # Projects are inherently relevant
                
                if not conversation_topic:
                    continue
                
                # Split into keywords for better matching
                conversation_keywords = set(conversation_topic.split())
                
                # Find matching trends
                for trend_signal in trend_signals:
                    trend_keyword = trend_signal.data.get('keyword', '').lower()
                    
                    if not trend_keyword:
                        continue
                    
                    trend_keywords = set(trend_keyword.split())
                    
                    # Check for keyword overlap
                    keyword_overlap = len(conversation_keywords & trend_keywords)
                    substring_match = conversation_topic in trend_keyword or trend_keyword in conversation_topic
                    
                    if keyword_overlap >= 1 or substring_match:
                        # Found a correlation!
                        
                        # Try to find related knowledge
                        related_knowledge = None
                        for knowledge_signal in knowledge_signals:
                            knowledge_title = (knowledge_signal.data.get('title') or '').lower()
                            
                            if (conversation_topic in knowledge_title or
                                trend_keyword in knowledge_title):
                                related_knowledge = knowledge_signal
                                break
                        
                        # Build context
                        context = {
                            'conversation_topic': conversation_signal.data.get('keyword') or conversation_signal.data.get('project_name'),
                            'conversation_relevance': conversation_relevance,
                            'conversation_category': conversation_signal.data.get('category', 'general'),
                            'thread_id': conversation_signal.data.get('thread_id'),
                            'message_count': conversation_signal.data.get('message_count', 1),
                            'trend_keyword': trend_signal.data.get('keyword'),
                            'trend_score': trend_signal.data.get('trend_score'),
                            'trend_type': trend_signal.signal_type,
                            'trend_momentum': trend_signal.data.get('momentum') or trend_signal.data.get('trend_momentum'),
                            'business_area': trend_signal.data.get('business_area'),
                            'correlation_type': 'exact_match' if substring_match else 'keyword_overlap',
                            'keyword_overlap_count': keyword_overlap
                        }
                        
                        # Add spike details if available
                        if trend_signal.signal_type == 'trend_spike':
                            context['spike_change'] = trend_signal.data.get('score_change')
                        
                        # Add knowledge context if found
                        if related_knowledge:
                            context['knowledge_available'] = True
                            context['knowledge_entry'] = {
                                'entry_id': related_knowledge.data.get('entry_id'),
                                'title': related_knowledge.data.get('title')
                            }
                        else:
                            context['knowledge_available'] = False
                        
                        # Create actionable insight
                        if context['knowledge_available']:
                            context['insight'] = f"You've discussed {conversation_topic}, it's trending (score: {context['trend_score']}), and you have relevant knowledge - perfect alignment for content creation!"
                        else:
                            context['insight'] = f"You've discussed {conversation_topic} and it's now trending (score: {context['trend_score']}) - consider creating content."
                        
                        # Collect related signals
                        related_signals = [conversation_signal, trend_signal]
                        if related_knowledge:
                            related_signals.append(related_knowledge)
                        
                        # Determine expiry based on trend urgency
                        if trend_signal.signal_type == 'trend_spike':
                            expires_hours = 48
                        else:
                            expires_hours = 72
                        
                        # Create the situation
                        situation = self._create_situation(
                            situation_type='conversation_trend_alignment',
                            context=context,
                            related_signals=related_signals,
                            requires_action=False,  # Opportunity, not requirement
                            expires_hours=expires_hours
                        )
                        
                        situations.append(situation)
                        
                        knowledge_note = "with knowledge" if context['knowledge_available'] else "no formal knowledge yet"
                        logger.info(f"💡 Detected conversation-trend alignment: {conversation_topic} ↔ {trend_keyword} ({knowledge_note})")
        
        except Exception as e:
            logger.error(f"Error detecting conversation-trend correlations: {e}", exc_info=True)
        
        return situations
    
    
    #===========================================================================
    # SITUATION DETECTOR 6: Weather Impact on Schedule/Health
    #===========================================================================
    
    async def detect_weather_impact(self, signals: List) -> List[Situation]:
        """
        Detect when weather conditions should affect your schedule or health.
        
        Pattern: (uv_index_alert OR headache_risk_high OR weather_alert) + calendar events
        
        This creates a situation saying: "UV index is 8 (dangerous for your allergy)
        and you have 3 outdoor events today - consider rescheduling or prepare 
        protection!"
        """
        situations = []
        
        try:
            # Get weather signals
            weather_signals = self._get_signals_by_type(signals, [
                'uv_index_alert',
                'uv_forecast_alert',
                'headache_risk_high',
                'weather_alert',
                'pressure_dropping'
            ])
            
            # Get calendar signals
            calendar_signals = self._get_signals_by_type(signals, [
                'event_upcoming_24h',
                'event_upcoming_48h',
                'meeting_cluster'
            ])
            
            if not weather_signals:
                logger.debug("No weather signals found")
                return situations
            
            # Process each weather signal
            for weather_signal in weather_signals:
                signal_type = weather_signal.signal_type
                
                # Determine severity and impact
                if signal_type == 'uv_index_alert':
                    uv_index = weather_signal.data.get('uv_index') or 0
                    uv_level = weather_signal.data.get('uv_level')
                    
                    # Build context for UV alert
                    context = {
                        'weather_condition': 'high_uv_index',
                        'uv_index': uv_index,
                        'uv_level': uv_level,
                        'location': weather_signal.data.get('location'),
                        'warning': weather_signal.data.get('warning'),
                        'health_impact': 'Sun allergy risk - protection required',
                        'severity': 'critical' if uv_index >= 8 else 'high'
                    }
                    
                    # Find outdoor events
                    outdoor_events = []
                    for calendar_signal in calendar_signals:
                        event_title = (calendar_signal.data.get('event_title') or '').lower()
                        location = (calendar_signal.data.get('location') or '').lower()
                        
                        # Check if event is likely outdoor
                        outdoor_keywords = ['outdoor', 'outside', 'park', 'garden', 'lunch', 'walk', 'site visit', 'field']
                        is_outdoor = any(kw in event_title or kw in location for kw in outdoor_keywords)
                        
                        if is_outdoor:
                            outdoor_events.append({
                                'event_title': calendar_signal.data.get('event_title'),
                                'event_time': calendar_signal.data.get('start_time'),
                                'hours_until': calendar_signal.data.get('hours_until'),
                                'location': calendar_signal.data.get('location')
                            })
                    
                    if outdoor_events:
                        context['affected_events'] = outdoor_events
                        context['event_count'] = len(outdoor_events)
                        context['recommendation'] = f"Reschedule {len(outdoor_events)} outdoor events or prepare maximum sun protection"
                        related_signals = [weather_signal] + [s for s in calendar_signals if any(
                            e['event_title'] == s.data.get('event_title') for e in outdoor_events
                        )]
                    else:
                        # No outdoor events, but still important for general planning
                        context['affected_events'] = []
                        context['event_count'] = 0
                        context['recommendation'] = "Avoid outdoor activities today - UV dangerous for sun allergy"
                        related_signals = [weather_signal]
                    
                    # Create situation
                    situation = self._create_situation(
                        situation_type='weather_impact_calendar',
                        context=context,
                        related_signals=related_signals,
                        requires_action=True,
                        expires_hours=6  # UV changes throughout day
                    )
                    
                    situations.append(situation)
                    
                    logger.warning(f"☀️ UV impact detected: Index {uv_index} with {len(outdoor_events)} outdoor events")
                
                elif signal_type == 'headache_risk_high':
                    risk_level = weather_signal.data.get('risk_level')
                    risk_score = weather_signal.data.get('risk_score')
                    
                    # Build context for headache risk
                    context = {
                        'weather_condition': 'high_headache_risk',
                        'risk_level': risk_level,
                        'risk_score': risk_score,
                        'risk_factors': weather_signal.data.get('risk_factors', []),
                        'location': weather_signal.data.get('location'),
                        'health_impact': 'Headache likely - preventive measures recommended',
                        'severity': 'critical' if risk_level == 'severe' else 'high'
                    }
                    
                    # Check if user has busy calendar (meeting cluster)
                    meeting_clusters = [s for s in calendar_signals if s.signal_type == 'meeting_cluster']
                    busy_day = len(meeting_clusters) > 0 or len(calendar_signals) >= 3
                    
                    if busy_day:
                        context['calendar_status'] = 'busy'
                        context['event_count'] = len(calendar_signals)
                        context['recommendation'] = "High headache risk on a busy day - take preventive medication, stay hydrated, consider blocking rest time"
                        
                        if meeting_clusters:
                            cluster = meeting_clusters[0]
                            context['meeting_cluster'] = {
                                'date': cluster.data.get('date'),
                                'meeting_count': cluster.data.get('meeting_count'),
                                'total_minutes': cluster.data.get('total_minutes')
                            }
                        
                        related_signals = [weather_signal] + calendar_signals[:3]
                    else:
                        context['calendar_status'] = 'light'
                        context['event_count'] = len(calendar_signals)
                        context['recommendation'] = "High headache risk - take preventive measures, avoid screen time"
                        related_signals = [weather_signal]
                    
                    # Create situation
                    situation = self._create_situation(
                        situation_type='weather_health_impact',
                        context=context,
                        related_signals=related_signals,
                        requires_action=True,
                        expires_hours=12
                    )
                    
                    situations.append(situation)
                    
                    logger.warning(f"⚠️ Headache risk impact: {risk_level} risk on {'busy' if busy_day else 'light'} day")
                
                elif signal_type == 'weather_alert':
                    # Severe weather alert
                    context = {
                        'weather_condition': 'severe_weather_alert',
                        'alert_description': weather_signal.data.get('alert_description'),
                        'location': weather_signal.data.get('location'),
                        'weather': weather_signal.data.get('weather'),
                        'wind_speed': weather_signal.data.get('wind_speed'),
                        'health_impact': 'Safety risk - avoid travel',
                        'severity': 'critical'
                    }
                    
                    # Any events during alert period?
                    if calendar_signals:
                        context['affected_events'] = [
                            {
                                'event_title': s.data.get('event_title'),
                                'event_time': s.data.get('start_time'),
                                'hours_until': s.data.get('hours_until')
                            }
                            for s in calendar_signals[:5]
                        ]
                        context['event_count'] = len(calendar_signals)
                        context['recommendation'] = f"SEVERE WEATHER ALERT - Consider rescheduling {len(calendar_signals)} events for safety"
                        related_signals = [weather_signal] + calendar_signals[:3]
                    else:
                        context['affected_events'] = []
                        context['event_count'] = 0
                        context['recommendation'] = "SEVERE WEATHER ALERT - Stay indoors and monitor conditions"
                        related_signals = [weather_signal]
                    
                    # Create situation
                    situation = self._create_situation(
                        situation_type='weather_emergency_alert',
                        context=context,
                        related_signals=related_signals,
                        requires_action=True,
                        expires_hours=6
                    )
                    
                    situations.append(situation)
                    
                    logger.error(f"🚨 Severe weather impact: {context['alert_description']} with {len(calendar_signals)} events")
        
        except Exception as e:
            logger.error(f"Error detecting weather impacts: {e}", exc_info=True)
        
        return situations


#===============================================================================
# MODULE EXPORTS
#===============================================================================

__all__ = [
    'Situation',
    'SituationDetector',
    'get_situation_detector',
]
