# modules/integrations/image_generation/database_manager.py
"""
Image Generation Database Manager for Syntax Prime V2
Handles saving, retrieving, and managing generated images and style templates

Key Features:
- Save generated images with full metadata
- Retrieve image history and search by keywords
- Manage style templates for consistency
- Track download counts and usage analytics
- Integration with existing user system
- Uses core db_manager for connection pooling
"""

import logging
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Default user ID for single-user system
DEFAULT_USER_ID = 'b7c60682-4815-4d9d-8ebe-66c6cd24eff9'


@dataclass
class GeneratedImage:
    """Container for generated image data"""
    id: str
    user_id: str
    original_prompt: str
    enhanced_prompt: str
    image_url: str
    image_base64: str
    model_used: str
    generation_time_seconds: float
    style_applied: str
    content_type: str
    resolution: str
    file_format: str
    download_count: int
    created_at: datetime


@dataclass
class StyleTemplate:
    """Container for style template data"""
    id: str
    name: str
    business_area: str
    style_prompt: str
    color_scheme: Dict
    typical_elements: List
    usage_count: int
    success_rate: float


class ImageDatabase:
    """
    Manages all database operations for image generation system
    Integrates with existing Syntax Prime V2 user system
    Uses core db_manager for proper connection pooling
    """
    
    def __init__(self):
        # No longer need database_url - using shared db_manager
        pass
    
    # ============================================================================
    # USER MANAGEMENT
    # ============================================================================
    
    async def get_user_id(self) -> str:
        """Get user ID - returns default for single-user system"""
        # For single-user system, return the known user ID
        # This avoids unnecessary database query
        return DEFAULT_USER_ID
    
    # ============================================================================
    # IMAGE GENERATION MANAGEMENT
    # ============================================================================
    
    async def save_generated_image(self, generation_result: Dict[str, Any],
                                 user_id: str = None) -> str:
        """
        Save a generated image to the database
        
        Args:
            generation_result: Result from OpenRouterImageClient.generate_image()
            user_id: Optional user ID (uses default if not provided)
            
        Returns:
            UUID of the saved image record
        """
        if not user_id:
            user_id = await self.get_user_id()
        
        # Extract data from generation result
        original_prompt = generation_result.get('original_prompt', '')
        enhanced_prompt = generation_result.get('enhanced_prompt', '')
        image_url = generation_result.get('image_url', '')
        image_base64 = generation_result.get('image_base64', '')
        model_used = generation_result.get('model_used', '')
        generation_time = generation_result.get('generation_time_seconds', 0)
        style_applied = generation_result.get('style_applied', '')
        content_type = generation_result.get('content_type', 'general')
        resolution = generation_result.get('resolution', '1024x1024')
        file_format = 'png'
        content_context = json.dumps(generation_result.get('metadata', {}))
        related_keywords = json.dumps(self._extract_keywords(original_prompt))
        
        # Calculate file size estimate (base64 is ~33% larger than binary)
        file_size_bytes = 0
        if image_base64:
            file_size_bytes = int(len(image_base64) * 0.75)
        
        # Insert the record
        query = """
            INSERT INTO generated_images 
            (user_id, original_prompt, enhanced_prompt, image_url, image_data_base64,
             model_used, generation_time_seconds, style_applied, content_type,
             resolution, file_format, file_size_bytes, content_context, related_keywords)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """
        
        try:
            result = await db_manager.fetch_one(
                query,
                user_id, original_prompt, enhanced_prompt, image_url, image_base64,
                model_used, generation_time, style_applied, content_type,
                resolution, file_format, file_size_bytes, content_context, related_keywords
            )
            
            image_id = str(result['id']) if result else None
            logger.info(f"Saved generated image with ID: {image_id}")
            return image_id
            
        except Exception as e:
            logger.error(f"Failed to save generated image: {e}")
            raise
    
    async def get_image_by_id(self, image_id: str) -> Optional[GeneratedImage]:
        """Get a specific generated image by ID"""
        query = """
            SELECT id, user_id, original_prompt, enhanced_prompt, image_url,
                   image_data_base64, model_used, generation_time_seconds,
                   style_applied, content_type, resolution, file_format,
                   download_count, created_at
            FROM generated_images 
            WHERE id = $1
        """
        
        row = await db_manager.fetch_one(query, image_id)
        
        if row:
            return GeneratedImage(
                id=str(row['id']),
                user_id=str(row['user_id']),
                original_prompt=row['original_prompt'] or '',
                enhanced_prompt=row['enhanced_prompt'] or '',
                image_url=row['image_url'] or '',
                image_base64=row['image_data_base64'] or '',
                model_used=row['model_used'] or '',
                generation_time_seconds=float(row['generation_time_seconds'] or 0),
                style_applied=row['style_applied'] or '',
                content_type=row['content_type'] or 'general',
                resolution=row['resolution'] or '1024x1024',
                file_format=row['file_format'] or 'png',
                download_count=row['download_count'] or 0,
                created_at=row['created_at']
            )
        return None
    
    async def get_recent_images(self, user_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent generated images for a user"""
        if not user_id:
            user_id = await self.get_user_id()
        
        query = """
            SELECT id, original_prompt, enhanced_prompt, content_type,
                   model_used, generation_time_seconds, resolution,
                   download_count, created_at
            FROM generated_images 
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        
        rows = await db_manager.fetch_all(query, user_id, limit)
        return [dict(row) for row in rows] if rows else []
    
    async def search_images_by_keyword(self, keywords: List[str],
                                     user_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search generated images by keywords in prompts"""
        if not user_id:
            user_id = await self.get_user_id()
        
        # Build search terms for LIKE matching
        search_terms = [f"%{keyword.lower()}%" for keyword in keywords]
        
        query = """
            SELECT id, original_prompt, enhanced_prompt, content_type,
                   model_used, created_at, download_count
            FROM generated_images 
            WHERE user_id = $1 
            AND (
                LOWER(original_prompt) LIKE ANY($2) OR 
                LOWER(enhanced_prompt) LIKE ANY($2) OR
                related_keywords @> $3
            )
            ORDER BY created_at DESC
            LIMIT $4
        """
        
        rows = await db_manager.fetch_all(
            query, user_id, search_terms, json.dumps(keywords), limit
        )
        return [dict(row) for row in rows] if rows else []
    
    async def increment_download_count(self, image_id: str) -> bool:
        """Increment download count for an image"""
        query = """
            UPDATE generated_images 
            SET download_count = download_count + 1,
                downloaded_at = NOW()
            WHERE id = $1
        """
        
        try:
            await db_manager.execute(query, image_id)
            return True
        except Exception as e:
            logger.error(f"Failed to increment download count: {e}")
            return False
    
    # ============================================================================
    # STYLE TEMPLATE MANAGEMENT
    # ============================================================================
    
    async def get_style_template(self, name: str = None,
                               business_area: str = None) -> Optional[StyleTemplate]:
        """Get a style template by name or business area"""
        if name:
            query = """
                SELECT id, name, business_area, style_prompt, color_scheme,
                       typical_elements, usage_count, success_rate
                FROM image_style_templates 
                WHERE name = $1
            """
            row = await db_manager.fetch_one(query, name)
        elif business_area:
            query = """
                SELECT id, name, business_area, style_prompt, color_scheme,
                       typical_elements, usage_count, success_rate
                FROM image_style_templates 
                WHERE business_area = $1
                ORDER BY usage_count DESC
                LIMIT 1
            """
            row = await db_manager.fetch_one(query, business_area)
        else:
            return None
        
        if row:
            # Parse JSON fields safely
            color_scheme = row['color_scheme']
            if isinstance(color_scheme, str):
                color_scheme = json.loads(color_scheme) if color_scheme else {}
            elif color_scheme is None:
                color_scheme = {}
            
            typical_elements = row['typical_elements']
            if isinstance(typical_elements, str):
                typical_elements = json.loads(typical_elements) if typical_elements else []
            elif typical_elements is None:
                typical_elements = []
            
            return StyleTemplate(
                id=str(row['id']),
                name=row['name'],
                business_area=row['business_area'] or '',
                style_prompt=row['style_prompt'] or '',
                color_scheme=color_scheme,
                typical_elements=typical_elements,
                usage_count=row['usage_count'] or 0,
                success_rate=float(row['success_rate'] or 0)
            )
        return None
    
    async def update_style_usage(self, template_name: str, success: bool = True) -> bool:
        """Update style template usage statistics"""
        query = """
            UPDATE image_style_templates 
            SET usage_count = usage_count + 1,
                success_rate = CASE 
                    WHEN $2 THEN LEAST(1.0, success_rate + 0.1)
                    ELSE GREATEST(0.0, success_rate - 0.1)
                END
            WHERE name = $1
        """
        
        try:
            await db_manager.execute(query, template_name, success)
            return True
        except Exception as e:
            logger.error(f"Failed to update style usage: {e}")
            return False
    
    async def get_available_styles(self) -> List[Dict[str, Any]]:
        """Get all available style templates"""
        query = """
            SELECT name, business_area, style_prompt, usage_count, success_rate
            FROM image_style_templates 
            ORDER BY usage_count DESC, success_rate DESC
        """
        
        rows = await db_manager.fetch_all(query)
        return [dict(row) for row in rows] if rows else []
    
    # ============================================================================
    # ANALYTICS AND REPORTING
    # ============================================================================
    
    async def get_generation_stats(self, user_id: str = None,
                                 days: int = 30) -> Dict[str, Any]:
        """Get image generation statistics"""
        if not user_id:
            user_id = await self.get_user_id()
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Total images generated
        total_query = """
            SELECT COUNT(*) as count FROM generated_images 
            WHERE user_id = $1 AND created_at >= $2
        """
        total_result = await db_manager.fetch_one(total_query, user_id, cutoff_date)
        total_images = total_result['count'] if total_result else 0
        
        # Most used content types
        content_query = """
            SELECT content_type, COUNT(*) as count
            FROM generated_images 
            WHERE user_id = $1 AND created_at >= $2
            GROUP BY content_type
            ORDER BY count DESC
        """
        content_rows = await db_manager.fetch_all(content_query, user_id, cutoff_date)
        content_types = [dict(row) for row in content_rows] if content_rows else []
        
        # Most used models
        model_query = """
            SELECT model_used, COUNT(*) as count
            FROM generated_images 
            WHERE user_id = $1 AND created_at >= $2
            GROUP BY model_used
            ORDER BY count DESC
        """
        model_rows = await db_manager.fetch_all(model_query, user_id, cutoff_date)
        models_used = [dict(row) for row in model_rows] if model_rows else []
        
        # Average generation time
        avg_query = """
            SELECT AVG(generation_time_seconds) as avg_time
            FROM generated_images 
            WHERE user_id = $1 AND created_at >= $2
        """
        avg_result = await db_manager.fetch_one(avg_query, user_id, cutoff_date)
        avg_time = float(avg_result['avg_time'] or 0) if avg_result else 0
        
        return {
            'total_images': total_images,
            'avg_generation_time': round(avg_time, 2),
            'content_types': content_types,
            'models_used': models_used,
            'period_days': days
        }
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def _extract_keywords(self, prompt: str) -> List[str]:
        """Extract keywords from a prompt for search indexing"""
        if not prompt:
            return []
        
        # Split by common delimiters
        words = re.split(r'[,\s]+', prompt.lower())
        
        # Filter out short words and common terms
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at',
                      'to', 'for', 'of', 'with', 'by', 'is', 'it', 'as'}
        keywords = [word.strip() for word in words
                   if len(word.strip()) > 2 and word.strip() not in stop_words]
        
        return keywords[:10]  # Limit to 10 keywords
    
    async def cleanup_old_images(self, days_to_keep: int = 90) -> int:
        """Clean up old generated images to manage storage"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # First count images to delete
        count_query = """
            SELECT COUNT(*) as count FROM generated_images 
            WHERE created_at < $1 
            AND (downloaded_at IS NULL OR downloaded_at < $1)
            AND download_count = 0
        """
        count_result = await db_manager.fetch_one(count_query, cutoff_date)
        count_to_delete = count_result['count'] if count_result else 0
        
        if count_to_delete > 0:
            # Delete old images
            delete_query = """
                DELETE FROM generated_images 
                WHERE created_at < $1 
                AND (downloaded_at IS NULL OR downloaded_at < $1)
                AND download_count = 0
            """
            await db_manager.execute(delete_query, cutoff_date)
            logger.info(f"Cleaned up {count_to_delete} old images")
        
        return count_to_delete
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health and image generation system status"""
        try:
            # Check table existence
            tables_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name IN ('generated_images', 'image_style_templates')
                AND table_schema = 'public'
            """
            tables = await db_manager.fetch_all(tables_query)
            table_names = [row['table_name'] for row in tables] if tables else []
            
            # Get recent activity
            recent_query = """
                SELECT COUNT(*) as count FROM generated_images 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """
            recent_result = await db_manager.fetch_one(recent_query)
            recent_images = recent_result['count'] if recent_result else 0
            
            # Get totals
            total_images_result = await db_manager.fetch_one(
                "SELECT COUNT(*) as count FROM generated_images"
            )
            total_images = total_images_result['count'] if total_images_result else 0
            
            total_templates_result = await db_manager.fetch_one(
                "SELECT COUNT(*) as count FROM image_style_templates"
            )
            total_templates = total_templates_result['count'] if total_templates_result else 0
            
            return {
                'healthy': len(table_names) == 2,
                'tables_exist': table_names,
                'recent_generations': recent_images,
                'total_images': total_images,
                'total_templates': total_templates,
                'database_accessible': True
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'database_accessible': False
            }
