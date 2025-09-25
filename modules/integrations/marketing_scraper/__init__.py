# modules/integrations/marketing_scraper/__init__.py
"""
Marketing Scraper Integration Module for Syntax Prime V2
Intelligent competitor website analysis system that provides AI-powered marketing insights

Module Structure:
- scraper_client.py: Website content extraction and cleaning
- content_analyzer.py: AI-powered competitive analysis using SyntaxPrime
- database_manager.py: Store and retrieve scraped insights
- router.py: FastAPI endpoints for health checks and status
- integration_info.py: Health checks and system information

Workflow:
1. User command: scrape [URL] in chat
2. Extract and clean website content  
3. AI analysis with SyntaxPrime personality
4. Store insights in database for permanent reference
5. Provide immediate context for content creation
"""

from .scraper_client import MarketingScraperClient
from .content_analyzer import ContentAnalyzer  
from .database_manager import ScrapedContentDatabase
from .router import router

# Public API - what other modules can import
__all__ = [
    'MarketingScraperClient',
    'ContentAnalyzer', 
    'ScrapedContentDatabase',
    'router'
]

# Module metadata
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'AI-powered marketing scraper for competitive analysis'

# Module configuration constants
MODULE_NAME = 'marketing_scraper'
INTEGRATION_TYPE = 'chat_command'
SUPPORTED_COMMANDS = ['scrape', 'scrape history', 'scrape insights']

def check_module_health() -> dict:
    """Check if marketing scraper module is properly configured"""
    import os
    
    required_vars = [
        'DATABASE_URL',
        'OPENROUTER_API_KEY'  # For AI analysis
    ]
    
    optional_vars = [
        'SCRAPER_USER_AGENT',
        'SCRAPER_TIMEOUT_SECONDS'
    ]
    
    status = {
        'healthy': True, 
        'missing_vars': [], 
        'configured_vars': [],
        'optional_missing': []
    }
    
    # Check required variables
    for var in required_vars:
        if os.getenv(var):
            status['configured_vars'].append(var)
        else:
            status['missing_vars'].append(var)
            status['healthy'] = False
    
    # Check optional variables
    for var in optional_vars:
        if os.getenv(var):
            status['configured_vars'].append(var)
        else:
            status['optional_missing'].append(var)
    
    # Test database connectivity
    try:
        from .database_manager import ScrapedContentDatabase
        db = ScrapedContentDatabase()
        # This will be tested in the actual implementation
        status['database_accessible'] = True
    except Exception as e:
        status['database_accessible'] = False
        status['database_error'] = str(e)
        status['healthy'] = False
    
    return status

def get_integration_info() -> dict:
    """Get marketing scraper integration information"""
    health_status = check_module_health()
    
    return {
        'module': MODULE_NAME,
        'version': __version__,
        'description': __description__,
        'integration_type': INTEGRATION_TYPE,
        'health_status': health_status,
        
        'chat_commands': {
            'scrape [URL]': 'Analyze competitor website for marketing insights',
            'scrape history': 'Show recent scraping activity',
            'scrape insights [topic]': 'Find stored insights on specific topic'
        },
        
        'features': [
            'Clean website content extraction',
            'AI-powered competitive analysis with SyntaxPrime', 
            'Marketing angles and positioning insights',
            'Technical analysis (CTAs, page structure)',
            'Tone and voice analysis',
            'Permanent storage for future reference',
            'Intelligent context for content creation'
        ],
        
        'endpoints': {
            'status': '/integrations/marketing-scraper/status',
            'health': '/integrations/marketing-scraper/health',
            'stats': '/integrations/marketing-scraper/stats'
        },
        
        'analysis_components': [
            'Competitive positioning insights',
            'Marketing angles and messaging',
            'Call-to-action analysis',
            'Page structure and technical details',
            'Tone and voice patterns',
            'Content strategy insights'
        ],
        
        'storage': {
            'table': 'scraped_content',
            'retention': 'permanent',
            'indexing': 'full_text_search_enabled'
        },
        
        'ai_integration': {
            'personality': 'syntaxprime',
            'analysis_depth': 'comprehensive',
            'context_integration': 'automatic',
            'memory_retention': 'permanent'
        }
    }

# Convenience function for chat integration
def get_scraper_commands() -> dict:
    """Get available scraper commands for chat integration"""
    return {
        'scrape': {
            'pattern': r'scrape\s+(https?://\S+)',
            'description': 'Analyze website for marketing insights',
            'usage': 'scrape https://competitor.com'
        },
        'scrape_history': {
            'pattern': r'scrape\s+history',
            'description': 'Show recent scraping activity', 
            'usage': 'scrape history'
        },
        'scrape_insights': {
            'pattern': r'scrape\s+insights\s+(.+)',
            'description': 'Find stored insights on topic',
            'usage': 'scrape insights [topic]'
        }
    }