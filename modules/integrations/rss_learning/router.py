# modules/integrations/rss_learning/router.py
"""
RSS Learning FastAPI Router - API endpoints for RSS learning system
Provides endpoints for RSS management and AI brain integration

UPDATED: Session 15 - Fixed module-level instantiation, added knowledge base endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime

from .database_manager import get_rss_database
from .feed_processor import get_feed_processor
from .marketing_insights import get_marketing_insights_extractor
from ...core.auth import get_current_user

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/integrations/rss", tags=["RSS Learning"])


@router.get("/status")
async def get_rss_status():
    """Get RSS learning system status and statistics"""
    try:
        rss_db = get_rss_database()
        rss_processor = get_feed_processor()
        
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
                "trend_tracking": True,
                "knowledge_base_integration": True
            },
            "knowledge_base": {
                "entries_synced": stats.get('knowledge_entries', 0),
                "integration_status": "active"
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get RSS status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve RSS status")


@router.get("/sources")
async def list_rss_sources():
    """List all configured RSS sources"""
    try:
        rss_db = get_rss_database()
        
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
        insights_extractor = get_marketing_insights_extractor()
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
        rss_db = get_rss_database()
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
        insights_extractor = get_marketing_insights_extractor()
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
        insights_extractor = get_marketing_insights_extractor()
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
        insights_extractor = get_marketing_insights_extractor()
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
        
        rss_processor = get_feed_processor()
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
        rss_db = get_rss_database()
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
        rss_db = get_rss_database()
        
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


# =========================================================================
# AI Brain Integration Endpoints
# =========================================================================

@router.get("/ai-brain/latest-trends")
async def ai_brain_latest_trends(category: Optional[str] = None):
    """Get latest trends formatted for AI brain consumption"""
    try:
        insights_extractor = get_marketing_insights_extractor()
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
        insights_extractor = get_marketing_insights_extractor()
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


# =========================================================================
# Knowledge Base Integration Endpoints (NEW in Session 15)
# =========================================================================

@router.post("/backfill-knowledge")
async def backfill_knowledge_base(user = Depends(get_current_user)):
    """
    One-time backfill of existing RSS entries to knowledge base.
    Run this once after deploying the knowledge base integration.
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        logger.info(f"Knowledge base backfill triggered by user {user.get('email', 'unknown')}")
        
        rss_db = get_rss_database()
        result = await rss_db.backfill_knowledge_base()
        
        return {
            "message": "Knowledge base backfill completed",
            "result": result,
            "triggered_by": user.get('email'),
            "triggered_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to backfill knowledge base: {e}")
        raise HTTPException(status_code=500, detail="Failed to backfill knowledge base")


@router.get("/knowledge-stats")
async def get_knowledge_stats():
    """Get statistics about RSS content in knowledge base"""
    try:
        rss_db = get_rss_database()
        
        # Get RSS-specific knowledge stats
        stats_query = '''
            SELECT 
                COUNT(*) as total_entries,
                COUNT(CASE WHEN search_vector IS NOT NULL THEN 1 END) as searchable_entries,
                AVG(word_count) as avg_word_count,
                MAX(created_at) as latest_entry,
                MIN(created_at) as oldest_entry
            FROM knowledge_entries 
            WHERE source_id = (SELECT id FROM knowledge_sources WHERE source_type = 'rss_feed')
        '''
        
        result = await rss_db.db.fetch_one(stats_query)
        
        # Get source info
        source_query = '''
            SELECT id, name, description, is_active, created_at
            FROM knowledge_sources 
            WHERE source_type = 'rss_feed'
        '''
        source = await rss_db.db.fetch_one(source_query)
        
        return {
            "knowledge_source": dict(source) if source else None,
            "statistics": {
                "total_entries": result['total_entries'] if result else 0,
                "searchable_entries": result['searchable_entries'] if result else 0,
                "avg_word_count": float(result['avg_word_count']) if result and result['avg_word_count'] else 0,
                "latest_entry": result['latest_entry'].isoformat() if result and result['latest_entry'] else None,
                "oldest_entry": result['oldest_entry'].isoformat() if result and result['oldest_entry'] else None
            },
            "integration_status": "active" if source else "not_initialized",
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get knowledge stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get knowledge stats")


@router.get("/health")
async def health_check():
    """Health check endpoint for RSS learning system"""
    try:
        rss_db = get_rss_database()
        rss_processor = get_feed_processor()
        
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
                "ai_analysis": "healthy",
                "knowledge_base": "healthy" if stats.get('knowledge_entries', 0) > 0 else "empty"
            },
            "metrics": {
                "sources": stats.get('total_sources', 0),
                "items": stats.get('total_items', 0),
                "processed_items": stats.get('processed_items', 0),
                "knowledge_entries": stats.get('knowledge_entries', 0)
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
