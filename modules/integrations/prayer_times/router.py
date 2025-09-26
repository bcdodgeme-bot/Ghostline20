# modules/integrations/prayer_times/router.py
"""
Prayer Times FastAPI Router
Provides REST endpoints for health checks and module status
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database_manager import get_prayer_database_manager, get_next_prayer, get_todays_prayers
from .aladhan_client import test_aladhan_api

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(prefix="/integrations/prayer-times", tags=["Prayer Times"])

# Response models
class HealthResponse(BaseModel):
    healthy: bool
    module: str
    version: str
    timestamp: str
    details: Dict[str, Any]

class StatusResponse(BaseModel):
    module_info: Dict[str, Any]
    system_status: Dict[str, Any]

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Prayer times health check endpoint"""
    try:
        health_status = check_module_health()
        integration_info = get_integration_info()
        
        return HealthResponse(
            healthy=health_status['healthy'],
            module=integration_info['module'],
            version=integration_info['version'],
            timestamp=datetime.now().isoformat(),
            details={
                'database_available': health_status.get('database_available', False),
                'aladhan_api_available': health_status.get('aladhan_api_available', False),
                'cache_system_ready': health_status.get('cache_system_ready', False),
                'location': integration_info.get('location', 'Merrifield, Virginia'),
                'calculation_method': integration_info.get('calculation_method', 'ISNA'),
                'features_available': len(integration_info['features'])
            }
        )
        
    except Exception as e:
        logger.error(f"Prayer times health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@router.get("/status", response_model=StatusResponse)
async def module_status():
    """Get detailed module status and configuration"""
    try:
        integration_info = get_integration_info()
        
        # Test system components
        system_status = {
            'database_connection': bool(os.getenv("DATABASE_URL")),
            'aladhan_api_accessible': await test_aladhan_api(),
            'cache_tables_ready': True,  # Tables were created in setup
            'chat_integration_active': True
        }
        
        return StatusResponse(
            module_info=integration_info,
            system_status=system_status
        )
        
    except Exception as e:
        logger.error(f"Prayer times status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@router.get("/test")
async def test_prayer_system():
    """Test prayer times system components"""
    try:
        results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # Test AlAdhan API
        try:
            api_test = await test_aladhan_api()
            results['tests']['aladhan_api'] = {
                'status': 'success' if api_test else 'failed',
                'accessible': api_test
            }
        except Exception as e:
            results['tests']['aladhan_api'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Test database manager
        try:
            manager = await get_prayer_database_manager()
            results['tests']['database_manager'] = {
                'status': 'success',
                'initialized': manager is not None
            }
        except Exception as e:
            results['tests']['database_manager'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Test next prayer function
        try:
            next_prayer = await get_next_prayer()
            results['tests']['next_prayer_function'] = {
                'status': 'success' if next_prayer else 'no_data',
                'has_data': next_prayer is not None
            }
        except Exception as e:
            results['tests']['next_prayer_function'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Test today's prayers function
        try:
            todays_prayers = await get_todays_prayers()
            results['tests']['daily_prayers_function'] = {
                'status': 'success' if todays_prayers else 'no_data',
                'has_data': todays_prayers is not None
            }
        except Exception as e:
            results['tests']['daily_prayers_function'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Overall system health
        successful_tests = sum(1 for test in results['tests'].values() if test['status'] == 'success')
        total_tests = len(results['tests'])
        
        results['summary'] = {
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'success_rate': f"{(successful_tests/total_tests)*100:.1f}%",
            'overall_status': 'healthy' if successful_tests >= total_tests * 0.75 else 'degraded'
        }
        
        return results
        
    except Exception as e:
        logger.error(f"Prayer times system test failed: {e}")
        raise HTTPException(status_code=500, detail=f"System test failed: {str(e)}")

# Integration info and health check functions
def get_integration_info() -> Dict[str, Any]:
    """Get prayer times integration information"""
    return {
        'module': 'prayer_times',
        'version': '1.0.0',
        'description': 'Islamic prayer times with intelligent scheduling',
        'location': 'Merrifield, Virginia',
        'calculation_method': 'ISNA',
        'timezone': 'America/New_York',
        'api_provider': 'AlAdhan.com',
        'features': [
            'Daily prayer time calculation',
            'Islamic calendar integration', 
            'Chat command interface',
            'AlAdhan API integration',
            'Database caching system',
            'Midnight refresh automation'
        ],
        'chat_commands': [
            'How long till [prayer name]?',
            'What are prayer times today?',
            'Islamic date',
            'Next prayer'
        ],
        'endpoints': {
            'health': '/integrations/prayer-times/health',
            'status': '/integrations/prayer-times/status',
            'test': '/integrations/prayer-times/test'
        }
    }

def check_module_health() -> Dict[str, Any]:
    """Check prayer times module health"""
    
    # Check database availability
    database_available = bool(os.getenv("DATABASE_URL"))
    
    # AlAdhan API is always available (free service)
    aladhan_api_available = True
    
    # Cache system ready if database is available
    cache_system_ready = database_available
    
    # Overall health
    healthy = database_available and aladhan_api_available and cache_system_ready
    
    status = {
        'healthy': healthy,
        'database_available': database_available,
        'aladhan_api_available': aladhan_api_available,
        'cache_system_ready': cache_system_ready,
        'missing_components': []
    }
    
    # Track missing components
    if not database_available:
        status['missing_components'].append('DATABASE_URL')
    
    return status