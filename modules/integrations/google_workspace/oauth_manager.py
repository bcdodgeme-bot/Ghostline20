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

# How many minutes before expiry to proactively refresh
TOKEN_REFRESH_BUFFER_MINUTES = 10

# Maximum age for state tokens (OAuth CSRF protection)
STATE_TOKEN_MAX_AGE_MINUTES = 10

# Maximum entries in caches
MAX_CREDENTIALS_CACHE_SIZE = 50
MAX_STATE_CACHE_SIZE = 100


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
        self._oauth_credentials_cache = {}  # email -> (credentials, cached_at)
        self._state_cache = {}  # state -> {user_id, created_at}
        
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
            
            # Clean up expired state tokens first
            self._cleanup_expired_states()
            
            # Generate state token for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Enforce cache size limit
            if len(self._state_cache) >= MAX_STATE_CACHE_SIZE:
                # Remove oldest entries
                sorted_states = sorted(
                    self._state_cache.items(),
                    key=lambda x: x[1]['created_at']
                )
                for old_state, _ in sorted_states[:10]:  # Remove 10 oldest
                    del self._state_cache[old_state]
            
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
    
    def _cleanup_expired_states(self):
        """Remove expired state tokens from cache"""
        now = datetime.now()
        expired = [
            state for state, data in self._state_cache.items()
            if (now - data['created_at']) > timedelta(minutes=STATE_TOKEN_MAX_AGE_MINUTES)
        ]
        for state in expired:
            del self._state_cache[state]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired OAuth state tokens")
    
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
            # Clean up expired states
            self._cleanup_expired_states()
            
            # Verify state token
            if state not in self._state_cache:
                raise GoogleAuthenticationError("Invalid or expired state token")
            
            state_data = self._state_cache[state]
            user_id = state_data['user_id']
            
            # Check if state is expired (10 minutes)
            if datetime.now() - state_data['created_at'] > timedelta(minutes=STATE_TOKEN_MAX_AGE_MINUTES):
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
                    ORDER BY CASE WHEN email_address LIKE '%@bcdodge.me' THEN 0 ELSE 1 END, authenticated_at DESC
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
            
            # Check cache first
            if email in self._oauth_credentials_cache:
                creds, cached_at = self._oauth_credentials_cache[email]
                
                # Check if credentials need refresh (expired or expiring soon)
                needs_refresh = False
                if creds.expiry:
                    # Refresh if expired OR expiring within buffer window
                    buffer_time = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_REFRESH_BUFFER_MINUTES)
                    if creds.expiry <= buffer_time:
                        needs_refresh = True
                        logger.info(f"Token for {email} is expired or expiring soon, refreshing...")
                
                if needs_refresh and creds.refresh_token:
                    try:
                        # Use async HTTP refresh instead of synchronous library
                        refreshed_creds = await self._refresh_token_async(user_id, email, creds.refresh_token)
                        if refreshed_creds:
                            return refreshed_creds
                        else:
                            # Refresh failed, remove from cache
                            del self._oauth_credentials_cache[email]
                            raise GoogleTokenExpiredError(
                                f"Token refresh failed for {email}. Use 'google auth setup' to re-authenticate."
                            )
                    except GoogleTokenExpiredError:
                        raise
                    except Exception as e:
                        logger.error(f"Token refresh error for {email}: {e}")
                        del self._oauth_credentials_cache[email]
                        raise GoogleTokenExpiredError(
                            f"Token refresh failed for {email}. Use 'google auth setup' to re-authenticate."
                        )
                
                # Credentials are valid
                return creds
            
            # Not in cache - load from database
            return await self._load_oauth_credentials(user_id, email)
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"Failed to get credentials: {e}")
            return None
    
    async def _refresh_token_async(self, user_id: str, email: str, refresh_token: str) -> Optional[Credentials]:
        """
        Refresh OAuth token using async HTTP request
        
        This is more reliable than using the synchronous Google library refresh
        in an async context.
        
        Args:
            user_id: User ID
            email: Email address of the account
            refresh_token: The refresh token to use
            
        Returns:
            New Credentials object or None if refresh failed
        """
        try:
            logger.info(f"🔄 Refreshing token for {email} via async HTTP...")
            
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, data=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token refresh failed ({response.status}): {error_text}")
                        
                        # Check if refresh token is invalid/revoked
                        if response.status == 400:
                            error_data = await response.json()
                            if error_data.get('error') == 'invalid_grant':
                                logger.error(f"Refresh token revoked or expired for {email}")
                                # Mark account as needing re-auth
                                await self._mark_account_needs_reauth(user_id, email)
                        return None
                    
                    token_data = await response.json()
            
            # Calculate new expiry time
            expires_in = token_data.get('expires_in', 3600)
            new_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            # Create new credentials object
            # Note: Google doesn't return a new refresh_token, so we keep the old one
            new_creds = Credentials(
                token=token_data['access_token'],
                refresh_token=refresh_token,  # Keep existing refresh token
                token_uri=self.token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.oauth_scopes,
                expiry=new_expiry
            )
            
            # Update database with new access token
            await self._update_oauth_tokens_from_refresh(user_id, email, token_data['access_token'], new_expiry)
            
            # Update cache
            self._oauth_credentials_cache[email] = (new_creds, datetime.now())
            
            logger.info(f"✅ Token refreshed successfully for {email}, expires at {new_expiry}")
            
            return new_creds
            
        except Exception as e:
            logger.error(f"❌ Async token refresh failed for {email}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _mark_account_needs_reauth(self, user_id: str, email: str):
        """Mark an account as needing re-authentication"""
        try:
            conn = await db_manager.get_connection()
            try:
                await conn.execute('''
                    UPDATE google_oauth_accounts
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE user_id = $1 AND email_address = $2
                ''', user_id, email)
                logger.warning(f"⚠️ Marked {email} as needing re-authentication")
            finally:
                await db_manager.release_connection(conn)
        except Exception as e:
            logger.error(f"Failed to mark account for reauth: {e}")
    
    async def _update_oauth_tokens_from_refresh(self, user_id: str, email: str,
                                                 access_token: str, expires_at: datetime):
        """Update only the access token after a refresh (refresh token stays the same)"""
        try:
            encrypted_access_token = encrypt_token(access_token)
            
            conn = await db_manager.get_connection()
            try:
                await conn.execute('''
                    UPDATE google_oauth_accounts
                    SET access_token_encrypted = $1, token_expires_at = $2, updated_at = NOW()
                    WHERE user_id = $3 AND email_address = $4
                ''', encrypted_access_token, expires_at, user_id, email)
            finally:
                await db_manager.release_connection(conn)
                
            logger.debug(f"Updated access token in database for {email}")
            
        except Exception as e:
            logger.error(f"Failed to update tokens for {email}: {e}")
    
    async def refresh_all_tokens(self, user_id: str) -> Dict[str, bool]:
        """
        Proactively refresh all tokens for a user
        
        Call this periodically (e.g., every 45 minutes) to keep tokens fresh.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict mapping email -> success status
        """
        results = {}
        
        try:
            # Get all active accounts
            conn = await db_manager.get_connection()
            try:
                rows = await conn.fetch('''
                    SELECT email_address, refresh_token_encrypted, token_expires_at
                    FROM google_oauth_accounts
                    WHERE user_id = $1 AND is_active = TRUE
                ''', user_id)
            finally:
                await db_manager.release_connection(conn)
            
            for row in rows:
                email = row['email_address']
                expires_at = row['token_expires_at']
                
                # Check if token needs refresh (expires within 15 minutes)
                if expires_at:
                    buffer_time = datetime.now(timezone.utc) + timedelta(minutes=15)
                    if expires_at > buffer_time:
                        logger.debug(f"Token for {email} still valid until {expires_at}, skipping refresh")
                        results[email] = True
                        continue
                
                # Decrypt refresh token and refresh
                try:
                    refresh_token = decrypt_token(row['refresh_token_encrypted'])
                    if refresh_token:
                        new_creds = await self._refresh_token_async(user_id, email, refresh_token)
                        results[email] = new_creds is not None
                    else:
                        logger.warning(f"No refresh token for {email}")
                        results[email] = False
                except Exception as e:
                    logger.error(f"Failed to refresh {email}: {e}")
                    results[email] = False
            
            success_count = sum(1 for v in results.values() if v)
            logger.info(f"🔄 Token refresh complete: {success_count}/{len(results)} accounts refreshed")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to refresh all tokens: {e}")
            return results
    
    async def get_analytics_credentials(self, user_id: str, email: Optional[str] = None):
        """
        Get credentials specifically for Analytics API with proper timezone handling
        """
        # Get credentials the normal way
        creds = await self.get_valid_credentials(user_id, email)
        
        if not creds:
            return None
        
        # CRITICAL FIX: Ensure expiry is timezone-aware for Analytics
        # (Analytics uses synchronous google-analytics-data library which is stricter)
        if creds.expiry and creds.expiry.tzinfo is None:
            # Create new credentials with timezone-aware expiry
            creds = Credentials(
                token=creds.token,
                refresh_token=creds.refresh_token,
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=creds.scopes,
                expiry=creds.expiry.replace(tzinfo=timezone.utc)
            )
        
        return creds
    
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
                    expires_at = row['token_expires_at']
                    
                    # Determine if expired or expiring soon
                    is_expired = False
                    expiring_soon = False
                    if expires_at:
                        now = datetime.now(timezone.utc)
                        is_expired = now > expires_at
                        expiring_soon = not is_expired and (expires_at - now) < timedelta(minutes=15)
                    
                    accounts.append({
                        'email': row['email_address'],
                        'scopes': scopes,
                        'authenticated_at': row['authenticated_at'],
                        'expires_at': expires_at,
                        'is_expired': is_expired,
                        'expiring_soon': expiring_soon
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
                    'is_expired': False,
                    'expiring_soon': False
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
            
            # Calculate expiration time (timezone-aware)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get('expires_in', 3600))
            
            query = '''
                INSERT INTO google_oauth_accounts
                (user_id, email_address, access_token_encrypted, refresh_token_encrypted, 
                 token_expires_at, scopes, auth_flow_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, email_address) DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                    token_expires_at = EXCLUDED.token_expires_at,
                    is_active = TRUE,
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
                token_uri=self.token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.oauth_scopes,
                expiry=expires_at
            )
            
            self._oauth_credentials_cache[user_email] = (credentials, datetime.now())
            
            logger.info(f"OAuth tokens stored for {user_email}")
            
        except Exception as e:
            logger.error(f"Failed to store OAuth tokens: {e}")
            raise
    
    async def _load_oauth_credentials(self, user_id: str, email: str):
        """Load and decrypt OAuth credentials from database, refreshing if needed"""
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
                    logger.warning(f"No credentials found for {email}")
                    return None
                
                # Decrypt tokens
                access_token = decrypt_token(row['access_token_encrypted'])
                refresh_token = decrypt_token(row['refresh_token_encrypted']) if row['refresh_token_encrypted'] else None
                expires_at = row['token_expires_at']
                
                # Make expiry timezone-aware if it isn't
                if expires_at and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                
            finally:
                await db_manager.release_connection(conn)
            
            # FIX: Check if token is expired or expiring soon, and refresh if needed
            needs_refresh = False
            if expires_at:
                buffer_time = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_REFRESH_BUFFER_MINUTES)
                if expires_at <= buffer_time:
                    needs_refresh = True
                    logger.info(f"Token for {email} from database is expired/expiring, attempting refresh...")
            
            if needs_refresh and refresh_token:
                # Try to refresh
                new_creds = await self._refresh_token_async(user_id, email, refresh_token)
                if new_creds:
                    return new_creds
                else:
                    # Refresh failed
                    raise GoogleTokenExpiredError(
                        f"Token expired and refresh failed for {email}. Use 'google auth setup' to re-authenticate."
                    )
            
            # Create credentials object
            credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri=self.token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.oauth_scopes,
                expiry=expires_at
            )
            
            # Enforce cache size limit
            if len(self._oauth_credentials_cache) >= MAX_CREDENTIALS_CACHE_SIZE:
                # Remove oldest entries
                sorted_cache = sorted(
                    self._oauth_credentials_cache.items(),
                    key=lambda x: x[1][1]  # Sort by cached_at timestamp
                )
                for old_email, _ in sorted_cache[:10]:  # Remove 10 oldest
                    del self._oauth_credentials_cache[old_email]
            
            # Cache for future use
            self._oauth_credentials_cache[email] = (credentials, datetime.now())
            
            return credentials
            
        except GoogleTokenExpiredError:
            raise
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
            expires_at = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
            
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
        
        logger.info(f"🔑 get_aiogoogle_creds called: user_id={user_id}, email={email}")
        
        # Get regular credentials first
        credentials = await self.get_valid_credentials(user_id, email)
        
        logger.info(f"🔑 get_valid_credentials returned: {credentials is not None}")
        
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

async def refresh_all_google_tokens(user_id: str) -> Dict[str, bool]:
    """Proactively refresh all tokens for a user"""
    return await google_auth_manager.refresh_all_tokens(user_id)
