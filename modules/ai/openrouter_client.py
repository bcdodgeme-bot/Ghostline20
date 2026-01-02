# modules/ai/openrouter_client.py
"""
OpenRouter AI Client for Syntax Prime V2
Tiered Model Routing: Mercury for quick tasks, Claude for heavy lifting

Updated: 2026-01-02 - Added task-type-based model selection
- Mercury (inception/mercury) for: Bluesky drafts, simple lookups, conversational
- Claude (anthropic/claude-*) for: Board reports, complex analysis, long-form, vision
- OpenAI models BLOCKED due to math hallucination issues
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    'OpenRouterClient',
    'get_openrouter_client',
    'cleanup_openrouter_client',
    'chat_with_openrouter',
    'test_openrouter_connection',
    'TASK_TYPE_QUICK',
    'TASK_TYPE_HEAVY',
]


# =============================================================================
# Task Type Constants
# =============================================================================

TASK_TYPE_QUICK = "quick"    # Fast responses: Bluesky drafts, simple lookups, conversational
TASK_TYPE_HEAVY = "heavy"    # Quality responses: Board reports, analysis, long-form, vision


# =============================================================================
# OpenRouter Client
# =============================================================================

class OpenRouterClient:
    """
    OpenRouter API client with tiered model routing.
    
    Task Types:
    - "quick": Uses Mercury for fast, cost-effective responses
    - "heavy": Uses Claude for quality, complex reasoning
    - None/default: Uses Claude (safety default)
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self.app_name = "SyntaxPrime-V2"
        self.site_url = os.getenv("SITE_URL", "https://damnitcarl.dev")
        
        # =================================================================
        # BLOCKED MODELS - Updated 2026-01-02
        # OpenAI models blocked due to math hallucination issues
        # =================================================================
        self.blocked_models = [
            # GPT-5 variants (block when they exist)
            "openai/gpt-5o",
            "openai/gpt-5o-mini",
            "openai/gpt-5-turbo",
            # GPT-4 variants - BLOCKED: bad at math, hallucination issues
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4-turbo",
            "openai/gpt-4",
        ]
        
        # =================================================================
        # CLAUDE MODELS - For heavy lifting (quality, reasoning, analysis)
        # =================================================================
        self.claude_models = [
            "anthropic/claude-sonnet-4",      # Claude 4 Sonnet (latest, best)
            "anthropic/claude-3.5-sonnet",    # Claude 3.5 Sonnet (proven reliable)
            "anthropic/claude-3-haiku",       # Claude 3 Haiku (fast Claude option)
        ]
        
        # =================================================================
        # MERCURY MODELS - For quick tasks (fast, cost-effective)
        # =================================================================
        self.mercury_models = [
            "inception/mercury",              # Mercury - fast diffusion LLM
        ]
        
        # Legacy preferred_models list (for backwards compatibility)
        # Now defaults to Claude - Mercury accessed via task_type="quick"
        self.preferred_models = self.claude_models.copy()
        
        # Model context length mapping
        self.model_contexts = {
            # Claude models
            "anthropic/claude-sonnet-4": 200000,
            "anthropic/claude-3.5-sonnet": 200000,
            "anthropic/claude-3-opus": 200000,
            "anthropic/claude-3-haiku": 200000,
            # Mercury
            "inception/mercury": 128000,
            # Others (kept for reference, but blocked/unused)
            "openai/gpt-4o": 128000,
            "openai/gpt-4o-mini": 128000,
            "openai/gpt-4-turbo": 128000,
            "meta-llama/llama-3.1-70b-instruct": 131072,
            "meta-llama/llama-3.1-8b-instruct": 131072,
            "mistralai/mixtral-8x7b-instruct": 32768,
            "mistralai/mistral-large": 128000,
            "google/gemini-pro-1.5": 1000000,
            "google/gemini-flash-1.5": 1000000,
        }
        
        # Session for reuse
        self.session = None
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        
        logger.info("🤖 OpenRouter client initialized with tiered routing (Mercury quick / Claude heavy)")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": self.site_url,
                "X-Title": self.app_name,
                "Content-Type": "application/json"
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def close(self):
        """Close the client session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_available_models(self) -> List[Dict]:
        """Get list of available models, excluding blocked ones"""
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("data", [])
                    
                    # Filter out blocked models
                    available_models = [
                        model for model in models
                        if model.get("id") not in self.blocked_models
                    ]
                    
                    logger.info(f"Found {len(available_models)} available models (blocked {len(self.blocked_models)} models)")
                    return available_models
                else:
                    logger.error(f"Failed to get models: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []
    
    def select_best_model(
        self,
        available_models: List[Dict] = None,
        requirements: Dict = None,
        task_type: str = None
    ) -> str:
        """
        Select the best model based on task type and requirements.
        
        Args:
            available_models: List of available models from API (optional validation)
            requirements: Dict with 'context_length', 'speed_priority', etc.
            task_type: "quick" for Mercury, "heavy" or None for Claude
            
        Returns:
            Model ID string
        """
        requirements = requirements or {}
        
        # Determine model pool based on task type
        if task_type == TASK_TYPE_QUICK:
            # Quick tasks → Mercury first, then Claude Haiku as fallback
            model_pool = self.mercury_models + ["anthropic/claude-3-haiku"]
            logger.info(f"🚀 Task type 'quick' → using Mercury model pool")
        else:
            # Heavy tasks or default → Claude models only
            model_pool = self.claude_models
            if task_type == TASK_TYPE_HEAVY:
                logger.info(f"🧠 Task type 'heavy' → using Claude model pool")
            else:
                logger.info(f"🧠 Task type default → using Claude model pool")
        
        # If we have available models list, validate against it
        available_ids = []
        if available_models:
            available_ids = [model.get("id") for model in available_models]
        
        # Check models in order of preference
        for model_id in model_pool:
            if not available_ids or model_id in available_ids:
                if self._model_meets_requirements(model_id, requirements):
                    logger.info(f"✅ Selected model: {model_id}")
                    return model_id
        
        # Fallback to first Claude model (always safe)
        fallback = self.claude_models[0]
        logger.warning(f"⚠️ Using fallback model: {fallback}")
        return fallback
    
    def _model_meets_requirements(self, model_id: str, requirements: Dict) -> bool:
        """Check if a model meets the given requirements"""
        # Context length requirements
        min_context = requirements.get('context_length', 100000)  # Default 100K for our use case
        
        # Look up model context from our mapping
        model_context = self.model_contexts.get(model_id, 100000)  # Default 100K if unknown
        
        return model_context >= min_context
    
    async def chat_completion(self,
                            messages: List[Dict],
                            model: str = None,
                            max_tokens: int = 4000,
                            temperature: float = 0.7,
                            stream: bool = False,
                            task_type: str = None,
                            **kwargs) -> Dict:
        """
        Create a chat completion with tiered model routing.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Specific model to use (overrides task_type selection)
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            stream: Whether to stream the response
            task_type: "quick" for Mercury, "heavy" or None for Claude
            **kwargs: Additional parameters
        """
        
        # Auto-select model if not specified
        if not model:
            available_models = await self.get_available_models()
            model = self.select_best_model(
                available_models,
                kwargs.get('requirements', {}),
                task_type=task_type
            )
        
        # Validate model is not blocked
        if model in self.blocked_models:
            logger.warning(f"⛔ Blocked model requested: {model}, falling back to Claude")
            model = self.claude_models[0]
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Remove our custom keys that OpenRouter doesn't understand
        payload.pop('requirements', None)
        payload.pop('task_type', None)
        
        session = await self._get_session()
        
        try:
            async with session.post(f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status == 200:
                    if stream:
                        return self._handle_stream_response(response)
                    else:
                        result = await response.json()
                        # Add metadata
                        result['_metadata'] = {
                            'model_used': model,
                            'task_type': task_type or 'default',
                            'timestamp': datetime.utcnow().isoformat(),
                            'response_time_ms': None  # Could add timing if needed
                        }
                        return result
                else:
                    error_text = await response.text()
                    logger.error(f"OpenRouter API error {response.status}: {error_text}")
                    raise Exception(f"OpenRouter API error: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            raise
    
    async def _handle_stream_response(self, response) -> AsyncGenerator[Dict, None]:
        """Handle streaming response from OpenRouter"""
        async for line in response.content:
            line = line.decode('utf-8').strip()
            if line.startswith('data: '):
                data = line[6:]  # Remove 'data: ' prefix
                if data == '[DONE]':
                    break
                try:
                    chunk = json.loads(data)
                    yield chunk
                except json.JSONDecodeError:
                    continue
    
    async def test_connection(self) -> Dict:
        """Test the OpenRouter connection and return status"""
        try:
            available_models = await self.get_available_models()
            
            if not available_models:
                return {
                    'status': 'error',
                    'message': 'No models available',
                    'api_key_set': bool(self.api_key)
                }
            
            # Test with a simple message using Claude (heavy/default)
            test_messages = [{
                'role': 'user',
                'content': 'Respond with exactly: "OpenRouter connection successful"'
            }]
            
            model = self.select_best_model(available_models, task_type=TASK_TYPE_HEAVY)
            response = await self.chat_completion(
                messages=test_messages,
                model=model,
                max_tokens=50,
                temperature=0.1
            )
            
            return {
                'status': 'success',
                'message': 'OpenRouter connection successful',
                'model_used': response.get('_metadata', {}).get('model_used'),
                'available_models_count': len(available_models),
                'blocked_models_count': len(self.blocked_models),
                'routing': {
                    'quick_models': self.mercury_models,
                    'heavy_models': self.claude_models
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e),
                'api_key_set': bool(self.api_key)
            }
    
    def get_model_info(self, model_id: str = None) -> Dict[str, Any]:
        """Get information about a specific model or all configured models"""
        if model_id:
            return {
                'model_id': model_id,
                'context_length': self.model_contexts.get(model_id, 'unknown'),
                'is_blocked': model_id in self.blocked_models,
                'is_claude': model_id in self.claude_models,
                'is_mercury': model_id in self.mercury_models,
                'task_type': 'quick' if model_id in self.mercury_models else 'heavy'
            }
        
        # Return info about all configured models
        return {
            'claude_models': [
                {
                    'model_id': mid,
                    'context_length': self.model_contexts.get(mid, 'unknown'),
                    'task_type': 'heavy'
                }
                for mid in self.claude_models
            ],
            'mercury_models': [
                {
                    'model_id': mid,
                    'context_length': self.model_contexts.get(mid, 'unknown'),
                    'task_type': 'quick'
                }
                for mid in self.mercury_models
            ],
            'blocked_models': self.blocked_models,
            'routing_rules': {
                'quick': 'Mercury (inception/mercury) - Bluesky drafts, simple lookups, conversational',
                'heavy': 'Claude (anthropic/claude-*) - Board reports, analysis, long-form, vision',
                'default': 'Claude (safety default)'
            }
        }


# =============================================================================
# Global Instance and Factory
# =============================================================================

_client: Optional[OpenRouterClient] = None


async def get_openrouter_client() -> OpenRouterClient:
    """Get the global OpenRouter client instance"""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def cleanup_openrouter_client():
    """Cleanup the global client (call on app shutdown)"""
    global _client
    if _client:
        await _client.close()
        _client = None


# =============================================================================
# Convenience Functions
# =============================================================================

async def chat_with_openrouter(messages: List[Dict],
                             personality_id: str = 'syntaxprime',
                             task_type: str = None,
                             **kwargs) -> Dict:
    """
    Convenience function for chat completions
    
    Args:
        messages: List of message dicts
        personality_id: Personality for post-processing (future use)
        task_type: "quick" for Mercury, "heavy" or None for Claude
        **kwargs: Additional parameters
    """
    client = await get_openrouter_client()
    return await client.chat_completion(messages, task_type=task_type, **kwargs)


async def test_openrouter_connection() -> Dict:
    """Test OpenRouter connection"""
    client = await get_openrouter_client()
    return await client.test_connection()


# =============================================================================
# Test Script
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing OpenRouter client with tiered routing...")
        
        # Test connection
        result = await test_openrouter_connection()
        print(f"Connection test: {result}")
        
        if result['status'] == 'success':
            client = await get_openrouter_client()
            
            # Test heavy task (Claude)
            print("\n--- Testing HEAVY task (Claude) ---")
            messages = [{
                'role': 'user',
                'content': 'Calculate: 80 hours/month × 12 months × $40/hour. Show your work.'
            }]
            response = await client.chat_completion(messages, task_type=TASK_TYPE_HEAVY)
            print(f"Model used: {response.get('_metadata', {}).get('model_used')}")
            print(f"Response: {response.get('choices', [{}])[0].get('message', {}).get('content')[:200]}...")
            
            # Test quick task (Mercury)
            print("\n--- Testing QUICK task (Mercury) ---")
            messages = [{
                'role': 'user',
                'content': 'Write a short, witty Bluesky post about Monday mornings. Max 280 chars.'
            }]
            response = await client.chat_completion(messages, task_type=TASK_TYPE_QUICK)
            print(f"Model used: {response.get('_metadata', {}).get('model_used')}")
            print(f"Response: {response.get('choices', [{}])[0].get('message', {}).get('content')}")
            
            # Show model info
            print("\n--- Model Configuration ---")
            print(json.dumps(client.get_model_info(), indent=2))
        
        await cleanup_openrouter_client()
    
    asyncio.run(test())
