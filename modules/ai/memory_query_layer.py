"""
SYNTAX PRIME V2 - MEMORY QUERY LAYER
Created: 2024-10-26
Updated: 2025 - Fixed SQL injection vulnerabilities (INTERVAL string formatting)
Updated: 2025-12-18 - Added notification thread filtering to prevent conversation loops
Updated: 2025-12-26 - Fixed UUID case-sensitivity bug causing every message to load COMPREHENSIVE context
Updated: 2025-12-29 - Added iOS calendar/reminders integration + FIXED email body not being queried

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
    'hot_cache_days': 60,           # Always loaded (recent discussions)
    'warm_cache_days': 90,          # Loaded on new day/thread
    'cold_cache_days': 150,         # Query-based (everything in V2)
    'hours_gap_threshold': 8,       # Hours before comprehensive context
    
    'limits': {
        'hot_conversations': 800,    # Recent messages always available
        'warm_conversations': 1300,  # Comprehensive context
        'cold_conversations': 250,   # Semantic search results
        'meetings': 14,              # From last 14 days
        'emails': 50,                # Unread/important
        'calendar_events': 30,       # Upcoming events
        'trends': 30,                # High-priority trends
        'knowledge_base': 100,       # Semantic search results
        'weather': 1,                # Current reading
        'tasks': 20,                 # Active tasks
        'ios_calendar': 20,          # iOS calendar events
        'ios_reminders': 30          # iOS reminders
    }
}

# ============================================================================
# NOTIFICATION THREAD FILTER
# ============================================================================
# These are AI-generated notification threads, NOT user conversations.
# Including them in memory context causes the AI to regenerate the same content.

EXCLUDED_THREAD_PATTERNS = [
    'Bluesky Draft:%',           # AI-generated Bluesky drafts
    'Trending Opportunities',     # Trend notifications
    'Intelligence Briefings',     # Proactive intelligence
    'Weather Alerts',             # Weather notifications
    'Prayer Times',               # Prayer reminders
    'Meeting Summaries',          # Fathom meeting summaries
    'Email Notifications',        # Email alerts
    'Calendar Alerts',            # Calendar reminders
    'Reminders',                  # General reminders
    'Engagement Opportunities',   # Bluesky engagement
    'Analytics Reports',          # Analytics notifications
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
        if not include_notification_threads:
            exclusion_conditions = []
            for pattern in EXCLUDED_THREAD_PATTERNS:
                param_count += 1
                exclusion_conditions.append(f"ct.title NOT LIKE ${param_count}")
                params.append(pattern)
            
            if exclusion_conditions:
                where_clauses.append(f"({' AND '.join(exclusion_conditions)})")
                logger.debug(f"🚫 Excluding {len(EXCLUDED_THREAD_PATTERNS)} notification thread patterns from memory")
        
        # Keyword filter (if semantic search)
        if keywords:
            keyword_conditions = []
            for keyword in keywords[:5]:  # Limit to 5 keywords
                param_count += 1
                keyword_conditions.append(f"cm.content ILIKE ${param_count}")
                params.append(f"%{keyword}%")
            
            if keyword_conditions:
                where_clauses.append(f"({' OR '.join(keyword_conditions)})")
        
        param_count += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            cm.id,
            cm.thread_id,
            cm.role,
            cm.content,
            cm.created_at,
            ct.title as thread_title
        FROM conversation_messages cm
        LEFT JOIN conversation_threads ct ON cm.thread_id = ct.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY cm.created_at DESC
        LIMIT ${param_count}
        """
        
        results = await db_manager.fetch_all(query, *params)
        logger.info(f"💬 Found {len(results)} conversation messages (last {days} days)")
        return results
        
    except Exception as e:
        logger.error(f"❌ Failed to query conversations: {e}")
        return []


async def query_meetings(
    user_id: str,
    days: int = 14,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Query fathom_meetings for recent meetings with transcripts and summaries
    """
    try:
        query = """
        SELECT 
            id,
            title,
            ai_summary,
            transcript_text,
            meeting_date,
            duration_minutes,
            participants,
            key_points,
            created_at
        FROM fathom_meetings
        WHERE meeting_date >= NOW() - INTERVAL '1 day' * $1
        ORDER BY meeting_date DESC
        LIMIT $2
        """
        
        meetings = await db_manager.fetch_all(query, days, limit)
        logger.info(f"📅 Found {len(meetings)} meetings (last {days} days)")
        return meetings
        
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
    """
    Query google_gmail_analysis for recent emails
    
    FIXED 2025-12-29: Now includes 'body' field so AI can actually read email content!
    """
    try:
        where_clauses = ["user_id = $1"]
        params: List[Any] = [user_id]
        param_count = 1
        
        # Time filter - parameterized
        param_count += 1
        where_clauses.append(f"received_at >= NOW() - INTERVAL '1 day' * ${param_count}")
        params.append(days)
        
        if important_only:
            where_clauses.append("priority_level IN ('high', 'urgent')")
        
        where_clause = " AND ".join(where_clauses)
        
        param_count += 1
        params.append(limit)
        
        # FIXED: Now includes 'body' column so AI can read email content!
        query = f"""
        SELECT 
            message_id,
            thread_id,
            subject,
            sender_name,
            sender_email,
            snippet,
            body,
            received_at,
            priority_level,
            category,
            requires_response,
            sentiment,
            action_items,
            key_entities
        FROM google_gmail_analysis
        WHERE {where_clause}
        ORDER BY received_at DESC
        LIMIT ${param_count}
        """
        
        emails = await db_manager.fetch_all(query, *params)
        logger.info(f"📧 Found {len(emails)} emails (last {days} days, important={important_only})")
        return emails
        
    except Exception as e:
        logger.error(f"❌ Failed to query emails: {e}")
        return []


async def query_calendar(
    user_id: str,
    days_ahead: int = 7,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Query google_calendar_events for upcoming events
    """
    try:
        query = """
        SELECT 
            event_id,
            calendar_id,
            summary,
            description,
            start_time,
            end_time,
            location,
            attendees,
            is_cancelled,
            created_at
        FROM google_calendar_events
        WHERE user_id = $1
        AND start_time >= NOW()
        AND start_time <= NOW() + INTERVAL '1 day' * $2
        ORDER BY start_time ASC
        LIMIT $3
        """
        
        events = await db_manager.fetch_all(query, user_id, days_ahead, limit)
        logger.info(f"📆 Found {len(events)} calendar events (next {days_ahead} days)")
        return events
        
    except Exception as e:
        logger.error(f"❌ Failed to query calendar: {e}")
        return []


async def query_trends(
    user_id: str,
    days: int = 7,
    limit: int = 15,
    business_area: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query trends data - DISABLED for now since google_trends_data table doesn't exist
    TODO: Implement with expanded_keywords_for_trends table
    """
    try:
        logger.info("📊 Trends query disabled - table structure needs updating")
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to query trends: {e}")
        return []


async def query_knowledge_base(
    user_id: str,
    query_text: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Query knowledge_entries with semantic search
    This is the reference library (ChatGPT export data)
    """
    try:
        # Simple keyword search (can be enhanced with vector search later)
        keywords = query_text.lower().split()
        keyword_conditions = []
        params: List[Any] = [user_id]
        param_count = 1
        
        for keyword in keywords[:5]:  # Limit to 5 keywords
            param_count += 1
            keyword_conditions.append(f"(LOWER(title) LIKE ${param_count} OR LOWER(content) LIKE ${param_count})")
            params.append(f"%{keyword}%")
        
        if not keyword_conditions:
            return []
        
        keyword_clause = " OR ".join(keyword_conditions)
        
        param_count += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            id,
            title,
            content,
            content_type,
            key_topics,
            word_count,
            relevance_score,
            created_at,
            updated_at
        FROM knowledge_entries
        WHERE user_id = $1
        AND ({keyword_clause})
        ORDER BY updated_at DESC
        LIMIT ${param_count}
        """
        
        results = await db_manager.fetch_all(query, *params)
        logger.info(f"📚 Found {len(results)} knowledge entries matching: {query_text[:50]}")
        return results
        
    except Exception as e:
        logger.error(f"❌ Failed to query knowledge base: {e}")
        return []


async def query_weather(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Query weather_readings for most recent weather data
    """
    try:
        query = """
        SELECT 
            timestamp,
            location,
            temperature,
            temperature_apparent,
            humidity,
            wind_speed,
            weather_description,
            precipitation_probability,
            uv_index,
            uv_risk_level,
            headache_risk_level,
            headache_risk_score,
            headache_risk_factors,
            severe_weather_alert,
            alert_description
        FROM weather_readings
        WHERE user_id = $1
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        weather = await db_manager.fetch_one(query, user_id)
        if weather:
            logger.info(f"⛅ Found current weather: {weather['temperature']}°F, {weather['weather_description']}")
        return weather
        
    except Exception as e:
        logger.error(f"❌ Failed to query weather: {e}")
        return None


async def query_tasks(
    user_id: str,
    limit: int = 20,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query clickup_tasks for active tasks
    """
    try:
        where_clauses = ["user_id = $1"]
        params: List[Any] = [user_id]
        param_count = 1
        
        if status:
            param_count += 1
            where_clauses.append(f"status = ${param_count}")
            params.append(status)
        else:
            # Default: exclude completed/closed
            where_clauses.append("status NOT IN ('complete', 'closed', 'done')")
        
        param_count += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            task_id,
            name,
            description,
            status,
            priority,
            due_date,
            assignees,
            list_name,
            folder_name,
            created_at,
            updated_at
        FROM clickup_tasks
        WHERE {' AND '.join(where_clauses)}
        ORDER BY 
            CASE priority 
                WHEN 'urgent' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'normal' THEN 3 
                WHEN 'low' THEN 4 
            END,
            due_date ASC NULLS LAST
        LIMIT ${param_count}
        """
        
        tasks = await db_manager.fetch_all(query, *params)
        logger.info(f"✅ Found {len(tasks)} active tasks")
        return tasks
        
    except Exception as e:
        logger.error(f"❌ Failed to query tasks: {e}")
        return []


# ============================================================================
# iOS QUERY FUNCTIONS (NEW)
# ============================================================================

async def query_ios_calendar(
    user_id: str,
    days_ahead: int = 7,
    days_behind: int = 0,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Query ios_calendar_events for events synced from iOS device.
    
    Args:
        user_id: User UUID
        days_ahead: Days into the future to include
        days_behind: Days into the past to include (for context)
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
    - query_ios_reminders (NEW)
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
    
    # iOS Reminders queries (NEW)
    reminder_keywords = [
        'reminder', 'remind me', 'don\'t forget', 'need to',
        'pick up', 'buy', 'grocery', 'groceries', 'shopping list'
    ]
    if any(kw in message_lower for kw in reminder_keywords):
        intent['query_ios_reminders'] = True
    
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
    """Format meeting history for AI context"""
    if not meetings:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📅 RECENT MEETINGS",
        "="*80,
        f"Found {len(meetings)} meetings from last 14 days:",
        ""
    ]
    
    for meeting in meetings:
        title = meeting.get('title') or 'Untitled Meeting'
        
        # Convert UTC to user timezone
        from modules.ai.chat import convert_utc_to_user_timezone
        
        meeting_date = meeting.get('meeting_date')
        if meeting_date and isinstance(meeting_date, datetime):
            meeting_dt = convert_utc_to_user_timezone(meeting_date)
            start = meeting_dt.strftime('%Y-%m-%d %H:%M')
        else:
            start = 'Unknown'
        
        duration = meeting.get('duration_minutes') or 0
        
        lines.append(f"\n📌 {title}")
        lines.append(f"   Time: {start} ({duration} min)")
        
        # Parse participants if it's a JSON string
        if meeting.get('participants'):
            parts = meeting['participants']
            if isinstance(parts, str):
                try:
                    parts = json.loads(parts)
                except (json.JSONDecodeError, TypeError):
                    parts = []
            if isinstance(parts, list) and parts:
                parts_str = ', '.join(parts[:3])  # First 3 participants
                lines.append(f"   Participants: {parts_str}")

        # Use 'ai_summary' instead of 'summary'
        if meeting.get('ai_summary'):
            summary = meeting['ai_summary'][:200] + "..." if len(meeting['ai_summary']) > 200 else meeting['ai_summary']
            lines.append(f"   Summary: {summary}")

        # Parse key_points if it's a JSON string
        if meeting.get('key_points'):
            key_points = meeting['key_points']
            if isinstance(key_points, str):
                try:
                    key_points = json.loads(key_points)
                except (json.JSONDecodeError, TypeError):
                    key_points = []
            if isinstance(key_points, list) and key_points:
                lines.append("   Key Points:")
                for item in key_points[:3]:  # First 3 items
                    lines.append(f"      • {item}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_emails_context(emails: List[Dict]) -> str:
    """
    Format email summary for AI context
    
    FIXED 2025-12-29: Now shows actual email content (body/snippet) instead of just metadata!
    Shows ALL emails, not just priority/response ones.
    """
    if not emails:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📧 RECENT EMAILS",
        "="*80,
        f"Found {len(emails)} emails:",
        ""
    ]
    
    # Separate by priority for better organization
    high_priority = [e for e in emails if e.get('priority_level') in ['high', 'urgent']]
    needs_response = [e for e in emails if e.get('requires_response') and e not in high_priority]
    regular = [e for e in emails if e not in high_priority and e not in needs_response]
    
    def format_email(email: Dict) -> List[str]:
        """Format a single email with content"""
        email_lines = []
        sender = email.get('sender_name') or email.get('sender_email', 'Unknown')
        subject = email.get('subject', 'No subject')
        
        # Get email content - prefer body, fall back to snippet
        content = email.get('body') or email.get('snippet') or ''
        
        # Truncate long content but show enough to be useful
        if len(content) > 500:
            content = content[:500] + "..."
        
        # Format received time
        received = email.get('received_at')
        if received and isinstance(received, datetime):
            time_str = received.strftime('%m/%d %I:%M %p')
        else:
            time_str = 'Unknown time'
        
        email_lines.append(f"\n   📩 From: {sender}")
        email_lines.append(f"      Subject: {subject}")
        email_lines.append(f"      Received: {time_str}")
        
        # Show sentiment and category if available
        if email.get('sentiment'):
            email_lines.append(f"      Sentiment: {email['sentiment']}")
        if email.get('category'):
            email_lines.append(f"      Category: {email['category']}")
        
        # Show the actual email content!
        if content:
            email_lines.append(f"      Content: {content}")
        
        # Show action items if present
        action_items = email.get('action_items')
        if action_items:
            if isinstance(action_items, str):
                try:
                    action_items = json.loads(action_items)
                except (json.JSONDecodeError, TypeError):
                    action_items = []
            if isinstance(action_items, list) and action_items:
                email_lines.append("      Action Items:")
                for item in action_items[:3]:
                    email_lines.append(f"         • {item}")
        
        return email_lines
    
    # High priority emails first
    if high_priority:
        lines.append("🔴 HIGH PRIORITY:")
        for email in high_priority[:10]:  # Top 10
            lines.extend(format_email(email))
    
    # Needs response
    if needs_response:
        lines.append("\n⚡ NEEDS RESPONSE:")
        for email in needs_response[:10]:  # Top 10
            lines.extend(format_email(email))
    
    # Regular emails (show fewer to avoid context bloat)
    if regular:
        lines.append("\n📬 OTHER EMAILS:")
        for email in regular[:10]:  # Top 10
            lines.extend(format_email(email))
    
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
        "📆 UPCOMING EVENTS (Google Calendar)",
        "="*80,
        f"Found {len(events)} events in next 7 days:",
        ""
    ]
    
    # Group by date
    by_date: Dict[str, List[Dict]] = {}
    for event in events:
        start = event.get('start_time')
        if start:
            date_key = start.strftime('%Y-%m-%d (%A)')
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(event)
    
    for date_key, date_events in sorted(by_date.items()):
        lines.append(f"\n📅 {date_key}:")
        for event in date_events:
            summary = event.get('summary', 'Untitled')
            start = event.get('start_time')
            time_str = start.strftime('%H:%M') if start else 'TBD'
            lines.append(f"   • {time_str} - {summary}")
            
            if event.get('location'):
                lines.append(f"     📍 {event['location']}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_trends_context(trends: List[Dict]) -> str:
    """Format trends for AI context"""
    if not trends:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📊 TRENDING OPPORTUNITIES",
        "="*80,
        f"Found {len(trends)} relevant trends:",
        ""
    ]
    
    for trend in trends[:10]:
        keyword = trend.get('keyword', 'Unknown')
        score = trend.get('score', 0)
        momentum = trend.get('momentum', 'stable')
        
        emoji = "🔥" if score > 80 else "📈" if score > 50 else "📊"
        lines.append(f"{emoji} {keyword} (Score: {score}/100, {momentum})")
    
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
        "📚 KNOWLEDGE BASE MATCHES",
        "="*80,
        f"Found {len(entries)} relevant entries:",
        ""
    ]
    
    for entry in entries[:5]:
        title = entry.get('title', 'Untitled')[:50]
        content = entry.get('content', '')[:150]
        
        lines.append(f"\n📖 {title}")
        lines.append(f"   {content}...")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_weather_context(weather: Dict) -> str:
    """Format weather for AI context"""
    if not weather:
        return ""
    
    temp = weather.get('temperature', 'N/A')
    feels = weather.get('temperature_apparent', temp)
    desc = weather.get('weather_description', 'Unknown')
    uv = weather.get('uv_index', 0)
    uv_risk = weather.get('uv_risk_level', 'low')
    headache = weather.get('headache_risk_level', 'low')
    
    lines = [
        "\n" + "="*80,
        "⛅ CURRENT WEATHER",
        "="*80,
        f"Temperature: {temp}°F (feels like {feels}°F)",
        f"Conditions: {desc}",
        f"UV Index: {uv} ({uv_risk} risk)",
        f"Headache Risk: {headache}",
    ]
    
    if weather.get('severe_weather_alert'):
        lines.append(f"⚠️ ALERT: {weather.get('alert_description', 'Severe weather')}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_tasks_context(tasks: List[Dict]) -> str:
    """Format tasks for AI context"""
    if not tasks:
        return ""
    
    lines = [
        "\n" + "="*80,
        "✅ ACTIVE TASKS (ClickUp)",
        "="*80,
        f"Found {len(tasks)} active tasks:",
        ""
    ]
    
    # Group by priority
    by_priority: Dict[str, List[Dict]] = {}
    for task in tasks:
        priority = task.get('priority', 'normal')
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(task)
    
    priority_order = ['urgent', 'high', 'normal', 'low']
    
    for priority in priority_order:
        if priority not in by_priority:
            continue
        
        priority_tasks = by_priority[priority]
        emoji = "🔴" if priority == 'urgent' else "🟠" if priority == 'high' else "🟡" if priority == 'normal' else "🟢"
        
        lines.append(f"\n{emoji} {priority.upper()} ({len(priority_tasks)}):")
        
        for task in priority_tasks[:5]:  # Top 5 per priority
            name = task.get('name') or 'Untitled Task'
            status = task.get('status', 'unknown')
            
            lines.append(f"   • {name} [{status}]")
            
            if task.get('due_date'):
                due = task['due_date'].strftime('%Y-%m-%d')
                lines.append(f"     Due: {due}")
            
            if task.get('assignees'):
                assignees = task['assignees'][:2]  # First 2
                lines.append(f"     Assigned: {', '.join(assignees)}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


# ============================================================================
# iOS CONTEXT FORMATTERS (NEW)
# ============================================================================

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
        "🎵 NOW PLAYING",
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
    MAIN FUNCTION - Build comprehensive memory context
    
    This is the single entry point called from router.py
    
    Process:
    1. Detect context level (minimal/comprehensive/full)
    2. Detect query intent (what to search for)
    3. Query relevant databases
    4. Format results for AI
    5. Return formatted context string
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
            
            # iOS Calendar (NEW)
            ios_calendar = await query_ios_calendar(
                user_id=user_id,
                days_ahead=7,
                limit=CONTEXT_CONFIG['limits']['ios_calendar']
            )
            if ios_calendar:
                context_parts.append(format_ios_calendar_context(ios_calendar))
            
            # iOS Reminders (NEW)
            ios_reminders = await query_ios_reminders(
                user_id=user_id,
                include_completed=False,
                limit=CONTEXT_CONFIG['limits']['ios_reminders']
            )
            if ios_reminders:
                context_parts.append(format_ios_reminders_context(ios_reminders))
            
            # Current Music (NEW)
            current_music = await get_current_music(user_id)
            if current_music:
                context_parts.append(format_music_context(current_music))
            
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
            
            # iOS Reminders (NEW) - triggered by reminder keywords
            if intent['query_ios_reminders']:
                ios_reminders = await query_ios_reminders(user_id=user_id, limit=20)
                if ios_reminders:
                    context_parts.append(format_ios_reminders_context(ios_reminders))
        
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
