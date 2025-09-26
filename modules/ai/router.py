# modules/ai/router.py
"""
AI Brain Support Router for Syntax Prime V2 - NO CHAT ENDPOINT
Handles support endpoints only: personalities, stats, feedback, conversations
Chat processing handled by chat.py to avoid duplication
Date: 9/26/25 - Removed /ai/chat endpoint to stop duplication
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import time
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

#-- Support Endpoints Only (NO /ai/chat - that's handled by chat.py)

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
            "system_health": {
                "memory_active": True,
                "knowledge_engine_active": True,
                "learning_active": feedback_summary.get('learning_active', False),
                "chat_endpoint": "handled_by_chat_module",
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
        "chat_endpoint_status": "handled_by_chat_module",
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
    """Get information about the AI brain support integration"""
    return {
        "name": "AI Brain Support Router",
        "version": "2.0.0",
        "description": "Support endpoints only - chat handled by chat.py",
        "note": "Chat processing handled by chat.py module to avoid duplication",
        "components": [
            "Personality Engine",
            "Feedback Processor",
            "Conversation Manager",
            "Knowledge Query Engine",
            "AI Provider Testing"
        ],
        "endpoints": {
            "feedback": "/ai/feedback",
            "personalities": "/ai/personalities",
            "conversations": "/ai/conversations",
            "knowledge_search": "/ai/knowledge/search",
            "stats": "/ai/stats",
            "test": "/ai/test"
        },
        "features": [
            "👍👎😄 feedback learning",
            "Personality system management",
            "Conversation history access",
            "Knowledge base search",
            "AI provider health monitoring",
            "Usage statistics"
        ],
        "default_user_id": DEFAULT_USER_ID
    }

def check_module_health():
    """Check AI brain support module health"""
    missing_vars = []
    
    # Check required environment variables
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "status": "ready" if len(missing_vars) == 0 else "needs_configuration",
        "chat_endpoint_status": "handled_by_chat_module",
        "default_user_id": DEFAULT_USER_ID,
        "note": "This module handles support endpoints only - chat in chat.py"
    }
