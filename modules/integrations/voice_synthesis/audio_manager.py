"""
Audio Cache Manager
Handles database storage and retrieval of synthesized audio files

Features:
- Database audio caching (conversation_messages table)
- Audio file compression and optimization
- Cache statistics and analytics
- Cleanup and maintenance operations
- Audio retrieval and streaming
- Cache hit/miss tracking

Storage Strategy:
- Audio stored as BYTEA in database (Railway PostgreSQL)
- Metadata stored in voice_synthesis_metadata JSONB field
- Indexed for fast retrieval by message_id
- Automatic cleanup of old audio files
"""

import asyncio
import logging
import json
import gzip
import base64
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import time

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class AudioCacheManager:
    """
    Manages audio file caching in database for voice synthesis
    Optimized for Railway PostgreSQL with efficient storage
    """
    
    def __init__(self):
        # Audio storage settings
        self.compression_enabled = True  # GZIP compress audio before storage
        self.max_audio_size = 5 * 1024 * 1024  # 5MB max per audio file
        self.cache_duration_days = 90  # Keep audio for 90 days
        
        # Performance tracking
        self.cache_hits = 0
        self.cache_misses = 0
        self.generation_times = []
    
    async def cache_audio(self, 
                         message_id: str, 
                         audio_data: bytes,
                         metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cache audio data in database with metadata
        
        Args:
            message_id: Unique message identifier
            audio_data: Raw MP3 audio bytes
            metadata: Voice synthesis metadata (personality, voice, etc.)
            
        Returns:
            Dictionary with success status and cache information
        """
        try:
            if len(audio_data) > self.max_audio_size:
                return {
                    'success': False,
                    'error': f'Audio file too large: {len(audio_data)} bytes (max: {self.max_audio_size})'
                }
            
            # Prepare audio data for storage
            if self.compression_enabled:
                compressed_data = gzip.compress(audio_data)
                storage_data = compressed_data
                metadata['compressed'] = True
                compression_ratio = len(compressed_data) / len(audio_data)
                logger.debug(f"Audio compressed: {len(audio_data)} → {len(compressed_data)} bytes ({compression_ratio:.2f})")
            else:
                storage_data = audio_data
                metadata['compressed'] = False
            
            # Encode for database storage
            encoded_data = base64.b64encode(storage_data).decode('utf-8')
            
            # Add storage metadata
            metadata.update({
                'original_size': len(audio_data),
                'stored_size': len(storage_data),
                'encoding': 'base64',
                'mime_type': 'audio/mpeg',
                'cached_at': datetime.now().isoformat()
            })
            
            metadata_json = json.dumps(metadata)
            
            # Update conversation_messages with audio data
            query = """
            UPDATE conversation_messages 
            SET 
                audio_file_path = $1,
                audio_file_size = $2,
                voice_synthesis_metadata = $3::jsonb,
                audio_generated_at = NOW()
            WHERE id = $4::uuid
            RETURNING id;
            """
            
            result = await db_manager.fetch_one(
                query,
                encoded_data,  # Store base64 encoded audio in audio_file_path
                len(audio_data),  # Original file size
                metadata_json,
                message_id
            )
            
            if result:
                logger.info(f"✅ Cached audio for message {message_id} ({len(audio_data)} bytes)")
                
                # Update cache statistics
                await self._update_cache_stats('cache_hit')
                
                return {
                    'success': True,
                    'message_id': message_id,
                    'file_size': len(audio_data),
                    'stored_size': len(storage_data),
                    'compression_ratio': len(storage_data) / len(audio_data) if self.compression_enabled else 1.0
                }
            else:
                return {
                    'success': False,
                    'error': f'Message {message_id} not found in database'
                }
        
        except Exception as e:
            logger.error(f"❌ Failed to cache audio for message {message_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_cached_audio(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if audio exists in cache and return metadata
        
        Args:
            message_id: Message identifier to check
            
        Returns:
            Dictionary with cache metadata or None if not cached
        """
        try:
            query = """
            SELECT 
                audio_file_size,
                voice_synthesis_metadata,
                audio_generated_at
            FROM conversation_messages 
            WHERE id = $1::uuid 
                AND audio_file_path IS NOT NULL
                AND audio_file_size > 0;
            """
            
            result = await db_manager.fetch_one(query, message_id)
            
            if result:
                # Parse metadata
                metadata = result['voice_synthesis_metadata']
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                self.cache_hits += 1
                
                return {
                    'file_size': result['audio_file_size'],
                    'metadata': metadata,
                    'generated_at': result['audio_generated_at'].isoformat() if result['audio_generated_at'] else None,
                    'voice_used': metadata.get('voice_id', 'unknown'),
                    'personality': metadata.get('personality_id', 'unknown')
                }
            else:
                self.cache_misses += 1
                return None
        
        except Exception as e:
            logger.error(f"❌ Error checking audio cache for message {message_id}: {e}")
            self.cache_misses += 1
            return None
    
    async def get_audio_data(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve actual audio data from cache
        
        Args:
            message_id: Message identifier
            
        Returns:
            Dictionary with audio data and metadata
        """
        try:
            query = """
            SELECT 
                audio_file_path,
                audio_file_size,
                voice_synthesis_metadata
            FROM conversation_messages 
            WHERE id = $1::uuid 
                AND audio_file_path IS NOT NULL;
            """
            
            result = await db_manager.fetch_one(query, message_id)
            
            if not result:
                return None
            
            # Decode audio data
            encoded_data = result['audio_file_path']
            storage_data = base64.b64decode(encoded_data.encode('utf-8'))
            
            # Parse metadata
            metadata = result['voice_synthesis_metadata']
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            # Decompress if needed
            if metadata.get('compressed', False):
                audio_data = gzip.decompress(storage_data)
            else:
                audio_data = storage_data
            
            logger.info(f"🎵 Retrieved cached audio for message {message_id} ({len(audio_data)} bytes)")
            
            return {
                'data': audio_data,
                'size': len(audio_data),
                'metadata': metadata,
                'mime_type': metadata.get('mime_type', 'audio/mpeg')
            }
        
        except Exception as e:
            logger.error(f"❌ Error retrieving audio data for message {message_id}: {e}")
            return None
    
    async def delete_cached_audio(self, message_id: str) -> Dict[str, Any]:
        """
        Delete cached audio for a specific message
        """
        try:
            query = """
            UPDATE conversation_messages 
            SET 
                audio_file_path = NULL,
                audio_file_size = NULL,
                voice_synthesis_metadata = '{}',
                audio_generated_at = NULL
            WHERE id = $1::uuid 
                AND audio_file_path IS NOT NULL
            RETURNING id;
            """
            
            result = await db_manager.fetch_one(query, message_id)
            
            if result:
                logger.info(f"🗑️  Deleted cached audio for message {message_id}")
                return {
                    'success': True,
                    'message_id': message_id
                }
            else:
                return {
                    'success': False,
                    'error': f'No cached audio found for message {message_id}'
                }
        
        except Exception as e:
            logger.error(f"❌ Error deleting cached audio for message {message_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def cleanup_old_audio(self, days_to_keep: int = 90) -> Dict[str, Any]:
        """
        Clean up audio files older than specified days
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Get files to be deleted (for size calculation)
            query_select = """
            SELECT COUNT(*) as file_count, SUM(audio_file_size) as total_size
            FROM conversation_messages 
            WHERE audio_generated_at < $1 
                AND audio_file_path IS NOT NULL;
            """
            
            stats = await db_manager.fetch_one(query_select, cutoff_date)
            
            # Delete old audio files
            query_delete = """
            UPDATE conversation_messages 
            SET 
                audio_file_path = NULL,
                audio_file_size = NULL,
                voice_synthesis_metadata = '{}',
                audio_generated_at = NULL
            WHERE audio_generated_at < $1 
                AND audio_file_path IS NOT NULL;
            """
            
            await db_manager.execute(query_delete, cutoff_date)
            
            files_deleted = stats['file_count'] or 0
            space_freed_bytes = stats['total_size'] or 0
            space_freed_mb = space_freed_bytes / (1024 * 1024)
            
            logger.info(f"🧹 Cleaned up {files_deleted} audio files, freed {space_freed_mb:.2f} MB")
            
            return {
                'success': True,
                'files_deleted': files_deleted,
                'space_freed_mb': round(space_freed_mb, 2)
            }
        
        except Exception as e:
            logger.error(f"❌ Error during audio cleanup: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics
        """
        try:
            # Current cache stats
            query_stats = """
            SELECT 
                COUNT(*) as total_files,
                SUM(audio_file_size) as total_size_bytes,
                AVG(audio_file_size) as avg_file_size,
                MIN(audio_generated_at) as oldest_audio,
                MAX(audio_generated_at) as newest_audio
            FROM conversation_messages 
            WHERE audio_file_path IS NOT NULL 
                AND audio_file_size > 0;
            """
            
            stats = await db_manager.fetch_one(query_stats)
            
            # Personality breakdown
            query_personality = """
            SELECT 
                json_extract(voice_synthesis_metadata, '$.personality_id') as personality_id,
                COUNT(*) as audio_count,
                SUM(audio_file_size) as total_size
            FROM conversation_messages 
            WHERE voice_synthesis_metadata IS NOT NULL 
                AND voice_synthesis_metadata != '{}'
                AND audio_file_path IS NOT NULL
            GROUP BY json_extract(voice_synthesis_metadata, '$.personality_id')
            ORDER BY audio_count DESC;
            """
            
            personality_stats = await db_manager.fetch_all(query_personality)
            
            # Recent activity (last 24 hours)
            query_recent = """
            SELECT COUNT(*) as recent_generations
            FROM conversation_messages 
            WHERE audio_generated_at >= NOW() - INTERVAL '24 hours'
                AND audio_file_path IS NOT NULL;
            """
            
            recent = await db_manager.fetch_one(query_recent)
            
            total_size_bytes = stats['total_size_bytes'] or 0
            total_size_mb = total_size_bytes / (1024 * 1024)
            
            return {
                'total_files': stats['total_files'] or 0,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_mb, 2),
                'avg_file_size': stats['avg_file_size'] or 0,
                'oldest_audio': stats['oldest_audio'].isoformat() if stats['oldest_audio'] else None,
                'newest_audio': stats['newest_audio'].isoformat() if stats['newest_audio'] else None,
                'recent_generations_24h': recent['recent_generations'] or 0,
                'personality_breakdown': [
                    {
                        'personality': stat['personality_id'],
                        'audio_count': stat['audio_count'],
                        'total_size_mb': round((stat['total_size'] or 0) / (1024 * 1024), 2)
                    }
                    for stat in personality_stats
                ],
                'cache_hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0.0,
                'total_cache_checks': self.cache_hits + self.cache_misses
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting cache statistics: {e}")
            return {
                'total_files': 0,
                'total_size_mb': 0.0,
                'error': str(e)
            }
    
    async def get_daily_statistics(self) -> Dict[str, Any]:
        """
        Get daily audio generation statistics
        """
        try:
            # Last 7 days of activity
            query = """
            SELECT 
                DATE(audio_generated_at) as generation_date,
                COUNT(*) as daily_generations,
                SUM(audio_file_size) as daily_size_bytes,
                AVG(json_extract(voice_synthesis_metadata, '$.generation_time_ms')::int) as avg_generation_time_ms
            FROM conversation_messages 
            WHERE audio_generated_at >= NOW() - INTERVAL '7 days'
                AND audio_file_path IS NOT NULL
                AND voice_synthesis_metadata IS NOT NULL
            GROUP BY DATE(audio_generated_at)
            ORDER BY generation_date DESC;
            """
            
            daily_stats = await db_manager.fetch_all(query)
            
            return {
                'daily_breakdown': [
                    {
                        'date': stat['generation_date'].isoformat() if stat['generation_date'] else None,
                        'generations': stat['daily_generations'],
                        'size_mb': round((stat['daily_size_bytes'] or 0) / (1024 * 1024), 2),
                        'avg_generation_time_ms': stat['avg_generation_time_ms']
                    }
                    for stat in daily_stats
                ],
                'total_days': len(daily_stats)
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting daily statistics: {e}")
            return {
                'daily_breakdown': [],
                'error': str(e)
            }
    
    async def get_personality_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics by personality
        """
        try:
            query = """
            SELECT 
                json_extract(voice_synthesis_metadata, '$.personality_id') as personality_id,
                json_extract(voice_synthesis_metadata, '$.voice_id') as voice_id,
                COUNT(*) as usage_count,
                SUM(audio_file_size) as total_size_bytes,
                AVG(audio_file_size) as avg_file_size,
                AVG(json_extract(voice_synthesis_metadata, '$.generation_time_ms')::int) as avg_generation_time_ms,
                MAX(audio_generated_at) as last_used
            FROM conversation_messages 
            WHERE voice_synthesis_metadata IS NOT NULL 
                AND voice_synthesis_metadata != '{}'
                AND audio_file_path IS NOT NULL
            GROUP BY 
                json_extract(voice_synthesis_metadata, '$.personality_id'),
                json_extract(voice_synthesis_metadata, '$.voice_id')
            ORDER BY usage_count DESC;
            """
            
            stats = await db_manager.fetch_all(query)
            
            personality_summary = {}
            for stat in stats:
                personality_id = stat['personality_id']
                if personality_id not in personality_summary:
                    personality_summary[personality_id] = {
                        'total_usage': 0,
                        'total_size_mb': 0.0,
                        'voices_used': {},
                        'avg_generation_time_ms': 0,
                        'last_used': None
                    }
                
                voice_id = stat['voice_id']
                personality_summary[personality_id]['voices_used'][voice_id] = {
                    'usage_count': stat['usage_count'],
                    'size_mb': round((stat['total_size_bytes'] or 0) / (1024 * 1024), 2),
                    'avg_file_size': stat['avg_file_size'],
                    'avg_generation_time_ms': stat['avg_generation_time_ms'],
                    'last_used': stat['last_used'].isoformat() if stat['last_used'] else None
                }
                
                personality_summary[personality_id]['total_usage'] += stat['usage_count']
                personality_summary[personality_id]['total_size_mb'] += round((stat['total_size_bytes'] or 0) / (1024 * 1024), 2)
                
                # Update last used if more recent
                if (not personality_summary[personality_id]['last_used'] or 
                    (stat['last_used'] and stat['last_used'] > datetime.fromisoformat(personality_summary[personality_id]['last_used']))):
                    personality_summary[personality_id]['last_used'] = stat['last_used'].isoformat() if stat['last_used'] else None
            
            return {
                'personalities': personality_summary,
                'total_personalities': len(personality_summary)
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting personality statistics: {e}")
            return {
                'personalities': {},
                'error': str(e)
            }
    
    async def _update_cache_stats(self, operation: str):
        """
        Update cache statistics in database
        """
        try:
            # Simple daily stats update
            query = """
            INSERT INTO audio_cache_stats (date_recorded, daily_generations, cache_hits)
            VALUES (CURRENT_DATE, 1, CASE WHEN $1 = 'cache_hit' THEN 1 ELSE 0 END)
            ON CONFLICT (date_recorded) 
            DO UPDATE SET 
                daily_generations = audio_cache_stats.daily_generations + 1,
                cache_hits = audio_cache_stats.cache_hits + CASE WHEN $1 = 'cache_hit' THEN 1 ELSE 0 END;
            """
            
            await db_manager.execute(query, operation)
        
        except Exception as e:
            logger.error(f"❌ Error updating cache stats: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check audio cache health and connectivity
        """
        try:
            # Test database connectivity
            query = "SELECT COUNT(*) FROM conversation_messages WHERE audio_file_path IS NOT NULL;"
            result = await db_manager.fetch_one(query)
            
            cached_files = result['count'] if result else 0
            
            return {
                'connected': True,
                'cached_files': cached_files,
                'compression_enabled': self.compression_enabled,
                'max_file_size_mb': self.max_audio_size / (1024 * 1024),
                'cache_duration_days': self.cache_duration_days
            }
        
        except Exception as e:
            logger.error(f"❌ Audio cache health check failed: {e}")
            return {
                'connected': False,
                'error': str(e)
            }

# Testing function
async def test_audio_cache_manager():
    """Test the audio cache manager"""
    manager = AudioCacheManager()
    
    print("🎵 TESTING AUDIO CACHE MANAGER")
    print("=" * 35)
    
    # Test health check
    health = await manager.health_check()
    print(f"   Database connected: {health.get('connected', False)}")
    print(f"   Cached files: {health.get('cached_files', 0)}")
    
    # Test cache statistics
    stats = await manager.get_cache_statistics()
    print(f"   Total cached audio: {stats.get('total_files', 0)}")
    print(f"   Cache size: {stats.get('total_size_mb', 0.0)} MB")
    print(f"   Cache hit rate: {stats.get('cache_hit_rate', 0.0):.2%}")
    
    print("\n✅ Audio cache manager test complete!")

if __name__ == "__main__":
    asyncio.run(test_audio_cache_manager())
