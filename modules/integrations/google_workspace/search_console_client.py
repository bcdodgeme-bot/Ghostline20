# modules/integrations/google_workspace/search_console_client.py
"""
Google Search Console Client - PRIMARY FOCUS
Keyword Opportunity Detection & Existing Keyword Table Integration

This module:
1. Fetches Search Console data for all 5 sites
2. Identifies new keyword opportunities
3. Integrates with EXISTING keyword tables (bcdodge_keywords, etc.)
4. Presents opportunities for user approval
5. Adds approved keywords to site tables and expanded_keywords_for_trends

Keyword Flow:
Search Console finds keyword → Store in google_search_console_data → 
Create opportunity → Ask user (add/ignore) → If add: site table + expansion table
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

# Import after logger setup
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    SEARCH_CONSOLE_AVAILABLE = True
except ImportError:
    SEARCH_CONSOLE_AVAILABLE = False
    logger.warning("⚠️ Google API client not installed - install google-api-python-client")

from . import SUPPORTED_SITES
from .oauth_manager import get_google_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class SearchConsoleClient:
    """
    Google Search Console API client with keyword opportunity detection
    Integrates with existing keyword tables for content strategy
    """
    
    def __init__(self):
        """Initialize Search Console client"""
        if not SEARCH_CONSOLE_AVAILABLE:
            logger.error("❌ Google API client not available")
            raise RuntimeError("Google API client required - run: pip install google-api-python-client")
        
        self._service = None
        self._user_id = None
        
        logger.info("🔍 Search Console client initialized")
    
    async def initialize(self, user_id: str):
        """
        Initialize Search Console service with credentials
        
        Args:
            user_id: User ID for credential lookup
        """
        try:
            self._user_id = user_id
            
            # Get credentials from auth manager
            credentials = await get_google_credentials(user_id, email=None)
            
            if not credentials:
                raise Exception("No valid credentials available")
            
            # Build Search Console service
            self._service = build('searchconsole', 'v1', credentials=credentials)
            
            logger.info("✅ Search Console service initialized")
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Search Console initialization failed: {e}")
            raise
    
    async def fetch_search_data_for_site(self, site_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch Search Console data for a specific site
        
        Args:
            site_name: Site identifier (bcdodge, rose_angel, etc.)
            days: Number of days of data to fetch
            
        Returns:
            List of search query data with clicks, impressions, CTR, position
        """
        try:
            if not self._service:
                raise Exception("Search Console service not initialized")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            site_url = site_config['search_console_url']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Build request
            request = {
                'startDate': start_date.isoformat(),
                'endDate': end_date.isoformat(),
                'dimensions': ['query'],
                'rowLimit': 1000,  # Get top 1000 queries
                'dataState': 'final'  # Only finalized data
            }
            
            logger.info(f"📊 Fetching Search Console data for {site_name}...")
            
            # Execute request
            response = self._service.searchanalytics().query(
                siteUrl=site_url,
                body=request
            ).execute()
            
            rows = response.get('rows', [])
            
            logger.info(f"✅ Found {len(rows)} search queries for {site_name}")
            
            return rows
            
        except HttpError as e:
            if e.resp.status == 403:
                logger.error(f"❌ Access denied for {site_name} - check Search Console permissions")
            else:
                logger.error(f"❌ Search Console API error for {site_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Failed to fetch data for {site_name}: {e}")
            return []
    
    async def fetch_all_sites_data(self, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch Search Console data for all configured sites
        
        Args:
            days: Number of days of data to fetch
            
        Returns:
            Dict mapping site_name to list of search query data
        """
        results = {}
        
        for site_name in SUPPORTED_SITES.keys():
            try:
                data = await self.fetch_search_data_for_site(site_name, days)
                results[site_name] = data
            except Exception as e:
                logger.error(f"❌ Failed to fetch data for {site_name}: {e}")
                results[site_name] = []
        
        return results
    
    async def store_search_console_data(self, site_name: str, search_data: List[Dict[str, Any]]):
        """
        Store Search Console data in database
        
        Args:
            site_name: Site identifier
            search_data: List of search query data from API
        """
        try:
            if not search_data:
                logger.info(f"ℹ️ No data to store for {site_name}")
                return
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            site_url = site_config['search_console_url']
            
            async with db_manager.get_connection() as conn:
                for row in search_data:
                    query = row.get('keys', [''])[0]  # Query is in keys[0]
                    clicks = row.get('clicks', 0)
                    impressions = row.get('impressions', 0)
                    ctr = row.get('ctr', 0.0)
                    position = row.get('position', 0.0)
                    
                    # Store in database
                    await conn.execute('''
                        INSERT INTO google_search_console_data
                        (user_id, site_name, site_url, query, clicks, impressions, ctr, position, date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (user_id, site_name, query, date) DO UPDATE SET
                            clicks = EXCLUDED.clicks,
                            impressions = EXCLUDED.impressions,
                            ctr = EXCLUDED.ctr,
                            position = EXCLUDED.position
                    ''', 
                    self._user_id,
                    site_name,
                    site_url,
                    query,
                    clicks,
                    impressions,
                    ctr,
                    position,
                    datetime.now().date()
                    )
            
            logger.info(f"✅ Stored {len(search_data)} queries for {site_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store Search Console data: {e}")
            raise
    
    async def identify_keyword_opportunities(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Identify new keyword opportunities from Search Console data
        
        Opportunities are keywords that:
        1. Are NOT in the existing site keyword table
        2. Have decent impressions (100+)
        3. Are in positions 11-30 (page 2-3, improvable)
        
        Args:
            site_name: Site identifier
            
        Returns:
            List of keyword opportunity dictionaries
        """
        try:
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            keyword_table = site_config['keyword_table']
            
            async with db_manager.get_connection() as conn:
                # Find keywords NOT in existing table with opportunity potential
                opportunities = await conn.fetch(f'''
                    SELECT 
                        gsc.query as keyword,
                        gsc.clicks,
                        gsc.impressions,
                        gsc.ctr,
                        gsc.position,
                        gsc.date
                    FROM google_search_console_data gsc
                    WHERE gsc.user_id = $1
                        AND gsc.site_name = $2
                        AND gsc.impressions >= 100
                        AND gsc.position BETWEEN 11 AND 30
                        AND gsc.user_decision IS NULL
                        AND NOT EXISTS (
                            SELECT 1 FROM {keyword_table} kt
                            WHERE LOWER(kt.keyword) = LOWER(gsc.query)
                        )
                    ORDER BY gsc.impressions DESC, gsc.position ASC
                    LIMIT 50
                ''', self._user_id, site_name)
                
                opportunity_list = []
                for opp in opportunities:
                    opportunity_list.append({
                        'keyword': opp['keyword'],
                        'clicks': opp['clicks'],
                        'impressions': opp['impressions'],
                        'ctr': float(opp['ctr']),
                        'position': float(opp['position']),
                        'date': opp['date'],
                        'site_name': site_name,
                        'opportunity_type': self._classify_opportunity(opp),
                        'potential_impact': self._estimate_impact(opp)
                    })
                
                logger.info(f"🎯 Found {len(opportunity_list)} keyword opportunities for {site_name}")
                
                return opportunity_list
                
        except Exception as e:
            logger.error(f"❌ Failed to identify opportunities for {site_name}: {e}")
            return []
    
    def _classify_opportunity(self, data: Dict[str, Any]) -> str:
        """Classify the type of keyword opportunity"""
        position = float(data['position'])
        impressions = data['impressions']
        
        if position <= 15 and impressions >= 500:
            return 'quick_win'  # High visibility, easy to push to page 1
        elif position <= 20 and impressions >= 200:
            return 'content_boost'  # Needs content improvement
        else:
            return 'long_term'  # Requires sustained effort
    
    def _estimate_impact(self, data: Dict[str, Any]) -> str:
        """Estimate potential impact of optimizing for this keyword"""
        impressions = data['impressions']
        position = float(data['position'])
        
        # High impressions + decent position = high potential
        if impressions >= 1000 and position <= 20:
            return 'high'
        elif impressions >= 500 and position <= 25:
            return 'medium'
        else:
            return 'low'
    
    async def add_keyword_to_site_table(self, site_name: str, keyword: str) -> bool:
        """
        Add approved keyword to site-specific keyword table
        
        Args:
            site_name: Site identifier
            keyword: Keyword to add
            
        Returns:
            True if added successfully
        """
        try:
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            keyword_table = site_config['keyword_table']
            
            async with db_manager.get_connection() as conn:
                # Add to site keyword table
                await conn.execute(f'''
                    INSERT INTO {keyword_table} (keyword, source, added_date)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (keyword) DO NOTHING
                ''', keyword, 'search_console', datetime.now())
                
                # Mark as added in search console data
                await conn.execute('''
                    UPDATE google_search_console_data
                    SET added_to_keywords = TRUE,
                        user_decision = 'add',
                        keyword_table_name = $1
                    WHERE user_id = $2 AND site_name = $3 AND query = $4
                ''', keyword_table, self._user_id, site_name, keyword)
            
            logger.info(f"✅ Added keyword '{keyword}' to {keyword_table}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add keyword to {site_name} table: {e}")
            return False
    
    async def ignore_keyword_opportunity(self, site_name: str, keyword: str) -> bool:
        """
        Mark keyword opportunity as ignored
        
        Args:
            site_name: Site identifier
            keyword: Keyword to ignore
            
        Returns:
            True if marked successfully
        """
        try:
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    UPDATE google_search_console_data
                    SET user_decision = 'ignore'
                    WHERE user_id = $1 AND site_name = $2 AND query = $3
                ''', self._user_id, site_name, keyword)
            
            logger.info(f"✅ Ignored keyword '{keyword}' for {site_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to ignore keyword: {e}")
            return False
    
    async def get_pending_opportunities(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get pending keyword opportunities across all sites
        
        Args:
            limit: Maximum number of opportunities to return
            
        Returns:
            List of pending keyword opportunities
        """
        try:
            async with db_manager.get_connection() as conn:
                opportunities = await conn.fetch('''
                    SELECT * FROM google_new_keyword_opportunities
                    LIMIT $1
                ''', limit)
                
                return [dict(opp) for opp in opportunities]
                
        except Exception as e:
            logger.error(f"❌ Failed to get pending opportunities: {e}")
            return []

# Global instance
search_console_client = SearchConsoleClient()

# Convenience functions for other modules
async def fetch_search_console_data(user_id: str, site_name: Optional[str] = None, days: int = 7):
    """Fetch Search Console data for site(s)"""
    await search_console_client.initialize(user_id)
    
    if site_name:
        return await search_console_client.fetch_search_data_for_site(site_name, days)
    else:
        return await search_console_client.fetch_all_sites_data(days)

async def find_keyword_opportunities(user_id: str, site_name: str) -> List[Dict[str, Any]]:
    """Find keyword opportunities for a site"""
    await search_console_client.initialize(user_id)
    return await search_console_client.identify_keyword_opportunities(site_name)

async def approve_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Approve and add keyword to site table"""
    await search_console_client.initialize(user_id)
    return await search_console_client.add_keyword_to_site_table(site_name, keyword)

async def reject_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Reject/ignore keyword opportunity"""
    await search_console_client.initialize(user_id)
    return await search_console_client.ignore_keyword_opportunity(site_name, keyword)