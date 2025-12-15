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

# Import singleton getters for core components
from .keyword_expander import get_keyword_expander
from .trends_client import get_google_trends_client
from .keyword_monitor import get_keyword_monitor
from .database_manager import get_trends_database

# Import singleton getters for analysis components
try:
    from .trend_analyzer import get_trend_analyzer
except ImportError:
    get_trend_analyzer = None

try:
    from .opportunity_detector import get_opportunity_detector
except ImportError:
    get_opportunity_detector = None

try:
    from .rss_cross_reference import get_rss_cross_reference
except ImportError:
    get_rss_cross_reference = None

try:
    from .router import router
except ImportError:
    router = None

try:
    from .integration_info import get_integration_info, check_module_health, get_integration_info_manager
except ImportError:
    get_integration_info = None
    check_module_health = None
    get_integration_info_manager = None

# Import db_manager for database operations
from ...core.database import db_manager

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

# Business areas supported (list for backward compatibility)
BUSINESS_AREAS = [
    'amcf',        # Charity/nonprofit/zakat (1,242 keywords → 13,445 expanded)
    'bcdodge',     # Digital marketing/strategy (884 keywords → 9,917 expanded)
    'damnitcarl',  # Cat content/emotional support (402 keywords → 5,172 expanded)
    'mealsnfeelz', # Food donation/pantries (312 keywords → 3,891 expanded)
    'roseandangel', # Marketing consulting (1,451 keywords → 15,229 expanded)
    'tvsignals'    # Streaming/TV shows (295 keywords → 3,820 expanded)
]

# Valid business areas frozenset for validation
VALID_BUSINESS_AREAS = frozenset(BUSINESS_AREAS)

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
    # Singleton getters for core components
    'get_keyword_expander',
    'get_google_trends_client',
    'get_keyword_monitor',
    'get_trends_database',
    
    # Singleton getters for analysis components (conditional)
    'get_trend_analyzer',
    'get_opportunity_detector',
    'get_rss_cross_reference',
    
    # Integration components
    'router',
    'get_integration_info',
    'check_module_health',
    'get_integration_info_manager',
    
    # Configuration
    'MODULE_NAME',
    'BUSINESS_AREAS',
    'VALID_BUSINESS_AREAS',
    'SUPPORTED_COMMANDS',
    'DEFAULT_MONITORING_CONFIG',
    
    # Module functions
    'get_module_status',
    'initialize_module',
    'quick_module_health_check'
]


async def _get_module_status_async() -> Dict[str, Any]:
    """Async implementation of get_module_status"""
    # Check core components
    status = {
        'module_name': MODULE_NAME,
        'version': __version__,
        'components_available': {
            'keyword_expander': get_keyword_expander is not None,
            'trends_client': get_google_trends_client is not None,
            'keyword_monitor': get_keyword_monitor is not None,
            'database_manager': get_trends_database is not None,
            'trend_analyzer': get_trend_analyzer is not None,
            'opportunity_detector': get_opportunity_detector is not None,
            'rss_cross_reference': get_rss_cross_reference is not None,
            'router': router is not None,
            'integration_info': get_integration_info is not None
        },
        'business_areas': BUSINESS_AREAS,
        'supported_commands': SUPPORTED_COMMANDS
    }
    
    # Get database health if available
    try:
        db = get_trends_database()
        health = await db.health_check()
        status['database_health'] = health
    except Exception as e:
        status['database_health'] = {'error': str(e)}
    
    # Get keyword expansion status
    conn = None
    try:
        conn = await db_manager.get_connection()
        
        # Check expanded keywords count
        expanded_count = await conn.fetchval('''
            SELECT COUNT(*) FROM expanded_keywords_for_trends
        ''')
        
        # Check original keywords count
        original_counts = {}
        for area in VALID_BUSINESS_AREAS:
            count = await conn.fetchval(
                f'SELECT COUNT(*) FROM {area}_keywords WHERE is_active = true'
            ) or 0
            original_counts[area] = count
        
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
    finally:
        if conn:
            await db_manager.release_connection(conn)
    
    return status


def get_module_status() -> Dict[str, Any]:
    """Get comprehensive module status and health
    
    Note: This runs async code synchronously. For async contexts,
    use _get_module_status_async() directly.
    """
    import asyncio
    
    try:
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, can't use asyncio.run()
            # Return basic status without async calls
            return {
                'module_name': MODULE_NAME,
                'version': __version__,
                'components_available': {
                    'keyword_expander': get_keyword_expander is not None,
                    'trends_client': get_google_trends_client is not None,
                    'keyword_monitor': get_keyword_monitor is not None,
                    'database_manager': get_trends_database is not None,
                    'trend_analyzer': get_trend_analyzer is not None,
                    'opportunity_detector': get_opportunity_detector is not None,
                    'rss_cross_reference': get_rss_cross_reference is not None,
                    'router': router is not None,
                    'integration_info': get_integration_info is not None
                },
                'business_areas': BUSINESS_AREAS,
                'supported_commands': SUPPORTED_COMMANDS,
                'note': 'Call _get_module_status_async() for full status in async context'
            }
        except RuntimeError:
            # No running event loop, safe to use asyncio.run()
            return asyncio.run(_get_module_status_async())
    except Exception as e:
        return {
            'module_name': MODULE_NAME,
            'version': __version__,
            'error': str(e)
        }


def initialize_module() -> Dict[str, Any]:
    """Initialize the Google Trends module with all components
    
    Uses singleton pattern - components are initialized on first access.
    """
    try:
        # Get singleton instances of core components
        components = {}
        
        if get_keyword_expander:
            components['expander'] = get_keyword_expander()
        
        if get_google_trends_client:
            components['trends_client'] = get_google_trends_client()
        
        if get_keyword_monitor:
            components['monitor'] = get_keyword_monitor()
        
        if get_trends_database:
            components['database'] = get_trends_database()
        
        # Initialize optional components
        if get_trend_analyzer:
            components['analyzer'] = get_trend_analyzer()
        
        if get_opportunity_detector:
            components['opportunity_detector'] = get_opportunity_detector()
            
        if get_rss_cross_reference:
            components['rss_cross_reference'] = get_rss_cross_reference()
        
        logging.info(f"Google Trends module initialized with {len(components)} components")
        
        return {
            'success': True,
            'components': list(components.keys()),
            'module_version': __version__
        }
        
    except Exception as e:
        logging.error(f"Failed to initialize Google Trends module: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def quick_module_health_check() -> Dict[str, Any]:
    """Quick health check for the module (no database calls)
    
    For comprehensive health checks, use check_module_health() from integration_info.
    """
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
    
    # Count available component getters
    component_getters = [
        get_keyword_expander,
        get_google_trends_client,
        get_keyword_monitor,
        get_trends_database,
        get_trend_analyzer,
        get_opportunity_detector,
        get_rss_cross_reference,
        get_integration_info
    ]
    
    available = sum(1 for getter in component_getters if getter is not None)
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
    
    # Check basic health (no database calls)
    health = quick_module_health_check()
    if not health['healthy']:
        logger.warning(f"Google Trends module health issues: {health}")
    else:
        logger.info(f"Google Trends module healthy: {health['components_available']}/{health['total_components']} components available")


# Run initialization
_on_import()
