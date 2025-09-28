# modules/integrations/prayer_times/location_detector.py
"""
IP-based Location Detection for Prayer Times
Automatically detects user location from IP address for accurate prayer time calculations
"""

import asyncio
import httpx
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class IPLocationDetector:
    """Detects user location from IP address for prayer time calculations"""
    
    def __init__(self):
        self.cache_duration = timedelta(hours=24)  # Cache location for 24 hours
        self.location_cache = {}
        
        # Fallback location (Merrifield, Virginia)
        self.fallback_location = {
            'city': 'Merrifield',
            'region': 'Virginia',
            'country': 'United States',
            'latitude': 38.8606,
            'longitude': -77.2287,
            'timezone': 'America/New_York'
        }
        
        # Multiple IP geolocation services for redundancy
        self.location_services = [
            {
                'name': 'ipapi.co',
                'url': 'https://ipapi.co/{ip}/json/',
                'parser': self._parse_ipapi_response
            },
            {
                'name': 'ip-api.com',
                'url': 'http://ip-api.com/json/{ip}',
                'parser': self._parse_ipapi_com_response
            },
            {
                'name': 'ipinfo.io',
                'url': 'https://ipinfo.io/{ip}/json',
                'parser': self._parse_ipinfo_response
            }
        ]
    
    async def get_location_from_ip(self, ip_address: str = None) -> Dict[str, any]:
        """
        Get location data from IP address with caching and fallback
        
        Args:
            ip_address: IP address to geolocate (None = detect automatically)
            
        Returns:
            Location dict with lat, lng, city, country, timezone
        """
        
        # Use cached location if available and recent
        cache_key = ip_address or 'auto'
        if cache_key in self.location_cache:
            cached_data = self.location_cache[cache_key]
            if datetime.now() - cached_data['cached_at'] < self.cache_duration:
                logger.info(f"📍 Using cached location for {cache_key}")
                return cached_data['location']
        
        # Try to detect location from IP
        detected_location = await self._detect_location_with_fallback(ip_address)
        
        # Cache the result
        self.location_cache[cache_key] = {
            'location': detected_location,
            'cached_at': datetime.now()
        }
        
        return detected_location
    
    async def _detect_location_with_fallback(self, ip_address: str = None) -> Dict[str, any]:
        """Try multiple location services with fallback"""
        
        for service in self.location_services:
            try:
                logger.info(f"🌐 Trying location detection with {service['name']}")
                location = await self._query_location_service(service, ip_address)
                
                if location and self._validate_location(location):
                    logger.info(f"✅ Location detected: {location['city']}, {location['country']}")
                    return location
                    
            except Exception as e:
                logger.warning(f"⚠️ {service['name']} failed: {e}")
                continue
        
        # All services failed - use fallback location
        logger.warning(f"🔄 All location services failed, using fallback location: {self.fallback_location['city']}")
        return self.fallback_location
    
    async def _query_location_service(self, service: Dict, ip_address: str = None) -> Optional[Dict]:
        """Query a specific location service"""
        
        # Handle automatic IP detection
        url = service['url'].format(ip=ip_address or '')
        if not ip_address:
            url = url.replace('/', '')  # Remove trailing slash for auto-detection
        
        timeout = httpx.Timeout(10.0)  # 10 second timeout
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            return service['parser'](data)
    
    def _parse_ipapi_response(self, data: Dict) -> Optional[Dict]:
        """Parse ipapi.co response"""
        if data.get('error'):
            return None
            
        return {
            'city': data.get('city', 'Unknown'),
            'region': data.get('region', ''),
            'country': data.get('country_name', 'Unknown'),
            'latitude': float(data.get('latitude', 0)),
            'longitude': float(data.get('longitude', 0)),
            'timezone': data.get('timezone', 'UTC'),
            'source': 'ipapi.co'
        }
    
    def _parse_ipapi_com_response(self, data: Dict) -> Optional[Dict]:
        """Parse ip-api.com response"""
        if data.get('status') != 'success':
            return None
            
        return {
            'city': data.get('city', 'Unknown'),
            'region': data.get('regionName', ''),
            'country': data.get('country', 'Unknown'),
            'latitude': float(data.get('lat', 0)),
            'longitude': float(data.get('lon', 0)),
            'timezone': data.get('timezone', 'UTC'),
            'source': 'ip-api.com'
        }
    
    def _parse_ipinfo_response(self, data: Dict) -> Optional[Dict]:
        """Parse ipinfo.io response (requires parsing loc field)"""
        if 'loc' not in data:
            return None
            
        try:
            lat, lng = data['loc'].split(',')
            return {
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', ''),
                'country': data.get('country', 'Unknown'),
                'latitude': float(lat),
                'longitude': float(lng),
                'timezone': data.get('timezone', 'UTC'),
                'source': 'ipinfo.io'
            }
        except (ValueError, KeyError):
            return None
    
    def _validate_location(self, location: Dict) -> bool:
        """Validate that location data is reasonable"""
        try:
            lat = location['latitude']
            lng = location['longitude']
            
            # Basic validation - check if coordinates are in valid range
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return False
                
            # Check if we have at least city name
            if not location.get('city') or location['city'] == 'Unknown':
                return False
                
            return True
            
        except (KeyError, TypeError, ValueError):
            return False
    
    async def get_location_for_prayers(self, user_id: str, ip_address: str = None) -> Tuple[str, float, float]:
        """
        Get location specifically formatted for prayer time calculations
        
        Returns:
            Tuple of (location_name, latitude, longitude)
        """
        
        try:
            location = await self.get_location_from_ip(ip_address)
            
            # Format location name for prayer database
            city = location['city']
            region = location['region']
            country = location['country']
            
            if region and region != city:
                location_name = f"{city}, {region}"
            else:
                location_name = f"{city}, {country}"
            
            return location_name, location['latitude'], location['longitude']
            
        except Exception as e:
            logger.error(f"Failed to get location for prayers: {e}")
            # Return fallback location
            return ("Merrifield, Virginia", 38.8606, -77.2287)
    
    def clear_cache(self):
        """Clear location cache"""
        self.location_cache.clear()
        logger.info("🗑️ Location cache cleared")
    
    def get_cache_status(self) -> Dict:
        """Get current cache status"""
        return {
            'cached_locations': len(self.location_cache),
            'cache_duration_hours': self.cache_duration.total_seconds() / 3600,
            'cached_ips': list(self.location_cache.keys())
        }

# Global location detector instance
_location_detector = None

def get_location_detector() -> IPLocationDetector:
    """Get the global location detector"""
    global _location_detector
    if _location_detector is None:
        _location_detector = IPLocationDetector()
    return _location_detector

# Convenience functions
async def detect_user_location(ip_address: str = None) -> Dict:
    """Detect user location from IP"""
    detector = get_location_detector()
    return await detector.get_location_from_ip(ip_address)

async def get_prayer_location(user_id: str, ip_address: str = None) -> Tuple[str, float, float]:
    """Get location for prayer time calculations"""
    detector = get_location_detector()
    return await detector.get_location_for_prayers(user_id, ip_address)
