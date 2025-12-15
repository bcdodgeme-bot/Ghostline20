# modules/integrations/fathom/database_manager.py
"""
Fathom Database Manager
Handles all PostgreSQL operations for meeting storage and retrieval

Key Features:
- Store meeting metadata in fathom_meetings table
- Save action items in meeting_action_items table
- Track topics in meeting_topics table
- Search meetings by keywords, date, participants
- Retrieve meeting history for conversational memory
- Integration with Syntax's existing database architecture
- Bridge meeting summaries to knowledge_entries for chat accessibility

Database Tables:
- fathom_meetings: Core meeting data (title, date, participants, transcript)
- meeting_action_items: Extracted action items and tasks
- meeting_topics: Key topics and themes discussed
- knowledge_entries: Chat's searchable knowledge base (bridged to)

FIXES APPLIED (Session 6 - Fathom Review):
- Fixed _get_action_items() which had wrong variable names and tried to parse non-existent 'keywords' column
- Fixed duplicate _get_action_items() call in get_meeting_by_recording_id()
- Fixed _get_topics() to properly parse keywords JSON
- Fixed get_meeting_statistics() which couldn't unnest JSON string participants
- Added _get_topics() call to get_meeting_by_id() for consistency
- ADDED: add_meeting_to_knowledge_base() to bridge meetings into chat's knowledge system
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from ...core.database import db_manager

logger = logging.getLogger(__name__)

# Hardcoded user ID - this is a single-user personal project
DEFAULT_USER_ID = 'b7c60682-4815-4d9d-8ebe-66c6cd24eff9'


@dataclass
class MeetingRecord:
    """Container for meeting data"""
    id: str
    fathom_recording_id: int
    title: str
    meeting_date: datetime
    duration_minutes: int
    participants: List[str]
    transcript_text: str
    ai_summary: str
    key_points: List[str]
    created_at: datetime


@dataclass
class ActionItem:
    """Container for action item data"""
    id: str
    meeting_id: str
    action_text: str
    assigned_to: Optional[str]
    due_date: Optional[datetime]
    priority: str
    status: str


class FathomDatabaseManager:
    """
    Manages all database operations for Fathom meeting integration
    Integrates with Syntax Prime V2's existing database architecture
    """
    
    def __init__(self):
        self.db = db_manager
    
    # ============================================================================
    # MEETING STORAGE
    # ============================================================================
    
    async def store_meeting(self, recording_data: Dict[str, Any],
                          summary_data: Dict[str, Any]) -> str:
        """
        Store complete meeting data (details + summary + action items + topics)
        
        Args:
            recording_data: Raw recording data from Fathom API
            summary_data: AI-generated summary and insights
            
        Returns:
            Meeting ID (UUID) from database
        """
        try:
            # Extract from correct structure
            details = recording_data.get('details', {})
            transcript_data = recording_data.get('transcript', {})
            
            # Use correct field names from Fathom API
            recording_id = details.get('id')  # This is an integer
            title = details.get('title', 'Untitled Meeting')
            
            # Handle start_time properly
            start_time_str = details.get('start_time', datetime.now().isoformat())
            if isinstance(start_time_str, str):
                # Remove 'Z' and parse
                start_time_str = start_time_str.replace('Z', '+00:00')
                meeting_date = datetime.fromisoformat(start_time_str)
            else:
                meeting_date = start_time_str
            
            # Duration is in seconds, convert to minutes
            duration_seconds = details.get('duration', 0)
            duration_minutes = duration_seconds // 60
            
            # Extract participant names from attendees
            attendees = details.get('attendees', [])
            participants = [att.get('name', 'Unknown') for att in attendees]
            
            # Convert participants list to JSON string
            participants_json = json.dumps(participants) if participants else json.dumps([])
            
            # Handle transcript that comes as list of segments
            transcript_text = self._extract_transcript_text(transcript_data)
            
            # Extract summary components
            ai_summary = summary_data.get('summary', '')
            key_points = summary_data.get('key_points', [])
            sentiment = summary_data.get('sentiment', 'neutral')
            
            # Convert key_points list to JSON string
            key_points_json = json.dumps(key_points) if key_points else json.dumps([])
            
            # Use recording_id (BIGINT) instead of meeting_id
            query = '''
                INSERT INTO fathom_meetings 
                (recording_id, title, meeting_date, duration_minutes,
                 participants, transcript_text, ai_summary, key_points,
                 sentiment, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
                ON CONFLICT (recording_id) 
                DO UPDATE SET
                    title = EXCLUDED.title,
                    ai_summary = EXCLUDED.ai_summary,
                    key_points = EXCLUDED.key_points,
                    updated_at = NOW()
                RETURNING id
            '''
            
            result = await self.db.fetch_one(
                query,
                recording_id,
                title,
                meeting_date,
                duration_minutes,
                participants_json,
                transcript_text,
                ai_summary,
                key_points_json,
                sentiment
            )
            
            db_meeting_id = str(result['id'])
            
            logger.info(f"✅ Stored meeting: {title} (ID: {db_meeting_id})")
            
            # Store action items
            action_items = summary_data.get('action_items', [])
            if action_items:
                await self._store_action_items(db_meeting_id, action_items)
            
            # Store topics
            topics = summary_data.get('topics', [])
            if topics:
                await self._store_topics(db_meeting_id, topics)
            
            # Bridge to knowledge_entries for chat accessibility
            await self._add_meeting_to_knowledge_base(
                meeting_id=db_meeting_id,
                title=title,
                meeting_date=meeting_date,
                participants=participants,
                summary_data=summary_data
            )
            
            return db_meeting_id
            
        except Exception as e:
            logger.error(f"❌ Failed to store meeting: {e}")
            raise
    
    # ============================================================================
    # KNOWLEDGE BASE BRIDGE
    # ============================================================================
    
    async def _add_meeting_to_knowledge_base(
        self,
        meeting_id: str,
        title: str,
        meeting_date: datetime,
        participants: List[str],
        summary_data: Dict[str, Any]
    ) -> None:
        """
        Bridge meeting data into knowledge_entries for chat accessibility.
        
        This allows the main chat AI to find and reference meeting content
        through its normal knowledge retrieval process.
        
        Args:
            meeting_id: Database UUID of the stored meeting
            title: Meeting title
            meeting_date: When the meeting occurred
            participants: List of participant names
            summary_data: AI-generated summary and insights
        """
        try:
            # Get or create knowledge source for Fathom meetings
            source_id = await self._ensure_fathom_knowledge_source()
            
            # Format meeting date nicely
            date_str = meeting_date.strftime('%Y-%m-%d %H:%M') if meeting_date else 'Unknown date'
            
            # Build action items text
            action_items = summary_data.get('action_items', [])
            action_items_text = ""
            if action_items:
                action_lines = []
                for item in action_items:
                    if isinstance(item, dict):
                        text = item.get('text', str(item))
                        assigned = item.get('assigned_to')
                        priority = item.get('priority', 'medium')
                        if assigned:
                            action_lines.append(f"• [{priority.upper()}] {text} (assigned to: {assigned})")
                        else:
                            action_lines.append(f"• [{priority.upper()}] {text}")
                    else:
                        action_lines.append(f"• {item}")
                action_items_text = "\n".join(action_lines)
            
            # Build topics text
            topics = summary_data.get('topics', [])
            topics_text = ", ".join(t.get('name', str(t)) if isinstance(t, dict) else str(t) for t in topics)
            
            # Build key points text
            key_points = summary_data.get('key_points', [])
            key_points_text = "\n".join(f"• {point}" for point in key_points)
            
            # Build decisions text
            decisions = summary_data.get('decisions_made', [])
            decisions_text = "\n".join(f"• {decision}" for decision in decisions) if decisions else ""
            
            # Build comprehensive, searchable content
            content_parts = [
                f"MEETING RECORDING: {title}",
                f"DATE: {date_str}",
                f"PARTICIPANTS: {', '.join(participants) if participants else 'Not specified'}",
                "",
                "=" * 50,
                "",
                "SUMMARY:",
                summary_data.get('summary', 'No summary available'),
                ""
            ]
            
            if key_points_text:
                content_parts.extend([
                    "KEY POINTS:",
                    key_points_text,
                    ""
                ])
            
            if decisions_text:
                content_parts.extend([
                    "DECISIONS MADE:",
                    decisions_text,
                    ""
                ])
            
            if action_items_text:
                content_parts.extend([
                    "ACTION ITEMS:",
                    action_items_text,
                    ""
                ])
            
            if topics_text:
                content_parts.extend([
                    "TOPICS DISCUSSED:",
                    topics_text,
                    ""
                ])
            
            # Add metadata footer for deep-dive queries
            content_parts.extend([
                "",
                "=" * 50,
                f"[Meeting ID: {meeting_id} - Full transcript available via Fathom integration]"
            ])
            
            content = "\n".join(content_parts)
            
            # Extract topic names for key_topics JSON
            key_topics = [t.get('name', str(t)) if isinstance(t, dict) else str(t) for t in topics]
            
            # Check if we already have a knowledge entry for this meeting
            existing = await self.db.fetch_one(
                '''
                SELECT id FROM knowledge_entries 
                WHERE content_type = 'meeting_summary' 
                AND title = $1 
                AND user_id = $2
                ''',
                title,
                DEFAULT_USER_ID
            )
            
            if existing:
                # Update existing entry
                await self.db.execute(
                    '''
                    UPDATE knowledge_entries
                    SET content = $1, summary = $2, key_topics = $3, updated_at = NOW()
                    WHERE id = $4
                    ''',
                    content,
                    summary_data.get('summary', ''),
                    json.dumps(key_topics),
                    existing['id']
                )
                logger.info(f"✅ Updated knowledge entry for meeting: {title}")
            else:
                # Insert new entry
                await self.db.execute(
                    '''
                    INSERT INTO knowledge_entries 
                    (source_id, title, content, content_type, summary, key_topics, user_id, created_at, updated_at)
                    VALUES ($1, $2, $3, 'meeting_summary', $4, $5, $6, NOW(), NOW())
                    ''',
                    source_id,
                    title,
                    content,
                    summary_data.get('summary', ''),
                    json.dumps(key_topics),
                    DEFAULT_USER_ID
                )
                logger.info(f"✅ Added knowledge entry for meeting: {title}")
            
        except Exception as e:
            # Don't fail the whole meeting storage if knowledge bridge fails
            logger.error(f"⚠️ Failed to bridge meeting to knowledge base: {e}")
            logger.info("   Meeting still stored successfully in fathom_meetings")
    
    async def _ensure_fathom_knowledge_source(self) -> int:
        """
        Ensure a knowledge_source entry exists for Fathom meetings.
        Creates one if it doesn't exist.
        
        Returns:
            source_id (int) of the fathom_meetings knowledge source
        """
        try:
            # Check if source exists
            result = await self.db.fetch_one(
                "SELECT id FROM knowledge_sources WHERE name = 'fathom_meetings'"
            )
            
            if result:
                return result['id']
            
            # Create new source
            result = await self.db.fetch_one(
                '''
                INSERT INTO knowledge_sources (name, source_type, description, is_active)
                VALUES ('fathom_meetings', 'integration', 'Meeting recordings and transcripts from Fathom with AI summaries', true)
                RETURNING id
                '''
            )
            
            logger.info("✅ Created knowledge_source for fathom_meetings")
            return result['id']
            
        except Exception as e:
            logger.error(f"❌ Failed to ensure knowledge source: {e}")
            # Return a fallback - source_id can be NULL
            return None
    
    # ============================================================================
    # TRANSCRIPT EXTRACTION
    # ============================================================================
    
    def _extract_transcript_text(self, transcript_data: Any) -> str:
        """
        Extract plain text transcript from various formats Fathom might send.
        
        Fathom can send transcript as:
        1. Plain string: "This is the transcript..."
        2. Dict with 'transcript' key containing string
        3. Dict with 'transcript' key containing list of segments
        4. List of segments directly
        
        Args:
            transcript_data: Raw transcript data from Fathom webhook
            
        Returns:
            Plain text string transcript
        """
        try:
            # Case 1: Already a string
            if isinstance(transcript_data, str):
                return transcript_data
            
            # Case 2 & 3: Dict with 'transcript' key
            if isinstance(transcript_data, dict) and 'transcript' in transcript_data:
                transcript_value = transcript_data['transcript']
                
                # If it's a string, return it
                if isinstance(transcript_value, str):
                    return transcript_value
                
                # If it's a list of segments, format it
                if isinstance(transcript_value, list):
                    return self._format_transcript_from_segments(transcript_value)
            
            # Case 4: List of segments directly
            if isinstance(transcript_data, list):
                return self._format_transcript_from_segments(transcript_data)
            
            # Fallback
            logger.warning(f"⚠️ Unexpected transcript format: {type(transcript_data)}")
            return str(transcript_data) if transcript_data else ""
            
        except Exception as e:
            logger.error(f"❌ Error extracting transcript: {e}", exc_info=True)
            return ""
    
    def _format_transcript_from_segments(self, segments: List[Dict]) -> str:
        """
        Format a list of transcript segments into readable text.
        Each segment has: {'speaker': {'display_name': 'Name'}, 'text': '...', 'start': 0}
        
        Args:
            segments: List of transcript segment dicts
            
        Returns:
            Formatted transcript string with speaker names
        """
        try:
            transcript_lines = []
            
            for segment in segments:
                # Extract speaker name
                speaker_name = "Unknown"
                if 'speaker' in segment and segment['speaker']:
                    speaker = segment['speaker']
                    if isinstance(speaker, dict):
                        speaker_name = speaker.get('display_name') or speaker.get('name', 'Unknown')
                    elif isinstance(speaker, str):
                        speaker_name = speaker
                
                # Extract text
                text = segment.get('text', '').strip()
                
                if text:
                    transcript_lines.append(f"{speaker_name}: {text}")
            
            return "\n\n".join(transcript_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formatting transcript segments: {e}", exc_info=True)
            # Fallback: concatenate text without speaker names
            try:
                return "\n\n".join(s.get('text', '').strip() for s in segments if s.get('text'))
            except:
                return ""
    
    # ============================================================================
    # ACTION ITEMS & TOPICS STORAGE
    # ============================================================================
    
    async def _store_action_items(self, meeting_id: str,
                                 action_items: List[Dict[str, Any]]) -> None:
        """Store action items extracted from meeting"""
        try:
            query = '''
                INSERT INTO meeting_action_items
                (meeting_id, action_text, assigned_to, due_date, priority, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            '''
            
            for item in action_items:
                await self.db.execute(
                    query,
                    meeting_id,
                    item.get('text', ''),
                    item.get('assigned_to'),
                    item.get('due_date'),
                    item.get('priority', 'medium'),
                    'pending'
                )
            
            logger.info(f"✅ Stored {len(action_items)} action items")
            
        except Exception as e:
            logger.error(f"❌ Failed to store action items: {e}")
    
    async def _store_topics(self, meeting_id: str,
                          topics: List[Dict[str, Any]]) -> None:
        """Store topics discussed in meeting"""
        try:
            query = '''
                INSERT INTO meeting_topics
                (meeting_id, topic_name, importance_score, keywords)
                VALUES ($1, $2, $3, $4)
            '''
            
            for topic in topics:
                # Convert keywords list to JSON string
                keywords = topic.get('keywords', [])
                keywords_json = json.dumps(keywords) if keywords else json.dumps([])
                
                await self.db.execute(
                    query,
                    meeting_id,
                    topic.get('name', ''),
                    topic.get('importance', 5),
                    keywords_json
                )
            
            logger.info(f"✅ Stored {len(topics)} topics")
            
        except Exception as e:
            logger.error(f"❌ Failed to store topics: {e}")
    
    # ============================================================================
    # MEETING RETRIEVAL
    # ============================================================================
    
    async def get_meeting_by_id(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get complete meeting data by database ID"""
        try:
            query = '''
                SELECT * FROM fathom_meetings
                WHERE id = $1
            '''
            
            result = await self.db.fetch_one(query, meeting_id)
            
            if not result:
                return None
            
            meeting = dict(result)
            
            # Parse JSON strings back to lists
            if meeting.get('participants') and isinstance(meeting['participants'], str):
                try:
                    meeting['participants'] = json.loads(meeting['participants'])
                except:
                    meeting['participants'] = []
            
            if meeting.get('key_points') and isinstance(meeting['key_points'], str):
                try:
                    meeting['key_points'] = json.loads(meeting['key_points'])
                except:
                    meeting['key_points'] = []
            
            # Get action items
            meeting['action_items'] = await self._get_action_items(meeting_id)
            
            # Get topics
            meeting['topics'] = await self._get_topics(meeting_id)
            
            return meeting
            
        except Exception as e:
            logger.error(f"❌ Failed to get meeting: {e}")
            return None
    
    async def get_meeting_by_recording_id(self, recording_id: int) -> Optional[Dict[str, Any]]:
        """Get complete meeting data by Fathom recording_id"""
        try:
            query = '''
                SELECT * FROM fathom_meetings
                WHERE recording_id = $1
            '''
            
            result = await self.db.fetch_one(query, recording_id)
            
            if not result:
                return None
            
            meeting = dict(result)
            meeting_id = str(meeting['id'])
            
            # Parse JSON strings back to lists
            if meeting.get('participants') and isinstance(meeting['participants'], str):
                try:
                    meeting['participants'] = json.loads(meeting['participants'])
                except:
                    meeting['participants'] = []
            
            if meeting.get('key_points') and isinstance(meeting['key_points'], str):
                try:
                    meeting['key_points'] = json.loads(meeting['key_points'])
                except:
                    meeting['key_points'] = []
            
            # Get action items
            meeting['action_items'] = await self._get_action_items(meeting_id)
            
            # Get topics
            meeting['topics'] = await self._get_topics(meeting_id)
            
            return meeting
            
        except Exception as e:
            logger.error(f"❌ Failed to get meeting by recording_id: {e}")
            return None
    
    async def _get_action_items(self, meeting_id: str) -> List[Dict[str, Any]]:
        """
        Get action items for a meeting
        
        FIXED: Original code had wrong variable names ('topics' instead of 'items')
        and tried to parse 'keywords' which doesn't exist on meeting_action_items table.
        
        meeting_action_items columns: id, meeting_id, action_text, assigned_to, 
        due_date, priority, status, created_at, updated_at, completed_at
        """
        try:
            query = '''
                SELECT * FROM meeting_action_items
                WHERE meeting_id = $1
                ORDER BY priority DESC, created_at
            '''
            
            results = await self.db.fetch_all(query, meeting_id)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Failed to get action items: {e}")
            return []
    
    async def _get_topics(self, meeting_id: str) -> List[Dict[str, Any]]:
        """
        Get topics for a meeting
        
        FIXED: Added JSON parsing for keywords column
        
        meeting_topics columns: id, meeting_id, topic_name, importance_score, 
        keywords (jsonb), created_at
        """
        try:
            query = '''
                SELECT * FROM meeting_topics
                WHERE meeting_id = $1
                ORDER BY importance_score DESC
            '''
            
            results = await self.db.fetch_all(query, meeting_id)
            
            # Parse keywords JSON back to list
            topics = []
            for row in results:
                topic = dict(row)
                if topic.get('keywords') and isinstance(topic['keywords'], str):
                    try:
                        topic['keywords'] = json.loads(topic['keywords'])
                    except:
                        topic['keywords'] = []
                topics.append(topic)
            
            return topics
            
        except Exception as e:
            logger.error(f"❌ Failed to get topics: {e}")
            return []
    
    async def get_recent_meetings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent meetings ordered by date"""
        try:
            query = '''
                SELECT id, recording_id, title, meeting_date,
                       duration_minutes, participants, ai_summary,
                       key_points, created_at
                FROM fathom_meetings
                ORDER BY meeting_date DESC
                LIMIT $1
            '''
            
            results = await self.db.fetch_all(query, limit)
            
            # Parse JSON strings back to lists
            meetings = []
            for row in results:
                meeting = dict(row)
                if meeting.get('participants') and isinstance(meeting['participants'], str):
                    try:
                        meeting['participants'] = json.loads(meeting['participants'])
                    except:
                        meeting['participants'] = []
                if meeting.get('key_points') and isinstance(meeting['key_points'], str):
                    try:
                        meeting['key_points'] = json.loads(meeting['key_points'])
                    except:
                        meeting['key_points'] = []
                meetings.append(meeting)
            
            return meetings
            
        except Exception as e:
            logger.error(f"❌ Failed to get recent meetings: {e}")
            return []
    
    async def search_meetings(self, query_text: str,
                            limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search meetings by keywords in title, summary, or transcript
        Uses PostgreSQL full-text search for better results
        """
        try:
            query = '''
                SELECT id, recording_id, title, meeting_date,
                       duration_minutes, participants, ai_summary,
                       key_points, created_at,
                       ts_rank(to_tsvector('english', 
                           COALESCE(title, '') || ' ' || 
                           COALESCE(ai_summary, '') || ' ' ||
                           COALESCE(transcript_text, '')
                       ), plainto_tsquery('english', $1)) as rank
                FROM fathom_meetings
                WHERE to_tsvector('english', 
                    COALESCE(title, '') || ' ' || 
                    COALESCE(ai_summary, '') || ' ' ||
                    COALESCE(transcript_text, '')
                ) @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC, meeting_date DESC
                LIMIT $2
            '''
            
            results = await self.db.fetch_all(query, query_text, limit)
            
            # Parse JSON strings back to lists
            meetings = []
            for row in results:
                meeting = dict(row)
                if meeting.get('participants') and isinstance(meeting['participants'], str):
                    try:
                        meeting['participants'] = json.loads(meeting['participants'])
                    except:
                        meeting['participants'] = []
                if meeting.get('key_points') and isinstance(meeting['key_points'], str):
                    try:
                        meeting['key_points'] = json.loads(meeting['key_points'])
                    except:
                        meeting['key_points'] = []
                meetings.append(meeting)
            
            return meetings
            
        except Exception as e:
            logger.error(f"❌ Failed to search meetings: {e}")
            return []
    
    async def get_meetings_by_date_range(self, start_date: datetime,
                                        end_date: datetime) -> List[Dict[str, Any]]:
        """Get meetings within a date range"""
        try:
            query = '''
                SELECT id, recording_id, title, meeting_date,
                       duration_minutes, participants, ai_summary,
                       key_points, created_at
                FROM fathom_meetings
                WHERE meeting_date BETWEEN $1 AND $2
                ORDER BY meeting_date DESC
            '''
            
            results = await self.db.fetch_all(query, start_date, end_date)
            
            # Parse JSON strings back to lists
            meetings = []
            for row in results:
                meeting = dict(row)
                if meeting.get('participants') and isinstance(meeting['participants'], str):
                    try:
                        meeting['participants'] = json.loads(meeting['participants'])
                    except:
                        meeting['participants'] = []
                if meeting.get('key_points') and isinstance(meeting['key_points'], str):
                    try:
                        meeting['key_points'] = json.loads(meeting['key_points'])
                    except:
                        meeting['key_points'] = []
                meetings.append(meeting)
            
            return meetings
            
        except Exception as e:
            logger.error(f"❌ Failed to get meetings by date: {e}")
            return []
    
    # ============================================================================
    # ACTION ITEMS MANAGEMENT
    # ============================================================================
    
    async def get_pending_action_items(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all pending action items across all meetings"""
        try:
            query = '''
                SELECT ai.*, m.title as meeting_title, m.meeting_date
                FROM meeting_action_items ai
                JOIN fathom_meetings m ON ai.meeting_id = m.id
                WHERE ai.status = 'pending'
                ORDER BY ai.priority DESC, ai.due_date ASC NULLS LAST
                LIMIT $1
            '''
            
            results = await self.db.fetch_all(query, limit)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending action items: {e}")
            return []
    
    async def update_action_item_status(self, item_id: str,
                                       status: str) -> bool:
        """Update action item status (pending/completed/cancelled)"""
        try:
            query = '''
                UPDATE meeting_action_items
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            '''
            
            await self.db.execute(query, status, item_id)
            logger.info(f"✅ Updated action item {item_id} to {status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update action item: {e}")
            return False
    
    # ============================================================================
    # ANALYTICS & STATISTICS
    # ============================================================================
    
    async def get_meeting_statistics(self) -> Dict[str, Any]:
        """
        Get overall meeting statistics
        
        FIXED: Original query tried to use unnest() on participants which is stored
        as a JSON string, not a PostgreSQL array. Now parses JSON in Python.
        """
        try:
            # Basic stats query (participants counted separately due to JSON string storage)
            query = '''
                SELECT 
                    COUNT(*) as total_meetings,
                    COALESCE(SUM(duration_minutes), 0) as total_minutes,
                    COALESCE(AVG(duration_minutes), 0) as avg_duration
                FROM fathom_meetings
            '''
            
            result = await self.db.fetch_one(query)
            
            # Count unique participants by parsing JSON strings
            # This is necessary because participants is stored as JSON string, not JSONB array
            participants_query = '''
                SELECT participants FROM fathom_meetings
                WHERE participants IS NOT NULL AND participants != '[]'
            '''
            participant_rows = await self.db.fetch_all(participants_query)
            
            unique_participants = set()
            for row in participant_rows:
                try:
                    participants_str = row['participants']
                    if isinstance(participants_str, str):
                        participants_list = json.loads(participants_str)
                        unique_participants.update(participants_list)
                except:
                    pass
            
            # Get action items stats
            action_query = '''
                SELECT 
                    COUNT(*) as total_actions,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
                FROM meeting_action_items
            '''
            
            action_result = await self.db.fetch_one(action_query)
            
            return {
                'total_meetings': result['total_meetings'] or 0,
                'total_minutes': result['total_minutes'] or 0,
                'avg_duration': float(result['avg_duration'] or 0),
                'unique_participants': len(unique_participants),
                'total_action_items': action_result['total_actions'] or 0,
                'pending_actions': action_result['pending'] or 0,
                'completed_actions': action_result['completed'] or 0
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get statistics: {e}")
            return {}
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health and connectivity"""
        try:
            # Test basic connectivity
            result = await self.db.fetch_one(
                "SELECT COUNT(*) as count FROM fathom_meetings"
            )
            
            # Get recent activity
            recent = await self.db.fetch_one('''
                SELECT COUNT(*) as count 
                FROM fathom_meetings
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            ''')
            
            return {
                'database_connected': True,
                'total_meetings': result['count'] or 0,
                'meetings_last_24h': recent['count'] or 0,
                'last_check': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {
                'database_connected': False,
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }


# ============================================================================
# CONVENIENCE FUNCTIONS FOR EXTERNAL USE
# ============================================================================

async def store_fathom_meeting(recording_data: Dict[str, Any],
                              summary_data: Dict[str, Any]) -> str:
    """Convenience function to store meeting"""
    db = FathomDatabaseManager()
    return await db.store_meeting(recording_data, summary_data)


async def search_meeting_history(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Convenience function to search meetings"""
    db = FathomDatabaseManager()
    return await db.search_meetings(query, limit)
