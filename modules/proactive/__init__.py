# modules/proactive/__init__.py
"""
Proactive Module - AI-Generated Content Before You See It

This module provides the unified proactive engine that handles:
- Email: AI drafts replies before you see the notification
- Meeting: Full summaries with action items ready to paste/create tasks
- Trends: Blog outlines + Bluesky posts with RSS context
- Calendar: Meeting prep notes
- ClickUp: Task summaries

The core principle: AI generates content BEFORE the notification arrives.
User sees draft + one-tap action buttons.

Usage:
    from modules.proactive import get_unified_engine
    
    engine = get_unified_engine()
    await engine.process_email(email_data)
    await engine.process_meeting(meeting_data, summary_data)
    await engine.process_trend(trend_data)
"""

from .unified_engine import (
    get_unified_engine,
    UnifiedProactiveEngine,
    SourceType,
    ContentType,
    ProactiveItem,
    process_email_proactively,
    process_meeting_proactively,
    process_trend_proactively,
)

__all__ = [
    'get_unified_engine',
    'UnifiedProactiveEngine',
    'SourceType',
    'ContentType',
    'ProactiveItem',
    'process_email_proactively',
    'process_meeting_proactively',
    'process_trend_proactively',
]
