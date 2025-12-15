# modules/integrations/rss_learning/__init__.py
"""
RSS Learning Integration Module for Syntax Prime V2
Intelligent marketing content analysis system that feeds insights to the AI brain

UPDATED: Session 15 - Use singleton getters, added knowledge base integration
"""

from .feed_processor import RSSFeedProcessor, get_feed_processor
from .content_analyzer import ContentAnalyzer, get_content_analyzer
from .marketing_insights import MarketingInsightsExtractor, get_marketing_insights_extractor
from .database_manager import RSSDatabase, get_rss_database
from .router import router

__version__ = "1.1.0"  # Updated for Session 15 changes
__description__ = "RSS Learning System for marketing insights and AI brain integration"

__all__ = [
    'RSSFeedProcessor',
    'get_feed_processor',
    'ContentAnalyzer',
    'get_content_analyzer',
    'MarketingInsightsExtractor',
    'get_marketing_insights_extractor',
    'RSSDatabase',
    'get_rss_database',
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
        'configured': bool(database_url),
        'knowledge_base_integration': True  # New feature
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
            'fetch': '/integrations/rss/fetch',
            'backfill_knowledge': '/integrations/rss/backfill-knowledge',
            'knowledge_stats': '/integrations/rss/knowledge-stats'
        },
        'features': [
            'Weekly RSS feed processing',
            'AI-powered content analysis',
            'Marketing insights extraction',
            'Trend identification',
            'Content categorization',
            'AI brain integration for writing assistance',
            'Knowledge base synchronization'
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


async def start_rss_service():
    """Start RSS background processing service"""
    processor = get_feed_processor()
    
    if processor.running:
        return False
    
    await processor.start_background_processing()
    return True


async def stop_rss_service():
    """Stop RSS background processing service"""
    processor = get_feed_processor()
    
    if not processor.running:
        return False
    
    await processor.stop_background_processing()
    return True


async def get_service_status():
    """Get RSS service status"""
    processor = get_feed_processor()
    
    return {
        'running': processor.running,
        'processor': processor.get_status()
    }


async def backfill_knowledge_base():
    """
    Convenience function to backfill existing RSS entries to knowledge base.
    Call this once after deploying the Session 15 update.
    """
    db = get_rss_database()
    return await db.backfill_knowledge_base()
