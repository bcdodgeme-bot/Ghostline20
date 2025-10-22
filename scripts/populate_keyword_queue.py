#!/usr/bin/env python3
"""
Keyword Queue Population Script
Intelligently populates keyword_monitoring_queue from 51,474 expanded keywords
"""

import asyncio
import asyncpg
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging
import os
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KeywordQueuePopulator:
    """Populate keyword monitoring queue with prioritized keywords"""
    
    # Business area priority weights (1-10 scale)
    BUSINESS_PRIORITIES = {
        'bcdodge': 9,      # Personal blog, AI drafts allowed
        'damnitcarl': 8,   # Emotional support cat
        'tvsignals': 7,    # Streaming content, AI drafts allowed
        'roseandangel': 6, # Consulting, human-only
        'mealsnfeelz': 5   # Food programs, sensitive, human-only
    }
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.stats = {
            'keywords_evaluated': 0,
            'keywords_queued': 0,
            'by_business_area': {}
        }
    
    async def get_connection(self):
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    async def calculate_keyword_score(
        self,
        keyword: str,
        business_area: str,
        conn: asyncpg.Connection
    ) -> float:
        """
        Calculate priority score for a keyword (0-100 scale)
        
        Score components:
        - Base business priority (0-45 points): Business area importance
        - Keyword specificity (0-25 points): Longer/more specific = higher
        - Historical performance (0-30 points): Past trend success
        """
        
        # Component 1: Business area priority (0-45 points)
        business_weight = self.BUSINESS_PRIORITIES.get(business_area, 5)
        business_score = (business_weight / 10) * 45
        
        # Component 2: Keyword specificity (0-25 points)
        # Longer, more specific keywords are more valuable
        word_count = len(keyword.split())
        char_length = len(keyword)
        
        specificity_score = 0
        if word_count >= 4:
            specificity_score = 25
        elif word_count == 3:
            specificity_score = 20
        elif word_count == 2:
            specificity_score = 15
        else:
            specificity_score = 10
        
        # Bonus for reasonable length (not too short, not too long)
        if 20 <= char_length <= 60:
            specificity_score += 5
        
        # Cap at 25
        specificity_score = min(25, specificity_score)
        
        # Component 3: Historical performance (0-30 points)
        historical_score = await self._get_historical_performance(keyword, business_area, conn)
        
        # Total score (0-100)
        total_score = business_score + specificity_score + historical_score
        
        return round(total_score, 2)
    
    async def _get_historical_performance(
        self,
        keyword: str,
        business_area: str,
        conn: asyncpg.Connection
    ) -> float:
        """
        Check if keyword has trended before and calculate historical score
        Returns 0-30 points based on past performance
        """
        try:
            # Check trend_monitoring table for past performance
            query = '''
                SELECT 
                    COUNT(*) as trend_count,
                    AVG(trend_score) as avg_score,
                    MAX(trend_score) as max_score,
                    MAX(trend_date) as last_trend_date
                FROM trend_monitoring
                WHERE keyword = $1 AND business_area = $2
                AND trend_date >= NOW() - INTERVAL '90 days'
            '''
            
            result = await conn.fetchrow(query, keyword, business_area)
            
            if not result or result['trend_count'] == 0:
                return 0  # No historical data
            
            trend_count = result['trend_count']
            avg_score = result['avg_score'] or 0
            max_score = result['max_score'] or 0
            last_trend_date = result['last_trend_date']
            
            # Calculate historical score
            score = 0
            
            # Points for trending frequency (0-10 points)
            if trend_count >= 10:
                score += 10
            elif trend_count >= 5:
                score += 7
            elif trend_count >= 2:
                score += 5
            else:
                score += 2
            
            # Points for average trend strength (0-10 points)
            if avg_score >= 50:
                score += 10
            elif avg_score >= 30:
                score += 7
            elif avg_score >= 20:
                score += 5
            else:
                score += 2
            
            # Points for peak performance (0-10 points)
            if max_score >= 80:
                score += 10
            elif max_score >= 60:
                score += 7
            elif max_score >= 40:
                score += 5
            else:
                score += 2
            
            return min(30, score)  # Cap at 30 points
            
        except Exception as e:
            logger.warning(f"Error checking historical performance for '{keyword}': {e}")
            return 0
    
    async def get_prioritized_keywords(
        self,
        limit: int = 500,
        business_area: Optional[str] = None,
        priority_min: float = 0,
        balanced: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get prioritized keywords from expanded_keywords_for_trends
        
        Args:
            limit: Maximum number of keywords to return
            business_area: Filter by specific business area
            priority_min: Minimum priority score (0-100)
            balanced: If True, ensure fair distribution across business areas
        
        Returns:
            List of keyword dicts with scores
        """
        conn = await self.get_connection()
        
        try:
            if balanced and not business_area:
                # Get balanced distribution across all business areas
                return await self._get_balanced_keywords(limit, priority_min, conn)
            
            # Original logic: pure priority-based selection
            # Build query based on filters
            query = '''
                SELECT 
                    expanded_keyword,
                    business_area,
                    original_keyword,
                    expansion_type,
                    created_at
                FROM expanded_keywords_for_trends
                WHERE business_area != 'amcf'
            '''
            
            params = []
            if business_area:
                query += ' AND business_area = $1'
                params.append(business_area)
            
            query += ' ORDER BY created_at DESC'
            
            rows = await conn.fetch(query, *params)
            
            logger.info(f"Evaluating {len(rows)} expanded keywords...")
            
            # Score all keywords
            scored_keywords = []
            for i, row in enumerate(rows):
                keyword = row['expanded_keyword']
                area = row['business_area']
                
                score = await self.calculate_keyword_score(keyword, area, conn)
                
                if score >= priority_min:
                    scored_keywords.append({
                        'keyword': keyword,
                        'business_area': area,
                        'original_keyword': row['original_keyword'],
                        'expansion_type': row['expansion_type'],
                        'priority_score': score
                    })
                
                self.stats['keywords_evaluated'] += 1
                
                # Progress update every 1000 keywords
                if (i + 1) % 1000 == 0:
                    logger.info(f"Evaluated {i + 1}/{len(rows)} keywords...")
            
            # Sort by priority score (highest first)
            scored_keywords.sort(key=lambda x: x['priority_score'], reverse=True)
            
            # Limit results
            return scored_keywords[:limit]
            
        finally:
            await conn.close()
    
    async def _get_balanced_keywords(
        self,
        limit: int,
        priority_min: float,
        conn: asyncpg.Connection
    ) -> List[Dict[str, Any]]:
        """
        Get keywords with balanced distribution across business areas
        Ensures each area gets representation in the final queue
        """
        business_areas = list(self.BUSINESS_PRIORITIES.keys())
        
        # Calculate keywords per area (weighted by priority)
        total_priority = sum(self.BUSINESS_PRIORITIES.values())
        keywords_per_area = {}
        
        for area in business_areas:
            priority = self.BUSINESS_PRIORITIES[area]
            # Allocate keywords proportional to priority
            allocation = int((priority / total_priority) * limit)
            keywords_per_area[area] = max(1, allocation)  # At least 1 keyword per area
        
        # Adjust to ensure we hit the limit exactly
        total_allocated = sum(keywords_per_area.values())
        if total_allocated < limit:
            # Give remaining to highest priority area
            highest_priority_area = max(business_areas, key=lambda x: self.BUSINESS_PRIORITIES[x])
            keywords_per_area[highest_priority_area] += (limit - total_allocated)
        
        logger.info(f"Balanced allocation: {keywords_per_area}")
        
        # Get top keywords for each business area
        all_keywords = []
        
        for area in business_areas:
            area_limit = keywords_per_area[area]
            
            query = '''
                SELECT 
                    expanded_keyword,
                    business_area,
                    original_keyword,
                    expansion_type,
                    created_at
                FROM expanded_keywords_for_trends
                WHERE business_area = $1
                ORDER BY created_at DESC
            '''
            
            rows = await conn.fetch(query, area)
            
            logger.info(f"Evaluating {len(rows)} keywords for {area}...")
            
            # Score keywords for this area
            scored_keywords = []
            for row in rows:
                keyword = row['expanded_keyword']
                score = await self.calculate_keyword_score(keyword, area, conn)
                
                if score >= priority_min:
                    scored_keywords.append({
                        'keyword': keyword,
                        'business_area': area,
                        'original_keyword': row['original_keyword'],
                        'expansion_type': row['expansion_type'],
                        'priority_score': score
                    })
                
                self.stats['keywords_evaluated'] += 1
            
            # Sort by score and take top N for this area
            scored_keywords.sort(key=lambda x: x['priority_score'], reverse=True)
            all_keywords.extend(scored_keywords[:area_limit])
        
        # Final sort by priority across all areas
        all_keywords.sort(key=lambda x: x['priority_score'], reverse=True)
        
        return all_keywords
    
    async def populate_queue(
        self,
        keywords: List[Dict[str, Any]],
        stagger_hours: int = 24
    ) -> int:
        """
        Populate keyword_monitoring_queue with prioritized keywords
        
        Args:
            keywords: List of keyword dicts with scores
            stagger_hours: Spread check times across this many hours
        
        Returns:
            Number of keywords successfully queued
        """
        conn = await self.get_connection()
        
        try:
            now = datetime.utcnow()
            queued_count = 0
            
            # Stagger check times across the specified hours
            for i, kw in enumerate(keywords):
                # Calculate next_check_at with staggered timing
                stagger_minutes = (i * (stagger_hours * 60)) // len(keywords)
                next_check = now + timedelta(minutes=stagger_minutes)
                
                # Convert 0-100 priority score to 1-10 scale for database
                # Database requires monitoring_priority to be INTEGER between 1-10
                priority_100_scale = kw['priority_score']
                monitoring_priority = max(1, min(10, int(priority_100_scale / 10)))
                
                # Calculate check frequency based on priority
                # High priority = more frequent checks
                if priority_100_scale >= 70:
                    check_frequency_minutes = 240  # Every 4 hours
                elif priority_100_scale >= 50:
                    check_frequency_minutes = 480  # Every 8 hours
                elif priority_100_scale >= 30:
                    check_frequency_minutes = 720  # Every 12 hours
                else:
                    check_frequency_minutes = 1440  # Daily
                
                try:
                    query = '''
                        INSERT INTO keyword_monitoring_queue (
                            base_keyword,
                            expanded_keyword,
                            business_area,
                            monitoring_priority,
                            next_check_at,
                            check_frequency_minutes
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (expanded_keyword, business_area) 
                        DO UPDATE SET
                            monitoring_priority = EXCLUDED.monitoring_priority,
                            next_check_at = EXCLUDED.next_check_at,
                            check_frequency_minutes = EXCLUDED.check_frequency_minutes,
                            updated_at = NOW()
                    '''
                    
                    await conn.execute(
                        query,
                        kw['original_keyword'],
                        kw['keyword'],
                        kw['business_area'],
                        monitoring_priority,  # Now using 1-10 scale
                        next_check,
                        check_frequency_minutes
                    )
                    
                    queued_count += 1
                    
                    # Track stats by business area
                    area = kw['business_area']
                    if area not in self.stats['by_business_area']:
                        self.stats['by_business_area'][area] = 0
                    self.stats['by_business_area'][area] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to queue keyword '{kw['keyword']}': {e}")
            
            self.stats['keywords_queued'] = queued_count
            return queued_count
            
        finally:
            await conn.close()
    
    def print_stats(self):
        """Print population statistics"""
        print("\n" + "="*70)
        print("🎯 KEYWORD QUEUE POPULATION COMPLETE")
        print("="*70)
        print(f"Keywords Evaluated: {self.stats['keywords_evaluated']:,}")
        print(f"Keywords Queued: {self.stats['keywords_queued']:,}")
        print(f"\n📊 By Business Area:")
        
        for area, count in sorted(
            self.stats['by_business_area'].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            priority = self.BUSINESS_PRIORITIES.get(area, 0)
            print(f"   {area:15} {count:4} keywords (priority: {priority})")
        
        print("="*70 + "\n")


async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Populate keyword monitoring queue from expanded keywords'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=500,
        help='Maximum number of keywords to queue (default: 500)'
    )
    parser.add_argument(
        '--business-area',
        type=str,
        choices=['bcdodge', 'damnitcarl', 'tvsignals', 'roseandangel', 'mealsnfeelz'],
        help='Filter by specific business area'
    )
    parser.add_argument(
        '--priority-min',
        type=float,
        default=0,
        help='Minimum priority score (0-100, default: 0)'
    )
    parser.add_argument(
        '--stagger-hours',
        type=int,
        default=24,
        help='Spread check times across this many hours (default: 24)'
    )
    parser.add_argument(
        '--balanced',
        action='store_true',
        help='Ensure fair distribution across all business areas (weighted by priority)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be queued without actually queuing'
    )
    
    args = parser.parse_args()
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set")
        return
    
    print("\n🚀 KEYWORD QUEUE POPULATOR")
    print("="*70)
    print(f"Limit: {args.limit}")
    print(f"Business Area: {args.business_area or 'All (excluding amcf)'}")
    print(f"Priority Min: {args.priority_min}")
    print(f"Stagger Hours: {args.stagger_hours}")
    print(f"Balanced Mode: {args.balanced}")
    print(f"Dry Run: {args.dry_run}")
    print("="*70 + "\n")
    
    populator = KeywordQueuePopulator(database_url)
    
    # Get prioritized keywords
    print("📊 Evaluating and scoring keywords...")
    keywords = await populator.get_prioritized_keywords(
        limit=args.limit,
        business_area=args.business_area,
        priority_min=args.priority_min,
        balanced=args.balanced
    )
    
    print(f"\n✅ Selected {len(keywords)} keywords for queueing\n")
    
    if keywords:
        # Show top 10
        print("🏆 Top 10 Keywords by Priority:")
        print("-"*70)
        for i, kw in enumerate(keywords[:10], 1):
            print(f"{i:2}. [{kw['priority_score']:5.1f}] {kw['business_area']:12} {kw['keyword']}")
        print("-"*70 + "\n")
    
    if args.dry_run:
        print("🔍 DRY RUN - Not actually queueing keywords")
        populator.stats['keywords_evaluated'] = len(keywords)
        populator.stats['keywords_queued'] = 0
        for kw in keywords:
            area = kw['business_area']
            if area not in populator.stats['by_business_area']:
                populator.stats['by_business_area'][area] = 0
            populator.stats['by_business_area'][area] += 1
    else:
        # Populate the queue
        print("💾 Populating keyword_monitoring_queue...")
        queued = await populator.populate_queue(keywords, args.stagger_hours)
        print(f"✅ Successfully queued {queued} keywords")
    
    # Print final stats
    populator.print_stats()


if __name__ == '__main__':
    asyncio.run(main())
