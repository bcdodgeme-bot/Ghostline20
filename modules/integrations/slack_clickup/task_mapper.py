"""
Task Mapping Business Logic
Maps Slack events to ClickUp tasks based on context and commands

Updated: Session 13 - Added singleton getter pattern
"""
import re
from typing import Dict, Optional, Tuple
from datetime import datetime

#--Section 1: Singleton Pattern
_task_mapper_instance: Optional['TaskMapper'] = None


def get_task_mapper() -> 'TaskMapper':
    """Get singleton TaskMapper instance"""
    global _task_mapper_instance
    if _task_mapper_instance is None:
        _task_mapper_instance = TaskMapper()
    return _task_mapper_instance


#--Section 2: Class Initialization & Command Patterns
class TaskMapper:
    def __init__(self):
        self.command_patterns = {
            'remind': r'(?:remind|reminder|remember)',
            'task': r'(?:task|todo|do)',
            'blog': r'(?:blog|write|article)',
            'follow_up': r'(?:follow up|followup|check back)',
        }

    #--Section 3: Slack Mention Processing
    def extract_mention_task(self, message_data: Dict) -> Optional[Dict]:
        """Extract task details from a Slack mention"""
        text = message_data.get('text', '')
        user = message_data.get('user', '')
        channel = message_data.get('channel', '')
        timestamp = message_data.get('ts', '')
        
        # Clean up the message text (remove mentions, extra spaces)
        clean_text = self._clean_message_text(text)
        
        # Extract task title (first sentence or reasonable chunk)
        title = self._extract_task_title(clean_text)
        
        # Build description with context
        description = self._build_mention_description(
            original_text=text,
            user=user,
            channel=channel,
            timestamp=timestamp
        )
        
        return {
            'title': title,
            'description': description,
            'type': 'mention',
            'source_data': message_data
        }

    #--Section 4: AI Command Processing
    def extract_command_task(self, message: str, context: str = "") -> Optional[Dict]:
        """Extract task details from an AI conversation command"""
        # Look for command patterns
        command_type = self._detect_command_type(message)
        
        # Extract the actual task content
        task_content = self._extract_command_content(message)
        
        if not task_content:
            return None
        
        title = self._extract_task_title(task_content)
        description = self._build_command_description(
            original_message=message,
            context=context,
            command_type=command_type
        )
        
        return {
            'title': title,
            'description': description,
            'type': 'command',
            'command_type': command_type
        }

    #--Section 5: Text Cleaning & Parsing Utilities
    def _clean_message_text(self, text: str) -> str:
        """Remove Slack mentions and clean up text"""
        # Remove user mentions
        text = re.sub(r'<@[A-Z0-9]+>', '', text)
        # Remove channel mentions
        text = re.sub(r'<#[A-Z0-9]+\|[^>]+>', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_task_title(self, text: str, max_length: int = 80) -> str:
        """Extract a reasonable task title from text"""
        # Take first sentence or first reasonable chunk
        sentences = text.split('.')
        title = sentences[0].strip()
        
        # If too long, truncate at word boundary
        if len(title) > max_length:
            words = title.split()
            title = ' '.join(words[:10]) + '...'
        
        return title if title else "Task from Slack"

    #--Section 6: Command Detection & Content Extraction
    def _detect_command_type(self, message: str) -> str:
        """Detect the type of command in the message"""
        message_lower = message.lower()
        
        for command, pattern in self.command_patterns.items():
            if re.search(pattern, message_lower):
                return command
        
        return 'general'
    
    def _extract_command_content(self, message: str) -> str:
        """Extract the actual task content from a command"""
        # Common command starters to remove
        prefixes = [
            r'^(?:please\s+)?(?:remind me to|remember to|task to|todo:?)\s*',
            r'^(?:can you\s+)?(?:remind|remember)\s+(?:me\s+)?(?:to\s+)?',
            r'^(?:add\s+)?(?:task:?|todo:?)\s*',
        ]
        
        content = message
        for prefix in prefixes:
            content = re.sub(prefix, '', content, flags=re.IGNORECASE).strip()
        
        return content

    #--Section 7: Description Builders
    def _build_mention_description(self, original_text: str, user: str, channel: str, timestamp: str) -> str:
        """Build detailed description for mention-based tasks"""
        dt = datetime.fromtimestamp(float(timestamp))
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        return f"""📩 **Slack Mention Task**
        
**Original Message:** {original_text}

**Context:**
- From: <@{user}>
- Channel: <#{channel}>
- Time: {formatted_time}
- Source: Slack Integration

**Action Required:** Review and respond to this mention within 3 days."""
    
    def _build_command_description(self, original_message: str, context: str, command_type: str) -> str:
        """Build detailed description for AI command tasks"""
        return f"""🤖 **AI Command Task**
        
**Command:** {original_message}

**Context:** {context if context else 'Generated from AI conversation'}

**Type:** {command_type.title()}
**Created:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Source:** AI Integration

**Note:** This task was created from an AI conversation command."""
