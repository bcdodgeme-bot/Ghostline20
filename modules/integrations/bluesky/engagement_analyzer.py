# modules/integrations/bluesky/engagement_analyzer.py
"""
Engagement Analyzer - Keyword Intelligence + Cross-Account Routing
Analyzes posts against keyword database for engagement opportunities
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import re
import logging

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Valid keyword tables - SQL injection prevention
VALID_KEYWORD_TABLES = frozenset({
    'bcdodge_keywords',
    'roseandangel_keywords',
    'tvsignals_keywords',
    'mealsnfeelz_keywords',
    'damnitcarl_keywords',
    'amcf_keywords',
})


class EngagementAnalyzer:
    """Analyzes Bluesky posts for engagement opportunities using keyword intelligence"""
    
    def __init__(self):
        self.keyword_cache = {}
        self.cache_duration = 3600  # 1 hour cache for keywords
        
        # Engagement opportunity types
        self.opportunity_types = {
            'high_match': 'High keyword match (80%+)',
            'conversation_starter': 'Post asks questions or seeks input',
            'expertise_showcase': 'Opportunity to demonstrate knowledge',
            'community_building': 'Community/networking opportunity',
            'trending_topic': 'Trending topic relevant to keywords',
            'cross_account': 'Could work across multiple accounts'
        }
    
    def _validate_table_name(self, table_name: str) -> bool:
        """Validate table name against allowlist to prevent SQL injection"""
        return table_name in VALID_KEYWORD_TABLES
    
    async def get_account_keywords(self, account_id: str, keywords_table: str) -> List[str]:
        """Get keywords for specific account from database"""
        cache_key = f"{account_id}_{keywords_table}"
        
        if cache_key in self.keyword_cache:
            cached_time, keywords = self.keyword_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_duration:
                return keywords
        
        # Validate table name against allowlist
        if not self._validate_table_name(keywords_table):
            logger.error(f"Invalid keywords table name: {keywords_table}")
            return []
        
        try:
            # Safe query - table name validated against allowlist
            query = f"SELECT keyword FROM {keywords_table} WHERE is_active = true"
            results = await db_manager.fetch_all(query)
            
            keywords = [row['keyword'].lower() for row in results]
            
            # Cache the results
            self.keyword_cache[cache_key] = (datetime.now(), keywords)
            
            logger.info(f"Loaded {len(keywords)} keywords for {account_id} from {keywords_table}")
            return keywords
            
        except Exception as e:
            logger.error(f"Failed to load keywords for {account_id}: {e}")
            return []
    
    def calculate_keyword_match_score(self, post_text: str, keywords: List[str]) -> Tuple[float, List[str]]:
        """Calculate keyword match score and return matching keywords"""
        if not keywords or not post_text:
            return 0.0, []
        
        post_lower = post_text.lower()
        post_words = re.findall(r'\b\w+\b', post_lower)
        
        matched_keywords = []
        match_score = 0.0
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            
            # Exact phrase match (higher weight)
            if keyword_lower in post_lower:
                matched_keywords.append(keyword)
                match_score += 2.0
            
            # Individual word matches (lower weight)
            elif any(word in keyword_lower.split() for word in post_words):
                keyword_words = keyword_lower.split()
                if any(word in post_words for word in keyword_words):
                    matched_keywords.append(keyword)
                    match_score += 1.0
        
        # Normalize score based on number of keywords and post length
        if matched_keywords:
            # Score based on percentage of keywords matched vs total keywords
            keyword_coverage = len(set(matched_keywords)) / len(keywords)
            # Boost for multiple matches in shorter posts
            density_bonus = min(match_score / len(post_words) * 100, 0.5)
            final_score = min((keyword_coverage * 0.8 + density_bonus * 0.2), 1.0)
        else:
            final_score = 0.0
        
        return final_score, list(set(matched_keywords))
    
    def detect_conversation_opportunities(self, post_text: str) -> Dict[str, Any]:
        """Detect if post contains conversation starters or engagement hooks"""
        post_lower = post_text.lower()
        
        opportunities = {
            'is_question': False,
            'seeks_advice': False,
            'shares_experience': False,
            'controversial_topic': False,
            'asks_for_recommendations': False,
            'engagement_hooks': []
        }
        
        # Question indicators
        question_patterns = [
            r'\?', r'what do you think', r'thoughts on', r'anyone else',
            r'does anyone', r'who has experience', r'how do you'
        ]
        if any(re.search(pattern, post_lower) for pattern in question_patterns):
            opportunities['is_question'] = True
            opportunities['engagement_hooks'].append('Question/Discussion starter')
        
        # Advice seeking
        advice_patterns = [
            r'need advice', r'looking for help', r'suggestions',
            r'recommendations', r'has anyone', r'best way to'
        ]
        if any(re.search(pattern, post_lower) for pattern in advice_patterns):
            opportunities['seeks_advice'] = True
            opportunities['engagement_hooks'].append('Seeking advice/recommendations')
        
        # Experience sharing
        experience_patterns = [
            r'just learned', r'discovered', r'found out', r'realized',
            r'my experience', r'what i learned', r'lesson learned'
        ]
        if any(re.search(pattern, post_lower) for pattern in experience_patterns):
            opportunities['shares_experience'] = True
            opportunities['engagement_hooks'].append('Sharing experience/insights')
        
        # Hot takes / controversial
        controversial_patterns = [
            r'hot take', r'unpopular opinion', r'controversial', r'change my mind',
            r'disagree with me', r'fight me on this'
        ]
        if any(re.search(pattern, post_lower) for pattern in controversial_patterns):
            opportunities['controversial_topic'] = True
            opportunities['engagement_hooks'].append('Hot take/controversial opinion')
        
        # Recommendations
        rec_patterns = [
            r'recommend', r'suggestions for', r'best.*for', r'looking for.*app',
            r'tool.*recommend', r'what.*use for'
        ]
        if any(re.search(pattern, post_lower) for pattern in rec_patterns):
            opportunities['asks_for_recommendations'] = True
            opportunities['engagement_hooks'].append('Asking for recommendations')
        
        return opportunities
    
    async def analyze_post_for_account(self,
                                     post: Dict[str, Any],
                                     account_id: str,
                                     account_config: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single post for a specific account"""
        
        # Extract post content
        post_record = post.get('post', {}).get('record', {})
        post_text = post_record.get('text', '')
        
        if not post_text or len(post_text.strip()) < 10:
            return None
        
        # Get post metadata
        author = post.get('post', {}).get('author', {})
        author_handle = author.get('handle', 'unknown')
        author_display = author.get('displayName', author_handle)
        created_at = post_record.get('createdAt', '')
        post_uri = post.get('post', {}).get('uri', '')
        
        # Get engagement stats
        post_info = post.get('post', {})
        like_count = post_info.get('likeCount', 0)
        reply_count = post_info.get('replyCount', 0)
        repost_count = post_info.get('repostCount', 0)
        
        # Load keywords for this account
        keywords = await self.get_account_keywords(account_id, account_config['keywords_table'])
        
        # Calculate keyword match score
        keyword_score, matched_keywords = self.calculate_keyword_match_score(post_text, keywords)
        
        # Skip low-relevance posts early (lowered threshold for testing)
        if keyword_score < 0.02:  # 2% threshold
            logger.debug(f"Skipped post from {author_handle}: keyword_score too low ({keyword_score:.2f})")
            return None
        
        # Log potential matches
        logger.info(f"✨ Analyzing post from {author_handle}: keyword_score={keyword_score:.3f}, matched={len(matched_keywords)} keywords")
        
        # Log when we find potential matches
        if keyword_score >= 0.02:
            logger.info(f"✨ Found potential match from {author_handle}: score={keyword_score:.2f}, keywords={len(matched_keywords)}")
        
        # Detect conversation opportunities
        conversation_ops = self.detect_conversation_opportunities(post_text)
        
        # Calculate engagement potential
        engagement_potential = self._calculate_engagement_potential(
            keyword_score,
            conversation_ops,
            like_count,
            reply_count
        )
        
        # Generate engagement suggestion
        suggestion_type = self._suggest_engagement_type(post_text, conversation_ops, account_config)
        
        # Build analysis result
        analysis = {
            'account_id': account_id,
            'post_uri': post_uri,
            'author': {
                'handle': author_handle,
                'display_name': author_display
            },
            'post_content': post_text,
            'created_at': created_at,
            'engagement_stats': {
                'likes': like_count,
                'replies': reply_count,
                'reposts': repost_count
            },
            'keyword_analysis': {
                'match_score': keyword_score,
                'matched_keywords': matched_keywords,
                'keyword_count': len(matched_keywords)
            },
            'conversation_opportunities': conversation_ops,
            'engagement_potential': engagement_potential,
            'suggested_action': suggestion_type,
            'priority_level': self._calculate_priority_level(keyword_score, engagement_potential),
            'account_config': {
                'personality': account_config['personality'],
                'ai_posting_allowed': account_config.get('ai_posting_allowed', False),
                'sensitive_topics': account_config.get('sensitive_topics', False)
            }
        }
        
        # Log the final decision
        logger.info(f"   📊 Engagement potential: {engagement_potential:.3f}")
        logger.info(f"   🎯 Priority: {self._calculate_priority_level(keyword_score, engagement_potential)}")
        logger.info(f"   💬 Has question: {conversation_ops['is_question']}")
        logger.info(f"   📝 Matched keywords: {matched_keywords[:5]}")  # Show first 5
        
        return analysis
    
    def _calculate_engagement_potential(self,
                                      keyword_score: float,
                                      conversation_ops: Dict[str, Any],
                                      like_count: int,
                                      reply_count: int) -> float:
        """Calculate overall engagement potential score"""
        
        # Base score from keyword matching
        base_score = keyword_score
        
        # Boost for conversation opportunities
        conversation_boost = 0.0
        if conversation_ops['is_question']:
            conversation_boost += 0.2
        if conversation_ops['seeks_advice']:
            conversation_boost += 0.15
        if conversation_ops['shares_experience']:
            conversation_boost += 0.1
        if conversation_ops['asks_for_recommendations']:
            conversation_boost += 0.15
        
        # Social proof boost (but not too much weight)
        social_boost = 0.0
        if like_count > 0:
            social_boost += min(like_count / 100, 0.1)  # Max 0.1 boost
        if reply_count > 0:
            social_boost += min(reply_count / 20, 0.1)   # Max 0.1 boost
        
        # Recency boost for newer posts
        # (You could implement time decay here)
        
        final_score = min(base_score + conversation_boost + social_boost, 1.0)
        return final_score
    
    def _suggest_engagement_type(self,
                                post_text: str,
                                conversation_ops: Dict[str, Any],
                                account_config: Dict[str, Any]) -> str:
        """Suggest type of engagement based on post content and account config"""
        
        post_lower = post_text.lower()
        
        # For sensitive accounts (Rose & Angel, Meals n Feelz)
        if account_config.get('sensitive_topics'):
            if conversation_ops['seeks_advice']:
                return "professional_advice"
            elif conversation_ops['shares_experience']:
                return "supportive_comment"
            else:
                return "thoughtful_like"
        
        # For AI-enabled accounts
        if account_config.get('ai_posting_allowed'):
            if conversation_ops['is_question']:
                return "ai_generated_reply"
            elif conversation_ops['asks_for_recommendations']:
                return "ai_recommendation_reply"
            elif conversation_ops['controversial_topic']:
                return "ai_perspective_reply"
            else:
                return "ai_insightful_comment"
        
        # Default engagement types
        if conversation_ops['is_question']:
            return "thoughtful_reply"
        elif conversation_ops['seeks_advice']:
            return "helpful_advice"
        elif conversation_ops['shares_experience']:
            return "related_experience_share"
        else:
            return "supportive_engagement"
    
    def _calculate_priority_level(self, keyword_score: float, engagement_potential: float) -> str:
        """Calculate priority level for the opportunity"""
        combined_score = (keyword_score + engagement_potential) / 2
        
        if combined_score >= 0.8:
            return "high"
        elif combined_score >= 0.5:
            return "medium"
        elif combined_score >= 0.3:
            return "low"
        else:
            return "minimal"
    
    async def find_cross_account_opportunities(self,
                                             analyses: List[Dict[str, Any]],
                                             account_configs: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Find posts that could work across multiple accounts"""
        
        cross_opportunities = []
        
        # Group analyses by post URI to find duplicates
        post_groups = {}
        for analysis in analyses:
            if analysis and analysis.get('priority_level') in ['high', 'medium']:
                uri = analysis['post_uri']
                if uri not in post_groups:
                    post_groups[uri] = []
                post_groups[uri].append(analysis)
        
        # Find posts that multiple accounts could engage with
        for post_uri, account_analyses in post_groups.items():
            if len(account_analyses) > 1:
                # Check if accounts are allowed to cross-pollinate
                viable_accounts = []
                for analysis in account_analyses:
                    account_id = analysis['account_id']
                    account_config = account_configs.get(account_id, {})
                    
                    # Check cross-pollination rules
                    can_cross_to = account_config.get('can_cross_to', [])
                    other_account_ids = [a['account_id'] for a in account_analyses if a['account_id'] != account_id]
                    
                    if any(other_id in can_cross_to for other_id in other_account_ids):
                        viable_accounts.append(analysis)
                
                if len(viable_accounts) > 1:
                    # Create cross-account opportunity
                    cross_opportunity = {
                        'type': 'cross_account',
                        'post_uri': post_uri,
                        'post_content': account_analyses[0]['post_content'][:200] + "...",
                        'author': account_analyses[0]['author'],
                        'viable_accounts': [
                            {
                                'account_id': analysis['account_id'],
                                'keyword_score': analysis['keyword_analysis']['match_score'],
                                'suggested_action': analysis['suggested_action'],
                                'matched_keywords': analysis['keyword_analysis']['matched_keywords']
                            }
                            for analysis in viable_accounts
                        ],
                        'priority_score': max(a['engagement_potential'] for a in viable_accounts),
                        'recommendation': self._generate_cross_account_recommendation(viable_accounts)
                    }
                    
                    cross_opportunities.append(cross_opportunity)
        
        return cross_opportunities
    
    def _generate_cross_account_recommendation(self, viable_accounts: List[Dict]) -> str:
        """Generate recommendation for cross-account opportunities"""
        
        account_names = [a['account_id'].replace('_', ' ').title() for a in viable_accounts]
        
        # Find the account with highest engagement potential
        best_account = max(viable_accounts, key=lambda x: x['engagement_potential'])
        
        if len(viable_accounts) == 2:
            return f"Both {account_names[0]} and {account_names[1]} could engage - suggest {best_account['account_id']} leads"
        else:
            return f"Multiple accounts interested ({', '.join(account_names)}) - {best_account['account_id']} has strongest match"
    
    def clear_cache(self):
        """Clear keyword cache"""
        self.keyword_cache.clear()
        logger.info("Engagement analyzer cache cleared")

# Global analyzer instance
_engagement_analyzer = None

def get_engagement_analyzer() -> EngagementAnalyzer:
    """Get the global engagement analyzer"""
    global _engagement_analyzer
    if _engagement_analyzer is None:
        _engagement_analyzer = EngagementAnalyzer()
    return _engagement_analyzer
