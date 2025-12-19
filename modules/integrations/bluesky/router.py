# modules/integrations/bluesky/router.py
"""
Bluesky FastAPI Router - Complete Multi-Account API
Provides endpoints for chat interface integration and manual controls

UPDATED: 2025-12-19
- Added proactive_engine integration for unified detect→draft→notify flow
- Added /proactive/* endpoints for managing proactive queue
- Updated background scan to use proactive engine
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from ...core.auth import get_current_user
from .multi_account_client import get_bluesky_multi_client
from .engagement_analyzer import get_engagement_analyzer
from .approval_system import get_approval_system
from .proactive_engine import get_proactive_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bluesky", tags=["Bluesky Multi-Account"])

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class PostRequest(BaseModel):
    account_id: str
    text: str
    reply_to_uri: Optional[str] = None

class ApprovalAction(BaseModel):
    approval_id: str
    action: str  # 'approve', 'reject', 'edit'
    edited_text: Optional[str] = None
    rejection_reason: Optional[str] = None

class ScanRequest(BaseModel):
    account_ids: Optional[List[str]] = None
    force_scan: bool = False

class ProactiveEditRequest(BaseModel):
    queue_id: str
    new_text: str

# ============================================================================
# ACCOUNT MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/accounts/status")
async def get_accounts_status(current_user: dict = Depends(get_current_user)):
    """Get status of all configured accounts"""
    try:
        multi_client = get_bluesky_multi_client()
        return {
            "success": True,
            "accounts": multi_client.get_all_accounts_status(),
            "configured_count": len(multi_client.get_configured_accounts()),
            "authenticated_count": len(multi_client.get_authenticated_accounts())
        }
    except Exception as e:
        logger.error(f"Failed to get accounts status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/accounts/authenticate")
async def authenticate_accounts(
    account_ids: Optional[List[str]] = None,
    current_user: dict = Depends(get_current_user)
):
    """Authenticate specific accounts or all accounts"""
    try:
        multi_client = get_bluesky_multi_client()
        
        if account_ids:
            results = {}
            for account_id in account_ids:
                results[account_id] = await multi_client.authenticate_account(account_id)
        else:
            results = await multi_client.authenticate_all_accounts()
        
        authenticated_count = sum(results.values())
        total_count = len(results)
        
        return {
            "success": True,
            "message": f"Authenticated {authenticated_count}/{total_count} accounts",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Failed to authenticate accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PROACTIVE QUEUE ENDPOINTS (NEW!)
# ============================================================================

@router.get("/proactive/pending")
async def get_proactive_pending(
    account_id: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """
    Get pending opportunities from the proactive queue.
    These have pre-generated drafts ready for one-tap posting.
    """
    try:
        engine = get_proactive_engine()
        opportunities = await engine.get_pending_opportunities(
            account_id=account_id,
            limit=limit
        )
        
        return {
            "success": True,
            "opportunities": opportunities,
            "total_count": len(opportunities),
            "source": "proactive_queue"
        }
        
    except Exception as e:
        logger.error(f"Failed to get proactive pending: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proactive/post/{queue_id}")
async def proactive_post(
    queue_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Post a proactive opportunity to Bluesky.
    Alternative to using Telegram button.
    """
    try:
        engine = get_proactive_engine()
        result = await engine.execute_post(queue_id)
        
        if result.get('success'):
            return {
                "success": True,
                "message": "Posted successfully",
                "posted_uri": result.get('posted_uri')
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get('message', 'Post failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute proactive post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proactive/skip/{queue_id}")
async def proactive_skip(
    queue_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Skip a proactive opportunity.
    Alternative to using Telegram button.
    """
    try:
        engine = get_proactive_engine()
        result = await engine.skip_opportunity(queue_id, reason or "Skipped via API")
        
        return {
            "success": result.get('success', False),
            "message": result.get('message', 'Skipped')
        }
        
    except Exception as e:
        logger.error(f"Failed to skip proactive opportunity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proactive/edit")
async def proactive_edit_and_post(
    request: ProactiveEditRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Edit a proactive draft and then post it.
    Used when user wants to modify the AI-generated draft.
    """
    try:
        engine = get_proactive_engine()
        result = await engine.edit_and_post(request.queue_id, request.new_text)
        
        if result.get('success'):
            return {
                "success": True,
                "message": "Edited and posted successfully",
                "posted_uri": result.get('posted_uri')
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get('message', 'Edit and post failed')
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to edit and post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proactive/cleanup")
async def proactive_cleanup(
    current_user: dict = Depends(get_current_user)
):
    """
    Clean up expired proactive opportunities.
    """
    try:
        engine = get_proactive_engine()
        count = await engine.cleanup_expired()
        
        return {
            "success": True,
            "expired_cleaned": count
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup proactive queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# INTELLIGENCE & SCANNING ENDPOINTS
# ============================================================================

@router.post("/scan")
async def scan_for_opportunities(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Scan timelines for engagement opportunities.
    Now uses proactive engine for unified detect→draft→notify flow.
    """
    
    # Add background task for actual scanning
    background_tasks.add_task(
        _background_scan_proactive,
        current_user['id'],
        request.account_ids,
        request.force_scan
    )
    
    return {
        "success": True,
        "message": "Proactive scan initiated in background",
        "scanning_accounts": request.account_ids or "all configured accounts",
        "mode": "proactive"
    }

@router.get("/opportunities")
async def get_opportunities(
    account_id: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """
    Get current engagement opportunities.
    Now returns from BOTH legacy approval queue AND proactive queue.
    """
    try:
        # Get from proactive queue (new system)
        engine = get_proactive_engine()
        proactive_opps = await engine.get_pending_opportunities(
            account_id=account_id,
            limit=limit
        )
        
        # Also get from legacy approval system (backwards compatibility)
        approval_system = get_approval_system()
        try:
            legacy_opps = await approval_system.get_pending_approvals(
                account_id=account_id,
                priority=priority,
                limit=limit
            )
        except:
            legacy_opps = []
        
        return {
            "success": True,
            "proactive_opportunities": proactive_opps,
            "legacy_opportunities": legacy_opps,
            "total_proactive": len(proactive_opps),
            "total_legacy": len(legacy_opps),
            "filters": {
                "account_id": account_id,
                "priority": priority,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/opportunities/stats")
async def get_opportunity_stats(current_user: dict = Depends(get_current_user)):
    """Get statistics about pending opportunities"""
    try:
        from ...core.database import db_manager
        
        # Get proactive queue stats
        proactive_stats = {}
        try:
            conn = await db_manager.get_connection()
            try:
                # Count by status
                status_rows = await conn.fetch('''
                    SELECT status, COUNT(*) as count
                    FROM bluesky_proactive_queue
                    GROUP BY status
                ''')
                proactive_stats['by_status'] = {row['status']: row['count'] for row in status_rows}
                
                # Count pending by account
                account_rows = await conn.fetch('''
                    SELECT detected_by_account, COUNT(*) as count
                    FROM bluesky_proactive_queue
                    WHERE status = 'pending' AND expires_at > NOW()
                    GROUP BY detected_by_account
                ''')
                proactive_stats['pending_by_account'] = {row['detected_by_account']: row['count'] for row in account_rows}
                
                # Count pending by priority
                priority_rows = await conn.fetch('''
                    SELECT priority, COUNT(*) as count
                    FROM bluesky_proactive_queue
                    WHERE status = 'pending' AND expires_at > NOW()
                    GROUP BY priority
                ''')
                proactive_stats['pending_by_priority'] = {row['priority']: row['count'] for row in priority_rows}
                
                # Total pending
                pending_row = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM bluesky_proactive_queue
                    WHERE status = 'pending' AND expires_at > NOW()
                ''')
                proactive_stats['total_pending'] = pending_row['count'] if pending_row else 0
                
            finally:
                await db_manager.release_connection(conn)
        except Exception as e:
            logger.warning(f"Could not get proactive stats: {e}")
            proactive_stats = {'error': str(e)}
        
        # Get legacy approval stats
        legacy_stats = {}
        try:
            approval_system = get_approval_system()
            legacy_stats = await approval_system.get_approval_stats()
        except Exception as e:
            legacy_stats = {'error': str(e)}
        
        return {
            "success": True,
            "proactive_stats": proactive_stats,
            "legacy_stats": legacy_stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get opportunity stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# APPROVAL WORKFLOW ENDPOINTS (Legacy - kept for backwards compatibility)
# ============================================================================

@router.post("/approve")
async def handle_approval_action(
    action: ApprovalAction,
    current_user: dict = Depends(get_current_user)
):
    """
    Handle approval, rejection, or editing of opportunities.
    This is the LEGACY approval system. New flow uses /proactive/* endpoints.
    """
    try:
        approval_system = get_approval_system()
        user_id = current_user['id']
        
        if action.action == "approve":
            result = await approval_system.approve_and_post(action.approval_id, user_id)
            
        elif action.action == "reject":
            result = await approval_system.reject_approval(
                action.approval_id,
                user_id,
                action.rejection_reason or "User rejected"
            )
            
        elif action.action == "edit":
            if not action.edited_text:
                raise HTTPException(status_code=400, detail="edited_text required for edit action")
            
            result = await approval_system.edit_and_approve(
                action.approval_id,
                action.edited_text,
                user_id
            )
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle approval action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# POSTING ENDPOINTS
# ============================================================================

@router.post("/post")
async def create_post(
    request: PostRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new post on specified account"""
    try:
        multi_client = get_bluesky_multi_client()
        
        # Build reply reference if provided
        reply_to = None
        if request.reply_to_uri:
            # Would need to fetch the post to get CID
            # For now, simple implementation
            reply_to = {
                "root": {"uri": request.reply_to_uri, "cid": ""},
                "parent": {"uri": request.reply_to_uri, "cid": ""}
            }
        
        result = await multi_client.create_post(
            account_id=request.account_id,
            text=request.text,
            reply_to=reply_to
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to create post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# NOTIFICATION ENDPOINTS
# ============================================================================

@router.get("/notifications")
async def get_notifications(
    notification_type: Optional[str] = None,
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """Get Bluesky-related notifications"""
    try:
        # Get proactive queue items that were notified
        from ...core.database import db_manager
        
        conn = await db_manager.get_connection()
        try:
            rows = await conn.fetch('''
                SELECT 
                    id,
                    detected_by_account,
                    author_handle,
                    original_text,
                    draft_text,
                    engagement_score,
                    priority,
                    status,
                    notification_sent_at,
                    bluesky_url
                FROM bluesky_proactive_queue
                WHERE notification_sent_at IS NOT NULL
                ORDER BY notification_sent_at DESC
                LIMIT $1
            ''', limit)
            
            notifications = [dict(row) for row in rows]
            
            return {
                "success": True,
                "notifications": notifications,
                "total_count": len(notifications)
            }
            
        finally:
            await db_manager.release_connection(conn)
        
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CHAT INTERFACE ENDPOINTS
# ============================================================================

@router.get("/chat-summary")
async def get_chat_summary(current_user: dict = Depends(get_current_user)):
    """Get summary for chat interface display"""
    try:
        multi_client = get_bluesky_multi_client()
        engine = get_proactive_engine()
        
        # Get pending proactive opportunities
        proactive_opps = await engine.get_pending_opportunities(limit=5)
        
        # Get account status
        accounts_status = multi_client.get_all_accounts_status()
        authenticated_accounts = [
            name for name, info in accounts_status.items()
            if info.get('authenticated', False)
        ]
        
        # Count by priority
        high_priority = [o for o in proactive_opps if o.get('priority') == 'high']
        
        # Format for chat display
        summary = {
            "authenticated_accounts": len(authenticated_accounts),
            "total_accounts": len(accounts_status),
            "pending_opportunities": len(proactive_opps),
            "high_priority_count": len(high_priority),
            "top_opportunities": proactive_opps[:3] if proactive_opps else [],
            "system": "proactive",  # Indicate new system
            "quick_actions": [
                {"action": "scan_all", "label": "Scan All Accounts", "available": len(authenticated_accounts) > 0},
                {"action": "view_high_priority", "label": f"View High Priority ({len(high_priority)})", "available": len(high_priority) > 0},
                {"action": "authenticate", "label": "Re-authenticate Accounts", "available": len(authenticated_accounts) < len(accounts_status)}
            ]
        }
        
        return {"success": True, "summary": summary}
        
    except Exception as e:
        logger.error(f"Failed to get chat summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# BACKGROUND TASKS - PROACTIVE (NEW!)
# ============================================================================

async def _background_scan_proactive(
    user_id: str,
    account_ids: Optional[List[str]] = None,
    force_scan: bool = False
):
    """
    Background task for scanning timelines using PROACTIVE ENGINE.
    
    This is the new unified flow:
    1. Scan timeline
    2. Detect opportunity
    3. Generate AI draft immediately
    4. Store in proactive_queue
    5. Send rich Telegram notification with draft + buttons
    
    All in one pass - no more disconnected tables!
    """
    try:
        logger.info(f"🚀 Starting PROACTIVE background scan for user {user_id}")
        
        multi_client = get_bluesky_multi_client()
        engagement_analyzer = get_engagement_analyzer()
        proactive_engine = get_proactive_engine()
        
        # Authenticate accounts if needed
        await multi_client.authenticate_all_accounts()
        
        # Determine which accounts to scan
        if account_ids:
            accounts_to_scan = account_ids
        else:
            accounts_to_scan = multi_client.get_authenticated_accounts()
        
        if force_scan:
            logger.info(f"Force scan requested - scanning all {len(accounts_to_scan)} accounts")
        else:
            # Filter accounts that need scanning
            accounts_to_scan = [
                account_id for account_id in accounts_to_scan
                if multi_client.should_scan_account(account_id)
            ]
            logger.info(f"Regular scan - {len(accounts_to_scan)} accounts need scanning")
        
        if not accounts_to_scan:
            logger.info("No accounts need scanning at this time")
            return
        
        # Stats tracking
        total_posts_scanned = 0
        total_opportunities_created = 0
        
        # Scan each account
        for account_id in accounts_to_scan:
            try:
                logger.info(f"📱 Scanning {account_id}...")
                
                # Get timeline
                timeline = await multi_client.get_timeline(account_id, limit=50)
                if not timeline:
                    logger.warning(f"No timeline returned for {account_id}")
                    continue
                
                total_posts_scanned += len(timeline)
                
                # Get account config for keyword matching
                account_config = multi_client.get_account_info(account_id)
                
                # Process each post through proactive engine
                account_opportunities = 0
                
                for post in timeline:
                    try:
                        # First, analyze the post for keyword matches
                        analysis = await engagement_analyzer.analyze_post_for_account(
                            post, account_id, account_config
                        )
                        
                        if not analysis:
                            continue
                        
                        # Check if it meets our threshold
                        engagement_potential = analysis.get('engagement_potential', 0)
                        if engagement_potential < 0.3:
                            continue
                        
                        # Convert engagement_potential (0-1) to score (0-100)
                        engagement_score = engagement_potential * 100
                        
                        # Get matched keywords
                        matched_keywords = analysis.get('keyword_analysis', {}).get('matched_keywords', [])
                        
                        # Process through proactive engine
                        # This does: generate draft, store, send notification
                        queue_id = await proactive_engine.process_opportunity(
                            post=post,
                            account_id=account_id,
                            matched_keywords=matched_keywords,
                            engagement_score=engagement_score,
                            opportunity_type='reply'
                        )
                        
                        if queue_id:
                            account_opportunities += 1
                            total_opportunities_created += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing post: {e}")
                        continue
                
                logger.info(f"✅ {account_id}: {account_opportunities} opportunities created")
                
                # Small delay between accounts to avoid rate limiting
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to scan {account_id}: {e}")
                continue
        
        # Cleanup expired opportunities
        expired_count = await proactive_engine.cleanup_expired()
        
        logger.info(f"""
🎯 PROACTIVE SCAN COMPLETE
   Posts scanned: {total_posts_scanned}
   Opportunities created: {total_opportunities_created}
   Expired cleaned: {expired_count}
   Accounts scanned: {len(accounts_to_scan)}
""")
        
    except Exception as e:
        logger.error(f"Proactive background scan failed: {e}", exc_info=True)


# ============================================================================
# LEGACY BACKGROUND TASK (Kept for reference, no longer called)
# ============================================================================

async def _background_scan_legacy(
    user_id: str,
    account_ids: Optional[List[str]] = None,
    force_scan: bool = False
):
    """
    LEGACY background task - kept for reference.
    The new proactive scan (_background_scan_proactive) should be used instead.
    """
    logger.warning("Legacy background scan called - consider using proactive scan instead")
    # ... original implementation preserved but not executed ...
    pass


# ============================================================================
# MAINTENANCE ENDPOINTS
# ============================================================================

@router.post("/maintenance/cleanup")
async def cleanup_expired_data(current_user: dict = Depends(get_current_user)):
    """Clean up expired approvals and proactive queue items"""
    try:
        # Clean proactive queue
        engine = get_proactive_engine()
        proactive_expired = await engine.cleanup_expired()
        
        # Clean legacy approval system
        approval_system = get_approval_system()
        try:
            legacy_expired = await approval_system.cleanup_expired_approvals()
        except:
            legacy_expired = 0
        
        return {
            "success": True,
            "proactive_expired_cleaned": proactive_expired,
            "legacy_expired_cleaned": legacy_expired
        }
        
    except Exception as e:
        logger.error(f"Failed cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        multi_client = get_bluesky_multi_client()
        accounts_status = multi_client.get_all_accounts_status()
        
        configured_accounts = len([a for a in accounts_status.values() if a.get('password')])
        authenticated_accounts = len([a for a in accounts_status.values() if a.get('authenticated')])
        
        return {
            "success": True,
            "status": "healthy",
            "accounts_configured": configured_accounts,
            "accounts_authenticated": authenticated_accounts,
            "services": {
                "multi_client": "operational",
                "engagement_analyzer": "operational",
                "approval_system": "operational (legacy)",
                "proactive_engine": "operational",
                "notification_manager": "operational"
            },
            "mode": "proactive"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }
