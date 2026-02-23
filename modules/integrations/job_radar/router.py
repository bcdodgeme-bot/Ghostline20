# modules/integrations/job_radar/router.py
"""
Job Radar FastAPI Router for Syntax Prime V2
=============================================
Provides endpoints for:
- Manual scan trigger
- Top matches retrieval
- Job detail and response tracking
- Statistics and health

Also contains the background scan orchestrator that runs every 4 hours.

Created: 2026-02-23
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ...core.auth import get_current_user
from .database_manager import get_job_radar_db, JobRadarDatabaseManager
from .job_search_client import get_search_client
from .job_scorer import get_job_scorer
from .halal_filter import get_halal_filter
from .company_reviewer import get_company_reviewer
from .profile_config import (
    NOTIFICATION_THRESHOLDS,
    SEARCH_QUERIES,
    check_instant_reject,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-radar", tags=["Job Radar"])

# Default user ID
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class JobResponseRequest(BaseModel):
    """User response to a job listing"""
    status: str  # 'applied', 'saved', 'skipped', 'rejected'
    notes: Optional[str] = None


class ManualScanRequest(BaseModel):
    """Override queries for a manual scan"""
    queries: Optional[List[str]] = None
    max_per_query: int = 10


# =============================================================================
# BACKGROUND SCAN ORCHESTRATOR
# =============================================================================

async def run_job_scan(
    telegram_service=None,
    manual_queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Complete job scan pipeline:
    1. Search all APIs
    2. Deduplicate against existing jobs
    3. Pre-filter (instant reject)
    4. Halal pre-screen
    5. AI score remaining jobs
    6. Store results
    7. Send notifications for high matches
    8. Bridge top matches to knowledge_entries

    Args:
        telegram_service: NotificationManager instance (optional)
        manual_queries: Override search queries

    Returns:
        Scan statistics dict
    """
    scan_start = time.time()
    db = get_job_radar_db()
    search_client = get_search_client()
    scorer = get_job_scorer()
    halal = get_halal_filter()
    reviewer = get_company_reviewer()

    # Start scan log
    scan_id = await db.start_scan_log()

    stats = {
        "queries_run": 0,
        "total_results": 0,
        "duplicates_skipped": 0,
        "instant_rejects": 0,
        "halal_rejects": 0,
        "ai_scored": 0,
        "high_matches": 0,
        "notifications_sent": 0,
        "errors": [],
    }

    try:
        # Step 1: Search
        queries = manual_queries or SEARCH_QUERIES
        stats["queries_run"] = len(queries)
        logger.info(f"🔍 Starting job scan with {len(queries)} queries...")

        raw_results = await search_client.search_all(queries=queries)
        stats["total_results"] = len(raw_results)
        logger.info(f"🔍 Got {len(raw_results)} raw results")

        if not raw_results:
            logger.info("No results found — scan complete")
            stats["duration_seconds"] = time.time() - scan_start
            await db.complete_scan_log(scan_id, stats)
            return stats

        # Step 2: Deduplicate
        hashes = []
        hash_to_job = {}
        for job in raw_results:
            h = db.compute_dedup_hash(
                job.get('title', ''),
                job.get('company', ''),
                job.get('location', '')
            )
            job['dedup_hash'] = h
            if h not in hash_to_job:
                hash_to_job[h] = job
            hashes.append(h)

        existing = await db.bulk_check_existing(list(hash_to_job.keys()))
        new_jobs = [
            job for h, job in hash_to_job.items()
            if h not in existing
        ]
        stats["duplicates_skipped"] = len(hash_to_job) - len(new_jobs)
        logger.info(f"🔍 {len(new_jobs)} new jobs after dedup ({stats['duplicates_skipped']} dupes)")

        if not new_jobs:
            logger.info("All duplicates — scan complete")
            stats["duration_seconds"] = time.time() - scan_start
            await db.complete_scan_log(scan_id, stats)
            return stats

        # Step 3: Pre-filter + Halal pre-screen
        jobs_to_score = []
        for job in new_jobs:
            # Instant reject check
            reject_reason = check_instant_reject(job)
            if reject_reason:
                job['instant_reject_reason'] = reject_reason
                await db.store_job(job)
                stats["instant_rejects"] += 1
                continue

            # Halal pre-screen (fast keyword check)
            halal_result = halal.evaluate(job)
            if halal_result['result'] == 'FAIL':
                job['instant_reject_reason'] = f"Halal: {halal_result['reason']}"
                await db.store_job(job)
                stats["halal_rejects"] += 1
                continue

            jobs_to_score.append(job)

        logger.info(
            f"🔍 {len(jobs_to_score)} jobs pass pre-filter "
            f"({stats['instant_rejects']} rejected, {stats['halal_rejects']} halal fails)"
        )

        # Step 4: AI scoring
        if jobs_to_score:
            score_results = await scorer.score_batch(jobs_to_score)
            stats["ai_scored"] = len(score_results)

            # Step 5: Store results and process
            for job, scores in zip(jobs_to_score, score_results):
                # Store the job first
                job_id = await db.store_job(job)
                if not job_id:
                    continue

                # Update with scores
                await db.update_job_scores(job_id, scores)

                overall = scores.get('overall_score', 0)

                # Track high matches
                if overall >= NOTIFICATION_THRESHOLDS['immediate_push']:
                    stats["high_matches"] += 1

                    # Bridge to knowledge_entries
                    await db.bridge_to_knowledge(job_id)

                    # Send immediate notification
                    if telegram_service:
                        try:
                            msg = _format_job_notification(job, scores)
                            buttons = _build_job_buttons(job_id)
                            result = await telegram_service.send_notification(
                                user_id=DEFAULT_USER_ID,
                                notification_type='intelligence',
                                notification_subtype='job_match',
                                message_text=msg,
                                buttons=buttons,
                                message_data={
                                    "job_id": job_id,
                                    "score": overall,
                                    "company": job.get('company'),
                                    "title": job.get('title'),
                                },
                            )
                            if result.get('success'):
                                await db.mark_notification_sent(
                                    job_id, 'immediate',
                                    result.get('telegram_message_id')
                                )
                                stats["notifications_sent"] += 1
                        except Exception as e:
                            logger.error(f"Notification error: {e}")
                            stats["errors"].append(f"Notification: {e}")

                elif overall >= NOTIFICATION_THRESHOLDS['daily_digest']:
                    # Bridge good matches too
                    await db.bridge_to_knowledge(job_id)

    except Exception as e:
        logger.error(f"Job scan error: {e}", exc_info=True)
        stats["errors"].append(str(e))

    stats["duration_seconds"] = round(time.time() - scan_start, 1)
    await db.complete_scan_log(scan_id, stats)

    logger.info(
        f"✅ Job scan complete in {stats['duration_seconds']}s: "
        f"{stats['total_results']} found, {stats['ai_scored']} scored, "
        f"{stats['high_matches']} high matches"
    )

    return stats


# =============================================================================
# TELEGRAM NOTIFICATION FORMATTING
# =============================================================================

def _format_job_notification(
    job: Dict[str, Any],
    scores: Dict[str, Any]
) -> str:
    """Format a high-scoring job match as a Telegram notification"""
    overall = scores.get('overall_score', 0)
    recommendation = scores.get('recommendation', 'UNKNOWN')

    # Score emoji
    if overall >= 90:
        score_emoji = "🔥"
    elif overall >= 80:
        score_emoji = "⭐"
    else:
        score_emoji = "📋"

    # Salary range
    salary_str = ""
    if job.get('salary_min') or job.get('salary_max'):
        sal_min = f"${job['salary_min']:,.0f}" if job.get('salary_min') else "?"
        sal_max = f"${job['salary_max']:,.0f}" if job.get('salary_max') else "?"
        salary_str = f"\n💰 {sal_min} - {sal_max}"

    # Top reasons
    reasons = scores.get('top_3_reasons_for', [])
    reasons_str = ""
    if reasons:
        reasons_str = "\n\n**Why it matches:**\n"
        for r in reasons[:3]:
            reasons_str += f"• {r}\n"

    # Cover letter angle
    cover = scores.get('cover_letter_angle', '')
    cover_str = f"\n\n💡 *Angle: {cover}*" if cover else ""

    # Apply URL
    apply_str = ""
    if job.get('apply_url'):
        apply_str = f"\n\n🔗 [Apply Here]({job['apply_url']})"

    return (
        f"{score_emoji} **Job Match: {overall}/100**\n"
        f"📌 {recommendation.replace('_', ' ').title()}\n\n"
        f"**{job.get('title', 'Unknown')}**\n"
        f"🏢 {job.get('company', 'Unknown')}\n"
        f"📍 {job.get('location', 'Remote')}"
        f"{salary_str}"
        f"{reasons_str}"
        f"{cover_str}"
        f"{apply_str}"
    )


def _build_job_buttons(job_id: str) -> list:
    """Build Telegram inline keyboard buttons for job actions"""
    return [
        [
            {"text": "✅ Save", "callback_data": f"job:save:{job_id}"},
            {"text": "📝 Applied", "callback_data": f"job:applied:{job_id}"},
        ],
        [
            {"text": "⏭️ Skip", "callback_data": f"job:skip:{job_id}"},
            {"text": "❌ Not Interested", "callback_data": f"job:reject:{job_id}"},
        ],
    ]


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/scan")
async def trigger_scan(
    request: ManualScanRequest = None,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Manually trigger a job scan.
    Optionally override search queries.
    """
    try:
        queries = request.queries if request else None
        result = await run_job_scan(manual_queries=queries)
        return {"success": True, "scan_results": result}
    except Exception as e:
        logger.error(f"Manual scan error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches")
async def get_matches(
    min_score: int = Query(60, ge=0, le=100),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get top-scoring job matches"""
    db = get_job_radar_db()
    jobs = await db.get_top_matches(min_score=min_score, limit=limit, status=status)

    return {
        "success": True,
        "count": len(jobs),
        "min_score": min_score,
        "jobs": jobs,
    }


@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get full detail for a specific job listing"""
    db = get_job_radar_db()
    job = await db.get_job_by_id(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"success": True, "job": job}


@router.post("/jobs/{job_id}/respond")
async def respond_to_job(
    job_id: str,
    request: JobResponseRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Record user response to a job listing.
    Status: 'applied', 'saved', 'skipped', 'rejected'
    """
    valid_statuses = {'applied', 'saved', 'skipped', 'rejected', 'reviewed'}
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    db = get_job_radar_db()
    success = await db.update_job_status(job_id, request.status, request.notes)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update job status")

    return {"success": True, "job_id": job_id, "status": request.status}


@router.get("/stats")
async def get_statistics(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get job radar statistics"""
    db = get_job_radar_db()
    stats = await db.get_scan_statistics()

    return {"success": True, "statistics": stats}


@router.get("/digest")
async def get_digest(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get jobs ready for daily digest (score 60-79, unsent)"""
    db = get_job_radar_db()
    jobs = await db.get_jobs_for_digest()

    return {"success": True, "count": len(jobs), "jobs": jobs}


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint — no auth required"""
    try:
        from .integration_info import check_module_health
        health = await check_module_health()
        return health
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# =============================================================================
# TELEGRAM CALLBACK HANDLER
# =============================================================================

async def handle_job_callback(
    action: str,
    job_id: str,
    chat_id: int,
    message_id: int,
    bot_client=None,
) -> Dict[str, Any]:
    """
    Handle Telegram inline button callbacks for job actions.
    Called from telegram_webhook.py when callback_data starts with 'job:'.

    Args:
        action: 'save', 'applied', 'skip', 'reject'
        job_id: UUID of the job listing
        chat_id: Telegram chat ID
        message_id: Telegram message ID
        bot_client: TelegramBotClient instance
    """
    db = get_job_radar_db()

    status_map = {
        'save': 'saved',
        'applied': 'applied',
        'skip': 'skipped',
        'reject': 'rejected',
    }

    status = status_map.get(action)
    if not status:
        return {"success": False, "error": f"Unknown action: {action}"}

    success = await db.update_job_status(job_id, status)

    # Confirmation messages
    confirmations = {
        'saved': "💾 Job saved for later review",
        'applied': "📝 Marked as applied — good luck!",
        'skipped': "⏭️ Skipped",
        'rejected': "❌ Not interested — noted",
    }

    # Send answer to callback query
    if bot_client and success:
        try:
            confirmation = confirmations.get(status, "Updated")
            await bot_client.answer_callback_query(
                callback_query_id=None,  # Will be provided by webhook handler
                text=confirmation,
            )
        except Exception as e:
            logger.error(f"Callback answer error: {e}")

    return {"success": success, "status": status}


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = ['router', 'run_job_scan', 'handle_job_callback']
