# modules/integrations/google_workspace/analytics_client.py
"""
Google Analytics Client - User Journey & Audience Intelligence
Full user journey analysis from traffic sources to conversion

This module:
1. Fetches Analytics data for all 5 sites (GA4 & Universal Analytics)
2. Analyzes user behavior patterns and content performance
3. Identifies optimal content timing based on traffic patterns
4. Provides audience insights for content strategy
5. Correlates Analytics data with Search Console keywords

Analytics Focus:
- Traffic patterns by time/day for optimal posting
- Content performance correlation with keywords
- Audience behavior for content strategy
- User journey analysis for conversion optimization
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
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    logger.warning("⚠️ Google Analytics API client not installed")

from . import SUPPORTED_SITES
from .oauth_manager import get_google_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class AnalyticsClient:
    """
    Google Analytics API client with audience intelligence
    Supports both GA4 and Universal Analytics for V1 compatibility
    """
    
    def __init__(self):
        """Initialize Analytics client"""
        if not ANALYTICS_AVAILABLE:
            logger.error("❌ Google Analytics API client not available")
            raise RuntimeError("Google API client required - run: pip install google-api-python-client")
        
        self._service = None
        self._service_v4 = None  # GA4
        self._user_id = None
        
        logger.info("📊 Analytics client initialized")
    
    async def initialize(self, user_id: str):
        """
        Initialize Analytics services with credentials
        
        Args:
            user_id: User ID for credential lookup
        """
        try:
            self._user_id = user_id
            
            # Get credentials from auth manager
            credentials = await get_google_credentials(user_id, email=None)
            
            if not credentials:
                raise Exception("No valid credentials available")
            
            # Build Analytics services (both Universal Analytics and GA4)
            self._service = build('analytics', 'v3', credentials=credentials)
            self._service_v4 = build('analyticsdata', 'v1beta', credentials=credentials)
            
            logger.info("✅ Analytics services initialized")
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Analytics initialization failed: {e}")
            raise
    
    async def fetch_traffic_summary(self, site_name: str, days: int = 30) -> Dict[str, Any]:
        """
        Fetch traffic summary for a site
        
        Args:
            site_name: Site identifier
            days: Number of days of data to fetch
            
        Returns:
            Dict with traffic metrics
        """
        try:
            if not self._service:
                raise Exception("Analytics service not initialized")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"📊 Fetching Analytics data for {site_name}...")
            
            # Fetch basic metrics
            response = self._service.data().ga().get(
                ids=f'ga:{view_id}',
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                metrics='ga:sessions,ga:users,ga:pageviews,ga:bounceRate,ga:avgSessionDuration',
                dimensions='ga:date'
            ).execute()
            
            rows = response.get('rows', [])
            
            if not rows:
                logger.warning(f"⚠️ No Analytics data found for {site_name}")
                return {}
            
            # Parse data
            total_sessions = sum(int(row[1]) for row in rows)
            total_users = sum(int(row[2]) for row in rows)
            total_pageviews = sum(int(row[3]) for row in rows)
            avg_bounce_rate = sum(float(row[4]) for row in rows) / len(rows)
            avg_session_duration = sum(float(row[5]) for row in rows) / len(rows)
            
            summary = {
                'site_name': site_name,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'metrics': {
                    'sessions': total_sessions,
                    'users': total_users,
                    'pageviews': total_pageviews,
                    'bounce_rate': round(avg_bounce_rate, 2),
                    'avg_session_duration': round(avg_session_duration, 2)
                },
                'daily_data': rows
            }
            
            logger.info(f"✅ Fetched Analytics for {site_name}: {total_sessions} sessions")
            
            return summary
            
        except HttpError as e:
            if e.resp.status == 403:
                logger.error(f"❌ Access denied for {site_name} - check Analytics permissions")
            else:
                logger.error(f"❌ Analytics API error for {site_name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Failed to fetch Analytics data: {e}")
            return {}
    
    async def fetch_traffic_sources(self, site_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch traffic sources for a site
        
        Args:
            site_name: Site identifier
            days: Number of days of data
            
        Returns:
            List of traffic source data
        """
        try:
            if not self._service:
                raise Exception("Analytics service not initialized")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Fetch traffic source data
            response = self._service.data().ga().get(
                ids=f'ga:{view_id}',
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                metrics='ga:sessions,ga:users',
                dimensions='ga:source,ga:medium'
            ).execute()
            
            rows = response.get('rows', [])
            
            sources = []
            for row in rows:
                sources.append({
                    'source': row[0],
                    'medium': row[1],
                    'sessions': int(row[2]),
                    'users': int(row[3])
                })
            
            # Sort by sessions
            sources.sort(key=lambda x: x['sessions'], reverse=True)
            
            logger.info(f"✅ Fetched {len(sources)} traffic sources for {site_name}")
            
            return sources
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch traffic sources: {e}")
            return []
    
    async def fetch_content_performance(self, site_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch content performance (top pages)
        
        Args:
            site_name: Site identifier
            days: Number of days of data
            
        Returns:
            List of page performance data
        """
        try:
            if not self._service:
                raise Exception("Analytics service not initialized")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Fetch page performance data
            response = self._service.data().ga().get(
                ids=f'ga:{view_id}',
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                metrics='ga:pageviews,ga:uniquePageviews,ga:avgTimeOnPage,ga:bounceRate',
                dimensions='ga:pagePath,ga:pageTitle',
                sort='-ga:pageviews',
                max_results=50
            ).execute()
            
            rows = response.get('rows', [])
            
            pages = []
            for row in rows:
                pages.append({
                    'path': row[0],
                    'title': row[1],
                    'pageviews': int(row[2]),
                    'unique_pageviews': int(row[3]),
                    'avg_time_on_page': float(row[4]),
                    'bounce_rate': float(row[5])
                })
            
            logger.info(f"✅ Fetched performance for {len(pages)} pages on {site_name}")
            
            return pages
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch content performance: {e}")
            return []
    
    async def analyze_traffic_patterns(self, site_name: str, days: int = 30) -> Dict[str, Any]:
        """
        Analyze traffic patterns to identify optimal content timing
        
        Args:
            site_name: Site identifier
            days: Number of days to analyze
            
        Returns:
            Dict with traffic pattern insights
        """
        try:
            if not self._service:
                raise Exception("Analytics service not initialized")
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            view_id = site_config['analytics_view_id']
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Fetch traffic by hour and day of week
            response = self._service.data().ga().get(
                ids=f'ga:{view_id}',
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                metrics='ga:sessions',
                dimensions='ga:dayOfWeek,ga:hour'
            ).execute()
            
            rows = response.get('rows', [])
            
            # Analyze patterns
            day_totals = {}
            hour_totals = {}
            
            for row in rows:
                day = int(row[0])  # 0=Sunday, 6=Saturday
                hour = int(row[1])
                sessions = int(row[2])
                
                day_totals[day] = day_totals.get(day, 0) + sessions
                hour_totals[hour] = hour_totals.get(hour, 0) + sessions
            
            # Find best day
            best_day = max(day_totals.items(), key=lambda x: x[1])
            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            
            # Find best hours
            top_hours = sorted(hour_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            
            patterns = {
                'site_name': site_name,
                'best_day': {
                    'day': day_names[best_day[0]],
                    'sessions': best_day[1]
                },
                'best_hours': [
                    {'hour': hour, 'sessions': sessions} 
                    for hour, sessions in top_hours
                ],
                'day_breakdown': {
                    day_names[day]: sessions 
                    for day, sessions in day_totals.items()
                },
                'recommendation': f"Post content on {day_names[best_day[0]]} around {top_hours[0][0]}:00 for maximum engagement"
            }
            
            logger.info(f"✅ Traffic patterns analyzed for {site_name}")
            
            return patterns
            
        except Exception as e:
            logger.error(f"❌ Failed to analyze traffic patterns: {e}")
            return {}
    
    async def store_analytics_data(self, site_name: str, analytics_data: Dict[str, Any]):
        """
        Store Analytics data in database
        
        Args:
            site_name: Site identifier
            analytics_data: Analytics data from fetch_traffic_summary
        """
        try:
            if not analytics_data:
                logger.info(f"ℹ️ No Analytics data to store for {site_name}")
                return
            
            site_config = SUPPORTED_SITES.get(site_name)
            if not site_config:
                raise Exception(f"Unknown site: {site_name}")
            
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO google_analytics_data
                    (user_id, site_name, property_id, view_id, 
                     date_range_start, date_range_end, metrics, dimensions)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (user_id, site_name, property_id, date_range_start, date_range_end)
                    DO UPDATE SET
                        metrics = EXCLUDED.metrics,
                        dimensions = EXCLUDED.dimensions
                ''',
                self._user_id,
                site_name,
                site_config['analytics_view_id'],
                site_config['analytics_view_id'],
                analytics_data['date_range']['start'],
                analytics_data['date_range']['end'],
                analytics_data.get('metrics', {}),
                analytics_data.get('dimensions', {})
                )
            
            logger.info(f"✅ Stored Analytics data for {site_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store Analytics data: {e}")
            raise
    
    async def get_optimal_posting_time(self, site_name: str) -> Dict[str, Any]:
        """
        Get optimal posting time based on historical traffic patterns
        
        Args:
            site_name: Site identifier
            
        Returns:
            Dict with optimal timing recommendation
        """
        try:
            patterns = await self.analyze_traffic_patterns(site_name, days=30)
            
            if not patterns:
                return {
                    'site_name': site_name,
                    'recommendation': 'No data available yet - post during typical business hours'
                }
            
            return {
                'site_name': site_name,
                'best_day': patterns['best_day']['day'],
                'best_hour': patterns['best_hours'][0]['hour'],
                'recommendation': patterns['recommendation']
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get optimal posting time: {e}")
            return {}

# Global instance
analytics_client = AnalyticsClient()

# Convenience functions for other modules
async def fetch_analytics_summary(user_id: str, site_name: str, days: int = 30) -> Dict[str, Any]:
    """Fetch Analytics summary for a site"""
    await analytics_client.initialize(user_id)
    return await analytics_client.fetch_traffic_summary(site_name, days)

async def get_traffic_sources(user_id: str, site_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get traffic sources for a site"""
    await analytics_client.initialize(user_id)
    return await analytics_client.fetch_traffic_sources(site_name, days)

async def get_content_performance(user_id: str, site_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get content performance for a site"""
    await analytics_client.initialize(user_id)
    return await analytics_client.fetch_content_performance(site_name, days)

async def get_optimal_timing(user_id: str, site_name: str) -> Dict[str, Any]:
    """Get optimal content posting time"""
    await analytics_client.initialize(user_id)
    return await analytics_client.get_optimal_posting_time(site_name)