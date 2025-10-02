# modules/integrations/google_workspace/analytics_client.py
"""
Google Analytics Client - REFACTORED FOR AIOGOOGLE
True async API calls for traffic analysis
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from aiogoogle import Aiogoogle
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    logger.warning("⚠️ aiogoogle not installed")

from . import SUPPORTED_SITES
from .oauth_manager import get_aiogoogle_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class AnalyticsClient:
    """Analytics client with TRUE async support"""
    
    def __init__(self):
        if not ANALYTICS_AVAILABLE:
            raise RuntimeError("aiogoogle required")
        
        self._user_id = None
        self._user_creds = None
        logger.info("📊 Analytics client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str):
        """Initialize with credentials"""
        try:
            logger.debug(f"🔧 Analytics.initialize() called with user_id={user_id}")
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                logger.error(f"❌ No credentials found for user_id={user_id}")
                raise Exception("No valid credentials available")
            
            logger.info(f"✅ Analytics initialized for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Analytics init failed: {e}", exc_info=True)
            raise
    
    async def get_analytics_summary(self, site_name: str, days: int = 30) -> Dict[str, Any]:
        """
        Get analytics summary - WITH AUTO-FETCH
        
        This method:
        1. Checks database for recent data
        2. If database is empty or stale, fetches from API first
        3. Returns summary from database
        """
        try:
            logger.info(f"📊 Getting analytics summary: site={site_name}, days={days}")
            
            # Check if we have recent data in database
            cutoff_date = datetime.now().date() - timedelta(days=days)
            
            async with db_manager.get_connection() as conn:
                latest_data = await conn.fetchrow('''
                    SELECT date, visitors, pageviews, sessions, updated_at
                    FROM google_analytics_data
                    WHERE user_id = $1 AND site_name = $2
                    ORDER BY date DESC
                    LIMIT 1
                ''', self._user_id, site_name)
                
                # Determine if we need fresh data
                needs_fetch = False
                
                if not latest_data:
                    logger.info(f"📊 No analytics data in DB for {site_name}")
                    needs_fetch = True
                else:
                    days_old = (datetime.now().date() - latest_data['date']).days
                    logger.debug(f"📊 Latest data is {days_old} days old (date: {latest_data['date']})")
                    
                    # Fetch if data is more than 1 day old
                    if days_old > 1:
                        logger.info(f"🔄 Data is stale ({days_old} days old), fetching fresh data...")
                        needs_fetch = True
                
                # Fetch from API if needed
                if needs_fetch:
                    try:
                        logger.info(f"🌐 Fetching fresh analytics data from Google API...")
                        await self.fetch_traffic_summary(site_name, days)
                        logger.info(f"✅ Fresh data fetched and stored")
                    except Exception as fetch_error:
                        logger.error(f"⚠️ Failed to fetch from API: {fetch_error}", exc_info=True)
                        # Continue anyway - maybe we can still provide partial data
                
                # Now get summary from database
                logger.debug(f"🔍 Querying database for analytics summary...")
                
                summary_data = await conn.fetchrow('''
                    SELECT 
                        SUM(visitors) as total_visitors,
                        SUM(pageviews) as total_pageviews,
                        SUM(sessions) as total_sessions,
                        AVG(avg_session_duration) as avg_duration,
                        COUNT(*) as days_of_data
                    FROM google_analytics_data
                    WHERE user_id = $1 
                    AND site_name = $2
                    AND date >= $3
                ''', self._user_id, site_name, cutoff_date)
                
                # Get top pages if available
                top_pages = await conn.fetch('''
                    SELECT page_path, pageviews
                    FROM google_analytics_pages
                    WHERE user_id = $1 AND site_name = $2
                    ORDER BY pageviews DESC
                    LIMIT 5
                ''', self._user_id, site_name)
                
                # Get traffic sources if available
                traffic_sources = await conn.fetch('''
                    SELECT source, sessions
                    FROM google_analytics_sources
                    WHERE user_id = $1 AND site_name = $2
                    ORDER BY sessions DESC
                    LIMIT 5
                ''', self._user_id, site_name)
                
                if not summary_data or summary_data['total_visitors'] is None:
                    logger.warning(f"⚠️ No analytics data available for {site_name}")
                    return {
                        'site_name': site_name,
                        'period_days': days,
                        'total_visitors': 0,
                        'total_pageviews': 0,
                        'total_sessions': 0,
                        'avg_session_duration': 0,
                        'bounce_rate': 0.0,
                        'top_pages': [],
                        'traffic_sources': {},
                        'note': 'No data available'
                    }
                
                summary = {
                    'site_name': site_name,
                    'period_days': days,
                    'total_visitors': int(summary_data['total_visitors'] or 0),
                    'total_pageviews': int(summary_data['total_pageviews'] or 0),
                    'total_sessions': int(summary_data['total_sessions'] or 0),
                    'avg_session_duration': float(summary_data['avg_duration'] or 0),
                    'bounce_rate': 0.0,  # Calculate this properly if available
                    'top_pages': [f"{row['page_path']}" for row in top_pages],
                    'traffic_sources': {row['source']: int(row['sessions']) for row in traffic_sources}
                }
                
                logger.info(f"✅ Analytics summary: {summary['total_visitors']} visitors, {summary['total_pageviews']} pageviews")
                return summary
                
        except Exception as e:
            logger.error(f"❌ Failed to get analytics summary: {e}", exc_info=True)
            raise
    
    async def fetch_traffic_summary(self, site_name: str, days: int = 30) -> Dict[str, Any]:
        """
        Fetch traffic summary from Google Analytics API - TRULY ASYNC
        """
        try:
            logger.info(f"🌐 fetch_traffic_summary() called: site={site_name}, days={days}")
            
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing...")
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"❌ Unknown site: {site_name}")
                logger.debug(f"📋 Available sites: {list(SUPPORTED_SITES.keys())}")
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            logger.debug(f"📊 Using Analytics view_id: {view_id}")
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"📅 Fetching Analytics for {site_name}: {start_date} to {end_date}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                # Try GA4 first (analyticsdata v1beta)
                try:
                    logger.debug(f"🔍 Attempting GA4 API call...")
                    analytics_v1 = await aiogoogle.discover('analyticsdata', 'v1beta')
                    
                    # GA4 uses property ID format
                    property_id = f"properties/{view_id}"
                    logger.debug(f"📊 GA4 property_id: {property_id}")
                    
                    response = await aiogoogle.as_user(
                        analytics_v1.properties.runReport(
                            property=property_id,
                            json={
                                'dateRanges': [{
                                    'startDate': start_date.isoformat(),
                                    'endDate': end_date.isoformat()
                                }],
                                'metrics': [
                                    {'name': 'activeUsers'},
                                    {'name': 'screenPageViews'},
                                    {'name': 'sessions'}
                                ],
                                'dimensions': [{'name': 'date'}]
                            }
                        )
                    )
                    
                    logger.debug(f"📦 GA4 API response received")
                    
                    # Parse GA4 response
                    rows = response.get('rows', [])
                    logger.debug(f"📊 GA4 returned {len(rows)} rows")
                    
                    total_users = 0
                    total_pageviews = 0
                    total_sessions = 0
                    
                    for idx, row in enumerate(rows):
                        metric_values = row.get('metricValues', [])
                        if len(metric_values) >= 3:
                            users = int(metric_values[0].get('value', 0))
                            pageviews = int(metric_values[1].get('value', 0))
                            sessions = int(metric_values[2].get('value', 0))
                            
                            total_users += users
                            total_pageviews += pageviews
                            total_sessions += sessions
                            
                            if idx < 3:  # Log first 3 rows for debugging
                                logger.debug(f"  Row {idx}: users={users}, pageviews={pageviews}, sessions={sessions}")
                    
                    summary = {
                        'site_name': site_name,
                        'period_days': days,
                        'total_users': total_users,
                        'total_pageviews': total_pageviews,
                        'total_sessions': total_sessions,
                        'avg_daily_users': total_users // days if days > 0 else 0,
                        'api_version': 'GA4'
                    }
                    
                    logger.info(f"✅ GA4 data fetched: {total_users} users, {total_pageviews} pageviews")
                    
                except Exception as ga4_error:
                    logger.warning(f"⚠️ GA4 failed: {ga4_error}")
                    logger.debug(f"🔄 Falling back to Universal Analytics...")
                    
                    # Fallback to Universal Analytics (v3)
                    try:
                        analytics_v3 = await aiogoogle.discover('analytics', 'v3')
                        logger.debug(f"🔍 Attempting Universal Analytics API call...")
                        
                        response = await aiogoogle.as_user(
                            analytics_v3.data.ga.get(
                                ids=f'ga:{view_id}',
                                start_date=start_date.isoformat(),
                                end_date=end_date.isoformat(),
                                metrics='ga:users,ga:pageviews,ga:sessions'
                            )
                        )
                        
                        logger.debug(f"📦 Universal Analytics API response received")
                        
                        # Parse Universal Analytics response
                        rows = response.get('rows', [])
                        logger.debug(f"📊 Universal Analytics returned {len(rows)} rows")
                        
                        if rows and len(rows[0]) >= 3:
                            total_users = int(rows[0][0])
                            total_pageviews = int(rows[0][1])
                            total_sessions = int(rows[0][2])
                            
                            logger.debug(f"📊 UA data: users={total_users}, pageviews={total_pageviews}, sessions={total_sessions}")
                            
                            summary = {
                                'site_name': site_name,
                                'period_days': days,
                                'total_users': total_users,
                                'total_pageviews': total_pageviews,
                                'total_sessions': total_sessions,
                                'avg_daily_users': total_users // days if days > 0 else 0,
                                'api_version': 'UA'
                            }
                            
                            logger.info(f"✅ Universal Analytics data fetched: {total_users} users")
                        else:
                            logger.warning(f"⚠️ Universal Analytics returned no data")
                            # No data available
                            summary = {
                                'site_name': site_name,
                                'period_days': days,
                                'total_users': 0,
                                'total_pageviews': 0,
                                'total_sessions': 0,
                                'avg_daily_users': 0,
                                'api_version': 'UA',
                                'note': 'No data available from API'
                            }
                    
                    except Exception as ua_error:
                        logger.error(f"❌ Universal Analytics also failed: {ua_error}", exc_info=True)
                        raise
            
            logger.info(f"✅ Analytics fetched: {summary['total_users']} users")
            
            # Store in database
            await self._store_analytics_data(site_name, summary)
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Analytics fetch failed for {site_name}: {e}", exc_info=True)
            raise
    
    async def _store_analytics_data(self, site_name: str, summary: Dict[str, Any]):
        """Store analytics data in database"""
        try:
            logger.debug(f"💾 Storing analytics data for {site_name}...")
            
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO google_analytics_data
                    (user_id, site_name, date, visitors, pageviews, sessions, avg_session_duration)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, site_name, date) DO UPDATE SET
                        visitors = EXCLUDED.visitors,
                        pageviews = EXCLUDED.pageviews,
                        sessions = EXCLUDED.sessions,
                        updated_at = NOW()
                ''',
                self._user_id,
                site_name,
                datetime.now().date(),
                summary['total_users'],
                summary['total_pageviews'],
                summary['total_sessions'],
                0  # avg_session_duration not in basic query
                )
            
            logger.info(f"✅ Stored Analytics data for {site_name}: {summary['total_users']} visitors")
            
        except Exception as e:
            logger.error(f"❌ Failed to store Analytics: {e}", exc_info=True)
            # Don't raise - storing is optional

# Global instance
analytics_client = AnalyticsClient()

# Convenience function
async def fetch_analytics_summary(user_id: str, site_name: str, days: int = 30):
    """Get analytics summary with auto-fetch if needed"""
    logger.debug(f"🔧 fetch_analytics_summary() called: user_id={user_id}, site={site_name}, days={days}")
    await analytics_client.initialize(user_id)
    return await analytics_client.get_analytics_summary(site_name, days)

async def get_optimal_timing(user_id: str, site_name: str) -> Dict[str, Any]:
    """Get optimal posting timing - placeholder"""
    logger.debug(f"🔧 get_optimal_timing() called: user_id={user_id}, site={site_name}")
    await analytics_client.initialize(user_id)
    logger.info(f"📊 Optimal timing for {site_name} - not yet implemented")
    return {
        'site_name': site_name,
        'recommendation': 'Optimal timing analysis not yet implemented',
        'best_day': 'Monday',
        'best_hour': 10
    }
