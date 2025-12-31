"""
SYNTAX PRIME V2 - MEMORY QUERY LAYER
Created: 2024-10-26
Updated: 2025 - Fixed SQL injection vulnerabilities (INTERVAL string formatting)
Updated: 2025-12-18 - Added notification thread filtering to prevent conversation loops
Updated: 2025-12-26 - Fixed UUID case-sensitivity bug causing every message to load COMPREHENSIVE context
Updated: 2025-12-29 - Added iOS calendar/reminders integration + FIXED email body not being queried
Updated: 2025-12-30 - Added iOS music, contacts, location, health/battery context + intent triggers

PURPOSE:
Transform Syntax from conversation-window memory to database-driven memory.
Queries all databases to build comprehensive context, enabling:
- True cross-thread memory
- Proactive intelligence
- Contextual awareness across all data sources

ARCHITECTURE:
1. Query Functions - One per database table
2. Context Detection - Determines what level of context to load
3. Intent Detection - Analyzes user message to decide what to query
4. Orchestrator - Builds comprehensive context from all sources
5. Formatters - Presents context in AI-readable format

INTEGRATION:
Called from modules/ai/router.py before building AI context window
"""

import logging
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple

# Import database manager
from modules.core.database import db_manager

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

CONTEXT_CONFIG = {
    'hot_cache_days': 20,           # Always loaded (recent discussions)
    'warm_cache_days': 50,          # Loaded on new day/thread
    'cold_cache_days': 365,         # Query-based (everything in V2)
    'hours_gap_threshold': 8,       # Hours before comprehensive context
    
    'limits': {
        'hot_conversations': 300,    # Recent messages always available
        'warm_conversations': 500,  # Comprehensive context
        'cold_conversations': 250,   # Semantic search results
        'meetings': 14,              # From last 14 days
        'emails': 50,                # Unread/important
        'calendar_events': 30,       # Upcoming events
        'trends': 30,                # High-priority trends
        'knowledge_base': 100,       # Semantic search results
        'weather': 1,                # Current reading
        'tasks': 20,                 # Active tasks
        'ios_calendar': 20,          # iOS calendar events
        'ios_reminders': 30,         # iOS reminders
        'ios_contacts': 50           # iOS contacts (NEW)
    }
}

# ============================================================================
# NOTIFICATION THREAD FILTER
# ============================================================================
# These are AI-generated notification threads, NOT user conversations.
# Including them in memory context causes the AI to regenerate the same content.

EXCLUDED_THREAD_PATTERNS = [
#    'Bluesky Draft:%',           # AI-generated Bluesky drafts
#    'Trending Opportunities',     # Trend notifications
#    'Intelligence Briefings',     # Proactive intelligence
#    'Weather Alerts',             # Weather notifications
#    'Prayer Times',               # Prayer reminders
#    'Meeting Summaries',          # Fathom meeting summaries
#    'Email Notifications',        # Email alerts
#    'Calendar Alerts',            # Calendar reminders
#    'Reminders',                  # General reminders
#    'Engagement Opportunities',   # Bluesky engagement
#    'Analytics Reports',          # Analytics notifications
]


# ============================================================================
# CONTEXT LEVEL DETECTION
# ============================================================================

async def detect_context_level(user_id: str, thread_id: Optional[str]) -> str:
    """
    Determine what level of context to load based on:
    - Time since last interaction
    - Whether this is a new thread
    - Whether this is first interaction of the day
    
    Returns: 'minimal' | 'comprehensive' | 'full'
    
    NO LOOPS: Only checks timestamps, doesn't trigger actions
    """
    try:
        # Get user's last message
        query = """
        SELECT created_at, thread_id
        FROM conversation_messages
        WHERE user_id = $1 AND role = 'user'
        ORDER BY created_at DESC
        LIMIT 1
        """
        last_msg = await db_manager.fetch_one(query, user_id)
        
        if not last_msg:
            logger.info("🆕 First ever interaction - loading FULL context")
            return 'full'
        
        now = datetime.now(timezone.utc)
        last_time = last_msg['created_at']
        
        # Ensure timezone awareness
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        
        # Calculate gaps
        hours_gap = (now - last_time).total_seconds() / 3600
        is_new_day = last_time.date() < now.date()
        # BUGFIX 2025-12-26: Normalize UUIDs to lowercase - iOS sends uppercase, DB returns lowercase
        is_new_thread = not thread_id or str(last_msg['thread_id']).lower() != str(thread_id).lower()
        
        logger.info(f"⏰ Context detection: {hours_gap:.1f}h gap, new_day={is_new_day}, new_thread={is_new_thread}")
        
        # FULL: New day AND new thread
        if is_new_day and is_new_thread:
            logger.info("📚 Loading FULL context (new day + new thread)")
            return 'full'
        
        # COMPREHENSIVE: 8+ hour gap OR new thread during same day
        if hours_gap >= CONTEXT_CONFIG['hours_gap_threshold'] or is_new_thread:
            logger.info("📖 Loading COMPREHENSIVE context (8+ hours or new thread)")
            return 'comprehensive'
        
        # MINIMAL: Continuing active conversation
        logger.info("📄 Loading MINIMAL context (active conversation)")
        return 'minimal'
        
    except Exception as e:
        logger.error(f"❌ Failed to detect context level: {e}")
        return 'comprehensive'  # Default to comprehensive on error


# ============================================================================
# QUERY FUNCTIONS - ONE PER DATABASE
# ============================================================================

async def query_conversations(
    user_id: str,
    days: int = 10,
    limit: int = 100,
    keywords: Optional[List[str]] = None,
    exclude_thread_id: Optional[str] = None,
    include_notification_threads: bool = False
) -> List[Dict[str, Any]]:
    """
    Query conversation_messages across ALL threads
    
    This enables TRUE CROSS-THREAD MEMORY
    
    Args:
        user_id: User ID to query
        days: Number of days to look back
        limit: Maximum messages to return
        keywords: Optional keyword filter for semantic search
        exclude_thread_id: Thread ID to exclude (current thread)
        include_notification_threads: If False, excludes AI-generated notification threads
                                      to prevent regenerating the same content (default: False)
    """
    try:
        where_clauses = ["cm.user_id = $1"]
        params: List[Any] = [user_id]
        param_count = 1
        
        # Time filter - using parameterized interval
        if days:
            param_count += 1
            where_clauses.append(f"cm.created_at >= NOW() - INTERVAL '1 day' * ${param_count}")
            params.append(days)
        
        # Exclude current thread (to avoid duplication)
        if exclude_thread_id:
            param_count += 1
            where_clauses.append(f"NOT (cm.thread_id = ${param_count} AND cm.created_at >= NOW() - INTERVAL '1 hour')")
            params.append(exclude_thread_id)
        
        # ================================================================
        # NEW: Exclude notification-generated threads to prevent loops
        # ================================================================
        if not include_notification_threads and EXCLUDED_THREAD_PATTERNS:
            exclusion_conditions = []
            for pattern in EXCLUDED_THREAD_PATTERNS:
                param_count += 1
                exclusion_conditions.append(f"ct.title NOT LIKE ${param_count}")
                params.append(pattern)
            
            if exclusion_conditions:
                where_clauses.append(f"({' AND '.join(exclusion_conditions)})")
        
        # Build query with JOIN to conversation_threads for title filtering
        query = f"""
            SELECT DISTINCT ON (cm.id)
                cm.id,
                cm.thread_id,
                cm.role,
                cm.content,
                cm.created_at,
                ct.title as thread_title
            FROM conversation_messages cm
            LEFT JOIN conversation_threads ct ON cm.thread_id = ct.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY cm.id, cm.created_at DESC
            LIMIT ${param_count + 1}
        """
        params.append(limit)
        
        results = await db_manager.fetch_all(query, *params)
        
        if results:
            messages = [dict(r) for r in results]
            logger.info(f"💬 Found {len(messages)} messages from conversations")
            return messages
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query conversations: {e}")
        return []


async def query_meetings(
    user_id: str,
    days: int = 14,
    limit: int = 10,
    keywords: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Query fathom_meetings for recent meeting summaries"""
    try:
        query = """
            SELECT 
                id,
                title,
                meeting_date,
                duration_minutes,
                participants,
                ai_summary,
                key_points,
                action_items
            FROM fathom_meetings
            WHERE meeting_date >= NOW() - INTERVAL '1 day' * $1
            ORDER BY meeting_date DESC
            LIMIT $2
        """
        
        results = await db_manager.fetch_all(query, days, limit)
        
        if results:
            meetings = [dict(r) for r in results]
            logger.info(f"📅 Found {len(meetings)} meetings")
            return meetings
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query meetings: {e}")
        return []


async def query_emails(
    user_id: str,
    days: int = 7,
    limit: int = 20,
    unread_only: bool = False,
    important_only: bool = False
) -> List[Dict[str, Any]]:
    """Query gmail_emails for recent emails"""
    try:
        where_clauses = ["received_at >= NOW() - INTERVAL '1 day' * $1"]
        params: List[Any] = [days]
        param_count = 1
        
        if unread_only:
            where_clauses.append("is_read = FALSE")
        
        if important_only:
            where_clauses.append("is_important = TRUE")
        
        param_count += 1
        params.append(limit)
        
        # FIXED: Now includes body_text for full email context
        query = f"""
            SELECT 
                id,
                gmail_id,
                subject,
                sender_email,
                sender_name,
                snippet,
                body_text,
                received_at,
                is_read,
                is_important,
                labels,
                ai_summary
            FROM gmail_emails
            WHERE {' AND '.join(where_clauses)}
            ORDER BY received_at DESC
            LIMIT ${param_count}
        """
        
        results = await db_manager.fetch_all(query, *params)
        
        if results:
            emails = [dict(r) for r in results]
            logger.info(f"📧 Found {len(emails)} emails")
            return emails
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query emails: {e}")
        return []


async def query_calendar(
    user_id: str,
    days_ahead: int = 7,
    days_behind: int = 1,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Query google_calendar_events for upcoming events"""
    try:
        query = """
            SELECT 
                id,
                calendar_id,
                event_id,
                title,
                description,
                start_time,
                end_time,
                location,
                attendees,
                is_all_day,
                recurrence,
                status
            FROM google_calendar_events
            WHERE start_time >= NOW() - INTERVAL '1 day' * $1
              AND start_time <= NOW() + INTERVAL '1 day' * $2
              AND status != 'cancelled'
            ORDER BY start_time ASC
            LIMIT $3
        """
        
        results = await db_manager.fetch_all(query, days_behind, days_ahead, limit)
        
        if results:
            events = [dict(r) for r in results]
            logger.info(f"📆 Found {len(events)} calendar events")
            return events
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query calendar: {e}")
        return []


async def query_trends(
    user_id: str,
    days: int = 7,
    limit: int = 20,
    min_priority: int = 5
) -> List[Dict[str, Any]]:
    """Query google_trends_opportunities for trending topics"""
    try:
        query = """
            SELECT 
                id,
                keyword,
                search_volume,
                growth_percentage,
                opportunity_score,
                priority_score,
                status,
                target_account,
                ai_analysis,
                created_at
            FROM google_trends_opportunities
            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
              AND priority_score >= $2
              AND status IN ('pending', 'approved')
            ORDER BY priority_score DESC, created_at DESC
            LIMIT $3
        """
        
        results = await db_manager.fetch_all(query, days, min_priority, limit)
        
        if results:
            trends = [dict(r) for r in results]
            logger.info(f"📈 Found {len(trends)} trending opportunities")
            return trends
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query trends: {e}")
        return []


async def query_knowledge_base(
    user_id: str,
    query_text: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Query knowledge_entries for relevant information"""
    try:
        # Use text search for now - could add vector similarity later
        keywords = extract_keywords(query_text)
        
        if not keywords:
            return []
        
        # Build search pattern
        search_patterns = [f"%{kw}%" for kw in keywords[:5]]
        
        # Build OR conditions for each keyword
        conditions = []
        params = []
        for i, pattern in enumerate(search_patterns):
            conditions.append(f"(title ILIKE ${i+1} OR content ILIKE ${i+1})")
            params.append(pattern)
        
        params.append(limit)
        
        query = f"""
            SELECT 
                id,
                source_type,
                source_id,
                title,
                content,
                created_at,
                metadata
            FROM knowledge_entries
            WHERE {' OR '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${len(params)}
        """
        
        results = await db_manager.fetch_all(query, *params)
        
        if results:
            entries = [dict(r) for r in results]
            logger.info(f"📚 Found {len(entries)} knowledge entries")
            return entries
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query knowledge base: {e}")
        return []


async def query_weather(user_id: str) -> Optional[Dict[str, Any]]:
    """Query weather_readings for current conditions"""
    try:
        query = """
            SELECT 
                id,
                temperature,
                feels_like,
                humidity,
                pressure,
                uv_index,
                conditions,
                wind_speed,
                wind_direction,
                visibility,
                recorded_at,
                location_name
            FROM weather_readings
            ORDER BY recorded_at DESC
            LIMIT 1
        """
        
        result = await db_manager.fetch_one(query)
        
        if result:
            weather = dict(result)
            logger.info(f"🌤️ Found weather data: {weather.get('conditions')} at {weather.get('temperature')}°")
            return weather
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Failed to query weather: {e}")
        return None


async def query_tasks(
    user_id: str,
    limit: int = 20,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Query clickup_tasks for active tasks"""
    try:
        where_clauses = []
        params = []
        param_count = 0
        
        if status:
            param_count += 1
            where_clauses.append(f"status = ${param_count}")
            params.append(status)
        else:
            # Default: exclude completed tasks
            where_clauses.append("status NOT IN ('complete', 'closed')")
        
        param_count += 1
        params.append(limit)
        
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        query = f"""
            SELECT 
                id,
                clickup_id,
                name,
                description,
                status,
                priority,
                due_date,
                assignees,
                list_name,
                folder_name,
                space_name,
                updated_at
            FROM clickup_tasks
            {where_clause}
            ORDER BY 
                CASE priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5
                END,
                due_date ASC NULLS LAST
            LIMIT ${param_count}
        """
        
        results = await db_manager.fetch_all(query, *params)
        
        if results:
            tasks = [dict(r) for r in results]
            logger.info(f"✅ Found {len(tasks)} tasks")
            return tasks
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query tasks: {e}")
        return []


# ============================================================================
# iOS QUERY FUNCTIONS
# ============================================================================

async def query_ios_calendar(
    user_id: str,
    days_ahead: int = 7,
    days_behind: int = 1,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Query ios_calendar_events for events synced from iOS device.
    
    Args:
        user_id: User UUID
        days_ahead: How many days ahead to query
        days_behind: How many days back to query (for recently passed events)
        limit: Maximum events to return
    
    Returns:
        List of calendar event dicts
    """
    try:
        query = """
        SELECT 
            event_id,
            title,
            start_time,
            end_time,
            location,
            notes,
            is_all_day,
            calendar_name,
            synced_at
        FROM ios_calendar_events
        WHERE user_id = $1
          AND start_time >= NOW() - INTERVAL '1 day' * $2
          AND start_time <= NOW() + INTERVAL '1 day' * $3
        ORDER BY start_time ASC
        LIMIT $4
        """
        
        from uuid import UUID
        results = await db_manager.fetch_all(
            query,
            UUID(user_id),
            days_behind,
            days_ahead,
            limit
        )
        
        events = [dict(r) for r in results]
        logger.info(f"📱 Found {len(events)} iOS calendar events")
        return events
        
    except Exception as e:
        logger.error(f"❌ Failed to query iOS calendar: {e}")
        return []


async def query_ios_reminders(
    user_id: str,
    include_completed: bool = False,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Query ios_reminders for reminders synced from iOS device.
    
    Args:
        user_id: User UUID
        include_completed: Whether to include completed reminders
        limit: Maximum reminders to return
    
    Returns:
        List of reminder dicts
    """
    try:
        where_clause = "user_id = $1"
        params = [user_id]
        param_idx = 1
        
        if not include_completed:
            where_clause += " AND is_completed = FALSE"
        
        param_idx += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            reminder_id,
            title,
            notes,
            due_date,
            is_completed,
            completed_at,
            priority,
            list_name,
            synced_at
        FROM ios_reminders
        WHERE {where_clause}
        ORDER BY 
            CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
            due_date ASC,
            priority DESC
        LIMIT ${param_idx}
        """
        
        from uuid import UUID
        results = await db_manager.fetch_all(query, UUID(user_id), limit)
        
        reminders = [dict(r) for r in results]
        logger.info(f"📱 Found {len(reminders)} iOS reminders")
        return reminders
        
    except Exception as e:
        logger.error(f"❌ Failed to query iOS reminders: {e}")
        return []


async def get_current_music(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current music context from iOS device.
    Returns None if nothing playing or last update > 30 min ago.
    """
    try:
        query = """
        SELECT 
            track_title,
            artist,
            album,
            genre,
            duration_seconds,
            is_playing,
            mood_hint,
            started_at,
            updated_at
        FROM ios_music_context
        WHERE user_id = $1
          AND is_playing = TRUE
          AND updated_at >= NOW() - INTERVAL '30 minutes'
        ORDER BY updated_at DESC
        LIMIT 1
        """
        
        from uuid import UUID
        result = await db_manager.fetch_one(query, UUID(user_id))
        
        if result:
            music = dict(result)
            logger.debug(f"🎵 Current music: {music['track_title']} by {music['artist']}")
            return music
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Failed to get current music: {e}")
        return None


async def query_ios_contacts(
    user_id: str,
    search_term: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Query ios_contacts for contacts synced from iOS device.
    
    Args:
        user_id: User UUID
        search_term: Optional search term for name/email/org
        limit: Maximum contacts to return
    
    Returns:
        List of contact dicts
    """
    try:
        from uuid import UUID
        params = [UUID(user_id)]
        param_idx = 1
        
        where_clause = "user_id = $1"
        
        if search_term:
            param_idx += 1
            search_pattern = f"%{search_term}%"
            where_clause += f"""
                AND (
                    full_name ILIKE ${param_idx}
                    OR primary_email ILIKE ${param_idx}
                    OR organization ILIKE ${param_idx}
                    OR nickname ILIKE ${param_idx}
                )
            """
            params.append(search_pattern)
        
        param_idx += 1
        params.append(limit)
        
        query = f"""
            SELECT 
                contact_id,
                given_name,
                family_name,
                nickname,
                full_name,
                organization,
                job_title,
                primary_email,
                primary_phone,
                birthday,
                notes,
                synced_at
            FROM ios_contacts
            WHERE {where_clause}
            ORDER BY full_name ASC
            LIMIT ${param_idx}
        """
        
        results = await db_manager.fetch_all(query, *params)
        
        contacts = [dict(r) for r in results]
        logger.info(f"👥 Found {len(contacts)} iOS contacts")
        return contacts
        
    except Exception as e:
        logger.error(f"❌ Failed to query iOS contacts: {e}")
        return []


async def get_device_context(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current device context (location, health, battery) from iOS device.
    Returns the most recently updated active device's context.
    """
    try:
        from uuid import UUID
        
        query = """
        SELECT 
            device_name,
            device_model,
            last_latitude,
            last_longitude,
            last_location_name,
            last_health_data,
            last_seen_at
        FROM ios_devices
        WHERE user_id = $1
          AND is_active = TRUE
          AND last_seen_at >= NOW() - INTERVAL '1 hour'
        ORDER BY last_seen_at DESC
        LIMIT 1
        """
        
        result = await db_manager.fetch_one(query, UUID(user_id))
        
        if result:
            context = dict(result)
            logger.debug(f"📱 Device context: {context.get('last_location_name', 'Unknown location')}")
            return context
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Failed to get device context: {e}")
        return None


# ============================================================================
# INTENT DETECTION
# ============================================================================

def detect_query_intent(message: str) -> Dict[str, bool]:
    """
    Analyze user message to determine what databases to query.
    
    Intent flags:
    - query_meetings
    - query_emails
    - query_calendar
    - query_trends
    - query_knowledge
    - query_weather
    - query_tasks
    - query_ios_reminders
    - query_music (NEW)
    - query_contacts (NEW)
    - query_location (NEW)
    - query_health (NEW)
    - needs_briefing (comprehensive context)
    """
    message_lower = message.lower()
    
    intent = {
        'query_meetings': False,
        'query_emails': False,
        'query_calendar': False,
        'query_trends': False,
        'query_knowledge': False,
        'query_weather': False,
        'query_tasks': False,
        'query_ios_reminders': False,
        'query_music': False,
        'query_contacts': False,
        'query_location': False,
        'query_health': False,
        'needs_briefing': False
    }
    
    # Morning/briefing triggers
    briefing_keywords = [
        'good morning', 'morning', 'brief me', 'briefing', 'catch me up',
        'what did i miss', 'update me', 'what\'s new', 'what happened',
        'summary', 'overview', 'status update', 'daily report'
    ]
    if any(kw in message_lower for kw in briefing_keywords):
        intent['needs_briefing'] = True
    
    # Meeting queries
    meeting_keywords = [
        'meeting', 'call', 'zoom', 'teams', 'fathom', 'transcript',
        'discussed', 'met with', 'talked to', 'conversation with'
    ]
    if any(kw in message_lower for kw in meeting_keywords):
        intent['query_meetings'] = True
    
    # Email queries
    email_keywords = [
        'email', 'mail', 'inbox', 'message from', 'received',
        'sent', 'reply', 'forward', 'gmail', 'urgent email'
    ]
    if any(kw in message_lower for kw in email_keywords):
        intent['query_emails'] = True
    
    # Calendar queries
    calendar_keywords = [
        'calendar', 'schedule', 'event', 'appointment', 'meeting today',
        'this week', 'tomorrow', 'upcoming', 'when is', 'what time'
    ]
    if any(kw in message_lower for kw in calendar_keywords):
        intent['query_calendar'] = True
    
    # Trend queries
    trend_keywords = [
        'trend', 'trending', 'popular', 'viral', 'google trends',
        'content idea', 'topic', 'keyword', 'search volume'
    ]
    if any(kw in message_lower for kw in trend_keywords):
        intent['query_trends'] = True
    
    # Knowledge base queries
    knowledge_keywords = [
        'remember when', 'we discussed', 'previously', 'last time',
        'you told me', 'i mentioned', 'recall', 'history', 'past'
    ]
    if any(kw in message_lower for kw in knowledge_keywords):
        intent['query_knowledge'] = True
    
    # Weather queries
    weather_keywords = [
        'weather', 'temperature', 'rain', 'sun', 'uv', 'forecast',
        'hot', 'cold', 'humid', 'headache', 'outside'
    ]
    if any(kw in message_lower for kw in weather_keywords):
        intent['query_weather'] = True
    
    # Task queries
    task_keywords = [
        'task', 'todo', 'to do', 'to-do', 'clickup', 'due', 'deadline',
        'priority', 'assigned', 'work on'
    ]
    if any(kw in message_lower for kw in task_keywords):
        intent['query_tasks'] = True
    
    # iOS Reminders queries
    reminder_keywords = [
        'reminder', 'remind me', 'don\'t forget', 'need to',
        'pick up', 'buy', 'grocery', 'groceries', 'shopping list'
    ]
    if any(kw in message_lower for kw in reminder_keywords):
        intent['query_ios_reminders'] = True
    
    # Music queries (NEW)
    music_keywords = [
        'music', 'listening', 'playing', 'song', 'track', 'artist',
        'album', 'what am i listening', 'now playing', 'spotify', 'apple music',
        'tune', 'jamming', 'audio', 'playlist'
    ]
    if any(kw in message_lower for kw in music_keywords):
        intent['query_music'] = True
    
    # Contact queries (NEW)
    contact_keywords = [
        'contact', 'phone number', 'email address', 'call', 'text',
        'who is', 'reach', 'get ahold', 'number for', 'email for',
        'send to', 'message to', 'works at', 'birthday'
    ]
    if any(kw in message_lower for kw in contact_keywords):
        intent['query_contacts'] = True
    
    # Location queries (NEW)
    location_keywords = [
        'where am i', 'my location', 'current location', 'nearby',
        'around here', 'close to me', 'in the area', 'directions',
        'how far', 'distance to', 'local'
    ]
    if any(kw in message_lower for kw in location_keywords):
        intent['query_location'] = True
    
    # Health/battery queries (NEW)
    health_keywords = [
        'battery', 'charge', 'charging', 'low power', 'health', 'steps',
        'heart rate', 'sleep', 'calories', 'workout', 'exercise',
        'activity', 'fitness', 'phone battery', 'device battery'
    ]
    if any(kw in message_lower for kw in health_keywords):
        intent['query_health'] = True
    
    return intent


def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text for semantic search"""
    # Remove common words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'can', 'what', 'when', 'where',
        'who', 'which', 'how', 'why', 'that', 'this', 'these', 'those'
    }
    
    words = text.lower().split()
    keywords = [w.strip('.,!?;:') for w in words if w not in stop_words and len(w) > 2]
    return keywords[:10]  # Limit to 10 keywords


# ============================================================================
# CONTEXT FORMATTERS
# ============================================================================

def format_conversations_context(messages: List[Dict]) -> str:
    """Format conversation history for AI context"""
    if not messages:
        return ""
    
    lines = [
        "\n" + "="*80,
        "💬 CONVERSATION MEMORY (Cross-Thread)",
        "="*80,
        f"Found {len(messages)} relevant messages from past conversations:",
        ""
    ]
    
    current_thread = None
    for msg in reversed(messages):  # Show chronologically
        # Thread separator
        if msg['thread_id'] != current_thread:
            current_thread = msg['thread_id']
            thread_title = msg.get('thread_title') or 'Untitled'
            created = msg['created_at'].strftime('%Y-%m-%d %H:%M')
            lines.append(f"\n--- Thread: {thread_title} ({created}) ---")
        
        # Message
        role = "You" if msg['role'] == 'user' else "Assistant"
        content = msg['content'][:200] + "..." if len(msg['content']) > 200 else msg['content']
        lines.append(f"{role}: {content}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_meetings_context(meetings: List[Dict]) -> str:
    """Format meeting summaries for AI context"""
    if not meetings:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📅 RECENT MEETINGS (Fathom)",
        "="*80,
        f"Found {len(meetings)} meetings:",
        ""
    ]
    
    for meeting in meetings:
        date = meeting['meeting_date'].strftime('%Y-%m-%d') if meeting.get('meeting_date') else 'Unknown'
        title = meeting.get('title', 'Untitled Meeting')
        duration = meeting.get('duration_minutes', 0)
        
        lines.append(f"\n📌 {title}")
        lines.append(f"   Date: {date} | Duration: {duration} min")
        
        if meeting.get('participants'):
            participants = meeting['participants']
            if isinstance(participants, list):
                lines.append(f"   Participants: {', '.join(str(p) for p in participants[:5])}")
        
        if meeting.get('ai_summary'):
            summary = meeting['ai_summary'][:300] + "..." if len(meeting['ai_summary']) > 300 else meeting['ai_summary']
            lines.append(f"   Summary: {summary}")
        
        if meeting.get('key_points'):
            points = meeting['key_points']
            if isinstance(points, list) and len(points) > 0:
                lines.append("   Key Points:")
                for point in points[:3]:
                    lines.append(f"     • {point}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_emails_context(emails: List[Dict]) -> str:
    """Format emails for AI context"""
    if not emails:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📧 RECENT EMAILS",
        "="*80,
        f"Found {len(emails)} emails:",
        ""
    ]
    
    for email in emails:
        date = email['received_at'].strftime('%Y-%m-%d %H:%M') if email.get('received_at') else 'Unknown'
        sender = email.get('sender_name') or email.get('sender_email', 'Unknown')
        subject = email.get('subject', 'No Subject')
        is_read = "📖" if email.get('is_read') else "📬"
        is_important = "⭐" if email.get('is_important') else ""
        
        lines.append(f"\n{is_read}{is_important} From: {sender}")
        lines.append(f"   Subject: {subject}")
        lines.append(f"   Date: {date}")
        
        # Include email body if available (FIXED)
        if email.get('body_text'):
            body = email['body_text'][:500] + "..." if len(email['body_text']) > 500 else email['body_text']
            lines.append(f"   Body: {body}")
        elif email.get('snippet'):
            lines.append(f"   Preview: {email['snippet']}")
        
        if email.get('ai_summary'):
            lines.append(f"   AI Summary: {email['ai_summary']}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_calendar_context(events: List[Dict]) -> str:
    """Format calendar events for AI context"""
    if not events:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📆 GOOGLE CALENDAR",
        "="*80,
        f"Found {len(events)} upcoming events:",
        ""
    ]
    
    current_date = None
    for event in events:
        start = event.get('start_time')
        if start:
            event_date = start.strftime('%Y-%m-%d (%A)')
            if event_date != current_date:
                current_date = event_date
                lines.append(f"\n📅 {event_date}:")
            
            time_str = start.strftime('%I:%M %p')
            title = event.get('title', 'Untitled')
            
            lines.append(f"   {time_str} - {title}")
            
            if event.get('location'):
                lines.append(f"      📍 {event['location']}")
            
            if event.get('attendees'):
                attendees = event['attendees']
                if isinstance(attendees, list) and len(attendees) > 0:
                    lines.append(f"      👥 {len(attendees)} attendees")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_trends_context(trends: List[Dict]) -> str:
    """Format trending topics for AI context"""
    if not trends:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📈 TRENDING OPPORTUNITIES",
        "="*80,
        f"Found {len(trends)} active trends:",
        ""
    ]
    
    for trend in trends:
        keyword = trend.get('keyword', 'Unknown')
        priority = trend.get('priority_score', 0)
        volume = trend.get('search_volume', 0)
        growth = trend.get('growth_percentage', 0)
        target = trend.get('target_account', 'general')
        
        lines.append(f"\n🔥 {keyword}")
        lines.append(f"   Priority: {priority}/10 | Volume: {volume:,} | Growth: {growth}%")
        lines.append(f"   Target: {target}")
        
        if trend.get('ai_analysis'):
            analysis = trend['ai_analysis'][:200] + "..." if len(trend['ai_analysis']) > 200 else trend['ai_analysis']
            lines.append(f"   Analysis: {analysis}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_knowledge_context(entries: List[Dict]) -> str:
    """Format knowledge base entries for AI context"""
    if not entries:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📚 KNOWLEDGE BASE",
        "="*80,
        f"Found {len(entries)} relevant entries:",
        ""
    ]
    
    for entry in entries:
        source = entry.get('source_type', 'unknown')
        title = entry.get('title', 'Untitled')
        content = entry.get('content', '')[:300] + "..." if len(entry.get('content', '')) > 300 else entry.get('content', '')
        
        lines.append(f"\n📄 [{source}] {title}")
        lines.append(f"   {content}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_weather_context(weather: Dict) -> str:
    """Format weather data for AI context"""
    if not weather:
        return ""
    
    temp = weather.get('temperature', 'N/A')
    feels_like = weather.get('feels_like', temp)
    conditions = weather.get('conditions', 'Unknown')
    humidity = weather.get('humidity', 'N/A')
    uv = weather.get('uv_index', 'N/A')
    location = weather.get('location_name', 'Current Location')
    
    lines = [
        "\n" + "="*80,
        "🌤️ CURRENT WEATHER",
        "="*80,
        f"Location: {location}",
        f"Conditions: {conditions}",
        f"Temperature: {temp}°F (feels like {feels_like}°F)",
        f"Humidity: {humidity}%",
        f"UV Index: {uv}",
        "="*80,
        ""
    ]
    
    return "\n".join(lines)


def format_tasks_context(tasks: List[Dict]) -> str:
    """Format ClickUp tasks for AI context"""
    if not tasks:
        return ""
    
    lines = [
        "\n" + "="*80,
        "✅ CLICKUP TASKS",
        "="*80,
        f"Found {len(tasks)} active tasks:",
        ""
    ]
    
    # Group by priority
    urgent = [t for t in tasks if t.get('priority') == 'urgent']
    high = [t for t in tasks if t.get('priority') == 'high']
    normal = [t for t in tasks if t.get('priority') in ['normal', None]]
    
    if urgent:
        lines.append("\n🔴 URGENT:")
        for task in urgent:
            lines.append(f"   • {task.get('name', 'Untitled')} ({task.get('status', 'unknown')})")
    
    if high:
        lines.append("\n🟠 HIGH PRIORITY:")
        for task in high:
            lines.append(f"   • {task.get('name', 'Untitled')} ({task.get('status', 'unknown')})")
    
    if normal:
        lines.append("\n🟢 NORMAL:")
        for task in normal[:10]:  # Limit normal priority
            lines.append(f"   • {task.get('name', 'Untitled')} ({task.get('status', 'unknown')})")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_ios_calendar_context(events: List[Dict]) -> str:
    """Format iOS calendar events for AI context"""
    if not events:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📱 iOS CALENDAR",
        "="*80,
        f"Found {len(events)} events from iPhone:",
        ""
    ]
    
    # Group by date
    by_date: Dict[str, List[Dict]] = {}
    for event in events:
        start = event.get('start_time')
        if start:
            if isinstance(start, datetime):
                date_key = start.strftime('%Y-%m-%d (%A)')
            else:
                date_key = 'Unknown Date'
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(event)
    
    for date_key, date_events in sorted(by_date.items()):
        lines.append(f"\n📅 {date_key}:")
        for event in date_events:
            title = event.get('title', 'Untitled')
            start = event.get('start_time')
            is_all_day = event.get('is_all_day', False)
            
            if is_all_day:
                time_str = "All Day"
            elif start and isinstance(start, datetime):
                time_str = start.strftime('%I:%M %p')
            else:
                time_str = 'TBD'
            
            calendar_name = event.get('calendar_name', '')
            calendar_suffix = f" [{calendar_name}]" if calendar_name else ""
            
            lines.append(f"   • {time_str} - {title}{calendar_suffix}")
            
            if event.get('location'):
                lines.append(f"     📍 {event['location']}")
            
            if event.get('notes'):
                notes = event['notes'][:100] + "..." if len(event['notes']) > 100 else event['notes']
                lines.append(f"     📝 {notes}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_ios_reminders_context(reminders: List[Dict]) -> str:
    """Format iOS reminders for AI context"""
    if not reminders:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📱 iOS REMINDERS",
        "="*80,
        f"Found {len(reminders)} reminders from iPhone:",
        ""
    ]
    
    # Separate by due date status
    overdue = []
    due_today = []
    upcoming = []
    no_date = []
    
    now = datetime.now(timezone.utc)
    today = now.date()
    
    for reminder in reminders:
        due_date = reminder.get('due_date')
        if due_date:
            if isinstance(due_date, datetime):
                due = due_date.date()
            else:
                due = due_date
            
            if due < today:
                overdue.append(reminder)
            elif due == today:
                due_today.append(reminder)
            else:
                upcoming.append(reminder)
        else:
            no_date.append(reminder)
    
    def format_reminder(r: Dict) -> str:
        title = r.get('title', 'Untitled')
        priority = r.get('priority', 0)
        list_name = r.get('list_name', '')
        due_date = r.get('due_date')
        
        priority_marker = "❗" if priority >= 4 else ""
        list_suffix = f" [{list_name}]" if list_name else ""
        
        if due_date and isinstance(due_date, datetime):
            due_str = due_date.strftime('%m/%d %I:%M %p')
            return f"   {priority_marker}• {title}{list_suffix} (Due: {due_str})"
        else:
            return f"   {priority_marker}• {title}{list_suffix}"
    
    if overdue:
        lines.append("⚠️ OVERDUE:")
        for r in overdue[:5]:
            lines.append(format_reminder(r))
    
    if due_today:
        lines.append("\n📌 DUE TODAY:")
        for r in due_today[:5]:
            lines.append(format_reminder(r))
    
    if upcoming:
        lines.append("\n📋 UPCOMING:")
        for r in upcoming[:10]:
            lines.append(format_reminder(r))
    
    if no_date:
        lines.append("\n📝 NO DUE DATE:")
        for r in no_date[:5]:
            lines.append(format_reminder(r))
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_music_context(music: Dict) -> str:
    """Format current music for AI context"""
    if not music:
        return ""
    
    track = music.get('track_title', 'Unknown')
    artist = music.get('artist', 'Unknown Artist')
    album = music.get('album', '')
    genre = music.get('genre', '')
    
    lines = [
        "\n" + "="*80,
        "🎵 NOW PLAYING (LIVE DATA - USE THIS, NOT CONVERSATION HISTORY)",
        "="*80,
        f"Track: {track}",
        f"Artist: {artist}",
    ]
    
    if album:
        lines.append(f"Album: {album}")
    if genre:
        lines.append(f"Genre: {genre}")
    
    if music.get('mood_hint'):
        lines.append(f"Mood: {music['mood_hint']}")
    
    lines.extend([
        "",
        "IMPORTANT: This is real-time data from the iOS device. When the user asks",
        "what they're listening to, use THIS data, not anything from conversation history.",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_contacts_context(contacts: List[Dict], search_term: Optional[str] = None) -> str:
    """Format iOS contacts for AI context"""
    if not contacts:
        return ""
    
    header = f"🔍 Contacts matching '{search_term}':" if search_term else "👥 iOS CONTACTS"
    
    lines = [
        "\n" + "="*80,
        header,
        "="*80,
        f"Found {len(contacts)} contacts:",
        ""
    ]
    
    for contact in contacts:
        name = contact.get('full_name', 'Unknown')
        org = contact.get('organization', '')
        title = contact.get('job_title', '')
        email = contact.get('primary_email', '')
        phone = contact.get('primary_phone', '')
        
        lines.append(f"\n👤 {name}")
        
        if org and title:
            lines.append(f"   💼 {title} at {org}")
        elif org:
            lines.append(f"   🏢 {org}")
        elif title:
            lines.append(f"   💼 {title}")
        
        if email:
            lines.append(f"   📧 {email}")
        if phone:
            lines.append(f"   📱 {phone}")
        
        if contact.get('birthday'):
            birthday = contact['birthday']
            if isinstance(birthday, datetime):
                lines.append(f"   🎂 {birthday.strftime('%B %d')}")
        
        if contact.get('notes'):
            notes = contact['notes'][:100] + "..." if len(contact['notes']) > 100 else contact['notes']
            lines.append(f"   📝 {notes}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_location_context(device_context: Dict) -> str:
    """Format location context for AI"""
    if not device_context:
        return ""
    
    location_name = device_context.get('last_location_name', 'Unknown')
    latitude = device_context.get('last_latitude')
    longitude = device_context.get('last_longitude')
    device_name = device_context.get('device_name', 'iPhone')
    last_seen = device_context.get('last_seen_at')
    
    lines = [
        "\n" + "="*80,
        "📍 CURRENT LOCATION (LIVE DATA)",
        "="*80,
        f"Device: {device_name}",
        f"Location: {location_name}",
    ]
    
    if latitude and longitude:
        lines.append(f"Coordinates: {latitude:.4f}, {longitude:.4f}")
    
    if last_seen:
        if isinstance(last_seen, datetime):
            lines.append(f"Last Updated: {last_seen.strftime('%I:%M %p')}")
    
    lines.extend([
        "",
        "IMPORTANT: This is real-time location from the iOS device.",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_health_context(device_context: Dict) -> str:
    """Format health/battery context for AI"""
    if not device_context:
        return ""
    
    health_data = device_context.get('last_health_data', {})
    
    if not health_data:
        return ""
    
    # Handle case where health_data might be a JSON string
    if isinstance(health_data, str):
        try:
            health_data = json.loads(health_data)
        except:
            return ""
    
    device_name = device_context.get('device_name', 'iPhone')
    
    lines = [
        "\n" + "="*80,
        "📱 DEVICE STATUS & HEALTH (LIVE DATA)",
        "="*80,
        f"Device: {device_name}",
        ""
    ]
    
    # Battery info
    battery_level = health_data.get('battery_level')
    battery_state = health_data.get('battery_state')
    is_charging = health_data.get('is_charging')
    is_low_power = health_data.get('is_low_power_mode')
    is_low_battery = health_data.get('is_low_battery')
    is_critical = health_data.get('is_critical_battery')
    
    if battery_level is not None:
        battery_emoji = "🔋"
        if is_critical:
            battery_emoji = "🪫"
            lines.append(f"{battery_emoji} CRITICAL BATTERY: {battery_level}%")
        elif is_low_battery:
            battery_emoji = "🔋"
            lines.append(f"{battery_emoji} LOW BATTERY: {battery_level}%")
        elif is_charging:
            battery_emoji = "⚡"
            lines.append(f"{battery_emoji} Charging: {battery_level}%")
        else:
            lines.append(f"{battery_emoji} Battery: {battery_level}%")
        
        if is_low_power:
            lines.append("   ⚠️ Low Power Mode is ON")
    
    # Health metrics
    steps = health_data.get('step_count')
    heart_rate = health_data.get('heart_rate')
    calories = health_data.get('active_calories')
    sleep = health_data.get('sleep_hours')
    
    if steps or heart_rate or calories or sleep:
        lines.append("\n📊 Health Metrics:")
        if steps:
            lines.append(f"   👟 Steps: {steps:,}")
        if heart_rate:
            lines.append(f"   ❤️ Heart Rate: {heart_rate} bpm")
        if calories:
            lines.append(f"   🔥 Active Calories: {calories}")
        if sleep:
            lines.append(f"   😴 Sleep: {sleep} hours")
    
    lines.extend([
        "",
        "IMPORTANT: This is real-time data from the iOS device.",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

async def build_memory_context(
    user_id: str,
    user_message: str,
    thread_id: Optional[str] = None
) -> str:
    """
    Main orchestrator: Build comprehensive context based on:
    1. Context level (minimal/comprehensive/full)
    2. Query intent (what the user is asking about)
    
    This is called BEFORE building the AI prompt to inject relevant memory.
    
    NO LOOPS: This function only QUERIES data, never triggers actions.
    """
    try:
        logger.info("="*80)
        logger.info("🧠 MEMORY QUERY LAYER - Starting context build")
        logger.info("="*80)
        
        # Step 1: Detect context level
        context_level = await detect_context_level(user_id, thread_id)
        
        # Step 2: Detect query intent
        intent = detect_query_intent(user_message)
        
        # Step 3: Build context based on level and intent
        context_parts = []
        
        # ALWAYS: Load recent conversations (hot cache)
        # NOTE: Notification threads are now EXCLUDED by default to prevent loops
        conversations = await query_conversations(
            user_id=user_id,
            days=CONTEXT_CONFIG['hot_cache_days'],
            limit=CONTEXT_CONFIG['limits']['hot_conversations'],
            exclude_thread_id=thread_id,
            include_notification_threads=False  # Prevents regenerating AI drafts
        )
        if conversations:
            context_parts.append(format_conversations_context(conversations))
        
        # COMPREHENSIVE/FULL: Load additional conversation history
        if context_level in ['comprehensive', 'full']:
            older_conversations = await query_conversations(
                user_id=user_id,
                days=CONTEXT_CONFIG['warm_cache_days'],
                limit=CONTEXT_CONFIG['limits']['warm_conversations'],
                exclude_thread_id=thread_id,
                include_notification_threads=False  # Prevents regenerating AI drafts
            )
            # Don't duplicate, just note we have deeper history
            if older_conversations and len(older_conversations) > len(conversations):
                logger.info(f"📚 Loaded {len(older_conversations)} total conversations (warm cache)")
        
        # FULL: Load everything including iOS data
        if context_level == 'full' or intent['needs_briefing']:
            logger.info("📊 Full briefing mode - loading all data sources")
            
            # Meetings
            meetings = await query_meetings(
                user_id=user_id,
                days=14,
                limit=CONTEXT_CONFIG['limits']['meetings']
            )
            if meetings:
                context_parts.append(format_meetings_context(meetings))
            
            # Google Calendar
            calendar = await query_calendar(
                user_id=user_id,
                days_ahead=7,
                limit=CONTEXT_CONFIG['limits']['calendar_events']
            )
            if calendar:
                context_parts.append(format_calendar_context(calendar))
            
            # iOS Calendar
            ios_calendar = await query_ios_calendar(
                user_id=user_id,
                days_ahead=7,
                limit=CONTEXT_CONFIG['limits']['ios_calendar']
            )
            if ios_calendar:
                context_parts.append(format_ios_calendar_context(ios_calendar))
            
            # iOS Reminders
            ios_reminders = await query_ios_reminders(
                user_id=user_id,
                include_completed=False,
                limit=CONTEXT_CONFIG['limits']['ios_reminders']
            )
            if ios_reminders:
                context_parts.append(format_ios_reminders_context(ios_reminders))
            
            # Current Music
            current_music = await get_current_music(user_id)
            if current_music:
                context_parts.append(format_music_context(current_music))
            
            # Device Context (Location + Health/Battery)
            device_context = await get_device_context(user_id)
            if device_context:
                context_parts.append(format_location_context(device_context))
                context_parts.append(format_health_context(device_context))
            
            # Emails (FIXED - now includes body!)
            emails = await query_emails(
                user_id=user_id,
                days=7,
                limit=CONTEXT_CONFIG['limits']['emails'],
                unread_only=False,
                important_only=False
            )
            if emails:
                context_parts.append(format_emails_context(emails))
            
            # Tasks
            tasks = await query_tasks(
                user_id=user_id,
                limit=CONTEXT_CONFIG['limits']['tasks']
            )
            if tasks:
                context_parts.append(format_tasks_context(tasks))
            
            # Trends
            trends = await query_trends(
                user_id=user_id,
                days=7,
                limit=CONTEXT_CONFIG['limits']['trends']
            )
            if trends:
                context_parts.append(format_trends_context(trends))
            
            # Weather
            weather = await query_weather(user_id)
            if weather:
                context_parts.append(format_weather_context(weather))
        
        # INTENT-BASED: Query specific databases based on user message
        else:
            if intent['query_meetings']:
                meetings = await query_meetings(user_id=user_id, days=14, limit=10)
                if meetings:
                    context_parts.append(format_meetings_context(meetings))
            
            if intent['query_emails']:
                emails = await query_emails(user_id=user_id, days=7, limit=15)
                if emails:
                    context_parts.append(format_emails_context(emails))
            
            if intent['query_calendar']:
                # Query both Google and iOS calendars
                calendar = await query_calendar(user_id=user_id, days_ahead=7, limit=20)
                if calendar:
                    context_parts.append(format_calendar_context(calendar))
                
                ios_calendar = await query_ios_calendar(user_id=user_id, days_ahead=7, limit=20)
                if ios_calendar:
                    context_parts.append(format_ios_calendar_context(ios_calendar))
            
            if intent['query_trends']:
                trends = await query_trends(user_id=user_id, days=7, limit=10)
                if trends:
                    context_parts.append(format_trends_context(trends))
            
            if intent['query_knowledge']:
                knowledge = await query_knowledge_base(
                    user_id=user_id,
                    query_text=user_message,
                    limit=CONTEXT_CONFIG['limits']['knowledge_base']
                )
                if knowledge:
                    context_parts.append(format_knowledge_context(knowledge))
            
            if intent['query_weather']:
                weather = await query_weather(user_id)
                if weather:
                    context_parts.append(format_weather_context(weather))
            
            if intent['query_tasks']:
                tasks = await query_tasks(user_id=user_id, limit=15)
                if tasks:
                    context_parts.append(format_tasks_context(tasks))
            
            # iOS Reminders - triggered by reminder keywords
            if intent['query_ios_reminders']:
                ios_reminders = await query_ios_reminders(user_id=user_id, limit=20)
                if ios_reminders:
                    context_parts.append(format_ios_reminders_context(ios_reminders))
            
            # Music - triggered by music keywords (NEW)
            if intent['query_music']:
                current_music = await get_current_music(user_id)
                if current_music:
                    context_parts.append(format_music_context(current_music))
                else:
                    # Let the AI know we checked but nothing is playing
                    context_parts.append("\n🎵 No music currently playing (checked iOS device)\n")
            
            # Contacts - triggered by contact keywords (NEW)
            if intent['query_contacts']:
                # Try to extract a name from the query
                search_term = None
                name_patterns = [
                    r"who is (\w+)",
                    r"contact (?:for |info for )?(\w+)",
                    r"(\w+)'s (?:number|email|phone|contact)",
                    r"call (\w+)",
                    r"text (\w+)",
                    r"email (\w+)"
                ]
                for pattern in name_patterns:
                    match = re.search(pattern, user_message.lower())
                    if match:
                        search_term = match.group(1)
                        break
                
                contacts = await query_ios_contacts(
                    user_id=user_id,
                    search_term=search_term,
                    limit=CONTEXT_CONFIG['limits']['ios_contacts']
                )
                if contacts:
                    context_parts.append(format_contacts_context(contacts, search_term))
            
            # Location - triggered by location keywords (NEW)
            if intent['query_location']:
                device_context = await get_device_context(user_id)
                if device_context:
                    context_parts.append(format_location_context(device_context))
            
            # Health/Battery - triggered by health keywords (NEW)
            if intent['query_health']:
                device_context = await get_device_context(user_id)
                if device_context:
                    context_parts.append(format_health_context(device_context))
        
        # Combine all context parts
        if not context_parts:
            logger.info("ℹ️  No additional context found")
            return ""
        
        full_context = "\n".join(context_parts)
        
        logger.info("="*80)
        logger.info(f"✅ Memory context built: {len(full_context)} characters")
        logger.info(f"   Context level: {context_level}")
        logger.info(f"   Sources queried: {len(context_parts)}")
        logger.info("="*80)
        
        return full_context
        
    except Exception as e:
        logger.error(f"❌ Failed to build memory context: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ""


# ============================================================================
# EXPORT
# ============================================================================

__all__ = ['build_memory_context']
