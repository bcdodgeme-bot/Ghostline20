#!/usr/bin/env python3
"""
Google Trends Integration Module for Syntax Prime V2
Intelligent Google Trends monitoring system with keyword expansion and low-threshold alerts

Module Structure:
- keyword_expander.py: Smart keyword expansion (4,586 → 51,474 terms)
- trends_client.py: Google Trends API integration with rate limiting
- keyword_monitor.py: Complete monitoring workflow orchestration
- database_manager.py: Trend data storage and retrieval
- trend_analyzer.py: Advanced trend analysis and pattern detection
- opportunity_detector.py: Content creation opportunity identification
- rss_cross_reference.py: Cross-system intelligence with RSS insights
- router.py: FastAPI endpoints for chat integration
- integration_info.py: Health checks and system information

Key Features:
- 11.2x keyword expansion for comprehensive coverage
- Low threshold alerts (learned from TV signals missing events)
- Smart rate limiting (45% under Google's limits)
- User feedback training system (good/bad match)
- Cross-system integration with RSS learning
- Real-time chat commands and status monitoring
"""

import os
import logging
from typing import Dict, Any, Optional

# Import core components
from .keyword_expander import KeywordExpander
from .trends_client import GoogleTrendsClient  
from .keyword_monitor import KeywordMonitor
from .database_manager import TrendsDatabase

# Import analysis components (will be available after building)
try:
    from .trend_analyzer import TrendAnalyzer
except ImportError:
    TrendAnalyzer = None

try:
    from .opportunity_detector import OpportunityDetector
except ImportError:
    OpportunityDetector = None

try:
    from .rss_cross_reference import RSSCrossReference
except ImportError:
    RSSCrossReference = None

try:
    from .router import router
except ImportError:
    router = None

try:
    from .integration_info import get_integration_info, check_module_health
except ImportError:
    get_integration_info = None
    check_module_health = None

# Module metadata
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'Google Trends monitoring with smart keyword expansion and low-threshold alerts'

# Module configuration
MODULE_NAME = 'google_trends'
INTEGRATION_TYPE = 'trend_monitoring'
SUPPORTED_COMMANDS = [
    'trends status',
    'trends [business_area]', 
    'trends rising',
    'trends opportunities',
    'trends compare [keyword1] [keyword2]',
    'trends history [keyword]'
]

# Business areas supported
BUSINESS_AREAS = [
    'amcf',        # Charity/nonprofit/zakat (1,242 keywords → 13,445 expanded)
    'bcdodge',     # Digital marketing/strategy (884 keywords → 9,917 expanded)  
    'damnitcarl',  # Cat content/emotional support (402 keywords → 5,172 expanded)
    'mealsnfeelz', # Food donation/pantries (312 keywords → 3,891 expanded)
    'roseandangel', # Marketing consulting (1,451 keywords → 15,229 expanded)
    'tvsignals'    # Streaming/TV shows (295 keywords → 3,820 expanded)
]

# Configuration constants
DEFAULT_MONITORING_CONFIG = {
    'keywords_per_area': 50,
    'monitoring_frequency': '3x_daily',  # morning, noon, evening
    'alert_thresholds': {
        'rising': 15,      # Score increase of 15+ points
        'breakout': 25,    # Sudden spike of 25+ points  
        'stable_high': 40, # Sustained score of 40+
        'momentum': 20     # Any score of 20+ (very low threshold)
    },
    'rate_limiting': {
        'request_delay': 3.0,        # 3 seconds between requests
        'daily_limit': 800,          # Conservative daily API limit
        'safety_margin': 0.45        # Stay 45% under limits
    }
}

# Public API - what other modules can import
__all__ = [
    # Core components
    'KeywordExpander',
    'GoogleTrendsClient', 
    'KeywordMonitor',
    'TrendsDatabase',
    
    # Analysis components (conditional)
    'TrendAnalyzer',
    'OpportunityDetector', 
    'RSSCrossReference',
    
    # Integration components
    'router',
    'get_integration_info',
    'check_module_health',
    
    # Configuration
    'MODULE_NAME',
    'BUSINESS_AREAS',
    'SUPPORTED_COMMANDS',
    'DEFAULT_MONITORING_CONFIG'
]

def get_module_status() -> Dict[str, Any]:
    """Get comprehensive module status and health"""
    import asyncio
    
    async def _get_status():
        database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
        
        # Check core components
        status = {
            'module_name': MODULE_NAME,
            'version': __version__,
            'components_available': {
                'keyword_expander': True,
                'trends_client': True,
                'keyword_monitor': True,
                'database_manager': True,
                'trend_analyzer': TrendAnalyzer is not None,
                'opportunity_detector': OpportunityDetector is not None,
                'rss_cross_reference': RSSCrossReference is not None,
                'router': router is not None,
                'integration_info': get_integration_info is not None
            },
            'business_areas': BUSINESS_AREAS,
            'supported_commands': SUPPORTED_COMMANDS
        }
        
        # Get database health if available
        try:
            db = TrendsDatabase(database_url)
            health = await db.health_check()
            status['database_health'] = health
        except Exception as e:
            status['database_health'] = {'error': str(e)}
        
        # Get keyword expansion status
        try:
            import asyncpg
            conn = await asyncpg.connect(database_url)
            
            # Check expanded keywords count
            expanded_count = await conn.fetchval('''
                SELECT COUNT(*) FROM expanded_keywords_for_trends
            ''')
            
            # Check original keywords count
            original_counts = {}
            for area in BUSINESS_AREAS:
                count = await conn.fetchval(f'''
                    SELECT COUNT(*) FROM {area}_keywords WHERE is_active = true
                ''')
                original_counts[area] = count
            
            await conn.close()
            
            total_original = sum(original_counts.values())
            expansion_ratio = expanded_count / total_original if total_original > 0 else 0
            
            status['keyword_status'] = {
                'original_keywords': total_original,
                'expanded_keywords': expanded_count,
                'expansion_ratio': round(expansion_ratio, 1),
                'by_business_area': original_counts
            }
            
        except Exception as e:
            status['keyword_status'] = {'error': str(e)}
        
        return status
    
    try:
        return asyncio.run(_get_status())
    except Exception as e:
        return {
            'module_name': MODULE_NAME,
            'version': __version__,
            'error': str(e)
        }

def initialize_module(database_url: Optional[str] = None) -> Dict[str, Any]:
    """Initialize the Google Trends module with all components"""
    if database_url is None:
        database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
    
    try:
        # Initialize core components
        components = {
            'expander': KeywordExpander(database_url),
            'trends_client': GoogleTrendsClient(database_url),
            'monitor': KeywordMonitor(database_url),
            'database': TrendsDatabase(database_url)
        }
        
        # Initialize optional components
        if TrendAnalyzer:
            components['analyzer'] = TrendAnalyzer(database_url)
        
        if OpportunityDetector:
            components['opportunity_detector'] = OpportunityDetector(database_url)
            
        if RSSCrossReference:
            components['rss_cross_reference'] = RSSCrossReference(database_url)
        
        logging.info(f"Google Trends module initialized with {len(components)} components")
        
        return {
            'success': True,
            'components': list(components.keys()),
            'database_url': database_url,
            'module_version': __version__
        }
        
    except Exception as e:
        logging.error(f"Failed to initialize Google Trends module: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def check_module_health() -> Dict[str, Any]:
    """Quick health check for the module"""
    required_env_vars = ['DATABASE_URL']
    optional_env_vars = ['OPENROUTER_API_KEY']  # For future AI analysis
    
    status = {
        'healthy': True,
        'missing_required': [],
        'missing_optional': [],
        'components_available': 0,
        'total_components': 8
    }
    
    # Check environment variables
    for var in required_env_vars:
        if not os.getenv(var):
            status['missing_required'].append(var)
            status['healthy'] = False
    
    for var in optional_env_vars:
        if not os.getenv(var):
            status['missing_optional'].append(var)
    
    # Count available components
    components = [
        KeywordExpander, GoogleTrendsClient, KeywordMonitor, TrendsDatabase,
        TrendAnalyzer, OpportunityDetector, RSSCrossReference, 
        (router, get_integration_info)
    ]
    
    available = sum(1 for comp in components if comp is not None)
    status['components_available'] = available
    
    if available < 4:  # Core components required
        status['healthy'] = False
    
    return status

# Module initialization on import
def _on_import():
    """Run when module is imported"""
    logger = logging.getLogger(__name__)
    
    # Log module import
    logger.info(f"Google Trends module v{__version__} imported")
    
    # Check basic health
    health = check_module_health()
    if not health['healthy']:
        logger.warning(f"Google Trends module health issues: {health}")
    else:
        logger.info(f"Google Trends module healthy: {health['components_available']}/{health['total_components']} components available")

# Run initialization
_on_import()