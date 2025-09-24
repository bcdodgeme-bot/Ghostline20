# modules/integrations/weather/health_monitor.py
"""
Health Monitor for Weather-Based Alerts
Pressure tracking for headaches and UV monitoring for sun sensitivity
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Monitor weather conditions for health impacts"""
    
    def __init__(self):
        # Health thresholds based on user requirements
        self.pressure_drop_threshold = 3.0  # mbar - headache trigger
        self.uv_protection_threshold = 4.0  # UV index - sun sensitivity
        self.severe_uv_threshold = 8.0      # UV index - stay indoors
    
    async def get_pressure_history(self, user_id: str, hours_back: int = 3) -> Optional[float]:
        """Get pressure reading from X hours ago"""
        query = """
        SELECT pressure_surface_level 
        FROM weather_readings 
        WHERE user_id = $1 
        AND timestamp <= NOW() - INTERVAL '%s hours'
        ORDER BY timestamp DESC 
        LIMIT 1;
        """ % hours_back
        
        try:
            result = await db_manager.fetch_one(query, user_id)
            return float(result['pressure_surface_level']) if result else None
        except Exception as e:
            logger.error(f"Failed to get pressure history: {e}")
            return None
    
    def calculate_health_risks(self, uv_index: float, pressure_change_3h: Optional[float]) -> Tuple[str, str]:
        """Calculate headache and UV risk levels"""
        
        # UV risk calculation (user's sun sensitivity threshold is 4.0)
        if uv_index >= self.severe_uv_threshold:
            uv_risk = "very_high"
        elif uv_index >= 6:
            uv_risk = "high" 
        elif uv_index >= self.uv_protection_threshold:
            uv_risk = "moderate"
        elif uv_index >= 1:
            uv_risk = "low"
        else:
            uv_risk = "minimal"
        
        # Headache risk calculation based on pressure drop
        if pressure_change_3h and pressure_change_3h <= -self.pressure_drop_threshold:
            headache_risk = "high"
        elif pressure_change_3h and pressure_change_3h <= -1.5:
            headache_risk = "moderate"
        else:
            headache_risk = "low"
        
        return headache_risk, uv_risk
    
    def generate_health_alerts(self, weather_data: dict, headache_risk: str, uv_risk: str) -> List[str]:
        """Generate health alert messages"""
        alerts = []
        
        # Pressure-based headache alerts
        pressure_change = weather_data.get('pressure_change_3h')
        if headache_risk == "high":
            alerts.append(f"HEADACHE ALERT: Significant pressure drop detected ({pressure_change:.1f} mbar)")
        elif headache_risk == "moderate":
            alerts.append(f"Moderate headache risk: Pressure dropping ({pressure_change:.1f} mbar)")
        
        # UV-based sun protection alerts
        uv_index = weather_data.get('uv_index', 0)
        if uv_risk == "very_high":
            alerts.append(f"EXTREME UV WARNING: Stay indoors (UV {uv_index})")
        elif uv_risk == "high":
            alerts.append(f"HIGH UV ALERT: Full sun protection required (UV {uv_index})")
        elif uv_risk == "moderate":
            alerts.append(f"UV Protection needed: Use sunscreen (UV {uv_index})")
        
        return alerts