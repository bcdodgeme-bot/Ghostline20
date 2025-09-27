#!/usr/bin/env python3
"""
FastAPI Router for Google Trends Integration
Provides API endpoints for the Google Trends monitoring system
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import os

from .database_manager import TrendsDatabase
from .opportunity_detector import OpportunityDetector
from .opportunity_training import OpportunityTraining
from .keyword_monitor import KeywordMonitor
from .integration_info import check_module_health, get_system_statistics, get_integration_info

logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter()

# Database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')

# ============================================================================
# HEALTH AND STATUS ENDPOINTS
# ============================================================================

@router.get("/health")
async def health_check():
    """Get Google Trends module health status"""
    try:
        health_status = await check_module_health()
        return {
            "status": "healthy" if health_status["healthy"] else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "details": health_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check error: {str(e)}")

@router.get("/info")
async def integration_info():
    """Get comprehensive integration information"""
    try:
        info = await get_integration_info()
        return info
    except Exception as e:
        logger.error(f"Integration info failed: {e}")
        raise HTTPException(status_code=500, detail=f"Integration info error: {str(e)}")

@router.get("/statistics")
async def system_statistics():
    """Get comprehensive system statistics"""
    try:
        stats = await get_system_statistics()
        return {
            "timestamp": datetime.now().isoformat(),
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"Statistics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics error: {str(e)}")

# ============================================================================
# TREND MONITORING ENDPOINTS
# ============================================================================

@router.get("/trends/recent")
async def get_recent_trends(
    business_area: Optional[str] = Query(None, description="Filter by business area"),
    days: int = Query(7, description="Number of days to look back"),
    limit: int = Query(50, description="Maximum number of results")
):
    """Get recent trend data"""
    try:
        db = TrendsDatabase(DATABASE_URL)
        trends = await db.get_recent_trends(business_area=business_area, days=days, limit=limit)
        
        return {
            "business_area": business_area,
            "days": days,
            "count": len(trends),
            "trends": trends
        }
    except Exception as e:
        logger.error(f"Recent trends retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Trends retrieval error: {str(e)}")

@router.get("/trends/business/{business_area}")
async def get_business_trends(
    business_area: str,
    min_score: int = Query(20, description="Minimum trend score"),
    days: int = Query(3, description="Number of days to look back")
):
    """Get trending keywords for a specific business area"""
    try:
        # Validate business area
        valid_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
        if business_area not in valid_areas:
            raise HTTPException(status_code=400, detail=f"Invalid business area. Must be one of: {valid_areas}")
        
        db = TrendsDatabase(DATABASE_URL)
        trends = await db.get_trending_keywords(business_area=business_area, min_score=min_score, days=days)
        
        return {
            "business_area": business_area,
            "min_score": min_score,
            "days": days,
            "count": len(trends),
            "trending_keywords": trends
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Business trends retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Business trends error: {str(e)}")

# ============================================================================
# OPPORTUNITY ENDPOINTS
# ============================================================================

@router.get("/opportunities/current")
async def get_current_opportunities(
    business_area: Optional[str] = Query(None, description="Filter by business area"),
    hours_lookback: int = Query(24, description="Hours to look back for opportunities")
):
    """Get current content opportunities"""
    try:
        if business_area:
            valid_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
            if business_area not in valid_areas:
                raise HTTPException(status_code=400, detail=f"Invalid business area. Must be one of: {valid_areas}")
        
        detector = OpportunityDetector(DATABASE_URL)
        opportunities = await detector.detect_current_opportunities(
            business_area=business_area, 
            hours_lookback=hours_lookback
        )
        
        # Convert opportunities to dictionaries for JSON response
        opportunity_dicts = []
        for opp in opportunities:
            opportunity_dicts.append({
                "keyword": opp.keyword,
                "business_area": opp.business_area,
                "opportunity_type": opp.opportunity_type.value,
                "urgency_level": opp.urgency_level.value,
                "trend_score": opp.trend_score,
                "opportunity_score": opp.opportunity_score,
                "business_relevance": opp.business_relevance,
                "content_window_start": opp.content_window_start.isoformat(),
                "content_window_end": opp.content_window_end.isoformat(),
                "reasoning": opp.reasoning,
                "suggested_content_types": opp.suggested_content_types,
                "competitor_advantage": opp.competitor_advantage
            })
        
        return {
            "business_area": business_area,
            "hours_lookback": hours_lookback,
            "count": len(opportunity_dicts),
            "opportunities": opportunity_dicts
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Current opportunities retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Opportunities error: {str(e)}")

@router.get("/opportunities/active")
async def get_active_opportunities(
    business_area: Optional[str] = Query(None, description="Filter by business area"),
    urgency_filter: Optional[str] = Query(None, description="Filter by urgency level")
):
    """Get active opportunities from database"""
    try:
        if business_area:
            valid_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
            if business_area not in valid_areas:
                raise HTTPException(status_code=400, detail=f"Invalid business area. Must be one of: {valid_areas}")
        
        if urgency_filter:
            valid_urgency = ['critical', 'high', 'medium', 'low']
            if urgency_filter not in valid_urgency:
                raise HTTPException(status_code=400, detail=f"Invalid urgency level. Must be one of: {valid_urgency}")
        
        detector = OpportunityDetector(DATABASE_URL)
        
        # Convert urgency filter to enum if provided
        urgency_enum = None
        if urgency_filter:
            from .opportunity_detector import UrgencyLevel
            urgency_enum = UrgencyLevel(urgency_filter)
        
        opportunities = await detector.get_active_opportunities(
            business_area=business_area,
            urgency_filter=urgency_enum
        )
        
        # Convert opportunities to dictionaries
        opportunity_dicts = []
        for opp in opportunities:
            opportunity_dicts.append({
                "id": opp.id,
                "keyword": opp.keyword,
                "business_area": opp.business_area,
                "opportunity_type": opp.opportunity_type.value,
                "urgency_level": opp.urgency_level.value,
                "trend_score": opp.trend_score,
                "content_window_start": opp.content_window_start.isoformat(),
                "content_window_end": opp.content_window_end.isoformat(),
                "created_at": opp.created_at.isoformat(),
                "processed": opp.processed,
                "user_feedback": opp.user_feedback
            })
        
        return {
            "business_area": business_area,
            "urgency_filter": urgency_filter,
            "count": len(opportunity_dicts),
            "opportunities": opportunity_dicts
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Active opportunities retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Active opportunities error: {str(e)}")

# ============================================================================
# TRAINING ENDPOINTS
# ============================================================================

@router.get("/training/pending")
async def get_pending_training_opportunities(
    limit: int = Query(5, description="Maximum number of opportunities to return")
):
    """Get opportunities pending training feedback"""
    try:
        trainer = OpportunityTraining(DATABASE_URL)
        opportunities = await trainer.get_pending_opportunities(limit=limit)
        
        return {
            "count": len(opportunities),
            "opportunities": opportunities
        }
    except Exception as e:
        logger.error(f"Pending training opportunities retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Training opportunities error: {str(e)}")

@router.post("/training/feedback")
async def submit_training_feedback(
    opportunity_id: str = Body(..., description="Opportunity ID"),
    feedback: str = Body(..., description="Feedback type: good_match or bad_match"),
    feedback_details: Optional[str] = Body(None, description="Additional feedback details")
):
    """Submit training feedback for an opportunity"""
    try:
        # Validate feedback type
        valid_feedback = ['good_match', 'bad_match']
        if feedback not in valid_feedback:
            raise HTTPException(status_code=400, detail=f"Invalid feedback. Must be one of: {valid_feedback}")
        
        trainer = OpportunityTraining(DATABASE_URL)
        success = await trainer.submit_feedback(
            opportunity_id=opportunity_id,
            feedback=feedback,
            feedback_details=feedback_details
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to submit feedback")
        
        return {
            "success": True,
            "opportunity_id": opportunity_id,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Training feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Feedback submission error: {str(e)}")

@router.get("/training/statistics")
async def get_training_statistics():
    """Get training statistics and progress"""
    try:
        trainer = OpportunityTraining(DATABASE_URL)
        stats = await trainer.get_training_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "training_statistics": stats
        }
    except Exception as e:
        logger.error(f"Training statistics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Training statistics error: {str(e)}")

# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@router.post("/monitoring/run")
async def run_monitoring_cycle(
    mode: str = Body("fast", description="Monitoring mode: fast, normal, or full")
):
    """Run a monitoring cycle"""
    try:
        valid_modes = ['fast', 'normal', 'full']
        if mode not in valid_modes:
            raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")
        
        monitor = KeywordMonitor(DATABASE_URL, mode=mode)
        result = await monitor.run_monitoring_cycle()
        
        return {
            "monitoring_mode": mode,
            "timestamp": datetime.now().isoformat(),
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Monitoring cycle failed: {e}")
        raise HTTPException(status_code=500, detail=f"Monitoring cycle error: {str(e)}")

@router.get("/monitoring/status")
async def get_monitoring_status():
    """Get current monitoring system status"""
    try:
        monitor = KeywordMonitor(DATABASE_URL)
        status = await monitor.get_monitoring_status()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_status": status
        }
    except Exception as e:
        logger.error(f"Monitoring status retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Monitoring status error: {str(e)}")

# ============================================================================
# BUSINESS AREA ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/analysis/business/{business_area}")
async def get_business_analysis(
    business_area: str,
    days: int = Query(7, description="Number of days to analyze")
):
    """Get comprehensive business area analysis"""
    try:
        # Validate business area
        valid_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
        if business_area not in valid_areas:
            raise HTTPException(status_code=400, detail=f"Invalid business area. Must be one of: {valid_areas}")
        
        db = TrendsDatabase(DATABASE_URL)
        summary = await db.get_business_area_summary(business_area=business_area, days=days)
        
        return {
            "business_area": business_area,
            "analysis_period_days": days,
            "timestamp": datetime.now().isoformat(),
            "analysis": {
                "total_keywords_monitored": summary.total_keywords_monitored,
                "trending_keywords": summary.trending_keywords,
                "high_priority_alerts": summary.high_priority_alerts,
                "recent_opportunities": summary.recent_opportunities,
                "avg_trend_score": summary.avg_trend_score,
                "top_keywords": summary.top_keywords
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Business analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Business analysis error: {str(e)}")

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Google Trends Integration API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/health",
            "info": "/info", 
            "statistics": "/statistics",
            "trends": "/trends/*",
            "opportunities": "/opportunities/*",
            "training": "/training/*",
            "monitoring": "/monitoring/*",
            "analysis": "/analysis/*"
        }
    }