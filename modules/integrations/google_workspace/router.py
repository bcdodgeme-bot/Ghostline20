# modules/integrations/google_workspace/router.py
"""
Google Workspace Integration Router
FastAPI endpoints for Google Workspace functionality

Endpoints:
- OAuth authentication (web flow)
- Search Console keyword opportunities
- Analytics summaries and insights
- Drive document creation
- Integration status and health checks

Chat Commands Integration:
- google auth setup
- google keywords [site]
- google analytics [site]
- google drive create doc [title]
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

logger = logging.getLogger(__name__)

from ...core.auth import get_current_user
from . import SUPPORTED_SITES
from .oauth_manager import (
    google_auth_manager,
    start_google_oauth,
    handle_google_oauth_callback,
    get_google_accounts,
    GoogleTokenExpiredError
)
from .search_console_client import (
    search_console_client,
    find_keyword_opportunities,
    approve_keyword,
    reject_keyword
)
from .analytics_client import (
    analytics_client,
    fetch_analytics_summary,
    get_optimal_timing
)
from .drive_client import (
    drive_client,
    create_google_doc,
    create_google_sheet
)
from .database_manager import (
    google_workspace_db,
    get_workspace_stats
)

# Create router
router = APIRouter(prefix="/google", tags=["google_workspace"])

# ==================== REQUEST/RESPONSE MODELS ====================

class OAuthStartResponse(BaseModel):
    success: bool
    authorization_url: str
    message: str

class OAuthCallbackResponse(BaseModel):
    success: bool
    message: str
    email: Optional[str] = None

class KeywordOpportunityResponse(BaseModel):
    keyword: str
    site_name: str
    clicks: int
    impressions: int
    position: float
    opportunity_type: str
    potential_impact: str

class KeywordDecisionRequest(BaseModel):
    site_name: str
    keyword: str
    decision: str  # 'add' or 'ignore'

class DocumentCreateRequest(BaseModel):
    title: str
    content: str
    chat_thread_id: Optional[str] = None

class SpreadsheetCreateRequest(BaseModel):
    title: str
    data: List[List[Any]]
    chat_thread_id: Optional[str] = None

# ==================== AUTHENTICATION ENDPOINTS ====================

@router.get("/auth/start")
async def start_oauth_flow(user_id: Optional[str] = None, user = Depends(get_current_user)):
    """
    Start Google OAuth web flow
    
    Returns authorization URL for user to visit
    """
    try:
        # Allow either authenticated user OR user_id parameter (for internal calls)
        if not user and not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Use user_id from parameter if provided, otherwise from authenticated user
        final_user_id = user_id if user_id else user['id']
        
        auth_url = await start_google_oauth(final_user_id)
        
        return OAuthStartResponse(
            success=True,
            authorization_url=auth_url,
            message="Visit the authorization URL to complete authentication"
        )
        
    except Exception as e:
        logger.error(f"Failed to start OAuth flow: {type(e).__name__}: {str(e)}")
        logger.error(f"Exception repr: {repr(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@router.get("/auth/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF protection")
):
    """
    Handle OAuth callback from Google
    
    This endpoint receives the redirect after user authorizes
    """
    try:
        result = await handle_google_oauth_callback(code, state)
        
        if result['success']:
            # Redirect to a success page or back to chat
            return RedirectResponse(
                url=f"/chat?google_auth=success&email={result['email']}",
                status_code=302
            )
        else:
            return RedirectResponse(
                url="/chat?google_auth=failed",
                status_code=302
            )
        
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return RedirectResponse(
            url=f"/chat?google_auth=error&message={str(e)}",
            status_code=302
        )

@router.get("/auth/accounts")
async def get_accounts(
    user_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Get list of authenticated Google accounts
    """
    try:
        # Allow internal calls with user_id parameter OR authenticated user
        if not user and not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Use user_id parameter if provided (for internal calls), otherwise authenticated user
        final_user_id = user_id if user_id else user['id']
        
        logger.info(f"Getting accounts for user: {final_user_id}")
        accounts = await get_google_accounts(final_user_id)
        logger.info(f"Retrieved {len(accounts)} accounts")
        
        return {
            "success": True,
            "accounts": accounts,
            "count": len(accounts)
        }
        
    except Exception as e:
        logger.error(f"Failed to get accounts: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {type(e).__name__} - {str(e)}")

# ==================== SEARCH CONSOLE ENDPOINTS ====================

@router.get("/keywords/opportunities")
async def get_keyword_opportunities(
    site_name: str,
    user = Depends(get_current_user)
):
    """
    Get keyword opportunities for a site from Search Console
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if site_name not in SUPPORTED_SITES:
            raise HTTPException(status_code=400, detail=f"Site not supported. Supported sites: {list(SUPPORTED_SITES.keys())}")
        
        opportunities = await find_keyword_opportunities(user['id'], site_name)
        
        return {
            "success": True,
            "site": site_name,
            "opportunities": opportunities,
            "count": len(opportunities)
        }
        
    except GoogleTokenExpiredError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get keyword opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/keywords/decision")
async def make_keyword_decision(
    decision: KeywordDecisionRequest,
    user = Depends(get_current_user)
):
    """
    Approve or reject a keyword opportunity
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if decision.decision == 'add':
            result = await approve_keyword(user['id'], decision.site_name, decision.keyword)
        elif decision.decision == 'ignore':
            result = await reject_keyword(user['id'], decision.site_name, decision.keyword)
        else:
            raise HTTPException(status_code=400, detail="Decision must be 'add' or 'ignore'")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to process keyword decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ANALYTICS ENDPOINTS ====================

@router.get("/analytics/summary")
async def get_analytics_summary(
    site_name: str,
    days: int = 30,
    user_id: Optional[str] = None,  # ← ADD THIS
    user = Depends(get_current_user)
):
    """Get analytics summary for a site"""
    try:
        # Allow internal calls with user_id parameter OR authenticated user
        if not user and not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Use user_id parameter if provided (for internal calls), otherwise authenticated user
        final_user_id = user_id if user_id else user['id']
        
        if site_name not in SUPPORTED_SITES:
            raise HTTPException(status_code=400, detail=f"Site not supported")
        
        summary = await fetch_analytics_summary(final_user_id, site_name, days)
        
        return {
            "success": True,
            "site": site_name,
            "period_days": days,
            "summary": summary
        }
        
    except GoogleTokenExpiredError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get analytics summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/timing")
async def get_posting_timing(
    site_name: str,
    user = Depends(get_current_user)
):
    """
    Get optimal posting timing based on analytics
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        timing = await get_optimal_timing(user['id'], site_name)
        
        return {
            "success": True,
            "site": site_name,
            "optimal_timing": timing
        }
        
    except Exception as e:
        logger.error(f"Failed to get optimal timing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DRIVE ENDPOINTS ====================

@router.post("/drive/document")
async def create_document(
    request: DocumentCreateRequest,
    user = Depends(get_current_user)
):
    """
    Create a Google Doc
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        doc = await create_google_doc(
            user['id'],
            request.title,
            request.content,
            request.chat_thread_id
        )
        
        return {
            "success": True,
            "document": doc
        }
        
    except Exception as e:
        logger.error(f"Failed to create document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drive/spreadsheet")
async def create_spreadsheet(
    request: SpreadsheetCreateRequest,
    user = Depends(get_current_user)
):
    """
    Create a Google Sheet
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        sheet = await create_google_sheet(
            user['id'],
            request.title,
            request.data,
            request.chat_thread_id
        )
        
        return {
            "success": True,
            "spreadsheet": sheet
        }
        
    except Exception as e:
        logger.error(f"Failed to create spreadsheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== STATUS ENDPOINTS ====================

@router.get("/status")
async def get_integration_status(user = Depends(get_current_user)):
    """
    Get Google Workspace integration status
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        accounts = await get_google_accounts(user['id'])
        stats = await get_workspace_stats(user['id'])
        
        return {
            "success": True,
            "authenticated_accounts": len(accounts),
            "accounts": accounts,
            "statistics": stats,
            "supported_sites": list(SUPPORTED_SITES.keys())
        }
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "service": "google_workspace",
        "components": {
            "oauth": "ready",
            "search_console": "ready",
            "analytics": "ready",
            "drive": "ready"
        }
    }
