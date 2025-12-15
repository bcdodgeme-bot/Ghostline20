# modules/integrations/telegram/notification_types/weather_notifications.py
"""
Weather Notification Handler
Sends proactive weather updates and alerts

FIXED:
- Split alerts (short) vs forecasts (full)
- Fixed floating point display (26.240000000000002 → 26.2)
- Fixed location display (coordinates → city name)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

from ....core.database import db_manager

logger = logging.getLogger(__name__)


class WeatherNotificationHandler:
    """
    Handles weather notifications
    
    Notification Types:
    - ALERTS: Short, urgent messages (freeze, headache, UV)
    - FORECASTS: Full weather briefings (morning, midday, evening)
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
        # Cache location name
        self._location_name = None

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
            weather_data = await self._get_current_weather()
            
            if not weather_data:
                logger.warning("No weather data available")
                return False
            
            # Check what type of notification to send (if any)
            notification_type = await self._get_notification_type(weather_data)
            
            if notification_type == 'none':
                return False
            elif notification_type == 'alert':
                await self._send_weather_alert(weather_data)
                return True
            elif notification_type == 'forecast':
                await self._send_weather_forecast(weather_data)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking weather notifications: {e}")
            return False
    
    async def _get_location_name(self) -> str:
        """Get human-readable location name from prayer_preferences"""
        if self._location_name:
            return self._location_name
        
        try:
            query = """
                SELECT default_location
                FROM prayer_preferences
                WHERE user_id = $1
            """
            result = await self.db.fetch_one(query, self.user_id)
            
            if result and result['default_location']:
                self._location_name = result['default_location']
            else:
                self._location_name = "Your Location"
            
            return self._location_name
            
        except Exception as e:
            logger.warning(f"Could not fetch location name: {e}")
            return "Your Location"
    
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
        
        # Convert Celsius to Fahrenheit with proper rounding
        temp_c = float(result['temperature'])
        feels_like_c = float(result['temperature_apparent'])
        temp_f = round((temp_c * 9/5) + 32, 1)
        feels_like_f = round((feels_like_c * 9/5) + 32, 1)
        
        # Get human-readable location
        location_name = await self._get_location_name()
        
        return {
            'location': location_name,
            'temperature': temp_f,
            'feels_like': feels_like_f,
            'condition': result['weather_description'],
            'humidity': int(result['humidity']) if result['humidity'] else 0,
            'wind_speed': round(float(result['wind_speed']), 1) if result['wind_speed'] else 0,
            'headache_risk': result['headache_risk_level'],
            'uv_risk': result['uv_risk_level'],
            'timestamp': result['timestamp']
        }
    
    async def _get_notification_type(self, weather_data: Dict[str, Any]) -> str:
        """
        Determine what type of notification to send (if any)
        
        Returns:
            'alert' - Short urgent message
            'forecast' - Full weather briefing
            'none' - No notification needed
        """
        condition = weather_data['condition'].lower()
        temp = weather_data['temperature']
        uv_risk = weather_data.get('uv_risk', 'low')
        headache_risk = weather_data.get('headache_risk', 'low')
        
        eastern = ZoneInfo('America/New_York')
        now = datetime.now(eastern)
        current_hour = now.hour
        
        logger.info(f"🌤️ Weather check at {now.strftime('%I:%M %p')} - Temp: {temp}°F, Condition: {condition}, UV: {uv_risk}")
        
        # =====================================================================
        # EMERGENCY ALERTS (anytime) - Always send immediately as SHORT ALERT
        # =====================================================================
        
        # Severe weather conditions
        alert_conditions = ['storm', 'thunder', 'severe', 'warning', 'tornado', 'hurricane']
        if any(alert in condition for alert in alert_conditions):
            return 'alert'
        
        # Extreme temperatures
        if temp < 32 or temp > 95:
            # Check if we already sent a temp alert today
            already_sent = await self._check_if_alert_sent_today('temperature')
            if not already_sent:
                return 'alert'
        
        # Dangerous UV (very high or extreme)
        if uv_risk in ['very_high', 'extreme']:
            already_sent = await self._check_if_alert_sent_today('uv')
            if not already_sent:
                return 'alert'
        
        # High headache risk
        if headache_risk in ['high']:
            already_sent = await self._check_if_alert_sent_today('headache')
            if not already_sent:
                return 'alert'
        
        # =====================================================================
        # SCHEDULED FORECASTS (specific time windows)
        # =====================================================================
        
        # MORNING FORECAST (7-8 AM)
        if 7 <= current_hour < 8:
            already_sent = await self._check_if_sent_in_window('morning')
            if not already_sent:
                return 'forecast'
        
        # MIDDAY CHECK (11 AM - 1 PM) - Only if UV is moderate+
        if 11 <= current_hour < 13:
            if uv_risk in ['moderate', 'high', 'very_high', 'extreme']:
                already_sent = await self._check_if_sent_in_window('midday')
                if not already_sent:
                    return 'forecast'
        
        # EVENING FORECAST (5-6 PM)
        if 17 <= current_hour < 18:
            already_sent = await self._check_if_sent_in_window('evening')
            if not already_sent:
                return 'forecast'
        
        return 'none'
    
    async def _check_if_alert_sent_today(self, alert_type: str) -> bool:
        """Check if a specific alert type was already sent today"""
        query = """
            SELECT COUNT(*) as count
            FROM telegram_notifications
            WHERE user_id = $1
            AND notification_type = 'weather'
            AND notification_subtype = $2
            AND DATE(sent_at) = CURRENT_DATE
        """
        
        result = await self.db.fetch_one(query, self.user_id, f"alert_{alert_type}")
        return result['count'] > 0 if result else False
    
    async def _check_if_sent_in_window(self, window: str) -> bool:
        """Check if weather notification was already sent in a specific time window today"""
        from datetime import time
        
        windows = {
            'morning': (time(7, 0), time(8, 0)),
            'midday': (time(11, 0), time(13, 0)),
            'evening': (time(17, 0), time(18, 0))
        }
        
        if window not in windows:
            return False
            
        start_time, end_time = windows[window]
        
        query = """
            SELECT COUNT(*) as count
            FROM telegram_notifications
            WHERE user_id = $1
            AND notification_type = 'weather'
            AND DATE(sent_at) = CURRENT_DATE
            AND sent_at::time >= $2
            AND sent_at::time < $3
        """
        
        result = await self.db.fetch_one(query, self.user_id, start_time, end_time)
        return result['count'] > 0 if result else False
    
    # =========================================================================
    # SHORT ALERTS (urgent, minimal info)
    # =========================================================================
    
    async def _send_weather_alert(self, weather_data: Dict[str, Any]) -> None:
        """Send a SHORT weather alert (not full forecast)"""
        
        temp = weather_data['temperature']
        condition = weather_data['condition'].lower()
        headache_risk = weather_data.get('headache_risk', 'low')
        uv_risk = weather_data.get('uv_risk', 'low')
        
        # Determine alert type and message
        alert_subtype = 'alert_general'
        
        # Freezing alert
        if temp < 32:
            emoji = "🥶"
            message = f"{emoji} *Freezing Alert*\n\n"
            message += f"It's {temp}°F outside - dress warmly!"
            alert_subtype = 'alert_temperature'
        
        # Extreme heat
        elif temp > 95:
            emoji = "🔥"
            message = f"{emoji} *Extreme Heat Alert*\n\n"
            message += f"It's {temp}°F - stay hydrated and limit outdoor activity!"
            alert_subtype = 'alert_temperature'
        
        # Headache risk
        elif headache_risk == 'high':
            emoji = "🤕"
            message = f"{emoji} *Headache Risk: HIGH*\n\n"
            message += "Pressure changes detected. Consider preventive measures."
            alert_subtype = 'alert_headache'
        
        # UV alert
        elif uv_risk in ['very_high', 'extreme']:
            uv_emoji = '🚨' if uv_risk == 'extreme' else '⚠️'
            message = f"{uv_emoji} *UV Alert: {uv_risk.replace('_', ' ').upper()}*\n\n"
            message += "Avoid direct sun exposure. Sunscreen strongly recommended."
            alert_subtype = 'alert_uv'
        
        # Severe weather
        else:
            emoji = "⛈️"
            message = f"{emoji} *Weather Alert*\n\n"
            message += f"Current conditions: {condition.title()}\n"
            message += "Take appropriate precautions."
            alert_subtype = 'alert_severe'
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='weather',
            notification_subtype=alert_subtype,
            message_text=message,
            message_data={
                'alert_type': alert_subtype,
                'temperature': temp,
                'condition': condition
            }
        )
        
        logger.info(f"✅ Sent weather ALERT: {alert_subtype}")
    
    # =========================================================================
    # FULL FORECASTS (scheduled, comprehensive)
    # =========================================================================
    
    async def _send_weather_forecast(self, weather_data: Dict[str, Any]) -> None:
        """Send a FULL weather forecast briefing"""
        
        location = weather_data['location']
        temp = weather_data['temperature']
        feels_like = weather_data['feels_like']
        condition = weather_data['condition']
        humidity = weather_data['humidity']
        wind_speed = weather_data['wind_speed']
        headache_risk = weather_data.get('headache_risk', None)
        uv_risk = weather_data.get('uv_risk', None)
        
        # Get forecast
        forecast = await self._get_forecast_summary()
        
        # Determine time-appropriate header
        eastern = ZoneInfo('America/New_York')
        now = datetime.now(eastern)
        current_hour = now.hour
        
        if 7 <= current_hour < 10:
            header = "☀️ *Morning Weather Forecast*"
        elif 11 <= current_hour < 14:
            header = "🌤️ *Midday Weather Update*"
        elif 17 <= current_hour < 20:
            header = "🌆 *Evening Weather Forecast*"
        else:
            header = "🌡️ *Weather Update*"
        
        # Weather emoji
        emoji = self._get_weather_emoji(condition)
        
        # Build message
        message = f"{header}\n\n"
        message += f"📍 *{location}*\n"
        message += f"{emoji} {condition}\n\n"
        message += f"🌡️ *Temperature:* {temp}°F (feels like {feels_like}°F)\n"
        message += f"💧 *Humidity:* {humidity}%\n"
        message += f"💨 *Wind:* {wind_speed} mph\n"
        
        # Forecast section
        if forecast:
            message += f"\n*Forecast:*\n{forecast}\n"
        
        # Health alerts section (if any)
        alerts = []
        
        if headache_risk and headache_risk in ['medium', 'high']:
            alerts.append(f"🤕 Headache Risk: {headache_risk.upper()}")
        
        if uv_risk and uv_risk in ['moderate', 'high', 'very_high', 'extreme']:
            uv_display = uv_risk.replace('_', ' ').title()
            alerts.append(f"☀️ UV Index: {uv_display}")
        
        if temp < 32:
            alerts.append("❄️ Freezing - dress warmly!")
        elif temp > 90:
            alerts.append("🥵 Hot - stay hydrated!")
        
        if alerts:
            message += "\n*Alerts:*\n"
            for alert in alerts:
                message += f"• {alert}\n"
        
        # Send via notification manager
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='weather',
            notification_subtype='forecast',
            message_text=message,
            message_data={
                'location': location,
                'temperature': temp,
                'condition': condition,
                'forecast_time': now.isoformat()
            }
        )
        
        logger.info(f"✅ Sent weather FORECAST: {location} - {temp}°F, {condition}")
    
    async def _get_forecast_summary(self) -> Optional[str]:
        """Get brief forecast summary from Tomorrow.io"""
        try:
            from modules.integrations.weather.tomorrow_client import TomorrowClient
            
            client = TomorrowClient()
            forecast_data = await client.get_weather_forecast(days=2)
            
            if not forecast_data or len(forecast_data) == 0:
                return None
            
            # Weather code mappings
            WEATHER_CODES = {
                1000: "Clear", 1100: "Mostly Clear", 1101: "Partly Cloudy",
                1102: "Mostly Cloudy", 1001: "Cloudy", 2000: "Fog",
                4000: "Drizzle", 4001: "Rain", 4200: "Light Rain",
                4201: "Heavy Rain", 5000: "Snow", 5100: "Light Snow",
                5101: "Heavy Snow", 8000: "Thunderstorm"
            }
            
            forecast_lines = []
            
            tomorrow = forecast_data[0] if len(forecast_data) > 0 else None
            day_after = forecast_data[1] if len(forecast_data) > 1 else None
            
            if tomorrow:
                values = tomorrow.get('values', {})
                temp_min_c = values.get('temperatureMin', 0)
                temp_max_c = values.get('temperatureMax', 0)
                temp_min_f = round(temp_min_c * 9/5 + 32)
                temp_max_f = round(temp_max_c * 9/5 + 32)
                weather_code = values.get('weatherCodeMax', 1000)
                condition = WEATHER_CODES.get(weather_code, "Unknown")
                precip_prob = values.get('precipitationProbabilityAvg', 0)
                
                line = f"Tomorrow: {condition}, {temp_min_f}-{temp_max_f}°F"
                if precip_prob > 30:
                    line += f" ({precip_prob:.0f}% precip)"
                forecast_lines.append(line)
            
            if day_after:
                values = day_after.get('values', {})
                temp_min_c = values.get('temperatureMin', 0)
                temp_max_c = values.get('temperatureMax', 0)
                temp_min_f = round(temp_min_c * 9/5 + 32)
                temp_max_f = round(temp_max_c * 9/5 + 32)
                weather_code = values.get('weatherCodeMax', 1000)
                condition = WEATHER_CODES.get(weather_code, "Unknown")
                
                forecast_lines.append(f"Day After: {condition}, {temp_min_f}-{temp_max_f}°F")
            
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
            'mostly clear': '🌤️',
            'cloudy': '☁️',
            'overcast': '☁️',
            'mostly cloudy': '🌥️',
            'rain': '🌧️',
            'drizzle': '🌦️',
            'light rain': '🌦️',
            'heavy rain': '🌧️',
            'snow': '❄️',
            'light snow': '🌨️',
            'heavy snow': '❄️',
            'sleet': '🌨️',
            'storm': '⛈️',
            'thunder': '⛈️',
            'thunderstorm': '⛈️',
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
            
            await self._send_weather_forecast(weather_data)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily forecast: {e}")
            return False
