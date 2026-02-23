# modules/integrations/job_radar/integration_info.py
"""
Job Radar Integration Info - Health Monitoring & Documentation
Follows established Syntax Prime V2 patterns for module health.

Created: 2026-02-23
"""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def get_integration_info() -> Dict[str, Any]:
    """
    Get Job Radar integration module information.

    Returns:
        Module metadata and configuration
    """
    return {
        "name": "Job Radar - AI-Powered Job Search",
        "version": "1.0.0",
        "description": (
            "Automated job search that scores listings against personality "
            "assessments (CliftonStrengths, HIGH5, MBTI), halal compliance, "
            "culture fit, and professional experience"
        ),
        "author": "Syntax Prime V2",
        "created": "2026-02-23",

        "data_sources": {
            "jsearch": {
                "description": "Google for Jobs aggregator via RapidAPI",
                "env_var": "JSEARCH_API_KEY",
            },
            "adzuna": {
                "description": "Free tier job search with salary estimates",
                "env_vars": ["ADZUNA_APP_ID", "ADZUNA_API_KEY"],
            },
            "serpapi": {
                "description": "Google Jobs scraping + company rating lookup",
                "env_var": "SERPAPI_API_KEY",
            },
        },

        "scoring_dimensions": {
            "skills_match": {"weight": 0.25, "description": "Skills alignment"},
            "culture_fit": {"weight": 0.25, "description": "Work style + values"},
            "seniority_alignment": {"weight": 0.15, "description": "Level match"},
            "strengths_utilization": {"weight": 0.15, "description": "Assessment fit"},
            "growth_potential": {"weight": 0.10, "description": "Room to build"},
            "company_reputation": {"weight": 0.10, "description": "Rating + reviews"},
        },

        "notification_thresholds": {
            "immediate_push": "Score 80+ → Telegram notification NOW",
            "daily_digest": "Score 60-79 → included in daily digest",
            "log_only": "Score 40-59 → stored but no notification",
            "discard": "Score <40 → not stored",
        },

        "hard_filters": {
            "remote": "Fully remote required",
            "salary": "$95K+ base",
            "halal": "Strict Islamic compliance",
            "rating": "3.5+ company rating",
            "benefits": "401k, health, PTO, sick leave",
        },

        "database_tables": [
            "job_radar_listings",
            "job_radar_scan_log",
        ],

        "endpoints": {
            "scan": "POST /job-radar/scan (manual trigger)",
            "matches": "GET /job-radar/matches",
            "stats": "GET /job-radar/stats",
            "job_detail": "GET /job-radar/jobs/{job_id}",
            "respond": "POST /job-radar/jobs/{job_id}/respond",
            "health": "GET /job-radar/health",
        },

        "background_task": {
            "interval": "4 hours",
            "startup_delay": "25 minutes",
            "queries_per_scan": "16 search queries across 3 APIs",
        },
    }


async def check_module_health() -> Dict[str, Any]:
    """
    Perform health check on all Job Radar components.

    Returns:
        Health status for each component
    """
    health = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "healthy",
        "components": {},
    }

    # Check search client
    try:
        from .job_search_client import get_search_client
        client = get_search_client()
        status = client.get_status()
        health["components"]["search_client"] = {
            "status": "healthy" if status['available_apis'] else "degraded",
            "available_apis": status['available_apis'],
        }
        if not status['available_apis']:
            health["overall_status"] = "degraded"
    except Exception as e:
        health["components"]["search_client"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "unhealthy"

    # Check job scorer
    try:
        from .job_scorer import get_job_scorer
        scorer = get_job_scorer()
        status = scorer.get_status()
        health["components"]["job_scorer"] = {
            "status": "healthy" if status['api_configured'] else "degraded",
            "model": status['model'],
        }
        if not status['api_configured']:
            health["overall_status"] = "degraded"
    except Exception as e:
        health["components"]["job_scorer"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "unhealthy"

    # Check company reviewer
    try:
        from .company_reviewer import get_company_reviewer
        reviewer = get_company_reviewer()
        status = reviewer.get_status()
        health["components"]["company_reviewer"] = {
            "status": "healthy" if status['serpapi_configured'] else "degraded",
        }
    except Exception as e:
        health["components"]["company_reviewer"] = {"status": "unhealthy", "error": str(e)}

    # Check database tables
    try:
        from .database_manager import get_job_radar_db
        db = get_job_radar_db()
        stats = await db.get_scan_statistics()
        health["components"]["database"] = {
            "status": "healthy",
            "total_jobs": stats.get('total_jobs', 0),
            "strong_matches": stats.get('strong_matches', 0),
        }
    except Exception as e:
        health["components"]["database"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "unhealthy"

    return health
