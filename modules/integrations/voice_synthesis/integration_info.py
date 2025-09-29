"""
Voice Synthesis Integration Information
Provides module metadata, health checks, and system status for voice synthesis integration

This module serves as the central information hub for:
- Integration metadata and capabilities
- Health monitoring and diagnostics
- Performance metrics and statistics
- Configuration validation
- System requirements documentation

Used by the main application for module discovery and health monitoring.
"""

import asyncio
import os
import logging
from typing import Dict, Any, List
from datetime import datetime
import json

from .voice_client import ElevenLabsClient
from .personality_voices import PersonalityVoiceManager
from .audio_manager import AudioCacheManager

logger = logging.getLogger(__name__)

class VoiceSynthesisIntegration:
    """
    Voice Synthesis Integration information and health monitoring
    """
    
    def __init__(self):
        self.module_name = "voice_synthesis"
        self.version = "1.0.0"
        self.description = "ElevenLabs voice synthesis with personality-driven voice selection"
        
        # Component instances for health checks
        self._voice_client = None
        self._personality_manager = None
        self._audio_manager = None
    
    def get_voice_client(self) -> ElevenLabsClient:
        """Get voice client instance"""
        if self._voice_client is None:
            self._voice_client = ElevenLabsClient()
        return self._voice_client
    
    def get_personality_manager(self) -> PersonalityVoiceManager:
        """Get personality manager instance"""
        if self._personality_manager is None:
            self._personality_manager = PersonalityVoiceManager()
        return self._personality_manager
    
    def get_audio_manager(self) -> AudioCacheManager:
        """Get audio manager instance"""
        if self._audio_manager is None:
            self._audio_manager = AudioCacheManager()
        return self._audio_manager

async def get_integration_info() -> Dict[str, Any]:
    """
    Get comprehensive integration information for voice synthesis module
    """
    integration = VoiceSynthesisIntegration()
    
    return {
        'module_info': {
            'name': integration.module_name,
            'version': integration.version,
            'description': integration.description,
            'author': 'SyntaxPrime & Claude',
            'integration_date': '2025-09-28',
            'last_updated': datetime.now().isoformat()
        },
        
        'capabilities': {
            'text_to_speech': True,
            'personality_voices': True,
            'audio_caching': True,
            'multiple_voices': True,
            'voice_fallback': True,
            'compression': True,
            'statistics_tracking': True,
            'cleanup_automation': True
        },
        
        'personality_voices': {
            'syntaxprime': {
                'primary_voice': 'Adam',
                'style': 'professional sass with edge',
                'stability': 0.75,
                'description': 'Perfect blend of warmth and professionalism with sarcastic edge'
            },
            'syntaxbot': {
                'primary_voice': 'Josh',
                'secondary_voice': 'Adam',
                'style': 'quick professional',
                'stability': 0.80,
                'description': 'Quick response version with professional efficiency'
            },
            'nil_exe': {
                'primary_voice': 'Daniel',
                'secondary_voice': 'Antoni',
                'style': 'chaotic intelligence',
                'stability': 0.60,
                'description': 'Chaotic energy with underlying intelligence - perfect for chaos agent'
            },
            'ggpt': {
                'primary_voice': 'Sam',
                'secondary_voice': 'Josh',
                'style': 'gaming energy',
                'stability': 0.85,
                'description': 'Enthusiastic gaming streamer energy with expertise'
            }
        },
        
        'technical_specs': {
            'audio_format': 'MP3',
            'quality': '44.1kHz, 128kbps',
            'compression': 'GZIP + Base64',
            'storage': 'PostgreSQL Database',
            'max_file_size': '5MB',
            'cache_duration': '90 days',
            'api_provider': 'ElevenLabs',
            'model': 'eleven_monolingual_v1'
        },
        
        'api_endpoints': [
            {
                'method': 'POST',
                'path': '/api/voice/synthesize',
                'description': 'Generate speech from text with personality voice',
                'parameters': ['text', 'message_id', 'personality_id', 'voice_override']
            },
            {
                'method': 'GET',
                'path': '/api/voice/audio/{message_id}',
                'description': 'Retrieve cached audio file',
                'returns': 'MP3 audio stream'
            },
            {
                'method': 'GET',
                'path': '/api/voice/personalities',
                'description': 'Get all personality voice mappings',
                'returns': 'Voice configuration for all personalities'
            },
            {
                'method': 'GET',
                'path': '/api/voice/health',
                'description': 'Comprehensive health check',
                'returns': 'System health status and statistics'
            },
            {
                'method': 'GET',
                'path': '/api/voice/stats',
                'description': 'Detailed usage statistics',
                'returns': 'Cache statistics and analytics'
            },
            {
                'method': 'DELETE',
                'path': '/api/voice/cache/{message_id}',
                'description': 'Delete cached audio',
                'returns': 'Deletion confirmation'
            },
            {
                'method': 'POST',
                'path': '/api/voice/cache/cleanup',
                'description': 'Clean up old audio files',
                'returns': 'Cleanup statistics'
            }
        ],
        
        'database_schema': {
            'tables_modified': [
                {
                    'name': 'conversation_messages',
                    'columns_added': [
                        'audio_file_path (VARCHAR(500))',
                        'audio_file_size (INTEGER)',
                        'voice_synthesis_metadata (JSONB)',
                        'audio_generated_at (TIMESTAMP WITH TIME ZONE)'
                    ]
                }
            ],
            'tables_created': [
                {
                    'name': 'voice_personality_mappings',
                    'purpose': 'Store personality voice configurations',
                    'key_columns': ['personality_id', 'primary_voice_id', 'voice_settings']
                },
                {
                    'name': 'audio_cache_stats',
                    'purpose': 'Track daily audio generation statistics',
                    'key_columns': ['date_recorded', 'daily_generations', 'cache_hits']
                }
            ],
            'indexes_created': [
                'idx_conversation_messages_audio_path',
                'idx_conversation_messages_voice_metadata',
                'idx_conversation_messages_audio_generated'
            ]
        },
        
        'configuration': {
            'required_env_vars': [
                {
                    'name': 'ELEVENLABS_API_KEY',
                    'description': 'ElevenLabs API key for voice synthesis',
                    'example': 'sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                    'configured': bool(os.getenv('ELEVENLABS_API_KEY'))
                },
                {
                    'name': 'DATABASE_URL',
                    'description': 'PostgreSQL connection string',
                    'example': 'postgresql://user:pass@host:port/db',
                    'configured': bool(os.getenv('DATABASE_URL'))
                }
            ],
            'optional_settings': [
                {
                    'name': 'VOICE_CACHE_DURATION_DAYS',
                    'description': 'Audio cache retention period',
                    'default': 90
                },
                {
                    'name': 'VOICE_MAX_FILE_SIZE_MB',
                    'description': 'Maximum audio file size',
                    'default': 5
                },
                {
                    'name': 'VOICE_COMPRESSION_ENABLED',
                    'description': 'Enable GZIP compression for audio',
                    'default': True
                }
            ]
        },
        
        'performance_metrics': {
            'typical_generation_time': '2-5 seconds',
            'audio_compression_ratio': '0.3-0.4 (60-70% reduction)',
            'cache_hit_rate_target': '80%',
            'storage_efficiency': 'Base64 + GZIP in PostgreSQL',
            'rate_limiting': '100ms between ElevenLabs requests'
        },
        
        'integration_workflow': [
            '1. User clicks speaker button on AI response',
            '2. Frontend sends POST to /api/voice/synthesize',
            '3. System checks database cache for existing audio',
            '4. If cached: Return cached audio URL immediately',
            '5. If not cached: Generate with ElevenLabs API',
            '6. Apply personality-specific voice settings',
            '7. Compress and store audio in database',
            '8. Return audio URL for frontend playback',
            '9. Frontend plays MP3 audio with proper controls',
            '10. Cache statistics updated for analytics'
        ]
    }

async def check_module_health() -> Dict[str, Any]:
    """
    Comprehensive health check for voice synthesis module
    """
    health_results = {
        'module': 'voice_synthesis',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'overall_healthy': True,
        'components': {},
        'critical_issues': [],
        'warnings': [],
        'recommendations': []
    }
    
    integration = VoiceSynthesisIntegration()
    
    try:
        # 1. Check Environment Configuration
        api_key_configured = bool(os.getenv('ELEVENLABS_API_KEY'))
        database_configured = bool(os.getenv('DATABASE_URL'))
        
        health_results['components']['environment'] = {
            'healthy': api_key_configured and database_configured,
            'api_key_configured': api_key_configured,
            'database_configured': database_configured
        }
        
        if not api_key_configured:
            health_results['critical_issues'].append('ELEVENLABS_API_KEY not configured')
        if not database_configured:
            health_results['critical_issues'].append('DATABASE_URL not configured')
        
        # 2. Check ElevenLabs API Connectivity
        try:
            voice_client = integration.get_voice_client()
            api_health = await voice_client.health_check()
            
            health_results['components']['elevenlabs_api'] = {
                'healthy': api_health.get('connected', False),
                'connection_status': 'connected' if api_health.get('connected') else 'failed',
                'error': api_health.get('error'),
                'subscription_info': api_health.get('subscription', {}),
                'character_usage': {
                    'used': api_health.get('character_count', 0),
                    'limit': api_health.get('character_limit', 0)
                }
            }
            
            if not api_health.get('connected', False):
                health_results['critical_issues'].append(f"ElevenLabs API connection failed: {api_health.get('error')}")
            
            # Check character usage
            char_count = api_health.get('character_count', 0)
            char_limit = api_health.get('character_limit', 0)
            if char_limit > 0 and char_count / char_limit > 0.9:
                health_results['warnings'].append(f"ElevenLabs character usage at {(char_count/char_limit)*100:.1f}%")
        
        except Exception as e:
            health_results['components']['elevenlabs_api'] = {
                'healthy': False,
                'error': str(e)
            }
            health_results['critical_issues'].append(f"ElevenLabs client error: {str(e)}")
        
        # 3. Check Database Connectivity and Audio Cache
        try:
            audio_manager = integration.get_audio_manager()
            cache_health = await audio_manager.health_check()
            cache_stats = await audio_manager.get_cache_statistics()
            
            health_results['components']['audio_cache'] = {
                'healthy': cache_health.get('connected', False),
                'database_connected': cache_health.get('connected', False),
                'cached_files': cache_stats.get('total_files', 0),
                'cache_size_mb': cache_stats.get('total_size_mb', 0.0),
                'cache_hit_rate': cache_stats.get('cache_hit_rate', 0.0),
                'compression_enabled': cache_health.get('compression_enabled', False)
            }
            
            if not cache_health.get('connected', False):
                health_results['critical_issues'].append(f"Audio cache database connection failed: {cache_health.get('error')}")
            
            # Check cache performance
            if cache_stats.get('cache_hit_rate', 0.0) < 0.5:
                health_results['warnings'].append(f"Low cache hit rate: {cache_stats.get('cache_hit_rate', 0.0):.1%}")
            
            # Check cache size
            if cache_stats.get('total_size_mb', 0.0) > 500:  # 500MB warning threshold
                health_results['recommendations'].append(f"Large audio cache size ({cache_stats.get('total_size_mb', 0.0):.1f} MB) - consider cleanup")
        
        except Exception as e:
            health_results['components']['audio_cache'] = {
                'healthy': False,
                'error': str(e)
            }
            health_results['critical_issues'].append(f"Audio cache error: {str(e)}")
        
        # 4. Check Personality Voice Mappings
        try:
            personality_manager = integration.get_personality_manager()
            voice_mappings = await personality_manager.get_all_personality_mappings()
            
            required_personalities = ['syntaxprime', 'syntaxbot', 'nil_exe', 'ggpt']
            configured_personalities = list(voice_mappings.keys())
            missing_personalities = [p for p in required_personalities if p not in configured_personalities]
            
            health_results['components']['personality_voices'] = {
                'healthy': len(missing_personalities) == 0,
                'configured_personalities': len(configured_personalities),
                'required_personalities': len(required_personalities),
                'missing_personalities': missing_personalities,
                'voice_mappings': {
                    personality: {
                        'primary_voice': mapping.get('primary_voice'),
                        'has_fallback': bool(mapping.get('fallback_voice'))
                    }
                    for personality, mapping in voice_mappings.items()
                }
            }
            
            if missing_personalities:
                health_results['critical_issues'].append(f"Missing voice mappings for personalities: {missing_personalities}")
        
        except Exception as e:
            health_results['components']['personality_voices'] = {
                'healthy': False,
                'error': str(e)
            }
            health_results['critical_issues'].append(f"Personality voice mapping error: {str(e)}")
        
        # 5. Overall Health Assessment
        component_health = [
            health_results['components'].get('environment', {}).get('healthy', False),
            health_results['components'].get('elevenlabs_api', {}).get('healthy', False),
            health_results['components'].get('audio_cache', {}).get('healthy', False),
            health_results['components'].get('personality_voices', {}).get('healthy', False)
        ]
        
        health_results['overall_healthy'] = all(component_health) and len(health_results['critical_issues']) == 0
        health_results['components_healthy'] = sum(component_health)
        health_results['components_total'] = len(component_health)
        
        # 6. Performance Recommendations
        if health_results['overall_healthy']:
            if len(health_results['warnings']) == 0:
                health_results['recommendations'].append("Voice synthesis system is operating optimally")
            else:
                health_results['recommendations'].append("System healthy but consider addressing warnings")
        else:
            health_results['recommendations'].append("Critical issues must be resolved before system can operate")
    
    except Exception as e:
        health_results['overall_healthy'] = False
        health_results['critical_issues'].append(f"Health check failed: {str(e)}")
        logger.error(f"❌ Voice synthesis health check failed: {e}")
    
    return health_results

async def get_system_statistics() -> Dict[str, Any]:
    """
    Get comprehensive system statistics for voice synthesis
    """
    try:
        integration = VoiceSynthesisIntegration()
        
        # Get statistics from all components
        audio_manager = integration.get_audio_manager()
        personality_manager = integration.get_personality_manager()
        
        cache_stats = await audio_manager.get_cache_statistics()
        daily_stats = await audio_manager.get_daily_statistics()
        personality_stats = await audio_manager.get_personality_statistics()
        voice_usage_stats = await personality_manager.get_voice_usage_statistics()
        
        return {
            'module': 'voice_synthesis',
            'timestamp': datetime.now().isoformat(),
            'cache_statistics': cache_stats,
            'daily_statistics': daily_stats,
            'personality_statistics': personality_stats,
            'voice_usage_statistics': voice_usage_stats,
            'system_summary': {
                'total_audio_generated': cache_stats.get('total_files', 0),
                'total_storage_mb': cache_stats.get('total_size_mb', 0.0),
                'cache_efficiency': cache_stats.get('cache_hit_rate', 0.0),
                'most_used_personality': max(
                    personality_stats.get('personalities', {}).keys(),
                    key=lambda k: personality_stats.get('personalities', {}).get(k, {}).get('total_usage', 0),
                    default='none'
                ) if personality_stats.get('personalities') else 'none',
                'system_uptime_healthy': True  # Based on successful stats collection
            }
        }
    
    except Exception as e:
        logger.error(f"❌ Error getting voice synthesis statistics: {e}")
        return {
            'module': 'voice_synthesis',
            'timestamp': datetime.now().isoformat(),
            'error': str(e),
            'system_summary': {
                'system_uptime_healthy': False
            }
        }

# Testing and utility functions
async def test_integration_info():
    """Test the integration info module"""
    print("🎤 TESTING VOICE SYNTHESIS INTEGRATION INFO")
    print("=" * 45)
    
    # Test integration info
    print("\n📋 Getting integration info...")
    info = await get_integration_info()
    print(f"   Module: {info['module_info']['name']} v{info['module_info']['version']}")
    print(f"   Personalities: {len(info['personality_voices'])}")
    print(f"   API Endpoints: {len(info['api_endpoints'])}")
    
    # Test health check
    print(f"\n🏥 Running health check...")
    health = await check_module_health()
    print(f"   Overall healthy: {health['overall_healthy']}")
    print(f"   Components healthy: {health['components_healthy']}/{health['components_total']}")
    print(f"   Critical issues: {len(health['critical_issues'])}")
    print(f"   Warnings: {len(health['warnings'])}")
    
    # Test statistics
    print(f"\n📊 Getting system statistics...")
    stats = await get_system_statistics()
    cache_stats = stats.get('cache_statistics', {})
    print(f"   Total audio files: {cache_stats.get('total_files', 0)}")
    print(f"   Cache size: {cache_stats.get('total_size_mb', 0.0)} MB")
    print(f"   Cache hit rate: {cache_stats.get('cache_hit_rate', 0.0):.1%}")
    
    print(f"\n✅ Integration info test complete!")

if __name__ == "__main__":
    asyncio.run(test_integration_info())