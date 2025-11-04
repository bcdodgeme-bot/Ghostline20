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
"""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from uuid import UUID

logger = logging.getLogger(__name__)

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
        ai_service=None
    ):
        """
        Initialize with all necessary integrations.
        
        Args:
            db_manager: Database manager
            clickup_handler: ClickUp API handler
            calendar_client: Google Calendar client
            gmail_client: Gmail client
            ai_service: AI service for drafting (OpenRouter)
        """
        self.db = db_manager
        self.clickup = clickup_handler
        self.calendar = calendar_client
        self.gmail = gmail_client
        self.ai = ai_service
        
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
                assigned_to = item.get('assigned_to', 'You')
                meeting_id = item.get('meeting_id')
                
                # Fetch meeting context from database
                meeting_summary = ""
                meeting_points = ""
                recording_link = ""
                
                if meeting_id:
                    meeting_query = """
                        SELECT ai_summary, key_points, share_url 
                        FROM fathom_meetings 
                        WHERE id = $1
                    """
                    meeting_data = await self.db.fetch_one(meeting_query, meeting_id)
                    
                    if meeting_data:
                        meeting_summary = meeting_data['ai_summary'] or ""
                        meeting_points = meeting_data['key_points'] or ""
                        recording_link = meeting_data['share_url'] or ""
                
                # Create task title
                title = f"[{meeting_title}] {action_text}"
                
                # Build enriched description
                description = f"**Action Item:** {action_text}\n"
                description += f"**Assigned To:** {assigned_to}\n\n"
                description += "---\n\n"
                description += f"**From Meeting:** {meeting_title}\n\n"
                
                if meeting_summary:
                    description += f"**Meeting Summary:**\n{meeting_summary}\n\n"
                
                if meeting_points:
                    description += f"**Key Points:**\n{meeting_points}\n\n"
                
                if recording_link:
                    description += f"🎥 **[View Recording]({recording_link})**\n\n"
                
                if urgent or item.get('overdue', False):
                    description = "⚠️ **URGENT - This is overdue!**\n\n" + description
                
                # Create ClickUp task
                result = await self.clickup.create_personal_task(
                    title=title,
                    description=description
                )
            
                if result:
                    created_tasks.append({
                        'action_text': action_text,
                        'task_id': result.get('id'),
                        'task_url': result.get('url')
                    })
                    logger.info(f"✅ Created task: {title}")
                else:
                    failed_tasks.append(action_text)
                    logger.warning(f"❌ Failed to create task: {title}")
    
            except Exception as e:
                logger.error(f"Error creating reminder for item: {e}")
                failed_tasks.append(action_text)
        
        # Build result message
        if created_tasks and not failed_tasks:
            message = f"✅ **Created {len(created_tasks)} reminder(s)**\n\n"
            for task in created_tasks[:3]:  # Show first 3
                message += f"✓ {task['action_text']}\n"
            
            if len(created_tasks) > 3:
                message += f"\n...and {len(created_tasks) - 3} more"
            
            return {
                'success': True,
                'message': message,
                'details': {
                    'created_count': len(created_tasks),
                    'tasks': created_tasks
                }
            }
        
        elif created_tasks and failed_tasks:
            message = f"⚠️ **Created {len(created_tasks)} of {len(action_items)} reminders**\n\n"
            message += f"✅ Succeeded: {len(created_tasks)}\n"
            message += f"❌ Failed: {len(failed_tasks)}"
            
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
                'message': f"❌ Failed to create any reminders ({len(failed_tasks)} items)",
                'details': {
                    'failed_count': len(failed_tasks),
                    'failed_items': failed_tasks
                }
            }
    
    
    async def _execute_draft_email(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Draft an email using AI.
        
        Uses OpenRouter to generate email draft based on context.
        """
        meeting_title = parameters.get('meeting_title', 'Meeting')
        action_items = parameters.get('action_items', [])
        next_meeting = parameters.get('next_meeting', {})
        
        # Build prompt for AI
        prompt = f"Draft a professional follow-up email for a meeting titled '{meeting_title}'.\n\n"
        
        if action_items:
            prompt += "Action items from the meeting:\n"
            for item in action_items:
                prompt += f"- {item.get('action_text', 'Action')}\n"
            prompt += "\n"
        
        if next_meeting:
            next_title = next_meeting.get('title', 'Follow-up')
            prompt += f"Mention that we have a follow-up meeting scheduled: {next_title}\n\n"
        
        prompt += "Keep the tone professional but friendly. Include a subject line."
        
        # For now, return a placeholder - you'll integrate with OpenRouter
        # TODO: Integrate with your existing OpenRouter chat service
        
        draft = f"**Subject:** Follow-up: {meeting_title}\n\n"
        draft += f"Hi team,\n\n"
        draft += f"Thanks for a productive meeting on {meeting_title}. "
        
        if action_items:
            draft += f"I wanted to recap our {len(action_items)} action items:\n\n"
            for item in action_items:
                draft += f"• {item.get('action_text', 'Action')}\n"
        
        if next_meeting:
            draft += f"\n\nLooking forward to our next discussion: {next_meeting.get('title', 'Follow-up')}"
        
        draft += "\n\nBest regards"
        
        return {
            'success': True,
            'message': f"✅ **Email Draft Created**\n\n{draft}\n\n_Copy this draft to your email client_",
            'details': {
                'draft': draft,
                'meeting_title': meeting_title,
                'action_items_count': len(action_items)
            }
        }
    
    
    async def _execute_draft_email_response(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Draft a response to an email."""
        sender_name = parameters.get('sender_name', 'Sender')
        subject = parameters.get('subject', 'Email')
        
        draft = f"**RE: {subject}**\n\n"
        draft += f"Hi {sender_name},\n\n"
        draft += f"Thanks for your email. I've reviewed the information and here are my thoughts:\n\n"
        draft += f"[Add your response here]\n\n"
        draft += f"Best regards"
        
        return {
            'success': True,
            'message': f"✅ **Email Response Draft**\n\n{draft}\n\n_Customize and send_",
            'details': {
                'draft': draft,
                'sender_name': sender_name,
                'subject': subject
            }
        }
    
    
    async def _execute_review_notes(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Fetch and display meeting notes/summary."""
        meeting_id = parameters.get('meeting_id')
        meeting_title = parameters.get('meeting_title', 'Meeting')
        
        if not meeting_id:
            return {
                'success': False,
                'message': "❌ No meeting ID provided",
                'details': {}
            }
        
        # Fetch meeting from database
        query = """
            SELECT 
                title,
                meeting_date,
                ai_summary,
                key_points,
                transcript_text
            FROM fathom_meetings
            WHERE id = $1
        """
        
        meeting = await self.db.fetch_one(query, meeting_id)
        
        if not meeting:
            return {
                'success': False,
                'message': f"❌ Meeting notes not found for {meeting_title}",
                'details': {'meeting_id': str(meeting_id)}
            }
        
        # Build notes summary
        notes = f"📋 **Meeting Notes: {meeting['title']}**\n\n"
        notes += f"**Date:** {meeting['meeting_date'].strftime('%B %d, %Y')}\n\n"
        
        if meeting['ai_summary']:
            notes += f"**Summary:**\n{meeting['ai_summary']}\n\n"
        
        if meeting['key_points']:
            points = json.loads(meeting['key_points']) if isinstance(meeting['key_points'], str) else meeting['key_points']
            if points:
                notes += f"**Key Points:**\n"
                for point in points[:5]:  # Show top 5
                    notes += f"• {point}\n"
        
        return {
            'success': True,
            'message': notes,
            'details': {
                'meeting_id': str(meeting_id),
                'meeting_title': meeting['title'],
                'has_summary': bool(meeting['ai_summary']),
                'has_transcript': bool(meeting['transcript_text'])
            }
        }
    
    
    async def _execute_check_action_items(
        self,
        parameters: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Check action items from a specific meeting."""
        meeting_id = parameters.get('meeting_id')
        meeting_title = parameters.get('meeting_title', 'Meeting')
        
        if not meeting_id:
            return {
                'success': False,
                'message': "❌ No meeting ID provided",
                'details': {}
            }
        
        # Fetch action items
        query = """
            SELECT 
                action_text,
                assigned_to,
                due_date,
                priority,
                status
            FROM meeting_action_items
            WHERE meeting_id = $1
            ORDER BY priority DESC, due_date ASC
        """
        
        items = await self.db.fetch_all(query, meeting_id)
        
        if not items:
            return {
                'success': True,
                'message': f"📋 No action items found for {meeting_title}",
                'details': {'action_items_count': 0}
            }
        
        # Build action items list
        message = f"📋 **Action Items: {meeting_title}**\n\n"
        
        pending_items = [item for item in items if item['status'] == 'pending']
        completed_items = [item for item in items if item['status'] == 'completed']
        
        if pending_items:
            message += f"**Pending ({len(pending_items)}):**\n"
            for item in pending_items:
                priority_emoji = "🔴" if item['priority'] == 'high' else "🟡" if item['priority'] == 'medium' else "🟢"
                message += f"{priority_emoji} {item['action_text']}\n"
                message += f"   Assigned: {item['assigned_to'] or 'Unassigned'}\n"
        
        if completed_items:
            message += f"\n**Completed ({len(completed_items)}):**\n"
            for item in completed_items[:3]:  # Show first 3 completed
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
