# modules/integrations/telegram/notification_types/weather_notifications.py
"""
Weather Notification Handler
Sends proactive weather updates and alerts
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from ....core.database import db_manager

logger = logging.getLogger(__name__)

class WeatherNotificationHandler:
    """
    Handles weather notifications
    
    Checks every 2 hours for weather updates
    Sends alerts for significant weather changes
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None  # Lazy initialization
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

    # 2. ADD THIS PROPERTY RIGHT AFTER __init__:
    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def check_and_notify(self) -> bool:
        """
        Check weather and send notification if conditions warrant
        
        Returns:
            True if notification was sent
        """
        try:
            # Get current weather from weather cache
            weather_data = await self._get_current_weather()
            
            if not weather_data:
                logger.warning("No weather data available")
                return False
            
            # Check if we should send notification
            should_notify = await self._should_notify_weather(weather_data)
            
            if should_notify:
                await self._send_weather_notification(weather_data)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking weather notifications: {e}")
            return False
    
    async def _get_current_weather(self) -> Optional[Dict[str, Any]]:
        """Get latest weather reading from database + fetch forecast"""
        query = """
        SELECT 
            location,
            temperature,
            temperature_apparent,
            humidity,
            wind_speed,
            weather_description,
            headache_risk_level,
            uv_risk_level,
            timestamp
        FROM weather_readings
        WHERE user_id = $1
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        result = await self.db.fetch_one(query, self.user_id)
        
        if not result:
            return None
        
        # Get forecast from Tomorrow.io
        forecast_summary = await self._get_forecast_summary()
        
        temp_c = float(result['temperature'])
        feels_like_c = float(result['temperature_apparent'])
        temp_f = (temp_c * 9/5) + 32
        feels_like_f = (feels_like_c * 9/5) + 32
        
        return {
            'location': result['location'],
            'temperature': temp_f,  # Now in Fahrenheit
            'feels_like': feels_like_f,  # Now in Fahrenheit
            'condition': result['weather_description'],
            'humidity': int(result['humidity']) if result['humidity'] else 0,
            'wind_speed': float(result['wind_speed']) if result['wind_speed'] else 0,
            'headache_risk': result['headache_risk_level'],
            'uv_risk': result['uv_risk_level'],
            'timestamp': result['timestamp'],
            'forecast': forecast_summary 
        }
    
    async def _should_notify_weather(self, weather_data: Dict[str, Any]) -> bool:
        """
        Determine if weather conditions warrant a notification
        
        Notify if:
        - Significant weather event (rain, snow, storm)
        - Extreme temperatures
        - First update of the day
        """
        condition = weather_data['condition'].lower()
        temp = weather_data['temperature']
        
        # Check for significant weather
        alert_conditions = ['rain', 'storm', 'snow', 'thunder', 'severe', 'warning']
        if any(alert in condition for alert in alert_conditions):
            return True
        
        # Check for extreme temperatures
        if temp < 32 or temp > 95:
            return True
        
        # Check if this is morning update (between 6-9 AM)
        now = datetime.now()
        if 6 <= now.hour <= 9:
            # Check if we already sent today
            already_sent = await self._check_if_sent_today()
            if not already_sent:
                return True
        
        return False
    
    async def _check_if_sent_today(self) -> bool:
        """Check if weather notification was already sent today"""
        query = """
        SELECT COUNT(*) as count
        FROM telegram_notifications
        WHERE user_id = $1
        AND notification_type = 'weather'
        AND DATE(sent_at) = CURRENT_DATE
        """
        
        result = await self.db.fetch_one(query, self.user_id)
        return result['count'] > 0 if result else False
    
    async def _send_weather_notification(self, weather_data: Dict[str, Any]) -> None:
        """Send weather notification"""
        location = weather_data['location']
        temp = weather_data['temperature']
        feels_like = weather_data['feels_like']
        condition = weather_data['condition']
        humidity = weather_data['humidity']
        wind_speed = weather_data['wind_speed']
        headache_risk = weather_data.get('headache_risk', None)
        uv_risk = weather_data.get('uv_risk', None)
        forecast = weather_data.get('forecast', None)
        
        # Weather emoji based on condition
        emoji = self._get_weather_emoji(condition)
        
        # Build message
        message = f"{emoji} *Weather Update*\n\n"
        message += f"*{location}*\n"
        message += f"Temperature: {temp}°F (feels like {feels_like}°F)\n"
        message += f"Conditions: {condition}\n"
        message += f"Humidity: {humidity}%\n"
        message += f"Wind: {wind_speed} mph\n"
        
        if forecast:
            message += f"\n*Forecast:*\n{forecast}"
        
        # Add health alerts if present
        if headache_risk and headache_risk in ['medium', 'high']:
            message += f"\n\n🤕 *Headache Risk:* {headache_risk.upper()}"
            
        if uv_risk and uv_risk in ['medium', 'high', 'very_high']:
            message += f"\n\n☀️ *UV Risk:* {uv_risk.replace('_', ' ').upper()}"

        # Add advisory if extreme conditions
        if temp < 32:
            message += "\n\n❄️ *Advisory:* Freezing temperatures - dress warmly!"
        elif temp > 95:
            message += "\n\n🌡️ *Advisory:* Extreme heat - stay hydrated!"

        if 'rain' in condition.lower():
            message += "\n\n☔ Don't forget your umbrella!"
        
        # Metadata
        metadata = {
            'location': location,
            'temperature': temp,
            'condition': condition,
            'cached_at': weather_data.get('cached_at', datetime.utcnow()).isoformat() if isinstance(weather_data.get('cached_at'), datetime) else str(weather_data.get('cached_at', datetime.utcnow()))
        }
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='weather',
            notification_subtype='daily_update',
            message_text=message,
            message_data=metadata
        )
        
        logger.info(f"✅ Sent weather notification: {location} - {temp}°F, {condition}")
    
    async def _get_forecast_summary(self) -> Optional[str]:
        """
        Get brief forecast summary from Tomorrow.io
        Returns a short text forecast for the next 24-48 hours
        """
        try:
            from modules.integrations.weather.tomorrow_client import TomorrowClient
            
            client = TomorrowClient()
            
            # Get 2-day forecast
            forecast_data = await client.get_weather_forecast(days=2)
            
            if not forecast_data or len(forecast_data) == 0:
                return None
            
            # Weather code mappings (simplified)
            WEATHER_CODES = {
                1000: "Clear", 1100: "Mostly Clear", 1101: "Partly Cloudy",
                1102: "Mostly Cloudy", 1001: "Cloudy", 2000: "Fog",
                4000: "Drizzle", 4001: "Rain", 4200: "Light Rain",
                4201: "Heavy Rain", 5000: "Snow", 5100: "Light Snow",
                5101: "Heavy Snow", 8000: "Thunderstorm"
            }
            
            # Format brief forecast
            tomorrow = forecast_data[0] if len(forecast_data) > 0 else None
            day_after = forecast_data[1] if len(forecast_data) > 1 else None
            
            forecast_lines = []
            
            if tomorrow:
                values = tomorrow.get('values', {})
                temp_min_c = values.get('temperatureMin', 0)
                temp_max_c = values.get('temperatureMax', 0)
                temp_min_f = temp_min_c * 9/5 + 32
                temp_max_f = temp_max_c * 9/5 + 32
                weather_code = values.get('weatherCodeMax', 1000)
                condition = WEATHER_CODES.get(weather_code, "Unknown")
                precip_prob = values.get('precipitationProbabilityAvg', 0)
                
                forecast_lines.append(
                    f"Tomorrow: {condition}, {temp_min_f:.0f}-{temp_max_f:.0f}°F"
                )
                
                if precip_prob > 30:
                    forecast_lines.append(f"  {precip_prob:.0f}% chance of precipitation")
            
            if day_after:
                values = day_after.get('values', {})
                temp_min_c = values.get('temperatureMin', 0)
                temp_max_c = values.get('temperatureMax', 0)
                temp_min_f = temp_min_c * 9/5 + 32
                temp_max_f = temp_max_c * 9/5 + 32
                weather_code = values.get('weatherCodeMax', 1000)
                condition = WEATHER_CODES.get(weather_code, "Unknown")
                
                forecast_lines.append(
                    f"Day After: {condition}, {temp_min_f:.0f}-{temp_max_f:.0f}°F"
                )
            
            return "\n".join(forecast_lines) if forecast_lines else None
            
        except Exception as e:
            logger.warning(f"Could not fetch forecast: {e}")
            return None
    
    def _get_weather_emoji(self, condition: str) -> str:
        """Get emoji based on weather condition"""
        condition_lower = condition.lower()
        
        emoji_map = {
            'clear': '☀️',
            'sunny': '☀️',
            'partly cloudy': '⛅',
            'cloudy': '☁️',
            'overcast': '☁️',
            'rain': '🌧️',
            'drizzle': '🌦️',
            'snow': '❄️',
            'sleet': '🌨️',
            'storm': '⛈️',
            'thunder': '⛈️',
            'fog': '🌫️',
            'mist': '🌫️',
            'windy': '💨',
            'hot': '🌡️',
            'cold': '❄️'
        }
        
        for key, emoji in emoji_map.items():
            if key in condition_lower:
                return emoji
        
        return '🌤️'  # default
    
    async def send_daily_forecast(self) -> bool:
        """
        Send daily weather forecast (can be called manually or scheduled)
        
        Returns:
            True if successful
        """
        try:
            weather_data = await self._get_current_weather()
            
            if not weather_data:
                return False
            
            await self._send_weather_notification(weather_data)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily forecast: {e}")
            return False
