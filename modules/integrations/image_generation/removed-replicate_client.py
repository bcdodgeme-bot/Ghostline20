# modules/integrations/image_generation/replicate_client.py
"""
Replicate API Client for Syntax Prime V2
Handles image generation with smart model selection and error handling

Key Features:
- Smart model selection based on content type and use case
- Rate limiting and error handling
- Base64 conversion for inline display
- Prompt optimization for better results
"""

import os
import asyncio
import aiohttp
import logging
import time
import base64
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class ReplicateImageClient:
    """
    Replicate API client with intelligent model selection
    Eliminates the confusing model selection experience
    """
    
    def __init__(self):
        self.api_token = os.getenv('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable is required")
        self.base_url = "https://api.replicate.com/v1"
        self.session = None
        
        # Smart model selection - based on your requirements
        self.model_map = {
            # High-quality for marketing and professional use
            'blog': 'stability-ai/stable-diffusion-xl-base-1.0',
            'marketing': 'stability-ai/stable-diffusion-xl-base-1.0',
            'professional': 'stability-ai/stable-diffusion-xl-base-1.0',
            
            # Fast generation for social media
            'social': 'bytedance/sdxl-lightning-4step',
            'quick': 'bytedance/sdxl-lightning-4step',
            
            # Specialized models
            'illustration': 'lucataco/realistic-vision-v5.1',
            'artistic': 'lucataco/realistic-vision-v5.1',
            'logo': 'stability-ai/stable-diffusion-xl-base-1.0',
            
            # Default fallback
            'general': 'stability-ai/stable-diffusion-xl-base-1.0'
        }
        
        # Rate limiting - be gentle with API
        self.last_request_time = 0
        self.min_request_interval = 2.0  # 2 seconds between requests
        
    async def ensure_session(self):
        """Ensure we have an active aiohttp session"""
        if self.session is None or self.session.closed:
            headers = {
                'Authorization': f'Token {self.api_token}',
                'Content-Type': 'application/json'
            }
            self.session = aiohttp.ClientSession(headers=headers)
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def select_model(self, content_type: str = 'general', speed_priority: bool = False) -> str:
        """
        Smart model selection based on content type
        
        Args:
            content_type: Type of content ('blog', 'social', 'marketing', etc.)
            speed_priority: If True, prefer faster models
            
        Returns:
            Model identifier string
        """
        if speed_priority:
            return self.model_map.get('quick', self.model_map['general'])
        
        return self.model_map.get(content_type.lower(), self.model_map['general'])
    
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
        if content_type == 'blog':
            enhanced += ", professional, clean, blog header suitable, high quality"
        elif content_type == 'social':
            enhanced += ", eye-catching, social media optimized, vibrant"
        elif content_type == 'marketing':
            enhanced += ", professional marketing design, corporate, polished"
        elif content_type == 'illustration':
            enhanced += ", artistic illustration, creative, detailed"
        
        # Always add quality modifiers
        enhanced += ", high quality, detailed, sharp focus"
        
        # Remove any duplicate words
        words = enhanced.split(', ')
        unique_words = []
        for word in words:
            if word not in unique_words:
                unique_words.append(word)
        
        return ', '.join(unique_words)
    
    async def rate_limit_wait(self):
        """Ensure we don't hit rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            logger.info(f"Rate limiting: waiting {wait_time:.1f} seconds")
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    async def generate_image(self, prompt: str, content_type: str = 'general',
                           width: int = 1024, height: int = 1024,
                           style_template: Optional[Dict] = None,
                           speed_priority: bool = False) -> Dict[str, Any]:
        """
        Generate an image using Replicate API
        
        Args:
            prompt: Text description of desired image
            content_type: Type of content ('blog', 'social', 'marketing', etc.)
            width: Image width in pixels
            height: Image height in pixels
            style_template: Optional style template from database
            speed_priority: Prioritize speed over quality
            
        Returns:
            Dict with generation results, image data, and metadata
        """
        await self.ensure_session()
        await self.rate_limit_wait()
        
        start_time = time.time()
        
        try:
            # Select appropriate model
            model = self.select_model(content_type, speed_priority)
            
            # Enhance the prompt
            enhanced_prompt = self.enhance_prompt(prompt, content_type, style_template)
            
            logger.info(f"Generating image with model: {model}")
            logger.info(f"Enhanced prompt: {enhanced_prompt[:100]}...")
            
            # Prepare the request
            prediction_data = {
                "version": await self._get_model_version(model),
                "input": {
                    "prompt": enhanced_prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": 1,
                    "guidance_scale": 7.5,
                    "num_inference_steps": 50 if not speed_priority else 4
                }
            }
            
            # Create the prediction
            async with self.session.post(f"{self.base_url}/predictions", 
                                       json=prediction_data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise Exception(f"Failed to create prediction: {response.status} - {error_text}")
                
                prediction = await response.json()
                prediction_id = prediction['id']
            
            # Wait for completion
            image_url = await self._wait_for_completion(prediction_id)
            
            # Download and convert to base64
            image_base64 = await self._download_image_as_base64(image_url)
            
            generation_time = time.time() - start_time
            
            return {
                'success': True,
                'image_url': image_url,
                'image_base64': image_base64,
                'original_prompt': prompt,
                'enhanced_prompt': enhanced_prompt,
                'model_used': model,
                'generation_time_seconds': round(generation_time, 2),
                'resolution': f"{width}x{height}",
                'content_type': content_type,
                'metadata': {
                    'prediction_id': prediction_id,
                    'created_at': datetime.now().isoformat()
                }
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
    
    async def _get_model_version(self, model_name: str) -> str:
        """Get the latest version of a model"""
        try:
            async with self.session.get(f"{self.base_url}/models/{model_name}") as response:
                if response.status == 200:
                    model_data = await response.json()
                    return model_data['latest_version']['id']
                else:
                    # Fallback to known version IDs for common models
                    fallback_versions = {
                        'stability-ai/stable-diffusion-xl-base-1.0': '7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc',
                        'bytedance/sdxl-lightning-4step': '5f24084160c9089501c1b3545d9be3c27883ae2239b6f412990e82d4a6210f8f',
                        'lucataco/realistic-vision-v5.1': 'ac732df83cea7fff18b8472768c88ad041fa750ff7682a21affe81863cbe77e4'
                    }
                    return fallback_versions.get(model_name, fallback_versions['stability-ai/stable-diffusion-xl-base-1.0'])
        except Exception as e:
            logger.warning(f"Failed to get model version for {model_name}: {e}")
            # Return known good version as fallback
            return '7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc'
    
    async def _wait_for_completion(self, prediction_id: str, max_wait: int = 300) -> str:
        """Wait for prediction to complete and return image URL"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            await asyncio.sleep(2)  # Check every 2 seconds
            
            async with self.session.get(f"{self.base_url}/predictions/{prediction_id}") as response:
                if response.status == 200:
                    prediction = await response.json()
                    status = prediction['status']
                    
                    if status == 'succeeded':
                        output = prediction['output']
                        if isinstance(output, list) and len(output) > 0:
                            return output[0]  # Return first image URL
                        elif isinstance(output, str):
                            return output
                        else:
                            raise Exception(f"Unexpected output format: {output}")
                    
                    elif status == 'failed':
                        error_detail = prediction.get('error', 'Unknown error')
                        raise Exception(f"Prediction failed: {error_detail}")
                    
                    # Still processing, continue waiting
                    logger.info(f"Prediction {prediction_id} status: {status}")
                
                else:
                    raise Exception(f"Failed to check prediction status: {response.status}")
        
        raise Exception(f"Prediction timed out after {max_wait} seconds")
    
    async def _download_image_as_base64(self, image_url: str) -> str:
        """Download image and convert to base64 for inline display"""
        try:
            async with self.session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    return image_base64
                else:
                    raise Exception(f"Failed to download image: {response.status}")
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return ""
    
    def get_available_models(self) -> Dict[str, str]:
        """Get list of available models and their use cases"""
        return {
            'High Quality (Professional/Marketing)': self.model_map['professional'],
            'Fast Generation (Social Media)': self.model_map['social'],
            'Artistic/Illustration': self.model_map['illustration'],
            'General Purpose': self.model_map['general']
        }
    
    async def test_api_connection(self) -> Dict[str, Any]:
        """Test API connection and return status"""
        await self.ensure_session()
        
        try:
            async with self.session.get(f"{self.base_url}/models") as response:
                if response.status == 200:
                    return {
                        'success': True,
                        'status': 'API connection successful',
                        'available_models': len(self.model_map)
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

# Test function for development
async def test_replicate_client():
    """Test the Replicate client with a simple generation"""
    client = ReplicateImageClient()
    
    print("🧪 TESTING REPLICATE CLIENT")
    print("=" * 40)
    
    # Test API connection
    connection_test = await client.test_api_connection()
    print(f"API Connection: {'✅' if connection_test['success'] else '❌'} {connection_test['status']}")
    
    if connection_test['success']:
        # Test image generation with a simple prompt
        print("\n🎨 Testing image generation...")
        result = await client.generate_image(
            prompt="a simple blue circle on white background",
            content_type="test",
            width=512,
            height=512,
            speed_priority=True  # Use fast model for testing
        )
        
        if result['success']:
            print(f"✅ Image generated successfully!")
            print(f"   Model: {result['model_used']}")
            print(f"   Generation time: {result['generation_time_seconds']}s")
            print(f"   Image URL: {result['image_url'][:50]}...")
            print(f"   Base64 length: {len(result['image_base64'])} characters")
        else:
            print(f"❌ Generation failed: {result['error']}")
    
    await client.close_session()

if __name__ == "__main__":
    asyncio.run(test_replicate_client())