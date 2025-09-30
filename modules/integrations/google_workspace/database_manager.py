# modules/integrations/google_workspace/database_manager.py
"""
Google Workspace Database Manager
Centralized database operations for all Google Workspace data

This module:
1. Manages all Google Workspace database operations
2. Provides data retrieval and aggregation functions
3. Handles cross-system correlations (Analytics + Search Console + Trends)
4. Supports keyword workflow integration with existing tables
5. Provides health checks and data quality monitoring

Database Tables:
- google_oauth_accounts (authentication)
- google_service_config (service accounts)
- google_analytics_data (traffic metrics)
- google_search_console_data (keyword data)
- google_drive_documents (created docs)
- google_sites_config (site configuration)
- google_oauth_status (OAuth status tracking)
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from . import SUPPORTED_SITES
from ...core.database import db_manager

class GoogleWorkspaceDatabase:
    """
    Centralized database manager for Google Workspace integration
    Handles all data storage, retrieval, and correlation operations
    """
    
    def __init__(self):
        """Initialize database manager"""
        logger.info("🗄️ Google Workspace Database Manager initialized")
    
    # ==================== ANALYTICS DATA ====================
    
    async def get_analytics_summary(self, user_id: str, site_name: str, days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Get Analytics summary for a site
        
        Args:
            user_id: User ID
            site_name: Site identifier
            days: Number of days to look back
            
        Returns:
            Analytics summary dict or None
        """
        try:
            cutoff_date = datetime.now().date() - timedelta(days=days)
            
            async with db_manager.get_connection() as conn:
                result = await conn.fetchrow('''
                    SELECT 
                        site_name,
                        date_range_start,
                        date_range_end,
                        metrics,
                        created_at
                    FROM google_analytics_data
                    WHERE user_id = $1 
                        AND site_name = $2
                        AND date_range_start >= $3
                    ORDER BY date_range_start DESC
                    LIMIT 1
                ''', user_id, site_name, cutoff_date)
                
                if result:
                    return dict(result)
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get Analytics summary: {e}")
            return None
    
    async def get_all_sites_analytics(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get Analytics summaries for all sites"""
        summaries = []
        
        for site_name in SUPPORTED_SITES.keys():
            summary = await self.get_analytics_summary(user_id, site_name, days)
            if summary:
                summaries.append(summary)
        
        return summaries
    
    # ==================== SEARCH CONSOLE DATA ====================
    
    async def get_top_keywords(self, user_id: str, site_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top performing keywords from Search Console
        
        Args:
            user_id: User ID
            site_name: Site identifier
            limit: Number of keywords to return
            
        Returns:
            List of top keywords with metrics
        """
        try:
            async with db_manager.get_connection() as conn:
                keywords = await conn.fetch('''
                    SELECT 
                        query as keyword,
                        clicks,
                        impressions,
                        ctr,
                        position,
                        date
                    FROM google_search_console_data
                    WHERE user_id = $1 AND site_name = $2
                    ORDER BY clicks DESC, impressions DESC
                    LIMIT $3
                ''', user_id, site_name, limit)
                
                return [dict(kw) for kw in keywords]
                
        except Exception as e:
            logger.error(f"❌ Failed to get top keywords: {e}")
            return []
    
    async def get_keyword_opportunities_count(self, user_id: str, site_name: Optional[str] = None) -> int:
        """
        Get count of pending keyword opportunities
        
        Args:
            user_id: User ID
            site_name: Optional site filter
            
        Returns:
            Count of pending opportunities
        """
        try:
            async with db_manager.get_connection() as conn:
                if site_name:
                    count = await conn.fetchval('''
                        SELECT COUNT(*) FROM google_search_console_data
                        WHERE user_id = $1 
                            AND site_name = $2
                            AND user_decision IS NULL
                            AND impressions >= 100
                            AND position BETWEEN 11 AND 30
                    ''', user_id, site_name)
                else:
                    count = await conn.fetchval('''
                        SELECT COUNT(*) FROM google_search_console_data
                        WHERE user_id = $1
                            AND user_decision IS NULL
                            AND impressions >= 100
                            AND position BETWEEN 11 AND 30
                    ''', user_id)
                
                return count or 0
                
        except Exception as e:
            logger.error(f"❌ Failed to get opportunities count: {e}")
            return 0
    
    async def get_keyword_decisions_summary(self, user_id: str, site_name: str) -> Dict[str, int]:
        """
        Get summary of keyword decisions (added/ignored)
        
        Args:
            user_id: User ID
            site_name: Site identifier
            
        Returns:
            Dict with counts by decision type
        """
        try:
            async with db_manager.get_connection() as conn:
                results = await conn.fetch('''
                    SELECT user_decision, COUNT(*) as count
                    FROM google_search_console_data
                    WHERE user_id = $1 AND site_name = $2
                        AND user_decision IS NOT NULL
                    GROUP BY user_decision
                ''', user_id, site_name)
                
                summary = {'add': 0, 'ignore': 0, 'pending': 0}
                
                for row in results:
                    summary[row['user_decision']] = row['count']
                
                # Get pending count
                pending = await self.get_keyword_opportunities_count(user_id, site_name)
                summary['pending'] = pending
                
                return summary
                
        except Exception as e:
            logger.error(f"❌ Failed to get keyword decisions summary: {e}")
            return {'add': 0, 'ignore': 0, 'pending': 0}
    
    # ==================== DRIVE DOCUMENTS ====================
    
    async def get_recent_documents(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently created Drive documents"""
        try:
            async with db_manager.get_connection() as conn:
                docs = await conn.fetch('''
                    SELECT 
                        google_doc_id,
                        document_title,
                        document_type,
                        document_url,
                        created_at
                    FROM google_drive_documents
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                ''', user_id, limit)
                
                return [dict(doc) for doc in docs]
                
        except Exception as e:
            logger.error(f"❌ Failed to get recent documents: {e}")
            return []
    
    # ==================== OAUTH STATUS ====================
    
    async def get_oauth_status(self, user_id: str) -> Dict[str, Any]:
        """
        Get OAuth configuration and access status
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with OAuth status information
        """
        try:
            async with db_manager.get_connection() as conn:
                status = await conn.fetchrow('''
                    SELECT * FROM google_oauth_status
                    WHERE user_id = $1
                ''', user_id)
                
                if status:
                    return dict(status)
                
                # Create default status if not exists
                await conn.execute('''
                    INSERT INTO google_oauth_status (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                ''', user_id)
                
                return {
                    'has_service_account': False,
                    'has_oauth_accounts': False,
                    'analytics_access': False,
                    'search_console_access': False,
                    'drive_access': False
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get OAuth status: {e}")
            return {}
    
    async def update_oauth_status(self, user_id: str, updates: Dict[str, Any]):
        """
        Update OAuth status
        
        Args:
            user_id: User ID
            updates: Dict of fields to update
        """
        try:
            # Build dynamic update query
            set_clauses = []
            values = []
            param_count = 1
            
            for key, value in updates.items():
                set_clauses.append(f"{key} = ${param_count}")
                values.append(value)
                param_count += 1
            
            values.append(user_id)
            
            query = f'''
                UPDATE google_oauth_status
                SET {', '.join(set_clauses)}, updated_at = NOW()
                WHERE user_id = ${param_count}
            '''
            
            async with db_manager.get_connection() as conn:
                await conn.execute(query, *values)
            
            logger.info(f"✅ Updated OAuth status for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update OAuth status: {e}")
    
    # ==================== SITE CONFIGURATION ====================
    
    async def get_site_config(self, user_id: str, site_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific site"""
        try:
            async with db_manager.get_connection() as conn:
                config = await conn.fetchrow('''
                    SELECT * FROM google_sites_config
                    WHERE user_id = $1 AND site_name = $2
                ''', user_id, site_name)
                
                if config:
                    return dict(config)
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get site config: {e}")
            return None
    
    async def get_all_sites_config(self, user_id: str) -> List[Dict[str, Any]]:
        """Get configuration for all sites"""
        try:
            async with db_manager.get_connection() as conn:
                configs = await conn.fetch('''
                    SELECT * FROM google_sites_config
                    WHERE user_id = $1 AND is_active = TRUE
                    ORDER BY site_name
                ''', user_id)
                
                return [dict(config) for config in configs]
                
        except Exception as e:
            logger.error(f"❌ Failed to get all sites config: {e}")
            return []
    
    # ==================== CROSS-SYSTEM CORRELATIONS ====================
    
    async def correlate_keywords_with_analytics(self, user_id: str, site_name: str) -> List[Dict[str, Any]]:
        """
        Correlate Search Console keywords with Analytics content performance
        
        Args:
            user_id: User ID
            site_name: Site identifier
            
        Returns:
            List of correlated keyword/content insights
        """
        try:
            # Get top keywords from Search Console
            top_keywords = await self.get_top_keywords(user_id, site_name, limit=20)
            
            # Get Analytics summary
            analytics = await self.get_analytics_summary(user_id, site_name, days=30)
            
            if not top_keywords or not analytics:
                return []
            
            # Basic correlation (can be enhanced)
            correlations = []
            
            for keyword in top_keywords:
                correlations.append({
                    'keyword': keyword['keyword'],
                    'search_metrics': {
                        'clicks': keyword['clicks'],
                        'impressions': keyword['impressions'],
                        'position': keyword['position']
                    },
                    'recommendation': self._generate_keyword_recommendation(keyword, analytics)
                })
            
            return correlations
            
        except Exception as e:
            logger.error(f"❌ Failed to correlate keywords with Analytics: {e}")
            return []
    
    def _generate_keyword_recommendation(self, keyword: Dict[str, Any], analytics: Dict[str, Any]) -> str:
        """Generate content recommendation based on keyword and Analytics data"""
        position = float(keyword.get('position', 0))
        impressions = keyword.get('impressions', 0)
        
        if position <= 15 and impressions >= 500:
            return f"Quick win: Create targeted content for '{keyword['keyword']}' - already getting visibility"
        elif position <= 25 and impressions >= 200:
            return f"Content boost: Enhance existing content around '{keyword['keyword']}' to improve ranking"
        else:
            return f"Long-term: Build comprehensive content strategy around '{keyword['keyword']}'"
    
    # ==================== DATA QUALITY & HEALTH ====================
    
    async def get_data_freshness(self, user_id: str) -> Dict[str, Any]:
        """
        Check data freshness across all Google Workspace sources
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with last sync times for each data source
        """
        try:
            async with db_manager.get_connection() as conn:
                # Get last Analytics sync
                analytics_sync = await conn.fetchval('''
                    SELECT MAX(created_at) FROM google_analytics_data
                    WHERE user_id = $1
                ''', user_id)
                
                # Get last Search Console sync
                search_console_sync = await conn.fetchval('''
                    SELECT MAX(created_at) FROM google_search_console_data
                    WHERE user_id = $1
                ''', user_id)
                
                # Get OAuth status
                oauth_status = await self.get_oauth_status(user_id)
                
                return {
                    'analytics_last_sync': analytics_sync,
                    'search_console_last_sync': search_console_sync,
                    'oauth_status': oauth_status,
                    'data_fresh': self._is_data_fresh(analytics_sync, search_console_sync)
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to check data freshness: {e}")
            return {}
    
    def _is_data_fresh(self, analytics_sync, search_console_sync) -> bool:
        """Check if data is fresh (synced within last 3 hours)"""
        now = datetime.now()
        threshold = timedelta(hours=3)
        
        if analytics_sync and (now - analytics_sync) < threshold:
            return True
        if search_console_sync and (now - search_console_sync) < threshold:
            return True
        
        return False
    
    async def get_integration_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get overall integration statistics
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with comprehensive stats
        """
        try:
            async with db_manager.get_connection() as conn:
                # Get counts
                analytics_count = await conn.fetchval('''
                    SELECT COUNT(*) FROM google_analytics_data WHERE user_id = $1
                ''', user_id)
                
                search_console_count = await conn.fetchval('''
                    SELECT COUNT(*) FROM google_search_console_data WHERE user_id = $1
                ''', user_id)
                
                documents_count = await conn.fetchval('''
                    SELECT COUNT(*) FROM google_drive_documents WHERE user_id = $1
                ''', user_id)
                
                opportunities_count = await self.get_keyword_opportunities_count(user_id)
                
                return {
                    'analytics_records': analytics_count or 0,
                    'search_console_records': search_console_count or 0,
                    'documents_created': documents_count or 0,
                    'pending_opportunities': opportunities_count,
                    'sites_configured': len(SUPPORTED_SITES)
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get integration stats: {e}")
            return {}

# Global instance
google_workspace_db = GoogleWorkspaceDatabase()

# Convenience functions for other modules
async def get_analytics_data(user_id: str, site_name: str, days: int = 30) -> Optional[Dict[str, Any]]:
    """Get Analytics data for a site"""
    return await google_workspace_db.get_analytics_summary(user_id, site_name, days)

async def get_keyword_opportunities(user_id: str, site_name: Optional[str] = None) -> int:
    """Get count of keyword opportunities"""
    return await google_workspace_db.get_keyword_opportunities_count(user_id, site_name)

async def get_workspace_stats(user_id: str) -> Dict[str, Any]:
    """Get overall Google Workspace integration statistics"""
    return await google_workspace_db.get_integration_stats(user_id)