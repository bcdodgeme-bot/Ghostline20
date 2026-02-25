# modules/integrations/job_radar/database_manager.py
"""
Job Radar Database Manager for Syntax Prime V2
===============================================
Handles all PostgreSQL operations for job search tracking.

Key Features:
- Store discovered job listings with full metadata
- Deduplication via title+company+location hash
- Track job scores, user responses (applied, skipped, saved)
- Bridge high-scoring jobs to knowledge_entries for chat access
- Analytics on search effectiveness

Database Tables:
- job_radar_listings: All discovered jobs with scores
- job_radar_scan_log: Track scan runs for monitoring

Uses core db_manager for connection pooling (never direct asyncpg).

Created: 2026-02-23
"""

import logging
import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Default user ID for single-user system
DEFAULT_USER_ID = 'b7c60682-4815-4d9d-8ebe-66c6cd24eff9'


class JobRadarDatabaseManager:
    """
    Manages all database operations for job radar system.
    Uses core db_manager for proper connection pooling.
    """

    def __init__(self):
        self.db = db_manager

    # =========================================================================
    # TABLE CREATION (run once via migration script)
    # =========================================================================

    @staticmethod
    def get_migration_sql() -> str:
        """Return SQL to create job_radar tables"""
        return """
        -- Core job listings table
        CREATE TABLE IF NOT EXISTS job_radar_listings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL DEFAULT 'b7c60682-4815-4d9d-8ebe-66c6cd24eff9'::uuid,
            
            -- Job identity
            dedup_hash VARCHAR NOT NULL,
            source_api VARCHAR NOT NULL,          -- 'jsearch', 'adzuna', 'serpapi'
            source_job_id VARCHAR,                -- External ID from API
            
            -- Job details
            title VARCHAR NOT NULL,
            company VARCHAR NOT NULL,
            location VARCHAR,
            description TEXT,
            employment_type VARCHAR,              -- 'FULLTIME', 'PARTTIME', 'CONTRACT'
            salary_min NUMERIC,
            salary_max NUMERIC,
            salary_currency VARCHAR DEFAULT 'USD',
            apply_url TEXT,
            job_posted_at TIMESTAMPTZ,
            
            -- Company info
            company_logo_url TEXT,
            company_website TEXT,
            company_rating NUMERIC,               -- Glassdoor/review score
            company_rating_source VARCHAR,
            company_review_count INTEGER,
            
            -- AI scoring results
            halal_compliance VARCHAR,              -- 'PASS', 'FAIL', 'PENDING'
            halal_notes TEXT,
            skills_match_score INTEGER,
            culture_fit_score INTEGER,
            seniority_score INTEGER,
            strengths_score INTEGER,
            growth_score INTEGER,
            reputation_score INTEGER,
            overall_score INTEGER,
            recommendation VARCHAR,                -- 'STRONG_MATCH', 'GOOD_MATCH', etc.
            scoring_details JSONB DEFAULT '{}'::jsonb,
            
            -- Pre-filter result
            instant_reject_reason TEXT,            -- NULL if passed pre-filter
            
            -- User interaction
            status VARCHAR DEFAULT 'new',          -- 'new', 'reviewed', 'applied', 'saved', 'skipped', 'rejected'
            user_notes TEXT,
            applied_at TIMESTAMPTZ,
            
            -- Notification tracking
            notification_sent BOOLEAN DEFAULT false,
            notification_type VARCHAR,             -- 'immediate', 'digest', NULL
            notification_sent_at TIMESTAMPTZ,
            telegram_message_id BIGINT,
            
            -- Metadata
            raw_api_response JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            
            -- Prevent duplicates
            CONSTRAINT uq_job_radar_dedup UNIQUE (dedup_hash)
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_job_radar_overall_score
            ON job_radar_listings (overall_score DESC NULLS LAST);
        CREATE INDEX IF NOT EXISTS idx_job_radar_status
            ON job_radar_listings (status);
        CREATE INDEX IF NOT EXISTS idx_job_radar_created
            ON job_radar_listings (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_job_radar_halal
            ON job_radar_listings (halal_compliance);
        CREATE INDEX IF NOT EXISTS idx_job_radar_recommendation
            ON job_radar_listings (recommendation);
        CREATE INDEX IF NOT EXISTS idx_job_radar_notification
            ON job_radar_listings (notification_sent, overall_score DESC);

        -- Scan log for monitoring
        CREATE TABLE IF NOT EXISTS job_radar_scan_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scan_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            scan_completed_at TIMESTAMPTZ,
            queries_run INTEGER DEFAULT 0,
            total_results INTEGER DEFAULT 0,
            duplicates_skipped INTEGER DEFAULT 0,
            instant_rejects INTEGER DEFAULT 0,
            ai_scored INTEGER DEFAULT 0,
            high_matches INTEGER DEFAULT 0,
            errors JSONB DEFAULT '[]'::jsonb,
            duration_seconds NUMERIC,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    @staticmethod
    def compute_dedup_hash(title: str, company: str, location: str = "") -> str:
        """
        Generate dedup hash from job title + company + location.
        Normalized to lowercase, stripped of extra whitespace.
        """
        normalized = f"{title.lower().strip()}|{company.lower().strip()}|{location.lower().strip()}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    async def job_exists(self, dedup_hash: str) -> bool:
        """Check if we've already seen this job"""
        result = await self.db.fetch_one(
            "SELECT 1 FROM job_radar_listings WHERE dedup_hash = $1",
            dedup_hash
        )
        return result is not None

    async def bulk_check_existing(self, hashes: List[str]) -> set:
        """Check multiple hashes at once. Returns set of existing hashes."""
        if not hashes:
            return set()
        
        rows = await self.db.fetch_all(
            "SELECT dedup_hash FROM job_radar_listings WHERE dedup_hash = ANY($1)",
            hashes
        )
        return {row['dedup_hash'] for row in rows}

    # =========================================================================
    # JOB STORAGE
    # =========================================================================

    async def store_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """
        Store a job listing. Returns job ID or None if duplicate.
        
        Args:
            job_data: Dict with keys matching column names
            
        Returns:
            UUID string of inserted job, or None if duplicate
        """
        dedup_hash = job_data.get('dedup_hash') or self.compute_dedup_hash(
            job_data.get('title', ''),
            job_data.get('company', ''),
            job_data.get('location', '')
        )

        try:
            result = await self.db.fetch_one(
                """
                INSERT INTO job_radar_listings (
                    dedup_hash, source_api, source_job_id,
                    title, company, location, description,
                    employment_type, salary_min, salary_max,
                    apply_url, job_posted_at,
                    company_logo_url, company_website,
                    instant_reject_reason,
                    raw_api_response
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16
                )
                ON CONFLICT (dedup_hash) DO NOTHING
                RETURNING id
                """,
                dedup_hash,
                job_data.get('source_api', 'unknown'),
                job_data.get('source_job_id'),
                job_data.get('title', 'Unknown'),
                job_data.get('company', 'Unknown'),
                job_data.get('location'),
                job_data.get('description'),
                job_data.get('employment_type'),
                job_data.get('salary_min'),
                job_data.get('salary_max'),
                job_data.get('apply_url'),
                job_data.get('job_posted_at'),
                job_data.get('company_logo_url'),
                job_data.get('company_website'),
                job_data.get('instant_reject_reason'),
                json.dumps(job_data.get('raw_api_response', {}))
            )

            if result:
                return str(result['id'])
            return None  # Duplicate

        except Exception as e:
            logger.error(f"Error storing job: {e}")
            return None

    async def update_job_scores(
        self,
        job_id: str,
        scores: Dict[str, Any]
    ) -> bool:
        """
        Update a job listing with AI scoring results.
        
        Args:
            job_id: UUID of the job listing
            scores: Dict from Claude API scoring response
        """
        try:
            await self.db.execute(
                """
                UPDATE job_radar_listings SET
                    halal_compliance = $2,
                    halal_notes = $3,
                    skills_match_score = $4,
                    culture_fit_score = $5,
                    seniority_score = $6,
                    strengths_score = $7,
                    growth_score = $8,
                    reputation_score = $9,
                    overall_score = $10,
                    recommendation = $11,
                    scoring_details = $12,
                    updated_at = now()
                WHERE id = $1
                """,
                job_id,
                scores.get('halal_compliance', 'PENDING'),
                scores.get('halal_notes'),
                scores.get('skills_match'),
                scores.get('culture_fit'),
                scores.get('seniority_alignment'),
                scores.get('strengths_utilization'),
                scores.get('growth_potential'),
                scores.get('company_reputation_signals'),
                scores.get('overall_score'),
                scores.get('recommendation'),
                json.dumps(scores)
            )
            return True
        except Exception as e:
            logger.error(f"Error updating job scores: {e}")
            return False

    # =========================================================================
    # USER INTERACTION TRACKING
    # =========================================================================

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> bool:
        """Update user's response to a job listing"""
        try:
            applied_at = "now()" if status == 'applied' else None
            
            if status == 'applied':
                await self.db.execute(
                    """UPDATE job_radar_listings 
                       SET status = $2, user_notes = $3, applied_at = now(), updated_at = now()
                       WHERE id = $1""",
                    job_id, status, notes
                )
            else:
                await self.db.execute(
                    """UPDATE job_radar_listings 
                       SET status = $2, user_notes = $3, updated_at = now()
                       WHERE id = $1""",
                    job_id, status, notes
                )
            return True
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False

    async def mark_notification_sent(
        self,
        job_id: str,
        notification_type: str,
        telegram_message_id: Optional[int] = None
    ) -> bool:
        """Mark that a notification was sent for this job"""
        try:
            await self.db.execute(
                """UPDATE job_radar_listings SET
                    notification_sent = true,
                    notification_type = $2,
                    notification_sent_at = now(),
                    telegram_message_id = $3,
                    updated_at = now()
                WHERE id = $1""",
                job_id, notification_type, telegram_message_id
            )
            return True
        except Exception as e:
            logger.error(f"Error marking notification: {e}")
            return False

    # =========================================================================
    # QUERIES
    # =========================================================================

    async def get_top_matches(
        self,
        min_score: int = 60,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get top-scoring job matches"""
        query = """
            SELECT * FROM job_radar_listings
            WHERE overall_score >= $1
              AND halal_compliance = 'PASS'
              AND instant_reject_reason IS NULL
        """
        params = [min_score]
        
        if status:
            query += " AND status = $2"
            params.append(status)
        
        query += " ORDER BY overall_score DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        rows = await self.db.fetch_all(query, *params)
        return [dict(row) for row in rows] if rows else []

    async def get_unsent_matches(self, min_score: int = 60) -> List[Dict[str, Any]]:
        """Get high-scoring jobs that haven't been notified yet"""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM job_radar_listings
            WHERE overall_score >= $1
              AND halal_compliance = 'PASS'
              AND instant_reject_reason IS NULL
              AND notification_sent = false
            ORDER BY overall_score DESC
            """,
            min_score
        )
        return [dict(row) for row in rows] if rows else []

    async def get_jobs_for_digest(self) -> List[Dict[str, Any]]:
        """Get jobs scoring 60-79 for daily digest"""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM job_radar_listings
            WHERE overall_score BETWEEN 60 AND 79
              AND halal_compliance = 'PASS'
              AND instant_reject_reason IS NULL
              AND notification_sent = false
              AND created_at > now() - INTERVAL '24 hours'
            ORDER BY overall_score DESC
            """
        )
        return [dict(row) for row in rows] if rows else []

    async def get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job listing by ID"""
        row = await self.db.fetch_one(
            "SELECT * FROM job_radar_listings WHERE id = $1",
            job_id
        )
        return dict(row) if row else None

    async def get_scan_statistics(self) -> Dict[str, Any]:
        """Get overall job radar statistics"""
        stats = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_jobs,
                COUNT(*) FILTER (WHERE overall_score >= 80) as strong_matches,
                COUNT(*) FILTER (WHERE overall_score BETWEEN 60 AND 79) as good_matches,
                COUNT(*) FILTER (WHERE halal_compliance = 'FAIL') as halal_rejected,
                COUNT(*) FILTER (WHERE instant_reject_reason IS NOT NULL) as instant_rejected,
                COUNT(*) FILTER (WHERE status = 'applied') as applied,
                COUNT(*) FILTER (WHERE status = 'saved') as saved,
                COUNT(*) FILTER (WHERE status = 'skipped') as skipped,
                COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '24 hours') as last_24h,
                COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '7 days') as last_7d,
                AVG(overall_score) FILTER (WHERE overall_score IS NOT NULL) as avg_score
            FROM job_radar_listings
            """
        )
        return dict(stats) if stats else {}

    # =========================================================================
    # SCAN LOG
    # =========================================================================

    async def start_scan_log(self) -> str:
        """Create a new scan log entry, return its ID"""
        result = await self.db.fetch_one(
            "INSERT INTO job_radar_scan_log DEFAULT VALUES RETURNING id"
        )
        return str(result['id'])

    async def complete_scan_log(
        self,
        scan_id: str,
        stats: Dict[str, Any]
    ) -> None:
        """Update scan log with completion stats"""
        await self.db.execute(
            """
            UPDATE job_radar_scan_log SET
                scan_completed_at = now(),
                queries_run = $2,
                total_results = $3,
                duplicates_skipped = $4,
                instant_rejects = $5,
                ai_scored = $6,
                high_matches = $7,
                errors = $8,
                duration_seconds = $9
            WHERE id = $1
            """,
            scan_id,
            stats.get('queries_run', 0),
            stats.get('total_results', 0),
            stats.get('duplicates_skipped', 0),
            stats.get('instant_rejects', 0),
            stats.get('ai_scored', 0),
            stats.get('high_matches', 0),
            json.dumps(stats.get('errors', [])),
            stats.get('duration_seconds', 0)
        )

    def _fmt_salary(val):
        """Format salary value safely"""
        if val is None:
            return "N/A"
        try:
            return f"${val:,.0f}"
        except (TypeError, ValueError):
            return str(val)
            
    # =========================================================================
    # KNOWLEDGE ENTRIES BRIDGE
    # =========================================================================

    async def bridge_to_knowledge(self, job_id: str) -> Optional[str]:
        """
        Add a high-scoring job to knowledge_entries so the chat AI
        can reference it in conversation.
        
        Returns knowledge_entry ID or None on failure.
        """
        job = await self.get_job_by_id(job_id)
        if not job:
            return None

        scores = job.get('scoring_details', {})
        if isinstance(scores, str):
            scores = json.loads(scores)

        # Build knowledge content
        content = (
            f"Job Match: {job['title']} at {job['company']}\n"
            f"Location: {job.get('location', 'Remote')}\n"
            f"Salary: {_fmt_salary(job.get('salary_min'))} - {_fmt_salary(job.get('salary_max'))}\n"
            f"Overall Score: {job.get('overall_score', 'N/A')}/100\n"
            f"Recommendation: {job.get('recommendation', 'N/A')}\n"
            f"Halal: {job.get('halal_compliance', 'N/A')}\n\n"
            f"Why it matches:\n"
        )

        reasons = scores.get('top_3_reasons_for', [])
        for r in reasons:
            content += f"- {r}\n"

        concerns = scores.get('top_3_concerns', [])
        if concerns:
            content += f"\nConcerns:\n"
            for c in concerns:
                content += f"- {c}\n"

        cover_angle = scores.get('cover_letter_angle', '')
        if cover_angle:
            content += f"\nCover letter angle: {cover_angle}\n"

        content += f"\nApply: {job.get('apply_url', 'N/A')}"

        try:
            result = await self.db.fetch_one(
                """
                INSERT INTO knowledge_entries (
                    source_id, title, project_id, content,
                    content_type, user_id, summary,
                    key_topics, relevance_score
                ) VALUES (
                    (SELECT id FROM knowledge_sources WHERE name = 'Job Radar' LIMIT 1),
                    $1, NULL, $2, 'job_match', $3::uuid, $4,
                    $5, $6
                )
                RETURNING id
                """,
                f"Job Match: {job['title']} at {job['company']}",
                content,
                DEFAULT_USER_ID,
                f"Job match scoring {job.get('overall_score', 0)}/100 - {job.get('recommendation', '')}",
                json.dumps(["job search", "career", job.get('company', ''), job.get('title', '')]),
                float(job.get('overall_score', 50)) / 10.0  # Scale 0-100 to 0-10
            )
            return str(result['id']) if result else None
        except Exception as e:
            logger.error(f"Error bridging job to knowledge: {e}")
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_instance: Optional[JobRadarDatabaseManager] = None


def get_job_radar_db() -> JobRadarDatabaseManager:
    """Get singleton JobRadarDatabaseManager instance"""
    global _instance
    if _instance is None:
        _instance = JobRadarDatabaseManager()
    return _instance
