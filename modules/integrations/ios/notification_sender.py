# modules/integrations/ios/notification_sender.py
"""
iOS Notification Sender
Queues notifications for iOS app to poll and schedule locally.

This runs parallel to Telegram notifications - when Telegram sends,
iOS queues for the next poll cycle.

Usage:
    from modules.integrations.ios.notification_sender import queue_ios_notification
    
    await queue_ios_notification(
        notification_type="prayer",
        title="🕌 Maghrib Prayer",
        body="Maghrib prayer time in 15 minutes",
        payload={"action": "open_prayer"}
    )
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .database_manager import get_ios_db_manager, DEFAULT_USER_ID

logger = logging.getLogger(__name__)


# =============================================================================
# PRIORITY MAPPING
# =============================================================================

# Map notification types to default priorities
NOTIFICATION_PRIORITIES = {
    # Critical - time-sensitive, safety-related
    'weather_alert': 'critical',
    'emergency': 'critical',
    
    # High - time-sensitive, actionable
    'prayer': 'high',
    'reminder': 'high',
    'calendar': 'high',
    'clickup': 'high',
    
    # Medium - informational but important
    'email': 'medium',
    'bluesky': 'medium',
    'trends': 'medium',
    
    # Low - digest/summary style
    'analytics': 'low',
    'digest': 'low',
    'weather': 'low',  # Regular weather (not alerts)
}

# Default expiration times by type (in hours)
NOTIFICATION_EXPIRY = {
    'prayer': 2,          # Prayer times are time-sensitive
    'reminder': 24,       # Reminders stay for a day
    'calendar': 4,        # Calendar events expire after event
    'weather_alert': 6,   # Weather alerts have limited relevance
    'weather': 12,        # Regular weather updates
    'email': 48,          # Emails can wait
    'clickup': 24,        # Tasks stay relevant
    'bluesky': 12,        # Social engagement windows
    'trends': 24,         # Trends analysis
    'analytics': 48,      # Analytics summaries
}


# =============================================================================
# MAIN NOTIFICATION FUNCTION
# =============================================================================

async def queue_ios_notification(
    notification_type: str,
    title: str,
    body: str,
    payload: Optional[Dict[str, Any]] = None,
    priority: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    device_id: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
    respect_quiet_hours: bool = True,
    respect_preferences: bool = True
) -> Dict[str, Any]:
    """
    Queue a notification for iOS delivery.
    
    Args:
        notification_type: Type of notification (prayer, weather, reminder, etc.)
        title: Notification title (shown in iOS notification)
        body: Notification body text
        payload: Optional dict with action data, deep links, etc.
        priority: Override default priority (critical, high, medium, low)
        scheduled_for: When to deliver (default: now)
        expires_at: When notification becomes stale (default: based on type)
        device_id: Specific device UUID (default: all devices)
        user_id: User UUID (default: Carl's UUID)
        respect_quiet_hours: Skip if device in quiet hours
        respect_preferences: Skip if notification type disabled
    
    Returns:
        Dict with success status and notification IDs
    """
    db = get_ios_db_manager()
    results = {
        'success': False,
        'queued': 0,
        'skipped': 0,
        'notification_ids': [],
        'errors': []
    }
    
    try:
        # Determine priority if not specified
        if priority is None:
            priority = get_priority_for_type(notification_type)
        
        # Calculate expiration if not specified
        if expires_at is None:
            expiry_hours = NOTIFICATION_EXPIRY.get(notification_type, 24)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
        
        # Build payload with type info
        full_payload = {
            'type': notification_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **(payload or {})
        }
        
        # If specific device requested, queue just for that device
        if device_id:
            device = await db.get_device_by_id(device_id)
            if device:
                should_send, reason = await should_send_to_device(
                    device,
                    notification_type,
                    respect_quiet_hours,
                    respect_preferences
                )
                
                if should_send:
                    notif_id = await db.create_notification(
                        notification_type=notification_type,
                        title=title,
                        body=body,
                        payload=full_payload,
                        priority=priority,
                        scheduled_for=scheduled_for,
                        expires_at=expires_at,
                        device_id=device_id,
                        user_id=user_id
                    )
                    if notif_id:
                        results['queued'] += 1
                        results['notification_ids'].append(notif_id)
                else:
                    results['skipped'] += 1
                    logger.debug(f"⏭️ Skipped device {device_id}: {reason}")
            else:
                results['errors'].append(f"Device not found: {device_id}")
        
        else:
            # Queue for all user's active devices
            devices = await db.get_user_devices(user_id)
            
            if not devices:
                logger.warning(f"📱 No active iOS devices for user {user_id}")
                results['errors'].append("No active iOS devices")
                return results
            
            for device in devices:
                should_send, reason = await should_send_to_device(
                    device,
                    notification_type,
                    respect_quiet_hours,
                    respect_preferences
                )
                
                if should_send:
                    notif_id = await db.create_notification(
                        notification_type=notification_type,
                        title=title,
                        body=body,
                        payload=full_payload,
                        priority=priority,
                        scheduled_for=scheduled_for,
                        expires_at=expires_at,
                        device_id=str(device['id']),
                        user_id=user_id
                    )
                    if notif_id:
                        results['queued'] += 1
                        results['notification_ids'].append(notif_id)
                else:
                    results['skipped'] += 1
                    logger.debug(f"⏭️ Skipped device {device['device_identifier']}: {reason}")
        
        results['success'] = results['queued'] > 0
        
        if results['queued'] > 0:
            logger.info(f"📬 Queued {results['queued']} iOS notification(s): {notification_type}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Failed to queue iOS notification: {e}")
        results['errors'].append(str(e))
        return results


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def should_send_to_device(
    device: Dict[str, Any],
    notification_type: str,
    respect_quiet_hours: bool = True,
    respect_preferences: bool = True
) -> tuple[bool, str]:
    """
    Check if notification should be sent to a device.
    
    Returns:
        Tuple of (should_send: bool, reason: str)
    """
    db = get_ios_db_manager()
    
    # Check if notifications enabled at all
    if not device.get('notifications_enabled', True):
        return False, "notifications_disabled"
    
    # Check notification type preference
    if respect_preferences:
        allowed_types = device.get('notification_types', [])
        if allowed_types and notification_type not in allowed_types:
            return False, f"type_not_allowed:{notification_type}"
    
    # Check quiet hours (skip for critical notifications)
    if respect_quiet_hours:
        priority = get_priority_for_type(notification_type)
        if priority != 'critical':
            is_quiet = await db.is_quiet_hours(device['device_identifier'])
            if is_quiet:
                return False, "quiet_hours"
    
    return True, "ok"


def get_priority_for_type(notification_type: str) -> str:
    """Get default priority for a notification type"""
    return NOTIFICATION_PRIORITIES.get(notification_type, 'medium')


def get_expiry_hours_for_type(notification_type: str) -> int:
    """Get default expiry hours for a notification type"""
    return NOTIFICATION_EXPIRY.get(notification_type, 24)


# =============================================================================
# CONVENIENCE FUNCTIONS FOR SPECIFIC NOTIFICATION TYPES
# =============================================================================

async def queue_prayer_notification(
    title: str,
    body: str,
    prayer_name: str,
    prayer_time: str,
    **kwargs
) -> Dict[str, Any]:
    """Queue a prayer notification"""
    return await queue_ios_notification(
        notification_type="prayer",
        title=title,
        body=body,
        payload={
            "action": "open_prayer",
            "prayer_name": prayer_name,
            "prayer_time": prayer_time
        },
        **kwargs
    )


async def queue_weather_notification(
    title: str,
    body: str,
    is_alert: bool = False,
    weather_data: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a weather notification"""
    return await queue_ios_notification(
        notification_type="weather_alert" if is_alert else "weather",
        title=title,
        body=body,
        payload={
            "action": "open_weather",
            "is_alert": is_alert,
            "weather_data": weather_data or {}
        },
        **kwargs
    )


async def queue_reminder_notification(
    title: str,
    body: str,
    reminder_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a reminder notification"""
    return await queue_ios_notification(
        notification_type="reminder",
        title=title,
        body=body,
        payload={
            "action": "open_reminder",
            "reminder_id": reminder_id
        },
        **kwargs
    )


async def queue_calendar_notification(
    title: str,
    body: str,
    event_id: Optional[str] = None,
    event_time: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a calendar notification"""
    return await queue_ios_notification(
        notification_type="calendar",
        title=title,
        body=body,
        payload={
            "action": "open_calendar",
            "event_id": event_id,
            "event_time": event_time
        },
        **kwargs
    )


async def queue_email_notification(
    title: str,
    body: str,
    email_id: Optional[str] = None,
    sender: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue an email notification"""
    return await queue_ios_notification(
        notification_type="email",
        title=title,
        body=body,
        payload={
            "action": "open_email",
            "email_id": email_id,
            "sender": sender
        },
        **kwargs
    )


async def queue_clickup_notification(
    title: str,
    body: str,
    task_id: Optional[str] = None,
    task_url: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a ClickUp task notification"""
    return await queue_ios_notification(
        notification_type="clickup",
        title=title,
        body=body,
        payload={
            "action": "open_clickup",
            "task_id": task_id,
            "task_url": task_url
        },
        **kwargs
    )


async def queue_bluesky_notification(
    title: str,
    body: str,
    post_uri: Optional[str] = None,
    engagement_type: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a Bluesky notification"""
    return await queue_ios_notification(
        notification_type="bluesky",
        title=title,
        body=body,
        payload={
            "action": "open_bluesky",
            "post_uri": post_uri,
            "engagement_type": engagement_type
        },
        **kwargs
    )


async def queue_trends_notification(
    title: str,
    body: str,
    trend_data: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue a Google Trends notification"""
    return await queue_ios_notification(
        notification_type="trends",
        title=title,
        body=body,
        payload={
            "action": "open_trends",
            "trend_data": trend_data or {}
        },
        **kwargs
    )


async def queue_analytics_notification(
    title: str,
    body: str,
    report_type: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Queue an analytics notification"""
    return await queue_ios_notification(
        notification_type="analytics",
        title=title,
        body=body,
        payload={
            "action": "open_analytics",
            "report_type": report_type
        },
        **kwargs
    )