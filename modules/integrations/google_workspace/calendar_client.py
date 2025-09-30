# modules/integrations/google_workspace/calendar_client.py
"""
Google Calendar Client - 11-Feed Calendar Intelligence
Analytics-Powered Scheduling & Meeting Preparation

This module:
1. Integrates all 11 calendar feeds into unified view
2. Provides meeting preparation with Analytics/Search Console insights
3. Optimizes content scheduling based on traffic patterns
4. Identifies optimal posting windows around meetings
5. Generates preparation suggestions for calendar events
6. Correlates calendar events with business intelligence

11-Feed Integration:
- Google Calendar (primary)
- Work calendar
- Project calendars
- Shared calendars
- Subscription calendars
- All accessible calendars via Google Calendar API

Intelligence Features:
- "Meeting at 2pm about bcdodge site? Here are this week's top keywords"
- "Free block Tuesday 10am-12pm - optimal time for content posting"
- "Client call in 1 hour - here are relevant Analytics insights"
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import asyncio

logger = logging.getLogger(__name__)

# Import after logger setup
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False
    logger.warning("⚠️ Google Calendar API client not installed")

from .oauth_manager import get_google_credentials, GoogleTokenExpiredError
from .analytics_client import analytics_client
from .search_console_client import search_console_client
from .database_manager import google_workspace_db
from ...core.database import db_manager

class CalendarClient:
    """
    Google Calendar API client with 11-feed integration
    Analytics-powered scheduling intelligence
    """
    
    def __init__(self):
        """Initialize Calendar client"""
        if not CALENDAR_AVAILABLE:
            logger.error("❌ Calendar API client not available")
            raise RuntimeError("Calendar API client required - run: pip install google-api-python-client")
        
        self._service = None
        self._user_id = None
        self._calendars_cache = []
        
        logger.info("📅 Calendar client initialized")
    
    async def initialize(self, user_id: str):
        """
        Initialize Calendar service with credentials
        
        Args:
            user_id: User ID for credential lookup
        """
        try:
            self._user_id = user_id
            
            # Get credentials from auth manager
            credentials = await get_google_credentials(user_id, email=None)
            
            if not credentials:
                raise Exception("No valid credentials available")
            
            # Build Calendar service
            self._service = build('calendar', 'v3', credentials=credentials)
            
            logger.info("✅ Calendar service initialized")
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Calendar initialization failed: {e}")
            raise
    
    async def get_calendar_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all accessible calendars (the 11 feeds!)
        
        Returns:
            List of calendar dictionaries with metadata
        """
        try:
            if not self._service:
                raise Exception("Calendar service not initialized")
            
            logger.info("📅 Fetching calendar list...")
            
            # Get calendar list
            calendar_list = self._service.calendarList().list().execute()
            
            calendars = []
            for calendar in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar['id'],
                    'summary': calendar.get('summary', 'Unnamed Calendar'),
                    'description': calendar.get('description', ''),
                    'primary': calendar.get('primary', False),
                    'access_role': calendar.get('accessRole', 'reader'),
                    'background_color': calendar.get('backgroundColor', '#ffffff'),
                    'selected': calendar.get('selected', True)
                })
            
            self._calendars_cache = calendars
            
            logger.info(f"✅ Found {len(calendars)} calendar feeds")
            
            return calendars
            
        except HttpError as e:
            logger.error(f"❌ Calendar API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Failed to get calendar list: {e}")
            return []
    
    async def get_events(self, time_min: Optional[datetime] = None,
                        time_max: Optional[datetime] = None,
                        calendar_id: str = 'primary',
                        max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get calendar events for a specific calendar
        
        Args:
            time_min: Start time (default: now)
            time_max: End time (default: 7 days from now)
            calendar_id: Calendar ID or 'primary'
            max_results: Maximum number of events
            
        Returns:
            List of calendar events
        """
        try:
            if not self._service:
                raise Exception("Calendar service not initialized")
            
            # Set default time range
            if time_min is None:
                time_min = datetime.now(timezone.utc)
            if time_max is None:
                time_max = time_min + timedelta(days=7)
            
            # Format times for API
            time_min_str = time_min.isoformat()
            time_max_str = time_max.isoformat()
            
            logger.info(f"📅 Fetching events from {calendar_id}...")
            
            # Get events
            events_result = self._service.events().list(
                calendarId=calendar_id,
                timeMin=time_min_str,
                timeMax=time_max_str,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            logger.info(f"✅ Found {len(events)} events in {calendar_id}")
            
            return events
            
        except HttpError as e:
            logger.error(f"❌ Calendar API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Failed to get events: {e}")
            return []
    
    async def get_all_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get events from ALL accessible calendars (11-feed integration!)
        
        Args:
            days: Number of days to look ahead
            
        Returns:
            List of all events across all calendars
        """
        try:
            # Get calendar list if not cached
            if not self._calendars_cache:
                await self.get_calendar_list()
            
            time_min = datetime.now(timezone.utc)
            time_max = time_min + timedelta(days=days)
            
            all_events = []
            
            # Fetch events from each calendar
            for calendar in self._calendars_cache:
                if calendar.get('selected', True):  # Only selected calendars
                    events = await self.get_events(
                        time_min=time_min,
                        time_max=time_max,
                        calendar_id=calendar['id']
                    )
                    
                    # Add calendar info to each event
                    for event in events:
                        event['calendar_name'] = calendar['summary']
                        event['calendar_id'] = calendar['id']
                        all_events.append(event)
            
            # Sort by start time
            all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
            
            logger.info(f"✅ Retrieved {len(all_events)} events from {len(self._calendars_cache)} calendars")
            
            return all_events
            
        except Exception as e:
            logger.error(f"❌ Failed to get all events: {e}")
            return []
    
    async def get_today_events(self) -> List[Dict[str, Any]]:
        """Get today's events across all calendars"""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        return await self.get_all_events_in_range(start_of_day, end_of_day)
    
    async def get_week_events(self) -> List[Dict[str, Any]]:
        """Get this week's events across all calendars"""
        return await self.get_all_events(days=7)
    
    async def get_all_events_in_range(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """Get all events in a specific time range"""
        if not self._calendars_cache:
            await self.get_calendar_list()
        
        all_events = []
        
        for calendar in self._calendars_cache:
            if calendar.get('selected', True):
                events = await self.get_events(
                    time_min=start,
                    time_max=end,
                    calendar_id=calendar['id']
                )
                
                for event in events:
                    event['calendar_name'] = calendar['summary']
                    event['calendar_id'] = calendar['id']
                    all_events.append(event)
        
        all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
        
        return all_events
    
    async def prepare_meeting_insights(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate meeting preparation insights using Analytics & Search Console
        
        Args:
            event: Calendar event dictionary
            
        Returns:
            Dict with preparation insights
        """
        try:
            insights = {
                'event_title': event.get('summary', 'Meeting'),
                'event_start': event.get('start', {}).get('dateTime', ''),
                'suggestions': [],
                'analytics_insights': {},
                'keyword_insights': {}
            }
            
            # Extract topic from event title/description
            event_text = f"{event.get('summary', '')} {event.get('description', '')}".lower()
            
            # Try to identify which site this meeting is about
            site_mentioned = None
            for site_name, site_config in __import__('modules.integrations.google_workspace', fromlist=['SUPPORTED_SITES']).SUPPORTED_SITES.items():
                if site_name in event_text or any(alias in event_text for alias in site_config.get('aliases', [])):
                    site_mentioned = site_name
                    break
            
            if site_mentioned:
                insights['suggestions'].append(f"Meeting appears to be about {site_mentioned} site")
                
                # Get Analytics summary
                try:
                    analytics_summary = await google_workspace_db.get_analytics_summary(
                        self._user_id, 
                        site_mentioned, 
                        days=7
                    )
                    
                    if analytics_summary:
                        metrics = analytics_summary.get('metrics', {})
                        insights['analytics_insights'] = {
                            'sessions': metrics.get('sessions', 0),
                            'users': metrics.get('users', 0),
                            'bounce_rate': metrics.get('bounce_rate', 0)
                        }
                        insights['suggestions'].append(
                            f"📊 Last 7 days: {metrics.get('sessions', 0):,} sessions, {metrics.get('users', 0):,} users"
                        )
                except Exception as e:
                    logger.warning(f"Could not fetch Analytics for {site_mentioned}: {e}")
                
                # Get top keywords
                try:
                    top_keywords = await google_workspace_db.get_top_keywords(
                        self._user_id,
                        site_mentioned,
                        limit=5
                    )
                    
                    if top_keywords:
                        insights['keyword_insights'] = {
                            'top_keywords': [kw['keyword'] for kw in top_keywords[:3]]
                        }
                        top_3 = ', '.join([f"'{kw['keyword']}'" for kw in top_keywords[:3]])
                        insights['suggestions'].append(f"🎯 Top keywords: {top_3}")
                except Exception as e:
                    logger.warning(f"Could not fetch keywords for {site_mentioned}: {e}")
            else:
                insights['suggestions'].append("General meeting - no specific site identified")
            
            return insights
            
        except Exception as e:
            logger.error(f"❌ Failed to prepare meeting insights: {e}")
            return {'suggestions': ['Could not generate insights']}
    
    async def find_optimal_content_windows(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Find optimal time windows for content work based on calendar and Analytics
        
        Args:
            days: Number of days to analyze
            
        Returns:
            List of optimal time windows
        """
        try:
            # Get all events for the period
            events = await self.get_all_events(days=days)
            
            # Find free blocks (simplified - would be more sophisticated in production)
            now = datetime.now(timezone.utc)
            optimal_windows = []
            
            # Check each day
            for day_offset in range(days):
                check_date = now + timedelta(days=day_offset)
                
                # Define working hours (9am - 5pm)
                work_start = check_date.replace(hour=9, minute=0, second=0)
                work_end = check_date.replace(hour=17, minute=0, second=0)
                
                # Get events for this day
                day_events = [e for e in events if self._event_on_date(e, check_date)]
                
                # If no events, entire day is free
                if not day_events:
                    optimal_windows.append({
                        'date': check_date.date().isoformat(),
                        'start_time': work_start.time().isoformat(),
                        'end_time': work_end.time().isoformat(),
                        'duration_hours': 8,
                        'reason': 'Full day available for content work'
                    })
            
            logger.info(f"✅ Found {len(optimal_windows)} optimal content windows")
            
            return optimal_windows
            
        except Exception as e:
            logger.error(f"❌ Failed to find optimal windows: {e}")
            return []
    
    def _event_on_date(self, event: Dict[str, Any], check_date: datetime) -> bool:
        """Check if event occurs on a specific date"""
        start = event.get('start', {})
        event_date_str = start.get('dateTime', start.get('date', ''))
        
        if not event_date_str:
            return False
        
        try:
            if 'T' in event_date_str:  # DateTime
                event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
            else:  # Date only
                event_date = datetime.fromisoformat(event_date_str)
            
            return event_date.date() == check_date.date()
        except:
            return False
    
    async def store_calendar_intelligence(self, event: Dict[str, Any], insights: Dict[str, Any]):
        """
        Store calendar event with intelligence insights
        
        Args:
            event: Calendar event
            insights: Generated insights
        """
        try:
            calendar_source = event.get('calendar_name', 'unknown')
            event_id = event.get('id', '')
            event_title = event.get('summary', '')
            
            # Parse start/end times
            start = event.get('start', {})
            end = event.get('end', {})
            
            event_start = start.get('dateTime', start.get('date'))
            event_end = end.get('dateTime', end.get('date'))
            is_all_day = 'date' in start and 'dateTime' not in start
            
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO google_calendar_intelligence
                    (user_id, calendar_source, event_id, event_title, 
                     event_start, event_end, is_all_day, 
                     optimal_content_timing, preparation_suggestions, related_analytics_insights)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (user_id, calendar_source, event_id) DO UPDATE SET
                        event_title = EXCLUDED.event_title,
                        event_start = EXCLUDED.event_start,
                        event_end = EXCLUDED.event_end,
                        optimal_content_timing = EXCLUDED.optimal_content_timing,
                        preparation_suggestions = EXCLUDED.preparation_suggestions,
                        related_analytics_insights = EXCLUDED.related_analytics_insights
                ''',
                self._user_id,
                calendar_source,
                event_id,
                event_title,
                event_start,
                event_end,
                is_all_day,
                insights.get('optimal_windows', []),
                insights.get('suggestions', []),
                str(insights.get('analytics_insights', {}))
                )
            
            logger.info(f"✅ Stored calendar intelligence for {event_title}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store calendar intelligence: {e}")

# Global instance
calendar_client = CalendarClient()

# Convenience functions for other modules
async def get_today_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get today's events across all calendars"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_today_events()

async def get_week_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get this week's events across all calendars"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_week_events()

async def get_calendar_feeds(user_id: str) -> List[Dict[str, Any]]:
    """Get list of all calendar feeds (the 11 feeds!)"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_calendar_list()

async def prepare_for_meeting(user_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """Get meeting preparation insights"""
    await calendar_client.initialize(user_id)
    return await calendar_client.prepare_meeting_insights(event)

async def find_content_windows(user_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Find optimal time windows for content work"""
    await calendar_client.initialize(user_id)
    return await calendar_client.find_optimal_content_windows(days)