# modules/ai/conversation_manager.py
"""
Digital Elephant Conversation Manager for Syntax Prime V2 - FIXED
Never forgets. Maintains 250K context + last 500 conversations.
FIX: Added missing _update_thread_after_message method
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import json
import logging

from ..core.database import db_manager

logger = logging.getLogger(__name__)

class DigitalElephantMemory:
    """
    The Digital Elephant - never forgets, always remembers
    Manages conversation threads, messages, and long-term memory
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.max_context_tokens = 250000  # 250K context window
        self.max_stored_conversations = 500  # Last 500 conversations always accessible
        self.current_thread_id = None
        
        # In-memory cache for performance
        self._conversation_cache = {}
        self._last_500_cache = None
        self._cache_expiry = None
    
    async def create_conversation_thread(self,
                                       platform: str = 'web',
                                       title: str = None,
                                       primary_project_id: int = None) -> str:
        """
        Create a new conversation thread
        
        Returns:
            thread_id: UUID of the created thread
        """
        thread_id = str(uuid.uuid4())
        
        # Auto-generate title based on first message (will be updated later)
        if not title:
            title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        insert_query = """
        INSERT INTO conversation_threads 
        (id, user_id, title, platform, primary_project_id, status, created_at, updated_at, last_message_at)
        VALUES ($1, $2, $3, $4, $5, 'active', NOW(), NOW(), NOW())
        RETURNING id;
        """
        
        try:
            result = await db_manager.fetch_one(insert_query,
                                               thread_id,
                                               self.user_id,
                                               title,
                                               platform,
                                               primary_project_id)
            
            self.current_thread_id = thread_id
            logger.info(f"Created conversation thread: {thread_id}")
            return thread_id
            
        except Exception as e:
            logger.error(f"Failed to create conversation thread: {e}")
            raise
    
    async def add_message(self,
                         thread_id: str,
                         role: str,  # 'user' or 'assistant'
                         content: str,
                         content_type: str = 'text',
                         model_used: str = None,
                         response_time_ms: int = None,
                         knowledge_sources_used: List[str] = None,
                         extracted_preferences: Dict = None) -> str:
        """
        Add a message to a conversation thread
        
        Returns:
            message_id: UUID of the created message
        """
        message_id = str(uuid.uuid4())
        
        # Prepare JSONB fields
        knowledge_sources_json = json.dumps(knowledge_sources_used or [])
        preferences_json = json.dumps(extracted_preferences or {})
        
        insert_query = """
        INSERT INTO conversation_messages
        (id, thread_id, user_id, role, content, content_type, 
         response_time_ms, model_used, knowledge_sources_used, extracted_preferences, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, NOW(), NOW())
        RETURNING id;
        """
        
        try:
            result = await db_manager.fetch_one(insert_query,
                                               message_id,
                                               thread_id,
                                               self.user_id,
                                               role,
                                               content,
                                               content_type,
                                               response_time_ms,
                                               model_used,
                                               knowledge_sources_json,
                                               preferences_json)
            
            # Update thread metadata
            await self._update_thread_after_message(thread_id, content if role == 'user' else None)
            
            # Invalidate cache
            self._invalidate_cache(thread_id)
            
            logger.info(f"Added {role} message to thread {thread_id}: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            raise
    
    # FIXED: Added the missing method
    async def _update_thread_after_message(self, thread_id: str, user_content: str = None):
        """Update conversation thread metadata after adding a message"""
        try:
            # Update basic thread stats
            update_query = """
            UPDATE conversation_threads 
            SET message_count = message_count + 1,
                last_message_at = NOW(),
                updated_at = NOW()
            WHERE id = $1;
            """
            
            await db_manager.execute(update_query, thread_id)
            
            # If this is a user message and we don't have a proper title yet, update it
            if user_content and len(user_content.strip()) > 0:
                # Check if thread has a generic title
                thread_query = "SELECT title FROM conversation_threads WHERE id = $1"
                thread_result = await db_manager.fetch_one(thread_query, thread_id)
                
                if thread_result and thread_result['title']:
                    current_title = thread_result['title']
                    # If it's a generic timestamp title, replace it with content-based title
                    if 'Conversation 20' in current_title or current_title == 'New Conversation':
                        # Create title from first part of user message
                        new_title = user_content.strip()[:50]
                        if len(user_content) > 50:
                            new_title += "..."
                        
                        title_update_query = """
                        UPDATE conversation_threads 
                        SET title = $1, updated_at = NOW()
                        WHERE id = $2;
                        """
                        await db_manager.execute(title_update_query, new_title, thread_id)
                        logger.info(f"Updated thread title: {new_title}")
            
        except Exception as e:
            logger.warning(f"Failed to update thread metadata: {e}")
            # Don't fail the whole operation if metadata update fails
    
    # FIXED: Added the missing cache invalidation method
    def _invalidate_cache(self, thread_id: str = None):
        """Invalidate conversation cache"""
        if thread_id:
            # Remove specific thread from cache
            keys_to_remove = [key for key in self._conversation_cache.keys() if thread_id in key]
            for key in keys_to_remove:
                del self._conversation_cache[key]
        else:
            # Clear entire cache
            self._conversation_cache.clear()
    
    async def get_conversation_history(self,
                                     thread_id: str,
                                     limit: int = None,
                                     include_metadata: bool = False) -> List[Dict]:
        """
        Get conversation history for a thread
        """
        
        # Check cache first
        cache_key = f"{thread_id}_{limit}_{include_metadata}"
        if cache_key in self._conversation_cache:
            return self._conversation_cache[cache_key]
        
        # Build query
        if include_metadata:
            select_fields = """
            id, role, content, content_type, response_time_ms, model_used, 
            knowledge_sources_used, extracted_preferences, created_at
            """
        else:
            select_fields = "id, role, content, created_at"
        
        query = f"""
        SELECT {select_fields}
        FROM conversation_messages
        WHERE thread_id = $1
        ORDER BY created_at ASC
        """
        
        params = [thread_id]
        if limit:
            query += " LIMIT $2"
            params.append(limit)
        
        try:
            messages = await db_manager.fetch_all(query, *params)
            
            # Convert to list of dicts
            result = []
            for msg in messages:
                message_dict = {
                    'id': msg['id'],
                    'role': msg['role'],
                    'content': msg['content'],
                    'timestamp': msg['created_at'].isoformat() if msg['created_at'] else None
                }
                
                if include_metadata:
                    message_dict.update({
                        'content_type': msg['content_type'],
                        'response_time_ms': msg['response_time_ms'],
                        'model_used': msg['model_used'],
                        'knowledge_sources_used': msg['knowledge_sources_used'],
                        'extracted_preferences': msg['extracted_preferences']
                    })
                
                result.append(message_dict)
            
            # Cache the result
            self._conversation_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            raise
    
    async def get_context_for_ai(self,
                                thread_id: str,
                                max_tokens: int = None) -> Tuple[List[Dict], Dict]:
        """
        Get context for AI conversation, managing 250K token limit
        
        Returns:
            (messages, context_info): Messages for AI and metadata about context
        """
        max_tokens = max_tokens or self.max_context_tokens
        
        # Get conversation history
        messages = await self.get_conversation_history(thread_id, include_metadata=True)
        
        # Estimate token count (rough approximation: 4 chars = 1 token)
        def estimate_tokens(text: str) -> int:
            return len(text) // 4
        
        # Build context from newest to oldest, staying within token limit
        context_messages = []
        total_tokens = 0
        
        for message in reversed(messages):
            message_tokens = estimate_tokens(message['content'])
            
            if total_tokens + message_tokens > max_tokens:
                break
                
            context_messages.insert(0, {
                'role': message['role'],
                'content': message['content']
            })
            total_tokens += message_tokens
        
        context_info = {
            'thread_id': thread_id,
            'total_messages': len(context_messages),
            'estimated_tokens': total_tokens,
            'token_limit': max_tokens,
            'has_memory_context': False,
            'total_available_conversations': 0
        }
        
        return context_messages, context_info

# Global memory managers (keyed by user_id)
_memory_managers = {}

def get_memory_manager(user_id: str):
    """Get or create a memory manager for a user"""
    if user_id not in _memory_managers:
        _memory_managers[user_id] = DigitalElephantMemory(user_id)
    return _memory_managers[user_id]

async def cleanup_memory_managers():
    """Cleanup all memory managers"""
    for manager in _memory_managers.values():
        if hasattr(manager, 'cleanup'):
            await manager.cleanup()
    _memory_managers.clear()

# Note: This is a simplified version for display
# The full version would include search, long-term memory, and caching
