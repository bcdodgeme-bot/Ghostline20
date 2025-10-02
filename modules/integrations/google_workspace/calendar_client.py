# modules/integrations/google_workspace/calendar_client.py
"""
Google Calendar Client - REFACTORED FOR AIOGOOGLE
11-Feed Calendar Intelligence with Analytics-Powered Scheduling
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

try:
    from aiogoogle import Aiogoogle
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False
    logger.warning("⚠️ aiogoogle not installed")

from .oauth_manager import get_aiogoogle_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class CalendarClient:
    """Calendar client with TRUE async support"""
    
    def __init__(self):
        if not CALENDAR_AVAILABLE:
            raise RuntimeError("aiogoogle required")
        
        self._user_id = None
        self._user_creds = None
        self._calendars_cache = []
        logger.info("📅 Calendar client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str):
        """Initialize with credentials"""
        try:
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                raise Exception("No valid credentials")
            
            logger.info("✅ Calendar initialized")
            
        except Exception as e:
            logger.error(f"❌ Calendar init failed: {e}")
            raise
    
    async def get_calendar_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all accessible calendars - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            logger.info("📅 Fetching calendar list...")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                calendar_v3 = await aiogoogle.discover('calendar', 'v3')
                
                calendar_list = await aiogoogle.as_user(
                    calendar_v3.calendarList.list()
                )
                
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
                
        except Exception as e:
            logger.error(f"❌ Failed to get calendar list: {e}")
            raise
    
    async def get_events(self, time_min: Optional[datetime] = None,
                        time_max: Optional[datetime] = None,
                        calendar_id: str = 'primary',
                        max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get calendar events - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            # Set default time range
            if time_min is None:
                time_min = datetime.now(timezone.utc)
            if time_max is None:
                time_max = time_min + timedelta(days=7)
            
            logger.info(f"📅 Fetching events from {calendar_id}...")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                calendar_v3 = await aiogoogle.discover('calendar', 'v3')
                
                events_result = await aiogoogle.as_user(
                    calendar_v3.events.list(
                        calendarId=calendar_id,
                        timeMin=time_min.isoformat(),
                        timeMax=time_max.isoformat(),
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy='startTime'
                    )
                )
                
                events = []
                for event in events_result.get('items', []):
                    events.append({
                        'id': event['id'],
                        'summary': event.get('summary', '(No title)'),
                        'description': event.get('description', ''),
                        'start': event.get('start', {}),
                        'end': event.get('end', {}),
                        'location': event.get('location', ''),
                        'attendees': event.get('attendees', []),
                        'creator': event.get('creator', {}),
                        'organizer': event.get('organizer', {})
                    })
                
                logger.info(f"✅ Retrieved {len(events)} events")
                
                return events
                
        except Exception as e:
            logger.error(f"❌ Failed to get events: {e}")
            raise
    
    async def get_all_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get events from ALL calendars
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
                if calendar.get('selected', True):
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
        
        if not self._calendars_cache:
            await self.get_calendar_list()
        
        all_events = []
        
        for calendar in self._calendars_cache:
            if calendar.get('selected', True):
                events = await self.get_events(
                    time_min=start_of_day,
                    time_max=end_of_day,
                    calendar_id=calendar['id']
                )
                
                for event in events:
                    event['calendar_name'] = calendar['summary']
                    event['calendar_id'] = calendar['id']
                    all_events.append(event)
        
        all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
        
        return all_events
    
    async def get_week_events(self) -> List[Dict[str, Any]]:
        """Get this week's events across all calendars"""
        return await self.get_all_events(days=7)

# Global instance
calendar_client = CalendarClient()

# Convenience functions
async def get_today_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get today's events across all calendars"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_today_events()

async def get_week_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get this week's events across all calendars"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_week_events()

async def get_calendar_feeds(user_id: str) -> List[Dict[str, Any]]:
    """Get list of all calendar feeds"""
    await calendar_client.initialize(user_id)
    return await calendar_client.get_calendar_list()
