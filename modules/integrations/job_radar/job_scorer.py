# modules/integrations/job_radar/job_scorer.py
"""
Job Scorer for Syntax Prime V2
================================
Sends job listings to Claude API for evaluation against Carl's complete
professional profile. Handles the AI scoring pipeline including prompt
construction, API calls, response parsing, and fallback handling.

Uses OpenRouter for model access (consistent with rest of system).

Created: 2026-02-23
"""

import os
import json
import logging
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List

from .profile_config import (
    build_scoring_prompt,
    SCORING_WEIGHTS,
    NOTIFICATION_THRESHOLDS,
    check_instant_reject,
)

logger = logging.getLogger(__name__)

# OpenRouter config (consistent with Syntax Prime V2 patterns)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SCORING_MODEL = "anthropic/claude-sonnet-4-20250514"  # Cost-effective for bulk scoring
FALLBACK_MODEL = "anthropic/claude-haiku-4-5-20251001"  # Ultra-cheap fallback


class JobScorer:
    """
    AI-powered job scoring pipeline.
    Evaluates each job against Carl's personality, skills, and hard requirements.
    """

    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            logger.warning("⚠️ OPENROUTER_API_KEY not set — job scoring disabled")

        self.model = SCORING_MODEL
        self.fallback_model = FALLBACK_MODEL

        # Rate limiting: max concurrent scoring calls
        self._semaphore = asyncio.Semaphore(3)

        # Stats for current scan
        self._scored_count = 0
        self._error_count = 0

    def get_status(self) -> Dict[str, Any]:
        """Return scorer status for health checks"""
        return {
            "api_configured": bool(self.api_key),
            "model": self.model,
            "fallback_model": self.fallback_model,
            "scored_count": self._scored_count,
            "error_count": self._error_count,
        }

    # =========================================================================
    # MAIN SCORING PIPELINE
    # =========================================================================

    async def score_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a single job listing against Carl's profile.

        Pipeline:
        1. Pre-filter (instant reject check)
        2. Build Claude prompt with full profile
        3. Call Claude API via OpenRouter
        4. Parse structured JSON response
        5. Calculate weighted overall score
        6. Return complete scoring result

        Args:
            job_data: Normalized job dict from search client

        Returns:
            Scoring result dict with all scores and metadata
        """
        # Step 1: Pre-filter
        reject_reason = check_instant_reject(job_data)
        if reject_reason:
            logger.info(f"⛔ Instant reject: {job_data.get('title', '?')} at {job_data.get('company', '?')} — {reject_reason}")
            return {
                "status": "rejected",
                "instant_reject_reason": reject_reason,
                "overall_score": 0,
                "recommendation": "SKIP",
            }

        # Step 2: Call AI scorer
        if not self.api_key:
            logger.warning("No API key — returning placeholder scores")
            return self._placeholder_score(job_data)

        async with self._semaphore:
            scores = await self._call_ai_scorer(job_data)

        if not scores:
            self._error_count += 1
            return {
                "status": "error",
                "overall_score": 0,
                "recommendation": "SKIP",
                "error": "AI scoring failed",
            }

        self._scored_count += 1

        # Step 3: Validate and enhance scores
        scores = self._validate_scores(scores)

        # Step 4: Check halal compliance from AI response
        if scores.get('halal_compliance') == 'FAIL':
            scores['recommendation'] = 'SKIP'
            scores['overall_score'] = 0
            logger.info(f"🚫 Halal fail: {job_data.get('title', '?')} at {job_data.get('company', '?')}")

        scores['status'] = 'scored'
        return scores

    async def score_batch(
        self,
        jobs: List[Dict[str, Any]],
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Score a batch of job listings concurrently.

        Args:
            jobs: List of normalized job dicts
            max_concurrent: Max concurrent API calls

        Returns:
            List of scoring results (same order as input)
        """
        self._scored_count = 0
        self._error_count = 0

        tasks = [self.score_job(job) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scored = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Scoring exception for job {i}: {result}")
                scored.append({
                    "status": "error",
                    "overall_score": 0,
                    "recommendation": "SKIP",
                    "error": str(result),
                })
            else:
                scored.append(result)

        logger.info(
            f"📊 Batch scoring complete: {self._scored_count} scored, "
            f"{self._error_count} errors, {len(jobs)} total"
        )
        return scored

    # =========================================================================
    # AI API CALL
    # =========================================================================

    async def _call_ai_scorer(
        self,
        job_data: Dict[str, Any],
        use_fallback: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Call Claude via OpenRouter to score a job listing.

        Args:
            job_data: Normalized job dict
            use_fallback: Whether to use cheaper fallback model

        Returns:
            Parsed scoring dict, or None on failure
        """
        prompt = build_scoring_prompt(job_data)
        model = self.fallback_model if use_fallback else self.model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ghostline20-production.up.railway.app",
            "X-Title": "Syntax Prime V2 Job Radar",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": 1500,
            "temperature": 0.1,  # Low temp for consistent scoring
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 429:
                        logger.warning(f"Rate limited on {model}, retrying in 5s...")
                        await asyncio.sleep(5)
                        return await self._call_ai_scorer(job_data, use_fallback=True)

                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"OpenRouter error {resp.status}: {error_text[:200]}")
                        # Try fallback model
                        if not use_fallback:
                            return await self._call_ai_scorer(job_data, use_fallback=True)
                        return None

                    data = await resp.json()

            # Extract response text
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if not content:
                logger.error("Empty response from AI scorer")
                return None

            # Parse JSON from response
            return self._parse_ai_response(content)

        except asyncio.TimeoutError:
            logger.error(f"AI scorer timeout ({model})")
            if not use_fallback:
                return await self._call_ai_scorer(job_data, use_fallback=True)
            return None
        except Exception as e:
            logger.error(f"AI scorer error: {e}")
            return None

    # =========================================================================
    # RESPONSE PARSING
    # =========================================================================

    def _parse_ai_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Parse Claude's JSON response. Handles markdown code blocks and
        other formatting quirks.
        """
        # Strip markdown code blocks if present
        cleaned = content.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            scores = json.loads(cleaned)
            return scores
        except json.JSONDecodeError:
            # Try to find JSON object in response
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    pass

            logger.error(f"Failed to parse AI response: {content[:200]}...")
            return None

    def _validate_scores(self, scores: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clamp AI scores to expected ranges.
        Recalculate weighted overall if individual scores are present.
        """
        # Clamp individual scores to 0-100
        score_keys = [
            'skills_match', 'culture_fit', 'seniority_alignment',
            'strengths_utilization', 'growth_potential', 'company_reputation_signals'
        ]

        for key in score_keys:
            if key in scores and isinstance(scores[key], (int, float)):
                scores[key] = max(0, min(100, int(scores[key])))

        # Recalculate weighted overall score
        weight_map = {
            'skills_match': SCORING_WEIGHTS['skills_match'],
            'culture_fit': SCORING_WEIGHTS['culture_fit'],
            'seniority_alignment': SCORING_WEIGHTS['seniority_alignment'],
            'strengths_utilization': SCORING_WEIGHTS['strengths_utilization'],
            'growth_potential': SCORING_WEIGHTS['growth_potential'],
            'company_reputation_signals': SCORING_WEIGHTS['company_reputation'],
        }

        weighted_total = 0
        total_weight = 0
        for key, weight in weight_map.items():
            if key in scores and isinstance(scores[key], (int, float)):
                weighted_total += scores[key] * weight
                total_weight += weight

        if total_weight > 0:
            scores['overall_score'] = int(weighted_total / total_weight)

        # Validate recommendation
        valid_recommendations = {
            'STRONG_MATCH', 'GOOD_MATCH', 'WORTH_REVIEWING', 'WEAK_MATCH', 'SKIP'
        }
        if scores.get('recommendation') not in valid_recommendations:
            # Derive from score
            score = scores.get('overall_score', 0)
            if score >= 80:
                scores['recommendation'] = 'STRONG_MATCH'
            elif score >= 70:
                scores['recommendation'] = 'GOOD_MATCH'
            elif score >= 60:
                scores['recommendation'] = 'WORTH_REVIEWING'
            elif score >= 40:
                scores['recommendation'] = 'WEAK_MATCH'
            else:
                scores['recommendation'] = 'SKIP'

        # Validate halal_compliance
        if scores.get('halal_compliance') not in ('PASS', 'FAIL'):
            scores['halal_compliance'] = 'PASS'  # Default to pass, halal_filter.py handles deep check

        # Ensure list fields exist
        for list_key in ['top_3_reasons_for', 'top_3_concerns', 'suggested_resume_highlights']:
            if not isinstance(scores.get(list_key), list):
                scores[list_key] = []

        if not isinstance(scores.get('cover_letter_angle'), str):
            scores['cover_letter_angle'] = ''

        return scores

    def _placeholder_score(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Return placeholder scores when API is unavailable"""
        return {
            "status": "placeholder",
            "halal_compliance": "PENDING",
            "halal_notes": "API unavailable — manual review needed",
            "skills_match": 50,
            "culture_fit": 50,
            "seniority_alignment": 50,
            "strengths_utilization": 50,
            "growth_potential": 50,
            "company_reputation_signals": 50,
            "overall_score": 50,
            "recommendation": "WORTH_REVIEWING",
            "top_3_reasons_for": ["Pending AI evaluation"],
            "top_3_concerns": ["Scores are placeholder — AI unavailable"],
            "suggested_resume_highlights": [],
            "cover_letter_angle": "",
        }

    # =========================================================================
    # NOTIFICATION HELPERS
    # =========================================================================

    @staticmethod
    def get_notification_tier(score: int) -> Optional[str]:
        """
        Determine notification tier from overall score.

        Returns:
            'immediate', 'digest', 'log', or None (discard)
        """
        if score >= NOTIFICATION_THRESHOLDS['immediate_push']:
            return 'immediate'
        elif score >= NOTIFICATION_THRESHOLDS['daily_digest']:
            return 'digest'
        elif score >= NOTIFICATION_THRESHOLDS['log_only']:
            return 'log'
        return None


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[JobScorer] = None


def get_job_scorer() -> JobScorer:
    """Get singleton JobScorer instance"""
    global _instance
    if _instance is None:
        _instance = JobScorer()
    return _instance
