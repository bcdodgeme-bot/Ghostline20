# modules/integrations/telegram/telegram_webhook.py
"""
Telegram Webhook Handler
========================
Processes incoming Telegram updates, specifically callback queries from inline buttons.

This enables one-tap actions:
- User taps "✅ Post This" → callback_data="bsky:post:uuid" → Posts to Bluesky
- User taps "✅ Send Reply" → callback_data="proactive:send:uuid" → Sends email
- User taps "📋 Copy to Slack" → callback_data="proactive:copy:uuid" → Marks as copied
- User taps "📝 Create Tasks" → callback_data="proactive:tasks:uuid" → Creates ClickUp tasks

UPDATED: 2025-12-19 - Added proactive:* callbacks for unified engine

Webhook URL: https://ghostline20-production.up.railway.app/integrations/telegram/webhook
(Note: /integrations prefix from app.py router registration)

Created: 2025-12-19
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from .bot_client import get_bot_client

logger = logging.getLogger(__name__)

# =============================================================================
# CALLBACK PREFIXES
# =============================================================================

# Bluesky proactive actions (original bluesky_proactive_queue)
PREFIX_BSKY_POST = "bsky:post:"      # Post to Bluesky
PREFIX_BSKY_SKIP = "bsky:skip:"      # Skip opportunity
PREFIX_BSKY_EDIT = "bsky:edit:"      # Edit (redirects to chat)

# Unified proactive actions (unified_proactive_queue)
PREFIX_PROACTIVE = "proactive:"      # All unified proactive actions
# Formats: proactive:send:{id}, proactive:skip:{id}, proactive:copy:{id}, etc.

# Meeting-specific actions (for legacy support)
PREFIX_MEETING = "meeting:"          # meeting:copy:{id}, meeting:tasks:{id}, meeting:done:{id}

# Trend-specific actions (for legacy support)
PREFIX_TREND = "trend:"              # trend:draft:{id}, trend:research:{id}, trend:skip:{id}

# Email-specific actions
PREFIX_EMAIL = "email_"              # email_read:{id}, email_archive:{id}, email_ignore:{id}

# Intelligence/situation actions (existing system)
PREFIX_SITUATION = "situation:"       # Existing situation callbacks
PREFIX_AUTO_FEEDBACK = "auto_feedback:"  # Feedback on auto-executed actions

# Engagement actions (legacy - may still be in use)
PREFIX_ENGAGEMENT = "engagement:"     # Legacy engagement callbacks

# Prayer actions
PREFIX_PRAYER = "prayer:"              # prayer:prayed:{user_id}, prayer:skip:{prayer_name}


# =============================================================================
# WEBHOOK HANDLER CLASS
# =============================================================================

class TelegramWebhookHandler:
    """
    Handles incoming Telegram webhook updates.
    
    Routes callback queries to appropriate handlers based on prefix.
    """
    
    def __init__(self):
        self.bot_client = None
        self.bluesky_proactive_engine = None
        self.unified_engine = None
        self.intelligence_orchestrator = None
    
    # =========================================================================
    # LAZY LOADING
    # =========================================================================
    
    def _get_bot_client(self):
        """Lazy load bot client"""
        if not self.bot_client:
            self.bot_client = get_bot_client()
        return self.bot_client
    
    async def _get_bluesky_proactive_engine(self):
        """Lazy load Bluesky proactive engine"""
        if not self.bluesky_proactive_engine:
            try:
                from ..bluesky.proactive_engine import get_proactive_engine
                self.bluesky_proactive_engine = get_proactive_engine()
            except Exception as e:
                logger.warning(f"Could not load Bluesky proactive engine: {e}")
        return self.bluesky_proactive_engine
    
    async def _get_unified_engine(self):
        """Lazy load unified proactive engine"""
        if not self.unified_engine:
            try:
                from modules.proactive.unified_engine import get_unified_engine
                self.unified_engine = get_unified_engine()
            except Exception as e:
                logger.warning(f"Could not load unified engine: {e}")
        return self.unified_engine
    
    async def _get_intelligence_orchestrator(self):
        """Lazy load intelligence orchestrator"""
        if not self.intelligence_orchestrator:
            try:
                from ...intelligence.intelligence_orchestrator import get_intelligence_orchestrator
                from ...core.database import db_manager
                self.intelligence_orchestrator = get_intelligence_orchestrator(db_manager=db_manager)
            except Exception as e:
                logger.warning(f"Could not load intelligence orchestrator: {e}")
        return self.intelligence_orchestrator
    
    # =========================================================================
    # MAIN WEBHOOK HANDLER
    # =========================================================================
    
    async def handle_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for Telegram webhook updates.
        """
        try:
            update_id = update.get('update_id')
            logger.info(f"📥 Received Telegram update: {update_id}")
            
            # Handle callback queries (inline button presses)
            if 'callback_query' in update:
                return await self._handle_callback_query(update['callback_query'])
            
            # Handle regular messages
            if 'message' in update:
                return await self._handle_message(update['message'])
            
            # Handle edited messages
            if 'edited_message' in update:
                logger.debug("Received edited_message update, ignoring")
                return {'success': True, 'action': 'ignored', 'reason': 'edited_message'}
            
            # Unknown update type
            logger.debug(f"Unknown update type: {list(update.keys())}")
            return {'success': True, 'action': 'ignored', 'reason': 'unknown_type'}
            
        except Exception as e:
            logger.error(f"Error handling update: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # CALLBACK QUERY HANDLER
    # =========================================================================
    
    async def _handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callback queries."""
        try:
            callback_id = callback_query.get('id')
            callback_data = callback_query.get('data', '')
            
            # Get context
            from_user = callback_query.get('from', {})
            user_id = from_user.get('id')
            message = callback_query.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            message_id = message.get('message_id')
            
            logger.info(f"🔘 Callback: {callback_data} from user {user_id}")
            
            # Route to appropriate handler
            result = await self._route_callback(
                callback_data=callback_data,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id
            )
            
            # Answer the callback query (removes loading indicator)
            await self._answer_callback(
                callback_id=callback_id,
                text=result.get('toast_message'),
                show_alert=result.get('show_alert', False)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            
            # Try to answer with error
            try:
                await self._answer_callback(
                    callback_id=callback_query.get('id'),
                    text="❌ Error processing action",
                    show_alert=True
                )
            except:
                pass
            
            return {'success': False, 'error': str(e)}
    
    async def _route_callback(
        self,
        callback_data: str,
        user_id: int,
        chat_id: int,
        message_id: int
    ) -> Dict[str, Any]:
        """Route callback to appropriate handler based on prefix."""
        
        # =====================================================================
        # BLUESKY PROACTIVE ACTIONS (bluesky_proactive_queue)
        # =====================================================================
        
        if callback_data.startswith(PREFIX_BSKY_POST):
            queue_id = callback_data[len(PREFIX_BSKY_POST):]
            return await self._handle_bsky_post(queue_id)
        
        if callback_data.startswith(PREFIX_BSKY_SKIP):
            queue_id = callback_data[len(PREFIX_BSKY_SKIP):]
            return await self._handle_bsky_skip(queue_id)
        
        if callback_data.startswith(PREFIX_BSKY_EDIT):
            queue_id = callback_data[len(PREFIX_BSKY_EDIT):]
            return await self._handle_bsky_edit(queue_id)
        
        # =====================================================================
        # UNIFIED PROACTIVE ACTIONS (unified_proactive_queue)
        # =====================================================================
        
        if callback_data.startswith(PREFIX_PROACTIVE):
            return await self._handle_proactive_callback(callback_data)
        
        # =====================================================================
        # MEETING ACTIONS (may use unified or legacy)
        # =====================================================================
        
        if callback_data.startswith(PREFIX_MEETING):
            return await self._handle_meeting_callback(callback_data)
        
        # =====================================================================
        # TREND ACTIONS
        # =====================================================================
        
        if callback_data.startswith(PREFIX_TREND):
            return await self._handle_trend_callback(callback_data)
        
        # =====================================================================
        # EMAIL ACTIONS
        # =====================================================================
        
        if callback_data.startswith(PREFIX_EMAIL):
            return await self._handle_email_callback(callback_data)
        
        # =====================================================================
        # INTELLIGENCE SITUATION ACTIONS
        # =====================================================================
        
        if callback_data.startswith(PREFIX_SITUATION):
            return await self._handle_situation_callback(callback_data, user_id)
        
        if callback_data.startswith(PREFIX_AUTO_FEEDBACK):
            return await self._handle_auto_feedback(callback_data, user_id)
        
        # =====================================================================
        # LEGACY ENGAGEMENT ACTIONS
        # =====================================================================
        
        if callback_data.startswith(PREFIX_ENGAGEMENT):
            return await self._handle_legacy_engagement(callback_data)
        
        # =====================================================================
        # PRAYER ACTIONS
        # =====================================================================
        
        if callback_data.startswith(PREFIX_PRAYER):
            return await self._handle_prayer_callback(callback_data, user_id)
        
        # =====================================================================
        # BARE ACTION FALLBACK (for malformed buttons without prefix)
        # =====================================================================
        
        bare_actions = ['blog', 'research', 'skip', 'post', 'send', 'edit', 'ignore', 'copy', 'tasks', 'done', 'action']
        if callback_data in bare_actions:
            logger.warning(f"⚠️ Received bare action without prefix: '{callback_data}' - check button creation code")
            action_messages = {
                'blog': '📝 Open chat to start blog',
                'research': '🔍 Research mode - open chat',
                'skip': '⏭️ Skipped',
                'post': '🦋 Open chat to post',
                'send': '✅ Open chat to send',
                'edit': '✏️ Open chat to edit',
                'ignore': '🔕 Ignored',
                'copy': '📋 Copied',
                'tasks': '📝 Open chat for tasks',
                'done': '✅ Done',
                'action': '✅ Noted',
            }
            return {
                'success': True,
                'toast_message': action_messages.get(callback_data, '✅ Noted'),
                'show_alert': False
            }
        
        # =====================================================================
        # UNKNOWN CALLBACK
        # =====================================================================
        
        logger.warning(f"Unknown callback data: {callback_data}")
        return {
            'success': False,
            'error': 'Unknown action',
            'toast_message': '❓ Unknown action',
            'show_alert': True
        }
    
    # =========================================================================
    # UNIFIED PROACTIVE HANDLERS
    # =========================================================================
    
    async def _handle_proactive_callback(self, callback_data: str) -> Dict[str, Any]:
        """
        Handle unified proactive actions.
        
        Format: proactive:{action}:{queue_id}
        Actions: send, edit, ignore, copy, tasks, done, blog, post, research, skip, action
        """
        try:
            # Parse callback: proactive:{action}:{queue_id}
            parts = callback_data.split(':')
            if len(parts) < 3:
                return {'success': False, 'toast_message': '❌ Invalid callback', 'show_alert': True}
            
            action = parts[1]
            queue_id = parts[2]
            
            logger.info(f"🎯 Proactive action: {action} on {queue_id}")
            
            engine = await self._get_unified_engine()
            if not engine:
                return {
                    'success': False,
                    'toast_message': '❌ Proactive engine unavailable',
                    'show_alert': True
                }
            
            # Execute the action
            result = await engine.execute_action(queue_id, action)
            
            # Build response based on action
            action_responses = {
                'send': ('✅ Reply Sent!', False),
                'post': ('✅ Posted to Bluesky!', False),
                'copy': ('📋 Copied! Paste into Slack.', False),
                'tasks': ('✅ Tasks Created!', False),
                'blog': ('📝 Blog started in chat', False),
                'research': ('🔍 Research started', False),
                'done': ('✅ Done', False),
                'skip': ('⏭️ Skipped', False),
                'ignore': ('🔕 Ignored', False),
                'edit': ('✏️ Edit in chat', False),
                'action': ('✅ Action taken', False),
            }
            
            if result.get('success'):
                toast, show_alert = action_responses.get(action, ('✅ Done', False))
                return {
                    'success': True,
                    'action': action,
                    'toast_message': toast,
                    'show_alert': show_alert
                }
            else:
                return {
                    'success': False,
                    'action': action,
                    'toast_message': f"❌ {result.get('message', 'Action failed')}",
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error handling proactive callback: {e}", exc_info=True)
            return {
                'success': False,
                'toast_message': '❌ Error processing action',
                'show_alert': True
            }
    
    # =========================================================================
    # MEETING HANDLERS
    # =========================================================================
    
    async def _handle_meeting_callback(self, callback_data: str) -> Dict[str, Any]:
        """
        Handle meeting-specific callbacks.
        
        Format: meeting:{action}:{meeting_id}
        Actions: copy, tasks, done
        """
        try:
            parts = callback_data.split(':')
            if len(parts) < 3:
                return {'success': False, 'toast_message': '❌ Invalid callback', 'show_alert': True}
            
            action = parts[1]
            meeting_id = parts[2]
            
            logger.info(f"📋 Meeting action: {action} on {meeting_id}")
            
            if action == 'copy':
                return {
                    'success': True,
                    'toast_message': '📋 Copied! Paste into Slack.',
                    'show_alert': False
                }
            elif action == 'tasks':
                # TODO: Implement ClickUp task creation
                return {
                    'success': True,
                    'toast_message': '📝 Task creation coming soon!',
                    'show_alert': False
                }
            elif action == 'done':
                return {
                    'success': True,
                    'toast_message': '✅ Done',
                    'show_alert': False
                }
            else:
                return {
                    'success': False,
                    'toast_message': f'❓ Unknown meeting action: {action}',
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error handling meeting callback: {e}")
            return {'success': False, 'toast_message': '❌ Error', 'show_alert': True}
    
    # =========================================================================
    # TREND HANDLERS
    # =========================================================================
    
    async def _handle_trend_callback(self, callback_data: str) -> Dict[str, Any]:
        """
        Handle trend-specific callbacks.
        
        Format: trend:{action}:{trend_id}
        Actions: draft, research, skip, details
        """
        try:
            parts = callback_data.split(':')
            if len(parts) < 3:
                return {'success': False, 'toast_message': '❌ Invalid callback', 'show_alert': True}
            
            action = parts[1]
            trend_id = parts[2]
            
            logger.info(f"📊 Trend action: {action} on {trend_id}")
            
            if action == 'draft':
                return {
                    'success': True,
                    'toast_message': '📝 Draft started in chat',
                    'show_alert': False
                }
            elif action == 'research':
                return {
                    'success': True,
                    'toast_message': '🔍 Research started',
                    'show_alert': False
                }
            elif action == 'skip':
                # Mark trend as processed
                from modules.core.database import db_manager
                await db_manager.execute(
                    "UPDATE trend_opportunities SET processed = true WHERE id = $1",
                    trend_id
                )
                return {
                    'success': True,
                    'toast_message': '⏭️ Skipped',
                    'show_alert': False
                }
            elif action == 'details':
                return {
                    'success': True,
                    'toast_message': '📊 View details in chat',
                    'show_alert': False
                }
            else:
                return {
                    'success': False,
                    'toast_message': f'❓ Unknown trend action: {action}',
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error handling trend callback: {e}")
            return {'success': False, 'toast_message': '❌ Error', 'show_alert': True}
    
    # =========================================================================
    # EMAIL HANDLERS
    # =========================================================================
    
    async def _handle_email_callback(self, callback_data: str) -> Dict[str, Any]:
        """
        Handle email-specific callbacks.
        
        Format: email_{action}:{email_id}
        Actions: read, archive, ignore
        """
        try:
            # Parse email_read:123 or email_archive:123
            parts = callback_data.split(':')
            if len(parts) < 2:
                return {'success': False, 'toast_message': '❌ Invalid callback', 'show_alert': True}
            
            action_part = parts[0]  # email_read, email_archive, email_ignore
            email_id = parts[1]
            
            # Extract action from prefix
            action = action_part.replace('email_', '')
            
            logger.info(f"📧 Email action: {action} on {email_id}")
            
            from modules.core.database import db_manager
            
            if action == 'read':
                await db_manager.execute(
                    "UPDATE google_gmail_analysis SET is_read = true WHERE id = $1",
                    int(email_id)
                )
                return {
                    'success': True,
                    'toast_message': '📖 Marked as read',
                    'show_alert': False
                }
            elif action == 'archive':
                await db_manager.execute(
                    "UPDATE google_gmail_analysis SET archived = true WHERE id = $1",
                    int(email_id)
                )
                return {
                    'success': True,
                    'toast_message': '🗑️ Archived',
                    'show_alert': False
                }
            elif action == 'ignore':
                # Add to ignore list (ignore this specific email)
                await db_manager.execute('''
                    INSERT INTO email_ignore_list (user_id, ignore_type, message_id, reason)
                    SELECT 
                        $1,
                        'message',
                        message_id,
                        'Ignored via Telegram'
                    FROM google_gmail_analysis WHERE id = $2
                    ON CONFLICT DO NOTHING
                ''', 'b7c60682-4815-4d9d-8ebe-66c6cd24eff9', int(email_id))
                return {
                    'success': True,
                    'toast_message': '🔕 Ignored',
                    'show_alert': False
                }
            else:
                return {
                    'success': False,
                    'toast_message': f'❓ Unknown email action: {action}',
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error handling email callback: {e}")
            return {'success': False, 'toast_message': '❌ Error', 'show_alert': True}
    
    # =========================================================================
    # BLUESKY HANDLERS
    # =========================================================================
    
    async def _handle_bsky_post(self, queue_id: str) -> Dict[str, Any]:
        """Handle "Post This" button - actually post to Bluesky"""
        try:
            logger.info(f"📤 Posting to Bluesky: {queue_id}")
            
            engine = await self._get_bluesky_proactive_engine()
            if not engine:
                return {
                    'success': False,
                    'toast_message': '❌ Bluesky engine unavailable',
                    'show_alert': True
                }
            
            result = await engine.execute_post(queue_id)
            
            if result.get('success'):
                return {
                    'success': True,
                    'action': 'posted',
                    'toast_message': '✅ Posted to Bluesky!',
                    'show_alert': False,
                    'posted_uri': result.get('posted_uri')
                }
            else:
                return {
                    'success': False,
                    'action': 'post_failed',
                    'toast_message': f"❌ {result.get('message', 'Post failed')}",
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error posting to Bluesky: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'toast_message': '❌ Error posting',
                'show_alert': True
            }
    
    async def _handle_bsky_skip(self, queue_id: str) -> Dict[str, Any]:
        """Handle "Skip" button - mark opportunity as skipped"""
        try:
            logger.info(f"⏭️ Skipping opportunity: {queue_id}")
            
            engine = await self._get_bluesky_proactive_engine()
            if not engine:
                return {
                    'success': False,
                    'toast_message': '❌ Bluesky engine unavailable',
                    'show_alert': True
                }
            
            result = await engine.skip_opportunity(queue_id)
            
            if result.get('success'):
                return {
                    'success': True,
                    'action': 'skipped',
                    'toast_message': '⏭️ Skipped',
                    'show_alert': False
                }
            else:
                return {
                    'success': False,
                    'action': 'skip_failed',
                    'toast_message': f"❌ {result.get('message', 'Skip failed')}",
                    'show_alert': True
                }
                
        except Exception as e:
            logger.error(f"Error skipping opportunity: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'toast_message': '❌ Error skipping',
                'show_alert': True
            }
    
    async def _handle_bsky_edit(self, queue_id: str) -> Dict[str, Any]:
        """Handle "Edit" button - just acknowledge, user follows URL to chat."""
        logger.info(f"✏️ Edit requested for: {queue_id}")
        
        return {
            'success': True,
            'action': 'edit_redirect',
            'toast_message': '✏️ Opening editor...',
            'show_alert': False
        }
    
    # =========================================================================
    # INTELLIGENCE HANDLERS
    # =========================================================================
    
    async def _handle_situation_callback(
        self,
        callback_data: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Handle intelligence situation action callbacks"""
        try:
            orchestrator = await self._get_intelligence_orchestrator()
            
            if not orchestrator:
                return {
                    'success': False,
                    'toast_message': '❌ Intelligence system unavailable',
                    'show_alert': True
                }
            
            from uuid import UUID
            result = await orchestrator.handle_situation_callback(
                callback_data=callback_data,
                user_id=UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")
            )
            
            return {
                'success': result.get('success', False),
                'toast_message': result.get('message', '✅ Action executed'),
                'show_alert': not result.get('success', False)
            }
            
        except Exception as e:
            logger.error(f"Error handling situation callback: {e}", exc_info=True)
            return {
                'success': False,
                'toast_message': f'❌ Error: {str(e)[:50]}',
                'show_alert': True
            }
    
    async def _handle_auto_feedback(
        self,
        callback_data: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Handle feedback on auto-executed actions"""
        try:
            orchestrator = await self._get_intelligence_orchestrator()
            
            if not orchestrator:
                return {
                    'success': False,
                    'toast_message': '❌ Intelligence system unavailable',
                    'show_alert': True
                }
            
            from uuid import UUID
            result = await orchestrator.handle_auto_feedback(
                callback_data=callback_data,
                user_id=UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")
            )
            
            return {
                'success': result.get('success', False),
                'toast_message': result.get('message', '👍 Feedback recorded'),
                'show_alert': False
            }
            
        except Exception as e:
            logger.error(f"Error handling auto feedback: {e}", exc_info=True)
            return {
                'success': False,
                'toast_message': f'❌ Error: {str(e)[:50]}',
                'show_alert': True
            }
    
    # =========================================================================
    # LEGACY HANDLERS
    # =========================================================================
    
    async def _handle_legacy_engagement(self, callback_data: str) -> Dict[str, Any]:
        """Handle legacy engagement callbacks."""
        logger.warning(f"Legacy engagement callback received: {callback_data}")
        
        parts = callback_data.split(':')
        if len(parts) >= 3:
            action = parts[1]
            
            if action == 'view':
                return {
                    'success': True,
                    'toast_message': '👀 Use "View Post" button',
                    'show_alert': False
                }
            elif action == 'skip':
                return {
                    'success': True,
                    'toast_message': '⏭️ Noted (legacy action)',
                    'show_alert': False
                }
            else:
                return {
                    'success': True,
                    'toast_message': '⚠️ Please use newer notifications',
                    'show_alert': True
                }
        
        return {
            'success': False,
            'toast_message': '❌ Invalid legacy callback',
            'show_alert': True
        }
    
    # =========================================================================
    # PRAYER HANDLERS
    # =========================================================================
    
    async def _handle_prayer_callback(
        self,
        callback_data: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Handle prayer-related callbacks.
        
        Format: prayer:{action}:{user_id_or_prayer_name}
        Actions: prayed, skip, remind_later
        """
        try:
            parts = callback_data.split(':')
            if len(parts) < 3:
                return {'success': False, 'toast_message': '❌ Invalid prayer callback', 'show_alert': True}
            
            action = parts[1]
            target = parts[2]  # user_id or prayer name
            
            logger.info(f"🕌 Prayer action: {action} for {target}")
            
            if action == 'prayed':
                # User marked prayer as completed
                try:
                    from modules.core.database import db_manager
                    conn = await db_manager.get_connection()
                    try:
                        # Record prayer completion
                        await conn.execute('''
                            INSERT INTO prayer_log (user_id, prayer_name, prayed_at, action)
                            VALUES ($1, $2, NOW(), 'prayed')
                            ON CONFLICT DO NOTHING
                        ''', target, 'current')  # target is user_id here
                    finally:
                        await db_manager.release_connection(conn)
                except Exception as e:
                    logger.warning(f"Could not log prayer (table may not exist): {e}")
                
                return {
                    'success': True,
                    'toast_message': '🕌 Prayer logged. May it be accepted!',
                    'show_alert': False
                }
            
            elif action == 'skip':
                return {
                    'success': True,
                    'toast_message': '⏭️ Skipped',
                    'show_alert': False
                }
            
            elif action == 'remind_later':
                return {
                    'success': True,
                    'toast_message': '⏰ Will remind you later',
                    'show_alert': False
                }
            
            else:
                return {
                    'success': True,
                    'toast_message': f'✅ {action.title()}',
                    'show_alert': False
                }
                
        except Exception as e:
            logger.error(f"Error handling prayer callback: {e}", exc_info=True)
            return {
                'success': False,
                'toast_message': '❌ Error processing prayer action',
                'show_alert': True
            }
    
    # =========================================================================
    # MESSAGE HANDLER
    # =========================================================================
    
    async def _handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle regular text messages."""
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        
        logger.debug(f"Received message in chat {chat_id}: {text[:50]}...")
        
        return {
            'success': True,
            'action': 'message_received',
            'chat_id': chat_id
        }
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def _answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """Answer a callback query to remove the loading indicator."""
        try:
            bot_client = self._get_bot_client()
            return await bot_client.answer_callback_query(
                callback_query_id=callback_id,
                text=text,
                show_alert=show_alert
            )
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
            return False


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_webhook_handler: Optional[TelegramWebhookHandler] = None


def get_webhook_handler() -> TelegramWebhookHandler:
    """Get the singleton webhook handler instance"""
    global _webhook_handler
    if _webhook_handler is None:
        _webhook_handler = TelegramWebhookHandler()
    return _webhook_handler


# =============================================================================
# CONVENIENCE FUNCTION FOR FASTAPI
# =============================================================================

async def process_telegram_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a Telegram update - convenience function for FastAPI route.
    
    Usage in router:
        @router.post("/telegram/webhook")
        async def telegram_webhook(update: dict):
            return await process_telegram_update(update)
    """
    handler = get_webhook_handler()
    return await handler.handle_update(update)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'TelegramWebhookHandler',
    'get_webhook_handler',
    'process_telegram_update',
]
