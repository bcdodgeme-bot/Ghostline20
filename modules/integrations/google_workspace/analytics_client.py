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
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                raise Exception("No valid credentials available")
            
            logger.info("✅ Analytics initialized")
            
        except Exception as e:
            logger.error(f"❌ Analytics init failed: {e}")
            raise
    
    async def fetch_traffic_summary(self, site_name: str, days: int = 30) -> Dict[str, Any]:
        """
        Fetch traffic summary - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"📊 Fetching Analytics for {site_name}...")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                # Try GA4 first (analyticsdata v1beta)
                try:
                    analytics_v1 = await aiogoogle.discover('analyticsdata', 'v1beta')
                    
                    # GA4 uses property ID format
                    property_id = f"properties/{view_id}"
                    
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
                    
                    # Parse GA4 response
                    rows = response.get('rows', [])
                    
                    total_users = 0
                    total_pageviews = 0
                    total_sessions = 0
                    
                    for row in rows:
                        metric_values = row.get('metricValues', [])
                        if len(metric_values) >= 3:
                            total_users += int(metric_values[0].get('value', 0))
                            total_pageviews += int(metric_values[1].get('value', 0))
                            total_sessions += int(metric_values[2].get('value', 0))
                    
                    summary = {
                        'site_name': site_name,
                        'period_days': days,
                        'total_users': total_users,
                        'total_pageviews': total_pageviews,
                        'total_sessions': total_sessions,
                        'avg_daily_users': total_users // days if days > 0 else 0,
                        'api_version': 'GA4'
                    }
                    
                except Exception as ga4_error:
                    logger.warning(f"GA4 failed, trying Universal Analytics: {ga4_error}")
                    
                    # Fallback to Universal Analytics (v3)
                    analytics_v3 = await aiogoogle.discover('analytics', 'v3')
                    
                    response = await aiogoogle.as_user(
                        analytics_v3.data.ga.get(
                            ids=f'ga:{view_id}',
                            start_date=start_date.isoformat(),
                            end_date=end_date.isoformat(),
                            metrics='ga:users,ga:pageviews,ga:sessions'
                        )
                    )
                    
                    # Parse Universal Analytics response
                    rows = response.get('rows', [])
                    
                    if rows and len(rows[0]) >= 3:
                        summary = {
                            'site_name': site_name,
                            'period_days': days,
                            'total_users': int(rows[0][0]),
                            'total_pageviews': int(rows[0][1]),
                            'total_sessions': int(rows[0][2]),
                            'avg_daily_users': int(rows[0][0]) // days if days > 0 else 0,
                            'api_version': 'UA'
                        }
                    else:
                        # No data available
                        summary = {
                            'site_name': site_name,
                            'period_days': days,
                            'total_users': 0,
                            'total_pageviews': 0,
                            'total_sessions': 0,
                            'avg_daily_users': 0,
                            'api_version': 'UA',
                            'note': 'No data available'
                        }
            
            logger.info(f"✅ Analytics fetched: {summary['total_users']} users")
            
            # Store in database
            await self._store_analytics_data(site_name, summary)
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Analytics fetch failed for {site_name}: {e}")
            # Don't swallow - let it bubble for debugging
            raise
    
    async def _store_analytics_data(self, site_name: str, summary: Dict[str, Any]):
        """Store analytics data in database"""
        try:
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
            
            logger.info(f"✅ Stored Analytics data for {site_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store Analytics: {e}")

# Global instance
analytics_client = AnalyticsClient()

# Convenience function
async def fetch_analytics_summary(user_id: str, site_name: str, days: int = 30):
    await analytics_client.initialize(user_id)
    return await analytics_client.fetch_traffic_summary(site_name, days)
