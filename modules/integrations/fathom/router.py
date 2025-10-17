# modules/integrations/fathom/router.py
"""
Fathom Integration FastAPI Router
Handles webhooks from Fathom and provides API endpoints for meeting access

Endpoints:
- POST /integrations/fathom/webhook - Receive Fathom webhooks when meetings end
- GET /integrations/fathom/meetings - List recent meetings
- GET /integrations/fathom/meetings/{meeting_id} - Get specific meeting
- GET /integrations/fathom/search - Search meetings by keywords
- GET /integrations/fathom/action-items - Get pending action items
- GET /integrations/fathom/status - Integration health check

Workflow:
1. Fathom webhook fires when meeting ends → /webhook
2. Fetch meeting + transcript from Fathom API
3. Generate AI summary using Claude
4. Store in PostgreSQL
5. Return success
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

from .fathom_handler import FathomHandler
from .meeting_processor import MeetingProcessor
from .database_manager import FathomDatabaseManager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/integrations/fathom", tags=["Fathom Meetings"])

# Initialize handlers
fathom_handler = FathomHandler()
meeting_processor = MeetingProcessor()
database_manager = FathomDatabaseManager()

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WebhookResponse(BaseModel):
    success: bool
    meeting_id: Optional[str] = None
    message: str
    error: Optional[str] = None

class MeetingSearchRequest(BaseModel):
    query: str
    limit: int = 10

class MeetingListResponse(BaseModel):
    meetings: List[Dict[str, Any]]
    total: int

class ActionItemUpdateRequest(BaseModel):
    item_id: str
    status: str  # pending/completed/cancelled

# ============================================================================
# WEBHOOK ENDPOINT (PRIMARY INTEGRATION POINT)
# ============================================================================

@router.post("/webhook", response_model=WebhookResponse)
async def fathom_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive webhooks from Fathom when meetings end
    
    Fathom sends POST requests to this endpoint with:
    - Headers: X-Fathom-Timestamp, X-Fathom-Signature
    - Body: meeting_id, event_type, etc.
    
    This endpoint:
    1. Verifies webhook signature
    2. Queues background processing
    3. Returns immediately (Fathom expects fast response)
    """
    try:
        logger.info("📥 Fathom webhook received")
        
        # Get headers for signature verification
        timestamp = request.headers.get("x-fathom-timestamp") or request.headers.get("X-Fathom-Timestamp")
        signature = request.headers.get("x-fathom-signature") or request.headers.get("X-Fathom-Signature")
        
        logger.info(f"   Timestamp: {timestamp}")
        logger.info(f"   Signature: {'Present' if signature else 'Missing'}")
        
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify webhook signature
        if timestamp and signature:
            is_valid = fathom_handler.verify_webhook_signature(body, timestamp, signature)
            
            if not is_valid:
                logger.error("❌ Webhook signature verification failed")
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
        else:
            logger.warning("⚠️ No signature headers - verification skipped")
        
        # Parse webhook data
        webhook_data = json.loads(body.decode('utf-8'))
        
        event_type = webhook_data.get('event_type', 'unknown')
        meeting_id = webhook_data.get('meeting_id')
        
        logger.info(f"   Event type: {event_type}")
        logger.info(f"   Meeting ID: {meeting_id}")
        
        # Only process meeting.ended events
        if event_type != 'meeting.ended':
            logger.info(f"⏭️ Ignoring event type: {event_type}")
            return WebhookResponse(
                success=True,
                message=f"Event type {event_type} ignored"
            )
        
        if not meeting_id:
            logger.error("❌ No meeting_id in webhook")
            raise HTTPException(status_code=400, detail="Missing meeting_id")
        
        # Queue background processing
        # This allows us to return immediately to Fathom
        background_tasks.add_task(
            process_meeting_webhook,
            meeting_id,
            webhook_data
        )
        
        logger.info(f"✅ Meeting {meeting_id} queued for processing")
        
        return WebhookResponse(
            success=True,
            meeting_id=meeting_id,
            message="Meeting queued for processing"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

async def process_meeting_webhook(meeting_id: str, webhook_data: Dict[str, Any]):
    """
    Background task to process meeting webhook
    This runs asynchronously after webhook returns
    
    Steps:
    1. Fetch meeting details + transcript from Fathom
    2. Generate AI summary using Claude
    3. Store everything in PostgreSQL
    """
    try:
        logger.info(f"🔄 Processing meeting: {meeting_id}")
        
        # Step 1: Fetch complete meeting data from Fathom API
        logger.info("   📥 Fetching meeting data from Fathom...")
        meeting_data = await fathom_handler.get_complete_meeting_data(meeting_id)
        
        # Check for errors
        if 'error' in meeting_data.get('details', {}):
            logger.error(f"❌ Failed to fetch meeting details: {meeting_data['details']['error']}")
            return
        
        if 'error' in meeting_data.get('transcript', {}):
            logger.error(f"❌ Failed to fetch transcript: {meeting_data['transcript']['error']}")
            return
        
        # Step 2: Generate AI summary using Claude
        logger.info("   🤖 Generating AI summary with Claude...")
        summary_data = await meeting_processor.generate_summary(meeting_data)
        
        # Check for processing errors
        if 'error' in summary_data:
            logger.error(f"❌ AI summary generation failed: {summary_data['error']}")
            # Continue anyway - we can store meeting without summary
        
        # Step 3: Store in database
        logger.info("   💾 Storing in database...")
        db_meeting_id = await database_manager.store_meeting(meeting_data, summary_data)
        
        logger.info(f"✅ Meeting processing complete: {db_meeting_id}")
        
    except Exception as e:
        logger.error(f"❌ Background processing failed for {meeting_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ============================================================================
# MEETING RETRIEVAL ENDPOINTS
# ============================================================================

@router.get("/meetings", response_model=MeetingListResponse)
async def get_recent_meetings(limit: int = Query(10, ge=1, le=50)):
    """
    Get recent meetings ordered by date
    
    Query params:
    - limit: Number of meetings to return (1-50, default 10)
    """
    try:
        meetings = await database_manager.get_recent_meetings(limit=limit)
        
        return MeetingListResponse(
            meetings=meetings,
            total=len(meetings)
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get meetings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meetings/{meeting_id}")
async def get_meeting_by_id(meeting_id: str):
    """
    Get complete details for a specific meeting
    
    Returns:
    - Meeting metadata
    - AI summary
    - Action items
    - Topics
    - Full transcript
    """
    try:
        meeting = await database_manager.get_meeting_by_id(meeting_id)
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        return meeting
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_meetings(search_request: MeetingSearchRequest):
    """
    Search meetings by keywords
    
    Searches across:
    - Meeting titles
    - AI summaries
    - Key points
    - Full transcripts
    
    Uses PostgreSQL full-text search for best results
    """
    try:
        results = await database_manager.search_meetings(
            query_text=search_request.query,
            limit=search_request.limit
        )
        
        return {
            "query": search_request.query,
            "results": results,
            "total": len(results)
        }
        
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meetings/date-range")
async def get_meetings_by_date(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Get meetings within a date range
    
    Query params:
    - start_date: Start date in YYYY-MM-DD format
    - end_date: End date in YYYY-MM-DD format
    """
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        meetings = await database_manager.get_meetings_by_date_range(start, end)
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "meetings": meetings,
            "total": len(meetings)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"❌ Failed to get meetings by date: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ACTION ITEMS ENDPOINTS
# ============================================================================

@router.get("/action-items")
async def get_pending_action_items(limit: int = Query(20, ge=1, le=100)):
    """
    Get all pending action items across all meetings
    
    Returns action items with:
    - Task description
    - Assigned person
    - Due date
    - Priority
    - Associated meeting info
    """
    try:
        items = await database_manager.get_pending_action_items(limit=limit)
        
        return {
            "action_items": items,
            "total": len(items)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get action items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action-items/update")
async def update_action_item(update_request: ActionItemUpdateRequest):
    """
    Update action item status
    
    Valid statuses:
    - pending
    - completed
    - cancelled
    """
    try:
        valid_statuses = ['pending', 'completed', 'cancelled']
        
        if update_request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        success = await database_manager.update_action_item_status(
            item_id=update_request.item_id,
            status=update_request.status
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Action item not found")
        
        return {
            "success": True,
            "item_id": update_request.item_id,
            "new_status": update_request.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update action item: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STATUS & HEALTH CHECK
# ============================================================================

@router.get("/status")
async def get_integration_status():
    """
    Get Fathom integration status and health information
    
    Returns:
    - Database connectivity
    - Recent activity
    - Configuration status
    - Statistics
    """
    try:
        # Get database health
        db_health = await database_manager.health_check()
        
        # Get statistics
        stats = await database_manager.get_meeting_statistics()
        
        # Check configuration
        import os
        config_status = {
            'api_key_configured': bool(os.getenv('FATHOM_API_KEY')),
            'webhook_secret_configured': bool(os.getenv('FATHOM_WEBHOOK_SECRET')),
            'claude_configured': bool(os.getenv('ANTHROPIC_API_KEY'))
        }
        
        return {
            'integration': 'fathom_meetings',
            'version': '1.0.0',
            'healthy': db_health.get('database_connected', False),
            'database': db_health,
            'configuration': config_status,
            'statistics': stats,
            'endpoints': {
                'webhook': '/integrations/fathom/webhook',
                'meetings': '/integrations/fathom/meetings',
                'search': '/integrations/fathom/search',
                'action_items': '/integrations/fathom/action-items'
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        return {
            'integration': 'fathom_meetings',
            'healthy': False,
            'error': str(e)
        }

# ============================================================================
# STARTUP EVENT
# ============================================================================

@router.on_event("startup")
async def startup_fathom_integration():
    """Initialize Fathom integration on startup"""
    logger.info("🎙️ Fathom meeting integration starting up...")
    
    try:
        # Test database connectivity
        health = await database_manager.health_check()
        
        if health.get('database_connected'):
            logger.info("✅ Database connected")
            logger.info(f"   Total meetings: {health.get('total_meetings', 0)}")
        else:
            logger.error("❌ Database connection failed")
        
        # Log configuration status
        import os
        logger.info("Configuration:")
        logger.info(f"   API Key: {'✅' if os.getenv('FATHOM_API_KEY') else '❌'}")
        logger.info(f"   Webhook Secret: {'✅' if os.getenv('FATHOM_WEBHOOK_SECRET') else '❌'}")
        logger.info(f"   Claude API: {'✅' if os.getenv('ANTHROPIC_API_KEY') else '❌'}")
        
        logger.info("🎉 Fathom integration ready!")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")