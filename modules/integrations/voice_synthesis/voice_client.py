"""
ElevenLabs Voice Client
Handles direct integration with ElevenLabs API for text-to-speech generation

Features:
- Text-to-speech synthesis with personality-optimized settings
- Voice model selection and fallback handling
- Audio quality optimization (MP3, smallest file size)
- Rate limiting and error handling
- Voice availability checking
- Audio generation timing and metrics

ElevenLabs API Documentation: https://docs.elevenlabs.io/
"""

import aiohttp
import asyncio
import os
import logging
import time
from typing import Dict, Any, Optional, List
import json

logger = logging.getLogger(__name__)

class ElevenLabsClient:
    """
    ElevenLabs API client for voice synthesis
    Optimized for Syntax Prime personality voices
    """
    
    def __init__(self):
        self.api_key = os.getenv('ELEVENLABS_API_KEY')
        self.base_url = "https://api.elevenlabs.io/v1"
        self.session = None
        
        # Voice optimization settings per personality
        self.voice_settings = {
            'syntaxprime': {
                'stability': 0.75,  # Professional but with edge
                'similarity_boost': 0.85,
                'style': 0.20,  # Slight style variation for sass
                'use_speaker_boost': True
            },
            'syntaxbot': {
                'stability': 0.80,  # Quick and consistent
                'similarity_boost': 0.90,
                'style': 0.10,  # Minimal style for efficiency
                'use_speaker_boost': True
            },
            'nil_exe': {
                'stability': 0.60,  # Chaotic but intelligible
                'similarity_boost': 0.70,
                'style': 0.40,  # High style for chaos
                'use_speaker_boost': False
            },
            'ggpt': {
                'stability': 0.85,  # Enthusiastic but clear
                'similarity_boost': 0.80,
                'style': 0.25,  # Gaming energy
                'use_speaker_boost': True
            }
        }
        
        # Audio quality settings (optimized for smallest file size)
        self.audio_settings = {
            'output_format': 'mp3_44100_128',  # 128kbps MP3, good quality/size balance
            'optimize_streaming_latency': 3,    # Optimize for file size over latency
            'normalize': True                   # Normalize audio levels
        }
        
        # Rate limiting (ElevenLabs has usage limits)
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'XI-API-KEY': self.api_key,
                    'Content-Type': 'application/json'
                }
            )
        return self.session
    
    async def _rate_limit(self):
        """Simple rate limiting to respect API limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def generate_speech(self, 
                            text: str, 
                            voice_id: str,
                            personality_id: str = 'syntaxprime') -> Dict[str, Any]:
        """
        Generate speech from text using specified voice
        
        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID (e.g., 'Adam', 'Josh')
            personality_id: Personality for voice settings optimization
            
        Returns:
            Dictionary with success status, audio data, and metadata
        """
        start_time = time.time()
        
        try:
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'ELEVENLABS_API_KEY not configured'
                }
            
            if not text.strip():
                return {
                    'success': False,
                    'error': 'Text cannot be empty'
                }
            
            # Apply rate limiting
            await self._rate_limit()
            
            # Get voice settings for personality
            voice_settings = self.voice_settings.get(
                personality_id, 
                self.voice_settings['syntaxprime']
            )
            
            # Prepare request payload
            payload = {
                'text': text.strip(),
                'model_id': 'eleven_monolingual_v1',  # Fast, high-quality model
                'voice_settings': voice_settings
            }
            
            # Add audio optimization settings
            payload.update(self.audio_settings)
            
            logger.info(f"🎤 Generating speech for voice {voice_id} (personality: {personality_id})")
            logger.debug(f"Text length: {len(text)} characters")
            
            # Make API request
            session = await self._get_session()
            url = f"{self.base_url}/text-to-speech/{voice_id}"
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    generation_time_ms = int((time.time() - start_time) * 1000)
                    
                    logger.info(f"✅ Speech generated successfully in {generation_time_ms}ms")
                    logger.debug(f"Audio size: {len(audio_data)} bytes")
                    
                    return {
                        'success': True,
                        'audio_data': audio_data,
                        'generation_time_ms': generation_time_ms,
                        'voice_id': voice_id,
                        'personality_id': personality_id,
                        'file_size': len(audio_data),
                        'text_length': len(text)
                    }
                
                elif response.status == 401:
                    return {
                        'success': False,
                        'error': 'Invalid ElevenLabs API key'
                    }
                
                elif response.status == 422:
                    error_data = await response.json()
                    return {
                        'success': False,
                        'error': f"Voice not found or invalid: {voice_id}",
                        'details': error_data
                    }
                
                elif response.status == 429:
                    return {
                        'success': False,
                        'error': 'ElevenLabs rate limit exceeded'
                    }
                
                else:
                    error_text = await response.text()
                    return {
                        'success': False,
                        'error': f"ElevenLabs API error {response.status}: {error_text}"
                    }
        
        except aiohttp.ClientError as e:
            logger.error(f"❌ Network error in speech generation: {e}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        
        except Exception as e:
            logger.error(f"❌ Unexpected error in speech generation: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    async def get_available_voices(self) -> Dict[str, Any]:
        """
        Get list of available voices from ElevenLabs
        Useful for voice validation and selection
        """
        try:
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'ELEVENLABS_API_KEY not configured'
                }
            
            await self._rate_limit()
            
            session = await self._get_session()
            url = f"{self.base_url}/voices"
            
            async with session.get(url) as response:
                if response.status == 200:
                    voices_data = await response.json()
                    
                    # Extract voice information
                    voices = []
                    for voice in voices_data.get('voices', []):
                        voices.append({
                            'voice_id': voice.get('voice_id'),
                            'name': voice.get('name'),
                            'category': voice.get('category'),
                            'description': voice.get('description'),
                            'preview_url': voice.get('preview_url')
                        })
                    
                    logger.info(f"📋 Retrieved {len(voices)} available voices")
                    
                    return {
                        'success': True,
                        'voices': voices,
                        'total_voices': len(voices)
                    }
                
                else:
                    error_text = await response.text()
                    return {
                        'success': False,
                        'error': f"Failed to get voices: {response.status} {error_text}"
                    }
        
        except Exception as e:
            logger.error(f"❌ Error getting available voices: {e}")
            return {
                'success': False,
                'error': f"Error getting voices: {str(e)}"
            }
    
    async def validate_voice(self, voice_id: str) -> bool:
        """
        Validate that a voice ID exists and is available
        """
        try:
            voices_result = await self.get_available_voices()
            
            if not voices_result.get('success'):
                return False
            
            voice_names = [v.get('name', '').lower() for v in voices_result.get('voices', [])]
            voice_ids = [v.get('voice_id', '') for v in voices_result.get('voices', [])]
            
            # Check by name or ID
            return (
                voice_id.lower() in voice_names or 
                voice_id in voice_ids
            )
        
        except Exception as e:
            logger.error(f"❌ Error validating voice {voice_id}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check ElevenLabs API connectivity and account status
        """
        try:
            if not self.api_key:
                return {
                    'connected': False,
                    'error': 'API key not configured'
                }
            
            await self._rate_limit()
            
            # Test with a simple voices request
            session = await self._get_session()
            url = f"{self.base_url}/voices"
            
            async with session.get(url) as response:
                if response.status == 200:
                    # Get user account info if available
                    user_url = f"{self.base_url}/user"
                    async with session.get(user_url) as user_response:
                        user_data = {}
                        if user_response.status == 200:
                            user_data = await user_response.json()
                    
                    return {
                        'connected': True,
                        'api_status': 'healthy',
                        'subscription': user_data.get('subscription', {}),
                        'character_count': user_data.get('character_count', 0),
                        'character_limit': user_data.get('character_limit', 0)
                    }
                
                elif response.status == 401:
                    return {
                        'connected': False,
                        'error': 'Invalid API key'
                    }
                
                else:
                    return {
                        'connected': False,
                        'error': f"API error: {response.status}"
                    }
        
        except Exception as e:
            logger.error(f"❌ ElevenLabs health check failed: {e}")
            return {
                'connected': False,
                'error': f"Health check failed: {str(e)}"
            }
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

# Utility functions for voice management
async def test_voice_generation():
    """Test function for voice generation"""
    client = ElevenLabsClient()
    
    try:
        # Test with SyntaxPrime's voice
        result = await client.generate_speech(
            text="Hello! This is a test of the voice synthesis system.",
            voice_id="Adam",
            personality_id="syntaxprime"
        )
        
        if result.get('success'):
            print(f"✅ Voice generation test successful!")
            print(f"   Generation time: {result.get('generation_time_ms')}ms")
            print(f"   Audio size: {result.get('file_size')} bytes")
        else:
            print(f"❌ Voice generation test failed: {result.get('error')}")
        
        return result
    
    finally:
        await client.close()

if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_voice_generation())