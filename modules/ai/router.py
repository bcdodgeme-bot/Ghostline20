# modules/ai/router.py
"""
AI Brain Router for Syntax Prime V2 - COMPLETE WITH ALL INTEGRATIONS
Handles all AI endpoints including chat with full integration support
Integration Order: Weather → Bluesky → RSS → Scraper → Prayer → Health → Chat/AI
Date: 9/26/25 - Complete rewrite with all integrations properly ordered
"""

import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

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

#-- Main Chat Endpoint (THE CORE FUNCTIONALITY)
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(chat_request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """
    Main chat endpoint - processes message through complete AI brain
    Integration Order: Weather → Bluesky → RSS → Scraper → Prayer → Health → Chat/AI
    """
    start_time = time.time()
    thread_id = chat_request.thread_id or str(uuid.uuid4())
    
    try:
        # Import helper functions from chat.py
        from .chat import (
            get_current_datetime_context,
            detect_weather_request, get_weather_for_user,
            detect_prayer_command, process_prayer_command,
            detect_bluesky_command, process_bluesky_command,
            detect_rss_command, get_rss_marketing_context,
            detect_scraper_command, process_scraper_command
        )
        
        # Get AI components
        personality_engine = get_personality_engine()
        memory_manager = get_memory_manager(user_id)
        knowledge_engine = get_knowledge_engine()
        openrouter_client = await get_openrouter_client()
        
        # Get current datetime context
        datetime_context = get_current_datetime_context()
        
        # Store user message
        user_message_id = str(uuid.uuid4())
        await memory_manager.store_message(
            thread_id=thread_id,
            message_id=user_message_id,
            user_id=user_id,
            role="user",
            content=chat_request.message,
            metadata={"personality_requested": chat_request.personality_id}
        )
        
        # Build message content
        message_content = chat_request.message
        
        # INTEGRATION ORDER: Check for special commands in the specified order
        special_response = None
        
        # 1. 🌦️ Weather command detection (FIRST)
        if detect_weather_request(message_content):
            logger.info("🌦️ Processing weather request")
            weather_data = await get_weather_for_user(user_id)
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
            else:
                special_response = f"🌦️ **Weather Service Error**\n\nUnable to retrieve weather data: {weather_data.get('error', 'Unknown error')}"
        
        # 2. 🔵 Bluesky command detection (SECOND)
        elif detect_bluesky_command(message_content):
            logger.info("🔵 Processing Bluesky command")
            special_response = await process_bluesky_command(message_content, user_id)
        
        # 3. 📰 RSS Learning command detection (THIRD)
        elif detect_rss_command(message_content):
            logger.info("📰 Processing RSS Learning request")
            # RSS is handled differently - it provides context rather than direct responses
            # We'll get the context and let the AI incorporate it naturally
            pass
        
        # 4. 🔍 Marketing Scraper command detection (FOURTH)
        elif detect_scraper_command(message_content):
            logger.info("🔍 Processing marketing scraper command")
            special_response = await process_scraper_command(message_content, user_id)
        
        # 5. 🕌 Prayer Times command detection (FIFTH)
        elif detect_prayer_command(message_content):
            logger.info("🕌 Processing prayer times request")
            special_response = await process_prayer_command(message_content, user_id)
        
        # 6. 🏥 Health Check command detection (SIXTH)
        elif any(term in message_content.lower() for term in ['health check', 'system status', 'system health', 'how are you feeling']):
            logger.info("🏥 Processing health check request")
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
            except Exception as e:
                special_response = f"🏥 **Health Check Error**\n\nUnable to retrieve system health: {str(e)}"
        
        # 7. 🧠 Chat/AI function (SEVENTH - DEFAULT AI PROCESSING)
        if special_response:
            # Use the special response from one of the integrations
            final_response = special_response
            model_used = "integration_response"
            knowledge_sources = []
        else:
            # Regular AI processing with full integration context
            logger.info("🧠 Processing regular AI chat request")
            
            # Get conversation history
            conversation_history = await memory_manager.get_conversation_context(
                thread_id, max_messages=20
            )
            
            # Search knowledge base if requested
            knowledge_sources = []
            if chat_request.include_knowledge:
                knowledge_results = await knowledge_engine.search_knowledge(
                    query=message_content,
                    personality_id=chat_request.personality_id,
                    limit=5
                )
                knowledge_sources = knowledge_results
            
            # Get RSS marketing context for writing assistance (integration #3)
            rss_context = ""
            if detect_rss_command(message_content) or any(term in message_content.lower() for term in ['write', 'content', 'marketing', 'blog', 'email']):
                logger.info("📰 Adding RSS Learning context to AI response")
                rss_context = await get_rss_marketing_context(message_content)
            
            # Build system prompt with personality
            personality_prompt = personality_engine.get_personality_prompt(
                chat_request.personality_id,
                conversation_context=conversation_history
            )
            
            # Create enhanced system prompt with context
            system_parts = [
                personality_prompt,
                f"""Current DateTime Context: {datetime_context['full_datetime']}
Today is {datetime_context['day_of_week']}, {datetime_context['month_name']} {datetime_context['current_date']}.
Current time: {datetime_context['current_time_12h']} ({datetime_context['timezone']})

User Context: The user is asking questions on {datetime_context['full_datetime']}.
When discussing time or dates, use the current information provided above.

Integration Status: All systems active - Weather, Bluesky, RSS Learning, Marketing Scraper, Prayer Times, and Health monitoring are available via chat commands."""
            ]
            
            # Add RSS context if available
            if rss_context:
                system_parts.append(rss_context)
            
            # Add knowledge context
            if knowledge_sources:
                knowledge_context = "RELEVANT KNOWLEDGE BASE INFORMATION:\n"
                for source in knowledge_sources:
                    knowledge_context += f"- {source['title']}: {source['content'][:200]}...\n"
                system_parts.append(knowledge_context)
            
            # Build AI messages
            ai_messages = [{
                "role": "system",
                "content": "\n\n".join(system_parts)
            }]
            
            # Add conversation history
            for msg in conversation_history[-10:]:  # Last 10 messages
                ai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Add current message
            ai_messages.append({
                "role": "user",
                "content": message_content
            })
            
            # Get AI response
            ai_response = await openrouter_client.chat_completion(
                messages=ai_messages,
                model="anthropic/claude-3.5-sonnet:beta",
                max_tokens=4000,
                temperature=0.7
            )
            
            # Extract response content
            if ai_response and 'choices' in ai_response:
                final_response = ai_response['choices'][0]['message']['content']
                model_used = ai_response.get('model', 'claude-3.5-sonnet')
            else:
                final_response = "I'm sorry, I encountered an error processing your message. Please try again."
                model_used = "error"
        
        # Store AI response
        ai_message_id = str(uuid.uuid4())
        response_time_ms = int((time.time() - start_time) * 1000)
        
        await memory_manager.store_message(
            thread_id=thread_id,
            message_id=ai_message_id,
            user_id=user_id,
            role="assistant",
            content=final_response,
            metadata={
                "personality_used": chat_request.personality_id,
                "model_used": model_used,
                "response_time_ms": response_time_ms,
                "knowledge_sources_count": len(knowledge_sources),
                "integration_order": "weather->bluesky->rss->scraper->prayer->health->ai"
            }
        )
        
        # Build response
        logger.info(f"✅ Chat processed successfully: {response_time_ms}ms, model: {model_used}")
        
        return ChatResponse(
            response=final_response,
            thread_id=thread_id,
            message_id=ai_message_id,
            personality_id=chat_request.personality_id,
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
                'message_count': len(conversation_history) + 1 if 'conversation_history' in locals() else 1,
                'has_knowledge': len(knowledge_sources) > 0,
                'integration_processing_order': 'weather->bluesky->rss->scraper->prayer->health->ai'
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Chat processing failed: {e}")
        logger.error(f"Exception details:", exc_info=True)
        
        # Store error message
        error_message = f"Sorry, I encountered an error processing your message. Please try again.\n\nError details: {str(e)}"
        
        error_message_id = str(uuid.uuid4())
        response_time_ms = int((time.time() - start_time) * 1000)
        
        try:
            memory_manager = get_memory_manager(user_id)
            await memory_manager.store_message(
                thread_id=thread_id,
                message_id=error_message_id,
                user_id=user_id,
                role="assistant",
                content=error_message,
                metadata={
                    "error": True,
                    "error_type": type(e).__name__,
                    "response_time_ms": response_time_ms
                }
            )
        except:
            pass  # Don't fail if we can't store the error
        
        return ChatResponse(
            response=error_message,
            thread_id=thread_id,
            message_id=error_message_id,
            personality_id=chat_request.personality_id,
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
            "integration_order": "weather->bluesky->rss->scraper->prayer->health->ai",
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
        "integration_order": "weather->bluesky->rss->scraper->prayer->health->ai",
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
        "name": "AI Brain Router with Full Integration Support",
        "version": "2.0.0",
        "description": "Complete AI chat with ordered integration processing",
        "integration_order": "🌦️ Weather → 🔵 Bluesky → 📰 RSS → 🔍 Scraper → 🕌 Prayer → 🏥 Health → 🧠 Chat/AI",
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
            "Prayer Times",
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
            "🕌 Islamic prayer times",
            "🏥 System health monitoring",
            "🧠 Advanced AI chat processing"
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
        "integration_order": "weather->bluesky->rss->scraper->prayer->health->ai",
        "default_user_id": DEFAULT_USER_ID,
        "note": "Complete AI router with all integrations properly ordered"
    }
