# modules/integrations/google_workspace/oauth_manager.py
"""
Google Workspace Authentication Manager
Railway-compatible OAuth Device Flow + Service Account Hybrid System

This module handles:
1. Service Account authentication for carl@bcdodge.me domain
2. OAuth Device Flow for additional Gmail accounts (Railway-friendly)
3. Token management with Fort Knox encryption
4. Automatic token refresh and error handling
5. Multi-account support with unified API access

Authentication Flows:
- Service Account: Seamless access to domain resources
- Device Flow: User-friendly authentication for additional accounts
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
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
    logger.warning("⚠️ Google auth libraries not installed - install google-auth and google-auth-oauthlib")

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
    Combines service account and OAuth device flow authentication
    """
    
    def __init__(self):
        """Initialize authentication manager with environment configuration"""
        
        if not GOOGLE_AUTH_AVAILABLE:
            logger.error("❌ Google authentication libraries not available")
            raise RuntimeError("Google auth libraries required - run: pip install google-auth google-auth-oauthlib")
        
        # V1 Configuration (working credentials)
        self.client_id = os.getenv('GOOGLE_CLIENT_ID', '301236765855-eb1n47m7pg904kr6ng56c3179lrpbju5.apps.googleusercontent.com')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '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')
        
        # Service Account Configuration
        self.service_account_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        self.workspace_domain = os.getenv('GOOGLE_WORKSPACE_DOMAIN', 'bcdodge.me')
        self.admin_email = os.getenv('GOOGLE_WORKSPACE_ADMIN_EMAIL', 'carl@bcdodge.me')
        
        # OAuth Scopes (comprehensive access)
        self.oauth_scopes = [
            'https://www.googleapis.com/auth/analytics.readonly',
            'https://www.googleapis.com/auth/webmasters.readonly',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        
        # Device Flow URLs
        self.device_code_url = 'https://oauth2.googleapis.com/device/code'
        self.token_url = 'https://oauth2.googleapis.com/token'
        self.device_verification_url = 'https://www.google.com/device'
        
        # Authentication state
        self._service_credentials = None
        self._oauth_credentials_cache = {}  # email -> credentials
        self._device_flow_cache = {}  # device_code -> flow_data
        
        logger.info("🔐 Google Auth Manager initialized")
    
    async def initialize_service_account(self) -> bool:
        """
        Initialize service account authentication for domain access
        
        Returns:
            True if service account is ready, False if not configured
        """
        try:
            if not os.path.exists(self.service_account_path):
                logger.warning(f"⚠️ Service account file not found: {self.service_account_path}")
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
            
            logger.info("✅ Service account authentication initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Service account initialization failed: {e}")
            return False
    
    async def start_oauth_device_flow(self, user_id: str) -> Dict[str, str]:
        """
        Start OAuth device flow for additional Google accounts
        Railway-compatible - no browser popup required
        
        Args:
            user_id: User ID for token storage
            
        Returns:
            Dict with device_code, user_code, verification_url, and expires_in
        """
        try:
            payload = {
                'client_id': self.client_id,
                'scope': ' '.join(self.oauth_scopes)
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.device_code_url, data=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise GoogleAuthenticationError(f"Device flow start failed: {error_text}")
                    
                    data = await response.json()
                    
                    # Store device flow state temporarily
                    device_code = data['device_code']
                    self._device_flow_cache[f"{user_id}:{device_code}"] = {
                        **data,
                        'created_at': datetime.now()
                    }
                    
                    logger.info(f"🎯 Device flow started for user {user_id}")
                    
                    return {
                        'device_code': device_code,
                        'user_code': data['user_code'],
                        'verification_url': data['verification_url'],
                        'expires_in': data['expires_in'],
                        'interval': data.get('interval', 5)
                    }
                    
        except Exception as e:
            logger.error(f"❌ Device flow start failed: {e}")
            raise GoogleAuthenticationError(f"Failed to start device flow: {e}")
    
    async def poll_device_flow_completion(self, user_id: str, device_code: str) -> Dict[str, Any]:
        """
        Poll for device flow completion and exchange for tokens
        
        Args:
            user_id: User ID
            device_code: Device code from start_oauth_device_flow
            
        Returns:
            Dict with success status and token info
        """
        try:
            # Get device flow state
            key = f"{user_id}:{device_code}"
            flow_state = self._device_flow_cache.get(key)
            
            if not flow_state:
                raise GoogleAuthenticationError("Device flow state not found")
            
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'device_code': device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, data=payload) as response:
                    data = await response.json()
                    
                    if response.status == 200:
                        # Success! Store the tokens
                        await self._store_oauth_tokens(user_id, data)
                        
                        # Get user email from token
                        user_email = await self._get_user_email_from_token(data['access_token'])
                        
                        # Clean up device flow cache
                        del self._device_flow_cache[key]
                        
                        logger.info(f"✅ OAuth completed for {user_email}")
                        
                        return {
                            'success': True,
                            'email': user_email,
                            'access_expires_in': data.get('expires_in', 3600)
                        }
                    
                    elif response.status == 428:  # Authorization pending
                        return {
                            'success': False,
                            'status': 'pending',
                            'message': 'User has not completed authorization yet'
                        }
                    
                    elif response.status == 400:
                        error = data.get('error', 'unknown')
                        if error == 'expired_token':
                            # Clean up expired device flow
                            if key in self._device_flow_cache:
                                del self._device_flow_cache[key]
                            return {
                                'success': False,
                                'status': 'expired',
                                'message': 'Device code expired. Please start over.'
                            }
                        elif error == 'access_denied':
                            return {
                                'success': False,
                                'status': 'denied',
                                'message': 'User denied authorization'
                            }
                    
                    # Other error
                    error_msg = data.get('error_description', 'Unknown error')
                    raise GoogleAuthenticationError(f"Token exchange failed: {error_msg}")
                    
        except Exception as e:
            logger.error(f"❌ Device flow polling failed: {e}")
            if isinstance(e, GoogleAuthenticationError):
                raise
            else:
                raise GoogleAuthenticationError(f"Device flow polling error: {e}")
    
    async def get_valid_credentials(self, user_id: str, email: Optional[str] = None):
        """
        Get valid credentials for API calls, refreshing if necessary
        
        Args:
            user_id: User ID
            email: Specific email account, or None for service account
            
        Returns:
            Valid credentials or None if unavailable
        """
        try:
            if email is None:
                # Use service account
                if self._service_credentials:
                    if self._service_credentials.expired:
                        self._service_credentials.refresh(Request())
                    return self._service_credentials
                else:
                    logger.warning("⚠️ Service account not initialized")
                    return None
            
            # Use OAuth credentials for specific email
            if email in self._oauth_credentials_cache:
                creds = self._oauth_credentials_cache[email]
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Update stored tokens
                        await self._update_oauth_tokens(user_id, email, creds)
                        return creds
                    except RefreshError:
                        logger.error(f"❌ Token refresh failed for {email}")
                        # Remove invalid credentials
                        del self._oauth_credentials_cache[email]
                        raise GoogleTokenExpiredError(f"Hey, your Google Authorization expired again! Use 'google auth setup' to renew.")
                return creds
            
            # Load from database
            return await self._load_oauth_credentials(user_id, email)
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to get credentials: {e}")
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
            async with db_manager.get_connection() as conn:
                rows = await conn.fetch(query, user_id)
                
                for row in rows:
                    accounts.append({
                        'email': row['email_address'],
                        'scopes': row['scopes'],
                        'authenticated_at': row['authenticated_at'],
                        'expires_at': row['token_expires_at'],
                        'is_expired': datetime.now() > row['token_expires_at'] if row['token_expires_at'] else False
                    })
            
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
            logger.error(f"❌ Failed to get authenticated accounts: {e}")
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
            async with db_manager.get_connection() as conn:
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
                    
                    await conn.execute(
                        query,
                        user_id,
                        service_account_data.get('client_email'),
                        encrypted_key,
                        self.workspace_domain,
                        self.oauth_scopes
                    )
                    
                    logger.info("🔐 Service account config stored securely")
                    
        except Exception as e:
            logger.error(f"❌ Failed to store service account config: {e}")
    
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
            
            async with db_manager.get_connection() as conn:
                await conn.execute(
                    query,
                    user_id,
                    user_email,
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_at,
                    self.oauth_scopes,
                    'oauth'
                )
            
            # Cache credentials
            credentials = Credentials(
                token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token'),
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.oauth_scopes
            )
            
            self._oauth_credentials_cache[user_email] = credentials
            
            logger.info(f"🔐 OAuth tokens stored for {user_email}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store OAuth tokens: {e}")
            raise
    
    async def _load_oauth_credentials(self, user_id: str, email: str):
        """Load and decrypt OAuth credentials from database"""
        try:
            query = '''
                SELECT access_token_encrypted, refresh_token_encrypted, token_expires_at
                FROM google_oauth_accounts
                WHERE user_id = $1 AND email_address = $2 AND is_active = TRUE
            '''
            
            async with db_manager.get_connection() as conn:
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
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    scopes=self.oauth_scopes,
                    expiry=row['token_expires_at']
                )
                
                # Cache for future use
                self._oauth_credentials_cache[email] = credentials
                
                return credentials
                
        except Exception as e:
            logger.error(f"❌ Failed to load OAuth credentials for {email}: {e}")
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
            logger.error(f"❌ Failed to get user email: {e}")
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
            
            async with db_manager.get_connection() as conn:
                await conn.execute(query, encrypted_access_token, expires_at, user_id, email)
                
            logger.info(f"🔄 Tokens updated for {email}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update tokens for {email}: {e}")

# Global instance
google_auth_manager = GoogleAuthManager()

# Convenience functions for other modules
async def get_google_credentials(user_id: str, email: Optional[str] = None):
    """Get valid Google credentials for API calls"""
    return await google_auth_manager.get_valid_credentials(user_id, email)

async def start_google_oauth(user_id: str) -> Dict[str, str]:
    """Start Google OAuth device flow"""
    return await google_auth_manager.start_oauth_device_flow(user_id)

async def check_oauth_completion(user_id: str, device_code: str) -> Dict[str, Any]:
    """Check if OAuth device flow is complete"""
    return await google_auth_manager.poll_device_flow_completion(user_id, device_code)

async def get_google_accounts(user_id: str) -> List[Dict[str, Any]]:
    """Get list of authenticated Google accounts"""
    return await google_auth_manager.get_authenticated_accounts(user_id)
