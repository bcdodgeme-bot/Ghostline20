# modules/integrations/google_workspace/__init__.py
"""
Google Workspace Integration for Syntax Prime V2
Business Intelligence & Content Strategy Engine

This module provides comprehensive Google Workspace integration:
- Analytics: Full user journey analysis and audience insights
- Search Console: Keyword opportunity detection (PRIMARY FOCUS)
- Drive: Document creation with rich formatting
- OAuth: Railway-compatible device flow authentication

Integration Philosophy:
- Uses existing keyword tables (bcdodge_keywords, etc.)
- Adds to expanded_keywords_for_trends for Google Trends integration
- Keyword opportunity workflow: Search Console → User decision → Site tables → Expansion
- Privacy-first approach with minimal data retention
"""

# Module metadata
__version__ = "2.0.0"
__description__ = "Google Workspace integration with keyword intelligence"
__author__ = "Syntax Prime V2"

# Module configuration
MODULE_NAME = 'google_workspace'
INTEGRATION_TYPE = 'business_intelligence'

# Supported sites (from V1 configuration)
SUPPORTED_SITES = {
    'bcdodge': {
        'display_name': 'BCDodge-me',
        'analytics_view_id': '470408310',
        'search_console_url': 'https://bcdodge.me',
        'keyword_table': 'bcdodge_keywords',
        'aliases': ['bcdodge', 'dodge', 'my site']
    },
    'rose_angel': {
        'display_name': 'Rose and Angel',
        'analytics_view_id': '481814743',
        'search_console_url': 'https://roseandangel.com',
        'keyword_table': 'roseandangel_keywords',
        'aliases': ['rose', 'angel']
    },
    'meals_feelz': {
        'display_name': 'Meals N Feelz',
        'analytics_view_id': '486327048',
        'search_console_url': 'https://mealsnfeelz.org',
        'keyword_table': 'mealsnfeelz_keywords',
        'aliases': ['meals', 'feelz']
    },
    'tv_signals': {
        'display_name': 'TV Signals',
        'analytics_view_id': '488602505',
        'search_console_url': 'https://tvsignals.com',
        'keyword_table': 'tvsignals_keywords',
        'aliases': ['signals', 'tv', 'tv signals']
    },
    'damn_it_carl': {
        'display_name': 'Damn It Carl',
        'analytics_view_id': '489873151',
        'search_console_url': 'https://damnitcarl.com',
        'keyword_table': 'damnitcarl_keywords',
        'aliases': ['damnitcarl', 'carl']
    }
}

# OAuth scopes required for Google Workspace access
OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/analytics.readonly',
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

# Processing configuration
POLL_INTERVAL_SECONDS = 7200  # 2 hours (not every 3 minutes like V1!)
MAX_KEYWORD_OPPORTUNITIES_PER_SITE = 50  # Limit opportunities to prevent overwhelm
KEYWORD_OPPORTUNITY_EXPIRY_DAYS = 30  # How long opportunities stay active

# Import router and functions AFTER all constants are defined
# This prevents circular import errors
from .router import router
from .integration_info import get_integration_info, check_module_health

# Export public API
__all__ = [
    'router',
    'get_integration_info',
    'check_module_health',
    'SUPPORTED_SITES',
    'OAUTH_SCOPES',
    'MODULE_NAME'
]
