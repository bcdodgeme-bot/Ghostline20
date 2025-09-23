# modules/ai/inception_client.py
"""
Inception Labs AI Client for Syntax Prime V2
Fallback provider when OpenRouter fails - now with real API integration
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class InceptionLabsClient:
    """
    Inception Labs API client - fallback for OpenRouter
    Uses the Mercury model via their official API
    """
    
    def __init__(self):
        self.api_key = os.getenv("INCEPTION_LABS_API_KEY")
        self.base_url = "https://api.inceptionlabs.ai/v1"
        self.app_name = "SyntaxPrime-V2"
        
        # Available models
        self.available_models = ["mercury"]
        self.default_model = "mercury"
        
        # Session for reuse
        self.session = None
        
        if not self.api_key:
            logger.warning("INCEPTION_LABS_API_KEY not set - client will fail on actual requests")
        else:
            logger.info("Inception Labs client initialized with API key")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def close(self):
        """Close the client session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_available_models(self) -> List[Dict]:
        """Get list of available models"""
        # Return known models - Inception Labs primarily uses Mercury
        return [
            {
                "id": "mercury",
                "name": "Inception Mercury",
                "context_length": 100000,
                "description": "High-performance reasoning model"
            }
        ]
    
    def select_best_model(self, requirements: Dict = None) -> str:
        """Select the best available model for the task"""
        # Currently only Mercury is available
        return self.default_model
    
    async def chat_completion(self, 
                            messages: List[Dict], 
                            model: str = None,
                            max_tokens: int = 4000,
                            temperature: float = 0.7,
                            **kwargs) -> Dict:
        """
        Create a chat completion using Inception Labs API
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Specific model to use (defaults to mercury)
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters
        """
        
        if not self.api_key:
            raise Exception("INCEPTION_LABS_API_KEY not configured")
        
        # Auto-select model if not specified
        if not model:
            model = self.select_best_model(kwargs.get('requirements', {}))
        
        # Build payload according to Inception Labs API format
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        session = await self._get_session()
        
        try:
            async with session.post(f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    # Add metadata for tracking
                    result['_metadata'] = {
                        'model_used': model,
                        'timestamp': datetime.utcnow().isoformat(),
                        'is_fallback': True,
                        'provider': 'inception_labs',
                        'response_time_ms': None
                    }
                    
                    logger.info(f"Inception Labs completion successful: model={model}")
                    return result
                    
                else:
                    error_text = await response.text()
                    logger.error(f"Inception Labs API error {response.status}: {error_text}")
                    raise Exception(f"Inception Labs API error {response.status}: {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Inception Labs connection error: {e}")
            raise Exception(f"Inception Labs connection failed: {e}")
        except Exception as e:
            logger.error(f"Inception Labs unexpected error: {e}")
            raise
    
    async def test_connection(self) -> Dict:
        """Test the Inception Labs connection"""
        if not self.api_key:
            return {
                'status': 'error',
                'message': 'INCEPTION_LABS_API_KEY not configured',
                'api_key_set': False,
                'ready_for_production': False
            }
        
        try:
            # Test with a simple message
            test_messages = [{
                'role': 'user', 
                'content': 'Respond with exactly: "Inception Labs connection successful"'
            }]
            
            response = await self.chat_completion(
                messages=test_messages,
                max_tokens=50,
                temperature=0.1
            )
            
            # Check if we got a valid response
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0]['message']['content']
                
                return {
                    'status': 'success',
                    'message': 'Inception Labs connection successful',
                    'model_used': response.get('_metadata', {}).get('model_used', 'mercury'),
                    'api_key_set': True,
                    'test_response': content[:100]  # First 100 chars
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Invalid response format from Inception Labs',
                    'api_key_set': True
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Connection test failed: {str(e)}",
                'api_key_set': bool(self.api_key)
            }

# Global client instance
_inception_client = None

async def get_inception_client() -> InceptionLabsClient:
    """Get the global Inception Labs client instance"""
    global _inception_client
    if _inception_client is None:
        _inception_client = InceptionLabsClient()
    return _inception_client

async def cleanup_inception_client():
    """Cleanup the global client"""
    global _inception_client
    if _inception_client:
        await _inception_client.close()
        _inception_client = None

if __name__ == "__main__":
    # Test script
    async def test():
        print("Testing Inception Labs client...")
        
        client = await get_inception_client()
        result = await client.test_connection()
        
        print(f"Connection test: {result}")
        
        if result['status'] == 'success':
            # Test actual chat completion
            messages = [{
                'role': 'user',
                'content': 'Hello! Please respond with a brief, helpful message.'
            }]
            
            try:
                response = await client.chat_completion(messages)
                print("Chat test response:")
                print(response.get('choices', [{}])[0].get('message', {}).get('content'))
            except Exception as e:
                print(f"Chat test failed: {e}")
        
        await cleanup_inception_client()
    
    asyncio.run(test())