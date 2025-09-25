# modules/integrations/marketing_scraper/router.py
"""
Marketing Scraper FastAPI Router
Provides REST endpoints for health checks and module status
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from modules.core.auth import get_current_user_id
from .database_manager import ScrapedContentDatabase
from .integration_info import get_integration_info, check_module_health

logger = logging.getLogger(__name__)

# Create router instance
router = APIRouter(prefix="/integrations/marketing-scraper", tags=["Marketing Scraper"])

# Response models
class HealthResponse(BaseModel):
    healthy: bool
    module: str
    version: str
    timestamp: str
    details: Dict[str, Any]

class StatsResponse(BaseModel):
    user_stats: Dict[str, Any]
    module_info: Dict[str, Any]

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Marketing scraper health check endpoint"""
    try:
        health_status = check_module_health()
        integration_info = get_integration_info()
        
        return HealthResponse(
            healthy=health_status['healthy'],
            module=integration_info['module'],
            version=integration_info['version'],
            timestamp=datetime.now().isoformat(),
            details={
                'status': health_status,
                'configured_vars': health_status.get('configured_vars', []),
                'missing_vars': health_status.get('missing_vars', []),
                'database_accessible': health_status.get('database_accessible', False),
                'features_available': len(integration_info['features']),
                'commands_available': len(integration_info['chat_commands'])
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@router.get("/status")
async def module_status():
    """Get detailed module status and configuration"""
    try:
        return get_integration_info()
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@router.get("/stats", response_model=StatsResponse)
async def get_user_stats(user_id: str = Depends(get_current_user_id)):
    """Get user's marketing scraper statistics"""
    try:
        db = ScrapedContentDatabase()
        user_stats = await db.get_user_stats(user_id)
        module_info = get_integration_info()
        
        return StatsResponse(
            user_stats=user_stats,
            module_info={
                'module': module_info['module'],
                'version': module_info['version'],
                'features_count': len(module_info['features']),
                'commands_count': len(module_info['chat_commands'])
            }
        )
        
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

@router.get("/history")
async def get_scrape_history(
    limit: int = 20,
    user_id: str = Depends(get_current_user_id)
):
    """Get user's recent scraping history"""
    try:
        if limit > 100:  # Reasonable limit
            limit = 100
            
        db = ScrapedContentDatabase()
        history = await db.get_user_scrape_history(user_id, limit)
        
        return {
            'history': history,
            'count': len(history),
            'limit': limit
        }
        
    except Exception as e:
        logger.error(f"History retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"History retrieval failed: {str(e)}")