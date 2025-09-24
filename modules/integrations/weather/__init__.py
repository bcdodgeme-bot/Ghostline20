# modules/integrations/weather/__init__.py
"""
Weather Integration Module for Syntax Prime V2
Health-focused weather monitoring with Tomorrow.io API
"""

from .tomorrow_client import TomorrowClient
from .health_monitor import HealthMonitor
from .weather_processor import WeatherProcessor
from .router import router

__version__ = "1.0.0"
__description__ = "Weather integration with health monitoring for headaches and UV sensitivity"

__all__ = ['TomorrowClient', 'HealthMonitor', 'WeatherProcessor', 'router']

def check_module_health() -> dict:
    """Check if weather module is properly configured"""
    import os
    
    api_key = os.getenv('TOMORROW_IO_API_KEY')
    location = os.getenv('DEFAULT_WEATHER_LOCATION', '38.8606,-77.2287')
    
    return {
        'healthy': bool(api_key),
        'missing_vars': [] if api_key else ['TOMORROW_IO_API_KEY'],
        'default_location': location,
        'configured': bool(api_key)
    }

def get_integration_info() -> dict:
    """Get weather integration information"""
    return {
        'module': 'weather',
        'version': __version__,
        'description': __description__,
        'endpoints': {
            'current': '/integrations/weather/current',
            'alerts': '/integrations/weather/alerts/{user_id}',
            'status': '/integrations/weather/status'
        },
        'features': [
            'Pressure tracking for headache prediction',
            'UV monitoring for sun sensitivity',
            'Health alerts and notifications',
            'Integration with Tomorrow.io API',
            'Database storage of weather history'
        ],
        'health': check_module_health()
    }