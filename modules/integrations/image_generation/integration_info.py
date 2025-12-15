# modules/integrations/image_generation/integration_info.py
"""
Integration Information and Health Checks for Image Generation Module
Provides comprehensive system status, health monitoring, and configuration validation

Key Features:
- Complete health check system
- Environment validation
- API connectivity testing
- Database health monitoring
- Performance metrics
- Configuration verification
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

# Module constants
MODULE_NAME = 'image_generation'
MODULE_VERSION = '2.0.0'
MODULE_DESCRIPTION = 'AI-powered image generation with inline display and download functionality'

def check_module_health() -> Dict[str, Any]:
    """
    Comprehensive health check for image generation module
    
    Returns:
        Dict with health status, missing configurations, and recommendations
    """
    health_status = {
        'healthy': True,
        'module': MODULE_NAME,
        'version': MODULE_VERSION,
        'timestamp': datetime.now().isoformat(),
        'checks': {},
        'missing_vars': [],
        'configured_vars': [],
        'optional_missing': [],
        'errors': [],
        'warnings': [],
        'recommendations': []
    }
    
    # 1. Environment Variables Check
    required_vars = [
        'DATABASE_URL',
        'OPENROUTER_API_KEY'
    ]
    
    optional_vars = [
        'IMAGE_GENERATION_TIMEOUT',
        'IMAGE_QUALITY_DEFAULT',
        'IMAGE_STORAGE_PATH',
        'MAX_IMAGE_SIZE_MB'
    ]
    
    env_check = _check_environment_variables(required_vars, optional_vars)
    health_status['checks']['environment'] = env_check
    health_status['missing_vars'] = env_check['missing_required']
    health_status['configured_vars'] = env_check['configured']
    health_status['optional_missing'] = env_check['missing_optional']
    
    if env_check['missing_required']:
        health_status['healthy'] = False
        health_status['errors'].append(f"Missing required environment variables: {', '.join(env_check['missing_required'])}")
    
    # 2. Component Initialization Check
    component_check = _check_component_initialization()
    health_status['checks']['components'] = component_check
    
    if not component_check['all_initialized']:
        health_status['healthy'] = False
        health_status['errors'].extend(component_check['errors'])
    
    # 3. Dependency Check
    dependency_check = _check_dependencies()
    health_status['checks']['dependencies'] = dependency_check
    
    if dependency_check['missing_critical']:
        health_status['healthy'] = False
        health_status['errors'].extend(dependency_check['errors'])
    
    if dependency_check['missing_optional']:
        health_status['warnings'].extend(dependency_check['warnings'])
    
    # 4. Configuration Validation
    config_check = _check_configuration()
    health_status['checks']['configuration'] = config_check
    
    if config_check['issues']:
        health_status['warnings'].extend(config_check['issues'])
    
    # 5. Generate Recommendations
    health_status['recommendations'] = _generate_recommendations(health_status)
    
    return health_status

async def check_runtime_health() -> Dict[str, Any]:
    """
    Runtime health check that tests actual functionality
    
    Returns:
        Dict with runtime status and performance metrics
    """
    runtime_status = {
        'healthy': True,
        'timestamp': datetime.now().isoformat(),
        'tests': {},
        'performance': {},
        'errors': [],
        'warnings': []
    }
    
    try:
        # 1. Database Connection Test
        db_test = await _test_database_connection()
        runtime_status['tests']['database'] = db_test
        
        if not db_test['success']:
            runtime_status['healthy'] = False
            runtime_status['errors'].append(f"Database test failed: {db_test['error']}")
        
        # 2. OpenRouter API Test
        api_test = await _test_openrouter_api()
        runtime_status['tests']['openrouter_api'] = api_test
        
        if not api_test['success']:
            runtime_status['healthy'] = False
            runtime_status['errors'].append(f"OpenRouter API test failed: {api_test['error']}")
        
        # 3. Image Processing Test
        processing_test = await _test_image_processing()
        runtime_status['tests']['image_processing'] = processing_test
        
        if not processing_test['success']:
            runtime_status['warnings'].append(f"Image processing test failed: {processing_test['error']}")
        
        # 4. Performance Metrics
        if runtime_status['healthy']:
            performance_metrics = await _collect_performance_metrics()
            runtime_status['performance'] = performance_metrics
    
    except Exception as e:
        logger.error(f"Runtime health check failed: {e}")
        runtime_status['healthy'] = False
        runtime_status['errors'].append(f"Health check exception: {str(e)}")
    
    return runtime_status

def get_integration_info() -> Dict[str, Any]:
    """
    Get comprehensive integration information
    
    Returns:
        Complete module information including features, commands, and configuration
    """
    return {
        'module': MODULE_NAME,
        'version': MODULE_VERSION,
        'description': MODULE_DESCRIPTION,
        'integration_type': 'chat_command',
        'status': 'active',
        
        # Health status
        'health_status': check_module_health(),
        
        # Chat commands
        'chat_commands': {
            'image create [prompt]': {
                'description': 'Generate image from text description',
                'example': 'image create a professional business meeting',
                'parameters': ['prompt: text description of desired image']
            },
            'image blog [topic]': {
                'description': 'Create blog featured image for topic',
                'example': 'image blog content marketing trends',
                'parameters': ['topic: blog post topic or theme']
            },
            'image social [content]': {
                'description': 'Generate social media graphic',
                'example': 'image social new product announcement',
                'parameters': ['content: social media content description']
            },
            'image marketing [campaign]': {
                'description': 'Create marketing visual',
                'example': 'image marketing email campaign header',
                'parameters': ['campaign: marketing campaign description']
            },
            'image style [style_name] [prompt]': {
                'description': 'Generate with specific style template',
                'example': 'image style professional blog a business strategy',
                'parameters': ['style_name: template name', 'prompt: image description']
            },
            'image history': {
                'description': 'Show recent generated images',
                'example': 'image history',
                'parameters': []
            }
        },
        
        # Core features
        'features': [
            'Inline image display (base64) - no external URLs to follow',
            'OpenRouter API with Gemini image generation',
            'Content intelligence integration (RSS/Trends/Scraper)',
            'Prompt optimization using marketing insights',
            'Multiple format downloads (PNG, JPG, WebP)',
            'Style templates for consistent branding',
            'Social media size pack generation',
            'Real-time download tracking and analytics',
            'Background processing for fast chat responses',
            'Professional image processing and optimization'
        ],
        
        # Technical capabilities
        'technical_capabilities': {
            'supported_models': [
                'Gemini (via OpenRouter)',
                'Aspect ratio support per content type',
                'Direct base64 response (no polling)'
            ],
            'supported_formats': ['PNG', 'JPG', 'JPEG', 'WebP'],
            'quality_presets': ['web_optimized', 'high_quality', 'print_ready', 'social_media', 'thumbnail'],
            'resolution_presets': [
                'Original', 'HD (1920x1080)', 'Instagram (1080x1080)',
                'Facebook (1200x630)', 'Twitter (1200x675)', 'Blog Header (1200x630)'
            ],
            'content_intelligence': [
                'RSS marketing insights integration',
                'Trending keyword enhancement',
                'Sentiment-aware visual guidance',
                'Business context optimization'
            ]
        },
        
        # API endpoints
        'endpoints': {
            'generate': {
                'url': '/integrations/image-generation/generate',
                'method': 'POST',
                'description': 'Generate image with full options'
            },
            'quick_generate': {
                'url': '/integrations/image-generation/quick-generate/{prompt}',
                'method': 'GET',
                'description': 'Quick generation for chat commands'
            },
            'chat_generate': {
                'url': '/integrations/image-generation/chat-generate',
                'method': 'POST',
                'description': 'Specialized endpoint for AI router integration'
            },
            'history': {
                'url': '/integrations/image-generation/history',
                'method': 'GET',
                'description': 'Get user image generation history'
            },
            'download': {
                'url': '/integrations/image-generation/download/{image_id}',
                'method': 'GET',
                'description': 'Download image in specified format'
            },
            'styles': {
                'url': '/integrations/image-generation/styles',
                'method': 'GET',
                'description': 'Get available style templates'
            },
            'health': {
                'url': '/integrations/image-generation/health',
                'method': 'GET',
                'description': 'System health check'
            },
            'stats': {
                'url': '/integrations/image-generation/stats',
                'method': 'GET',
                'description': 'Generation statistics and analytics'
            }
        },
        
        # Database schema
        'database_schema': {
            'tables': {
                'generated_images': {
                    'description': 'Stores generated images with metadata',
                    'key_fields': ['id', 'user_id', 'original_prompt', 'enhanced_prompt', 'image_data_base64']
                },
                'image_style_templates': {
                    'description': 'Style templates for consistent branding',
                    'key_fields': ['id', 'name', 'style_prompt', 'color_scheme', 'usage_count']
                }
            },
            'indexes': [
                'idx_generated_images_user (user performance)',
                'idx_generated_images_content_type (filtering)',
                'idx_generated_images_keywords (search)',
                'idx_style_templates_business (style lookup)'
            ]
        },
        
        # Configuration requirements
        'configuration': {
            'required_env_vars': [
                {
                    'name': 'DATABASE_URL',
                    'description': 'PostgreSQL connection string',
                    'example': 'postgresql://user:pass@host:port/dbname'
                },
                {
                    'name': 'OPENROUTER_API_KEY',
                    'description': 'OpenRouter API authentication key',
                    'example': 'sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                }
            ],
            'optional_env_vars': [
                {
                    'name': 'IMAGE_GENERATION_TIMEOUT',
                    'description': 'Generation timeout in seconds',
                    'example': '300'
                }
            ],
            'database_requirements': [
                'PostgreSQL with JSONB support',
                'UUID extension (uuid-ossp)',
                'Full-text search capabilities',
                'Sufficient storage for base64 image data'
            ]
        },
        
        # Integration workflow
        'workflow': [
            '1. User types image command in chat interface',
            '2. AI router detects image generation request',
            '3. Prompt optimizer enhances description using content intelligence',
            '4. OpenRouter client generates image via Gemini',
            '5. Image displays inline immediately via base64 encoding',
            '6. Database manager saves image with full metadata',
            '7. Download buttons provide multiple format options',
            '8. Analytics track usage patterns and optimization'
        ],
        
        # Business value
        'business_value': {
            'content_creation_acceleration': 'Generate professional visuals instantly',
            'marketing_intelligence_integration': 'Images informed by current trends',
            'brand_consistency': 'Style templates ensure cohesive visual identity',
            'workflow_efficiency': 'Inline display eliminates external URL friction',
            'cost_optimization': 'OpenRouter provides competitive pricing',
            'analytics_insights': 'Track what visual content performs best'
        },
        
        # Troubleshooting
        'troubleshooting': {
            'common_issues': {
                'generation_timeout': 'Check OPENROUTER_API_KEY and network connectivity',
                'database_errors': 'Verify DATABASE_URL and table existence',
                'style_template_missing': 'Run database setup script to create default templates',
                'format_conversion_failure': 'Ensure PIL/Pillow dependencies are installed'
            },
            'diagnostic_commands': [
                'Check health endpoint: GET /integrations/image-generation/health',
                'View recent activity: GET /integrations/image-generation/stats',
                'Test generation: GET /integrations/image-generation/quick-generate/test'
            ]
        }
    }

# Helper functions for health checks

def _check_environment_variables(required_vars: List[str], optional_vars: List[str]) -> Dict[str, Any]:
    """Check environment variable configuration"""
    configured = []
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if os.getenv(var):
            configured.append(var)
        else:
            missing_required.append(var)
    
    for var in optional_vars:
        if os.getenv(var):
            configured.append(var)
        else:
            missing_optional.append(var)
    
    return {
        'configured': configured,
        'missing_required': missing_required,
        'missing_optional': missing_optional,
        'total_configured': len(configured),
        'configuration_score': len(configured) / (len(required_vars) + len(optional_vars))
    }

def _check_component_initialization() -> Dict[str, Any]:
    """Check if all components can be initialized"""
    components = {
        'openrouter_client': False,
        'database_manager': False,
        'image_processor': False,
        'prompt_optimizer': False
    }
    errors = []
    
    try:
        from .openrouter_image_client import OpenRouterImageClient
        OpenRouterImageClient()
        components['openrouter_client'] = True
    except Exception as e:
        errors.append(f"OpenRouterImageClient: {str(e)}")
    
    try:
        from .database_manager import ImageDatabase
        ImageDatabase()
        components['database_manager'] = True
    except Exception as e:
        errors.append(f"ImageDatabase: {str(e)}")
    
    try:
        from .image_processor import ImageProcessor
        ImageProcessor()
        components['image_processor'] = True
    except Exception as e:
        errors.append(f"ImageProcessor: {str(e)}")
    
    try:
        from .prompt_optimizer import PromptOptimizer
        PromptOptimizer()
        components['prompt_optimizer'] = True
    except Exception as e:
        errors.append(f"PromptOptimizer: {str(e)}")
    
    return {
        'components': components,
        'all_initialized': all(components.values()),
        'initialized_count': sum(components.values()),
        'total_components': len(components),
        'errors': errors
    }

def _check_dependencies() -> Dict[str, Any]:
    """Check Python package dependencies"""
    critical_deps = [
        ('asyncpg', 'Database connectivity'),
        ('aiohttp', 'HTTP requests for OpenRouter API'),
        ('fastapi', 'API framework'),
        ('pydantic', 'Data validation')
    ]
    
    optional_deps = [
        ('PIL', 'Image processing'),
        ('Pillow', 'Image processing (alternative)'),
        ('numpy', 'Numerical operations'),
        ('requests', 'HTTP requests fallback')
    ]
    
    missing_critical = []
    missing_optional = []
    errors = []
    warnings = []
    
    for dep, description in critical_deps:
        try:
            __import__(dep)
        except ImportError:
            missing_critical.append(dep)
            errors.append(f"Missing critical dependency: {dep} ({description})")
    
    for dep, description in optional_deps:
        try:
            __import__(dep)
        except ImportError:
            missing_optional.append(dep)
            warnings.append(f"Missing optional dependency: {dep} ({description})")
    
    return {
        'missing_critical': missing_critical,
        'missing_optional': missing_optional,
        'errors': errors,
        'warnings': warnings,
        'dependency_score': (len(critical_deps) - len(missing_critical)) / len(critical_deps)
    }

def _check_configuration() -> Dict[str, Any]:
    """Check configuration values and settings"""
    issues = []
    
    # Check OpenRouter API key format (typically starts with sk-or-)
    api_key = os.getenv('OPENROUTER_API_KEY')
    if api_key and not (api_key.startswith('sk-or-') or api_key.startswith('sk-')):
        issues.append("OPENROUTER_API_KEY format looks unusual (expected sk-or-* or sk-*)")
    
    # Check database URL format
    db_url = os.getenv('DATABASE_URL')
    if db_url and not db_url.startswith('postgresql://'):
        issues.append("DATABASE_URL should be a PostgreSQL connection string")
    
    # Check timeout setting
    timeout = os.getenv('IMAGE_GENERATION_TIMEOUT')
    if timeout:
        try:
            timeout_val = int(timeout)
            if timeout_val < 30 or timeout_val > 600:
                issues.append("IMAGE_GENERATION_TIMEOUT should be between 30-600 seconds")
        except ValueError:
            issues.append("IMAGE_GENERATION_TIMEOUT must be a valid integer")
    
    return {
        'issues': issues,
        'valid_configuration': len(issues) == 0
    }

async def _test_database_connection() -> Dict[str, Any]:
    """Test database connectivity"""
    try:
        from .database_manager import ImageDatabase
        db = ImageDatabase()
        health = await db.health_check()
        
        return {
            'success': health['healthy'],
            'response_time_ms': 0,  # Could add timing
            'tables_accessible': health.get('tables_exist', []),
            'error': None if health['healthy'] else health.get('error', 'Unknown database error')
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'response_time_ms': 0,
            'tables_accessible': []
        }

async def _test_openrouter_api() -> Dict[str, Any]:
    """Test OpenRouter API connectivity"""
    try:
        from .openrouter_image_client import OpenRouterImageClient
        client = OpenRouterImageClient()
        
        start_time = datetime.now()
        result = await client.test_api_connection()
        end_time = datetime.now()
        
        await client.close_session()
        
        response_time = (end_time - start_time).total_seconds() * 1000
        
        return {
            'success': result['success'],
            'response_time_ms': round(response_time, 2),
            'status': result['status'],
            'error': result.get('error')
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'response_time_ms': 0,
            'status': 'connection_failed'
        }

async def _test_image_processing() -> Dict[str, Any]:
    """Test image processing capabilities"""
    try:
        from .image_processor import ImageProcessor
        processor = ImageProcessor()
        
        # Test basic functionality without actual image
        presets = processor.get_available_presets()
        
        return {
            'success': True,
            'quality_presets': len(presets['quality_presets']),
            'resolution_presets': len(presets['resolution_presets']),
            'supported_formats': len(presets['supported_formats']),
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'quality_presets': 0,
            'resolution_presets': 0,
            'supported_formats': 0
        }

async def _collect_performance_metrics() -> Dict[str, Any]:
    """Collect performance metrics"""
    try:
        from .database_manager import ImageDatabase
        db = ImageDatabase()
        
        # Get recent generation stats
        stats = await db.get_generation_stats(days=7)
        
        return {
            'recent_generations': stats.get('total_images', 0),
            'avg_generation_time': stats.get('avg_generation_time', 0),
            'popular_content_types': stats.get('content_types', [])[:3],
            'popular_models': stats.get('models_used', [])[:3]
        }
    except Exception as e:
        logger.warning(f"Could not collect performance metrics: {e}")
        return {
            'recent_generations': 0,
            'avg_generation_time': 0,
            'popular_content_types': [],
            'popular_models': []
        }

def _generate_recommendations(health_status: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on health status"""
    recommendations = []
    
    if health_status['missing_vars']:
        recommendations.append(f"Set required environment variables: {', '.join(health_status['missing_vars'])}")
    
    if health_status.get('checks', {}).get('dependencies', {}).get('missing_optional'):
        recommendations.append("Install optional dependencies for enhanced image processing: pip install Pillow")
    
    if not health_status.get('checks', {}).get('configuration', {}).get('valid_configuration', True):
        recommendations.append("Review configuration warnings and adjust environment variables")
    
    if health_status['optional_missing']:
        recommendations.append("Consider setting optional environment variables for enhanced functionality")
    
    if not recommendations:
        recommendations.append("System is healthy and ready for image generation!")
    
    return recommendations

# Convenience function for external health checks
async def get_system_status() -> Dict[str, Any]:
    """Get complete system status including static and runtime health"""
    static_health = check_module_health()
    runtime_health = await check_runtime_health()
    
    return {
        'module': MODULE_NAME,
        'version': MODULE_VERSION,
        'overall_healthy': static_health['healthy'] and runtime_health['healthy'],
        'static_health': static_health,
        'runtime_health': runtime_health,
        'timestamp': datetime.now().isoformat()
    }

if __name__ == "__main__":
    # Test health checks
    print("🔍 TESTING IMAGE GENERATION HEALTH CHECKS")
    print("=" * 50)
    
    # Static health check
    health = check_module_health()
    print(f"Static Health: {'✅' if health['healthy'] else '❌'}")
    print(f"Configured vars: {len(health['configured_vars'])}")
    print(f"Missing vars: {health['missing_vars']}")
    
    # Runtime health check
    async def test_runtime():
        runtime = await check_runtime_health()
        print(f"Runtime Health: {'✅' if runtime['healthy'] else '❌'}")
        print(f"Tests passed: {sum(1 for t in runtime['tests'].values() if t.get('success', False))}/{len(runtime['tests'])}")
    
    asyncio.run(test_runtime())
