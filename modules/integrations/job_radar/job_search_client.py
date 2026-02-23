# modules/integrations/job_radar/job_search_client.py
"""
Job Search Client for Syntax Prime V2
======================================
Multi-API job search aggregator. Queries 3 sources and normalizes results
into a common format for the scoring pipeline.

APIs:
1. JSearch (via RapidAPI) — Google for Jobs aggregator
2. Adzuna — Free tier job search with salary estimates
3. SerpAPI — Google Jobs scraping with structured output

All API keys stored in Railway environment variables:
- JSEARCH_API_KEY (RapidAPI key)
- ADZUNA_APP_ID
- ADZUNA_API_KEY
- SERPAPI_API_KEY

Created: 2026-02-23
"""

import os
import logging
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from .profile_config import SEARCH_QUERIES, MAX_RESULTS_PER_QUERY

logger = logging.getLogger(__name__)


class JobSearchClient:
    """
    Aggregates job listings from multiple APIs into normalized format.
    """

    def __init__(self):
        # API credentials from environment
        self.jsearch_key = os.getenv('JSEARCH_API_KEY')
        self.adzuna_app_id = os.getenv('ADZUNA_APP_ID')
        self.adzuna_key = os.getenv('ADZUNA_API_KEY')
        self.serpapi_key = os.getenv('SERPAPI_API_KEY')

        # Track which APIs are configured
        self.available_apis = []
        if self.jsearch_key:
            self.available_apis.append('jsearch')
        if self.adzuna_app_id and self.adzuna_key:
            self.available_apis.append('adzuna')
        if self.serpapi_key:
            self.available_apis.append('serpapi')

        logger.info(f"🔍 JobSearchClient initialized. Available APIs: {self.available_apis}")

    def get_status(self) -> Dict[str, Any]:
        """Return configuration status for health checks"""
        return {
            "available_apis": self.available_apis,
            "jsearch_configured": bool(self.jsearch_key),
            "adzuna_configured": bool(self.adzuna_app_id and self.adzuna_key),
            "serpapi_configured": bool(self.serpapi_key),
            "search_queries_count": len(SEARCH_QUERIES),
        }

    # =========================================================================
    # MAIN SEARCH ORCHESTRATOR
    # =========================================================================

    async def search_all(
        self,
        queries: Optional[List[str]] = None,
        max_per_query: int = MAX_RESULTS_PER_QUERY
    ) -> List[Dict[str, Any]]:
        """
        Run all configured APIs with all search queries.
        Returns normalized, deduplicated list of job listings.

        Args:
            queries: Override default search queries
            max_per_query: Max results per API per query

        Returns:
            List of normalized job dicts
        """
        queries = queries or SEARCH_QUERIES
        all_results = []
        errors = []

        async with aiohttp.ClientSession() as session:
            for query in queries:
                # Run available APIs concurrently for each query
                tasks = []

                if 'jsearch' in self.available_apis:
                    tasks.append(self._search_jsearch(session, query, max_per_query))
                if 'adzuna' in self.available_apis:
                    tasks.append(self._search_adzuna(session, query, max_per_query))
                if 'serpapi' in self.available_apis:
                    tasks.append(self._search_serpapi(session, query, max_per_query))

                if not tasks:
                    logger.warning("No job search APIs configured!")
                    return []

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        errors.append(str(result))
                        logger.error(f"API error for query '{query}': {result}")
                    elif isinstance(result, list):
                        all_results.extend(result)

                # Brief pause between queries to respect rate limits
                await asyncio.sleep(0.5)

        if errors:
            logger.warning(f"Search completed with {len(errors)} errors")

        logger.info(f"🔍 Total raw results: {len(all_results)} from {len(queries)} queries")
        return all_results

    # =========================================================================
    # JSEARCH (RapidAPI — Google for Jobs)
    # =========================================================================

    async def _search_jsearch(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_results: int
    ) -> List[Dict[str, Any]]:
        """Query JSearch API and return normalized results"""
        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "x-rapidapi-key": self.jsearch_key,
            "x-rapidapi-host": "jsearch.p.rapidapi.com"
        }
        params = {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "date_posted": "week",  # Only recent listings
            "remote_jobs_only": "true",
        }

        try:
            async with session.get(url, headers=headers, params=params, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"JSearch API error: {resp.status}")
                    return []

                data = await resp.json()
                jobs = data.get('data', [])

                return [self._normalize_jsearch(job) for job in jobs[:max_results]]

        except asyncio.TimeoutError:
            logger.error("JSearch API timeout")
            return []
        except Exception as e:
            logger.error(f"JSearch API error: {e}")
            return []

    def _normalize_jsearch(self, job: Dict) -> Dict[str, Any]:
        """Normalize JSearch result to common format"""
        # Parse salary
        salary_min = None
        salary_max = None
        if job.get('job_min_salary'):
            salary_min = float(job['job_min_salary'])
        if job.get('job_max_salary'):
            salary_max = float(job['job_max_salary'])

        # Parse posted date
        posted_at = None
        if job.get('job_posted_at_datetime_utc'):
            try:
                posted_at = datetime.fromisoformat(
                    job['job_posted_at_datetime_utc'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass

        return {
            "source_api": "jsearch",
            "source_job_id": job.get('job_id'),
            "title": job.get('job_title', 'Unknown'),
            "company": job.get('employer_name', 'Unknown'),
            "location": self._build_location(
                job.get('job_city'), job.get('job_state'),
                job.get('job_country'), job.get('job_is_remote')
            ),
            "description": job.get('job_description', ''),
            "employment_type": job.get('job_employment_type'),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "apply_url": job.get('job_apply_link'),
            "job_posted_at": posted_at,
            "company_logo_url": job.get('employer_logo'),
            "company_website": job.get('employer_website'),
            "is_remote": job.get('job_is_remote', False),
            "raw_api_response": job,
        }

    # =========================================================================
    # ADZUNA
    # =========================================================================

    async def _search_adzuna(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_results: int
    ) -> List[Dict[str, Any]]:
        """Query Adzuna API and return normalized results"""
        url = f"https://api.adzuna.com/v1/api/jobs/us/search/1"
        params = {
            "app_id": self.adzuna_app_id,
            "app_key": self.adzuna_key,
            "results_per_page": min(max_results, 20),
            "what": query.replace(" remote", ""),  # Adzuna handles remote differently
            "where": "remote",
            "max_days_old": 7,
            "sort_by": "relevance",
            "content-type": "application/json",
        }

        try:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"Adzuna API error: {resp.status}")
                    return []

                data = await resp.json()
                jobs = data.get('results', [])

                return [self._normalize_adzuna(job) for job in jobs[:max_results]]

        except asyncio.TimeoutError:
            logger.error("Adzuna API timeout")
            return []
        except Exception as e:
            logger.error(f"Adzuna API error: {e}")
            return []

    def _normalize_adzuna(self, job: Dict) -> Dict[str, Any]:
        """Normalize Adzuna result to common format"""
        salary_min = job.get('salary_min')
        salary_max = job.get('salary_max')

        posted_at = None
        if job.get('created'):
            try:
                posted_at = datetime.fromisoformat(job['created'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        location = job.get('location', {})
        location_str = location.get('display_name', '') if isinstance(location, dict) else str(location)

        return {
            "source_api": "adzuna",
            "source_job_id": str(job.get('id', '')),
            "title": job.get('title', 'Unknown'),
            "company": job.get('company', {}).get('display_name', 'Unknown') if isinstance(job.get('company'), dict) else str(job.get('company', 'Unknown')),
            "location": location_str,
            "description": job.get('description', ''),
            "employment_type": job.get('contract_time', '').upper() if job.get('contract_time') else None,
            "salary_min": float(salary_min) if salary_min else None,
            "salary_max": float(salary_max) if salary_max else None,
            "apply_url": job.get('redirect_url'),
            "job_posted_at": posted_at,
            "company_logo_url": None,
            "company_website": None,
            "is_remote": 'remote' in location_str.lower() if location_str else False,
            "raw_api_response": job,
        }

    # =========================================================================
    # SERPAPI (Google Jobs)
    # =========================================================================

    async def _search_serpapi(
        self,
        session: aiohttp.ClientSession,
        query: str,
        max_results: int
    ) -> List[Dict[str, Any]]:
        """Query SerpAPI Google Jobs and return normalized results"""
        url = "https://serpapi.com/search"
        params = {
            "engine": "google_jobs",
            "q": query,
            "hl": "en",
            "gl": "us",
            "api_key": self.serpapi_key,
        }

        try:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"SerpAPI error: {resp.status}")
                    return []

                data = await resp.json()
                jobs = data.get('jobs_results', [])

                return [self._normalize_serpapi(job) for job in jobs[:max_results]]

        except asyncio.TimeoutError:
            logger.error("SerpAPI timeout")
            return []
        except Exception as e:
            logger.error(f"SerpAPI error: {e}")
            return []

    def _normalize_serpapi(self, job: Dict) -> Dict[str, Any]:
        """Normalize SerpAPI Google Jobs result to common format"""
        # SerpAPI doesn't always give structured salary
        extensions = job.get('detected_extensions', {})

        # Check for remote
        is_remote = extensions.get('work_from_home', False)

        return {
            "source_api": "serpapi",
            "source_job_id": job.get('job_id'),
            "title": job.get('title', 'Unknown'),
            "company": job.get('company_name', 'Unknown'),
            "location": job.get('location', ''),
            "description": job.get('description', ''),
            "employment_type": extensions.get('schedule_type'),
            "salary_min": None,  # SerpAPI rarely provides structured salary
            "salary_max": None,
            "apply_url": job.get('share_link'),
            "job_posted_at": None,  # Would need to parse "X days ago"
            "company_logo_url": job.get('thumbnail'),
            "company_website": None,
            "is_remote": is_remote,
            "raw_api_response": job,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _build_location(
        city: Optional[str],
        state: Optional[str],
        country: Optional[str],
        is_remote: Optional[bool]
    ) -> str:
        """Build location string from components"""
        parts = []
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if country and country != "US":
            parts.append(country)
        
        location = ", ".join(parts) if parts else ""
        
        if is_remote:
            location = f"Remote{' — ' + location if location else ''}"
        
        return location or "Unknown"


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[JobSearchClient] = None


def get_search_client() -> JobSearchClient:
    """Get singleton JobSearchClient instance"""
    global _instance
    if _instance is None:
        _instance = JobSearchClient()
    return _instance
