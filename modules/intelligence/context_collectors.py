# modules/intelligence/context_collectors.py
"""
Context Collectors for Syntax Prime V2 Intelligence Hub
Monitors 8 data sources and produces context signals for situation detection

Each collector inherits from ContextCollector and produces ContextSignal objects
that feed into the situation detector.

Created: 10/22/25
"""

import logging
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)

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
    """
    
    def __init__(self, db_manager):
        """
        Args:
            db_manager: Database manager for running queries
        """
        self.db = db_manager
        self.collector_name = self.__class__.__name__
        
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
                # DEBUG: Log meeting_id being used
                logger.info(f"🔍 DEBUG: Creating meeting_processed signal with meeting_id={str(meeting['id'])}")
                
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
            # This creates a signal when a follow-up meeting is scheduled
            upcoming_meetings_query = """
                SELECT 
                    id,
                    meeting_title,
                    meeting_date,
                    attendees
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
                    priority=8 if hours_until < 24 else 7,  # Higher priority if within 24h
                    expires_hours=int(hours_until) + 2  # Expires shortly after meeting
                ))
                
                logger.info(f"Upcoming meeting in {hours_until:.1f}h: {meeting['meeting_title']}")
            
            logger.info(f"MeetingContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting meeting signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of meetings data source"""
        try:
            # Count total meetings
            total_meetings = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM fathom_meetings"
            )
            
            # Count pending action items
            pending_actions = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM meeting_action_items WHERE status IN ('pending', 'in_progress')"
            )
            
            # Get latest meeting date
            latest_meeting = await self.db.fetch_one(
                "SELECT MAX(meeting_date) as latest FROM fathom_meetings"
            )
            
            # Get overdue count
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

class ConversationContextCollector(ContextCollector):
    """
    Monitors chat conversation messages and extracts meaningful context.
    
    Uses AI (OpenRouter) to analyze recent conversations and identify:
    - Topics being discussed frequently
    - Questions that might need follow-up
    - Projects mentioned by the user
    
    This is more sophisticated than keyword matching - it uses AI to understand
    the semantic meaning of conversations.
    """
    
    def __init__(self, db_manager, openrouter_client=None):
        """
        Args:
            db_manager: Database manager
            openrouter_client: OpenRouter client for AI analysis (optional, will import if None)
        """
        super().__init__(db_manager)
        self.openrouter_client = openrouter_client
        
    async def _get_openrouter_client(self):
        """Lazy load OpenRouter client"""
        if self.openrouter_client is None:
            from ..ai.openrouter_client import get_openrouter_client
            self.openrouter_client = await get_openrouter_client()
        return self.openrouter_client
    
    async def collect_signals(self, lookback_hours: int = 24) -> List[ContextSignal]:
        """
        Collect conversation signals from recent chat messages.
        
        Uses 24-hour lookback by default since conversations are more ephemeral
        than meetings.
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
                AND cm.role = 'user'  -- Only user messages, not AI responses
                ORDER BY cm.created_at DESC
                LIMIT 100  -- Cap at 100 messages to avoid overwhelming AI
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
                    # Call AI to analyze conversation
                    response = await client.chat_completion(
                        messages=[{"role": "user", "content": analysis_prompt}],
                        model="anthropic/claude-3.5-sonnet",
                        temperature=0.3,  # Lower temperature for more consistent extraction
                        max_tokens=1000
                    )
                    
                    # Parse AI response
                    ai_text = response['choices'][0]['message']['content']
                    
                    # Extract JSON from response (AI might wrap it in markdown)
                    import re
                    json_match = re.search(r'\{.*\}', ai_text, re.DOTALL)
                    if json_match:
                        analysis = json.loads(json_match.group())
                    else:
                        logger.warning(f"Could not parse AI analysis for thread {thread_id}")
                        continue
                    
                    # Create signals for topics discussed
                    for topic in analysis.get('topics', []):
                        if topic['relevance'] >= 6:  # Only high-relevance topics
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
                                priority=min(topic['relevance'], 7),  # Cap at 7 for topics
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
                            expires_hours=168  # Projects relevant for a week
                        ))
                        
                        logger.info(f"Project signal: {project['project_name']}")
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse AI analysis JSON for thread {thread_id}: {e}")
                except Exception as e:
                    logger.error(f"Error analyzing thread {thread_id}: {e}", exc_info=True)
            
            logger.info(f"ConversationContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting conversation signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of conversation data source"""
        try:
            # Count total messages
            total_messages = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM conversation_messages"
            )
            
            # Count total threads
            total_threads = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM conversation_threads"
            )
            
            # Get latest message
            latest_message = await self.db.fetch_one(
                "SELECT MAX(created_at) as latest FROM conversation_messages"
            )
            
            # Count messages from last 24h
            recent_messages = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM conversation_messages WHERE created_at >= NOW() - INTERVAL '24 hours'"
            )
            
            return {
                'collector': 'ConversationContextCollector',
                'total_messages': total_messages['count'] if total_messages else 0,
                'total_threads': total_threads['count'] if total_threads else 0,
                'messages_last_24h': recent_messages['count'] if recent_messages else 0,
                'latest_message': latest_message['latest'].isoformat() if latest_message and latest_message['latest'] else None,
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

class CalendarContextCollector(ContextCollector):
    """
    Monitors Google Calendar events for upcoming commitments.
    
    Produces signals for:
    - Events within 24 hours (high priority)
    - Events within 48 hours (medium priority)
    - Meeting clusters (multiple meetings same day)
    - Events that need preparation time
    """
    
    async def collect_signals(self, lookback_hours: int = 168) -> List[ContextSignal]:
        """
        Collect calendar signals for next 7 days.
        
        Note: Unlike other collectors that look BACK, calendar looks FORWARD
        since we care about upcoming events, not past ones.
        """
        signals = []
        now = datetime.now(timezone.utc)
        seven_days_ahead = now + timedelta(hours=lookback_hours)
        
        try:
            # Query: Get upcoming events
            events_query = """
                SELECT 
                    id,
                    event_title,
                    start_time,
                    end_time,
                    location,
                    description,
                    attendees,
                    is_all_day,
                    calendar_name,
                    created_at
                FROM google_calendar_events
                WHERE start_time BETWEEN $1 AND $2
                AND is_cancelled = false
                ORDER BY start_time ASC
            """
            
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
                        priority=9,  # Very high priority - happening soon!
                        expires_hours=int(hours_until) + 2  # Expires shortly after event
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
                        priority=7,  # Medium priority - some time to prepare
                        expires_hours=int(hours_until) + 2
                    ))
                    
                    logger.debug(f"Upcoming: Event in {hours_until:.1f}h - {event['event_title'] or 'Untitled Event'}")
                
                # Signal 3: Check if event needs preparation
                # Look for keywords suggesting preparation is needed
                needs_prep = self._check_if_needs_preparation(event)
                
                if needs_prep and hours_until > 2:  # Only if we have time to prep
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
                        expires_hours=int(hours_until) - 2  # Expires before event with buffer
                    ))
                    
                    logger.info(f"Prep needed: {event['event_title'] or 'Untitled Event'} - {needs_prep['reason']}")
            
            # Signal 4: Detect meeting clusters (multiple meetings same day)
            for event_date, day_events in events_by_date.items():
                if len(day_events) >= 3:  # 3+ meetings = cluster
                    # Calculate total meeting time
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
        
        # Keywords that suggest preparation needed
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
        
        # Check attendee count - large meetings often need prep
        if event['attendees'] and len(event['attendees']) >= 5:
            return {'hours': 1, 'reason': 'Large meeting with 5+ attendees'}
        
        return None
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of calendar data source"""
        try:
            now = datetime.now(timezone.utc)
            
            # Count total events
            total_events = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM google_calendar_events"
            )
            
            # Count upcoming events (next 7 days)
            upcoming_events = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_calendar_events 
                   WHERE start_time BETWEEN $1 AND $2 
                   AND is_cancelled = false""",
                now, now + timedelta(days=7)
            )
            
            # Count events in next 24h
            urgent_events = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_calendar_events 
                   WHERE start_time BETWEEN $1 AND $2 
                   AND is_cancelled = false""",
                now, now + timedelta(hours=24)
            )
            
            # Get next event
            next_event = await self.db.fetch_one(
                """SELECT event_title, start_time FROM google_calendar_events 
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
            emails_query = """
                SELECT
                    id,
                    message_id,
                    thread_id,
                    sender_email,
                    subject_line as subject,
                    priority_level,
                    category,
                    requires_response,
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
            
            user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
            emails = await self.db.fetch_all(emails_query, self.user_id, lookback_time)
            
            if not emails:
                logger.info("EmailContextCollector: No high-priority emails found")
                return signals
            
            logger.info(f"EmailContextCollector: Processing {len(emails)} high-priority emails")
            
            for email in emails:
                from datetime import timezone
                hours_old = (datetime.utcnow() - email['received_at']).total_seconds() / 3600
                
                # Determine base priority from email priority level
                if email['priority_level'] == 'urgent':
                    base_priority = 9
                else:  # high
                    base_priority = 8
                
                # Adjust priority based on age - older emails get slightly lower priority
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
                    'subject': email['subject'],
                    'received_at': email['received_at'].isoformat(),
                    'hours_old': round(hours_old, 1),
                    'priority_level': email['priority_level'],
                    'category': email['category']
                }
                
                signals.append(self._create_signal(
                    signal_type='email_priority_high',
                    data=signal_data,
                    priority=priority,
                    expires_hours=48
                ))
                
                logger.debug(f"High-priority email from {email['sender_email']}: {email['subject'][:50]}...")
                
                # Signal 2: Email requires response
                signals.append(self._create_signal(
                    signal_type='email_requires_response',
                    data={
                        'email_id': str(email['id']),
                        'message_id': email['message_id'],
                        'thread_id': email['thread_id'],
                        'sender_email': email['sender_email'],
                        'subject': email['subject'],
                        'received_at': email['received_at'].isoformat(),
                        'hours_old': round(hours_old, 1),
                        'priority_level': email['priority_level']
                    },
                    priority=8,
                    expires_hours=72
                ))
                
                logger.info(f"Response needed from {email['sender_name']}: {email['subject'][:50]}...")
                
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
                        expires_hours=72  # More time for follow-ups
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
        subject_lower = email['subject'].lower()
        snippet_lower = email['snippet'].lower() if email['snippet'] else ''
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
        
        # Check for question marks - might need response
        if '?' in email['snippet'] or '?' in email['subject']:
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
            # Count total analyzed emails
            total_emails = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM google_gmail_analysis"
            )
            
            # Count high-priority emails from last 48h
            high_priority = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_gmail_analysis 
                   WHERE received_at >= NOW() - INTERVAL '48 hours'
                   AND priority_level IN ('high', 'urgent')"""
            )
            
            # Count emails requiring response
            needs_response = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM google_gmail_analysis 
                   WHERE received_at >= NOW() - INTERVAL '48 hours'
                   AND requires_response = true"""
            )
            
            # Get latest email
            latest_email = await self.db.fetch_one(
                """SELECT sender_name, subject, received_at 
                   FROM google_gmail_analysis 
                   ORDER BY received_at DESC LIMIT 1"""
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
                # Query 1: Get recent high-scoring or rising trends
                trends_query = """
                    SELECT
                        keyword,
                        business_area,
                        trend_score,
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
                
                trends = await self.db.fetch_all(trends_query, lookback_time)
                
                if not trends:
                    logger.info("TrendContextCollector: No significant trends found")
                    return signals
                
                logger.info(f"TrendContextCollector: Processing {len(trends)} trends")
                
                for trend in trends:
                    keyword = trend['keyword']
                    current_score = trend['trend_score']
                    momentum = trend['trend_momentum']
                    
                    # Signal 1: Trend spike (score jumped 15+ points)
                    if score_change >= 15:
                        signals.append(self._create_signal(
                            signal_type='trend_spike',
                            data={
                                'keyword': trend['keyword'],
                                'business_area': trend['business_area'],
                                'current_score': current_score,
                                'previous_score': previous_score,
                                'score_change': score_change,
                                'search_volume': trend['search_volume'],
                                'related_topics': trend['related_topics'],
                                'last_checked': trend['last_checked'].isoformat()
                            },
                            priority=10 if score_change >= 25 else 9,
                            expires_hours=48
                        ))
                        
                        logger.warning(f"🔥 Trend SPIKE: {trend['keyword']} jumped {score_change} points to {current_score}")
                    
                    # Signal 2: Trend is rising (momentum indicator)
                    elif trend['trend_momentum'] == 'rising':
                        signals.append(self._create_signal(
                            signal_type='trend_rising',
                            data={
                                'keyword': trend['keyword'],
                                'business_area': trend['business_area'],
                                'current_score': current_score,
                                'momentum': trend['trend_momentum'],
                                'search_volume': trend['search_volume'],
                                'related_topics': trend['related_topics']
                            },
                            priority=8,
                            expires_hours=72
                        ))
                        
                        logger.info(f"📈 Rising trend: {trend['keyword']} (score: {current_score})")
                    
                    # Signal 3: Stable high trend (score >= 70 for multiple checks)
                    if current_score >= 80:
                        signal_type = 'trend_spike'
                        priority = 9
                    elif momentum == 'rising' and current_score >= 70:
                        signal_type = 'trend_rising'
                        priority = 8
                    elif current_score >= 70:
                        signal_type = 'trend_stable_high'
                        priority = 7
                    else:
                        signal_type = 'trend_opportunity'
                        priority = 6
                    
                    signals.append(self._create_signal(
                        signal_type=signal_type,
                        data={
                            'keyword': keyword,
                            'business_area': trend['business_area'],
                            'current_score': current_score,
                            'momentum': momentum,
                            'regional_score': trend.get('regional_score'),
                            'trend_date': trend['trend_date'].isoformat() if trend.get('trend_date') else None
                        },
                        priority=priority,
                        expires_hours=72
                    ))
                        
                    logger.debug(f"🎯 Stable high trend: {trend['keyword']} (score: {current_score})")
                
                # Query 2: Get new trend opportunities created
                opportunities_query = """
                    SELECT 
                        id,
                        keyword,
                        business_area,
                        opportunity_type,
                        opportunity_score,
                        content_angle,
                        target_audience,
                        suggested_action,
                        created_at
                    FROM trend_opportunities
                    WHERE created_at >= $1
                    ORDER BY opportunity_score DESC
                """
                
                opportunities = await self.db.fetch_all(opportunities_query, lookback_time)
                
                if opportunities:
                    logger.info(f"TrendContextCollector: Found {len(opportunities)} new opportunities")
                    
                    for opp in opportunities:
                        signals.append(self._create_signal(
                            signal_type='trend_opportunity_created',
                            data={
                                'opportunity_id': str(opp['id']),
                                'keyword': opp['keyword'],
                                'business_area': opp['business_area'],
                                'opportunity_type': opp['opportunity_type'],
                                'opportunity_score': opp['opportunity_score'],
                                'content_angle': opp['content_angle'],
                                'target_audience': opp['target_audience'],
                                'suggested_action': opp['suggested_action'],
                                'created_at': opp['created_at'].isoformat()
                            },
                            priority=8,
                            expires_hours=96
                        ))
                        
                        logger.info(f"💡 New opportunity: {opp['keyword']} - {opp['opportunity_type']}")
                
                logger.info(f"TrendContextCollector: Collected {len(signals)} signals")
                
            except Exception as e:
                logger.error(f"Error collecting trend signals: {e}", exc_info=True)
            
            return signals
    
    def _calculate_stability_days(self, trend: Dict) -> int:
        """
        Calculate how many days a trend has been stable at high levels.
        
        This is a simplified calculation - in reality you'd check trend history.
        For now, estimate based on created_at.
        """
        if trend['created_at']:
            days_tracked = (datetime.utcnow() - trend['created_at']).days
            return min(days_tracked, 30)  # Cap at 30 days
        return 0
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of trend monitoring"""
        try:
            # Count total trends being monitored
            total_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring"
            )
            
            # Count high-scoring trends
            high_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring WHERE trend_score >= 70"
            )
            
            # Count rising trends
            rising_trends = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_monitoring WHERE trend_momentum = 'rising'"
            )
            
            # Count opportunities
            total_opportunities = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM trend_opportunities"
            )
            
            # Get top trend
            top_trend = await self.db.fetch_one(
                """SELECT keyword, trend_score, business_area 
                   FROM trend_monitoring 
                   ORDER BY trend_score DESC LIMIT 1"""
            )
            
            # Get latest trend check
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
            # Count pending opportunities
            pending = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM bluesky_engagement_opportunities 
                   WHERE user_response IS NULL 
                   AND already_engaged = false"""
            )
            
            # Count recent posts
            recent_posts = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM bluesky_posts 
                   WHERE posted_at >= NOW() - INTERVAL '7 days'"""
            )
            
            # Count total engagement opportunities ever detected
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

class KnowledgeContextCollector(ContextCollector):
    """
    Matches knowledge base entries against topics from other signals.
    
    This is a "supportive" collector - it doesn't generate urgent signals
    on its own, but helps surface relevant knowledge when other collectors
    find interesting topics.
    
    Produces signals for:
    - Relevant knowledge exists for a topic
    - Knowledge gap detected (topic discussed but no entry exists)
    """
    
    def __init__(self, db_manager, context_topics: Optional[List[str]] = None):
        """
        Args:
            db_manager: Database manager
            context_topics: List of topics to search for (from other collectors)
        """
        super().__init__(db_manager)
        self.context_topics = context_topics or []
    
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
            
            # Query: Get trends that spiked, are rising, or are stable high
            # Changed: removed momentum filter, just look at high scores
            trends_query = """
                SELECT 
                    id,
                    keyword,
                    trend_score,
                    previous_score,
                    trend_momentum,
                    business_area,
                    search_volume,
                    related_topics,
                    last_checked,
                    created_at
                FROM trend_monitoring
                WHERE last_checked >= $1
                AND (
                    trend_score >= 60
                    OR (trend_score > previous_score AND (trend_score - previous_score) >= 10)
                )
                ORDER BY trend_score DESC
                LIMIT 50
            """
            
            trends = await self.db.fetch_all(trends_query, lookback_time)
            
            if not trends:
                logger.info("TrendContextCollector: No high-scoring trends found")
                return signals
            
            logger.info(f"TrendContextCollector: Processing {len(trends)} trending keywords")
            
            for trend in trends:
                keyword = trend['keyword']
                current_score = trend['trend_score']
                previous_score = trend['previous_score'] or 0
                score_change = current_score - previous_score
                momentum = trend['trend_momentum']
                
                # Determine signal type based on score and change
                if score_change >= 20:
                    signal_type = 'trend_spike'
                    priority = 9
                elif score_change >= 10:
                    signal_type = 'trend_rising'
                    priority = 8
                elif current_score >= 70:
                    signal_type = 'trend_stable_high'
                    priority = 7
                else:
                    signal_type = 'trend_opportunity_created'
                    priority = 6
                
                signal_data = {
                    'keyword': keyword,
                    'current_score': current_score,
                    'previous_score': previous_score,
                    'score_change': score_change,
                    'momentum': momentum,
                    'business_area': trend['business_area'],
                    'search_volume': trend['search_volume'],
                    'related_topics': trend['related_topics'],
                    'last_checked': trend['last_checked'].isoformat() if trend['last_checked'] else None
                }
                
                signals.append(self._create_signal(
                    signal_type=signal_type,
                    data=signal_data,
                    priority=priority,
                    expires_hours=72
                ))
                
                logger.debug(f"📈 Trend signal: {keyword} ({signal_type}, score: {current_score})")
            
            logger.info(f"TrendContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting trend signals: {e}", exc_info=True)
        
        return signals
        
    def set_context_topics(self, topics: List[str]):
        """
        Set context topics to search for.
        
        This should be called by the orchestrator after other collectors
        have identified interesting topics.
        """
        self.context_topics = topics
        logger.debug(f"KnowledgeContextCollector: Set {len(topics)} context topics")
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of knowledge base"""
        try:
            # Count total knowledge entries
            total_entries = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM knowledge_entries WHERE processed = true"
            )
            
            # Count by content type
            type_counts = await self.db.fetch_all(
                """SELECT content_type, COUNT(*) as count 
                   FROM knowledge_entries 
                   WHERE processed = true 
                   GROUP BY content_type"""
            )
            
            # Count high-relevance entries
            high_relevance = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM knowledge_entries WHERE relevance_score >= 8.0"
            )
            
            # Get most accessed entry
            most_accessed = await self.db.fetch_one(
                """SELECT title, access_count, last_accessed 
                   FROM knowledge_entries 
                   WHERE processed = true 
                   ORDER BY access_count DESC LIMIT 1"""
            )
            
            # Get latest entry
            latest_entry = await self.db.fetch_one(
                """SELECT title, created_at 
                   FROM knowledge_entries 
                   WHERE processed = true 
                   ORDER BY created_at DESC LIMIT 1"""
            )
            
            return {
                'collector': 'KnowledgeContextCollector',
                'total_entries': total_entries['count'] if total_entries else 0,
                'high_relevance_entries': high_relevance['count'] if high_relevance else 0,
                'content_types': {row['content_type']: row['count'] for row in type_counts},
                'context_topics_loaded': len(self.context_topics),
                'most_accessed_entry': most_accessed['title'] if most_accessed else None,
                'most_accessed_count': most_accessed['access_count'] if most_accessed else None,
                'latest_entry': latest_entry['title'] if latest_entry else None,
                'latest_entry_date': latest_entry['created_at'].isoformat() if latest_entry else None,
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
# WEATHER CONTEXT COLLECTOR - Monitors weather, headache risk & UV alerts
#===============================================================================

class WeatherContextCollector(ContextCollector):
    """
    Monitors weather data and health-related alerts.
    
    Produces signals for:
    - High UV index (>4 triggers sun allergy warning)
    - High headache risk (pressure changes)
    - Significant pressure drops
    - Severe weather alerts
    """
    
    async def collect_signals(self, lookback_hours: int = 24) -> List[ContextSignal]:
        """
        Collect weather signals from recent readings.
        
        Uses 24-hour lookback since weather changes daily.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query 1: Get latest weather reading with all health metrics
            latest_weather_query = """
                SELECT 
                    id,
                    location,
                    temperature,
                    feels_like,
                    humidity,
                    pressure,
                    weather_description,
                    wind_speed,
                    uv_index,
                    headache_risk_level,
                    headache_risk_score,
                    headache_risk_factors,
                    severe_weather_alert,
                    alert_description,
                    timestamp,
                    created_at
                FROM weather_readings
                WHERE created_at >= $1
                ORDER BY created_at DESC
                LIMIT 1
            """
            
            latest = await self.db.fetch_one(latest_weather_query, lookback_time)
            
            if not latest:
                logger.info("WeatherContextCollector: No recent weather data found")
                return signals
            
            logger.info(f"WeatherContextCollector: Processing weather data for {latest['location']}")
            
            logger.info(f"WeatherContextCollector: Processing weather data for {latest['location']}")
            
            # 🔍 DEBUG: Log all weather data fields
            logger.info(f"🔍 DEBUG - Weather data fields:")
            logger.info(f"   uv_index: {latest.get('uv_index')} (type: {type(latest.get('uv_index'))})")
            logger.info(f"   headache_risk_level: {latest.get('headache_risk_level')}")
            logger.info(f"   headache_risk_score: {latest.get('headache_risk_score')}")
            logger.info(f"   headache_risk_factors: {latest.get('headache_risk_factors')}")
            logger.info(f"   severe_weather_alert: {latest.get('severe_weather_alert')}")
            logger.info(f"   alert_description: {latest.get('alert_description')}")
            
            # Signal 1: UV INDEX HIGH (>4 triggers sun allergy warning)
            logger.info(f"🔍 DEBUG - Checking UV index signal...")
                        
            uv_index = latest.get('uv_index')
            if uv_index is not None and uv_index > 4:
                # Determine severity
                if uv_index >= 8:
                    uv_level = 'very_high'
                    priority = 10  # Maximum priority - dangerous for sun allergy
                elif uv_index >= 6:
                    uv_level = 'high'
                    priority = 9
                else:  # 4-6
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
                    expires_hours=6  # UV changes throughout the day
                ))
                
                logger.warning(f"☀️ UV ALERT: Index {uv_index} ({uv_level}) - SUN PROTECTION REQUIRED!")
            
            # Signal 2: High headache risk
            logger.info(f"🔍 DEBUG - Checking headache risk signal...")
            
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
                    expires_hours=12  # Headache risk changes relatively quickly
                ))
                
                logger.warning(f"⚠️ {latest['headache_risk_level'].upper()} headache risk detected - Score: {latest['headache_risk_score']}")
            
            # Signal 3: Severe weather alert
            logger.info(f"🔍 DEBUG - Checking severe weather alert signal...")
            
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
                    priority=10,  # Severe weather = max priority
                    expires_hours=6  # Short expiry - weather moves fast
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
                datetime.utcnow() - timedelta(hours=12)  # Last 12 hours
            )
            
            if len(pressure_readings) >= 2:
                # Calculate pressure change - with None check
                current_pressure = pressure_readings[0]['pressure_surface_level']
                oldest_pressure = pressure_readings[-1]['pressure_surface_level']
                
                # Only calculate if both values exist
                if current_pressure is not None and oldest_pressure is not None:
                    pressure_change = current_pressure - oldest_pressure
                else:
                    logger.warning("Pressure readings contain None values, skipping pressure change calculation")
                    pressure_change = None
                
                # Signal 4: Significant pressure drop (headache trigger)
                # Pressure drop > 0.1 inHg (or 3.4 mb) is significant
                if pressure_change is not None and pressure_change < -0.1:
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
                    # Check for UV alerts in forecast
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
                                    priority=5,  # Informational
                                    expires_hours=int(hours_until) + 2
                                ))
                                
                                logger.debug(f"🌧️ High precipitation chance in {hours_until:.1f}h: {period['precipitation_chance']}%")
                                precip_alert_sent = True
                        
                        # Stop after finding both types
                        if uv_alert_sent and precip_alert_sent:
                            break
                
            except Exception as e:
                # Forecast table might not exist yet - skip silently
                logger.debug(f"No forecast data available: {e}")
            
            logger.info(f"WeatherContextCollector: Collected {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"Error collecting weather signals: {e}", exc_info=True)
        
        return signals
    
    async def get_current_state(self) -> Dict[str, Any]:
        """Get current state of weather monitoring"""
        try:
            # Get latest weather reading
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
            
            # Count total readings
            total_readings = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM weather_readings"
            )
            
            # Count high UV days in last week (>4)
            high_uv_count = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM weather_readings 
                   WHERE created_at >= NOW() - INTERVAL '7 days'
                   AND uv_index > 4"""
            )
            
            # Count high headache risk days in last week
            high_risk_count = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM weather_readings 
                   WHERE created_at >= NOW() - INTERVAL '7 days'
                   AND headache_risk_level IN ('high', 'severe')"""
            )
            
            # Count severe weather alerts in last week
            alert_count = await self.db.fetch_one(
                """SELECT COUNT(*) as count FROM weather_readings 
                   WHERE created_at >= NOW() - INTERVAL '7 days'
                   AND severe_weather_alert = true"""
            )
            
            # Determine current UV status
            current_uv = latest.get('uv_index') if latest else None
            if current_uv is not None:
                if current_uv >= 8:
                    uv_status = 'VERY HIGH - DANGER'
                elif current_uv >= 6:
                    uv_status = 'HIGH - CAUTION'
                elif current_uv > 4:
                    uv_status = 'MODERATE HIGH - PROTECT'
                elif current_uv > 2:
                    uv_status = 'MODERATE - SAFE'
                else:
                    uv_status = 'LOW - SAFE'
            else:
                uv_status = 'UNKNOWN'
            
            return {
                'collector': 'WeatherContextCollector',
                'total_readings': total_readings['count'] if total_readings else 0,
                'current_location': latest['location'] if latest else None,
                'current_temperature': latest['temperature'] if latest else None,
                'current_weather': latest['weather_description'] if latest else None,
                'current_uv_index': current_uv,
                'current_uv_status': uv_status,
                'current_headache_risk': latest['headache_risk_level'] if latest else None,
                'current_risk_score': latest['headache_risk_score'] if latest else None,
                'high_uv_days_last_week': high_uv_count['count'] if high_uv_count else 0,
                'high_risk_days_last_week': high_risk_count['count'] if high_risk_count else 0,
                'severe_alerts_last_week': alert_count['count'] if alert_count else 0,
                'last_updated': latest['timestamp'].isoformat() if latest else None,
                'sun_allergy_protection_active': current_uv is not None and current_uv > 4,
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
# PERFORMANCE CONTEXT COLLECTOR - Monitors Bluesky post analytics
#===============================================================================

class PerformanceContextCollector(ContextCollector):
    """
    Monitors Bluesky post analytics to learn what content performs well.
    
    Produces signals for:
    - Posts performing exceptionally well (learn from success)
    - Posts performing poorly (learn from failure)
    - Patterns worth learning from
    
    This is a "learning" collector - lower priority but builds intelligence
    about what content works.
    """
    
    async def collect_signals(self, lookback_hours: int = 168) -> List[ContextSignal]:
        """
        Collect performance signals from last 7 days (168 hours).
        
        7-day lookback gives posts time to accumulate engagement
        and provides meaningful performance data.
        """
        signals = []
        lookback_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        try:
            # Query 1: Get recent posts with analytics
            posts_query = """
                SELECT 
                    id,
                    account_handle,
                    post_text,
                    post_uri,
                    created_at,
                    likes_count,
                    reposts_count,
                    replies_count,
                    total_engagement,
                    engagement_rate,
                    reach,
                    impressions,
                    topics,
                    sentiment
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
            if posts:
                avg_engagement = sum(p['total_engagement'] for p in posts) / len(posts)
                avg_engagement_rate = sum(p['engagement_rate'] for p in posts if p['engagement_rate']) / len([p for p in posts if p['engagement_rate']])
                
                logger.debug(f"Average engagement: {avg_engagement:.1f}, Average rate: {avg_engagement_rate:.2%}")
            else:
                avg_engagement = 0
                avg_engagement_rate = 0
            
            for post in posts:
                engagement = post['total_engagement'] or 0
                engagement_rate = post['engagement_rate'] or 0
                
                # Signal 1: Post performing exceptionally well (learn from success)
                # REALISTIC thresholds: 3x average OR 10+ engagement (since 2 likes is "trending" for you)
                # We want to catch genuine wins, not inflate expectations
                if engagement >= max(avg_engagement * 3, 10):
                    signals.append(self._create_signal(
                        signal_type='post_performing_well',
                        data={
                            'post_id': str(post['id']),
                            'account_handle': post['account_handle'],
                            'post_text': post['post_text'][:200],  # First 200 chars
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
                        priority=5,  # Learning priority - not urgent
                        expires_hours=336  # Keep for 2 weeks to learn from
                    ))
                    
                    logger.info(f"✅ High-performing post: {engagement} engagement ({engagement / avg_engagement:.1f}x avg)")
                
                # Signal 2: Post performing poorly - REMOVED
                # We're NOT flagging low-performing posts because:
                # 1. Bluesky engagement is naturally low
                # 2. You're "fighting uphill" with niche content
                # 3. Zero engagement doesn't mean bad content - just different audience/timing
                # 4. Creates negative signal noise that isn't actionable
                #
                # Instead, we only focus on POSITIVE learning from what works
            
            # Query 2: Look for patterns across high-performing posts
            # REALISTIC: Only look for patterns where posts actually got engagement
            # Require at least 5+ engagement per post in the pattern (not asking for miracles)
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
                    # Signal 3: Learning opportunity - consistent pattern detected
                    # REALISTIC: Pattern just needs to be better than average, not 1.5x
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
            # REALISTIC: Only analyze times where you got some engagement
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
                
                # REALISTIC: Only flag timing if it's noticeably better (not requiring 1.3x)
                if timing_patterns and timing_patterns[0]['avg_engagement'] > avg_engagement and timing_patterns[0]['avg_engagement'] >= 5:
                    best_timing = timing_patterns[0]
                    
                    # Convert day_of_week to name
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
            # Count total posts analyzed
            total_posts = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM bluesky_post_analytics"
            )
            
            # Get average engagement metrics
            avg_metrics = await self.db.fetch_one(
                """SELECT 
                    AVG(total_engagement) as avg_engagement,
                    AVG(engagement_rate) as avg_rate,
                    AVG(likes_count) as avg_likes,
                    AVG(reposts_count) as avg_reposts
                FROM bluesky_post_analytics
                WHERE created_at >= NOW() - INTERVAL '7 days'"""
            )
            
            # Get best performing post in last 7 days
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
            
            # Get worst performing post in last 7 days
            worst_post = await self.db.fetch_one(
                """SELECT 
                    account_handle,
                    post_text,
                    total_engagement,
                    created_at
                FROM bluesky_post_analytics
                WHERE created_at >= NOW() - INTERVAL '7 days'
                ORDER BY total_engagement ASC LIMIT 1"""
            )
            
            # Count posts by account
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
                'best_post_text': best_post['post_text'][:100] if best_post else None,
                'best_post_engagement': best_post['total_engagement'] if best_post else None,
                'worst_post_text': worst_post['post_text'][:100] if worst_post else None,
                'worst_post_engagement': worst_post['total_engagement'] if worst_post else None,
                'posts_by_account': {row['account_handle']: row['count'] for row in account_counts},
                'status': 'operational'
            }
        except Exception as e:
            logger.error(f"Error getting performance state: {e}")
            return {
                'collector': 'PerformanceContextCollector',
                'status': 'error',
                'error': str(e)
            }
