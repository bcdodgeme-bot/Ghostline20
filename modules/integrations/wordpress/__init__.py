# modules/integrations/wordpress/__init__.py
"""
WordPress Multi-Site Integration
Creates drafts across 5 WordPress sites based on business area
"""

from .wordpress_client import (
    WordPressMultiClient,
    get_wordpress_client,
    create_wordpress_draft
)

__all__ = [
    'WordPressMultiClient',
    'get_wordpress_client',
    'create_wordpress_draft'
]