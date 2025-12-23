# modules/integrations/wordpress/wordpress_client.py
"""
Multi-Site WordPress API Client
Handles authentication and operations across 5 WordPress sites
Mirrors the Bluesky multi-account pattern for consistency

Sites:
- personal (bcdodge.me)
- rose_angel (roseandangel.com)
- binge_tv (tvsignals.com)
- meals_feelz (mealsnfeelz.org)
- damn_it_carl (damnitcarl.com)
"""

import os
import base64
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class WordPressMultiClient:
    """Multi-site WordPress client with REST API support"""
    
    def __init__(self):
        self.sites = self._load_site_config()
        self.sessions = {}  # Cache for aiohttp sessions
        
        # Map business areas to WordPress sites
        self.business_to_site = {
            # Personal blog
            'personal': 'personal',
            'technology': 'personal',
            'ai': 'personal',
            'productivity': 'personal',
            
            # Rose & Angel (nonprofit consulting)
            'rose_angel': 'rose_angel',
            'nonprofit': 'rose_angel',
            'consulting': 'rose_angel',
            
            # TV Signals (streaming/entertainment)
            'binge_tv': 'binge_tv',
            'tvsignals': 'binge_tv',
            'streaming': 'binge_tv',
            'entertainment': 'binge_tv',
            'tv': 'binge_tv',
            
            # Meals n Feelz (food nonprofit)
            'meals_feelz': 'meals_feelz',
            'food': 'meals_feelz',
            'charity': 'meals_feelz',
            
            # Damn it Carl (creative)
            'damn_it_carl': 'damn_it_carl',
            'creative': 'damn_it_carl',
            'burnout': 'damn_it_carl',
        }
    
    def _load_site_config(self) -> Dict[str, Dict]:
        """Load site configuration from environment variables"""
        return {
            'personal': {
                'url': os.getenv('WORDPRESS_PERSONAL_URL', 'https://bcdodge.me'),
                'user': os.getenv('WORDPRESS_PERSONAL_USER'),
                'app_password': os.getenv('WORDPRESS_PERSONAL_APP_PASSWORD'),
                'description': 'Personal blog - Tech, AI, productivity'
            },
            'rose_angel': {
                'url': os.getenv('WORDPRESS_ROSE_ANGEL_URL', 'https://roseandangel.com'),
                'user': os.getenv('WORDPRESS_ROSE_ANGEL_USER'),
                'app_password': os.getenv('WORDPRESS_ROSE_ANGEL_APP_PASSWORD'),
                'description': 'Rose & Angel - Nonprofit consulting'
            },
            'binge_tv': {
                'url': os.getenv('WORDPRESS_BINGE_TV_URL', 'https://tvsignals.com'),
                'user': os.getenv('WORDPRESS_BINGE_TV_USER'),
                'app_password': os.getenv('WORDPRESS_BINGE_TV_APP_PASSWORD'),
                'description': 'TV Signals - Streaming and entertainment'
            },
            'meals_feelz': {
                'url': os.getenv('WORDPRESS_MEALS_FEELZ_URL', 'https://mealsnfeelz.org'),
                'user': os.getenv('WORDPRESS_MEALS_FEELZ_USER'),
                'app_password': os.getenv('WORDPRESS_MEALS_FEELZ_APP_PASSWORD'),
                'description': 'Meals n Feelz - Food programs nonprofit'
            },
            'damn_it_carl': {
                'url': os.getenv('WORDPRESS_DAMN_IT_CARL_URL', 'https://damnitcarl.com'),
                'user': os.getenv('WORDPRESS_DAMN_IT_CARL_USER'),
                'app_password': os.getenv('WORDPRESS_DAMN_IT_CARL_APP_PASSWORD'),
                'description': 'Damn it Carl - Creative outlet'
            }
        }
    
    def _get_auth_header(self, site_id: str) -> Optional[str]:
        """Generate Basic Auth header for a site"""
        site = self.sites.get(site_id)
        if not site or not site.get('user') or not site.get('app_password'):
            return None
        
        # WordPress Application Passwords use Basic Auth
        credentials = f"{site['user']}:{site['app_password']}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def get_site_for_business(self, business_area: str) -> Optional[str]:
        """Map a business area to its WordPress site"""
        # Normalize business area
        normalized = business_area.lower().replace(' ', '_').replace('-', '_')
        return self.business_to_site.get(normalized)
    
    def is_site_configured(self, site_id: str) -> bool:
        """Check if a site has credentials configured"""
        site = self.sites.get(site_id)
        if not site:
            return False
        return bool(site.get('user') and site.get('app_password'))
    
    def get_configured_sites(self) -> List[str]:
        """Get list of sites with credentials configured"""
        return [
            site_id for site_id in self.sites.keys()
            if self.is_site_configured(site_id)
        ]
    
    async def create_draft(
        self,
        site_id: str,
        title: str,
        content: str,
        focus_keyword: Optional[str] = None,
        excerpt: Optional[str] = None,
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Create a draft post on a WordPress site
        
        Args:
            site_id: Site identifier (personal, rose_angel, binge_tv, etc.)
            title: Post title
            content: Post content (HTML or Markdown)
            focus_keyword: Rank Math focus keyword
            excerpt: Post excerpt/summary
            categories: List of category IDs (optional)
            tags: List of tag IDs (optional)
        
        Returns:
            Dict with success status and post details
        """
        site = self.sites.get(site_id)
        if not site:
            return {"success": False, "error": f"Unknown site: {site_id}"}
        
        auth_header = self._get_auth_header(site_id)
        if not auth_header:
            return {"success": False, "error": f"Site {site_id} not configured (missing credentials)"}
        
        # Build the post data
        post_data = {
            "title": title,
            "content": content,
            "status": "draft",  # Always create as draft
        }
        
        if excerpt:
            post_data["excerpt"] = excerpt
        
        if categories:
            post_data["categories"] = categories
        
        if tags:
            post_data["tags"] = tags
        
        # Add Rank Math focus keyword via meta
        if focus_keyword:
            post_data["meta"] = {
                "rank_math_focus_keyword": focus_keyword
            }
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{site['url']}/wp-json/wp/v2/posts"
                headers = {
                    "Authorization": auth_header,
                    "Content-Type": "application/json"
                }
                
                async with session.post(url, json=post_data, headers=headers, timeout=30) as response:
                    if response.status == 201:
                        result = await response.json()
                        
                        post_id = result.get('id')
                        post_link = result.get('link')
                        edit_link = f"{site['url']}/wp-admin/post.php?post={post_id}&action=edit"
                        
                        logger.info(f"✅ Created WordPress draft on {site_id}: {title[:50]}...")
                        
                        return {
                            "success": True,
                            "site_id": site_id,
                            "site_url": site['url'],
                            "post_id": post_id,
                            "post_link": post_link,
                            "edit_link": edit_link,
                            "title": title,
                            "focus_keyword": focus_keyword,
                            "created_at": datetime.now().isoformat()
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ WordPress API error ({response.status}): {error_text[:200]}")
                        return {
                            "success": False,
                            "error": f"API error {response.status}: {error_text[:200]}"
                        }
        
        except aiohttp.ClientError as e:
            logger.error(f"❌ WordPress connection error for {site_id}: {e}")
            return {"success": False, "error": f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"❌ WordPress draft creation failed for {site_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def create_draft_for_business(
        self,
        business_area: str,
        title: str,
        content: str,
        focus_keyword: Optional[str] = None,
        excerpt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a draft on the appropriate site for a business area
        
        Args:
            business_area: Business area from trend detection
            title: Post title
            content: Post content
            focus_keyword: Rank Math focus keyword
            excerpt: Optional excerpt
        
        Returns:
            Dict with success status and post details
        """
        site_id = self.get_site_for_business(business_area)
        
        if not site_id:
            # Default to personal blog for unknown business areas
            site_id = 'personal'
            logger.warning(f"Unknown business area '{business_area}', defaulting to personal blog")
        
        if not self.is_site_configured(site_id):
            return {
                "success": False,
                "error": f"Site '{site_id}' for business area '{business_area}' is not configured"
            }
        
        return await self.create_draft(
            site_id=site_id,
            title=title,
            content=content,
            focus_keyword=focus_keyword,
            excerpt=excerpt
        )
    
    async def test_connection(self, site_id: str) -> Dict[str, Any]:
        """Test connection to a WordPress site"""
        site = self.sites.get(site_id)
        if not site:
            return {"success": False, "error": f"Unknown site: {site_id}"}
        
        auth_header = self._get_auth_header(site_id)
        if not auth_header:
            return {"success": False, "error": "Site not configured"}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Test by fetching current user info
                url = f"{site['url']}/wp-json/wp/v2/users/me"
                headers = {"Authorization": auth_header}
                
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        return {
                            "success": True,
                            "site_id": site_id,
                            "site_url": site['url'],
                            "authenticated_as": user_data.get('name'),
                            "user_id": user_data.get('id'),
                            "capabilities": user_data.get('capabilities', {})
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Auth failed: HTTP {response.status}"
                        }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def test_all_connections(self) -> Dict[str, Dict]:
        """Test connections to all configured sites"""
        results = {}
        
        for site_id in self.sites.keys():
            if self.is_site_configured(site_id):
                results[site_id] = await self.test_connection(site_id)
            else:
                results[site_id] = {
                    "success": False,
                    "error": "Not configured (missing credentials)"
                }
        
        configured = sum(1 for r in results.values() if r.get('success'))
        logger.info(f"📝 WordPress Multi-Site Status: {configured}/{len(results)} sites connected")
        
        return results
    
    def get_all_sites_status(self) -> Dict[str, Dict]:
        """Get configuration status of all sites (sync, no API calls)"""
        return {
            site_id: {
                'url': config['url'],
                'configured': self.is_site_configured(site_id),
                'description': config['description']
            }
            for site_id, config in self.sites.items()
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_wordpress_client: Optional[WordPressMultiClient] = None


def get_wordpress_client() -> WordPressMultiClient:
    """Get the global WordPress multi-site client instance"""
    global _wordpress_client
    if _wordpress_client is None:
        _wordpress_client = WordPressMultiClient()
    return _wordpress_client


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def create_wordpress_draft(
    business_area: str,
    title: str,
    content: str,
    focus_keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to create a WordPress draft
    
    Args:
        business_area: Business area (maps to appropriate site)
        title: Post title
        content: Post content (HTML or Markdown)
        focus_keyword: Rank Math focus keyword
    
    Returns:
        Dict with success status and post details
    """
    client = get_wordpress_client()
    return await client.create_draft_for_business(
        business_area=business_area,
        title=title,
        content=content,
        focus_keyword=focus_keyword
    )