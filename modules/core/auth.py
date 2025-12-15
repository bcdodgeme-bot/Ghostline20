# modules/core/auth.py
"""
Authentication system for Syntax Prime V2
Handles user login, session management, and password verification

CHANGELOG 12/09/25:
- FIXED: Garbled unicode characters in log messages
- FIXED: Sessions now stored in PostgreSQL (survives Railway deploys)
- ADDED: Automatic session table creation
- ADDED: Better error handling and logging
- IMPROVED: Async consistency throughout

CHANGELOG Session 19:
- ADDED: __all__ exports
- MOVED: json and timezone imports to top level
- ADDED: Deprecation warnings on sync wrappers (to track usage)
"""

import asyncio
import concurrent.futures
import json
import logging
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import bcrypt
from fastapi import Cookie

from .database import db_manager

logger = logging.getLogger(__name__)

__all__ = [
    'AuthManager',
    'get_current_user',
    'get_user_id_from_session',
    'get_user_id_from_session_async',
]


class AuthManager:
    """
    Authentication and session management for Syntax Prime V2
    
    Sessions are stored in PostgreSQL to survive container restarts.
    This fixes the issue where Railway deploys would log out all users.
    """
    
    # Session configuration
    _session_timeout = timedelta(hours=24)  # 24-hour sessions
    _table_initialized = False
    
    # =========================================================================
    # Session Table Management
    # =========================================================================
    
    @staticmethod
    async def _ensure_session_table():
        """Create the sessions table if it doesn't exist"""
        if AuthManager._table_initialized:
            return
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token VARCHAR(255) PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_email VARCHAR(255) NOT NULL,
            user_data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
        """
        
        try:
            await db_manager.execute(create_table_query)
            AuthManager._table_initialized = True
            logger.info("✅ Session table initialized")
        except Exception as e:
            # Table might already exist, that's fine
            if "already exists" in str(e).lower():
                AuthManager._table_initialized = True
            else:
                logger.error(f"❌ Failed to create session table: {e}")
                raise
    
    # =========================================================================
    # Password Hashing
    # =========================================================================
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password_bytes, salt)
        return password_hash.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception as e:
            logger.error(f"❌ Password verification error: {e}")
            return False
    
    # =========================================================================
    # User Authentication
    # =========================================================================
    
    @staticmethod
    async def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user with email and password
        Returns user info if successful, None if failed
        """
        try:
            # Get user from database
            query = """
            SELECT id, email, username, password_hash, display_name, 
                   timezone, is_active, created_at
            FROM users 
            WHERE email = $1 AND is_active = true
            """
            
            user = await db_manager.fetch_one(query, email.lower().strip())
            
            if not user:
                logger.warning(f"🔐 Authentication failed: User {email} not found")
                return None
            
            # Verify password
            if not AuthManager.verify_password(password, user['password_hash']):
                logger.warning(f"🔐 Authentication failed: Invalid password for {email}")
                return None
            
            # Update last login
            await db_manager.execute(
                "UPDATE users SET updated_at = NOW() WHERE id = $1",
                user['id']
            )
            
            # Return user info (without password hash)
            return {
                'id': str(user['id']),
                'email': user['email'],
                'username': user['username'],
                'display_name': user['display_name'],
                'timezone': user['timezone'],
                'created_at': user['created_at'].isoformat() if user['created_at'] else None
            }
            
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            return None
    
    # =========================================================================
    # Session Management (Database-backed)
    # =========================================================================
    
    @staticmethod
    async def create_session(user_info: Dict[str, Any]) -> str:
        """
        Create a new session for the user (stored in PostgreSQL)
        """
        await AuthManager._ensure_session_table()
        
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + AuthManager._session_timeout
        
        # Store session in database
        insert_query = """
        INSERT INTO user_sessions (session_token, user_id, user_email, user_data, created_at, expires_at, last_activity)
        VALUES ($1, $2, $3, $4, NOW(), $5, NOW())
        ON CONFLICT (session_token) DO UPDATE SET
            user_data = $4,
            expires_at = $5,
            last_activity = NOW()
        """
        
        try:
            user_data_json = json.dumps(user_info)
            
            await db_manager.execute(
                insert_query,
                session_token,
                user_info['id'],
                user_info['email'],
                user_data_json,
                expires_at
            )
            
            logger.info(f"🔐 Session created for user {user_info['email']}")
            return session_token
            
        except Exception as e:
            logger.error(f"❌ Failed to create session: {e}")
            raise
    
    @staticmethod
    async def validate_session(session_token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a session token and return user info if valid
        """
        if not session_token:
            logger.debug("🔐 No session token provided")
            return None
        
        await AuthManager._ensure_session_table()
        
        # Query session from database
        query = """
        SELECT session_token, user_id, user_email, user_data, created_at, expires_at, last_activity
        FROM user_sessions
        WHERE session_token = $1
        """
        
        try:
            session = await db_manager.fetch_one(query, session_token)
            
            if not session:
                logger.debug(f"🔐 Session token not found in database")
                return None
            
            # Check if session has expired
            now = datetime.now(timezone.utc)
            expires_at = session['expires_at']
            
            # Ensure expires_at is timezone-aware for comparison
            if expires_at.tzinfo is None:
                # If stored without timezone, assume UTC
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if now > expires_at:
                logger.info(f"🔐 Session expired for {session['user_email']}")
                await AuthManager.destroy_session(session_token)
                return None
            
            # Update last activity
            await db_manager.execute(
                "UPDATE user_sessions SET last_activity = NOW() WHERE session_token = $1",
                session_token
            )
            
            # Parse and return user data
            user_data = session['user_data']
            
            # Handle both string and dict formats
            if isinstance(user_data, str):
                user_info = json.loads(user_data)
            else:
                user_info = dict(user_data)
            
            logger.debug(f"🔐 Session valid for {session['user_email']}")
            return user_info
            
        except Exception as e:
            logger.error(f"❌ Session validation error: {e}")
            return None
    
    @staticmethod
    async def destroy_session(session_token: str) -> bool:
        """Destroy a session"""
        if not session_token:
            return False
        
        await AuthManager._ensure_session_table()
        
        try:
            # Get user email for logging before deletion
            session = await db_manager.fetch_one(
                "SELECT user_email FROM user_sessions WHERE session_token = $1",
                session_token
            )
            
            user_email = session['user_email'] if session else 'unknown'
            
            # Delete the session
            await db_manager.execute(
                "DELETE FROM user_sessions WHERE session_token = $1",
                session_token
            )
            
            logger.info(f"🔐 Session destroyed for user {user_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to destroy session: {e}")
            return False
    
    @staticmethod
    async def cleanup_expired_sessions():
        """Clean up expired sessions from the database"""
        await AuthManager._ensure_session_table()
        
        try:
            result = await db_manager.execute(
                "DELETE FROM user_sessions WHERE expires_at < NOW()"
            )
            
            # Parse the DELETE count from result (format: "DELETE N")
            if result and isinstance(result, str):
                deleted_count = result.split()[-1] if result.startswith("DELETE") else "0"
                if deleted_count != "0":
                    logger.info(f"🔐 Cleaned up {deleted_count} expired sessions")
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired sessions: {e}")
    
    @staticmethod
    async def get_session_info() -> Dict[str, Any]:
        """Get information about current sessions (for admin purposes)"""
        await AuthManager._ensure_session_table()
        
        try:
            # Get active sessions count and details
            query = """
            SELECT 
                session_token,
                user_email,
                created_at,
                expires_at,
                last_activity
            FROM user_sessions
            WHERE expires_at > NOW()
            ORDER BY last_activity DESC
            """
            
            sessions = await db_manager.fetch_all(query)
            
            active_sessions = []
            for session in sessions:
                active_sessions.append({
                    'token': session['session_token'][:8] + '...',  # Partial token for security
                    'user_email': session['user_email'],
                    'created_at': session['created_at'].isoformat() if session['created_at'] else None,
                    'expires_at': session['expires_at'].isoformat() if session['expires_at'] else None,
                    'last_activity': session['last_activity'].isoformat() if session['last_activity'] else None
                })
            
            return {
                'active_sessions': len(active_sessions),
                'sessions': active_sessions
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get session info: {e}")
            return {
                'active_sessions': 0,
                'sessions': [],
                'error': str(e)
            }
    
    # =========================================================================
    # Synchronous Wrappers (DEPRECATED - for backwards compatibility only)
    # =========================================================================
    # WARNING: These are deprecated and may cause issues with async event loops.
    # Use the async versions directly when possible.
    # Deprecation warnings will log when these are called to track usage.
    
    @staticmethod
    def create_session_sync(user_info: Dict[str, Any]) -> str:
        """
        DEPRECATED: Synchronous wrapper for create_session.
        Use create_session() directly when possible.
        
        This wrapper may cause event loop conflicts in async contexts.
        """
        logger.warning("⚠️ DEPRECATED: create_session_sync() called - consider using async create_session()")
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a new task
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        AuthManager.create_session(user_info)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(AuthManager.create_session(user_info))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(AuthManager.create_session(user_info))
    
    @staticmethod
    def validate_session_sync(session_token: str) -> Optional[Dict[str, Any]]:
        """
        DEPRECATED: Synchronous wrapper for validate_session.
        Use validate_session() directly when possible.
        
        This wrapper may cause event loop conflicts in async contexts.
        """
        logger.warning("⚠️ DEPRECATED: validate_session_sync() called - consider using async validate_session()")
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        AuthManager.validate_session(session_token)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(AuthManager.validate_session(session_token))
        except RuntimeError:
            return asyncio.run(AuthManager.validate_session(session_token))
    
    @staticmethod
    def destroy_session_sync(session_token: str) -> bool:
        """
        DEPRECATED: Synchronous wrapper for destroy_session.
        Use destroy_session() directly when possible.
        
        This wrapper may cause event loop conflicts in async contexts.
        """
        logger.warning("⚠️ DEPRECATED: destroy_session_sync() called - consider using async destroy_session()")
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        AuthManager.destroy_session(session_token)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(AuthManager.destroy_session(session_token))
        except RuntimeError:
            return asyncio.run(AuthManager.destroy_session(session_token))


# =============================================================================
# FastAPI Dependency Functions
# =============================================================================

async def get_current_user(session_token: str = Cookie(None)) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to get the current authenticated user
    Usage: user = Depends(get_current_user)
    """
    logger.debug(f"🔐 get_current_user called")
    
    if not session_token:
        logger.debug("🔐 No session_token cookie provided")
        return None
    
    user = await AuthManager.validate_session(session_token)
    logger.debug(f"🔐 Session validation result: {'valid' if user else 'invalid'}")
    
    return user


def get_user_id_from_session(session_token: str) -> Optional[str]:
    """
    DEPRECATED: Get user ID from session token (synchronous version)
    Prefer using async version get_user_id_from_session_async() when possible.
    """
    logger.warning("⚠️ DEPRECATED: get_user_id_from_session() called - consider using async get_user_id_from_session_async()")
    user = AuthManager.validate_session_sync(session_token)
    return user['id'] if user else None


async def get_user_id_from_session_async(session_token: str) -> Optional[str]:
    """Get user ID from session token (async version - preferred)"""
    user = await AuthManager.validate_session(session_token)
    return user['id'] if user else None
