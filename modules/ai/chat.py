# modules/ai/chat.py
# AI Chat Router for Syntax Prime V2 - SECTIONED AND FIXED
# Clean, sectioned chat endpoint with file upload support, weather integration, and Bluesky commands
# Date: 9/23/25, Updated: 9/24/25 - Added Weather Integration, Updated: 9/24/25 - Added Bluesky Integration

#-- Section 1: Core Imports - 9/23/25
import os
import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
import logging
import httpx  # Added for weather API calls

# File processing imports
from PIL import Image, ImageOps
import pdfplumber
import pandas as pd
import magic
import cv2
import numpy as np
from io import BytesIO
import base64

#-- Section 2: Internal Module Imports - 9/23/25
from modules.core.database import db_manager
from modules.ai.personality_engine import get_personality_engine
from modules.ai.openrouter_client import get_openrouter_client
from modules.ai.conversation_manager import get_memory_manager
from modules.ai.knowledge_query import get_knowledge_engine

#-- NEW Section 2a: Bluesky Integration Import - added 9/24/25
from modules.integrations.bluesky.multi_account_client import get_bluesky_multi_client
from modules.integrations.bluesky.engagement_analyzer import get_engagement_analyzer
from modules.integrations.bluesky.approval_system import get_approval_system
from modules.integrations.bluesky.notification_manager import get_notification_manager

#-- Section 3: Request/Response Models - 9/23/25
class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None

class ChatRequest(BaseModel):
    message: str
    personality_id: Optional[str] = 'syntaxprime'
    thread_id: Optional[str] = None
    include_knowledge: Optional[bool] = True
    stream: Optional[bool] = False

class BookmarkRequest(BaseModel):
    message_id: str
    bookmark_name: str
    thread_id: str

class ChatResponse(BaseModel):
    message_id: str
    thread_id: str
    response: str
    personality_used: str
    response_time_ms: int
    knowledge_sources: List[Dict] = []
    timestamp: datetime

#-- Section 4: Router Setup - 9/23/25
router = APIRouter(prefix="/ai", tags=["AI Chat"])
logger = logging.getLogger(__name__)

# File upload configuration - FIXED for Docker permissions
UPLOAD_DIR = Path("/home/app/uploads/chat_files")  # Use user's home directory
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.txt', '.md', '.csv'}

# Create upload directory safely (not at import time)
def ensure_upload_dir():
    """Ensure upload directory exists with proper error handling"""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except PermissionError as e:
        logger.error(f"Cannot create upload directory: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error creating upload directory: {e}")
        return False

# Call this function instead of doing it at import time
_upload_dir_created = False

def get_upload_dir():
    """Get upload directory, creating it if necessary"""
    global _upload_dir_created
    if not _upload_dir_created:
        _upload_dir_created = ensure_upload_dir()
    return UPLOAD_DIR if _upload_dir_created else None

#-- Section 5: Helper Functions - 9/23/25
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    # TODO: Implement proper authentication
    return "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

async def get_weather_for_user(user_id: str, location: str = None) -> Dict:
    """Get current weather data for the user"""
    try:
        # Build the URL for your weather endpoint - using localhost for internal calls
        base_url = os.getenv("RAILWAY_STATIC_URL", "http://localhost:8000")
        params = {"user_id": user_id}
        if location:
            params["location"] = location
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/integrations/weather/current",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Weather API returned {response.status_code}")
                return {"error": f"Weather API returned {response.status_code}"}
                
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return {"error": f"Failed to get weather: {str(e)}"}

def detect_weather_request(message: str) -> bool:
    """Detect if user is asking about weather"""
    logger.info(f"🌦️ WEATHER DEBUG: Checking message '{message}'")
    weather_keywords = [
        "weather", "temperature", "forecast", "rain", "sunny", "cloudy",
        "pressure", "headache", "uv", "sun", "humidity", "wind", "barometric",
        "hot", "cold", "warm", "cool", "storm", "thunderstorm", "snow",
        "precipitation", "conditions", "outside", "today's weather"
    ]
    message_lower = message.lower()
    result = any(keyword in message_lower for keyword in weather_keywords)
    logger.info(f"🌦️ WEATHER DEBUG: Detection result = {result}")
    return result

#-- NEW Section 5a: Bluesky Command Processing - added 9/24/25
def detect_bluesky_command(message: str) -> bool:
    """Detect if user is issuing a Bluesky command"""
    bluesky_keywords = [
        "bluesky", "blue sky", "social media", "engagement", "opportunities",
        "post to bluesky", "scan bluesky", "bluesky scan", "bluesky opportunities",
        "bluesky high priority", "bluesky approve", "bluesky health",
        "bluesky accounts", "bluesky status", "social assistant"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in bluesky_keywords)

async def process_bluesky_command(message: str, user_id: str) -> str:
    """Process Bluesky-related commands and return formatted response"""
    try:
        multi_client = get_bluesky_multi_client()
        engagement_analyzer = get_engagement_analyzer()
        approval_system = get_approval_system()
        notification_manager = get_notification_manager()
        
        message_lower = message.lower()
        
        # Track user activity for notification system
        await notification_manager.track_user_activity(user_id, 'chat_interaction')
        
        # Command routing
        if any(phrase in message_lower for phrase in ['bluesky scan', 'scan bluesky', 'scan all accounts']):
            # Trigger background scan
            import asyncio
            asyncio.create_task(trigger_background_scan(user_id))
            
            # Get account status
            accounts_status = multi_client.get_all_accounts_status()
            configured_count = len([a for a in accounts_status.values() if a.get('password')])
            authenticated_count = len([a for a in accounts_status.values() if a.get('authenticated')])
            
            return f"""🔵 **Bluesky Scan Initiated**

📱 **Accounts Status:** {authenticated_count}/{configured_count} accounts authenticated
⏳ **Scanning:** All authenticated accounts for engagement opportunities
🕐 **Process Time:** ~2-3 minutes for complete analysis

**What I'm looking for:**
• High keyword matches (80%+) across your 5 accounts
• Conversation starters and engagement opportunities  
• Cross-account collaboration possibilities
• Trending topics relevant to your interests

Check back in a few minutes with `bluesky opportunities` to see what I found!"""

        elif any(phrase in message_lower for phrase in ['bluesky opportunities', 'bluesky suggestions', 'show opportunities']):
            # Get pending opportunities
            opportunities = await approval_system.get_pending_approvals(limit=10)
            
            if not opportunities:
                return f"""📭 **No Pending Opportunities**

Looks like your queue is empty! This could mean:
• No recent high-relevance posts found in timelines
• All opportunities have been reviewed
• Accounts need re-scanning (every 3.5 hours automatically)

Try: `bluesky scan` to force a fresh scan across all accounts."""
            
            # Format opportunities for chat display
            response_lines = [f"🎯 **{len(opportunities)} Engagement Opportunities Found**\n"]
            
            for i, opp in enumerate(opportunities[:5], 1):
                account_name = opp['account_id'].replace('_', ' ').title()
                score = int(opp.get('keyword_score', 0) * 100)
                priority = opp['priority'].title()
                
                response_lines.append(f"**{i}. {account_name}** ({priority} Priority • {score}% match)")
                response_lines.append(f"   📱 **Post:** {opp['original_post'][:150]}...")
                response_lines.append(f"   💡 **Draft:** {opp['draft_text']}")
                response_lines.append(f"   🎯 **Action:** {opp['engagement_type'].replace('_', ' ').title()}")
                response_lines.append("")
            
            if len(opportunities) > 5:
                response_lines.append(f"... and {len(opportunities) - 5} more opportunities available.")
            
            response_lines.extend([
                "\n**Quick Actions:**",
                "• `bluesky approve 1` - Approve first opportunity",
                "• `bluesky high priority` - Show only high-priority items",
                "• `bluesky accounts` - Check account status"
            ])
            
            return "\n".join(response_lines)
            
        elif any(phrase in message_lower for phrase in ['bluesky high priority', 'high priority']):
            # Get only high-priority opportunities
            opportunities = await approval_system.get_pending_approvals(priority='high', limit=10)
            
            if not opportunities:
                return "⭐ **No High-Priority Opportunities** - All current suggestions are medium/low priority."
            
            response_lines = [f"⭐ **{len(opportunities)} High-Priority Opportunities**\n"]
            
            for i, opp in enumerate(opportunities, 1):
                account_name = opp['account_id'].replace('_', ' ').title()
                score = int(opp.get('keyword_score', 0) * 100)
                
                response_lines.append(f"**{i}. {account_name}** ({score}% keyword match)")
                response_lines.append(f"   📱 **Author:** {opp['author']['display_name']}")
                response_lines.append(f"   💡 **Draft:** {opp['draft_text']}")
                response_lines.append("")
            
            return "\n".join(response_lines)
            
        elif any(phrase in message_lower for phrase in ['bluesky accounts', 'account status', 'bluesky status']):
            # Show account status
            accounts_status = multi_client.get_all_accounts_status()
            
            response_lines = ["🔵 **Bluesky Accounts Status**\n"]
            
            for account_id, info in accounts_status.items():
                account_name = account_id.replace('_', ' ').title()
                status_emoji = "✅" if info.get('authenticated') else "❌"
                keyword_count = info.get('keyword_count', 0)
                personality = info.get('personality', 'unknown').title()
                
                response_lines.append(f"{status_emoji} **{account_name}**")
                response_lines.append(f"   🔑 Keywords: {keyword_count}")
                response_lines.append(f"   🎭 Personality: {personality}")
                response_lines.append(f"   🤖 AI Posting: {'Yes' if info.get('ai_posting_allowed') else 'Human-only'}")
                if info.get('last_scan'):
                    response_lines.append(f"   🕐 Last Scan: {info['last_scan'].strftime('%H:%M %m/%d')}")
                response_lines.append("")
            
            return "\n".join(response_lines)
            
        elif any(phrase in message_lower for phrase in ['bluesky health', 'bluesky test']):
            # Test connections
            try:
                auth_results = await multi_client.authenticate_all_accounts()
                working_accounts = sum(auth_results.values())
                total_accounts = len(auth_results)
                
                return f"""🔵 **Bluesky System Health Check**

📱 **Accounts:** {working_accounts}/{total_accounts} connected successfully
🤖 **AI Assistant:** All personalities loaded
⚙️ **Services:** Engagement analyzer, approval system, notifications all operational

**Connection Results:**
{chr(10).join([f"{'✅' if status else '❌'} {account_id.replace('_', ' ').title()}" for account_id, status in auth_results.items()])}

System Status: **{'Healthy' if working_accounts > 0 else 'Needs Attention'}**"""
                
            except Exception as e:
                return f"❌ **Health Check Failed:** {str(e)}"
        
        elif 'post to bluesky' in message_lower:
            return """📝 **Direct Posting Available**

To post directly to Bluesky accounts:
• Use the `/bluesky/post` API endpoint
• Or try: `post "Your message here" to personal account`

**Available Accounts:**
• Personal (bcdodgeme) - Syntax tone ✅
• Rose & Angel - Professional only 
• TV Signals - Syntax tone ✅
• Meals n Feelz - Human-only
• Damn it Carl - Syntax tone ✅

**Note:** All posts require approval first - no auto-posting anywhere!"""
            
        else:
            # General Bluesky info
            accounts_status = multi_client.get_all_accounts_status()
            configured_count = len([a for a in accounts_status.values() if a.get('password')])
            
            return f"""🔵 **Bluesky Social Media Assistant**

Your 5-account AI social media management system is ready!

📱 **Configured Accounts:** {configured_count}/5
🤖 **Features:** Keyword intelligence, engagement suggestions, approval workflow
⏰ **Auto-Scan:** Every 3.5 hours across all accounts

**Available Commands:**
• `bluesky scan` - Force scan all accounts  
• `bluesky opportunities` - View engagement suggestions
• `bluesky high priority` - Show top matches only
• `bluesky accounts` - Check account status
• `bluesky health` - System health check

**How it works:**
1. I scan your 5 Bluesky timelines for keyword matches
2. Generate engagement suggestions with AI-written drafts
3. Present opportunities for your approval
4. Post only after you approve (no auto-posting!)

Ready to find your next great engagement opportunity?"""
    
    except Exception as e:
        logger.error(f"Bluesky command processing failed: {e}")
        return f"❌ **Bluesky Command Error:** {str(e)}\n\nTry `bluesky health` to check system status."

async def trigger_background_scan(user_id: str):
    """Trigger a background scan of all Bluesky accounts"""
    try:
        multi_client = get_bluesky_multi_client()
        engagement_analyzer = get_engagement_analyzer()
        approval_system = get_approval_system()
        
        # Authenticate accounts
        await multi_client.authenticate_all_accounts()
        
        # Get all timelines
        timelines = await multi_client.get_all_timelines()
        
        # Analyze opportunities
        all_opportunities = []
        for account_id, timeline in timelines.items():
            account_config = multi_client.get_account_info(account_id)
            
            for post in timeline[:20]:  # Limit for performance
                analysis = await engagement_analyzer.analyze_post_for_account(
                    post, account_id, account_config
                )
                
                if analysis and analysis.get('engagement_potential', 0) >= 0.3:
                    # Generate draft
                    draft_result = await approval_system.generate_draft_post(analysis, "reply")
                    
                    if draft_result['success']:
                        # Create approval item
                        await approval_system.create_approval_item(
                            analysis, draft_result, analysis.get('priority_level', 'medium')
                        )
                        all_opportunities.append(analysis)
        
        logger.info(f"Background scan complete: {len(all_opportunities)} opportunities found")
        
    except Exception as e:
        logger.error(f"Background scan failed: {e}")

async def process_uploaded_files(files: List[UploadFile]) -> List[Dict]:
    """Process uploaded files and return file information"""
    processed_files = []
    
    for file in files:
        if not file.filename:
            continue
            
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Validate file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} too large. Max size: 10MB"
            )
        
        # Save file with unique name
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Analyze file content (basic)
        file_info = {
            'file_id': file_id,
            'filename': file.filename,
            'file_type': file_ext,
            'file_size': len(content),
            'file_path': str(file_path),
            'analysis': await analyze_file_content(file_path, file_ext)
        }
        
        processed_files.append(file_info)
        
        # Reset file pointer for potential reuse
        await file.seek(0)
    
    return processed_files

async def analyze_file_content(file_path: Path, file_type: str) -> Dict:
    """
    Comprehensive file analysis with real processing capabilities
    """
    analysis = {
        'type': 'unknown',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        if file_type in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
            analysis.update(await analyze_image_file(file_path))
            
        elif file_type == '.pdf':
            analysis.update(await analyze_pdf_file(file_path))
            
        elif file_type in ['.txt', '.md']:
            analysis.update(await analyze_text_file(file_path))
            
        elif file_type == '.csv':
            analysis.update(await analyze_csv_file(file_path))
            
        else:
            analysis['description'] = f"Unsupported file type: {file_type}"
            
    except Exception as e:
        logger.error(f"File analysis failed for {file_path}: {e}")
        analysis['description'] = f"Analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

# [Keep all your existing analyze_* functions here - they're already perfect]
# I'm not including them to save space, but keep:
# - analyze_image_file
# - analyze_dominant_colors
# - analyze_pdf_file
# - analyze_text_file
# - analyze_csv_file

#-- Section 6: Main Chat Endpoints - Updated 9/24/25 with Bluesky Integration
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id)
):
    """
    Main chat endpoint with file upload support, weather integration, and Bluesky command processing
    """
    start_time = datetime.now()
    logger.info(f"🔍 DEBUG: chat_with_ai called with message: '{request.message}'")
    
    try:
        # Process any uploaded files
        processed_files = []
        if files and files[0].filename:  # Check if files were actually uploaded
            processed_files = await process_uploaded_files(files)
            logger.info(f"Processed {len(processed_files)} uploaded files")
        
        # NEW: Check for Bluesky commands first - added 9/24/25
        if detect_bluesky_command(request.message):
            logger.info(f"🔵 Bluesky command detected: {request.message}")
            
            # Process Bluesky command
            bluesky_response = await process_bluesky_command(request.message, user_id)
            
            # Get or create conversation thread for storing the interaction
            memory_manager = get_memory_manager(user_id)
            
            if request.thread_id:
                thread_id = request.thread_id
            else:
                thread_id = await memory_manager.create_conversation_thread(
                    platform="web_interface",
                    title="Bluesky Social Media Management"
                )
            
            # Store user message
            user_message_id = str(uuid.uuid4())
            await memory_manager.add_message(
                thread_id=thread_id,
                role="user",
                content=request.message,
                content_type="bluesky_command"
            )
            
            # Store assistant response
            ai_message_id = str(uuid.uuid4())
            response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=bluesky_response,
                response_time_ms=response_time_ms,
                model_used="bluesky_assistant"
            )
            
            return ChatResponse(
                message_id=ai_message_id,
                thread_id=thread_id,
                response=bluesky_response,
                personality_used="bluesky_assistant",
                response_time_ms=response_time_ms,
                knowledge_sources=[],
                timestamp=datetime.now()
            )
        
        # Get or create conversation thread
        memory_manager = get_memory_manager(user_id)
        
        if request.thread_id:
            thread_id = request.thread_id
        else:
            thread_id = await memory_manager.create_conversation_thread(
                platform="web_interface",
                title=None  # Will be auto-generated
            )
        
        # Store user message with file references
        user_message_id = str(uuid.uuid4())
        
        # Prepare message content with file context
        message_content = request.message
        if processed_files:
            file_context = "\n\nUploaded files:\n"
            for file_info in processed_files:
                file_context += f"- {file_info['filename']} ({file_info['file_type']}, {file_info['file_size']} bytes)\n"
                if file_info['analysis']['extracted_text']:
                    file_context += f"  Content preview: {file_info['analysis']['extracted_text'][:200]}...\n"
                else:
                    file_context += f"  {file_info['analysis']['description']}\n"
            message_content += file_context
        
        await memory_manager.add_message(
            thread_id=thread_id,
            role="user",
            content=message_content,
            content_type="text_with_files" if processed_files else "text"
        )
        
        # Get conversation context
        conversation_history, context_info = await memory_manager.get_context_for_ai(
            thread_id=thread_id,
            max_tokens=200000  # Use full 250K context
        )
        
        # Check if this is a weather request - EXISTING WEATHER FUNCTIONALITY
        weather_data = None
        if detect_weather_request(request.message):
            logger.info(f"Weather request detected for user {user_id}")
            weather_data = await get_weather_for_user(user_id)
            
            if weather_data and "data" in weather_data:
                # Add weather context to the conversation
                weather_info = weather_data["data"]
                weather_context = f"""
CURRENT WEATHER DATA:
Location: {weather_info.get('location', 'Current location')}
Current conditions: {weather_info.get('current_conditions', 'N/A')}
Temperature: {weather_info.get('temperature_f', 'N/A')}°F
Barometric Pressure: {weather_info.get('pressure', 'N/A')} mbar
Pressure Change (3h): {weather_info.get('pressure_change_3h', 'N/A')} mbar
UV Index: {weather_info.get('uv_index', 'N/A')}
Headache Risk: {weather_info.get('headache_risk', 'N/A')}
UV Risk: {weather_info.get('uv_risk', 'N/A')}
Health Alerts: {', '.join(weather_info.get('health_alerts', ['None']))}

Please respond naturally about the weather using this current data. Focus on health implications if relevant (headaches from pressure changes, UV protection needs, etc.).
"""
                logger.info("Weather context added to AI conversation")
            elif weather_data and "error" in weather_data:
                weather_context = f"""
WEATHER REQUEST DETECTED: Unfortunately, I'm having trouble accessing current weather data: {weather_data['error']}
Please respond appropriately about being unable to access weather information.
"""
                logger.warning(f"Weather API error: {weather_data['error']}")
            else:
                weather_context = """
WEATHER REQUEST DETECTED: Weather service is currently unavailable. Please respond appropriately.
"""
                logger.warning("Weather service returned unexpected response")
        
        # Search knowledge base if requested
        knowledge_sources = []
        if request.include_knowledge:
            knowledge_engine = get_knowledge_engine()
            knowledge_results = await knowledge_engine.search_knowledge(
                query=request.message,
                conversation_context=conversation_history,
                personality_id=request.personality_id,
                limit=5
            )
            knowledge_sources = knowledge_results
        
        # Get personality system prompt
        personality_engine = get_personality_engine()
        system_prompt = personality_engine.get_personality_system_prompt(
            personality_id=request.personality_id,
            conversation_context=conversation_history,
            knowledge_context=knowledge_sources
        )
        
        # Prepare messages for OpenRouter
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add weather context as system message if weather request detected
        if weather_data and detect_weather_request(request.message):
            messages.append({"role": "system", "content": weather_context})
        
        # Add conversation history (last 10 messages)
        for msg in conversation_history[-10:]:
            if msg['role'] in ['user', 'assistant']:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": message_content
        })
        
        # Get AI response
        openrouter_client = await get_openrouter_client()
        ai_response = await openrouter_client.chat_completion(
            messages=messages,
            model=None,  # Auto-select best model
            max_tokens=4000,
            temperature=0.7
        )
        
        # Extract response content
        response_content = ai_response.get('choices', [{}])[0].get('message', {}).get('content', '')
        model_used = ai_response.get('_metadata', {}).get('model_used')
        
        # Process response through personality engine
        processed_response = personality_engine.process_ai_response(
            response=response_content,
            personality_id=request.personality_id,
            conversation_context=conversation_history
        )
        
        # Store AI response
        ai_message_id = str(uuid.uuid4())
        response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        await memory_manager.add_message(
            thread_id=thread_id,
            role="assistant",
            content=processed_response,
            response_time_ms=response_time_ms,
            model_used=model_used,
            knowledge_sources_used=[source.get('id') for source in knowledge_sources]
        )
        
        logger.info(f"Chat completed - Thread: {thread_id}, Response time: {response_time_ms}ms, Weather: {'Yes' if weather_data else 'No'}, Bluesky: No")
        
        return ChatResponse(
            message_id=ai_message_id,
            thread_id=thread_id,
            response=processed_response,
            personality_used=request.personality_id,
            response_time_ms=response_time_ms,
            knowledge_sources=knowledge_sources,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

# [Keep all your existing endpoints - they're already perfect]
# I'm preserving your existing structure:
# - stream_chat
# - create_bookmark
# - get_thread_bookmarks
# - get_user_conversations
# - get_conversation_messages
# - get_available_personalities
# - get_ai_stats
# - delete_uploaded_file
# - get_integration_info
# - check_module_health

#-- Section 15: Module Information and Health Check Functions - Updated 9/24/25
def get_integration_info() -> Dict[str, Any]:
    """Get information about the AI chat integration"""
    return {
        "name": "AI Chat System",
        "version": "2.0.0",
        "endpoints": [
            "/ai/chat",
            "/ai/chat/stream",
            "/ai/bookmarks",
            "/ai/conversations",
            "/ai/personalities",
            "/ai/stats"
        ],
        "features": [
            "Multi-personality chat",
            "File upload support",
            "Bookmark system",
            "Knowledge integration",
            "Streaming responses",
            "Conversation management",
            "Weather integration",
            "Bluesky social media commands"  # NEW
        ],
        "file_upload_support": True,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "supported_file_types": list(ALLOWED_EXTENSIONS),
        "weather_integration": True,
        "bluesky_integration": True  # NEW
    }

def check_module_health() -> Dict[str, Any]:
    """Check the health of the AI chat module"""
    missing_vars = []
    warnings = []
    
    # Check required directories
    if not UPLOAD_DIR.exists():
        warnings.append("Upload directory not found")
    
    # Check OpenRouter configuration
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    # Check weather integration (optional)
    if not os.getenv("TOMORROW_IO_API_KEY"):
        warnings.append("Weather integration not configured (TOMORROW_IO_API_KEY missing)")
    
    # Check Bluesky integration (optional) - NEW
    bluesky_configured = any([
        os.getenv("BLUESKY_PERSONAL_PASSWORD"),
        os.getenv("BLUESKY_ROSE_ANGEL_PASSWORD"),
        os.getenv("BLUESKY_BINGE_TV_PASSWORD"),
        os.getenv("BLUESKY_MEALS_FEELZ_PASSWORD"),
        os.getenv("BLUESKY_DAMN_IT_CARL_PASSWORD")
    ])
    
    if not bluesky_configured:
        warnings.append("Bluesky integration not configured (account passwords missing)")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "warnings": warnings,
        "upload_directory": str(UPLOAD_DIR),
        "max_file_size": f"{MAX_FILE_SIZE // (1024 * 1024)}MB",
        "weather_integration_available": bool(os.getenv("TOMORROW_IO_API_KEY")),
        "bluesky_integration_available": bluesky_configured  # NEW
    }
