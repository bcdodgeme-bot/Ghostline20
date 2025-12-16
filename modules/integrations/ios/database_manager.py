# modules/integrations/ios/database_manager.py
"""
iOS Integration Database Manager
Handles ios_devices and ios_pending_notifications tables

Follows established patterns:
- Singleton with _instance + get_ios_db_manager() getter
- Uses db_manager for all database operations
- Parameterized SQL queries
- Timezone-aware datetimes
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from modules.database.db_manager import get_db_manager

logger = logging.getLogger(__name__)

# Single-user system - Carl's UUID
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"


class iOSDatabaseManager:
    """Database operations for iOS integration"""
    
    _instance = None
    
    def __init__(self):
        self.db = get_db_manager()
    
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
            result = await self.db.fetchrow(
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
            result = await self.db.fetchrow(query, device_identifier)
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
            result = await self.db.fetchrow(query, UUID(device_id))
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
                params.append(health_data)
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
            results = await self.db.fetch(query, UUID(user_id))
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
            result = await self.db.fetchrow(query, device_identifier)
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
        """Update notification preferences"""
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
            logger.error(f"❌ Failed to update preferences: {e}")
            return False
    
    # =========================================================================
    # NOTIFICATION QUEUE MANAGEMENT
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
        Create a pending notification in the queue.
        Returns notification ID if successful.
        """
        try:
            query = """
                INSERT INTO ios_pending_notifications (
                    user_id, device_id, notification_type,
                    title, body, payload,
                    priority, scheduled_for, expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """
            
            now = datetime.now(timezone.utc)
            result = await self.db.fetchrow(
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
            results = await self.db.fetch(query, UUID(user_id), now, limit)
            
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
            results = await self.db.fetch(query, UUID(user_id))
            
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


# =============================================================================
# SINGLETON GETTER
# =============================================================================

def get_ios_db_manager() -> iOSDatabaseManager:
    """Get singleton instance of iOS database manager"""
    if iOSDatabaseManager._instance is None:
        iOSDatabaseManager._instance = iOSDatabaseManager()
    return iOSDatabaseManager._instance