# modules/integrations/ios/database_manager.py
"""
iOS Integration Database Manager
Handles ios_devices, ios_pending_notifications, and iOS sync tables:
- ios_calendar_events
- ios_reminders
- ios_contacts
- ios_music_context
- ios_health_daily
- ios_workout_history

Also handles proactive actions from unified_proactive_queue for iOS.

Follows established patterns:
- Singleton with _instance + get_ios_db_manager() getter
- Uses db_manager for all database operations
- Parameterized SQL queries
- Timezone-aware datetimes

Updated: 2026-01-06 - Added proactive action methods for iOS conversational execution
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import json

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

# Single-user system - Carl's UUID
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"


class iOSDatabaseManager:
    """Database operations for iOS integration"""
    
    _instance = None
    
    def __init__(self):
        self.db = db_manager
    
    # =========================================================================
    # DEVICE MANAGEMENT
    # =========================================================================
    
    async def register_device(
        self,
        device_identifier: str,
        device_name: Optional[str] = None,
        device_model: Optional[str] = None,
        os_version: Optional[str] = None,
        app_version: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID
    ) -> Optional[Dict[str, Any]]:
        """
        Register or update an iOS device.
        Uses UPSERT to handle both new and existing devices.
        """
        try:
            query = """
                INSERT INTO ios_devices (
                    user_id, device_identifier, device_name, 
                    device_model, os_version, app_version,
                    last_seen_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
                ON CONFLICT (device_identifier) DO UPDATE SET
                    device_name = COALESCE(EXCLUDED.device_name, ios_devices.device_name),
                    device_model = COALESCE(EXCLUDED.device_model, ios_devices.device_model),
                    os_version = COALESCE(EXCLUDED.os_version, ios_devices.os_version),
                    app_version = COALESCE(EXCLUDED.app_version, ios_devices.app_version),
                    last_seen_at = EXCLUDED.last_seen_at,
                    updated_at = EXCLUDED.updated_at,
                    is_active = TRUE
                RETURNING id, user_id, device_identifier, device_name, 
                          device_model, os_version, app_version,
                          notifications_enabled, notification_types,
                          created_at, updated_at
            """
            
            now = datetime.now(timezone.utc)
            result = await self.db.fetch_one(
                query,
                UUID(user_id), device_identifier, device_name,
                device_model, os_version, app_version, now
            )
            
            if result:
                logger.info(f"📱 iOS device registered: {device_identifier}")
                return dict(result)
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to register iOS device: {e}")
            return None
    
    async def get_device(
        self,
        device_identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Get device by identifier"""
        try:
            query = """
                SELECT * FROM ios_devices 
                WHERE device_identifier = $1 AND is_active = TRUE
            """
            result = await self.db.fetch_one(query, device_identifier)
            return dict(result) if result else None
            
        except Exception as e:
            logger.error(f"❌ Failed to get iOS device: {e}")
            return None
    
    async def get_device_by_id(
        self,
        device_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get device by UUID"""
        try:
            query = """
                SELECT * FROM ios_devices 
                WHERE id = $1 AND is_active = TRUE
            """
            result = await self.db.fetch_one(query, UUID(device_id))
            return dict(result) if result else None
            
        except Exception as e:
            logger.error(f"❌ Failed to get iOS device by ID: {e}")
            return None
    
    async def update_device_context(
        self,
        device_identifier: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        location_name: Optional[str] = None,
        health_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update device location and health context"""
        try:
            # Build dynamic update
            updates = ["last_seen_at = $2", "updated_at = $2"]
            params = [device_identifier, datetime.now(timezone.utc)]
            param_idx = 3
            
            if latitude is not None:
                updates.append(f"last_latitude = ${param_idx}")
                params.append(latitude)
                param_idx += 1
            
            if longitude is not None:
                updates.append(f"last_longitude = ${param_idx}")
                params.append(longitude)
                param_idx += 1
            
            if location_name is not None:
                updates.append(f"last_location_name = ${param_idx}")
                params.append(location_name)
                param_idx += 1
            
            if health_data is not None:
                updates.append(f"last_health_data = ${param_idx}")
                params.append(json.dumps(health_data))  # Serialize dict to JSON string for PostgreSQL
                param_idx += 1
            
            query = f"""
                UPDATE ios_devices 
                SET {', '.join(updates)}
                WHERE device_identifier = $1
            """
            
            await self.db.execute(query, *params)
            logger.debug(f"📍 Updated context for device: {device_identifier}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update device context: {e}")
            return False
    
    async def update_last_seen(self, device_identifier: str) -> bool:
        """Touch last_seen_at timestamp"""
        try:
            query = """
                UPDATE ios_devices 
                SET last_seen_at = $2, updated_at = $2
                WHERE device_identifier = $1
            """
            now = datetime.now(timezone.utc)
            await self.db.execute(query, device_identifier, now)
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update last_seen: {e}")
            return False
    
    async def get_user_devices(
        self,
        user_id: str = DEFAULT_USER_ID
    ) -> List[Dict[str, Any]]:
        """Get all active devices for a user"""
        try:
            query = """
                SELECT * FROM ios_devices 
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY last_seen_at DESC
            """
            results = await self.db.fetch_all(query, UUID(user_id))
            return [dict(r) for r in results]
            
        except Exception as e:
            logger.error(f"❌ Failed to get user devices: {e}")
            return []
    
    async def get_device_preferences(
        self,
        device_identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Get notification preferences for a device"""
        try:
            query = """
                SELECT notifications_enabled, notification_types,
                       quiet_hours_start, quiet_hours_end
                FROM ios_devices 
                WHERE device_identifier = $1 AND is_active = TRUE
            """
            result = await self.db.fetch_one(query, device_identifier)
            return dict(result) if result else None
            
        except Exception as e:
            logger.error(f"❌ Failed to get device preferences: {e}")
            return None
    
    async def update_device_preferences(
        self,
        device_identifier: str,
        notifications_enabled: Optional[bool] = None,
        notification_types: Optional[List[str]] = None,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None
    ) -> bool:
        """Update notification preferences for a device"""
        try:
            updates = ["updated_at = $2"]
            params = [device_identifier, datetime.now(timezone.utc)]
            param_idx = 3
            
            if notifications_enabled is not None:
                updates.append(f"notifications_enabled = ${param_idx}")
                params.append(notifications_enabled)
                param_idx += 1
            
            if notification_types is not None:
                updates.append(f"notification_types = ${param_idx}")
                params.append(notification_types)
                param_idx += 1
            
            if quiet_hours_start is not None:
                updates.append(f"quiet_hours_start = ${param_idx}")
                params.append(quiet_hours_start)
                param_idx += 1
            
            if quiet_hours_end is not None:
                updates.append(f"quiet_hours_end = ${param_idx}")
                params.append(quiet_hours_end)
                param_idx += 1
            
            query = f"""
                UPDATE ios_devices 
                SET {', '.join(updates)}
                WHERE device_identifier = $1
            """
            
            await self.db.execute(query, *params)
            logger.info(f"⚙️ Updated preferences for device: {device_identifier}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update device preferences: {e}")
            return False
    
    # =========================================================================
    # NOTIFICATION MANAGEMENT
    # =========================================================================
    
    async def create_notification(
        self,
        notification_type: str,
        title: str,
        body: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: str = "medium",
        scheduled_for: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        device_id: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID
    ) -> Optional[str]:
        """
        Create a pending notification for iOS delivery.
        Returns notification ID if successful.
        """
        try:
            now = datetime.now(timezone.utc)
            
            query = """
                INSERT INTO ios_pending_notifications (
                    user_id, device_id, notification_type,
                    title, body, payload, priority,
                    scheduled_for, expires_at, status, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', $10)
                RETURNING id
            """
            
            result = await self.db.fetch_one(
                query,
                UUID(user_id),
                UUID(device_id) if device_id else None,
                notification_type,
                title,
                body,
                payload or {},
                priority,
                scheduled_for or now,
                expires_at
            )
            
            if result:
                notification_id = str(result['id'])
                logger.info(f"📬 Created iOS notification: {notification_type} - {title[:50]}")
                return notification_id
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to create iOS notification: {e}")
            return None
    
    async def get_pending_notifications(
        self,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get pending notifications ready for delivery.
        Filters by scheduled_for <= now and status = pending.
        """
        try:
            query = """
                SELECT id, notification_type, title, body, payload,
                       priority, scheduled_for, expires_at, created_at
                FROM ios_pending_notifications
                WHERE user_id = $1 
                  AND status = 'pending'
                  AND scheduled_for <= $2
                  AND (expires_at IS NULL OR expires_at > $2)
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        WHEN 'low' THEN 4 
                    END,
                    scheduled_for ASC
                LIMIT $3
            """
            
            now = datetime.now(timezone.utc)
            results = await self.db.fetch_all(query, UUID(user_id), now, limit)
            
            notifications = []
            for r in results:
                notif = dict(r)
                # Convert UUID to string for JSON serialization
                notif['id'] = str(notif['id'])
                notifications.append(notif)
            
            return notifications
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending notifications: {e}")
            return []
    
    async def mark_delivered(
        self,
        notification_id: str
    ) -> bool:
        """Mark notification as delivered"""
        try:
            query = """
                UPDATE ios_pending_notifications
                SET status = 'delivered', delivered_at = $2
                WHERE id = $1
            """
            now = datetime.now(timezone.utc)
            await self.db.execute(query, UUID(notification_id), now)
            logger.debug(f"✅ Marked notification delivered: {notification_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to mark delivered: {e}")
            return False
    
    async def mark_acknowledged(
        self,
        notification_id: str
    ) -> bool:
        """Mark notification as acknowledged by user"""
        try:
            query = """
                UPDATE ios_pending_notifications
                SET acknowledged_at = $2
                WHERE id = $1
            """
            now = datetime.now(timezone.utc)
            await self.db.execute(query, UUID(notification_id), now)
            logger.debug(f"👆 Marked notification acknowledged: {notification_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to mark acknowledged: {e}")
            return False
    
    async def mark_expired_notifications(self) -> int:
        """Mark expired notifications. Returns count of expired."""
        try:
            query = """
                UPDATE ios_pending_notifications
                SET status = 'expired'
                WHERE status = 'pending' 
                  AND expires_at IS NOT NULL 
                  AND expires_at < $1
            """
            now = datetime.now(timezone.utc)
            result = await self.db.execute(query, now)
            
            # Extract count from "UPDATE X" result
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"⏰ Marked {count} notifications as expired")
            return count
            
        except Exception as e:
            logger.error(f"❌ Failed to mark expired: {e}")
            return 0
    
    async def cleanup_old_notifications(
        self,
        days_old: int = 7
    ) -> int:
        """Delete old delivered/expired notifications"""
        try:
            query = """
                DELETE FROM ios_pending_notifications
                WHERE status IN ('delivered', 'expired', 'dismissed')
                  AND created_at < $1
            """
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
            result = await self.db.execute(query, cutoff)
            
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"🧹 Cleaned up {count} old iOS notifications")
            return count
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old notifications: {e}")
            return 0
    
    async def get_notification_stats(
        self,
        user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, Any]:
        """Get notification statistics"""
        try:
            query = """
                SELECT 
                    status,
                    COUNT(*) as count
                FROM ios_pending_notifications
                WHERE user_id = $1
                GROUP BY status
            """
            results = await self.db.fetch_all(query, UUID(user_id))
            
            stats = {
                'pending': 0,
                'delivered': 0,
                'expired': 0,
                'dismissed': 0
            }
            for r in results:
                stats[r['status']] = r['count']
            
            stats['total'] = sum(stats.values())
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get notification stats: {e}")
            return {'error': str(e)}
    
    # =========================================================================
    # QUIET HOURS CHECK
    # =========================================================================
    
    async def is_quiet_hours(
        self,
        device_identifier: str
    ) -> bool:
        """Check if device is currently in quiet hours"""
        try:
            prefs = await self.get_device_preferences(device_identifier)
            if not prefs:
                return False
            
            start = prefs.get('quiet_hours_start')
            end = prefs.get('quiet_hours_end')
            
            if not start or not end:
                return False
            
            now = datetime.now().time()
            
            # Handle overnight quiet hours (e.g., 22:00 - 07:00)
            if start > end:
                return now >= start or now <= end
            else:
                return start <= now <= end
                
        except Exception as e:
            logger.error(f"❌ Failed to check quiet hours: {e}")
            return False

    # =========================================================================
    # iOS CALENDAR SYNC
    # =========================================================================
    
    async def sync_calendar_events(
        self,
        device_identifier: str,
        events: List[Dict[str, Any]],
        user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, int]:
        """
        Sync calendar events from iOS device.
        Uses UPSERT to handle new and updated events.
        """
        synced = 0
        failed = 0
        now = datetime.now(timezone.utc)
        
        for event in events:
            try:
                # Parse datetime strings
                start_time = event.get('start_time')
                end_time = event.get('end_time')
                
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if isinstance(end_time, str):
                    end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                
                query = """
                    INSERT INTO ios_calendar_events (
                        user_id, device_identifier, event_id,
                        title, start_time, end_time,
                        location, notes, is_all_day, calendar_name,
                        synced_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
                    ON CONFLICT (user_id, event_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        location = EXCLUDED.location,
                        notes = EXCLUDED.notes,
                        is_all_day = EXCLUDED.is_all_day,
                        calendar_name = EXCLUDED.calendar_name,
                        synced_at = EXCLUDED.synced_at,
                        updated_at = EXCLUDED.updated_at
                """
                
                await self.db.execute(
                    query,
                    UUID(user_id),
                    device_identifier,
                    event['event_id'],
                    event['title'],
                    start_time,
                    end_time,
                    event.get('location'),
                    event.get('notes'),
                    event.get('is_all_day', False),
                    event.get('calendar_name'),
                    now
                )
                synced += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to sync calendar event {event.get('event_id')}: {e}")
                failed += 1
        
        logger.info(f"📅 iOS calendar sync: {synced} synced, {failed} failed")
        return {'synced': synced, 'failed': failed}
    
    async def query_ios_calendar(
        self,
        user_id: str = DEFAULT_USER_ID,
        days_ahead: int = 7,
        days_behind: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Query iOS calendar events for memory layer."""
        try:
            query = """
                SELECT 
                    event_id,
                    title,
                    start_time,
                    end_time,
                    location,
                    notes,
                    is_all_day,
                    calendar_name,
                    synced_at
                FROM ios_calendar_events
                WHERE user_id = $1
                  AND start_time >= NOW() - INTERVAL '1 day' * $2
                  AND start_time <= NOW() + INTERVAL '1 day' * $3
                ORDER BY start_time ASC
                LIMIT $4
            """
            
            results = await self.db.fetch_all(
                query,
                UUID(user_id),
                days_behind,
                days_ahead,
                limit
            )
            
            events = [dict(r) for r in results]
            logger.debug(f"📱 Found {len(events)} iOS calendar events")
            return events
            
        except Exception as e:
            logger.error(f"❌ Failed to query iOS calendar: {e}")
            return []

    # =========================================================================
    # iOS REMINDERS SYNC
    # =========================================================================
    
    async def sync_reminders(
        self,
        device_identifier: str,
        reminders: List[Dict[str, Any]],
        user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, int]:
        """Sync reminders from iOS device."""
        synced = 0
        failed = 0
        now = datetime.now(timezone.utc)
        
        for reminder in reminders:
            try:
                # Parse datetime strings
                due_date = reminder.get('due_date')
                completed_at = reminder.get('completed_at')
                
                if isinstance(due_date, str):
                    due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                if isinstance(completed_at, str):
                    completed_at = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                
                query = """
                    INSERT INTO ios_reminders (
                        user_id, device_identifier, reminder_id,
                        title, notes, due_date,
                        is_completed, completed_at, priority, list_name,
                        synced_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
                    ON CONFLICT (user_id, reminder_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        notes = EXCLUDED.notes,
                        due_date = EXCLUDED.due_date,
                        is_completed = EXCLUDED.is_completed,
                        completed_at = EXCLUDED.completed_at,
                        priority = EXCLUDED.priority,
                        list_name = EXCLUDED.list_name,
                        synced_at = EXCLUDED.synced_at,
                        updated_at = EXCLUDED.updated_at
                """
                
                await self.db.execute(
                    query,
                    UUID(user_id),
                    device_identifier,
                    reminder['reminder_id'],
                    reminder['title'],
                    reminder.get('notes'),
                    due_date,
                    reminder.get('is_completed', False),
                    completed_at,
                    reminder.get('priority', 0),
                    reminder.get('list_name'),
                    now
                )
                synced += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to sync reminder {reminder.get('reminder_id')}: {e}")
                failed += 1
        
        logger.info(f"✅ iOS reminders sync: {synced} synced, {failed} failed")
        return {'synced': synced, 'failed': failed}
    
    async def query_ios_reminders(
        self,
        user_id: str = DEFAULT_USER_ID,
        include_completed: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Query iOS reminders for memory layer."""
        try:
            where_clause = "user_id = $1"
            params = [UUID(user_id)]
            param_idx = 1
            
            if not include_completed:
                where_clause += " AND is_completed = FALSE"
            
            param_idx += 1
            params.append(limit)
            
            query = f"""
                SELECT 
                    reminder_id,
                    title,
                    notes,
                    due_date,
                    is_completed,
                    completed_at,
                    priority,
                    list_name,
                    synced_at
                FROM ios_reminders
                WHERE {where_clause}
                ORDER BY 
                    CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
                    due_date ASC,
                    priority DESC
                LIMIT ${param_idx}
            """
            
            results = await self.db.fetch_all(query, *params)
            
            reminders = [dict(r) for r in results]
            logger.debug(f"📱 Found {len(reminders)} iOS reminders")
            return reminders
            
        except Exception as e:
            logger.error(f"❌ Failed to query iOS reminders: {e}")
            return []

    # =========================================================================
    # iOS CONTACTS SYNC
    # =========================================================================
    
    async def sync_contacts(
        self,
        device_identifier: str,
        contacts: List[Dict[str, Any]],
        user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, int]:
        """Sync contacts from iOS device."""
        synced = 0
        failed = 0
        now = datetime.now(timezone.utc)
        
        for contact in contacts:
            try:
                # Build full_name
                given = contact.get('given_name', '') or ''
                family = contact.get('family_name', '') or ''
                full_name = f"{given} {family}".strip() or contact.get('nickname') or 'Unknown'
                
                # Parse birthday
                birthday = contact.get('birthday')
                if isinstance(birthday, str):
                    try:
                        birthday = datetime.fromisoformat(birthday).date()
                    except ValueError:
                        birthday = None
                
                query = """
                    INSERT INTO ios_contacts (
                        user_id, device_identifier, contact_id,
                        given_name, family_name, nickname,
                        organization, job_title,
                        primary_email, primary_phone,
                        birthday, notes, full_name,
                        synced_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (user_id, contact_id) DO UPDATE SET
                        given_name = EXCLUDED.given_name,
                        family_name = EXCLUDED.family_name,
                        nickname = EXCLUDED.nickname,
                        organization = EXCLUDED.organization,
                        job_title = EXCLUDED.job_title,
                        primary_email = EXCLUDED.primary_email,
                        primary_phone = EXCLUDED.primary_phone,
                        birthday = EXCLUDED.birthday,
                        notes = EXCLUDED.notes,
                        full_name = EXCLUDED.full_name,
                        synced_at = EXCLUDED.synced_at
                """
                
                await self.db.execute(
                    query,
                    UUID(user_id),
                    device_identifier,
                    contact['contact_id'],
                    contact.get('given_name'),
                    contact.get('family_name'),
                    contact.get('nickname'),
                    contact.get('organization'),
                    contact.get('job_title'),
                    contact.get('primary_email'),
                    contact.get('primary_phone'),
                    birthday,
                    contact.get('notes'),
                    full_name,
                    now
                )
                synced += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to sync contact {contact.get('contact_id')}: {e}")
                failed += 1
        
        logger.info(f"👥 iOS contacts sync: {synced} synced, {failed} failed")
        return {'synced': synced, 'failed': failed}
    
    async def query_ios_contacts(
        self,
        user_id: str = DEFAULT_USER_ID,
        search_term: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query iOS contacts for memory layer."""
        try:
            params = [UUID(user_id)]
            param_idx = 1
            
            where_clause = "user_id = $1"
            
            if search_term:
                param_idx += 1
                search_pattern = f"%{search_term}%"
                where_clause += f"""
                    AND (
                        full_name ILIKE ${param_idx}
                        OR primary_email ILIKE ${param_idx}
                        OR organization ILIKE ${param_idx}
                        OR nickname ILIKE ${param_idx}
                    )
                """
                params.append(search_pattern)
            
            param_idx += 1
            params.append(limit)
            
            query = f"""
                SELECT 
                    contact_id,
                    given_name,
                    family_name,
                    nickname,
                    full_name,
                    organization,
                    job_title,
                    primary_email,
                    primary_phone,
                    birthday,
                    notes,
                    synced_at
                FROM ios_contacts
                WHERE {where_clause}
                ORDER BY full_name ASC
                LIMIT ${param_idx}
            """
            
            results = await self.db.fetch_all(query, *params)
            
            contacts = [dict(r) for r in results]
            logger.debug(f"👥 Found {len(contacts)} iOS contacts")
            return contacts
            
        except Exception as e:
            logger.error(f"❌ Failed to query iOS contacts: {e}")
            return []

    # =========================================================================
    # iOS MUSIC CONTEXT
    # =========================================================================
    
    async def update_music_context(
        self,
        device_identifier: str,
        track_title: str,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        is_playing: bool = True,
        mood_hint: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID
    ) -> bool:
        """Update current music context from iOS device."""
        try:
            now = datetime.now(timezone.utc)
            
            query = """
                INSERT INTO ios_music_context (
                    user_id, device_identifier,
                    track_title, artist, album, genre,
                    duration_seconds, is_playing, mood_hint,
                    started_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
                ON CONFLICT (user_id, device_identifier) DO UPDATE SET
                    track_title = EXCLUDED.track_title,
                    artist = EXCLUDED.artist,
                    album = EXCLUDED.album,
                    genre = EXCLUDED.genre,
                    duration_seconds = EXCLUDED.duration_seconds,
                    is_playing = EXCLUDED.is_playing,
                    mood_hint = EXCLUDED.mood_hint,
                    started_at = CASE 
                        WHEN ios_music_context.track_title != EXCLUDED.track_title 
                        THEN EXCLUDED.started_at 
                        ELSE ios_music_context.started_at 
                    END,
                    updated_at = EXCLUDED.updated_at
            """
            
            await self.db.execute(
                query,
                UUID(user_id),
                device_identifier,
                track_title,
                artist,
                album,
                genre,
                duration_seconds,
                is_playing,
                mood_hint,
                now
            )
            
            logger.debug(f"🎵 Updated music context: {track_title} by {artist}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update music context: {e}")
            return False
    
    async def get_current_music(
        self,
        user_id: str = DEFAULT_USER_ID
    ) -> Optional[Dict[str, Any]]:
        """Get current music context for memory layer."""
        try:
            query = """
                SELECT 
                    track_title,
                    artist,
                    album,
                    genre,
                    duration_seconds,
                    is_playing,
                    mood_hint,
                    started_at,
                    updated_at
                FROM ios_music_context
                WHERE user_id = $1
                  AND is_playing = TRUE
                  AND updated_at >= NOW() - INTERVAL '30 minutes'
                ORDER BY updated_at DESC
                LIMIT 1
            """
            
            result = await self.db.fetch_one(query, UUID(user_id))
            
            if result:
                music = dict(result)
                logger.debug(f"🎵 Current music: {music['track_title']} by {music['artist']}")
                return music
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get current music: {e}")
            return None
    
    async def clear_music_context(
        self,
        device_identifier: str,
        user_id: str = DEFAULT_USER_ID
    ) -> bool:
        """Mark music as stopped (is_playing = FALSE)."""
        try:
            query = """
                UPDATE ios_music_context
                SET is_playing = FALSE, updated_at = $3
                WHERE user_id = $1 AND device_identifier = $2
            """
            
            now = datetime.now(timezone.utc)
            await self.db.execute(query, UUID(user_id), device_identifier, now)
            
            logger.debug(f"🎵 Cleared music context for {device_identifier}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to clear music context: {e}")
            return False

    # =========================================================================
    # HEALTH HISTORY TRACKING
    # =========================================================================
    
    async def store_daily_health(
        self,
        device_identifier: str,
        health_data: Dict[str, Any],
        user_id: str = DEFAULT_USER_ID
    ) -> bool:
        """Store or update daily health snapshot."""
        try:
            today = datetime.now(timezone.utc).date()
            
            query = """
                INSERT INTO ios_health_daily (
                    user_id, device_identifier, date,
                    step_count, active_calories, sleep_hours, sleep_end_time,
                    heart_rate_avg, workout_minutes, workout_calories, workout_count,
                    calories_consumed, protein_grams, carbs_grams, fat_grams,
                    water_liters, caffeine_mg, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW())
                ON CONFLICT (user_id, device_identifier, date) DO UPDATE SET
                    step_count = COALESCE(EXCLUDED.step_count, ios_health_daily.step_count),
                    active_calories = COALESCE(EXCLUDED.active_calories, ios_health_daily.active_calories),
                    sleep_hours = COALESCE(EXCLUDED.sleep_hours, ios_health_daily.sleep_hours),
                    sleep_end_time = COALESCE(EXCLUDED.sleep_end_time, ios_health_daily.sleep_end_time),
                    heart_rate_avg = COALESCE(EXCLUDED.heart_rate_avg, ios_health_daily.heart_rate_avg),
                    workout_minutes = COALESCE(EXCLUDED.workout_minutes, ios_health_daily.workout_minutes),
                    workout_calories = COALESCE(EXCLUDED.workout_calories, ios_health_daily.workout_calories),
                    workout_count = COALESCE(EXCLUDED.workout_count, ios_health_daily.workout_count),
                    calories_consumed = COALESCE(EXCLUDED.calories_consumed, ios_health_daily.calories_consumed),
                    protein_grams = COALESCE(EXCLUDED.protein_grams, ios_health_daily.protein_grams),
                    carbs_grams = COALESCE(EXCLUDED.carbs_grams, ios_health_daily.carbs_grams),
                    fat_grams = COALESCE(EXCLUDED.fat_grams, ios_health_daily.fat_grams),
                    water_liters = COALESCE(EXCLUDED.water_liters, ios_health_daily.water_liters),
                    caffeine_mg = COALESCE(EXCLUDED.caffeine_mg, ios_health_daily.caffeine_mg),
                    updated_at = NOW()
            """
            
            await self.db.execute(
                query,
                UUID(user_id),
                device_identifier,
                today,
                health_data.get('step_count'),
                health_data.get('active_calories'),
                health_data.get('sleep_hours'),
                health_data.get('last_sleep_end'),
                health_data.get('heart_rate'),
                health_data.get('today_workout_minutes'),
                health_data.get('today_workout_calories'),
                health_data.get('workout_count', 1 if health_data.get('today_workout_minutes') else 0),
                health_data.get('calories_consumed'),
                health_data.get('protein_grams'),
                health_data.get('carbs_grams'),
                health_data.get('fat_grams'),
                health_data.get('water_liters'),
                health_data.get('caffeine_milligrams')
            )
            
            logger.debug(f"📊 Stored daily health for {device_identifier}: {today}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store daily health: {e}")
            return False
    
    async def store_workout(
        self,
        device_identifier: str,
        workout: Dict[str, Any],
        user_id: str = DEFAULT_USER_ID
    ) -> bool:
        """Store individual workout to history."""
        try:
            query = """
                INSERT INTO ios_workout_history (
                    user_id, device_identifier,
                    workout_type, duration_minutes, calories_burned, distance_meters,
                    started_at, ended_at, source_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id, device_identifier, started_at, workout_type) DO NOTHING
            """
            
            await self.db.execute(
                query,
                UUID(user_id),
                device_identifier,
                workout.get('type', 'Workout'),
                workout.get('duration_minutes', 0),
                workout.get('calories_burned'),
                workout.get('distance_meters'),
                workout.get('start_time'),
                workout.get('end_time'),
                workout.get('source_id')
            )
            
            logger.debug(f"🏋️ Stored workout: {workout.get('type')} for {workout.get('duration_minutes')} min")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store workout: {e}")
            return False
    
    async def get_health_history(
        self,
        days: int = 7,
        user_id: str = DEFAULT_USER_ID
    ) -> List[Dict[str, Any]]:
        """Get health history for the past N days."""
        try:
            query = """
                SELECT 
                    date,
                    step_count,
                    active_calories,
                    sleep_hours,
                    heart_rate_avg,
                    workout_minutes,
                    workout_calories,
                    workout_count,
                    calories_consumed,
                    protein_grams,
                    carbs_grams,
                    fat_grams,
                    water_liters,
                    caffeine_mg
                FROM ios_health_daily
                WHERE user_id = $1
                  AND date >= CURRENT_DATE - $2::INTEGER
                ORDER BY date DESC
            """
            
            results = await self.db.fetch_all(query, UUID(user_id), days)
            
            history = [dict(r) for r in results]
            logger.debug(f"📊 Retrieved {len(history)} days of health history")
            return history
            
        except Exception as e:
            logger.error(f"❌ Failed to get health history: {e}")
            return []
    
    async def get_workout_history(
        self,
        days: int = 30,
        workout_type: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID
    ) -> List[Dict[str, Any]]:
        """Get workout history for the past N days."""
        try:
            params = [UUID(user_id), days]
            
            type_filter = ""
            if workout_type:
                type_filter = "AND workout_type = $3"
                params.append(workout_type)
            
            query = f"""
                SELECT 
                    workout_type,
                    duration_minutes,
                    calories_burned,
                    distance_meters,
                    started_at,
                    ended_at
                FROM ios_workout_history
                WHERE user_id = $1
                  AND started_at >= NOW() - ($2::INTEGER || ' days')::INTERVAL
                  {type_filter}
                ORDER BY started_at DESC
            """
            
            results = await self.db.fetch_all(query, *params)
            
            workouts = [dict(r) for r in results]
            logger.debug(f"🏋️ Retrieved {len(workouts)} workouts from history")
            return workouts
            
        except Exception as e:
            logger.error(f"❌ Failed to get workout history: {e}")
            return []
    
    async def get_health_summary(
        self,
        days: int = 7,
        user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, Any]:
        """Get aggregated health summary for AI context."""
        try:
            query = """
                SELECT 
                    ROUND(AVG(step_count)) as avg_steps,
                    ROUND(AVG(sleep_hours)::numeric, 1) as avg_sleep,
                    ROUND(AVG(active_calories)) as avg_active_calories,
                    SUM(workout_minutes) as total_workout_minutes,
                    COUNT(CASE WHEN workout_count > 0 THEN 1 END) as workout_days,
                    ROUND(AVG(calories_consumed)) as avg_calories_consumed,
                    ROUND(AVG(protein_grams)) as avg_protein,
                    MAX(date) as latest_date,
                    MIN(date) as earliest_date,
                    COUNT(*) as days_tracked
                FROM ios_health_daily
                WHERE user_id = $1
                  AND date >= CURRENT_DATE - $2::INTEGER
            """
            
            result = await self.db.fetch_one(query, UUID(user_id), days)
            
            if result:
                summary = dict(result)
                logger.debug(f"📊 Health summary: {summary['days_tracked']} days, avg {summary['avg_steps']} steps")
                return summary
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Failed to get health summary: {e}")
            return {}

    # =========================================================================
    # PROACTIVE ACTIONS (iOS Conversational Execution)
    # Queries unified_proactive_queue for iOS action handling
    # Added: 2026-01-06
    # =========================================================================
    
    async def get_pending_actions(
        self,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get pending actionable items from unified_proactive_queue.
        
        These are AI-generated drafts waiting for user action:
        - Email replies ready to send
        - Bluesky posts ready to publish
        - Meeting summaries with action items
        - Trend content with blog outlines
        
        Returns items ordered by priority and creation time.
        """
        try:
            query = """
                SELECT 
                    id,
                    source_type,
                    source_id,
                    source_url,
                    source_title,
                    source_preview,
                    source_metadata,
                    content_type,
                    draft_title,
                    draft_text,
                    draft_secondary,
                    draft_structured,
                    business_context,
                    priority,
                    status,
                    created_at
                FROM unified_proactive_queue
                WHERE status = 'pending'
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        WHEN 'low' THEN 4 
                    END,
                    created_at DESC
                LIMIT $1
            """
            
            results = await self.db.fetch_all(query, limit)
            
            actions = []
            for r in results:
                action = dict(r)
                # Convert UUID to string for JSON serialization
                action['id'] = str(action['id'])
                # Parse JSONB fields if they're strings
                if isinstance(action.get('source_metadata'), str):
                    action['source_metadata'] = json.loads(action['source_metadata'])
                if isinstance(action.get('draft_structured'), str):
                    action['draft_structured'] = json.loads(action['draft_structured'])
                actions.append(action)
            
            logger.debug(f"📋 Retrieved {len(actions)} pending actions")
            return actions
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending actions: {e}")
            return []
    
    async def get_action_by_id(
        self,
        queue_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single action with full details for conversation display.
        
        Returns complete draft, context, and source info needed
        for the iOS ActionConversationView.
        """
        try:
            query = """
                SELECT 
                    id,
                    source_type,
                    source_id,
                    source_url,
                    source_title,
                    source_preview,
                    source_metadata,
                    rss_context,
                    trend_context,
                    business_context,
                    content_type,
                    draft_title,
                    draft_text,
                    draft_secondary,
                    draft_structured,
                    personality_used,
                    model_used,
                    priority,
                    status,
                    action_taken,
                    action_result,
                    actioned_at,
                    created_at
                FROM unified_proactive_queue
                WHERE id = $1
            """
            
            result = await self.db.fetch_one(query, UUID(queue_id))
            
            if result:
                action = dict(result)
                action['id'] = str(action['id'])
                # Parse JSONB fields
                for field in ['source_metadata', 'rss_context', 'trend_context', 'draft_structured', 'action_result']:
                    if isinstance(action.get(field), str):
                        try:
                            action[field] = json.loads(action[field])
                        except json.JSONDecodeError:
                            pass
                return action
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get action by ID: {e}")
            return None
    
    async def update_action_draft(
        self,
        queue_id: str,
        new_draft_text: str,
        new_draft_secondary: Optional[str] = None
    ) -> bool:
        """
        Update action draft after AI editing.
        
        Called when user says "make it shorter" and we regenerate
        the draft with Claude.
        """
        try:
            if new_draft_secondary:
                query = """
                    UPDATE unified_proactive_queue
                    SET draft_text = $2,
                        draft_secondary = $3,
                        updated_at = NOW()
                    WHERE id = $1
                """
                await self.db.execute(query, UUID(queue_id), new_draft_text, new_draft_secondary)
            else:
                query = """
                    UPDATE unified_proactive_queue
                    SET draft_text = $2,
                        updated_at = NOW()
                    WHERE id = $1
                """
                await self.db.execute(query, UUID(queue_id), new_draft_text)
            
            logger.info(f"✏️ Updated draft for action: {queue_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update action draft: {e}")
            return False
    
    async def dismiss_action(
        self,
        queue_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Dismiss an action (user said "skip" or "ignore").
        
        Different from execute_action ignore which tracks sender stats.
        This is a simple dismissal without learning.
        """
        try:
            query = """
                UPDATE unified_proactive_queue
                SET status = 'dismissed',
                    action_taken = 'dismiss',
                    action_result = $2,
                    actioned_at = NOW()
                WHERE id = $1
            """
            
            result_json = json.dumps({'reason': reason}) if reason else '{}'
            await self.db.execute(query, UUID(queue_id), result_json)
            
            logger.info(f"⏭️ Dismissed action: {queue_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to dismiss action: {e}")
            return False
    
    async def get_action_stats(
        self,
        user_id: str = DEFAULT_USER_ID,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get action statistics for the past N days.
        
        Useful for understanding action patterns and
        auto-execution eligibility.
        """
        try:
            query = """
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                    COUNT(*) FILTER (WHERE status = 'actioned') as actioned_count,
                    COUNT(*) FILTER (WHERE status = 'dismissed') as dismissed_count,
                    COUNT(*) FILTER (WHERE status = 'expired') as expired_count,
                    COUNT(*) FILTER (WHERE action_taken = 'send') as emails_sent,
                    COUNT(*) FILTER (WHERE action_taken = 'post') as posts_made,
                    COUNT(*) as total
                FROM unified_proactive_queue
                WHERE created_at > NOW() - ($1::INTEGER || ' days')::INTERVAL
            """
            
            result = await self.db.fetch_one(query, days)
            
            if result:
                return dict(result)
            return {}
            
        except Exception as e:
            logger.error(f"❌ Failed to get action stats: {e}")
            return {}


# =============================================================================
# SINGLETON GETTER
# =============================================================================

def get_ios_db_manager() -> iOSDatabaseManager:
    """Get singleton instance of iOS database manager"""
    if iOSDatabaseManager._instance is None:
        iOSDatabaseManager._instance = iOSDatabaseManager()
    return iOSDatabaseManager._instance
