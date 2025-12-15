# modules/ai/conversation_manager.py
"""
Digital Elephant Conversation Manager for Syntax Prime V2
Never forgets. Maintains 250K context + last 500 conversations.

Updated: 2025 - Added bounded TTL cache, fixed cleanup methods, removed dead code
"""

import asyncio
import uuid
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional, Any, Tuple

from ..core.database import db_manager

logger = logging.getLogger(__name__)


# =============================================================================
# TTL Cache (same implementation as knowledge_query.py for consistency)
# =============================================================================

class TTLCache:
    """
    Thread-safe LRU cache with TTL (time-to-live) expiration.
    
    Features:
    - Maximum size limit with LRU eviction
    - TTL-based expiration
    - Thread-safe operations
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired."""
        with self._lock:
            if key not in self._cache:
                return None
            
            cached_time, value = self._cache[key]
            elapsed = (datetime.now() - cached_time).total_seconds()
            
            if elapsed >= self._ttl_seconds:
                del self._cache[key]
                return None
            
            self._cache.move_to_end(key)
            return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (datetime.now(), value)
    
    def invalidate(self, key_pattern: str = None) -> int:
        """
        Invalidate cache entries matching pattern.
        If pattern is None, clears entire cache.
        Returns count of removed entries.
        """
        with self._lock:
            if key_pattern is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            
            keys_to_remove = [k for k in self._cache.keys() if key_pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
            return len(keys_to_remove)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        removed = 0
        with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, (cached_time, _) in self._cache.items()
                if (now - cached_time).total_seconds() >= self._ttl_seconds
            ]
            
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        
        return removed
    
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds
            }


# =============================================================================
# Digital Elephant Memory Manager
# =============================================================================

class DigitalElephantMemory:
    """
    The Digital Elephant - never forgets, always remembers
    Manages conversation threads, messages, and long-term memory
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.max_context_tokens = 250000  # 250K context window
        self.max_stored_conversations = 500  # Last 500 conversations always accessible
        self.current_thread_id: Optional[str] = None
        
        # Bounded cache for conversation history
        # 5-minute TTL, max 50 cached conversations per user
        self._conversation_cache = TTLCache(max_size=50, ttl_seconds=300)
    
    async def create_conversation_thread(
        self,
        platform: str = 'web',
        title: str = None,
        primary_project_id: int = None
    ) -> str:
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
            result = await db_manager.fetch_one(
                insert_query,
                thread_id,
                self.user_id,
                title,
                platform,
                primary_project_id
            )
            
            self.current_thread_id = thread_id
            logger.info(f"Created conversation thread: {thread_id}")
            return thread_id
            
        except Exception as e:
            logger.error(f"Failed to create conversation thread: {e}")
            raise
    
    async def add_message(
        self,
        thread_id: str,
        role: str,  # 'user' or 'assistant'
        content: str,
        content_type: str = 'text',
        model_used: str = None,
        response_time_ms: int = None,
        knowledge_sources_used: List[str] = None,
        extracted_preferences: Dict = None,
        metadata: Dict = None
    ) -> str:
        """
        Add a message to a conversation thread
        
        Args:
            thread_id: UUID of the thread
            role: 'user' or 'assistant'
            content: Message content
            content_type: Type of content (default 'text')
            model_used: AI model used for assistant messages
            response_time_ms: Response generation time
            knowledge_sources_used: List of knowledge entry IDs referenced
            extracted_preferences: Any preferences extracted from user message
            metadata: Optional structured data for this message (JSONB)
        
        Returns:
            message_id: UUID of the created message
        """
        message_id = str(uuid.uuid4())
        
        # Ensure all values are JSON serializable (convert UUIDs to strings)
        if knowledge_sources_used:
            knowledge_sources_used = [str(item) for item in knowledge_sources_used]

        # Prepare JSONB fields
        knowledge_sources_json = json.dumps(knowledge_sources_used or [])
        preferences_json = json.dumps(extracted_preferences or {})
        metadata_json = json.dumps(metadata or {})
        
        insert_query = """
        INSERT INTO conversation_messages
        (id, thread_id, user_id, role, content, content_type, 
         response_time_ms, model_used, knowledge_sources_used, extracted_preferences, metadata, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11::jsonb, NOW(), NOW())
        RETURNING id;
        """
        
        try:
            result = await db_manager.fetch_one(
                insert_query,
                message_id,
                thread_id,
                self.user_id,
                role,
                content,
                content_type,
                response_time_ms,
                model_used,
                knowledge_sources_json,
                preferences_json,
                metadata_json
            )
            
            # Update thread metadata
            await self._update_thread_after_message(thread_id, content if role == 'user' else None)
            
            # Invalidate cache for this thread
            self._conversation_cache.invalidate(thread_id)
            
            logger.info(f"Added {role} message to thread {thread_id}: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            raise
    
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
    
    async def get_conversation_history(
        self,
        thread_id: str,
        limit: int = None,
        include_metadata: bool = False
    ) -> List[Dict]:
        """
        Get conversation history for a thread
        
        Args:
            thread_id: UUID of the thread
            limit: Maximum messages to return (None for all)
            include_metadata: Include full message metadata
            
        Returns:
            List of message dicts
        """
        # Check cache first
        cache_key = f"{thread_id}_{limit}_{include_metadata}"
        cached = self._conversation_cache.get(cache_key)
        if cached is not None:
            return cached
        
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
            self._conversation_cache.set(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            raise
    
    async def get_context_for_ai(
        self,
        thread_id: str,
        max_tokens: int = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Get context for AI conversation, managing 250K token limit
        
        Args:
            thread_id: UUID of the thread
            max_tokens: Override default token limit
        
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
    
    async def get_thread_info(self, thread_id: str) -> Optional[Dict]:
        """Get metadata about a conversation thread"""
        query = """
        SELECT id, title, platform, status, message_count, 
               created_at, updated_at, last_message_at
        FROM conversation_threads
        WHERE id = $1 AND user_id = $2
        """
        
        try:
            result = await db_manager.fetch_one(query, thread_id, self.user_id)
            if result:
                return {
                    'id': result['id'],
                    'title': result['title'],
                    'platform': result['platform'],
                    'status': result['status'],
                    'message_count': result['message_count'],
                    'created_at': result['created_at'].isoformat() if result['created_at'] else None,
                    'updated_at': result['updated_at'].isoformat() if result['updated_at'] else None,
                    'last_message_at': result['last_message_at'].isoformat() if result['last_message_at'] else None
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get thread info: {e}")
            return None
    
    async def list_threads(
        self,
        limit: int = 50,
        status: str = 'active'
    ) -> List[Dict]:
        """List conversation threads for this user"""
        query = """
        SELECT id, title, platform, status, message_count,
               created_at, updated_at, last_message_at
        FROM conversation_threads
        WHERE user_id = $1 AND status = $2
        ORDER BY last_message_at DESC
        LIMIT $3
        """
        
        try:
            results = await db_manager.fetch_all(query, self.user_id, status, limit)
            return [
                {
                    'id': r['id'],
                    'title': r['title'],
                    'platform': r['platform'],
                    'status': r['status'],
                    'message_count': r['message_count'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    'last_message_at': r['last_message_at'].isoformat() if r['last_message_at'] else None
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to list threads: {e}")
            return []
    
    def clear_cache(self) -> None:
        """Clear the conversation cache"""
        self._conversation_cache.clear()
        logger.debug(f"Cleared conversation cache for user {self.user_id}")
    
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self._conversation_cache.stats()
    
    async def cleanup(self) -> None:
        """Cleanup resources (call on shutdown)"""
        expired = self._conversation_cache.cleanup_expired()
        if expired > 0:
            logger.debug(f"Cleaned up {expired} expired cache entries for user {self.user_id}")
        self._conversation_cache.clear()


# =============================================================================
# Global Memory Manager Registry
# =============================================================================

# Configuration for manager registry
MAX_CACHED_MANAGERS = 20  # Maximum number of user managers to keep in memory

_memory_managers: Dict[str, DigitalElephantMemory] = {}
_manager_access_times: Dict[str, datetime] = {}
_managers_lock = Lock()


def get_memory_manager(user_id: str) -> DigitalElephantMemory:
    """
    Get or create a memory manager for a user.
    
    Uses LRU eviction to prevent unbounded growth.
    """
    global _memory_managers, _manager_access_times
    
    with _managers_lock:
        # Update access time
        _manager_access_times[user_id] = datetime.now()
        
        # Return existing manager if available
        if user_id in _memory_managers:
            return _memory_managers[user_id]
        
        # Evict oldest managers if at capacity
        while len(_memory_managers) >= MAX_CACHED_MANAGERS:
            # Find oldest accessed manager
            oldest_user = min(_manager_access_times, key=_manager_access_times.get)
            
            # Clean it up
            old_manager = _memory_managers.pop(oldest_user, None)
            _manager_access_times.pop(oldest_user, None)
            
            if old_manager:
                old_manager.clear_cache()
                logger.debug(f"Evicted memory manager for user {oldest_user}")
        
        # Create new manager
        _memory_managers[user_id] = DigitalElephantMemory(user_id)
        logger.debug(f"Created memory manager for user {user_id}")
        
        return _memory_managers[user_id]


async def cleanup_memory_managers() -> None:
    """Cleanup all memory managers (call on app shutdown)"""
    global _memory_managers, _manager_access_times
    
    with _managers_lock:
        for user_id, manager in _memory_managers.items():
            try:
                await manager.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up manager for {user_id}: {e}")
        
        _memory_managers.clear()
        _manager_access_times.clear()
    
    logger.info("All memory managers cleaned up")


def memory_manager_stats() -> Dict[str, Any]:
    """Get statistics about memory managers"""
    with _managers_lock:
        return {
            "active_managers": len(_memory_managers),
            "max_managers": MAX_CACHED_MANAGERS,
            "user_ids": list(_memory_managers.keys())
        }
