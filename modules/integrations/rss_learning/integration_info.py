# modules/integrations/rss_learning/integration_info.py
"""
RSS Learning Integration Info - Health checks and system information
Provides comprehensive status information for the RSS learning system
"""

import os
import asyncio
from typing import Dict, Any
from datetime import datetime
import logging

from .database_manager import RSSDatabase
from .feed_processor import RSSFeedProcessor
from .marketing_insights import MarketingInsightsExtractor

logger = logging.getLogger(__name__)

async def get_integration_health() -> Dict[str, Any]:
    """Get comprehensive health check for RSS learning integration"""
    
    health_status = {
        'status': 'healthy',
        'components': {},
        'metrics': {},
        'configuration': {},
        'last_checked': datetime.now().isoformat()
    }
    
    try:
        # Database health
        db = RSSDatabase()
        stats = await db.get_rss_statistics()
        
        health_status['components']['database'] = {
            'status': 'healthy' if stats.get('total_sources', 0) > 0 else 'warning',
            'total_sources': stats.get('total_sources', 0),
            'active_sources': stats.get('active_sources', 0),
            'total_items': stats.get('total_items', 0),
            'processed_items': stats.get('processed_items', 0)
        }
        
        # Processor health
        processor = RSSFeedProcessor()
        processor_status = processor.get_status()
        
        health_status['components']['feed_processor'] = {
            'status': 'healthy' if processor_status.get('running') else 'stopped',
            'running': processor_status.get('running', False),
            'has_session': processor_status.get('has_session', False),
            'background_task_active': processor_status.get('background_task_active', False)
        }
        
        # AI Analysis health
        insights = MarketingInsightsExtractor()
        
        health_status['components']['ai_analysis'] = {
            'status': 'healthy',
            'openai_available': bool(os.getenv('OPENAI_API_KEY')),
            'fallback_mode': not bool(os.getenv('OPENAI_API_KEY'))
        }
        
        # Configuration check
        health_status['configuration'] = {
            'database_url': bool(os.getenv('DATABASE_URL')),
            'openai_key': bool(os.getenv('OPENAI_API_KEY')),
            'background_processing': processor_status.get('running', False)
        }
        
        # Metrics
        health_status['metrics'] = {
            'avg_relevance_score': stats.get('avg_relevance', 0),
            'avg_trend_score': stats.get('avg_trend_score', 0),
            'recent_items_7_days': stats.get('recent_items', 0),
            'processing_rate': f"{stats.get('processed_items', 0)}/{stats.get('total_items', 1)}"
        }
        
        # Overall status
        critical_issues = 0
        
        if stats.get('total_sources', 0) == 0:
            critical_issues += 1
        
        if stats.get('total_items', 0) == 0:
            critical_issues += 1
            
        if not processor_status.get('running'):
            critical_issues += 1
        
        if critical_issues > 1:
            health_status['status'] = 'error'
        elif critical_issues == 1:
            health_status['status'] = 'warning'
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status['status'] = 'error'
        health_status['error'] = str(e)
    
    return health_status

async def get_system_info() -> Dict[str, Any]:
    """Get detailed system information for RSS learning integration"""
    
    info = {
        'module': 'rss_learning',
        'version': '1.0.0',
        'description': 'RSS Learning System for marketing insights and AI brain integration',
        'features': [
            'Weekly RSS feed processing',
            'AI-powered content analysis', 
            'Marketing insights extraction',
            'Trend identification',
            'Content categorization',
            'AI brain integration for writing assistance'
        ],
        'endpoints': {
            'status': '/integrations/rss/status',
            'sources': '/integrations/rss/sources',
            'insights': '/integrations/rss/insights',
            'trends': '/integrations/rss/trends',
            'writing_inspiration': '/integrations/rss/writing-inspiration',
            'campaign_insights': '/integrations/rss/campaign-insights/{type}',
            'research': '/integrations/rss/research',
            'fetch': '/integrations/rss/fetch',
            'ai_brain_trends': '/integrations/rss/ai-brain/latest-trends',
            'ai_brain_context': '/integrations/rss/ai-brain/writing-context',
            'health': '/integrations/rss/health'
        }
    }
    
    try:
        # Get RSS sources info
        db = RSSDatabase()
        query = "SELECT name, category, feed_url FROM rss_sources WHERE active = true ORDER BY category, name"
        sources = await db.db.fetch_all(query)
        
        info['rss_sources'] = [
            {
                'name': source['name'],
                'category': source['category'],
                'url': source['feed_url']
            }
            for source in sources
        ]
        
        # Categories
        categories = list(set(source['category'] for source in sources))
        info['categories'] = categories
        
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        info['rss_sources'] = []
        info['categories'] = []
        info['error'] = str(e)
    
    return info

async def get_ai_brain_integration_status() -> Dict[str, Any]:
    """Get AI brain integration status and capabilities"""
    
    integration = {
        'status': 'active',
        'capabilities': [
            'Latest marketing trends retrieval',
            'Writing inspiration and context',
            'Campaign insights for email/blog/social',
            'Content research and keyword analysis',
            'Trending topics identification',
            'Best practices compilation'
        ],
        'ai_brain_endpoints': [
            '/integrations/rss/ai-brain/latest-trends',
            '/integrations/rss/ai-brain/writing-context'
        ],
        'integration_methods': {
            'trends_lookup': 'get_latest_trends(category, limit)',
            'writing_context': 'get_writing_inspiration(content_type, topic)',
            'campaign_insights': 'get_campaign_insights(campaign_type)',
            'content_research': 'get_content_research(keywords)'
        }
    }
    
    try:
        # Test integration by getting sample data
        insights_extractor = MarketingInsightsExtractor()
        
        # Test trends retrieval
        trends = await insights_extractor.get_latest_trends(limit=3)
        integration['sample_trends'] = {
            'summary': trends.get('trends_summary', '')[:100] + '...',
            'actionable_count': len(trends.get('actionable_insights', [])),
            'trending_keywords_count': len(trends.get('trending_keywords', []))
        }
        
        # Test writing inspiration
        inspiration = await insights_extractor.get_writing_inspiration('blog', 'seo')
        integration['sample_inspiration'] = {
            'content_ideas_count': len(inspiration.get('content_ideas', [])),
            'key_messages_count': len(inspiration.get('key_messages', [])),
            'trending_angles_count': len(inspiration.get('trending_angles', []))
        }
        
        integration['last_tested'] = datetime.now().isoformat()
        integration['test_status'] = 'passed'
        
    except Exception as e:
        logger.error(f"AI brain integration test failed: {e}")
        integration['status'] = 'error'
        integration['test_status'] = 'failed'
        integration['error'] = str(e)
    
    return integration

def get_configuration_status() -> Dict[str, Any]:
    """Get configuration status for RSS learning system"""
    
    config = {
        'environment_variables': {
            'DATABASE_URL': {
                'present': bool(os.getenv('DATABASE_URL')),
                'required': True,
                'status': 'ok' if os.getenv('DATABASE_URL') else 'missing'
            },
            'OPENAI_API_KEY': {
                'present': bool(os.getenv('OPENAI_API_KEY')),
                'required': False,
                'status': 'ok' if os.getenv('OPENAI_API_KEY') else 'missing (fallback mode)',
                'impact': 'AI analysis will use fallback methods without OpenAI'
            }
        },
        'database_tables': [
            'rss_sources',
            'rss_feed_entries' 
        ],
        'background_services': {
            'rss_processor': {
                'schedule': 'weekly',
                'interval': '604800 seconds (7 days)',
                'auto_start': True
            }
        },
        'ai_features': {
            'content_analysis': 'enabled',
            'insights_extraction': 'enabled',
            'trend_identification': 'enabled',
            'fallback_analysis': 'enabled'
        }
    }
    
    # Overall configuration status
    critical_missing = []
    
    for var, settings in config['environment_variables'].items():
        if settings['required'] and not settings['present']:
            critical_missing.append(var)
    
    if critical_missing:
        config['status'] = 'incomplete'
        config['critical_missing'] = critical_missing
    else:
        config['status'] = 'complete'
    
    return config

async def run_system_diagnostics() -> Dict[str, Any]:
    """Run comprehensive system diagnostics"""
    
    diagnostics = {
        'timestamp': datetime.now().isoformat(),
        'overall_status': 'unknown'
    }
    
    try:
        # Get all status information
        diagnostics['health'] = await get_integration_health()
        diagnostics['system_info'] = await get_system_info()
        diagnostics['ai_brain_integration'] = await get_ai_brain_integration_status()
        diagnostics['configuration'] = get_configuration_status()
        
        # Determine overall status
        health_status = diagnostics['health']['status']
        config_status = diagnostics['configuration']['status'] 
        ai_status = diagnostics['ai_brain_integration']['status']
        
        if all(status in ['healthy', 'complete', 'active'] for status in [health_status, config_status, ai_status]):
            diagnostics['overall_status'] = 'excellent'
        elif health_status == 'error' or config_status == 'incomplete':
            diagnostics['overall_status'] = 'requires_attention'
        else:
            diagnostics['overall_status'] = 'good'
        
        # Summary
        diagnostics['summary'] = {
            'rss_sources': len(diagnostics['system_info'].get('rss_sources', [])),
            'categories': len(diagnostics['system_info'].get('categories', [])),
            'total_items': diagnostics['health']['components']['database']['total_items'],
            'ai_features': 'enabled' if diagnostics['configuration']['environment_variables']['OPENAI_API_KEY']['present'] else 'fallback',
            'background_processing': diagnostics['health']['components']['feed_processor']['running']
        }
        
    except Exception as e:
        logger.error(f"System diagnostics failed: {e}")
        diagnostics['overall_status'] = 'error'
        diagnostics['error'] = str(e)
    
    return diagnostics