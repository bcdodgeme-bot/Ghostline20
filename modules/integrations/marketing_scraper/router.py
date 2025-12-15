# modules/integrations/marketing_scraper/router.py
"""
Marketing Scraper FastAPI Router
Provides REST endpoints for health checks, module status, and competitive analysis
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from .database_manager import get_scraped_content_database
from .integration_info import get_integration_info, check_module_health

logger = logging.getLogger(__name__)


async def get_current_user_id() -> str:
    """Get current user ID - placeholder for marketing scraper"""
    return "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"


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


class ComparisonRequest(BaseModel):
    content_ids: List[str]


class ComparisonResponse(BaseModel):
    competitors_compared: int
    comparison: Optional[Dict[str, Any]]
    error: Optional[str] = None


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
        db = get_scraped_content_database()
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
    limit: int = Query(default=20, le=100, ge=1),
    user_id: str = Depends(get_current_user_id)
):
    """Get user's recent scraping history"""
    try:
        db = get_scraped_content_database()
        history = await db.get_user_scrape_history(user_id, limit)
        
        return {
            'history': history,
            'count': len(history),
            'limit': limit
        }
        
    except Exception as e:
        logger.error(f"History retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"History retrieval failed: {str(e)}")


# =========================================================================
# COMPETITIVE ANALYSIS ENDPOINTS
# =========================================================================

@router.post("/compare")
async def compare_competitors(
    request: ComparisonRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Compare multiple scraped competitors side-by-side
    
    Requires at least 2 content IDs from previous scrapes.
    Returns patterns, similarities, and differentiation opportunities.
    """
    try:
        if len(request.content_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 content IDs required for comparison"
            )
        
        if len(request.content_ids) > 10:
            raise HTTPException(
                status_code=400,
                detail="Maximum 10 competitors can be compared at once"
            )
        
        db = get_scraped_content_database()
        comparison = await db.compare_competitors(user_id, request.content_ids)
        
        if comparison.get('error'):
            raise HTTPException(status_code=400, detail=comparison['error'])
        
        return comparison
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Competitor comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.get("/domain/{domain}")
async def get_domain_insights(
    domain: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get aggregated insights for a specific domain
    
    Useful when multiple pages from the same competitor have been scraped.
    Aggregates all insights across pages for comprehensive domain analysis.
    """
    try:
        db = get_scraped_content_database()
        insights = await db.get_domain_insights(user_id, domain)
        
        if insights.get('error'):
            raise HTTPException(status_code=400, detail=insights['error'])
        
        return insights
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Domain insights retrieval failed for {domain}: {e}")
        raise HTTPException(status_code=500, detail=f"Domain insights failed: {str(e)}")


@router.get("/competitive-summary")
async def get_competitive_summary(
    limit: int = Query(default=10, le=50, ge=1),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get cross-competitor analysis patterns from recent scrapes
    
    Analyzes patterns across all recent scrapes to identify:
    - Common market tactics
    - Saturated approaches
    - Differentiation opportunities
    """
    try:
        db = get_scraped_content_database()
        summary = await db.get_competitive_summary(user_id, limit)
        
        if summary.get('error'):
            raise HTTPException(status_code=400, detail=summary['error'])
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Competitive summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Competitive summary failed: {str(e)}")


@router.get("/search")
async def search_insights(
    topic: str = Query(..., min_length=2, description="Topic or keyword to search"),
    limit: int = Query(default=10, le=50, ge=1),
    user_id: str = Depends(get_current_user_id)
):
    """
    Search stored insights by topic or keyword
    
    Searches across all scraped content including:
    - Page titles and content
    - Competitive insights
    - Marketing angles
    """
    try:
        db = get_scraped_content_database()
        results = await db.search_scraped_insights(user_id, topic, limit)
        
        return {
            'query': topic,
            'results': results,
            'count': len(results),
            'limit': limit
        }
        
    except Exception as e:
        logger.error(f"Insight search failed for topic '{topic}': {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/content/{content_id}")
async def get_scraped_content(
    content_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get specific scraped content by ID
    
    Returns full content including all analysis results.
    Updates last_accessed_at timestamp.
    """
    try:
        db = get_scraped_content_database()
        content = await db.get_scraped_content(content_id, user_id)
        
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        return content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Content retrieval failed for {content_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Content retrieval failed: {str(e)}")
