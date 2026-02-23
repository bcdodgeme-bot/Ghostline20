# modules/integrations/job_radar/__init__.py
"""
Job Radar Integration Module for Syntax Prime V2
=================================================
AI-powered job search that matches listings against Carl's complete professional
identity — personality assessments, hard filters, halal compliance, culture fit.

Module Structure:
- profile_config.py: Complete candidate profile (assessments, resume, filters)
- job_search_client.py: Multi-API job search (JSearch, Adzuna, SerpAPI)
- job_scorer.py: Claude API scoring pipeline
- company_reviewer.py: Company reputation lookup
- halal_filter.py: Islamic income compliance checking
- database_manager.py: Job storage, dedup, tracking
- router.py: FastAPI endpoints
- integration_info.py: Health checks and system information

Workflow:
1. Background task runs every 4 hours
2. Search 3 APIs with configured queries
3. Deduplicate against previously seen jobs
4. Pre-filter (instant reject on obvious mismatches)
5. AI score remaining jobs against full profile
6. Store results, notify on high-scoring matches
7. Bridge top matches to knowledge_entries for chat access

Created: 2026-02-23
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Module metadata
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'AI-powered job search with personality-based matching'

MODULE_NAME = 'job_radar'
INTEGRATION_TYPE = 'background_scan'


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

_search_client: Optional['JobSearchClient'] = None
_job_scorer: Optional['JobScorer'] = None
_company_reviewer: Optional['CompanyReviewer'] = None
_halal_filter: Optional['HalalFilter'] = None
_db_manager: Optional['JobRadarDatabaseManager'] = None


def get_search_client() -> 'JobSearchClient':
    """Get singleton JobSearchClient instance"""
    global _search_client
    if _search_client is None:
        from .job_search_client import JobSearchClient
        _search_client = JobSearchClient()
    return _search_client


def get_job_scorer() -> 'JobScorer':
    """Get singleton JobScorer instance"""
    global _job_scorer
    if _job_scorer is None:
        from .job_scorer import JobScorer
        _job_scorer = JobScorer()
    return _job_scorer


def get_company_reviewer() -> 'CompanyReviewer':
    """Get singleton CompanyReviewer instance"""
    global _company_reviewer
    if _company_reviewer is None:
        from .company_reviewer import CompanyReviewer
        _company_reviewer = CompanyReviewer()
    return _company_reviewer


def get_halal_filter() -> 'HalalFilter':
    """Get singleton HalalFilter instance"""
    global _halal_filter
    if _halal_filter is None:
        from .halal_filter import HalalFilter
        _halal_filter = HalalFilter()
    return _halal_filter


def get_job_radar_db() -> 'JobRadarDatabaseManager':
    """Get singleton JobRadarDatabaseManager instance"""
    global _db_manager
    if _db_manager is None:
        from .database_manager import JobRadarDatabaseManager
        _db_manager = JobRadarDatabaseManager()
    return _db_manager


# =============================================================================
# PUBLIC API
# =============================================================================

from .router import router
from .integration_info import get_integration_info, check_module_health

__all__ = [
    # Router
    'router',
    # Singleton getters
    'get_search_client',
    'get_job_scorer',
    'get_company_reviewer',
    'get_halal_filter',
    'get_job_radar_db',
    # Module utilities
    'get_integration_info',
    'check_module_health',
]
