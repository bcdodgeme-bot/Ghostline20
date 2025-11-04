"""
Telegram Callback Handler - Button Click Processing
Processes inline keyboard button clicks and updates notification state
UPDATED: Added Contextual Intelligence Layer handlers
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from .bot_client import TelegramBotClient
from .database_manager import TelegramDatabaseManager
from .notification_manager import NotificationManager

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
            
            elif notification_type == 'trends':
                result = await self._handle_trends_callback(
                    action, notification_id, message_id, extra_params
                )
            
            # ====== NEW: Contextual Intelligence Layer handlers ======
            elif notification_type == 'content':
                result = await self._handle_content_callback(
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
                
            elif notification_type == 'situation':
                result = await self._handle_situation_callback(
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
    # BLUESKY TRAINING CALLBACKS
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
        
        return {"success": False, "error": "Unknown Bluesky action"}
    
    # ========================================================================
    # TRENDS TRAINING CALLBACKS
    # ========================================================================
    
    async def _handle_trends_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """Handle Trends training button clicks"""
        
        opportunity_id = params[0] if params else None
        
        if action == 'good_match':
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='trends_keyword',
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
            await self.db_manager.store_training_feedback(
                user_id="b7c60682-4815-4d9d-8ebe-66c6cd24eff9",
                feedback_type='trends_keyword',
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
        
        return {"success": False, "error": "Unknown Trends action"}
    
    # ========================================================================
    # CONTEXTUAL INTELLIGENCE: CONTENT CALLBACKS (NEW)
    # ========================================================================
    
    async def _handle_content_callback(
        self,
        action: str,
        notification_id: str,
        message_id: int,
        params: list
    ) -> Dict[str, Any]:
        """
        Handle content draft callbacks (Contextual Intelligence Layer)
        
        Actions:
            - draft_bluesky: Generate Bluesky post draft
            - post_now: Post approved content
            - edit: Request to edit draft
            - save: Save draft for later
            - dismiss: Reject draft
        """
        
        if action == 'draft_bluesky':
            # Generate Bluesky draft from trend opportunity
            opportunity_id = notification_id
            account_id = params[0] if params else 'bcdodge'
            
            try:
                # Import content generator
                import sys
                sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                from modules.content.content_generator import get_content_generator
                
                database_url = os.getenv('DATABASE_URL')
                generator = await get_content_generator(database_url)
                
                result = await generator.generate_bluesky_post(
                    opportunity_id=UUID(opportunity_id),
                    account_id=account_id
                )
                
                if not result['success']:
                    await self.bot_client.edit_message(
                        message_id,
                        f"❌ Failed to generate draft: {result.get('error', 'Unknown error')}",
                        reply_markup=None
                    )
                    return {"success": False, "ack_text": "❌ Generation failed"}
                
                # Build draft notification message
                message = f"📝 *Draft Bluesky Post* (@{account_id})\n\n"
                message += f"{result['preview']}\n\n"
                message += f"_Confidence: {int(result['recommendation_score'] * 100)}%_"
                
                # New buttons for draft approval
                buttons = {
                    'inline_keyboard': [
                        [
                            {'text': '✅ Post Now', 'callback_data': f"content:post_now:{result['queue_id']}:{account_id}"},
                            {'text': '✏️ Edit', 'callback_data': f"content:edit:{result['queue_id']}"}
                        ],
                        [
                            {'text': '💾 Save', 'callback_data': f"content:save:{result['queue_id']}"},
                            {'text': '❌ Dismiss', 'callback_data': f"content:dismiss:{result['queue_id']}"}
                        ]
                    ]
                }
                
                await self.bot_client.edit_message(
                    message_id,
                    message,
                    reply_markup=buttons
                )
                
                return {"success": True, "ack_text": "✅ Draft generated!"}
            
            except Exception as e:
                logger.error(f"Draft generation failed: {e}")
                await self.bot_client.edit_message(
                    message_id,
                    f"❌ Generation error: {str(e)}",
                    reply_markup=None
                )
                return {"success": False, "ack_text": "❌ Error"}
        
        elif action == 'post_now':
            # Post content to Bluesky
            queue_id = notification_id
            account_id = params[0] if params else 'bcdodge'
            
            try:
                import asyncpg
                from modules.integrations.bluesky.multi_account_client import get_bluesky_multi_client
                
                database_url = os.getenv('DATABASE_URL')
                conn = await asyncpg.connect(database_url)
                
                try:
                    # Get content from queue
                    content = await conn.fetchrow('''
                        SELECT 
                            id, content_type, business_area,
                            generated_content, trend_opportunity_id
                        FROM content_recommendation_queue
                        WHERE id = $1
                    ''', UUID(queue_id))
                    
                    if not content:
                        await self.bot_client.edit_message(
                            message_id,
                            "❌ Content not found",
                            reply_markup=None
                        )
                        return {"success": False, "ack_text": "❌ Not found"}
                    
                    generated = json.loads(content['generated_content'])
                    post_text = generated.get('text', '')
                    
                    # Post to Bluesky
                    bluesky_client = get_bluesky_multi_client()
                    post_result = await bluesky_client.create_post(
                        account_id=account_id,
                        text=post_text
                    )
                    
                    if not post_result.get('success'):
                        await self.bot_client.edit_message(
                            message_id,
                            "❌ Bluesky posting failed",
                            reply_markup=None
                        )
                        return {"success": False, "ack_text": "❌ Post failed"}
                    
                    post_uri = post_result.get('uri')
                    
                    # Update queue
                    await conn.execute('''
                        UPDATE content_recommendation_queue
                        SET user_feedback = 'posted', posted_at = NOW(), updated_at = NOW()
                        WHERE id = $1
                    ''', UUID(queue_id))
                    
                    # Track in analytics
                    await conn.execute('''
                        INSERT INTO bluesky_post_analytics (
                            post_uri, account_id, business_area, post_text,
                            source_type, source_id, posted_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ''', post_uri, account_id, content['business_area'],
                        post_text, 'trend_opportunity', content['trend_opportunity_id'])
                    
                    # Record learning
                    await conn.execute('''
                        INSERT INTO contextual_learnings (
                            learning_type, pattern_description, evidence_type,
                            confidence_score, situation_context, can_act_on
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                    ''', 'content_approval',
                        f'User posted content about: {generated.get("keyword")}',
                        'explicit_feedback', 0.9,
                        json.dumps({'keyword': generated.get('keyword'), 'action': 'posted'}),
                        True)
                    
                    await self.bot_client.edit_message(
                        message_id,
                        f"✅ *Posted to @{account_id}!*\n\n{post_text}\n\n[View Post]({post_result.get('url', '#')})",
                        reply_markup=None
                    )
                    
                    return {"success": True, "ack_text": "✅ Posted!"}
                
                finally:
                    await conn.close()
            
            except Exception as e:
                logger.error(f"Post now failed: {e}")
                await self.bot_client.edit_message(
                    message_id,
                    f"❌ Posting error: {str(e)}",
                    reply_markup=None
                )
                return {"success": False, "ack_text": "❌ Error"}
        
        elif action == 'edit':
            queue_id = notification_id
            await self.bot_client.edit_message(
                message_id,
                f"✏️ To edit this draft, use:\n\n`/edit {queue_id}`\n\nI'll help you refine the content!",
                reply_markup=None
            )
            return {"success": True, "ack_text": "Edit in chat"}
        
        elif action == 'save':
            queue_id = notification_id
            try:
                import asyncpg
                database_url = os.getenv('DATABASE_URL')
                conn = await asyncpg.connect(database_url)
                try:
                    await conn.execute('''
                        UPDATE content_recommendation_queue
                        SET user_feedback = 'saved_for_later', updated_at = NOW()
                        WHERE id = $1
                    ''', UUID(queue_id))
                    
                    await self.bot_client.edit_message(
                        message_id,
                        "💾 *Draft Saved*\n\nI'll remind you about this later!",
                        reply_markup=None
                    )
                    return {"success": True, "ack_text": "💾 Saved"}
                finally:
                    await conn.close()
            except Exception as e:
                logger.error(f"Save failed: {e}")
                return {"success": False, "ack_text": "❌ Error"}
        
        elif action == 'dismiss':
            queue_id = notification_id
            try:
                import asyncpg
                database_url = os.getenv('DATABASE_URL')
                conn = await asyncpg.connect(database_url)
                try:
                    # Mark as dismissed
                    await conn.execute('''
                        UPDATE content_recommendation_queue
                        SET user_feedback = 'dismissed', updated_at = NOW()
                        WHERE id = $1
                    ''', UUID(queue_id))
                    
                    # Record negative learning
                    content = await conn.fetchrow('''
                        SELECT generated_content FROM content_recommendation_queue WHERE id = $1
                    ''', UUID(queue_id))
                    
                    if content:
                        generated = json.loads(content['generated_content'])
                        await conn.execute('''
                            INSERT INTO contextual_learnings (
                                learning_type, pattern_description, evidence_type,
                                confidence_score, situation_context, can_act_on
                            ) VALUES ($1, $2, $3, $4, $5, $6)
                        ''', 'content_rejection',
                            f'User dismissed content about: {generated.get("keyword")}',
                            'explicit_feedback', 0.7,
                            json.dumps({'keyword': generated.get('keyword'), 'action': 'dismissed'}),
                            False)
                    
                    await self.bot_client.edit_message(
                        message_id,
                        "✅ Dismissed (AI learning from your feedback)",
                        reply_markup=None
                    )
                    return {"success": True, "ack_text": "✅ Dismissed"}
                finally:
                    await conn.close()
            except Exception as e:
                logger.error(f"Dismiss failed: {e}")
                return {"success": False, "ack_text": "❌ Error"}
        
        return {"success": False, "error": "Unknown content action"}
    
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
                        f"🔗 [View Conversation]({url})",
                        reply_markup=None
                    )
                    return {"success": True, "ack_text": "Opening..."}
            except Exception as e:
                logger.error(f"View failed: {e}")
            
            return {"success": False, "ack_text": "❌ Invalid link"}
        
        elif action == 'draft_reply':
            await self.bot_client.edit_message(
                message_id,
                "🚧 Reply drafting coming soon!",
                reply_markup=None
            )
            return {"success": True, "ack_text": "Coming soon"}
        
        elif action == 'like':
            await self.bot_client.edit_message(
                message_id,
                "❤️ Like feature coming soon!",
                reply_markup=None
            )
            return {"success": True, "ack_text": "Coming soon"}
        
        elif action == 'skip':
            opportunity_id = notification_id
            try:
                import asyncpg
                database_url = os.getenv('DATABASE_URL')
                conn = await asyncpg.connect(database_url)
                try:
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
                finally:
                    await conn.close()
            except Exception as e:
                logger.error(f"Skip failed: {e}")
                return {"success": False, "ack_text": "❌ Error"}
        
        return {"success": False, "error": "Unknown engagement action"}

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
            from modules.core.database import db_manager
            from uuid import UUID
            
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
                if situation:
                    await orchestrator.situation_manager.update_learning(
                        pattern_type=situation['situation_type'],
                        user_response='dismissed',
                        confidence_adjustment=-0.1
                    )
                
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
                
                # Format detailed view
                details = f"""🧠 **Situation Details**

**Type:** {situation['situation_type'].replace('_', ' ').title()}
**Priority:** {situation['priority_score']}/10
**Confidence:** {int(situation['confidence_score']*100)}%

**Context:**
{situation.get('context_summary', 'No additional context')}

**Detected:** {situation['detected_at'].strftime('%b %d at %I:%M %p')}
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
                
                # Update learning (positive reinforcement)
                situation = await orchestrator.situation_manager.get_situation_by_id(notification_id)
                if situation:
                    await orchestrator.situation_manager.update_learning(
                        pattern_type=situation['situation_type'],
                        user_response='acted',
                        confidence_adjustment=0.05
                    )
                
                if result.get('success'):
                    await self.bot_client.edit_message(
                        message_id,
                        f"✅ {result.get('message', 'Action executed successfully')}",
                        reply_markup=None
                    )
                    
                    return {
                        "success": True,
                        "ack_text": "Action executed"
                    }
                else:
                    await self.bot_client.edit_message(
                        message_id,
                        f"❌ {result.get('message', 'Action failed')}",
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
