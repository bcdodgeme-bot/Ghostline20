# modules/integrations/google_workspace/search_console_client.py
"""
Search Console Client - Direct REST API Implementation
Real Search Console data fetching using aiohttp with proper async authentication
COMPLETELY ABANDONED aiogoogle library - using direct REST API calls like Analytics
"""

import json
import logging
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from . import SUPPORTED_SITES
from ...core.database import db_manager

logger = logging.getLogger(__name__)

SEARCH_CONSOLE_API_BASE = "https://searchconsole.googleapis.com/webmasters/v3"


class SearchConsoleClient:
    """Google Search Console client using direct REST API calls"""
    
    def __init__(self):
        self._user_id = None
        self._access_token = None
        logger.info("🔍 Search Console initialized (REST API)")
    
    async def initialize(self, user_id: str):
        """Initialize with Google credentials from database"""
        try:
            self._user_id = user_id
            
            # Load access token directly from database (same as Analytics)
            query = '''
                SELECT access_token_encrypted, token_expires_at
                FROM google_oauth_accounts
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY CASE WHEN email_address LIKE '%@bcdodge.me' THEN 0 ELSE 1 END
                LIMIT 1
            '''
            
            conn = await db_manager.get_connection()
            try:
                row = await conn.fetchrow(query, user_id)
                
                if not row:
                    raise Exception("No credentials found")
                
                from ...core.crypto import decrypt_token
                self._access_token = decrypt_token(row['access_token_encrypted'])
                
                # Check if token is expired
                if row['token_expires_at']:
                    from datetime import timezone
                    if datetime.now(timezone.utc) >= row['token_expires_at']:
                        logger.warning("Access token expired, needs refresh")
                        raise Exception("Token expired - please re-authenticate")
            finally:
                await db_manager.release_connection(conn)
                
            logger.info(f"✅ Search Console initialized for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Search Console initialization failed: {e}", exc_info=True)
            raise
    
    async def get_keyword_opportunities(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Get keyword opportunities - WITH AUTO-FETCH
        
        This method:
        1. Checks database for recent Search Console data
        2. If database is empty or stale, fetches from API first
        3. Returns keyword opportunities from database
        """
        try:
            logger.info(f"🎯 Getting keyword opportunities for {site_name}")
            
            if not self._user_id:
                raise Exception("Client not initialized")
            
            # Check if we have recent data in database
            conn = await db_manager.get_connection()
            try:
                latest_data = await conn.fetchrow('''
                    SELECT MAX(date) as latest_date, COUNT(*) as total_queries
                    FROM google_search_console_data
                    WHERE user_id = $1 AND site_name = $2
                ''', self._user_id, site_name)
                
                # Determine if we need fresh data
                needs_fetch = False
                
                if not latest_data or latest_data['total_queries'] == 0:
                    logger.info(f"🔍 No Search Console data in DB for {site_name}")
                    needs_fetch = True
                elif latest_data['latest_date']:
                    days_old = (datetime.now().date() - latest_data['latest_date']).days
                    logger.debug(f"🔍 Latest Search Console data is {days_old} days old")
                    
                    # Fetch if data is more than 2 days old
                    if days_old > 2:
                        logger.info(f"🔄 Search Console data is stale ({days_old} days old), fetching fresh data...")
                        needs_fetch = True
                
                # Fetch from API if needed
                if needs_fetch:
                    try:
                        logger.info(f"🌐 Fetching fresh Search Console data from Google API...")
                        await self.fetch_search_data_for_site(site_name, days=30)
                        logger.info(f"✅ Fresh Search Console data fetched and stored")
                    except Exception as fetch_error:
                        logger.error(f"⚠️ Failed to fetch from API: {fetch_error}", exc_info=True)
                        # Continue anyway - maybe we can still provide partial data
                
            finally:
                await db_manager.release_connection(conn)
            
            # Now identify opportunities from database
            logger.debug(f"🔍 Identifying keyword opportunities from database...")
            opportunities = await self.identify_keyword_opportunities(site_name)
            
            return opportunities
                
        except Exception as e:
            logger.error(f"❌ Failed to get keyword opportunities: {e}", exc_info=True)
            raise
    
    async def fetch_search_data_for_site(self, site_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch Search Console data from Google API using direct REST calls
        """
        try:
            logger.info(f"🌐 fetch_search_data_for_site() called: site={site_name}, days={days}")
            
            if not self._access_token:
                logger.debug(f"🔧 No access token loaded, initializing...")
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"❌ Unknown site: {site_name}")
                logger.debug(f"📋 Available sites: {list(SUPPORTED_SITES.keys())}")
                raise Exception(f"Unknown site: {site_name}")
            
            site_url = site_config['search_console_url']
            logger.debug(f"🔍 Using site URL: {site_url}")
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"📅 Fetching Search Console for {site_name}: {start_date} to {end_date}")
            
            # Build the API request
            api_url = f"{SEARCH_CONSOLE_API_BASE}/sites/{site_url}/searchAnalytics/query"
            
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }
            
            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "rowLimit": 25000,  # Maximum allowed
                "startRow": 0
            }
            
            logger.debug(f"🔍 Calling Search Console API: {api_url}")
            logger.debug(f"📦 Request body: {json.dumps(request_body, indent=2)}")
            
            # Make the API call using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=request_body) as response:
                    if response.status == 200:
                        data = await response.json()
                        rows = data.get('rows', [])
                        
                        logger.info(f"✅ Retrieved {len(rows)} queries from Search Console API")
                        
                        if not rows:
                            logger.warning(f"⚠️ No Search Console data returned for {site_name}")
                            return []
                        
                        # Log sample data
                        if len(rows) > 0:
                            sample = rows[0]
                            logger.debug(f"📊 Sample query: {sample.get('keys', [''])[0]} - "
                                       f"clicks={sample.get('clicks', 0)}, "
                                       f"impressions={sample.get('impressions', 0)}, "
                                       f"position={sample.get('position', 0)}")
                        
                        # Store data in database
                        await self._store_search_data(site_name, site_url, rows)
                        
                        logger.info(f"✅ Retrieved and stored {len(rows)} queries for {site_name}")
                        
                        return rows
                    
                    elif response.status == 401:
                        error_text = await response.text()
                        logger.error(f"❌ Authentication failed: {error_text}")
                        raise Exception("Authentication failed - token may be expired")
                    
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.error(f"❌ Permission denied: {error_text}")
                        raise Exception(f"Permission denied for site: {site_url}")
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ API error {response.status}: {error_text}")
                        raise Exception(f"Search Console API error: {response.status}")
                
        except Exception as e:
            logger.error(f"❌ Search Console fetch failed for {site_name}: {e}", exc_info=True)
            raise
    
    async def _store_search_data(self, site_name: str, site_url: str, rows: List[Dict]):
        """Store Search Console data in database"""
        try:
            logger.debug(f"💾 Storing {len(rows)} queries for {site_name}...")
            
            conn = await db_manager.get_connection()
            try:
                stored_count = 0
                for idx, row in enumerate(rows):
                    # Extract data from API response
                    keys = row.get('keys', [])
                    query = keys[0] if len(keys) > 0 else ''
                    
                    if not query:
                        continue
                    
                    clicks = row.get('clicks', 0)
                    impressions = row.get('impressions', 0)
                    ctr = row.get('ctr', 0.0)
                    position = row.get('position', 0.0)
                    
                    # Insert/update in database
                    await conn.execute('''
                        INSERT INTO google_search_console_data
                        (user_id, site_name, site_url, query, clicks, impressions, ctr, position, date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (user_id, site_name, query, date) DO UPDATE SET
                            clicks = EXCLUDED.clicks,
                            impressions = EXCLUDED.impressions,
                            ctr = EXCLUDED.ctr,
                            position = EXCLUDED.position,
                            updated_at = NOW()
                    ''',
                    self._user_id, site_name, site_url, query,
                    clicks, impressions, ctr, position,
                    datetime.now().date()
                    )
                    
                    stored_count += 1
                    
                    # Log progress every 100 queries
                    if stored_count % 100 == 0:
                        logger.debug(f"💾 Stored {stored_count}/{len(rows)} queries...")
                
                logger.info(f"✅ Stored {stored_count} queries for {site_name}")
                
            finally:
                await db_manager.release_connection(conn)
            
        except Exception as e:
            logger.error(f"❌ Failed to store Search Console data: {e}", exc_info=True)
            raise
    
    async def identify_keyword_opportunities(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Find keyword opportunities by querying database
        
        Looks for keywords with:
        - High impressions (100+)
        - Positions 11-30 (page 2-3)
        - Not already being tracked
        """
        try:
            logger.debug(f"🎯 identify_keyword_opportunities() called for {site_name}")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"❌ Unknown site: {site_name}")
                raise Exception(f"Unknown site: {site_name}")
            
            keyword_table = site_config['keyword_table']
            logger.debug(f"📊 Using keyword table: {keyword_table}")
            
            conn = await db_manager.get_connection()
            try:
                logger.debug(f"🔍 Querying database for opportunities...")
                
                # Find keywords NOT in the site's keyword table with good metrics
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
                    AND NOT EXISTS (
                        SELECT 1 FROM {keyword_table} kw
                        WHERE LOWER(kw.keyword) = LOWER(gsc.query)
                    )
                    ORDER BY gsc.impressions DESC, gsc.position ASC
                    LIMIT 50
                ''', self._user_id, site_name)
                
                logger.debug(f"📊 Found {len(opportunities)} opportunities")
                
                # Format results
                results = []
                for opp in opportunities:
                    opportunity_data = {
                        'keyword': opp['keyword'],
                        'site_name': site_name,
                        'clicks': opp['clicks'],
                        'impressions': opp['impressions'],
                        'ctr': round(opp['ctr'] * 100, 2),  # Convert to percentage
                        'position': round(opp['position'], 1),
                        'date': opp['date'].isoformat() if opp['date'] else None,
                        'opportunity_type': self._classify_opportunity(opp),
                        'potential_impact': self._estimate_impact(opp)
                    }
                    results.append(opportunity_data)
                
                logger.info(f"✅ Identified {len(results)} keyword opportunities for {site_name}")
                return results
                
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"❌ Failed to identify opportunities: {e}", exc_info=True)
            return []
    
    def _classify_opportunity(self, data: Dict[str, Any]) -> str:
        """Classify the type of keyword opportunity"""
        position = float(data['position'])
        impressions = data['impressions']
        
        if position <= 15 and impressions >= 500:
            opportunity_type = 'quick_win'
        elif position <= 20 and impressions >= 200:
            opportunity_type = 'content_boost'
        else:
            opportunity_type = 'long_term'
        
        logger.debug(f"🏷️ Classified '{data['keyword']}' as {opportunity_type}")
        return opportunity_type
    
    def _estimate_impact(self, data: Dict[str, Any]) -> str:
        """Estimate potential impact"""
        impressions = data['impressions']
        position = float(data['position'])
        
        if impressions >= 1000 and position <= 20:
            impact = 'high'
        elif impressions >= 500 and position <= 25:
            impact = 'medium'
        else:
            impact = 'low'
        
        logger.debug(f"📊 Estimated impact for '{data['keyword']}': {impact}")
        return impact


# Global instance
search_console_client = SearchConsoleClient()

# Convenience functions
async def find_keyword_opportunities(user_id: str, site_name: str):
    """Get keyword opportunities with auto-fetch if needed"""
    logger.debug(f"🔧 find_keyword_opportunities() called: user_id={user_id}, site={site_name}")
    await search_console_client.initialize(user_id)
    return await search_console_client.get_keyword_opportunities(site_name)

async def approve_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Approve and add keyword to site table"""
    logger.debug(f"🔧 approve_keyword() called: site={site_name}, keyword={keyword}")
    await search_console_client.initialize(user_id)
    # TODO: Implement keyword approval logic
    logger.info(f"✅ Keyword approval for '{keyword}' on {site_name} - not yet implemented")
    return True

async def reject_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Reject/ignore keyword opportunity"""
    logger.debug(f"🔧 reject_keyword() called: site={site_name}, keyword={keyword}")
    await search_console_client.initialize(user_id)
    # TODO: Implement keyword rejection logic
    logger.info(f"🚫 Keyword rejection for '{keyword}' on {site_name} - not yet implemented")
    return True
