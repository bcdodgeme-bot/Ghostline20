# modules/integrations/prayer_times/location_detector.py
"""
IP-based Location Detection for Prayer Times
Automatically detects user location from IP address for accurate prayer time calculations

Updated: 01/12/26 - Added GPS priority for iOS/macOS apps
Priority: GPS > IP > Fallback (Merrifield, VA)
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
            'timezone': 'America/New_York',
            'source': 'fallback'
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
    
    #-- Section 1: Main Location Method with GPS Priority - 01/12/26
    async def get_location_from_ip(self, ip_address: str = None, gps_latitude: float = None, gps_longitude: float = None) -> Dict[str, any]:
        """
        Get location data with GPS > IP > Fallback priority
        
        Args:
            ip_address: IP address to geolocate (None = detect automatically)
            gps_latitude: GPS latitude from mobile device (optional)
            gps_longitude: GPS longitude from mobile device (optional)
            
        Returns:
            Location dict with lat, lng, city, country, timezone, source
        """
        
        # PRIORITY 1: GPS coordinates from iOS/macOS (if provided)
        if gps_latitude is not None and gps_longitude is not None:
            # Validate GPS coordinates
            if -90 <= gps_latitude <= 90 and -180 <= gps_longitude <= 180 and not (gps_latitude == 0 and gps_longitude == 0):
                logger.info(f"📍 Using GPS location: {gps_latitude}, {gps_longitude}")
                return {
                    'city': 'GPS Location',
                    'region': '',
                    'country': 'United States',
                    'latitude': gps_latitude,
                    'longitude': gps_longitude,
                    'timezone': 'America/New_York',
                    'source': 'gps'
                }
            else:
                logger.warning(f"⚠️ Invalid GPS coordinates: {gps_latitude}, {gps_longitude}")
        
        # PRIORITY 2: IP-based geolocation
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
    
    #-- Section 2: IP Detection with Fallback
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
            url = url.rstrip('/')  # Remove only trailing slash for auto-detection
        
        timeout = httpx.Timeout(10.0)  # 10 second timeout
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            return service['parser'](data)
    
    #-- Section 3: Response Parsers
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
    
    #-- Section 4: Validation
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
    
    #-- Section 5: Prayer-specific Location Method - Updated 01/12/26
    async def get_location_for_prayers(self, user_id: str, ip_address: str = None, gps_latitude: float = None, gps_longitude: float = None) -> Tuple[str, float, float]:
        """
        Get location specifically formatted for prayer time calculations
        Now supports GPS priority for iOS/macOS apps
        
        Args:
            user_id: User ID for caching/preferences
            ip_address: IP address for geolocation
            gps_latitude: GPS latitude from mobile device
            gps_longitude: GPS longitude from mobile device
            
        Returns:
            Tuple of (location_name, latitude, longitude)
        """
        
        try:
            location = await self.get_location_from_ip(ip_address, gps_latitude, gps_longitude)
            
            # Log the source for debugging
            source = location.get('source', 'unknown')
            logger.info(f"📍 Prayer location source: {source}")
            
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
    
    #-- Section 6: Cache Management
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


#-- Section 7: Global Instance and Convenience Functions - Updated 01/12/26
_location_detector = None

def get_location_detector() -> IPLocationDetector:
    """Get the global location detector"""
    global _location_detector
    if _location_detector is None:
        _location_detector = IPLocationDetector()
    return _location_detector

async def detect_user_location(ip_address: str = None, gps_latitude: float = None, gps_longitude: float = None) -> Dict:
    """
    Detect user location with GPS > IP > Fallback priority
    
    Args:
        ip_address: IP address for geolocation
        gps_latitude: GPS latitude from mobile device
        gps_longitude: GPS longitude from mobile device
    """
    detector = get_location_detector()
    return await detector.get_location_from_ip(ip_address, gps_latitude, gps_longitude)

async def get_prayer_location(user_id: str, ip_address: str = None, gps_latitude: float = None, gps_longitude: float = None) -> Tuple[str, float, float]:
    """
    Get location for prayer time calculations with GPS priority
    
    Args:
        user_id: User ID
        ip_address: IP address for geolocation
        gps_latitude: GPS latitude from mobile device
        gps_longitude: GPS longitude from mobile device
    
    Returns:
        Tuple of (location_name, latitude, longitude)
    """
    detector = get_location_detector()
    return await detector.get_location_for_prayers(user_id, ip_address, gps_latitude, gps_longitude)
