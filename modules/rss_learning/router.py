# modules/integrations/rss_learning/router.py
"""
RSS Learning FastAPI Router - API endpoints for RSS learning system
Provides endpoints for RSS management and AI brain integration
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime

from .feed_processor import RSSFeedProcessor
from .marketing_insights import MarketingInsightsExtractor
from .database_manager import RSSDatabase
from ...core.auth import get_current_user

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/integrations/rss", tags=["RSS Learning"])

# Initialize components
rss_processor = RSSFeedProcessor()
insights_extractor = MarketingInsightsExtractor()
rss_db = RSSDatabase()

@router.get("/status")
async def get_rss_status():
    """Get RSS learning system status and statistics"""
    try:
        stats = await rss_db.get_rss_statistics()
        processor_status = rss_processor.get_status()
        
        return {
            "status": "healthy" if stats.get('total_sources', 0) > 0 else "no_sources",
            "statistics": stats,
            "processor": processor_status,
            "last_updated": datetime.now().isoformat(),
            "features": {
                "background_processing": processor_status.get('running', False),
                "ai_analysis": True,
                "marketing_insights": True,
                "trend_tracking": True
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get RSS status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve RSS status")

@router.get("/sources")
async def list_rss_sources():
    """List all configured RSS sources"""
    try:
        # Get sources from database
        query = '''
            SELECT id, name, feed_url, category, description, active,
                   last_fetched, error_count, items_fetched
            FROM rss_sources 
            ORDER BY category, name
        '''
        
        sources = await rss_db.db.fetch_all(query)
        
        return {
            "sources": [dict(source) for source in sources],
            "total_count": len(sources),
            "active_count": sum(1 for s in sources if s['active']),
            "categories": list(set(s['category'] for s in sources))
        }
        
    except Exception as e:
        logger.error(f"Failed to list RSS sources: {e}")
        raise HTTPException(status_code=500, detail="Failed to list RSS sources")

@router.get("/insights")
async def get_marketing_insights(
    category: Optional[str] = Query(None, description="Filter by category (seo, content_marketing, social_media, etc.)"),
    limit: int = Query(10, ge=1, le=50, description="Number of insights to return")
):
    """Get marketing insights for AI brain integration"""
    try:
        trends = await insights_extractor.get_latest_trends(category, limit)
        
        return {
            "insights": trends,
            "category": category or "all",
            "generated_at": datetime.now().isoformat(),
            "source": "rss_learning_system"
        }
        
    except Exception as e:
        logger.error(f"Failed to get marketing insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve marketing insights")

@router.get("/trends")
async def get_trending_topics(
    days: int = Query(30, ge=1, le=90, description="Number of days to analyze"),
    limit: int = Query(10, ge=1, le=20, description="Number of trending topics")
):
    """Get trending topics from RSS content"""
    try:
        trending = await rss_db.get_trending_topics(days, limit)
        
        return {
            "trending_topics": trending,
            "analysis_period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_topics": len(trending)
        }
        
    except Exception as e:
        logger.error(f"Failed to get trending topics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trending topics")

@router.get("/writing-inspiration")
async def get_writing_inspiration(
    content_type: str = Query(..., description="Type of content (email, blog, social)"),
    topic: Optional[str] = Query(None, description="Specific topic to focus on"),
    target_audience: Optional[str] = Query(None, description="Target audience")
):
    """Get writing inspiration and insights for content creation"""
    try:
        inspiration = await insights_extractor.get_writing_inspiration(
            content_type, topic, target_audience
        )
        
        return {
            "inspiration": inspiration,
            "content_type": content_type,
            "topic": topic,
            "target_audience": target_audience,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get writing inspiration: {e}")
        raise HTTPException(status_code=500, detail="Failed to get writing inspiration")

@router.get("/campaign-insights/{campaign_type}")
async def get_campaign_insights(campaign_type: str):
    """Get insights for specific campaign types"""
    
    valid_types = ['email', 'social', 'blog', 'seo']
    if campaign_type not in valid_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid campaign type. Must be one of: {', '.join(valid_types)}"
        )
    
    try:
        insights = await insights_extractor.get_campaign_insights(campaign_type)
        
        return {
            "campaign_insights": insights,
            "campaign_type": campaign_type,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get campaign insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to get campaign insights")

@router.post("/research")
async def research_content(keywords: List[str]):
    """Research content based on keywords"""
    if not keywords or len(keywords) > 10:
        raise HTTPException(
            status_code=400,
            detail="Must provide 1-10 keywords for research"
        )
    
    try:
        research = await insights_extractor.get_content_research(keywords)
        
        return {
            "research": research,
            "keywords": keywords,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to research content: {e}")
        raise HTTPException(status_code=500, detail="Failed to research content")

@router.post("/fetch")
async def force_fetch_feeds(user = Depends(get_current_user)):
    """Force immediate fetch of all RSS feeds (admin only)"""
    try:
        # Only allow authenticated users to force fetch
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"Force RSS fetch triggered by user {user.get('email', 'unknown')}")
        
        results = await rss_processor.force_fetch_all()
        
        return {
            "message": "RSS fetch completed",
            "results": results,
            "triggered_by": user.get('email'),
            "triggered_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force fetch feeds: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch RSS feeds")

@router.get("/content/{category}")
async def get_content_by_category(
    category: str,
    limit: int = Query(10, ge=1, le=50)
):
    """Get RSS content by category"""
    try:
        insights = await rss_db.get_marketing_insights(category, limit)
        
        return {
            "content": insights,
            "category": category,
            "count": len(insights),
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get content by category: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get {category} content")

@router.get("/search")
async def search_content(
    q: str = Query(..., description="Search query"),
    limit: int = Query(5, ge=1, le=20)
):
    """Search RSS content"""
    try:
        # Split search query into keywords
        keywords = [word.strip() for word in q.split() if len(word.strip()) > 2]
        
        if not keywords:
            raise HTTPException(status_code=400, detail="Search query too short")
        
        results = await rss_db.search_content_by_keywords(keywords, limit)
        
        return {
            "results": results,
            "query": q,
            "keywords": keywords,
            "count": len(results),
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search content: {e}")
        raise HTTPException(status_code=500, detail="Failed to search content")

# AI Brain Integration Endpoints
@router.get("/ai-brain/latest-trends")
async def ai_brain_latest_trends(category: Optional[str] = None):
    """Get latest trends formatted for AI brain consumption"""
    try:
        trends = await insights_extractor.get_latest_trends(category, 5)
        
        # Format for AI brain
        ai_response = {
            "summary": trends.get('trends_summary', ''),
            "actionable_insights": trends.get('actionable_insights', []),
            "trending_keywords": trends.get('trending_keywords', []),
            "content_angles": trends.get('content_angles', []),
            "source": "rss_learning",
            "confidence": "high" if len(trends.get('actionable_insights', [])) > 3 else "medium"
        }
        
        return ai_response
        
    except Exception as e:
        logger.error(f"Failed to get AI brain trends: {e}")
        return {
            "summary": "Unable to retrieve current trends",
            "actionable_insights": [],
            "trending_keywords": [],
            "content_angles": [],
            "source": "rss_learning", 
            "confidence": "low"
        }

@router.get("/ai-brain/writing-context")
async def ai_brain_writing_context(
    content_type: str = Query("blog", description="Content type for writing context"),
    topic: Optional[str] = Query(None, description="Topic for context")
):
    """Get writing context for AI brain when assisting with content creation"""
    try:
        inspiration = await insights_extractor.get_writing_inspiration(content_type, topic)
        
        # Format for AI brain consumption
        context = {
            "content_ideas": inspiration.get('content_ideas', [])[:3],
            "key_messages": inspiration.get('key_messages', [])[:3], 
            "supporting_data": inspiration.get('supporting_data', [])[:3],
            "trending_angles": inspiration.get('trending_angles', [])[:3],
            "cta_suggestions": inspiration.get('call_to_action_ideas', [])[:3],
            "context_source": "rss_marketing_insights",
            "freshness": "current"
        }
        
        return context
        
    except Exception as e:
        logger.error(f"Failed to get AI brain writing context: {e}")
        return {
            "content_ideas": [],
            "key_messages": ["Focus on providing value to your audience"],
            "supporting_data": [],
            "trending_angles": [],
            "cta_suggestions": ["Take action on this insight"],
            "context_source": "fallback",
            "freshness": "static"
        }

@router.get("/health")
async def health_check():
    """Health check endpoint for RSS learning system"""
    try:
        stats = await rss_db.get_rss_statistics()
        processor_status = rss_processor.get_status()
        
        healthy = (
            stats.get('total_sources', 0) > 0 and 
            stats.get('total_items', 0) > 0 and
            processor_status.get('running', False)
        )
        
        return {
            "status": "healthy" if healthy else "degraded",
            "components": {
                "database": "healthy" if stats.get('total_sources', 0) > 0 else "error",
                "processor": "healthy" if processor_status.get('running') else "stopped",
                "ai_analysis": "healthy"
            },
            "metrics": {
                "sources": stats.get('total_sources', 0),
                "items": stats.get('total_items', 0),
                "processed_items": stats.get('processed_items', 0)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"RSS health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }