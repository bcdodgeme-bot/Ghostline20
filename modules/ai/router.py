# modules/ai/router.py
"""
AI Brain Main Router for Syntax Prime V2 - COMPLETE WORKING VERSION
Handles /ai/chat with basic functionality, no complex integrations yet
Date: 9/26/25 - Fixed syntax errors, working version
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import time
import logging
import os

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field

# Import our AI brain components
from .openrouter_client import get_openrouter_client
from .conversation_manager import get_memory_manager
from .knowledge_query import get_knowledge_engine
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

logger = logging.getLogger(__name__)

#-- Request/Response Models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    personality_id: Optional[str] = Field(default='syntaxprime', description="Personality to use")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    include_knowledge: Optional[bool] = Field(default=True, description="Include knowledge base search")
    context: Optional[Dict] = Field(default=None, description="Optional context data")

class ChatResponse(BaseModel):
    message_id: str
    thread_id: str
    response: str
    personality_used: str
    response_time_ms: int
    knowledge_sources: List[Dict] = []
    timestamp: datetime

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

async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    return DEFAULT_USER_ID

def get_current_datetime_context() -> dict:
    """Get current datetime context"""
    import pytz
    now = datetime.now()
    
    try:
        user_timezone = pytz.timezone('America/New_York')
        now_user_tz = now.astimezone(user_timezone)
    except:
        now_user_tz = now
    
    return {
        "current_date": now_user_tz.strftime("%Y-%m-%d"),
        "current_time_24h": now_user_tz.strftime("%H:%M"),
        "current_time_12h": now_user_tz.strftime("%I:%M %p"),
        "day_of_week": now_user_tz.strftime("%A"),
        "month_name": now_user_tz.strftime("%B"),
        "full_datetime": now_user_tz.strftime("%A, %B %d, %Y at %H:%M"),
        "timezone": str(now_user_tz.tzinfo),
        "iso_timestamp": now_user_tz.isoformat(),
        "unix_timestamp": int(now_user_tz.timestamp())
    }

#-- Main Chat Endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id)
):
    """
    Main chat endpoint - basic version without complex integrations
    """
    start_time = datetime.now()
    logger.info(f"🚀 DEBUG: process_chat_message called with message: '{request.message}'")
    
    try:
        # Get current date/time context
        datetime_context = get_current_datetime_context()
        logger.info(f"🕐 Current datetime context: {datetime_context['full_datetime']}")
        
        # Get AI components
        memory_manager = get_memory_manager(user_id)
        knowledge_engine = get_knowledge_engine()
        personality_engine = get_personality_engine()
        
        # Handle conversation thread
        thread_id = request.thread_id
        if not thread_id:
            thread_id = await memory_manager.create_conversation_thread(
                platform="web_interface",
                title=None
            )
        
        # Store user message
        user_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role="user",
            content=request.message,
            content_type="text"
        )
        
        # Get conversation context
        conversation_history, context_info = await memory_manager.get_context_for_ai(
            thread_id=thread_id,
            max_tokens=200000
        )
        
        # Get knowledge sources if enabled
        knowledge_sources = []
        if request.include_knowledge:
            knowledge_sources = await knowledge_engine.search_knowledge(
                query=request.message,
                max_results=5
            )
        
        # Build AI messages
        ai_messages = []
        
        # Get personality prompt
        personality_prompt = personality_engine.get_personality_prompt(request.personality_id)
        
        # Add critical datetime context for AI
        enhanced_personality_prompt = f"""{personality_prompt}

CRITICAL CURRENT CONTEXT - USE THIS INFORMATION:
📅 Current Date: {datetime_context['current_date']} ({datetime_context['day_of_week']})
🕐 Current Time: {datetime_context['current_time_24h']} (24-hour) / {datetime_context['current_time_12h']} (12-hour)
🌍 Full Context: {datetime_context['full_datetime']}
🕰️ Timezone: {datetime_context['timezone']}

IMPORTANT: Always use 24-hour time format (like {datetime_context['current_time_24h']}) when giving time in your responses.

User Context: The user is asking questions on {datetime_context['full_datetime']}.
When discussing time or dates, use the current information provided above."""

        ai_messages.append({
            "role": "system",
            "content": enhanced_personality_prompt
        })
        
        # Add knowledge context if available
        if knowledge_sources:
            knowledge_context = "RELEVANT KNOWLEDGE BASE INFORMATION:\n"
            for source in knowledge_sources:
                knowledge_context += f"- {source['title']}: {source['content'][:200]}...\n"
            ai_messages.append({
                "role": "system",
                "content": f"RELEVANT KNOWLEDGE:\n{knowledge_context}"
            })
        
        # Add conversation history
        ai_messages.extend(conversation_history)
        
        # Add current user message
        ai_messages.append({
            "role": "user",
            "content": request.message
        })
        
        # Get AI response
        openrouter_client = await get_openrouter_client()
        ai_response = await openrouter_client.get_completion(
            messages=ai_messages,
            model="anthropic/claude-3.5-sonnet:beta",
            max_tokens=4000,
            temperature=0.7
        )
        
        # Process through personality engine
        final_response = personality_engine.process_ai_response(
            response=ai_response,
            personality_id=request.personality_id,
            conversation_context=conversation_history
        )
        
        # Store AI response
        knowledge_source_ids = [source.get('id', '') for source in knowledge_sources]
        response_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role="assistant",
            content=final_response,
            model_used="anthropic/claude-3.5-sonnet:beta",
            knowledge_sources_used=knowledge_source_ids
        )
        
        # Calculate response time
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        logger.info(f"✅ Chat response generated in {response_time_ms}ms with current datetime: {datetime_context['full_datetime']}")
        
        return ChatResponse(
            message_id=response_message_id,
            thread_id=thread_id,
            response=final_response,
            personality_used=request.personality_id,
            response_time_ms=response_time_ms,
            knowledge_sources=knowledge_sources,
            timestamp=end_time
        )
        
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

#-- Other AI Endpoints
@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback_request: FeedbackRequest):
    """Submit feedback for AI learning"""
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
            "system_health": {
                "memory_active": True,
                "knowledge_engine_active": True,
                "learning_active": feedback_summary.get('learning_active', False),
                "chat_processing": "basic_version",
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
    
    # Overall health
    primary_healthy = results.get('openrouter', {}).get('status') == 'success'
    
    return {
        "providers": results,
        "system_status": "healthy" if primary_healthy else "degraded",
        "primary_provider": "openrouter",
        "chat_processing": "basic_version",
        "default_user_id": DEFAULT_USER_ID
    }

#-- Module Information Functions
def get_integration_info():
    """Get information about the AI brain integration"""
    return {
        "name": "AI Brain Router - Basic Chat Processing",
        "version": "2.0.0",
        "description": "Basic chat processing without complex integrations",
        "components": [
            "OpenRouter Client",
            "Digital Elephant Memory",
            "Knowledge Query Engine",
            "Personality Engine",
            "Feedback Processor"
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
            "250K context window",
            "500 conversation memory",
            "21K knowledge base integration",
            "4 personality system",
            "👍👎😄 feedback learning",
            "Real-time datetime context"
        ],
        "default_user_id": DEFAULT_USER_ID
    }

def check_module_health():
    """Check AI brain module health"""
    missing_vars = []
    
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "status": "ready" if len(missing_vars) == 0 else "needs_configuration",
        "chat_processing": "basic_version",
        "default_user_id": DEFAULT_USER_ID,
        "note": "Basic version without complex integrations"
    }
