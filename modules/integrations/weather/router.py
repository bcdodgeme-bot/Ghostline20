# modules/integrations/weather/router.py
"""
Weather API Router - FastAPI endpoints for weather data
Provides endpoints for current conditions, health alerts, and integration
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import Optional

from ...core.database import db_manager
from .tomorrow_client import TomorrowClient
from .weather_processor import WeatherProcessor
from .health_monitor import HealthMonitor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/weather", tags=["weather"])

# Lazy initialization - singletons created on first use
_client: Optional[TomorrowClient] = None
_processor: Optional[WeatherProcessor] = None
_health_monitor: Optional[HealthMonitor] = None


def get_client() -> TomorrowClient:
    """Get or create TomorrowClient singleton"""
    global _client
    if _client is None:
        _client = TomorrowClient()
    return _client


def get_processor() -> WeatherProcessor:
    """Get or create WeatherProcessor singleton"""
    global _processor
    if _processor is None:
        _processor = WeatherProcessor()
    return _processor


def get_health_monitor() -> HealthMonitor:
    """Get or create HealthMonitor singleton"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


@router.get("/current")
async def get_current_weather(user_id: str, location: Optional[str] = None):
    """Get current weather conditions with health monitoring"""
    try:
        client = get_client()
        processor = get_processor()
        health_monitor = get_health_monitor()
        
        # Fetch weather data from Tomorrow.io
        weather_data = await client.get_current_weather(location)
        
        # Store reading with health calculations
        reading_id = await processor.store_weather_reading(user_id, weather_data, location)
        
        # Get pressure history for context
        previous_pressure = await health_monitor.get_pressure_history(user_id, 3)
        current_pressure = float(weather_data.get("pressureSurfaceLevel", 0))
        pressure_change = (current_pressure - previous_pressure) if previous_pressure else None
        
        # Calculate health risks
        uv_index = float(weather_data.get("uvIndex", 0))
        headache_risk, uv_risk = health_monitor.calculate_health_risks(uv_index, pressure_change)
        
        # Generate alerts
        enhanced_data = {**weather_data, 'pressure_change_3h': pressure_change, 'uv_index': uv_index}
        alerts = health_monitor.generate_health_alerts(enhanced_data, headache_risk, uv_risk)
        
        return {
            'status': 'success',
            'data': {
                'reading_id': reading_id,
                'current_conditions': processor.format_weather_summary(weather_data),
                'temperature_f': weather_data.get("temperature", 0) * 9/5 + 32,
                'pressure': current_pressure,
                'pressure_change_3h': pressure_change,
                'uv_index': uv_index,
                'headache_risk': headache_risk,
                'uv_risk': uv_risk,
                'health_alerts': alerts
            }
        }
        
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{user_id}")
async def get_health_alerts(user_id: str):
    """Get current health alerts based on latest weather reading"""
    try:
        health_monitor = get_health_monitor()
        
        # Get latest weather reading for user
        query = """
            SELECT pressure_change_3h, uv_index, headache_risk_level, uv_risk_level
            FROM weather_readings 
            WHERE user_id = $1 
            ORDER BY timestamp DESC 
            LIMIT 1;
        """
        
        result = await db_manager.fetch_one(query, user_id)
        
        if not result:
            return {'alerts': [], 'message': 'No weather data available'}
        
        # Generate current alerts
        weather_data = {
            'pressure_change_3h': float(result['pressure_change_3h']) if result['pressure_change_3h'] else None,
            'uv_index': float(result['uv_index'])
        }
        
        alerts = health_monitor.generate_health_alerts(
            weather_data, result['headache_risk_level'], result['uv_risk_level']
        )
        
        return {'alerts': alerts, 'health_status': 'monitoring'}
        
    except Exception as e:
        logger.error(f"Health alerts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_weather_status():
    """Get weather service status"""
    client = get_client()
    return {
        'api_configured': bool(client.api_key),
        'default_location': client.default_location,
        'health_monitoring': True,
        'status': 'operational' if client.api_key else 'api_key_missing'
    }


@router.on_event("shutdown")
async def cleanup():
    """Clean up resources"""
    if _client is not None:
        await _client.close()
