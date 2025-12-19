# modules/integrations/telegram/router.py
"""
Telegram FastAPI Router
=======================
Provides endpoints for:
- Webhook receiving (Telegram sends updates here)
- Webhook management (set/delete/status)
- Bot status and testing

Webhook URL: https://ghostline20-production.up.railway.app/telegram/webhook

Created: 2025-12-19
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from ...core.auth import get_current_user
from .bot_client import get_bot_client
from .telegram_webhook import process_telegram_update, get_webhook_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])

# Default webhook URL
DEFAULT_WEBHOOK_URL = "https://ghostline20-production.up.railway.app/telegram/webhook"


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WebhookSetRequest(BaseModel):
    """Request to set webhook URL"""
    url: Optional[str] = None  # If None, uses default Railway URL
    drop_pending_updates: bool = False


# ============================================================================
# WEBHOOK ENDPOINT - Receives updates from Telegram
# ============================================================================

@router.post("/webhook")
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    """
    Receive webhook updates from Telegram.
    
    This is the endpoint Telegram sends updates to when:
    - A user clicks an inline button (callback_query)
    - A user sends a message to the bot
    - Other subscribed events occur
    
    NO AUTHENTICATION - Telegram must be able to reach this endpoint.
    We validate the update structure instead.
    """
    try:
        # Parse the incoming update
        update = await request.json()
        
        # Basic validation - must have update_id
        if 'update_id' not in update:
            logger.warning("Invalid webhook payload - missing update_id")
            return {"ok": True, "error": "Invalid payload"}
        
        # Process the update
        result = await process_telegram_update(update)
        
        # Always return 200 OK to Telegram (even on errors)
        # Otherwise Telegram will keep retrying
        return {"ok": True, "result": result}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        # Still return 200 to prevent Telegram from retrying
        return {"ok": True, "error": str(e)}


# ============================================================================
# WEBHOOK MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/webhook/set")
async def set_webhook(
    request: WebhookSetRequest = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Set the Telegram webhook URL.
    
    If no URL provided, uses the default Railway URL:
    https://ghostline20-production.up.railway.app/telegram/webhook
    """
    try:
        bot_client = get_bot_client()
        
        # Use provided URL or default
        webhook_url = DEFAULT_WEBHOOK_URL
        if request and request.url:
            webhook_url = request.url
        
        drop_pending = request.drop_pending_updates if request else False
        
        result = await bot_client.set_webhook(
            url=webhook_url,
            drop_pending_updates=drop_pending
        )
        
        if result.get('success'):
            return {
                "success": True,
                "message": f"Webhook set successfully",
                "webhook_url": webhook_url
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set webhook: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/webhook")
async def delete_webhook(
    drop_pending_updates: bool = False,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Delete the Telegram webhook (switch to polling mode).
    
    Args:
        drop_pending_updates: Whether to drop any pending updates
    """
    try:
        bot_client = get_bot_client()
        result = await bot_client.delete_webhook(drop_pending_updates=drop_pending_updates)
        
        if result.get('success'):
            return {
                "success": True,
                "message": "Webhook deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete webhook: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/status")
async def get_webhook_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current webhook status and info.
    """
    try:
        bot_client = get_bot_client()
        result = await bot_client.get_webhook_info()
        
        webhook_url = result.get('webhook_url', '')
        is_set = bool(webhook_url)
        
        return {
            "success": True,
            "webhook_configured": is_set,
            "webhook_url": webhook_url or None,
            "pending_update_count": result.get('pending_update_count', 0),
            "expected_url": DEFAULT_WEBHOOK_URL,
            "status": "active" if webhook_url == DEFAULT_WEBHOOK_URL else (
                "custom" if is_set else "not_configured"
            ),
            "raw_info": result.get('result', {})
        }
        
    except Exception as e:
        logger.error(f"Error getting webhook status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BOT STATUS ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_bot_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get Telegram bot status and connection info.
    """
    try:
        bot_client = get_bot_client()
        
        # Test connection
        connection_result = await bot_client.test_connection()
        
        # Get webhook info
        webhook_info = await bot_client.get_webhook_info()
        
        bot_info = connection_result.get('bot_info', {})
        
        return {
            "success": True,
            "connected": connection_result.get('success', False),
            "bot": {
                "username": bot_info.get('username'),
                "first_name": bot_info.get('first_name'),
                "can_join_groups": bot_info.get('can_join_groups'),
                "can_read_all_group_messages": bot_info.get('can_read_all_group_messages'),
                "supports_inline_queries": bot_info.get('supports_inline_queries')
            },
            "webhook": {
                "configured": bool(webhook_info.get('webhook_url')),
                "url": webhook_info.get('webhook_url') or None,
                "pending_updates": webhook_info.get('pending_update_count', 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return {
            "success": False,
            "connected": False,
            "error": str(e)
        }


@router.post("/test")
async def test_bot_connection(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Test the Telegram bot connection.
    """
    try:
        bot_client = get_bot_client()
        result = await bot_client.test_connection()
        
        return {
            "success": result.get('success', False),
            "bot_info": result.get('bot_info'),
            "error": result.get('error')
        }
        
    except Exception as e:
        logger.error(f"Error testing bot connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MANUAL TRIGGER ENDPOINTS (For testing)
# ============================================================================

@router.post("/test-callback")
async def test_callback_handling(
    callback_data: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Test callback handling without going through Telegram.
    Useful for debugging.
    
    Args:
        callback_data: The callback_data string to test (e.g., "bsky:post:uuid")
    """
    try:
        handler = get_webhook_handler()
        
        # Simulate callback routing
        result = await handler._route_callback(
            callback_data=callback_data,
            user_id=0,  # Fake user ID
            chat_id=0,  # Fake chat ID
            message_id=0  # Fake message ID
        )
        
        return {
            "success": True,
            "callback_data": callback_data,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error testing callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for Telegram integration.
    No authentication required.
    """
    try:
        bot_client = get_bot_client()
        connection = await bot_client.test_connection()
        
        return {
            "status": "healthy" if connection.get('success') else "degraded",
            "bot_connected": connection.get('success', False),
            "webhook_handler": "ready"
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = ['router']
