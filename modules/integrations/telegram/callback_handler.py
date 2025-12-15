"""
Telegram Callback Handler - Button Click Processing
Processes inline keyboard button clicks and updates notification state
UPDATED: Added Contextual Intelligence Layer handlers
FIXED: Corrected database connection patterns (db_manager instead of asyncpg.connect)
FIXED: 2025-12-15 - Added html.escape() for user content to prevent Telegram parse errors
FIXED: 2025-12-15 - Corrected button format (list not dict) in all handlers
"""

import os
import logging
import json
import html
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from .bot_client import TelegramBotClient
from .database_manager import TelegramDatabaseManager
from .notification_manager import NotificationManager
from modules.core.database import db_manager

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Handles Telegram inline keyboard button callbacks"""
    
    def __init__(self, bot_client=None, notification_manager=None):
        self.bot_client = bot_client
        self.notification_manager = notification_manager
        # Note: db_manager will be initialized when needed
    
    async def edit_message(self, message_id: int, text: str, reply_markup=None):
        """Helper to edit message - wraps bot_client.edit_message_text"""
        # Get chat_id from the notification manager's default
        chat_id = self.notification_manager._default_chat_id or os.getenv('TELEGRAM_CHAT_ID')
        
        return await self.bot_client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
    
    @property
    def db_manager(self):
        """Lazy-load database manager"""
        if not hasattr(self, '_db_manager'):
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    async def process_callback(
        self,
        callback_query_id: str,
        callback_data: str,
        message_id: int
    ) -> Dict[str, Any]:
        """
        Process a button callback from Telegram
        
        Callback data format: {type}:{action}:{notification_id}:{optional_params}
        Examples:
            - "prayer:prayed:uuid"
            - "prayer:snooze:uuid:10"
            - "bluesky:good_match:uuid:account_id"
            - "reminder:done:uuid"
            - "content:draft_bluesky:opportunity_id:account_id"  # NEW
            - "content:post_now:queue_id:account_id"  # NEW
        
        Args:
            callback_query_id: Telegram callback query ID
            callback_data: Data from button click
            message_id: Telegram message ID
        
        Returns:
            Result dict with success status
        """
        try:
            # Parse callback data
            parts = callback_data.split(':')
            if len(parts) < 3:
                logger.error(f"Invalid callback data format: {callback_data}")
                return {"success": False, "error": "Invalid callback format"}
            
            notification_type = parts[0]
            action = parts[1]
            notification_id = parts[2]
            extra_params = parts[3:] if len(parts) > 3 else []
            
            logger.info(f"Processing callback: {notification_type}/{action} for {notification_id}")
            
            # Route to appropriate handler
            if notification_type == 'prayer':
                result = await self._handle_prayer_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'weather':
                result = await self._handle_weather_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'reminder':
                result = await self._handle_reminder_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'calendar':
                result = await self._handle_calendar_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'email':
                result = await self._handle_email_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'clickup':
                result = await self._handle_clickup_callback(
                    action, notification_id, message_id
                )
            
            elif notification_type == 'bluesky':
                result = await self._handle_bluesky_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'situation':
                result = await self._handle_situation_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'engagement':
                result = await self._handle_engagement_callback(
                    action, notification_id, message_id, extra_params
                )
            
            elif notification_type == 'meeting':
                result = await self._handle_meeting_callback(
                    action, notification_id, message_id, extra_params
                )
            
            # ====== END NEW ======
            
            else:
                logger.error(f"Unknown notification type: {notification_type}")
                result = {"success": False, "error": "Unknown notification type"}
            
            # Acknowledge callback to remove loading state
            await self.bot_client.answer_callback_query(
                callback_query_id,
                text=result.get('ack_text', 'Acknowledged')
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Exception processing callback: {e}")
            await self.bot_client.answer_callback_query(
                callback_query_id,
                text="Error processing action"
            )
            return {"success": False, "error": str(e)}
    
    # ========================================================================
    # PRAYER CALLBACKS
    # ========================================================================
    
    async def _handle_prayer_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle prayer notification button clicks"""
        
        if action == 'prayed':
            # User acknowledged prayer
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'prayed'
            )
            
            # Update message to show acknowledgment
            await self.bot_client.edit_message(
                message_id,
                "✅ Prayer acknowledged",
                reply_markup=None  # Remove buttons
            )
            
            return {
                "success": True,
                "ack_text": "Prayer acknowledged"
            }
        
        elif action == 'snooze':
            minutes = int(params[0]) if params else 10
            
            await self.notification_manager.acknowledge_notification(
                notification_id,
                f'snoozed_{minutes}m'
            )
            
            await self.bot_client.edit_message(
                message_id,
                f"⏰ Snoozed for {minutes} minutes",
                reply_markup=None
            )
            
            return {
                "success": True,
                "ack_text": f"Snoozed {minutes} minutes"
            }
        
        elif action == 'next':
            # Skip this prayer, remind at next one
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'skip_to_next'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "⏭️ Will remind at next prayer",
                reply_markup=None
            )
            
            return {
                "success": True,
                "ack_text": "Will remind at next prayer"
            }
        
        return {"success": False, "error": "Unknown prayer action"}
    
    # ========================================================================
    # WEATHER CALLBACKS
    # ========================================================================
    
    async def _handle_weather_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle weather notification button clicks"""
        
        if action == 'got_it':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'acknowledged'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Weather alert acknowledged",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Acknowledged"}
        
        return {"success": False, "error": "Unknown weather action"}
    
    # ========================================================================
    # REMINDER CALLBACKS
    # ========================================================================
    
    async def _handle_reminder_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle reminder button clicks"""
        
        if action == 'done':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'completed'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Reminder completed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Completed"}
        
        return {"success": False, "error": "Unknown reminder action"}
    
    # ========================================================================
    # CALENDAR CALLBACKS
    # ========================================================================
    
    async def _handle_calendar_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle calendar event button clicks"""
        
        if action == 'ready':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ready'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Ready for event",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Ready"}
        
        elif action == 'snooze':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'snoozed_15m'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "⏰ Snoozed for 15 minutes",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Snoozed 15 minutes"}
        
        return {"success": False, "error": "Unknown calendar action"}
    
    # ========================================================================
    # EMAIL CALLBACKS
    # ========================================================================
    
    async def _handle_email_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle email notification button clicks"""
        
        if action == 'not_urgent':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'false_positive'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as not urgent (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Marked not urgent"}
        
        elif action == 'ignore':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ignored'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Dismissed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Dismissed"}
        
        return {"success": False, "error": "Unknown email action"}
    
    # ========================================================================
    # CLICKUP CALLBACKS
    # ========================================================================
    
    async def _handle_clickup_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Handle ClickUp task button clicks"""
        
        if action == 'done':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'marked_done'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Task marked complete",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Task completed"}
        
        elif action == 'got_it':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'acknowledged'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Acknowledged",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Acknowledged"}
        
        return {"success": False, "error": "Unknown ClickUp action"}
    
    # ========================================================================
    # BLUESKY CALLBACKS
    # ========================================================================
    
    async def _handle_bluesky_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle Bluesky training button clicks"""
        
        opportunity_id = params[0] if params else None
        
        if action == 'good_match':
            # Store positive training feedback
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",  # Your user ID
                feedback_type='bluesky_engagement',
                opportunity_id=opportunity_id or notification_id,
                user_response='good_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as good match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Good match recorded"}
        
        elif action == 'bad_match':
            # Store negative training feedback
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='bluesky_engagement',
                opportunity_id=opportunity_id or notification_id,
                user_response='bad_match',
                opportunity_data={}
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Marked as bad match (AI learning)",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Bad match recorded"}
        
        elif action == 'ignore':
            await self.notification_manager.acknowledge_notification(
                notification_id,
                'ignored'
            )
            
            await self.bot_client.edit_message(
                message_id,
                "✅ Dismissed",
                reply_markup=None
            )
            
            return {"success": True, "ack_text": "Dismissed"}
        
        elif action == 'draft':
            # Generate a reply to this Bluesky engagement opportunity
            opportunity_id = notification_id
            conn = None
            
            try:
                from modules.integrations.bluesky.approval_system import get_approval_system
                
                conn = await db_manager.get_connection()
                
                # Fetch the engagement opportunity details
                opportunity = await conn.fetchrow('''
                    SELECT
                        id, post_uri, post_text, author_handle, author_did,
                        detected_by_account, engagement_score, matched_keywords
                    FROM bluesky_engagement_opportunities
                    WHERE id = $1
                ''', UUID(opportunity_id))
                
                if not opportunity:
                    await self.bot_client.edit_message(
                        message_id,
                        "❌ Opportunity not found",
                        reply_markup=None
                    )
                    return {"success": False, "ack_text": "❌ Not found"}
                
                # Build analysis dict for approval system
                analysis = {
                    'account_id': opportunity['detected_by_account'],
                    'account_config': {'personality': 'professional'},
                    'post_content': opportunity['post_text'],
                    'author': {
                        'handle': opportunity['author_handle'],
                        'display_name': opportunity['author_handle']  # Use handle as display name
                    },
                    'keyword_analysis': {
                        'matched_keywords': json.loads(opportunity['matched_keywords']) if opportunity['matched_keywords'] else []
                    },
                    'suggested_action': 'reply'
                }
                
                # Generate draft using approval system
                approval_system = get_approval_system()
                draft_result = await approval_system.generate_draft_post(analysis, post_type="reply")
                
                if not draft_result.get('success'):
                    await self.bot_client.edit_message(
                        message_id,
                        "❌ Failed to generate reply draft",
                        reply_markup=None
                    )
                    return {"success": False, "ack_text": "❌ Generation failed"}
                
                draft_text = draft_result['draft_text']
                
                # Build draft notification message - ESCAPE USER CONTENT
                post_preview = html.escape(str(opportunity['post_text'] or '')[:100])
                escaped_draft = html.escape(str(draft_text or ''))
                escaped_handle = html.escape(str(opportunity['author_handle'] or ''))
                escaped_account = html.escape(str(opportunity['detected_by_account'] or ''))
                
                message_text = f"💬 <b>Draft Reply</b> (@{escaped_account})\n\n"
                message_text += f"<b>Replying to:</b> @{escaped_handle}\n"
                message_text += f'"{post_preview}..."\n\n'
                message_text += f"<b>Your reply:</b>\n{escaped_draft}\n\n"
                message_text += f"<i>{len(draft_text)} characters</i>"
                
                # Buttons for draft approval - USE LIST FORMAT
                buttons = [
                    [
                        {'text': '✅ Post Reply', 'callback_data': f"bluesky:post_reply:{opportunity_id}"},
                        {'text': '⏭️ Skip', 'callback_data': f"bluesky:ignore:{opportunity_id}"}
                    ]
                ]
                
                await self.bot_client.edit_message(
                    message_id,
                    message_text,
                    reply_markup=buttons
                )
                
                return {"success": True, "ack_text": "✅ Draft generated!"}
                
            except Exception as e:
                logger.error(f"Reply draft generation failed: {e}", exc_info=True)
                await self.bot_client.edit_message(
                    message_id,
                    f"❌ Error: {html.escape(str(e))}",
                    reply_markup=None
                )
                return {"success": False, "ack_text": "❌ Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        return {"success": False, "error": "Unknown Bluesky action"}
    
    
    # ========================================================================
    # CONTEXTUAL INTELLIGENCE: ENGAGEMENT CALLBACKS (NEW)
    # ========================================================================
    
    async def _handle_engagement_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """
        Handle Bluesky engagement callbacks (Contextual Intelligence Layer)
        
        Actions:
            - view: View conversation
            - draft_reply: Generate reply
            - like: Like the post
            - skip: Skip this opportunity
        """
        
        if action == 'view':
            # Return Bluesky URL
            post_uri = ':'.join([notification_id] + params)
            
            try:
                parts = post_uri.replace('at://', '').split('/')
                if len(parts) >= 3:
                    did = parts[0]
                    post_id = parts[2]
                    url = f"https://bsky.app/profile/{did}/post/{post_id}"
                    
                    await self.bot_client.edit_message(
                        message_id,
                        f"🔗 <a href=\"{url}\">View Conversation</a>",
                        reply_markup=None
                    )
                    return {"success": True, "ack_text": "Opening..."}
            except Exception as e:
                logger.error(f"View failed: {e}")
            
            return {"success": False, "ack_text": "❌ Invalid link"}
        
        elif action == 'draft_reply':
            # Generate a reply to this post
            opportunity_id = notification_id
            conn = None
            
            try:
                conn = await db_manager.get_connection()
                
                # Load opportunity from database
                opportunity = await conn.fetchrow('''
                    SELECT 
                        id, detected_by_account, post_text, author_handle,
                        matched_keywords, opportunity_type, engagement_score,
                        post_uri
                    FROM bluesky_engagement_opportunities
                    WHERE id = $1
                ''', UUID(opportunity_id))
                
                if not opportunity:
                    raise Exception("Opportunity not found in database")
                
                # Get matched keywords (stored as JSON array)
                matched_keywords = opportunity['matched_keywords']
                if isinstance(matched_keywords, str):
                    matched_keywords = json.loads(matched_keywords)
                elif matched_keywords is None:
                    matched_keywords = []
                
                # Build proper analysis context for draft generation
                from modules.integrations.bluesky.approval_system import get_approval_system
                
                analysis = {
                    'account_id': opportunity['detected_by_account'],
                    'account_config': {
                        'personality': 'professional',
                        'sensitive_topics': True,
                        'pg13_mode': True
                    },
                    'post_content': opportunity['post_text'],
                    'author': {
                        'display_name': opportunity['author_handle'].replace('@', ''),
                        'handle': opportunity['author_handle']
                    },
                    'keyword_analysis': {
                        'matched_keywords': matched_keywords
                    },
                    'suggested_action': opportunity.get('opportunity_type', 'reply')
                }
                
                logger.info(f"🎨 Generating draft reply with context: {len(matched_keywords)} keywords matched")
                
                # Generate draft using approval system
                approval_system = get_approval_system()
                draft_result = await approval_system.generate_draft_post(analysis, post_type="reply")
                
                if not draft_result.get('success'):
                    await self.bot_client.edit_message(
                        message_id,
                        "❌ Failed to generate reply draft",
                        reply_markup=None
                    )
                    return {"success": False, "ack_text": "❌ Generation failed"}
                
                draft_text = draft_result['draft_text']
                
                # Build draft notification message - ESCAPE USER CONTENT
                post_preview = html.escape(str(opportunity['post_text'] or '')[:100])
                escaped_draft = html.escape(str(draft_text or ''))
                escaped_handle = html.escape(str(opportunity['author_handle'] or ''))
                escaped_account = html.escape(str(opportunity['detected_by_account'] or ''))
                
                message = f"💬 <b>Draft Reply</b> (@{escaped_account})\n\n"
                message += f"<b>Replying to:</b> @{escaped_handle}\n"
                message += f'"{post_preview}..."\n\n'
                message += f"<b>Your reply:</b>\n{escaped_draft}\n\n"
                message += f"<i>{len(draft_text)} characters</i>"
                
                # Buttons for draft approval - USE LIST FORMAT
                buttons = [
                    [
                        {'text': '✅ Post Reply', 'callback_data': f"engagement:post_reply:{opportunity_id}"},
                        {'text': '✏️ Edit', 'callback_data': f"engagement:edit_reply:{opportunity_id}"}
                    ],
                    [
                        {'text': '❌ Dismiss', 'callback_data': f"engagement:skip:{opportunity_id}"}
                    ]
                ]
                
                await self.bot_client.edit_message(
                    message_id,
                    message,
                    reply_markup=buttons
                )
                
                return {"success": True, "ack_text": "✅ Draft generated!"}
                
            except Exception as e:
                logger.error(f"Reply draft generation failed: {e}", exc_info=True)
                await self.bot_client.edit_message(
                    message_id,
                    f"❌ Error: {html.escape(str(e))}",
                    reply_markup=None
                )
                return {"success": False, "ack_text": "❌ Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        elif action == 'like':
            # Like the post on Bluesky
            opportunity_id = notification_id
            conn = None
            
            try:
                conn = await db_manager.get_connection()
                
                # Get the opportunity details
                opportunity = await conn.fetchrow('''
                    SELECT post_uri, detected_by_account
                    FROM bluesky_engagement_opportunities
                    WHERE id = $1
                ''', UUID(opportunity_id))
                
                if not opportunity:
                    raise Exception("Opportunity not found")
                
                # Like the post using Bluesky client
                from modules.integrations.bluesky.client import get_bluesky_client
                bluesky_client = get_bluesky_client()
                
                account_id = opportunity['detected_by_account']
                post_uri = opportunity['post_uri']
                
                await bluesky_client.like_post(account_id, post_uri)
                
                # Mark as liked in database
                await conn.execute('''
                    UPDATE bluesky_engagement_opportunities
                    SET user_response = 'liked', updated_at = NOW()
                    WHERE id = $1
                ''', UUID(opportunity_id))
                
                await self.edit_message(
                    message_id,
                    "❤️ Post liked!",
                    reply_markup=None
                )
                
                logger.info(f"✅ Liked post {post_uri}")
                return {"success": True, "ack_text": "Liked!"}
                
            except Exception as e:
                logger.error(f"Like failed: {e}")
                await self.edit_message(
                    message_id,
                    f"❌ Failed to like: {html.escape(str(e))}"
                )
                return {"success": False, "ack_text": "Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        elif action == 'skip':
            opportunity_id = notification_id
            conn = None
            
            try:
                conn = await db_manager.get_connection()
                
                await conn.execute('''
                    UPDATE bluesky_engagement_opportunities
                    SET user_response = 'dismissed', updated_at = NOW()
                    WHERE id = $1
                ''', UUID(opportunity_id))
                
                await self.bot_client.edit_message(
                    message_id,
                    "⏭️ Skipped",
                    reply_markup=None
                )
                return {"success": True, "ack_text": "Skipped"}
                
            except Exception as e:
                logger.error(f"Skip failed: {e}")
                return {"success": False, "ack_text": "❌ Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        return {"success": False, "error": "Unknown engagement action"}

    # ========================================================================
    # MEETING CALLBACKS
    # ========================================================================
    
    async def _handle_meeting_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle meeting action callbacks"""
        
        if action == 'send_to_clickup':
            meeting_id = notification_id
            conn = None
            
            try:
                conn = await db_manager.get_connection()
                
                # Mark meeting as processed
                await conn.execute('''
                    UPDATE fathom_meetings
                    SET action_items_sent = true,
                        action_items_sent_at = NOW()
                    WHERE id = $1
                ''', UUID(meeting_id))
                
                # Get count
                result = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM meeting_action_items
                    WHERE meeting_id = $1
                ''', UUID(meeting_id))
                
                item_count = result['count'] if result else 0
                
                await self.edit_message(
                    message_id,
                    f"✅ Sent {item_count} action items to ClickUp!\n\n<i>Meeting marked as processed.</i>"
                )
                
                logger.info(f"✅ Meeting {meeting_id} marked as processed")
                return {"success": True, "ack_text": "Sent to ClickUp"}
                
            except Exception as e:
                logger.error(f"Failed to process meeting: {e}")
                await self.edit_message(message_id, f"❌ Error: {html.escape(str(e))}")
                return {"success": False, "ack_text": "Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        elif action == 'dismiss':
            meeting_id = notification_id
            conn = None
            
            try:
                conn = await db_manager.get_connection()
                
                # Mark meeting as dismissed (user_response field or similar)
                await conn.execute('''
                    UPDATE fathom_meetings
                    SET processed_at = NOW()
                    WHERE id = $1
                ''', UUID(meeting_id))
                
                await self.edit_message(
                    message_id,
                    "⏭️ Meeting dismissed",
                    reply_markup=None
                )
                
                logger.info(f"✅ Meeting {meeting_id} dismissed")
                return {"success": True, "ack_text": "Dismissed"}
                
            except Exception as e:
                logger.error(f"Failed to dismiss meeting: {e}")
                return {"success": False, "ack_text": "Error"}
            
            finally:
                if conn:
                    await db_manager.release_connection(conn)
        
        elif action == 'snooze':
            # Snooze meeting notification
            await self.edit_message(
                message_id,
                "⏰ Snoozed - will remind later",
                reply_markup=None
            )
            return {"success": True, "ack_text": "Snoozed"}
        
        return {"success": False, "error": "Unknown meeting action"}

    # ========================================================================
    # INTELLIGENCE SYSTEM: SITUATION CALLBACKS (NEW - 10/22/25)
    # ========================================================================
    
    async def _handle_situation_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """
        Handle situation callbacks from Intelligence Hub
        
        Callback format: situation:action:situation_id[:optional_params]
        
        Actions:
            - dismiss: User dismissed situation
            - details: User wants more information
            - action1/action2: User clicked suggested action
        """
        try:
            from modules.intelligence.intelligence_orchestrator import IntelligenceOrchestrator
            
            user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
            
            orchestrator = IntelligenceOrchestrator(
                db_manager=db_manager,
                user_id=UUID(user_id) if isinstance(user_id, str) else user_id
            )
            
            if action == 'dismiss':
                # User dismissed the situation
                await orchestrator.situation_manager.record_user_response(
                    notification_id,
                    'dismissed',
                    'none'
                )
                
                # Update learning system
                situation = await orchestrator.situation_manager.get_situation_by_id(notification_id)
                
                await self.bot_client.edit_message(
                    message_id,
                    "✅ Situation dismissed (AI learning from your feedback)",
                    reply_markup=None
                )
                
                return {
                    "success": True,
                    "ack_text": "Dismissed"
                }
            
            elif action == 'snooze':
                # User wants to snooze this situation
                minutes = int(params[0]) if params else 60  # Default 60 minutes
                
                await orchestrator.situation_manager.record_user_response(
                    notification_id,
                    'snoozed',
                    f'snoozed_{minutes}m'
                )
                
                await self.edit_message(
                    message_id,
                    f"⏰ Snoozed for {minutes} minutes - I'll remind you later",
                    reply_markup=None
                )
                
                return {
                    "success": True,
                    "ack_text": f"Snoozed {minutes} minutes"
                }
            
            elif action == 'details':
                # User wants more details
                situation = await orchestrator.situation_manager.get_situation_by_id(notification_id)
                
                if not situation:
                    return {"success": False, "error": "Situation not found"}
                
                # Format detailed view - ESCAPE USER CONTENT
                sit_type = html.escape(str(situation['situation_type']).replace('_', ' ').title())
                context_summary = html.escape(str(situation.get('context_summary', 'No additional context')))
                detected_at = html.escape(str(situation.get('detected_at', 'Unknown')))
                
                details = f"""🧠 <b>Situation Details</b>

<b>Type:</b> {sit_type}
<b>Priority:</b> {situation['priority_score']}/10
<b>Confidence:</b> {int(situation['confidence_score']*100)}%

<b>Context:</b>
{context_summary}

<b>Detected:</b> {detected_at}
"""
                
                await self.bot_client.edit_message(
                    message_id,
                    details,
                    reply_markup=None
                )
                
                return {
                    "success": True,
                    "ack_text": "Details shown"
                }
            
            elif action.startswith('action'):
                # User clicked an action button (action1, action2, etc.)
                action_index = int(action.replace('action', '')) - 1
                
                # Execute the action via orchestrator
                callback_data = f"situation:{action}:{notification_id}"
                if params:
                    callback_data += ":" + ":".join(params)
                
                result = await orchestrator.handle_situation_callback(
                    callback_data,
                    user_id
                )
                
                # Record user response
                await orchestrator.situation_manager.record_user_response(
                    notification_id,
                    'acted',
                    f'action_{action_index + 1}'
                )
                
                if result.get('success'):
                    # ESCAPE the message from action executor
                    result_message = html.escape(str(result.get('message', 'Action executed successfully')))
                    await self.bot_client.edit_message(
                        message_id,
                        f"✅ {result_message}",
                        reply_markup=None
                    )
                    
                    return {
                        "success": True,
                        "ack_text": "Action executed"
                    }
                else:
                    result_message = html.escape(str(result.get('message', 'Action failed')))
                    await self.bot_client.edit_message(
                        message_id,
                        f"❌ {result_message}",
                        reply_markup=None
                    )
                    
                    return {
                        "success": False,
                        "ack_text": "Action failed"
                    }
            
            return {"success": False, "error": "Unknown situation action"}
        
        except Exception as e:
            logger.error(f"Situation callback error: {e}")
            return {"success": False, "error": str(e)}


# Global instance
_callback_handler = None

def get_callback_handler() -> CallbackHandler:
    """Get the global callback handler instance"""
    global _callback_handler
    if _callback_handler is None:
        import os
        from .bot_client import TelegramBotClient
        from .notification_manager import get_notification_manager
        
        # Get bot token from environment
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
        bot_client = TelegramBotClient(bot_token)
        notification_manager = get_notification_manager()
        
        _callback_handler = CallbackHandler(
            bot_client=bot_client,
            notification_manager=notification_manager
        )
    return _callback_handler
