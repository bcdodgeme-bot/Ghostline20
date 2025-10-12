"""
Telegram Proactive Notification System
Push notifications for 9 critical life management categories

This module transforms Syntax Prime V2 from a reactive chat assistant 
into a proactive personal operating system with Telegram notifications.
"""

from .bot_client import TelegramBotClient
from .database_manager import TelegramDatabaseManager
from .kill_switch import KillSwitch
from .notification_manager import NotificationManager
from .message_formatter import MessageFormatter
from .callback_handler import CallbackHandler
from .router import router
from .integration_info import (
    get_integration_info,
    check_module_health,
    get_notification_statistics,
    get_setup_instructions
)

__all__ = [
    # Core classes
    'TelegramBotClient',
    'TelegramDatabaseManager',
    'TelegramKillSwitch',
    'NotificationManager',
    'MessageFormatter',
    'CallbackHandler',
        
    # Router
    'router',
    
    # Info functions
    'get_integration_info',
    'check_module_health',
    'get_notification_statistics',
    'get_setup_instructions'
]

__version__ = "2.0.0"
__description__ = "Telegram proactive notification system with AI-powered safety controls"
__author__ = "Syntax Prime V2"

# Module metadata
MODULE_NAME = 'telegram_notifications'
INTEGRATION_TYPE = 'notification_system'
NOTIFICATION_TYPES = [
    'prayer',
    'weather', 
    'reminders',
    'calendar',
    'email',
    'clickup',
    'bluesky',
    'trends',
    'analytics'
]
