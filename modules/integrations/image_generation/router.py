# modules/integrations/image_generation/router.py
"""
Image Generation FastAPI Router for Syntax Prime V2
Provides endpoints for chat interface integration and image management

Key Features:
- Generate images from chat commands via OpenRouter/Gemini 3 Pro
- Retrieve image history and downloads
- Style template management
- Health checks and system status
- Integration with chat interface
"""

import logging
import base64
import io
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .openrouter_image_client import OpenRouterImageClient
from .database_manager import ImageDatabase

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(prefix="/integrations/image-generation", tags=["Image Generation"])

# Lazy initialization - singletons created on first use
_image_client: Optional[OpenRouterImageClient] = None
_image_db: Optional[ImageDatabase] = None


def get_image_client() -> OpenRouterImageClient:
    """Get or create OpenRouterImageClient singleton"""
    global _image_client
    if _image_client is None:
        _image_client = OpenRouterImageClient()
    return _image_client


def get_image_db() -> ImageDatabase:
    """Get or create ImageDatabase singleton"""
    global _image_db
    if _image_db is None:
        _image_db = ImageDatabase()
    return _image_db


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ImageGenerationRequest(BaseModel):
    prompt: str
    content_type: Optional[str] = "general"
    width: Optional[int] = 1024
    height: Optional[int] = 1024
    style_template: Optional[str] = None
    speed_priority: Optional[bool] = False


class ImageGenerationResponse(BaseModel):
    success: bool
    image_id: Optional[str] = None
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    original_prompt: str
    enhanced_prompt: str
    model_used: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    resolution: Optional[str] = None
    error: Optional[str] = None


class ImageHistoryResponse(BaseModel):
    images: List[Dict[str, Any]]
    total_count: int
    page: int
    limit: int


class StyleTemplateResponse(BaseModel):
    templates: List[Dict[str, Any]]
    total_count: int


class HealthResponse(BaseModel):
    healthy: bool
    api_status: str
    database_status: str
    total_images: int
    recent_generations: int
    available_models: int


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_current_user_id() -> str:
    """Get current user ID - integrates with your auth system"""
    try:
        db = get_image_db()
        user_id = await db.get_user_id()
        if not user_id:
            raise HTTPException(status_code=401, detail="No user found")
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user ID: {e}")
        raise HTTPException(status_code=500, detail="Failed to authenticate user")


# ============================================================================
# IMAGE GENERATION ENDPOINTS
# ============================================================================

@router.post("/generate", response_model=ImageGenerationResponse)
async def generate_image(
    request: ImageGenerationRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id)
):
    """
    Generate an image from a text prompt
    This is the main endpoint called by chat commands
    """
    try:
        client = get_image_client()
        db = get_image_db()
        
        logger.info(f"Generating image: '{request.prompt[:50]}...' for user {user_id}")
        
        # Get style template if specified
        style_template = None
        if request.style_template:
            style_template_obj = await db.get_style_template(name=request.style_template)
            if style_template_obj:
                style_template = {
                    'style_prompt': style_template_obj.style_prompt,
                    'color_scheme': style_template_obj.color_scheme
                }
                # Update usage stats in background
                background_tasks.add_task(
                    db.update_style_usage,
                    request.style_template,
                    True
                )
        
        # Generate the image using OpenRouter/Gemini 3 Pro
        generation_result = await client.generate_image(
            prompt=request.prompt,
            content_type=request.content_type,
            width=request.width,
            height=request.height,
            style_template=style_template,
            speed_priority=request.speed_priority
        )
        
        if not generation_result['success']:
            logger.error(f"Image generation failed: {generation_result.get('error')}")
            return ImageGenerationResponse(
                success=False,
                original_prompt=request.prompt,
                enhanced_prompt=generation_result.get('enhanced_prompt', request.prompt),
                error=generation_result.get('error', 'Unknown generation error')
            )
        
        # Save to database
        image_id = None
        try:
            generation_result['style_applied'] = request.style_template or ''
            image_id = await db.save_generated_image(generation_result, user_id)
        except Exception as e:
            logger.error(f"Failed to save image to database: {e}")
            # Don't fail the request if save fails - user still gets the image
        
        return ImageGenerationResponse(
            success=True,
            image_id=image_id,
            image_base64=generation_result['image_base64'],
            image_url=generation_result.get('image_url', ''),
            original_prompt=generation_result['original_prompt'],
            enhanced_prompt=generation_result['enhanced_prompt'],
            model_used=generation_result['model_used'],
            generation_time_seconds=generation_result['generation_time_seconds'],
            resolution=generation_result['resolution']
        )
        
    except Exception as e:
        logger.error(f"Image generation endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@router.get("/quick-generate/{prompt}")
async def quick_generate(
    prompt: str,
    content_type: str = "general",
    user_id: str = Depends(get_current_user_id)
):
    """
    Quick image generation endpoint for simple chat commands
    Usage: GET /integrations/image-generation/quick-generate/blue circle
    """
    request = ImageGenerationRequest(
        prompt=prompt,
        content_type=content_type,
        speed_priority=True,  # Use fast model for quick requests
        width=1024,
        height=1024
    )
    
    return await generate_image(request, BackgroundTasks(), user_id)


# ============================================================================
# IMAGE RETRIEVAL ENDPOINTS
# ============================================================================

@router.get("/history", response_model=ImageHistoryResponse)
async def get_image_history(
    page: int = 1,
    limit: int = 20,
    content_type: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get user's image generation history"""
    try:
        db = get_image_db()
        
        # Get recent images
        images = await db.get_recent_images(user_id, limit)
        
        # Filter by content type if specified
        if content_type:
            images = [img for img in images if img.get('content_type') == content_type]
        
        # Format for response (exclude base64 data for list view)
        formatted_images = []
        for img in images:
            formatted_img = dict(img)
            formatted_img['id'] = str(formatted_img['id'])
            if formatted_img.get('created_at'):
                formatted_img['created_at'] = formatted_img['created_at'].isoformat()
            # Don't include base64 in list view for performance
            formatted_img.pop('image_data_base64', None)
            formatted_images.append(formatted_img)
        
        return ImageHistoryResponse(
            images=formatted_images,
            total_count=len(formatted_images),
            page=page,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Failed to get image history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve image history")


@router.get("/image/{image_id}")
async def get_image_details(
    image_id: str,
    include_base64: bool = True,
    user_id: str = Depends(get_current_user_id)
):
    """Get detailed information about a specific image"""
    try:
        db = get_image_db()
        image = await db.get_image_by_id(image_id)
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Verify user owns this image
        if image.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        result = {
            'id': image.id,
            'original_prompt': image.original_prompt,
            'enhanced_prompt': image.enhanced_prompt,
            'content_type': image.content_type,
            'model_used': image.model_used,
            'generation_time_seconds': image.generation_time_seconds,
            'resolution': image.resolution,
            'file_format': image.file_format,
            'download_count': image.download_count,
            'created_at': image.created_at.isoformat() if image.created_at else None,
            'image_url': image.image_url
        }
        
        if include_base64:
            result['image_base64'] = image.image_base64
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get image details: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve image details")


@router.get("/search")
async def search_images(
    keywords: str,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id)
):
    """Search images by keywords in prompts"""
    try:
        db = get_image_db()
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
        
        if not keyword_list:
            raise HTTPException(status_code=400, detail="No keywords provided")
        
        images = await db.search_images_by_keyword(keyword_list, user_id, limit)
        
        # Format response
        formatted_images = []
        for img in images:
            formatted_img = dict(img)
            formatted_img['id'] = str(formatted_img['id'])
            if formatted_img.get('created_at'):
                formatted_img['created_at'] = formatted_img['created_at'].isoformat()
            formatted_images.append(formatted_img)
        
        return {
            'images': formatted_images,
            'keywords_searched': keyword_list,
            'total_found': len(formatted_images)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image search failed: {e}")
        raise HTTPException(status_code=500, detail="Image search failed")


# ============================================================================
# DOWNLOAD ENDPOINTS
# ============================================================================

@router.get("/download/{image_id}")
async def download_image(
    image_id: str,
    format: str = "png",
    user_id: str = Depends(get_current_user_id)
):
    """Download an image in specified format"""
    try:
        db = get_image_db()
        image = await db.get_image_by_id(image_id)
        
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        
        if image.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Convert base64 to bytes
        if not image.image_base64:
            raise HTTPException(status_code=404, detail="Image data not available")
        
        try:
            image_bytes = base64.b64decode(image.image_base64)
        except Exception:
            raise HTTPException(status_code=500, detail="Invalid image data")
        
        # Update download count
        await db.increment_download_count(image_id)
        
        # Generate filename
        safe_prompt = "".join(
            c for c in image.original_prompt[:30]
            if c.isalnum() or c in (' ', '-', '_')
        ).rstrip()
        filename = f"{safe_prompt}_{image_id[:8]}.{format}"
        
        # Return file download
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type=f"image/{format}",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")


# ============================================================================
# STYLE TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/styles", response_model=StyleTemplateResponse)
async def get_available_styles():
    """Get all available style templates"""
    try:
        db = get_image_db()
        styles = await db.get_available_styles()
        
        return StyleTemplateResponse(
            templates=styles,
            total_count=len(styles)
        )
        
    except Exception as e:
        logger.error(f"Failed to get styles: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve styles")


@router.get("/styles/{style_name}")
async def get_style_template(style_name: str):
    """Get details about a specific style template"""
    try:
        db = get_image_db()
        template = await db.get_style_template(name=style_name)
        
        if not template:
            raise HTTPException(status_code=404, detail="Style template not found")
        
        return {
            'id': template.id,
            'name': template.name,
            'business_area': template.business_area,
            'style_prompt': template.style_prompt,
            'color_scheme': template.color_scheme,
            'typical_elements': template.typical_elements,
            'usage_count': template.usage_count,
            'success_rate': template.success_rate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get style template: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve style template")


# ============================================================================
# ANALYTICS AND ADMIN ENDPOINTS
# ============================================================================

@router.get("/stats")
async def get_generation_stats(
    days: int = 30,
    user_id: str = Depends(get_current_user_id)
):
    """Get image generation statistics"""
    try:
        db = get_image_db()
        stats = await db.get_generation_stats(user_id, days)
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for image generation system"""
    try:
        client = get_image_client()
        db = get_image_db()
        
        # Check database health
        db_health = await db.health_check()
        
        # Check API connection
        api_health = await client.test_api_connection()
        
        # Get available models
        models = client.get_available_models()
        
        return HealthResponse(
            healthy=db_health['healthy'] and api_health['success'],
            api_status=api_health['status'],
            database_status="healthy" if db_health['healthy'] else "unhealthy",
            total_images=db_health.get('total_images', 0),
            recent_generations=db_health.get('recent_generations', 0),
            available_models=len(models)
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            healthy=False,
            api_status="error",
            database_status="error",
            total_images=0,
            recent_generations=0,
            available_models=0
        )


# ============================================================================
# CHAT INTEGRATION ENDPOINTS (for AI router)
# ============================================================================

@router.post("/chat-generate")
async def chat_generate_image(
    prompt: str,
    content_type: str = "general",
    style: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Simplified endpoint for chat integration
    Called by the AI router when processing image commands
    """
    try:
        request = ImageGenerationRequest(
            prompt=prompt,
            content_type=content_type,
            style_template=style,
            speed_priority=False,  # Default to quality for chat commands
        )
        
        result = await generate_image(request, BackgroundTasks(), user_id)
        
        # Return simplified response for chat
        return {
            'success': result.success,
            'image_id': result.image_id,
            'image_base64': result.image_base64,
            'prompt': result.enhanced_prompt,
            'model': result.model_used,
            'generation_time': result.generation_time_seconds,
            'error': result.error
        }
        
    except Exception as e:
        logger.error(f"Chat image generation failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'prompt': prompt
        }


# ============================================================================
# STARTUP/SHUTDOWN HANDLERS
# ============================================================================

@router.on_event("startup")
async def startup_image_generation():
    """Initialize image generation system"""
    logger.info("🎨 Image generation system starting up...")
    
    try:
        client = get_image_client()
        db = get_image_db()
        
        db_health = await db.health_check()
        logger.info(f"Database: {'✅' if db_health['healthy'] else '❌'}")
        
        api_health = await client.test_api_connection()
        logger.info(f"OpenRouter API: {'✅' if api_health['success'] else '❌'}")
        
        if db_health['healthy'] and api_health['success']:
            logger.info("🎉 Image generation system ready!")
        else:
            logger.warning("⚠️ Image generation system has issues - check logs")
            
    except Exception as e:
        logger.error(f"Image generation startup failed: {e}")


@router.on_event("shutdown")
async def shutdown_image_generation():
    """Clean up image generation system"""
    logger.info("🎨 Image generation system shutting down...")
    
    if _image_client is not None:
        try:
            await _image_client.close_session()
            logger.info("✅ OpenRouter client session closed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
