# modules/integrations/ios/__init__.py
"""
iOS Integration Module for Syntax Prime V2
Proactive notifications via local scheduling on iPhone.

This module enables the iOS app to:
- Poll for pending notifications
- Register device info
- Send location and health context
- Acknowledge notification delivery

Architecture:
- No Apple Developer account required (7-day sideloading)
- Polling-based (no APNs push)
- Parallel with Telegram (both receive notifications)
- Background Fetch every ~15 min, foreground every 30 sec

Usage:
    # Queue a notification for iOS
    from modules.integrations.ios import queue_ios_notification
    
    await queue_ios_notification(
        notification_type="prayer",
        title="🕌 Maghrib Prayer",
        body="Maghrib in 15 minutes"
    )
    
    # Or use convenience functions
    from modules.integrations.ios import queue_prayer_notification
    
    await queue_prayer_notification(
        title="🕌 Maghrib Prayer",
        body="Maghrib in 15 minutes",
        prayer_name="Maghrib",
        prayer_time="5:45 PM"
    )
"""

import logging

from .database_manager import (
    iOSDatabaseManager,
    get_ios_db_manager,
    DEFAULT_USER_ID
)

from .notification_sender import (
    queue_ios_notification,
    queue_prayer_notification,
    queue_weather_notification,
    queue_reminder_notification,
    queue_calendar_notification,
    queue_email_notification,
    queue_clickup_notification,
    queue_bluesky_notification,
    queue_trends_notification,
    queue_analytics_notification,
    get_priority_for_type,
    get_expiry_hours_for_type
)

from .router import router

from .integration_info import (
    MODULE_NAME,
    MODULE_VERSION,
    MODULE_DESCRIPTION,
    SUPPORTED_NOTIFICATION_TYPES,
    ENDPOINTS,
    check_module_health,
    check_module_health_async,
    get_integration_info,
    get_integration_info_async,
    get_notification_statistics,
    get_setup_instructions
)

logger = logging.getLogger(__name__)

# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Database manager
    'iOSDatabaseManager',
    'get_ios_db_manager',
    'DEFAULT_USER_ID',
    
    # Notification sender - main function
    'queue_ios_notification',
    
    # Notification sender - convenience functions
    'queue_prayer_notification',
    'queue_weather_notification',
    'queue_reminder_notification',
    'queue_calendar_notification',
    'queue_email_notification',
    'queue_clickup_notification',
    'queue_bluesky_notification',
    'queue_trends_notification',
    'queue_analytics_notification',
    
    # Notification utilities
    'get_priority_for_type',
    'get_expiry_hours_for_type',
    
    # Router
    'router',
    
    # Info functions
    'check_module_health',
    'check_module_health_async',
    'get_integration_info',
    'get_integration_info_async',
    'get_notification_statistics',
    'get_setup_instructions',
    
    # Constants
    'MODULE_NAME',
    'MODULE_VERSION',
    'SUPPORTED_NOTIFICATION_TYPES',
    'ENDPOINTS'
]

__version__ = MODULE_VERSION
__description__ = MODULE_DESCRIPTION
__author__ = "Syntax Prime V2"


# =============================================================================
# MODULE REGISTRATION
# =============================================================================

def register_with_app(app):
    """
    Register iOS integration module with the main FastAPI app.
    
    Follows established pattern from telegram, fathom, slack_clickup modules.
    
    Usage in app.py:
        from modules.integrations.ios import register_with_app as register_ios
        register_ios(app)
    
    Or simply:
        from modules.integrations.ios import router as ios_router
        app.include_router(ios_router)
    """
    # Include the router
    app.include_router(router)
    
    # Add startup event
    @app.on_event("startup")
    async def startup_ios_integration():
        try:
            health = check_module_health()
            if health['healthy']:
                logger.info(f"✅ {MODULE_NAME} integration loaded successfully")
                logger.info(f"   📱 iOS endpoints available at /ios/*")
                logger.info(f"   🔔 Notification types: {', '.join(SUPPORTED_NOTIFICATION_TYPES)}")
            else:
                logger.warning(f"⚠️ {MODULE_NAME} integration loaded with warnings")
        except Exception as e:
            logger.error(f"❌ {MODULE_NAME} startup failed: {e}")
    
    return {
        'module': MODULE_NAME,
        'version': MODULE_VERSION,
        'router_prefix': '/ios',
        'status': 'registered',
        'endpoints': list(ENDPOINTS.keys())
    }