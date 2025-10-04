# modules/integrations/google_workspace/oauth_manager.py
"""
Google Workspace Authentication Manager
Railway-compatible OAuth Web Flow + Service Account Hybrid System

This module handles:
1. Service Account authentication for carl@bcdodge.me domain
2. OAuth Web Flow for additional Gmail accounts (Railway-friendly)
3. Token management with Fort Knox encryption
4. Automatic token refresh and error handling
5. Multi-account support with unified API access

Authentication Flows:
- Service Account: Seamless access to domain resources
- Web Flow: User clicks link, authorizes, gets redirected back
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import aiohttp

logger = logging.getLogger(__name__)

# Import after logger setup to avoid circular imports
try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    logger.warning("Google auth libraries not installed - install google-auth and google-auth-oauthlib")

from ...core.database import db_manager
from ...core.crypto import encrypt_token, decrypt_token, encrypt_json, decrypt_json

class GoogleAuthenticationError(Exception):
    """Custom exception for Google authentication errors"""
    pass

class GoogleTokenExpiredError(GoogleAuthenticationError):
    """Token expired and refresh failed"""
    pass

class GoogleAuthManager:
    """
    Hybrid Google authentication system for Railway deployment
    Combines service account and OAuth web flow authentication
    """
    
    def __init__(self):
        """Initialize authentication manager with environment configuration"""
        
        if not GOOGLE_AUTH_AVAILABLE:
            logger.error("Google authentication libraries not available")
            raise RuntimeError("Google auth libraries required - run: pip install google-auth google-auth-oauthlib")
        
        # OAuth Client Configuration (Web Application type)
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            logger.error("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
            raise RuntimeError("Missing Google OAuth credentials")
        
        # Service Account Configuration
        self.service_account_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        self.workspace_domain = os.getenv('GOOGLE_WORKSPACE_DOMAIN', 'bcdodge.me')
        self.admin_email = os.getenv('GOOGLE_WORKSPACE_ADMIN_EMAIL', 'carl@bcdodge.me')
        
        # OAuth Scopes (comprehensive access including Search Console and Gmail)
        self.oauth_scopes = [
            'https://www.googleapis.com/auth/analytics.readonly',
            'https://www.googleapis.com/auth/webmasters.readonly',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        
        # OAuth URLs
        self.auth_url = 'https://accounts.google.com/o/oauth2/v2/auth'
        self.token_url = 'https://oauth2.googleapis.com/token'
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/google/auth/callback')
        
        # Authentication state
        self._service_credentials = None
        self._oauth_credentials_cache = {}  # email -> credentials
        self._state_cache = {}  # state -> user_id mapping
        
        logger.info("Google Auth Manager initialized")
    
    async def initialize_service_account(self) -> bool:
        """
        Initialize service account authentication for domain access
        
        Returns:
            True if service account is ready, False if not configured
        """
        try:
            if not os.path.exists(self.service_account_path):
                logger.warning(f"Service account file not found: {self.service_account_path}")
                return False
            
            # Load service account credentials
            self._service_credentials = service_account.Credentials.from_service_account_file(
                self.service_account_path,
                scopes=self.oauth_scopes
            )
            
            # Test credentials by getting token info
            self._service_credentials.refresh(Request())
            
            # Store encrypted service account info in database
            await self._store_service_account_config()
            
            logger.info("Service account authentication initialized")
            return True
            
        except Exception as e:
            logger.error(f"Service account initialization failed: {e}")
            return False
    
    async def start_oauth_web_flow(self, user_id: str) -> str:
        """
        Start OAuth web flow - returns authorization URL
        
        Args:
            user_id: User ID for state tracking
            
        Returns:
            Authorization URL for user to visit
        """
        try:
            import secrets
            
            # Generate state token for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Store state temporarily (expires in 10 minutes)
            self._state_cache[state] = {
                'user_id': user_id,
                'created_at': datetime.now()
            }
            
            # Build authorization URL
            from urllib.parse import urlencode
            
            params = {
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'response_type': 'code',
                'scope': ' '.join(self.oauth_scopes),
                'state': state,
                'access_type': 'offline',
                'prompt': 'consent'
            }
            
            auth_url = f"{self.auth_url}?{urlencode(params)}"
            
            logger.info(f"OAuth web flow started for user {user_id}")
            return auth_url
            
        except Exception as e:
            logger.error(f"Web flow start failed: {e}")
            raise GoogleAuthenticationError(f"Failed to start web flow: {e}")
    
    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """
        Handle OAuth callback and exchange code for tokens
        
        Args:
            code: Authorization code from Google
            state: State token for CSRF verification
            
        Returns:
            Dict with success status and user info
        """
        try:
            # Verify state token
            if state not in self._state_cache:
                raise GoogleAuthenticationError("Invalid or expired state token")
            
            state_data = self._state_cache[state]
            user_id = state_data['user_id']
            
            # Check if state is expired (10 minutes)
            if datetime.now() - state_data['created_at'] > timedelta(minutes=10):
                del self._state_cache[state]
                raise GoogleAuthenticationError("State token expired")
            
            # Exchange code for tokens
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, data=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {error_text}")
                        raise GoogleAuthenticationError(f"Token exchange failed: {error_text}")
                    
                    token_data = await response.json()
            
            # Store tokens
            await self._store_oauth_tokens(user_id, token_data)
            
            # Get user email
            user_email = await self._get_user_email_from_token(token_data['access_token'])
            
            # Clean up state
            del self._state_cache[state]
            
            logger.info(f"OAuth completed for {user_email}")
            
            return {
                'success': True,
                'email': user_email,
                'user_id': user_id
            }
            
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}")
            raise GoogleAuthenticationError(f"OAuth callback error: {e}")
    
    async def get_valid_credentials(self, user_id: str, email: Optional[str] = None):
        """
        Get valid credentials for API calls, refreshing if necessary
        
        Args:
            user_id: User ID
            email: Specific email account, or None for service account OR first available OAuth account
            
        Returns:
            Valid credentials or None if unavailable
        """
        try:
            if email is None:
                # Try service account first
                if self._service_credentials:
                    if self._service_credentials.expired:
                        self._service_credentials.refresh(Request())
                    return self._service_credentials
                
                # If no service account, look for ANY OAuth credentials
                logger.info("Service account not available, checking for OAuth credentials...")
                
                # Query database for any active OAuth account for this user
                query = '''
                    SELECT email_address
                    FROM google_oauth_accounts
                    WHERE user_id = $1 AND is_active = TRUE
                    ORDER BY authenticated_at DESC
                    LIMIT 1
                '''
                
                conn = await db_manager.get_connection()
                try:
                    row = await conn.fetchrow(query, user_id)
                    
                    if row:
                        email = row['email_address']
                        logger.info(f"Found OAuth credentials for {email}, using these instead")
                        # Continue to OAuth flow below
                    else:
                        logger.warning("No service account or OAuth credentials available")
                        return None
                finally:
                    await db_manager.release_connection(conn)
            
            # Use OAuth credentials for specific email (or auto-detected email)
            if email in self._oauth_credentials_cache:
                creds = self._oauth_credentials_cache[email]
                if creds.expiry and creds.expiry <= datetime.now(timezone.utc) and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Update stored tokens
                        await self._update_oauth_tokens(user_id, email, creds)
                        return creds
                    except RefreshError:
                        logger.error(f"Token refresh failed for {email}")
                        # Remove invalid credentials
                        del self._oauth_credentials_cache[email]
                        raise GoogleTokenExpiredError(f"Hey, your Google Authorization expired again! Use 'google auth setup' to renew.")
                return creds
            
            # Load from database
            return await self._load_oauth_credentials(user_id, email)
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Failed to get credentials: {e}")
            return None
    
    async def get_authenticated_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get list of authenticated Google accounts
        
        Args:
            user_id: User ID
            
        Returns:
            List of account info dictionaries
        """
        try:
            query = '''
                SELECT email_address, scopes, authenticated_at, token_expires_at, is_active
                FROM google_oauth_accounts
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY authenticated_at DESC
            '''
            
            accounts = []
            conn = await db_manager.get_connection()
            try:
                rows = await conn.fetch(query, user_id)
                
                for row in rows:
                    scopes = row['scopes'] if row['scopes'] else []
                    
                    accounts.append({
                        'email': row['email_address'],
                        'scopes': scopes,
                        'authenticated_at': row['authenticated_at'],
                        'expires_at': row['token_expires_at'],
                        'is_expired': (datetime.now(timezone.utc) > row['token_expires_at']) if row['token_expires_at'] else False
                    })
            finally:
                await db_manager.release_connection(conn)
            
            # Add service account info if available
            if self._service_credentials:
                accounts.insert(0, {
                    'email': self.admin_email,
                    'type': 'service_account',
                    'scopes': self.oauth_scopes,
                    'authenticated_at': datetime.now(),
                    'expires_at': None,
                    'is_expired': False
                })
            
            return accounts
            
        except Exception as e:
            logger.error(f"Failed to get authenticated accounts: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    # Private helper methods
    
    async def _store_service_account_config(self):
        """Store encrypted service account configuration"""
        try:
            # Read service account file
            with open(self.service_account_path, 'r') as f:
                service_account_data = json.load(f)
            
            # Encrypt the service account key
            encrypted_key = encrypt_json(service_account_data)
            
            # Get user ID
            conn = await db_manager.get_connection()
            try:
                user_id = await conn.fetchval("SELECT id FROM users LIMIT 1")
                
                if user_id:
                    query = '''
                        INSERT INTO google_service_config 
                        (user_id, service_account_email, service_key_encrypted, domain, scopes)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (user_id, domain) DO UPDATE SET
                            service_account_email = EXCLUDED.service_account_email,
                            service_key_encrypted = EXCLUDED.service_key_encrypted,
                            scopes = EXCLUDED.scopes
                    '''
                    
                    # Python list automatically converts to PostgreSQL ARRAY
                    await conn.execute(
                        query,
                        user_id,
                        service_account_data.get('client_email'),
                        encrypted_key,
                        self.workspace_domain,
                        self.oauth_scopes
                    )
                    
                    logger.info("Service account config stored securely")
            finally:
                await db_manager.release_connection(conn)
                    
        except Exception as e:
            logger.error(f"Failed to store service account config: {e}")
    
    async def _store_oauth_tokens(self, user_id: str, token_data: Dict[str, Any]):
        """Store encrypted OAuth tokens in database"""
        try:
            # Get user email from access token
            user_email = await self._get_user_email_from_token(token_data['access_token'])
            
            # Encrypt tokens
            encrypted_access_token = encrypt_token(token_data['access_token'])
            encrypted_refresh_token = encrypt_token(token_data.get('refresh_token', ''))
            
            # Calculate expiration time
            expires_at = datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))
            
            query = '''
                INSERT INTO google_oauth_accounts
                (user_id, email_address, access_token_encrypted, refresh_token_encrypted, 
                 token_expires_at, scopes, auth_flow_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, email_address) DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                    token_expires_at = EXCLUDED.token_expires_at,
                    updated_at = NOW()
            '''
            
            conn = await db_manager.get_connection()
            try:
                # Python list automatically converts to PostgreSQL ARRAY
                await conn.execute(
                    query,
                    user_id,
                    user_email,
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_at,
                    self.oauth_scopes,
                    'oauth_web'
                )
            finally:
                await db_manager.release_connection(conn)
            
            # Cache credentials
            credentials = Credentials(
                token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token'),
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.oauth_scopes
            )
            
            self._oauth_credentials_cache[user_email] = credentials
            
            logger.info(f"OAuth tokens stored for {user_email}")
            
        except Exception as e:
            logger.error(f"Failed to store OAuth tokens: {e}")
            raise
    
    async def _load_oauth_credentials(self, user_id: str, email: str):
        """Load and decrypt OAuth credentials from database"""
        try:
            query = '''
                SELECT access_token_encrypted, refresh_token_encrypted, token_expires_at
                FROM google_oauth_accounts
                WHERE user_id = $1 AND email_address = $2 AND is_active = TRUE
            '''
            
            conn = await db_manager.get_connection()
            try:
                row = await conn.fetchrow(query, user_id, email)
                
                if not row:
                    return None
                
                # Decrypt tokens
                access_token = decrypt_token(row['access_token_encrypted'])
                refresh_token = decrypt_token(row['refresh_token_encrypted']) if row['refresh_token_encrypted'] else None
                
                # Create credentials
                credentials = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri=self.token_url,           # ← ADD THIS
                    client_id=self.client_id,           # ← ADD THIS
                    client_secret=self.client_secret,
                    scopes=self.oauth_scopes,
                    expiry=row['token_expires_at']
                )
                
                # Cache for future use
                self._oauth_credentials_cache[email] = credentials
                
                return credentials
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"Failed to load OAuth credentials for {email}: {e}")
            return None
    
    async def _get_user_email_from_token(self, access_token: str) -> str:
        """Get user email from access token"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {access_token}'}
                async with session.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers) as response:
                    if response.status == 200:
                        user_info = await response.json()
                        return user_info['email']
                    else:
                        raise GoogleAuthenticationError("Failed to get user email from token")
        except Exception as e:
            logger.error(f"Failed to get user email: {e}")
            raise GoogleAuthenticationError(f"Failed to get user email: {e}")
    
    async def _update_oauth_tokens(self, user_id: str, email: str, credentials: Credentials):
        """Update stored OAuth tokens after refresh"""
        try:
            encrypted_access_token = encrypt_token(credentials.token)
            expires_at = credentials.expiry
            
            query = '''
                UPDATE google_oauth_accounts
                SET access_token_encrypted = $1, token_expires_at = $2, updated_at = NOW()
                WHERE user_id = $3 AND email_address = $4
            '''
            
            conn = await db_manager.get_connection()
            try:
                await conn.execute(query, encrypted_access_token, expires_at, user_id, email)
            finally:
                await db_manager.release_connection(conn)
                
            logger.info(f"Tokens updated for {email}")
            
        except Exception as e:
            logger.error(f"Failed to update tokens for {email}: {e}")

    async def get_aiogoogle_creds(self, user_id: str, email: Optional[str] = None):
            """
            Get credentials in aiogoogle format
            
            Returns:
                UserCreds object for aiogoogle
            """
            from aiogoogle.auth.creds import UserCreds
            
            # Get regular credentials first
            credentials = await self.get_valid_credentials(user_id, email)
            
            if not credentials:
                return None
            
            # Convert to aiogoogle format
            user_creds = UserCreds(
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                expires_at=credentials.expiry.isoformat() if credentials.expiry else None,
                scopes=list(credentials.scopes) if credentials.scopes else []
            )
            
            return user_creds

# Global instance
google_auth_manager = GoogleAuthManager()

# Convenience functions for other modules
async def get_google_credentials(user_id: str, email: Optional[str] = None):
    """Get valid Google credentials for API calls"""
    return await google_auth_manager.get_valid_credentials(user_id, email)

async def start_google_oauth(user_id: str) -> str:
    """Start Google OAuth web flow - returns authorization URL"""
    return await google_auth_manager.start_oauth_web_flow(user_id)

async def handle_google_oauth_callback(code: str, state: str) -> Dict[str, Any]:
    """Handle OAuth callback"""
    return await google_auth_manager.handle_oauth_callback(code, state)

async def get_google_accounts(user_id: str) -> List[Dict[str, Any]]:
    """Get list of authenticated Google accounts"""
    return await google_auth_manager.get_authenticated_accounts(user_id)

async def get_aiogoogle_credentials(user_id: str, email: Optional[str] = None):
    """Get aiogoogle-formatted credentials"""
    return await google_auth_manager.get_aiogoogle_creds(user_id, email)
