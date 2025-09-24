# modules/integrations/bluesky/multi_account_client.py
"""
Multi-Account Bluesky API Client
Handles authentication and operations across 5 accounts
"""

import os
import requests
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BlueskyMultiClient:
    """Multi-account Bluesky client with smart rate limiting"""
    
    def __init__(self):
        self.api_base = "https://bsky.social"
        self.accounts = self._load_account_config()
        self.sessions = {}
        self.last_scan = {}
        self.scan_interval = timedelta(hours=3, minutes=30)  # 3.5 hour intervals
        
    def _load_account_config(self) -> Dict[str, Dict]:
        """Load account configuration from environment variables"""
        return {
            'personal': {
                'handle': os.getenv('BLUESKY_PERSONAL_HANDLE', 'bcdodgeme.bsky.social'),
                'password': os.getenv('BLUESKY_PERSONAL_PASSWORD', '#062308Ghada!'),
                'personality': 'syntaxprime',
                'keywords_table': 'bcdodge_keywords',  # 884 keywords (personal blog)
                'can_cross_to': ['rose_angel', 'binge_tv'],
                'ai_posting_allowed': True,
                'pg13_mode': True,
                'keyword_count': 884,
                'description': 'Personal account - Syntax proven successful here'
            },
            'rose_angel': {
                'handle': os.getenv('BLUESKY_ROSE_ANGEL_HANDLE', 'roseandangel.bsky.social'),
                'password': os.getenv('BLUESKY_ROSE_ANGEL_PASSWORD', 'RWsArrfwdkMWDb4'), 
                'personality': 'professional',
                'keywords_table': 'roseandangel_keywords',  # 1,451 keywords (consulting agency)
                'can_cross_to': ['personal', 'meals_feelz'],
                'ai_posting_allowed': False,
                'sensitive_topics': True,
                'keyword_count': 1451,
                'description': 'Rose & Angel - Non-profit consulting, professional tone only'
            },
            'binge_tv': {
                'handle': os.getenv('BLUESKY_BINGE_TV_HANDLE', 'tvsignals.bsky.social'),
                'password': os.getenv('BLUESKY_BINGE_TV_PASSWORD', 'wpaQ2MQdCs4RfQG'),
                'personality': 'syntaxprime',
                'keywords_table': 'tvsignals_keywords',  # 295 keywords (streaming content)
                'can_cross_to': ['personal'],
                'ai_posting_allowed': True,
                'pg13_mode': True,
                'keyword_count': 295,
                'description': 'Binge TV - Entertainment content, Syntax tone OK'
            },
            'meals_feelz': {
                'handle': os.getenv('BLUESKY_MEALS_FEELZ_HANDLE', 'mealsnfeelz.bsky.social'),
                'password': os.getenv('BLUESKY_MEALS_FEELZ_PASSWORD', '55X3XyFwMHGfsNG'),
                'personality': 'compassionate',
                'keywords_table': 'mealsnfeelz_keywords',  # 312 keywords (food nonprofit startup)
                'can_cross_to': ['personal', 'rose_angel'],
                'ai_posting_allowed': False,
                'sensitive_topics': True,
                'religious_context': True,
                'keyword_count': 312,
                'description': 'Meals n Feelz - Islamic giving + food programs, very sensitive'
            },
            'damn_it_carl': {
                'handle': os.getenv('BLUESKY_DAMN_IT_CARL_HANDLE', 'syntax-ceo.bsky.social'),
                'password': os.getenv('BLUESKY_DAMN_IT_CARL_PASSWORD', 'C9T.uhTRYqEPxH.'),
                'personality': 'syntaxprime',
                'keywords_table': 'damnitcarl_keywords',  # 402 keywords (creative burnout + merch)
                'can_cross_to': [],  # ISLAND MODE
                'ai_posting_allowed': True,
                'creative_dumping': True,
                'keyword_count': 402,
                'description': 'Damn it Carl - Creative dumping ground, Syntax\'s baby'
            }
        }
    
    async def authenticate_account(self, account_id: str) -> bool:
        """Authenticate a specific account"""
        account = self.accounts.get(account_id)
        if not account or not account['password']:
            logger.warning(f"Account {account_id} not configured or missing password")
            return False
        
        try:
            auth_url = f"{self.api_base}/xrpc/com.atproto.server.createSession"
            
            auth_data = {
                "identifier": account['handle'],
                "password": account['password']
            }
            
            response = requests.post(auth_url, json=auth_data, timeout=10)
            response.raise_for_status()
            
            session_data = response.json()
            
            self.sessions[account_id] = {
                'access_jwt': session_data.get('accessJwt'),
                'refresh_jwt': session_data.get('refreshJwt'),
                'authenticated_at': datetime.now(),
                'handle': account['handle']
            }
            
            logger.info(f"✅ Authenticated Bluesky account: {account['handle']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Authentication failed for {account_id}: {e}")
            return False
    
    async def authenticate_all_accounts(self) -> Dict[str, bool]:
        """Authenticate all configured accounts"""
        results = {}
        
        for account_id in self.accounts.keys():
            if self.accounts[account_id]['password']:  # Only try if password is set
                results[account_id] = await self.authenticate_account(account_id)
            else:
                results[account_id] = False
                logger.warning(f"Skipping {account_id} - no password configured")
        
        authenticated_count = sum(results.values())
        logger.info(f"🔵 Bluesky Multi-Account Status: {authenticated_count}/{len(results)} accounts authenticated")
        
        return results
    
    def get_auth_headers(self, account_id: str) -> Dict[str, str]:
        """Get authentication headers for specific account"""
        session = self.sessions.get(account_id)
        if not session or not session.get('access_jwt'):
            return {}
        
        return {
            "Authorization": f"Bearer {session['access_jwt']}",
            "Content-Type": "application/json"
        }
    
    async def get_timeline(self, account_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch timeline for specific account"""
        if account_id not in self.sessions:
            if not await self.authenticate_account(account_id):
                return []
        
        try:
            timeline_url = f"{self.api_base}/xrpc/app.bsky.feed.getTimeline"
            params = {"limit": limit}
            
            response = requests.get(
                timeline_url,
                headers=self.get_auth_headers(account_id),
                params=params,
                timeout=15
            )
            response.raise_for_status()
            
            timeline_data = response.json()
            posts = timeline_data.get('feed', [])
            
            logger.info(f"📱 Fetched {len(posts)} posts from {account_id} timeline")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch timeline for {account_id}: {e}")
            return []
    
    async def get_all_timelines(self) -> Dict[str, List[Dict]]:
        """Fetch timelines for all authenticated accounts"""
        timelines = {}
        
        for account_id in self.accounts.keys():
            if account_id in self.sessions:
                timeline = await self.get_timeline(account_id)
                timelines[account_id] = timeline
                
                # Update last scan time
                self.last_scan[account_id] = datetime.now()
        
        return timelines
    
    async def create_post(self, account_id: str, text: str, reply_to: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a post on specific account"""
        if account_id not in self.sessions:
            if not await self.authenticate_account(account_id):
                return {"success": False, "error": "Authentication failed"}
        
        if len(text) > 300:
            return {"success": False, "error": f"Post too long ({len(text)}/300 characters)"}
        
        try:
            record = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.utcnow().isoformat() + "Z"
            }
            
            if reply_to:
                record["reply"] = reply_to
            
            create_url = f"{self.api_base}/xrpc/com.atproto.repo.createRecord"
            post_data = {
                "repo": self.accounts[account_id]['handle'],
                "collection": "app.bsky.feed.post",
                "record": record
            }
            
            response = requests.post(
                create_url,
                headers=self.get_auth_headers(account_id),
                json=post_data,
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            
            logger.info(f"✅ Posted to {account_id}: '{text[:50]}...'")
            
            return {
                "success": True,
                "account_id": account_id,
                "uri": result.get("uri"),
                "cid": result.get("cid"),
                "text": text,
                "char_count": len(text),
                "posted_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create post on {account_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def should_scan_account(self, account_id: str) -> bool:
        """Check if account needs scanning based on interval"""
        last_scan = self.last_scan.get(account_id)
        if not last_scan:
            return True
        
        return datetime.now() - last_scan >= self.scan_interval
    
    def get_account_info(self, account_id: str) -> Dict[str, Any]:
        """Get account configuration and status"""
        if account_id not in self.accounts:
            return {}
        
        account = self.accounts[account_id].copy()
        account['authenticated'] = account_id in self.sessions
        account['last_scan'] = self.last_scan.get(account_id)
        account['needs_scan'] = self.should_scan_account(account_id)
        
        # Don't expose password in info
        account.pop('password', None)
        
        return account
    
    def get_all_accounts_status(self) -> Dict[str, Dict]:
        """Get status of all accounts"""
        return {
            account_id: self.get_account_info(account_id)
            for account_id in self.accounts.keys()
        }
    
    def get_configured_accounts(self) -> List[str]:
        """Get list of accounts with passwords configured"""
        return [
            account_id for account_id, config in self.accounts.items()
            if config.get('password')
        ]
    
    def get_authenticated_accounts(self) -> List[str]:
        """Get list of currently authenticated accounts"""
        return list(self.sessions.keys())

# Global multi-client instance
_multi_client = None

def get_bluesky_multi_client() -> BlueskyMultiClient:
    """Get the global multi-client instance"""
    global _multi_client
    if _multi_client is None:
        _multi_client = BlueskyMultiClient()
    return _multi_client