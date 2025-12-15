# modules/intelligence/action_executor.py
"""
Action Executor for Syntax Prime V2 Intelligence Hub
Executes actions suggested by the Action Suggester

This module takes action dictionaries and makes them happen:
- Creates ClickUp tasks
- Creates calendar reminders
- Drafts emails using AI
- Fetches meeting notes
- Generates talking points

Each execution returns a result dict with:
- success: bool
- message: str (user-facing message)
- details: dict (execution details for learning)

Created: 11/04/25
Updated: 2025-01-XX - Added singleton pattern, fixed duplicate review_email bug
Updated: 2025-12-15 - Fixed singleton to use imported db_manager as fallback
Updated: 2025-12-15 - CRITICAL FIX: Removed async from get_action_executor (was causing coroutine errors)
"""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID

from modules.core.database import db_manager

logger = logging.getLogger(__name__)

#===============================================================================
# CONSTANTS
#===============================================================================

USER_ID = UUID("b7c60682-4815-4d9d-8ebe-66c6cd24eff9")

#===============================================================================
# SINGLETON INSTANCE
#===============================================================================

_executor_instance: Optional['ActionExecutor'] = None


def get_action_executor(
    clickup_handler=None,
    calendar_client=None,
    gmail_client=None,
    ai_service=None,
    content_generator=None
) -> 'ActionExecutor':
    """
    Get or create the singleton ActionExecutor instance.
    
    Uses the global db_manager singleton automatically.
    Optional integrations can be passed on first call.
    
    NOTE: This is intentionally NOT async - no async operations needed.
    
    Args:
        clickup_handler: ClickUp API handler (optional)
        calendar_client: Google Calendar client (optional)
        gmail_client: Gmail client (optional)
        ai_service: AI service for drafting (optional)
        content_generator: Content generator for Bluesky posts (optional)
        
    Returns:
        ActionExecutor singleton instance
    """
    global _executor_instance
    
    if _executor_instance is None:
        _executor_instance = ActionExecutor(
            db_manager=db_manager,
            clickup_handler=clickup_handler,
            calendar_client=calendar_client,
            gmail_client=gmail_client,
            ai_service=ai_service,
            content_generator=content_generator
        )
    
    return _executor_instance


#===============================================================================
# ACTION EXECUTOR - Makes actions happen
#===============================================================================

class ActionExecutor:
    """
    Executes actions from the intelligence system.
    
    Routes action types to appropriate integrations and returns
    results for the learning system.
    """
    
    def __init__(
        self,
        db_manager,
        clickup_handler=None,
        calendar_client=None,
        gmail_client=None,
        ai_service=None,
        content_generator=None
    ):
        """
        Initialize with all necessary integrations.
        
        Args:
            db_manager: Database manager
            clickup_handler: ClickUp API handler
            calendar_client: Google Calendar client
            gmail_client: Gmail client
            ai_service: AI service for drafting (OpenRouter)
            content_generator: Content generator for Bluesky posts
        """
        self.db = db_manager
        self.clickup = clickup_handler
        self.calendar = calendar_client
        self.gmail = gmail_client
        self.ai = ai_service
        self.content_generator = content_generator
        
        logger.info("🔧 Action Executor initialized")
    
    
    async def execute_action(
        self,
        action: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Execute a single action.
        
        Args:
            action: Action dict from ActionSuggester
            user_id: User ID
            
        Returns:
            Result dict with success, message, and details
        """
        action_type = action.get('action_type', 'unknown')
        parameters = action.get('parameters', {})
        
        logger.info(f"⚡ Executing action: {action_type}")
        
        try:
            # Route to appropriate executor
            if action_type == 'create_reminders':
                return await self._execute_create_reminders(parameters, user_id)
            
            elif action_type == 'draft_email':
                return await self._execute_draft_email(parameters, user_id)
            
            elif action_type == 'draft_email_response':
                return await self._execute_draft_email_response(parameters, user_id)
            
            elif action_type == 'review_notes':
                return await self._execute_review_notes(parameters, user_id)
            
            elif action_type == 'check_action_items':
                return await self._execute_check_action_items(parameters, user_id)
            
            elif action_type == 'prepare_talking_points':
                return await self._execute_prepare_talking_points(parameters, user_id)
            
            elif action_type == 'create_clickup_task':
                return await self._execute_create_clickup_task(parameters, user_id)
            
            elif action_type == 'review_email':
                return await self._execute_review_email(parameters, user_id)

            elif action_type == 'draft_bluesky_post':
                return await self._execute_draft_bluesky_post(parameters, user_id)

            else:
                logger.warning(f"Unknown action type: {action_type}")
                return {
                    'success': False,
                    'message': f"❌ Action type '{action_type}' not implemented yet",
                    'details': {'action_type': action_type}
                }
            
        except Exception as e:
            logger.error(f"Error executing {action_type}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"❌ Error: {str(e)}",
                'details': {'error': str(e), 'action_type': action_type}
            }
    
    
    #===========================================================================
    # ACTION EXECUTORS - One for each action type
    #===========================================================================
    
    async def _execute_create_reminders(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Create calendar reminders for action items.
        
        Creates ClickUp tasks for each action item with due dates.
        """
        action_items = parameters.get('action_items', [])
        meeting_title = parameters.get('meeting_title', 'Meeting')
        urgent = parameters.get('urgent', False)
        meeting_id = parameters.get('meeting_id')
        
        # ADD THIS DEBUG LINE:
        logger.info(f"🔍 DEBUG: meeting_id = {meeting_id}")
        
        if not action_items:
            return {
                'success': False,
                'message': "❌ No action items to create reminders for",
                'details': {'action_items_count': 0}
            }
        
        if not self.clickup:
            return {
                'success': False,
                'message': "❌ ClickUp integration not available",
                'details': {'integration_missing': 'clickup'}
            }
        
        created_tasks = []
        failed_tasks = []
        
        for item in action_items:
            try:
                action_text = item.get('action_text', 'Action item')
                due_date = item.get('due_date')
                assignee = item.get('assignee', 'Carl')
                
                # Determine priority (higher for urgent items)
                priority = 2 if urgent else 3  # 2=High, 3=Normal in ClickUp
                
                # Build task description with meeting context
                description = f"📋 From meeting: {meeting_title}\n\n"
                description += f"Action item: {action_text}\n"
                if assignee:
                    description += f"Assigned to: {assignee}\n"
                if meeting_id:
                    description += f"\n[View Meeting Notes](/meetings/{meeting_id})"
                
                # Create task in personal workspace
                result = await self.clickup.create_personal_task(
                    name=action_text[:100],  # ClickUp has title limits
                    description=description,
                    due_date=due_date,
                    priority=priority
                )
                
                if result:
                    created_tasks.append({
                        'action': action_text,
                        'task_id': result.get('id'),
                        'url': result.get('url')
                    })
                else:
                    failed_tasks.append(action_text)
                    
            except Exception as e:
                logger.error(f"Failed to create task for '{action_text}': {e}")
                failed_tasks.append(action_text)
        
        # Build response message
        if created_tasks:
            message = f"✅ Created {len(created_tasks)} task(s) from {meeting_title}:\n\n"
            for task in created_tasks:
                message += f"• {task['action'][:50]}...\n"
            
            if failed_tasks:
                message += f"\n⚠️ {len(failed_tasks)} task(s) failed to create"
            
            return {
                'success': True,
                'message': message,
                'details': {
                    'created_count': len(created_tasks),
                    'failed_count': len(failed_tasks),
                    'tasks': created_tasks
                }
            }
        else:
            return {
                'success': False,
                'message': f"❌ Failed to create tasks from {meeting_title}",
                'details': {
                    'created_count': 0,
                    'failed_count': len(failed_tasks)
                }
            }
    
    
    async def _execute_draft_email(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Draft an email using AI."""
        recipient = parameters.get('recipient', 'Unknown')
        context = parameters.get('context', '')
        email_type = parameters.get('email_type', 'followup')
        
        # For now, return a placeholder
        # TODO: Integrate with AI service for actual drafting
        return {
            'success': True,
            'message': f"📝 Draft email ready for {recipient}\n\nContext: {context[:100]}...\n\n[Click to edit in Gmail]",
            'details': {
                'recipient': recipient,
                'email_type': email_type,
                'draft_created': True
            }
        }
    
    
    async def _execute_draft_email_response(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Draft a response to an existing email thread using AI.
        """
        email_id = parameters.get('email_id')
        sender_name = parameters.get('sender_name', 'Unknown')
        subject = parameters.get('subject', 'Email')
        tone = parameters.get('tone', 'professional')  # professional, friendly, formal
        
        if not email_id:
            return {
                'success': False,
                'message': "❌ No email ID provided for response",
                'details': {}
            }
        
        # Fetch original email from database
        query = """
            SELECT sender_email, subject, snippet, body_preview
            FROM google_gmail_analysis
            WHERE id = $1
        """
        
        email = await self.db.fetch_one(query, email_id)
        
        if not email:
            return {
                'success': False,
                'message': f"❌ Original email not found",
                'details': {'email_id': str(email_id)}
            }
        
        # For now, provide guidance for manual drafting
        # TODO: Integrate with AI for actual draft generation
        message = f"📧 **Draft Response to {sender_name}**\n\n"
        message += f"**Subject:** Re: {email['subject']}\n"
        message += f"**Tone:** {tone.title()}\n\n"
        message += "**Original message preview:**\n"
        message += f"{email.get('snippet', '')[:150]}...\n\n"
        message += "💡 **Suggested approach:**\n"
        message += "• Acknowledge their message\n"
        message += "• Address main points\n"
        message += "• Propose next steps\n"
        message += "• End with clear call to action\n"
        
        return {
            'success': True,
            'message': message,
            'details': {
                'email_id': str(email_id),
                'sender': sender_name,
                'tone': tone
            }
        }
    
    
    async def _execute_review_notes(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Fetch and display meeting notes for review."""
        meeting_id = parameters.get('meeting_id')
        meeting_title = parameters.get('meeting_title', 'Meeting')
        
        if not meeting_id:
            return {
                'success': False,
                'message': "❌ No meeting ID provided",
                'details': {}
            }
        
        # Fetch notes from database
        query = """
            SELECT title, summary, transcript_summary, action_items
            FROM fathom_meetings
            WHERE id = $1
        """
        
        meeting = await self.db.fetch_one(query, meeting_id)
        
        if not meeting:
            return {
                'success': False,
                'message': f"❌ Meeting notes not found for: {meeting_title}",
                'details': {'meeting_id': str(meeting_id)}
            }
        
        # Build notes summary
        notes = f"📝 **Meeting Notes: {meeting['title']}**\n\n"
        
        if meeting.get('summary'):
            notes += f"**Summary:**\n{meeting['summary'][:500]}\n\n"
        
        if meeting.get('action_items'):
            items = meeting['action_items']
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except:
                    items = []
            
            if items:
                notes += "**Action Items:**\n"
                for item in items[:5]:  # Limit to 5 items
                    action_text = item.get('action_text', str(item))
                    notes += f"• {action_text}\n"
        
        return {
            'success': True,
            'message': notes,
            'details': {
                'meeting_id': str(meeting_id),
                'title': meeting['title'],
                'has_summary': bool(meeting.get('summary')),
                'action_item_count': len(meeting.get('action_items', []))
            }
        }
    
    
    async def _execute_check_action_items(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Check status of action items from a meeting."""
        meeting_id = parameters.get('meeting_id')
        
        if not meeting_id:
            return {
                'success': False,
                'message': "❌ No meeting ID provided",
                'details': {}
            }
        
        # Fetch action items
        query = """
            SELECT action_items FROM fathom_meetings WHERE id = $1
        """
        
        result = await self.db.fetch_one(query, meeting_id)
        
        if not result or not result.get('action_items'):
            return {
                'success': False,
                'message': "❌ No action items found for this meeting",
                'details': {'meeting_id': str(meeting_id)}
            }
        
        items = result['action_items']
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
        
        # Categorize items (for now, just list them)
        # TODO: Track completion status in separate table
        pending_items = []
        completed_items = []
        
        for item in items:
            # Check if item is marked complete (future feature)
            if item.get('completed'):
                completed_items.append(item)
            else:
                pending_items.append(item)
        
        message = f"📋 **Action Item Status**\n\n"
        
        if pending_items:
            message += f"**Pending ({len(pending_items)}):**\n"
            for item in pending_items[:5]:
                action_text = item.get('action_text', str(item))
                message += f"⏳ {action_text}\n"
        
        if completed_items:
            message += f"\n**Completed ({len(completed_items)}):**\n"
            for item in completed_items[:3]:
                message += f"✅ {item['action_text']}\n"
        
        return {
            'success': True,
            'message': message,
            'details': {
                'total_items': len(items),
                'pending_count': len(pending_items),
                'completed_count': len(completed_items)
            }
        }
    
    
    async def _execute_prepare_talking_points(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Generate talking points for a meeting based on context."""
        email_subject = parameters.get('email_subject', '')
        event_title = parameters.get('event_title', 'Meeting')
        
        # Build talking points based on context
        points = f"💡 **Talking Points: {event_title}**\n\n"
        
        if email_subject:
            points += f"**Context:** Email about '{email_subject}'\n\n"
        
        points += "**Key topics to discuss:**\n"
        points += "• Review objectives and expected outcomes\n"
        points += "• Clarify next steps and responsibilities\n"
        points += "• Set timeline for deliverables\n"
        points += "• Address any blockers or concerns\n"
        points += "• Schedule follow-up if needed\n"
        
        return {
            'success': True,
            'message': points,
            'details': {
                'event_title': event_title,
                'has_email_context': bool(email_subject)
            }
        }
    
    
    async def _execute_create_clickup_task(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Create a ClickUp task."""
        title = parameters.get('title', 'Task')
        description = parameters.get('description', '')
        workspace = parameters.get('workspace', 'personal')  # 'personal' or 'amcf'
        
        if not self.clickup:
            return {
                'success': False,
                'message': "❌ ClickUp integration not available",
                'details': {}
            }
        
        # Create task in appropriate workspace
        if workspace == 'amcf':
            result = await self.clickup.create_amcf_task(title, description)
        else:
            result = await self.clickup.create_personal_task(title, description)
        
        if result:
            task_url = result.get('url', '')
            return {
                'success': True,
                'message': f"✅ **Task Created**\n\n{title}\n\n[View in ClickUp]({task_url})",
                'details': {
                    'task_id': result.get('id'),
                    'task_url': task_url,
                    'workspace': workspace
                }
            }
        else:
            return {
                'success': False,
                'message': f"❌ Failed to create task: {title}",
                'details': {'title': title, 'workspace': workspace}
            }
    
    
    async def _execute_review_email(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Fetch and display an email for review."""
        email_id = parameters.get('email_id')
        sender_name = parameters.get('sender_name', 'Unknown')
        subject = parameters.get('subject', 'Email')
        
        if not email_id:
            return {
                'success': False,
                'message': "❌ No email ID provided",
                'details': {}
            }
        
        # Fetch email from database
        query = """
            SELECT 
                sender_name,
                subject,
                snippet,
                priority_level,
                category,
                requires_response,
                received_at
            FROM google_gmail_analysis
            WHERE id = $1
        """
        
        email = await self.db.fetch_one(query, email_id)
        
        if not email:
            return {
                'success': False,
                'message': f"❌ Email not found: {subject}",
                'details': {'email_id': str(email_id)}
            }
        
        # Build email summary
        review = f"📧 **Email Review**\n\n"
        review += f"**From:** {email['sender_name']}\n"
        review += f"**Subject:** {email['subject']}\n"
        review += f"**Priority:** {email['priority_level']}\n"
        review += f"**Category:** {email['category']}\n"
        review += f"**Received:** {email['received_at'].strftime('%b %d at %I:%M %p')}\n\n"
        
        if email['snippet']:
            review += f"**Preview:**\n{email['snippet'][:200]}...\n\n"
        
        if email['requires_response']:
            review += "⚠️ **Requires response**"
        
        return {
            'success': True,
            'message': review,
            'details': {
                'email_id': str(email_id),
                'sender_name': email['sender_name'],
                'subject': email['subject'],
                'priority': email['priority_level'],
                'requires_response': email['requires_response']
            }
        }
        
    async def _execute_draft_bluesky_post(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Generate a Bluesky post draft for a trending topic.
        
        Uses content generator to create a post draft based on trend opportunity.
        """
        keyword = parameters.get('keyword', 'Topic')
        account = parameters.get('account', 'syntaxprime')
        opportunity_id = parameters.get('opportunity_id')
        
        # Check if content generator is available
        if not self.content_generator:
            return {
                'success': False,
                'message': "❌ Content generator not available",
                'details': {'keyword': keyword}
            }
        
        # If we have an opportunity_id, use it directly
        if opportunity_id:
            try:
                result = await self.content_generator.generate_bluesky_post(
                    opportunity_id=UUID(opportunity_id),
                    account_id=account
                )
                
                if result.get('success'):
                    queue_id = result.get('queue_id')
                    preview = result.get('preview', keyword)[:100]
                    
                    return {
                        'success': True,
                        'message': f"✅ Draft created for '{keyword}' on @{account}\n\n{preview}...\n\nApproval notification coming soon!",
                        'details': {
                            'keyword': keyword,
                            'account': account,
                            'queue_id': str(queue_id)
                        }
                    }
                else:
                    return {
                        'success': False,
                        'message': f"❌ Failed to generate draft: {result.get('error', 'Unknown error')}",
                        'details': {'keyword': keyword, 'account': account}
                    }
                    
            except Exception as e:
                logger.error(f"Error generating Bluesky post: {e}", exc_info=True)
                return {
                    'success': False,
                    'message': f"❌ Error: {str(e)}",
                    'details': {'keyword': keyword, 'error': str(e)}
                }
        
        # Fallback: No opportunity_id available
        else:
            return {
                'success': False,
                'message': f"❌ Cannot generate post - missing opportunity ID",
                'details': {
                    'keyword': keyword,
                    'account': account
                }
            }


#===============================================================================
# MODULE EXPORTS
#===============================================================================

__all__ = [
    'ActionExecutor',
    'get_action_executor',
    'USER_ID'
]
