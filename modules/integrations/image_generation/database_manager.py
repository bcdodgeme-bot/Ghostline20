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
"""

import asyncio
import asyncpg
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)

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
    """
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL must be provided or set as environment variable")
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    # ============================================================================
    # USER MANAGEMENT
    # ============================================================================
    
    async def get_user_id(self) -> Optional[str]:
        """Get the first user ID (since this is a personal AI system)"""
        conn = await self.get_connection()
        try:
            user = await conn.fetchrow("SELECT id FROM users ORDER BY created_at LIMIT 1")
            return str(user['id']) if user else None
        finally:
            await conn.close()
    
    # ============================================================================
    # IMAGE GENERATION MANAGEMENT
    # ============================================================================
    
    async def save_generated_image(self, generation_result: Dict[str, Any],
                                 user_id: str = None) -> str:
        """
        Save a generated image to the database
        
        Args:
            generation_result: Result from ReplicateImageClient.generate_image()
            user_id: Optional user ID (will auto-detect if not provided)
            
        Returns:
            UUID of the saved image record
        """
        if not user_id:
            user_id = await self.get_user_id()
        
        conn = await self.get_connection()
        try:
            # Extract data from generation result
            image_data = {
                'user_id': user_id,
                'original_prompt': generation_result.get('original_prompt', ''),
                'enhanced_prompt': generation_result.get('enhanced_prompt', ''),
                'image_url': generation_result.get('image_url', ''),
                'image_data_base64': generation_result.get('image_base64', ''),
                'model_used': generation_result.get('model_used', ''),
                'generation_time_seconds': generation_result.get('generation_time_seconds', 0),
                'style_applied': generation_result.get('style_applied', ''),
                'content_type': generation_result.get('content_type', 'general'),
                'resolution': generation_result.get('resolution', '1024x1024'),
                'file_format': 'png',  # Default format
                'content_context': json.dumps(generation_result.get('metadata', {})),
                'related_keywords': json.dumps(self._extract_keywords(generation_result.get('original_prompt', '')))
            }
            
            # Calculate file size estimate (base64 is ~33% larger than binary)
            if image_data['image_data_base64']:
                estimated_size = int(len(image_data['image_data_base64']) * 0.75)
                image_data['file_size_bytes'] = estimated_size
            
            # Insert the record
            image_id = await conn.fetchval('''
                INSERT INTO generated_images 
                (user_id, original_prompt, enhanced_prompt, image_url, image_data_base64,
                 model_used, generation_time_seconds, style_applied, content_type,
                 resolution, file_format, file_size_bytes, content_context, related_keywords)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
            ''', 
            image_data['user_id'], image_data['original_prompt'], image_data['enhanced_prompt'],
            image_data['image_url'], image_data['image_data_base64'], image_data['model_used'],
            image_data['generation_time_seconds'], image_data['style_applied'], 
            image_data['content_type'], image_data['resolution'], image_data['file_format'],
            image_data['file_size_bytes'], image_data['content_context'], 
            image_data['related_keywords']
            )
            
            logger.info(f"Saved generated image with ID: {image_id}")
            return str(image_id)
            
        except Exception as e:
            logger.error(f"Failed to save generated image: {e}")
            raise
        finally:
            await conn.close()
    
    async def get_image_by_id(self, image_id: str) -> Optional[GeneratedImage]:
        """Get a specific generated image by ID"""
        conn = await self.get_connection()
        try:
            row = await conn.fetchrow('''
                SELECT id, user_id, original_prompt, enhanced_prompt, image_url,
                       image_data_base64, model_used, generation_time_seconds,
                       style_applied, content_type, resolution, file_format,
                       download_count, created_at
                FROM generated_images 
                WHERE id = $1
            ''', image_id)
            
            if row:
                return GeneratedImage(
                    id=str(row['id']),
                    user_id=str(row['user_id']),
                    original_prompt=row['original_prompt'],
                    enhanced_prompt=row['enhanced_prompt'],
                    image_url=row['image_url'],
                    image_base64=row['image_data_base64'],
                    model_used=row['model_used'],
                    generation_time_seconds=float(row['generation_time_seconds']),
                    style_applied=row['style_applied'],
                    content_type=row['content_type'],
                    resolution=row['resolution'],
                    file_format=row['file_format'],
                    download_count=row['download_count'],
                    created_at=row['created_at']
                )
            return None
            
        finally:
            await conn.close()
    
    async def get_recent_images(self, user_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent generated images for a user"""
        if not user_id:
            user_id = await self.get_user_id()
        
        conn = await self.get_connection()
        try:
            rows = await conn.fetch('''
                SELECT id, original_prompt, enhanced_prompt, content_type,
                       model_used, generation_time_seconds, resolution,
                       download_count, created_at
                FROM generated_images 
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    async def search_images_by_keyword(self, keywords: List[str], 
                                     user_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search generated images by keywords in prompts"""
        if not user_id:
            user_id = await self.get_user_id()
        
        conn = await self.get_connection()
        try:
            # Build search query for keywords in prompts
            search_terms = []
            for keyword in keywords:
                search_terms.append(f"%{keyword.lower()}%")
            
            query = '''
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
            '''
            
            rows = await conn.fetch(query, user_id, search_terms, 
                                  json.dumps(keywords), limit)
            
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    async def increment_download_count(self, image_id: str) -> bool:
        """Increment download count for an image"""
        conn = await self.get_connection()
        try:
            # Update download count and timestamp
            result = await conn.execute('''
                UPDATE generated_images 
                SET download_count = download_count + 1,
                    downloaded_at = NOW()
                WHERE id = $1
            ''', image_id)
            
            return result == "UPDATE 1"
            
        finally:
            await conn.close()
    
    # ============================================================================
    # STYLE TEMPLATE MANAGEMENT
    # ============================================================================
    
    async def get_style_template(self, name: str = None, 
                               business_area: str = None) -> Optional[StyleTemplate]:
        """Get a style template by name or business area"""
        conn = await self.get_connection()
        try:
            if name:
                row = await conn.fetchrow('''
                    SELECT id, name, business_area, style_prompt, color_scheme,
                           typical_elements, usage_count, success_rate
                    FROM image_style_templates 
                    WHERE name = $1
                ''', name)
            elif business_area:
                row = await conn.fetchrow('''
                    SELECT id, name, business_area, style_prompt, color_scheme,
                           typical_elements, usage_count, success_rate
                    FROM image_style_templates 
                    WHERE business_area = $1
                    ORDER BY usage_count DESC
                    LIMIT 1
                ''', business_area)
            else:
                return None
            
            if row:
                return StyleTemplate(
                    id=str(row['id']),
                    name=row['name'],
                    business_area=row['business_area'],
                    style_prompt=row['style_prompt'],
                    color_scheme=json.loads(row['color_scheme']) if row['color_scheme'] else {},
                    typical_elements=json.loads(row['typical_elements']) if row['typical_elements'] else [],
                    usage_count=row['usage_count'],
                    success_rate=float(row['success_rate'])
                )
            return None
            
        finally:
            await conn.close()
    
    async def update_style_usage(self, template_name: str, success: bool = True) -> bool:
        """Update style template usage statistics"""
        conn = await self.get_connection()
        try:
            # Increment usage count and update success rate
            await conn.execute('''
                UPDATE image_style_templates 
                SET usage_count = usage_count + 1,
                    success_rate = CASE 
                        WHEN $2 THEN LEAST(1.0, success_rate + 0.1)
                        ELSE GREATEST(0.0, success_rate - 0.1)
                    END
                WHERE name = $1
            ''', template_name, success)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update style usage: {e}")
            return False
        finally:
            await conn.close()
    
    async def get_available_styles(self) -> List[Dict[str, Any]]:
        """Get all available style templates"""
        conn = await self.get_connection()
        try:
            rows = await conn.fetch('''
                SELECT name, business_area, style_prompt, usage_count, success_rate
                FROM image_style_templates 
                ORDER BY usage_count DESC, success_rate DESC
            ''')
            
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    # ============================================================================
    # ANALYTICS AND REPORTING
    # ============================================================================
    
    async def get_generation_stats(self, user_id: str = None, 
                                 days: int = 30) -> Dict[str, Any]:
        """Get image generation statistics"""
        if not user_id:
            user_id = await self.get_user_id()
        
        conn = await self.get_connection()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Total images generated
            total_images = await conn.fetchval('''
                SELECT COUNT(*) FROM generated_images 
                WHERE user_id = $1 AND created_at >= $2
            ''', user_id, cutoff_date)
            
            # Most used content types
            content_types = await conn.fetch('''
                SELECT content_type, COUNT(*) as count
                FROM generated_images 
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY content_type
                ORDER BY count DESC
            ''', user_id, cutoff_date)
            
            # Most used models
            models = await conn.fetch('''
                SELECT model_used, COUNT(*) as count
                FROM generated_images 
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY model_used
                ORDER BY count DESC
            ''', user_id, cutoff_date)
            
            # Average generation time
            avg_time = await conn.fetchval('''
                SELECT AVG(generation_time_seconds)
                FROM generated_images 
                WHERE user_id = $1 AND created_at >= $2
            ''', user_id, cutoff_date)
            
            return {
                'total_images': total_images,
                'avg_generation_time': round(float(avg_time or 0), 2),
                'content_types': [dict(row) for row in content_types],
                'models_used': [dict(row) for row in models],
                'period_days': days
            }
            
        finally:
            await conn.close()
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def _extract_keywords(self, prompt: str) -> List[str]:
        """Extract keywords from a prompt for search indexing"""
        if not prompt:
            return []
        
        # Simple keyword extraction - split by common delimiters
        import re
        words = re.split(r'[,\s]+', prompt.lower())
        
        # Filter out short words and common terms
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        keywords = [word.strip() for word in words 
                   if len(word.strip()) > 2 and word.strip() not in stop_words]
        
        return keywords[:10]  # Limit to 10 keywords
    
    async def cleanup_old_images(self, days_to_keep: int = 90) -> int:
        """Clean up old generated images to manage storage"""
        conn = await self.get_connection()
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Only delete images that haven't been downloaded recently
            deleted_count = await conn.fetchval('''
                DELETE FROM generated_images 
                WHERE created_at < $1 
                AND (downloaded_at IS NULL OR downloaded_at < $1)
                AND download_count = 0
                RETURNING (SELECT COUNT(*) FROM generated_images 
                          WHERE created_at < $1 
                          AND (downloaded_at IS NULL OR downloaded_at < $1)
                          AND download_count = 0)
            ''', cutoff_date)
            
            logger.info(f"Cleaned up {deleted_count or 0} old images")
            return deleted_count or 0
            
        finally:
            await conn.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health and image generation system status"""
        conn = await self.get_connection()
        try:
            # Check table existence
            tables = await conn.fetch('''
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name IN ('generated_images', 'image_style_templates')
                AND table_schema = 'public'
            ''')
            
            # Get recent activity
            recent_images = await conn.fetchval('''
                SELECT COUNT(*) FROM generated_images 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            ''')
            
            total_images = await conn.fetchval('SELECT COUNT(*) FROM generated_images')
            total_templates = await conn.fetchval('SELECT COUNT(*) FROM image_style_templates')
            
            return {
                'healthy': len(tables) == 2,
                'tables_exist': [row['table_name'] for row in tables],
                'recent_generations': recent_images,
                'total_images': total_images,
                'total_templates': total_templates,
                'database_accessible': True
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'database_accessible': False
            }
        finally:
            await conn.close()

# Test function for development
async def test_image_database():
    """Test the image database functionality"""
    db = ImageDatabase()
    
    print("🧪 TESTING IMAGE DATABASE")
    print("=" * 40)
    
    # Test health check
    health = await db.health_check()
    print(f"Database Health: {'✅' if health['healthy'] else '❌'}")
    print(f"Total Images: {health.get('total_images', 0)}")
    print(f"Total Templates: {health.get('total_templates', 0)}")
    
    # Test getting user ID
    user_id = await db.get_user_id()
    print(f"User ID: {user_id}")
    
    if user_id:
        # Test getting recent images
        recent = await db.get_recent_images(user_id, limit=5)
        print(f"Recent Images: {len(recent)}")
        
        # Test getting available styles
        styles = await db.get_available_styles()
        print(f"Available Styles: {len(styles)}")
        for style in styles[:3]:  # Show first 3
            print(f"  - {style['name']} ({style['usage_count']} uses)")
        
        # Test generation stats
        stats = await db.get_generation_stats(user_id)
        print(f"Generation Stats: {stats['total_images']} images in last 30 days")

if __name__ == "__main__":
    asyncio.run(test_image_database())