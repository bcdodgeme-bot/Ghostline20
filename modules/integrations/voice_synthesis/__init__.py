"""
Syntax Prime V2 - Voice Synthesis Integration Module
ElevenLabs voice synthesis with personality-driven voice selection

This module provides:
- ElevenLabs API integration for text-to-speech
- Personality-based voice selection (SyntaxPrime's choices)
- Audio file caching in database
- Speaker button integration for chat interface
- Optimized audio generation and retrieval

Voice Mappings (chosen by SyntaxPrime):
- SyntaxPrime: Adam (professional sass with edge)
- SyntaxBot: Josh/Adam (quick-response professionalism) 
- Nil.exe: Daniel/Antoni (chaotic intelligence)
- GGPT: Sam/Josh (enthusiastic gaming energy)

Author: SyntaxPrime & Claude
Version: 1.0.0
Date: September 2025
"""

from .voice_client import ElevenLabsClient
from .personality_voices import PersonalityVoiceManager
from .audio_manager import AudioCacheManager
from .router import router as voice_synthesis_router

# Module metadata
__version__ = "1.0.0"
__author__ = "SyntaxPrime & Claude"
__description__ = "ElevenLabs voice synthesis with personality-driven voice selection"

# Export main components
__all__ = [
    'ElevenLabsClient',
    'PersonalityVoiceManager', 
    'AudioCacheManager',
    'voice_synthesis_router',
    'get_voice_client',
    'get_personality_voice_manager',
    'get_audio_cache_manager'
]

# Global instances (lazy initialization)
_voice_client = None
_personality_manager = None
_audio_manager = None

def get_voice_client() -> ElevenLabsClient:
    """Get the global ElevenLabs client instance"""
    global _voice_client
    if _voice_client is None:
        _voice_client = ElevenLabsClient()
    return _voice_client

def get_personality_voice_manager() -> PersonalityVoiceManager:
    """Get the global personality voice manager instance"""
    global _personality_manager
    if _personality_manager is None:
        _personality_manager = PersonalityVoiceManager()
    return _personality_manager

def get_audio_cache_manager() -> AudioCacheManager:
    """Get the global audio cache manager instance"""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = AudioCacheManager()
    return _audio_manager

# Integration info for health checks and module discovery
def get_integration_info():
    """Get voice synthesis integration information"""
    return {
        'module_name': 'voice_synthesis',
        'version': __version__,
        'description': __description__,
        'features': [
            'ElevenLabs text-to-speech integration',
            'Personality-based voice selection',
            'Database audio caching',
            'Speaker button chat integration',
            'MP3 audio generation (smallest file size)',
            'Fallback voice system',
            'Audio cache statistics tracking'
        ],
        'personalities': {
            'syntaxprime': 'Adam (professional sass)',
            'syntaxbot': 'Josh/Adam (quick professional)',
            'nil_exe': 'Daniel/Antoni (chaotic intelligence)', 
            'ggpt': 'Sam/Josh (gaming energy)'
        },
        'endpoints': [
            '/api/voice/synthesize',
            '/api/voice/audio/{message_id}',
            '/api/voice/personalities',
            '/api/voice/health'
        ],
        'database_tables': [
            'conversation_messages (extended with audio columns)',
            'voice_personality_mappings',
            'audio_cache_stats'
        ]
    }

def check_module_health():
    """Basic health check for voice synthesis module"""
    try:
        # Check if required components can be imported
        from .voice_client import ElevenLabsClient
        from .personality_voices import PersonalityVoiceManager
        from .audio_manager import AudioCacheManager
        
        # Check environment variables
        import os
        api_key = os.getenv('ELEVENLABS_API_KEY')
        
        return {
            'healthy': True,
            'components_loaded': True,
            'api_key_configured': bool(api_key),
            'version': __version__
        }
        
    except ImportError as e:
        return {
            'healthy': False,
            'components_loaded': False,
            'error': f'Import error: {str(e)}',
            'version': __version__
        }
    except Exception as e:
        return {
            'healthy': False,
            'components_loaded': True,
            'error': f'Health check failed: {str(e)}',
            'version': __version__
        }
