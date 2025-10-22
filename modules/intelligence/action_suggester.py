# modules/intelligence/action_suggester.py
"""
Action Suggester for Syntax Prime V2 Intelligence Hub
Generates specific, actionable recommendations for detected situations

Transforms situations from "here's what's happening" into "here's what you should do."

Each action includes:
- Clear description of what to do
- Action type (for tracking/execution)
- Priority/urgency indicator
- Optional: Parameters for automated execution

Created: 10/22/25
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json

logger = logging.getLogger(__name__)

#===============================================================================
# ACTION SUGGESTER - Generate actionable recommendations
#===============================================================================

class ActionSuggester:
    """
    Generates specific actions for situations.
    
    Takes a Situation object and returns a list of concrete actions
    the user can take to address it.
    """
    
    def __init__(self, db_manager=None):
        """
        Args:
            db_manager: Database manager (optional, for future enhancements)
        """
        self.db = db_manager
        self.suggester_name = "ActionSuggester"
    
    async def suggest_actions(self, situation) -> List[Dict[str, Any]]:
        """
        Generate suggested actions for a situation.
        
        Returns a list of action dictionaries, each containing:
        - action_type: Type of action (draft_email, create_reminder, etc.)
        - description: Human-readable description
        - priority: How important this action is (1-3, 1=most important)
        - parameters: Optional dict of parameters for execution
        
        Args:
            situation: Situation object (from situation_detector.py)
            
        Returns:
            List of action dictionaries
        """
        situation_type = situation.situation_type
        context = situation.situation_context
        
        # Route to appropriate action generator based on situation type
        if situation_type == 'post_meeting_action_required':
            return self._suggest_meeting_actions(context)
        
        elif situation_type == 'deadline_approaching_prep_needed':
            return self._suggest_deadline_actions(context)
        
        elif situation_type == 'trend_content_opportunity':
            return self._suggest_trend_actions(context)
        
        elif situation_type in ['email_priority_meeting_context', 'email_meeting_followup']:
            return self._suggest_email_actions(context, situation_type)
        
        elif situation_type == 'conversation_trend_alignment':
            return self._suggest_alignment_actions(context)
        
        elif situation_type in ['weather_impact_calendar', 'weather_health_impact', 'weather_emergency_alert']:
            return self._suggest_weather_actions(context, situation_type)
        
        else:
            # Unknown situation type - return generic action
            return [{
                'action_type': 'review',
                'description': 'Review this situation and decide on next steps',
                'priority': 2,
                'parameters': {}
            }]
    
    #===========================================================================
    # ACTION GENERATORS - One for each situation type
    #===========================================================================
    
    def _suggest_meeting_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest actions for post-meeting situations with action items.
        
        Actions:
        - Create calendar reminders for action items
        - Draft follow-up email
        - Surface relevant knowledge
        - Check for related trends
        """
        actions = []
        
        meeting_title = context.get('meeting_title', 'Meeting')
        action_items = context.get('action_items', [])
        has_next_meeting = 'next_meeting' in context
        
        # Action 1: Create calendar reminders for action items
        if action_items:
            overdue_items = [item for item in action_items if item.get('overdue', False)]
            
            if overdue_items:
                actions.append({
                    'action_type': 'create_reminders',
                    'description': f"⚠️ Create urgent reminders for {len(overdue_items)} OVERDUE action items",
                    'priority': 1,
                    'parameters': {
                        'action_items': action_items,
                        'meeting_title': meeting_title,
                        'urgent': True
                    }
                })
            else:
                actions.append({
                    'action_type': 'create_reminders',
                    'description': f"Create calendar reminders for {len(action_items)} action items",
                    'priority': 1,
                    'parameters': {
                        'action_items': action_items,
                        'meeting_title': meeting_title,
                        'urgent': False
                    }
                })
        
        # Action 2: Draft follow-up email (if next meeting exists)
        if has_next_meeting:
            next_meeting = context['next_meeting']
            actions.append({
                'action_type': 'draft_email',
                'description': f"Draft follow-up email before next meeting ({next_meeting['title']})",
                'priority': 2,
                'parameters': {
                    'meeting_title': meeting_title,
                    'action_items': action_items,
                    'next_meeting': next_meeting
                }
            })
        
        # Action 3: Review meeting notes/transcript
        if context.get('has_summary') or context.get('has_transcript'):
            actions.append({
                'action_type': 'review_notes',
                'description': f"Review meeting summary/transcript for {meeting_title}",
                'priority': 2,
                'parameters': {
                    'meeting_id': context.get('meeting_id'),
                    'meeting_title': meeting_title
                }
            })
        
        # Action 4: Prioritize action items
        if len(action_items) >= 3:
            actions.append({
                'action_type': 'prioritize_tasks',
                'description': f"Prioritize and schedule {len(action_items)} action items by urgency",
                'priority': 2,
                'parameters': {
                    'action_items': action_items
                }
            })
        
        return actions
    
    def _suggest_deadline_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest actions for approaching deadlines that need prep.
        
        Actions:
        - Block prep time on calendar
        - Review materials
        - Complete related action items
        - Create checklist
        """
        actions = []
        
        event_title = context.get('event_title', 'Event')
        hours_until = context.get('hours_until', 48)
        prep_required = context.get('prep_required', False)
        suggested_prep_hours = context.get('suggested_prep_hours', 1)
        related_actions = context.get('related_action_items', [])
        
        # Action 1: Block prep time on calendar (if prep needed)
        if prep_required:
            actions.append({
                'action_type': 'block_prep_time',
                'description': f"Block {suggested_prep_hours}h prep time before {event_title}",
                'priority': 1,
                'parameters': {
                    'event_title': event_title,
                    'prep_hours': suggested_prep_hours,
                    'event_time': context.get('event_time'),
                    'prep_reason': context.get('prep_reason')
                }
            })
        
        # Action 2: Complete related action items first
        if related_actions:
            actions.append({
                'action_type': 'complete_actions',
                'description': f"Complete {len(related_actions)} action items before {event_title}",
                'priority': 1,
                'parameters': {
                    'action_items': related_actions,
                    'event_title': event_title
                }
            })
        
        # Action 3: Review materials (if it's a presentation/demo/pitch)
        prep_reason = context.get('prep_reason', '').lower()
        if any(keyword in prep_reason for keyword in ['presentation', 'demo', 'pitch', 'review']):
            actions.append({
                'action_type': 'review_materials',
                'description': f"Review and practice materials for {event_title}",
                'priority': 1 if hours_until < 12 else 2,
                'parameters': {
                    'event_title': event_title,
                    'prep_type': prep_reason
                }
            })
        
        # Action 4: Create event checklist
        if hours_until < 24:
            actions.append({
                'action_type': 'create_checklist',
                'description': f"Create pre-event checklist for {event_title}",
                'priority': 2,
                'parameters': {
                    'event_title': event_title,
                    'hours_until': hours_until
                }
            })
        
        return actions
    
    def _suggest_trend_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest actions for trend content opportunities.
        
        Actions:
        - Generate Bluesky post draft
        - Generate blog outline
        - Surface related conversations
        - Surface related knowledge
        """
        actions = []
        
        keyword = context.get('keyword', 'Topic')
        business_area = context.get('business_area', 'general')
        suggested_account = context.get('suggested_account', 'syntaxprime')
        trend_score = context.get('trend_score', 0)
        discussed_recently = context.get('discussed_recently', False)
        knowledge_count = context.get('knowledge_count', 0)
        
        # Action 1: Generate Bluesky post (primary action)
        actions.append({
            'action_type': 'draft_bluesky_post',
            'description': f"Generate Bluesky post about '{keyword}' for @{suggested_account}",
            'priority': 1,
            'parameters': {
                'keyword': keyword,
                'business_area': business_area,
                'account': suggested_account,
                'trend_score': trend_score,
                'has_knowledge': knowledge_count > 0,
                'has_discussion': discussed_recently
            }
        })
        
        # Action 2: Generate blog outline (if high score or has knowledge)
        if trend_score >= 70 or knowledge_count >= 2:
            actions.append({
                'action_type': 'draft_blog_outline',
                'description': f"Generate blog outline about '{keyword}'",
                'priority': 2,
                'parameters': {
                    'keyword': keyword,
                    'business_area': business_area,
                    'trend_score': trend_score
                }
            })
        
        # Action 3: Review past conversations (if discussed recently)
        if discussed_recently and 'past_discussions' in context:
            discussions = context['past_discussions']
            actions.append({
                'action_type': 'review_conversations',
                'description': f"Review {len(discussions)} past conversations about {keyword}",
                'priority': 2,
                'parameters': {
                    'keyword': keyword,
                    'discussions': discussions
                }
            })
        
        # Action 4: Review knowledge entries (if available)
        if knowledge_count > 0:
            actions.append({
                'action_type': 'review_knowledge',
                'description': f"Review {knowledge_count} knowledge entries about {keyword}",
                'priority': 3,
                'parameters': {
                    'keyword': keyword,
                    'knowledge_entries': context.get('related_knowledge', [])
                }
            })
        
        return actions
    
    
    def _suggest_email_actions(
        self, 
        context: Dict[str, Any],
        situation_type: str
    ) -> List[Dict[str, Any]]:
        """
        Suggest actions for email-related situations.
        
        Actions depend on whether it's pre-meeting or post-meeting:
        - Pre-meeting: Review email before meeting
        - Post-meeting: Respond to follow-up email
        """
        actions = []
        
        sender_name = context.get('sender_name', 'Sender')
        subject = context.get('subject', 'Email')
        requires_response = context.get('requires_response', False)
        
        if situation_type == 'email_priority_meeting_context':
            # Email relates to upcoming meeting
            event_title = context.get('event_title', 'Meeting')
            hours_until = context.get('hours_until_event', 24)
            
            # Action 1: Review email before meeting
            actions.append({
                'action_type': 'review_email',
                'description': f"Review email from {sender_name} before {event_title}",
                'priority': 1,
                'parameters': {
                    'email_id': context.get('email_id'),
                    'sender_name': sender_name,
                    'subject': subject,
                    'event_title': event_title,
                    'hours_until': hours_until
                }
            })
            
            # Action 2: Prepare talking points for meeting
            if hours_until < 24:
                actions.append({
                    'action_type': 'prepare_talking_points',
                    'description': f"Prepare talking points for {event_title} based on email",
                    'priority': 1 if hours_until < 6 else 2,
                    'parameters': {
                        'email_subject': subject,
                        'event_title': event_title
                    }
                })
            
            # Action 3: Respond to email if response needed
            if requires_response:
                actions.append({
                    'action_type': 'draft_email_response',
                    'description': f"Draft response to {sender_name}",
                    'priority': 2,
                    'parameters': {
                        'email_id': context.get('email_id'),
                        'sender_name': sender_name,
                        'subject': subject
                    }
                })
        
        else:  # email_meeting_followup
            # Email is follow-up to past meeting
            meeting_title = context.get('meeting_title', 'Meeting')
            
            # Action 1: Review meeting notes/summary
            actions.append({
                'action_type': 'review_notes',
                'description': f"Review notes from {meeting_title} to respond accurately",
                'priority': 1,
                'parameters': {
                    'meeting_id': context.get('meeting_id'),
                    'meeting_title': meeting_title
                }
            })
            
            # Action 2: Draft response email
            actions.append({
                'action_type': 'draft_email_response',
                'description': f"Draft response to {sender_name}'s follow-up",
                'priority': 1,
                'parameters': {
                    'email_id': context.get('email_id'),
                    'sender_name': sender_name,
                    'subject': subject,
                    'meeting_context': meeting_title
                }
            })
            
            # Action 3: Check for action items from meeting
            actions.append({
                'action_type': 'check_action_items',
                'description': f"Verify action items from {meeting_title} before responding",
                'priority': 2,
                'parameters': {
                    'meeting_id': context.get('meeting_id'),
                    'meeting_title': meeting_title
                }
            })
        
        return actions
    
    
    def _suggest_alignment_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest actions for conversation-trend alignment situations.
        
        Actions:
        - Create content (post/blog)
        - Review discussions
        - Document insights
        """
        actions = []
        
        conversation_topic = context.get('conversation_topic', 'Topic')
        trend_keyword = context.get('trend_keyword', 'Trend')
        knowledge_available = context.get('knowledge_available', False)
        business_area = context.get('business_area', 'general')
        
        # Action 1: Create content about this aligned topic
        actions.append({
            'action_type': 'draft_bluesky_post',
            'description': f"Create post about {conversation_topic} (trending as '{trend_keyword}')",
            'priority': 1,
            'parameters': {
                'conversation_topic': conversation_topic,
                'trend_keyword': trend_keyword,
                'business_area': business_area,
                'has_knowledge': knowledge_available
            }
        })
        
        # Action 2: Review past conversations for insights
        if 'thread_id' in context:
            actions.append({
                'action_type': 'review_conversations',
                'description': f"Review your discussions about {conversation_topic}",
                'priority': 2,
                'parameters': {
                    'thread_id': context.get('thread_id'),
                    'topic': conversation_topic
                }
            })
        
        # Action 3: Create knowledge entry (if gap exists)
        if not knowledge_available:
            actions.append({
                'action_type': 'create_knowledge_entry',
                'description': f"Document your insights about {conversation_topic}",
                'priority': 3,
                'parameters': {
                    'topic': conversation_topic,
                    'trend_keyword': trend_keyword,
                    'suggestion': context.get('knowledge_gap_suggestion')
                }
            })
        else:
            # Review existing knowledge
            knowledge_count = context.get('knowledge_count', 0)
            actions.append({
                'action_type': 'review_knowledge',
                'description': f"Review {knowledge_count} knowledge entries about {conversation_topic}",
                'priority': 3,
                'parameters': {
                    'topic': conversation_topic,
                    'knowledge_entries': context.get('knowledge_entries', [])
                }
            })
        
        return actions
    
    
    def _suggest_weather_actions(
        self,
        context: Dict[str, Any],
        situation_type: str
    ) -> List[Dict[str, Any]]:
        """
        Suggest actions for weather-related situations.
        
        Actions depend on weather condition:
        - UV alert: Reschedule outdoor events, prepare protection
        - Headache risk: Take preventive measures, block rest time
        - Severe weather: Reschedule events, stay safe
        """
        actions = []
        
        weather_condition = context.get('weather_condition', 'unknown')
        severity = context.get('severity', 'moderate')
        
        if weather_condition == 'high_uv_index':
            # UV index alert
            uv_index = context.get('uv_index', 0)
            affected_events = context.get('affected_events', [])
            
            # Action 1: Reschedule outdoor events (if any)
            if affected_events:
                actions.append({
                    'action_type': 'reschedule_events',
                    'description': f"⚠️ Reschedule {len(affected_events)} outdoor events (UV {uv_index} - dangerous for sun allergy)",
                    'priority': 1,
                    'parameters': {
                        'uv_index': uv_index,
                        'affected_events': affected_events,
                        'reason': 'high_uv_sun_allergy'
                    }
                })
            
            # Action 2: Prepare sun protection (if events can't be moved)
            actions.append({
                'action_type': 'prepare_protection',
                'description': f"Prepare maximum sun protection (UV {uv_index})",
                'priority': 1 if not affected_events else 2,
                'parameters': {
                    'uv_index': uv_index,
                    'protection_level': 'maximum',
                    'items': ['SPF 50+ sunscreen', 'hat', 'long sleeves', 'sunglasses', 'seek shade']
                }
            })
            
            # Action 3: Set UV reminder for tomorrow
            actions.append({
                'action_type': 'set_reminder',
                'description': "Set reminder to check tomorrow's UV forecast",
                'priority': 3,
                'parameters': {
                    'reminder_type': 'uv_check',
                    'time': 'morning'
                }
            })
        
        elif weather_condition == 'high_headache_risk':
            # Headache risk alert
            risk_level = context.get('risk_level', 'high')
            calendar_status = context.get('calendar_status', 'light')
            event_count = context.get('event_count', 0)
            
            # Action 1: Take preventive medication
            actions.append({
                'action_type': 'take_preventive_action',
                'description': f"⚠️ Take preventive headache medication ({risk_level} risk)",
                'priority': 1,
                'parameters': {
                    'risk_level': risk_level,
                    'risk_factors': context.get('risk_factors', []),
                    'actions': ['Take preventive medication', 'Stay hydrated', 'Avoid bright screens']
                }
            })
            
            # Action 2: Block rest time (if busy day)
            if calendar_status == 'busy' and event_count >= 3:
                actions.append({
                    'action_type': 'block_rest_time',
                    'description': f"Block 30-60min rest time between meetings ({event_count} meetings today)",
                    'priority': 1,
                    'parameters': {
                        'duration_minutes': 30,
                        'reason': 'headache_risk_prevention',
                        'event_count': event_count
                    }
                })
            
            # Action 3: Adjust environment
            actions.append({
                'action_type': 'adjust_environment',
                'description': "Adjust workspace for headache prevention",
                'priority': 2,
                'parameters': {
                    'adjustments': ['Dim lights', 'Reduce screen brightness', 'Close blinds', 'Minimize noise']
                }
            })
        
        elif weather_condition == 'severe_weather_alert':
            # Severe weather emergency
            alert_description = context.get('alert_description', 'Severe weather')
            affected_events = context.get('affected_events', [])
            
            # Action 1: Reschedule ALL events (safety priority)
            if affected_events:
                actions.append({
                    'action_type': 'reschedule_events',
                    'description': f"🚨 URGENT: Reschedule {len(affected_events)} events for SAFETY ({alert_description})",
                    'priority': 1,
                    'parameters': {
                        'affected_events': affected_events,
                        'reason': 'severe_weather_safety',
                        'alert': alert_description,
                        'urgent': True
                    }
                })
            
            # Action 2: Stay indoors notification
            actions.append({
                'action_type': 'safety_alert',
                'description': f"🚨 Stay indoors and monitor weather: {alert_description}",
                'priority': 1,
                'parameters': {
                    'alert_description': alert_description,
                    'safety_level': 'critical'
                }
            })
            
            # Action 3: Notify affected parties
            if affected_events:
                actions.append({
                    'action_type': 'notify_parties',
                    'description': f"Notify attendees about rescheduled events",
                    'priority': 2,
                    'parameters': {
                        'affected_events': affected_events,
                        'reason': alert_description
                    }
                })
        
        return actions
    
    
    #===========================================================================
    # TELEGRAM NOTIFICATION FORMATTING
    #===========================================================================
    
    async def format_telegram_notification(
        self,
        situation,
        actions: List[Dict[str, Any]]
    ) -> Tuple[str, List[List[str]]]:
        """
        Format a situation and its actions into a Telegram notification.
        
        Returns a tuple of (message_text, button_layout) ready for Telegram API.
        
        Args:
            situation: Situation object
            actions: List of action dictionaries from suggest_actions()
            
        Returns:
            Tuple of (message_text, buttons) where buttons is list of button rows
        """
        # Friendly situation type names with emojis
        situation_names = {
            'post_meeting_action_required': '📋 Meeting Action Items',
            'deadline_approaching_prep_needed': '📅 Deadline Approaching',
            'trend_content_opportunity': '📈 Content Opportunity',
            'email_priority_meeting_context': '📧 Important Email + Meeting',
            'email_meeting_followup': '📧 Meeting Follow-up',
            'conversation_trend_alignment': '💡 Topic Alignment',
            'weather_impact_calendar': '☀️ Weather Alert',
            'weather_health_impact': '⚠️ Health Alert',
            'weather_emergency_alert': '🚨 WEATHER EMERGENCY'
        }
        
        situation_name = situation_names.get(
            situation.situation_type,
            situation.situation_type.replace('_', ' ').title()
        )
        
        # Build message
        message = f"🧠 **{situation_name}**\n\n"
        
        # Add situation summary based on type
        message += self._format_situation_summary(situation.situation_type, situation.situation_context)
        
        message += f"\n**Confidence:** {situation.confidence_score * 100:.0f}% | **Priority:** {situation.priority_score}/10\n"
        
        # Add suggested actions
        if actions:
            message += "\n💡 **Suggested Actions:**\n"
            for i, action in enumerate(actions[:3], 1):  # Show top 3 actions
                priority_emoji = "🔴" if action['priority'] == 1 else "🟡" if action['priority'] == 2 else "🟢"
                message += f"{i}. {priority_emoji} {action['description']}\n"
        
        # Add expiry
        if situation.expires_at:
            message += f"\n⏰ Expires: {situation.expires_at.strftime('%I:%M %p %m/%d')}"
        
        # Build buttons
        buttons = []
        
        # Top row: Action buttons (up to 2 primary actions)
        action_row = []
        for i, action in enumerate(actions[:2], 1):
            callback_data = f"situation:action{i}:{situation.situation_id}"
            action_row.append([action['description'][:30], callback_data])  # Truncate to 30 chars
        
        if action_row:
            buttons.append(action_row)
        
        # Second row: Response buttons
        buttons.append([
            ["⏭️ Dismiss", f"situation:dismiss:{situation.situation_id}"],
            ["⏰ Snooze", f"situation:snooze:{situation.situation_id}"]
        ])
        
        # Third row: More info button
        buttons.append([
            ["ℹ️ More Details", f"situation:details:{situation.situation_id}"]
        ])
        
        return message, buttons
    
    
    def _format_situation_summary(self, situation_type: str, context: Dict[str, Any]) -> str:
        """
        Format a brief summary of the situation for the notification.
        
        Args:
            situation_type: Type of situation
            context: Situation context
            
        Returns:
            Formatted summary string
        """
        if situation_type == 'post_meeting_action_required':
            meeting_title = context.get('meeting_title', 'Meeting')
            action_count = context.get('action_item_count', 0)
            overdue_count = context.get('overdue_count', 0)
            
            summary = f"**{meeting_title}**\n"
            summary += f"{action_count} action items"
            if overdue_count > 0:
                summary += f" ({overdue_count} OVERDUE!)"
            
            if 'next_meeting' in context:
                summary += f"\nNext meeting: {context['next_meeting']['title']}"
            
            return summary
        
        elif situation_type == 'deadline_approaching_prep_needed':
            event_title = context.get('event_title', 'Event')
            hours_until = context.get('hours_until', 0)
            
            summary = f"**{event_title}**\n"
            summary += f"In {hours_until:.1f} hours"
            
            if context.get('prep_required'):
                summary += f"\nPrep needed: {context.get('prep_reason')}"
            
            return summary
        
        elif situation_type == 'trend_content_opportunity':
            keyword = context.get('keyword', 'Topic')
            trend_score = context.get('trend_score', 0)
            
            summary = f"**Trending: {keyword}**\n"
            summary += f"Score: {trend_score}/100"
            
            if context.get('discussed_recently'):
                summary += "\nYou've discussed this recently!"
            
            return summary
        
        elif situation_type in ['email_priority_meeting_context', 'email_meeting_followup']:
            sender = context.get('sender_name', 'Sender')
            subject = context.get('subject', 'Email')
            
            summary = f"**From: {sender}**\n"
            summary += f"Subject: {subject[:50]}"
            
            if 'event_title' in context:
                summary += f"\nRelated to: {context['event_title']}"
            
            return summary
        
        elif situation_type == 'conversation_trend_alignment':
            topic = context.get('conversation_topic', 'Topic')
            trend = context.get('trend_keyword', 'Trend')
            
            summary = f"**You discussed: {topic}**\n"
            summary += f"Now trending: {trend}"
            
            return summary
        
        elif situation_type in ['weather_impact_calendar', 'weather_health_impact']:
            condition = context.get('weather_condition', 'Weather condition')
            
            if 'uv_index' in context:
                summary = f"**UV Index: {context['uv_index']}**\n"
                summary += f"Dangerous for sun allergy!"
            elif 'risk_level' in context:
                summary = f"**Headache Risk: {context['risk_level'].upper()}**\n"
                summary += "Preventive measures recommended"
            else:
                summary = f"**{condition}**"
            
            event_count = context.get('event_count', 0)
            if event_count > 0:
                summary += f"\n{event_count} events affected"
            
            return summary
        
        elif situation_type == 'weather_emergency_alert':
            alert = context.get('alert_description', 'Severe weather')
            
            summary = f"**⚠️ {alert.upper()} ⚠️**\n"
            summary += "Stay safe indoors!"
            
            return summary
        
        else:
            return "Review situation details"