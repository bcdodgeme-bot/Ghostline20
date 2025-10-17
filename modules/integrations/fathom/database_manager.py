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

Database Tables:
- fathom_meetings: Core meeting data (title, date, participants, transcript)
- meeting_action_items: Extracted action items and tasks
- meeting_topics: Key topics and themes discussed
"""

import asyncpg
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from ...core.database import db_manager

logger = logging.getLogger(__name__)

@dataclass
class MeetingRecord:
    """Container for meeting data"""
    id: str
    fathom_meeting_id: str
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
    
    async def store_meeting(self, meeting_data: Dict[str, Any], 
                          summary_data: Dict[str, Any]) -> str:
        """
        Store complete meeting data (details + summary + action items + topics)
        
        Args:
            meeting_data: Raw meeting data from Fathom API
            summary_data: AI-generated summary and insights
            
        Returns:
            Meeting ID (UUID) from database
        """
        try:
            # Extract meeting details
            details = meeting_data.get('details', {})
            transcript = meeting_data.get('transcript', {})
            
            meeting_id = details.get('id')
            title = details.get('title', 'Untitled Meeting')
            meeting_date = datetime.fromisoformat(
                details.get('start_time', datetime.now().isoformat())
            )
            duration = details.get('duration_minutes', 0)
            participants = details.get('participants', [])
            
            # Format transcript text
            transcript_text = self._format_transcript_text(transcript)
            
            # Extract summary components
            ai_summary = summary_data.get('summary', '')
            key_points = summary_data.get('key_points', [])
            sentiment = summary_data.get('sentiment', 'neutral')
            
            # Store main meeting record
            query = '''
                INSERT INTO fathom_meetings 
                (fathom_meeting_id, title, meeting_date, duration_minutes,
                 participants, transcript_text, ai_summary, key_points,
                 sentiment, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
                ON CONFLICT (fathom_meeting_id) 
                DO UPDATE SET
                    title = EXCLUDED.title,
                    ai_summary = EXCLUDED.ai_summary,
                    key_points = EXCLUDED.key_points,
                    updated_at = NOW()
                RETURNING id
            '''
            
            result = await self.db.fetch_one(
                query,
                meeting_id,
                title,
                meeting_date,
                duration,
                participants,
                transcript_text,
                ai_summary,
                key_points,
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
            
            return db_meeting_id
            
        except Exception as e:
            logger.error(f"❌ Failed to store meeting: {e}")
            raise
    
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
                await self.db.execute(
                    query,
                    meeting_id,
                    topic.get('name', ''),
                    topic.get('importance', 5),
                    topic.get('keywords', [])
                )
            
            logger.info(f"✅ Stored {len(topics)} topics")
            
        except Exception as e:
            logger.error(f"❌ Failed to store topics: {e}")
    
    # ============================================================================
    # MEETING RETRIEVAL
    # ============================================================================
    
    async def get_meeting_by_id(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get complete meeting data by ID"""
        try:
            query = '''
                SELECT * FROM fathom_meetings
                WHERE id = $1
            '''
            
            result = await self.db.fetch_one(query, meeting_id)
            
            if not result:
                return None
            
            meeting = dict(result)
            
            # Get action items
            meeting['action_items'] = await self._get_action_items(meeting_id)
            
            # Get topics
            meeting['topics'] = await self._get_topics(meeting_id)
            
            return meeting
            
        except Exception as e:
            logger.error(f"❌ Failed to get meeting: {e}")
            return None
    
    async def _get_action_items(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get action items for a meeting"""
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
        """Get topics for a meeting"""
        try:
            query = '''
                SELECT * FROM meeting_topics
                WHERE meeting_id = $1
                ORDER BY importance_score DESC
            '''
            
            results = await self.db.fetch_all(query, meeting_id)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Failed to get topics: {e}")
            return []
    
    async def get_recent_meetings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent meetings ordered by date"""
        try:
            query = '''
                SELECT id, fathom_meeting_id, title, meeting_date,
                       duration_minutes, participants, ai_summary,
                       key_points, created_at
                FROM fathom_meetings
                ORDER BY meeting_date DESC
                LIMIT $1
            '''
            
            results = await self.db.fetch_all(query, limit)
            return [dict(row) for row in results]
            
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
            # Search in title, summary, key points, and transcript
            query = '''
                SELECT id, fathom_meeting_id, title, meeting_date,
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
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Failed to search meetings: {e}")
            return []
    
    async def get_meetings_by_date_range(self, start_date: datetime,
                                        end_date: datetime) -> List[Dict[str, Any]]:
        """Get meetings within a date range"""
        try:
            query = '''
                SELECT id, fathom_meeting_id, title, meeting_date,
                       duration_minutes, participants, ai_summary,
                       key_points, created_at
                FROM fathom_meetings
                WHERE meeting_date BETWEEN $1 AND $2
                ORDER BY meeting_date DESC
            '''
            
            results = await self.db.fetch_all(query, start_date, end_date)
            return [dict(row) for row in results]
            
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
        """Get overall meeting statistics"""
        try:
            query = '''
                SELECT 
                    COUNT(*) as total_meetings,
                    SUM(duration_minutes) as total_minutes,
                    AVG(duration_minutes) as avg_duration,
                    COUNT(DISTINCT unnest(participants)) as unique_participants
                FROM fathom_meetings
            '''
            
            result = await self.db.fetch_one(query)
            
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
                'unique_participants': result['unique_participants'] or 0,
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
    
    def _format_transcript_text(self, transcript: Dict[str, Any]) -> str:
        """Format transcript segments into readable text"""
        try:
            segments = transcript.get('segments', [])
            
            if not segments:
                return ""
            
            lines = []
            current_speaker = None
            
            for segment in segments:
                speaker = segment.get('speaker', 'Unknown')
                text = segment.get('text', '').strip()
                
                if not text:
                    continue
                
                # Add speaker label when speaker changes
                if speaker != current_speaker:
                    lines.append(f"\n[{speaker}]")
                    current_speaker = speaker
                
                lines.append(text)
            
            return "\n".join(lines).strip()
            
        except Exception as e:
            logger.error(f"❌ Failed to format transcript: {e}")
            return ""
    
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

# Convenience functions for external use
async def store_fathom_meeting(meeting_data: Dict[str, Any],
                              summary_data: Dict[str, Any]) -> str:
    """Convenience function to store meeting"""
    db = FathomDatabaseManager()
    return await db.store_meeting(meeting_data, summary_data)

async def search_meeting_history(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Convenience function to search meetings"""
    db = FathomDatabaseManager()
    return await db.search_meetings(query, limit)