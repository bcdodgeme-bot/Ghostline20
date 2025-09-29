# modules/integrations/image_generation/image_processor.py
"""
Image Processing and Format Conversion for Syntax Prime V2
Handles image format conversion, optimization, and download preparation

Key Features:
- Multiple format conversion (PNG, JPG, WebP)
- Image optimization for different use cases
- Resolution scaling and aspect ratio management
- File size optimization
- Download preparation with proper metadata
- Quality presets for different platforms
"""

import asyncio
import logging
import base64
import io
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageEnhance, ImageFilter
import os

logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    Handles image processing, format conversion, and optimization
    Provides multiple download formats and quality options
    """
    
    def __init__(self):
        # Quality presets for different use cases
        self.quality_presets = {
            'web_optimized': {'quality': 85, 'optimize': True},
            'high_quality': {'quality': 95, 'optimize': True},
            'print_ready': {'quality': 100, 'optimize': False},
            'social_media': {'quality': 90, 'optimize': True},
            'thumbnail': {'quality': 75, 'optimize': True}
        }
        
        # Resolution presets for different platforms
        self.resolution_presets = {
            'original': None,  # Keep original size
            'hd': (1920, 1080),
            'fhd': (1920, 1080),
            'square_lg': (1080, 1080),
            'square_md': (800, 800),
            'square_sm': (400, 400),
            'instagram_post': (1080, 1080),
            'instagram_story': (1080, 1920),
            'facebook_post': (1200, 630),
            'twitter_card': (1200, 675),
            'linkedin_post': (1200, 627),
            'blog_header': (1200, 630),
            'youtube_thumbnail': (1280, 720),
            'pinterest': (735, 1102)
        }
        
        # Format specifications
        self.format_specs = {
            'png': {
                'mime_type': 'image/png',
                'extension': 'png',
                'supports_transparency': True,
                'best_for': ['logos', 'graphics', 'screenshots'],
                'compression': 'lossless'
            },
            'jpg': {
                'mime_type': 'image/jpeg',
                'extension': 'jpg',
                'supports_transparency': False,
                'best_for': ['photos', 'complex images', 'web display'],
                'compression': 'lossy'
            },
            'jpeg': {
                'mime_type': 'image/jpeg',
                'extension': 'jpg',
                'supports_transparency': False,
                'best_for': ['photos', 'complex images', 'web display'],
                'compression': 'lossy'
            },
            'webp': {
                'mime_type': 'image/webp',
                'extension': 'webp',
                'supports_transparency': True,
                'best_for': ['web optimization', 'modern browsers', 'smaller files'],
                'compression': 'lossy/lossless'
            }
        }
    
    async def process_image(self, image_base64: str, target_format: str = 'png',
                          quality_preset: str = 'web_optimized',
                          resolution_preset: str = 'original',
                          custom_size: Tuple[int, int] = None) -> Dict[str, Any]:
        """
        Process an image with format conversion and optimization
        
        Args:
            image_base64: Base64 encoded image data
            target_format: Target format ('png', 'jpg', 'webp')
            quality_preset: Quality preset name
            resolution_preset: Resolution preset name
            custom_size: Custom (width, height) tuple
            
        Returns:
            Dict with processed image data and metadata
        """
        try:
            # Decode base64 image
            image_data = base64.b64decode(image_base64)
            original_image = Image.open(io.BytesIO(image_data))
            
            # Get original metadata
            original_size = original_image.size
            original_format = original_image.format or 'PNG'
            original_mode = original_image.mode
            
            logger.info(f"Processing image: {original_size[0]}x{original_size[1]} {original_format} ({original_mode})")
            
            # Process the image
            processed_image = await self._process_image_pipeline(
                original_image, target_format, quality_preset, 
                resolution_preset, custom_size
            )
            
            # Convert back to base64
            output_buffer = io.BytesIO()
            save_params = self._get_save_parameters(target_format, quality_preset)
            processed_image.save(output_buffer, **save_params)
            
            processed_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
            
            # Calculate file sizes
            original_size_bytes = len(image_data)
            processed_size_bytes = len(output_buffer.getvalue())
            compression_ratio = processed_size_bytes / original_size_bytes if original_size_bytes > 0 else 1.0
            
            return {
                'success': True,
                'processed_image_base64': processed_base64,
                'original_dimensions': original_size,
                'processed_dimensions': processed_image.size,
                'original_format': original_format,
                'processed_format': target_format.upper(),
                'original_size_bytes': original_size_bytes,
                'processed_size_bytes': processed_size_bytes,
                'compression_ratio': round(compression_ratio, 3),
                'quality_preset': quality_preset,
                'resolution_preset': resolution_preset,
                'format_specs': self.format_specs.get(target_format.lower(), {}),
                'metadata': {
                    'color_mode': processed_image.mode,
                    'has_transparency': processed_image.mode in ('RGBA', 'LA'),
                    'mime_type': self.format_specs.get(target_format.lower(), {}).get('mime_type', 'image/png')
                }
            }
            
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_format': 'unknown'
            }
    
    async def _process_image_pipeline(self, image: Image.Image, target_format: str,
                                    quality_preset: str, resolution_preset: str,
                                    custom_size: Tuple[int, int] = None) -> Image.Image:
        """Internal image processing pipeline"""
        
        processed_image = image.copy()
        
        # 1. Handle transparency for JPEG conversion
        if target_format.lower() in ('jpg', 'jpeg') and processed_image.mode in ('RGBA', 'LA'):
            # Create white background for JPEG
            background = Image.new('RGB', processed_image.size, (255, 255, 255))
            if processed_image.mode == 'RGBA':
                background.paste(processed_image, mask=processed_image.split()[-1])
            else:
                background.paste(processed_image)
            processed_image = background
        
        # 2. Resize if needed
        target_size = custom_size or self.resolution_presets.get(resolution_preset)
        if target_size:
            processed_image = self._smart_resize(processed_image, target_size)
        
        # 3. Apply quality optimizations
        processed_image = self._apply_quality_enhancements(processed_image, quality_preset)
        
        # 4. Ensure correct color mode for target format
        processed_image = self._ensure_correct_mode(processed_image, target_format)
        
        return processed_image
    
    def _smart_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Smart resize that maintains aspect ratio and quality"""
        original_width, original_height = image.size
        target_width, target_height = target_size
        
        # Calculate aspect ratios
        original_ratio = original_width / original_height
        target_ratio = target_width / target_height
        
        # Choose resize method based on size change
        if target_width * target_height > original_width * original_height:
            # Upscaling - use LANCZOS for quality
            resample = Image.Resampling.LANCZOS
        else:
            # Downscaling - use LANCZOS for quality
            resample = Image.Resampling.LANCZOS
        
        # Crop to fit if aspect ratios don't match
        if abs(original_ratio - target_ratio) > 0.01:  # Small tolerance for floating point
            # Crop to target aspect ratio first
            if original_ratio > target_ratio:
                # Original is wider - crop width
                new_width = int(original_height * target_ratio)
                left = (original_width - new_width) // 2
                image = image.crop((left, 0, left + new_width, original_height))
            else:
                # Original is taller - crop height
                new_height = int(original_width / target_ratio)
                top = (original_height - new_height) // 2
                image = image.crop((0, top, original_width, top + new_height))
        
        # Resize to target dimensions
        return image.resize(target_size, resample)
    
    def _apply_quality_enhancements(self, image: Image.Image, quality_preset: str) -> Image.Image:
        """Apply quality enhancements based on preset"""
        
        if quality_preset == 'high_quality':
            # Slight sharpening for high quality
            image = image.filter(ImageFilter.UnsharpMask(radius=0.5, percent=120, threshold=3))
        
        elif quality_preset == 'social_media':
            # Enhance contrast slightly for social media
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.1)
            
            # Slight saturation boost
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(1.05)
        
        elif quality_preset == 'print_ready':
            # Minimal processing for print
            pass
        
        elif quality_preset == 'thumbnail':
            # Slight sharpening for small sizes
            image = image.filter(ImageFilter.UnsharpMask(radius=0.3, percent=100, threshold=2))
        
        return image
    
    def _ensure_correct_mode(self, image: Image.Image, target_format: str) -> Image.Image:
        """Ensure image has correct color mode for target format"""
        
        format_modes = {
            'png': ['RGB', 'RGBA', 'L', 'LA'],
            'jpg': ['RGB', 'L'],
            'jpeg': ['RGB', 'L'],
            'webp': ['RGB', 'RGBA', 'L']
        }
        
        target_modes = format_modes.get(target_format.lower(), ['RGB'])
        
        if image.mode not in target_modes:
            if 'RGB' in target_modes:
                if image.mode == 'RGBA':
                    # Create white background
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    return background
                else:
                    return image.convert('RGB')
            elif 'RGBA' in target_modes and image.mode == 'RGB':
                return image.convert('RGBA')
        
        return image
    
    def _get_save_parameters(self, target_format: str, quality_preset: str) -> Dict[str, Any]:
        """Get save parameters for PIL Image.save()"""
        
        quality_settings = self.quality_presets.get(quality_preset, self.quality_presets['web_optimized'])
        
        params = {'format': target_format.upper()}
        
        if target_format.lower() in ('jpg', 'jpeg'):
            params.update({
                'quality': quality_settings['quality'],
                'optimize': quality_settings['optimize'],
                'progressive': True  # Progressive JPEG for better loading
            })
        
        elif target_format.lower() == 'png':
            params.update({
                'optimize': quality_settings['optimize'],
                'compress_level': 6  # Good balance of speed vs compression
            })
        
        elif target_format.lower() == 'webp':
            params.update({
                'quality': quality_settings['quality'],
                'method': 6,  # Better compression
                'lossless': quality_preset == 'print_ready'
            })
        
        return params
    
    async def create_multiple_formats(self, image_base64: str,
                                    formats: List[str] = None,
                                    quality_preset: str = 'web_optimized') -> Dict[str, Any]:
        """
        Create multiple format versions of an image
        
        Args:
            image_base64: Base64 encoded source image
            formats: List of target formats ['png', 'jpg', 'webp']
            quality_preset: Quality preset to use
            
        Returns:
            Dict with all format versions and metadata
        """
        if formats is None:
            formats = ['png', 'jpg', 'webp']
        
        results = {}
        
        for format_name in formats:
            if format_name.lower() in self.format_specs:
                logger.info(f"Creating {format_name.upper()} version...")
                
                result = await self.process_image(
                    image_base64, format_name, quality_preset
                )
                
                if result['success']:
                    results[format_name] = {
                        'image_base64': result['processed_image_base64'],
                        'file_size_bytes': result['processed_size_bytes'],
                        'dimensions': result['processed_dimensions'],
                        'mime_type': result['metadata']['mime_type'],
                        'compression_ratio': result['compression_ratio']
                    }
                else:
                    results[format_name] = {'error': result['error']}
        
        return {
            'formats_created': list(results.keys()),
            'total_formats': len(results),
            'results': results,
            'quality_preset': quality_preset
        }
    
    async def create_social_media_pack(self, image_base64: str) -> Dict[str, Any]:
        """
        Create a complete social media size pack
        
        Args:
            image_base64: Base64 encoded source image
            
        Returns:
            Dict with all social media format versions
        """
        social_sizes = {
            'instagram_post': (1080, 1080),
            'instagram_story': (1080, 1920),
            'facebook_post': (1200, 630),
            'twitter_card': (1200, 675),
            'linkedin_post': (1200, 627)
        }
        
        results = {}
        
        for size_name, dimensions in social_sizes.items():
            logger.info(f"Creating {size_name} version ({dimensions[0]}x{dimensions[1]})...")
            
            result = await self.process_image(
                image_base64, 
                target_format='jpg',  # JPEG for social media efficiency
                quality_preset='social_media',
                custom_size=dimensions
            )
            
            if result['success']:
                results[size_name] = {
                    'image_base64': result['processed_image_base64'],
                    'dimensions': result['processed_dimensions'],
                    'file_size_bytes': result['processed_size_bytes'],
                    'platform': size_name.replace('_', ' ').title()
                }
            else:
                results[size_name] = {'error': result['error']}
        
        return {
            'social_media_pack': results,
            'platforms_created': len([r for r in results.values() if 'error' not in r]),
            'total_platforms': len(social_sizes)
        }
    
    def get_format_recommendations(self, use_case: str) -> Dict[str, Any]:
        """
        Get format recommendations based on use case
        
        Args:
            use_case: 'web', 'social', 'print', 'email', 'blog'
            
        Returns:
            Recommended formats and settings
        """
        recommendations = {
            'web': {
                'primary_format': 'webp',
                'fallback_format': 'jpg',
                'quality_preset': 'web_optimized',
                'reasoning': 'WebP offers best compression for modern browsers, JPEG fallback for compatibility'
            },
            'social': {
                'primary_format': 'jpg',
                'fallback_format': 'png',
                'quality_preset': 'social_media',
                'reasoning': 'JPEG optimized for social media algorithms and fast loading'
            },
            'print': {
                'primary_format': 'png',
                'fallback_format': 'jpg',
                'quality_preset': 'print_ready',
                'reasoning': 'PNG preserves quality for print, high-quality JPEG if file size matters'
            },
            'email': {
                'primary_format': 'jpg',
                'fallback_format': 'png',
                'quality_preset': 'web_optimized',
                'reasoning': 'JPEG for smaller email attachments, broad email client compatibility'
            },
            'blog': {
                'primary_format': 'webp',
                'fallback_format': 'jpg',
                'quality_preset': 'web_optimized',
                'reasoning': 'WebP for page speed, JPEG fallback for older browsers'
            }
        }
        
        return recommendations.get(use_case, recommendations['web'])
    
    def get_available_presets(self) -> Dict[str, Any]:
        """Get all available presets and their descriptions"""
        return {
            'quality_presets': {
                name: {
                    'settings': settings,
                    'description': self._describe_quality_preset(name)
                }
                for name, settings in self.quality_presets.items()
            },
            'resolution_presets': {
                name: {
                    'dimensions': dimensions,
                    'description': self._describe_resolution_preset(name)
                }
                for name, dimensions in self.resolution_presets.items()
            },
            'supported_formats': self.format_specs
        }
    
    def _describe_quality_preset(self, preset_name: str) -> str:
        """Get description for quality preset"""
        descriptions = {
            'web_optimized': 'Balanced quality and file size for web use',
            'high_quality': 'Maximum quality with minimal compression',
            'print_ready': 'Highest quality for print reproduction',
            'social_media': 'Optimized for social media platforms',
            'thumbnail': 'Optimized for small preview images'
        }
        return descriptions.get(preset_name, 'Custom quality settings')
    
    def _describe_resolution_preset(self, preset_name: str) -> str:
        """Get description for resolution preset"""
        descriptions = {
            'original': 'Keep original image dimensions',
            'hd': 'Standard HD resolution (1920x1080)',
            'square_lg': 'Large square format (1080x1080)',
            'instagram_post': 'Instagram post format (1080x1080)',
            'instagram_story': 'Instagram story format (1080x1920)',
            'facebook_post': 'Facebook post format (1200x630)',
            'twitter_card': 'Twitter card format (1200x675)',
            'blog_header': 'Blog header format (1200x630)',
            'youtube_thumbnail': 'YouTube thumbnail (1280x720)'
        }
        return descriptions.get(preset_name, f'Custom resolution: {self.resolution_presets.get(preset_name, "Unknown")}')

# Test function for development
async def test_image_processor():
    """Test the image processor with sample operations"""
    processor = ImageProcessor()
    
    print("🖼️ TESTING IMAGE PROCESSOR")
    print("=" * 40)
    
    # This would require a sample base64 image for testing
    print("✅ Image processor initialized")
    print(f"✅ Supported formats: {list(processor.format_specs.keys())}")
    print(f"✅ Quality presets: {list(processor.quality_presets.keys())}")
    print(f"✅ Resolution presets: {len(processor.resolution_presets)} available")
    
    # Test format recommendations
    recommendations = processor.get_format_recommendations('social')
    print(f"✅ Social media recommendation: {recommendations['primary_format']}")

if __name__ == "__main__":
    asyncio.run(test_image_processor())