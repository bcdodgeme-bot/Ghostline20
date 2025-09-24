# modules/integrations/rss_learning/__init__.py
"""
RSS Learning Integration Module for Syntax Prime V2
Intelligent marketing content analysis system that feeds insights to the AI brain
"""

from .feed_processor import RSSFeedProcessor
from .content_analyzer import ContentAnalyzer
from .marketing_insights import MarketingInsightsExtractor
from .database_manager import RSSDatabase
from .router import router

__version__ = "1.0.0"
__description__ = "RSS Learning System for marketing insights and AI brain integration"

__all__ = [
    'RSSFeedProcessor', 
    'ContentAnalyzer', 
    'MarketingInsightsExtractor', 
    'RSSDatabase', 
    'router'
]

def check_module_health() -> dict:
    """Check if RSS learning module is properly configured"""
    import os
    
    database_url = os.getenv('DATABASE_URL')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    return {
        'healthy': bool(database_url),
        'missing_vars': [var for var in ['DATABASE_URL'] if not os.getenv(var)],
        'optional_missing': [var for var in ['OPENAI_API_KEY'] if not os.getenv(var)],
        'ai_features': bool(openai_key),
        'configured': bool(database_url)
    }

def get_integration_info() -> dict:
    """Get RSS learning integration information"""
    return {
        'module': 'rss_learning',
        'version': __version__,
        'description': __description__,
        'endpoints': {
            'status': '/integrations/rss/status',
            'sources': '/integrations/rss/sources',
            'insights': '/integrations/rss/insights',
            'trends': '/integrations/rss/trends',
            'fetch': '/integrations/rss/fetch'
        },
        'features': [
            'Weekly RSS feed processing',
            'AI-powered content analysis',
            'Marketing insights extraction',
            'Trend identification',
            'Content categorization',
            'AI brain integration for writing assistance'
        ],
        'sources': [
            'Moz Blog (SEO)',
            'Content Marketing Institute',
            'HubSpot Marketing Blog', 
            'Neil Patel Blog',
            'Semrush Blog',
            'Social Media Examiner',
            'Google Blog',
            'Rank Math Blog'
        ],
        'health': check_module_health()
    }

# Background service management
_background_service = None

async def start_rss_service():
    """Start RSS background processing service"""
    global _background_service
    
    if _background_service is None:
        from .feed_processor import RSSFeedProcessor
        _background_service = RSSFeedProcessor()
        await _background_service.start_background_processing()
        return True
    return False

async def stop_rss_service():
    """Stop RSS background processing service"""
    global _background_service
    
    if _background_service:
        await _background_service.stop_background_processing()
        _background_service = None
        return True
    return False

async def get_service_status():
    """Get RSS service status"""
    global _background_service
    
    return {
        'running': _background_service is not None,
        'processor': _background_service.get_status() if _background_service else None
    }