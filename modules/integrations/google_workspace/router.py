# modules/integrations/google_workspace/router.py
"""
Google Workspace Integration Router
FastAPI endpoints for Google Workspace functionality

Endpoints:
- OAuth authentication (device flow)
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
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

logger = logging.getLogger(__name__)

from ...core.auth import get_current_user
from . import SUPPORTED_SITES
from .oauth_manager import (
    google_auth_manager, 
    start_google_oauth, 
    check_oauth_completion,
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
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    message: str

class OAuthStatusResponse(BaseModel):
    success: bool
    status: str
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
async def start_oauth_flow(user = Depends(get_current_user)):
    """
    Start Google OAuth device flow
    
    Returns device code and verification URL for user authentication
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        flow_data = await start_google_oauth(user_id)
        
        return OAuthStartResponse(
            success=True,
            device_code=flow_data['device_code'],
            user_code=flow_data['user_code'],
            verification_url=flow_data['verification_url'],
            expires_in=flow_data['expires_in'],
            message=f"Visit {flow_data['verification_url']} and enter code: {flow_data['user_code']}"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start OAuth flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/device/{device_code}")
async def check_oauth_status(device_code: str, user = Depends(get_current_user)):
    """
    Check OAuth device flow completion status
    
    Railway-friendly endpoint for completing authentication
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        result = await check_oauth_completion(user_id, device_code)
        
        return OAuthStatusResponse(
            success=result['success'],
            status=result.get('status', 'completed' if result['success'] else 'pending'),
            message=result.get('message', 'Authentication completed!' if result['success'] else 'Waiting for authorization...'),
            email=result.get('email')
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to check OAuth status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/accounts")
async def get_authenticated_accounts(user = Depends(get_current_user)):
    """Get list of authenticated Google accounts"""
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        accounts = await get_google_accounts(user_id)
        
        return {
            "success": True,
            "accounts": accounts,
            "count": len(accounts)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SEARCH CONSOLE ENDPOINTS ====================

@router.get("/keywords/opportunities/{site_name}")
async def get_keyword_opportunities(site_name: str, user = Depends(get_current_user)):
    """
    Get keyword opportunities for a specific site
    
    Returns keywords NOT in existing site keyword table with optimization potential
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if site_name not in SUPPORTED_SITES:
            raise HTTPException(status_code=404, detail=f"Unknown site: {site_name}")
        
        user_id = user['id']
        
        opportunities = await find_keyword_opportunities(user_id, site_name)
        
        return {
            "success": True,
            "site_name": site_name,
            "opportunities": opportunities,
            "count": len(opportunities)
        }
        
    except GoogleTokenExpiredError as e:
        return {
            "success": False,
            "error": "token_expired",
            "message": "Hey, your Google Authorization expired again! Use 'google auth setup' to renew."
        }
    except Exception as e:
        logger.error(f"❌ Failed to get keyword opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/keywords/decision")
async def make_keyword_decision(request: KeywordDecisionRequest, user = Depends(get_current_user)):
    """
    Make decision on keyword opportunity (add to site table or ignore)
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        if request.decision == 'add':
            success = await approve_keyword(user_id, request.site_name, request.keyword)
            message = f"Added '{request.keyword}' to {request.site_name} keyword table"
        elif request.decision == 'ignore':
            success = await reject_keyword(user_id, request.site_name, request.keyword)
            message = f"Ignored keyword '{request.keyword}'"
        else:
            raise HTTPException(status_code=400, detail="Decision must be 'add' or 'ignore'")
        
        return {
            "success": success,
            "message": message,
            "keyword": request.keyword,
            "decision": request.decision
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to process keyword decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/keywords/pending")
async def get_pending_keywords(limit: int = 20, user = Depends(get_current_user)):
    """Get pending keyword opportunities across all sites"""
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        opportunities = await search_console_client.get_pending_opportunities(limit)
        
        return {
            "success": True,
            "opportunities": opportunities,
            "count": len(opportunities)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get pending keywords: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ANALYTICS ENDPOINTS ====================

@router.get("/analytics/summary/{site_name}")
async def get_analytics_summary(site_name: str, days: int = 30, user = Depends(get_current_user)):
    """
    Get Analytics summary for a site
    
    Returns traffic metrics, user behavior, and content performance
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if site_name not in SUPPORTED_SITES:
            raise HTTPException(status_code=404, detail=f"Unknown site: {site_name}")
        
        user_id = user['id']
        
        summary = await fetch_analytics_summary(user_id, site_name, days)
        
        return {
            "success": True,
            "site_name": site_name,
            "summary": summary
        }
        
    except GoogleTokenExpiredError:
        return {
            "success": False,
            "error": "token_expired",
            "message": "Hey, your Google Authorization expired again! Use 'google auth setup' to renew."
        }
    except Exception as e:
        logger.error(f"❌ Failed to get Analytics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/optimal-timing/{site_name}")
async def get_optimal_posting_time(site_name: str, user = Depends(get_current_user)):
    """
    Get optimal content posting time based on traffic patterns
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if site_name not in SUPPORTED_SITES:
            raise HTTPException(status_code=404, detail=f"Unknown site: {site_name}")
        
        user_id = user['id']
        
        timing = await get_optimal_timing(user_id, site_name)
        
        return {
            "success": True,
            "site_name": site_name,
            "optimal_timing": timing
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get optimal timing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DRIVE ENDPOINTS ====================

@router.post("/drive/create/document")
async def create_document(request: DocumentCreateRequest, user = Depends(get_current_user)):
    """
    Create a Google Doc from chat content
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        doc_info = await create_google_doc(
            user_id, 
            request.title, 
            request.content, 
            request.chat_thread_id
        )
        
        return {
            "success": True,
            "document": doc_info,
            "message": f"Created Google Doc: {request.title}"
        }
        
    except GoogleTokenExpiredError:
        return {
            "success": False,
            "error": "token_expired",
            "message": "Hey, your Google Authorization expired again! Use 'google auth setup' to renew."
        }
    except Exception as e:
        logger.error(f"❌ Failed to create document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drive/create/spreadsheet")
async def create_spreadsheet(request: SpreadsheetCreateRequest, user = Depends(get_current_user)):
    """
    Create a Google Sheet from structured data
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        sheet_info = await create_google_sheet(
            user_id,
            request.title,
            request.data,
            request.chat_thread_id
        )
        
        return {
            "success": True,
            "spreadsheet": sheet_info,
            "message": f"Created Google Sheet: {request.title}"
        }
        
    except GoogleTokenExpiredError:
        return {
            "success": False,
            "error": "token_expired",
            "message": "Hey, your Google Authorization expired again! Use 'google auth setup' to renew."
        }
    except Exception as e:
        logger.error(f"❌ Failed to create spreadsheet: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/drive/recent")
async def get_recent_documents(limit: int = 10, user = Depends(get_current_user)):
    """Get recently created Drive documents"""
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        docs = await google_workspace_db.get_recent_documents(user_id, limit)
        
        return {
            "success": True,
            "documents": docs,
            "count": len(docs)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get recent documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== INTEGRATION STATUS ====================

@router.get("/status")
async def get_integration_status(user = Depends(get_current_user)):
    """
    Get overall Google Workspace integration status
    
    Returns OAuth status, data freshness, and statistics
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        user_id = user['id']
        
        # Get comprehensive status
        stats = await get_workspace_stats(user_id)
        oauth_status = await google_workspace_db.get_oauth_status(user_id)
        data_freshness = await google_workspace_db.get_data_freshness(user_id)
        
        return {
            "success": True,
            "status": {
                "oauth": oauth_status,
                "data_freshness": data_freshness,
                "statistics": stats,
                "sites_configured": SUPPORTED_SITES
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get integration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sites")
async def get_supported_sites():
    """Get list of supported sites with configuration"""
    return {
        "success": True,
        "sites": SUPPORTED_SITES,
        "count": len(SUPPORTED_SITES)
    }