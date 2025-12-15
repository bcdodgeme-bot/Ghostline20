# modules/intelligence/context_collectors.py
"""
Context Collectors for Syntax Prime V2 Intelligence Hub
Monitors 9 data sources and produces context signals for situation detection

Each collector inherits from ContextCollector and produces ContextSignal objects
that feed into the situation detector.

Created: 10/22/25
Updated: 12/11/25 - Added singleton pattern, fixed EmailContextCollector bug,
                    standardized USER_ID handling
"""

import logging
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS
#===============================================================================

# Single user system - hardcode the user ID
USER_ID = UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")


def convert_utc_to_user_timezone(dt: datetime) -> datetime:
    """Convert UTC datetime to America/New_York timezone"""
    import pytz
    user_tz = pytz.timezone('America/New_York')
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(user_tz)


#===============================================================================
# BASE CLASSES - Foundation for all collectors
#===============================================================================

@dataclass
class ContextSignal:
    """
    A single piece of context from a data source that might matter.
    
    Think of this as an "event that happened" - like a meeting occurred,
    an email arrived, a trend spiked, etc.
    """
    signal_id: UUID
    source: str              # Which collector produced this: 'meetings', 'calendar', 'email', etc.
    signal_type: str         # What kind of signal: 'action_item', 'event_upcoming', 'trend_spike'
    timestamp: datetime      # When this signal occurred
    data: Dict[str, Any]     # Source-specific data (meeting_id, event details, etc.)
    priority: int            # Urgency: 1-10 (10 = most urgent)
    expires_at: datetime     # When this signal is no longer relevant
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/transmission"""
        result = asdict(self)
        # Convert UUIDs and datetimes to strings for JSON serialization
        result['signal_id'] = str(result['signal_id'])
        result['timestamp'] = result['timestamp'].isoformat()
        result['expires_at'] = result['expires_at'].isoformat()
        return result


class ContextCollector:
    """
    Base class for all context collectors.
    
    Each collector monitors ONE data source and converts its data into
    ContextSignal objects that situation detector can understand.
    
    Uses the centralized db_manager singleton for all database operations.
    """
    
    def __init__(self):
        """Initialize collector with centralized db_manager"""
        self.db = db_manager
        self.collector_name = self.__class__.__name__
        self.user_id = USER_ID
        
    async def collect_signals(self, lookback_hours: int = 24) -> List[ContextSignal]:
        """
        Collect all relevant signals from this data source.
        
        Args:
            lookback_hours: How far back to look for signals (default 24 hours)
            
        Returns:
            List of ContextSignal objects
        """
        raise NotImplementedError("Subclasses must implement collect_signals()")
    
    async def get_current_state(self) -> Dict[str, Any]:
        """
        Get the current state of this data source for debugging/monitoring.
        
        Returns:
            Dictionary with current state info (record counts, latest timestamps, etc.)
        """
        raise NotImplementedError("Subclasses must implement get_current_state()")
    
    def _create_signal(
        self,
        signal_type: str,
        data: Dict[str, Any],
        priority: int,
        expires_hours: int = 48
    ) -> ContextSignal:
        """
        Helper to create a ContextSignal with consistent defaults.
        
        Args:
            signal_type: Type of signal being created
            data: Signal-specific data
            priority: Priority score 1-10
            expires_hours: Hours until signal expires (default 48)
            
        Returns:
            New ContextSignal object
        """
        now = datetime.now(timezone.utc)
        return ContextSignal(
            signal_id=uuid4(),
            source=self.collector_name.replace('ContextCollector', '').lower(),
            signal_type=signal_type,
            timestamp=now,
            data=data,
            priority=priority,
            expires_at=now + timedelta(hours=expires_hours)
        )


#===============================================================================
# MEETING CONTEXT COLLECTOR - Monitors Fathom meetings & action items
#===============================================================================

# Singleton instance
_meeting_collector: Optional['MeetingContextCollector'] = None


def get_meeting_collector() -> 'MeetingContextCollector':
    """Get singleton MeetingContextCollector instance"""
    global _meeting_collector
    if _meeting_collector is None:
        _meeting_collector = MeetingContextCollector()
    return _meeting_collector


class MeetingContextCollector(ContextCollector):
    """
    Monitors Fathom meetings and their action items.
    
    Produces signals for:
    - New meetings processed (with summaries/transcripts)
    - Pending action items (with due dates)
    - Overdue action items
    - Upcoming related meetings
    """
    
    async def collect_signals(self, lookback_hours: int = 168) -> List[ContextSignal]:
        """
        Collect meeting-related signals from last 7 days (168 hours default).
        
        Why 7 days? Meetings and action items typically have a weekly cadence.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query 1: Get recent meetings with their details
            meetings_query = """
                SELECT 
                    id,
                    title as meeting_title, 
                    meeting_date,
                    duration_minutes,
                    participants as attendees,
                    ai_summary as summary,  
                    transcript_text IS NOT NULL as transcript_available,  
                    created_at as processed_at 
                FROM fathom_meetings
                WHERE created_at >= $1
                ORDER BY meeting_date DESC
            """
            
            meetings = await self.db.fetch_all(meetings_query, lookback_time)
            
            # Create signals for each processed meeting
            for meeting in meetings:
                # Signal 1: Meeting was processed
                signals.append(self._create_signal(
                    signal_type='meeting_processed',
                    data={
                        'meeting_id': str(meeting['id']),
                        'meeting_title': meeting['meeting_title'],
                        'meeting_date': convert_utc_to_user_timezone(meeting['meeting_date']).isoformat(),
                        'duration_minutes': meeting['duration_minutes'],
                        'attendees': meeting['attendees'],
                        'summary': meeting['summary'],
                        'has_transcript': meeting['transcript_available']
                    },
                    priority=7,  # Meetings are important but not urgent by default
                    expires_hours=168  # Relevant for a week
                ))
                
                logger.debug(f"Created meeting_processed signal for: {meeting['meeting_title']}")
            
            # Query 2: Get pending action items from those meetings
            action_items_query = """
                SELECT 
                    ai.id,
                    ai.meeting_id,
                    ai.action_text,
                    ai.assigned_to,
                    ai.due_date,
                    ai.priority,
                    ai.status,
                    m.title as meeting_title
                FROM meeting_action_items ai
                JOIN fathom_meetings m ON ai.meeting_id = m.id
                WHERE ai.status = 'pending'
                AND m.created_at >= $1
                ORDER BY ai.due_date ASC NULLS LAST
            """
            
            action_items = await self.db.fetch_all(action_items_query, lookback_time)
            
            now = datetime.now(timezone.utc)
            
            for item in action_items:
                due_date = item['due_date']
                
                # Determine if overdue or just pending
                if due_date and due_date < now.date():
                    # Signal 2: Action item is OVERDUE
                    signals.append(self._create_signal(
                        signal_type='action_item_overdue',
                        data={
                            'action_item_id': str(item['id']),
                            'meeting_id': str(item['meeting_id']),
                            'meeting_title': item['meeting_title'],
                            'action_text': item['action_text'],
                            'assigned_to': item['assigned_to'],
                            'due_date': due_date.isoformat(),
                            'days_overdue': (now.date() - due_date).days,
                            'status': item['status']
                        },
                        priority=10,  # Overdue = maximum priority
                        expires_hours=24  # Very urgent, short expiry
                    ))
                    
                    logger.warning(f"Overdue action item: {item['action_text'][:50]}...")
                    
                else:
                    # Signal 3: Action item is pending (not overdue yet)
                    days_until_due = (due_date - now.date()).days if due_date else None
                    
                    # Priority calculation: closer to due date = higher priority
                    if days_until_due is not None:
                        if days_until_due <= 1:
                            priority = 9
                        elif days_until_due <= 3:
                            priority = 8
                        elif days_until_due <= 7:
                            priority = 7
                        else:
                            priority = 6
                    else:
                        priority = 6  # No due date = moderate priority
                    
                    signals.append(self._create_signal(
                        signal_type='action_item_pending',
                        data={
                            'action_item_id': str(item['id']),
                            'meeting_id': str(item['meeting_id']),
                            'meeting_title': item['meeting_title'],
                            'action_text': item['action_text'],
                            'assigned_to': item['assigned_to'],
                            'due_date': due_date.isoformat() if due_date else None,
                            'days_until_due': days_until_due,
                            'status': item['status']
                        },
                        priority=priority,
                        expires_hours=72  # Relevant for 3 days
                    ))
                    
                    logger.debug(f"Pending action item (due in {days_until_due} days): {item['action_text'][:50]}...")
            
            # Query 3: Check for upcoming meetings (related calendar events)
            upcoming_meetings_query = """
                SELECT 
                    id,
                    title as meeting_title,
                    meeting_date,
                    participants as attendees
                FROM fathom_meetings
                WHERE meeting_date BETWEEN $1 AND $2
                ORDER BY meeting_date ASC
            """
            
            now_date = datetime.utcnow()
            two_days_ahead = now_date + timedelta(hours=48)
            
            upcoming = await self.db.fetch_all(
                upcoming_meetings_query,
                now_date,
                two_days_ahead
            )
            
            for meeting in upcoming:
                hours_until = (meeting['meeting_date'] - now_date).total_seconds() / 3600
                
                # Signal 4: Meeting upcoming within 48 hours
                signals.append(self._create_signal(
                    signal_type='meeting_upcoming',
                    data={
                        'meeting_id': str(meeting['id']),
                        'meeting_title': meeting['meeting_title'],
                        'meeting_date': convert_utc_to_user_timezone(meeting['meeting_date']).isoformat(),
                        'hours_until': round(hours_until, 1),
                        'attendees': meeting['attendees']
                    },
                    priority=8 if hours_until < 24 else 7,
                    expires_hours=int(hours_until) + 2
                ))
                
                logger.info(f"Upcoming meeting in {hours_until:.1f}h: {meeting['meeting_title']}")
            
            logger.info(f"MeetingContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting meeting signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of meetings data source"""
        try:
            total_meetings = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM fathom_meetings"
            )
            
            pending_actions = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM meeting_action_items WHERE status IN ('pending', 'in_progress')"
            )
            
            latest_meeting = await self.db.fetch_one(
                "SELECT MAX(meeting_date) as latest FROM fathom_meetings"
            )
            
            overdue_actions = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM meeting_action_items WHERE due_date < CURRENT_DATE AND status IN ('pending', 'in_progress')"
            )
            
            return {
                'collector': 'MeetingContextCollector',
                'total_meetings': total_meetings['count'] if total_meetings else 0,
                'pending_action_items': pending_actions['count'] if pending_actions else 0,
                'overdue_action_items': overdue_actions['count'] if overdue_actions else 0,
                'latest_meeting_date': latest_meeting['latest'].isoformat() if latest_meeting and latest_meeting['latest'] else None,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting meeting state: {e}")
            return {
                'collector': 'MeetingContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# CONVERSATION CONTEXT COLLECTOR - Monitors chat messages for topics/projects
#===============================================================================

# Singleton instance
_conversation_collector: Optional['ConversationContextCollector'] = None


def get_conversation_collector() -> 'ConversationContextCollector':
    """Get singleton ConversationContextCollector instance"""
    global _conversation_collector
    if _conversation_collector is None:
        _conversation_collector = ConversationContextCollector()
    return _conversation_collector


class ConversationContextCollector(ContextCollector):
    """
    Monitors chat conversation messages and extracts meaningful context.
    
    Uses AI (OpenRouter) to analyze recent conversations and identify:
    - Topics being discussed frequently
    - Questions that might need follow-up
    - Projects mentioned by the user
    """
    
    def __init__(self):
        super().__init__()
        self.openrouter_client = None
        
    async def _get_openrouter_client(self):
        """Lazy load OpenRouter client"""
        if self.openrouter_client is None:
            from ..ai.openrouter_client import get_openrouter_client
            self.openrouter_client = await get_openrouter_client()
        return self.openrouter_client
    
    async def collect_signals(self, lookback_hours: int = 24) -> List[ContextSignal]:
        """
        Collect conversation signals from recent chat messages.
        
        Uses 24-hour lookback by default since conversations are more ephemeral.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query: Get recent messages grouped by thread
            messages_query = """
                SELECT 
                    cm.id,
                    cm.thread_id,
                    cm.role,
                    cm.content,
                    cm.created_at,
                    ct.user_id,
                    ct.personality,
                    ct.last_activity
                FROM conversation_messages cm
                JOIN conversation_threads ct ON cm.thread_id = ct.id
                WHERE cm.created_at >= $1
                AND cm.role = 'user'
                ORDER BY cm.created_at DESC
                LIMIT 100
            """
            
            messages = await self.db.fetch_all(messages_query, lookback_time)
            
            if not messages:
                logger.info("ConversationContextCollector: No recent messages found")
                return signals
            
            # Group messages by thread for better context
            threads = {}
            for msg in messages:
                thread_id = str(msg['thread_id'])
                if thread_id not in threads:
                    threads[thread_id] = []
                threads[thread_id].append(msg)
            
            logger.info(f"ConversationContextCollector: Analyzing {len(messages)} messages across {len(threads)} threads")
            
            # Get OpenRouter client for AI analysis
            client = await self._get_openrouter_client()
            
            # Analyze each thread for topics/patterns
            for thread_id, thread_messages in threads.items():
                # Combine messages into context for AI
                conversation_text = "\n\n".join([
                    f"[{msg['created_at'].strftime('%H:%M')}] User: {msg['content']}"
                    for msg in sorted(thread_messages, key=lambda m: m['created_at'])
                ])
                
                # AI analysis prompt
                analysis_prompt = f"""Analyze this conversation and extract:
1. Main topics discussed (3-5 keywords each)
2. Any questions the user asked that might need follow-up
3. Any projects/initiatives mentioned by name

Conversation:
{conversation_text[:2000]}  

Respond in JSON format:
{{
    "topics": [
        {{"keyword": "topic name", "relevance": 1-10, "category": "business/personal/technical/health"}},
        ...
    ],
    "questions": [
        {{"question": "text of question", "needs_followup": true/false}},
        ...
    ],
    "projects": [
        {{"project_name": "name", "context": "brief context"}},
        ...
    ]
}}"""

                try:
                    response = await client.chat_completion(
                        messages=[{"role": "user", "content": analysis_prompt}],
                        model="anthropic/claude-3.5-sonnet",
                        temperature=0.3,
                        max_tokens=1000
                    )
                    
                    ai_text = response['choices'][0]['message']['content']
                    
                    # Extract JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', ai_text, re.DOTALL)
                    if json_match:
                        analysis = json.loads(json_match.group())
                    else:
                        logger.warning(f"Could not parse AI analysis for thread {thread_id}")
                        continue
                    
                    # Create signals for topics discussed
                    for topic in analysis.get('topics', []):
                        if topic['relevance'] >= 6:
                            signals.append(self._create_signal(
                                signal_type='topic_discussed',
                                data={
                                    'thread_id': thread_id,
                                    'keyword': topic['keyword'],
                                    'relevance': topic['relevance'],
                                    'category': topic.get('category', 'general'),
                                    'message_count': len(thread_messages),
                                    'latest_mention': thread_messages[0]['created_at'].isoformat()
                                },
                                priority=min(topic['relevance'], 7),
                                expires_hours=48
                            ))
                            
                            logger.debug(f"Topic signal: {topic['keyword']} (relevance: {topic['relevance']})")
                    
                    # Create signals for questions needing follow-up
                    for question in analysis.get('questions', []):
                        if question.get('needs_followup', False):
                            signals.append(self._create_signal(
                                signal_type='question_asked',
                                data={
                                    'thread_id': thread_id,
                                    'question_text': question['question'],
                                    'asked_at': thread_messages[0]['created_at'].isoformat()
                                },
                                priority=6,
                                expires_hours=72
                            ))
                            
                            logger.debug(f"Question signal: {question['question'][:50]}...")
                    
                    # Create signals for projects mentioned
                    for project in analysis.get('projects', []):
                        signals.append(self._create_signal(
                            signal_type='project_mentioned',
                            data={
                                'thread_id': thread_id,
                                'project_name': project['project_name'],
                                'context': project.get('context', ''),
                                'mentioned_at': thread_messages[0]['created_at'].isoformat()
                            },
                            priority=7,
                            expires_hours=168
                        ))
                        
                        logger.info(f"Project signal: {project['project_name']}")
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse AI analysis JSON for thread {thread_id}: {e}")
                except Exception as e:
                    logger.error(f"Error analyzing thread {thread_id}: {e}")
            
            logger.info(f"ConversationContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting conversation signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of conversation data source"""
        try:
            total_messages = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM conversation_messages WHERE role = 'user'"
            )
            
            recent_messages = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM conversation_messages 
                   WHERE role = 'user' AND created_at >= NOW() - INTERVAL '24 hours'"""
            )
            
            active_threads = await self.db.fetch_one(
                """SELECT COUNT(DISTINCT thread_id) as count FROM conversation_messages 
                   WHERE created_at >= NOW() - INTERVAL '24 hours'"""
            )
            
            return {
                'collector': 'ConversationContextCollector',
                'total_user_messages': total_messages['count'] if total_messages else 0,
                'recent_messages_24h': recent_messages['count'] if recent_messages else 0,
                'active_threads_24h': active_threads['count'] if active_threads else 0,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting conversation state: {e}")
            return {
                'collector': 'ConversationContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# CALENDAR CONTEXT COLLECTOR - Monitors Google Calendar events
#===============================================================================

# Singleton instance
_calendar_collector: Optional['CalendarContextCollector'] = None


def get_calendar_collector() -> 'CalendarContextCollector':
    """Get singleton CalendarContextCollector instance"""
    global _calendar_collector
    if _calendar_collector is None:
        _calendar_collector = CalendarContextCollector()
    return _calendar_collector


class CalendarContextCollector(ContextCollector):
    """
    Monitors Google Calendar for upcoming events that need attention.
    
    Produces signals for:
    - Events within 24 hours (urgent)
    - Events within 48 hours (upcoming)
    - Events needing preparation
    - Meeting clusters (busy days)
    """
    
    async def collect_signals(self, lookback_hours: int = 0) -> List[ContextSignal]:
        """
        Collect calendar signals for upcoming events.
        
        Note: lookback_hours not used here - we look FORWARD at upcoming events.
        """
        signals = []
        
        try:
            now = datetime.now(timezone.utc)
            
            # Query: Get upcoming events for next 7 days
            events_query = """
                SELECT 
                    id,
                    event_id,
                    summary as event_title,
                    description,
                    location,
                    start_time,
                    end_time,
                    attendees,
                    calendar_name,
                    is_all_day,
                    is_cancelled
                FROM google_calendar_events
                WHERE start_time BETWEEN $1 AND $2
                AND is_cancelled = false
                ORDER BY start_time ASC
            """
            
            seven_days_ahead = now + timedelta(days=7)
            events = await self.db.fetch_all(events_query, now, seven_days_ahead)
            
            if not events:
                logger.info("CalendarContextCollector: No upcoming events found")
                return signals
            
            logger.info(f"CalendarContextCollector: Processing {len(events)} upcoming events")
            
            # Track events by date for cluster detection
            events_by_date = {}
            
            for event in events:
                start_time = event['start_time']
                hours_until = (start_time - now).total_seconds() / 3600
                event_date = start_time.date()
                
                # Track for cluster detection
                if event_date not in events_by_date:
                    events_by_date[event_date] = []
                events_by_date[event_date].append(event)
                
                # Signal 1: Event within 24 hours (HIGH PRIORITY)
                if hours_until <= 24:
                    signals.append(self._create_signal(
                        signal_type='event_upcoming_24h',
                        data={
                            'event_id': str(event['id']),
                            'event_title': event['event_title'],
                            'start_time': start_time.isoformat(),
                            'end_time': event['end_time'].isoformat() if event['end_time'] else None,
                            'location': event['location'],
                            'attendees': event['attendees'],
                            'hours_until': round(hours_until, 1),
                            'calendar_name': event['calendar_name']
                        },
                        priority=9,
                        expires_hours=int(hours_until) + 2
                    ))
                    
                    logger.info(f"Urgent: Event in {hours_until:.1f}h - {event['event_title'] or 'Untitled Event'}")
                
                # Signal 2: Event within 48 hours (MEDIUM PRIORITY)
                elif hours_until <= 48:
                    signals.append(self._create_signal(
                        signal_type='event_upcoming_48h',
                        data={
                            'event_id': str(event['id']),
                            'event_title': event['event_title'],
                            'start_time': start_time.isoformat(),
                            'end_time': event['end_time'].isoformat() if event['end_time'] else None,
                            'location': event['location'],
                            'attendees': event['attendees'],
                            'hours_until': round(hours_until, 1),
                            'calendar_name': event['calendar_name']
                        },
                        priority=7,
                        expires_hours=int(hours_until) + 2
                    ))
                    
                    logger.debug(f"Upcoming: Event in {hours_until:.1f}h - {event['event_title'] or 'Untitled Event'}")
                
                # Signal 3: Check if event needs preparation
                needs_prep = self._check_if_needs_preparation(event)
                
                if needs_prep and hours_until > 2:
                    signals.append(self._create_signal(
                        signal_type='prep_time_needed',
                        data={
                            'event_id': str(event['id']),
                            'event_title': event['event_title'],
                            'start_time': start_time.isoformat(),
                            'hours_until': round(hours_until, 1),
                            'prep_reason': needs_prep['reason'],
                            'suggested_prep_hours': needs_prep['hours']
                        },
                        priority=8,
                        expires_hours=int(hours_until) - 2
                    ))
                    
                    logger.info(f"Prep needed: {event['event_title'] or 'Untitled Event'} - {needs_prep['reason']}")
            
            # Signal 4: Detect meeting clusters (multiple meetings same day)
            for event_date, day_events in events_by_date.items():
                if len(day_events) >= 3:
                    total_minutes = sum([
                        (e['end_time'] - e['start_time']).total_seconds() / 60
                        for e in day_events
                        if e['end_time']
                    ])
                    
                    hours_until_first = (day_events[0]['start_time'] - now).total_seconds() / 3600
                    
                    signals.append(self._create_signal(
                        signal_type='meeting_cluster',
                        data={
                            'date': event_date.isoformat(),
                            'meeting_count': len(day_events),
                            'total_minutes': round(total_minutes),
                            'first_meeting': day_events[0]['event_title'] or 'Untitled Event',
                            'last_meeting': day_events[-1]['event_title'] or 'Untitled Event',
                            'hours_until_first': round(hours_until_first, 1),
                            'events': [
                                {
                                    'title': e['event_title'] or 'Untitled Event',
                                    'start': e['start_time'].isoformat()
                                }
                                for e in day_events
                            ]
                        },
                        priority=7,
                        expires_hours=int(hours_until_first) if hours_until_first > 0 else 1
                    ))
                    
                    logger.warning(f"Meeting cluster detected: {len(day_events)} meetings on {event_date}")
            
            logger.info(f"CalendarContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting calendar signals: {e}", exc_info=True)
        
        return signals
    
    def _check_if_needs_preparation(self, event: Dict) -> Optional[Dict[str, Any]]:
        """
        Check if an event likely needs preparation time.
        
        Returns dict with 'reason' and 'hours' if prep needed, None otherwise.
        """
        title_lower = (event['event_title'] or '').lower()
        description_lower = (event['description'] or '').lower()
        
        prep_keywords = {
            'presentation': {'hours': 2, 'reason': 'Presentation requires prep'},
            'demo': {'hours': 1, 'reason': 'Demo needs setup'},
            'pitch': {'hours': 2, 'reason': 'Pitch requires practice'},
            'interview': {'hours': 1, 'reason': 'Interview prep recommended'},
            'review': {'hours': 1, 'reason': 'Materials should be reviewed'},
            'workshop': {'hours': 1, 'reason': 'Workshop materials needed'},
            'training': {'hours': 1, 'reason': 'Training prep required'},
            'board meeting': {'hours': 2, 'reason': 'Board meeting needs thorough prep'},
            'client meeting': {'hours': 1, 'reason': 'Client research recommended'},
        }
        
        for keyword, prep_info in prep_keywords.items():
            if keyword in title_lower or keyword in description_lower:
                return prep_info
        
        # Large meetings often need prep
        if event['attendees'] and len(event['attendees']) >= 5:
            return {'hours': 1, 'reason': 'Large meeting with 5+ attendees'}
        
        return None
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of calendar data source"""
        try:
            now = datetime.now(timezone.utc)
            
            total_events = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM google_calendar_events"
            )
            
            upcoming_events = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_calendar_events 
                   WHERE start_time BETWEEN $1 AND $2 
                   AND is_cancelled = false""",
                now, now + timedelta(days=7)
            )
            
            urgent_events = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_calendar_events 
                   WHERE start_time BETWEEN $1 AND $2 
                   AND is_cancelled = false""",
                now, now + timedelta(hours=24)
            )
            
            next_event = await self.db.fetch_one(
                """SELECT summary as event_title, start_time FROM google_calendar_events 
                   WHERE start_time > $1 AND is_cancelled = false 
                   ORDER BY start_time ASC LIMIT 1""",
                now
            )
            
            return {
                'collector': 'CalendarContextCollector',
                'total_events': total_events['count'] if total_events else 0,
                'upcoming_7_days': upcoming_events['count'] if upcoming_events else 0,
                'urgent_24h': urgent_events['count'] if urgent_events else 0,
                'next_event': next_event['event_title'] if next_event else None,
                'next_event_time': next_event['start_time'].isoformat() if next_event else None,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting calendar state: {e}")
            return {
                'collector': 'CalendarContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# EMAIL CONTEXT COLLECTOR - Monitors Gmail priority messages
#===============================================================================

# Singleton instance
_email_collector: Optional['EmailContextCollector'] = None


def get_email_collector() -> 'EmailContextCollector':
    """Get singleton EmailContextCollector instance"""
    global _email_collector
    if _email_collector is None:
        _email_collector = EmailContextCollector()
    return _email_collector


class EmailContextCollector(ContextCollector):
    """
    Monitors Gmail for high-priority messages that need attention.
    
    Produces signals for:
    - High-priority emails (flagged by Gmail analysis)
    - Emails requiring response
    - Follow-up needed emails
    """
    
    async def collect_signals(self, lookback_hours: int = 48) -> List[ContextSignal]:
        """
        Collect email signals from last 48 hours.
        
        48 hours gives us time to catch important emails without overwhelming
        with too many signals.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query: Get high-priority emails from gmail analysis
            # FIXED: Include all columns we reference later
            emails_query = """
                SELECT
                    id,
                    message_id,
                    thread_id,
                    sender_email,
                    sender_name,
                    subject_line as subject,
                    snippet,
                    priority_level,
                    priority_score,
                    category,
                    categories,
                    requires_response,
                    urgency_indicators,
                    email_date as received_at
                FROM google_gmail_analysis
                WHERE user_id = $1
                AND email_date >= $2
                AND (
                    priority_level IN ('high', 'urgent')
                    OR requires_response = true
                    OR subject_line ILIKE '%urgent%'
                    OR subject_line ILIKE '%asap%'
                    OR subject_line ILIKE '%important%'
                )
                ORDER BY email_date DESC
                LIMIT 20
            """
            
            # FIXED: Use self.user_id (inherited from base class, set to USER_ID constant)
            emails = await self.db.fetch_all(emails_query, self.user_id, lookback_time)
            
            if not emails:
                logger.info("EmailContextCollector: No high-priority emails found")
                return signals
            
            logger.info(f"EmailContextCollector: Processing {len(emails)} high-priority emails")
            
            for email in emails:
                hours_old = (datetime.utcnow() - email['received_at']).total_seconds() / 3600
                
                # Determine base priority from email priority level
                if email['priority_level'] == 'urgent':
                    base_priority = 9
                elif email['priority_level'] == 'high':
                    base_priority = 8
                else:
                    base_priority = 7
                
                # Adjust priority based on age
                if hours_old > 24:
                    priority = max(base_priority - 1, 6)
                else:
                    priority = base_priority
                
                # Signal 1: High priority email received
                signal_data = {
                    'email_id': str(email['id']),
                    'message_id': email['message_id'],
                    'thread_id': email['thread_id'],
                    'sender_email': email['sender_email'],
                    'sender_name': email['sender_name'],
                    'subject': email['subject'],
                    'snippet': email['snippet'],
                    'received_at': email['received_at'].isoformat(),
                    'hours_old': round(hours_old, 1),
                    'priority_level': email['priority_level'],
                    'priority_score': float(email['priority_score']) if email['priority_score'] else None,
                    'category': email['category']
                }
                
                signals.append(self._create_signal(
                    signal_type='email_priority_high',
                    data=signal_data,
                    priority=priority,
                    expires_hours=48
                ))
                
                logger.debug(f"High-priority email from {email['sender_email']}: {email['subject'][:50] if email['subject'] else 'No subject'}...")
                
                # Signal 2: Email requires response
                if email['requires_response']:
                    signals.append(self._create_signal(
                        signal_type='email_requires_response',
                        data={
                            'email_id': str(email['id']),
                            'message_id': email['message_id'],
                            'thread_id': email['thread_id'],
                            'sender_email': email['sender_email'],
                            'sender_name': email['sender_name'],
                            'subject': email['subject'],
                            'received_at': email['received_at'].isoformat(),
                            'hours_old': round(hours_old, 1),
                            'priority_level': email['priority_level']
                        },
                        priority=8,
                        expires_hours=72
                    ))
                    
                    logger.info(f"Response needed from {email['sender_name'] or email['sender_email']}: {email['subject'][:50] if email['subject'] else 'No subject'}...")
                
                # Signal 3: Follow-up needed based on sender/context
                follow_up_needed = self._check_follow_up_needed(email)
                
                if follow_up_needed:
                    signals.append(self._create_signal(
                        signal_type='email_follow_up',
                        data={
                            **signal_data,
                            'follow_up_reason': follow_up_needed['reason'],
                            'suggested_action': follow_up_needed['action']
                        },
                        priority=7,
                        expires_hours=72
                    ))
                    
                    logger.debug(f"Follow-up needed: {follow_up_needed['reason']}")
            
            logger.info(f"EmailContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting email signals: {e}", exc_info=True)
        
        return signals
    
    def _check_follow_up_needed(self, email: Dict) -> Optional[Dict[str, str]]:
        """
        Determine if email needs follow-up based on content analysis.
        
        Returns dict with 'reason' and 'action' if follow-up needed, None otherwise.
        """
        subject_lower = (email['subject'] or '').lower()
        snippet_lower = (email['snippet'] or '').lower()
        urgency_indicators = email['urgency_indicators'] or []
        
        # Check for meeting-related emails
        meeting_keywords = ['meeting', 'call', 'sync', 'catch up', 'discuss']
        if any(kw in subject_lower for kw in meeting_keywords):
            return {
                'reason': 'Meeting coordination needed',
                'action': 'Schedule or confirm meeting time'
            }
        
        # Check for deadline mentions
        deadline_keywords = ['deadline', 'due', 'by friday', 'by monday', 'eod', 'asap']
        if any(kw in snippet_lower for kw in deadline_keywords):
            return {
                'reason': 'Deadline mentioned in email',
                'action': 'Review and prioritize task'
            }
        
        # Check urgency indicators from AI analysis
        if urgency_indicators:
            if 'time_sensitive' in urgency_indicators:
                return {
                    'reason': 'Time-sensitive content detected',
                    'action': 'Review and respond quickly'
                }
            if 'decision_required' in urgency_indicators:
                return {
                    'reason': 'Decision or approval needed',
                    'action': 'Make decision and communicate'
                }
        
        # Check for question marks
        if '?' in (email['snippet'] or '') or '?' in (email['subject'] or ''):
            return {
                'reason': 'Question asked in email',
                'action': 'Provide answer or clarification'
            }
        
        # Check categories for important types
        categories = email['categories'] or []
        if 'proposal' in categories or 'contract' in categories:
            return {
                'reason': 'Business proposal or contract',
                'action': 'Review and provide feedback'
            }
        
        return None
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of email data source"""
        try:
            total_emails = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM google_gmail_analysis"
            )
            
            high_priority = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_gmail_analysis 
                   WHERE email_date >= NOW() - INTERVAL '48 hours'
                   AND priority_level IN ('high', 'urgent')"""
            )
            
            needs_response = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_gmail_analysis 
                   WHERE email_date >= NOW() - INTERVAL '48 hours'
                   AND requires_response = true"""
            )
            
            latest_email = await self.db.fetch_one(
                """SELECT sender_name, subject_line as subject, email_date as received_at 
                   FROM google_gmail_analysis 
                   ORDER BY email_date DESC LIMIT 1"""
            )
            
            return {
                'collector': 'EmailContextCollector',
                'total_analyzed_emails': total_emails['count'] if total_emails else 0,
                'high_priority_48h': high_priority['count'] if high_priority else 0,
                'needs_response_48h': needs_response['count'] if needs_response else 0,
                'latest_email_from': latest_email['sender_name'] if latest_email else None,
                'latest_email_subject': latest_email['subject'] if latest_email else None,
                'latest_email_time': latest_email['received_at'].isoformat() if latest_email else None,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting email state: {e}")
            return {
                'collector': 'EmailContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# TREND CONTEXT COLLECTOR - Monitors trend_monitoring for opportunities
#===============================================================================

# Singleton instance
_trend_collector: Optional['TrendContextCollector'] = None


def get_trend_collector() -> 'TrendContextCollector':
    """Get singleton TrendContextCollector instance"""
    global _trend_collector
    if _trend_collector is None:
        _trend_collector = TrendContextCollector()
    return _trend_collector


class TrendContextCollector(ContextCollector):
    """
    Monitors trend_monitoring table for trending topics and opportunities.
    
    Produces signals for:
    - Trend spikes (score jumped significantly)
    - Rising trends (momentum = 'rising')
    - Stable high trends (consistently high scores)
    - New trend opportunities created
    """
    
    async def collect_signals(self, lookback_hours: int = 72) -> List[ContextSignal]:
        """
        Collect trend signals from last 72 hours (3 days).
        
        Trends change relatively slowly, so 3-day lookback captures
        meaningful changes without missing spikes.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # First check if trend_monitoring has any data
            count_check = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring"
            )
            
            if not count_check or count_check['count'] == 0:
                logger.info("TrendContextCollector: No trends in monitoring table")
                return signals
            
            # Query 1: Get recent high-scoring or rising trends
            trends_query = """
                SELECT
                    id,
                    keyword,
                    business_area,
                    trend_score,
                    previous_score,
                    trend_momentum,
                    regional_score,
                    trend_date,
                    created_at,
                    updated_at
                FROM trend_monitoring
                WHERE trend_date >= $1
                AND trend_score >= 60
                ORDER BY trend_score DESC
                LIMIT 50
            """
            
            trends = await self.db.fetch_all(trends_query, lookback_time.date())
            
            if not trends:
                logger.info("TrendContextCollector: No significant trends found")
                return signals
            
            logger.info(f"TrendContextCollector: Processing {len(trends)} trends")
            
            for trend in trends:
                trend_score = trend['trend_score'] or 0
                previous_score = trend['previous_score'] or 0
                momentum = trend['trend_momentum'] or 'stable'
                
                # Calculate score change
                score_change = trend_score - previous_score if previous_score else 0
                
                # Signal 1: Trend SPIKE (big jump in score)
                if score_change >= 20:
                    signals.append(self._create_signal(
                        signal_type='trend_spike',
                        data={
                            'trend_id': str(trend['id']),
                            'keyword': trend['keyword'],
                            'business_area': trend['business_area'],
                            'trend_score': trend_score,
                            'previous_score': previous_score,
                            'score_change': score_change,
                            'momentum': momentum,
                            'trend_date': trend['trend_date'].isoformat()
                        },
                        priority=9,
                        expires_hours=24
                    ))
                    
                    logger.info(f"🔥 Trend SPIKE: {trend['keyword']} jumped {score_change} points to {trend_score}")
                
                # Signal 2: Rising trend (momentum indicator)
                elif momentum == 'rising' and trend_score >= 70:
                    signals.append(self._create_signal(
                        signal_type='trend_rising',
                        data={
                            'trend_id': str(trend['id']),
                            'keyword': trend['keyword'],
                            'business_area': trend['business_area'],
                            'trend_score': trend_score,
                            'momentum': momentum,
                            'trend_date': trend['trend_date'].isoformat()
                        },
                        priority=7,
                        expires_hours=48
                    ))
                    
                    logger.debug(f"📈 Rising trend: {trend['keyword']} at {trend_score}")
                
                # Signal 3: Stable high trend (consistently high)
                elif trend_score >= 80:
                    signals.append(self._create_signal(
                        signal_type='trend_high',
                        data={
                            'trend_id': str(trend['id']),
                            'keyword': trend['keyword'],
                            'business_area': trend['business_area'],
                            'trend_score': trend_score,
                            'momentum': momentum,
                            'trend_date': trend['trend_date'].isoformat()
                        },
                        priority=6,
                        expires_hours=72
                    ))
                    
                    logger.debug(f"📊 High trend: {trend['keyword']} stable at {trend_score}")
            
            # Query 2: Get recent trend opportunities
            opportunities_query = """
                SELECT
                    id,
                    keyword,
                    business_area,
                    opportunity_type,
                    urgency_level,
                    trend_momentum,
                    opportunity_score,
                    content_angle,
                    target_audience,
                    suggested_action,
                    created_at
                FROM trend_opportunities
                WHERE created_at >= $1
                AND processed = false
                AND user_feedback IS NULL
                ORDER BY opportunity_score DESC
                LIMIT 20
            """
            
            opportunities = await self.db.fetch_all(opportunities_query, lookback_time)
            
            for opp in opportunities:
                priority = 8 if opp['urgency_level'] == 'high' else 7
                
                signals.append(self._create_signal(
                    signal_type='trend_opportunity',
                    data={
                        'opportunity_id': str(opp['id']),
                        'keyword': opp['keyword'],
                        'business_area': opp['business_area'],
                        'opportunity_type': opp['opportunity_type'],
                        'urgency_level': opp['urgency_level'],
                        'opportunity_score': float(opp['opportunity_score']) if opp['opportunity_score'] else 0,
                        'content_angle': opp['content_angle'],
                        'target_audience': opp['target_audience'],
                        'suggested_action': opp['suggested_action'],
                        'created_at': opp['created_at'].isoformat()
                    },
                    priority=priority,
                    expires_hours=48
                ))
                
                logger.info(f"💡 Trend opportunity: {opp['keyword']} ({opp['opportunity_type']})")
            
            logger.info(f"TrendContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting trend signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of trends data source"""
        try:
            total_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring"
            )
            
            high_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring WHERE trend_score >= 70"
            )
            
            rising_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring WHERE trend_momentum = 'rising'"
            )
            
            total_opportunities = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_opportunities"
            )
            
            top_trend = await self.db.fetch_one(
                """SELECT keyword, trend_score, business_area 
                   FROM trend_monitoring 
                   ORDER BY trend_score DESC LIMIT 1"""
            )
            
            latest_check = await self.db.fetch_one(
                "SELECT MAX(last_checked) as latest FROM trend_monitoring"
            )
            
            return {
                'collector': 'TrendContextCollector',
                'total_trends_monitored': total_trends['count'] if total_trends else 0,
                'high_score_trends': high_trends['count'] if high_trends else 0,
                'rising_trends': rising_trends['count'] if rising_trends else 0,
                'total_opportunities': total_opportunities['count'] if total_opportunities else 0,
                'top_trend_keyword': top_trend['keyword'] if top_trend else None,
                'top_trend_score': top_trend['trend_score'] if top_trend else None,
                'top_trend_area': top_trend['business_area'] if top_trend else None,
                'latest_check': latest_check['latest'].isoformat() if latest_check and latest_check['latest'] else None,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting trend state: {e}")
            return {
                'collector': 'TrendContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# BLUESKY CONTEXT COLLECTOR - Monitors Bluesky engagement opportunities
#===============================================================================

# Singleton instance
_bluesky_collector: Optional['BlueskyContextCollector'] = None


def get_bluesky_collector() -> 'BlueskyContextCollector':
    """Get singleton BlueskyContextCollector instance"""
    global _bluesky_collector
    if _bluesky_collector is None:
        _bluesky_collector = BlueskyContextCollector()
    return _bluesky_collector


class BlueskyContextCollector(ContextCollector):
    """
    Monitors Bluesky posts and conversations for engagement opportunities.
    
    Produces signals for:
    - Posts in approval queue
    - Recent posts with high engagement
    - Conversations matching user keywords
    """
    
    async def collect_signals(self, lookback_hours: int = 24) -> List[ContextSignal]:
        """
        Collect Bluesky signals from recent activity.
        
        24-hour lookback to catch recent conversations.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Signal 1: Posts in approval queue
            queue_query = """
                SELECT
                    id,
                    post_uri,
                    detected_by_account,
                    post_text,
                    matched_keywords,
                    engagement_score,
                    opportunity_type,
                    detected_at
                FROM bluesky_engagement_opportunities
                WHERE user_response IS NULL
                AND detected_at >= $1
                AND already_engaged = false
                ORDER BY engagement_score DESC
                LIMIT 10
            """
            
            try:
                queued_posts = await self.db.fetch_all(queue_query, lookback_time)
                
                for post in queued_posts:
                    signals.append(self._create_signal(
                        signal_type='bluesky_approval_needed',
                        data={
                            'opportunity_id': str(post['id']),
                            'account': post['detected_by_account'],
                            'post_text': post['post_text'][:200],
                            'engagement_score': float(post['engagement_score']),
                            'opportunity_type': post['opportunity_type'],
                            'post_uri': post['post_uri']
                        },
                        priority=8,
                        expires_hours=12
                    ))
                
                if queued_posts:
                    logger.info(f"🦋 Found {len(queued_posts)} Bluesky posts awaiting approval")
            
            except Exception as e:
                logger.debug(f"Bluesky approval queue empty or table doesn't exist: {e}")
            
            # Signal 2: Recent high-engagement posts
            posts_query = """
                SELECT
                    id,
                    account_handle,
                    post_text,
                    likes_count,
                    reposts_count,
                    replies_count,
                    quotes_count,
                    engagement_score,
                    posted_at
                FROM bluesky_posts
                WHERE posted_at >= $1
                AND (likes_count + reposts_count + replies_count) >= 5
                ORDER BY (likes_count + reposts_count + replies_count) DESC
                LIMIT 5
            """
            
            try:
                high_engagement_posts = await self.db.fetch_all(posts_query, lookback_time)
                
                for post in high_engagement_posts:
                    total_engagement = (post['likes_count'] or 0) + (post['reposts_count'] or 0) + (post['replies_count'] or 0)
                    
                    signals.append(self._create_signal(
                        signal_type='bluesky_post_performance',
                        data={
                            'post_id': str(post['id']),
                            'account': post['account_handle'],
                            'post_text': post['post_text'][:200],
                            'total_engagement': total_engagement,
                            'likes': post['likes_count'],
                            'reposts': post['reposts_count'],
                            'replies': post['replies_count']
                        },
                        priority=6,
                        expires_hours=72
                    ))
                
                if high_engagement_posts:
                    logger.info(f"🦋 Found {len(high_engagement_posts)} high-performing Bluesky posts")
            
            except Exception as e:
                logger.debug(f"Bluesky posts query failed or table empty: {e}")
            
            logger.info(f"BlueskyContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting Bluesky signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of Bluesky data"""
        try:
            pending = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM bluesky_engagement_opportunities 
                   WHERE user_response IS NULL 
                   AND already_engaged = false"""
            )
            
            recent_posts = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM bluesky_posts 
                   WHERE posted_at >= NOW() - INTERVAL '7 days'"""
            )
            
            total_opportunities = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM bluesky_engagement_opportunities"""
            )
            
            return {
                'collector': 'BlueskyContextCollector',
                'pending_opportunities': pending['count'] if pending else 0,
                'recent_posts_7d': recent_posts['count'] if recent_posts else 0,
                'total_opportunities_detected': total_opportunities['count'] if total_opportunities else 0,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting Bluesky state: {e}")
            return {
                'collector': 'BlueskyContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# KNOWLEDGE CONTEXT COLLECTOR - Matches knowledge base to current topics
#===============================================================================

# Singleton instance
_knowledge_collector: Optional['KnowledgeContextCollector'] = None


def get_knowledge_collector() -> 'KnowledgeContextCollector':
    """Get singleton KnowledgeContextCollector instance"""
    global _knowledge_collector
    if _knowledge_collector is None:
        _knowledge_collector = KnowledgeContextCollector()
    return _knowledge_collector


class KnowledgeContextCollector(ContextCollector):
    """
    Matches knowledge base entries against topics from other signals.
    
    This is a "supportive" collector - it doesn't generate urgent signals
    on its own, but helps surface relevant knowledge when other collectors
    find interesting topics.
    
    Produces signals for:
    - Relevant knowledge exists for a topic
    - Knowledge gap detected (topic discussed but no entry exists)
    - Recently accessed knowledge entries
    """
    
    def __init__(self):
        super().__init__()
        self.context_topics: List[str] = []
    
    def set_context_topics(self, topics: List[str]):
        """Set topics to search for in knowledge base"""
        self.context_topics = topics
    
    async def collect_signals(self, lookback_hours: int = 72) -> List[ContextSignal]:
        """
        Collect knowledge-related signals.
        
        Searches for recently accessed or highly relevant knowledge entries
        that might be useful for current context.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query 1: Recently accessed knowledge entries
            recent_query = """
                SELECT 
                    id,
                    title,
                    content_type,
                    summary,
                    key_topics,
                    relevance_score,
                    access_count,
                    last_accessed,
                    created_at
                FROM knowledge_entries
                WHERE last_accessed >= $1
                ORDER BY last_accessed DESC
                LIMIT 20
            """
            
            recent_entries = await self.db.fetch_all(recent_query, lookback_time)
            
            for entry in recent_entries:
                if entry['access_count'] and entry['access_count'] >= 3:
                    signals.append(self._create_signal(
                        signal_type='knowledge_frequently_accessed',
                        data={
                            'entry_id': str(entry['id']),
                            'title': entry['title'],
                            'content_type': entry['content_type'],
                            'summary': entry['summary'][:200] if entry['summary'] else None,
                            'topics': entry['key_topics'],
                            'access_count': entry['access_count'],
                            'last_accessed': entry['last_accessed'].isoformat() if entry['last_accessed'] else None
                        },
                        priority=5,
                        expires_hours=168
                    ))
            
            # Query 2: High-relevance knowledge entries
            relevant_query = """
                SELECT 
                    id,
                    title,
                    content_type,
                    summary,
                    key_topics,
                    relevance_score
                FROM knowledge_entries
                WHERE relevance_score >= 8
                ORDER BY relevance_score DESC
                LIMIT 10
            """
            
            high_relevance = await self.db.fetch_all(relevant_query)
            
            for entry in high_relevance:
                signals.append(self._create_signal(
                    signal_type='knowledge_high_relevance',
                    data={
                        'entry_id': str(entry['id']),
                        'title': entry['title'],
                        'content_type': entry['content_type'],
                        'summary': entry['summary'][:200] if entry['summary'] else None,
                        'topics': entry['key_topics'],
                        'relevance_score': float(entry['relevance_score']) if entry['relevance_score'] else None
                    },
                    priority=4,
                    expires_hours=336
                ))
            
            # Query 3: If context topics provided, search for matches
            if self.context_topics:
                for topic in self.context_topics[:5]:  # Limit to 5 topics
                    topic_query = """
                        SELECT 
                            id,
                            title,
                            content_type,
                            summary,
                            key_topics,
                            relevance_score
                        FROM knowledge_entries
                        WHERE search_vector @@ plainto_tsquery('english', $1)
                        ORDER BY relevance_score DESC
                        LIMIT 3
                    """
                    
                    matches = await self.db.fetch_all(topic_query, topic)
                    
                    for match in matches:
                        signals.append(self._create_signal(
                            signal_type='knowledge_topic_match',
                            data={
                                'entry_id': str(match['id']),
                                'title': match['title'],
                                'matched_topic': topic,
                                'content_type': match['content_type'],
                                'summary': match['summary'][:200] if match['summary'] else None,
                                'relevance_score': float(match['relevance_score']) if match['relevance_score'] else None
                            },
                            priority=6,
                            expires_hours=72
                        ))
            
            logger.info(f"KnowledgeContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting knowledge signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of knowledge base"""
        try:
            total_entries = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM knowledge_entries"
            )
            
            processed_entries = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM knowledge_entries WHERE processed = true"
            )
            
            recent_access = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM knowledge_entries 
                   WHERE last_accessed >= NOW() - INTERVAL '7 days'"""
            )
            
            avg_relevance = await self.db.fetch_one(
                "SELECT AVG(relevance_score) as avg FROM knowledge_entries"
            )
            
            return {
                'collector': 'KnowledgeContextCollector',
                'total_entries': total_entries['count'] if total_entries else 0,
                'processed_entries': processed_entries['count'] if processed_entries else 0,
                'recently_accessed_7d': recent_access['count'] if recent_access else 0,
                'avg_relevance_score': round(avg_relevance['avg'], 2) if avg_relevance and avg_relevance['avg'] else 0,
                'context_topics_set': len(self.context_topics),
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting knowledge state: {e}")
            return {
                'collector': 'KnowledgeContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# WEATHER CONTEXT COLLECTOR - Monitors weather for health/calendar impacts
#===============================================================================

# Singleton instance
_weather_collector: Optional['WeatherContextCollector'] = None


def get_weather_collector() -> 'WeatherContextCollector':
    """Get singleton WeatherContextCollector instance"""
    global _weather_collector
    if _weather_collector is None:
        _weather_collector = WeatherContextCollector()
    return _weather_collector


class WeatherContextCollector(ContextCollector):
    """
    Monitors weather data for health impacts and calendar correlations.
    
    Produces signals for:
    - High UV index (sun allergy warning)
    - High headache risk (pressure/humidity)
    - Severe weather alerts
    - Pressure changes (headache trigger)
    - Weather forecast alerts
    """
    
    async def collect_signals(self, lookback_hours: int = 6) -> List[ContextSignal]:
        """
        Collect weather signals from recent readings.
        
        6-hour lookback since weather changes frequently.
        """
        signals = []
        
        try:
            # Query 1: Get latest weather reading
            latest_query = """
                SELECT 
                    id,
                    location,
                    timestamp,
                    temperature,
                    temperature_apparent as feels_like,
                    humidity,
                    wind_speed,
                    pressure_surface_level as pressure,
                    uv_index,
                    weather_description,
                    headache_risk_level,
                    headache_risk_score,
                    headache_risk_factors,
                    severe_weather_alert,
                    alert_description
                FROM weather_readings
                ORDER BY created_at DESC
                LIMIT 1
            """
            
            latest = await self.db.fetch_one(latest_query)
            
            if not latest:
                logger.info("WeatherContextCollector: No weather data available")
                return signals
            
            logger.info(f"WeatherContextCollector: Processing weather data for {latest['location']}")
            
            # Signal 1: UV INDEX HIGH (>4 triggers sun allergy warning)
            uv_index = latest.get('uv_index')
            if uv_index is not None and uv_index > 4:
                if uv_index >= 8:
                    uv_level = 'very_high'
                    priority = 10
                elif uv_index >= 6:
                    uv_level = 'high'
                    priority = 9
                else:
                    uv_level = 'moderate_high'
                    priority = 8
                
                signals.append(self._create_signal(
                    signal_type='uv_index_alert',
                    data={
                        'location': latest['location'],
                        'uv_index': uv_index,
                        'uv_level': uv_level,
                        'temperature': latest['temperature'],
                        'weather': latest['weather_description'],
                        'warning': f"UV index is {uv_index} - Sun protection REQUIRED for allergy",
                        'timestamp': latest['timestamp'].isoformat()
                    },
                    priority=priority,
                    expires_hours=6
                ))
                
                logger.warning(f"☀️ UV ALERT: Index {uv_index} ({uv_level}) - SUN PROTECTION REQUIRED!")
            
            # Signal 2: High headache risk
            if latest['headache_risk_level'] in ['high', 'severe']:
                priority = 8 if latest['headache_risk_level'] == 'high' else 9
                
                signals.append(self._create_signal(
                    signal_type='headache_risk_high',
                    data={
                        'location': latest['location'],
                        'risk_level': latest['headache_risk_level'],
                        'risk_score': latest['headache_risk_score'],
                        'risk_factors': latest['headache_risk_factors'],
                        'temperature': latest['temperature'],
                        'pressure': latest['pressure'],
                        'humidity': latest['humidity'],
                        'weather': latest['weather_description'],
                        'timestamp': latest['timestamp'].isoformat()
                    },
                    priority=priority,
                    expires_hours=12
                ))
                
                logger.warning(f"⚠️ {latest['headache_risk_level'].upper()} headache risk detected - Score: {latest['headache_risk_score']}")
            
            # Signal 3: Severe weather alert
            if latest['severe_weather_alert']:
                signals.append(self._create_signal(
                    signal_type='weather_alert',
                    data={
                        'location': latest['location'],
                        'alert_description': latest['alert_description'],
                        'weather': latest['weather_description'],
                        'temperature': latest['temperature'],
                        'wind_speed': latest['wind_speed'],
                        'timestamp': latest['timestamp'].isoformat()
                    },
                    priority=10,
                    expires_hours=6
                ))
                
                logger.error(f"🚨 SEVERE WEATHER ALERT: {latest['alert_description']}")
            
            # Query 2: Check for pressure changes (headache trigger)
            pressure_change_query = """
                SELECT
                    pressure_surface_level,
                    timestamp,
                    created_at
                FROM weather_readings
                WHERE created_at >= $1
                ORDER BY created_at DESC
                LIMIT 10
            """
            
            pressure_readings = await self.db.fetch_all(
                pressure_change_query,
                datetime.utcnow() - timedelta(hours=12)
            )
            
            if len(pressure_readings) >= 2:
                current_pressure = pressure_readings[0]['pressure_surface_level']
                oldest_pressure = pressure_readings[-1]['pressure_surface_level']
                
                if current_pressure is not None and oldest_pressure is not None:
                    pressure_change = current_pressure - oldest_pressure
                    
                    # Signal 4: Significant pressure drop (headache trigger)
                    if pressure_change < -0.1:
                        signals.append(self._create_signal(
                            signal_type='pressure_dropping',
                            data={
                                'current_pressure': current_pressure,
                                'previous_pressure': oldest_pressure,
                                'pressure_change': round(pressure_change, 2),
                                'hours_tracked': round(
                                    (pressure_readings[0]['created_at'] - pressure_readings[-1]['created_at']).total_seconds() / 3600,
                                    1
                                ),
                                'location': latest['location']
                            },
                            priority=7,
                            expires_hours=8
                        ))
                        
                        logger.info(f"📉 Pressure dropping: {pressure_change:.2f} inHg over last few hours")
            
            # Query 3: Check forecast for UV and weather changes
            forecast_query = """
                SELECT 
                    id,
                    forecast_time,
                    temperature,
                    pressure,
                    weather_description,
                    precipitation_chance,
                    uv_index
                FROM weather_forecast
                WHERE forecast_time BETWEEN $1 AND $2
                ORDER BY forecast_time ASC
            """
            
            now = datetime.now(timezone.utc)
            next_24h = now + timedelta(hours=24)
            
            try:
                forecast = await self.db.fetch_all(forecast_query, now, next_24h)
                
                if forecast:
                    uv_alert_sent = False
                    precip_alert_sent = False
                    
                    for period in forecast:
                        # UV forecast alert
                        if not uv_alert_sent and period.get('uv_index') and period['uv_index'] > 4:
                            hours_until = (period['forecast_time'] - now).total_seconds() / 3600
                            
                            if hours_until <= 24:
                                signals.append(self._create_signal(
                                    signal_type='uv_forecast_alert',
                                    data={
                                        'forecast_time': period['forecast_time'].isoformat(),
                                        'hours_until': round(hours_until, 1),
                                        'uv_index': period['uv_index'],
                                        'temperature': period['temperature'],
                                        'weather': period['weather_description'],
                                        'warning': f"UV index will reach {period['uv_index']} - Plan sun protection"
                                    },
                                    priority=8,
                                    expires_hours=int(hours_until) + 2
                                ))
                                
                                logger.info(f"☀️ UV Forecast Alert: Index {period['uv_index']} in {hours_until:.1f}h")
                                uv_alert_sent = True
                        
                        # High precipitation forecast
                        if not precip_alert_sent and period.get('precipitation_chance') and period['precipitation_chance'] >= 70:
                            hours_until = (period['forecast_time'] - now).total_seconds() / 3600
                            
                            if hours_until <= 24:
                                signals.append(self._create_signal(
                                    signal_type='precipitation_forecast',
                                    data={
                                        'forecast_time': period['forecast_time'].isoformat(),
                                        'hours_until': round(hours_until, 1),
                                        'precipitation_chance': period['precipitation_chance'],
                                        'weather': period['weather_description'],
                                        'temperature': period['temperature']
                                    },
                                    priority=5,
                                    expires_hours=int(hours_until) + 2
                                ))
                                
                                logger.debug(f"🌧️ High precipitation chance in {hours_until:.1f}h: {period['precipitation_chance']}%")
                                precip_alert_sent = True
                        
                        if uv_alert_sent and precip_alert_sent:
                            break
                
            except Exception as e:
                logger.debug(f"No forecast data available: {e}")
            
            logger.info(f"WeatherContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting weather signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of weather monitoring"""
        try:
            latest = await self.db.fetch_one(
                """SELECT 
                    location,
                    temperature,
                    weather_description,
                    uv_index,
                    headache_risk_level,
                    headache_risk_score,
                    severe_weather_alert,
                    timestamp,
                    created_at
                FROM weather_readings 
                ORDER BY created_at DESC LIMIT 1"""
            )
            
            total_readings = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM weather_readings"
            )
            
            high_uv_count = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM weather_readings 
                   WHERE uv_index > 4 
                   AND created_at >= NOW() - INTERVAL '7 days'"""
            )
            
            return {
                'collector': 'WeatherContextCollector',
                'total_readings': total_readings['count'] if total_readings else 0,
                'high_uv_days_7d': high_uv_count['count'] if high_uv_count else 0,
                'current_location': latest['location'] if latest else None,
                'current_temperature': latest['temperature'] if latest else None,
                'current_weather': latest['weather_description'] if latest else None,
                'current_uv': latest['uv_index'] if latest else None,
                'current_headache_risk': latest['headache_risk_level'] if latest else None,
                'last_reading': latest['created_at'].isoformat() if latest else None,
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting weather state: {e}")
            return {
                'collector': 'WeatherContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# PERFORMANCE CONTEXT COLLECTOR - Monitors content performance for learning
#===============================================================================

# Singleton instance
_performance_collector: Optional['PerformanceContextCollector'] = None


def get_performance_collector() -> 'PerformanceContextCollector':
    """Get singleton PerformanceContextCollector instance"""
    global _performance_collector
    if _performance_collector is None:
        _performance_collector = PerformanceContextCollector()
    return _performance_collector


class PerformanceContextCollector(ContextCollector):
    """
    Monitors Bluesky post analytics to learn what content performs well.
    
    Produces signals for:
    - Posts performing exceptionally well (learn from success)
    - Learning opportunities (patterns detected)
    - Timing insights (best posting times)
    
    This is a LEARNING collector - it doesn't generate urgent signals,
    but helps the system learn from content performance patterns.
    """
    
    async def collect_signals(self, lookback_hours: int = 168) -> List[ContextSignal]:
        """
        Collect performance signals from last 7 days (168 hours).
        
        7-day lookback to capture enough data for pattern detection.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query 1: Get recent post analytics
            posts_query = """
                SELECT 
                    id,
                    post_uri,
                    account_handle,
                    post_text,
                    likes_count,
                    reposts_count,
                    replies_count,
                    quotes_count,
                    total_engagement,
                    engagement_rate,
                    reach,
                    impressions,
                    topics,
                    sentiment,
                    created_at
                FROM bluesky_post_analytics
                WHERE created_at >= $1
                ORDER BY created_at DESC
            """
            
            posts = await self.db.fetch_all(posts_query, lookback_time)
            
            if not posts:
                logger.info("PerformanceContextCollector: No recent posts found")
                return signals
            
            logger.info(f"PerformanceContextCollector: Processing {len(posts)} posts")
            
            # Calculate average performance metrics for baseline
            valid_posts = [p for p in posts if p['total_engagement'] is not None]
            if valid_posts:
                avg_engagement = sum(p['total_engagement'] for p in valid_posts) / len(valid_posts)
                rate_posts = [p for p in valid_posts if p['engagement_rate']]
                avg_engagement_rate = sum(p['engagement_rate'] for p in rate_posts) / len(rate_posts) if rate_posts else 0
                
                logger.debug(f"Average engagement: {avg_engagement:.1f}, Average rate: {avg_engagement_rate:.2%}")
            else:
                avg_engagement = 0
                avg_engagement_rate = 0
            
            for post in posts:
                engagement = post['total_engagement'] or 0
                engagement_rate = post['engagement_rate'] or 0
                
                # Signal 1: Post performing exceptionally well (learn from success)
                # REALISTIC thresholds: 3x average OR 10+ engagement
                if engagement >= max(avg_engagement * 3, 10):
                    signals.append(self._create_signal(
                        signal_type='post_performing_well',
                        data={
                            'post_id': str(post['id']),
                            'account_handle': post['account_handle'],
                            'post_text': post['post_text'][:200] if post['post_text'] else None,
                            'post_uri': post['post_uri'],
                            'likes': post['likes_count'],
                            'reposts': post['reposts_count'],
                            'replies': post['replies_count'],
                            'total_engagement': engagement,
                            'engagement_rate': engagement_rate,
                            'reach': post['reach'],
                            'impressions': post['impressions'],
                            'topics': post['topics'],
                            'sentiment': post['sentiment'],
                            'performance_vs_average': round(engagement / avg_engagement, 2) if avg_engagement > 0 else 0,
                            'created_at': post['created_at'].isoformat()
                        },
                        priority=5,
                        expires_hours=336
                    ))
                    
                    logger.info(f"✅ High-performing post: {engagement} engagement ({engagement / avg_engagement:.1f}x avg)" if avg_engagement > 0 else f"✅ High-performing post: {engagement} engagement")
            
            # Query 2: Look for patterns across high-performing posts
            pattern_query = """
                SELECT 
                    topics,
                    sentiment,
                    account_handle,
                    AVG(total_engagement) as avg_engagement,
                    AVG(engagement_rate) as avg_rate,
                    COUNT(*) as post_count
                FROM bluesky_post_analytics
                WHERE created_at >= $1
                AND total_engagement >= 5
                GROUP BY topics, sentiment, account_handle
                HAVING COUNT(*) >= 3
                ORDER BY avg_engagement DESC
                LIMIT 5
            """
            
            try:
                patterns = await self.db.fetch_all(pattern_query, lookback_time)
                
                for pattern in patterns:
                    if pattern['avg_engagement'] > avg_engagement and pattern['avg_engagement'] >= 5:
                        signals.append(self._create_signal(
                            signal_type='learning_opportunity',
                            data={
                                'pattern_type': 'topic_sentiment_combo',
                                'topics': pattern['topics'],
                                'sentiment': pattern['sentiment'],
                                'account_handle': pattern['account_handle'],
                                'avg_engagement': round(pattern['avg_engagement'], 1),
                                'avg_engagement_rate': round(pattern['avg_rate'], 4) if pattern['avg_rate'] else 0,
                                'post_count': pattern['post_count'],
                                'vs_overall_average': round(pattern['avg_engagement'] / avg_engagement, 2) if avg_engagement > 0 else 0,
                                'insight': f"Posts about {pattern['topics']} with {pattern['sentiment']} sentiment perform better than average (avg: {pattern['avg_engagement']:.1f} vs {avg_engagement:.1f})"
                            },
                            priority=5,
                            expires_hours=336
                        ))
                        
                        logger.info(f"📊 Pattern detected: {pattern['topics']} + {pattern['sentiment']} performs better (avg: {pattern['avg_engagement']:.1f})")
            
            except Exception as e:
                logger.debug(f"Could not analyze patterns: {e}")
            
            # Query 3: Check for timing patterns (best posting times)
            timing_query = """
                SELECT 
                    EXTRACT(DOW FROM created_at) as day_of_week,
                    EXTRACT(HOUR FROM created_at) as hour_of_day,
                    AVG(total_engagement) as avg_engagement,
                    COUNT(*) as post_count
                FROM bluesky_post_analytics
                WHERE created_at >= $1
                AND total_engagement >= 3
                GROUP BY day_of_week, hour_of_day
                HAVING COUNT(*) >= 2
                ORDER BY avg_engagement DESC
                LIMIT 3
            """
            
            try:
                timing_patterns = await self.db.fetch_all(timing_query, lookback_time)
                
                if timing_patterns and timing_patterns[0]['avg_engagement'] > avg_engagement and timing_patterns[0]['avg_engagement'] >= 5:
                    best_timing = timing_patterns[0]
                    
                    days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
                    day_name = days[int(best_timing['day_of_week'])]
                    hour = int(best_timing['hour_of_day'])
                    
                    performance_multiplier = best_timing['avg_engagement'] / avg_engagement if avg_engagement > 0 else 1
                    
                    signals.append(self._create_signal(
                        signal_type='timing_insight',
                        data={
                            'day_of_week': day_name,
                            'hour_of_day': hour,
                            'avg_engagement': round(best_timing['avg_engagement'], 1),
                            'post_count': best_timing['post_count'],
                            'vs_overall_average': round(performance_multiplier, 2),
                            'insight': f"Posts on {day_name} at {hour}:00 get better engagement (avg: {best_timing['avg_engagement']:.1f} vs overall {avg_engagement:.1f})"
                        },
                        priority=4,
                        expires_hours=336
                    ))
                    
                    logger.info(f"⏰ Timing insight: {day_name} at {hour}:00 performs better ({best_timing['avg_engagement']:.1f} avg)")
            
            except Exception as e:
                logger.debug(f"Could not analyze timing patterns: {e}")
            
            logger.info(f"PerformanceContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting performance signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of content performance"""
        try:
            total_posts = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM bluesky_post_analytics"
            )
            
            avg_metrics = await self.db.fetch_one(
                """SELECT 
                    AVG(total_engagement) as avg_engagement,
                    AVG(engagement_rate) as avg_rate,
                    AVG(likes_count) as avg_likes,
                    AVG(reposts_count) as avg_reposts
                FROM bluesky_post_analytics
                WHERE created_at >= NOW() - INTERVAL '7 days'"""
            )
            
            best_post = await self.db.fetch_one(
                """SELECT 
                    account_handle,
                    post_text,
                    total_engagement,
                    created_at
                FROM bluesky_post_analytics
                WHERE created_at >= NOW() - INTERVAL '7 days'
                ORDER BY total_engagement DESC LIMIT 1"""
            )
            
            account_counts = await self.db.fetch_all(
                """SELECT account_handle, COUNT(*) as count 
                FROM bluesky_post_analytics 
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY account_handle"""
            )
            
            return {
                'collector': 'PerformanceContextCollector',
                'total_posts_analyzed': total_posts['count'] if total_posts else 0,
                'avg_engagement_7d': round(avg_metrics['avg_engagement'], 1) if avg_metrics and avg_metrics['avg_engagement'] else 0,
                'avg_engagement_rate_7d': round(avg_metrics['avg_rate'], 4) if avg_metrics and avg_metrics['avg_rate'] else 0,
                'avg_likes_7d': round(avg_metrics['avg_likes'], 1) if avg_metrics and avg_metrics['avg_likes'] else 0,
                'avg_reposts_7d': round(avg_metrics['avg_reposts'], 1) if avg_metrics and avg_metrics['avg_reposts'] else 0,
                'best_post_text': best_post['post_text'][:100] if best_post and best_post['post_text'] else None,
                'best_post_engagement': best_post['total_engagement'] if best_post else None,
                'posts_by_account': {row['account_handle']: row['count'] for row in account_counts} if account_counts else {},
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting performance state: {e}")
            return {
                'collector': 'PerformanceContextCollector',
                'status': 'error',
                'error': str(e)
            }


#===============================================================================
# MODULE EXPORTS - Singleton getters for all collectors
#===============================================================================

__all__ = [
    # Base classes
    'ContextSignal',
    'ContextCollector',
    
    # User ID constant
    'USER_ID',
    
    # Collector classes
    'MeetingContextCollector',
    'ConversationContextCollector',
    'CalendarContextCollector',
    'EmailContextCollector',
    'TrendContextCollector',
    'BlueskyContextCollector',
    'KnowledgeContextCollector',
    'WeatherContextCollector',
    'PerformanceContextCollector',
    
    # Singleton getters
    'get_meeting_collector',
    'get_conversation_collector',
    'get_calendar_collector',
    'get_email_collector',
    'get_trend_collector',
    'get_bluesky_collector',
    'get_knowledge_collector',
    'get_weather_collector',
    'get_performance_collector',
]
