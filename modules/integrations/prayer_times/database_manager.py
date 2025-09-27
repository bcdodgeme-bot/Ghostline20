# modules/integrations/prayer_times/database_manager.py
"""
Prayer Times Database Manager for Syntax Prime V2
Handles caching, retrieval, and management of prayer times data
Implements the elegant midnight caching system!
"""

import asyncpg
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, date, time, timedelta
import json
import sys
import os

# Handle imports for both direct execution and module import
if __name__ == "__main__":
    # Running directly - add the project root to Python path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    sys.path.insert(0, project_root)
    
    from modules.core.database import db_manager
    from aladhan_client import AlAdhanClient
else:
    # Running as module - use relative imports
    from ...core.database import db_manager
    from .aladhan_client import AlAdhanClient

logger = logging.getLogger(__name__)

class PrayerDatabaseManager:
    """
    Manages prayer times database operations with intelligent caching
    One API call per day at midnight = efficient and fast!
    """
    
    def __init__(self):
        self.db = db_manager
        self.aladhan_client = AlAdhanClient()
        
        # Default user ID - since this is a personal AI system
        self.user_id = None
        
    async def initialize(self):
        """Initialize by getting the user ID"""
        try:
            # Get the first (and likely only) user
            user_row = await self.db.fetch_one("SELECT id FROM users ORDER BY created_at LIMIT 1")
            user_id = user_row['id'] if user_row else None
            if user_id:
                self.user_id = user_id
                logger.info(f"🕌 Prayer database manager initialized for user {user_id}")
            else:
                logger.warning("No users found - prayer system will wait for user creation")
        except Exception as e:
            logger.error(f"Failed to initialize prayer database manager: {e}")
    
    async def get_todays_prayer_times(self, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Get today's cached prayer times with automatic IP-based location detection
        
        Args:
            ip_address: User's IP address for location detection (None = auto-detect)
            
        Returns:
            Dict with prayer times and metadata, or None if failed
        """
        
        if not self.user_id:
            await self.initialize()
        
        today = date.today()
        
        # Get location from IP address
        try:
            from .location_detector import get_prayer_location
            location_name, latitude, longitude = await get_prayer_location(self.user_id, ip_address)
            logger.info(f"🌍 Using location from IP: {location_name} ({latitude}, {longitude})")
        except Exception as e:
            logger.warning(f"IP location detection failed, using fallback: {e}")
            location_name = "Merrifield, Virginia"
            latitude, longitude = 38.8606, -77.2287
        
        # Try to get from cache first
        cached_times = await self._get_cached_prayer_times(today, location_name)
        
        if cached_times:
            logger.info(f"✅ Using cached prayer times for {today} at {location_name}")
            return cached_times
    
        # Not cached - fetch fresh data with detected location
        logger.info(f"🔄 No cached prayer times for {today} at {location_name}, fetching from AlAdhan API...")
        return await self.fetch_and_cache_prayer_times(today, location_name, latitude, longitude)
    
    async def fetch_and_cache_prayer_times(self,
                                     target_date: date = None,
                                     location_name: str = None,
                                     latitude: float = None,
                                     longitude: float = None,
                                     ip_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch prayer times from AlAdhan API and cache in database with IP location detection
        
        Args:
            target_date: Date to fetch times for (defaults to today)
            location_name: Human-readable location name (auto-detected if None)
            latitude: Override latitude (auto-detected if None)
            longitude: Override longitude (auto-detected if None)
            ip_address: IP address for location detection
            
        Returns:
            Dict with prayer times and metadata
        """
        
        if not self.user_id:
            await self.initialize()
            if not self.user_id:
                logger.error("Cannot cache prayer times - no user found")
                return None
        
        target_date = target_date or date.today()
        
        # Auto-detect location if not provided
        if not location_name or not latitude or not longitude:
            try:
                from .location_detector import get_prayer_location
                detected_location, detected_lat, detected_lng = await get_prayer_location(self.user_id, ip_address)
                
                location_name = location_name or detected_location
                latitude = latitude or detected_lat
                longitude = longitude or detected_lng
                
                logger.info(f"🌍 Auto-detected location: {location_name} ({latitude}, {longitude})")
                
            except Exception as e:
                logger.warning(f"Location auto-detection failed, using fallback: {e}")
                location_name = location_name or "Merrifield, Virginia"
                latitude = latitude or 38.8606
                longitude = longitude or -77.2287
        
        date_str = target_date.strftime("%d-%m-%Y")
    
    # The rest of the function stays exactly the same...
    # (keep everything after this point unchanged)
        
        # Use default Virginia coordinates if not specified
        lat = latitude or 38.8606
        lng = longitude or -77.2287
        
        try:
            # Fetch from AlAdhan API
            api_data = await self.aladhan_client.get_prayer_times_for_date(
                date_str=date_str,
                latitude=lat,
                longitude=lng
            )
            
            if not api_data.get("success"):
                logger.error(f"Failed to fetch prayer times: {api_data.get('error')}")
                return None
            
            # Also fetch Islamic calendar info
            islamic_info = await self.aladhan_client.get_islamic_calendar_info(date_str)
            
            # Prepare data for database with proper type conversion
            prayer_times = api_data["prayer_times"]
            islamic_date_info = islamic_info if islamic_info.get("success") else {}
            
            # Convert Islamic year to integer (it comes as string from API)
            islamic_year = None
            if islamic_date_info.get("islamic_year"):
                try:
                    islamic_year = int(islamic_date_info["islamic_year"])
                except (ValueError, TypeError):
                    islamic_year = None
            
            # 🔍 DEBUG LOGGING - CRITICAL DIAGNOSTIC INFO
            logger.info("🔍 DEBUG: About to INSERT prayer times to database")
            logger.info(f"  api_data success: {api_data.get('success')}")
            logger.info(f"  target_date: {target_date}")
            logger.info(f"  location_name: {location_name}")
            
            # Check the prayer_times dictionary
            logger.info(f"  prayer_times dict: {prayer_times}")
            logger.info(f"  prayer_times type: {type(prayer_times)}")
            
            for prayer_name, prayer_time in prayer_times.items():
                logger.info(f"    {prayer_name}: {prayer_time}")
                logger.info(f"      type: {type(prayer_time)}")
                logger.info(f"      repr: {repr(prayer_time)}")
                logger.info(f"      str: {str(prayer_time)}")
                
                # Check if it's a valid time object
                if hasattr(prayer_time, 'hour'):
                    logger.info(f"      hour: {prayer_time.hour}, minute: {prayer_time.minute}")
                else:
                    logger.info(f"      ❌ NOT A TIME OBJECT!")
            
            # Check Islamic date info
            logger.info(f"  islamic_date_info: {islamic_date_info}")
            logger.info(f"  islamic_year: {islamic_year} (type: {type(islamic_year)})")
            
            # Check the actual parameters being passed to the query
            insert_params = [
                self.user_id, target_date, location_name, lat, lng,
                prayer_times["fajr"], prayer_times["dhuhr"], prayer_times["asr"],
                prayer_times["maghrib"], prayer_times["isha"],
                islamic_date_info.get("islamic_date"),
                islamic_date_info.get("islamic_month"),
                islamic_year,
                api_data["calculation_method"],
                api_data["location"]["timezone"],
                json.dumps(api_data["raw_api_response"])
            ]
            
            logger.info("🔍 DEBUG: INSERT parameters:")
            for i, param in enumerate(insert_params, 1):
                logger.info(f"    ${i}: {param} (type: {type(param)})")
            # 🔍 END DEBUG LOGGING
            
            # Insert/update in database
            query = """
            INSERT INTO prayer_times_cache (
                user_id, date, location_name, latitude, longitude,
                fajr_time, dhuhr_time, asr_time, maghrib_time, isha_time,
                islamic_date, islamic_month, islamic_year,
                calculation_method, timezone, api_response
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16
            )
            ON CONFLICT (user_id, date, location_name) 
            DO UPDATE SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                fajr_time = EXCLUDED.fajr_time,
                dhuhr_time = EXCLUDED.dhuhr_time,
                asr_time = EXCLUDED.asr_time,
                maghrib_time = EXCLUDED.maghrib_time,
                isha_time = EXCLUDED.isha_time,
                islamic_date = EXCLUDED.islamic_date,
                islamic_month = EXCLUDED.islamic_month,
                islamic_year = EXCLUDED.islamic_year,
                calculation_method = EXCLUDED.calculation_method,
                timezone = EXCLUDED.timezone,
                api_response = EXCLUDED.api_response,
                updated_at = NOW()
            RETURNING id
            """
            
            result_row = await self.db.fetch_one(query,
                self.user_id, target_date, location_name, lat, lng,
                prayer_times["fajr"], prayer_times["dhuhr"], prayer_times["asr"],
                prayer_times["maghrib"], prayer_times["isha"],
                islamic_date_info.get("islamic_date"),
                islamic_date_info.get("islamic_month"),
                islamic_year,  # Now properly converted to integer
                api_data["calculation_method"],
                api_data["location"]["timezone"],
                json.dumps(api_data["raw_api_response"])
            )
            
            result_id = result_row['id'] if result_row else None
            
            logger.info(f"✅ Cached prayer times for {target_date} (ID: {result_id})")
            
            # 🔍 DEBUG: Verify what was actually stored
            if result_id:
                verify_query = """
                SELECT fajr_time, dhuhr_time, asr_time, maghrib_time, isha_time 
                FROM prayer_times_cache 
                WHERE id = $1
                """
                stored_data = await self.db.fetch_one(verify_query, result_id)
                if stored_data:
                    logger.info("🔍 DEBUG: Verified stored data in database:")
                    logger.info(f"  Stored Fajr: {stored_data['fajr_time']} (type: {type(stored_data['fajr_time'])})")
                    logger.info(f"  Stored Dhuhr: {stored_data['dhuhr_time']} (type: {type(stored_data['dhuhr_time'])})")
                    logger.info(f"  Stored Asr: {stored_data['asr_time']} (type: {type(stored_data['asr_time'])})")
                    logger.info(f"  Stored Maghrib: {stored_data['maghrib_time']} (type: {type(stored_data['maghrib_time'])})")
                    logger.info(f"  Stored Isha: {stored_data['isha_time']} (type: {type(stored_data['isha_time'])})")
            
            # Return formatted response
            return self._format_prayer_times_response(
                target_date, location_name, lat, lng, prayer_times,
                islamic_date_info, api_data["calculation_method"]
            )
            
        except Exception as e:
            logger.error(f"Error caching prayer times: {e}")
            logger.error(f"Exception details:", exc_info=True)
            return None
    
    async def _get_cached_prayer_times(self, target_date: date, location_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached prayer times from database
        
        Args:
            target_date: Date to get times for
            location_name: Location name
            
        Returns:
            Cached prayer times or None
        """
        
        if not self.user_id:
            return None
        
        query = """
        SELECT date, location_name, latitude, longitude,
               fajr_time, dhuhr_time, asr_time, maghrib_time, isha_time,
               islamic_date, islamic_month, islamic_year,
               calculation_method, created_at
        FROM prayer_times_cache
        WHERE user_id = $1 AND date = $2 AND location_name = $3
        ORDER BY created_at DESC
        LIMIT 1
        """
        
        try:
            row = await self.db.fetch_one(query, self.user_id, target_date, location_name)
            
            if row:
                # 🔍 DEBUG: Check what we retrieved from database
                logger.info("🔍 DEBUG: Retrieved cached prayer times from database:")
                logger.info(f"  Retrieved Fajr: {row['fajr_time']} (type: {type(row['fajr_time'])})")
                logger.info(f"  Retrieved Dhuhr: {row['dhuhr_time']} (type: {type(row['dhuhr_time'])})")
                logger.info(f"  Retrieved Asr: {row['asr_time']} (type: {type(row['asr_time'])})")
                logger.info(f"  Retrieved Maghrib: {row['maghrib_time']} (type: {type(row['maghrib_time'])})")
                logger.info(f"  Retrieved Isha: {row['isha_time']} (type: {type(row['isha_time'])})")
                
                return self._format_prayer_times_response(
                    row["date"], row["location_name"],
                    float(row["latitude"]), float(row["longitude"]),
                    {
                        "fajr": row["fajr_time"],
                        "dhuhr": row["dhuhr_time"],
                        "asr": row["asr_time"],
                        "maghrib": row["maghrib_time"],
                        "isha": row["isha_time"]
                    },
                    {
                        "islamic_date": row["islamic_date"],
                        "islamic_month": row["islamic_month"],
                        "islamic_year": row["islamic_year"]
                    },
                    row["calculation_method"],
                    cached=True
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached prayer times: {e}")
            return None
    
    def _format_prayer_times_response(self,
                                    target_date: date,
                                    location_name: str,
                                    latitude: float,
                                    longitude: float,
                                    prayer_times: Dict[str, time],
                                    islamic_info: Dict[str, Any],
                                    calculation_method: str,
                                    cached: bool = False) -> Dict[str, Any]:
        """Format prayer times into a consistent response structure"""
        
        return {
            "success": True,
            "date": target_date,
            "location": {
                "name": location_name,
                "latitude": latitude,
                "longitude": longitude
            },
            "prayer_times": prayer_times,
            "islamic_date": {
                "date": islamic_info.get("islamic_date", "N/A"),
                "month": islamic_info.get("islamic_month", "Unknown"),
                "year": islamic_info.get("islamic_year", "N/A")
            },
            "calculation_method": calculation_method,
            "cached": cached,
            "timestamp": datetime.now()
        }
    
    async def get_next_prayer_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the next upcoming prayer
        Perfect for "How long till Dhuhr?" type questions
        
        Returns:
            Dict with next prayer name, time, and countdown info
        """
        
        prayer_data = await self.get_todays_prayer_times()
        if not prayer_data:
            return None
        
        now = datetime.now().time()
        today = date.today()
        prayer_times = prayer_data["prayer_times"]
        
        # Prayer order throughout the day
        prayer_order = ["fajr", "dhuhr", "asr", "maghrib", "isha"]
        
        # Find next prayer
        for prayer_name in prayer_order:
            prayer_time = prayer_times[prayer_name]
            
            if now < prayer_time:
                # Calculate time until prayer
                now_dt = datetime.combine(today, now)
                prayer_dt = datetime.combine(today, prayer_time)
                time_until = prayer_dt - now_dt
                
                return {
                    "prayer_name": prayer_name.title(),
                    "prayer_time": prayer_time,
                    "time_until": time_until,
                    "time_until_text": self._format_time_until(time_until),
                    "is_today": True
                }
        
        # All prayers passed for today - next prayer is tomorrow's Fajr
        # Try to get tomorrow's times
        tomorrow = today + timedelta(days=1)
        tomorrow_prayer_data = await self.get_todays_prayer_times()  # This will fetch tomorrow if needed
        
        if tomorrow_prayer_data:
            tomorrow_fajr = tomorrow_prayer_data["prayer_times"]["fajr"]
            now_dt = datetime.combine(today, now)
            fajr_dt = datetime.combine(tomorrow, tomorrow_fajr)
            time_until = fajr_dt - now_dt
            
            return {
                "prayer_name": "Fajr",
                "prayer_time": tomorrow_fajr,
                "time_until": time_until,
                "time_until_text": self._format_time_until(time_until),
                "is_today": False
            }
        
        return None
    
    def _format_time_until(self, time_delta: timedelta) -> str:
        """
        Format timedelta into human-readable text
        
        Args:
            time_delta: Time difference
            
        Returns:
            Human-readable string like "2 hours 15 minutes"
        """
        
        total_seconds = int(time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
        elif minutes > 0:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return "less than a minute"
    
    async def get_daily_prayer_schedule(self, target_date: date = None) -> Optional[Dict[str, Any]]:
        """
        Get full day's prayer schedule - perfect for "What are prayer times today?"
        
        Args:
            target_date: Date to get schedule for (defaults to today)
            
        Returns:
            Full prayer schedule with Islamic date info
        """
        
        target_date = target_date or date.today()
        prayer_data = await self.get_todays_prayer_times()
        
        if not prayer_data:
            return None
        
        # Add some helpful context
        prayer_data["is_today"] = target_date == date.today()
        prayer_data["formatted_date"] = target_date.strftime("%A, %B %d, %Y")
        
        return prayer_data
    
    async def schedule_daily_refresh(self):
        """
        Schedule the midnight refresh for tomorrow's prayer times
        This is the automated daily caching system!
        """
        
        tomorrow = date.today() + timedelta(days=1)
        logger.info(f"🌅 Scheduling daily prayer times refresh for {tomorrow}")
        
        # Fetch and cache tomorrow's prayer times
        result = await self.fetch_and_cache_prayer_times(tomorrow)
        
        if result:
            logger.info(f"✅ Successfully cached prayer times for {tomorrow}")
            return True
        else:
            logger.error(f"❌ Failed to cache prayer times for {tomorrow}")
            return False


# Convenience functions for easy import
async def get_prayer_database_manager():
    """Get initialized prayer database manager"""
    manager = PrayerDatabaseManager()
    await manager.initialize()
    return manager

async def get_next_prayer() -> Optional[Dict[str, Any]]:
    """Quick function to get next prayer info"""
    manager = await get_prayer_database_manager()
    return await manager.get_next_prayer_info()

async def get_todays_prayers() -> Optional[Dict[str, Any]]:
    """Quick function to get today's prayer schedule"""
    manager = await get_prayer_database_manager()
    return await manager.get_daily_prayer_schedule()


# Testing and development
if __name__ == "__main__":
    import asyncio
    
    async def test_prayer_database():
        print("🕌 Testing Prayer Database Manager")
        print("=" * 50)
        
        manager = PrayerDatabaseManager()
        await manager.initialize()
        
        # Test getting today's prayer times
        print("📅 Getting today's prayer times...")
        today_prayers = await manager.get_todays_prayer_times()
        
        if today_prayers:
            print(f"✅ Date: {today_prayers['formatted_date'] if 'formatted_date' in today_prayers else today_prayers['date']}")
            print(f"📍 Location: {today_prayers['location']['name']}")
            print(f"🕌 Islamic Date: {today_prayers['islamic_date']['date']} {today_prayers['islamic_date']['month']}")
            print(f"⏰ Cached: {'Yes' if today_prayers.get('cached') else 'No'}")
            
            times = today_prayers['prayer_times']
            print("\n🕐 Prayer Times:")
            print(f"   Fajr: {times['fajr']}")
            print(f"   Dhuhr: {times['dhuhr']}")
            print(f"   Asr: {times['asr']}")
            print(f"   Maghrib: {times['maghrib']}")
            print(f"   Isha: {times['isha']}")
        
        print("\n⏳ Getting next prayer info...")
        next_prayer = await manager.get_next_prayer_info()
        
        if next_prayer:
            print(f"✅ Next Prayer: {next_prayer['prayer_name']} at {next_prayer['prayer_time']}")
            print(f"⏰ Time Until: {next_prayer['time_until_text']}")
        
        print("\n🔄 Testing daily refresh...")
        refresh_result = await manager.schedule_daily_refresh()
        print(f"✅ Daily refresh: {'Success' if refresh_result else 'Failed'}")
    
    asyncio.run(test_prayer_database())
