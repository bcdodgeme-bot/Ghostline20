"""
SYNTAX PRIME V2 - MEMORY QUERY LAYER
Created: 2024-10-26
Updated: 2025 - Fixed SQL injection vulnerabilities (INTERVAL string formatting)
Updated: 2025-12-18 - Added notification thread filtering to prevent conversation loops

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
        'tasks': 20                  # Active tasks
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
        is_new_thread = not thread_id or str(last_msg['thread_id']) != str(thread_id)
        
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
            for keyword in keywords:
                param_count += 1
                keyword_conditions.append(f"cm.content ILIKE ${param_count}")
                params.append(f"%{keyword}%")
            where_clauses.append(f"({' OR '.join(keyword_conditions)})")
        
        where_clause = " AND ".join(where_clauses)
        
        param_count += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            cm.id,
            cm.thread_id,
            cm.role,
            cm.content,
            cm.created_at,
            ct.title as thread_title,
            ct.platform
        FROM conversation_messages cm
        JOIN conversation_threads ct ON cm.thread_id = ct.id
        WHERE {where_clause}
        ORDER BY cm.created_at DESC
        LIMIT ${param_count}
        """
        
        messages = await db_manager.fetch_all(query, *params)
        logger.info(f"💬 Found {len(messages)} conversation messages ({days}d, limit={limit}, excl_notif={not include_notification_threads})")
        return messages
        
    except Exception as e:
        logger.error(f"❌ Failed to query conversations: {e}")
        return []


async def query_meetings(
    user_id: str,
    days: int = 14,
    limit: int = 14
) -> List[Dict[str, Any]]:
    """
    Query fathom_meetings for recent transcribed meetings
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
        
        query = f"""
        SELECT 
            message_id,
            thread_id,
            subject,
            sender_name,
            sender_email,
            snippet,
            received_at,
            priority_level,
            category,
            requires_response,
            sentiment
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
            # Default: exclude closed tasks
            where_clauses.append("status != 'closed'")
        
        where_clause = " AND ".join(where_clauses)
        
        param_count += 1
        params.append(limit)
        
        query = f"""
        SELECT 
            clickup_task_id as task_id,
            task_name as name,
            task_description as description,
            status,
            priority,
            due_date,
            assignees,
            tags,
            list_name,
            space_name,
            created_at,
            updated_at
        FROM clickup_tasks
        WHERE {where_clause}
        ORDER BY priority DESC, due_date ASC NULLS LAST
        LIMIT ${param_count}
        """
        
        tasks = await db_manager.fetch_all(query, *params)
        logger.info(f"✅ Found {len(tasks)} active tasks")
        return tasks
        
    except Exception as e:
        logger.error(f"❌ Failed to query tasks: {e}")
        return []


# ============================================================================
# INTENT DETECTION
# ============================================================================

def detect_query_intent(message: str) -> Dict[str, Any]:
    """
    Analyze user message to determine what databases to query
    
    Returns dict with boolean flags for each query type:
    - query_meetings
    - query_emails
    - query_calendar
    - query_trends
    - query_knowledge
    - query_weather
    - query_tasks
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
    """Format email summary for AI context"""
    if not emails:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📧 RECENT EMAILS",
        "="*80,
        f"Found {len(emails)} emails:",
        ""
    ]
    
    important = [e for e in emails if e.get('priority_level') in ['high', 'urgent']]
    needs_response = [e for e in emails if e.get('requires_response')]
    
    if important:
        lines.append("🔴 HIGH PRIORITY:")
        for email in important[:5]:
            sender = email.get('sender_name') or email.get('sender_email', 'Unknown')
            subject = email.get('subject', 'No subject')[:50]
            lines.append(f"   • From: {sender}")
            lines.append(f"     Subject: {subject}")
    
    if needs_response:
        lines.append("\n⚡ NEEDS RESPONSE:")
        for email in needs_response[:5]:
            sender = email.get('sender_name') or email.get('sender_email', 'Unknown')
            subject = email.get('subject', 'No subject')[:50]
            lines.append(f"   • From: {sender}")
            lines.append(f"     Subject: {subject}")
    
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
        "📆 UPCOMING EVENTS",
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
        "✅ ACTIVE TASKS",
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
        
        # FULL: Load everything
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
            
            # Calendar
            calendar = await query_calendar(
                user_id=user_id,
                days_ahead=7,
                limit=CONTEXT_CONFIG['limits']['calendar_events']
            )
            if calendar:
                context_parts.append(format_calendar_context(calendar))
            
            # Emails
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
                calendar = await query_calendar(user_id=user_id, days_ahead=7, limit=20)
                if calendar:
                    context_parts.append(format_calendar_context(calendar))
            
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
