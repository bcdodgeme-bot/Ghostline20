# modules/integrations/bluesky/integration_info.py
"""
Integration info and health check functions for Bluesky Multi-Account System
These functions are imported by the main app.py for system status reporting
"""

import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def get_integration_info() -> Dict[str, Any]:
    """Get information about the Bluesky multi-account integration"""
    return {
        "name": "Bluesky Multi-Account Social Assistant",
        "version": "2.0.0",
        "description": "5-account AI-powered social media management system with keyword intelligence",
        "accounts_supported": {
            "personal": {
                "handle": "bcdodgeme.bsky.social",
                "personality": "syntaxprime",
                "ai_posting": True,
                "keyword_table": "bcdodge_keywords",
                "keyword_count": 884
            },
            "rose_angel": {
                "handle": "roseandangel.bsky.social", 
                "personality": "professional",
                "ai_posting": False,
                "keyword_table": "roseandangel_keywords",
                "keyword_count": 1451
            },
            "binge_tv": {
                "handle": "tvsignals.bsky.social",
                "personality": "syntaxprime", 
                "ai_posting": True,
                "keyword_table": "tvsignals_keywords",
                "keyword_count": 295
            },
            "meals_feelz": {
                "handle": "mealsnfeelz.bsky.social",
                "personality": "compassionate",
                "ai_posting": False,
                "keyword_table": "mealsnfeelz_keywords", 
                "keyword_count": 312
            },
            "damn_it_carl": {
                "handle": "syntax-ceo.bsky.social",
                "personality": "syntaxprime",
                "ai_posting": True,
                "keyword_table": "damnitcarl_keywords",
                "keyword_count": 402
            }
        },
        "total_keywords": 3344,  # Sum of all keyword counts
        "endpoints": {
            "scan": "/bluesky/scan",
            "opportunities": "/bluesky/opportunities", 
            "approve": "/bluesky/approve",
            "post": "/bluesky/post",
            "accounts_status": "/bluesky/accounts/status",
            "authenticate": "/bluesky/accounts/authenticate",
            "notifications": "/bluesky/notifications",
            "analytics": "/bluesky/analytics/keyword-performance",
            "chat_summary": "/bluesky/chat-summary",
            "health": "/bluesky/health"
        },
        "features": [
            "5-account simultaneous management",
            "Keyword-driven engagement intelligence",
            "AI-powered draft generation (3 personality types)",
            "Approval-first workflow (no auto-posting)",
            "Cross-account opportunity detection", 
            "Real-time vs digest notifications",
            "Per-account learning and analytics",
            "Smart scanning (3.5-hour intervals)",
            "Chat interface integration",
            "Background processing"
        ],
        "personalities": {
            "syntaxprime": "Sarcastic wit with helpful insights (Carl's proven tone)",
            "professional": "Conservative, business-appropriate for nonprofits",
            "compassionate": "Warm, empathetic for sensitive/religious contexts"
        },
        "workflow": "Approval-First AI Social Media Assistant Army",
        "scan_interval": "3.5 hours",
        "max_post_length": 300
    }

def check_module_health() -> Dict[str, Any]:
    """Check the health of the Bluesky multi-account integration"""
    
    # Check environment variables for each account
    account_configs = {
        "personal": {
            "handle": os.getenv("BLUESKY_PERSONAL_HANDLE"),
            "password": os.getenv("BLUESKY_PERSONAL_PASSWORD")
        },
        "rose_angel": {
            "handle": os.getenv("BLUESKY_ROSE_ANGEL_HANDLE"),
            "password": os.getenv("BLUESKY_ROSE_ANGEL_PASSWORD")
        },
        "binge_tv": {
            "handle": os.getenv("BLUESKY_BINGE_TV_HANDLE"),
            "password": os.getenv("BLUESKY_BINGE_TV_PASSWORD")
        },
        "meals_feelz": {
            "handle": os.getenv("BLUESKY_MEALS_FEELZ_HANDLE"),
            "password": os.getenv("BLUESKY_MEALS_FEELZ_PASSWORD")
        },
        "damn_it_carl": {
            "handle": os.getenv("BLUESKY_DAMN_IT_CARL_HANDLE"),
            "password": os.getenv("BLUESKY_DAMN_IT_CARL_PASSWORD")
        }
    }
    
    # Count configured accounts
    configured_accounts = 0
    missing_handles = []
    missing_passwords = []
    
    for account_id, config in account_configs.items():
        has_handle = bool(config["handle"])
        has_password = bool(config["password"])
        
        if has_handle and has_password:
            configured_accounts += 1
        
        if not has_handle:
            missing_handles.append(f"BLUESKY_{account_id.upper()}_HANDLE")
        if not has_password:
            missing_passwords.append(f"BLUESKY_{account_id.upper()}_PASSWORD")
    
    # Check database tables (keyword tables should exist)
    keyword_tables = [
        "bcdodge_keywords",
        "roseandangel_keywords", 
        "tvsignals_keywords",
        "mealsnfeelz_keywords",
        "damnitcarl_keywords"
    ]
    
    # Check if AI dependencies are available
    missing_vars = []
    warnings = []
    
    # Required for AI draft generation
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    # Database connection required for keyword lookup
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        missing_vars.append("DATABASE_URL")
    
    # Collect all missing environment variables
    all_missing_vars = missing_vars + missing_handles + missing_passwords
    
    # Generate warnings for partial configuration
    if 0 < configured_accounts < 5:
        warnings.append(f"Only {configured_accounts}/5 accounts configured")
    
    if missing_handles:
        warnings.append(f"Missing handles: {', '.join(missing_handles)}")
    
    if missing_passwords:
        warnings.append(f"Missing passwords: {', '.join(missing_passwords)}")
    
    # Determine overall health status
    is_healthy = len(all_missing_vars) == 0 and configured_accounts == 5
    
    return {
        "healthy": is_healthy,
        "missing_vars": all_missing_vars,
        "warnings": warnings,
        "configured_accounts": configured_accounts,
        "total_accounts": 5,
        "keyword_tables_expected": keyword_tables,
        "functionality_status": {
            "account_authentication": configured_accounts > 0,
            "keyword_intelligence": bool(database_url),
            "ai_draft_generation": bool(os.getenv("OPENROUTER_API_KEY")),
            "approval_workflow": True,  # Always available
            "notification_system": True,  # Always available
            "chat_integration": True  # Always available
        },
        "service_requirements": {
            "bluesky_api": "App passwords required for each account",
            "database": "PostgreSQL with keyword tables",
            "ai_provider": "OpenRouter API for draft generation",
            "memory": "Conversation system for chat integration"
        },
        "deployment_status": "ready" if is_healthy else "needs_configuration"
    }

def get_account_summary() -> Dict[str, Any]:
    """Get a summary of account configuration status"""
    health_status = check_module_health()
    
    return {
        "configured_accounts": health_status["configured_accounts"],
        "total_accounts": health_status["total_accounts"],
        "configuration_complete": health_status["healthy"],
        "missing_configuration": health_status["missing_vars"],
        "ready_for_deployment": health_status["deployment_status"] == "ready"
    }