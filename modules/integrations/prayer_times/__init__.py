# modules/integrations/prayer_times/__init__.py
"""
Prayer Times Integration Module for Syntax Prime V2
Islamic prayer times with intelligent scheduling
"""

from .router import router, get_integration_info, check_module_health
from .database_manager import get_prayer_database_manager, get_next_prayer, get_todays_prayers

# Public API - what other modules can import
__all__ = [
    'router',
    'get_integration_info',
    'check_module_health',
    'get_prayer_database_manager',
    'get_next_prayer',
    'get_todays_prayers'
]

# Module metadata
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'Islamic prayer times with intelligent scheduling'
