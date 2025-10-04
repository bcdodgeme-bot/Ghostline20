# modules/integrations/google_workspace/analytics_client.py
"""
Google Analytics Client - Using Official Google Analytics Data API
Real GA4 data fetching with proper authentication
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from . import SUPPORTED_SITES
from ...core.database import db_manager
from .oauth_manager import get_google_credentials, google_auth_manager
logger = logging.getLogger(__name__)

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest,
        DateRange,
        Dimension,
        Metric
    )
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    logger.warning("google-analytics-data not installed - run: pip install google-analytics-data")


class AnalyticsClient:
    """Google Analytics GA4 client with JSONB storage"""
    
    def __init__(self, user_id: str = None):
        if not ANALYTICS_AVAILABLE:
            raise RuntimeError("google-analytics-data required - run: pip install google-analytics-data")
    
        self._user_id = user_id
        self._credentials = None
    
    async def initialize(self, user_id: str):
        """Initialize with Google credentials"""
        try:
            self._user_id = user_id
        
            # Load credentials DIRECTLY for Analytics, bypassing all shared code
            from .oauth_manager import google_auth_manager
            
            query = '''
                SELECT access_token_encrypted, refresh_token_encrypted, token_expires_at
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
                from google.oauth2.credentials import Credentials
                from datetime import timezone
                
                access_token = decrypt_token(row['access_token_encrypted'])
                refresh_token = decrypt_token(row['refresh_token_encrypted'])
                
                # Force timezone-aware expiry for Analytics
                expiry = row['token_expires_at']
                if expiry and not expiry.tzinfo:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                
                self._credentials = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri=google_auth_manager.token_url,
                    client_id=google_auth_manager.client_id,
                    client_secret=google_auth_manager.client_secret,
                    scopes=google_auth_manager.oauth_scopes,
                    expiry=expiry
                )
            finally:
                await db_manager.release_connection(conn)
                
            logger.info(f"Analytics initialized for user {user_id}")
            
        except Exception as e:
            logger.error(f"Analytics initialization failed: {e}", exc_info=True)
            raise
    
    async def _store_analytics_data(self, site_name: str, summary: dict[str, Any]):
        """
        Store analytics data in the existing JSONB table structure
        
        Table columns:
        - user_id, site_name, property_id, view_id
        - date_range_start, date_range_end
        - metrics (JSONB)
        - dimensions (JSONB)
        - audience_insights (JSONB)
        - content_performance (JSONB)
        - traffic_patterns (JSONB)
        - created_at, sync_version
        """
        try:
            logger.debug(f"Storing analytics data for {site_name}...")
            
            # Get site config for property/view IDs
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                logger.error(f"Site {site_name} not found in config")
                return
            
            view_id = site_config['analytics_view_id']
            
            # Extract date range from summary
            start_date = summary.get('date_range', {}).get('start')
            end_date = summary.get('date_range', {}).get('end')
            
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date).date()
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date).date()
            
            # Build JSONB structures from comprehensive summary
            
            # METRICS - Core traffic numbers
            metrics = {
                'total_users': summary.get('overview', {}).get('total_users', 0),
                'new_users': summary.get('overview', {}).get('new_users', 0),
                'returning_users': summary.get('overview', {}).get('returning_users', 0),
                'sessions': summary.get('overview', {}).get('sessions', 0),
                'pageviews': summary.get('overview', {}).get('pageviews', 0),
                'avg_session_duration': summary.get('overview', {}).get('avg_session_duration', 0),
                'bounce_rate': summary.get('overview', {}).get('bounce_rate', 0),
                'engagement_rate': summary.get('overview', {}).get('engagement_rate', 0),
                'avg_sessions_per_user': summary.get('overview', {}).get('avg_sessions_per_user', 0),
                'avg_pages_per_session': summary.get('overview', {}).get('avg_pages_per_session', 0),
                'total_engagement_time': summary.get('overview', {}).get('total_engagement_time', 0)
            }
            
            # DIMENSIONS - Device breakdown, browser, OS
            dimensions = {
                'devices': summary.get('devices', []),
                'geography': summary.get('geography', []),
                'demographics': summary.get('demographics', []) if summary.get('demographics') else None
            }
            
            # AUDIENCE_INSIGHTS - Landing pages and user behavior
            audience_insights = {
                'landing_pages': summary.get('landing_pages', []),
                'new_vs_returning': {
                    'new_users': summary.get('overview', {}).get('new_users', 0),
                    'returning_users': summary.get('overview', {}).get('returning_users', 0),
                    'new_user_percentage': (
                        (summary.get('overview', {}).get('new_users', 0) /
                         summary.get('overview', {}).get('total_users', 1) * 100)
                        if summary.get('overview', {}).get('total_users', 0) > 0 else 0
                    )
                }
            }
            
            # CONTENT_PERFORMANCE - Top pages and events
            content_performance = {
                'top_pages': summary.get('pages', []),
                'events': summary.get('events', [])
            }
            
            # TRAFFIC_PATTERNS - Sources, mediums, campaigns
            traffic_patterns = {
                'sources': summary.get('sources', []),
                'api_version': summary.get('api_version', 'GA4'),
                'fetched_at': summary.get('fetched_at', datetime.now().isoformat())
            }
            
            conn = await db_manager.get_connection()
            try:
                await conn.execute('''
                    INSERT INTO google_analytics_data
                    (
                        user_id, 
                        site_name, 
                        property_id,
                        view_id,
                        date_range_start, 
                        date_range_end,
                        metrics,
                        dimensions,
                        audience_insights,
                        content_performance,
                        traffic_patterns,
                        sync_version
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, 1)
                    ON CONFLICT (user_id, site_name, date_range_start) 
                    DO UPDATE SET
                        date_range_end = EXCLUDED.date_range_end,
                        metrics = EXCLUDED.metrics,
                        dimensions = EXCLUDED.dimensions,
                        audience_insights = EXCLUDED.audience_insights,
                        content_performance = EXCLUDED.content_performance,
                        traffic_patterns = EXCLUDED.traffic_patterns,
                        sync_version = google_analytics_data.sync_version + 1,
                        created_at = NOW()
                ''',
                self._user_id,
                site_name,
                view_id,  # property_id
                view_id,  # view_id (same for now)
                start_date,
                end_date,
                json.dumps(metrics),
                json.dumps(dimensions),
                json.dumps(audience_insights),
                json.dumps(content_performance),
                json.dumps(traffic_patterns)
                )
                
                logger.info(f"Stored comprehensive analytics for {site_name}: {metrics['total_users']} users")
            finally:
                await db_manager.release_connection(conn)
            
        except Exception as e:
            logger.error(f"Failed to store analytics: {e}", exc_info=True)
            # Don't raise - storing is optional, don't break the fetch

    async def get_analytics_summary(self, site_name: str, days: int = 30) -> dict[str, Any]:
        """
        Get analytics summary from JSONB columns
        """
        try:
            logger.info(f"Getting analytics summary: site={site_name}, days={days}")
            
            cutoff_date = datetime.now().date() - timedelta(days=days)
            
            conn = await db_manager.get_connection()
            try:
                latest_data = await conn.fetchrow('''
                    SELECT 
                        date_range_start,
                        date_range_end,
                        metrics,
                        dimensions,
                        audience_insights,
                        content_performance,
                        traffic_patterns,
                        created_at
                    FROM google_analytics_data
                    WHERE user_id = $1 AND site_name = $2
                    ORDER BY date_range_start DESC
                    LIMIT 1
                ''', self._user_id, site_name)
                
                # Determine if we need fresh data
                needs_fetch = False
                
                if not latest_data:
                    logger.info(f"No analytics data in DB for {site_name}")
                    needs_fetch = True
                else:
                    days_old = (datetime.now().date() - latest_data['date_range_end']).days
                    logger.debug(f"Latest data is {days_old} days old")
                    
                    # Fetch if data is more than 1 day old
                    if days_old > 1:
                        logger.info(f"Data is stale ({days_old} days old), fetching fresh data...")
                        needs_fetch = True
                
                # Fetch from API if needed
                if needs_fetch:
                    try:
                        logger.info(f"Fetching fresh analytics data from Google API...")
                        await self.fetch_traffic_summary(site_name, days)
                        logger.info(f"Fresh data fetched and stored")
                        
                        # Re-query to get the fresh data we just stored
                        latest_data = await conn.fetchrow('''
                            SELECT 
                                date_range_start,
                                date_range_end,
                                metrics,
                                dimensions,
                                audience_insights,
                                content_performance,
                                traffic_patterns,
                                created_at
                            FROM google_analytics_data
                            WHERE user_id = $1 AND site_name = $2
                            ORDER BY date_range_start DESC
                            LIMIT 1
                        ''', self._user_id, site_name)
                        
                    except Exception as fetch_error:
                        logger.error(f"Failed to fetch from API: {fetch_error}", exc_info=True)
                
                if not latest_data:
                    logger.warning(f"No analytics data available for {site_name}")
                    return {
                        'site_name': site_name,
                        'period_days': days,
                        'total_visitors': 0,
                        'total_pageviews': 0,
                        'total_sessions': 0,
                        'note': 'No data available'
                    }
                
                # Parse JSONB data
                metrics = latest_data['metrics']
                dimensions = latest_data['dimensions']
                content = latest_data['content_performance']
                traffic = latest_data['traffic_patterns']
                
                # Build response in the format the chat interface expects
                summary = {
                    'site_name': site_name,
                    'period_days': days,
                    'total_visitors': metrics.get('total_users', 0),
                    'total_pageviews': metrics.get('pageviews', 0),
                    'total_sessions': metrics.get('sessions', 0),
                    'avg_session_duration': metrics.get('avg_session_duration', 0),
                    'bounce_rate': metrics.get('bounce_rate', 0),
                    'engagement_rate': metrics.get('engagement_rate', 0),
                    'new_users': metrics.get('new_users', 0),
                    'returning_users': metrics.get('returning_users', 0),
                    
                    # Device breakdown
                    'devices': dimensions.get('devices', [])[:5],  # Top 5
                    
                    # Top pages
                    'top_pages': [
                        page.get('page_path', '')
                        for page in content.get('top_pages', [])[:5]
                    ],
                    
                    # Traffic sources
                    'traffic_sources': {
                        source.get('source', 'unknown'): source.get('sessions', 0)
                        for source in traffic.get('sources', [])[:5]
                    },
                    
                    'fetched_at': latest_data['created_at'].isoformat()
                }
                
                logger.info(f"Analytics summary: {summary['total_visitors']} visitors, {summary['total_pageviews']} pageviews")
                return summary
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"Failed to get analytics summary: {e}", exc_info=True)
            raise
    
    async def fetch_traffic_summary(self, site_name: str, days: int = 30):
        """
        Fetch traffic summary from Google Analytics Data API (GA4)
        Using official google-analytics-data library
        """
        try:
            logger.info(f"Fetching GA4 data for {site_name}, last {days} days")
            
            if not self._credentials:
                await self.initialize(self._user_id)
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            property_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"Fetching Analytics for property {property_id}: {start_date} to {end_date}")
            
            # Create client with credentials
            client = BetaAnalyticsDataClient(credentials=self._credentials)
            
            # Build the request
            request = RunReportRequest(
                property=f'properties/{property_id}',
                date_ranges=[DateRange(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )],
                metrics=[
                    Metric(name='activeUsers'),
                    Metric(name='newUsers'),
                    Metric(name='sessions'),
                    Metric(name='screenPageViews'),
                    Metric(name='averageSessionDuration'),
                    Metric(name='bounceRate'),
                    Metric(name='engagementRate')
                ],
                dimensions=[
                    Dimension(name='deviceCategory')
                ]
            )
            
            # Make the API call
            response = client.run_report(request)
            
            logger.info(f"GA4 API response received with {len(response.rows)} rows")
            
            # Parse response and build summary structure
            summary = self._parse_ga4_response(response, start_date, end_date)
            
            # Store the data
            await self._store_analytics_data(site_name, summary)
            
            logger.info(f"Successfully fetched and stored GA4 data for {site_name}")
            
        except Exception as e:
            logger.error(f"Failed to fetch GA4 data: {e}", exc_info=True)
            raise
    
    def _parse_ga4_response(self, response, start_date, end_date) -> dict[str, Any]:
        """Parse GA4 API response into our summary structure"""
        try:
            if not response.rows:
                logger.warning("No data in GA4 response")
                return self._empty_summary(start_date, end_date)
            
            # Aggregate metrics
            total_users = 0
            new_users = 0
            sessions = 0
            pageviews = 0
            total_duration = 0
            bounce_rate = 0
            engagement_rate = 0
            
            devices = []
            
            for row in response.rows:
                # Get metric values
                metric_values = row.metric_values
                
                if len(metric_values) >= 7:
                    total_users += int(metric_values[0].value) if metric_values[0].value else 0
                    new_users += int(metric_values[1].value) if metric_values[1].value else 0
                    sessions += int(metric_values[2].value) if metric_values[2].value else 0
                    pageviews += int(metric_values[3].value) if metric_values[3].value else 0
                    total_duration += float(metric_values[4].value) if metric_values[4].value else 0
                    bounce_rate = float(metric_values[5].value) if metric_values[5].value else 0
                    engagement_rate = float(metric_values[6].value) if metric_values[6].value else 0
                
                # Get device dimension
                if row.dimension_values:
                    device = row.dimension_values[0].value
                    devices.append({
                        'device': device,
                        'sessions': int(metric_values[2].value) if len(metric_values) > 2 and metric_values[2].value else 0
                    })
            
            avg_duration = total_duration / len(response.rows) if response.rows else 0
            returning_users = total_users - new_users if total_users > new_users else 0
            
            summary = {
                'date_range': {
                    'start': start_date,
                    'end': end_date
                },
                'overview': {
                    'total_users': total_users,
                    'new_users': new_users,
                    'returning_users': returning_users,
                    'sessions': sessions,
                    'pageviews': pageviews,
                    'avg_session_duration': avg_duration,
                    'bounce_rate': bounce_rate,
                    'engagement_rate': engagement_rate,
                    'avg_sessions_per_user': sessions / total_users if total_users > 0 else 0,
                    'avg_pages_per_session': pageviews / sessions if sessions > 0 else 0,
                    'total_engagement_time': total_duration
                },
                'devices': devices,
                'geography': [],
                'demographics': [],
                'landing_pages': [],
                'pages': [],
                'events': [],
                'sources': [],
                'api_version': 'GA4',
                'fetched_at': datetime.now().isoformat()
            }
            
            logger.info(f"Parsed GA4 data: {total_users} users, {sessions} sessions, {pageviews} pageviews")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to parse GA4 response: {e}", exc_info=True)
            return self._empty_summary(start_date, end_date)
    
    def _empty_summary(self, start_date, end_date) -> dict[str, Any]:
        """Return empty summary structure"""
        return {
            'date_range': {
                'start': start_date,
                'end': end_date
            },
            'overview': {
                'total_users': 0,
                'new_users': 0,
                'returning_users': 0,
                'sessions': 0,
                'pageviews': 0,
                'avg_session_duration': 0,
                'bounce_rate': 0,
                'engagement_rate': 0,
                'avg_sessions_per_user': 0,
                'avg_pages_per_session': 0,
                'total_engagement_time': 0
            },
            'devices': [],
            'geography': [],
            'demographics': [],
            'landing_pages': [],
            'pages': [],
            'events': [],
            'sources': [],
            'api_version': 'GA4',
            'fetched_at': datetime.now().isoformat()
        }


# Module-level instance and helper functions for router
analytics_client = None

def get_analytics_client(user_id: str) -> AnalyticsClient:
    """Get or create analytics client for user"""
    return AnalyticsClient(user_id)

async def fetch_analytics_summary(user_id: str, site_name: str, days: int = 30):
    """Helper function for router"""
    client = get_analytics_client(user_id)
    return await client.get_analytics_summary(site_name, days)

async def get_optimal_timing(user_id: str, site_name: str):
    """Get optimal posting times based on traffic patterns"""
    # TODO: Implement based on traffic_patterns JSONB data
    return {
        "peak_hours": [9, 14, 20],
        "peak_days": ["Monday", "Wednesday", "Thursday"]
    }
