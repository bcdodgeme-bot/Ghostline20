# modules/integrations/google_workspace/search_console_client.py
"""
Search Console Client - Direct REST API Implementation
Real Search Console data fetching using aiohttp with proper async authentication
COMPLETELY ABANDONED aiogoogle library - using direct REST API calls like Analytics
"""

import json
import logging
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import quote

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
            logger.info("=" * 70)
            logger.info("SEARCH CONSOLE INIT DEBUG START")
            logger.info(f"User ID: {user_id}")
        
            self._user_id = user_id
            
            # Load access token directly from database (same as Analytics)
            query = '''
                SELECT access_token_encrypted, token_expires_at, email_address
                FROM google_oauth_accounts
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY CASE WHEN email_address LIKE '%@bcdodge.me' THEN 0 ELSE 1 END
                LIMIT 1
            '''
            
            logger.info("Querying database for OAuth tokens...")
            conn = await db_manager.get_connection()
            try:
                row = await conn.fetchrow(query, user_id)
                
                if not row:
                    logger.error(f"NO CREDENTIALS FOUND IN DATABASE for user {user_id}")
                    raise Exception("No credentials found")
                
                logger.info(f"Found credentials for: {row['email_address']}")
                logger.info(f"Token expires: {row['token_expires_at']}")
                
                from ...core.crypto import decrypt_token
                logger.info("Decrypting token...")
                self._access_token = decrypt_token(row['access_token_encrypted'])
                logger.info(f"Token decrypted - length: {len(self._access_token)}")
                
                # Check if token is expired
                if row['token_expires_at']:
                    if datetime.now(timezone.utc) >= row['token_expires_at']:
                        logger.error("TOKEN IS EXPIRED")
                        raise Exception("Token expired - please re-authenticate")
                    else:
                        logger.info("Token is valid (not expired)")
            finally:
                await db_manager.release_connection(conn)
                
            logger.info("Search Console initialized successfully")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error("=" * 70)
            logger.error("SEARCH CONSOLE INIT FAILED")
            logger.error(f"Error: {e}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error("=" * 70)
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
                    logger.info(f"🔍 Latest Search Console data is {days_old} days old")
                    
                    # Fetch if data is more than 2 days old
                    if days_old > 2:
                        logger.info(f"🔄 Search Console data is stale ({days_old} days old), fetching fresh data...")
                        needs_fetch = True
                
                # Fetch from API if needed
                if needs_fetch:
                    try:
                        logger.info("🌐 Fetching fresh Search Console data from Google API...")
                        await self.fetch_search_data_for_site(site_name, days=30)
                        logger.info("✅ Fresh Search Console data fetched and stored")
                    except Exception as fetch_error:
                        logger.error(f"⚠️ Failed to fetch from API: {fetch_error}", exc_info=True)
                        # Continue anyway - maybe we can still provide partial data
                
            finally:
                await db_manager.release_connection(conn)
            
            # Now identify opportunities from database
            logger.info("🔍 Identifying keyword opportunities from database...")
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
            logger.info("=" * 70)
            logger.info("FETCH SEARCH DATA DEBUG START")
            logger.info(f"Site: {site_name}, Days: {days}")
            
            if not self._access_token:
                logger.error("No access token - calling initialize")
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"Unknown site: {site_name}")
                logger.error(f"Available: {list(SUPPORTED_SITES.keys())}")
                raise Exception(f"Unknown site: {site_name}")
            
            site_url = site_config['search_console_url']
            logger.info(f"Site URL: {site_url}")
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            logger.info(f"Date range: {start_date} to {end_date}")
            
            # Build the API request
            encoded_site_url = quote(site_url, safe='')
            api_url = f"{SEARCH_CONSOLE_API_BASE}/sites/{encoded_site_url}/searchAnalytics/query"
            logger.info(f"API URL: {api_url}")
            
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json"
            }
            
            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "rowLimit": 25000,
                "startRow": 0
            }
            
            logger.info("Making API request...")
            
            # Make the API call using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=request_body, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    logger.info(f"API Response Status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        rows = data.get('rows', [])
                        
                        logger.info(f"SUCCESS - Retrieved {len(rows)} queries")
                        
                        if not rows:
                            logger.warning("No data returned (empty result)")
                            logger.info("=" * 70)
                            return []
                        
                        # Log sample
                        if len(rows) > 0:
                            sample = rows[0]
                            logger.info(f"Sample: {sample.get('keys', [''])[0]} - clicks={sample.get('clicks', 0)}, impressions={sample.get('impressions', 0)}")
                        
                        # Store data in database
                        await self._store_search_data(site_name, site_url, rows)
                        
                        logger.info("=" * 70)
                        return rows
                    
                    elif response.status == 401:
                        error_text = await response.text()
                        logger.error("API ERROR 401 - Authentication failed")
                        logger.error(f"Response: {error_text[:500]}")
                        logger.error("=" * 70)
                        raise Exception("Authentication failed - token may be expired")
                    
                    elif response.status == 403:
                        error_text = await response.text()
                        logger.error("API ERROR 403 - Permission denied")
                        logger.error(f"Response: {error_text[:500]}")
                        logger.error("=" * 70)
                        raise Exception(f"Permission denied for site: {site_url}")
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"API ERROR {response.status}")
                        logger.error(f"Response: {error_text[:500]}")
                        logger.error("=" * 70)
                        raise Exception(f"Search Console API error {response.status}: {error_text[:200]}")
            
        except Exception as e:
            logger.error("=" * 70)
            logger.error("FETCH FAILED")
            logger.error(f"Error: {e}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error("=" * 70)
            raise
    
    async def _store_search_data(self, site_name: str, site_url: str, rows: List[Dict]):
        """Store Search Console data in database"""
        try:
            logger.info(f"💾 Storing {len(rows)} queries for {site_name}...")
            
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
                        (user_id, site_name, site_url, query, page, country, device, clicks, impressions, ctr, position, date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (user_id, site_name, query, page, country, device, date) DO UPDATE SET
                            clicks = EXCLUDED.clicks,
                            impressions = EXCLUDED.impressions,
                            ctr = EXCLUDED.ctr,
                            position = EXCLUDED.position,
                            updated_at = NOW()
                    ''',
                    self._user_id, site_name, site_url, query,
                    None, None, None,
                    clicks, impressions, ctr, position,
                    datetime.now().date()
                    )
                    
                    stored_count += 1
                    
                    # Log progress every 100 queries
                    if stored_count % 100 == 0:
                        logger.info(f"💾 Stored {stored_count}/{len(rows)} queries...")
                
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
            logger.info(f"🎯 identify_keyword_opportunities() called for {site_name}")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"❌ Unknown site: {site_name}")
                raise Exception(f"Unknown site: {site_name}")
            
            keyword_table = site_config['keyword_table']
            logger.info(f"📊 Using keyword table: {keyword_table}")
            
            conn = await db_manager.get_connection()
            try:
                logger.info("🔍 Querying database for opportunities...")
                
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
                
                logger.info(f"📊 Found {len(opportunities)} opportunities")
                
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
        
        return impact


# Global instance
search_console_client = SearchConsoleClient()

# Convenience functions
async def find_keyword_opportunities(user_id: str, site_name: str):
    """Get keyword opportunities with auto-fetch if needed"""
    logger.info(f"🔧 find_keyword_opportunities() called: user_id={user_id}, site={site_name}")
    await search_console_client.initialize(user_id)
    return await search_console_client.get_keyword_opportunities(site_name)

async def approve_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Approve and add keyword to site table"""
    logger.info(f"🔧 approve_keyword() called: site={site_name}, keyword={keyword}")
    await search_console_client.initialize(user_id)
    # TODO: Implement keyword approval logic
    logger.info(f"✅ Keyword approval for '{keyword}' on {site_name} - not yet implemented")
    return True

async def reject_keyword(user_id: str, site_name: str, keyword: str) -> bool:
    """Reject/ignore keyword opportunity"""
    logger.info(f"🔧 reject_keyword() called: site={site_name}, keyword={keyword}")
    await search_console_client.initialize(user_id)
    # TODO: Implement keyword rejection logic
    logger.info(f"🚫 Keyword rejection for '{keyword}' on {site_name} - not yet implemented")
    return True
