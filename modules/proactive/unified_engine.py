# modules/proactive/unified_engine.py
"""
Unified Proactive Engine
Handles AI-generated drafts for ALL notification types

This is THE core engine that gives everything the "Bluesky Proactive Treatment":
- Email → AI drafts reply BEFORE you see notification
- Meeting → Full summary + action items ready to paste/create tasks
- Trends → Blog outline + Bluesky post with RSS context
- Calendar → Meeting prep notes generated
- ClickUp → Task summary with quick actions

FLOW FOR ALL TYPES:
1. DETECT opportunity (email arrives, meeting ends, trend detected)
2. GATHER CONTEXT (RSS articles, previous conversations, etc.)
3. GENERATE DRAFT (AI creates content immediately)
4. STORE in unified_proactive_queue
5. SEND rich notification with draft + action buttons
6. ONE-TAP execute (user taps, action happens)

Created: 2025-12-19
"""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, date
from dataclasses import dataclass
from enum import Enum

from modules.core.database import db_manager
from modules.ai.openrouter_client import get_openrouter_client

logger = logging.getLogger(__name__)


def json_serialize(obj: Any) -> str:
    """JSON serialize with datetime handling"""
    def default_handler(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
    
    return json.dumps(obj, default=default_handler)


class SourceType(str, Enum):
    EMAIL = "email"
    MEETING = "meeting"
    TREND = "trend"
    CALENDAR = "calendar"
    CLICKUP = "clickup"
    BLUESKY = "bluesky"
    RSS = "rss"


class ContentType(str, Enum):
    REPLY = "reply"
    SUMMARY = "summary"
    BLOG_OUTLINE = "blog_outline"
    BLUESKY_POST = "bluesky_post"
    ACTION_ITEMS = "action_items"
    MEETING_PREP = "meeting_prep"
    TASK_SUMMARY = "task_summary"
    TREND_ANALYSIS = "trend_analysis"


@dataclass
class ProactiveItem:
    """Container for a proactive queue item"""
    source_type: SourceType
    source_id: str
    source_title: str
    source_preview: str
    content_type: ContentType
    draft_text: str
    draft_title: Optional[str] = None
    draft_secondary: Optional[str] = None
    draft_structured: Optional[Dict] = None
    source_url: Optional[str] = None
    source_metadata: Optional[Dict] = None
    rss_context: Optional[List[Dict]] = None
    trend_context: Optional[Dict] = None
    business_context: Optional[str] = None
    priority: str = "medium"
    personality_used: Optional[str] = None
    model_used: Optional[str] = None


# Singleton instance
_unified_engine: Optional['UnifiedProactiveEngine'] = None


def get_unified_engine() -> 'UnifiedProactiveEngine':
    """Get singleton UnifiedProactiveEngine instance"""
    global _unified_engine
    if _unified_engine is None:
        _unified_engine = UnifiedProactiveEngine()
    return _unified_engine


class UnifiedProactiveEngine:
    """
    The unified engine for all proactive AI content generation.
    
    This replaces scattered notification logic with a single, consistent flow.
    """
    
    def __init__(self):
        self.user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        self.default_model = None  # Auto-select from OpenRouter preferred models
        
        # Personality mapping for different contexts
        self.personalities = {
            'professional': """You write in a professional, warm tone. Clear and concise.
                             You're helpful without being overly formal.""",
            'syntaxprime': """You're a helpful AI assistant with a touch of wit.
                            You're knowledgeable about tech and marketing.
                            Keep responses conversational but substantive.""",
            'compassionate': """You write with empathy and warmth. You understand
                              the importance of community and helping others.
                              Your tone is caring and supportive.""",
        }
        
        logger.info("✅ Unified Proactive Engine initialized")
    
    # =========================================================================
    # MAIN PROCESSING METHODS
    # =========================================================================
    
    async def process_email(
        self,
        email_data: Dict[str, Any],
        generate_reply: bool = True
    ) -> Optional[str]:
        """
        Process an important email and generate a draft reply.
        
        Args:
            email_data: Email information (subject, sender, body, etc.)
            generate_reply: Whether to generate an AI reply draft
            
        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            logger.info(f"📧 Processing email: {email_data.get('subject', 'No subject')}")
            
            # Check if already processed
            if await self._is_already_processed('email', email_data.get('message_id')):
                logger.info("   Already processed, skipping")
                return None
            
            # Check ignore list
            if await self._is_email_ignored(email_data):
                logger.info("   Email is ignored, skipping")
                return None
            
            # Generate AI draft reply
            draft_text = ""
            if generate_reply:
                draft_text = await self._generate_email_reply(email_data)
            
            # Create proactive item
            item = ProactiveItem(
                source_type=SourceType.EMAIL,
                source_id=email_data.get('message_id'),
                source_title=email_data.get('subject', 'No subject'),
                source_preview=email_data.get('snippet', '')[:200],
                source_url=self._build_gmail_url(email_data.get('message_id')),
                source_metadata={
                    'sender_email': email_data.get('sender_email'),
                    'sender_name': email_data.get('sender_name'),
                    'received_at': email_data.get('received_at'),
                    'priority': email_data.get('priority_level', 'normal'),
                    'requires_response': email_data.get('requires_response', False),
                    'thread_id': email_data.get('thread_id'),
                },
                content_type=ContentType.REPLY,
                draft_text=draft_text,
                priority=self._map_email_priority(email_data.get('priority_level')),
                personality_used='professional',
                model_used=self.default_model,
            )
            
            # Store and notify
            queue_id = await self._store_and_notify(item)
            
            logger.info(f"✅ Email processed: {queue_id}")
            return queue_id
            
        except Exception as e:
            logger.error(f"❌ Failed to process email: {e}", exc_info=True)
            return None
    
    async def process_meeting(
        self,
        meeting_data: Dict[str, Any],
        summary_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Process a completed meeting with full summary and action items.
        
        Args:
            meeting_data: Meeting details (title, date, attendees, etc.)
            summary_data: AI-generated summary (summary, key_points, action_items, etc.)
            
        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            recording_id = str(meeting_data.get('recording_id', ''))
            title = meeting_data.get('details', {}).get('title', 'Untitled Meeting')
            
            logger.info(f"🎙️ Processing meeting: {title}")
            
            # Check if already processed
            if await self._is_already_processed('meeting', recording_id):
                logger.info("   Already processed, skipping")
                return None
            
            # Build the FULL summary text (NO TRUNCATION!)
            full_summary = self._build_full_meeting_summary(meeting_data, summary_data)
            
            # Extract structured data
            structured_data = {
                'key_points': summary_data.get('key_points', []),
                'action_items': summary_data.get('action_items', []),
                'decisions': summary_data.get('decisions_made', []),
                'topics': summary_data.get('topics', []),
                'sentiment': summary_data.get('sentiment', 'neutral'),
                'effectiveness_score': summary_data.get('effectiveness_score', 5),
                'recommendations': summary_data.get('recommendations', []),
            }
            
            # Create proactive item
            item = ProactiveItem(
                source_type=SourceType.MEETING,
                source_id=recording_id,
                source_title=title,
                source_preview=summary_data.get('summary', '')[:300],
                source_url=meeting_data.get('details', {}).get('share_url'),
                source_metadata={
                    'start_time': meeting_data.get('details', {}).get('start_time'),
                    'duration_minutes': meeting_data.get('details', {}).get('duration', 0) // 60,
                    'attendees': [
                        a.get('name', 'Unknown')
                        for a in meeting_data.get('details', {}).get('attendees', [])
                    ],
                },
                content_type=ContentType.SUMMARY,
                draft_text=full_summary,
                draft_title=title,
                draft_structured=structured_data,
                priority=self._calculate_meeting_priority(summary_data),
                personality_used='professional',
                model_used=self.default_model,
            )
            
            # Store and notify
            queue_id = await self._store_and_notify(item)
            
            # Store action items separately for tracking
            await self._store_meeting_action_items(
                recording_id,
                queue_id,
                summary_data.get('action_items', [])
            )
            
            logger.info(f"✅ Meeting processed: {queue_id}")
            return queue_id
            
        except Exception as e:
            logger.error(f"❌ Failed to process meeting: {e}", exc_info=True)
            return None
    
    async def process_trend(
        self,
        trend_data: Dict[str, Any],
        include_rss_context: bool = True
    ) -> Optional[str]:
        """
        Process a trending topic and generate blog outline + Bluesky post.
        
        Args:
            trend_data: Trend information (keyword, score, business_area, etc.)
            include_rss_context: Whether to fetch related RSS articles
            
        Returns:
            Queue ID if successful, None otherwise
        """
        try:
            keyword = trend_data.get('keyword', '')
            business_area = trend_data.get('business_area', '')
            
            logger.info(f"📊 Processing trend: {keyword} ({business_area})")
            
            # Check if already processed
            trend_id = str(trend_data.get('id', ''))
            if await self._is_already_processed('trend', trend_id):
                logger.info("   Already processed, skipping")
                return None
            
            # Get RSS context
            rss_context = []
            if include_rss_context:
                rss_context = await self._get_rss_context(keyword, business_area)
            
            # Generate blog outline WITH RSS context
            blog_outline = await self._generate_blog_outline(
                keyword,
                business_area,
                trend_data,
                rss_context
            )
            
            # Generate Bluesky post
            bluesky_post = await self._generate_trend_bluesky_post(
                keyword,
                business_area,
                trend_data,
                rss_context
            )
            
            # Create proactive item
            item = ProactiveItem(
                source_type=SourceType.TREND,
                source_id=trend_id,
                source_title=f"Trending: {keyword}",
                source_preview=f"Score: {trend_data.get('trend_score_at_alert', 0)}/100 | {trend_data.get('urgency_level', 'medium').upper()}",
                source_metadata={
                    'trend_score': trend_data.get('trend_score_at_alert', 0),
                    'momentum': trend_data.get('trend_momentum', 'STABLE'),
                    'urgency': trend_data.get('urgency_level', 'medium'),
                    'opportunity_type': trend_data.get('opportunity_type', ''),
                },
                content_type=ContentType.BLOG_OUTLINE,
                draft_text=blog_outline,
                draft_title=f"Blog: {keyword}",
                draft_secondary=bluesky_post,  # Bluesky post as secondary content
                rss_context=rss_context,
                trend_context={
                    'keyword': keyword,
                    'score': trend_data.get('trend_score_at_alert', 0),
                    'momentum': trend_data.get('trend_momentum', 'STABLE'),
                },
                business_context=business_area,
                priority=trend_data.get('urgency_level', 'medium'),
                personality_used='syntaxprime',
                model_used=self.default_model,
            )
            
            # Store and notify
            queue_id = await self._store_and_notify(item)
            
            logger.info(f"✅ Trend processed: {queue_id}")
            return queue_id
            
        except Exception as e:
            logger.error(f"❌ Failed to process trend: {e}", exc_info=True)
            return None
    
    # =========================================================================
    # AI GENERATION METHODS
    # =========================================================================
    
    async def _generate_email_reply(self, email_data: Dict[str, Any]) -> str:
        """Generate an AI draft reply for an email"""
        try:
            openrouter = await get_openrouter_client()
            
            sender = email_data.get('sender_name') or email_data.get('sender_email', 'Unknown')
            subject = email_data.get('subject', 'No subject')
            body = email_data.get('body', email_data.get('snippet', ''))
            
            prompt = f"""You are drafting a reply to an email. Be professional, warm, and concise.

**From:** {sender}
**Subject:** {subject}

**Email Content:**
{body[:3000]}

**Instructions:**
1. Write a complete, ready-to-send reply
2. Be professional but warm
3. Address all points raised in the email
4. If there are action items mentioned, acknowledge them
5. Keep it concise but complete
6. Sign off appropriately

Write the reply now (no explanations, just the reply text):"""

            response = await openrouter.chat_completion(
                messages=[
                    {"role": "system", "content": self.personalities['professional']},
                    {"role": "user", "content": prompt}
                ],
                model=self.default_model,
                max_tokens=1000,
                temperature=0.7
            )
            
            draft = response['choices'][0]['message']['content'].strip()
            logger.info(f"✅ Generated email reply ({len(draft)} chars)")
            return draft
            
        except Exception as e:
            logger.error(f"❌ Failed to generate email reply: {e}")
            return f"[Draft generation failed: {e}]"
    
    async def _generate_blog_outline(
        self,
        keyword: str,
        business_area: str,
        trend_data: Dict[str, Any],
        rss_context: List[Dict]
    ) -> str:
        """Generate a blog outline with RSS context"""
        try:
            openrouter = await get_openrouter_client()
            
            # Format RSS context
            rss_text = ""
            if rss_context:
                rss_text = "\n\n**Related Industry Insights (from RSS feeds):**\n"
                for i, article in enumerate(rss_context[:5], 1):
                    rss_text += f"{i}. {article.get('title', 'Untitled')}\n"
                    rss_text += f"   Key insight: {article.get('insight', '')[:150]}\n"
            
            prompt = f"""Create a blog post outline for this trending topic.

**Trending Keyword:** {keyword}
**Business Area:** {business_area}
**Trend Score:** {trend_data.get('trend_score_at_alert', 0)}/100
**Momentum:** {trend_data.get('trend_momentum', 'STABLE')}
{rss_text}

**Instructions:**
1. Create a compelling title
2. Write a hook/intro paragraph
3. Outline 3-5 main sections with bullet points
4. Include a call-to-action
5. Incorporate insights from the RSS articles where relevant
6. Make it actionable and valuable

Format as a ready-to-expand outline:"""

            response = await openrouter.chat_completion(
                messages=[
                    {"role": "system", "content": self.personalities['syntaxprime']},
                    {"role": "user", "content": prompt}
                ],
                model=self.default_model,
                max_tokens=1500,
                temperature=0.7
            )
            
            outline = response['choices'][0]['message']['content'].strip()
            logger.info(f"✅ Generated blog outline ({len(outline)} chars)")
            return outline
            
        except Exception as e:
            logger.error(f"❌ Failed to generate blog outline: {e}")
            return f"[Blog outline generation failed: {e}]"
    
    async def _generate_trend_bluesky_post(
        self,
        keyword: str,
        business_area: str,
        trend_data: Dict[str, Any],
        rss_context: List[Dict]
    ) -> str:
        """Generate a Bluesky post for a trend"""
        try:
            openrouter = await get_openrouter_client()
            
            # Get an insight from RSS if available
            rss_insight = ""
            if rss_context:
                rss_insight = f"\nRecent industry insight: {rss_context[0].get('insight', '')[:100]}"
            
            prompt = f"""Write a Bluesky post about this trending topic.

**Keyword:** {keyword}
**Business Area:** {business_area}
**Trend Score:** {trend_data.get('trend_score_at_alert', 0)}/100
{rss_insight}

**Requirements:**
1. Max 280 characters
2. Engaging and shareable
3. Include a perspective or insight, not just facts
4. No hashtags unless absolutely necessary
5. Sound like a real person, not a bot

Write the post now:"""

            response = await openrouter.chat_completion(
                messages=[
                    {"role": "system", "content": "You write engaging, authentic social media posts. You're witty but substantive."},
                    {"role": "user", "content": prompt}
                ],
                model=self.default_model,
                max_tokens=150,
                temperature=0.8
            )
            
            post = response['choices'][0]['message']['content'].strip()
            
            # Ensure under 280 chars
            if len(post) > 280:
                post = post[:277] + "..."
            
            logger.info(f"✅ Generated Bluesky post ({len(post)} chars)")
            return post
            
        except Exception as e:
            logger.error(f"❌ Failed to generate Bluesky post: {e}")
            return f"[Post generation failed]"
    
    # =========================================================================
    # CONTEXT GATHERING
    # =========================================================================
    
    async def _get_rss_context(
        self,
        keyword: str,
        business_area: str,
        limit: int = 5
    ) -> List[Dict]:
        """Get relevant RSS articles for context"""
        try:
            # Query knowledge_entries for relevant content
            conn = await db_manager.get_connection()
            try:
                rows = await conn.fetch('''
                    SELECT 
                        ke.title,
                        ke.content,
                        ke.source_url,
                        ke.created_at,
                        ts_rank(ke.search_vector, plainto_tsquery('english', $1)) AS relevance
                    FROM knowledge_entries ke
                    WHERE ke.search_vector @@ plainto_tsquery('english', $1)
                    AND ke.created_at > NOW() - INTERVAL '30 days'
                    ORDER BY relevance DESC
                    LIMIT $2
                ''', keyword, limit)
                
                context = []
                for row in rows:
                    # Extract first meaningful sentence as insight
                    content = row['content'] or ''
                    sentences = content.split('.')
                    insight = sentences[0].strip() if sentences else ''
                    
                    context.append({
                        'title': row['title'],
                        'insight': insight,
                        'url': row['source_url'],
                        'relevance': float(row['relevance']),
                    })
                
                logger.info(f"✅ Found {len(context)} RSS articles for '{keyword}'")
                return context
                
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.warning(f"⚠️ Failed to get RSS context: {e}")
            return []
    
    # =========================================================================
    # STORAGE AND NOTIFICATION
    # =========================================================================
    
    async def _store_and_notify(self, item: ProactiveItem) -> Optional[str]:
        """Store item in queue and send notification"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Insert into unified_proactive_queue
            queue_id = await conn.fetchval('''
                INSERT INTO unified_proactive_queue (
                    source_type, source_id, source_url, source_title, source_preview,
                    source_metadata, rss_context, trend_context, business_context,
                    content_type, draft_title, draft_text, draft_secondary, draft_structured,
                    personality_used, model_used, priority, status
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 'pending'
                )
                RETURNING id
            ''',
                item.source_type.value,
                item.source_id,
                item.source_url,
                item.source_title,
                item.source_preview,
                json_serialize(item.source_metadata) if item.source_metadata else '{}',
                json_serialize(item.rss_context) if item.rss_context else '[]',
                json_serialize(item.trend_context) if item.trend_context else '{}',
                item.business_context,
                item.content_type.value,
                item.draft_title,
                item.draft_text,
                item.draft_secondary,
                json_serialize(item.draft_structured) if item.draft_structured else '{}',
                item.personality_used,
                item.model_used,
                item.priority,
            )
            
            queue_id_str = str(queue_id)
            
            # Send Telegram notification
            telegram_result = await self._send_proactive_notification(item, queue_id_str)
            
            # Update with Telegram message ID
            if telegram_result.get('success'):
                await conn.execute('''
                    UPDATE unified_proactive_queue
                    SET telegram_message_id = $2,
                        telegram_chat_id = $3,
                        notification_sent_at = NOW()
                    WHERE id = $1
                ''', queue_id, telegram_result.get('message_id'), telegram_result.get('chat_id'))
            
            return queue_id_str
            
        except Exception as e:
            logger.error(f"❌ Failed to store and notify: {e}")
            return None
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _send_proactive_notification(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> Dict[str, Any]:
        """Send rich Telegram notification with draft and action buttons"""
        try:
            from modules.integrations.telegram.bot_client import get_bot_client
            
            bot = get_bot_client()
            chat_id = await self._get_telegram_chat_id()
            
            if not chat_id:
                logger.warning("⚠️ No Telegram chat ID configured")
                return {'success': False, 'error': 'No chat ID'}
            
            # Build message based on source type
            message, buttons = self._build_notification_message(item, queue_id)
            
            # Send message
            result = await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown',
                buttons=buttons
            )
            
            if result.get('success'):
                logger.info(f"✅ Notification sent for {item.source_type.value}")
                return {
                    'success': True,
                    'message_id': result.get('message_id'),
                    'chat_id': chat_id
                }
            else:
                logger.error(f"❌ Notification failed: {result.get('error')}")
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")
            return {'success': False, 'error': str(e)}
    
    def _build_notification_message(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> tuple[str, List[List[Dict]]]:
        """Build notification message and buttons based on source type"""
        
        if item.source_type == SourceType.EMAIL:
            return self._build_email_notification(item, queue_id)
        elif item.source_type == SourceType.MEETING:
            return self._build_meeting_notification(item, queue_id)
        elif item.source_type == SourceType.TREND:
            return self._build_trend_notification(item, queue_id)
        else:
            return self._build_generic_notification(item, queue_id)
    
    def _build_email_notification(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> tuple[str, List[List[Dict]]]:
        """Build email notification with AI draft reply"""
        meta = item.source_metadata or {}
        sender = meta.get('sender_name') or meta.get('sender_email', 'Unknown')
        priority = meta.get('priority', 'normal')
        
        priority_emoji = "🔴" if priority == "urgent" else "🟡" if priority == "high" else "📧"
        
        message = f"{priority_emoji} *New Email - Reply Ready*\n\n"
        message += f"*From:* {self._escape_markdown(sender)}\n"
        message += f"*Subject:* {self._escape_markdown(item.source_title)}\n"
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        message += "📝 *Your Draft Reply:*\n"
        message += f"```\n{item.draft_text[:800]}\n```"
        
        if len(item.draft_text) > 800:
            message += "\n_(truncated for preview)_"
        
        buttons = [
            [
                {"text": "✅ Send Reply", "callback_data": f"proactive:send:{queue_id}"},
                {"text": "✏️ Edit", "callback_data": f"proactive:edit:{queue_id}"}
            ],
            [
                {"text": "👀 View Email", "url": item.source_url} if item.source_url else
                {"text": "❌ Ignore", "callback_data": f"proactive:ignore:{queue_id}"},
                {"text": "❌ Ignore", "callback_data": f"proactive:ignore:{queue_id}"}
            ]
        ]
        
        # Clean up buttons if no URL
        if not item.source_url:
            buttons[1] = [{"text": "❌ Ignore This Email", "callback_data": f"proactive:ignore:{queue_id}"}]
        
        return message, buttons
    
    def _build_meeting_notification(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> tuple[str, List[List[Dict]]]:
        """Build meeting notification with FULL summary (NO TRUNCATION!)"""
        meta = item.source_metadata or {}
        structured = item.draft_structured or {}
        
        duration = meta.get('duration_minutes', 0)
        attendees = meta.get('attendees', [])
        
        message = f"🎙️ *Meeting Summary Ready*\n\n"
        message += f"*{self._escape_markdown(item.source_title)}*\n"
        message += f"📅 {meta.get('start_time', 'Unknown date')}"
        if duration:
            message += f" | ⏱️ {duration} min"
        if attendees:
            message += f"\n👥 {', '.join(attendees[:3])}"
            if len(attendees) > 3:
                message += f" +{len(attendees) - 3} more"
        
        message += "\n\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # FULL SUMMARY - NO TRUNCATION!
        message += "📋 *Summary:*\n"
        message += f"{self._escape_markdown(item.draft_text)}\n"
        
        # Key points
        key_points = structured.get('key_points', [])
        if key_points:
            message += "\n📌 *Key Points:*\n"
            for point in key_points:
                message += f"• {self._escape_markdown(point)}\n"
        
        # Action items
        action_items = structured.get('action_items', [])
        if action_items:
            message += "\n✅ *Action Items:*\n"
            for item_data in action_items[:5]:  # Show up to 5
                if isinstance(item_data, dict):
                    task = item_data.get('text', str(item_data))
                    priority = item_data.get('priority', 'medium')
                    priority_marker = "🔴" if priority == "high" else "🟡" if priority == "medium" else "⚪"
                    assigned = item_data.get('assigned_to')
                    assigned_text = f" → {assigned}" if assigned else ""
                    message += f"{priority_marker} {self._escape_markdown(task)}{assigned_text}\n"
                else:
                    message += f"• {self._escape_markdown(str(item_data))}\n"
        
        # Decisions
        decisions = structured.get('decisions', [])
        if decisions:
            message += "\n🎯 *Decisions Made:*\n"
            for decision in decisions[:3]:
                message += f"• {self._escape_markdown(decision)}\n"
        
        buttons = [
            [
                {"text": "📋 Copy to Slack", "callback_data": f"proactive:copy:{queue_id}"},
                {"text": "📝 Create Tasks", "callback_data": f"proactive:tasks:{queue_id}"}
            ],
            [
                {"text": "✅ Done", "callback_data": f"proactive:done:{queue_id}"}
            ]
        ]
        
        if item.source_url:
            buttons[1].insert(0, {"text": "🔗 View Recording", "url": item.source_url})
        
        return message, buttons
    
    def _build_trend_notification(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> tuple[str, List[List[Dict]]]:
        """Build trend notification with blog outline and Bluesky post"""
        meta = item.source_metadata or {}
        trend_ctx = item.trend_context or {}
        
        score = meta.get('trend_score', 0)
        momentum = meta.get('momentum', 'STABLE')
        urgency = meta.get('urgency', 'medium')
        
        urgency_emoji = "🔴" if urgency == "high" else "🟡" if urgency == "medium" else "🟢"
        momentum_emoji = "🚀" if momentum == "BREAKOUT" else "📈" if momentum == "RISING" else "➡️"
        
        message = f"📊 *Content Opportunity*\n\n"
        message += f"*{self._escape_markdown(item.source_title)}*\n"
        message += f"Score: {score}/100 {urgency_emoji} | {momentum_emoji} {momentum}\n"
        
        if item.business_context:
            message += f"Business: {item.business_context}\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Blog outline
        message += "📝 *Blog Outline:*\n"
        message += f"```\n{item.draft_text[:1000]}\n```\n"
        
        # Bluesky post (secondary)
        if item.draft_secondary:
            message += "\n🦋 *Bluesky Post:*\n"
            message += f"`{item.draft_secondary}`\n"
        
        # RSS context
        if item.rss_context:
            message += "\n📚 *Based on RSS insights:*\n"
            for ctx in item.rss_context[:2]:
                message += f"• {self._escape_markdown(ctx.get('title', ''))[:50]}...\n"
        
        buttons = [
            [
                {"text": "📝 Start Blog", "callback_data": f"proactive:blog:{queue_id}"},
                {"text": "🦋 Post This", "callback_data": f"proactive:post:{queue_id}"}
            ],
            [
                {"text": "🔍 Research More", "callback_data": f"proactive:research:{queue_id}"},
                {"text": "❌ Skip", "callback_data": f"proactive:skip:{queue_id}"}
            ]
        ]
        
        return message, buttons
    
    def _build_generic_notification(
        self,
        item: ProactiveItem,
        queue_id: str
    ) -> tuple[str, List[List[Dict]]]:
        """Build generic notification"""
        message = f"📌 *{self._escape_markdown(item.source_title)}*\n\n"
        message += f"{self._escape_markdown(item.draft_text[:500])}\n"
        
        buttons = [
            [
                {"text": "✅ Action", "callback_data": f"proactive:action:{queue_id}"},
                {"text": "❌ Skip", "callback_data": f"proactive:skip:{queue_id}"}
            ]
        ]
        
        return message, buttons
    
    # =========================================================================
    # ACTION HANDLERS
    # =========================================================================
    
    async def execute_action(
        self,
        queue_id: str,
        action: str,
        edited_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute an action on a proactive queue item"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get the queue item
            row = await conn.fetchrow('''
                SELECT * FROM unified_proactive_queue WHERE id = $1
            ''', queue_id)
            
            if not row:
                return {'success': False, 'message': 'Item not found'}
            
            source_type = row['source_type']
            
            # Route to appropriate handler
            if action == 'send' and source_type == 'email':
                result = await self._execute_send_email(row, edited_text)
            elif action == 'post' and source_type == 'trend':
                result = await self._execute_bluesky_post(row)
            elif action == 'tasks' and source_type == 'meeting':
                result = await self._execute_create_tasks(row)
            elif action == 'copy':
                result = await self._execute_copy(row)
            elif action in ['skip', 'ignore', 'done']:
                result = await self._execute_skip(row, action)
            else:
                result = {'success': False, 'message': f'Unknown action: {action}'}
            
            # Update queue item status
            if result.get('success'):
                await conn.execute('''
                    UPDATE unified_proactive_queue
                    SET status = 'actioned',
                        action_taken = $2,
                        action_result = $3,
                        actioned_at = NOW()
                    WHERE id = $1
                ''', queue_id, action, json_serialize(result))
                
                # Update Telegram message
                await self._update_telegram_message(row, action, result)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to execute action: {e}")
            return {'success': False, 'message': str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _execute_skip(self, row: Dict, action: str) -> Dict[str, Any]:
        """Mark item as skipped/ignored/done"""
        return {
            'success': True,
            'message': f'Marked as {action}',
            'action': action
        }
    
    async def _execute_create_tasks(self, row: Dict) -> Dict[str, Any]:
        """Create ClickUp tasks from meeting action items"""
        # TODO: Implement ClickUp task creation
        return {
            'success': True,
            'message': 'Tasks would be created (not yet implemented)',
            'action': 'tasks'
        }
    
    async def _execute_copy(self, row: Dict) -> Dict[str, Any]:
        """Mark as copied (user copies from Telegram)"""
        return {
            'success': True,
            'message': 'Copied! Paste into Slack.',
            'action': 'copy'
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _build_full_meeting_summary(
        self,
        meeting_data: Dict[str, Any],
        summary_data: Dict[str, Any]
    ) -> str:
        """Build full meeting summary text (NO TRUNCATION!)"""
        return summary_data.get('summary', 'No summary available')
    
    async def _is_already_processed(self, source_type: str, source_id: str) -> bool:
        """Check if source has already been processed"""
        if not source_id:
            return False
            
        conn = await db_manager.get_connection()
        try:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM unified_proactive_queue
                WHERE source_type = $1 AND source_id = $2
            ''', source_type, source_id)
            return count > 0
        finally:
            await db_manager.release_connection(conn)
    
    async def _is_email_ignored(self, email_data: Dict[str, Any]) -> bool:
        """Check if email should be ignored"""
        conn = await db_manager.get_connection()
        try:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM email_ignore_list
                WHERE user_id = $1
                AND (
                    message_id = $2
                    OR thread_id = $3
                    OR sender_email = $4
                )
                AND (expires_at IS NULL OR expires_at > NOW())
            ''',
                self.user_id,
                email_data.get('message_id'),
                email_data.get('thread_id'),
                email_data.get('sender_email')
            )
            return count > 0
        except:
            return False
        finally:
            await db_manager.release_connection(conn)
    
    async def _store_meeting_action_items(
        self,
        meeting_id: str,
        queue_id: str,
        action_items: List[Dict]
    ):
        """Store meeting action items for tracking"""
        if not action_items:
            return
            
        conn = await db_manager.get_connection()
        try:
            for item in action_items:
                if isinstance(item, dict):
                    await conn.execute('''
                        INSERT INTO meeting_action_items 
                        (meeting_id, proactive_queue_id, task_text, assigned_to, priority)
                        VALUES ($1, $2, $3, $4, $5)
                    ''',
                        meeting_id,
                        queue_id,
                        item.get('text', str(item)),
                        item.get('assigned_to'),
                        item.get('priority', 'medium')
                    )
        finally:
            await db_manager.release_connection(conn)
    
    def _map_email_priority(self, priority: Optional[str]) -> str:
        """Map email priority to queue priority"""
        mapping = {
            'urgent': 'critical',
            'high': 'high',
            'normal': 'medium',
            'low': 'low'
        }
        return mapping.get(priority, 'medium')
    
    def _calculate_meeting_priority(self, summary_data: Dict) -> str:
        """Calculate meeting priority based on action items"""
        action_items = summary_data.get('action_items', [])
        high_priority_items = [
            item for item in action_items
            if isinstance(item, dict) and item.get('priority') == 'high'
        ]
        
        if len(high_priority_items) >= 2:
            return 'high'
        elif action_items:
            return 'medium'
        return 'low'
    
    def _build_gmail_url(self, message_id: Optional[str]) -> Optional[str]:
        """Build Gmail URL from message ID"""
        if not message_id:
            return None
        return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"
    
    async def _get_telegram_chat_id(self) -> Optional[int]:
        """Get Telegram chat ID for notifications"""
        conn = await db_manager.get_connection()
        try:
            row = await conn.fetchrow('''
                SELECT telegram_chat_id FROM user_settings
                WHERE user_id = $1
            ''', self.user_id)
            return row['telegram_chat_id'] if row else None
        except:
            # Fallback to environment variable
            import os
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            return int(chat_id) if chat_id else None
        finally:
            await db_manager.release_connection(conn)
    
    async def _update_telegram_message(
        self,
        row: Dict,
        action: str,
        result: Dict
    ):
        """Update Telegram message after action"""
        try:
            message_id = row.get('telegram_message_id')
            chat_id = row.get('telegram_chat_id')
            
            if not message_id or not chat_id:
                return
            
            from modules.integrations.telegram.bot_client import get_bot_client
            bot = get_bot_client()
            
            # Build updated message
            action_emoji = {
                'send': '✅ Reply Sent!',
                'post': '✅ Posted to Bluesky!',
                'tasks': '✅ Tasks Created!',
                'copy': '📋 Copied!',
                'skip': '⏭️ Skipped',
                'ignore': '🔕 Ignored',
                'done': '✅ Done'
            }
            
            status_text = action_emoji.get(action, f'✅ {action.title()}')
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{status_text}\n\n_{row.get('source_title', 'Item')}_",
                buttons=[]  # Remove buttons
            )
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to update Telegram message: {e}")
    
    def _escape_markdown(self, text: str) -> str:
        """Escape Markdown special characters"""
        if not text:
            return ""
        for char in ['*', '_', '`', '[', ']']:
            text = text.replace(char, '\\' + char)
        return text


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

async def process_email_proactively(email_data: Dict[str, Any]) -> Optional[str]:
    """Convenience function to process an email"""
    engine = get_unified_engine()
    return await engine.process_email(email_data)


async def process_meeting_proactively(
    meeting_data: Dict[str, Any],
    summary_data: Dict[str, Any]
) -> Optional[str]:
    """Convenience function to process a meeting"""
    engine = get_unified_engine()
    return await engine.process_meeting(meeting_data, summary_data)


async def process_trend_proactively(trend_data: Dict[str, Any]) -> Optional[str]:
    """Convenience function to process a trend"""
    engine = get_unified_engine()
    return await engine.process_trend(trend_data)
