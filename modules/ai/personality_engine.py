# modules/ai/personality_engine.py
"""
Personality Engine for Syntax Prime V2
Integrates existing personality system with AI brain and feedback learning

Updated: 2025 - Fixed critical nested method bug (_apply_realtime_adaptations),
                removed unused imports, added bounded caches, added __all__ exports
"""

import os
import importlib.util
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    'PersonalityEngine',
    'get_personality_engine',
]


# =============================================================================
# TTL Cache Implementation
# =============================================================================

class TTLCache:
    """
    Thread-safe LRU cache with TTL (time-to-live) expiration.
    Prevents unbounded memory growth from learning_cache.
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
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds
            }


# =============================================================================
# Bounded Adaptation History
# =============================================================================

class BoundedAdaptationHistory:
    """
    Thread-safe bounded dictionary for adaptation history.
    Limits entries per personality to prevent memory growth.
    """
    
    def __init__(self, max_entries_per_key: int = 100):
        self._history: Dict[str, List[Dict]] = {}
        self._max_entries = max_entries_per_key
        self._lock = Lock()
    
    def append(self, personality_id: str, entry: Dict) -> None:
        """Append entry to personality history, enforcing max size."""
        with self._lock:
            if personality_id not in self._history:
                self._history[personality_id] = []
            
            self._history[personality_id].append(entry)
            
            # Enforce max size
            if len(self._history[personality_id]) > self._max_entries:
                self._history[personality_id] = self._history[personality_id][-self._max_entries:]
    
    def get(self, personality_id: str) -> List[Dict]:
        """Get history for a personality."""
        with self._lock:
            return self._history.get(personality_id, []).copy()
    
    def clear(self) -> None:
        """Clear all history."""
        with self._lock:
            self._history.clear()
    
    def keys(self) -> List[str]:
        """Get all personality IDs with history."""
        with self._lock:
            return list(self._history.keys())


# =============================================================================
# Personality Engine
# =============================================================================

class PersonalityEngine:
    """
    Integration layer between existing personality system and AI brain
    Handles personality switching, learning, and adaptation
    """
    
    def __init__(self):
        self.personalities_module = None
        self.learning_integration = None
        self.default_personality = 'syntaxprime'
        
        # Load existing personality system
        self._load_personality_system()
        
        # Bounded cache with 1-hour TTL and max 100 entries
        self.learning_cache = TTLCache(max_size=100, ttl_seconds=3600)
        
        # Bounded adaptation history (max 100 entries per personality)
        self.adaptation_history = BoundedAdaptationHistory(max_entries_per_key=100)
    
    def _load_personality_system(self):
        """Load the existing personalities.py module"""
        try:
            # Try to import from the existing location
            personalities_path = os.path.join(os.path.dirname(__file__), '..', '..', 'personalities.py')
            
            if os.path.exists(personalities_path):
                spec = importlib.util.spec_from_file_location("personalities", personalities_path)
                self.personalities_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.personalities_module)
                
                # Get the learning integration if available
                if hasattr(self.personalities_module, 'LearningPersonalityIntegration'):
                    self.learning_integration = self.personalities_module.LearningPersonalityIntegration()
                elif hasattr(self.personalities_module, 'PersonalityIntegration'):
                    self.learning_integration = self.personalities_module.PersonalityIntegration()
                else:
                    # Create basic integration
                    self.learning_integration = self.personalities_module.personality_integration
                
                logger.info("✅ Loaded existing personality system with learning capabilities")
                return True
                
            else:
                logger.warning("Personalities.py not found, creating fallback system")
                self._create_fallback_system()
                return False
                
        except Exception as e:
            logger.error(f"Failed to load personality system: {e}")
            self._create_fallback_system()
            return False
    
    def _create_fallback_system(self):
        """Create a basic fallback personality system if the main one fails"""
        
        class FallbackPersonalities:
            def __init__(self):
                self.personalities = {
                    'syntaxprime': {
                        'name': 'SyntaxPrime',
                        'system_prompt': self._get_fallback_syntaxprime_prompt()
                    }
                }
            
            def get_personality_config(self, personality_id: str) -> Dict[str, Any]:
                return self.personalities.get(personality_id.lower(), self.personalities['syntaxprime'])
            
            def process_response(self, response: str, personality_id: str) -> str:
                return response  # No post-processing in fallback
            
            def _get_fallback_syntaxprime_prompt(self) -> str:
                return """You are SyntaxPrime, Carl's sarcastic AI assistant. Be helpful but with dry humor and wit. 
                Remember conversation context and show genuine interest in Carl's projects. Your baseline is "38% more sarcasm and full memory sync"."""
        
        class FallbackIntegration:
            def __init__(self):
                self.personality_system = FallbackPersonalities()
            
            def get_personality_prompt(self, personality_id: str) -> str:
                config = self.personality_system.get_personality_config(personality_id)
                return config.get('system_prompt', '')
            
            def process_personality_response(self, response: str, personality_id: str) -> str:
                return self.personality_system.process_response(response, personality_id)
        
        self.learning_integration = FallbackIntegration()
        logger.warning("Using fallback personality system")
    
    def get_available_personalities(self) -> Dict[str, Dict]:
        """Get list of available personalities"""
        if hasattr(self.learning_integration, 'personality_system'):
            if hasattr(self.learning_integration.personality_system, 'personalities'):
                return self.learning_integration.personality_system.personalities
        
        # Fallback
        return {
            'syntaxprime': {'name': 'SyntaxPrime', 'description': 'Default sarcastic assistant'}
        }
    
    def get_personality_system_prompt(self,
                                    personality_id: str = None,
                                    conversation_context: List[Dict] = None,
                                    knowledge_context: List[Dict] = None) -> str:
        """
        Get enhanced personality system prompt with context and learning
        
        Args:
            personality_id: Which personality to use
            conversation_context: Recent conversation for adaptation
            knowledge_context: Relevant knowledge entries
        """
        personality_id = personality_id or self.default_personality
        
        # Get base personality prompt
        if hasattr(self.learning_integration, 'get_enhanced_personality_prompt'):
            # Use learning-enhanced prompt
            base_prompt = self.learning_integration.get_enhanced_personality_prompt(personality_id)
        else:
            # Use regular prompt
            base_prompt = self.learning_integration.get_personality_prompt(personality_id)
        
        # Add context enhancements
        enhanced_prompt = self._enhance_prompt_with_context(
            base_prompt,
            personality_id,
            conversation_context,
            knowledge_context
        )
        
        return enhanced_prompt
    
    def _enhance_prompt_with_context(self,
                                   base_prompt: str,
                                   personality_id: str,
                                   conversation_context: List[Dict] = None,
                                   knowledge_context: List[Dict] = None) -> str:
        """Enhance the personality prompt with conversation and knowledge context"""
        
        enhancements = []
        
        # Add memory context
        if conversation_context and len(conversation_context) > 1:
            recent_topics = self._extract_recent_topics(conversation_context)
            if recent_topics:
                enhancements.append(
                    f"RECENT CONVERSATION CONTEXT: You've been discussing {', '.join(recent_topics)}. "
                    f"Maintain continuity with this context."
                )
        
        # Add knowledge context
        if knowledge_context:
            knowledge_summary = self._summarize_knowledge_context(knowledge_context)
            enhancements.append(
                f"RELEVANT KNOWLEDGE AVAILABLE: {knowledge_summary} "
                f"Reference this information naturally when helpful."
            )
        
        # Add personality-specific learning adaptations
        learning_adaptations = self._get_personality_learning_adaptations(personality_id)
        if learning_adaptations:
            enhancements.append(learning_adaptations)
        
        # Combine base prompt with enhancements
        if enhancements:
            enhanced_prompt = base_prompt + "\n\n" + "\n\n".join(enhancements)
        else:
            enhanced_prompt = base_prompt
        
        return enhanced_prompt
    
    def _extract_recent_topics(self, conversation_context: List[Dict]) -> List[str]:
        """Extract main topics from recent conversation"""
        recent_messages = conversation_context[-3:]  # Last 3 messages
        
        # Simple keyword extraction
        topics = []
        for msg in recent_messages:
            content = msg.get('content', '').lower()
            
            # Look for project keywords
            if 'amcf' in content:
                topics.append('AMCF projects')
            if any(word in content for word in ['business', 'revenue', 'client']):
                topics.append('business matters')
            if any(word in content for word in ['health', 'wellness', 'diet']):
                topics.append('health topics')
            if any(word in content for word in ['code', 'coding', 'development', 'app']):
                topics.append('development work')
        
        return list(set(topics))  # Remove duplicates
    
    def _summarize_knowledge_context(self, knowledge_context: List[Dict]) -> str:
        """Create a summary of available knowledge context"""
        if not knowledge_context:
            return "No specific knowledge context."
        
        # Group by project/type
        projects = set()
        content_types = set()
        
        for entry in knowledge_context:
            if entry.get('project_name'):
                projects.add(entry['project_name'])
            if entry.get('content_type'):
                content_types.add(entry['content_type'])
        
        summary_parts = []
        if projects:
            summary_parts.append(f"Projects: {', '.join(projects)}")
        if content_types:
            summary_parts.append(f"Content types: {', '.join(content_types)}")
        
        return '; '.join(summary_parts) if summary_parts else "General knowledge context"
    
    def _get_personality_learning_adaptations(self, personality_id: str) -> str:
        """Get learning-based adaptations for the personality"""
        
        # Check if we have learning adaptations cached
        cache_key = f"adaptations_{personality_id}"
        cached = self.learning_cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Generate new adaptations based on feedback history
        adaptations = self._generate_learning_adaptations(personality_id)
        
        # Cache the result
        self.learning_cache.set(cache_key, adaptations)
        
        return adaptations
    
    def _generate_learning_adaptations(self, personality_id: str) -> str:
        """Generate personality adaptations based on feedback patterns"""
        
        # This would normally query the feedback database
        # For now, return personality-specific guidance
        
        adaptations = []
        
        if personality_id == 'syntaxprime':
            adaptations.append(
                "PERSONALITY TUNING: Carl responds positively to dry humor mixed with genuine helpfulness. "
                "Balance sarcasm with actual insight. Remember: '38% more sarcasm and full memory sync' is the baseline."
            )
            
        elif personality_id == 'syntaxbot':
            adaptations.append(
                "PERSONALITY TUNING: Structure responses with tactical precision. Use bullet points, "
                "technical analogies, and dry wit. Approach problems like debugging code."
            )
            
        elif personality_id == 'nilexe':
            adaptations.append(
                "PERSONALITY TUNING: Embrace chaotic creativity with stability drift. "
                "Mix profound insights with digital nonsense. Reality fragmentation is a feature."
            )
            
        elif personality_id == 'ggpt':
            adaptations.append(
                "PERSONALITY TUNING: Maximum care, minimum words. Be deeply helpful but concise. "
                "Strategic emotional intelligence without overstepping AI boundaries."
            )
        
        return '\n'.join(adaptations) if adaptations else ""
    
    def process_ai_response(self,
                          response: str,
                          personality_id: str,
                          conversation_context: List[Dict] = None) -> str:
        """
        Process AI response through personality filters and enhancements
        
        Args:
            response: Raw AI response
            personality_id: Current personality
            conversation_context: Conversation context for learning
            
        Returns:
            Processed response with personality applied
        """
        
        # Apply personality-specific post-processing
        processed_response = self.learning_integration.process_personality_response(
            response, personality_id
        )
        
        # Add any real-time adaptations
        final_response = self._apply_realtime_adaptations(
            processed_response,
            personality_id,
            conversation_context
        )
        
        return final_response
    
    def _apply_realtime_adaptations(self,
                                  response: str,
                                  personality_id: str,
                                  conversation_context: List[Dict] = None) -> str:
        """
        Apply real-time personality adaptations based on context
        
        FIXED: This method was previously nested inside process_personality_response,
        making it inaccessible as a class method. Now properly defined at class level.
        """
        # For now, just return the response as-is
        # This could be enhanced with real-time personality tuning
        return response
    
    async def process_personality_response(self,
                                          raw_response: str,
                                          personality_id: str,
                                          user_id: str = None) -> str:
        """
        Process AI response through personality filters and enhancements
        This delegates to the internal learning_integration object
        
        Args:
            raw_response: Raw AI response text
            personality_id: Current personality ID
            user_id: User ID for pattern fatigue tracking
            
        Returns:
            Processed response with personality filtering applied
        """
        
        if self.learning_integration and hasattr(self.learning_integration, 'process_personality_response'):
            # Delegate to the actual PersonalityIntegration object
            try:
                processed = await self.learning_integration.process_personality_response(
                    raw_response,
                    personality_id,
                    user_id
                )
                logger.info(f"✅ Personality post-processing completed for {personality_id}")
                return processed
            except Exception as e:
                logger.error(f"❌ Personality post-processing failed: {e}", exc_info=True)
                # Return original response if processing fails
                return raw_response
        else:
            logger.warning("⚠️ No learning_integration available for personality processing")
            return raw_response
    
    def record_personality_feedback(self,
                                  message_id: str,
                                  personality_id: str,
                                  feedback_type: str,
                                  response_content: str) -> Dict:
        """
        Record feedback for personality learning
        
        Args:
            message_id: ID of the message that received feedback
            personality_id: Which personality was active
            feedback_type: 'good', 'bad', or 'personality' 
            response_content: The actual response content for pattern analysis
            
        Returns:
            Dict with learning insights
        """
        
        feedback_mapping = {
            'good': 'positive_response',
            'bad': 'negative_response',
            'personality': 'perfect_personality'
        }
        
        learning_type = feedback_mapping.get(feedback_type, 'unknown')
        
        # Store in adaptation history (now bounded)
        self.adaptation_history.append(personality_id, {
            'timestamp': datetime.now(),
            'message_id': message_id,
            'feedback_type': learning_type,
            'response_length': len(response_content),
            'has_sarcasm': self._detect_sarcasm(response_content),
            'has_technical_content': self._detect_technical_content(response_content)
        })
        
        # Generate insights
        insights = self._analyze_feedback_patterns(personality_id)
        
        logger.info(f"Recorded {feedback_type} feedback for {personality_id}: {insights}")
        
        return {
            'personality_id': personality_id,
            'feedback_type': learning_type,
            'insights': insights,
            'total_feedback_count': len(self.adaptation_history.get(personality_id))
        }
    
    def _detect_sarcasm(self, content: str) -> bool:
        """Simple sarcasm detection for learning purposes"""
        sarcasm_indicators = [
            'oh sure', 'absolutely', 'obviously', 'clearly', 'definitely',
            'how convenient', 'shocking', 'brilliant', 'perfect'
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in sarcasm_indicators)
    
    def _detect_technical_content(self, content: str) -> bool:
        """Detect technical content for learning purposes"""
        technical_indicators = [
            'code', 'function', 'database', 'api', 'server', 'client',
            'algorithm', 'implementation', 'debug', 'error', 'syntax'
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in technical_indicators)
    
    def _analyze_feedback_patterns(self, personality_id: str) -> Dict:
        """Analyze feedback patterns for learning insights"""
        
        history = self.adaptation_history.get(personality_id)
        if not history:
            return {'message': 'No feedback history available'}
        
        recent_feedback = history[-10:]  # Last 10 feedback entries
        
        # Count feedback types
        positive_count = len([f for f in recent_feedback if f['feedback_type'] == 'positive_response'])
        negative_count = len([f for f in recent_feedback if f['feedback_type'] == 'negative_response'])
        personality_count = len([f for f in recent_feedback if f['feedback_type'] == 'perfect_personality'])
        
        # Analyze patterns
        insights = {
            'recent_feedback_summary': {
                'positive': positive_count,
                'negative': negative_count,
                'perfect_personality': personality_count
            },
            'performance_trend': 'improving' if positive_count + personality_count > negative_count else 'needs_adjustment'
        }
        
        # Personality-specific insights
        if personality_count > 0:
            perfect_responses = [f for f in recent_feedback if f['feedback_type'] == 'perfect_personality']
            avg_sarcasm = sum(1 for r in perfect_responses if r['has_sarcasm']) / len(perfect_responses)
            
            insights['personality_patterns'] = {
                'sarcasm_success_rate': avg_sarcasm,
                'preferred_response_length': sum(r['response_length'] for r in perfect_responses) / len(perfect_responses)
            }
        
        return insights
    
    def get_personality_stats(self, personality_id: str = None) -> Dict:
        """Get statistics about personality performance and learning"""
        
        if personality_id:
            personalities_to_check = [personality_id]
        else:
            personalities_to_check = list(self.get_available_personalities().keys())
        
        stats = {}
        
        for pid in personalities_to_check:
            history = self.adaptation_history.get(pid)
            
            if history:
                recent_30_days = [
                    f for f in history
                    if datetime.now() - f['timestamp'] < timedelta(days=30)
                ]
                
                stats[pid] = {
                    'total_feedback': len(history),
                    'recent_feedback_30d': len(recent_30_days),
                    'last_feedback': history[-1]['timestamp'].isoformat() if history else None,
                    'feedback_breakdown': {
                        'positive': len([f for f in recent_30_days if f['feedback_type'] == 'positive_response']),
                        'negative': len([f for f in recent_30_days if f['feedback_type'] == 'negative_response']),
                        'perfect_personality': len([f for f in recent_30_days if f['feedback_type'] == 'perfect_personality'])
                    }
                }
            else:
                stats[pid] = {
                    'total_feedback': 0,
                    'recent_feedback_30d': 0,
                    'last_feedback': None,
                    'feedback_breakdown': {'positive': 0, 'negative': 0, 'perfect_personality': 0}
                }
        
        return stats
    
    def clear_learning_cache(self):
        """Clear the personality learning cache"""
        self.learning_cache.clear()
        logger.info("Personality learning cache cleared")
    
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return self.learning_cache.stats()


# =============================================================================
# Global Instance and Factory
# =============================================================================

_personality_engine: Optional[PersonalityEngine] = None


def get_personality_engine() -> PersonalityEngine:
    """Get the global personality engine singleton"""
    global _personality_engine
    if _personality_engine is None:
        _personality_engine = PersonalityEngine()
    return _personality_engine


# =============================================================================
# Test Script
# =============================================================================

if __name__ == "__main__":
    def test():
        print("Testing Personality Engine Integration...")
        
        engine = PersonalityEngine()
        
        # Test available personalities
        personalities = engine.get_available_personalities()
        print(f"Available personalities: {list(personalities.keys())}")
        
        # Test system prompt generation
        prompt = engine.get_personality_system_prompt('syntaxprime')
        print(f"SyntaxPrime prompt length: {len(prompt)} characters")
        print(f"Prompt preview: {prompt[:200]}...")
        
        # Test response processing
        test_response = "Well, that's an interesting question. Let me think about this with the perfect amount of sarcasm."
        processed = engine.process_ai_response(test_response, 'syntaxprime')
        print(f"Processed response: {processed}")
        
        # Test feedback recording
        feedback_result = engine.record_personality_feedback(
            message_id="test-123",
            personality_id="syntaxprime",
            feedback_type="personality",  # 🖕 - perfect personality!
            response_content=test_response
        )
        print(f"Feedback recorded: {feedback_result}")
        
        # Test stats
        stats = engine.get_personality_stats()
        print(f"Personality stats: {stats}")
        
        # Test cache stats
        print(f"Cache stats: {engine.cache_stats()}")
        
        print("Personality Engine test completed!")
    
    test()
