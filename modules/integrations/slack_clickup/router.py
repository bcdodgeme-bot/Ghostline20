"""
Slack-ClickUp Integration Router with Enhanced Debug Logging
API endpoints for webhook handling and manual commands

Updated: Session 13 - Converted to lazy initialization with singleton getters
"""
import os
import json
import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from typing import Dict, Optional

from .slack_handler import SlackHandler
from .clickup_handler import ClickUpHandler
from .task_mapper import TaskMapper

#-- Section 1: Router Initialization & Singleton Getters
router = APIRouter(prefix="/integrations/slack-clickup", tags=["slack-clickup"])
logger = logging.getLogger(__name__)

# Singleton instances (lazy initialization)
_slack_handler: Optional[SlackHandler] = None
_clickup_handler: Optional[ClickUpHandler] = None
_task_mapper: Optional[TaskMapper] = None


def get_slack_handler() -> SlackHandler:
    """Get singleton SlackHandler instance"""
    global _slack_handler
    if _slack_handler is None:
        _slack_handler = SlackHandler()
    return _slack_handler


def get_clickup_handler() -> ClickUpHandler:
    """Get singleton ClickUpHandler instance"""
    global _clickup_handler
    if _clickup_handler is None:
        _clickup_handler = ClickUpHandler()
    return _clickup_handler


def get_task_mapper() -> TaskMapper:
    """Get singleton TaskMapper instance"""
    global _task_mapper
    if _task_mapper is None:
        _task_mapper = TaskMapper()
    return _task_mapper


#-- Section 2: Webhook Verification & Security with Debug Logging
async def verify_slack_request(request: Request) -> Dict:
    """Verify and parse incoming Slack webhook request with comprehensive debug logging"""
    
    slack_handler = get_slack_handler()
    
    logger.info(f"🔐 WEBHOOK VERIFICATION STARTED")
    
    # Get headers
    timestamp = request.headers.get("x-slack-request-timestamp") or request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("x-slack-signature") or request.headers.get("X-Slack-Signature")
    content_type = request.headers.get("content-type")
    
    
    logger.info(f"📋 Headers received:")
    logger.info(f"   ⏰ Timestamp: {timestamp}")
    logger.info(f"   🔏 Signature: {signature}")
    logger.info(f"   📄 Content-Type: {content_type}")
    
    if not timestamp or not signature:
        logger.error(f"❌ Missing required Slack headers")
        logger.error(f"   ⏰ Has timestamp: {bool(timestamp)}")
        logger.error(f"   🔏 Has signature: {bool(signature)}")
        raise HTTPException(status_code=401, detail="Missing Slack headers")
    
    # Get body
    body = await request.body()
    
    logger.info(f"📦 Body received: {len(body)} bytes")
    logger.info(f"📝 Body preview: {body[:200].decode(errors='ignore')}...")
    
    # Verify signature with debug logging
    logger.info(f"🔍 Verifying Slack signature...")
    verification_result = slack_handler.verify_request(body, timestamp, signature)
    logger.info(f"🔒 Signature verification result: {verification_result}")
    
    if not verification_result:
        logger.error(f"❌ SIGNATURE VERIFICATION FAILED!")
        logger.error(f"   🔑 Signing secret configured: {bool(slack_handler.signing_secret)}")
        logger.error(f"   ⏰ Timestamp: {timestamp}")
        logger.error(f"   🔏 Received signature: {signature}")
        
        # Let's also log what we computed for debugging
        try:
            from datetime import datetime as dt
            import hmac, hashlib
            current_time = int(dt.now().timestamp())
            timestamp_int = int(timestamp)
            time_diff = abs(current_time - timestamp_int)
            logger.error(f"   📅 Time difference: {time_diff} seconds (max allowed: 300)")
            
            sig_basestring = f"v0:{timestamp}:{body.decode()}"
            computed_hash = hmac.new(
                slack_handler.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256
            ).hexdigest()
            computed_signature = f"v0={computed_hash}"
            logger.error(f"   🧮 Computed signature: {computed_signature}")
            logger.error(f"   📊 Signatures match: {computed_signature == signature}")
        except Exception as debug_error:
            logger.error(f"   🚫 Debug signature computation failed: {debug_error}")
        
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    
    logger.info(f"✅ Signature verification passed!")
    
    # Parse body
    try:
        if content_type == "application/json":
            logger.info(f"📋 Parsing JSON body...")
            parsed_data = json.loads(body.decode())
            logger.info(f"✅ JSON parsed successfully")
            logger.info(f"📊 Data keys: {list(parsed_data.keys())}")
            return parsed_data
        else:
            logger.info(f"📋 Parsing URL-encoded body...")
            # URL-encoded form data
            from urllib.parse import parse_qs
            parsed = parse_qs(body.decode())
            parsed_data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            logger.info(f"✅ URL-encoded data parsed successfully")
            logger.info(f"📊 Data keys: {list(parsed_data.keys())}")
            return parsed_data
    except Exception as e:
        logger.error(f"❌ Body parsing failed: {e}")
        logger.error(f"📄 Content-Type: {content_type}")
        logger.error(f"📦 Body: {body[:500]}")
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")


#-- Section 3: Background Task Processing with Debug Logging
async def process_mention_task(message_data: Dict):
    """Background task to process Slack mentions with comprehensive debug logging"""
    
    task_mapper = get_task_mapper()
    clickup_handler = get_clickup_handler()
    slack_handler = get_slack_handler()
    
    logger.info(f"🔄 BACKGROUND TASK STARTED - Processing mention task")
    logger.info(f"📝 Message data received: {json.dumps(message_data, indent=2)}")
    
    try:
        # Extract task details with debug logging
        logger.info(f"🧩 Attempting to extract task from mention...")
        task_info = task_mapper.extract_mention_task(message_data)
        
        if not task_info:
            logger.warning("❌ Could not extract task from mention - task_info is None")
            logger.info(f"📄 Raw message text was: {message_data.get('text', 'NO_TEXT_FOUND')}")
            return
        
        logger.info(f"✅ Task info extracted successfully:")
        logger.info(f"   📋 Title: {task_info.get('title', 'NO_TITLE')}")
        logger.info(f"   📝 Description length: {len(task_info.get('description', ''))}")
        logger.info(f"   🏷️ Type: {task_info.get('type', 'NO_TYPE')}")
        
        # Create AMCF task (work-related, 3-day due date) with debug logging
        logger.info(f"🎯 Creating AMCF task in ClickUp...")
        result = await clickup_handler.create_amcf_task(
            title=task_info['title'],
            description=task_info['description']
        )
        
        if result:
            task_url = result.get('url', 'NO_URL')
            task_id = result.get('id', 'NO_ID')
            logger.info(f"🎉 AMCF task created successfully!")
            logger.info(f"   🆔 Task ID: {task_id}")
            logger.info(f"   🔗 Task URL: {task_url}")
            
            # Send confirmation back to Slack with debug logging
            channel_id = message_data.get('channel')
            thread_ts = message_data.get('ts')
            logger.info(f"📤 Sending Slack confirmation...")
            logger.info(f"   📺 Channel ID: {channel_id}")
            logger.info(f"   🧵 Thread TS: {thread_ts}")
            
            try:
                await slack_handler.send_response(
                    channel_id=channel_id,
                    text=f"✅ Created AMCF task: {task_url}",
                    thread_ts=thread_ts
                )
                logger.info(f"✅ Slack confirmation sent successfully")
            except Exception as slack_error:
                logger.error(f"❌ Failed to send Slack confirmation: {slack_error}")
            
            logger.info(f"🏆 BACKGROUND TASK COMPLETED SUCCESSFULLY - Task: {task_id}")
        else:
            logger.error("❌ ClickUp task creation failed - result was None/False")
            logger.error("🔍 Check ClickUp API credentials and permissions")
            
    except Exception as e:
        logger.error(f"💥 BACKGROUND TASK EXCEPTION: {e}")
        logger.error(f"🔍 Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"📚 Full traceback: {traceback.format_exc()}")


async def process_command_task(command: str, context: str = ""):
    """Background task to process AI command tasks"""
    
    task_mapper = get_task_mapper()
    clickup_handler = get_clickup_handler()
    
    logger.info(f"🔄 Processing command task: {command}")
    
    try:
        # Extract task details
        task_info = task_mapper.extract_command_task(command, context)
        
        if not task_info:
            logger.warning("Could not extract task from command")
            return
        
        # Create personal task (5-day due date)
        result = await clickup_handler.create_personal_task(
            title=task_info['title'],
            description=task_info['description']
        )
        
        if result:
            logger.info(f"Created personal task: {result.get('id')}")
            return result
        else:
            logger.error("Failed to create personal task")
            return None
            
    except Exception as e:
        logger.error(f"Error processing command task: {e}")
        return None


#-- Section 4: Slack Webhook Endpoints with Debug Logging
@router.post("/slack/events")
async def handle_slack_events(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack Events API webhooks with enhanced debug logging"""
    
    slack_handler = get_slack_handler()
    
    # EMERGENCY DEBUG - This should ALWAYS show if endpoint is called
    print("🚨 EMERGENCY DEBUG: /slack/events endpoint called!")
    print(f"🚨 Request headers: {dict(request.headers)}")
    
    try:
        logger.info(f"🌐 WEBHOOK RECEIVED - Processing Slack event")
        
        data = await verify_slack_request(request)
        logger.info(f"📊 Webhook data type: {data.get('type', 'NO_TYPE')}")
        
        # Handle URL verification
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            logger.info(f"🔍 URL verification challenge: {challenge}")
            return {"challenge": challenge}
        
        # Handle event callbacks
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_type = event.get("type")
            logger.info(f"📨 Event callback type: {event_type}")
            
            # Handle app mentions with detailed logging
            if event_type == "app_mention":
                message_text = event.get("text", "")
                user = event.get("user", "")
                channel = event.get("channel", "")
                
                logger.info(f"👥 APP MENTION EVENT:")
                logger.info(f"   👤 From user: {user}")
                logger.info(f"   📺 In channel: {channel}")
                logger.info(f"   💬 Message text: {message_text}")
                logger.info(f"   🎯 Looking for user ID: {slack_handler.user_id}")
                
                # Check if our user is mentioned
                is_mentioned = slack_handler.is_user_mentioned(message_text)
                logger.info(f"   ✅ User mentioned result: {is_mentioned}")
                
                if is_mentioned:
                    logger.info(f"🚀 USER IS MENTIONED - Adding background task")
                    background_tasks.add_task(process_mention_task, event)
                    logger.info(f"✅ Background task added to queue")
                else:
                    logger.info(f"⏭️ User not mentioned, skipping task creation")
            
            # Handle regular messages that mention our user (main use case!)
            elif event_type == "message":
                message_text = event.get("text", "")
                user = event.get("user", "")
                channel = event.get("channel", "")
                channel_type = event.get("channel_type", "")
                
                logger.info(f"💬 MESSAGE EVENT:")
                logger.info(f"   👤 From user: {user}")
                logger.info(f"   📺 In channel: {channel}")
                logger.info(f"   🏷️ Channel type: {channel_type}")
                logger.info(f"   💬 Message text: {message_text}")
                logger.info(f"   🎯 Looking for user ID: {slack_handler.user_id}")
                
                # Check if our user is mentioned in the message
                is_mentioned = slack_handler.is_user_mentioned(message_text)
                logger.info(f"   ✅ User mentioned result: {is_mentioned}")
                
                if is_mentioned:
                    logger.info(f"🚀 USER MENTIONED IN MESSAGE - Adding background task")
                    background_tasks.add_task(process_mention_task, event)
                    logger.info(f"✅ Background task added to queue")
                else:
                    logger.info(f"⏭️ User not mentioned in message, skipping task creation")
                    
                # Handle direct messages separately if needed
                if channel_type == "im":
                    logger.info(f"📱 This was a direct message")
            else:
                logger.info(f"ℹ️ Unhandled event type: {event_type}")
        
        logger.info(f"✅ Webhook processing complete, returning OK status")
        return {"status": "ok"}
        
    except Exception as e:
        print(f"🚨 EMERGENCY DEBUG: Exception caught: {e}")
        print(f"🚨 Exception type: {type(e).__name__}")
        import traceback
        print(f"🚨 Full traceback: {traceback.format_exc()}")
        return {"status": "error", "error": str(e)}


@router.post("/slack/slash")
async def handle_slash_commands(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack slash commands"""
    
    slack_handler = get_slack_handler()
    
    data = await verify_slack_request(request)
    
    command = data.get("command", "")
    text = data.get("text", "")
    user_id = data.get("user_id", "")
    
    logger.info(f"⚡ Slash command received: {command} from user {user_id}")
    
    # Only process if command is from our configured user
    if user_id == slack_handler.user_id:
        if command == "/task" or command == "/remind":
            logger.info(f"📝 Processing slash command: {text}")
            background_tasks.add_task(process_command_task, text, "Slack slash command")
            return {"text": "📝 Creating personal task...", "response_type": "ephemeral"}
    
    return {"text": "Command processed", "response_type": "ephemeral"}


#-- Section 5: Manual API Endpoints
@router.post("/tasks/personal")
async def create_personal_task_endpoint(task_data: Dict):
    """Manual endpoint to create personal tasks"""
    
    clickup_handler = get_clickup_handler()
    
    title = task_data.get("title")
    description = task_data.get("description", "")
    
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    
    result = await clickup_handler.create_personal_task(title, description)
    
    if result:
        return {"status": "success", "task": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to create task")


@router.post("/tasks/work")
async def create_work_task_endpoint(task_data: Dict):
    """Manual endpoint to create AMCF work tasks"""
    
    clickup_handler = get_clickup_handler()
    
    title = task_data.get("title")
    description = task_data.get("description", "")
    
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    
    result = await clickup_handler.create_amcf_task(title, description)
    
    if result:
        return {"status": "success", "task": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to create task")


#-- Section 6: Status & Health Check Endpoints
@router.get("/status")
async def integration_status():
    """Get integration status and configuration"""
    
    slack_handler = get_slack_handler()
    clickup_handler = get_clickup_handler()
    
    return {
        "status": "active",
        "slack_user_id": slack_handler.user_id,
        "clickup_user_id": clickup_handler.user_id,
        "amcf_space_id": clickup_handler.amcf_space_id,
        "personal_space_id": clickup_handler.personal_space_id,
        "endpoints": {
            "slack_events": "/integrations/slack-clickup/slack/events",
            "slack_slash": "/integrations/slack-clickup/slack/slash",
            "manual_personal": "/integrations/slack-clickup/tasks/personal",
            "manual_work": "/integrations/slack-clickup/tasks/work"
        }
    }


#-- Section 7: Debug Testing Endpoint
@router.post("/debug/test-mention")
async def debug_test_mention(test_data: Dict):
    """Debug endpoint to test mention processing manually"""
    
    slack_handler = get_slack_handler()
    
    logger.info(f"🧪 DEBUG TEST - Manual mention test")
    
    # Create a fake Slack mention event for testing
    fake_event = {
        "type": "app_mention",
        "text": test_data.get("text", f"<@{slack_handler.user_id}> test task"),
        "user": test_data.get("user", "U12345678"),
        "channel": test_data.get("channel", "C12345678"),
        "ts": test_data.get("ts", "1234567890.123456")
    }
    
    logger.info(f"🎭 Fake event created: {fake_event}")
    
    # Process the fake mention
    await process_mention_task(fake_event)
    
    return {
        "status": "debug_test_completed",
        "fake_event": fake_event,
        "message": "Check logs for detailed processing information"
    }
