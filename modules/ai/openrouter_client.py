# modules/ai/openrouter_client.py
"""
OpenRouter AI Client for Syntax Prime V2
Excludes ChatGPT models and provides intelligent model selection
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OpenRouterClient:
    """
    OpenRouter API client with ChatGPT model exclusion and smart fallbacks
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self.app_name = "SyntaxPrime-V2"
        self.site_url = os.getenv("SITE_URL", "https://damnitcarl.dev")
        
        # BLOCKED: All ChatGPT models - Carl doesn't want this crap
        self.blocked_models = [
            "openai/gpt-5o",           # Block GPT-5o variants if/when they exist
            "openai/gpt-5o-mini",
            "openai/gpt-5-turbo",
        ]
        
        # Preferred models in order of preference
        self.preferred_models = [
            "anthropic/claude-sonnet-4.5",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "anthropic/claude-3-haiku",
            "meta-llama/llama-3.1-70b-instruct",
            "mistralai/mixtral-8x7b-instruct",
            "google/gemini-pro-1.5"
        ]
        
        # Session for reuse
        self.session = None
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
    
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
                    
                    logger.info(f"Found {len(available_models)} available models (blocked {len(self.blocked_models)} ChatGPT models)")
                    return available_models
                else:
                    logger.error(f"Failed to get models: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []
    
    def select_best_model(self, available_models: List[Dict] = None, requirements: Dict = None) -> str:
        """
        Select the best available model based on requirements and preferences
        
        Args:
            available_models: List of available models from API
            requirements: Dict with 'context_length', 'speed_priority', etc.
        """
        requirements = requirements or {}
        
        # If we have available models, use them to validate
        available_ids = []
        if available_models:
            available_ids = [model.get("id") for model in available_models]
        
        # Check preferred models in order
        for model_id in self.preferred_models:
            if not available_ids or model_id in available_ids:
                # Check if model meets requirements
                if self._model_meets_requirements(model_id, requirements):
                    logger.info(f"Selected model: {model_id}")
                    return model_id
        
        # Fallback to first preferred model
        fallback = self.preferred_models[0]
        logger.warning(f"Using fallback model: {fallback}")
        return fallback
    
    def _model_meets_requirements(self, model_id: str, requirements: Dict) -> bool:
        """Check if a model meets the given requirements"""
        # Context length requirements
        min_context = requirements.get('context_length', 100000)  # Default 100K for our use case
        
        # Model context length mapping (approximate)
        model_contexts = {
            "anthropic/claude-3.5-sonnet": 200000,
            "anthropic/claude-3-haiku": 200000,
            "meta-llama/llama-3.1-70b-instruct": 131072,
            "mistralai/mixtral-8x7b-instruct": 32768,
            "google/gemini-pro-1.5": 1000000
        }
        
        model_context = model_contexts.get(model_id, 100000)
        return model_context >= min_context
    
    async def chat_completion(self,
                            messages: List[Dict],
                            model: str = None,
                            max_tokens: int = 4000,
                            temperature: float = 0.7,
                            stream: bool = False,
                            **kwargs) -> Dict:
        """
        Create a chat completion
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Specific model to use (if None, auto-select)
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            stream: Whether to stream the response
            **kwargs: Additional parameters
        """
        
        # Auto-select model if not specified
        if not model:
            available_models = await self.get_available_models()
            model = self.select_best_model(available_models, kwargs.get('requirements', {}))
        
        # Validate model is not blocked
        if model in self.blocked_models:
            raise ValueError(f"Model {model} is blocked. Only GPT-5o variants are blocked - the other ChatGPT models are lovely!")
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # Remove our custom requirements key if it exists
        payload.pop('requirements', None)
        
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
            
            # Test with a simple message
            test_messages = [{
                'role': 'user',
                'content': 'Respond with exactly: "OpenRouter connection successful"'
            }]
            
            model = self.select_best_model(available_models)
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
                'blocked_models_count': len(self.blocked_models)
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e),
                'api_key_set': bool(self.api_key)
            }

# Global client instance
_client = None

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

# Convenience functions
async def chat_with_openrouter(messages: List[Dict],
                             personality_id: str = 'syntaxprime',
                             **kwargs) -> Dict:
    """
    Convenience function for chat completions
    This will be enhanced with personality integration later
    """
    client = await get_openrouter_client()
    return await client.chat_completion(messages, **kwargs)

async def test_openrouter_connection() -> Dict:
    """Test OpenRouter connection"""
    client = await get_openrouter_client()
    return await client.test_connection()

if __name__ == "__main__":
    # Test script
    async def test():
        print("Testing OpenRouter client...")
        
        # Test connection
        result = await test_openrouter_connection()
        print(f"Connection test: {result}")
        
        if result['status'] == 'success':
            # Test chat
            messages = [{
                'role': 'user',
                'content': 'Say hello in the style of a sarcastic AI assistant.'
            }]
            
            client = await get_openrouter_client()
            response = await client.chat_completion(messages)
            
            print("Chat test response:")
            print(response.get('choices', [{}])[0].get('message', {}).get('content'))
        
        await cleanup_openrouter_client()
    
    asyncio.run(test())
