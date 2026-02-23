# modules/integrations/job_radar/halal_filter.py
"""
Halal Income Compliance Filter for Syntax Prime V2
===================================================
Evaluates job listings for Islamic income compliance.

Two-layer approach:
1. FAST CHECK: Keyword matching against known haram industries/signals
2. DEEP CHECK: AI evaluation of company culture, revenue sources, and
   whether haram is normalized in corporate life

The goal isn't just "is the company in a haram industry" but
"would Carl feel comfortable working here during Ramadan?"

Created: 2026-02-23
"""

import logging
from typing import Dict, Any, Tuple, Optional, List

from .profile_config import HALAL_FILTER

logger = logging.getLogger(__name__)


class HalalFilter:
    """
    Islamic income compliance checker.
    Returns PASS, FAIL, or REVIEW_NEEDED with explanation.
    """

    def __init__(self):
        # Pre-compile lowercase versions of all filter lists
        self._excluded_industries = [
            i.lower() for i in HALAL_FILTER['excluded_industries']
        ]
        self._company_red_flags = [
            f.lower() for f in HALAL_FILTER['company_red_flags']
        ]
        self._culture_red_flags = [
            f.lower() for f in HALAL_FILTER['culture_red_flags']
        ]

    # =========================================================================
    # MAIN FILTER
    # =========================================================================

    def evaluate(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a job listing for halal compliance.

        Args:
            job_data: Normalized job dict with title, company, description

        Returns:
            Dict with:
                result: 'PASS', 'FAIL', or 'REVIEW_NEEDED'
                reason: Explanation string
                flags: List of specific flags triggered
                confidence: 'high' or 'low'
        """
        title = (job_data.get('title') or '').lower()
        company = (job_data.get('company') or '').lower()
        description = (job_data.get('description') or '').lower()
        location = (job_data.get('location') or '').lower()

        # Combine all text for scanning
        all_text = f"{title} {company} {description}"

        flags: List[str] = []

        # Layer 1: Company name check
        company_flags = self._check_company_name(company)
        if company_flags:
            flags.extend(company_flags)
            return {
                "result": "FAIL",
                "reason": f"Company name triggers halal filter: {', '.join(company_flags)}",
                "flags": flags,
                "confidence": "high",
            }

        # Layer 2: Industry keywords in description
        industry_flags = self._check_industry_keywords(all_text)
        if industry_flags:
            flags.extend(industry_flags)
            # If multiple industry flags, high confidence fail
            if len(industry_flags) >= 2:
                return {
                    "result": "FAIL",
                    "reason": f"Multiple haram industry signals: {', '.join(industry_flags)}",
                    "flags": flags,
                    "confidence": "high",
                }
            # Single flag could be coincidental (e.g. "spirits" in a tech context)
            # but still worth flagging

        # Layer 3: Culture red flags
        culture_flags = self._check_culture_signals(description)
        if culture_flags:
            flags.extend(culture_flags)

        # Decision logic
        if len(flags) >= 3:
            return {
                "result": "FAIL",
                "reason": f"Multiple halal concerns: {', '.join(flags[:5])}",
                "flags": flags,
                "confidence": "high",
            }
        elif len(flags) >= 1:
            return {
                "result": "REVIEW_NEEDED",
                "reason": f"Potential halal concerns require AI review: {', '.join(flags[:5])}",
                "flags": flags,
                "confidence": "low",
            }
        else:
            return {
                "result": "PASS",
                "reason": "No halal compliance issues detected",
                "flags": [],
                "confidence": "high",
            }

    # =========================================================================
    # CHECK LAYERS
    # =========================================================================

    def _check_company_name(self, company: str) -> List[str]:
        """Check company name against known haram indicators"""
        flags = []
        for flag in self._company_red_flags:
            if flag in company:
                flags.append(f"company_name:{flag}")
        return flags

    def _check_industry_keywords(self, text: str) -> List[str]:
        """Check for haram industry keywords in job text"""
        flags = []

        # Direct industry matches
        for industry in self._excluded_industries:
            if industry in text:
                flags.append(f"industry:{industry}")

        # Specific high-confidence patterns
        high_confidence_patterns = [
            ("interest rate", "conventional finance"),
            ("mortgage lending", "conventional lending"),
            ("payday loan", "predatory lending"),
            ("slot machine", "gambling"),
            ("sports book", "gambling"),
            ("craft beer", "alcohol"),
            ("wine list", "alcohol"),
            ("cocktail menu", "alcohol"),
            ("pork belly", "pork"),  # Also a finance term, hence low weight alone
            ("dispensary", "cannabis"),
            ("thc", "cannabis"),
            ("ammunition", "weapons"),
            ("firearm", "weapons"),
        ]

        for pattern, category in high_confidence_patterns:
            if pattern in text:
                flags.append(f"pattern:{category}({pattern})")

        return flags

    def _check_culture_signals(self, description: str) -> List[str]:
        """Check for culture signals that normalize haram activities"""
        flags = []
        for flag in self._culture_red_flags:
            if flag in description:
                flags.append(f"culture:{flag}")
        return flags

    # =========================================================================
    # KNOWN SAFE/UNSAFE COMPANIES (curated list)
    # =========================================================================

    # Companies known to be in haram industries
    KNOWN_HARAM_COMPANIES = {
        "anheuser-busch", "budweiser", "molson coors", "diageo",
        "pernod ricard", "constellation brands", "boston beer",
        "mgm resorts", "caesars entertainment", "wynn resorts",
        "draftkings", "fanduel", "bet365", "betmgm",
        "goldman sachs", "jp morgan", "wells fargo", "bank of america",
        "citibank", "hsbc", "barclays", "deutsche bank",
        "morgan stanley", "credit suisse",
        "altria", "philip morris", "british american tobacco",
        "smith & wesson", "ruger", "lockheed martin", "raytheon",
        "northrop grumman", "general dynamics",
    }

    # Companies known to be halal-friendly or in permissible industries
    KNOWN_SAFE_COMPANIES = {
        "google", "microsoft", "apple", "amazon",  # Tech (general)
        "salesforce", "hubspot", "slack", "notion",  # SaaS
        "khan academy", "coursera",  # EdTech
        "mayo clinic", "cleveland clinic",  # Healthcare
        "habitat for humanity", "red cross",  # Nonprofit
        "islamic relief", "muslim aid",  # Islamic nonprofit
    }

    def quick_company_check(self, company_name: str) -> Optional[str]:
        """
        Quick check against known company lists.
        Returns 'PASS', 'FAIL', or None if unknown.
        """
        normalized = company_name.lower().strip()

        for haram_company in self.KNOWN_HARAM_COMPANIES:
            if haram_company in normalized or normalized in haram_company:
                return "FAIL"

        for safe_company in self.KNOWN_SAFE_COMPANIES:
            if safe_company in normalized or normalized in safe_company:
                return "PASS"

        return None  # Unknown, needs full evaluation


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[HalalFilter] = None


def get_halal_filter() -> HalalFilter:
    """Get singleton HalalFilter instance"""
    global _instance
    if _instance is None:
        _instance = HalalFilter()
    return _instance
