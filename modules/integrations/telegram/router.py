"""
Telegram Router - FastAPI Webhook Endpoints
Handles incoming webhooks from Telegram for button callbacks and commands
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])

# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receive updates from Telegram
    This endpoint receives button clicks, commands, etc.
    """
    try:
        data = await request.json()
        logger.info(f"Received Telegram webhook: {data.get('update_id')}")
        
        # Handle callback queries (button clicks)
        if 'callback_query' in data:
            from .callback_handler import get_callback_handler
            callback_query = data['callback_query']
            callback_handler = get_callback_handler()  # Use the getter function!
            
            result = await callback_handler.process_callback(
                callback_query_id=callback_query['id'],
                callback_data=callback_query['data'],
                message_id=callback_query['message']['message_id']
            )
            
            return {"success": result['success']}
        
        # Handle text messages (commands)
        elif 'message' in data:
            message = data['message']
            text = message.get('text', '')
            
            # Process telegram commands (kill switch, etc.)
            if text.lower().startswith('telegram'):
                response = await process_telegram_command(text)
                return {"success": True, "response": response}
        
        return {"success": True}
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# COMMAND PROCESSING
# ============================================================================

async def process_telegram_command(command: str) -> str:
    """
    Process telegram control commands
    
    Commands:
        - telegram kill / telegram stop
        - telegram resume / telegram enable
        - telegram disable [type]
        - telegram enable [type]
        - telegram status
    """
    from .kill_switch import KillSwitch
    from .notification_manager import get_notification_manager
    
    command_lower = command.lower().strip()
    user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"  # Your user ID
    
    kill_switch = KillSwitch()
    
    # Global kill switch
    if 'kill' in command_lower or 'stop all' in command_lower:
        await kill_switch.disable(user_id, "User command via Telegram")
        return "🛑 All notifications stopped. Use 'telegram resume' to re-enable."
    
    # Resume notifications
    elif 'resume' in command_lower or ('enable' in command_lower and 'disable' not in command_lower):
        await kill_switch.enable(user_id)
        return "✅ Notifications resumed."
    
    # Status check
    elif 'status' in command_lower:
        status = await kill_switch.get_status(user_id)
        notification_manager = get_notification_manager()
        rate_limits = await notification_manager.get_rate_limit_status(user_id)
        
        # Build status message
        if not status['enabled']:
            msg = "🛑 **All notifications STOPPED**\n\n"
            msg += f"Reason: {status.get('reason', 'Manual stop')}\n"
            msg += "Use 'telegram resume' to re-enable."
        else:
            msg = "✅ **Notifications Active**\n\n"
            msg += "**Rate Limits (24h):**\n"
            for notif_type, limits in rate_limits.items():
                if limits['count'] > 0:
                    msg += f"  • {notif_type.title()}: {limits['count']}/{limits['limit']}\n"
        
        return msg
    
    return "❓ Unknown command. Try: kill, resume, status"

# ============================================================================
# MANUAL NOTIFICATION ENDPOINTS (For Testing)
# ============================================================================

@router.post("/test/send")
async def send_test_notification():
    """Send a test notification to verify system is working"""
    try:
        from .notification_manager import get_notification_manager
        
        notification_manager = get_notification_manager()
        
        result = await notification_manager.send_notification(
            user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
            notification_type="reminders",
            notification_subtype="test",
            message_text="🧪 **Test Notification**\n\nTelegram notification system is working!",
            buttons=[[
                {"text": "✅ Got it", "callback_data": "reminder:done:test"}
            ]],
            message_data={"test": True}
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def health_check():
    """Check Telegram integration health"""
    try:
        from .bot_client import get_bot_client
        
        bot_client = get_bot_client()
        connection_test = await bot_client.test_connection()
        
        return {
            "success": True,
            "status": "healthy" if connection_test['success'] else "unhealthy",
            "bot_info": connection_test.get('bot_info', {}),
            "endpoints": {
                "webhook": "/telegram/webhook",
                "test": "/telegram/test/send",
                "health": "/telegram/health"
            }
        }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }

# ============================================================================
# STATUS ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_notification_status():
    """Get current notification system status"""
    try:
        from .kill_switch import KillSwitch
        from .notification_manager import get_notification_manager
        
        user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
        kill_switch = KillSwitch()
        notification_manager = get_notification_manager()
        
        status = await kill_switch.get_status(user_id)
        rate_limits = await notification_manager.get_rate_limit_status(user_id)
        
        return {
            "success": True,
            "kill_switch": status,
            "rate_limits": rate_limits
        }
    
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
