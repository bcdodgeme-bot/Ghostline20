#!/usr/bin/env python3
"""
Keyword Monitor Script - Orchestrates the complete Google Trends monitoring process

Workflow:
1. Expand keywords from database (4,586 → 15k-20k terms)
2. Monitor expanded keywords via Google Trends API
3. Apply low threshold detection for alerts
4. Store results and create opportunity alerts
5. Log comprehensive monitoring statistics

Designed for 2-3 times daily execution (morning, noon, evening)
"""

import asyncio
import asyncpg
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
import sys
import os

# Import our custom modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from .keyword_expander import KeywordExpander
from trends_client import GoogleTrendsClient
from database_manager import TrendsDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trends_monitoring.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class KeywordMonitor:
    """Orchestrates complete keyword monitoring workflow"""
    
    def __init__(self, database_url: str, mode: str = 'normal'):
        self.database_url = database_url
        self.mode = mode  # 'normal', 'fast', 'full'
        
        # Initialize components
        self.expander = KeywordExpander(database_url)
        self.trends_client = GoogleTrendsClient(database_url)
        self.database = TrendsDatabase(database_url)
        
        # Monitoring configuration based on mode
        self.config = self._get_monitoring_config(mode)
        
        # Statistics tracking
        self.stats = {
            'start_time': None,
            'end_time': None,
            'keywords_expanded': 0,
            'keywords_monitored': 0,
            'trends_fetched': 0,
            'alerts_created': 0,
            'errors': 0,
            'business_areas_processed': 0
        }
    
    def _get_monitoring_config(self, mode: str) -> Dict[str, Any]:
        """Get monitoring configuration based on mode"""
        configs = {
            'fast': {
                'keywords_per_area': 10,     # Quick test
                'expand_keywords': False,     # Use existing only
                'business_areas': ['tvsignals'],  # Single area
                'create_alerts': False,       # Testing only
                'description': 'Fast testing mode'
            },
            'normal': {
                'keywords_per_area': 50,      # Moderate monitoring
                'expand_keywords': True,      # Expand if needed
                'business_areas': None,       # All areas
                'create_alerts': True,        # Full functionality
                'description': 'Normal daily monitoring'
            },
            'full': {
                'keywords_per_area': 200,     # Comprehensive monitoring
                'expand_keywords': True,      # Always expand
                'business_areas': None,       # All areas
                'create_alerts': True,        # Full functionality
                'description': 'Full comprehensive monitoring'
            }
        }
        return configs.get(mode, configs['normal'])
    
    async def ensure_expanded_keywords_exist(self) -> bool:
        """Ensure expanded keywords table exists and has data"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Check if expanded keywords table exists and has data
            count = await conn.fetchval('''
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_name = 'expanded_keywords_for_trends'
            ''')
            
            if count == 0:
                logger.info("Creating expanded keywords table...")
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS expanded_keywords_for_trends (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        original_keyword VARCHAR(500) NOT NULL,
                        expanded_keyword VARCHAR(500) NOT NULL,
                        business_area VARCHAR(100) NOT NULL,
                        expansion_type VARCHAR(50),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        
                        UNIQUE(expanded_keyword, business_area)
                    );
                ''')
            
            # Check if we have expanded keywords data
            keyword_count = await conn.fetchval('''
                SELECT COUNT(*) FROM expanded_keywords_for_trends
            ''')
            
            if keyword_count == 0 and self.config['expand_keywords']:
                logger.info("No expanded keywords found, running expansion...")
                expanded_keywords = await self.expander.expand_all_keywords()
                await self.expander.save_expanded_keywords_to_database(expanded_keywords)
                self.stats['keywords_expanded'] = sum(len(keywords) for keywords in expanded_keywords.values())
                return True
            
            logger.info(f"Found {keyword_count} expanded keywords in database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to ensure expanded keywords exist: {e}")
            return False
        finally:
            await conn.close()
    
    async def get_monitoring_keywords(self, business_area: str, limit: int) -> List[str]:
        """Get keywords to monitor for a business area"""
        conn = await asyncpg.connect(self.database_url)
        
        try:
            # Try to get from expanded keywords first
            expanded_query = '''
                SELECT expanded_keyword 
                FROM expanded_keywords_for_trends 
                WHERE business_area = $1 
                ORDER BY created_at DESC
                LIMIT $2
            '''
            
            expanded_rows = await conn.fetch(expanded_query, business_area, limit)
            
            if expanded_rows:
                keywords = [row['expanded_keyword'] for row in expanded_rows]
                logger.info(f"Using {len(keywords)} expanded keywords for {business_area}")
                return keywords
            
            # Fallback to original keywords
            original_query = f'''
                SELECT keyword 
                FROM {business_area}_keywords 
                WHERE is_active = true 
                ORDER BY created_at DESC
                LIMIT $1
            '''
            
            original_rows = await conn.fetch(original_query, limit)
            keywords = [row['keyword'] for row in original_rows]
            logger.info(f"Using {len(keywords)} original keywords for {business_area}")
            
            return keywords
            
        finally:
            await conn.close()
    
    async def monitor_business_area(self, business_area: str) -> Dict[str, Any]:
        """Monitor trends for a specific business area"""
        area_stats = {
            'business_area': business_area,
            'keywords_monitored': 0,
            'trends_fetched': 0,
            'alerts_created': 0,
            'errors': 0,
            'top_trends': []
        }
        
        try:
            logger.info(f"Starting monitoring for {business_area}")
            
            # Get keywords to monitor
            keywords = await self.get_monitoring_keywords(
                business_area,
                self.config['keywords_per_area']
            )
            
            if not keywords:
                logger.warning(f"No keywords found for {business_area}")
                return area_stats
            
            area_stats['keywords_monitored'] = len(keywords)
            
            # Monitor keywords in batches
            batch_size = 5  # Google Trends limit
            trends_data = []
            
            for i in range(0, len(keywords), batch_size):
                batch = keywords[i:i + batch_size]
                
                try:
                    # Fetch trends for this batch
                    batch_results = await self.trends_client.fetch_trend_data(batch)
                    
                    # Process and save results
                    for keyword, trend_data in batch_results.items():
                        # Save to database
                        await self.database.save_trend_data(
                            keyword=trend_data.keyword,
                            business_area=business_area,
                            trend_score=trend_data.trend_score,
                            trend_momentum=trend_data.momentum,
                            regional_score=trend_data.regional_score,
                            trend_date=trend_data.trend_date
                        )
                        
                        trends_data.append(trend_data)
                        area_stats['trends_fetched'] += 1
                        
                        # Check for alert-worthy trends
                        if self.config['create_alerts']:
                            should_alert, reason = self.trends_client.should_create_alert(trend_data)
                            
                            if should_alert:
                                alert_id = await self.database.create_opportunity_alert(
                                    keyword=keyword,
                                    business_area=business_area,
                                    opportunity_type='content',
                                    urgency_level='medium' if trend_data.trend_score >= 30 else 'low',
                                    trend_momentum=trend_data.momentum,
                                    trend_score=trend_data.trend_score
                                )
                                
                                if alert_id:
                                    area_stats['alerts_created'] += 1
                                    logger.info(f"Alert created for {keyword}: {reason}")
                    
                    # Rate limiting delay
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    logger.error(f"Error processing batch {batch}: {e}")
                    area_stats['errors'] += 1
            
            # Get top trending keywords for this area
            if trends_data:
                sorted_trends = sorted(trends_data, key=lambda x: x.trend_score, reverse=True)
                area_stats['top_trends'] = [
                    {'keyword': t.keyword, 'score': t.trend_score, 'momentum': t.momentum}
                    for t in sorted_trends[:5]
                ]
            
            logger.info(f"Completed {business_area}: {area_stats['trends_fetched']} trends, {area_stats['alerts_created']} alerts")
            
        except Exception as e:
            logger.error(f"Failed to monitor {business_area}: {e}")
            area_stats['errors'] += 1
        
        return area_stats
    
    async def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Run a complete monitoring cycle"""
        self.stats['start_time'] = datetime.now()
        
        print(f"🚀 GOOGLE TRENDS MONITORING CYCLE - {self.config['description'].upper()}")
        print("=" * 70)
        print(f"Start time: {self.stats['start_time'].isoformat()}")
        print(f"Mode: {self.mode}")
        print(f"Keywords per area: {self.config['keywords_per_area']}")
        print(f"Create alerts: {self.config['create_alerts']}")
        print("=" * 70)
        
        try:
            # Ensure expanded keywords exist
            if not await self.ensure_expanded_keywords_exist():
                raise Exception("Failed to set up expanded keywords")
            
            # Get business areas to monitor
            if self.config['business_areas']:
                business_areas = self.config['business_areas']
            else:
                business_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
            
            # Monitor each business area
            area_results = []
            
            for area in business_areas:
                print(f"\n📊 Monitoring {area.upper()}...")
                
                area_stats = await self.monitor_business_area(area)
                area_results.append(area_stats)
                
                # Update global stats
                self.stats['keywords_monitored'] += area_stats['keywords_monitored']
                self.stats['trends_fetched'] += area_stats['trends_fetched']
                self.stats['alerts_created'] += area_stats['alerts_created']
                self.stats['errors'] += area_stats['errors']
                self.stats['business_areas_processed'] += 1
                
                print(f"   ✅ {area}: {area_stats['trends_fetched']} trends, {area_stats['alerts_created']} alerts")
                
                # Show top trends
                if area_stats['top_trends']:
                    print(f"   📈 Top trends:")
                    for trend in area_stats['top_trends'][:3]:
                        print(f"      • {trend['keyword']}: {trend['score']} ({trend['momentum']})")
            
            self.stats['end_time'] = datetime.now()
            duration = self.stats['end_time'] - self.stats['start_time']
            
            # Final summary
            print(f"\n🎯 MONITORING CYCLE COMPLETE")
            print("=" * 50)
            print(f"Duration: {duration}")
            print(f"Business areas: {self.stats['business_areas_processed']}")
            print(f"Keywords monitored: {self.stats['keywords_monitored']}")
            print(f"Trends fetched: {self.stats['trends_fetched']}")
            print(f"Alerts created: {self.stats['alerts_created']}")
            print(f"Errors: {self.stats['errors']}")
            
            # Request limit status
            requests_made = getattr(self.trends_client, 'requests_made_today', 0)
            request_limit = getattr(self.trends_client, 'daily_request_limit', 800)
            print(f"API requests: {requests_made}/{request_limit}")
            
            return {
                'success': True,
                'stats': self.stats,
                'area_results': area_results,
                'duration_seconds': duration.total_seconds()
            }
            
        except Exception as e:
            self.stats['end_time'] = datetime.now()
            logger.error(f"Monitoring cycle failed: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'stats': self.stats
            }
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring system status"""
        health = await self.database.health_check()
        
        # Get recent activity across all business areas
        business_summaries = {}
        business_areas = ['amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals']
        
        for area in business_areas:
            try:
                summary = await self.database.get_business_area_summary(area)
                business_summaries[area] = {
                    'keywords_monitored': summary.total_keywords_monitored,
                    'trending_keywords': summary.trending_keywords,
                    'alerts': summary.high_priority_alerts,
                    'avg_score': round(summary.avg_trend_score, 1)
                }
            except Exception as e:
                logger.error(f"Failed to get summary for {area}: {e}")
                business_summaries[area] = {'error': str(e)}
        
        return {
            'system_health': health,
            'business_summaries': business_summaries,
            'last_check': datetime.now().isoformat()
        }

async def main():
    """Main entry point for keyword monitoring"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Trends Keyword Monitoring')
    parser.add_argument('--mode', choices=['fast', 'normal', 'full'], default='fast',
                       help='Monitoring mode (default: fast)')
    parser.add_argument('--status', action='store_true',
                       help='Show monitoring status only')
    
    args = parser.parse_args()
    
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/syntaxprime_v2')
    monitor = KeywordMonitor(database_url, mode=args.mode)
    
    if args.status:
        print("📊 MONITORING STATUS")
        print("=" * 30)
        status = await monitor.get_monitoring_status()
        
        health = status['system_health']
        print(f"Database: {'✅' if health['database_connected'] else '❌'}")
        print(f"Recent trends (24h): {health['recent_trends_24h']}")
        print(f"Unprocessed alerts: {health['unprocessed_alerts']}")
        
        print(f"\n📈 Business Area Activity:")
        for area, summary in status['business_summaries'].items():
            if 'error' not in summary:
                print(f"   {area}: {summary['keywords_monitored']} keywords, {summary['trending_keywords']} trending")
            else:
                print(f"   {area}: Error - {summary['error']}")
    else:
        # Run monitoring cycle
        result = await monitor.run_monitoring_cycle()
        
        if result['success']:
            print("\n✅ Monitoring cycle completed successfully!")
        else:
            print(f"\n❌ Monitoring cycle failed: {result['error']}")

if __name__ == "__main__":
    asyncio.run(main())
    
