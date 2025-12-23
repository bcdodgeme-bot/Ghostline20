# modules/integrations/wordpress/integration_info.py
"""
WordPress Multi-Site Integration Info and Health Checks
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_integration_info() -> Dict[str, Any]:
    """Get information about the WordPress multi-site integration"""
    return {
        "name": "WordPress Multi-Site Draft System",
        "version": "1.0.0",
        "description": "Automatic blog draft creation across 5 WordPress sites",
        "sites": {
            "personal": {
                "url": "https://bcdodge.me",
                "business_areas": ["personal", "technology", "ai", "productivity"],
                "description": "Personal blog - Tech, AI, productivity"
            },
            "rose_angel": {
                "url": "https://roseandangel.com",
                "business_areas": ["rose_angel", "nonprofit", "consulting"],
                "description": "Rose & Angel - Nonprofit consulting"
            },
            "binge_tv": {
                "url": "https://tvsignals.com",
                "business_areas": ["binge_tv", "tvsignals", "streaming", "entertainment", "tv"],
                "description": "TV Signals - Streaming and entertainment"
            },
            "meals_feelz": {
                "url": "https://mealsnfeelz.org",
                "business_areas": ["meals_feelz", "food", "charity"],
                "description": "Meals n Feelz - Food programs nonprofit"
            },
            "damn_it_carl": {
                "url": "https://damnitcarl.com",
                "business_areas": ["damn_it_carl", "creative", "burnout"],
                "description": "Damn it Carl - Creative outlet"
            }
        },
        "features": [
            "5-site simultaneous management",
            "Automatic business area to site mapping",
            "Draft creation via REST API",
            "Rank Math focus keyword integration",
            "Edit link in notifications",
            "Application Password authentication"
        ],
        "workflow": "Trend → Blog Generated → WordPress Draft → Telegram notification with edit link"
    }


def check_module_health() -> Dict[str, Any]:
    """Check the health of the WordPress multi-site integration"""
    
    sites_config = {
        "personal": {
            "url_var": "WORDPRESS_PERSONAL_URL",
            "user_var": "WORDPRESS_PERSONAL_USER",
            "password_var": "WORDPRESS_PERSONAL_APP_PASSWORD"
        },
        "rose_angel": {
            "url_var": "WORDPRESS_ROSE_ANGEL_URL",
            "user_var": "WORDPRESS_ROSE_ANGEL_USER",
            "password_var": "WORDPRESS_ROSE_ANGEL_APP_PASSWORD"
        },
        "binge_tv": {
            "url_var": "WORDPRESS_BINGE_TV_URL",
            "user_var": "WORDPRESS_BINGE_TV_USER",
            "password_var": "WORDPRESS_BINGE_TV_APP_PASSWORD"
        },
        "meals_feelz": {
            "url_var": "WORDPRESS_MEALS_FEELZ_URL",
            "user_var": "WORDPRESS_MEALS_FEELZ_USER",
            "password_var": "WORDPRESS_MEALS_FEELZ_APP_PASSWORD"
        },
        "damn_it_carl": {
            "url_var": "WORDPRESS_DAMN_IT_CARL_URL",
            "user_var": "WORDPRESS_DAMN_IT_CARL_USER",
            "password_var": "WORDPRESS_DAMN_IT_CARL_APP_PASSWORD"
        }
    }
    
    configured_sites = 0
    missing_vars = []
    warnings = []
    site_status = {}
    
    for site_id, vars_config in sites_config.items():
        has_url = bool(os.getenv(vars_config["url_var"]))
        has_user = bool(os.getenv(vars_config["user_var"]))
        has_password = bool(os.getenv(vars_config["password_var"]))
        
        site_configured = has_user and has_password
        
        site_status[site_id] = {
            "configured": site_configured,
            "has_url": has_url,
            "has_user": has_user,
            "has_password": has_password
        }
        
        if site_configured:
            configured_sites += 1
        else:
            if not has_user:
                missing_vars.append(vars_config["user_var"])
            if not has_password:
                missing_vars.append(vars_config["password_var"])
    
    if 0 < configured_sites < 5:
        warnings.append(f"Only {configured_sites}/5 sites configured")
    
    is_healthy = configured_sites > 0
    
    return {
        "healthy": is_healthy,
        "missing_vars": missing_vars,
        "warnings": warnings,
        "configured_sites": configured_sites,
        "total_sites": 5,
        "site_status": site_status,
        "functionality_status": {
            "draft_creation": configured_sites > 0,
            "rank_math_integration": True,
            "automatic_site_mapping": True
        },
        "deployment_status": "ready" if is_healthy else "needs_configuration"
    }