"""
Personality Voice Manager
Handles voice selection and mapping for different AI personalities

Voice Mappings (chosen by SyntaxPrime):
- SyntaxPrime: Adam (professional sass with edge)
- SyntaxBot: Josh/Adam (quick-response professionalism) 
- Nil.exe: Daniel/Antoni (chaotic intelligence)
- GGPT: Sam/Josh (enthusiastic gaming energy)

Features:
- Database-driven voice mappings
- Fallback voice system
- Voice availability validation
- Dynamic voice switching
- Voice preference learning
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
import json

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class PersonalityVoiceManager:
    """
    Manages voice selection for different AI personalities
    Integrates with database for persistent voice mappings
    """
    
    def __init__(self):
        # Default fallback mappings (if database is unavailable)
        self.default_mappings = {
            'syntaxprime': {
                'primary_voice': 'Adam',
                'secondary_voice': None,
                'fallback_voice': 'Adam',
                'voice_settings': {
                    'style': 'professional_sass',
                    'stability': 0.75,
                    'clarity': 0.85,
                    'energy': 0.70
                }
            },
            'syntaxbot': {
                'primary_voice': 'Josh',
                'secondary_voice': 'Adam',
                'fallback_voice': 'Josh',
                'voice_settings': {
                    'style': 'quick_professional',
                    'stability': 0.80,
                    'clarity': 0.90,
                    'energy': 0.75
                }
            },
            'nil_exe': {
                'primary_voice': 'Daniel',
                'secondary_voice': 'Antoni',
                'fallback_voice': 'Daniel',
                'voice_settings': {
                    'style': 'chaotic_intelligence',
                    'stability': 0.60,
                    'clarity': 0.70,
                    'energy': 0.95
                }
            },
            'ggpt': {
                'primary_voice': 'Sam',
                'secondary_voice': 'Josh',
                'fallback_voice': 'Sam',
                'voice_settings': {
                    'style': 'gaming_energy',
                    'stability': 0.85,
                    'clarity': 0.80,
                    'energy': 0.90
                }
            }
        }
        
        # Voice ID mappings (ElevenLabs voice names to IDs)
        # Note: These might need to be updated based on actual ElevenLabs voice library
        self.voice_id_mappings = {
            'Adam': 'pNInz6obpgDQGcFmaJgB',
            'Josh': 'TxGEqnHWrfWFTfGW9XjX',
            'Daniel': 'onwK4e9ZLuTAKqWW03F9',
            'Antoni': 'ErXwobaYiN019PkySvjV',
            'Sam': 'yoZ06aMxZJJ28mfd3POQ'
        }
        
        # Cache for database mappings
        self._mapping_cache = {}
        self._cache_timestamp = 0
        self._cache_duration = 300  # 5 minutes
    
    def get_voice_for_personality(self, personality_id: str) -> Optional[str]:
        """
        Get the primary voice ID for a personality
        Returns ElevenLabs voice ID, not voice name
        """
        try:
            # Try to get from database first
            mapping = self._get_personality_mapping(personality_id)
            
            if mapping:
                primary_voice = mapping.get('primary_voice')
                if primary_voice:
                    # Convert voice name to ElevenLabs ID
                    return self.voice_id_mappings.get(primary_voice, primary_voice)
            
            # Fallback to default mapping
            default_mapping = self.default_mappings.get(personality_id.lower())
            if default_mapping:
                primary_voice = default_mapping['primary_voice']
                return self.voice_id_mappings.get(primary_voice, primary_voice)
            
            # Ultimate fallback - use SyntaxPrime's voice
            return self.voice_id_mappings.get('Adam', 'Adam')
        
        except Exception as e:
            logger.error(f"❌ Error getting voice for personality {personality_id}: {e}")
            return self.voice_id_mappings.get('Adam', 'Adam')
    
    def get_fallback_voice(self, personality_id: str) -> str:
        """
        Get fallback voice if primary voice fails
        """
        try:
            mapping = self._get_personality_mapping(personality_id)
            
            if mapping:
                # Try secondary voice first
                secondary_voice = mapping.get('secondary_voice')
                if secondary_voice:
                    return self.voice_id_mappings.get(secondary_voice, secondary_voice)
                
                # Then fallback voice
                fallback_voice = mapping.get('fallback_voice')
                if fallback_voice:
                    return self.voice_id_mappings.get(fallback_voice, fallback_voice)
            
            # Default fallback logic
            default_mapping = self.default_mappings.get(personality_id.lower())
            if default_mapping:
                secondary_voice = default_mapping.get('secondary_voice')
                if secondary_voice:
                    return self.voice_id_mappings.get(secondary_voice, secondary_voice)
                
                fallback_voice = default_mapping['fallback_voice']
                return self.voice_id_mappings.get(fallback_voice, fallback_voice)
            
            # Ultimate fallback
            return self.voice_id_mappings.get('Adam', 'Adam')
        
        except Exception as e:
            logger.error(f"❌ Error getting fallback voice for {personality_id}: {e}")
            return self.voice_id_mappings.get('Adam', 'Adam')
    
    def _get_personality_mapping(self, personality_id: str) -> Optional[Dict[str, Any]]:
        """
        Get personality mapping from database with caching
        """
        try:
            import time
            current_time = time.time()
            
            # Check cache first
            if (personality_id in self._mapping_cache and
                current_time - self._cache_timestamp < self._cache_duration):
                return self._mapping_cache[personality_id]
            
            # Get from database (this would be async in real implementation)
            # For now, return default mapping
            # TODO: Implement actual database query
            
            mapping = self.default_mappings.get(personality_id.lower())
            if mapping:
                self._mapping_cache[personality_id] = mapping
                self._cache_timestamp = current_time
            
            return mapping
        
        except Exception as e:
            logger.error(f"❌ Error getting personality mapping for {personality_id}: {e}")
            return None
    
    async def get_all_personality_mappings(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all personality voice mappings from database
        """
        try:
            # Query database for all mappings
            query = """
            SELECT personality_id, primary_voice_id, secondary_voice_id, 
                   fallback_voice_id, voice_settings
            FROM voice_personality_mappings
            ORDER BY personality_id;
            """
            
            mappings = await db_manager.fetch_all(query)
            
            result = {}
            for mapping in mappings:
                personality_id = mapping['personality_id']
                
                # Parse voice settings JSON
                voice_settings = mapping['voice_settings']
                if isinstance(voice_settings, str):
                    voice_settings = json.loads(voice_settings)
                
                result[personality_id] = {
                    'primary_voice': mapping['primary_voice_id'],
                    'secondary_voice': mapping['secondary_voice_id'],
                    'fallback_voice': mapping['fallback_voice_id'],
                    'voice_settings': voice_settings,
                    'primary_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['primary_voice_id'],
                        mapping['primary_voice_id']
                    ),
                    'secondary_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['secondary_voice_id'],
                        mapping['secondary_voice_id']
                    ) if mapping['secondary_voice_id'] else None,
                    'fallback_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['fallback_voice_id'],
                        mapping['fallback_voice_id']
                    )
                }
            
            # Add any missing personalities from defaults
            for personality_id, default_mapping in self.default_mappings.items():
                if personality_id not in result:
                    result[personality_id] = {
                        **default_mapping,
                        'primary_voice_elevenlabs_id': self.voice_id_mappings.get(
                            default_mapping['primary_voice']
                        ),
                        'secondary_voice_elevenlabs_id': self.voice_id_mappings.get(
                            default_mapping['secondary_voice']
                        ) if default_mapping['secondary_voice'] else None,
                        'fallback_voice_elevenlabs_id': self.voice_id_mappings.get(
                            default_mapping['fallback_voice']
                        )
                    }
            
            logger.info(f"📋 Retrieved voice mappings for {len(result)} personalities")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error getting all personality mappings: {e}")
            
            # Return default mappings with ElevenLabs IDs
            result = {}
            for personality_id, mapping in self.default_mappings.items():
                result[personality_id] = {
                    **mapping,
                    'primary_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['primary_voice']
                    ),
                    'secondary_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['secondary_voice']
                    ) if mapping['secondary_voice'] else None,
                    'fallback_voice_elevenlabs_id': self.voice_id_mappings.get(
                        mapping['fallback_voice']
                    )
                }
            
            return result
    
    async def update_personality_voice(self,
                                     personality_id: str,
                                     primary_voice: str,
                                     secondary_voice: Optional[str] = None,
                                     voice_settings: Optional[Dict] = None) -> bool:
        """
        Update voice mapping for a personality
        """
        try:
            # Prepare voice settings
            if voice_settings is None:
                voice_settings = self.default_mappings.get(
                    personality_id.lower(), {}
                ).get('voice_settings', {})
            
            voice_settings_json = json.dumps(voice_settings)
            
            # Update database
            query = """
            UPDATE voice_personality_mappings 
            SET primary_voice_id = $1,
                secondary_voice_id = $2,
                voice_settings = $3::jsonb,
                updated_at = NOW()
            WHERE personality_id = $4
            """
            
            await db_manager.execute(
                query,
                primary_voice,
                secondary_voice,
                voice_settings_json,
                personality_id
            )
            
            # Clear cache for this personality
            if personality_id in self._mapping_cache:
                del self._mapping_cache[personality_id]
            
            logger.info(f"✅ Updated voice mapping for {personality_id}: {primary_voice}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error updating voice mapping for {personality_id}: {e}")
            return False
    
    def get_voice_characteristics(self, personality_id: str) -> Dict[str, Any]:
        """
        Get voice characteristics and settings for a personality
        """
        try:
            mapping = self._get_personality_mapping(personality_id)
            
            if mapping and 'voice_settings' in mapping:
                return mapping['voice_settings']
            
            # Return default characteristics
            return {
                'style': 'neutral',
                'stability': 0.75,
                'clarity': 0.80,
                'energy': 0.75
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting voice characteristics for {personality_id}: {e}")
            return {}
    
    def validate_personality_voice_setup(self, personality_id: str) -> Dict[str, Any]:
        """
        Validate that a personality has proper voice configuration
        """
        try:
            primary_voice = self.get_voice_for_personality(personality_id)
            fallback_voice = self.get_fallback_voice(personality_id)
            characteristics = self.get_voice_characteristics(personality_id)
            
            validation = {
                'personality_id': personality_id,
                'has_primary_voice': bool(primary_voice),
                'has_fallback_voice': bool(fallback_voice),
                'has_voice_settings': bool(characteristics),
                'primary_voice_name': self._get_voice_name_from_id(primary_voice),
                'fallback_voice_name': self._get_voice_name_from_id(fallback_voice),
                'voice_settings': characteristics
            }
            
            validation['is_valid'] = (
                validation['has_primary_voice'] and
                validation['has_fallback_voice'] and
                validation['has_voice_settings']
            )
            
            return validation
        
        except Exception as e:
            logger.error(f"❌ Error validating voice setup for {personality_id}: {e}")
            return {
                'personality_id': personality_id,
                'is_valid': False,
                'error': str(e)
            }
    
    def _get_voice_name_from_id(self, voice_id: str) -> Optional[str]:
        """Get voice name from ElevenLabs ID"""
        for name, id_val in self.voice_id_mappings.items():
            if id_val == voice_id:
                return name
        return voice_id  # Return the ID if name not found
    
    async def get_voice_usage_statistics(self) -> Dict[str, Any]:
        """
        Get statistics on voice usage across personalities
        """
        try:
            # FIXED: Using PostgreSQL JSONB syntax (was SQLite json_extract)
            query = """
            SELECT 
                voice_synthesis_metadata->>'personality_id' as personality_id,
                voice_synthesis_metadata->>'voice_id' as voice_id,
                COUNT(*) as usage_count,
                COALESCE(AVG(audio_file_size), 0) as avg_file_size,
                MAX(audio_generated_at) as last_used
            FROM conversation_messages 
            WHERE voice_synthesis_metadata IS NOT NULL 
                AND voice_synthesis_metadata != '{}'::jsonb
                AND audio_file_path IS NOT NULL
            GROUP BY 
                voice_synthesis_metadata->>'personality_id',
                voice_synthesis_metadata->>'voice_id'
            ORDER BY usage_count DESC;
            """
            
            usage_stats = await db_manager.fetch_all(query)
            
            # Process results
            stats_by_personality = {}
            total_usage = 0
            
            for stat in usage_stats:
                personality_id = stat['personality_id']
                voice_id = stat['voice_id']
                usage_count = stat['usage_count']
                
                # Skip if personality_id is None (shouldn't happen but be safe)
                if personality_id is None:
                    continue
                
                if personality_id not in stats_by_personality:
                    stats_by_personality[personality_id] = {
                        'total_usage': 0,
                        'voices_used': {},
                        'avg_file_size': 0,
                        'last_used': None
                    }
                
                stats_by_personality[personality_id]['voices_used'][voice_id] = {
                    'usage_count': usage_count,
                    'avg_file_size': stat['avg_file_size'],
                    'last_used': stat['last_used'].isoformat() if stat['last_used'] else None
                }
                
                stats_by_personality[personality_id]['total_usage'] += usage_count
                total_usage += usage_count
            
            return {
                'total_voice_generations': total_usage,
                'personalities': stats_by_personality,
                'summary': {
                    'most_used_personality': max(
                        stats_by_personality.keys(),
                        key=lambda k: stats_by_personality[k]['total_usage']
                    ) if stats_by_personality else None,
                    'total_personalities_used': len(stats_by_personality)
                }
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting voice usage statistics: {e}")
            return {
                'total_voice_generations': 0,
                'personalities': {},
                'error': str(e)
            }


# Testing and utility functions
async def test_personality_voice_manager():
    """Test the personality voice manager"""
    manager = PersonalityVoiceManager()
    
    print("🎭 TESTING PERSONALITY VOICE MANAGER")
    print("=" * 40)
    
    # Test voice selection for each personality
    personalities = ['syntaxprime', 'syntaxbot', 'nil_exe', 'ggpt']
    
    for personality in personalities:
        primary_voice = manager.get_voice_for_personality(personality)
        fallback_voice = manager.get_fallback_voice(personality)
        characteristics = manager.get_voice_characteristics(personality)
        validation = manager.validate_personality_voice_setup(personality)
        
        print(f"\n🎤 {personality.upper()}:")
        print(f"   Primary Voice: {primary_voice}")
        print(f"   Fallback Voice: {fallback_voice}")
        print(f"   Valid Setup: {validation.get('is_valid', False)}")
        print(f"   Voice Style: {characteristics.get('style', 'unknown')}")
    
    # Test getting all mappings
    print(f"\n📋 Testing database mappings...")
    all_mappings = await manager.get_all_personality_mappings()
    print(f"   Total personalities configured: {len(all_mappings)}")
    
    print("\n✅ Personality voice manager test complete!")

if __name__ == "__main__":
    asyncio.run(test_personality_voice_manager())
