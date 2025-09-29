# modules/integrations/image_generation/__init__.py
"""
Image Generation Integration Module for Syntax Prime V2
AI-powered image generation with inline display and download functionality

Module Structure:
- replicate_client.py: Replicate API integration with smart model selection
- database_manager.py: Image storage, retrieval, and analytics
- router.py: FastAPI endpoints for chat integration
- prompt_optimizer.py: Content intelligence-enhanced prompt optimization (future)
- image_processor.py: Format conversion and download functionality (future)

Key Features:
- Inline image display (base64) - no external URLs to follow
- Smart model selection eliminates confusing Replicate interface
- Download functionality with multiple formats
- Style templates for consistent branding
- Content intelligence integration (RSS/Trends/Scraper context)
- Complete chat command integration

Workflow:
1. User types "image create [description]" in chat
2. System enhances prompt using content intelligence
3. Replicate API generates high-quality image
4. Image displays inline immediately (base64)
5. Download buttons provide format options
6. Analytics track usage and optimize performance
"""

import os
import logging
from typing import Dict, Any, Optional

# Import core components
from .replicate_client import ReplicateImageClient
from .database_manager import ImageDatabase
from .router import router
from typing import List, Dict, Any

# Import health check functions
try:
    from .integration_info import get_integration_info, check_module_health
except ImportError:
    # Will be available after creating integration_info.py
    get_integration_info = None
    check_module_health = None

# Module metadata
__version__ = '1.0.0'
__author__ = 'Syntax Prime V2'
__description__ = 'AI-powered image generation with inline display and download functionality'

# Module configuration
MODULE_NAME = 'image_generation'
INTEGRATION_TYPE = 'chat_command'
SUPPORTED_COMMANDS = [
    'image create', 'image generate', 'image blog', 'image social', 
    'image marketing', 'image style', 'image history', 'image download'
]

# Public API - what other modules can import
__all__ = [
    'ReplicateImageClient',
    'ImageDatabase', 
    'router',
    'get_integration_info',
    'check_module_health',
    'generate_image_for_chat',
    'get_image_history_for_chat'
]

# ============================================================================
# CHAT INTEGRATION HELPERS
# ============================================================================

async def generate_image_for_chat(prompt: str, content_type: str = "general", 
                                user_id: str = None, style: str = None) -> Dict[str, Any]:
    """
    Helper function for chat integration
    Generates an image and returns data suitable for chat display
    
    Args:
        prompt: User's text description
        content_type: Type of content ('blog', 'social', 'marketing', 'general')
        user_id: User ID (will auto-detect if not provided)
        style: Optional style template name
        
    Returns:
        Dict with success status, image data, and metadata
    """
    try:
        # Initialize components
        client = ReplicateImageClient()
        db = ImageDatabase()
        
        # Get user ID if not provided
        if not user_id:
            user_id = await db.get_user_id()
        
        # Get style template if specified
        style_template = None
        if style:
            template_obj = await db.get_style_template(name=style)
            if template_obj:
                style_template = {
                    'style_prompt': template_obj.style_prompt,
                    'color_scheme': template_obj.color_scheme
                }
        
        # Generate the image
        result = await client.generate_image(
            prompt=prompt,
            content_type=content_type,
            style_template=style_template
        )
        
        if result['success']:
            # Save to database
            try:
                result['style_applied'] = style or ''
                image_id = await db.save_generated_image(result, user_id)
                result['image_id'] = image_id
            except Exception as e:
                logging.warning(f"Failed to save image to database: {e}")
                # Don't fail the generation if save fails
        
        # Close client session
        await client.close_session()
        
        return result
        
    except Exception as e:
        logging.error(f"Chat image generation failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'original_prompt': prompt
        }

async def get_image_history_for_chat(user_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Helper function to get recent images for chat display
    
    Args:
        user_id: User ID (will auto-detect if not provided)
        limit: Number of recent images to return
        
    Returns:
        List of recent images with essential data
    """
    try:
        db = ImageDatabase()
        
        if not user_id:
            user_id = await db.get_user_id()
        
        images = await db.get_recent_images(user_id, limit)
        
        # Format for chat display
        formatted_images = []
        for img in images:
            formatted_images.append({
                'id': str(img['id']),
                'prompt': img['original_prompt'][:100] + ('...' if len(img['original_prompt']) > 100 else ''),
                'content_type': img['content_type'],
                'model_used': img['model_used'],
                'created_at': img['created_at'].strftime('%Y-%m-%d %H:%M'),
                'download_count': img['download_count']
            })
        
        return formatted_images
        
    except Exception as e:
        logging.error(f"Failed to get image history for chat: {e}")
        return []

# ============================================================================
# MODULE HEALTH AND INFO
# ============================================================================

def check_module_health() -> Dict[str, Any]:
    """Check if image generation module is properly configured"""
    required_vars = [
        'DATABASE_URL',
        'REPLICATE_API_TOKEN'
    ]
    
    optional_vars = [
        'REPLICATE_MODEL_PREFERENCE',
        'IMAGE_GENERATION_TIMEOUT'
    ]
    
    status = {
        'healthy': True,
        'missing_vars': [],
        'configured_vars': [],
        'optional_missing': []
    }
    
    # Check required environment variables
    for var in required_vars:
        if os.getenv(var):
            status['configured_vars'].append(var)
        else:
            status['missing_vars'].append(var)
            status['healthy'] = False
    
    # Check optional variables
    for var in optional_vars:
        if os.getenv(var):
            status['configured_vars'].append(var)
        else:
            status['optional_missing'].append(var)
    
    # Test component initialization
    try:
        client = ReplicateImageClient()
        status['replicate_client'] = 'initialized'
    except Exception as e:
        status['replicate_client'] = f'failed: {str(e)}'
        status['healthy'] = False
    
    try:
        db = ImageDatabase()
        status['database_manager'] = 'initialized'
    except Exception as e:
        status['database_manager'] = f'failed: {str(e)}'
        status['healthy'] = False
    
    return status

def get_integration_info() -> Dict[str, Any]:
    """Get comprehensive information about the image generation module"""
    health_status = check_module_health()
    
    return {
        'module': MODULE_NAME,
        'version': __version__,
        'description': __description__,
        'integration_type': INTEGRATION_TYPE,
        'health_status': health_status,
        
        'chat_commands': {
            'image create [prompt]': 'Generate image from text description',
            'image blog [topic]': 'Create blog featured image',
            'image social [content]': 'Generate social media graphic',
            'image marketing [campaign]': 'Create marketing visual',
            'image style [style_name] [prompt]': 'Generate with specific style',
            'image history': 'Show recent generated images',
            'image download [image_id] [format]': 'Download image in format'
        },
        
        'features': [
            'Inline image display (base64) - no external URLs',
            'Smart model selection eliminates confusion',
            'Prompt enhancement with content intelligence',
            'Multiple format downloads (PNG, JPG, WebP)',
            'Style templates for consistent branding',
            'Usage analytics and optimization',
            'Integration with RSS/Trends/Scraper context',
            'Background processing for fast chat responses'
        ],
        
        'models_supported': [
            'Stable Diffusion XL (high quality)',
            'SDXL Lightning (fast generation)',
            'Realistic Vision (artistic/illustration)',
            'Smart fallbacks and selection'
        ],
        
        'endpoints': {
            'generate': '/integrations/image-generation/generate',
            'quick_generate': '/integrations/image-generation/quick-generate/{prompt}',
            'chat_generate': '/integrations/image-generation/chat-generate',
            'history': '/integrations/image-generation/history',
            'download': '/integrations/image-generation/download/{image_id}',
            'styles': '/integrations/image-generation/styles',
            'health': '/integrations/image-generation/health'
        },
        
        'storage': {
            'table': 'generated_images',
            'style_templates': 'image_style_templates',
            'retention': 'configurable with cleanup utilities',
            'indexing': 'keyword search and content type filtering'
        },
        
        'configuration': {
            'required_env_vars': [
                'DATABASE_URL (PostgreSQL connection)',
                'REPLICATE_API_TOKEN (Replicate API access)'
            ],
            'optional_env_vars': [
                'REPLICATE_MODEL_PREFERENCE (default model override)',
                'IMAGE_GENERATION_TIMEOUT (generation timeout seconds)'
            ],
            'database_requirements': [
                'generated_images table',
                'image_style_templates table',
                'PostgreSQL with JSONB support'
            ]
        },
        
        'workflow': [
            '1. User types image command in chat',
            '2. AI router detects image generation request',
            '3. Prompt enhanced with content intelligence',
            '4. Replicate API generates high-quality image',
            '5. Image displays inline immediately (base64)',
            '6. Download buttons provide format options',
            '7. Analytics track usage and optimize performance'
        ],
        
        'integration_points': [
            'Chat interface (inline display)',
            'AI router (command detection)',
            'Content intelligence (RSS/Trends/Scraper)',
            'User system (authentication)',
            'Database (persistent storage)',
            'File download system'
        ]
    }

# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_available_content_types() -> List[str]:
    """Get list of supported content types"""
    return ['general', 'blog', 'social', 'marketing', 'illustration', 'artistic', 'logo', 'professional']

def get_supported_formats() -> List[str]:
    """Get list of supported download formats"""
    return ['png', 'jpg', 'jpeg', 'webp']

def get_common_resolutions() -> Dict[str, tuple]:
    """Get common resolution presets"""
    return {
        'square': (1024, 1024),
        'landscape': (1344, 768),
        'portrait': (768, 1344),
        'social_square': (1080, 1080),
        'social_story': (1080, 1920),
        'blog_header': (1200, 630),
        'twitter_card': (1200, 675)
    }

# Module initialization logging
logging.getLogger(__name__).info(f"🎨 Image Generation module v{__version__} initialized")
