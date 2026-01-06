# modules/integrations/ios/router.py
"""
iOS Integration API Router
Endpoints for iOS app to communicate with Syntax Prime V2 backend.

Endpoints:
- GET  /ios/pending-notifications  - Fetch notifications to schedule locally
- POST /ios/register-device        - Register/update iOS device
- POST /ios/ack-notification/{id}  - Acknowledge notification delivery
- POST /ios/context                - Receive location/health context
- GET  /ios/health                 - Module health check
- GET  /ios/devices                - List registered devices
- GET  /ios/stats                  - Notification statistics
- POST /ios/cleanup                - Cleanup old notifications
- POST /ios/calendar               - Sync calendar events from iOS
- POST /ios/reminders              - Sync reminders from iOS
- POST /ios/contacts               - Sync contacts from iOS
- POST /ios/music                  - Update music context from iOS
- GET  /ios/health-history         - Get health data history for trends
- GET  /ios/workout-history        - Get workout history
- GET  /ios/health-summary         - Get aggregated health summary
- GET  /ios/actions/pending        - Get pending proactive actions (NEW)
- GET  /ios/actions/{queue_id}     - Get action details (NEW)
- POST /ios/actions/{queue_id}/execute  - Execute action (NEW)
- POST /ios/actions/{queue_id}/dismiss  - Dismiss action (NEW)
- POST /ios/actions/{queue_id}/edit     - Edit action draft with AI (NEW)
- GET  /ios/actions/stats          - Get action statistics (NEW)

Authentication:
- All endpoints require X-iOS-Key header matching IOS_API_KEY env var

Updated: 2026-01-06 - Added proactive action endpoints for conversational execution
"""

import os
import json
import logging
from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from pydantic import BaseModel, Field

from .database_manager import get_ios_db_manager, DEFAULT_USER_ID

logger = logging.getLogger(__name__)

# =============================================================================
# API KEY AUTHENTICATION
# =============================================================================

async def verify_ios_api_key(request: Request):
    """
    Verify iOS API key from X-iOS-Key header.
    All /ios/* endpoints require this.
    """
    api_key = os.getenv("IOS_API_KEY")
    
    if not api_key:
        logger.error("❌ IOS_API_KEY environment variable not set")
        raise HTTPException(status_code=500, detail="iOS API key not configured on server")
    
    provided_key = request.headers.get("X-iOS-Key")
    
    if not provided_key:
        logger.warning("⚠️ iOS request missing X-iOS-Key header")
        raise HTTPException(status_code=401, detail="Missing X-iOS-Key header")
    
    if provided_key != api_key:
        logger.warning("⚠️ iOS request with invalid API key")
        raise HTTPException(status_code=401, detail="Invalid iOS API key")
    
    # Key is valid
    return True


# =============================================================================
# ROUTER SETUP
# =============================================================================

router = APIRouter(
    prefix="/ios",
    tags=["iOS Integration"],
    dependencies=[Depends(verify_ios_api_key)],  # All routes require API key
    responses={
        401: {"description": "Invalid or missing API key"},
        404: {"description": "Not found"}
    }
)


# =============================================================================
# PYDANTIC MODELS - EXISTING
# =============================================================================

class DeviceRegistration(BaseModel):
    """Request model for device registration"""
    device_identifier: str = Field(..., description="Stable device ID from iOS")
    device_name: Optional[str] = Field(None, description="User-friendly device name")
    device_model: Optional[str] = Field(None, description="e.g., iPhone 15 Pro")
    os_version: Optional[str] = Field(None, description="e.g., iOS 17.2")
    app_version: Optional[str] = Field(None, description="e.g., 1.0.0")


class DeviceRegistrationResponse(BaseModel):
    """Response model for device registration"""
    success: bool
    device_id: Optional[str] = None
    message: str
    notifications_enabled: bool = True
    notification_types: List[str] = []


class PendingNotification(BaseModel):
    """Model for a pending notification"""
    id: str
    notification_type: str
    title: str
    body: str
    payload: Dict[str, Any] = {}
    priority: str
    scheduled_for: datetime
    expires_at: Optional[datetime] = None
    created_at: datetime


class PendingNotificationsResponse(BaseModel):
    """Response model for pending notifications"""
    success: bool
    notifications: List[PendingNotification] = []
    count: int = 0
    server_time: datetime


class AcknowledgeResponse(BaseModel):
    """Response model for notification acknowledgment"""
    success: bool
    notification_id: str
    message: str


class DeviceContext(BaseModel):
    """Request model for device context update"""
    device_identifier: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    health_data: Optional[Dict[str, Any]] = None


class ContextResponse(BaseModel):
    """Response model for context update"""
    success: bool
    message: str
    updated_fields: List[str] = []


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    module: str
    timestamp: datetime
    database_connected: bool
    active_devices: int
    pending_notifications: int


# =============================================================================
# PYDANTIC MODELS - DATA SYNC (Calendar, Reminders, Contacts, Music)
# =============================================================================

class CalendarEventItem(BaseModel):
    """Single calendar event from iOS"""
    event_id: str = Field(..., description="iOS EventKit identifier")
    title: str = Field(..., description="Event title")
    start_time: str = Field(..., description="ISO datetime string")
    end_time: str = Field(..., description="ISO datetime string")
    location: Optional[str] = Field(None, description="Event location")
    notes: Optional[str] = Field(None, description="Event notes")
    is_all_day: bool = Field(default=False, description="All-day event flag")
    calendar_name: Optional[str] = Field(None, description="Source calendar name")


class CalendarSyncRequest(BaseModel):
    """Request model for calendar sync"""
    device_identifier: str = Field(..., description="iOS device identifier")
    events: List[CalendarEventItem] = Field(..., description="Calendar events to sync")


class CalendarSyncResponse(BaseModel):
    """Response model for calendar sync"""
    success: bool
    synced: int = 0
    failed: int = 0
    message: str


class ReminderItem(BaseModel):
    """Single reminder from iOS"""
    reminder_id: str = Field(..., description="iOS Reminders identifier")
    title: str = Field(..., description="Reminder title")
    notes: Optional[str] = Field(None, description="Reminder notes")
    due_date: Optional[str] = Field(None, description="ISO datetime string")
    is_completed: bool = Field(default=False, description="Completion status")
    completed_at: Optional[str] = Field(None, description="ISO datetime when completed")
    priority: int = Field(default=0, description="Priority 0-9")
    list_name: Optional[str] = Field(None, description="Source list name")


class RemindersSyncRequest(BaseModel):
    """Request model for reminders sync"""
    device_identifier: str = Field(..., description="iOS device identifier")
    reminders: List[ReminderItem] = Field(..., description="Reminders to sync")


class RemindersSyncResponse(BaseModel):
    """Response model for reminders sync"""
    success: bool
    synced: int = 0
    failed: int = 0
    message: str


class ContactItem(BaseModel):
    """Single contact from iOS"""
    contact_id: str = Field(..., description="iOS Contacts identifier")
    given_name: Optional[str] = Field(None, description="First name")
    family_name: Optional[str] = Field(None, description="Last name")
    nickname: Optional[str] = Field(None, description="Nickname")
    organization: Optional[str] = Field(None, description="Company/organization")
    job_title: Optional[str] = Field(None, description="Job title")
    primary_email: Optional[str] = Field(None, description="Primary email address")
    primary_phone: Optional[str] = Field(None, description="Primary phone number")
    birthday: Optional[str] = Field(None, description="ISO date string (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, description="Contact notes")


class ContactsSyncRequest(BaseModel):
    """Request model for contacts sync"""
    device_identifier: str = Field(..., description="iOS device identifier")
    contacts: List[ContactItem] = Field(..., description="Contacts to sync")


class ContactsSyncResponse(BaseModel):
    """Response model for contacts sync"""
    success: bool
    synced: int = 0
    failed: int = 0
    message: str


class MusicContextRequest(BaseModel):
    """Request model for music context update"""
    device_identifier: str = Field(..., description="iOS device identifier")
    track_title: str = Field(..., description="Current track title")
    artist: Optional[str] = Field(None, description="Artist name")
    album: Optional[str] = Field(None, description="Album name")
    genre: Optional[str] = Field(None, description="Music genre")
    duration_seconds: Optional[int] = Field(None, description="Track duration in seconds")
    is_playing: bool = Field(default=True, description="Whether currently playing")
    mood_hint: Optional[str] = Field(None, description="AI-detected mood hint")


class MusicContextResponse(BaseModel):
    """Response model for music context update"""
    success: bool
    message: str
    track_title: Optional[str] = None


# =============================================================================
# PYDANTIC MODELS - PROACTIVE ACTIONS (NEW)
# =============================================================================

class PendingAction(BaseModel):
    """Model for a pending actionable item from unified_proactive_queue"""
    id: str
    source_type: str  # email, trend, meeting, etc.
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    source_title: str
    source_preview: str
    source_metadata: Optional[Dict[str, Any]] = None
    content_type: Optional[str] = None
    draft_title: Optional[str] = None
    draft_text: str
    draft_secondary: Optional[str] = None  # Bluesky post for trends
    draft_structured: Optional[Dict[str, Any]] = None
    business_context: Optional[str] = None
    priority: str = "medium"
    status: str
    created_at: datetime


class PendingActionsResponse(BaseModel):
    """Response model for pending actions list"""
    success: bool
    actions: List[PendingAction] = []
    count: int = 0
    server_time: datetime


class ActionDetailResponse(BaseModel):
    """Response model for single action with full details"""
    success: bool
    action: Optional[PendingAction] = None
    message: Optional[str] = None


class ExecuteActionRequest(BaseModel):
    """Request model for executing an action"""
    edited_text: Optional[str] = Field(None, description="Optional edited draft text")


class ExecuteActionResponse(BaseModel):
    """Response model for action execution"""
    success: bool
    message: str
    action: str
    result: Optional[Dict[str, Any]] = None


class DismissActionRequest(BaseModel):
    """Request model for dismissing an action"""
    reason: Optional[str] = Field(None, description="Optional reason for dismissal")


class EditActionRequest(BaseModel):
    """Request model for editing an action draft"""
    instructions: str = Field(..., description="Instructions for how to edit the draft")


class EditActionResponse(BaseModel):
    """Response model for draft editing"""
    success: bool
    message: str
    action: Optional[PendingAction] = None  # Updated action with new draft


class ActionStatsResponse(BaseModel):
    """Response model for action statistics"""
    success: bool
    stats: Dict[str, Any] = {}
    days: int = 7


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_json_field(value: Any, default: Any = None) -> Any:
    """
    Parse a field that may be returned as a JSON string by asyncpg.
    
    Args:
        value: The value to parse (may be string, dict, list, or None)
        default: Default value if parsing fails
    
    Returns:
        Parsed value or default
    """
    if value is None:
        return default if default is not None else ([] if isinstance(default, list) else {})
    
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except json.JSONDecodeError:
            return default if default is not None else ([] if isinstance(default, list) else {})
    
    return value


# =============================================================================
# ENDPOINTS - NOTIFICATIONS
# =============================================================================

@router.get(
    "/pending-notifications",
    response_model=PendingNotificationsResponse,
    summary="Get pending notifications",
    description="iOS app polls this endpoint to fetch notifications to schedule locally"
)
async def get_pending_notifications(
    device_identifier: str = Query(..., description="Device identifier for filtering"),
    limit: int = Query(20, ge=1, le=50, description="Max notifications to return")
):
    """
    Fetch pending notifications for iOS app.
    
    The iOS app calls this every 30 seconds (foreground) or ~15 minutes (background).
    Returns notifications ready for local scheduling, ordered by priority.
    """
    db = get_ios_db_manager()
    
    try:
        # Update last_seen for this device
        await db.update_last_seen(device_identifier)
        
        # Mark any expired notifications
        await db.mark_expired_notifications()
        
        # Get pending notifications
        notifications = await db.get_pending_notifications(
            user_id=DEFAULT_USER_ID,
            limit=limit
        )
        
        # Convert to response format
        notification_list = []
        for notif in notifications:
            # Handle payload - asyncpg may return JSONB as string
            payload = parse_json_field(notif.get('payload'), default={})
            
            notification_list.append(PendingNotification(
                id=notif['id'],
                notification_type=notif['notification_type'],
                title=notif['title'],
                body=notif['body'],
                payload=payload,
                priority=notif.get('priority', 'medium'),
                scheduled_for=notif['scheduled_for'],
                expires_at=notif.get('expires_at'),
                created_at=notif['created_at']
            ))
        
        logger.debug(f"📱 Returning {len(notification_list)} notifications to {device_identifier}")
        
        return PendingNotificationsResponse(
            success=True,
            notifications=notification_list,
            count=len(notification_list),
            server_time=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get pending notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/register-device",
    response_model=DeviceRegistrationResponse,
    summary="Register iOS device",
    description="Register or update an iOS device for notifications"
)
async def register_device(registration: DeviceRegistration):
    """
    Register an iOS device with the backend.
    
    Called on:
    - First app launch
    - App updates
    - User re-enables notifications
    
    Uses upsert to handle both new and existing devices.
    """
    db = get_ios_db_manager()
    
    try:
        result = await db.register_device(
            device_identifier=registration.device_identifier,
            device_name=registration.device_name,
            device_model=registration.device_model,
            os_version=registration.os_version,
            app_version=registration.app_version,
            user_id=DEFAULT_USER_ID
        )
        
        if result:
            logger.info(f"📱 Device registered: {registration.device_identifier} ({registration.device_model})")
            
            # Handle notification_types - asyncpg may return array as string
            notification_types = parse_json_field(
                result.get('notification_types'),
                default=[]
            )
            
            return DeviceRegistrationResponse(
                success=True,
                device_id=str(result['id']),
                message="Device registered successfully",
                notifications_enabled=result.get('notifications_enabled', True),
                notification_types=notification_types
            )
        else:
            return DeviceRegistrationResponse(
                success=False,
                message="Failed to register device"
            )
            
    except Exception as e:
        logger.error(f"❌ Device registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/ack-notification/{notification_id}",
    response_model=AcknowledgeResponse,
    summary="Acknowledge notification",
    description="Mark notification as delivered or acknowledged by user"
)
async def acknowledge_notification(
    notification_id: str,
    acknowledged: bool = Query(False, description="True if user interacted, False if just delivered")
):
    """
    Acknowledge notification delivery.
    
    Called by iOS app after:
    - Scheduling notification locally (delivered)
    - User taps/interacts with notification (acknowledged)
    
    This helps track delivery rates and user engagement.
    """
    db = get_ios_db_manager()
    
    try:
        # Mark as delivered
        delivered = await db.mark_delivered(notification_id)
        
        # If user acknowledged, mark that too
        if acknowledged:
            await db.mark_acknowledged(notification_id)
        
        if delivered:
            action = "acknowledged" if acknowledged else "delivered"
            logger.debug(f"✅ Notification {notification_id} {action}")
            
            return AcknowledgeResponse(
                success=True,
                notification_id=notification_id,
                message=f"Notification marked as {action}"
            )
        else:
            return AcknowledgeResponse(
                success=False,
                notification_id=notification_id,
                message="Notification not found or already processed"
            )
            
    except Exception as e:
        logger.error(f"❌ Failed to acknowledge notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Update device context",
    description="Receive location and health data from iOS device"
)
async def update_device_context(context: DeviceContext):
    """
    Update device context with location and health data.
    
    iOS app sends this periodically with:
    - Current GPS coordinates
    - Location name (if available)
    - HealthKit summary (steps, heart rate, sleep, workouts, nutrition)
    
    This data is used by the AI for context-aware notifications.
    Also stores health data to history tables for trend tracking.
    """
    db = get_ios_db_manager()
    
    try:
        updated_fields = []
        
        # Track what we're updating
        if context.latitude is not None:
            updated_fields.append("latitude")
        if context.longitude is not None:
            updated_fields.append("longitude")
        if context.location_name is not None:
            updated_fields.append("location_name")
        if context.health_data is not None:
            updated_fields.append("health_data")
        
        # Update current device context (existing behavior)
        success = await db.update_device_context(
            device_identifier=context.device_identifier,
            latitude=context.latitude,
            longitude=context.longitude,
            location_name=context.location_name,
            health_data=context.health_data
        )
        
        # Store health data to history table for trends
        if context.health_data is not None and success:
            try:
                await db.store_daily_health(
                    device_identifier=context.device_identifier,
                    health_data=context.health_data
                )
                logger.debug(f"📊 Stored health history for {context.device_identifier}")
                
                # If there's workout data, store that too
                last_workout = context.health_data.get('last_workout')
                if last_workout and isinstance(last_workout, dict):
                    await db.store_workout(
                        device_identifier=context.device_identifier,
                        workout=last_workout
                    )
                    logger.debug(f"🏋️ Stored workout to history")
            except Exception as hist_error:
                # Don't fail the whole request if history storage fails
                logger.warning(f"⚠️ Failed to store health history: {hist_error}")
        
        if success:
            logger.debug(f"📍 Context updated for {context.device_identifier}: {updated_fields}")
            
            return ContextResponse(
                success=True,
                message="Context updated successfully",
                updated_fields=updated_fields
            )
        else:
            return ContextResponse(
                success=False,
                message="Failed to update context",
                updated_fields=[]
            )
            
    except Exception as e:
        logger.error(f"❌ Failed to update device context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check iOS integration module health"
)
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
    - Module status
    - Database connectivity
    - Active device count
    - Pending notification count
    """
    db = get_ios_db_manager()
    
    try:
        # Get active devices count
        devices = await db.get_user_devices(DEFAULT_USER_ID)
        active_devices = len(devices)
        
        # Get pending notification count
        stats = await db.get_notification_stats(DEFAULT_USER_ID)
        pending_count = stats.get('pending', 0)
        
        return HealthResponse(
            status="healthy",
            module="ios_integration",
            timestamp=datetime.now(timezone.utc),
            database_connected=True,
            active_devices=active_devices,
            pending_notifications=pending_count
        )
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            module="ios_integration",
            timestamp=datetime.now(timezone.utc),
            database_connected=False,
            active_devices=0,
            pending_notifications=0
        )


# =============================================================================
# ENDPOINTS - UTILITY
# =============================================================================

@router.get(
    "/devices",
    summary="List registered devices",
    description="Get all registered iOS devices for the user"
)
async def list_devices():
    """List all registered iOS devices"""
    db = get_ios_db_manager()
    
    try:
        devices = await db.get_user_devices(DEFAULT_USER_ID)
        
        # Convert UUIDs to strings for JSON
        device_list = []
        for d in devices:
            device_list.append({
                'id': str(d['id']),
                'device_identifier': d['device_identifier'],
                'device_name': d.get('device_name'),
                'device_model': d.get('device_model'),
                'os_version': d.get('os_version'),
                'app_version': d.get('app_version'),
                'last_seen_at': d.get('last_seen_at'),
                'notifications_enabled': d.get('notifications_enabled', True),
                'is_active': d.get('is_active', True)
            })
        
        return {
            'success': True,
            'devices': device_list,
            'count': len(device_list)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stats",
    summary="Notification statistics",
    description="Get notification delivery statistics"
)
async def get_stats():
    """Get notification statistics"""
    db = get_ios_db_manager()
    
    try:
        stats = await db.get_notification_stats(DEFAULT_USER_ID)
        devices = await db.get_user_devices(DEFAULT_USER_ID)
        
        return {
            'success': True,
            'notifications': stats,
            'active_devices': len(devices),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cleanup",
    summary="Cleanup old notifications",
    description="Remove old delivered/expired notifications"
)
async def cleanup_notifications(
    days_old: int = Query(7, ge=1, le=30, description="Delete notifications older than this")
):
    """Cleanup old notifications"""
    db = get_ios_db_manager()
    
    try:
        # Mark expired first
        expired = await db.mark_expired_notifications()
        
        # Then cleanup old ones
        deleted = await db.cleanup_old_notifications(days_old=days_old)
        
        return {
            'success': True,
            'expired': expired,
            'deleted': deleted,
            'message': f"Marked {expired} expired, deleted {deleted} old notifications"
        }
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - HEALTH HISTORY
# =============================================================================

@router.get(
    "/health-history",
    summary="Get health history",
    description="Get health data history for trends and analysis"
)
async def get_health_history(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back")
):
    """
    Get health history for the past N days.
    
    Returns daily snapshots including:
    - Steps, calories, heart rate
    - Sleep hours
    - Workout totals
    - Nutrition data
    
    Also returns a summary with averages.
    """
    db = get_ios_db_manager()
    
    try:
        history = await db.get_health_history(days=days)
        summary = await db.get_health_summary(days=days)
        
        return {
            'success': True,
            'days_requested': days,
            'days_with_data': len(history),
            'history': history,
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get health history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/workout-history",
    summary="Get workout history",
    description="Get workout history for the past N days"
)
async def get_workout_history(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    workout_type: Optional[str] = Query(None, description="Filter by workout type (e.g., 'Running', 'Yoga')")
):
    """
    Get workout history for the past N days.
    
    Can optionally filter by workout type.
    
    Returns list of workouts with:
    - Type (Running, Yoga, Strength Training, etc.)
    - Duration in minutes
    - Calories burned
    - Distance (if applicable)
    - Start/end times
    """
    db = get_ios_db_manager()
    
    try:
        workouts = await db.get_workout_history(
            days=days,
            workout_type=workout_type
        )
        
        # Calculate summary stats
        total_minutes = sum(w.get('duration_minutes', 0) or 0 for w in workouts)
        total_calories = sum(w.get('calories_burned', 0) or 0 for w in workouts)
        
        # Count by type
        type_counts = {}
        for w in workouts:
            wtype = w.get('workout_type', 'Unknown')
            type_counts[wtype] = type_counts.get(wtype, 0) + 1
        
        return {
            'success': True,
            'days_requested': days,
            'workout_count': len(workouts),
            'filter': workout_type,
            'summary': {
                'total_workouts': len(workouts),
                'total_minutes': total_minutes,
                'total_calories': total_calories,
                'by_type': type_counts
            },
            'workouts': workouts
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get workout history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health-summary",
    summary="Get health summary",
    description="Get aggregated health summary for AI context"
)
async def get_health_summary_endpoint(
    days: int = Query(7, ge=1, le=30, description="Number of days to summarize")
):
    """
    Get aggregated health summary.
    
    Returns averages and totals useful for AI context:
    - Average daily steps
    - Average sleep hours
    - Total workout minutes
    - Workout frequency
    - Average calories consumed
    """
    db = get_ios_db_manager()
    
    try:
        summary = await db.get_health_summary(days=days)
        
        return {
            'success': True,
            'days': days,
            'summary': summary
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get health summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - DATA SYNC (Calendar, Reminders, Contacts, Music)
# =============================================================================

@router.post(
    "/calendar",
    response_model=CalendarSyncResponse,
    summary="Sync calendar events",
    description="Receive calendar events from iOS device"
)
async def sync_calendar(request: CalendarSyncRequest):
    """
    Sync calendar events from iOS device.
    
    iOS app sends calendar events periodically or on-demand.
    Uses UPSERT to handle new and updated events.
    
    This data is used by the AI for:
    - Context-aware responses ("You have a meeting in 30 minutes")
    - Scheduling suggestions
    - Daily briefings
    """
    db = get_ios_db_manager()
    
    try:
        # Update last_seen for this device
        await db.update_last_seen(request.device_identifier)
        
        # Convert Pydantic models to dicts
        events_data = [event.model_dump() for event in request.events]
        
        # Sync to database
        result = await db.sync_calendar_events(
            device_identifier=request.device_identifier,
            events=events_data,
            user_id=DEFAULT_USER_ID
        )
        
        synced = result.get('synced', 0)
        failed = result.get('failed', 0)
        
        logger.info(f"📅 Calendar sync from {request.device_identifier}: {synced} synced, {failed} failed")
        
        return CalendarSyncResponse(
            success=True,
            synced=synced,
            failed=failed,
            message=f"Synced {synced} calendar events" + (f", {failed} failed" if failed > 0 else "")
        )
        
    except Exception as e:
        logger.error(f"❌ Calendar sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/reminders",
    response_model=RemindersSyncResponse,
    summary="Sync reminders",
    description="Receive reminders from iOS device"
)
async def sync_reminders(request: RemindersSyncRequest):
    """
    Sync reminders from iOS device.
    
    iOS app sends reminders periodically or on-demand.
    Uses UPSERT to handle new and updated reminders.
    
    This data is used by the AI for:
    - Task awareness ("Don't forget to pick up groceries")
    - Priority management
    - Proactive reminders
    """
    db = get_ios_db_manager()
    
    try:
        # Update last_seen for this device
        await db.update_last_seen(request.device_identifier)
        
        # Convert Pydantic models to dicts
        reminders_data = [reminder.model_dump() for reminder in request.reminders]
        
        # Sync to database
        result = await db.sync_reminders(
            device_identifier=request.device_identifier,
            reminders=reminders_data,
            user_id=DEFAULT_USER_ID
        )
        
        synced = result.get('synced', 0)
        failed = result.get('failed', 0)
        
        logger.info(f"✅ Reminders sync from {request.device_identifier}: {synced} synced, {failed} failed")
        
        return RemindersSyncResponse(
            success=True,
            synced=synced,
            failed=failed,
            message=f"Synced {synced} reminders" + (f", {failed} failed" if failed > 0 else "")
        )
        
    except Exception as e:
        logger.error(f"❌ Reminders sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/contacts",
    response_model=ContactsSyncResponse,
    summary="Sync contacts",
    description="Receive contacts from iOS device"
)
async def sync_contacts(request: ContactsSyncRequest):
    """
    Sync contacts from iOS device.
    
    iOS app sends contacts on first sync or when changes detected.
    Uses UPSERT to handle new and updated contacts.
    
    This data is used by the AI for:
    - Name recognition in conversations
    - Contact lookups ("What's John's phone number?")
    - Birthday reminders
    """
    db = get_ios_db_manager()
    
    try:
        # Update last_seen for this device
        await db.update_last_seen(request.device_identifier)
        
        # Convert Pydantic models to dicts
        contacts_data = [contact.model_dump() for contact in request.contacts]
        
        # Sync to database
        result = await db.sync_contacts(
            device_identifier=request.device_identifier,
            contacts=contacts_data,
            user_id=DEFAULT_USER_ID
        )
        
        synced = result.get('synced', 0)
        failed = result.get('failed', 0)
        
        logger.info(f"👥 Contacts sync from {request.device_identifier}: {synced} synced, {failed} failed")
        
        return ContactsSyncResponse(
            success=True,
            synced=synced,
            failed=failed,
            message=f"Synced {synced} contacts" + (f", {failed} failed" if failed > 0 else "")
        )
        
    except Exception as e:
        logger.error(f"❌ Contacts sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/music",
    response_model=MusicContextResponse,
    summary="Update music context",
    description="Receive currently playing music from iOS device"
)
async def update_music_context(request: MusicContextRequest):
    """
    Update currently playing music from iOS device.
    
    iOS app sends this when music playback changes.
    Uses UPSERT - one row per user/device.
    
    This data is used by the AI for:
    - Mood-aware responses
    - Music recommendations
    - Context awareness ("I see you're listening to jazz...")
    """
    db = get_ios_db_manager()
    
    try:
        # Update last_seen for this device
        await db.update_last_seen(request.device_identifier)
        
        if request.is_playing:
            # Update music context
            success = await db.update_music_context(
                device_identifier=request.device_identifier,
                track_title=request.track_title,
                artist=request.artist,
                album=request.album,
                genre=request.genre,
                duration_seconds=request.duration_seconds,
                is_playing=request.is_playing,
                mood_hint=request.mood_hint,
                user_id=DEFAULT_USER_ID
            )
            
            if success:
                logger.debug(f"🎵 Music updated: {request.track_title} by {request.artist}")
                return MusicContextResponse(
                    success=True,
                    message="Music context updated",
                    track_title=request.track_title
                )
            else:
                return MusicContextResponse(
                    success=False,
                    message="Failed to update music context"
                )
        else:
            # Music stopped - clear context
            await db.clear_music_context(
                device_identifier=request.device_identifier,
                user_id=DEFAULT_USER_ID
            )
            
            logger.debug(f"🎵 Music stopped for {request.device_identifier}")
            return MusicContextResponse(
                success=True,
                message="Music playback stopped"
            )
        
    except Exception as e:
        logger.error(f"❌ Music context update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/music",
    summary="Clear music context",
    description="Clear music context when playback stops"
)
async def clear_music_context(
    device_identifier: str = Query(..., description="iOS device identifier")
):
    """
    Clear music context when playback stops.
    Alternative to POST with is_playing=False.
    """
    db = get_ios_db_manager()
    
    try:
        await db.clear_music_context(
            device_identifier=device_identifier,
            user_id=DEFAULT_USER_ID
        )
        
        return {
            'success': True,
            'message': 'Music context cleared'
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to clear music context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - PROACTIVE ACTIONS (NEW)
# =============================================================================

@router.get(
    "/actions/pending",
    response_model=PendingActionsResponse,
    summary="Get pending actions",
    description="Fetch actionable items from the proactive queue (email replies, posts, etc.)"
)
async def get_pending_actions(
    limit: int = Query(20, ge=1, le=50, description="Max actions to return")
):
    """
    Fetch pending actionable items for iOS.
    
    These are AI-generated drafts ready for user action:
    - Email replies ready to send
    - Bluesky posts ready to publish  
    - Meeting summaries with action items
    - Trend content with blog outlines
    
    iOS polls this to show notification badges and populate action views.
    """
    db = get_ios_db_manager()
    
    try:
        actions = await db.get_pending_actions(
            user_id=DEFAULT_USER_ID,
            limit=limit
        )
        
        # Convert to response format
        action_list = []
        for action in actions:
            action_list.append(PendingAction(
                id=action['id'],
                source_type=action['source_type'],
                source_id=action.get('source_id'),
                source_url=action.get('source_url'),
                source_title=action['source_title'],
                source_preview=action.get('source_preview', ''),
                source_metadata=action.get('source_metadata'),
                content_type=action.get('content_type'),
                draft_title=action.get('draft_title'),
                draft_text=action['draft_text'],
                draft_secondary=action.get('draft_secondary'),
                draft_structured=action.get('draft_structured'),
                business_context=action.get('business_context'),
                priority=action.get('priority', 'medium'),
                status=action['status'],
                created_at=action['created_at']
            ))
        
        logger.debug(f"📋 Returning {len(action_list)} pending actions")
        
        return PendingActionsResponse(
            success=True,
            actions=action_list,
            count=len(action_list),
            server_time=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get pending actions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/actions/stats",
    response_model=ActionStatsResponse,
    summary="Get action statistics",
    description="Get action statistics for understanding patterns"
)
async def get_action_stats(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze")
):
    """
    Get action statistics for the past N days.
    
    Useful for:
    - Understanding action patterns
    - Auto-execution eligibility
    - Usage analytics
    """
    db = get_ios_db_manager()
    
    try:
        stats = await db.get_action_stats(
            user_id=DEFAULT_USER_ID,
            days=days
        )
        
        return ActionStatsResponse(
            success=True,
            stats=stats,
            days=days
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get action stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/actions/{queue_id}",
    response_model=ActionDetailResponse,
    summary="Get action details",
    description="Get full details for a specific action (for conversation display)"
)
async def get_action_details(queue_id: str):
    """
    Get full action details for conversation display.
    
    Called when user taps notification to open ActionConversationView.
    Returns complete draft, context, and source info.
    """
    db = get_ios_db_manager()
    
    try:
        action = await db.get_action_by_id(queue_id)
        
        if not action:
            return ActionDetailResponse(
                success=False,
                message="Action not found"
            )
        
        return ActionDetailResponse(
            success=True,
            action=PendingAction(
                id=action['id'],
                source_type=action['source_type'],
                source_id=action.get('source_id'),
                source_url=action.get('source_url'),
                source_title=action['source_title'],
                source_preview=action.get('source_preview', ''),
                source_metadata=action.get('source_metadata'),
                content_type=action.get('content_type'),
                draft_title=action.get('draft_title'),
                draft_text=action['draft_text'],
                draft_secondary=action.get('draft_secondary'),
                draft_structured=action.get('draft_structured'),
                business_context=action.get('business_context'),
                priority=action.get('priority', 'medium'),
                status=action['status'],
                created_at=action['created_at']
            )
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get action details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/actions/{queue_id}/execute",
    response_model=ExecuteActionResponse,
    summary="Execute action",
    description="Execute the action (send email, post to Bluesky, etc.)"
)
async def execute_action(
    queue_id: str,
    request: Optional[ExecuteActionRequest] = None
):
    """
    Execute the action on a pending item.
    
    This calls unified_engine.execute_action() which routes to:
    - _execute_send_email() for email replies
    - _execute_bluesky_post() for trend posts
    - _execute_create_tasks() for meeting action items
    
    Optionally accepts edited_text if user modified the draft.
    """
    try:
        from modules.proactive.unified_engine import get_unified_engine
        
        engine = get_unified_engine()
        
        # Determine action type from the queue item
        db = get_ios_db_manager()
        action_item = await db.get_action_by_id(queue_id)
        
        if not action_item:
            return ExecuteActionResponse(
                success=False,
                message="Action not found",
                action="unknown"
            )
        
        # Map source_type to action
        source_type = action_item['source_type']
        if source_type == 'email':
            action = 'send'
        elif source_type == 'trend':
            action = 'post'
        elif source_type == 'meeting':
            action = 'tasks'
        else:
            action = 'action'  # Generic
        
        # Get edited text if provided
        edited_text = request.edited_text if request else None
        
        # Execute via unified engine
        result = await engine.execute_action(
            queue_id=queue_id,
            action=action,
            edited_text=edited_text
        )
        
        if result.get('success'):
            logger.info(f"✅ Action executed: {action} for {queue_id}")
            return ExecuteActionResponse(
                success=True,
                message=result.get('message', 'Action completed'),
                action=action,
                result=result
            )
        else:
            return ExecuteActionResponse(
                success=False,
                message=result.get('message', 'Action failed'),
                action=action,
                result=result
            )
        
    except Exception as e:
        logger.error(f"❌ Failed to execute action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/actions/{queue_id}/dismiss",
    response_model=ExecuteActionResponse,
    summary="Dismiss action",
    description="Dismiss/skip an action without executing"
)
async def dismiss_action(
    queue_id: str,
    request: Optional[DismissActionRequest] = None
):
    """
    Dismiss an action (user said "skip" or "ignore").
    
    This is a simple dismissal. For email ignore with sender tracking,
    use execute with action='ignore' instead.
    """
    db = get_ios_db_manager()
    
    try:
        reason = request.reason if request else None
        success = await db.dismiss_action(queue_id, reason)
        
        if success:
            logger.info(f"⏭️ Action dismissed: {queue_id}")
            return ExecuteActionResponse(
                success=True,
                message="Action dismissed",
                action="dismiss"
            )
        else:
            return ExecuteActionResponse(
                success=False,
                message="Failed to dismiss action",
                action="dismiss"
            )
        
    except Exception as e:
        logger.error(f"❌ Failed to dismiss action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/actions/{queue_id}/edit",
    response_model=EditActionResponse,
    summary="Edit action draft",
    description="Edit the draft with AI (e.g., 'make it shorter', 'more casual')"
)
async def edit_action_draft(
    queue_id: str,
    request: EditActionRequest
):
    """
    Edit an action's draft using AI.
    
    User provides instructions like:
    - "make it shorter"
    - "more professional tone"
    - "add a question about timing"
    
    Claude rewrites the draft and returns the updated action.
    """
    try:
        from modules.ai.openrouter_client import get_openrouter_client
        
        db = get_ios_db_manager()
        
        # Get current action
        action_item = await db.get_action_by_id(queue_id)
        
        if not action_item:
            return EditActionResponse(
                success=False,
                message="Action not found"
            )
        
        # Get OpenRouter client for AI editing
        ai_client = get_openrouter_client()
        
        # Build prompt for editing
        source_type = action_item['source_type']
        current_draft = action_item['draft_text']
        instructions = request.instructions
        
        if source_type == 'email':
            edit_prompt = f"""You are editing an email reply draft. 

Current draft:
{current_draft}

User's editing instructions: {instructions}

Rewrite the email following the user's instructions. Return ONLY the new email text, no explanations."""

        elif source_type == 'trend':
            edit_prompt = f"""You are editing a social media post.

Current draft:
{current_draft}

User's editing instructions: {instructions}

Rewrite the post following the user's instructions. Keep it under 280 characters for Bluesky. Return ONLY the new post text, no explanations."""

        else:
            edit_prompt = f"""You are editing content.

Current draft:
{current_draft}

User's editing instructions: {instructions}

Rewrite the content following the user's instructions. Return ONLY the new text, no explanations."""

        # Call AI to rewrite
        response = await ai_client.chat(
            messages=[{"role": "user", "content": edit_prompt}],
            task_type="heavy"  # Use Claude for quality editing
        )
        
        new_draft = response.get('content', '').strip()
        
        if not new_draft:
            return EditActionResponse(
                success=False,
                message="AI failed to generate new draft"
            )
        
        # Update the draft in database
        await db.update_action_draft(
            queue_id=queue_id,
            new_draft_text=new_draft
        )
        
        # Return updated action
        updated_action = await db.get_action_by_id(queue_id)
        
        return EditActionResponse(
            success=True,
            message="Draft updated",
            action=PendingAction(
                id=updated_action['id'],
                source_type=updated_action['source_type'],
                source_id=updated_action.get('source_id'),
                source_url=updated_action.get('source_url'),
                source_title=updated_action['source_title'],
                source_preview=updated_action.get('source_preview', ''),
                source_metadata=updated_action.get('source_metadata'),
                content_type=updated_action.get('content_type'),
                draft_title=updated_action.get('draft_title'),
                draft_text=updated_action['draft_text'],
                draft_secondary=updated_action.get('draft_secondary'),
                draft_structured=updated_action.get('draft_structured'),
                business_context=updated_action.get('business_context'),
                priority=updated_action.get('priority', 'medium'),
                status=updated_action['status'],
                created_at=updated_action['created_at']
            )
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to edit action draft: {e}")
        raise HTTPException(status_code=500, detail=str(e))
