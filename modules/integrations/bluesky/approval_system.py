# modules/integrations/bluesky/approval_system.py
"""
Approval System - Draft Generator + Queue Manager
Generates personality-appropriate drafts and manages approval workflow
"""

import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import logging

from ...core.database import db_manager
from .multi_account_client import get_bluesky_multi_client

logger = logging.getLogger(__name__)

class ApprovalSystem:
    """Manages draft generation and approval workflow for all accounts"""
    
    def __init__(self):
        self.pending_approvals = {}  # In-memory queue
        self.draft_personalities = self._setup_draft_personalities()
        
    def _setup_draft_personalities(self) -> Dict[str, str]:
        """Setup personality prompts for different account types"""
        return {
            'syntaxprime': """You are posting as Carl's personal account. Use your signature sarcastic wit with helpful insights. 
            Keep it authentic, slightly sarcastic, but genuinely helpful. This is Carl's proven successful tone on Bluesky.""",
            
            'professional': """You are drafting for a professional non-profit consulting account (Rose & Angel). 
            Use conservative, respectful, business-appropriate tone. Focus on expertise, professionalism, and community value. 
            Avoid any humor, sarcasm, or casual language. This represents a serious consulting business.""",
            
            'compassionate': """You are drafting for a sensitive non-profit account focused on Islamic giving and food programs (Meals n Feelz). 
            Use warm, empathetic, community-focused language. Be respectful of religious context and cultural sensitivity. 
            Focus on compassion, community support, and positive impact. Absolutely no sarcasm or humor.""",
            
            'creative_dumping': """You are posting to Carl's creative dumping ground account (Damn it Carl). 
            This is raw, authentic creative burnout therapy. Use natural, unfiltered creative energy. 
            This was originally your baby - you can be as creative and authentic as you want here."""
        }
    
    async def generate_draft_post(self, 
                                analysis: Dict[str, Any],
                                post_type: str = "reply") -> Dict[str, Any]:
        """Generate a draft post/reply for an engagement opportunity"""
        
        account_id = analysis['account_id']
        account_config = analysis['account_config']
        personality_type = account_config['personality']
        
        # Build context for draft generation
        post_content = analysis['post_content']
        author = analysis['author']
        matched_keywords = analysis['keyword_analysis']['matched_keywords']
        suggested_action = analysis['suggested_action']
        
        # Create personality-specific prompt
        base_personality_prompt = self.draft_personalities.get(personality_type, self.draft_personalities['professional'])
        
        # Build draft generation prompt
        draft_prompt = f"""{base_personality_prompt}

CONTEXT:
- Account: {account_id.replace('_', ' ').title()}
- Original Post by {author['display_name']} (@{author['handle']}):
"{post_content}"

- Relevant Keywords Matched: {', '.join(matched_keywords[:5])}
- Suggested Engagement Type: {suggested_action}

TASK: Generate a {'reply to this post' if post_type == 'reply' else 'new post inspired by this topic'}.

REQUIREMENTS:
- Maximum 280 characters (Bluesky limit)
- Appropriate for this account's personality and audience
- Engage meaningfully with the original post
- {'Be professionally appropriate and sensitive' if account_config.get('sensitive_topics') else 'Be authentic to the account personality'}
- Include relevant insights or value
- {'Keep language PG-13' if account_config.get('pg13_mode') else 'Use appropriate language for the context'}

Return ONLY the draft text, no quotes or extra formatting."""
        
        try:
            # Try to use the AI system to generate draft
            # For now, we'll use a simple fallback approach
            draft_text = self._generate_fallback_draft(analysis, post_type)
            
            return {
                "success": True,
                "draft_text": draft_text,
                "character_count": len(draft_text),
                "personality_used": personality_type,
                "generated_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate draft for {account_id}: {e}")
            
            # Fallback to simple template
            fallback_text = self._generate_fallback_draft(analysis, post_type)
            
            return {
                "success": True,
                "draft_text": fallback_text,
                "character_count": len(fallback_text),
                "personality_used": f"{personality_type}_fallback",
                "generated_at": datetime.now(),
                "fallback": True
            }
    
    def _generate_fallback_draft(self, analysis: Dict[str, Any], post_type: str) -> str:
        """Generate simple fallback draft if AI generation fails"""
        account_id = analysis['account_id']
        suggested_action = analysis['suggested_action']
        matched_keywords = analysis['keyword_analysis']['matched_keywords']
        personality = analysis['account_config']['personality']
        
        if 'question' in suggested_action.lower():
            if personality == 'syntaxprime':
                return "Great question! I've had similar thoughts about this."
            elif personality == 'professional':
                return "This is an important question that merits thoughtful consideration."
            else:
                return "Thank you for sharing this thoughtful question."
        elif 'advice' in suggested_action.lower():
            if personality == 'syntaxprime':
                return "Thanks for sharing this - really valuable insights."
            elif personality == 'professional':  
                return "Your experience offers valuable insights for others facing similar challenges."
            else:
                return "Thank you for sharing your experience with the community."
        elif 'recommendation' in suggested_action.lower():
            if personality == 'syntaxprime':
                return f"This aligns well with {matched_keywords[0] if matched_keywords else 'our focus areas'}."
            else:
                return "This recommendation could be valuable for many people."
        else:
            if personality == 'syntaxprime':
                return "Interesting perspective! Thanks for sharing."
            elif personality == 'professional':
                return "Thank you for bringing this important topic to our attention."
            else:
                return "Thank you for sharing this with the community."
    
    async def create_approval_item(self, 
                                 analysis: Dict[str, Any],
                                 draft_result: Dict[str, Any],
                                 priority: str = "medium") -> str:
        """Create a new approval item in the queue"""
        
        approval_id = str(uuid.uuid4())
        
        approval_item = {
            "id": approval_id,
            "account_id": analysis['account_id'],
            "post_uri": analysis['post_uri'],
            "author": analysis['author'],
            "original_post": analysis['post_content'],
            "draft_text": draft_result['draft_text'],
            "character_count": draft_result['character_count'],
            "personality_used": draft_result['personality_used'],
            "engagement_type": analysis['suggested_action'],
            "matched_keywords": analysis['keyword_analysis']['matched_keywords'],
            "keyword_score": analysis['keyword_analysis']['match_score'],
            "priority": priority,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(hours=24),  # Expire after 24 hours
            "status": "pending"
        }
        
        self.pending_approvals[approval_id] = approval_item
        
        logger.info(f"Created approval item {approval_id} for {analysis['account_id']}")
        return approval_id
    
    async def get_pending_approvals(self, 
                                  account_id: Optional[str] = None,
                                  priority: Optional[str] = None,
                                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get pending approval items with optional filtering"""
        
        approvals = list(self.pending_approvals.values())
        
        # Filter by account
        if account_id:
            approvals = [a for a in approvals if a['account_id'] == account_id]
        
        # Filter by priority
        if priority:
            approvals = [a for a in approvals if a['priority'] == priority]
        
        # Filter out expired items
        now = datetime.now()
        approvals = [a for a in approvals if a['expires_at'] > now]
        
        # Sort by priority and creation time
        priority_order = {'high': 3, 'medium': 2, 'low': 1}
        approvals.sort(
            key=lambda x: (priority_order.get(x['priority'], 0), x['created_at']), 
            reverse=True
        )
        
        # Apply limit
        if limit:
            approvals = approvals[:limit]
        
        return approvals
    
    async def approve_and_post(self, approval_id: str, user_id: str) -> Dict[str, Any]:
        """Approve an item and post it immediately"""
        
        if approval_id not in self.pending_approvals:
            return {"success": False, "error": "Approval item not found"}
        
        approval_item = self.pending_approvals[approval_id]
        
        # Check if expired
        if datetime.now() > approval_item['expires_at']:
            del self.pending_approvals[approval_id]
            return {"success": False, "error": "Approval item has expired"}
        
        try:
            # Get multi-client and post
            multi_client = get_bluesky_multi_client()
            
            result = await multi_client.create_post(
                account_id=approval_item['account_id'],
                text=approval_item['draft_text']
            )
            
            if result['success']:
                # Mark as approved and remove from queue
                approval_item['status'] = 'approved'
                approval_item['posted_at'] = datetime.now()
                approval_item['post_result'] = result
                
                # Store in database for learning (optional)
                await self._record_approval_action(approval_id, 'approved', user_id)
                
                # Remove from pending queue
                del self.pending_approvals[approval_id]
                
                logger.info(f"Approved and posted {approval_id} to {approval_item['account_id']}")
                
                return {
                    "success": True,
                    "message": f"Posted to {approval_item['account_id']}",
                    "post_result": result,
                    "approval_item": approval_item
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to post: {result['error']}"
                }
                
        except Exception as e:
            logger.error(f"Failed to approve and post {approval_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def reject_approval(self, approval_id: str, user_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject an approval item"""
        
        if approval_id not in self.pending_approvals:
            return {"success": False, "error": "Approval item not found"}
        
        approval_item = self.pending_approvals[approval_id]
        approval_item['status'] = 'rejected'
        approval_item['rejection_reason'] = reason
        approval_item['rejected_at'] = datetime.now()
        
        # Record for learning
        await self._record_approval_action(approval_id, 'rejected', user_id, reason)
        
        # Remove from pending queue
        del self.pending_approvals[approval_id]
        
        logger.info(f"Rejected approval {approval_id}: {reason}")
        
        return {
            "success": True,
            "message": "Approval rejected",
            "approval_item": approval_item
        }
    
    async def edit_and_approve(self, 
                             approval_id: str, 
                             edited_text: str, 
                             user_id: str) -> Dict[str, Any]:
        """Edit the draft text and then approve/post"""
        
        if approval_id not in self.pending_approvals:
            return {"success": False, "error": "Approval item not found"}
        
        if len(edited_text) > 300:
            return {"success": False, "error": f"Edited text too long ({len(edited_text)}/300 characters)"}
        
        approval_item = self.pending_approvals[approval_id]
        
        # Update the draft text
        approval_item['original_draft'] = approval_item['draft_text']
        approval_item['draft_text'] = edited_text.strip()
        approval_item['character_count'] = len(approval_item['draft_text'])
        approval_item['edited_at'] = datetime.now()
        approval_item['edited_by'] = user_id
        
        # Now approve and post
        return await self.approve_and_post(approval_id, user_id)
    
    async def _record_approval_action(self, 
                                    approval_id: str, 
                                    action: str, 
                                    user_id: str, 
                                    reason: str = "") -> None:
        """Record approval action for learning purposes"""
        try:
            # For now, just log the action
            # In the future, you could store this in a database table for learning
            logger.info(f"Approval action recorded: {action} - {approval_id} by {user_id} - {reason}")
            
        except Exception as e:
            logger.warning(f"Failed to record approval action: {e}")
            # Don't fail the main operation if logging fails
    
    def cleanup_expired_approvals(self) -> int:
        """Remove expired approval items"""
        now = datetime.now()
        expired_ids = [
            approval_id for approval_id, item in self.pending_approvals.items()
            if item['expires_at'] <= now
        ]
        
        for approval_id in expired_ids:
            del self.pending_approvals[approval_id]
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired approval items")
        
        return len(expired_ids)
    
    def get_approval_stats(self) -> Dict[str, Any]:
        """Get statistics about pending approvals"""
        approvals = list(self.pending_approvals.values())
        
        stats = {
            "total_pending": len(approvals),
            "by_account": {},
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "by_age": {"<1h": 0, "1-6h": 0, "6-24h": 0},
            "expiring_soon": 0  # < 2 hours
        }
        
        now = datetime.now()
        
        for approval in approvals:
            # By account
            account = approval['account_id']
            stats["by_account"][account] = stats["by_account"].get(account, 0) + 1
            
            # By priority
            priority = approval['priority']
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
            
            # By age
            age = now - approval['created_at']
            if age < timedelta(hours=1):
                stats["by_age"]["<1h"] += 1
            elif age < timedelta(hours=6):
                stats["by_age"]["1-6h"] += 1
            else:
                stats["by_age"]["6-24h"] += 1
            
            # Expiring soon
            if approval['expires_at'] - now < timedelta(hours=2):
                stats["expiring_soon"] += 1
        
        return stats

# Global approval system
_approval_system = None

def get_approval_system() -> ApprovalSystem:
    """Get the global approval system"""
    global _approval_system
    if _approval_system is None:
        _approval_system = ApprovalSystem()
    return _approval_system