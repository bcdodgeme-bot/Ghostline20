# modules/integrations/google_workspace/search_console_client.py
"""
Search Console Client - REFACTORED FOR AIOGOOGLE
Keyword opportunity detection with true async
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from aiogoogle import Aiogoogle
    SEARCH_CONSOLE_AVAILABLE = True
except ImportError:
    SEARCH_CONSOLE_AVAILABLE = False
    logger.warning("⚠️ aiogoogle not installed")

from . import SUPPORTED_SITES
from .oauth_manager import get_aiogoogle_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class SearchConsoleClient:
    """Search Console with TRUE async"""
    
    def __init__(self):
        if not SEARCH_CONSOLE_AVAILABLE:
            raise RuntimeError("aiogoogle required")
        
        self._user_id = None
        self._user_creds = None
        logger.info("🔍 Search Console initialized (aiogoogle)")
    
    async def initialize(self, user_id: str):
        try:
            logger.debug(f"🔧 SearchConsole.initialize() called with user_id={user_id}")
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                logger.error(f"❌ No credentials found for user_id={user_id}")
                raise Exception("No valid credentials")
            
            logger.info(f"✅ Search Console initialized for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Search Console init failed: {e}", exc_info=True)
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
            
            # Check if we have recent data in database
            async with db_manager.get_connection() as conn:
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
                
                # Now identify opportunities from database
                logger.debug(f"🔍 Identifying keyword opportunities from database...")
                opportunities = await self.identify_keyword_opportunities(site_name)
                
                return opportunities
                
        except Exception as e:
            logger.error(f"❌ Failed to get keyword opportunities: {e}", exc_info=True)
            raise
    
    async def fetch_search_data_for_site(self, site_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch Search Console data from Google API - TRULY ASYNC
        """
        try:
            logger.info(f"🌐 fetch_search_data_for_site() called: site={site_name}, days={days}")
            
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing...")
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
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                search_console = await aiogoogle.discover('searchconsole', 'v1')
                
                logger.debug(f"🔍 Calling Search Console API: searchanalytics.query")
                
                # THIS IS TRULY ASYNC
                response = await aiogoogle.as_user(
                    search_console.searchanalytics.query(
                        siteUrl=site_url,
                        json={
                            'startDate': start_date.isoformat(),
                            'endDate': end_date.isoformat(),
                            'dimensions': ['query', 'page', 'country', 'device'],
                            'rowLimit': 1000
                        }
                    )
                )
                
                logger.debug(f"📦 Search Console API response received")
                
                rows = response.get('rows', [])
                logger.info(f"🔍 Retrieved {len(rows)} queries from Search Console API")
                
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
                
        except Exception as e:
            logger.error(f"❌ Search Console fetch failed for {site_name}: {e}", exc_info=True)
            raise
    
    async def _store_search_data(self, site_name: str, site_url: str, rows: List[Dict]):
        """Store Search Console data in database"""
        try:
            logger.debug(f"💾 Storing {len(rows)} queries for {site_name}...")
            
            async with db_manager.get_connection() as conn:
                stored_count = 0
                for idx, row in enumerate(rows):
                    query = row.get('keys', [''])[0]
                    page = row.get('keys', [''])[1] if len(row.get('keys', [])) > 1 else ''
                    country = row.get('keys', [''])[2] if len(row.get('keys', [])) > 2 else ''
                    device = row.get('keys', [''])[3] if len(row.get('keys', [])) > 3 else ''
                    clicks = row.get('clicks', 0)
                    impressions = row.get('impressions', 0)
                    ctr = row.get('ctr', 0.0)
                    position = row.get('position', 0.0)
                    
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
                    self._user_id, site_name, site_url, query, page, country, device,
                    clicks, impressions, ctr, position,
                    datetime.now().date()
                    )
                    
                    stored_count += 1
                    
                    # Log progress every 100 queries
                    if stored_count % 100 == 0:
                        logger.debug(f"💾 Stored {stored_count}/{len(rows)} queries...")
            
            logger.info(f"✅ Stored {stored_count} queries for {site_name}")
            
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
            
            async with db_manager.get_connection() as conn:
                logger.debug(f"🔍 Querying database for opportunities...")
                
                opportunities = await conn.fetch(f'''
                    SELECT 
                        gsc.query as keyword,
                        gsc.page,
                        gsc.country,
                        gsc.device,
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
                
                logger.debug(f"📊 Found {len(opportunities)} raw opportunities")
                
                opportunity_list = []
                for idx, opp in enumerate(opportunities):
                    opp_dict = dict(opp)
                    opp_type = self._classify_opportunity(opp_dict)
                    opp_impact = self._estimate_impact(opp_dict)
                    
                    opportunity_data = {
                        'keyword': opp['keyword'],
                        'page': opp.get('page', ''),
                        'country': opp.get('country', ''),
                        'device': opp.get('device', ''),
                        'clicks': opp['clicks'],
                        'impressions': opp['impressions'],
                        'ctr': float(opp['ctr']),
                        'position': float(opp['position']),
                        'date': opp['date'],
                        'site_name': site_name,
                        'opportunity_type': opp_type,
                        'potential_impact': opp_impact
                    }
                    
                    opportunity_list.append(opportunity_data)
                    
                    # Log first few opportunities
                    if idx < 3:
                        logger.debug(f"  🎯 Opportunity {idx+1}: {opp['keyword']} - "
                                   f"pos={opp['position']:.1f}, "
                                   f"impr={opp['impressions']}, "
                                   f"type={opp_type}, "
                                   f"impact={opp_impact}")
                
                logger.info(f"🎯 Found {len(opportunity_list)} keyword opportunities for {site_name}")
                return opportunity_list
                
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

# Convenience function
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
