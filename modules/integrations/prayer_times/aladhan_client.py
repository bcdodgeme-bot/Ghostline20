# modules/integrations/prayer_times/aladhan_client.py
"""
AlAdhan API Client for Syntax Prime V2
Fetches Islamic prayer times and calendar information from free AlAdhan API
No API key required - completely free service!

API Documentation:
- Prayer Times: https://aladhan.com/prayer-times-api
- Islamic Calendar: https://aladhan.com/islamic-calendar-api
"""

import asyncio
import httpx
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, date, time
import json

logger = logging.getLogger(__name__)

class AlAdhanClient:
    """
    Client for AlAdhan.com Islamic prayer times and calendar API
    Handles prayer time calculations and Islamic date information
    """
    
    def __init__(self):
        self.base_url = "http://api.aladhan.com/v1"
        self.timeout = 10.0
        
        # Default location: Merrifield, Virginia
        self.default_latitude = 38.8606
        self.default_longitude = -77.2287
        self.default_method = 2  # ISNA (Islamic Society of North America)
        self.default_timezone = "America/New_York"
    
    async def get_prayer_times_today(self,
                                   latitude: float = None,
                                   longitude: float = None,
                                   method: int = None) -> Dict[str, Any]:
        """
        Get today's prayer times for specified location
        
        Args:
            latitude: Location latitude (defaults to Virginia)
            longitude: Location longitude (defaults to Virginia)
            method: Calculation method (defaults to ISNA)
            
        Returns:
            Dict with prayer times and metadata
        """
        
        # Use defaults if not specified
        lat = latitude or self.default_latitude
        lng = longitude or self.default_longitude
        calc_method = method or self.default_method
        
        today = datetime.now().strftime("%d-%m-%Y")
        
        return await self.get_prayer_times_for_date(
            date_str=today,
            latitude=lat,
            longitude=lng,
            method=calc_method
        )
    
    async def get_prayer_times_for_date(self,
                                      date_str: str,
                                      latitude: float,
                                      longitude: float,
                                      method: int = 2) -> Dict[str, Any]:
        """
        Get prayer times for specific date and location
        
        Args:
            date_str: Date in DD-MM-YYYY format
            latitude: Location latitude
            longitude: Location longitude  
            method: Calculation method (2 = ISNA)
            
        Returns:
            Dict containing prayer times and Islamic calendar info
        """
        
        url = f"{self.base_url}/timings/{date_str}"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "method": method,
            "timezone": self.default_timezone
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"🕌 Fetching prayer times for {date_str} from AlAdhan API")
                
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("code") != 200:
                    raise Exception(f"AlAdhan API error: {data.get('status', 'Unknown error')}")
                
                # Extract the data we need
                api_data = data["data"]
                timings = api_data["timings"]
                
                # Handle different API response structures
                date_info = api_data["date"]
                if isinstance(date_info, dict) and "islamic" in date_info:
                    islamic_date = date_info["islamic"]
                    gregorian_date = date_info["gregorian"]
                else:
                    # Fallback: get Islamic date separately
                    logger.warning("Islamic date not in prayer times response, will fetch separately")
                    islamic_date = {"date": "N/A", "month": {"en": "Unknown"}, "year": "N/A"}
                    gregorian_date = {"date": datetime.now().strftime("%d-%m-%Y")}
                
                # Parse prayer times (they come as HH:MM strings)
                prayer_times = {
                    "fajr": self._parse_prayer_time(timings["Fajr"]),
                    "dhuhr": self._parse_prayer_time(timings["Dhuhr"]),
                    "asr": self._parse_prayer_time(timings["Asr"]),
                    "maghrib": self._parse_prayer_time(timings["Maghrib"]),
                    "isha": self._parse_prayer_time(timings["Isha"])
                }
                
                result = {
                    "success": True,
                    "date": gregorian_date.get("date", datetime.now().strftime("%d-%m-%Y")),
                    "location": {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": self.default_timezone
                    },
                    "prayer_times": prayer_times,
                    "islamic_date": {
                        "date": islamic_date.get("date", "N/A"),
                        "month": islamic_date.get("month", {}).get("en", "Unknown"),
                        "year": islamic_date.get("year", "N/A")
                    },
                    "calculation_method": self._get_method_name(method),
                    "raw_api_response": data  # Store full response for debugging
                }
                
                logger.info(f"✅ Successfully fetched prayer times: Fajr {prayer_times['fajr']}, Dhuhr {prayer_times['dhuhr']}")
                return result
                
        except httpx.TimeoutException:
            logger.error("⏰ AlAdhan API request timed out")
            return {"success": False, "error": "API timeout"}
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ AlAdhan API HTTP error: {e.response.status_code}")
            return {"success": False, "error": f"HTTP {e.response.status_code}"}
            
        except Exception as e:
            logger.error(f"❌ AlAdhan API error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_islamic_calendar_info(self, date_str: str = None) -> Dict[str, Any]:
        """
        Get Islamic calendar information for a date using the Islamic Calendar API
        This is the bonus API you found! 🎉
        
        Args:
            date_str: Date in DD-MM-YYYY format (defaults to today)
            
        Returns:
            Dict with Islamic calendar details
        """
        
        if not date_str:
            date_str = datetime.now().strftime("%d-%m-%Y")
        
        url = f"{self.base_url}/gToH/{date_str}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"📅 Fetching Islamic calendar info for {date_str}")
                
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("code") != 200:
                    raise Exception(f"Islamic Calendar API error: {data.get('status', 'Unknown error')}")
                
                hijri_data = data["data"]["hijri"]
                gregorian_data = data["data"]["gregorian"]
                
                result = {
                    "success": True,
                    "gregorian_date": gregorian_data["date"],
                    "islamic_date": hijri_data["date"],
                    "islamic_month": hijri_data["month"]["en"],
                    "islamic_year": hijri_data["year"],
                    "weekday": hijri_data["weekday"]["en"],
                    "holidays": hijri_data.get("holidays", []),  # Islamic holidays if any
                    "raw_response": data
                }
                
                logger.info(f"✅ Islamic date: {result['islamic_date']} {result['islamic_month']} {result['islamic_year']}")
                return result
                
        except Exception as e:
            logger.error(f"❌ Islamic Calendar API error: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_prayer_time(self, time_str: str) -> time:
        """
        Convert prayer time string (like "06:15") to Python time object
        
        Args:
            time_str: Time in HH:MM format
            
        Returns:
            Python time object
        """
        try:
            # Remove any timezone info or extra characters
            clean_time = time_str.split()[0]  # Take just the HH:MM part
            hour, minute = clean_time.split(":")
            return time(hour=int(hour), minute=int(minute))
        except Exception as e:
            logger.error(f"Error parsing time '{time_str}': {e}")
            return time(0, 0)  # Return midnight as fallback
    
    def _get_method_name(self, method_id: int) -> str:
        """
        Convert calculation method ID to human-readable name
        
        Args:
            method_id: AlAdhan calculation method ID
            
        Returns:
            Method name string
        """
        methods = {
            1: "Shia Ithna-Ashari",
            2: "ISNA",
            3: "MWL",
            4: "Makkah",
            5: "Egyptian",
            7: "Karachi",
            8: "North America",
            9: "Kuwait",
            10: "Qatar",
            11: "Singapore",
            12: "France",
            13: "Turkey",
            14: "Russia"
        }
        return methods.get(method_id, f"Method {method_id}")
    
    async def test_api_connection(self) -> bool:
        """
        Test if AlAdhan API is accessible
        
        Returns:
            True if API is working, False otherwise
        """
        try:
            result = await self.get_prayer_times_today()
            return result.get("success", False)
        except Exception:
            return False


# Convenience functions for easy import
async def get_todays_prayer_times(latitude: float = None, longitude: float = None) -> Dict[str, Any]:
    """Get today's prayer times - convenience function"""
    client = AlAdhanClient()
    return await client.get_prayer_times_today(latitude, longitude)

async def get_islamic_date_info() -> Dict[str, Any]:
    """Get today's Islamic calendar info - convenience function"""
    client = AlAdhanClient()
    return await client.get_islamic_calendar_info()

async def test_aladhan_api() -> bool:
    """Test AlAdhan API connectivity"""
    client = AlAdhanClient()
    return await client.test_api_connection()


# Example usage and testing
if __name__ == "__main__":
    async def main():
        print("🕌 Testing AlAdhan API Client")
        print("=" * 40)
        
        client = AlAdhanClient()
        
        # Test prayer times
        print("📿 Fetching today's prayer times for Virginia...")
        prayer_data = await client.get_prayer_times_today()
        
        if prayer_data["success"]:
            times = prayer_data["prayer_times"]
            print(f"✅ Fajr: {times['fajr']}")
            print(f"✅ Dhuhr: {times['dhuhr']}")
            print(f"✅ Asr: {times['asr']}")
            print(f"✅ Maghrib: {times['maghrib']}")
            print(f"✅ Isha: {times['isha']}")
            
            islamic_info = prayer_data['islamic_date']
            if islamic_info['date'] != 'N/A':
                print(f"📅 Islamic Date: {islamic_info['date']} {islamic_info['month']} {islamic_info['year']}")
            else:
                print("📅 Islamic date not available in prayer times response")
        else:
            print(f"❌ Prayer times failed: {prayer_data['error']}")
        
        print()
        
        # Test Islamic calendar
        print("📅 Fetching Islamic calendar info...")
        calendar_data = await client.get_islamic_calendar_info()
        
        if calendar_data["success"]:
            print(f"✅ Islamic Date: {calendar_data['islamic_date']}")
            print(f"✅ Month: {calendar_data['islamic_month']}")
            print(f"✅ Year: {calendar_data['islamic_year']}")
            print(f"✅ Weekday: {calendar_data['weekday']}")
            if calendar_data['holidays']:
                print(f"🎉 Holidays: {', '.join(calendar_data['holidays'])}")
        else:
            print(f"❌ Calendar failed: {calendar_data['error']}")
    
    asyncio.run(main())
