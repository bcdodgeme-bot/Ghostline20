# modules/integrations/image_generation/openrouter_image_client.py
"""
OpenRouter Image Generation Client for Syntax Prime V2
Uses Gemini 3 Pro Image Preview (Nano Banana Pro) via OpenRouter API

Key Features:
- Uses existing OpenRouter API key (no new credentials needed)
- Gemini 3 Pro's industry-leading text rendering in images
- Multiple aspect ratios for different content types
- Direct base64 response (no polling required)
- Rate limiting and error handling

FIXED: 2025-12-23 - Handle dict response format from Gemini API
"""

import os
import aiohttp
import asyncio
import logging
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class OpenRouterImageClient:
    """
    OpenRouter API client for Gemini 3 Pro image generation
    Drop-in replacement for ReplicateImageClient with same interface
    """
    
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
        self.base_url = "https://openrouter.ai/api/v1"
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=240)  # 2 min for image gen
        
        # Model configuration
        self.default_model = "google/gemini-3-pro-image-preview"
        self.fallback_model = "google/gemini-2.5-flash-image-preview"
        
        # Content type to aspect ratio mapping
        self.aspect_ratio_map = {
            'blog': '3:2',           # 1248x832 - landscape header
            'social': '1:1',         # 1024x1024 - square posts
            'marketing': '16:9',     # 1344x768 - wide format
            'professional': '3:2',   # 1248x832 - landscape
            'illustration': '1:1',   # 1024x1024 - square
            'artistic': '4:3',       # 1184x864 - classic
            'story': '9:16',         # 768x1344 - vertical stories
            'portrait': '3:4',       # 864x1184 - portrait
            'general': '1:1'         # 1024x1024 - default square
        }
        
        # Rate limiting
        self._last_request_time: float = 0
        self._min_request_interval = 1.0  # 1 second between requests
        
        # App identification for OpenRouter leaderboards
        self.app_name = os.getenv('APP_NAME', 'Syntax Prime V2')
        self.app_url = os.getenv('APP_URL', '')
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create reusable HTTP session"""
        if self._session is None or self._session.closed:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': self.app_url,
                'X-Title': self.app_name
            }
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=self._timeout
            )
        return self._session
    
    async def close_session(self) -> None:
        """Close HTTP session - call on shutdown"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("OpenRouterImageClient session closed")
    
    async def _rate_limit(self) -> None:
        """Ensure we don't hit rate limits"""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    def _get_aspect_ratio(self, content_type: str, width: int = None, height: int = None) -> str:
        """Determine aspect ratio from content type or dimensions"""
        # If explicit dimensions provided, calculate closest aspect ratio
        if width and height:
            ratio = width / height
            if ratio > 1.7:
                return '16:9'
            elif ratio > 1.3:
                return '3:2'
            elif ratio > 1.1:
                return '4:3'
            elif ratio > 0.9:
                return '1:1'
            elif ratio > 0.7:
                return '3:4'
            else:
                return '9:16'
        
        return self.aspect_ratio_map.get(content_type.lower(), '1:1')
    
    def enhance_prompt(self, original_prompt: str, content_type: str = 'general',
                      style_template: Optional[Dict] = None) -> str:
        """
        Enhance the user's prompt for better image generation
        
        Args:
            original_prompt: User's original prompt
            content_type: Type of content being created
            style_template: Optional style template from database
            
        Returns:
            Enhanced prompt string
        """
        enhanced = original_prompt
        
        # Add style elements from template if provided
        if style_template and 'style_prompt' in style_template:
            enhanced = f"{enhanced}, {style_template['style_prompt']}"
        
        # Add content-type specific enhancements
        content_enhancements = {
            'blog': ', professional blog header, clean composition, text-safe areas, high quality',
            'social': ', eye-catching, vibrant colors, social media optimized, engaging',
            'marketing': ', professional marketing design, polished, conversion-focused',
            'illustration': ', artistic illustration, creative, detailed linework',
            'professional': ', corporate, clean, trustworthy aesthetic',
            'artistic': ', artistic interpretation, creative composition, expressive'
        }
        
        if content_type.lower() in content_enhancements:
            enhanced += content_enhancements[content_type.lower()]
        
        # Always add quality modifiers
        enhanced += ', high quality, detailed, sharp focus'
        
        # Remove duplicate phrases
        parts = enhanced.split(', ')
        seen = set()
        unique_parts = []
        for part in parts:
            part_lower = part.lower().strip()
            if part_lower and part_lower not in seen:
                seen.add(part_lower)
                unique_parts.append(part.strip())
        
        return ', '.join(unique_parts)
    
    async def generate_image(self, prompt: str, content_type: str = 'general',
                           width: int = None, height: int = None,
                           style_template: Optional[Dict] = None,
                           speed_priority: bool = False) -> Dict[str, Any]:
        """
        Generate an image using OpenRouter's Gemini 3 Pro Image API
        
        Args:
            prompt: Text description of desired image
            content_type: Type of content ('blog', 'social', 'marketing', etc.)
            width: Optional width hint (used for aspect ratio calculation)
            height: Optional height hint (used for aspect ratio calculation)
            style_template: Optional style template from database
            speed_priority: If True, use faster model (Gemini 2.5 Flash)
            
        Returns:
            Dict with generation results, image data, and metadata
        """
        await self._rate_limit()
        start_time = time.time()
        
        # Select model
        model = self.fallback_model if speed_priority else self.default_model
        
        # Enhance the prompt
        enhanced_prompt = self.enhance_prompt(prompt, content_type, style_template)
        
        # Determine aspect ratio
        aspect_ratio = self._get_aspect_ratio(content_type, width, height)
        
        logger.info(f"Generating image with {model}, aspect ratio: {aspect_ratio}")
        logger.info(f"Prompt: {enhanced_prompt[:100]}...")
        
        try:
            session = await self._get_session()
            
            # Build request payload
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Generate an image: {enhanced_prompt}"
                    }
                ],
                "modalities": ["image", "text"],
                "image_config": {
                    "aspect_ratio": aspect_ratio
                }
            }
            
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                    raise Exception(f"API request failed: {response.status} - {error_text}")
                
                data = await response.json()
            
            # Extract image from response
            image_base64 = self._extract_image_from_response(data)
            
            if not image_base64:
                # Log the response structure for debugging
                logger.error(f"No image in response. Structure: {list(data.keys())}")
                if 'choices' in data and data['choices']:
                    msg = data['choices'][0].get('message', {})
                    logger.error(f"Message keys: {list(msg.keys())}")
                    if 'images' in msg:
                        logger.error(f"Images type: {type(msg['images'])}, content: {str(msg['images'])[:200]}")
                raise Exception("No image data in response")
            
            generation_time = time.time() - start_time
            
            # Get resolution from aspect ratio
            resolution = self._get_resolution_from_aspect_ratio(aspect_ratio)
            
            return {
                'success': True,
                'image_url': '',  # OpenRouter returns base64 directly
                'image_base64': image_base64,
                'original_prompt': prompt,
                'enhanced_prompt': enhanced_prompt,
                'model_used': model,
                'generation_time_seconds': round(generation_time, 2),
                'resolution': resolution,
                'content_type': content_type,
                'aspect_ratio': aspect_ratio,
                'metadata': {
                    'provider': 'openrouter',
                    'created_at': datetime.now().isoformat()
                }
            }
            
        except aiohttp.ClientError as e:
            logger.error(f"OpenRouter connection error: {e}")
            return {
                'success': False,
                'error': f"Connection error: {str(e)}",
                'original_prompt': prompt,
                'enhanced_prompt': enhanced_prompt if 'enhanced_prompt' in locals() else prompt,
                'generation_time_seconds': time.time() - start_time
            }
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_prompt': prompt,
                'enhanced_prompt': enhanced_prompt if 'enhanced_prompt' in locals() else prompt,
                'generation_time_seconds': time.time() - start_time
            }
    
    def _extract_image_from_response(self, response_data: Dict) -> Optional[str]:
        """
        Extract base64 image data from OpenRouter response.
        
        FIXED: Handle both string and dict formats from Gemini API.
        The API sometimes returns:
        - String: "data:image/png;base64,XXXXX"
        - Dict: {"url": "data:image/png;base64,XXXXX"} or {"b64_json": "XXXXX"}
        """
        try:
            choices = response_data.get('choices', [])
            if not choices:
                logger.warning("No choices in response")
                return None
            
            message = choices[0].get('message', {})
            
            # Check for images array (primary format)
            images = message.get('images', [])
            if images:
                image_data = images[0]
                
                # FIXED: Handle dict format (new API response)
                if isinstance(image_data, dict):
                    logger.debug(f"Image data is dict with keys: {list(image_data.keys())}")
                    # Try common dict keys for image data
                    image_data = (
                        image_data.get('url') or
                        image_data.get('b64_json') or
                        image_data.get('data') or
                        image_data.get('base64') or
                        image_data.get('image_url', {}).get('url') or
                        ''
                    )
                
                # Now image_data should be a string
                if isinstance(image_data, str) and image_data:
                    if image_data.startswith('data:'):
                        # Extract base64 portion after the comma
                        return image_data.split(',', 1)[1] if ',' in image_data else image_data
                    # Already base64 without data: prefix
                    return image_data
            
            # Check content for embedded image (alternative format)
            content = message.get('content', '')
            if isinstance(content, str) and 'data:image' in content:
                # Extract base64 from data URL in content
                match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', content)
                if match:
                    return match.group(1)
            
            # Check if content is a list (multimodal response)
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'image':
                        image_data = item.get('data', item.get('image_url', {}).get('url', ''))
                        
                        # FIXED: Handle dict format here too
                        if isinstance(image_data, dict):
                            image_data = (
                                image_data.get('url') or
                                image_data.get('b64_json') or
                                image_data.get('data') or
                                ''
                            )
                        
                        if isinstance(image_data, str) and image_data:
                            if image_data.startswith('data:'):
                                return image_data.split(',', 1)[1] if ',' in image_data else image_data
                            return image_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract image from response: {e}", exc_info=True)
            return None
    
    def _get_resolution_from_aspect_ratio(self, aspect_ratio: str) -> str:
        """Get resolution string from aspect ratio"""
        resolutions = {
            '1:1': '1024x1024',
            '2:3': '832x1248',
            '3:2': '1248x832',
            '3:4': '864x1184',
            '4:3': '1184x864',
            '4:5': '896x1152',
            '5:4': '1152x896',
            '9:16': '768x1344',
            '16:9': '1344x768',
            '21:9': '1536x672'
        }
        return resolutions.get(aspect_ratio, '1024x1024')
    
    def get_available_models(self) -> Dict[str, str]:
        """Get list of available models and their use cases"""
        return {
            'High Quality (Gemini 3 Pro)': self.default_model,
            'Fast Generation (Gemini 2.5 Flash)': self.fallback_model
        }
    
    def get_supported_aspect_ratios(self) -> Dict[str, str]:
        """Get supported aspect ratios and their resolutions"""
        return {
            '1:1': '1024x1024 (Square - Social, General)',
            '3:2': '1248x832 (Landscape - Blog, Professional)',
            '2:3': '832x1248 (Portrait)',
            '16:9': '1344x768 (Wide - Marketing, Video)',
            '9:16': '768x1344 (Vertical - Stories)',
            '4:3': '1184x864 (Classic)',
            '3:4': '864x1184 (Portrait Classic)'
        }
    
    async def test_api_connection(self) -> Dict[str, Any]:
        """Test API connection and return status"""
        try:
            session = await self._get_session()
            
            # Use OpenRouter's models endpoint to test connection
            async with session.get(f"{self.base_url}/models") as response:
                if response.status == 200:
                    data = await response.json()
                    # Check if our image model is available
                    models = data.get('data', [])
                    image_model_available = any(
                        m.get('id') == self.default_model for m in models
                    )
                    
                    return {
                        'success': True,
                        'status': 'API connection successful',
                        'image_model_available': image_model_available,
                        'model': self.default_model,
                        'available_models': len(self.get_available_models())
                    }
                else:
                    return {
                        'success': False,
                        'status': f'API connection failed: {response.status}',
                        'error': await response.text()
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'status': 'API connection failed',
                'error': str(e)
            }


# Convenience alias for backward compatibility
ReplicateImageClient = OpenRouterImageClient


# Test function for development
async def test_openrouter_client():
    """Test the OpenRouter image client"""
    print("🧪 TESTING OPENROUTER IMAGE CLIENT")
    print("=" * 50)
    
    try:
        client = OpenRouterImageClient()
        print(f"✅ Client initialized")
        print(f"   Default model: {client.default_model}")
        print(f"   Fallback model: {client.fallback_model}")
        
        # Test API connection
        print("\n📡 Testing API connection...")
        connection_test = await client.test_api_connection()
        print(f"   Status: {'✅' if connection_test['success'] else '❌'} {connection_test['status']}")
        
        if connection_test['success']:
            print(f"   Image model available: {connection_test.get('image_model_available', 'unknown')}")
            
            # Test image generation with a simple prompt
            print("\n🎨 Testing image generation...")
            result = await client.generate_image(
                prompt="a simple blue circle on white background",
                content_type="general",
                speed_priority=True  # Use faster model for testing
            )
            
            if result['success']:
                print(f"✅ Image generated successfully!")
                print(f"   Model: {result['model_used']}")
                print(f"   Generation time: {result['generation_time_seconds']}s")
                print(f"   Resolution: {result['resolution']}")
                print(f"   Base64 length: {len(result['image_base64'])} characters")
            else:
                print(f"❌ Generation failed: {result['error']}")
        
        await client.close_session()
        print("\n✅ Test complete")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_openrouter_client())
