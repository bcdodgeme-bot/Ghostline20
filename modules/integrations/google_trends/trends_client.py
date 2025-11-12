#!/usr/bin/env python3
"""
Google Trends Client for Syntax Prime V2
Monitors expanded keywords with smart rate limiting and low thresholds

Key Features:
- Smart rate limiting (45% under Google's limits)
- Batch processing for efficiency
- Low threshold detection (learned from TV signals issue)
- Regional focus (US/Virginia)
- Momentum detection for trend alerts
"""

import asyncio
import asyncpg
from pytrends.request import TrendReq
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, date
import time
import random
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TrendData:
    """Container for trend information"""
    keyword: str
    business_area: str
    trend_score: int
    trend_date: date
    momentum: str
    regional_score: Optional[int] = None
    raw_data: Optional[Dict] = None

class GoogleTrendsClient:
    """Smart Google Trends monitoring with rate limiting and low thresholds"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pytrends = None
        
        # Rate limiting - 45% under Google's limits for safety
        self.batch_size = 5  # Keywords per request (Google allows up to 5)
        self.request_delay = 3.0  # 3 seconds between requests (45% under typical limits)
        self.daily_request_limit = 800  # Conservative daily limit
        self.requests_made_today = 0
        
        # Low threshold settings (learned from TV signals missing events)
        self.alert_thresholds = {
            'rising': 15,      # Score increase of 15+ points
            'breakout': 25,    # Sudden spike of 25+ points
            'stable_high': 40, # Sustained score of 40+
            'momentum': 20     # Any score of 20+ (very low threshold)
        }
        
        # Regional settings
        self.primary_region = 'US'
        self.virginia_region = 'US-VA'  # Virginia-specific trends
        
    async def initialize_client(self):
        """Initialize pytrends client with proper settings"""
        try:
            self.pytrends = TrendReq(
                hl='en-US',  # Language
                tz=300,      # Eastern Time Zone (Virginia)
                timeout=(10, 25),  # Connection and read timeouts
            )
            logger.info("Google Trends client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Google Trends client: {e}")
            return False
    
    async def smart_delay(self):
        """Smart delay between requests with jitter"""
        # Add random jitter to avoid detection patterns
        jitter = random.uniform(0.5, 1.5)
        delay = self.request_delay * jitter
        await asyncio.sleep(delay)
    
    async def fetch_trend_data(self, keywords: List[str], timeframe: str = 'today 3-m') -> Dict[str, TrendData]:
        """Fetch trend data for a batch of keywords"""
        if not self.pytrends:
            if not await self.initialize_client():
                return {}
        
        try:
            # Check rate limiting
            if self.requests_made_today >= self.daily_request_limit:
                logger.warning("Daily request limit reached, skipping request")
                return {}
            
            # Build the query - limit to 5 keywords per request
            query_keywords = keywords[:self.batch_size]
            
            logger.info(f"Fetching trends for: {', '.join(query_keywords)}")
            
            # Build payload for pytrends
            self.pytrends.build_payload(
                kw_list=query_keywords,
                cat=0,  # All categories
                timeframe=timeframe,
                geo=self.primary_region,  # US trends
                gprop=''  # Web search
            )
            
            # Get interest over time data
            interest_data = self.pytrends.interest_over_time()
            
            # Get interest by region (for Virginia focus)
            try:
                region_data = self.pytrends.interest_by_region(
                    resolution='REGION',
                    inc_low_vol=True,
                    inc_geo_code=True
                )
            except:
                region_data = pd.DataFrame()  # Fallback if region data fails
            
            self.requests_made_today += 1
            
            # Process the data
            trend_results = {}
            
            if not interest_data.empty:
                # Get the latest date's data
                latest_date = interest_data.index[-1].date()
                
                for keyword in query_keywords:
                    if keyword in interest_data.columns:
                        # Get recent trend scores
                        recent_scores = interest_data[keyword].tail(7).tolist()  # Last 7 data points
                        current_score = recent_scores[-1] if recent_scores else 0
                        
                        # Calculate momentum
                        momentum = self.calculate_momentum(recent_scores)
                        
                        # Get Virginia-specific score if available
                        virginia_score = None
                        if not region_data.empty and keyword in region_data.columns:
                            # Look for Virginia in the regional data
                            virginia_row = region_data[region_data.index.str.contains('Virginia', case=False, na=False)]
                            if not virginia_row.empty:
                                virginia_score = virginia_row[keyword].iloc[0]
                        
                        trend_results[keyword] = TrendData(
                            keyword=keyword,
                            business_area='',  # Will be set by caller
                            trend_score=int(current_score),
                            trend_date=latest_date,
                            momentum=momentum,
                            regional_score=int(virginia_score) if virginia_score else None,
                            raw_data={
                                'recent_scores': recent_scores,
                                'timeframe': timeframe
                            }
                        )
            
            await self.smart_delay()  # Rate limiting delay
            return trend_results
            
        except Exception as e:
            logger.error(f"Error fetching trend data for {keywords}: {e}")
            await asyncio.sleep(5)  # Extra delay on error
            return {}
    
    def calculate_momentum(self, scores: List[float]) -> str:
        """Calculate trend momentum from score history"""
        if len(scores) < 2:
            return 'unknown'
        
        # Remove any NaN values
        clean_scores = [s for s in scores if pd.notna(s)]
        if len(clean_scores) < 2:
            return 'unknown'
        
        current = clean_scores[-1]
        previous = clean_scores[-2]
        
        # Calculate change
        change = current - previous
        change_percent = (change / previous * 100) if previous > 0 else 0
        
        # Momentum classification with LOW thresholds
        if change >= self.alert_thresholds['breakout']:
            return 'breakout'
        elif change >= self.alert_thresholds['rising']:
            return 'rising'
        elif change <= -15:
            return 'declining'
        elif current >= self.alert_thresholds['stable_high']:
            return 'stable_high'
        elif current >= self.alert_thresholds['momentum']:
            return 'stable'
        else:
            return 'low'
    
    def should_create_alert(self, trend_data: TrendData) -> Tuple[bool, str]:
        """Determine if trend should trigger an alert (LOW thresholds)"""
        score = trend_data.trend_score
        momentum = trend_data.momentum
        
        # Very low thresholds to catch everything (learned from TV signals)
        alert_conditions = [
            (momentum == 'breakout', 'Breakout trend detected'),
            (momentum == 'rising', 'Rising trend detected'),
            (momentum == 'stable_high', 'High sustained interest'),
            (score >= self.alert_thresholds['momentum'], f'Significant interest ({score} points)'),
            (trend_data.regional_score and trend_data.regional_score >= 30, 'High Virginia interest'),
        ]
        
        for condition, reason in alert_conditions:
            if condition:
                return True, reason
        
        return False, ''
    
    async def save_trend_data(self, trend_data: TrendData, business_area: str):
        """Save trend data to database"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Update business area
            trend_data.business_area = business_area
            
            # Insert into trend_monitoring table
            await conn.execute('''
                INSERT INTO trend_monitoring 
                (keyword, business_area, trend_score, trend_date, trend_momentum,
                 regional_score, region, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                ON CONFLICT (keyword, business_area, trend_date, region) 
                DO UPDATE SET 
                    trend_score = EXCLUDED.trend_score,
                    trend_momentum = EXCLUDED.trend_momentum,
                    regional_score = EXCLUDED.regional_score,
                    updated_at = NOW()
            ''', 
                trend_data.keyword,
                trend_data.business_area,
                trend_data.trend_score,
                trend_data.trend_date,
                trend_data.momentum,
                trend_data.regional_score,
                self.primary_region
            )
            
            # Check if this should create an opportunity alert
            should_alert, alert_reason = self.should_create_alert(trend_data)
            
            if should_alert:
                await self.create_opportunity_alert(conn, trend_data, alert_reason)
            
        finally:
            await conn.close()
    
    async def create_opportunity_alert(self, conn, trend_data: TrendData, reason: str):
        """Create a trend opportunity alert"""
        try:
            # Determine urgency based on momentum and score
            if trend_data.momentum == 'breakout' or trend_data.trend_score >= 50:
                urgency = 'high'
            elif trend_data.momentum == 'rising' or trend_data.trend_score >= 30:
                urgency = 'medium'
            else:
                urgency = 'low'
            
            # Determine opportunity type
            if trend_data.momentum in ['breakout', 'rising']:
                opp_type = 'breaking_news'
            elif trend_data.trend_score >= 40:
                opp_type = 'content'
            else:
                opp_type = 'social'
            
            # Calculate content window (24-72 hours for trending topics)
            window_start = datetime.now()
            if urgency == 'high':
                window_end = window_start + timedelta(hours=24)
            elif urgency == 'medium':
                window_end = window_start + timedelta(hours=48)
            else:
                window_end = window_start + timedelta(hours=72)
            
            await conn.execute('''
                INSERT INTO trend_opportunities 
                (keyword, business_area, opportunity_type, urgency_level, trend_momentum,
                 alert_threshold_met, trend_score_at_alert, 
                 optimal_content_window_start, optimal_content_window_end,
                 created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                ON CONFLICT DO NOTHING
            ''',
                trend_data.keyword,
                trend_data.business_area,
                opp_type,
                urgency,
                trend_data.momentum,
                True,
                trend_data.trend_score,
                window_start,
                window_end
            )
            
            logger.info(f"🚨 ALERT: {trend_data.keyword} ({trend_data.business_area}) - {reason}")
            
        except Exception as e:
            logger.error(f"Failed to create opportunity alert: {e}")
    
    async def monitor_business_area_keywords(self, business_area: str, limit: int = 50):
        """Monitor keywords for a specific business area"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Get expanded keywords for this business area
            query = '''
                SELECT DISTINCT expanded_keyword 
                FROM expanded_keywords_for_trends 
                WHERE business_area = $1 
                ORDER BY created_at DESC
                LIMIT $2
            '''
            
            rows = await conn.fetch(query, business_area, limit)
            keywords = [row['expanded_keyword'] for row in rows]
            
            if not keywords:
                logger.warning(f"No expanded keywords found for {business_area}")
                return
            
            logger.info(f"Monitoring {len(keywords)} keywords for {business_area}")
            
            # Process keywords in batches
            for i in range(0, len(keywords), self.batch_size):
                batch = keywords[i:i + self.batch_size]
                
                logger.info(f"Processing batch {i//self.batch_size + 1}: {batch}")
                
                # Fetch trend data for this batch
                trend_results = await self.fetch_trend_data(batch)
                
                # Save results to database
                for keyword, trend_data in trend_results.items():
                    await self.save_trend_data(trend_data, business_area)
                
                # Rate limiting between batches
                if i + self.batch_size < len(keywords):
                    await self.smart_delay()
            
        finally:
            await conn.close()
    
    async def monitor_all_business_areas(self, keywords_per_area: int = 25):
        """Monitor keywords across all business areas"""
        print("🚀 STARTING GOOGLE TRENDS MONITORING")
        print("=" * 50)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Keywords per area: {keywords_per_area}")
        print(f"Alert thresholds: {self.alert_thresholds}")
        print("=" * 50)
        
        business_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
        
        for area in business_areas:
            print(f"\n📊 Monitoring {area.upper()}...")
            try:
                await self.monitor_business_area_keywords(area, keywords_per_area)
                print(f"✅ {area} monitoring complete")
            except Exception as e:
                print(f"❌ {area} monitoring failed: {e}")
                logger.error(f"Failed to monitor {area}: {e}")
        
        print(f"\n🎯 Monitoring complete! Requests made today: {self.requests_made_today}")
        print(f"   Rate limit status: {self.requests_made_today}/{self.daily_request_limit}")

async def main():
    """Test the Google Trends client"""
    import os
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
    
    client = GoogleTrendsClient(database_url)
    
    # Test single business area first
    print("🧪 TESTING GOOGLE TRENDS CLIENT")
    print("=" * 40)
    
    # Monitor just TV signals to start (smallest keyword set)
    await client.monitor_business_area_keywords('tvsignals', limit=10)

if __name__ == "__main__":
    # Install pytrends if not already installed
    try:
        import pytrends
    except ImportError:
        print("📦 Installing pytrends...")
        import subprocess
        subprocess.check_call(['pip', 'install', 'pytrends'])
    
    asyncio.run(main())
