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
        self._client_creds = None  # ADD THIS LINE
        self._calendars_cache = []
        logger.info("📅 Calendar client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str):
        """Initialize with credentials"""
        try:
            logger.debug(f"🔧 Calendar.initialize() called with user_id={user_id}")
            self._user_id = user_id
            
            # Get BOTH user creds and client creds
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                logger.error(f"❌ No credentials found for user_id={user_id}")
                raise Exception("No valid credentials")
            
            # CRITICAL FIX: Load client credentials
            from .oauth_manager import google_auth_manager
            self._client_creds = {
                'client_id': google_auth_manager.client_id,
                'client_secret': google_auth_manager.client_secret
            }
            
            if not self._client_creds:
                logger.error(f"❌ No client credentials available")
                raise Exception("No OAuth app credentials configured")
            
            logger.info(f"✅ Calendar initialized for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Calendar init failed: {e}", exc_info=True)
            raise
    
    async def get_calendar_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all accessible calendars - TRULY ASYNC
        """
        try:
            logger.debug(f"📅 get_calendar_list() called")
            
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing...")
                await self.initialize(self._user_id)
            
            logger.info("📅 Fetching calendar list from Google API...")
            
            async with Aiogoogle(user_creds=self._user_creds, client_creds=self._client_creds) as aiogoogle:
                calendar_v3 = await aiogoogle.discover('calendar', 'v3')
                
                logger.debug(f"🔍 Calling Calendar API: calendarList.list")
                
                calendar_list = await aiogoogle.as_user(
                    calendar_v3.calendarList.list()
                )
                
                logger.debug(f"📦 Calendar API response received")
                
                calendars = []
                for idx, calendar in enumerate(calendar_list.get('items', [])):
                    calendar_data = {
                        'id': calendar['id'],
                        'summary': calendar.get('summary', 'Unnamed Calendar'),
                        'description': calendar.get('description', ''),
                        'primary': calendar.get('primary', False),
                        'access_role': calendar.get('accessRole', 'reader'),
                        'background_color': calendar.get('backgroundColor', '#ffffff'),
                        'selected': calendar.get('selected', True)
                    }
                    calendars.append(calendar_data)
                    
                    logger.debug(f"  📅 Calendar {idx+1}: {calendar_data['summary']} "
                               f"(primary={calendar_data['primary']}, selected={calendar_data['selected']})")
                
                self._calendars_cache = calendars
                
                logger.info(f"✅ Found {len(calendars)} calendar feeds")
                
                return calendars
                
        except Exception as e:
            logger.error(f"❌ Failed to get calendar list: {e}", exc_info=True)
            raise
    
    async def get_events(self, time_min: Optional[datetime] = None,
                        time_max: Optional[datetime] = None,
                        calendar_id: str = 'primary',
                        max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Get calendar events - TRULY ASYNC
        """
        try:
            logger.debug(f"📅 get_events() called: calendar_id={calendar_id}, max_results={max_results}")
            
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing...")
                await self.initialize(self._user_id)
            
            # Set default time range
            if time_min is None:
                time_min = datetime.now(timezone.utc)
            if time_max is None:
                time_max = time_min + timedelta(days=7)
            
            logger.info(f"📅 Fetching events from {calendar_id}: {time_min.date()} to {time_max.date()}")
            
            async with Aiogoogle(user_creds=self._user_creds, client_creds=self._client_creds) as aiogoogle:
                calendar_v3 = await aiogoogle.discover('calendar', 'v3')
                
                logger.debug(f"🔍 Calling Calendar API: events.list")
                
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
                
                logger.debug(f"📦 Events API response received")
                
                events = []
                for idx, event in enumerate(events_result.get('items', [])):
                    event_data = {
                        'id': event['id'],
                        'summary': event.get('summary', '(No title)'),
                        'description': event.get('description', ''),
                        'start': event.get('start', {}),
                        'end': event.get('end', {}),
                        'location': event.get('location', ''),
                        'attendees': event.get('attendees', []),
                        'creator': event.get('creator', {}),
                        'organizer': event.get('organizer', {})
                    }
                    events.append(event_data)
                    
                    # Store event in database
                    await self._store_event_data(calendar_id, event_data)
                    
                    # Log first few events
                    if idx < 3:
                        start_time = event_data['start'].get('dateTime', event_data['start'].get('date', 'Unknown'))
                        logger.debug(f"  📅 Event {idx+1}: {event_data['summary']} at {start_time}")
                
                logger.info(f"✅ Retrieved and stored {len(events)} events from {calendar_id}")
                
                return events
                
        except Exception as e:
            logger.error(f"❌ Failed to get events from {calendar_id}: {e}", exc_info=True)
            raise
    
    async def _store_event_data(self, calendar_id: str, event: Dict[str, Any]):
        """Store calendar event in database"""
        try:
            # Parse event times
            start = event['start']
            end = event['end']
            
            # Handle both datetime and date-only events
            if 'dateTime' in start:
                start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
                all_day = False
            else:
                start_time = datetime.fromisoformat(start['date'])
                end_time = datetime.fromisoformat(end['date'])
                all_day = True
            
            # FIX: Use db_manager.execute() instead of get_connection()
            await db_manager.execute('''
                INSERT INTO google_calendar_events
                (user_id, calendar_id, event_id, summary, description, location,
                 start_time, end_time, all_day, attendees_count, creator_email, fetched_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                ON CONFLICT (user_id, event_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    description = EXCLUDED.description,
                    location = EXCLUDED.location,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    attendees_count = EXCLUDED.attendees_count,
                    fetched_at = NOW()
            ''',
                self._user_id,
                calendar_id,
                event['id'],
                event.get('summary', ''),
                event.get('description', ''),
                event.get('location', ''),
                start_time,
                end_time,
                all_day,
                len(event.get('attendees', [])),
                event.get('creator', {}).get('email', '')
            )
            
            logger.debug(f"💾 Stored event: {event.get('summary', 'Untitled')}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store event data: {e}", exc_info=True)
            # Don't raise - storing is optional
    
    async def get_all_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get events from ALL calendars - WITH AUTO-FETCH
        """
        try:
            logger.info(f"📅 Getting all events for next {days} days")
            
            # Get calendar list if not cached
            if not self._calendars_cache:
                logger.debug(f"📅 No calendars cached, fetching calendar list...")
                await self.get_calendar_list()
            
            time_min = datetime.now(timezone.utc)
            time_max = time_min + timedelta(days=days)
            
            logger.debug(f"📅 Fetching events from {len(self._calendars_cache)} calendars")
            
            all_events = []
            
            # Fetch events from each calendar
            for idx, calendar in enumerate(self._calendars_cache):
                if calendar.get('selected', True):
                    logger.debug(f"📅 Fetching from calendar {idx+1}/{len(self._calendars_cache)}: {calendar['summary']}")
                    
                    try:
                        events = await self.get_events(
                            time_min=time_min,
                            time_max=time_max,
                            calendar_id=calendar['id']
                        )
                        
                        # Add calendar info to each event
                        for event in events:
                            event['calendar_name'] = calendar['summary']
                            event['calendar_id'] = calendar['id']
                            event['calendar_color'] = calendar['background_color']
                            all_events.append(event)
                        
                        logger.debug(f"  ✅ Got {len(events)} events from {calendar['summary']}")
                        
                    except Exception as cal_error:
                        logger.error(f"  ⚠️ Failed to get events from {calendar['summary']}: {cal_error}")
                        # Continue with other calendars
                        continue
            
            # Sort by start time
            all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
            
            logger.info(f"✅ Retrieved {len(all_events)} total events from {len(self._calendars_cache)} calendars")
            
            return all_events
            
        except Exception as e:
            logger.error(f"❌ Failed to get all events: {e}", exc_info=True)
            return []
    
    async def get_today_events(self) -> List[Dict[str, Any]]:
        """Get today's events across all calendars"""
        logger.info(f"📅 Getting today's events")
        
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        if not self._calendars_cache:
            logger.debug(f"📅 No calendars cached, fetching calendar list...")
            await self.get_calendar_list()
        
        all_events = []
        
        for calendar in self._calendars_cache:
            if calendar.get('selected', True):
                try:
                    events = await self.get_events(
                        time_min=start_of_day,
                        time_max=end_of_day,
                        calendar_id=calendar['id']
                    )
                    
                    for event in events:
                        event['calendar_name'] = calendar['summary']
                        event['calendar_id'] = calendar['id']
                        event['calendar_color'] = calendar['background_color']
                        all_events.append(event)
                        
                except Exception as cal_error:
                    logger.error(f"⚠️ Failed to get today's events from {calendar['summary']}: {cal_error}")
                    continue
        
        all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
        
        logger.info(f"✅ Found {len(all_events)} events today")
        return all_events
    
    async def get_week_events(self) -> List[Dict[str, Any]]:
        """Get this week's events across all calendars"""
        logger.info(f"📅 Getting this week's events")
        return await self.get_all_events(days=7)
    
    async def get_week_summary(self) -> Dict[str, Any]:
        """
        Get weekly calendar summary with analytics
        """
        try:
            logger.info(f"📊 Getting weekly calendar summary")
            
            events = await self.get_week_events()
            
            # Calculate statistics
            total_events = len(events)
            meetings = sum(1 for e in events if len(e.get('attendees', [])) > 0)
            all_day = sum(1 for e in events if 'date' in e.get('start', {}))
            
            # Group by day
            events_by_day = {}
            for event in events:
                start = event.get('start', {})
                date_str = start.get('dateTime', start.get('date', ''))[:10]
                
                if date_str not in events_by_day:
                    events_by_day[date_str] = []
                events_by_day[date_str].append(event)
            
            summary = {
                'total_events': total_events,
                'meetings': meetings,
                'all_day_events': all_day,
                'personal_events': total_events - meetings,
                'busiest_day': max(events_by_day.items(), key=lambda x: len(x[1]))[0] if events_by_day else None,
                'events_by_day': {day: len(evts) for day, evts in events_by_day.items()}
            }
            
            logger.info(f"✅ Weekly summary: {total_events} events, {meetings} meetings")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Failed to get week summary: {e}", exc_info=True)
            raise

# Global instance
calendar_client = CalendarClient()

# Convenience functions
async def get_today_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get today's events across all calendars"""
    logger.debug(f"🔧 get_today_schedule() called: user_id={user_id}")
    await calendar_client.initialize(user_id)
    return await calendar_client.get_today_events()

async def get_week_schedule(user_id: str) -> List[Dict[str, Any]]:
    """Get this week's events across all calendars"""
    logger.debug(f"🔧 get_week_schedule() called: user_id={user_id}")
    await calendar_client.initialize(user_id)
    return await calendar_client.get_week_events()

async def get_calendar_feeds(user_id: str) -> List[Dict[str, Any]]:
    """Get list of all calendar feeds"""
    logger.debug(f"🔧 get_calendar_feeds() called: user_id={user_id}")
    await calendar_client.initialize(user_id)
    return await calendar_client.get_calendar_list()

async def get_week_overview(user_id: str) -> Dict[str, Any]:
    """Get weekly calendar overview with analytics"""
    logger.debug(f"🔧 get_week_overview() called: user_id={user_id}")
    await calendar_client.initialize(user_id)
    return await calendar_client.get_week_summary()
