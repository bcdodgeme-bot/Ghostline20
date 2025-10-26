"""
SYNTAX PRIME V2 - MEMORY QUERY LAYER
Created: 2024-10-26

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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
import re

# Import database manager
from modules.core.database import db_manager

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

CONTEXT_CONFIG = {
    'hot_cache_days': 10,           # Always loaded (recent discussions)
    'warm_cache_days': 30,          # Loaded on new day/thread
    'cold_cache_days': 60,          # Query-based (everything in V2)
    'hours_gap_threshold': 8,       # Hours before comprehensive context
    
    'limits': {
        'hot_conversations': 100,    # Recent messages always available
        'warm_conversations': 300,   # Comprehensive context
        'cold_conversations': 50,    # Semantic search results
        'meetings': 14,              # From last 14 days
        'emails': 20,                # Unread/important
        'calendar_events': 30,       # Upcoming events
        'trends': 15,                # High-priority trends
        'knowledge_base': 10,        # Semantic search results
        'weather': 1,                # Current reading
        'tasks': 20                  # Active tasks
    }
}


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
    thread_id: str,
    days: int = 10,
    limit: int = 100,
    keywords: Optional[List[str]] = None,
    exclude_thread_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query conversation_messages across ALL threads
    
    This enables TRUE CROSS-THREAD MEMORY
    """
    try:
        where_clauses = ["cm.user_id = $1"]
        params = [user_id]
        param_count = 1
        
        # Time filter
        if days:
            where_clauses.append(f"cm.created_at >= NOW() - INTERVAL '{days} days'")
        
        # Exclude current thread (to avoid duplication)
        if exclude_thread_id:
            param_count += 1
            where_clauses.append(f"cm.thread_id != ${param_count}")
            params.append(exclude_thread_id)
        
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
        logger.info(f"💬 Found {len(messages)} conversation messages ({days}d, limit={limit})")
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
            summary,
            transcript_text,
            meeting_date,
            duration_minutes,
            participants,
            key_points,
            created_at
        FROM fathom_meetings
        WHERE meeting_date >= NOW() - INTERVAL '%s days'
        ORDER BY meeting_date DESC
        LIMIT $1
        """ % days
        
        meetings = await db_manager.fetch_all(query, limit)
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
        where_clauses = ["user_id = $1", f"received_at >= NOW() - INTERVAL '{days} days'"]
        params = [user_id]
        param_count = 1
        
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
        AND start_time <= NOW() + INTERVAL '%s days'
        ORDER BY start_time ASC
        LIMIT $2
        """ % days_ahead
        
        events = await db_manager.fetch_all(query, user_id, limit)
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
        logger.info(f"📊 Trends query disabled - table structure needs updating")
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
        params = [user_id]
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
        params = [user_id]
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
    
    Returns dict with boolean flags for each data source
    """
    message_lower = message.lower()
    
    intent = {
        'query_conversations': False,
        'query_meetings': False,
        'query_emails': False,
        'query_calendar': False,
        'query_trends': False,
        'query_knowledge': False,
        'query_weather': False,
        'query_tasks': False,
        'search_keywords': [],
        'is_casual_greeting': False,
        'needs_briefing': False
    }
    
    # Casual greetings (don't need briefing, just basic context)
    casual_patterns = [
        r'^(hey|hi|hello|sup|yo)[\s\?\!]*$',
        r'^(good morning|good afternoon|good evening)[\s\?\!]*$',
        r'^(what\'s up|whats up|wassup)[\s\?\!]*$'
    ]
    for pattern in casual_patterns:
        if re.match(pattern, message_lower):
            intent['is_casual_greeting'] = True
            return intent
    
    # Briefing requests (comprehensive context needed)
    briefing_keywords = [
        'briefing', 'brief me', 'update', 'what\'s new', 'catch me up',
        'what do i have', 'what\'s on my plate', 'priorities', 'focus'
    ]
    if any(kw in message_lower for kw in briefing_keywords):
        intent['needs_briefing'] = True
        intent['query_meetings'] = True
        intent['query_calendar'] = True
        intent['query_emails'] = True
        intent['query_tasks'] = True
        intent['query_trends'] = True
        intent['query_weather'] = True
        return intent
    
    # Conversation/memory queries
    memory_keywords = [
        'remember', 'discussed', 'talked about', 'mentioned', 'said',
        'conversation', 'chat', 'last time', 'previously', 'before'
    ]
    if any(kw in message_lower for kw in memory_keywords):
        intent['query_conversations'] = True
    
    # Meeting queries
    meeting_keywords = [
        'meeting', 'call', 'zoom', 'standup', 'sync', 'discussed in'
    ]
    if any(kw in message_lower for kw in meeting_keywords):
        intent['query_meetings'] = True
    
    # Email queries
    email_keywords = [
        'email', 'inbox', 'message', 'reply', 'responded', 'sent'
    ]
    if any(kw in message_lower for kw in email_keywords):
        intent['query_emails'] = True
    
    # Calendar queries
    calendar_keywords = [
        'calendar', 'schedule', 'meeting', 'appointment', 'event',
        'today', 'tomorrow', 'this week', 'next week', 'free', 'available'
    ]
    if any(kw in message_lower for kw in calendar_keywords):
        intent['query_calendar'] = True
    
    # Trends/intelligence queries
    trends_keywords = [
        'trend', 'trending', 'popular', 'spike', 'growth', 'traffic',
        'keyword', 'search volume', 'analytics'
    ]
    if any(kw in message_lower for kw in trends_keywords):
        intent['query_trends'] = True
    
    # Knowledge base queries (recipes, saved info, etc.)
    knowledge_keywords = [
        'recipe', 'cook', 'food', 'saved', 'remember saving', 'that article',
        'that post', 'that note', 'information about'
    ]
    if any(kw in message_lower for kw in knowledge_keywords):
        intent['query_knowledge'] = True
        # Extract search keywords
        intent['search_keywords'] = extract_keywords(message)
    
    # Weather queries
    weather_keywords = [
        'weather', 'temperature', 'rain', 'headache', 'uv', 'forecast'
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
        start = meeting['meeting_date'].strftime('%Y-%m-%d %H:%M')
        title = meeting.get('title') or 'Untitled Meeting'
        duration = meeting.get('duration_minutes') or 0
        
        lines.append(f"\n📌 {title}")
        lines.append(f"   Time: {start} ({duration} min)")
        
        if meeting.get('participants'):
            # participants is JSONB array
            parts = meeting['participants']
            if isinstance(parts, list):
                parts_str = ', '.join(parts[:3])  # First 3 participants
                lines.append(f"   Participants: {parts_str}")
        
        if meeting.get('summary'):
            summary = meeting['summary'][:200] + "..." if len(meeting['summary']) > 200 else meeting['summary']
            lines.append(f"   Summary: {summary}")
        
        if meeting.get('key_points'):
            # key_points is JSONB array
            key_points = meeting['key_points']
            if isinstance(key_points, list) and key_points:
                lines.append(f"   Key Points:")
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
    requires_response = [e for e in emails if e.get('requires_response', False)]
    
    if important:
        lines.append(f"⭐ {len(important)} high/urgent priority emails")
    if requires_response:
        lines.append(f"✉️  {len(requires_response)} emails requiring response")
    lines.append("")
    
    for email in emails[:10]:  # Show first 10
        received = email['received_at'].strftime('%Y-%m-%d %H:%M')
        subject = email.get('subject') or '(No Subject)'
        sender = email.get('sender_name') or email.get('sender_email', 'Unknown')
        
        status = "📬"
        if email.get('priority_level') in ['high', 'urgent']:
            status += " ⭐"
        if email.get('requires_response'):
            status += " ✉️"
        
        lines.append(f"{status} From: {sender}")
        lines.append(f"    Subject: {subject}")
        lines.append(f"    Time: {received}")
        
        if email.get('snippet'):
            snippet = email['snippet'][:150] + "..." if len(email['snippet']) > 150 else email['snippet']
            lines.append(f"    Preview: {snippet}")
        
        if email.get('category'):
            lines.append(f"    Category: {email['category']}")
        
        lines.append("")
    
    lines.extend([
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
        "📆 UPCOMING CALENDAR",
        "="*80,
        f"Found {len(events)} upcoming events:",
        ""
    ]
    
    # Group by day
    by_day = {}
    for event in events:
        day = event['start_time'].strftime('%Y-%m-%d')
        if day not in by_day:
            by_day[day] = []
        by_day[day].append(event)
    
    for day, day_events in sorted(by_day.items())[:7]:  # Next 7 days
        day_name = datetime.strptime(day, '%Y-%m-%d').strftime('%A, %B %d')
        lines.append(f"\n📅 {day_name}:")
        
        for event in sorted(day_events, key=lambda e: e['start_time']):
            start = event['start_time'].strftime('%H:%M')
            end = event['end_time'].strftime('%H:%M') if event.get('end_time') else '?'
            summary = event.get('summary') or 'Untitled Event'
            
            lines.append(f"   {start}-{end}: {summary}")
            
            if event.get('location'):
                lines.append(f"      📍 {event['location']}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_trends_context(trends: List[Dict]) -> str:
    """Format Google Trends data for AI context"""
    if not trends:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📊 TRENDING KEYWORDS",
        "="*80,
        f"Found {len(trends)} high-priority trends:",
        ""
    ]
    
    for trend in trends:
        keyword = trend['keyword']
        business = trend.get('business_area', 'Unknown')
        direction = trend.get('trend_direction', 'stable')
        change = trend.get('change_percentage', 0)
        priority = trend.get('priority', 0)
        
        arrow = "📈" if direction == 'up' else "📉" if direction == 'down' else "➡️"
        
        lines.append(f"{arrow} {keyword} ({business})")
        lines.append(f"   Priority: {priority}/10 | Change: {change:+.1f}%")
        
        if trend.get('notes'):
            notes = trend['notes'][:150] + "..." if len(trend['notes']) > 150 else trend['notes']
            lines.append(f"   Notes: {notes}")
        lines.append("")
    
    lines.extend([
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_knowledge_context(items: List[Dict]) -> str:
    """Format knowledge base items for AI context"""
    if not items:
        return ""
    
    lines = [
        "\n" + "="*80,
        "📚 KNOWLEDGE BASE (Reference Library)",
        "="*80,
        f"Found {len(items)} relevant saved items:",
        ""
    ]
    
    for item in items:
        title = item.get('title') or 'Untitled'
        content_type = item.get('content_type') or 'unknown'
        
        lines.append(f"📄 {title} ({content_type})")
        
        if item.get('key_topics'):
            topics = item['key_topics']
            if isinstance(topics, list) and topics:
                lines.append(f"   Topics: {', '.join(topics[:5])}")
        
        if item.get('content'):
            content = item['content'][:200] + "..." if len(item['content']) > 200 else item['content']
            lines.append(f"   {content}")
        
        if item.get('word_count'):
            lines.append(f"   Words: {item['word_count']}")
        
        lines.append("")
    
    lines.extend([
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_weather_context(weather: Optional[Dict]) -> str:
    """Format weather data for AI context"""
    if not weather:
        return ""
    
    lines = [
        "\n" + "="*80,
        "⛅ CURRENT WEATHER",
        "="*80,
        ""
    ]
    
    temp = weather.get('temperature')
    feels = weather.get('temperature_apparent')
    desc = weather.get('weather_description', 'Unknown')
    precip = weather.get('precipitation_probability', 0)
    
    lines.append(f"🌡️  Temperature: {temp}°F (feels like {feels}°F)")
    lines.append(f"☁️  Conditions: {desc}")
    lines.append(f"🌧️  Precipitation: {precip}%")
    
    if weather.get('headache_risk_level'):
        risk = weather['headache_risk_level']
        score = weather.get('headache_risk_score', 0)
        lines.append(f"🤕 Headache Risk: {risk.upper()} ({score}/100)")
        
        if weather.get('headache_risk_factors'):
            factors = weather['headache_risk_factors']
            # Handle JSONB or dict format
            if isinstance(factors, dict):
                factors_str = ', '.join([f'{k}: {v}' for k, v in list(factors.items())[:3]])
                lines.append(f"   Factors: {factors_str}")
            elif isinstance(factors, str):
                lines.append(f"   Factors: {factors}")
    
    if weather.get('uv_index'):
        uv = weather['uv_index']
        uv_risk = weather.get('uv_risk_level', 'unknown')
        lines.append(f"☀️  UV Index: {uv} ({uv_risk})")
    
    if weather.get('severe_weather_alert'):
        alert = weather.get('alert_description', 'Weather alert active')
        lines.append(f"⚠️  ALERT: {alert}")
    
    lines.extend([
        "",
        "="*80,
        ""
    ])
    
    return "\n".join(lines)


def format_tasks_context(tasks: List[Dict]) -> str:
    """Format ClickUp tasks for AI context"""
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
    by_priority = {}
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
        conversations = await query_conversations(
            user_id=user_id,
            days=CONTEXT_CONFIG['hot_cache_days'],
            limit=CONTEXT_CONFIG['limits']['hot_conversations'],
            exclude_thread_id=thread_id
        )
        if conversations:
            context_parts.append(format_conversations_context(conversations))
        
        # COMPREHENSIVE/FULL: Load additional conversation history
        if context_level in ['comprehensive', 'full']:
            older_conversations = await query_conversations(
                user_id=user_id,
                days=CONTEXT_CONFIG['warm_cache_days'],
                limit=CONTEXT_CONFIG['limits']['warm_conversations'],
                exclude_thread_id=thread_id
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
