"""
Telegram Integration Info - Health Monitoring & Documentation
Provides system status and integration information
"""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

def get_integration_info() -> Dict[str, Any]:
    """
    Get Telegram integration module information
    
    Returns:
        Module metadata and configuration
    """
    return {
        "name": "Telegram Proactive Notification System",
        "version": "2.0.0",
        "description": "Push notifications for 9 critical life management categories",
        "author": "Syntax Prime V2",
        "created": "2025-10-01",
        
        "notification_types": {
            "prayer": {
                "enabled_by_default": True,
                "description": "Persistent prayer time reminders with follow-ups",
                "polling_frequency": "Every 5 minutes"
            },
            "weather": {
                "enabled_by_default": True,
                "description": "Rain/UV/emergency weather alerts",
                "polling_frequency": "Every 2 hours"
            },
            "reminders": {
                "enabled_by_default": True,
                "description": "Custom user reminders via natural language",
                "polling_frequency": "Every 60 seconds"
            },
            "calendar": {
                "enabled_by_default": False,
                "description": "Google Calendar event reminders",
                "polling_frequency": "Every 30 minutes"
            },
            "email": {
                "enabled_by_default": False,
                "description": "AI-powered urgent email detection",
                "polling_frequency": "Every 1 hour"
            },
            "clickup": {
                "enabled_by_default": False,
                "description": "Task deadline and assignment alerts",
                "polling_frequency": "Every 4 hours"
            },
            "bluesky": {
                "enabled_by_default": False,
                "description": "Social media engagement training interface",
                "polling_frequency": "Event-driven"
            },
            "trends": {
                "enabled_by_default": False,
                "description": "Keyword opportunity training interface",
                "polling_frequency": "Event-driven"
            },
            "analytics": {
                "enabled_by_default": False,
                "description": "Traffic/ranking anomaly detection",
                "polling_frequency": "Every 12 hours"
            }
        },
        
        "safety_features": {
            "global_kill_switch": "Stop all notifications instantly",
            "per_type_kill": "Disable specific notification types",
            "rate_limiting": "Prevent notification spam",
            "quiet_hours": "Default 11pm-7am (configurable)",
            "test_mode": "Development mode with test-only notifications"
        },
        
        "database_tables": [
            "telegram_notifications",
            "telegram_preferences",
            "telegram_reminders",
            "telegram_training_feedback",
            "telegram_kill_switch",
            "telegram_rate_limits"
        ],
        
        "endpoints": {
            "webhook": "/telegram/webhook",
            "test": "/telegram/test/send",
            "health": "/telegram/health",
            "status": "/telegram/status"
        },
        
        "commands": {
            "telegram kill": "Stop all notifications",
            "telegram resume": "Resume notifications",
            "telegram disable [type]": "Disable specific type",
            "telegram enable [type]": "Enable specific type",
            "telegram status": "Show current status"
        }
    }

async def check_module_health() -> Dict[str, Any]:
    """
    Perform health check on all Telegram components
    
    Returns:
        Health status for each component
    """
    health = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "healthy",
        "components": {}
    }
    
    # Check bot client
    try:
        from .bot_client import get_bot_client
        bot_client = get_bot_client()
        connection_test = await bot_client.test_connection()
        
        health["components"]["bot_client"] = {
            "status": "healthy" if connection_test['success'] else "unhealthy",
            "bot_username": connection_test.get('bot_info', {}).get('username'),
            "error": connection_test.get('error')
        }
    except Exception as e:
        health["components"]["bot_client"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["overall_status"] = "unhealthy"
    
    # Check database manager
    try:
        from .database_manager import get_telegram_db_manager
        db_manager = get_telegram_db_manager()
        prefs = await db_manager.get_user_preferences("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")
        
        health["components"]["database_manager"] = {
            "status": "healthy" if prefs else "unhealthy",
            "preferences_loaded": bool(prefs)
        }
    except Exception as e:
        health["components"]["database_manager"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["overall_status"] = "unhealthy"
    
    # Check kill switch
    try:
        from .kill_switch import get_kill_switch
        kill_switch = get_kill_switch()
        status = await kill_switch.get_status("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")
        
        health["components"]["kill_switch"] = {
            "status": "healthy",
            "global_kill_active": status['global_kill_active'],
            "killed_types": status['killed_types']
        }
    except Exception as e:
        health["components"]["kill_switch"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["overall_status"] = "unhealthy"
    
    # Check notification manager
    try:
        from .notification_manager import get_notification_manager
        notification_manager = get_notification_manager()
        
        health["components"]["notification_manager"] = {
            "status": "healthy"
        }
    except Exception as e:
        health["components"]["notification_manager"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health["overall_status"] = "unhealthy"
    
    return health

async def get_notification_statistics(user_id: str) -> Dict[str, Any]:
    """
    Get notification statistics for user
    
    Args:
        user_id: User UUID
    
    Returns:
        Statistics about sent notifications
    """
    try:
        from .database_manager import get_telegram_db_manager
        from .notification_manager import get_notification_manager
        
        db_manager = get_telegram_db_manager()
        notification_manager = get_notification_manager()
        
        # Get rate limit status
        rate_limits = await notification_manager.get_rate_limit_status(user_id)
        
        # Calculate totals
        total_sent = sum(limits['count'] for limits in rate_limits.values())
        total_limit = sum(limits['limit'] for limits in rate_limits.values())
        
        return {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "total_sent_24h": total_sent,
            "total_limit_24h": total_limit,
            "by_type": rate_limits,
            "percentage_used": int((total_sent / total_limit) * 100) if total_limit > 0 else 0
        }
    
    except Exception as e:
        logger.error(f"Failed to get notification statistics: {e}")
        return {
            "error": str(e)
        }

def get_setup_instructions() -> str:
    """
    Get setup instructions for Telegram integration
    
    Returns:
        Markdown-formatted setup guide
    """
    return """
# Telegram Notification System Setup

## Environment Variables Required

Add these to Railway environment:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_WEBHOOK_URL=https://your-domain.railway.app/telegram/webhook
```

## Database Tables

All tables created via local script in `test/create_telegram_tables.py`

## Testing the System

1. Check health: GET /telegram/health
2. Send test notification: POST /telegram/test/send
3. Check status: GET /telegram/status

## Available Commands

Send these as messages to your bot:
- `telegram kill` - Stop all notifications
- `telegram resume` - Resume notifications  
- `telegram disable prayer` - Disable prayer notifications
- `telegram enable prayer` - Enable prayer notifications
- `telegram status` - Show current status

## Enabling Notification Types

By default, only prayer, weather, and reminders are enabled.

To enable additional types:
1. Update `telegram_preferences` table
2. Or send command: `telegram enable [type]`

## Rate Limits (24 hour windows)

- Prayer: 10 notifications
- Weather: 8 notifications
- Reminders: 20 notifications
- Calendar: 50 notifications
- Email: 10 notifications
- ClickUp: 15 notifications
- Bluesky: 15 notifications
- Trends: 15 notifications
- Analytics: 3 notifications

## Quiet Hours

Default: 11pm - 7am (no notifications except emergency weather)
Configurable in `telegram_preferences` table

## Kill Switch Levels

1. **Global Kill**: Stops everything (`telegram kill`)
2. **Type Kill**: Stops specific type (`telegram disable prayer`)
3. **Quiet Hours**: Time-based blocking
4. **Rate Limits**: Automatic spam prevention

## Support

Check health endpoint for diagnostics:
GET /telegram/health
"""