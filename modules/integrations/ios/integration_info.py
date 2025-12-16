# modules/integrations/ios/integration_info.py
"""
iOS Integration Module Information
Health checks, statistics, and setup instructions.

Follows patterns from telegram, weather, and fathom integrations.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from .database_manager import get_ios_db_manager, DEFAULT_USER_ID

logger = logging.getLogger(__name__)

# =============================================================================
# MODULE METADATA
# =============================================================================

MODULE_NAME = "ios_integration"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "iOS app integration for proactive notifications via local scheduling"

SUPPORTED_NOTIFICATION_TYPES = [
    "prayer",
    "weather",
    "weather_alert",
    "reminder",
    "calendar",
    "email",
    "clickup",
    "bluesky",
    "trends",
    "analytics"
]

ENDPOINTS = {
    "pending_notifications": "/ios/pending-notifications",
    "register_device": "/ios/register-device",
    "ack_notification": "/ios/ack-notification/{id}",
    "context": "/ios/context",
    "health": "/ios/health",
    "devices": "/ios/devices",
    "stats": "/ios/stats",
    "cleanup": "/ios/cleanup"
}


# =============================================================================
# HEALTH CHECK
# =============================================================================

def check_module_health() -> Dict[str, Any]:
    """
    Check if iOS module is properly configured.
    
    Returns health status dict with:
    - healthy: bool
    - missing_vars: list of missing env vars (none required for iOS)
    - configured: bool
    """
    # iOS module doesn't require env vars - it's database-driven
    # Unlike Telegram which needs BOT_TOKEN, iOS uses polling
    
    return {
        'healthy': True,
        'missing_vars': [],
        'configured': True,
        'notes': 'iOS integration uses polling - no API keys required'
    }


async def check_module_health_async() -> Dict[str, Any]:
    """
    Async health check with database connectivity test.
    """
    db = get_ios_db_manager()
    
    try:
        # Test database connectivity
        devices = await db.get_user_devices(DEFAULT_USER_ID)
        stats = await db.get_notification_stats(DEFAULT_USER_ID)
        
        return {
            'healthy': True,
            'database_connected': True,
            'active_devices': len(devices),
            'pending_notifications': stats.get('pending', 0),
            'total_notifications': stats.get('total', 0),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ iOS health check failed: {e}")
        return {
            'healthy': False,
            'database_connected': False,
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


# =============================================================================
# MODULE INFO
# =============================================================================

def get_integration_info() -> Dict[str, Any]:
    """
    Get iOS integration information.
    
    Returns complete module metadata for documentation and debugging.
    """
    return {
        'module': MODULE_NAME,
        'version': MODULE_VERSION,
        'description': MODULE_DESCRIPTION,
        'endpoints': ENDPOINTS,
        'notification_types': SUPPORTED_NOTIFICATION_TYPES,
        'features': [
            'Device registration and management',
            'Notification queue with priority levels',
            'Location context from iOS',
            'HealthKit data integration',
            'Quiet hours support',
            'Per-device notification preferences',
            'Parallel delivery with Telegram',
            'Background fetch support (~15 min polling)',
            'Foreground polling (30 second intervals)'
        ],
        'architecture': {
            'push_method': 'polling',
            'reason': 'No Apple Developer account required',
            'foreground_interval': '30 seconds',
            'background_interval': '~15 minutes (iOS controlled)',
            'notification_delivery': 'Local scheduling via UNUserNotificationCenter'
        },
        'health': check_module_health()
    }


async def get_integration_info_async() -> Dict[str, Any]:
    """
    Get iOS integration info with live statistics.
    """
    info = get_integration_info()
    health = await check_module_health_async()
    info['health'] = health
    info['live_stats'] = {
        'active_devices': health.get('active_devices', 0),
        'pending_notifications': health.get('pending_notifications', 0)
    }
    return info


# =============================================================================
# STATISTICS
# =============================================================================

async def get_notification_statistics() -> Dict[str, Any]:
    """
    Get detailed notification statistics.
    """
    db = get_ios_db_manager()
    
    try:
        stats = await db.get_notification_stats(DEFAULT_USER_ID)
        devices = await db.get_user_devices(DEFAULT_USER_ID)
        
        # Calculate delivery rate
        total = stats.get('total', 0)
        delivered = stats.get('delivered', 0)
        delivery_rate = (delivered / total * 100) if total > 0 else 0
        
        return {
            'notification_counts': stats,
            'delivery_rate_percent': round(delivery_rate, 1),
            'active_devices': len(devices),
            'devices': [
                {
                    'name': d.get('device_name', 'Unknown'),
                    'model': d.get('device_model'),
                    'last_seen': d.get('last_seen_at').isoformat() if d.get('last_seen_at') else None
                }
                for d in devices
            ],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get notification stats: {e}")
        return {'error': str(e)}


# =============================================================================
# SETUP INSTRUCTIONS
# =============================================================================

def get_setup_instructions() -> Dict[str, Any]:
    """
    Get setup instructions for iOS integration.
    """
    return {
        'title': 'iOS App Setup Instructions',
        'overview': '''
The iOS app connects to Syntax Prime V2 backend via polling.
No Apple Developer account is required - uses 7-day sideloading.
''',
        'steps': [
            {
                'step': 1,
                'title': 'Build iOS App',
                'description': 'Open Xcode project and build (⌘+B)',
                'notes': 'Ensure iOS 17+ SDK is installed'
            },
            {
                'step': 2,
                'title': 'Update API URL',
                'description': 'Set baseURL in APIClient.swift to Railway URL',
                'example': 'https://ghostline20-production.up.railway.app'
            },
            {
                'step': 3,
                'title': 'Deploy Backend',
                'description': 'Ensure iOS router is registered in app.py',
                'code': 'from modules.integrations.ios import router as ios_router\napp.include_router(ios_router)'
            },
            {
                'step': 4,
                'title': 'Sideload to iPhone',
                'description': 'Connect iPhone via USB, select as run destination, click Run (⌘+R)',
                'notes': 'Trust developer certificate in Settings > General > VPN & Device Management'
            },
            {
                'step': 5,
                'title': 'Grant Permissions',
                'description': 'Allow notifications, location, and HealthKit when prompted'
            },
            {
                'step': 6,
                'title': 'Test Connection',
                'description': 'Open app, check Settings view shows "Connected"',
                'verify_endpoint': '/ios/health'
            }
        ],
        'troubleshooting': [
            {
                'issue': 'App expires after 7 days',
                'solution': 'Re-build and re-install from Xcode'
            },
            {
                'issue': 'Notifications not appearing',
                'solution': 'Check notification permissions in iOS Settings'
            },
            {
                'issue': 'Background fetch not working',
                'solution': 'Ensure Background App Refresh is enabled for the app'
            },
            {
                'issue': 'API connection failed',
                'solution': 'Verify Railway URL in APIClient.swift and check /ios/health endpoint'
            }
        ],
        'maintenance': {
            'sideload_expiry': '7 days',
            'action_required': 'Re-build from Xcode weekly',
            'tip': 'Set a weekly reminder to refresh the app'
        }
    }