# modules/integrations/weather/tomorrow_client.py
"""
Tomorrow.io API Client - Production Version
Clean API client with rate limiting for Syntax Prime V2
"""

import os
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class TomorrowClient:
    """Tomorrow.io API client with rate limiting and session reuse"""
    
    def __init__(self):
        self.api_key = os.getenv('TOMORROW_IO_API_KEY')
        self.base_url = "https://api.tomorrow.io/v4"
        self.default_location = os.getenv('DEFAULT_WEATHER_LOCATION', '38.8606,-77.2287')
        self._last_request: Optional[datetime] = None
        self._min_interval = 300  # 5 minutes between requests
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=30)
        
        if not self.api_key:
            logger.warning("TOMORROW_IO_API_KEY not configured")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create reusable HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session
    
    async def close(self) -> None:
        """Close HTTP session - call on shutdown"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("TomorrowClient session closed")
    
    async def _rate_limit(self) -> None:
        """Rate limiting to avoid API abuse"""
        if self._last_request:
            elapsed = (datetime.now() - self._last_request).total_seconds()
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
        self._last_request = datetime.now()
    
    async def get_current_weather(self, location: Optional[str] = None) -> dict:
        """Get current weather from Tomorrow.io API"""
        if not self.api_key:
            raise ValueError("TOMORROW_IO_API_KEY not configured")
        
        location = location or self.default_location
        await self._rate_limit()
        
        fields = [
            "temperature", "temperatureApparent", "pressureSurfaceLevel",
            "uvIndex", "humidity", "windSpeed", "visibility", "weatherCode",
            "precipitationProbability"
        ]
        
        params = {
            'location': location,
            'fields': ','.join(fields),
            'units': 'metric',
            'apikey': self.api_key
        }
        
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/weather/realtime",
                params=params
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data['data']['values']
        except aiohttp.ClientError as e:
            logger.error(f"Tomorrow.io API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Tomorrow.io unexpected error: {e}")
            raise
    
    async def get_weather_forecast(self, location: Optional[str] = None, days: int = 5) -> List[dict]:
        """Get weather forecast from Tomorrow.io API"""
        if not self.api_key:
            raise ValueError("TOMORROW_IO_API_KEY not configured")
        
        location = location or self.default_location
        await self._rate_limit()
        
        params = {
            'location': location,
            'timesteps': '1d',
            'units': 'metric',
            'apikey': self.api_key
        }
        
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/weather/forecast",
                params=params
            ) as response:
                response.raise_for_status()
                data = await response.json()
                timelines = data.get('timelines', {}).get('daily', [])
                return timelines[:days]
        except aiohttp.ClientError as e:
            logger.error(f"Tomorrow.io Forecast API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Tomorrow.io Forecast unexpected error: {e}")
            raise
