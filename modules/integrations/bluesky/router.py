# modules/integrations/bluesky/router.py
"""
Bluesky FastAPI Router - Complete Multi-Account API
Provides endpoints for chat interface integration and manual controls
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
from .notification_manager import get_notification_manager

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
# INTELLIGENCE & SCANNING ENDPOINTS
# ============================================================================

@router.post("/scan")
async def scan_for_opportunities(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Scan timelines for engagement opportunities"""
    
    # Add background task for actual scanning
    background_tasks.add_task(
        _background_scan,
        current_user['id'],
        request.account_ids,
        request.force_scan
    )
    
    return {
        "success": True,
        "message": "Scan initiated in background",
        "scanning_accounts": request.account_ids or "all configured accounts"
    }

@router.get("/opportunities")
async def get_opportunities(
    account_id: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """Get current engagement opportunities"""
    try:
        approval_system = get_approval_system()
        
        opportunities = await approval_system.get_pending_approvals(
            account_id=account_id,
            priority=priority,
            limit=limit
        )
        
        return {
            "success": True,
            "opportunities": opportunities,
            "total_count": len(opportunities),
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
        approval_system = get_approval_system()
        notification_manager = get_notification_manager()
        
        approval_stats = approval_system.get_approval_stats()
        notification_stats = await notification_manager.get_notification_stats(current_user['id'])
        
        return {
            "success": True,
            "approval_stats": approval_stats,
            "notification_stats": notification_stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get opportunity stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# APPROVAL WORKFLOW ENDPOINTS
# ============================================================================

@router.post("/approve")
async def handle_approval_action(
    action: ApprovalAction,
    current_user: dict = Depends(get_current_user)
):
    """Handle approval, rejection, or editing of opportunities"""
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
        
    except Exception as e:
        logger.error(f"Failed to handle approval action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# DIRECT POSTING ENDPOINTS
# ============================================================================

@router.post("/post")
async def create_post(
    request: PostRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a direct post on specified account"""
    try:
        multi_client = get_bluesky_multi_client()
        
        # Validate account exists and user has permission
        account_info = multi_client.get_account_info(request.account_id)
        if not account_info:
            raise HTTPException(status_code=404, detail=f"Account {request.account_id} not found")
        
        # Create the post
        result = await multi_client.create_post(
            account_id=request.account_id,
            text=request.text
        )
        
        if result['success']:
            # Track user activity for notifications
            notification_manager = get_notification_manager()
            await notification_manager.track_user_activity(current_user['id'], 'direct_post')
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to create post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# NOTIFICATION ENDPOINTS
# ============================================================================

@router.get("/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    """Get current notifications (real-time or digest)"""
    try:
        notification_manager = get_notification_manager()
        user_id = current_user['id']
        
        # Track that user is checking notifications
        await notification_manager.track_user_activity(user_id, 'check_notifications')
        
        # Check if digest is ready
        if await notification_manager.should_send_digest(user_id):
            digest = await notification_manager.generate_digest_notification(user_id)
            if digest:
                await notification_manager.record_notification(user_id, 'digest', digest)
                return {"success": True, "notification": digest}
        
        # Get real-time notification if any pending opportunities
        approval_system = get_approval_system()
        recent_opportunities = await approval_system.get_pending_approvals(limit=10)
        
        if recent_opportunities:
            # Check if any warrant real-time notification
            realtime_worthy = []
            for opp in recent_opportunities:
                if await notification_manager.should_send_realtime_notification(user_id, opp):
                    realtime_worthy.append(opp)
            
            if realtime_worthy:
                realtime_notification = await notification_manager.generate_realtime_notification(realtime_worthy)
                if realtime_notification:
                    await notification_manager.record_notification(user_id, 'realtime', realtime_notification)
                    return {"success": True, "notification": realtime_notification}
        
        return {"success": True, "notification": None, "message": "No notifications at this time"}
        
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notifications/clear-digest")
async def clear_digest(current_user: dict = Depends(get_current_user)):
    """Clear user's pending digest"""
    try:
        notification_manager = get_notification_manager()
        success = await notification_manager.clear_digest(current_user['id'])
        
        return {
            "success": success,
            "message": "Digest cleared" if success else "No digest to clear"
        }
        
    except Exception as e:
        logger.error(f"Failed to clear digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ANALYTICS & LEARNING ENDPOINTS
# ============================================================================

@router.get("/analytics/keyword-performance")
async def get_keyword_performance(
    account_id: Optional[str] = None,
    days: int = 7,
    current_user: dict = Depends(get_current_user)
):
    """Get keyword performance analytics"""
    try:
        # This would integrate with your learning system
        # For now, return placeholder data
        return {
            "success": True,
            "message": "Keyword performance analytics not yet implemented",
            "placeholder_data": {
                "account_id": account_id,
                "period_days": days,
                "top_performing_keywords": [],
                "engagement_success_rate": 0.0
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get keyword performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CHAT INTEGRATION ENDPOINTS
# ============================================================================

@router.get("/chat-summary")
async def get_chat_summary(current_user: dict = Depends(get_current_user)):
    """Get summary for chat interface integration"""
    try:
        approval_system = get_approval_system()
        multi_client = get_bluesky_multi_client()
        
        # Get pending opportunities
        opportunities = await approval_system.get_pending_approvals(limit=5)
        
        # Get account status
        accounts_status = multi_client.get_all_accounts_status()
        authenticated_accounts = [
            name for name, info in accounts_status.items() 
            if info.get('authenticated', False)
        ]
        
        # Format for chat display
        summary = {
            "authenticated_accounts": len(authenticated_accounts),
            "total_accounts": len(accounts_status),
            "pending_opportunities": len(opportunities),
            "high_priority_count": len([o for o in opportunities if o.get('priority') == 'high']),
            "top_opportunities": opportunities[:3] if opportunities else [],
            "quick_actions": [
                {"action": "scan_all", "label": "Scan All Accounts", "available": len(authenticated_accounts) > 0},
                {"action": "view_high_priority", "label": f"View High Priority ({len([o for o in opportunities if o.get('priority') == 'high'])})", "available": True},
                {"action": "authenticate", "label": "Re-authenticate Accounts", "available": len(authenticated_accounts) < len(accounts_status)}
            ]
        }
        
        return {"success": True, "summary": summary}
        
    except Exception as e:
        logger.error(f"Failed to get chat summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def _background_scan(user_id: str, 
                          account_ids: Optional[List[str]] = None,
                          force_scan: bool = False):
    """Background task for scanning timelines"""
    try:
        logger.info(f"Starting background scan for user {user_id}")
        
        multi_client = get_bluesky_multi_client()
        engagement_analyzer = get_engagement_analyzer()
        approval_system = get_approval_system()
        notification_manager = get_notification_manager()
        
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
        
        # Scan timelines
        all_opportunities = []
        
        for account_id in accounts_to_scan:
            try:
                logger.info(f"Scanning {account_id}...")
                
                # Get timeline
                timeline = await multi_client.get_timeline(account_id, limit=50)
                if not timeline:
                    continue
                
                # Get account config
                account_config = multi_client.get_account_info(account_id)
                
                # Analyze each post
                opportunities = []
                for post in timeline:
                    analysis = await engagement_analyzer.analyze_post_for_account(
                        post, account_id, account_config
                    )
                    
                    if analysis and analysis.get('engagement_potential', 0) >= 0.3:
                        opportunities.append(analysis)
                
                logger.info(f"Found {len(opportunities)} opportunities for {account_id}")
                all_opportunities.extend(opportunities)
                
            except Exception as e:
                logger.error(f"Failed to scan {account_id}: {e}")
                continue
        
        if not all_opportunities:
            logger.info("No engagement opportunities found in scan")
            return
        
        # Find cross-account opportunities
        account_configs = {
            account_id: multi_client.get_account_info(account_id)
            for account_id in accounts_to_scan
        }
        
        cross_opportunities = await engagement_analyzer.find_cross_account_opportunities(
            all_opportunities, account_configs
        )
        
        # Generate drafts and create approval items
        approval_items_created = 0
        realtime_notifications = []
        
        for opportunity in all_opportunities:
            try:
                # Generate draft
                draft_result = await approval_system.generate_draft_post(opportunity, "reply")
                
                if draft_result['success']:
                    # Create approval item
                    priority = opportunity.get('priority_level', 'medium')
                    approval_id = await approval_system.create_approval_item(
                        opportunity, draft_result, priority
                    )
                    approval_items_created += 1
                    
                    # Check if should trigger real-time notification
                    if await notification_manager.should_send_realtime_notification(user_id, opportunity):
                        realtime_notifications.append(opportunity)
                
            except Exception as e:
                logger.error(f"Failed to process opportunity: {e}")
                continue
        
        # Handle notifications
        if realtime_notifications:
            logger.info(f"Sending real-time notification for {len(realtime_notifications)} opportunities")
            # Real-time notifications would be sent via WebSocket or similar
        elif all_opportunities:
            logger.info(f"Adding {len(all_opportunities)} opportunities to digest")
            await notification_manager.add_to_digest(user_id, all_opportunities)
        
        logger.info(f"Scan complete: {approval_items_created} approval items created, {len(cross_opportunities)} cross-account opportunities found")
        
    except Exception as e:
        logger.error(f"Background scan failed: {e}")

# ============================================================================
# MAINTENANCE ENDPOINTS
# ============================================================================

@router.post("/maintenance/cleanup")
async def cleanup_expired_data(current_user: dict = Depends(get_current_user)):
    """Clean up expired approvals and cache data"""
    try:
        approval_system = get_approval_system()
        notification_manager = get_notification_manager()
        
        expired_approvals = approval_system.cleanup_expired_approvals()
        cleaned_cache = notification_manager.cleanup_old_cache()
        
        return {
            "success": True,
            "expired_approvals_removed": expired_approvals,
            "cache_entries_cleaned": cleaned_cache
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
                "approval_system": "operational",
                "notification_manager": "operational"
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }