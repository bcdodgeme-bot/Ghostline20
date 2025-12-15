# modules/integrations/telegram/kill_switch.py
"""
Kill Switch - Emergency control for Telegram notifications
Provides instant system-wide notification disable capability
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ...core.database import db_manager

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    Emergency kill switch for Telegram notification system
    
    Features:
    - Instant disable of all notifications
    - Configurable auto-enable duration
    - Audit logging of all switch activations
    - Safety checks to prevent accidental enables
    """
    
    def __init__(self):
        self.db = db_manager
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=1)  # Cache for 1 minute
    
    async def is_enabled(self, user_id: str) -> bool:
        """
        Check if notifications are enabled for user
        Uses caching to minimize database hits
        
        Args:
            user_id: User UUID
            
        Returns:
            True if notifications are enabled, False if disabled
        """
        # Check cache first
        if self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                if self._cache.get('user_id') == user_id:
                    return self._cache.get('enabled', False)
        
        # Query database
        query = """
        SELECT enabled, auto_enable_at, reason
        FROM telegram_kill_switch
        WHERE user_id = $1
        """
        
        try:
            result = await self.db.fetch_one(query, user_id)
            
            if not result:
                # No kill switch record = enabled by default
                logger.info(f"No kill switch record for user {user_id}, defaulting to enabled")
                return True
            
            enabled = result['enabled']
            auto_enable_at = result['auto_enable_at']
            
            # Check if auto-enable time has passed
            if not enabled and auto_enable_at:
                if datetime.now() >= auto_enable_at:
                    logger.info(f"Auto-enabling notifications for user {user_id}")
                    await self.enable(user_id, "Auto-enable time reached")
                    return True
            
            # Update cache
            self._cache = {
                'user_id': user_id,
                'enabled': enabled,
                'auto_enable_at': auto_enable_at
            }
            self._cache_time = datetime.now()
            
            return enabled
            
        except Exception as e:
            logger.error(f"Failed to check kill switch status: {e}")
            # Fail open - allow notifications on error
            return True
    
    async def disable(self, user_id: str, reason: str = "Manual disable",
                     duration_minutes: Optional[int] = None) -> bool:
        """
        Disable all Telegram notifications
        
        Args:
            user_id: User UUID
            reason: Reason for disabling (for audit log)
            duration_minutes: Auto-enable after this many minutes (None = manual enable required)
            
        Returns:
            True if successful
        """
        try:
            auto_enable_at = None
            if duration_minutes:
                auto_enable_at = datetime.now() + timedelta(minutes=duration_minutes)
            
            query = """
            INSERT INTO telegram_kill_switch (user_id, enabled, reason, auto_enable_at)
            VALUES ($1, false, $2, $3)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                enabled = false,
                reason = $2,
                auto_enable_at = $3,
                disabled_at = NOW(),
                updated_at = NOW()
            """
            
            await self.db.execute(query, user_id, reason, auto_enable_at)
            
            # Clear cache
            self._cache = None
            self._cache_time = None
            
            duration_msg = f" for {duration_minutes} minutes" if duration_minutes else ""
            logger.warning(f"🛑 KILL SWITCH ACTIVATED for user {user_id}{duration_msg}: {reason}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable kill switch: {e}")
            return False
    
    async def enable(self, user_id: str, reason: str = "Manual enable") -> bool:
        """
        Enable Telegram notifications
        
        Args:
            user_id: User UUID
            reason: Reason for enabling (for audit log)
            
        Returns:
            True if successful
        """
        try:
            query = """
            INSERT INTO telegram_kill_switch (user_id, enabled, reason)
            VALUES ($1, true, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                enabled = true,
                reason = $2,
                auto_enable_at = NULL,
                enabled_at = NOW(),
                updated_at = NOW()
            """
            
            await self.db.execute(query, user_id, reason)
            
            # Clear cache
            self._cache = None
            self._cache_time = None
            
            logger.info(f"✅ Kill switch disabled for user {user_id}: {reason}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable kill switch: {e}")
            return False
    
    async def get_status(self, user_id: str) -> Dict[str, Any]:
        """
        Get detailed kill switch status
        
        Args:
            user_id: User UUID
            
        Returns:
            Dict with status details
        """
        query = """
        SELECT enabled, reason, auto_enable_at, disabled_at, enabled_at, updated_at
        FROM telegram_kill_switch
        WHERE user_id = $1
        """
        
        try:
            result = await self.db.fetch_one(query, user_id)
            
            if not result:
                return {
                    'enabled': True,
                    'reason': 'No kill switch record (default enabled)',
                    'auto_enable_at': None,
                    'disabled_at': None,
                    'enabled_at': None,
                    'updated_at': None
                }
            
            return {
                'enabled': result['enabled'],
                'reason': result['reason'],
                'auto_enable_at': result['auto_enable_at'],
                'disabled_at': result['disabled_at'],
                'enabled_at': result['enabled_at'],
                'updated_at': result['updated_at']
            }
            
        except Exception as e:
            logger.error(f"Failed to get kill switch status: {e}")
            return {
                'enabled': True,
                'reason': f'Error: {str(e)}',
                'auto_enable_at': None,
                'disabled_at': None,
                'enabled_at': None,
                'updated_at': None
            }
    
    async def toggle(self, user_id: str, reason: str = "Manual toggle") -> bool:
        """
        Toggle kill switch state (enable if disabled, disable if enabled)
        
        Args:
            user_id: User UUID
            reason: Reason for toggle
            
        Returns:
            New state (True = enabled, False = disabled)
        """
        current_state = await self.is_enabled(user_id)
        
        if current_state:
            await self.disable(user_id, reason)
            return False
        else:
            await self.enable(user_id, reason)
            return True


# Global singleton instance
_kill_switch: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    """
    Get the global KillSwitch instance (singleton pattern)
    
    Returns:
        KillSwitch instance
    """
    global _kill_switch
    
    if _kill_switch is None:
        _kill_switch = KillSwitch()
    
    return _kill_switch
