#!/usr/bin/env python3
"""
Smart Keyword Expansion System for Google Trends
Transforms 4,586 base keywords into 15k-20k monitoring terms
Based on ACTUAL keyword analysis from CSV files

Real Business Focus Areas:
- AMCF: Charity, donations, nonprofit, zakat, islamic giving
- BCDodge: Digital marketing, strategy, campaigns, branding
- DamnitCarl: Cat content, emotional support, tuxedo cats
- MealsNFeelz: Food donation, pantries, ramadan, fidya
- RoseAndAngel: Marketing consulting, small business help
- TVSignals: Streaming, TV shows, binge watching, netflix

FIXED: Now uses centralized db_manager instead of direct asyncpg.connect()
FIXED: Added whitelist validation for business area table names
"""

from typing import List, Dict, Set, Any, Optional
import logging

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Whitelist of valid business areas (used for table name validation)
VALID_BUSINESS_AREAS = frozenset([
    'amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals'
])


class KeywordExpander:
    """Intelligent keyword expansion based on real business contexts"""
    
    def __init__(self):
        """Initialize KeywordExpander - uses centralized db_manager"""
        # No database_url needed - we use the centralized db_manager
        
        # REAL semantic maps based on actual CSV keyword analysis
        self.semantic_maps = {
            # AMCF - Charity/Nonprofit/Islamic giving
            'charity': ['charitable', 'philanthropy', 'giving', 'donation'],
            'donation': ['donate', 'giving', 'contribute', 'support'],
            'nonprofit': ['non profit', 'charity organization', 'foundation'],
            'zakat': ['islamic charity', 'muslim donation', 'islamic giving'],
            'fundraising': ['fundraiser', 'fundraise', 'raise funds'],
            
            # BCDodge - Marketing/Digital strategy
            'marketing': ['advertising', 'promotion', 'branding', 'outreach'],
            'digital': ['online', 'internet', 'web', 'social media'],
            'strategy': ['strategic', 'planning', 'approach', 'tactics'],
            'campaign': ['promotion', 'advertising campaign', 'marketing push'],
            
            # DamnitCarl - Cat content/emotional support
            'cat': ['feline', 'kitten', 'kitty', 'pet cat'],
            'emotional support': ['therapy', 'comfort', 'support animal', 'emotional support animal'],
            'tuxedo cat': ['black and white cat', 'tuxedo kitten', 'formal cat'],
            'support cat': ['therapy cat', 'emotional support pet', 'comfort cat'],
            
            # MealsNFeelz - Food donation/Islamic charity
            'food pantry': ['food bank', 'community pantry', 'food distribution'],
            'ramadan': ['ramadan donation', 'islamic fasting', 'ramadan charity'],
            'fidya': ['missed fast', 'ramadan compensation', 'fast donation'],
            'donate food': ['food donation', 'feed the hungry', 'hunger relief'],
            
            # RoseAndAngel - Marketing consulting
            'marketing consultant': ['marketing expert', 'marketing advisor', 'marketing specialist'],
            'small business': ['small business marketing', 'local business', 'startup marketing'],
            'nonprofit marketing': ['charity marketing', 'nonprofit promotion'],
            
            # TVSignals - Streaming/TV content
            'tv show': ['television show', 'tv series', 'streaming show', 'tv program'],
            'streaming': ['streaming service', 'watch online', 'binge watch'],
            'netflix': ['netflix series', 'netflix shows', 'netflix streaming'],
            'binge': ['binge watch', 'binge watching', 'marathon watch']
        }
        
        # Business-specific context words
        self.business_contexts = {
            'amcf': ['charity', 'nonprofit', 'donation', 'zakat', 'islamic', 'muslim', 'giving'],
            'bcdodge': ['marketing', 'digital', 'strategy', 'campaign', 'brand', 'growth'],
            'damnitcarl': ['cat', 'emotional', 'support', 'pet', 'feline', 'tuxedo'],
            'mealsnfeelz': ['food', 'pantry', 'ramadan', 'fidya', 'donation', 'meal', 'hunger'],
            'roseandangel': ['marketing', 'consultant', 'business', 'nonprofit', 'strategy'],
            'tvsignals': ['tv', 'streaming', 'show', 'series', 'netflix', 'binge', 'watch']
        }
    
    def generate_semantic_variations(self, keyword: str, business_area: str) -> List[str]:
        """Generate semantic variations based on real keyword patterns"""
        variations = set()
        base_keyword = keyword.lower().strip()
        
        # Apply semantic mapping from real data analysis
        for base_term, related_terms in self.semantic_maps.items():
            if base_term in base_keyword:
                # Replace base term with related terms
                for related in related_terms:
                    new_keyword = base_keyword.replace(base_term, related)
                    if new_keyword != base_keyword:
                        variations.add(new_keyword)
                
                # Add related terms as standalone if they make sense
                for related in related_terms:
                    if len(related.split()) <= 3:  # Keep phrases reasonable
                        variations.add(related)
        
        # Business context expansions
        context_words = self.business_contexts.get(business_area, [])
        for context in context_words[:3]:  # Limit to 3 context additions
            variations.add(f"{base_keyword} {context}")
            variations.add(f"{context} {base_keyword}")
        
        return list(variations)[:5]  # Limit to top 5 semantic variations
    
    def generate_format_variations(self, keyword: str) -> List[str]:
        """Generate format and structural variations"""
        variations = set()
        base = keyword.lower().strip()
        
        # Pluralization patterns
        if not base.endswith('s'):
            variations.add(f"{base}s")
        if base.endswith('s') and len(base) > 3:
            variations.add(base[:-1])  # Remove 's'
        
        # Common format variations
        if ' ' in base:
            # Remove spaces: "food pantry" → "foodpantry"
            variations.add(base.replace(' ', ''))
            
            # Add hyphens: "food pantry" → "food-pantry"
            variations.add(base.replace(' ', '-'))
            
            # Reverse order for 2-word phrases
            words = base.split()
            if len(words) == 2:
                variations.add(f"{words[1]} {words[0]}")
        
        # Add common prefixes/suffixes based on business context
        prefixes = ['best', 'top', 'local', 'online', 'free']
        suffixes = ['near me', 'online', 'service', 'help', '2024', '2025']
        
        # Add 2 prefixes and 2 suffixes to avoid explosion
        for prefix in prefixes[:2]:
            variations.add(f"{prefix} {base}")
        for suffix in suffixes[:2]:
            variations.add(f"{base} {suffix}")
        
        return list(variations)[:5]  # Limit to 5 format variations
    
    def generate_trending_patterns(self, keyword: str, business_area: str) -> List[str]:
        """Generate trending search patterns"""
        variations = set()
        base = keyword.lower().strip()
        
        # Business-specific trending patterns
        trending_patterns = {
            'amcf': ['how to', 'best', 'top', 'near me', 'online'],
            'bcdodge': ['strategy', 'tips', 'best practices', 'guide', 'how to'],
            'damnitcarl': ['cute', 'funny', 'best', 'training', 'care'],
            'mealsnfeelz': ['near me', 'local', 'volunteer', 'donate to', 'help'],
            'roseandangel': ['for small business', 'consultant', 'expert', 'services'],
            'tvsignals': ['watch', 'stream', 'episode', 'season', 'where to watch']
        }
        
        patterns = trending_patterns.get(business_area, ['best', 'how to', 'near me'])
        
        for pattern in patterns[:3]:  # Limit to 3 trending patterns
            variations.add(f"{pattern} {base}")
            if pattern in ['near me', 'online']:
                variations.add(f"{base} {pattern}")
        
        return list(variations)[:3]  # Limit to 3 trending variations
    
    async def expand_keyword(self, keyword: str, business_area: str) -> List[str]:
        """Expand a single keyword into multiple monitoring terms"""
        all_variations = set()
        
        # Always include the original keyword
        all_variations.add(keyword.lower().strip())
        
        # Generate different types of variations
        semantic_vars = self.generate_semantic_variations(keyword, business_area)
        format_vars = self.generate_format_variations(keyword)
        trending_vars = self.generate_trending_patterns(keyword, business_area)
        
        # Add all variations
        all_variations.update(semantic_vars)
        all_variations.update(format_vars)
        all_variations.update(trending_vars)
        
        # Filter out very long phrases (>6 words) and very short ones (<2 chars)
        filtered_variations = [
            var for var in all_variations
            if 2 <= len(var) <= 100 and len(var.split()) <= 6
        ]
        
        # Return original + up to 14 variations (total ~15 per keyword)
        return filtered_variations[:15]
    
    async def get_base_keywords_from_database(self) -> Dict[str, List[str]]:
        """Fetch all active keywords from database by business area"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            all_keywords = {}
            
            for area in VALID_BUSINESS_AREAS:
                # Use parameterized approach - table name is from whitelist so safe
                # We can't parameterize table names, but we've validated against whitelist
                query = f'SELECT keyword FROM {area}_keywords WHERE is_active = true'
                rows = await conn.fetch(query)
                keywords = [row['keyword'] for row in rows]
                all_keywords[area] = keywords
                
                logger.info(f"Loaded {len(keywords)} keywords for {area}")
            
            return all_keywords
            
        except Exception as e:
            logger.error(f"Failed to get base keywords: {e}")
            return {}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def expand_all_keywords(self) -> Dict[str, List[str]]:
        """Expand all 4,586 base keywords into monitoring set"""
        print("🚀 EXPANDING ALL KEYWORDS FOR TREND MONITORING")
        print("=" * 60)
        
        # Get base keywords from database
        base_keywords = await self.get_base_keywords_from_database()
        
        if not base_keywords:
            logger.error("No base keywords found in database")
            return {}
        
        expanded_keywords = {}
        total_base = 0
        total_expanded = 0
        
        for business_area, keywords in base_keywords.items():
            print(f"\n📊 Expanding {business_area.upper()} keywords...")
            area_expanded = []
            
            for i, keyword in enumerate(keywords):
                variations = await self.expand_keyword(keyword, business_area)
                area_expanded.extend(variations)
                
                if (i + 1) % 100 == 0:
                    print(f"   Processed {i + 1}/{len(keywords)} keywords...")
            
            # Remove duplicates while preserving order
            unique_expanded = list(dict.fromkeys(area_expanded))
            expanded_keywords[business_area] = unique_expanded
            
            base_count = len(keywords)
            expanded_count = len(unique_expanded)
            expansion_ratio = expanded_count / base_count if base_count > 0 else 0
            
            print(f"   ✅ {business_area}: {base_count} → {expanded_count} keywords ({expansion_ratio:.1f}x)")
            
            total_base += base_count
            total_expanded += expanded_count
        
        overall_ratio = total_expanded / total_base if total_base > 0 else 0
        
        print(f"\n🎯 EXPANSION COMPLETE:")
        print(f"   Base keywords: {total_base:,}")
        print(f"   Expanded keywords: {total_expanded:,}")
        print(f"   Expansion ratio: {overall_ratio:.1f}x")
        print(f"   Ready for Google Trends monitoring!")
        
        return expanded_keywords
    
    async def save_expanded_keywords_to_database(self, expanded_keywords: Dict[str, List[str]]):
        """Save expanded keywords to database for trend monitoring"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Create expanded keywords table if not exists
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
            
            print("\n💾 Saving expanded keywords to database...")
            
            total_saved = 0
            for business_area, keywords in expanded_keywords.items():
                # Validate business area against whitelist
                if business_area not in VALID_BUSINESS_AREAS:
                    logger.warning(f"Skipping invalid business area: {business_area}")
                    continue
                
                for keyword in keywords:
                    try:
                        await conn.execute('''
                            INSERT INTO expanded_keywords_for_trends 
                            (original_keyword, expanded_keyword, business_area, expansion_type)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (expanded_keyword, business_area) DO NOTHING
                        ''', keyword, keyword, business_area, 'mixed')
                        total_saved += 1
                    except Exception as e:
                        logger.warning(f"Failed to save keyword '{keyword}': {e}")
            
            print(f"   ✅ Saved {total_saved:,} expanded keywords to database")
            
        except Exception as e:
            logger.error(f"Failed to save expanded keywords: {e}")
        finally:
            if conn:
                await db_manager.release_connection(conn)


# ============================================================================
# SINGLETON GETTER
# ============================================================================

_keyword_expander: Optional[KeywordExpander] = None


def get_keyword_expander() -> KeywordExpander:
    """Get or create the KeywordExpander singleton instance"""
    global _keyword_expander
    if _keyword_expander is None:
        _keyword_expander = KeywordExpander()
    return _keyword_expander
