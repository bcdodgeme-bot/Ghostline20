# modules/integrations/bluesky/notification_manager.py
"""
Notification Manager - Smart Real-time vs Digest Logic
Manages when to show real-time notifications vs batched digests
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

from ...core.database import db_manager

logger = logging.getLogger(__name__)

class NotificationManager:
    """Manages real-time vs digest notifications for Bluesky engagement suggestions"""
    
    def __init__(self):
        self.user_activity_cache = {}  # Track user activity
        self.digest_cache = {}  # Store digests for inactive users
        self.activity_timeout = timedelta(hours=2)  # Consider user inactive after 2 hours
        self.digest_min_interval = timedelta(hours=3)  # Minimum time between digests
        
        # Notification thresholds
        self.realtime_thresholds = {
            'high_priority_score': 0.8,  # Always notify for 80%+ matches
            'urgent_keywords': ['urgent', 'breaking', 'announce'],
            'cross_account_opportunities': True
        }
    
    async def track_user_activity(self, user_id: str, activity_type: str = "chat_interaction") -> None:
        """Track user activity to determine if they're active"""
        self.user_activity_cache[user_id] = {
            'last_activity': datetime.now(),
            'activity_type': activity_type,
            'session_active': True
        }
        
        logger.debug(f"👤 User {user_id} activity tracked: {activity_type}")
    
    def is_user_active(self, user_id: str) -> bool:
        """Check if user is currently active"""
        if user_id not in self.user_activity_cache:
            return False
        
        last_activity = self.user_activity_cache[user_id]['last_activity']
        return datetime.now() - last_activity < self.activity_timeout
    
    async def should_send_realtime_notification(self, 
                                              user_id: str,
                                              opportunity: Dict[str, Any]) -> bool:
        """Determine if opportunity should trigger real-time notification"""
        
        # Always check if user is active first
        if not self.is_user_active(user_id):
            return False
        
        # High priority opportunities always get real-time
        if opportunity.get('priority_level') == 'high':
            return True
        
        # Check engagement potential score
        engagement_score = opportunity.get('engagement_potential', 0)
        if engagement_score >= self.realtime_thresholds['high_priority_score']:
            return True
        
        # Cross-account opportunities are interesting
        if opportunity.get('type') == 'cross_account':
            return True
        
        # Check for urgent keywords
        post_content = opportunity.get('post_content', '').lower()
        if any(keyword in post_content for keyword in self.realtime_thresholds['urgent_keywords']):
            return True
        
        # Check if it's been a while since last real-time notification
        last_notification = await self.get_last_notification_time(user_id, 'realtime')
        if last_notification and datetime.now() - last_notification < timedelta(minutes=15):
            return False  # Don't spam with real-time notifications
        
        return False
    
    async def add_to_digest(self, 
                          user_id: str, 
                          opportunities: List[Dict[str, Any]]) -> None:
        """Add opportunities to user's digest"""
        
        if user_id not in self.digest_cache:
            self.digest_cache[user_id] = {
                'opportunities': [],
                'last_digest_sent': None,
                'created_at': datetime.now()
            }
        
        # Add new opportunities
        self.digest_cache[user_id]['opportunities'].extend(opportunities)
        
        # Deduplicate by post_uri
        seen_uris = set()
        unique_opportunities = []
        for opp in self.digest_cache[user_id]['opportunities']:
            uri = opp.get('post_uri')
            if uri not in seen_uris:
                seen_uris.add(uri)
                unique_opportunities.append(opp)
        
        self.digest_cache[user_id]['opportunities'] = unique_opportunities
        
        logger.info(f"📧 Added {len(opportunities)} opportunities to digest for {user_id} (total: {len(unique_opportunities)})")
    
    async def should_send_digest(self, user_id: str) -> bool:
        """Check if it's time to send a digest to inactive user"""
        
        if self.is_user_active(user_id):
            return False  # Don't send digest to active users
        
        if user_id not in self.digest_cache:
            return False  # No digest to send
        
        digest_data = self.digest_cache[user_id]
        
        # Check if we have opportunities to send
        if not digest_data['opportunities']:
            return False
        
        # Check minimum interval between digests
        last_digest = digest_data['last_digest_sent']
        if last_digest and datetime.now() - last_digest < self.digest_min_interval:
            return False
        
        # Check if digest has been sitting for at least 1 hour
        created_at = digest_data['created_at']
        if datetime.now() - created_at < timedelta(hours=1):
            return False
        
        return True
    
    async def generate_realtime_notification(self, 
                                           opportunities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a real-time notification message"""
        
        if not opportunities:
            return None
        
        # Sort by priority and engagement potential
        sorted_ops = sorted(
            opportunities, 
            key=lambda x: (x.get('engagement_potential', 0), x.get('priority_level') == 'high'), 
            reverse=True
        )
        
        top_opportunity = sorted_ops[0]
        
        notification = {
            'type': 'realtime',
            'timestamp': datetime.now(),
            'priority': top_opportunity.get('priority_level', 'medium'),
            'message': self._format_realtime_message(top_opportunity, len(opportunities)),
            'opportunities': sorted_ops[:3],  # Include top 3
            'action_buttons': [
                {'action': 'view_all', 'label': f'View All ({len(opportunities)})'},
                {'action': 'approve_top', 'label': 'Quick Approve Top'},
                {'action': 'dismiss', 'label': 'Dismiss'}
            ]
        }
        
        return notification
    
    def _format_realtime_message(self, opportunity: Dict[str, Any], total_count: int) -> str:
        """Format real-time notification message"""
        
        account_name = opportunity['account_id'].replace('_', ' ').title()
        author = opportunity['author']['display_name']
        engagement_score = int(opportunity.get('engagement_potential', 0) * 100)
        
        if total_count == 1:
            return f"🔵 **{account_name}** • New high-priority opportunity ({engagement_score}% match)\n📱 {author}: {opportunity['post_content'][:100]}..."
        else:
            return f"🔵 **Bluesky Intelligence** • {total_count} new opportunities\n⭐ **Top Priority:** {account_name} • {author} ({engagement_score}% match)"
    
    async def generate_digest_notification(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Generate digest notification for inactive user"""
        
        if user_id not in self.digest_cache:
            return None
        
        digest_data = self.digest_cache[user_id]
        opportunities = digest_data['opportunities']
        
        if not opportunities:
            return None
        
        # Group by account and priority
        account_groups = {}
        priority_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        for opp in opportunities:
            account_id = opp['account_id']
            if account_id not in account_groups:
                account_groups[account_id] = {'opportunities': [], 'top_score': 0}
            
            account_groups[account_id]['opportunities'].append(opp)
            account_groups[account_id]['top_score'] = max(
                account_groups[account_id]['top_score'],
                opp.get('engagement_potential', 0)
            )
            
            priority_counts[opp.get('priority_level', 'low')] += 1
        
        # Calculate time since last activity
        last_activity = self.user_activity_cache.get(user_id, {}).get('last_activity')
        time_away = ""
        if last_activity:
            hours_away = (datetime.now() - last_activity).total_seconds() / 3600
            if hours_away < 24:
                time_away = f"Last {int(hours_away)} hours"
            else:
                time_away = f"Last {int(hours_away/24)} days"
        
        digest = {
            'type': 'digest',
            'timestamp': datetime.now(),
            'time_period': time_away,
            'total_opportunities': len(opportunities),
            'priority_breakdown': priority_counts,
            'account_breakdown': {
                account_id: {
                    'count': len(data['opportunities']),
                    'top_score': int(data['top_score'] * 100),
                    'account_name': account_id.replace('_', ' ').title()
                }
                for account_id, data in account_groups.items()
            },
            'top_opportunities': self._get_top_digest_opportunities(opportunities, 5),
            'message': self._format_digest_message(opportunities, account_groups, time_away),
            'action_buttons': [
                {'action': 'review_high_priority', 'label': f'High Priority ({priority_counts["high"]})'},
                {'action': 'review_all', 'label': f'Review All ({len(opportunities)})'},
                {'action': 'clear_digest', 'label': 'Mark as Reviewed'}
            ]
        }
        
        # Mark digest as sent
        self.digest_cache[user_id]['last_digest_sent'] = datetime.now()
        
        return digest
    
    def _get_top_digest_opportunities(self, opportunities: List[Dict], limit: int) -> List[Dict]:
        """Get top opportunities for digest"""
        return sorted(
            opportunities,
            key=lambda x: (
                x.get('priority_level') == 'high',
                x.get('engagement_potential', 0),
                x.get('keyword_analysis', {}).get('match_score', 0)
            ),
            reverse=True
        )[:limit]
    
    def _format_digest_message(self, 
                             opportunities: List[Dict], 
                             account_groups: Dict,
                             time_away: str) -> str:
        """Format digest message"""
        
        total_count = len(opportunities)
        account_count = len(account_groups)
        
        # Get highest priority opportunity
        top_opp = max(opportunities, key=lambda x: x.get('engagement_potential', 0))
        top_score = int(top_opp.get('engagement_potential', 0) * 100)
        top_account = top_opp['account_id'].replace('_', ' ').title()
        
        header = f"🔵 **Bluesky Digest** ({time_away})"
        summary = f"📊 **{total_count} opportunities** across **{account_count} accounts**"
        highlight = f"⭐ **Top Match:** {top_account} • {top_score}% keyword relevance"
        
        return f"{header}\n{summary}\n{highlight}"
    
    async def get_last_notification_time(self, user_id: str, notification_type: str) -> Optional[datetime]:
        """Get timestamp of last notification sent to user"""
        try:
            query = """
            SELECT created_at FROM user_notifications 
            WHERE user_id = $1 AND notification_type = $2 
            ORDER BY created_at DESC LIMIT 1
            """
            
            result = await db_manager.fetch_one(query, user_id, notification_type)
            return result['created_at'] if result else None
            
        except Exception as e:
            logger.warning(f"Failed to get last notification time: {e}")
            return None
    
    async def record_notification(self, 
                                user_id: str, 
                                notification_type: str,
                                content: Dict[str, Any]) -> None:
        """Record notification in database"""
        try:
            query = """
            INSERT INTO user_notifications (user_id, notification_type, content, created_at)
            VALUES ($1, $2, $3, NOW())
            """
            
            await db_manager.execute(query, user_id, notification_type, json.dumps(content))
            
        except Exception as e:
            logger.warning(f"Failed to record notification: {e}")
    
    async def clear_digest(self, user_id: str) -> bool:
        """Clear user's digest cache"""
        if user_id in self.digest_cache:
            del self.digest_cache[user_id]
            logger.info(f"🧹 Cleared digest for user {user_id}")
            return True
        return False
    
    async def get_notification_stats(self, user_id: str) -> Dict[str, Any]:
        """Get notification statistics for user"""
        
        stats = {
            'is_active': self.is_user_active(user_id),
            'digest_pending': user_id in self.digest_cache,
            'digest_opportunity_count': len(self.digest_cache.get(user_id, {}).get('opportunities', [])),
            'last_activity': self.user_activity_cache.get(user_id, {}).get('last_activity'),
            'notification_preferences': {
                'realtime_enabled': True,
                'digest_enabled': True,
                'high_priority_only': False
            }
        }
        
        if stats['digest_pending']:
            digest_data = self.digest_cache[user_id]
            stats['digest_created_at'] = digest_data['created_at']
            stats['digest_ready'] = await self.should_send_digest(user_id)
        
        return stats
    
    def cleanup_old_cache(self) -> int:
        """Clean up old cache entries"""
        cleaned = 0
        cutoff_time = datetime.now() - timedelta(hours=48)
        
        # Clean activity cache
        expired_users = [
            user_id for user_id, data in self.user_activity_cache.items()
            if data['last_activity'] < cutoff_time
        ]
        
        for user_id in expired_users:
            del self.user_activity_cache[user_id]
            cleaned += 1
        
        # Clean digest cache (older entries)
        digest_cutoff = datetime.now() - timedelta(hours=72)
        expired_digests = [
            user_id for user_id, data in self.digest_cache.items()
            if data['created_at'] < digest_cutoff
        ]
        
        for user_id in expired_digests:
            del self.digest_cache[user_id]
            cleaned += 1
        
        if cleaned > 0:
            logger.info(f"🧹 Cleaned up {cleaned} old cache entries")
        
        return cleaned

# Global notification manager
_notification_manager = None

def get_notification_manager() -> NotificationManager:
    """Get the global notification manager"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager