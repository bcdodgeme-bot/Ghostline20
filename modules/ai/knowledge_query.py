# modules/ai/knowledge_query.py
"""
Knowledge Query Engine for Syntax Prime V2
Intelligently queries 21K+ knowledge entries with context awareness

Updated: 2025 - Fixed cache TTL bug (.seconds → .total_seconds()), 
                added bounded LRU cache with automatic cleanup
"""

import asyncio
import re
import json
import logging
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from threading import Lock

from ..core.database import db_manager

logger = logging.getLogger(__name__)


# =============================================================================
# LRU Cache with TTL Support
# =============================================================================

class TTLCache:
    """
    Thread-safe LRU cache with TTL (time-to-live) expiration.
    
    Features:
    - Maximum size limit with LRU eviction
    - TTL-based expiration (correctly using total_seconds)
    - Automatic cleanup of stale entries
    - Thread-safe operations
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
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
                # Expired - remove and return None
                del self._cache[key]
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        with self._lock:
            # If key exists, remove it first (will be re-added at end)
            if key in self._cache:
                del self._cache[key]
            
            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            # Add new entry
            self._cache[key] = (datetime.now(), value)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        removed = 0
        with self._lock:
            now = datetime.now()
            expired_keys = []
            
            for key, (cached_time, _) in self._cache.items():
                if (now - cached_time).total_seconds() >= self._ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        
        return removed
    
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            now = datetime.now()
            expired_count = sum(
                1 for cached_time, _ in self._cache.values()
                if (now - cached_time).total_seconds() >= self._ttl_seconds
            )
            
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
                "expired_pending_cleanup": expired_count
            }


# =============================================================================
# Knowledge Query Engine
# =============================================================================

class KnowledgeQueryEngine:
    """
    Intelligent knowledge base querying system
    Uses PostgreSQL full-text search, relevance scoring, and context awareness
    """
    
    def __init__(self):
        # Bounded cache with 1-hour TTL and max 200 entries
        self.cache = TTLCache(max_size=200, ttl_seconds=3600)
        
        # Knowledge source priorities
        self.source_priorities = {
            'conversation': 1.0,  # Highest priority - your actual conversations
            'raw_data': 0.8,      # Raw business/health data
            'processed': 0.9      # Processed knowledge entries
        }
        
        # Project relevance boosts
        self.project_boosts = {
            'AMCF': 0.2,           # Boost AMCF-related content when relevant
            'Business': 0.15,      # Business knowledge boost
            'Health': 0.15         # Health knowledge boost
        }
    
    async def search_knowledge(self,
                             query: str,
                             conversation_context: List[Dict] = None,
                             personality_id: str = 'syntaxprime',
                             limit: int = 10,
                             min_relevance: float = 0.01) -> List[Dict]:
        """
        Search knowledge base with context awareness
        
        Args:
            query: Search query
            conversation_context: Recent conversation for context
            personality_id: Current personality for relevance tuning
            limit: Maximum results
            min_relevance: Minimum relevance score
            
        Returns:
            List of relevant knowledge entries with scores
        """
        # Cache key
        cache_key = f"search_{hash(query)}_{personality_id}_{limit}"
        
        # Check cache (TTLCache handles expiration correctly)
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for query: {query[:50]}")
            return cached_result
        
        # Extract context keywords from conversation
        context_keywords = self._extract_context_keywords(conversation_context)
        
        # Build enhanced search query
        enhanced_query = self._build_enhanced_query(query, context_keywords)
        
        # Perform the search
        # PHASE 1: Try full-text search
        logger.info(f"📊 Phase 1: Full-text search for '{query}'")
        search_results = await self._execute_knowledge_search(enhanced_query, limit * 3)
        logger.info(f"📊 Full-text search returned {len(search_results)} results")

        # PHASE 2: If full-text returns nothing or low-quality results, use pattern matching
        needs_fallback = False
        if not search_results:
            needs_fallback = True
            logger.info("⚠️  Full-text search returned 0 results - using pattern matching fallback")
        elif len(search_results) < 3:
            needs_fallback = True
            logger.info(f"⚠️  Full-text search returned only {len(search_results)} results - augmenting with pattern matching")

        if needs_fallback:
            logger.info(f"🔄 Phase 2: Pattern matching search for '{query}'")
            pattern_results = await self._pattern_match_search(query, limit * 2)
            logger.info(f"📊 Pattern matching found {len(pattern_results)} additional results")
            
            # Merge results, avoiding duplicates
            existing_ids = {r['id'] for r in search_results}
            for result in pattern_results:
                if result['id'] not in existing_ids:
                    search_results.append(result)
        
        # Score and rank results
        scored_results = await self._score_and_rank_results(
            search_results,
            query,
            context_keywords,
            personality_id
        )
        
        # Filter by minimum relevance and limit
        final_results = [
            result for result in scored_results
            if result['final_score'] >= min_relevance
        ][:limit]
        
        # Update access counts
        await self._update_access_counts([r['id'] for r in final_results])
        
        # Cache the results
        self.cache.set(cache_key, final_results)
        
        logger.info(f"Knowledge search for '{query}': {len(final_results)} results (personality: {personality_id})")
        return final_results
    
    def _extract_context_keywords(self, conversation_context: List[Dict]) -> List[str]:
        """Extract relevant keywords from recent conversation context"""
        if not conversation_context:
            return []
        
        # Get last few messages for context
        recent_messages = conversation_context[-5:]  # Last 5 messages
        
        # Combine all text
        text = ' '.join([msg.get('content', '') for msg in recent_messages])
        
        # Extract keywords using simple techniques
        # Remove common words and focus on nouns/important terms
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'this', 'that', 'these', 'those',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can'
        }
        
        # Extract words, filter stop words, and prioritize longer words
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        keywords = [
            word for word in words
            if len(word) > 3 and word not in stop_words
        ]
        
        # Get most frequent keywords
        keyword_counts = Counter(keywords)
        
        # Return top keywords
        return [word for word, count in keyword_counts.most_common(10)]
    
    async def _pattern_match_search(self, query: str, limit: int) -> List[Dict]:
        """
        Fallback pattern matching search using ILIKE
        Used when full-text search fails or returns poor results
        """
        pattern_query = """
        SELECT 
            ke.id,
            ke.title,
            ke.content,
            ke.content_type,
            ke.word_count,
            ke.access_count,
            ke.relevance_score,
            ke.key_topics,
            ke.project_id,
            ke.summary,
            ke.created_at,
            kp.name as project_name,
            kp.category as project_category,
            ks.name as source_name,
            ks.source_type,
            -- Rank by position of term in content
            CASE 
                WHEN ke.title ILIKE $1 THEN 1.0
                WHEN POSITION(LOWER($2) IN LOWER(ke.content)) < 500 THEN 0.8
                WHEN POSITION(LOWER($2) IN LOWER(ke.content)) < 2000 THEN 0.6
                WHEN POSITION(LOWER($2) IN LOWER(ke.content)) < 5000 THEN 0.4
                ELSE 0.3
            END as search_rank,
            -- Context snippet
            SUBSTRING(
                ke.content,
                GREATEST(1, POSITION(LOWER($2) IN LOWER(ke.content)) - 100),
                300
            ) as snippet
        FROM knowledge_entries ke
        LEFT JOIN knowledge_projects kp ON ke.project_id = kp.id
        LEFT JOIN knowledge_sources ks ON ke.source_id = ks.id
        WHERE (ke.content ILIKE $1 OR ke.title ILIKE $1)
        AND ke.processed = true
        ORDER BY search_rank DESC, ke.access_count DESC, ke.relevance_score DESC
        LIMIT $3;
        """
        
        try:
            search_pattern = f'%{query}%'
            results = await db_manager.fetch_all(pattern_query, search_pattern, query, limit)
            
            # Convert to standard format
            formatted_results = []
            for row in results:
                formatted_results.append({
                    'id': row['id'],
                    'title': row['title'],
                    'content': row['content'],
                    'content_type': row['content_type'],
                    'word_count': row['word_count'],
                    'access_count': row['access_count'],
                    'relevance_score': float(row['relevance_score']) if row['relevance_score'] else 5.0,
                    'key_topics': row['key_topics'] or [],
                    'project_id': row['project_id'],
                    'project_name': row['project_name'],
                    'project_category': row['project_category'],
                    'source_name': row['source_name'],
                    'source_type': row['source_type'],
                    'search_rank': float(row['search_rank']),
                    'snippet': row['snippet'],
                    'created_at': row['created_at']
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Pattern match search failed: {e}")
            return []
    
    def _build_enhanced_query(self, original_query: str, context_keywords: List[str]) -> str:
        """Build an enhanced search query with context"""
        query_parts = [original_query]
        
        # Add context keywords with lower weight
        if context_keywords:
            # Take top 3 context keywords
            top_context = context_keywords[:3]
            context_query = ' OR '.join(top_context)
            query_parts.append(f"({context_query})")
        
        return ' '.join(query_parts)
    
    async def _execute_knowledge_search(self, query: str, limit: int) -> List[Dict]:
        """Execute the actual database search"""
        search_query = """
        SELECT 
            ke.id,
            ke.title,
            ke.content,
            ke.content_type,
            ke.word_count,
            ke.access_count,
            ke.relevance_score,
            ke.key_topics,
            ke.project_id,
            ke.summary,
            ke.created_at,
            kp.name as project_name,
            kp.category as project_category,
            ks.name as source_name,
            ks.source_type,
            -- Full-text search ranking
            ts_rank(ke.search_vector, plainto_tsquery('english', $1)) as search_rank,
            -- Highlighted content snippet
            ts_headline('english', ke.content, plainto_tsquery('english', $1), 
                       'MaxWords=50, MinWords=20, MaxFragments=2') as snippet
        FROM knowledge_entries ke
        LEFT JOIN knowledge_projects kp ON ke.project_id = kp.id
        LEFT JOIN knowledge_sources ks ON ke.source_id = ks.id
        WHERE ke.search_vector @@ plainto_tsquery('english', $1)
        AND ke.processed = true
        ORDER BY search_rank DESC, ke.relevance_score DESC, ke.access_count DESC
        LIMIT $2;
        """
        
        try:
            results = await db_manager.fetch_all(search_query, query, limit)
            
            # Convert to list of dicts with proper formatting
            knowledge_results = []
            for row in results:
                result = {
                    'id': row['id'],
                    'title': row['title'],
                    'content': row['content'],
                    'content_type': row['content_type'],
                    'word_count': row['word_count'],
                    'access_count': row['access_count'],
                    'relevance_score': float(row['relevance_score']) if row['relevance_score'] else 5.0,
                    'key_topics': row['key_topics'] or [],
                    'project_id': row['project_id'],
                    'project_name': row['project_name'],
                    'project_category': row['project_category'],
                    'source_name': row['source_name'],
                    'source_type': row['source_type'],
                    'search_rank': float(row['search_rank']) if row['search_rank'] else 0.0,
                    'snippet': row['snippet'],
                    'summary': row['summary'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                }
                knowledge_results.append(result)
            
            return knowledge_results
            
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            return []
    
    async def _score_and_rank_results(self,
                                    results: List[Dict],
                                    original_query: str,
                                    context_keywords: List[str],
                                    personality_id: str) -> List[Dict]:
        """Apply advanced scoring and ranking to search results"""
        scored_results = []
        
        for result in results:
            # Base search rank from PostgreSQL
            base_score = result['search_rank']
            
            # Source type multiplier
            source_multiplier = self.source_priorities.get(result['source_type'], 0.5)
            
            # Project relevance boost
            project_boost = 0.0
            if result['project_name'] and result['project_name'] in self.project_boosts:
                project_boost = self.project_boosts[result['project_name']]
            
            # Context keyword bonus
            context_bonus = 0.0
            if context_keywords:
                content_lower = result['content'].lower()
                title_lower = (result['title'] or '').lower()
                
                for keyword in context_keywords:
                    if keyword in content_lower:
                        context_bonus += 0.1
                    if keyword in title_lower:
                        context_bonus += 0.2  # Title matches are more important
            
            # Access count bonus (popular content gets slight boost)
            access_bonus = min(0.1, result['access_count'] / 100.0)  # Cap at 0.1
            
            # Relevance score from database
            stored_relevance = result['relevance_score'] / 10.0  # Normalize to 0-1
            
            # Word count factor (prefer substantial content, but not too long)
            word_count = result['word_count'] or 0
            if 100 <= word_count <= 5000:
                word_factor = 1.0
            elif word_count < 100:
                word_factor = 0.7  # Too short
            else:
                word_factor = 0.9  # Very long content
            
            # Personality-specific adjustments
            personality_factor = self._get_personality_factor(personality_id, result)
            
            # Calculate final score
            final_score = (
                (base_score * source_multiplier * word_factor * personality_factor) +
                project_boost +
                context_bonus +
                access_bonus +
                (stored_relevance * 0.2)  # Weight stored relevance less
            )
            
            # Add scoring metadata
            result['scoring'] = {
                'base_score': base_score,
                'source_multiplier': source_multiplier,
                'project_boost': project_boost,
                'context_bonus': context_bonus,
                'access_bonus': access_bonus,
                'stored_relevance': stored_relevance,
                'word_factor': word_factor,
                'personality_factor': personality_factor
            }
            
            result['final_score'] = final_score
            scored_results.append(result)
        
        # Sort by final score
        scored_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        return scored_results
    
    def _get_personality_factor(self, personality_id: str, result: Dict) -> float:
        """Adjust scoring based on personality preferences"""
        
        # SyntaxPrime prefers conversation history and creative content
        if personality_id == 'syntaxprime':
            if result['content_type'] == 'conversation':
                return 1.2
            elif result['project_category'] in ['client_work', 'creative']:
                return 1.1
            return 1.0
        
        # SyntaxBot prefers structured, technical content
        elif personality_id == 'syntaxbot':
            if result['source_type'] == 'raw_data':
                return 1.2
            elif result['project_category'] == 'domain_knowledge':
                return 1.15
            return 1.0
        
        # Nil.exe prefers abstract, creative content
        elif personality_id == 'nilexe':
            if 'creative' in str(result['key_topics']).lower():
                return 1.3
            elif result['content_type'] == 'conversation':
                return 1.1
            return 1.0
        
        # GGPT prefers concise, actionable content
        elif personality_id == 'ggpt':
            word_count = result['word_count'] or 0
            if 100 <= word_count <= 1000:  # Prefers shorter content
                return 1.2
            elif word_count > 5000:
                return 0.8  # Penalize very long content
            return 1.0
        
        return 1.0  # Default factor
    
    async def _update_access_counts(self, entry_ids: List[str]):
        """Update access counts for retrieved knowledge entries"""
        if not entry_ids:
            return
        
        placeholders = ','.join(['$' + str(i+1) for i in range(len(entry_ids))])
        
        update_query = f"""
        UPDATE knowledge_entries 
        SET access_count = access_count + 1,
            last_accessed = NOW()
        WHERE id IN ({placeholders});
        """
        
        try:
            await db_manager.execute(update_query, *entry_ids)
        except Exception as e:
            logger.error(f"Failed to update access counts: {e}")
    
    async def get_related_entries(self,
                                entry_id: str,
                                limit: int = 5) -> List[Dict]:
        """Get entries related to a specific knowledge entry"""
        
        # First, get the entry details
        entry_query = """
        SELECT key_topics, project_id, content_type, title
        FROM knowledge_entries 
        WHERE id = $1;
        """
        
        entry = await db_manager.fetch_one(entry_query, entry_id)
        if not entry:
            return []
        
        # Build related search based on key topics and project
        search_conditions = []
        params = []
        
        # Same project
        if entry['project_id']:
            search_conditions.append("project_id = $" + str(len(params) + 1))
            params.append(entry['project_id'])
        
        # Similar key topics
        if entry['key_topics']:
            topics_condition = "key_topics && $" + str(len(params) + 1) + "::jsonb"
            search_conditions.append(topics_condition)
            params.append(json.dumps(entry['key_topics']))
        
        # Same content type
        search_conditions.append("content_type = $" + str(len(params) + 1))
        params.append(entry['content_type'])
        
        # Exclude the original entry
        search_conditions.append("id != $" + str(len(params) + 1))
        params.append(entry_id)
        
        # Build final query
        related_query = f"""
        SELECT 
            id, title, content_type, word_count, relevance_score,
            key_topics, project_id, summary,
            LEFT(content, 200) as preview
        FROM knowledge_entries
        WHERE processed = true
        AND ({' OR '.join(search_conditions)})
        ORDER BY 
            CASE WHEN project_id = $1 THEN 2 ELSE 0 END +
            CASE WHEN key_topics && $2::jsonb THEN 1 ELSE 0 END +
            relevance_score DESC,
            access_count DESC
        LIMIT $""" + str(len(params) + 1)
        
        params.append(limit)
        
        try:
            results = await db_manager.fetch_all(related_query, *params)
            
            related_entries = []
            for row in results:
                related_entries.append({
                    'id': row['id'],
                    'title': row['title'],
                    'content_type': row['content_type'],
                    'word_count': row['word_count'],
                    'relevance_score': float(row['relevance_score']) if row['relevance_score'] else 0.0,
                    'key_topics': row['key_topics'] or [],
                    'project_id': row['project_id'],
                    'summary': row['summary'],
                    'preview': row['preview']
                })
            
            return related_entries
            
        except Exception as e:
            logger.error(f"Failed to get related entries: {e}")
            return []
    
    async def suggest_knowledge_for_context(self,
                                          conversation_context: List[Dict],
                                          personality_id: str = 'syntaxprime',
                                          limit: int = 3) -> List[Dict]:
        """
        Proactively suggest relevant knowledge based on conversation context
        This helps the AI provide context without being asked
        """
        if not conversation_context:
            return []
        
        # Extract themes from recent conversation
        context_keywords = self._extract_context_keywords(conversation_context)
        
        if not context_keywords:
            return []
        
        # Use top keywords as search query
        search_query = ' '.join(context_keywords[:3])
        
        # Search with lower threshold for proactive suggestions
        suggestions = await self.search_knowledge(
            query=search_query,
            conversation_context=conversation_context,
            personality_id=personality_id,
            limit=limit,
            min_relevance=0.05  # Lower threshold for suggestions
        )
        
        # Filter to only high-quality, relevant suggestions
        quality_suggestions = [
            suggestion for suggestion in suggestions
            if (suggestion['word_count'] or 0) > 100  # Substantial content
            and suggestion['final_score'] > 0.2  # Good relevance
        ]
        
        return quality_suggestions[:limit]
    
    def clear_cache(self):
        """Clear the knowledge query cache"""
        self.cache.clear()
        logger.info("Knowledge query cache cleared")
    
    def cleanup_cache(self) -> int:
        """Remove expired cache entries. Returns count of removed entries."""
        removed = self.cache.cleanup_expired()
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache entries")
        return removed
    
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return self.cache.stats()


# =============================================================================
# Global Instance and Factory
# =============================================================================

_knowledge_engine: Optional[KnowledgeQueryEngine] = None


def get_knowledge_engine() -> KnowledgeQueryEngine:
    """Get the global knowledge query engine"""
    global _knowledge_engine
    if _knowledge_engine is None:
        _knowledge_engine = KnowledgeQueryEngine()
    return _knowledge_engine


async def cleanup_knowledge_engine():
    """Cleanup the knowledge engine (call on app shutdown)"""
    global _knowledge_engine
    if _knowledge_engine is not None:
        _knowledge_engine.clear_cache()
        _knowledge_engine = None
        logger.info("Knowledge engine cleaned up")


# =============================================================================
# Test Script
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing Knowledge Query Engine...")
        
        engine = KnowledgeQueryEngine()
        
        # Test cache
        print("\n📦 Testing TTL Cache:")
        engine.cache.set("test_key", {"data": "test_value"})
        result = engine.cache.get("test_key")
        print(f"  Cache set/get: {'✅ PASS' if result else '❌ FAIL'}")
        print(f"  Cache stats: {engine.cache_stats()}")
        
        # Test search
        print("\n🔍 Testing Knowledge Search:")
        results = await engine.search_knowledge(
            query="AMCF email campaign",
            personality_id='syntaxprime',
            limit=5
        )
        
        print(f"Found {len(results)} knowledge entries:")
        for result in results:
            print(f"- {result['title']} (score: {result['final_score']:.3f})")
            print(f"  Project: {result['project_name']}, Type: {result['content_type']}")
            if result.get('snippet'):
                print(f"  Snippet: {result['snippet'][:100]}...")
            print()
        
        # Test related entries if we found any
        if results:
            print("\n🔗 Testing Related Entries:")
            related = await engine.get_related_entries(results[0]['id'])
            print(f"Found {len(related)} related entries to '{results[0]['title']}'")
        
        # Test cache cleanup
        print("\n🧹 Testing Cache Cleanup:")
        removed = engine.cleanup_cache()
        print(f"  Removed {removed} expired entries")
        print(f"  Final cache stats: {engine.cache_stats()}")
        
        print("\n✅ Knowledge Query Engine test completed!")
    
    asyncio.run(test())
