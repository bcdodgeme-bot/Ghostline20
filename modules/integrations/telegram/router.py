"""
Telegram Router - FastAPI Webhook Endpoints
Handles incoming webhooks from Telegram for button callbacks and commands
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any

from .callback_handler import get_callback_handler
from .kill_switch import get_kill_switch
from .notification_manager import get_notification_manager

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
            callback_query = data['callback_query']
            callback_handler = get_callback_handler()
            
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
    command_lower = command.lower().strip()
    user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"  # Your user ID
    
    kill_switch = get_kill_switch()
    
    # Global kill switch
    if 'kill' in command_lower or 'stop all' in command_lower:
        await kill_switch.activate_global_kill(user_id, "User command via Telegram")
        return "🛑 All notifications stopped. Use 'telegram resume' to re-enable."
    
    # Resume notifications
    elif 'resume' in command_lower or 'enable' in command_lower:
        if 'disable' not in command_lower:  # Avoid confusion with "enable [type]"
            await kill_switch.deactivate_global_kill(user_id)
            return "✅ Notifications resumed."
    
    # Disable specific type
    elif 'disable' in command_lower:
        # Extract type from command
        types = ['prayer', 'weather', 'reminders', 'calendar', 'email', 
                'clickup', 'bluesky', 'trends', 'analytics']
        
        for notif_type in types:
            if notif_type in command_lower:
                await kill_switch.kill_notification_type(user_id, notif_type)
                return f"✅ {notif_type.title()} notifications disabled."
        
        return "❓ Specify notification type to disable (prayer, weather, reminders, etc.)"
    
    # Enable specific type
    elif 'enable' in command_lower:
        types = ['prayer', 'weather', 'reminders', 'calendar', 'email',
                'clickup', 'bluesky', 'trends', 'analytics']
        
        for notif_type in types:
            if notif_type in command_lower:
                await kill_switch.revive_notification_type(user_id, notif_type)
                return f"✅ {notif_type.title()} notifications enabled."
        
        return "❓ Specify notification type to enable (prayer, weather, reminders, etc.)"
    
    # Status check
    elif 'status' in command_lower:
        status = await kill_switch.get_status(user_id)
        notification_manager = get_notification_manager()
        rate_limits = await notification_manager.get_rate_limit_status(user_id)
        
        # Build status message
        if status['global_kill_active']:
            msg = "🛑 **All notifications STOPPED**\n\n"
            msg += f"Reason: {status.get('activated_reason', 'Manual stop')}\n"
            msg += "Use 'telegram resume' to re-enable."
        else:
            msg = "✅ **Notifications Active**\n\n"
            
            if status['killed_types']:
                msg += "**Disabled Types:**\n"
                for t in status['killed_types']:
                    msg += f"  • {t.title()}\n"
                msg += "\n"
            
            msg += "**Rate Limits (24h):**\n"
            for notif_type, limits in rate_limits.items():
                if limits['count'] > 0:
                    msg += f"  • {notif_type.title()}: {limits['count']}/{limits['limit']}\n"
        
        return msg
    
    return "❓ Unknown command. Try: kill, resume, disable [type], enable [type], status"

# ============================================================================
# MANUAL NOTIFICATION ENDPOINTS (For Testing)
# ============================================================================

@router.post("/test/send")
async def send_test_notification():
    """Send a test notification to verify system is working"""
    try:
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
        user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
        kill_switch = get_kill_switch()
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