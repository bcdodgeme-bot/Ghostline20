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
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                raise Exception("No valid credentials")
            
            logger.info("✅ Search Console initialized")
            
        except Exception as e:
            logger.error(f"❌ Search Console init failed: {e}")
            raise
    
    async def fetch_search_data_for_site(self, site_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch Search Console data - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            site_url = site_config['url']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"🔍 Fetching Search Console for {site_name}...")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                search_console = await aiogoogle.discover('searchconsole', 'v1')
                
                # THIS IS TRULY ASYNC
                response = await aiogoogle.as_user(
                    search_console.searchanalytics.query(
                        siteUrl=site_url,
                        json={
                            'startDate': start_date.isoformat(),
                            'endDate': end_date.isoformat(),
                            'dimensions': ['query'],
                            'rowLimit': 1000
                        }
                    )
                )
                
                rows = response.get('rows', [])
                
                if not rows:
                    logger.info(f"ℹ️ No Search Console data for {site_name}")
                    return []
                
                # Store data in database
                await self._store_search_data(site_name, site_url, rows)
                
                logger.info(f"✅ Retrieved {len(rows)} queries for {site_name}")
                
                return rows
                
        except Exception as e:
            logger.error(f"❌ Search Console fetch failed: {e}")
            raise
    
    async def _store_search_data(self, site_name: str, site_url: str, rows: List[Dict]):
        """Store in database"""
        try:
            async with db_manager.get_connection() as conn:
                for row in rows:
                    query = row.get('keys', [''])[0]
                    clicks = row.get('clicks', 0)
                    impressions = row.get('impressions', 0)
                    ctr = row.get('ctr', 0.0)
                    position = row.get('position', 0.0)
                    
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
                    self._user_id, site_name, site_url, query,
                    clicks, impressions, ctr, position,
                    datetime.now().date()
                    )
            
            logger.info(f"✅ Stored {len(rows)} queries for {site_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store Search Console data: {e}")
            raise
    
    async def identify_keyword_opportunities(self, site_name: str) -> List[Dict[str, Any]]:
        """
        Find keyword opportunities (this queries DB, not API)
        """
        try:
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            keyword_table = site_config['keyword_table']
            
            async with db_manager.get_connection() as conn:
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
                        'opportunity_type': self._classify_opportunity(dict(opp)),
                        'potential_impact': self._estimate_impact(dict(opp))
                    })
                
                logger.info(f"🎯 Found {len(opportunity_list)} opportunities for {site_name}")
                return opportunity_list
                
        except Exception as e:
            logger.error(f"❌ Failed to identify opportunities: {e}")
            return []
    
    def _classify_opportunity(self, data: Dict[str, Any]) -> str:
        """Classify the type of keyword opportunity"""
        position = float(data['position'])
        impressions = data['impressions']
        
        if position <= 15 and impressions >= 500:
            return 'quick_win'
        elif position <= 20 and impressions >= 200:
            return 'content_boost'
        else:
            return 'long_term'
    
    def _estimate_impact(self, data: Dict[str, Any]) -> str:
        """Estimate potential impact"""
        impressions = data['impressions']
        position = float(data['position'])
        
        if impressions >= 1000 and position <= 20:
            return 'high'
        elif impressions >= 500 and position <= 25:
            return 'medium'
        else:
            return 'low'

# Global instance
search_console_client = SearchConsoleClient()

# Convenience function
async def find_keyword_opportunities(user_id: str, site_name: str):
    await search_console_client.initialize(user_id)
    return await search_console_client.identify_keyword_opportunities(site_name)
