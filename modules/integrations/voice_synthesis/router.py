"""
Voice Synthesis FastAPI Router
Handles all HTTP endpoints for ElevenLabs voice synthesis integration

Endpoints:
- POST /api/voice/synthesize - Generate speech from text
- GET /api/voice/audio/{message_id} - Retrieve cached audio
- GET /api/voice/personalities - Get personality voice mappings
- GET /api/voice/health - Voice integration health check
- GET /api/voice/stats - Audio cache statistics
"""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import logging
import os

# Use singleton getters instead of direct class imports
from . import get_voice_client, get_personality_voice_manager, get_audio_cache_manager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/voice", tags=["voice_synthesis"])

# Request/Response models
class VoiceSynthesisRequest(BaseModel):
    text: str
    message_id: str
    personality_id: str = "syntaxprime"
    voice_override: Optional[str] = None  # Override personality voice choice

class VoiceSynthesisResponse(BaseModel):
    success: bool
    message_id: str
    audio_url: Optional[str] = None
    file_size: Optional[int] = None
    generation_time_ms: Optional[int] = None
    voice_used: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None

class PersonalityVoicesResponse(BaseModel):
    personalities: Dict[str, Dict[str, Any]]
    total_personalities: int

class VoiceHealthResponse(BaseModel):
    healthy: bool
    api_key_configured: bool
    database_connected: bool
    total_cached_audio: int
    cache_size_mb: float
    last_generation: Optional[str] = None
    errors: list = []


@router.post("/synthesize", response_model=VoiceSynthesisResponse)
async def synthesize_speech(request: VoiceSynthesisRequest):
    """
    Generate speech from text using personality-specific voice
    Caches audio in database for future playback
    """
    try:
        # Get singleton instances (reuses existing connections/sessions)
        voice_client = get_voice_client()
        personality_manager = get_personality_voice_manager()
        audio_manager = get_audio_cache_manager()
        
        # Check if audio already exists in cache
        cached_audio = await audio_manager.get_cached_audio(request.message_id)
        if cached_audio:
            logger.info(f"🎵 Returning cached audio for message {request.message_id}")
            return VoiceSynthesisResponse(
                success=True,
                message_id=request.message_id,
                audio_url=f"/api/voice/audio/{request.message_id}",
                file_size=cached_audio.get('file_size'),
                voice_used=cached_audio.get('voice_used'),
                cached=True
            )
        
        # Get voice for personality
        voice_id = request.voice_override or personality_manager.get_voice_for_personality(
            request.personality_id
        )
        
        if not voice_id:
            raise HTTPException(
                status_code=400,
                detail=f"No voice configured for personality: {request.personality_id}"
            )
        
        # Generate audio
        logger.info(f"🎤 Generating audio for message {request.message_id} with voice {voice_id}")
        
        audio_result = await voice_client.generate_speech(
            text=request.text,
            voice_id=voice_id,
            personality_id=request.personality_id
        )
        
        if not audio_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Audio generation failed: {audio_result.get('error')}"
            )
        
        # Cache audio in database
        cache_result = await audio_manager.cache_audio(
            message_id=request.message_id,
            audio_data=audio_result['audio_data'],
            metadata={
                'personality_id': request.personality_id,
                'voice_id': voice_id,
                'text_length': len(request.text),
                'generation_time_ms': audio_result.get('generation_time_ms'),
                'file_format': 'mp3'
            }
        )
        
        if not cache_result.get('success'):
            logger.warning(f"⚠️  Failed to cache audio for message {request.message_id}")
        
        return VoiceSynthesisResponse(
            success=True,
            message_id=request.message_id,
            audio_url=f"/api/voice/audio/{request.message_id}",
            file_size=len(audio_result['audio_data']),
            generation_time_ms=audio_result.get('generation_time_ms'),
            voice_used=voice_id,
            cached=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Voice synthesis failed for message {request.message_id}: {e}")
        return VoiceSynthesisResponse(
            success=False,
            message_id=request.message_id,
            error=str(e)
        )


@router.get("/audio/{message_id}")
async def get_audio(message_id: str):
    """
    Retrieve cached audio file by message ID
    Returns MP3 audio data with proper headers
    """
    try:
        audio_manager = get_audio_cache_manager()
        
        # Get audio from cache
        audio_data = await audio_manager.get_audio_data(message_id)
        
        if not audio_data:
            raise HTTPException(
                status_code=404,
                detail=f"Audio not found for message: {message_id}"
            )
        
        # Return audio with proper headers
        return Response(
            content=audio_data['data'],
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"inline; filename=audio_{message_id}.mp3",
                "Content-Length": str(len(audio_data['data'])),
                "Cache-Control": "public, max-age=86400"  # Cache for 24 hours
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to retrieve audio for message {message_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve audio: {str(e)}"
        )


@router.get("/personalities", response_model=PersonalityVoicesResponse)
async def get_personality_voices():
    """
    Get voice mappings for all personalities
    Shows primary, secondary, and fallback voices
    """
    try:
        personality_manager = get_personality_voice_manager()
        personalities = await personality_manager.get_all_personality_mappings()
        
        return PersonalityVoicesResponse(
            personalities=personalities,
            total_personalities=len(personalities)
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get personality voices: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get personality voices: {str(e)}"
        )


@router.get("/health", response_model=VoiceHealthResponse)
async def voice_health_check():
    """
    Comprehensive health check for voice synthesis system
    """
    errors = []
    
    try:
        # Check API key
        api_key_configured = bool(os.getenv('ELEVENLABS_API_KEY'))
        if not api_key_configured:
            errors.append("ELEVENLABS_API_KEY not configured")
        
        # Check database connectivity
        audio_manager = get_audio_cache_manager()
        db_health = await audio_manager.health_check()
        database_connected = db_health.get('connected', False)
        
        if not database_connected:
            errors.append(f"Database connection failed: {db_health.get('error')}")
        
        # Get cache statistics
        cache_stats = await audio_manager.get_cache_statistics()
        
        # Check ElevenLabs API connectivity
        voice_client = get_voice_client()
        api_health = await voice_client.health_check()
        
        if not api_health.get('connected', False):
            errors.append(f"ElevenLabs API connection failed: {api_health.get('error')}")
        
        # Overall health
        healthy = (
            api_key_configured and
            database_connected and
            api_health.get('connected', False) and
            len(errors) == 0
        )
        
        return VoiceHealthResponse(
            healthy=healthy,
            api_key_configured=api_key_configured,
            database_connected=database_connected,
            total_cached_audio=cache_stats.get('total_files', 0),
            cache_size_mb=cache_stats.get('total_size_mb', 0.0),
            last_generation=cache_stats.get('newest_audio'),
            errors=errors
        )
        
    except Exception as e:
        logger.error(f"❌ Voice health check failed: {e}")
        return VoiceHealthResponse(
            healthy=False,
            api_key_configured=False,
            database_connected=False,
            total_cached_audio=0,
            cache_size_mb=0.0,
            errors=[f"Health check failed: {str(e)}"]
        )


@router.get("/stats")
async def get_voice_statistics():
    """
    Get detailed voice synthesis and audio cache statistics
    """
    try:
        audio_manager = get_audio_cache_manager()
        
        # Get comprehensive statistics
        daily_stats = await audio_manager.get_daily_statistics()
        cache_stats = await audio_manager.get_cache_statistics()
        personality_stats = await audio_manager.get_personality_statistics()
        
        return {
            "cache_statistics": cache_stats,
            "daily_statistics": daily_stats,
            "personality_breakdown": personality_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get voice statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )


# Additional utility endpoints
@router.delete("/cache/{message_id}")
async def delete_cached_audio(message_id: str):
    """
    Delete cached audio for a specific message
    Useful for cache management and testing
    """
    try:
        audio_manager = get_audio_cache_manager()
        result = await audio_manager.delete_cached_audio(message_id)
        
        if result.get('success'):
            return {"success": True, "message": f"Audio deleted for message {message_id}"}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Audio not found for message: {message_id}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete cached audio for {message_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete audio: {str(e)}"
        )


@router.post("/cache/cleanup")
async def cleanup_audio_cache():
    """
    Clean up old or unused audio cache entries
    Removes audio older than specified days
    """
    try:
        audio_manager = get_audio_cache_manager()
        
        # Clean up audio older than 30 days
        cleanup_result = await audio_manager.cleanup_old_audio(days_to_keep=30)
        
        return {
            "success": True,
            "files_deleted": cleanup_result.get('files_deleted', 0),
            "space_freed_mb": cleanup_result.get('space_freed_mb', 0.0),
            "message": "Audio cache cleanup completed"
        }
        
    except Exception as e:
        logger.error(f"❌ Audio cache cleanup failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache cleanup failed: {str(e)}"
        )
