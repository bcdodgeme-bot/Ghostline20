# modules/integrations/fathom/meeting_processor.py
"""
Meeting Processor with Claude AI Integration
Generates intelligent summaries from meeting transcripts

Key Features:
- Generate better summaries than Fathom's native AI
- Extract action items automatically
- Identify key topics and themes
- Analyze sentiment and meeting effectiveness
- Provide strategic insights and recommendations

Uses Claude (Anthropic) for superior understanding and context
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

# ✅ FIXED: Import OpenRouter client from correct location
from ai.openrouter_client import get_openrouter_client

logger = logging.getLogger(__name__)

class MeetingProcessor:
    """
    Processes meeting transcripts using Claude AI via OpenRouter to generate insights
    """
    
    def __init__(self):
        """Initialize meeting processor with OpenRouter Claude client"""
        self.model = "anthropic/claude-3.5-sonnet"  # Best Claude model via OpenRouter
        
        logger.info("✅ Meeting processor initialized with Claude 3.5 Sonnet via OpenRouter")
    
    # ✅ FIXED: Updated to handle actual Fathom data structure
    async def generate_summary(self, recording_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive AI summary from recording data
        
        Args:
            recording_data: Complete recording data from Fathom API
                          (includes both details and transcript)
            
        Returns:
            Dict with summary, action items, topics, sentiment, etc.
        """
        try:
            # ✅ FIXED: Extract from correct structure
            # recording_data has: 'recording_id', 'details', 'transcript'
            details = recording_data.get('details', {})
            transcript_data = recording_data.get('transcript', {})
            
            # ✅ FIXED: Extract fields that actually exist in Fathom response
            title = details.get('title', 'Untitled Meeting')
            start_time = details.get('start_time', '')
            duration = details.get('duration', 0)  # Duration in seconds
            participants = details.get('attendees', [])  # 'attendees' not 'participants'
            
            # ✅ FIXED: Get transcript text directly (it's already formatted)
            transcript_text = transcript_data.get('transcript', '')
            
            if not transcript_text:
                logger.warning("⚠️ No transcript text available")
                return self._create_empty_summary()
            
            logger.info(f"🔍 Processing meeting: {title}")
            logger.info(f"   Duration: {duration // 60} minutes")
            logger.info(f"   Participants: {len(participants)}")
            logger.info(f"   Transcript: {len(transcript_text)} characters")
            
            # Generate AI summary using Claude
            summary_result = await self._generate_ai_summary(
                title=title,
                date=start_time,
                participants=participants,
                duration=duration // 60,  # Convert to minutes
                transcript=transcript_text
            )
            
            logger.info("✅ AI summary generated successfully")
            return summary_result
            
        except Exception as e:
            logger.error(f"❌ Failed to generate summary: {e}")
            return self._create_empty_summary(error=str(e))
    
    async def _generate_ai_summary(self, title: str, date: str,
                                  participants: List[Dict], duration: int,
                                  transcript: str) -> Dict[str, Any]:
        """Generate comprehensive summary using Claude AI"""
        try:
            # ✅ FIXED: Extract participant names from attendee objects
            participant_names = [p.get('name', 'Unknown') for p in participants]
            
            # Build detailed prompt for Claude
            prompt = self._build_summary_prompt(
                title, date, participant_names, duration, transcript
            )
            
            # Get OpenRouter client
            openrouter = await get_openrouter_client()
            
            # Call Claude API
            response = await openrouter.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert meeting analyst. Your job is to analyze meeting transcripts and extract actionable insights, key decisions, and important discussion points. Be thorough, accurate, and focus on what matters."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                max_tokens=4000,
                temperature=0.3  # Lower temperature for more focused analysis
            )
            
            # Extract response
            ai_text = response['choices'][0]['message']['content']
            
            # Parse structured response from Claude
            parsed_summary = self._parse_ai_response(ai_text)
            
            return parsed_summary
            
        except Exception as e:
            logger.error(f"❌ AI summary generation failed: {e}")
            raise
    
    def _build_summary_prompt(self, title: str, date: str,
                             participants: List[str], duration: int,
                             transcript: str) -> str:
        """Build detailed prompt for Claude"""
        
        # Truncate transcript if too long (Claude has 200K context, but be reasonable)
        max_transcript_length = 50000
        if len(transcript) > max_transcript_length:
            transcript = transcript[:max_transcript_length] + "\n\n[Transcript truncated for length]"
        
        prompt = f"""Analyze this meeting and provide a comprehensive summary.

**Meeting Details:**
- Title: {title}
- Date: {date}
- Duration: {duration} minutes
- Participants: {', '.join(participants) if participants else 'Not specified'}

**Full Transcript:**
{transcript}

**Please provide your analysis in the following JSON format:**

{{
  "summary": "A concise 2-3 paragraph executive summary of the meeting",
  "key_points": [
    "Most important point 1",
    "Most important point 2",
    "Most important point 3"
  ],
  "action_items": [
    {{
      "text": "Clear, actionable task description",
      "assigned_to": "Person's name or null if unassigned",
      "due_date": "YYYY-MM-DD or null if not specified",
      "priority": "high/medium/low"
    }}
  ],
  "topics": [
    {{
      "name": "Topic name",
      "importance": 1-10,
      "keywords": ["relevant", "keywords"]
    }}
  ],
  "decisions_made": [
    "Clear decision 1",
    "Clear decision 2"
  ],
  "sentiment": "positive/neutral/negative/mixed",
  "effectiveness_score": 1-10,
  "recommendations": [
    "Suggestion for improvement 1",
    "Suggestion for improvement 2"
  ]
}}

**Important Guidelines:**
1. Be specific and actionable in action items
2. Focus on decisions and outcomes, not just discussion
3. Rate effectiveness based on clarity of outcomes and productive discussion
4. Sentiment should reflect overall meeting tone and energy
5. Recommendations should be practical and implementable
6. If information is not available, use null instead of guessing

Respond ONLY with the JSON object, no other text."""

        return prompt
    
    def _parse_ai_response(self, ai_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response into structured data"""
        try:
            # Try to find JSON in the response
            start_idx = ai_text.find('{')
            end_idx = ai_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = ai_text[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                # Validate required fields
                required_fields = ['summary', 'key_points', 'action_items',
                                 'topics', 'sentiment']
                
                for field in required_fields:
                    if field not in parsed:
                        logger.warning(f"⚠️ Missing field in AI response: {field}")
                        parsed[field] = self._get_default_value(field)
                
                logger.info("✅ Successfully parsed AI response")
                return parsed
            else:
                logger.error("❌ No JSON found in AI response")
                return self._create_empty_summary()
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse AI JSON: {e}")
            logger.error(f"Response text: {ai_text[:500]}")
            return self._create_empty_summary()
    
    # ✅ REMOVED: _format_transcript() method - no longer needed
    # Fathom's transcript is already formatted as plain text
    
    def _get_default_value(self, field: str) -> Any:
        """Get default value for a missing field"""
        defaults = {
            'summary': 'Summary not available',
            'key_points': [],
            'action_items': [],
            'topics': [],
            'decisions_made': [],
            'sentiment': 'neutral',
            'effectiveness_score': 5,
            'recommendations': []
        }
        return defaults.get(field, None)
    
    def _create_empty_summary(self, error: str = None) -> Dict[str, Any]:
        """Create empty summary structure when processing fails"""
        return {
            'summary': 'Summary generation failed' if error else 'No summary available',
            'key_points': [],
            'action_items': [],
            'topics': [],
            'decisions_made': [],
            'sentiment': 'neutral',
            'effectiveness_score': 5,
            'recommendations': [],
            'error': error
        }

# Convenience functions for external use
async def process_meeting(recording_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to process a recording"""
    processor = MeetingProcessor()
    return await processor.generate_summary(recording_data)

async def extract_action_items(transcript_text: str) -> List[Dict[str, Any]]:
    """Convenience function to extract just action items from transcript"""
    processor = MeetingProcessor()
    
    # Build simplified prompt for action items only
    try:
        openrouter = await get_openrouter_client()
        
        response = await openrouter.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Extract all action items from this meeting transcript. Return as JSON array."
                },
                {
                    "role": "user",
                    "content": f"Transcript:\n{transcript_text}\n\nExtract action items as JSON array with fields: text, assigned_to, due_date, priority"
                }
            ],
            model="anthropic/claude-3.5-sonnet",
            max_tokens=1000,
            temperature=0.3
        )
        
        ai_text = response['choices'][0]['message']['content']
        
        # Parse JSON array
        start_idx = ai_text.find('[')
        end_idx = ai_text.rfind(']') + 1
        
        if start_idx != -1 and end_idx != 0:
            json_str = ai_text[start_idx:end_idx]
            return json.loads(json_str)
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Failed to extract action items: {e}")
        return []
