"""
Slack-ClickUp Integration Router
API endpoints for webhook handling and manual commands
"""
import os
import json
import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from typing import Dict, Optional

from .slack_handler import SlackHandler
from .clickup_handler import ClickUpHandler  
from .task_mapper import TaskMapper

#--Section 1: Router Initialization & Configuration 9/23/25
router = APIRouter(prefix="/integrations/slack-clickup", tags=["slack-clickup"])
logger = logging.getLogger(__name__)

# Initialize handlers
slack_handler = SlackHandler()
clickup_handler = ClickUpHandler()
task_mapper = TaskMapper()

#--Section 2: Webhook Verification & Security 9/23/25
async def verify_slack_request(request: Request) -> Dict:
    """Verify and parse incoming Slack webhook request"""
    # Get headers
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing Slack headers")
    
    # Get body
    body = await request.body()
    
    # Verify signature
    if not slack_handler.verify_request(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    
    # Parse body
    try:
        if request.headers.get("content-type") == "application/json":
            return json.loads(body.decode())
        else:
            # URL-encoded form data
            from urllib.parse import parse_qs
            parsed = parse_qs(body.decode())
            return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

#--Section 3: Background Task Processing 9/23/25
async def process_mention_task(message_data: Dict):
    """Background task to process Slack mentions"""
    try:
        # Extract task details
        task_info = task_mapper.extract_mention_task(message_data)
        if not task_info:
            logger.warning("Could not extract task from mention")
            return
        
        # Create AMCF task (work-related, 3-day due date)
        result = await clickup_handler.create_amcf_task(
            title=task_info['title'],
            description=task_info['description']
        )
        
        if result:
            task_url = result.get('url', '')
            # Send confirmation back to Slack
            await slack_handler.send_response(
                channel_id=message_data.get('channel'),
                text=f"✅ Created AMCF task: {task_url}",
                thread_ts=message_data.get('ts')
            )
            logger.info(f"Created AMCF task: {result.get('id')}")
        else:
            logger.error("Failed to create AMCF task")
            
    except Exception as e:
        logger.error(f"Error processing mention task: {e}")

async def process_command_task(command: str, context: str = ""):
    """Background task to process AI command tasks"""
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

#--Section 4: Slack Webhook Endpoints 9/23/25
@router.post("/slack/events")
async def handle_slack_events(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack Events API webhooks"""
    data = await verify_slack_request(request)
    
    # Handle URL verification
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    
    # Handle event callbacks
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_type = event.get("type")
        
        # Handle app mentions
        if event_type == "app_mention":
            # Check if our user is mentioned
            if slack_handler.is_user_mentioned(event.get("text", "")):
                background_tasks.add_task(process_mention_task, event)
        
        # Handle direct messages
        elif event_type == "message" and event.get("channel_type") == "im":
            # Direct message - treat as potential command
            if slack_handler.is_user_mentioned(event.get("text", "")):
                background_tasks.add_task(process_mention_task, event)
    
    return {"status": "ok"}

@router.post("/slack/slash")
async def handle_slash_commands(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack slash commands"""
    data = await verify_slack_request(request)
    
    command = data.get("command", "")
    text = data.get("text", "")
    user_id = data.get("user_id", "")
    
    # Only process if command is from our configured user
    if user_id == slack_handler.user_id:
        if command == "/task" or command == "/remind":
            background_tasks.add_task(process_command_task, text, "Slack slash command")
            return {"text": "📝 Creating personal task...", "response_type": "ephemeral"}
    
    return {"text": "Command processed", "response_type": "ephemeral"}

#--Section 5: Manual API Endpoints 9/23/25
@router.post("/tasks/personal")
async def create_personal_task_endpoint(task_data: Dict):
    """Manual endpoint to create personal tasks"""
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
    title = task_data.get("title")
    description = task_data.get("description", "")
    
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    
    result = await clickup_handler.create_amcf_task(title, description)
    
    if result:
        return {"status": "success", "task": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to create task")

#--Section 6: Status & Health Check Endpoints 9/23/25
@router.get("/status")
async def integration_status():
    """Get integration status and configuration"""
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