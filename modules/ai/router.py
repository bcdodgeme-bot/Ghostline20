# modules/ai/router.py
"""
AI Brain Main Router for Syntax Prime V2
Ties together all AI components into FastAPI endpoints
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import time
import logging

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

# Import our AI brain components
from .openrouter_client import get_openrouter_client, cleanup_openrouter_client
from .inception_client import get_inception_client, cleanup_inception_client
from .conversation_manager import get_memory_manager, cleanup_memory_managers
from .knowledge_query import get_knowledge_engine
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

logger = logging.getLogger(__name__)

# Pydantic models for API requests/responses
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    personality_id: str = Field(default='syntaxprime', description="Personality to use")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    platform: str = Field(default='web', description="Platform (web/ios)")
    include_knowledge: bool = Field(default=True, description="Include knowledge base search")
    max_tokens: int = Field(default=4000, description="Maximum response tokens")
    temperature: float = Field(default=0.7, description="Response creativity")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    thread_id: str = Field(..., description="Conversation thread ID")
    message_id: str = Field(..., description="Response message ID")
    personality_id: str = Field(..., description="Personality used")
    model_used: str = Field(..., description="AI model used")
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    knowledge_sources: List[Dict] = Field(default_factory=list, description="Knowledge sources used")
    conversation_context: Dict = Field(..., description="Context metadata")

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

# Router setup
router = APIRouter(prefix="/ai", tags=["ai"])

# AI Brain orchestrator
class AIBrainOrchestrator:
    """
    Main orchestrator that coordinates all AI brain components
    """
    
    def __init__(self):
        self.default_user_id = "carl-default-user"  # Single user system
        self.fallback_attempts = 2
        
    async def process_chat_message(self, 
                                 chat_request: ChatRequest,
                                 user_id: str = None) -> ChatResponse:
        """
        Process a chat message through the complete AI brain pipeline
        """
        user_id = user_id or self.default_user_id
        start_time = time.time()
        
        # Get components
        memory_manager = get_memory_manager(user_id)
        knowledge_engine = get_knowledge_engine()
        personality_engine = get_personality_engine()
        
        # Handle conversation thread
        thread_id = chat_request.thread_id
        if not thread_id:
            thread_id = await memory_manager.create_conversation_thread(
                platform=chat_request.platform,
                title=None  # Will be auto-generated
            )
        
        # Store user message
        user_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role='user',
            content=chat_request.message
        )
        
        try:
            # Get conversation context for AI
            conversation_messages, context_info = await memory_manager.get_context_for_ai(
                thread_id, max_tokens=200000  # Leave room for knowledge and response
            )
            
            # Search knowledge base if requested
            knowledge_sources = []
            if chat_request.include_knowledge:
                knowledge_sources = await knowledge_engine.search_knowledge(
                    query=chat_request.message,
                    conversation_context=conversation_messages,
                    personality_id=chat_request.personality_id,
                    limit=5
                )
            
            # Get personality-enhanced system prompt
            system_prompt = personality_engine.get_personality_system_prompt(
                personality_id=chat_request.personality_id,
                conversation_context=conversation_messages,
                knowledge_context=knowledge_sources
            )
            
            # Build messages for AI
            ai_messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Add knowledge context if available
            if knowledge_sources:
                knowledge_context = self._build_knowledge_context(knowledge_sources)
                ai_messages.append({
                    "role": "system", 
                    "content": f"RELEVANT KNOWLEDGE:\n{knowledge_context}"
                })
            
            # Add conversation history
            ai_messages.extend(conversation_messages)
            
            # Add current user message
            ai_messages.append({
                "role": "user",
                "content": chat_request.message
            })
            
            # Get AI response with fallback
            ai_response, model_used = await self._get_ai_response_with_fallback(
                messages=ai_messages,
                max_tokens=chat_request.max_tokens,
                temperature=chat_request.temperature
            )
            
            # Process response through personality engine
            final_response = personality_engine.process_ai_response(
                response=ai_response,
                personality_id=chat_request.personality_id,
                conversation_context=conversation_messages
            )
            
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Store AI response
            knowledge_source_ids = [source['id'] for source in knowledge_sources]
            ai_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role='assistant',
                content=final_response,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources_used=knowledge_source_ids
            )
            
            # Build response
            chat_response = ChatResponse(
                response=final_response,
                thread_id=thread_id,
                message_id=ai_message_id,
                personality_id=chat_request.personality_id,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources=[
                    {
                        'id': source['id'],
                        'title': source['title'],
                        'snippet': source['snippet'],
                        'score': source['final_score']
                    }
                    for source in knowledge_sources
                ],
                conversation_context={
                    'thread_id': thread_id,
                    'message_count': context_info.get('total_messages', 0),
                    'tokens_used': context_info.get('estimated_tokens', 0),
                    'has_long_term_memory': context_info.get('has_memory_context', False)
                }
            )
            
            logger.info(f"Chat processed: {response_time_ms}ms, model: {model_used}, "
                       f"personality: {chat_request.personality_id}")
            
            return chat_response
            
        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            
            # Store error message
            error_message = f"Sorry, I encountered an error processing your message: {str(e)}"
            error_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role='assistant',
                content=error_message,
                model_used='error'
            )
            
            raise HTTPException(status_code=500, detail=str(e))
    
    def _build_knowledge_context(self, knowledge_sources: List[Dict]) -> str:
        """Build knowledge context string for AI prompt"""
        if not knowledge_sources:
            return "No specific knowledge context available."
        
        context_parts = []
        for i, source in enumerate(knowledge_sources[:3], 1):  # Top 3 sources
            context_parts.append(
                f"{i}. {source['title']} (Score: {source['final_score']:.2f})\n"
                f"   {source['snippet']}\n"
                f"   Project: {source.get('project_name', 'Unknown')}"
            )
        
        return "\n\n".join(context_parts)
    
    async def _get_ai_response_with_fallback(self, 
                                           messages: List[Dict],
                                           max_tokens: int,
                                           temperature: float) -> tuple[str, str]:
        """Get AI response with fallback between providers"""
        
        # Try OpenRouter first (primary)
        try:
            openrouter_client = await get_openrouter_client()
            response = await openrouter_client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            content = response['choices'][0]['message']['content']
            model_used = response.get('_metadata', {}).get('model_used', 'unknown')
            
            return content, model_used
            
        except Exception as e:
            logger.warning(f"OpenRouter failed, trying fallback: {e}")
            
            # Fallback to Inception Labs
            try:
                inception_client = await get_inception_client()
                response = await inception_client.chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                content = response['choices'][0]['message']['content']
                model_used = response.get('_metadata', {}).get('model_used', 'inception-fallback')
                
                return content, model_used
                
            except Exception as fallback_error:
                logger.error(f"Both AI providers failed: {fallback_error}")
                raise Exception(f"All AI providers failed. Primary: {e}, Fallback: {fallback_error}")
    
    async def process_feedback(self, 
                             feedback_request: FeedbackRequest,
                             user_id: str = None) -> FeedbackResponse:
        """Process user feedback for learning"""
        user_id = user_id or self.default_user_id
        
        # Get feedback processor
        feedback_processor = get_feedback_processor()
        
        # Get message details for context
        memory_manager = get_memory_manager(user_id)
        
        # We need to find the thread_id for this message
        # This is a simplified version - in production you'd query the database
        thread_id = "temp-thread-id"  # TODO: Get from message lookup
        
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

# Global orchestrator
orchestrator = AIBrainOrchestrator()

# API Endpoints
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(chat_request: ChatRequest):
    """
    Main chat endpoint - processes message through complete AI brain
    """
    return await orchestrator.process_chat_message(chat_request)

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback_request: FeedbackRequest):
    """
    Submit feedback for AI learning (👍👎🖕)
    """
    return await orchestrator.process_feedback(feedback_request)

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
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    conversations = await memory_manager.get_last_500_conversations()
    
    return {
        "conversations": conversations[:limit],
        "total_available": len(conversations)
    }

@router.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str, include_metadata: bool = False):
    """Get specific conversation history"""
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    
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
async def search_knowledge(q: str, 
                          personality: str = 'syntaxprime', 
                          limit: int = 10):
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
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    personality_engine = get_personality_engine()
    feedback_processor = get_feedback_processor()
    
    try:
        # Get conversation stats
        last_500 = await memory_manager.get_last_500_conversations()
        
        # Get personality stats
        personality_stats = personality_engine.get_personality_stats()
        
        # Get feedback summary
        feedback_summary = await feedback_processor.get_feedback_summary(
            orchestrator.default_user_id
        )
        
        return {
            "conversation_stats": {
                "total_conversations": len(last_500),
                "recent_conversations_30d": len([
                    c for c in last_500 
                    if c['last_message_at'] and 
                    (datetime.now() - datetime.fromisoformat(c['last_message_at'].replace('Z', '+00:00'))).days <= 30
                ])
            },
            "personality_stats": personality_stats,
            "feedback_stats": feedback_summary,
            "system_health": {
                "memory_active": True,
                "knowledge_engine_active": True,
                "learning_active": feedback_summary.get('learning_active', False)
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
        "fallback_provider": "inception_labs"
    }

# Cleanup on shutdown
@router.on_event("shutdown")
async def shutdown_ai_brain():
    """Cleanup AI brain components"""
    logger.info("Shutting down AI brain components...")
    
    await cleanup_openrouter_client()
    await cleanup_inception_client()
    await cleanup_memory_managers()
    
    logger.info("AI brain shutdown complete")

# Export router and integration info
def get_integration_info():
    """Get information about the AI brain integration"""
    return {
        "name": "AI Brain",
        "version": "2.0.0",
        "components": [
            "OpenRouter Client",
            "Inception Labs Client", 
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
            "👍👎🖕 feedback learning",
            "Provider fallback system"
        ]
    }

def check_module_health():
    """Check AI brain module health"""
    missing_vars = []
    
    # Check required environment variables
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    # Inception Labs is optional (can run in placeholder mode)
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "status": "ready" if len(missing_vars) == 0 else "needs_configuration"
    }