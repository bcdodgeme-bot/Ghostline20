# modules/ai/router.py
"""
AI Brain Router for Syntax Prime V2 - DEBUGGED VERSION
Handles all AI endpoints including chat with full integration support
Integration Order: Weather → Bluesky → RSS → Scraper → Prayer → Google Trends → Voice → Image → Health → Chat/AI
Date: 9/27/25 - Added extensive debugging and fixed critical bugs
Date: 9/27/25 - Added prayer notifications, location detection, and Google Trends integration
Date: 9/28/25 - Added Voice Synthesis and Image Generation to integration chain
"""

import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Depends, Request,Form, UploadFile,File
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any

# Import our AI brain components
from .openrouter_client import get_openrouter_client, cleanup_openrouter_client
from .inception_client import get_inception_client, cleanup_inception_client
from .conversation_manager import get_memory_manager, cleanup_memory_managers
from .knowledge_query import get_knowledge_engine
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

logger = logging.getLogger(__name__)

#-- Request/Response Models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    personality_id: str = Field(default='syntaxprime', description="AI personality to use")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    include_knowledge: bool = Field(default=True, description="Include knowledge base search")
    stream: bool = Field(default=False, description="Stream response")

class ChatResponse(BaseModel):
    response: str
    thread_id: str
    message_id: str
    personality_id: str
    model_used: str
    response_time_ms: int
    knowledge_sources: List[Dict] = []
    conversation_context: Dict = {}

class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="Message ID to rate")
    feedback_type: str = Field(..., description="good, bad, or personality")
    feedback_text: Optional[str] = Field(None, description="Optional text feedback")

class FeedbackResponse(BaseModel):
    feedback_id: str
    feedback_type: str
    emoji: str
    learning_result: Dict
    message: str

#-- Router Setup
router = APIRouter(prefix="/ai", tags=["ai"])
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

# Dependency function
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    return DEFAULT_USER_ID

#-- Main Chat Endpoint (THE CORE FUNCTIONALITY WITH EXTENSIVE DEBUG)
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    message: str = Form(...),
    personality_id: str = Form(default='syntaxprime'),
    thread_id: Optional[str] = Form(None),
    include_knowledge: bool = Form(default=True),
    files: List[UploadFile] = File(default=[]),
    request: Request = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Main chat endpoint with file upload support
    Integration Order: Weather → Bluesky → RSS → Scraper → Prayer → Google Trends → Voice → Image → Health → Chat/AI
    """
    # Process uploaded files if any
    file_context = ""
    
    # Import file processing function at the top to avoid scope issues
    from .chat import process_uploaded_files
    
    # 🚨 CRITICAL DEBUG: Log what FastAPI received
    logger.info(f"🔍 FILE DEBUG: files parameter type: {type(files)}")
    logger.info(f"🔍 FILE DEBUG: files parameter value: {files}")
    logger.info(f"🔍 FILE DEBUG: files length: {len(files) if files else 'None'}")
    
    if files:
        logger.info(f"🔍 FILE DEBUG: Iterating through {len(files)} file objects...")
        for idx, file in enumerate(files):
            logger.info(f"🔍 FILE DEBUG [{idx}]: filename={file.filename}, content_type={file.content_type}, size={file.size if hasattr(file, 'size') else 'unknown'}")
    
    if files and len(files) > 0:
        logger.info(f"📎 Processing {len(files)} uploaded files")    
        
        try:
            processed_files = await process_uploaded_files(files)
            logger.info(f"✅ Files processed successfully: {[f['filename'] for f in processed_files]}")
            
            # Add file context to the message
            file_context = "\n\n**Uploaded Files:**\n"
            image_attachments = []  # Store base64 image data for vision
            
            for file_info in processed_files:
                file_context += f"\n📎 **{file_info['filename']}**\n"
                if file_info['analysis'].get('description'):
                    file_context += f"   {file_info['analysis']['description']}\n"
                    
                if file_info['file_type'] in ['.png', '.jpg', '.jpeg', '.gif']:
                    try:
                        # Read the image file and encode as base64
                        with open(file_info['file_path'], 'rb') as img_file:
                            import base64
                            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                            
                            # Determine media type
                            media_type_map = {
                                '.png': 'image/png',
                                '.jpg': 'image/jpeg',
                                '.jpeg': 'image/jpeg',
                                '.gif': 'image/gif'
                            }
                            
                            image_attachments.append({
                                'filename': file_info['filename'],
                                'type': file_info['file_type'],
                                'base64': img_base64,
                                'media_type': media_type_map.get(file_info['file_type'], 'image/png')
                            })
                            logger.info(f"📸 Prepared image for vision: {file_info['filename']}")
                            
                    except Exception as e:
                        logger.error(f"Failed to encode image {file_info['filename']}: {e}")
                        
            if len(image_attachments) > 0:
                logger.info(f"📸 Total images ready for vision analysis: {len(image_attachments)}")
                
        except Exception as e:
            logger.error(f"Error processing uploaded files: {e}")
            file_context = "\n\n⚠️ Error processing uploaded files"
    
    # Combine message with file context
    full_message = message + file_context
    
    start_time = time.time()
    thread_id = thread_id or str(uuid.uuid4())
    
    # 🚨 CRITICAL DEBUG: Log everything
    logger.info(f"🚀 CHAT START: Processing message '{message[:50]}...'")
    logger.info(f"🔍 DEBUG: user_id={user_id}, personality={personality_id}")
    logger.info(f"🧵 DEBUG: thread_id={thread_id}")
    
    try:
        # Import helper functions from chat.py
        logger.info("📦 DEBUG: Loading helper functions from chat.py...")
        try:
            from .chat import (
                 get_current_datetime_context,
                 detect_weather_request, get_weather_for_user,get_weather_forecast_for_user, 
                 detect_prayer_command, process_prayer_command,
                 detect_prayer_notification_command, process_prayer_notification_command,
                 detect_location_command, process_location_command,
                 detect_bluesky_command, process_bluesky_command,
                 detect_rss_command, get_rss_marketing_context,
                 detect_scraper_command, process_scraper_command,
                 detect_trends_command, process_trends_command,
                 detect_voice_command, process_voice_command,
                 detect_image_command, process_image_command,
                 detect_google_command, process_google_command,
                 detect_pattern_complaint, handle_pattern_complaint,
                 detect_email_detail_command, process_email_detail_command,
                 detect_draft_creation_command, process_draft_creation_command # NEW 10/2/25
            )
            logger.info("✅ DEBUG: All chat helper functions loaded successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to import chat helpers: {e}")
            raise
        
        # Get AI components
        logger.info("🧠 DEBUG: Loading AI components...")
        try:
            personality_engine = get_personality_engine()
            memory_manager = get_memory_manager(user_id)
            knowledge_engine = get_knowledge_engine()
            openrouter_client = await get_openrouter_client()
            logger.info("✅ DEBUG: All AI components loaded successfully")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to load AI components: {e}")
            raise
        
        # Get current datetime context
        logger.info("📅 DEBUG: Getting datetime context...")
        try:
            datetime_context = get_current_datetime_context()
            logger.info(f"✅ DEBUG: Datetime context: {datetime_context['full_datetime']}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to get datetime context: {e}")
            datetime_context = {"full_datetime": "Unknown time"}
        
        # Ensure thread exists or create it
        logger.info("🧵 DEBUG: Managing conversation thread...")
        try:
            if not thread_id:
                logger.info("🆕 DEBUG: Creating new thread...")
                thread_id = await memory_manager.create_conversation_thread(
                    platform='web',
                    title=None  # Will be auto-generated from first message
                )
                logger.info(f"✅ DEBUG: New thread created: {thread_id}")
            else:
                # Verify existing thread exists
                logger.info(f"🔍 DEBUG: Verifying existing thread: {thread_id}")
                try:
                    from ..core.database import db_manager
                    thread_check = await db_manager.fetch_one(
                        "SELECT id FROM conversation_threads WHERE id = $1 AND user_id = $2",
                        thread_id, user_id
                    )
                    if not thread_check:
                        logger.warning(f"⚠️ DEBUG: Thread {thread_id} not found, creating new thread")
                        thread_id = await memory_manager.create_conversation_thread(
                            platform='web',
                            title=None
                        )
                        logger.info(f"✅ DEBUG: Fallback thread created: {thread_id}")
                    else:
                        thread_id = thread_id
                        logger.info(f"✅ DEBUG: Using existing thread: {thread_id}")
                except Exception as e:
                    logger.error(f"❌ DEBUG: Error checking thread: {e}")
                    # Create new thread as fallback
                    thread_id = await memory_manager.create_conversation_thread(
                        platform='web',
                        title=None
                    )
                    logger.info(f"✅ DEBUG: Emergency fallback thread created: {thread_id}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Thread management failed: {e}")
            raise
        
        # Build message content
        message_content = message
        logger.info(f"🔍 DEBUG: Processing message content: '{message_content[:100]}...'")
        
        # INTEGRATION ORDER: Check for special commands in the specified order
        special_response = None
        model_used = "integration_response"
        knowledge_sources = []
        
        # Initialize context_info for special responses (BUG FIX #1)
        context_info = {
            'total_messages': 1,
            'estimated_tokens': 0,
            'has_memory_context': False
        }
        
        logger.info("🔍 DEBUG: Starting integration command detection...")
        
        # 1. 🌦️ Weather command detection (FIRST)
        logger.info("🌦️ DEBUG: Checking for weather commands...")
        is_weather, weather_type = detect_weather_request(message_content)

        if is_weather:
            logger.info(f"✅ DEBUG: Weather command detected - type: {weather_type}")
            try:
                if weather_type == 'forecast':
                    # Handle forecast request
                    forecast_data = await get_weather_forecast_for_user(user_id)
                    logger.info(f"📊 DEBUG: Forecast data received: {forecast_data.get('success', False)}")
                    
                    if forecast_data.get('success'):
                        forecast_info = forecast_data['data']
                        
                        # Build forecast response
                        special_response = "🌦️ **5-Day Weather Forecast**\n\n"
                        special_response += f"📍 **Location:** {forecast_info.get('location', 'Unknown')}\n\n"
                        
                        for day in forecast_info['forecast_days']:
                            special_response += f"📅 **{day['day_name']}**\n"
                            special_response += f"🌡️ High: {day['temp_high']}°F / Low: {day['temp_low']}°F\n"
                            special_response += f"☁️ {day['condition']}\n"
                            special_response += f"💧 Precipitation: {day['precipitation_probability']:.0f}%\n"
                            special_response += f"💨 Wind: {day['wind_speed']:.1f} mph\n"
                            special_response += f"☀️ UV Index: {day['uv_index']:.0f}\n\n"
                        
                        special_response += "\nForecast data powered by Tomorrow.io"
                        logger.info("✅ DEBUG: Forecast response generated successfully")
                    else:
                        special_response = f"🌦️ **Weather Forecast Error**\n\nUnable to retrieve forecast: {forecast_data.get('error', 'Unknown error')}"
                        logger.warning(f"⚠️ DEBUG: Forecast service error: {forecast_data.get('error')}")
                        
                else:  # weather_type == 'current'
                    # Handle current weather request
                    weather_data = await get_weather_for_user(user_id)
                    logger.info(f"📊 DEBUG: Weather data received: {weather_data.get('success', False)}")
                    
                    if weather_data.get('success'):
                        weather_info = weather_data['data']
                        special_response = f"""🌦️ **Current Weather**

📍 **Location:** {weather_info.get('location', 'Unknown')}
🌡️ **Temperature:** {weather_info.get('temperature_f', 'N/A')}°F
💧 **Humidity:** {weather_info.get('humidity', 'N/A')}%
💨 **Wind:** {weather_info.get('wind_speed', 'N/A')} mph
📊 **Pressure:** {weather_info.get('pressure', 'N/A')} mbar
☀️ **UV Index:** {weather_info.get('uv_index', 'N/A')}
👁️ **Visibility:** {weather_info.get('visibility', 'N/A')} miles

Weather data powered by Tomorrow.io"""
                        logger.info("✅ DEBUG: Weather response generated successfully")
                    else:
                        special_response = f"🌦️ **Weather Service Error**\n\nUnable to retrieve weather data: {weather_data.get('error', 'Unknown error')}"
                        logger.warning(f"⚠️ DEBUG: Weather service error: {weather_data.get('error')}")
                        
            except Exception as e:
                logger.error(f"❌ DEBUG: Weather processing failed: {e}")
                special_response = f"🌦️ **Weather Processing Error**\n\nError: {str(e)}"
        
        # 2. 🔵 Bluesky command detection (SECOND)
        elif detect_bluesky_command(message_content):
            logger.info("🔵 DEBUG: Bluesky command detected - processing...")
            try:
                # Import directly to avoid cache issues
                from ..integrations.bluesky.multi_account_client import get_bluesky_multi_client
                
                multi_client = get_bluesky_multi_client()
                message_lower = message_content.lower()
                
                if 'health' in message_lower:
                    try:
                        auth_results = await multi_client.authenticate_all_accounts()
                        working_count = sum(auth_results.values())
                        total_count = len(auth_results)
                        
                        special_response = f"""🔵 **Bluesky System Health**

📱 **Accounts:** {working_count}/{total_count} connected
🤖 **AI Assistant:** All personalities loaded
⚙️ **Status:** {'Healthy' if working_count > 0 else 'Needs Attention'}"""
                        
                    except Exception as e:
                        special_response = f"❌ **Health Check Failed:** {str(e)}"
                else:
                    # Use direct method call
                    account_statuses = multi_client.get_all_accounts_status()
                    special_response = f"""🔵 **Bluesky Social Media Intelligence**

📱 **Configured Accounts:** {len(account_statuses)}/5
🤖 **Features:** Keyword intelligence, engagement suggestions, approval workflow

**Available Commands:**
- `bluesky health` - System health check
- `bluesky accounts` - Check account status"""
                
                logger.info("✅ DEBUG: Bluesky response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Bluesky processing failed: {e}")
                special_response = f"🔵 **Bluesky Processing Error**\n\nError: {str(e)}"
        
        # 3. 📰 RSS Learning command detection (THIRD)
        elif detect_rss_command(message_content):
            logger.info("📰 DEBUG: RSS Learning command detected - processing...")
            # RSS is handled differently - it provides context rather than direct responses
            # We'll get the context and let the AI incorporate it naturally
            try:
                rss_context = await get_rss_marketing_context(message_content)
                logger.info("✅ DEBUG: RSS context retrieved, will process in AI section")
            except Exception as e:
                logger.error(f"❌ DEBUG: RSS context retrieval failed: {e}")
        
        # 4. 🔍 Marketing Scraper command detection (FOURTH)
        elif detect_scraper_command(message_content):
            logger.info("🔍 DEBUG: Marketing scraper command detected - processing...")
            try:
                special_response = await process_scraper_command(message_content, user_id)
                logger.info("✅ DEBUG: Scraper response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Scraper processing failed: {e}")
                special_response = f"🔍 **Scraper Processing Error**\n\nError: {str(e)}"
        
        # 5. 🕌 Prayer Times command detection (FIFTH) - with IP location
        elif detect_prayer_command(message_content):
            logger.info("🕌 DEBUG: Prayer times command detected - processing with IP location...")
            try:
                # Get client IP address for location detection
                client_ip = request.client.host if hasattr(request, 'client') and request.client else None
                logger.info(f"🌍 DEBUG: Using IP address for location: {client_ip}")
                
                special_response = await process_prayer_command(message_content, user_id, client_ip)
                logger.info("✅ DEBUG: Prayer times response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Prayer times processing failed: {e}")
                special_response = f"🕌 **Prayer Times Processing Error**\n\nError: {str(e)}"
        
        # 5.1 🔔 Prayer Notification Management (FIFTH-A) - with IP location
        elif detect_prayer_notification_command(message_content):
            logger.info("🔔 DEBUG: Prayer notification command detected")
            try:
                client_ip = request.client.host if hasattr(request, 'client') and request.client else None
                special_response = await process_prayer_notification_command(message_content, user_id, client_ip)
                logger.info("✅ DEBUG: Prayer notification command response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Prayer notification command processing failed: {e}")
                special_response = f"🔔 **Prayer Notification Error**\n\nUnable to process notification request: {str(e)}"
        
        # 5.2 📍 Location Detection Commands (FIFTH-B)
        elif detect_location_command(message_content):
            logger.info("📍 DEBUG: Location command detected")
            try:
                client_ip = request.client.host if hasattr(request, 'client') and request.client else None
                special_response = await process_location_command(message_content, user_id, client_ip)
                logger.info("✅ DEBUG: Location command response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Location command processing failed: {e}")
                special_response = f"📍 **Location Detection Error**\n\nUnable to process location request: {str(e)}"
        
        # 5.3 🚫 Pattern Fatigue Complaints (FIFTH-C)
        elif detect_pattern_complaint(message_content)[0]:
            logger.info("🚫 DEBUG: Pattern complaint detected")
            try:
                is_complaint, pattern_type, complaint_text = detect_pattern_complaint(message_content)
                special_response = await handle_pattern_complaint(user_id, pattern_type, complaint_text)
                logger.info("✅ DEBUG: Pattern complaint handled successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Pattern complaint handling failed: {e}")
                special_response = "I understand you want me to stop that pattern. I'll try to be less repetitive."
        
        # 6. 📈 Google Trends command detection (SIXTH)
        elif detect_trends_command(message_content)[0]:  # [0] gets the boolean from the tuple
            logger.info("📈 DEBUG: Google Trends command detected - processing...")
            try:
                special_response = await process_trends_command(message_content, user_id)
                logger.info("✅ DEBUG: Google Trends response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Google Trends processing failed: {e}")
                special_response = f"📈 **Google Trends Processing Error**\n\nError: {str(e)}"
        
        # 7. 🎤 Voice Synthesis command detection (SEVENTH) - NEW 9/28/25
        elif detect_voice_command(message_content):
            logger.info("🎤 DEBUG: Voice synthesis command detected - processing...")
            try:
                special_response = await process_voice_command(message_content, user_id)
                logger.info("✅ DEBUG: Voice synthesis response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Voice synthesis processing failed: {e}")
                special_response = f"🎤 **Voice Synthesis Processing Error**\n\nError: {str(e)}"
        
        # 8. 🎨 Image Generation command detection (EIGHTH) - NEW 9/28/25
        elif detect_image_command(message_content):
            logger.info("🎨 DEBUG: Image generation command detected - processing...")
            try:
                special_response = await process_image_command(message_content, user_id)
                logger.info("✅ DEBUG: Image generation response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Image generation processing failed: {e}")
                special_response = f"🎨 **Image Generation Processing Error**\n\nError: {str(e)}"
        
       # 9. 🔍 Google Workspace command detection (NINTH) - NEW 9/30/25
        elif detect_google_command(message_content)[0]:
            logger.info("🔍 DEBUG: Google Workspace command detected - processing...")
            try:
                logger.info(f"🔍 DEBUG: Calling process_google_command with user_id={user_id}")
                special_response = await process_google_command(message_content, user_id, thread_id)
                logger.info("✅ DEBUG: Google Workspace response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Google Workspace processing failed: {e}")
                logger.error(f"❌ DEBUG: Full exception details: {repr(e)}")
                import traceback
                logger.error(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
                special_response = f"🔍 **Google Workspace Processing Error**\n\nError: {str(e)}"
        
        # 10. 📧 Email Detail & Draft Commands (TENTH) - NEW 10/2/25
        elif detect_email_detail_command(message_content)[0] or detect_draft_creation_command(message_content)[0]:
            logger.info("📧 DEBUG: Email or draft command detected - determining type...")
            
            # Get the actual detection results
            is_email_cmd, action_type, email_num = detect_email_detail_command(message_content)
            is_draft_cmd, draft_email_num, draft_instruction = detect_draft_creation_command(message_content)
            
            logger.info(f"🔍 DEBUG: Command check - email:{is_email_cmd}, draft:{is_draft_cmd}")
            
            if is_email_cmd:
                logger.info(f"📧 DEBUG: Email detail command detected: {action_type} for email #{email_num}")
                try:
                    special_response = await process_email_detail_command(action_type, email_num, user_id)
                    logger.info("✅ DEBUG: Email detail response generated successfully")
                except Exception as e:
                    logger.error(f"❌ DEBUG: Email detail processing failed: {e}")
                    import traceback
                    logger.error(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
                    special_response = f"📧 **Email Detail Error**\n\nError: {str(e)}"
            
            elif is_draft_cmd:
                logger.info(f"✉️ DEBUG: Draft creation command detected")
                try:
                    history = await memory_manager.get_conversation_history(thread_id, limit=10)
                    special_response = await process_draft_creation_command(history, user_id, draft_instruction)
                    logger.info("✅ DEBUG: Draft created successfully")
                except Exception as e:
                    logger.error(f"❌ DEBUG: Draft creation failed: {e}")
                    import traceback
                    logger.error(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
                    special_response = f"✉️ **Draft Creation Error**\n\nError: {str(e)}"
            
    # 11. 🏥 Health Check command detection (NINTH)
        elif any(term in message_content.lower() for term in ['health check', 'system status', 'system health', 'how are you feeling']):
            logger.info("🏥 DEBUG: Health check command detected - processing...")
            try:
                from ..core.health import get_health_status
                health_data = await get_health_status()
                
                special_response = f"""🏥 **System Health Check**

**Overall Status:** {"✅ Healthy" if health_data.get('healthy', False) else "⚠️ Issues Detected"}
**Database:** {"✅ Connected" if health_data.get('database', {}).get('connected', False) else "❌ Disconnected"}
**AI Brain:** {"✅ Active" if health_data.get('ai_brain', {}).get('healthy', False) else "⚠️ Issues"}
**Integrations:** {health_data.get('active_integrations', 0)} active

**Response Time:** {health_data.get('response_time_ms', 0)}ms
**Memory Usage:** {health_data.get('memory_usage', {}).get('percent', 'N/A')}%
**Uptime:** {health_data.get('uptime', 'Unknown')}

All systems operational and ready to assist!"""
                logger.info("✅ DEBUG: Health check response generated successfully")
            except Exception as e:
                logger.error(f"❌ DEBUG: Health check processing failed: {e}")
                special_response = f"🏥 **Health Check Error**\n\nUnable to retrieve system health: {str(e)}"
        
        # 12. 🧠 Chat/AI function (TENTH - DEFAULT AI PROCESSING)
        if special_response:
            # Use the special response from one of the integrations
            logger.info(f"✅ DEBUG: Using special integration response (length: {len(special_response)} chars)")
            final_response = special_response
        else:
            # Regular AI processing with full integration context
            logger.info("🧠 DEBUG: Processing regular AI chat request...")
            
            try:
                # Get conversation history
                logger.info("📚 DEBUG: Getting conversation history...")
                conversation_history, context_info = await memory_manager.get_context_for_ai(
                    thread_id, max_tokens=20000
                )
                logger.info(f"✅ DEBUG: Conversation history retrieved: {context_info.get('total_messages', 0)} messages")
                
                # Search knowledge base if requested
                if include_knowledge:
                    logger.info("🔍 DEBUG: Searching knowledge base...")
                    try:
                        knowledge_results = await knowledge_engine.search_knowledge(
                            query=message_content,
                            personality_id=personality_id,
                            limit=5
                        )
                        knowledge_sources = knowledge_results
                        logger.info(f"✅ DEBUG: Knowledge search completed: {len(knowledge_sources)} sources found")
                    except Exception as e:
                        logger.error(f"❌ DEBUG: Knowledge search failed: {e}")
                        knowledge_sources = []
                else:
                    logger.info("⭐ DEBUG: Skipping knowledge search (disabled)")
                    knowledge_sources = []
                
                # Get RSS marketing context for writing assistance (integration #3)
                rss_context = ""
                if detect_rss_command(message_content) or any(term in message_content.lower() for term in ['write', 'content', 'marketing', 'blog', 'email']):
                    logger.info("📰 DEBUG: Adding RSS Learning context to AI response...")
                    try:
                        rss_context = await get_rss_marketing_context(message_content)
                        logger.info(f"✅ DEBUG: RSS context retrieved (length: {len(rss_context)} chars)")
                    except Exception as e:
                        logger.error(f"❌ DEBUG: RSS context failed: {e}")
                        rss_context = ""
                
                # Build system prompt with personality
                logger.info("🎭 DEBUG: Building personality system prompt...")
                try:
                    personality_prompt = personality_engine.get_personality_system_prompt(
                        personality_id,
                        conversation_context=conversation_history
                    )
                    logger.info(f"✅ DEBUG: Personality prompt generated (length: {len(personality_prompt)} chars)")
                except Exception as e:
                    logger.error(f"❌ DEBUG: Personality prompt generation failed: {e}")
                    personality_prompt = "You are a helpful AI assistant."
                
                # Create enhanced system prompt with context
                system_parts = [
                    personality_prompt,
                    f"""Current DateTime Context: {datetime_context['full_datetime']}
Today is {datetime_context.get('day_of_week', 'Unknown')}, {datetime_context.get('month_name', 'Unknown')} {datetime_context.get('current_date', 'Unknown')}.
Current time: {datetime_context.get('current_time_12h', 'Unknown')} ({datetime_context.get('timezone', 'Unknown')})

User Context: The user is asking questions on {datetime_context['full_datetime']}.
When discussing time or dates, use the current information provided above.

Integration Status: All systems active - Weather, Bluesky, RSS Learning, Marketing Scraper, Prayer Times, Google Trends, Voice Synthesis, Image Generation, and Health monitoring are available via chat commands."""
                ]
                
                # Add RSS context if available
                if rss_context:
                    system_parts.append(rss_context)
                    logger.info("📰 DEBUG: RSS context added to system prompt")
                
                # Add knowledge context
                if knowledge_sources:
                    knowledge_context = "RELEVANT KNOWLEDGE BASE INFORMATION:\n"
                    for source in knowledge_sources:
                        knowledge_context += f"- {source['title']}: {source['content'][:200]}...\n"
                    system_parts.append(knowledge_context)
                    logger.info(f"📚 DEBUG: Knowledge context added: {len(knowledge_sources)} sources")
                
                # Build AI messages
                logger.info("💬 DEBUG: Building AI message array...")
                ai_messages = [{
                    "role": "system",
                    "content": "\n\n".join(system_parts)
                }]
                
                # Add conversation history
                ai_messages.extend(conversation_history)
                logger.info(f"✅ DEBUG: AI messages array built: {len(ai_messages)} total messages")
                
                # Add current message
                # Add user message with vision support if images are present
                if 'image_attachments' in locals() and len(image_attachments) > 0:
                    # Vision-enabled message format (array of content blocks)
                    logger.info(f"📸 Building vision message with {len(image_attachments)} images")
                    
                    content_blocks = [
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                    
                    # Add each image as a content block
                    for img in image_attachments:
                        content_blocks.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img['media_type']};base64,{img['base64']}"
                            }
                        })
                        logger.info(f"📸 Added to vision request: {img['filename']}")
                    
                    ai_messages.append({
                        "role": "user",
                        "content": content_blocks  # Array format for vision
                    })
                    
                    # Force vision-capable model
                    model_override = "anthropic/claude-3.5-sonnet"
                    logger.info(f"📸 Using vision model: {model_override}")
                else:
                    # Text-only message (original format)
                    ai_messages.append({
                        "role": "user",
                        "content": message_content
                    })
                    model_override = None
                
                # Get AI response (ONLY ONCE, AFTER message is added)
                logger.info("🤖 DEBUG: Calling OpenRouter for AI response...")
                try:
                    ai_response = await openrouter_client.chat_completion(
                        messages=ai_messages,
                        model=model_override,
                        max_tokens=4000,
                        temperature=0.7
                    )
                    logger.info("✅ DEBUG: OpenRouter response received")
                except Exception as e:
                    logger.error(f"❌ DEBUG: OpenRouter call failed: {e}")
                    raise
                
                # Force vision-capable model if images are present
                model_override = None
                if 'image_attachments' in locals() and len(image_attachments) > 0:
                    model_override = "anthropic/claude-3.5-sonnet"  # Force Claude for vision
                    logger.info(f"📸 Using vision model: {model_override}")
                
                # Get AI response
                logger.info("🤖 DEBUG: Calling OpenRouter for AI response...")
                try:
                    ai_response = await openrouter_client.chat_completion(
                        messages=ai_messages,
                        model=model_override,
                        max_tokens=4000,
                        temperature=0.7
                    )
                    logger.info("✅ DEBUG: OpenRouter response received")
                except Exception as e:
                    logger.error(f"❌ DEBUG: OpenRouter call failed: {e}")
                    raise
                
                # Extract response content
                if ai_response and 'choices' in ai_response:
                    final_response = ai_response['choices'][0]['message']['content']
                    model_used = ai_response.get('model', 'claude-3.5-sonnet')
                    logger.info(f"✅ DEBUG: AI response extracted (length: {len(final_response)} chars)")
                    
                    # Apply personality post-processing (includes pattern fatigue if available)
                    logger.info("🎭 DEBUG: Applying personality post-processing...")
                    try:
                        personality_engine = get_personality_engine()
                        processed_response = await personality_engine.process_personality_response(
                            final_response,
                            personality_id,
                            user_id
                        )
                        
                        if processed_response != final_response:
                            logger.info("🚫 DEBUG: Response modified by personality processing")
                            final_response = processed_response
                        else:
                            logger.info("✅ DEBUG: Personality processing completed, no changes")
                    except Exception as e:
                        logger.warning(f"⚠️ DEBUG: Personality processing failed: {e}")
                        # Continue with original response if processing fails
            
            except Exception as e:
                logger.error(f"❌ DEBUG: AI processing failed: {e}")
                raise
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"⏱️ DEBUG: Total processing time: {response_time_ms}ms")
        
        # Store user message AFTER getting AI response (prevents duplication in history)
        logger.info("💾 DEBUG: Storing user message (delayed to prevent echo)...")
        try:
            user_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role="user",
                content=message
            )
            logger.info(f"✅ DEBUG: User message stored: {user_message_id}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to store user message: {e}")
            user_message_id = str(uuid.uuid4())  # Fallback ID
        
        # Store AI response
        logger.info("💾 DEBUG: Storing AI response...")
        try:
            ai_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=final_response,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources_used=[source.get('id', '') for source in knowledge_sources]
            )
            logger.info(f"✅ DEBUG: AI response stored: {ai_message_id}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to store AI response: {e}")
            ai_message_id = str(uuid.uuid4())  # Fallback ID
        
        # Store AI response
        logger.info("💾 DEBUG: Storing AI response...")
        try:
            ai_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=final_response,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources_used=[source.get('id', '') for source in knowledge_sources]
            )
            logger.info(f"✅ DEBUG: AI response stored: {ai_message_id}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to store AI response: {e}")
            ai_message_id = str(uuid.uuid4())  # Fallback ID
        
        # Build response
        logger.info("📦 DEBUG: Building final response object...")
        
        try:
            chat_response = ChatResponse(
                response=final_response,
                thread_id=thread_id,
                message_id=ai_message_id,
                personality_id=personality_id,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources=[
                    {
                        'id': source.get('id', ''),
                        'title': source.get('title', ''),
                        'snippet': source.get('content', '')[:200],
                        'score': source.get('score', 0.0)
                    }
                    for source in knowledge_sources
                ],
                conversation_context={
                    'thread_id': thread_id,
                    'message_count': context_info.get('total_messages', 0) + 1,
                    'has_knowledge': len(knowledge_sources) > 0,
                    'integration_processing_order': 'weather->bluesky->rss->scraper->prayer->google_trends->voice->image->health->ai'
                }
            )
            
            logger.info(f"✅ CHAT SUCCESS: Response generated in {response_time_ms}ms")
            logger.info(f"📊 DEBUG: Final stats - model: {model_used}, knowledge: {len(knowledge_sources)}, special: {bool(special_response)}")
            
            return chat_response
            
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to build response object: {e}")
            raise
        
    except Exception as e:
        logger.error(f"❌ CHAT FAILED: {str(e)}")
        logger.error(f"💥 DEBUG: Exception details:", exc_info=True)
        
        # Store error message
        error_message = f"Sorry, I encountered an error processing your message. Please try again.\n\nError details: {str(e)}"
        
        error_message_id = str(uuid.uuid4())
        response_time_ms = int((time.time() - start_time) * 1000)
        
        try:
            memory_manager = get_memory_manager(user_id)
            await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=error_message
            )
            logger.info("✅ DEBUG: Error message stored successfully")
        except Exception as store_error:
            logger.error(f"❌ DEBUG: Failed to store error message: {store_error}")
        
        return ChatResponse(
            response=error_message,
            thread_id=thread_id,
            message_id=error_message_id,
            personality_id=personality_id,
            model_used="error",
            response_time_ms=response_time_ms,
            knowledge_sources=[],
            conversation_context={'error': True, 'error_type': type(e).__name__}
        )

#-- Support Endpoints (NO DUPLICATION - CLEAN SUPPORT ONLY)

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback_request: FeedbackRequest):
    """Submit feedback for AI learning (👍👎😄)"""
    user_id = DEFAULT_USER_ID
    feedback_processor = get_feedback_processor()
    
    # Get thread_id from message
    try:
        from ..core.database import db_manager
        thread_lookup_query = """
        SELECT thread_id FROM conversation_messages 
        WHERE id = $1
        """
        message_result = await db_manager.fetch_one(thread_lookup_query, feedback_request.message_id)
        thread_id = message_result['thread_id'] if message_result else str(uuid.uuid4())
    except Exception as e:
        thread_id = str(uuid.uuid4())
        logger.warning(f"Could not lookup thread_id for message {feedback_request.message_id}: {e}")
    
    try:
        feedback_result = await feedback_processor.record_feedback(
            user_id=user_id,
            message_id=feedback_request.message_id,
            thread_id=thread_id,
            feedback_type=feedback_request.feedback_type,
            feedback_text=feedback_request.feedback_text
        )
        
        # Generate response message
        emoji = feedback_result['emoji']
        feedback_type = feedback_request.feedback_type
        
        if feedback_type == 'personality':
            message = f"{emoji} Perfect personality! I'll remember this energy."
        elif feedback_type == 'good':
            message = f"{emoji} Thanks! I'll reinforce this approach."
        elif feedback_type == 'bad':
            message = f"{emoji} Got it, I'll avoid this approach next time."
        else:
            message = f"{emoji} Feedback received."
        
        return FeedbackResponse(
            feedback_id=feedback_result['feedback_id'],
            feedback_type=feedback_result['feedback_type'],
            emoji=emoji,
            learning_result=feedback_result['learning_result'],
            message=message
        )
        
    except Exception as e:
        logger.error(f"Feedback processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/personalities")
async def get_personalities():
    """Get list of available personalities"""
    personality_engine = get_personality_engine()
    personalities = personality_engine.get_available_personalities()
    
    return {
        "personalities": [
            {
                "id": pid,
                "name": config.get('name', pid),
                "description": config.get('description', ''),
                "is_default": pid == 'syntaxprime'
            }
            for pid, config in personalities.items()
        ],
        "default_personality": "syntaxprime"
    }
    
@router.post("/bookmarks")
async def create_bookmark(
    message_id: str = Form(...),
    bookmark_name: str = Form(...),
    thread_id: str = Form(None),
    user_id: str = Depends(get_current_user_id)
):
    """Save a message as a bookmark"""
    try:
        from ..core.database import db_manager
        
        bookmark_id = str(uuid.uuid4())
        
        insert_query = """
        INSERT INTO user_bookmark 
        (id, user_id, message_id, thread_id, bookmark_name, created_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        RETURNING id;
        """
        
        result = await db_manager.fetch_one(
            insert_query,
            bookmark_id,
            user_id,
            message_id,
            thread_id,
            bookmark_name
        )
        
        return {
            "success": True,
            "bookmark_id": result['id'],
            "message": f"✅ Bookmarked as '{bookmark_name}'"
        }
        
    except Exception as e:
        logger.error(f"Bookmark creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bookmarks")
async def get_bookmarks(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """Get user's bookmarks"""
    try:
        from ..core.database import db_manager
        
        query = """
        SELECT 
            b.id,
            b.message_id,
            b.thread_id,
            b.bookmark_name,
            b.notes,
            b.created_at,
            cm.content as message_content
        FROM user_bookmark b
        LEFT JOIN conversation_messages cm ON b.message_id = cm.id
        WHERE b.user_id = $1
        ORDER BY b.created_at DESC
        LIMIT $2;
        """
        
        bookmarks = await db_manager.fetch_all(query, user_id, limit)
        
        return {
            "bookmarks": [
                {
                    "id": b['id'],
                    "message_id": b['message_id'],
                    "thread_id": b['thread_id'],
                    "bookmark_name": b['bookmark_name'],
                    "notes": b['notes'],
                    "message_preview": b['message_content'][:100] if b['message_content'] else '',
                    "created_at": b['created_at'].isoformat() if b['created_at'] else None
                }
                for b in bookmarks
            ],
            "total": len(bookmarks)
        }
        
    except Exception as e:
        logger.error(f"Failed to get bookmarks: {e}")
        return {"bookmarks": [], "total": 0}

@router.get("/conversations")
async def get_conversations(limit: int = 50):
    """Get conversation threads"""
    try:
        from ..core.database import db_manager
        conversations_query = """
        SELECT id, title, platform, status, message_count, 
               created_at, updated_at, last_message_at
        FROM conversation_threads
        WHERE user_id = $1
        ORDER BY last_message_at DESC
        LIMIT $2
        """
        threads = await db_manager.fetch_all(conversations_query, DEFAULT_USER_ID, limit)
        
        conversations = []
        for thread in threads:
            conversations.append({
                'thread_id': thread['id'],
                'title': thread['title'] or f"Conversation {thread['created_at'].strftime('%m/%d')}" if thread['created_at'] else 'New Conversation',
                'platform': thread['platform'],
                'status': thread['status'],
                'message_count': thread['message_count'] or 0,
                'created_at': thread['created_at'].isoformat() if thread['created_at'] else None,
                'updated_at': thread['updated_at'].isoformat() if thread['updated_at'] else None,
                'last_message_at': thread['last_message_at'].isoformat() if thread['last_message_at'] else None
            })
        
        return {
            "conversations": conversations,
            "total_available": len(conversations)
        }
        
    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        return {"conversations": [], "total_available": 0}

@router.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str, include_metadata: bool = False):
    """Get specific conversation history"""
    memory_manager = get_memory_manager(DEFAULT_USER_ID)
    
    try:
        messages = await memory_manager.get_conversation_history(
            thread_id,
            include_metadata=include_metadata
        )
        
        return {
            "thread_id": thread_id,
            "messages": messages,
            "message_count": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {e}")

@router.get("/knowledge/search")
async def search_knowledge(q: str, personality: str = 'syntaxprime', limit: int = 10):
    """Search knowledge base"""
    knowledge_engine = get_knowledge_engine()
    
    results = await knowledge_engine.search_knowledge(
        query=q,
        personality_id=personality,
        limit=limit
    )
    
    return {
        "query": q,
        "results": results,
        "count": len(results)
    }

@router.get("/stats")
async def get_ai_stats():
    """Get AI brain statistics"""
    memory_manager = get_memory_manager(DEFAULT_USER_ID)
    personality_engine = get_personality_engine()
    feedback_processor = get_feedback_processor()
    
    try:
        from ..core.database import db_manager
        
        conversation_stats_query = """
        SELECT 
            COUNT(DISTINCT ct.id) as total_conversations,
            COUNT(cm.id) as total_messages,
            COUNT(CASE WHEN cm.role = 'user' THEN 1 END) as user_messages,
            COUNT(CASE WHEN cm.role = 'assistant' THEN 1 END) as assistant_messages,
            AVG(cm.response_time_ms) as avg_response_time_ms,
            MAX(ct.last_message_at) as last_conversation_at
        FROM conversation_threads ct
        LEFT JOIN conversation_messages cm ON ct.id = cm.thread_id
        WHERE ct.user_id = $1
        """
        
        stats_result = await db_manager.fetch_one(conversation_stats_query, DEFAULT_USER_ID)
        personality_stats = personality_engine.get_personality_stats()
        feedback_summary = await feedback_processor.get_feedback_summary(DEFAULT_USER_ID)
        
        return {
            "conversation_stats": {
                "total_conversations": stats_result['total_conversations'] or 0,
                "total_messages": stats_result['total_messages'] or 0,
                "user_messages": stats_result['user_messages'] or 0,
                "assistant_messages": stats_result['assistant_messages'] or 0,
                "average_response_time_ms": float(stats_result['avg_response_time_ms']) if stats_result['avg_response_time_ms'] else 0,
                "last_conversation_at": stats_result['last_conversation_at'].isoformat() if stats_result['last_conversation_at'] else None
            },
            "personality_stats": personality_stats,
            "feedback_stats": feedback_summary,
            "integration_order": "weather->bluesky->rss->scraper->prayer->google_trends->voice->image->health->ai",
            "system_health": {
                "memory_active": True,
                "knowledge_engine_active": True,
                "learning_active": feedback_summary.get('learning_active', False),
                "all_integrations_active": True,
                "default_user_id": DEFAULT_USER_ID
            }
        }
        
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_ai_connection():
    """Test AI provider connections"""
    results = {}
    
    # Test OpenRouter
    try:
        from .openrouter_client import test_openrouter_connection
        results['openrouter'] = await test_openrouter_connection()
    except Exception as e:
        results['openrouter'] = {'status': 'error', 'message': str(e)}
    
    # Test Inception Labs
    try:
        inception_client = await get_inception_client()
        results['inception_labs'] = await inception_client.test_connection()
    except Exception as e:
        results['inception_labs'] = {'status': 'error', 'message': str(e)}
    
    # Overall health
    primary_healthy = results.get('openrouter', {}).get('status') == 'success'
    fallback_available = results.get('inception_labs', {}).get('status') in ['success', 'placeholder']
    
    return {
        "providers": results,
        "system_status": "healthy" if primary_healthy or fallback_available else "degraded",
        "primary_provider": "openrouter",
        "fallback_provider": "inception_labs",
        "integration_order": "weather->bluesky->rss->scraper->prayer->google_trends->voice->image->health->ai",
        "default_user_id": DEFAULT_USER_ID
    }

#-- Cleanup and Shutdown Handlers
@router.on_event("shutdown")
async def shutdown_ai_brain():
    """Cleanup AI brain components"""
    logger.info("Shutting down AI brain support components...")
    
    await cleanup_openrouter_client()
    await cleanup_inception_client()
    await cleanup_memory_managers()
    
    logger.info("AI brain support shutdown complete")

#-- Module Information Functions
def get_integration_info():
    """Get information about the AI brain router integration"""
    return {
        "name": "AI Brain Router with Full Integration Support + Voice & Image",
        "version": "2.2.0",
        "description": "Complete AI chat with ordered integration processing including Voice Synthesis and Image Generation",
        "integration_order": "🌦️ Weather → 🔵 Bluesky → 📰 RSS → 🔍 Scraper → 🕌 Prayer → 📈 Google Trends → 🎤 Voice → 🎨 Image → 🏥 Health → 🧠 Chat/AI",
        "components": [
            "Main Chat Endpoint (/ai/chat)",
            "Personality Engine",
            "Feedback Processor",
            "Conversation Manager",
            "Knowledge Query Engine",
            "AI Provider Testing",
            "Weather Integration",
            "Bluesky Social Media Management",
            "RSS Learning System",
            "Marketing Scraper",
            "Prayer Times with Notifications",
            "Location Detection",
            "Google Trends Analysis",
            "Voice Synthesis with ElevenLabs",
            "Image Generation with Replicate",
            "Health Monitoring"
        ],
        "endpoints": {
            "chat": "/ai/chat",
            "feedback": "/ai/feedback",
            "personalities": "/ai/personalities",
            "conversations": "/ai/conversations",
            "knowledge_search": "/ai/knowledge/search",
            "stats": "/ai/stats",
            "test": "/ai/test"
        },
        "features": [
            "👍👎😄 feedback learning",
            "🎭 Multi-personality system",
            "📚 Knowledge base integration",
            "🌦️ Weather monitoring",
            "🔵 Bluesky social management",
            "📰 RSS learning insights",
            "🔍 Marketing competitive analysis",
            "🕌 Islamic prayer times with notifications",
            "📍 IP-based location detection",
            "📈 Google Trends analysis",
            "🎤 Voice synthesis with personality voices",
            "🎨 AI image generation with inline display",
            "🏥 System health monitoring",
            "🧠 Advanced AI chat processing",
            "🔧 Extensive debug logging"
        ],
        "debug_features": [
            "Step-by-step processing logs",
            "Integration command detection tracing",
            "Error context preservation",
            "Performance timing measurements",
            "Component loading verification",
            "Response generation tracking"
        ],
        "default_user_id": DEFAULT_USER_ID
    }

def check_module_health():
    """Check AI brain router module health"""
    missing_vars = []
    
    # Check required environment variables
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "status": "ready" if len(missing_vars) == 0 else "needs_configuration",
        "chat_endpoint_active": True,
        "integration_order": "weather->bluesky->rss->scraper->prayer->google_trends->voice->image->health->ai",
        "debug_features_active": True,
        "voice_synthesis_integrated": True,
        "image_generation_integrated": True,
        "default_user_id": DEFAULT_USER_ID,
        "note": "Complete AI router with Voice & Image integrations properly ordered and extensive debugging"
    }
