# modules/integrations/bluesky/proactive_engine.py
"""
Proactive Bluesky Engine
========================
Single unified flow: Detect → Draft → Store → Notify → Execute

This replaces the disconnected flow between:
- engagement_detector (stored opportunities without drafts)
- approval_system (stored drafts disconnected from notifications)
- bluesky_notifications (queried wrong table)

Now everything happens in one place:
1. Opportunity detected
2. AI draft generated IMMEDIATELY with personality
3. Stored in unified bluesky_proactive_queue table
4. Rich Telegram notification sent with draft + action buttons
5. One-tap execution when user presses button

Created: 2025-12-19
Updated: 2026-01-02 - Added task_type="quick" for Mercury model routing
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID, uuid4

from ...core.database import db_manager
from ..telegram.bot_client import get_bot_client

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

# Personality prompts for AI draft generation
PERSONALITY_PROMPTS = {
    'syntaxprime': """You are Carl's personal voice on Bluesky. Your tone is:
- Sarcastic but genuinely helpful
- Witty with sharp observations
- Authentic and unfiltered (but PG-13)
- You make people laugh while making a point
- You're the friend who tells it like it is

Examples of your voice:
- "Oh look, another platform that thinks 'user experience' means 'how many clicks until they give up'"
- "This hits different when you've spent 3 hours debugging a typo"
- "Finally someone said it. The emperor has no clothes AND no error handling"
""",

    'professional': """You are posting for Rose & Angel, a non-profit consulting agency. Your tone is:
- Professional and respectful
- Thoughtful and measured
- Focused on community impact
- Business-appropriate at all times
- NO humor, NO sarcasm, NO casual language

This represents a serious consulting business serving non-profits.
""",

    'compassionate': """You are posting for Meals n Feelz, an Islamic giving and food program. Your tone is:
- Warm and empathetic
- Community-focused
- Respectful of religious and cultural context
- Supportive and encouraging
- Absolutely NO sarcasm or humor

Focus on compassion, community support, and positive impact.
""",

    'creative_dumping': """You are Carl's creative outlet account (Damn it Carl). Your tone is:
- Raw and authentic
- Creative and unfiltered
- This is therapy through posting
- You can be as creative and weird as you want
- Stream of consciousness is welcome

This is the account where Carl dumps his creative energy.
"""
}

# Account to personality mapping
ACCOUNT_PERSONALITIES = {
    'personal': 'syntaxprime',
    'bcdodgeme': 'syntaxprime',
    'rose_angel': 'professional',
    'roseandangel': 'professional',
    'binge_tv': 'syntaxprime',
    'tvsignals': 'syntaxprime',
    'meals_feelz': 'compassionate',
    'mealsnfeelz': 'compassionate',
    'damn_it_carl': 'creative_dumping',
    'damnitcarl': 'creative_dumping',
    'syntax-ceo': 'creative_dumping',
}

# Minimum score to generate a draft (saves API calls)
MIN_SCORE_FOR_DRAFT = 50

# =============================================================================
# PROACTIVE ENGINE CLASS
# =============================================================================

class ProactiveBlueskyEngine:
    """
    Unified proactive engagement system for Bluesky.
    
    One flow does it all:
    1. process_opportunity() - Detect, score, draft, store, notify
    2. execute_post() - Actually post to Bluesky (called from Telegram button)
    3. skip_opportunity() - Mark as skipped
    4. edit_and_post() - Edit draft then post
    """
    
    def __init__(self):
        self.bluesky_client = None
        self.openrouter_client = None
        self._telegram_chat_id = None
    
    # =========================================================================
    # LAZY LOADING
    # =========================================================================
    
    async def _get_bluesky_client(self):
        """Lazy load Bluesky multi-account client"""
        if not self.bluesky_client:
            from .multi_account_client import get_bluesky_multi_client
            self.bluesky_client = get_bluesky_multi_client()
        return self.bluesky_client
    
    async def _get_openrouter_client(self):
        """Lazy load OpenRouter client"""
        if not self.openrouter_client:
            from ...ai.openrouter_client import get_openrouter_client
            self.openrouter_client = await get_openrouter_client()
        return self.openrouter_client
    
    async def _get_telegram_chat_id(self) -> Optional[int]:
        """Get Telegram chat ID for notifications"""
        if self._telegram_chat_id:
            return self._telegram_chat_id
        
        try:
            conn = await db_manager.get_connection()
            try:
                row = await conn.fetchrow('''
                    SELECT telegram_chat_id FROM user_preferences 
                    WHERE user_id = $1 AND telegram_chat_id IS NOT NULL
                    LIMIT 1
                ''', UUID(USER_ID))
                
                if row:
                    self._telegram_chat_id = row['telegram_chat_id']
                    return self._telegram_chat_id
            finally:
                await db_manager.release_connection(conn)
        except Exception as e:
            logger.warning(f"Could not get Telegram chat ID: {e}")
        
        return None
    
    # =========================================================================
    # MAIN FLOW: PROCESS OPPORTUNITY
    # =========================================================================
    
    async def process_opportunity(
        self,
        post: Dict[str, Any],
        account_id: str,
        matched_keywords: List[str],
        engagement_score: float,
        opportunity_type: str = 'reply'
    ) -> Optional[str]:
        """
        Process a single post as potential opportunity.
        
        This is THE main method that does everything:
        1. Validates and extracts post data
        2. Generates AI draft with personality
        3. Stores in unified queue
        4. Sends rich Telegram notification
        
        Args:
            post: Raw post data from Bluesky API
            account_id: Which account detected this (personal, damn_it_carl, etc.)
            matched_keywords: Keywords that matched
            engagement_score: 0-100 score
            opportunity_type: reply, quote_post, like, repost
            
        Returns:
            queue_id if opportunity created, None if skipped/failed
        """
        try:
            # Skip low-scoring opportunities
            if engagement_score < MIN_SCORE_FOR_DRAFT:
                logger.debug(f"Skipping low-score opportunity: {engagement_score}")
                return None
            
            # Extract post data
            post_data = self._extract_post_data(post)
            if not post_data:
                logger.warning("Could not extract post data")
                return None
            
            # Check for duplicates
            if await self._is_duplicate(post_data['post_uri'], account_id):
                logger.debug(f"Duplicate opportunity: {post_data['post_uri']}")
                return None
            
            # Generate AI draft
            draft_result = await self._generate_ai_draft(
                original_text=post_data['text'],
                author_handle=post_data['author_handle'],
                author_display_name=post_data['author_display_name'],
                account_id=account_id,
                matched_keywords=matched_keywords,
                opportunity_type=opportunity_type
            )
            
            if not draft_result['success']:
                logger.warning(f"Draft generation failed: {draft_result.get('error')}")
                return None
            
            # Determine priority
            priority = self._calculate_priority(engagement_score, matched_keywords)
            
            # Store in database
            queue_id = await self._store_opportunity(
                post_data=post_data,
                account_id=account_id,
                matched_keywords=matched_keywords,
                engagement_score=engagement_score,
                opportunity_type=opportunity_type,
                draft_text=draft_result['draft_text'],
                personality_used=draft_result['personality'],
                model_used=draft_result.get('model'),
                priority=priority
            )
            
            if not queue_id:
                logger.error("Failed to store opportunity")
                return None
            
            # Send Telegram notification
            await self._send_notification(
                queue_id=queue_id,
                post_data=post_data,
                account_id=account_id,
                draft_text=draft_result['draft_text'],
                engagement_score=engagement_score,
                priority=priority
            )
            
            logger.info(f"✅ Proactive opportunity created: {queue_id} for {account_id}")
            return queue_id
            
        except Exception as e:
            logger.error(f"Error processing opportunity: {e}", exc_info=True)
            return None
    
    # =========================================================================
    # POST DATA EXTRACTION
    # =========================================================================
    
    def _extract_post_data(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract relevant data from Bluesky post object"""
        try:
            # Handle both timeline format and direct post format
            post_obj = post.get('post', post)
            
            # Get URI and CID
            post_uri = post_obj.get('uri', '')
            post_cid = post_obj.get('cid', '')
            
            if not post_uri:
                return None
            
            # Get author info
            author = post_obj.get('author', {})
            author_handle = author.get('handle', 'unknown')
            author_did = author.get('did', '')
            author_display_name = author.get('displayName', author_handle)
            
            # Get post text
            record = post_obj.get('record', {})
            text = record.get('text', '')
            
            if not text:
                return None
            
            # Get post creation time
            created_at_str = record.get('createdAt')
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # Build Bluesky web URL
            bluesky_url = self._build_bluesky_url(post_uri, author_handle)
            
            return {
                'post_uri': post_uri,
                'post_cid': post_cid,
                'bluesky_url': bluesky_url,
                'author_handle': author_handle,
                'author_did': author_did,
                'author_display_name': author_display_name,
                'text': text,
                'created_at': created_at
            }
            
        except Exception as e:
            logger.error(f"Error extracting post data: {e}")
            return None
    
    def _build_bluesky_url(self, post_uri: str, author_handle: str) -> str:
        """Build clickable Bluesky web URL from post URI"""
        try:
            # Format: at://did:plc:xxx/app.bsky.feed.post/yyy
            # Target: https://bsky.app/profile/handle/post/yyy
            
            if not post_uri.startswith('at://'):
                return f"https://bsky.app/profile/{author_handle}"
            
            parts = post_uri.replace('at://', '').split('/')
            if len(parts) >= 3:
                post_id = parts[2]
                return f"https://bsky.app/profile/{author_handle}/post/{post_id}"
            
            return f"https://bsky.app/profile/{author_handle}"
            
        except Exception:
            return f"https://bsky.app/profile/{author_handle}"
    
    # =========================================================================
    # AI DRAFT GENERATION
    # =========================================================================
    
    async def _generate_ai_draft(
        self,
        original_text: str,
        author_handle: str,
        author_display_name: str,
        account_id: str,
        matched_keywords: List[str],
        opportunity_type: str
    ) -> Dict[str, Any]:
        """
        Generate AI draft using OpenRouter with personality.
        
        Returns:
            Dict with success, draft_text, personality, model
        """
        try:
            # Get personality for this account
            personality_key = ACCOUNT_PERSONALITIES.get(account_id, 'syntaxprime')
            personality_prompt = PERSONALITY_PROMPTS.get(personality_key, PERSONALITY_PROMPTS['syntaxprime'])
            
            # Build the generation prompt
            action_verb = {
                'reply': 'reply to',
                'quote_post': 'quote post',
                'like': 'comment on',
                'repost': 'respond to'
            }.get(opportunity_type, 'reply to')
            
            keywords_str = ', '.join(matched_keywords[:5]) if matched_keywords else 'general interest'
            
            messages = [
                {
                    'role': 'system',
                    'content': f"""{personality_prompt}

You are generating a Bluesky post. CRITICAL REQUIREMENTS:
- Maximum 280 characters (this is a HARD LIMIT)
- Sound natural, not like AI
- Don't start with "I" 
- Don't use hashtags
- Don't be sycophantic or overly agreeable
- Add value to the conversation
- Match the tone described above EXACTLY"""
                },
                {
                    'role': 'user',
                    'content': f"""Generate a {action_verb} this Bluesky post:

Author: {author_display_name} (@{author_handle})
Post: "{original_text}"

Relevant topics: {keywords_str}

Write ONLY the reply text, nothing else. Max 280 characters."""
                }
            ]
            
            # Call OpenRouter - use Mercury for fast Bluesky drafts
            client = await self._get_openrouter_client()
            response = await client.chat_completion(
                messages=messages,
                max_tokens=150,
                temperature=0.8,  # Slightly creative
                task_type="quick"  # Mercury for speed
            )
            
            # Extract response
            draft_text = response['choices'][0]['message']['content'].strip()
            
            # Clean up the draft
            draft_text = self._clean_draft(draft_text)
            
            # Enforce character limit
            if len(draft_text) > 280:
                draft_text = draft_text[:277] + "..."
            
            model_used = response.get('_metadata', {}).get('model_used', 'unknown')
            
            logger.info(f"✅ Generated draft ({len(draft_text)} chars) with {personality_key} personality")
            
            return {
                'success': True,
                'draft_text': draft_text,
                'personality': personality_key,
                'model': model_used
            }
            
        except Exception as e:
            logger.error(f"AI draft generation failed: {e}", exc_info=True)
            
            # Fallback to simple template
            fallback = self._generate_fallback_draft(account_id, opportunity_type)
            return {
                'success': True,
                'draft_text': fallback,
                'personality': 'fallback',
                'model': 'template',
                'fallback': True
            }
    
    def _clean_draft(self, draft_text: str) -> str:
        """Clean up AI-generated draft"""
        # Remove quotes if the AI wrapped it
        draft_text = draft_text.strip('"\'')
        
        # Remove "Here's a reply:" type prefixes
        prefixes_to_remove = [
            'Here\'s a reply:',
            'Here is a reply:',
            'Reply:',
            'Response:',
            'Draft:',
        ]
        for prefix in prefixes_to_remove:
            if draft_text.lower().startswith(prefix.lower()):
                draft_text = draft_text[len(prefix):].strip()
        
        return draft_text.strip()
    
    def _generate_fallback_draft(self, account_id: str, opportunity_type: str) -> str:
        """Generate simple fallback draft if AI fails"""
        personality = ACCOUNT_PERSONALITIES.get(account_id, 'syntaxprime')
        
        fallbacks = {
            'syntaxprime': [
                "This resonates more than it should.",
                "Finally, someone gets it.",
                "This is the content I'm here for.",
            ],
            'professional': [
                "Thank you for sharing this valuable perspective.",
                "This raises important considerations for the sector.",
            ],
            'compassionate': [
                "Thank you for sharing this with our community.",
                "This is a beautiful reminder of what matters.",
            ],
            'creative_dumping': [
                "This hit different.",
                "Mood.",
            ]
        }
        
        import random
        options = fallbacks.get(personality, fallbacks['syntaxprime'])
        return random.choice(options)
    
    # =========================================================================
    # PRIORITY CALCULATION
    # =========================================================================
    
    def _calculate_priority(self, engagement_score: float, matched_keywords: List[str]) -> str:
        """Calculate priority based on score and keywords"""
        if engagement_score >= 80 or len(matched_keywords) >= 5:
            return 'high'
        elif engagement_score >= 60 or len(matched_keywords) >= 3:
            return 'medium'
        else:
            return 'low'
    
    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================
    
    async def _is_duplicate(self, post_uri: str, account_id: str) -> bool:
        """Check if we already have this opportunity"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            row = await conn.fetchrow('''
                SELECT id FROM bluesky_proactive_queue
                WHERE post_uri = $1 AND detected_by_account = $2
            ''', post_uri, account_id)
            return row is not None
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _store_opportunity(
        self,
        post_data: Dict[str, Any],
        account_id: str,
        matched_keywords: List[str],
        engagement_score: float,
        opportunity_type: str,
        draft_text: str,
        personality_used: str,
        model_used: str,
        priority: str
    ) -> Optional[str]:
        """Store opportunity in database"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            queue_id = str(uuid4())
            
            await conn.execute('''
                INSERT INTO bluesky_proactive_queue (
                    id,
                    post_uri,
                    post_cid,
                    bluesky_url,
                    author_handle,
                    author_did,
                    author_display_name,
                    original_text,
                    original_post_created_at,
                    detected_by_account,
                    matched_keywords,
                    engagement_score,
                    opportunity_type,
                    draft_text,
                    personality_used,
                    draft_generation_model,
                    priority,
                    status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 'pending')
            ''',
                UUID(queue_id),
                post_data['post_uri'],
                post_data.get('post_cid'),
                post_data['bluesky_url'],
                post_data['author_handle'],
                post_data.get('author_did'),
                post_data.get('author_display_name'),
                post_data['text'],
                post_data.get('created_at'),
                account_id,
                json.dumps(matched_keywords),
                engagement_score,
                opportunity_type,
                draft_text,
                personality_used,
                model_used,
                priority
            )
            
            return queue_id
            
        except Exception as e:
            logger.error(f"Failed to store opportunity: {e}", exc_info=True)
            return None
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    # =========================================================================
    # TELEGRAM NOTIFICATION
    # =========================================================================
    
    async def _send_notification(
        self,
        queue_id: str,
        post_data: Dict[str, Any],
        account_id: str,
        draft_text: str,
        engagement_score: float,
        priority: str
    ) -> bool:
        """Send rich Telegram notification with draft and action buttons"""
        try:
            chat_id = await self._get_telegram_chat_id()
            if not chat_id:
                logger.warning("No Telegram chat ID configured")
                return False
            
            # Format account name
            account_display = account_id.replace('_', ' ').title()
            
            # Priority emoji
            priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(priority, '⚪')
            
            # Truncate original post for display
            original_preview = post_data['text']
            if len(original_preview) > 200:
                original_preview = original_preview[:197] + "..."
            
            # Build message
            message = f"🦋 *Bluesky • {account_display}*\n\n"
            message += f"@{post_data['author_handle']} posted:\n"
            message += f"_{original_preview}_\n\n"
            message += f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            message += f"📝 *Your Reply \\(Ready to Post\\):*\n"
            message += f"`{self._escape_markdown(draft_text)}`\n\n"
            message += f"{priority_emoji} Score: {int(engagement_score)}/100"
            
            # Build action buttons
            buttons = [
                [
                    {"text": "👀 View Post", "url": post_data['bluesky_url']}
                ],
                [
                    {"text": "✅ Post This", "callback_data": f"bsky:post:{queue_id}"},
                    {"text": "❌ Skip", "callback_data": f"bsky:skip:{queue_id}"}
                ],
                [
                    {"text": "✏️ Edit in Chat", "url": f"https://ghostline20-production.up.railway.app/chat?draft={queue_id}"}
                ]
            ]
            
            # Send via bot_client
            bot_client = get_bot_client()
            result = await bot_client.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='MarkdownV2',
                buttons=buttons
            )
            
            # Store Telegram message ID for later editing
            if result.get('success') and result.get('message_id'):
                await self._update_telegram_info(
                    queue_id=queue_id,
                    message_id=result['message_id'],
                    chat_id=chat_id
                )
            
            return result.get('success', False)
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return False
    
    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for MarkdownV2"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def _update_telegram_info(self, queue_id: str, message_id: int, chat_id: int) -> None:
        """Store Telegram message info for later editing"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            await conn.execute('''
                UPDATE bluesky_proactive_queue
                SET telegram_message_id = $1,
                    telegram_chat_id = $2,
                    notification_sent_at = NOW()
                WHERE id = $3
            ''', message_id, chat_id, UUID(queue_id))
        except Exception as e:
            logger.error(f"Failed to update Telegram info: {e}")
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    # =========================================================================
    # EXECUTION: POST TO BLUESKY
    # =========================================================================
    
    async def execute_post(self, queue_id: str) -> Dict[str, Any]:
        """
        Execute a pending post to Bluesky.
        Called from Telegram webhook when user taps "Post This".
        
        Args:
            queue_id: UUID of the proactive_queue item
            
        Returns:
            Dict with success, message, posted_uri
        """
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get the opportunity
            row = await conn.fetchrow('''
                SELECT 
                    id, post_uri, post_cid, author_did,
                    detected_by_account, draft_text, edited_text,
                    status, telegram_message_id, telegram_chat_id
                FROM bluesky_proactive_queue
                WHERE id = $1
            ''', UUID(queue_id))
            
            if not row:
                return {'success': False, 'message': 'Opportunity not found'}
            
            if row['status'] != 'pending':
                return {'success': False, 'message': f"Already {row['status']}"}
            
            # Use edited text if available, otherwise draft
            text_to_post = row['edited_text'] or row['draft_text']
            account_id = row['detected_by_account']
            
            # Build reply reference
            reply_ref = None
            if row['post_uri'] and row['post_cid']:
                reply_ref = {
                    "root": {
                        "uri": row['post_uri'],
                        "cid": row['post_cid']
                    },
                    "parent": {
                        "uri": row['post_uri'],
                        "cid": row['post_cid']
                    }
                }
            
            # Post to Bluesky
            bluesky_client = await self._get_bluesky_client()
            result = await bluesky_client.create_post(
                account_id=account_id,
                text=text_to_post,
                reply_to=reply_ref
            )
            
            if result.get('success'):
                # Update database
                await conn.execute('''
                    UPDATE bluesky_proactive_queue
                    SET status = 'posted',
                        posted_uri = $1,
                        posted_cid = $2,
                        posted_at = NOW(),
                        actioned_at = NOW()
                    WHERE id = $3
                ''', result.get('uri'), result.get('cid'), UUID(queue_id))
                
                # Update Telegram message to show success
                if row['telegram_message_id'] and row['telegram_chat_id']:
                    await self._update_telegram_posted(
                        message_id=row['telegram_message_id'],
                        chat_id=row['telegram_chat_id'],
                        posted_uri=result.get('uri'),
                        account_id=account_id
                    )
                
                logger.info(f"✅ Posted to Bluesky: {result.get('uri')}")
                return {
                    'success': True,
                    'message': 'Posted successfully!',
                    'posted_uri': result.get('uri')
                }
            else:
                # Update with error
                error_msg = result.get('error', 'Unknown error')
                await conn.execute('''
                    UPDATE bluesky_proactive_queue
                    SET status = 'error',
                        error_message = $1,
                        actioned_at = NOW()
                    WHERE id = $2
                ''', error_msg, UUID(queue_id))
                
                return {'success': False, 'message': f'Posting failed: {error_msg}'}
                
        except Exception as e:
            logger.error(f"Error executing post: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _update_telegram_posted(
        self,
        message_id: int,
        chat_id: int,
        posted_uri: str,
        account_id: str
    ) -> None:
        """Update Telegram message to show posting success"""
        try:
            # Build success message
            account_display = account_id.replace('_', ' ').title()
            
            # Try to build URL to the posted reply
            posted_url = None
            if posted_uri and posted_uri.startswith('at://'):
                parts = posted_uri.replace('at://', '').split('/')
                if len(parts) >= 3:
                    did = parts[0]
                    post_id = parts[2]
                    posted_url = f"https://bsky.app/profile/{did}/post/{post_id}"
            
            message = f"🦋 *Bluesky • {account_display}*\n\n"
            message += f"✅ *Posted successfully\\!*\n\n"
            
            buttons = []
            if posted_url:
                message += f"Your reply is now live\\."
                buttons = [[{"text": "👀 View Your Reply", "url": posted_url}]]
            
            bot_client = get_bot_client()
            await bot_client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                parse_mode='MarkdownV2',
                buttons=buttons if buttons else None
            )
            
        except Exception as e:
            logger.error(f"Failed to update Telegram message: {e}")
    
    # =========================================================================
    # SKIP OPPORTUNITY
    # =========================================================================
    
    async def skip_opportunity(self, queue_id: str, reason: str = "") -> Dict[str, Any]:
        """
        Mark opportunity as skipped.
        Called from Telegram webhook when user taps "Skip".
        """
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get opportunity
            row = await conn.fetchrow('''
                SELECT id, status, telegram_message_id, telegram_chat_id, detected_by_account
                FROM bluesky_proactive_queue
                WHERE id = $1
            ''', UUID(queue_id))
            
            if not row:
                return {'success': False, 'message': 'Opportunity not found'}
            
            if row['status'] != 'pending':
                return {'success': False, 'message': f"Already {row['status']}"}
            
            # Update status
            await conn.execute('''
                UPDATE bluesky_proactive_queue
                SET status = 'skipped',
                    skip_reason = $1,
                    actioned_at = NOW()
                WHERE id = $2
            ''', reason or 'User skipped', UUID(queue_id))
            
            # Update Telegram message
            if row['telegram_message_id'] and row['telegram_chat_id']:
                await self._update_telegram_skipped(
                    message_id=row['telegram_message_id'],
                    chat_id=row['telegram_chat_id'],
                    account_id=row['detected_by_account']
                )
            
            logger.info(f"⏭️ Skipped opportunity: {queue_id}")
            return {'success': True, 'message': 'Skipped'}
            
        except Exception as e:
            logger.error(f"Error skipping opportunity: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _update_telegram_skipped(
        self,
        message_id: int,
        chat_id: int,
        account_id: str
    ) -> None:
        """Update Telegram message to show skipped"""
        try:
            account_display = account_id.replace('_', ' ').title()
            
            message = f"🦋 *Bluesky • {account_display}*\n\n"
            message += f"⏭️ *Skipped*"
            
            bot_client = get_bot_client()
            await bot_client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                parse_mode='MarkdownV2',
                buttons=None  # Remove buttons
            )
            
        except Exception as e:
            logger.error(f"Failed to update Telegram message: {e}")
    
    # =========================================================================
    # EDIT AND POST
    # =========================================================================
    
    async def edit_and_post(self, queue_id: str, new_text: str) -> Dict[str, Any]:
        """
        Edit draft text and then post.
        Called from web chat when user edits the draft.
        """
        if len(new_text) > 300:
            return {'success': False, 'message': f'Text too long ({len(new_text)}/300)'}
        
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Update with edited text
            await conn.execute('''
                UPDATE bluesky_proactive_queue
                SET edited_text = $1
                WHERE id = $2 AND status = 'pending'
            ''', new_text.strip(), UUID(queue_id))
            
            # Now execute
            return await self.execute_post(queue_id)
            
        except Exception as e:
            logger.error(f"Error in edit_and_post: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def get_pending_opportunities(
        self,
        account_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get pending opportunities for display/management"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            if account_id:
                rows = await conn.fetch('''
                    SELECT * FROM bluesky_active_opportunities
                    WHERE detected_by_account = $1
                    LIMIT $2
                ''', account_id, limit)
            else:
                rows = await conn.fetch('''
                    SELECT * FROM bluesky_active_opportunities
                    LIMIT $1
                ''', limit)
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting pending opportunities: {e}")
            return []
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def cleanup_expired(self) -> int:
        """Mark expired opportunities"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            result = await conn.execute('''
                UPDATE bluesky_proactive_queue
                SET status = 'expired',
                    actioned_at = NOW()
                WHERE status = 'pending'
                  AND expires_at < NOW()
            ''')
            
            # Extract count
            count = int(result.split()[-1]) if result else 0
            
            if count > 0:
                logger.info(f"🗑️ Marked {count} expired opportunities")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired: {e}")
            return 0
        finally:
            if conn:
                await db_manager.release_connection(conn)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_engine_instance: Optional[ProactiveBlueskyEngine] = None


def get_proactive_engine() -> ProactiveBlueskyEngine:
    """Get the singleton ProactiveBlueskyEngine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ProactiveBlueskyEngine()
    return _engine_instance


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'ProactiveBlueskyEngine',
    'get_proactive_engine',
    'PERSONALITY_PROMPTS',
    'ACCOUNT_PERSONALITIES',
]
