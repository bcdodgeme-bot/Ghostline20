# modules/integrations/google_workspace/analytics_client.py
"""
Google Analytics Client - REFACTORED FOR AIOGOOGLE
True async API calls for traffic analysis
"""

import json
from datetime import datetime, timedelta

async def _store_analytics_data(self, site_name: str, summary: Dict[str, Any]):
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
        logger.debug(f"💾 Storing analytics data for {site_name}...")
        
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
        
        async with db_manager.get_connection() as conn:
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
        
        logger.info(f"✅ Stored comprehensive analytics for {site_name}: {metrics['total_users']} users")
        
    except Exception as e:
        logger.error(f"❌ Failed to store analytics: {e}", exc_info=True)
        # Don't raise - storing is optional, don't break the fetch


# Also update the retrieval function to read JSONB data
async def get_analytics_summary(self, site_name: str, days: int = 30) -> Dict[str, Any]:
    """
    Get analytics summary from JSONB columns
    """
    try:
        logger.info(f"📊 Getting analytics summary: site={site_name}, days={days}")
        
        cutoff_date = datetime.now().date() - timedelta(days=days)
        
        async with db_manager.get_connection() as conn:
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
                logger.info(f"📊 No analytics data in DB for {site_name}")
                needs_fetch = True
            else:
                days_old = (datetime.now().date() - latest_data['date_range_end']).days
                logger.debug(f"📊 Latest data is {days_old} days old")
                
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
                    logger.error(f"⚠️ Failed to fetch from API: {fetch_error}", exc_info=True)
            
            if not latest_data:
                logger.warning(f"⚠️ No analytics data available for {site_name}")
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
            
            logger.info(f"✅ Analytics summary: {summary['total_visitors']} visitors, {summary['total_pageviews']} pageviews")
            return summary
            
    except Exception as e:
        logger.error(f"❌ Failed to get analytics summary: {e}", exc_info=True)
        raise
