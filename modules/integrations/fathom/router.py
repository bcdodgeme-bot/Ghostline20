# modules/integrations/fathom/router.py
"""
Fathom Integration FastAPI Router
Handles webhooks from Fathom and provides API endpoints for meeting access

UPDATED: 2025-12-19 - Proactive Engine Integration
- Full meeting summary in notifications (NO TRUNCATION!)
- Action buttons: Copy to Slack, Create Tasks, Done
- Action items tracked in meeting_action_items table
- Uses unified_proactive_queue for consistent handling

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
5. Process through Unified Proactive Engine
6. Send FULL notification with action buttons
"""

import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

from .fathom_handler import FathomHandler
from .meeting_processor import MeetingProcessor
from .database_manager import FathomDatabaseManager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/integrations/fathom", tags=["Fathom Meetings"])

# ============================================================================
# LAZY INITIALIZATION PATTERN
# ============================================================================

_fathom_handler: Optional[FathomHandler] = None
_meeting_processor: Optional[MeetingProcessor] = None
_database_manager: Optional[FathomDatabaseManager] = None


def get_fathom_handler() -> FathomHandler:
    """Get or create FathomHandler singleton"""
    global _fathom_handler
    if _fathom_handler is None:
        _fathom_handler = FathomHandler()
    return _fathom_handler


def get_meeting_processor() -> MeetingProcessor:
    """Get or create MeetingProcessor singleton"""
    global _meeting_processor
    if _meeting_processor is None:
        _meeting_processor = MeetingProcessor()
    return _meeting_processor


def get_database_manager() -> FathomDatabaseManager:
    """Get or create FathomDatabaseManager singleton"""
    global _database_manager
    if _database_manager is None:
        _database_manager = FathomDatabaseManager()
    return _database_manager


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
        logger.info("=" * 80)
        logger.info("📥 FATHOM WEBHOOK RECEIVED")
        logger.info("=" * 80)
        
        # Log ALL headers
        logger.info("🔍 ALL REQUEST HEADERS:")
        for header_name, header_value in request.headers.items():
            logger.info(f"   {header_name}: {header_value}")
        
        # Get headers for signature verification
        timestamp = request.headers.get("x-fathom-timestamp") or request.headers.get("X-Fathom-Timestamp")
        signature = request.headers.get("x-fathom-signature") or request.headers.get("X-Fathom-Signature")
        
        logger.info(f"\n🔐 SIGNATURE INFO:")
        logger.info(f"   Timestamp: {timestamp}")
        logger.info(f"   Signature: {'Present' if signature else 'Missing'}")
        
        # Get raw body
        body = await request.body()
        
        # Try to parse as JSON
        try:
            webhook_data = json.loads(body.decode('utf-8'))
            logger.info(f"\n✅ JSON PARSED SUCCESSFULLY")
            logger.info(f"   Top-level keys: {list(webhook_data.keys())}")
            logger.info(f"\n📋 FULL WEBHOOK DATA:")
            logger.info(json.dumps(webhook_data, indent=2, default=str))
        except json.JSONDecodeError as e:
            logger.error(f"\n❌ JSON PARSE FAILED: {e}")
            logger.error(f"   Raw body: {body.decode('utf-8', errors='ignore')}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Verify webhook signature (if present)
        if timestamp and signature:
            fathom_handler = get_fathom_handler()
            is_valid = fathom_handler.verify_webhook_signature(body, timestamp, signature)
            if not is_valid:
                logger.error("❌ Webhook signature verification failed")
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
            logger.info("✅ Signature verified")
        else:
            logger.warning("⚠️ No signature headers - verification skipped")
        
        # Try multiple possible field names for event type
        event_type = (
            webhook_data.get('event_type') or
            webhook_data.get('event') or
            webhook_data.get('type') or
            webhook_data.get('action') or
            'unknown'
        )
        
        # Try multiple possible field names for meeting/recording ID
        meeting_id = (
            webhook_data.get('recording_id') or
            webhook_data.get('meeting_id') or
            webhook_data.get('call_id') or
            webhook_data.get('id')
        )
        
        # Convert to string if it's an integer
        if meeting_id:
            meeting_id = str(meeting_id)
                
        logger.info(f"\n🎯 EXTRACTED DATA:")
        logger.info(f"   Event type: {event_type}")
        logger.info(f"   Meeting ID: {meeting_id}")
        
        # For now, let's accept ANY event and try to process it
        if not meeting_id:
            logger.error("❌ No meeting/recording ID found in webhook")
            logger.error(f"   Available keys: {list(webhook_data.keys())}")
            # Still return success to avoid webhook retries
            return WebhookResponse(
                success=True,
                message="No meeting ID found - webhook logged for debugging"
            )
        
        # Queue background processing for ANY webhook with an ID
        logger.info(f"\n🚀 QUEUING BACKGROUND PROCESSING")
        logger.info(f"   Meeting ID: {meeting_id}")
        logger.info(f"   Event type: {event_type}")
        
        background_tasks.add_task(
            process_meeting_webhook,
            meeting_id,
            webhook_data
        )
        
        logger.info(f"✅ Meeting {meeting_id} queued for processing")
        logger.info("=" * 80)
        
        return WebhookResponse(
            success=True,
            meeting_id=meeting_id,
            message=f"Meeting {meeting_id} queued for processing"
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKGROUND PROCESSING - NOW WITH PROACTIVE ENGINE
# ============================================================================

async def process_meeting_webhook(meeting_id: str, webhook_data: Dict[str, Any]):
    """
    Background task to process meeting webhook
    
    UPDATED: Now uses Unified Proactive Engine for:
    - FULL summary in notification (NO TRUNCATION!)
    - Action buttons (Copy to Slack, Create Tasks, Done)
    - Proper action item tracking
    
    Steps:
    1. Extract data from webhook payload
    2. Generate AI summary using Claude
    3. Store everything in PostgreSQL
    4. Process through Proactive Engine (sends notification with buttons)
    """
    try:
        logger.info(f"🔄 Processing meeting: {meeting_id}")
        
        # Get handler instances via lazy initialization
        meeting_processor = get_meeting_processor()
        database_manager = get_database_manager()
        
        # Step 1: Use webhook data directly (it has everything we need!)
        logger.info("   📦 Using data from webhook payload...")
        
        # Format the webhook data into the structure our code expects
        meeting_data = {
            'recording_id': webhook_data.get('recording_id'),
            'fetched_at': datetime.now().isoformat(),
            'details': {
                'id': webhook_data.get('recording_id'),
                'title': webhook_data.get('title') or webhook_data.get('meeting_title', 'Untitled Meeting'),
                'start_time': webhook_data.get('recording_start_time'),
                'end_time': webhook_data.get('recording_end_time'),
                'duration': 0,  # Will calculate from times
                'attendees': [
                    {'name': inv.get('name') or inv.get('email', 'Unknown')}
                    for inv in webhook_data.get('calendar_invitees', [])
                ],
                'url': webhook_data.get('url'),
                'share_url': webhook_data.get('share_url')
            },
            'transcript': {
                'transcript': webhook_data.get('transcript', '')  # Already formatted text
            }
        }
        
        logger.info(f"   ✅ Extracted: {meeting_data['details']['title']}")
        logger.info(f"   📄 Transcript: {len(meeting_data['transcript']['transcript'])} chars")
        
        # Step 2: Generate AI summary using Claude
        logger.info("   🤖 Generating AI summary with Claude...")
        summary_data = await meeting_processor.generate_summary(meeting_data)
        
        # Check for processing errors
        if 'error' in summary_data:
            logger.error(f"❌ AI summary generation failed: {summary_data['error']}")
            # Continue anyway - we can store meeting without summary
        else:
            logger.info("   ✅ AI summary generated")
            logger.info(f"      Summary: {len(summary_data.get('summary', ''))} chars")
            logger.info(f"      Key points: {len(summary_data.get('key_points', []))}")
            logger.info(f"      Action items: {len(summary_data.get('action_items', []))}")
        
        # Step 3: Store in database
        logger.info("   💾 Storing in database...")
        db_meeting_id = await database_manager.store_meeting(meeting_data, summary_data)
        
        logger.info(f"✅ Meeting stored: {db_meeting_id}")
        
        # Step 4: Process through Unified Proactive Engine
        # This sends the FULL notification with action buttons
        try:
            logger.info("   🚀 Processing through Proactive Engine...")
            
            from modules.proactive.unified_engine import get_unified_engine
            
            engine = get_unified_engine()
            queue_id = await engine.process_meeting(meeting_data, summary_data)
            
            if queue_id:
                logger.info(f"   ✅ Proactive notification sent: {queue_id}")
            else:
                logger.warning("   ⚠️ Proactive processing returned no queue ID")
                # Fall back to legacy notification
                await _send_legacy_notification(meeting_data, summary_data)
                
        except ImportError as e:
            logger.warning(f"   ⚠️ Proactive engine not available: {e}")
            # Fall back to legacy notification (but with full content!)
            await _send_legacy_notification(meeting_data, summary_data)
        except Exception as e:
            logger.error(f"   ❌ Proactive engine error: {e}")
            # Fall back to legacy notification
            await _send_legacy_notification(meeting_data, summary_data)
        
        logger.info(f"✅ Meeting processing complete: {meeting_id}")
        
    except Exception as e:
        logger.error(f"❌ Background processing failed for {meeting_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def _send_legacy_notification(meeting_data: Dict[str, Any], summary_data: Dict[str, Any]):
    """
    Fallback notification if proactive engine isn't available.
    UPDATED: Now sends FULL content, not truncated!
    """
    try:
        logger.info("   📱 Sending legacy Telegram notification (full content)...")
        
        from modules.integrations.telegram.bot_client import get_bot_client
        from modules.integrations.telegram.kill_switch import get_kill_switch
        from modules.integrations.telegram.notification_manager import NotificationManager
        
        telegram_bot = get_bot_client()
        kill_switch = get_kill_switch()
        notification_manager = NotificationManager(telegram_bot, kill_switch)
        
        # Extract meeting details for notification
        title = meeting_data['details']['title']
        meeting_date = meeting_data['details'].get('start_time', 'Date unknown')
        attendees = [a.get('name', 'Unknown') for a in meeting_data['details'].get('attendees', [])]
        
        # Build notification message - FULL CONTENT!
        message_parts = []
        message_parts.append("🎙️ *Meeting Summary Ready*")
        message_parts.append("")
        message_parts.append(f"*{title}*")
        message_parts.append(f"📅 {meeting_date}")
        
        if attendees:
            attendees_str = ', '.join(attendees[:5])
            if len(attendees) > 5:
                attendees_str += f" +{len(attendees) - 5} more"
            message_parts.append(f"👥 {attendees_str}")
        
        message_parts.append("")
        message_parts.append("━━━━━━━━━━━━━━━━━━━━━━━")
        message_parts.append("")
        
        # FULL SUMMARY - NO TRUNCATION!
        if summary_data.get('summary'):
            message_parts.append("📋 *Summary:*")
            message_parts.append(summary_data['summary'])  # FULL TEXT!
            message_parts.append("")
        
        # Key points - ALL OF THEM
        if summary_data.get('key_points'):
            message_parts.append("📌 *Key Points:*")
            for point in summary_data['key_points']:
                message_parts.append(f"• {point}")
            message_parts.append("")
        
        # Action items - ALL OF THEM with priority
        if summary_data.get('action_items'):
            message_parts.append("✅ *Action Items:*")
            for item in summary_data['action_items']:
                if isinstance(item, dict):
                    task = item.get('text', str(item))
                    priority = item.get('priority', 'medium')
                    priority_marker = "🔴" if priority == "high" else "🟡" if priority == "medium" else "⚪"
                    assigned = item.get('assigned_to')
                    if assigned:
                        message_parts.append(f"{priority_marker} {task} → {assigned}")
                    else:
                        message_parts.append(f"{priority_marker} {task}")
                else:
                    message_parts.append(f"• {item}")
            message_parts.append("")
        
        # Decisions made
        if summary_data.get('decisions_made'):
            message_parts.append("🎯 *Decisions Made:*")
            for decision in summary_data['decisions_made']:
                message_parts.append(f"• {decision}")
            message_parts.append("")
        
        # Join all parts into final message
        notification_text = "\n".join(message_parts)
        
        # Create action buttons
        buttons = [
            [
                {"text": "📋 Copy to Slack", "callback_data": f"meeting:copy:{meeting_data['recording_id']}"},
                {"text": "📝 Create Tasks", "callback_data": f"meeting:tasks:{meeting_data['recording_id']}"}
            ],
            [
                {"text": "✅ Done", "callback_data": f"meeting:done:{meeting_data['recording_id']}"}
            ]
        ]
        
        # Add link to recording if available
        share_url = meeting_data['details'].get('share_url')
        if share_url:
            buttons[1].insert(0, {"text": "🔗 View Recording", "url": share_url})
        
        # Send notification with buttons
        result = await notification_manager.send_notification(
            user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
            notification_type="fathom",
            notification_subtype="meeting_processed",
            message_text=notification_text,
            buttons=buttons
        )
        
        if result.get('success'):
            logger.info("   ✅ Telegram notification sent successfully (full content)")
        else:
            logger.warning(f"   ⚠️ Telegram notification failed: {result.get('error')}")
            
    except Exception as telegram_error:
        # Don't fail the whole process if Telegram fails
        logger.error(f"   ❌ Telegram notification error: {telegram_error}")
        logger.info("   ℹ️ Meeting still processed successfully, only notification failed")


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
        database_manager = get_database_manager()
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
        database_manager = get_database_manager()
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
        database_manager = get_database_manager()
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
        
        database_manager = get_database_manager()
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
        database_manager = get_database_manager()
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
        
        database_manager = get_database_manager()
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
        database_manager = get_database_manager()
        
        # Get database health
        db_health = await database_manager.health_check()
        
        # Get statistics
        stats = await database_manager.get_meeting_statistics()
        
        # Check configuration
        config_status = {
            'api_key_configured': bool(os.getenv('FATHOM_API_KEY')),
            'webhook_secret_configured': bool(os.getenv('FATHOM_WEBHOOK_SECRET')),
            'claude_configured': bool(os.getenv('ANTHROPIC_API_KEY')),
            'proactive_engine_available': _check_proactive_engine()
        }
        
        return {
            'integration': 'fathom_meetings',
            'version': '2.0.0',  # Updated version
            'healthy': db_health.get('database_connected', False),
            'database': db_health,
            'configuration': config_status,
            'statistics': stats,
            'features': {
                'full_summary_notifications': True,
                'action_buttons': True,
                'action_item_tracking': True,
                'proactive_engine': config_status['proactive_engine_available']
            },
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


def _check_proactive_engine() -> bool:
    """Check if proactive engine is available"""
    try:
        from modules.proactive.unified_engine import get_unified_engine
        return True
    except ImportError:
        return False


# ============================================================================
# STARTUP EVENT
# ============================================================================

@router.on_event("startup")
async def startup_fathom_integration():
    """Initialize Fathom integration on startup"""
    logger.info("🎙️ Fathom meeting integration starting up...")
    
    try:
        # Get database manager (lazy init happens here)
        database_manager = get_database_manager()
        
        # Test database connectivity
        health = await database_manager.health_check()
        
        if health.get('database_connected'):
            logger.info("✅ Database connected")
            logger.info(f"   Total meetings: {health.get('total_meetings', 0)}")
        else:
            logger.error("❌ Database connection failed")
        
        # Log configuration status
        logger.info("Configuration:")
        logger.info(f"   API Key: {'✅' if os.getenv('FATHOM_API_KEY') else '❌'}")
        logger.info(f"   Webhook Secret: {'✅' if os.getenv('FATHOM_WEBHOOK_SECRET') else '❌'}")
        logger.info(f"   Claude API: {'✅' if os.getenv('ANTHROPIC_API_KEY') else '❌'}")
        logger.info(f"   Proactive Engine: {'✅' if _check_proactive_engine() else '❌ (fallback mode)'}")
        
        logger.info("🎉 Fathom integration ready!")
        logger.info("   ✨ Full summaries enabled (no truncation)")
        logger.info("   ✨ Action buttons enabled")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
