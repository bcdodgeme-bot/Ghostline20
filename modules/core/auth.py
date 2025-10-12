# modules/core/auth.py
# Authentication system for Syntax Prime V2
# Handles user login, session management, and password verification

import bcrypt
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from fastapi import Cookie

from .database import db_manager

logger = logging.getLogger(__name__)

class AuthManager:
    """Authentication and session management for Syntax Prime V2"""
    
    # In-memory session storage (for simplicity - could use Redis in production)
    _sessions = {}
    _session_timeout = timedelta(hours=24)  # 24-hour sessions
    
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
            logger.error(f"Password verification error: {e}")
            return False
    
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
                logger.warning(f"Authentication failed: User {email} not found")
                return None
            
            # Verify password
            if not AuthManager.verify_password(password, user['password_hash']):
                logger.warning(f"Authentication failed: Invalid password for {email}")
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
            logger.error(f"Authentication error: {e}")
            return None
    
    @staticmethod
    def create_session(user_info: Dict[str, Any]) -> str:
        """Create a new session for the user"""
        session_token = str(uuid.uuid4())
        
        AuthManager._sessions[session_token] = {
            'user': user_info,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + AuthManager._session_timeout,
            'last_activity': datetime.now()
        }
        
        logger.info(f"Session created for user {user_info['email']}: {session_token}")
        return session_token
    
    @staticmethod
    def validate_session(session_token: str) -> Optional[Dict[str, Any]]:
        """Validate a session token and return user info if valid"""
        if not session_token or session_token not in AuthManager._sessions:
            return None
        
        session = AuthManager._sessions[session_token]
        
        # Check if session has expired
        if datetime.now() > session['expires_at']:
            logger.info(f"Session expired: {session_token}")
            AuthManager.destroy_session(session_token)
            return None
        
        # Update last activity
        session['last_activity'] = datetime.now()
        
        return session['user']
    
    @staticmethod
    def destroy_session(session_token: str) -> bool:
        """Destroy a session"""
        if session_token in AuthManager._sessions:
            user_email = AuthManager._sessions[session_token]['user']['email']
            del AuthManager._sessions[session_token]
            logger.info(f"Session destroyed for user {user_email}: {session_token}")
            return True
        return False
    
    @staticmethod
    def cleanup_expired_sessions():
        """Clean up expired sessions (should be called periodically)"""
        now = datetime.now()
        expired_tokens = []
        
        for token, session in AuthManager._sessions.items():
            if now > session['expires_at']:
                expired_tokens.append(token)
        
        for token in expired_tokens:
            AuthManager.destroy_session(token)
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")
    
    @staticmethod
    def get_session_info() -> Dict[str, Any]:
        """Get information about current sessions (for admin purposes)"""
        active_sessions = []
        now = datetime.now()
        
        for token, session in AuthManager._sessions.items():
            if now <= session['expires_at']:
                active_sessions.append({
                    'token': token[:8] + '...',  # Partial token for security
                    'user_email': session['user']['email'],
                    'created_at': session['created_at'].isoformat(),
                    'expires_at': session['expires_at'].isoformat(),
                    'last_activity': session['last_activity'].isoformat()
                })
        
        return {
            'active_sessions': len(active_sessions),
            'sessions': active_sessions
        }

# Dependency function for FastAPI
async def get_current_user(session_token: str = Cookie(None)) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to get the current authenticated user
    Usage: user = Depends(get_current_user)
    """
    logger.info(f"🔍 get_current_user called")
    logger.info(f"   session_token type: {type(session_token)}")
    logger.info(f"   session_token value: {session_token}")
    
    if not session_token:
        logger.warning("⚠️ No session_token provided")
        return None
    
    user = AuthManager.validate_session(session_token)
    logger.info(f"   validate_session returned: {user is not None}")
    
    return user

# Utility functions for the web interface
def get_user_id_from_session(session_token: str) -> Optional[str]:
    """Get user ID from session token"""
    user = AuthManager.validate_session(session_token)
    return user['id'] if user else None
