# modules/integrations/telegram/notification_types/bluesky_notifications.py
"""
Bluesky Notification Handler
Sends PROACTIVE notifications for Bluesky engagement opportunities with AI-drafted replies

UPDATED: 2025-12-19 - Now uses proactive_engine for AI draft generation
Instead of just notifying "engagement opportunity found", we now:
1. Detect opportunity
2. Generate AI draft reply BEFORE notification (via proactive_engine)
3. Send rich notification with draft + one-tap action buttons
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from ....core.database import db_manager

logger = logging.getLogger(__name__)


class BlueskyNotificationHandler:
    """
    Handles Bluesky engagement notifications with AI-powered draft replies
    
    Flow:
    1. Check for pending opportunities in proactive queue
    2. For opportunities without notifications, send rich notification
    3. User taps once → reply posted
    """
    
    def __init__(self, notification_manager):
        self.notification_manager = notification_manager
        self.db = db_manager
        self._db_manager = None
        self._proactive_engine = None
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

    @property
    def db_manager(self):
        """Lazy-load TelegramDatabaseManager"""
        if self._db_manager is None:
            from ..database_manager import TelegramDatabaseManager
            self._db_manager = TelegramDatabaseManager()
        return self._db_manager
    
    @property
    def proactive_engine(self):
        """Lazy-load ProactiveBlueskyEngine"""
        if self._proactive_engine is None:
            try:
                from ...bluesky.proactive_engine import get_proactive_engine
                self._proactive_engine = get_proactive_engine()
            except Exception as e:
                logger.warning(f"Could not load proactive engine: {e}")
        return self._proactive_engine
    
    async def check_and_notify(self) -> bool:
        """
        Check for Bluesky engagement opportunities that need notifications.
        
        The proactive_engine already generates drafts and stores them.
        This method checks for any that might not have had notifications sent.
        
        Returns:
            True if any notifications were sent
        """
        try:
            # First, check proactive queue for items without notifications
            pending_proactive = await self._get_pending_proactive()
            
            if pending_proactive:
                logger.info(f"Found {len(pending_proactive)} proactive items needing notifications")
                for item in pending_proactive:
                    await self._send_proactive_notification(item)
                return True
            
            # Fallback: Check old engagement_opportunities table
            # and process them through proactive engine
            legacy_opportunities = await self._get_legacy_opportunities()
            
            if not legacy_opportunities:
                logger.debug("No Bluesky opportunities to process")
                return False
            
            logger.info(f"Processing {len(legacy_opportunities)} legacy opportunities through proactive engine")
            
            processed_count = 0
            for opp in legacy_opportunities:
                try:
                    success = await self._process_legacy_opportunity(opp)
                    if success:
                        processed_count += 1
                except Exception as e:
                    logger.error(f"Failed to process opportunity {opp.get('id')}: {e}")
                    continue
            
            return processed_count > 0
            
        except Exception as e:
            logger.error(f"Error checking Bluesky notifications: {e}", exc_info=True)
            return False
    
    async def _get_pending_proactive(self) -> List[Dict[str, Any]]:
        """Get proactive queue items that haven't had notifications sent"""
        query = """
        SELECT 
            id, post_uri, bluesky_url, author_handle, author_display_name,
            original_text, detected_by_account, matched_keywords,
            engagement_score, draft_text, personality_used,
            status, priority, expires_at, detected_at
        FROM bluesky_proactive_queue
        WHERE status = 'pending'
          AND telegram_message_id IS NULL
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY engagement_score DESC
        LIMIT 10
        """
        
        try:
            results = await self.db.fetch_all(query)
            return [dict(r) for r in results] if results else []
        except Exception as e:
            logger.error(f"Failed to get pending proactive: {e}")
            return []
    
    async def _get_legacy_opportunities(self) -> List[Dict[str, Any]]:
        """Get opportunities from old table that haven't been processed"""
        query = """
        SELECT 
            id, detected_by_account, author_handle, post_text,
            matched_keywords, engagement_score, opportunity_type,
            post_context, post_uri, detected_at, expires_at
        FROM bluesky_engagement_opportunities
        WHERE user_response IS NULL
          AND already_engaged = false
          AND (expires_at IS NULL OR expires_at > NOW())
          AND engagement_score >= 50
          AND NOT EXISTS (
              SELECT 1 FROM bluesky_proactive_queue bpq 
              WHERE bpq.post_uri = bluesky_engagement_opportunities.post_uri
          )
        ORDER BY engagement_score DESC
        LIMIT 10
        """
        
        try:
            results = await self.db.fetch_all(query)
            return [dict(r) for r in results] if results else []
        except Exception as e:
            logger.error(f"Failed to get legacy opportunities: {e}")
            return []
    
    async def _process_legacy_opportunity(self, opp: Dict[str, Any]) -> bool:
        """
        Process a legacy opportunity through the proactive engine.
        
        Reconstructs the post data format expected by proactive_engine.
        """
        try:
            if not self.proactive_engine:
                logger.warning("Proactive engine not available, using fallback notification")
                await self._send_fallback_notification(opp)
                return True
            
            # Reconstruct post data for proactive engine
            # The engine expects raw Bluesky API format
            post_data = {
                'uri': opp.get('post_uri', ''),
                'cid': '',  # Not available from legacy
                'author': {
                    'handle': opp.get('author_handle', 'unknown'),
                    'displayName': opp.get('author_handle', 'Unknown'),
                    'did': '',
                },
                'record': {
                    'text': opp.get('post_text', ''),
                    'createdAt': opp.get('detected_at', datetime.now(timezone.utc)).isoformat() if isinstance(opp.get('detected_at'), datetime) else opp.get('detected_at', ''),
                },
                'indexedAt': opp.get('detected_at', ''),
            }
            
            # Get matched keywords
            matched_keywords = opp.get('matched_keywords', [])
            if isinstance(matched_keywords, str):
                import json
                try:
                    matched_keywords = json.loads(matched_keywords)
                except:
                    matched_keywords = []
            
            # Process through proactive engine
            queue_id = await self.proactive_engine.process_opportunity(
                post=post_data,
                account_id=opp.get('detected_by_account', 'personal'),
                matched_keywords=matched_keywords,
                engagement_score=float(opp.get('engagement_score', 50)),
                opportunity_type=opp.get('opportunity_type', 'reply')
            )
            
            if queue_id:
                # Mark legacy opportunity as processed
                await self._mark_legacy_processed(opp['id'])
                logger.info(f"✅ Processed legacy opportunity: {queue_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to process legacy opportunity: {e}")
            return False
    
    async def _mark_legacy_processed(self, opp_id) -> None:
        """Mark legacy opportunity as engaged"""
        try:
            query = """
            UPDATE bluesky_engagement_opportunities
            SET already_engaged = true,
                user_response = 'processed_via_proactive'
            WHERE id = $1
            """
            await self.db.execute(query, opp_id)
        except Exception as e:
            logger.error(f"Failed to mark legacy processed: {e}")
    
    async def _send_proactive_notification(self, item: Dict[str, Any]) -> None:
        """
        Send notification for a proactive queue item.
        
        This is only called if the proactive engine stored an item
        but didn't send the notification (edge case).
        """
        try:
            from ...telegram.bot_client import get_bot_client
            
            # Format account display name
            account = item.get('detected_by_account', 'personal').replace('_', ' ').title()
            author = item.get('author_handle', 'unknown')
            score = int(item.get('engagement_score', 0))
            draft = item.get('draft_text', '')
            original = item.get('original_text', '')[:200]
            
            # Build Bluesky URL
            bluesky_url = item.get('bluesky_url', '')
            
            # Build message
            message = f"🦋 *Bluesky • {account}*\n\n"
            message += f"*@{author}* posted:\n"
            message += f"_{original}_\n\n"
            message += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            message += f"📝 *Your Draft Reply:*\n"
            message += f"`{draft}`\n\n"
            message += f"Score: {score}/100"
            
            if item.get('expires_at'):
                expires = item['expires_at']
                if isinstance(expires, datetime):
                    message += f"\n⏰ Expires: {expires.strftime('%I:%M %p %m/%d')}"
            
            # Build action buttons
            queue_id = str(item['id'])
            buttons = [
                [
                    {"text": "✅ Post This", "callback_data": f"bsky:post:{queue_id}"},
                    {"text": "✏️ Edit", "callback_data": f"bsky:edit:{queue_id}"}
                ],
                [
                    {"text": "❌ Skip", "callback_data": f"bsky:skip:{queue_id}"}
                ]
            ]
            
            # Add view post button if URL available
            if bluesky_url:
                buttons[1].insert(0, {"text": "👀 View Post", "url": bluesky_url})
            
            # Send via bot client directly to update telegram_message_id
            bot_client = get_bot_client()
            
            # Get chat ID
            chat_id = await self._get_telegram_chat_id()
            if not chat_id:
                logger.warning("No Telegram chat ID configured")
                return
            
            result = await bot_client.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown',
                buttons=buttons
            )
            
            # Update queue item with message ID
            if result.get('success'):
                await self._update_telegram_message_id(
                    queue_id=queue_id,
                    message_id=result.get('message_id'),
                    chat_id=chat_id
                )
                logger.info(f"✅ Sent proactive notification for {queue_id}")
            
        except Exception as e:
            logger.error(f"Failed to send proactive notification: {e}")
    
    async def _send_fallback_notification(self, opp: Dict[str, Any]) -> None:
        """
        Fallback notification when proactive engine isn't available.
        Still better than the old style - prompts user to engage.
        """
        account = opp.get('detected_by_account', 'personal').replace('_', ' ').title()
        author = opp.get('author_handle', 'unknown')
        score = int(opp.get('engagement_score', 0))
        post_text = opp.get('post_text', '')[:200]
        
        # Build Bluesky URL from post_uri
        post_uri = opp.get('post_uri', '')
        bluesky_url = None
        if post_uri and post_uri.startswith('at://'):
            try:
                parts = post_uri.replace('at://', '').split('/')
                if len(parts) >= 3:
                    did = parts[0]
                    post_id = parts[2]
                    bluesky_url = f"https://bsky.app/profile/{did}/post/{post_id}"
            except:
                pass
        
        message = f"🦋 *Bluesky Engagement Opportunity*\n\n"
        message += f"*Account:* {account}\n"
        message += f"*Author:* @{author}\n"
        message += f"*Score:* {score}/100\n\n"
        message += f"*Post:*\n_{post_text}_\n\n"
        message += "⚠️ _AI draft unavailable - open in chat to reply_"
        
        buttons = []
        if bluesky_url:
            buttons.append([{"text": "👀 View Post", "url": bluesky_url}])
        buttons.append([{"text": "💬 Open in Chat", "callback_data": f"bluesky:chat:{opp.get('id')}"}])
        
        await self.notification_manager.send_notification(
            user_id=self.user_id,
            notification_type='bluesky',
            notification_subtype='engagement_opportunity',
            message_text=message,
            buttons=buttons,
            message_data={
                'opportunity_id': str(opp['id']),
                'post_uri': post_uri,
                'account': opp.get('detected_by_account'),
                'author': author,
                'score': score
            }
        )
    
    async def _get_telegram_chat_id(self) -> Optional[int]:
        """Get Telegram chat ID for notifications"""
        try:
            query = """
            SELECT telegram_chat_id FROM telegram_preferences
            WHERE user_id = $1
            """
            result = await self.db.fetch_one(query, self.user_id)
            return result['telegram_chat_id'] if result else None
        except:
            import os
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            return int(chat_id) if chat_id else None
    
    async def _update_telegram_message_id(
        self,
        queue_id: str,
        message_id: int,
        chat_id: int
    ) -> None:
        """Update proactive queue with Telegram message ID"""
        try:
            query = """
            UPDATE bluesky_proactive_queue
            SET telegram_message_id = $2,
                telegram_chat_id = $3,
                notification_sent_at = NOW()
            WHERE id = $1
            """
            await self.db.execute(query, queue_id, message_id, chat_id)
        except Exception as e:
            logger.error(f"Failed to update telegram message id: {e}")
    
    async def send_daily_summary(self) -> bool:
        """Send daily Bluesky activity summary"""
        try:
            # Query both tables for complete picture
            query = """
            SELECT 
                (SELECT COUNT(*) FROM bluesky_proactive_queue 
                 WHERE DATE(detected_at) = CURRENT_DATE AND status = 'posted') as posted_count,
                (SELECT COUNT(*) FROM bluesky_proactive_queue 
                 WHERE DATE(detected_at) = CURRENT_DATE AND status = 'skipped') as skipped_count,
                (SELECT COUNT(*) FROM bluesky_proactive_queue 
                 WHERE DATE(detected_at) = CURRENT_DATE AND status = 'pending') as pending_count,
                (SELECT COUNT(*) FROM bluesky_proactive_queue 
                 WHERE DATE(detected_at) = CURRENT_DATE) as total_today
            """
            
            result = await self.db.fetch_one(query)
            
            if not result:
                return False
            
            posted = result['posted_count'] or 0
            skipped = result['skipped_count'] or 0
            pending = result['pending_count'] or 0
            total = result['total_today'] or 0
            
            message = f"🦋 *Bluesky Daily Summary*\n\n"
            message += f"*Opportunities Today:* {total}\n"
            
            if posted > 0:
                message += f"*Posted:* {posted} ✅\n"
            
            if skipped > 0:
                message += f"*Skipped:* {skipped} ⏭️\n"
            
            if pending > 0:
                message += f"*Pending:* {pending} ⏳\n"
                message += f"\n_You have {pending} opportunit{'ies' if pending != 1 else 'y'} ready with AI drafts._"
            elif total == 0:
                message += "\nNo opportunities detected today."
            else:
                message += "\n✅ All caught up!"
            
            await self.notification_manager.send_notification(
                user_id=self.user_id,
                notification_type='bluesky',
                notification_subtype='daily_summary',
                message_text=message,
                message_data={'summary_type': 'daily'}
            )
            
            logger.info("✅ Sent Bluesky daily summary")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Bluesky daily summary: {e}")
            return False
