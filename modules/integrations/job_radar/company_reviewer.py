# modules/integrations/job_radar/company_reviewer.py
"""
Company Reviewer for Syntax Prime V2
=====================================
Looks up company reputation scores from review platforms.

Strategy:
1. Check cached ratings first (avoid redundant lookups)
2. Use Google search to find Glassdoor/Indeed/Comparably ratings
3. Cache results in job_radar_listings for future lookups

Since Glassdoor doesn't have a free public API, we rely on:
- SerpAPI to scrape Google search results for ratings
- Cached data from previous lookups
- Manual overrides for known companies

Created: 2026-02-23
"""

import os
import logging
import aiohttp
import asyncio
import re
from typing import Dict, Any, Optional, Tuple

from .profile_config import HARD_FILTERS

logger = logging.getLogger(__name__)

# Minimum rating to pass (from hard filters)
MIN_RATING = HARD_FILTERS['min_company_rating']


class CompanyReviewer:
    """
    Looks up company reputation from review platforms.
    Caches results to avoid redundant API calls.
    """

    def __init__(self):
        self.serpapi_key = os.getenv('SERPAPI_API_KEY')
        self._cache: Dict[str, Dict[str, Any]] = {}  # In-memory cache

    def get_status(self) -> Dict[str, Any]:
        """Status for health checks"""
        return {
            "serpapi_configured": bool(self.serpapi_key),
            "cached_companies": len(self._cache),
        }

    # =========================================================================
    # MAIN LOOKUP
    # =========================================================================

    async def get_company_rating(
        self,
        company_name: str
    ) -> Dict[str, Any]:
        """
        Get company rating from available sources.

        Args:
            company_name: Company name to look up

        Returns:
            Dict with:
                rating: float or None
                rating_source: str
                review_count: int or None
                passes_threshold: bool
                details: dict with additional info
        """
        normalized = company_name.lower().strip()

        # Check cache first
        if normalized in self._cache:
            return self._cache[normalized]

        # Check known companies
        known = self._check_known_companies(normalized)
        if known:
            self._cache[normalized] = known
            return known

        # Try SerpAPI Google search for ratings
        if self.serpapi_key:
            result = await self._search_company_rating(company_name)
            if result and result.get('rating'):
                self._cache[normalized] = result
                return result

        # No data available — default to neutral (don't block)
        result = {
            "rating": None,
            "rating_source": "unknown",
            "review_count": None,
            "passes_threshold": True,  # Don't block on missing data
            "details": {"note": "No rating data found — manual review recommended"},
        }
        self._cache[normalized] = result
        return result

    # =========================================================================
    # SERPAPI SEARCH
    # =========================================================================

    async def _search_company_rating(
        self,
        company_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search Google via SerpAPI for company ratings.
        Looks for Glassdoor/Indeed rating in search results.
        """
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": f"{company_name} glassdoor rating",
            "api_key": self.serpapi_key,
            "num": 5,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()

            # Try to extract rating from knowledge graph
            knowledge = data.get('knowledge_graph', {})
            if knowledge:
                rating = self._extract_rating_from_knowledge(knowledge)
                if rating:
                    return rating

            # Try to extract from organic results
            organic = data.get('organic_results', [])
            for result in organic[:5]:
                rating = self._extract_rating_from_snippet(result)
                if rating:
                    return rating

            return None

        except Exception as e:
            logger.error(f"Company rating search error: {e}")
            return None

    def _extract_rating_from_knowledge(
        self,
        knowledge: Dict
    ) -> Optional[Dict[str, Any]]:
        """Extract rating from Google Knowledge Graph"""
        rating = knowledge.get('rating')
        if rating and isinstance(rating, (int, float)):
            review_count = knowledge.get('review_count')
            return {
                "rating": float(rating),
                "rating_source": "google_knowledge_graph",
                "review_count": review_count,
                "passes_threshold": float(rating) >= MIN_RATING,
                "details": {"source": "Google Knowledge Graph"},
            }
        return None

    def _extract_rating_from_snippet(
        self,
        result: Dict
    ) -> Optional[Dict[str, Any]]:
        """Extract rating from search result snippet"""
        snippet = result.get('snippet', '')
        title = result.get('title', '')
        link = result.get('link', '')

        # Pattern: "X.X out of 5" or "X.X/5" or "Rating: X.X"
        patterns = [
            r'(\d\.\d)\s*(?:out of|\/)\s*5',
            r'[Rr]ating[:\s]+(\d\.\d)',
            r'(\d\.\d)\s*stars?',
        ]

        text = f"{title} {snippet}"
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                rating = float(match.group(1))
                if 1.0 <= rating <= 5.0:  # Sanity check
                    source = "glassdoor" if "glassdoor" in link.lower() else \
                             "indeed" if "indeed" in link.lower() else \
                             "comparably" if "comparably" in link.lower() else \
                             "web_search"

                    return {
                        "rating": rating,
                        "rating_source": source,
                        "review_count": None,
                        "passes_threshold": rating >= MIN_RATING,
                        "details": {
                            "source_url": link,
                            "extracted_from": "search_snippet"
                        },
                    }

        return None

    # =========================================================================
    # KNOWN COMPANIES
    # =========================================================================

    # Curated list of companies with known ratings
    # Avoids wasting API calls on major companies
    KNOWN_RATINGS = {
        "google": (4.3, "glassdoor"),
        "microsoft": (4.2, "glassdoor"),
        "apple": (4.1, "glassdoor"),
        "amazon": (3.8, "glassdoor"),
        "meta": (3.9, "glassdoor"),
        "salesforce": (4.1, "glassdoor"),
        "hubspot": (4.5, "glassdoor"),
        "adobe": (4.3, "glassdoor"),
        "slack": (4.2, "glassdoor"),
        "notion": (4.0, "glassdoor"),
        "khan academy": (4.3, "glassdoor"),
        "coursera": (3.6, "glassdoor"),
    }

    def _check_known_companies(
        self,
        company_name: str
    ) -> Optional[Dict[str, Any]]:
        """Check against curated known company ratings"""
        for known_name, (rating, source) in self.KNOWN_RATINGS.items():
            if known_name in company_name or company_name in known_name:
                return {
                    "rating": rating,
                    "rating_source": f"{source}_curated",
                    "review_count": None,
                    "passes_threshold": rating >= MIN_RATING,
                    "details": {"note": "Curated known company rating"},
                }
        return None


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[CompanyReviewer] = None


def get_company_reviewer() -> CompanyReviewer:
    """Get singleton CompanyReviewer instance"""
    global _instance
    if _instance is None:
        _instance = CompanyReviewer()
    return _instance
