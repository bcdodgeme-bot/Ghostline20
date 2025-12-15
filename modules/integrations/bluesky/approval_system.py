# modules/integrations/bluesky/approval_system.py
"""
Approval System - Draft Generator + Queue Manager
Generates personality-appropriate drafts and manages approval workflow
Now with database persistence using bluesky_approval_queue table
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from ...core.database import db_manager
from .multi_account_client import get_bluesky_multi_client

logger = logging.getLogger(__name__)


class ApprovalSystem:
    """Manages draft generation and approval workflow for all accounts"""
    
    def __init__(self):
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
        """Create a new approval item in the database"""
        
        approval_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=24)
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            await conn.execute('''
                INSERT INTO bluesky_approval_queue (
                    id, account_id, post_uri, author_handle,
                    original_post_text, draft_text, personality_used,
                    matched_keywords, keyword_score, engagement_potential,
                    priority, status, expires_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ''',
                uuid.UUID(approval_id),
                analysis['account_id'],
                analysis['post_uri'],
                analysis['author']['handle'],
                analysis['post_content'],
                draft_result['draft_text'],
                draft_result['personality_used'],
                json.dumps(analysis['keyword_analysis']['matched_keywords']),
                analysis['keyword_analysis']['match_score'],
                analysis.get('engagement_potential', 0),
                priority,
                'pending',
                expires_at
            )
            
            logger.info(f"Created approval item {approval_id} for {analysis['account_id']}")
            return approval_id
            
        except Exception as e:
            logger.error(f"Failed to create approval item: {e}")
            raise
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_pending_approvals(self,
                                  account_id: Optional[str] = None,
                                  priority: Optional[str] = None,
                                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get pending approval items from database with optional filtering"""
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Build query with optional filters
            query = '''
                SELECT 
                    id, account_id, post_uri, author_handle,
                    original_post_text, draft_text, personality_used,
                    matched_keywords, keyword_score, engagement_potential,
                    priority, status, expires_at, created_at
                FROM bluesky_approval_queue
                WHERE status = 'pending' AND expires_at > NOW()
            '''
            params = []
            param_idx = 1
            
            if account_id:
                query += f' AND account_id = ${param_idx}'
                params.append(account_id)
                param_idx += 1
            
            if priority:
                query += f' AND priority = ${param_idx}'
                params.append(priority)
                param_idx += 1
            
            # Order by priority (high first) then by creation time
            query += '''
                ORDER BY 
                    CASE priority 
                        WHEN 'high' THEN 3 
                        WHEN 'medium' THEN 2 
                        WHEN 'low' THEN 1 
                        ELSE 0 
                    END DESC,
                    created_at DESC
            '''
            
            if limit:
                query += f' LIMIT ${param_idx}'
                params.append(limit)
            
            rows = await conn.fetch(query, *params)
            
            # Convert to list of dicts
            approvals = []
            for row in rows:
                approval = {
                    'id': str(row['id']),
                    'account_id': row['account_id'],
                    'post_uri': row['post_uri'],
                    'author': {'handle': row['author_handle']},
                    'original_post': row['original_post_text'],
                    'draft_text': row['draft_text'],
                    'character_count': len(row['draft_text']),
                    'personality_used': row['personality_used'],
                    'matched_keywords': json.loads(row['matched_keywords']) if row['matched_keywords'] else [],
                    'keyword_score': float(row['keyword_score']) if row['keyword_score'] else 0,
                    'engagement_potential': float(row['engagement_potential']) if row['engagement_potential'] else 0,
                    'priority': row['priority'],
                    'status': row['status'],
                    'created_at': row['created_at'],
                    'expires_at': row['expires_at']
                }
                approvals.append(approval)
            
            return approvals
            
        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            return []
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def approve_and_post(self, approval_id: str, user_id: str) -> Dict[str, Any]:
        """Approve an item and post it immediately"""
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get the approval item
            row = await conn.fetchrow('''
                SELECT 
                    id, account_id, post_uri, author_handle,
                    original_post_text, draft_text, personality_used,
                    matched_keywords, priority, status, expires_at
                FROM bluesky_approval_queue
                WHERE id = $1
            ''', uuid.UUID(approval_id))
            
            if not row:
                return {"success": False, "error": "Approval item not found"}
            
            if row['status'] != 'pending':
                return {"success": False, "error": f"Approval item is already {row['status']}"}
            
            # Check if expired
            if datetime.now(row['expires_at'].tzinfo) > row['expires_at']:
                await conn.execute('''
                    UPDATE bluesky_approval_queue 
                    SET status = 'expired', resolved_at = NOW()
                    WHERE id = $1
                ''', uuid.UUID(approval_id))
                return {"success": False, "error": "Approval item has expired"}
            
            # Get multi-client and post
            multi_client = get_bluesky_multi_client()
            
            result = await multi_client.create_post(
                account_id=row['account_id'],
                text=row['draft_text']
            )
            
            if result['success']:
                # Update status to approved
                await conn.execute('''
                    UPDATE bluesky_approval_queue 
                    SET status = 'approved', 
                        resolved_at = NOW(),
                        post_result = $2
                    WHERE id = $1
                ''', uuid.UUID(approval_id), json.dumps({
                    'uri': result.get('uri'),
                    'cid': result.get('cid'),
                    'posted_at': result.get('posted_at').isoformat() if result.get('posted_at') else None
                }))
                
                logger.info(f"Approved and posted {approval_id} to {row['account_id']}")
                
                return {
                    "success": True,
                    "message": f"Posted to {row['account_id']}",
                    "post_result": result,
                    "approval_id": approval_id
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to post: {result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"Failed to approve and post {approval_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def reject_approval(self, approval_id: str, user_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject an approval item"""
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Check if exists and is pending
            row = await conn.fetchrow('''
                SELECT id, status, account_id FROM bluesky_approval_queue WHERE id = $1
            ''', uuid.UUID(approval_id))
            
            if not row:
                return {"success": False, "error": "Approval item not found"}
            
            if row['status'] != 'pending':
                return {"success": False, "error": f"Approval item is already {row['status']}"}
            
            # Update to rejected
            await conn.execute('''
                UPDATE bluesky_approval_queue 
                SET status = 'rejected', 
                    resolved_at = NOW(),
                    rejection_reason = $2
                WHERE id = $1
            ''', uuid.UUID(approval_id), reason)
            
            logger.info(f"Rejected approval {approval_id}: {reason}")
            
            return {
                "success": True,
                "message": "Approval rejected",
                "approval_id": approval_id,
                "account_id": row['account_id']
            }
            
        except Exception as e:
            logger.error(f"Failed to reject approval {approval_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def edit_and_approve(self,
                             approval_id: str,
                             edited_text: str,
                             user_id: str) -> Dict[str, Any]:
        """Edit the draft text and then approve/post"""
        
        if len(edited_text) > 300:
            return {"success": False, "error": f"Edited text too long ({len(edited_text)}/300 characters)"}
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Update the draft text
            await conn.execute('''
                UPDATE bluesky_approval_queue 
                SET draft_text = $2, edited_text = $2
                WHERE id = $1 AND status = 'pending'
            ''', uuid.UUID(approval_id), edited_text.strip())
            
            # Now approve and post
            return await self.approve_and_post(approval_id, user_id)
            
        except Exception as e:
            logger.error(f"Failed to edit and approve {approval_id}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def cleanup_expired_approvals(self) -> int:
        """Mark expired approval items"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            result = await conn.execute('''
                UPDATE bluesky_approval_queue 
                SET status = 'expired', resolved_at = NOW()
                WHERE status = 'pending' AND expires_at <= NOW()
            ''')
            
            # Extract count from result string like "UPDATE 5"
            count = int(result.split()[-1]) if result else 0
            
            if count > 0:
                logger.info(f"Marked {count} expired approval items")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired approvals: {e}")
            return 0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_approval_stats(self) -> Dict[str, Any]:
        """Get statistics about pending approvals"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get counts by status
            status_counts = await conn.fetch('''
                SELECT status, COUNT(*) as count
                FROM bluesky_approval_queue
                GROUP BY status
            ''')
            
            # Get pending breakdown
            pending_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_pending,
                    COUNT(*) FILTER (WHERE priority = 'high') as high_priority,
                    COUNT(*) FILTER (WHERE priority = 'medium') as medium_priority,
                    COUNT(*) FILTER (WHERE priority = 'low') as low_priority,
                    COUNT(*) FILTER (WHERE expires_at - NOW() < INTERVAL '2 hours') as expiring_soon,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as last_hour,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '6 hours' AND created_at <= NOW() - INTERVAL '1 hour') as last_6h,
                    COUNT(*) FILTER (WHERE created_at <= NOW() - INTERVAL '6 hours') as older
                FROM bluesky_approval_queue
                WHERE status = 'pending' AND expires_at > NOW()
            ''')
            
            # Get by account
            account_counts = await conn.fetch('''
                SELECT account_id, COUNT(*) as count
                FROM bluesky_approval_queue
                WHERE status = 'pending' AND expires_at > NOW()
                GROUP BY account_id
            ''')
            
            stats = {
                "total_pending": pending_stats['total_pending'] if pending_stats else 0,
                "by_status": {row['status']: row['count'] for row in status_counts},
                "by_account": {row['account_id']: row['count'] for row in account_counts},
                "by_priority": {
                    "high": pending_stats['high_priority'] if pending_stats else 0,
                    "medium": pending_stats['medium_priority'] if pending_stats else 0,
                    "low": pending_stats['low_priority'] if pending_stats else 0
                },
                "by_age": {
                    "<1h": pending_stats['last_hour'] if pending_stats else 0,
                    "1-6h": pending_stats['last_6h'] if pending_stats else 0,
                    "6-24h": pending_stats['older'] if pending_stats else 0
                },
                "expiring_soon": pending_stats['expiring_soon'] if pending_stats else 0
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get approval stats: {e}")
            return {
                "total_pending": 0,
                "by_account": {},
                "by_priority": {"high": 0, "medium": 0, "low": 0},
                "by_age": {"<1h": 0, "1-6h": 0, "6-24h": 0},
                "expiring_soon": 0,
                "error": str(e)
            }
        finally:
            if conn:
                await db_manager.release_connection(conn)


# Global approval system
_approval_system = None

def get_approval_system() -> ApprovalSystem:
    """Get the global approval system"""
    global _approval_system
    if _approval_system is None:
        _approval_system = ApprovalSystem()
    return _approval_system
