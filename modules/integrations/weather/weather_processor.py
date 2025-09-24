# modules/integrations/weather/weather_processor.py
"""
Weather Data Processor - Database operations and formatting
Handles storing weather data and generating user-friendly summaries
"""

from typing import Dict, Optional
from datetime import datetime
import logging

from ...core.database import db_manager
from .health_monitor import HealthMonitor

logger = logging.getLogger(__name__)

# Weather code mappings from Tomorrow.io
WEATHER_CODES = {
    1000: "Clear, Sunny", 1100: "Mostly Clear", 1101: "Partly Cloudy",
    1102: "Mostly Cloudy", 1001: "Cloudy", 2000: "Fog", 4000: "Drizzle",
    4001: "Rain", 4200: "Light Rain", 4201: "Heavy Rain", 5000: "Snow",
    5100: "Light Snow", 5101: "Heavy Snow", 8000: "Thunderstorm"
}

class WeatherProcessor:
    """Process and store weather data with health monitoring"""
    
    def __init__(self):
        self.health_monitor = HealthMonitor()
    
    async def store_weather_reading(self, user_id: str, weather_data: dict, location: str = None) -> str:
        """Store weather reading in database with health calculations"""
        
        # Get pressure history for headache risk calculation
        previous_pressure = await self.health_monitor.get_pressure_history(user_id, 3)
        current_pressure = float(weather_data.get("pressureSurfaceLevel", 0))
        
        # Calculate pressure change
        pressure_change_3h = None
        if previous_pressure:
            pressure_change_3h = current_pressure - previous_pressure
        
        # Calculate health risks
        uv_index = float(weather_data.get("uvIndex", 0))
        headache_risk, uv_risk = self.health_monitor.calculate_health_risks(uv_index, pressure_change_3h)
        
        # Get weather description
        weather_code = weather_data.get("weatherCode", 1000)
        weather_description = WEATHER_CODES.get(weather_code, f"Unknown condition {weather_code}")
        
        # Insert into database
        insert_sql = """
        INSERT INTO weather_readings (
            user_id, timestamp, location, temperature, temperature_apparent,
            pressure_surface_level, uv_index, humidity, wind_speed, visibility,
            weather_code, weather_description, precipitation_probability,
            pressure_change_3h, headache_risk_level, uv_risk_level,
            severe_weather_alert, alert_sent
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
        ) RETURNING id;
        """
        
        try:
            reading_id = await db_manager.fetch_one(
                insert_sql,
                user_id, datetime.now(), location or "38.8606,-77.2287",
                weather_data.get("temperature"), weather_data.get("temperatureApparent"),
                current_pressure, uv_index, weather_data.get("humidity"),
                weather_data.get("windSpeed"), weather_data.get("visibility"),
                weather_code, weather_description, weather_data.get("precipitationProbability"),
                pressure_change_3h, headache_risk, uv_risk, False, False
            )
            
            logger.info(f"Weather reading stored for user {user_id}: {reading_id['id']}")
            return reading_id['id']
            
        except Exception as e:
            logger.error(f"Failed to store weather reading: {e}")
            raise
    
    def format_weather_summary(self, weather_data: dict) -> str:
        """Create user-friendly weather summary"""
        temp_c = weather_data.get("temperature", 0)
        temp_f = temp_c * 9/5 + 32 if temp_c else 0
        condition = WEATHER_CODES.get(weather_data.get("weatherCode", 1000), "Unknown")
        
        summary = f"Current weather: {condition}, {temp_f:.0f}F"
        
        uv_index = weather_data.get("uvIndex", 0)
        if uv_index >= 4:
            summary += f", UV {uv_index} (protection needed)"
        
        return summary