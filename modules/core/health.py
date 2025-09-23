"""
Health check module for Syntax Prime V2.
Database connectivity and system status verification.
"""

from typing import Dict, Any
from modules.core.database import db_manager
import asyncio
import time

#-- Section 1: Database Health Check - 9/23/25
async def check_database() -> Dict[str, Any]:
    """Check database connectivity and response time."""
    start_time = time.time()
    
    try:
        # Simple query to test connection
        result = await db_manager.execute_query("SELECT 1 as test")
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            "status": "healthy",
            "response_time_ms": response_time,
            "test_query": "passed"
        }
    
    except Exception as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "response_time_ms": response_time,
            "error": str(e)
        }

#-- Section 2: System Health Aggregation - 9/23/25
async def get_health_status() -> Dict[str, Any]:
    """Get complete system health status."""
    start_time = time.time()
    
    # Run health checks
    db_status = await check_database()
    
    # Determine overall status
    overall_status = "healthy" if db_status["status"] == "healthy" else "unhealthy"
    total_time = round((time.time() - start_time) * 1000, 2)
    
    return {
        "status": overall_status,
        "timestamp": time.time(),
        "total_check_time_ms": total_time,
        "services": {
            "database": db_status
        }
    }

#-- Section 3: Future Health Checks - 9/23/25
# Additional health check functions will be added here
# Examples: check_redis(), check_external_apis(), check_disk_space()