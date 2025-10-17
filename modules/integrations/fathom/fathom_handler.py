# modules/integrations/fathom/fathom_handler.py
"""
Fathom API Client
Handles all interactions with Fathom's API for fetching meeting data

Key Features:
- Authenticate with Fathom API using X-Api-Key header
- Fetch meeting details and metadata
- Download full meeting transcripts
- Handle API errors and rate limiting
- Verify webhook signatures for security

API Documentation: https://docs.fathom.video/docs/api-reference
Base URL: https://api.fathom.ai/external/v1
"""

import os
import hmac
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

class FathomHandler:
    """
    Fathom API client for fetching meeting recordings and transcripts
    """
    
    def __init__(self):
        """Initialize Fathom API client with credentials"""
        self.api_key = os.getenv('FATHOM_API_KEY')
        self.webhook_secret = os.getenv('FATHOM_WEBHOOK_SECRET')
        self.base_url = 'https://api.fathom.ai/external/v1'
        
        if not self.api_key:
            logger.error("❌ FATHOM_API_KEY not found in environment variables")
            raise ValueError("FATHOM_API_KEY is required")
        
        if not self.webhook_secret:
            logger.warning("⚠️ FATHOM_WEBHOOK_SECRET not found - webhook verification disabled")
        
        # Set up headers for API requests
        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        logger.info(f"✅ Fathom API client initialized")
    
    def verify_webhook_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """
        Verify that webhook request came from Fathom
        
        Args:
            body: Raw request body bytes
            timestamp: X-Fathom-Timestamp header
            signature: X-Fathom-Signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            logger.warning("⚠️ Webhook secret not configured - skipping verification")
            return True
        
        try:
            # Fathom uses HMAC-SHA256 for webhook signatures
            # Format: v1=<signature>
            expected_signature = signature.split('v1=')[-1] if 'v1=' in signature else signature
            
            # Create signature: HMAC-SHA256(webhook_secret, timestamp + "." + body)
            message = f"{timestamp}.{body.decode('utf-8')}"
            computed_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            is_valid = hmac.compare_digest(computed_signature, expected_signature)
            
            if is_valid:
                logger.info("✅ Webhook signature verified")
            else:
                logger.error("❌ Webhook signature verification failed")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Webhook verification error: {e}")
            return False
    
    async def get_meeting_details(self, meeting_id: str) -> Dict[str, Any]:
        """
        Fetch meeting details from Fathom API
        
        Args:
            meeting_id: Fathom meeting ID
            
        Returns:
            Dict with meeting metadata (title, date, duration, participants, etc.)
        """
        try:
            logger.info(f"📥 Fetching meeting details: {meeting_id}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/meetings/{meeting_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                response.raise_for_status()
                meeting_data = response.json()
                
                logger.info(f"✅ Meeting details retrieved: {meeting_data.get('title', 'Untitled')}")
                return meeting_data
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error fetching meeting: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error fetching meeting details: {e}")
            raise
    
    async def get_meeting_transcript(self, meeting_id: str) -> Dict[str, Any]:
        """
        Fetch full meeting transcript from Fathom API
        
        Args:
            meeting_id: Fathom meeting ID
            
        Returns:
            Dict with transcript data (speakers, timestamps, text)
        """
        try:
            logger.info(f"📝 Fetching transcript for meeting: {meeting_id}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/meetings/{meeting_id}/transcript",
                    headers=self.headers,
                    timeout=60.0  # Transcripts can be large
                )
                
                response.raise_for_status()
                transcript_data = response.json()
                
                # Count total words in transcript
                total_words = sum(
                    len(segment.get('text', '').split())
                    for segment in transcript_data.get('segments', [])
                )
                
                logger.info(f"✅ Transcript retrieved: {total_words} words")
                return transcript_data
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error fetching transcript: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error fetching transcript: {e}")
            raise
    
    async def list_recent_meetings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recent meetings from Fathom
        
        Args:
            limit: Maximum number of meetings to return
            
        Returns:
            List of meeting dictionaries
        """
        try:
            logger.info(f"📋 Listing {limit} recent meetings")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/meetings",
                    headers=self.headers,
                    params={'limit': limit},
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                meetings = data.get('meetings', [])
                
                logger.info(f"✅ Retrieved {len(meetings)} meetings")
                return meetings
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error listing meetings: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error listing meetings: {e}")
            raise
    
    async def get_complete_meeting_data(self, meeting_id: str) -> Dict[str, Any]:
        """
        Fetch complete meeting data (details + transcript) in one call
        
        Args:
            meeting_id: Fathom meeting ID
            
        Returns:
            Dict with both meeting details and full transcript
        """
        try:
            logger.info(f"📦 Fetching complete data for meeting: {meeting_id}")
            
            # Fetch both details and transcript in parallel
            import asyncio
            details, transcript = await asyncio.gather(
                self.get_meeting_details(meeting_id),
                self.get_meeting_transcript(meeting_id),
                return_exceptions=True
            )
            
            # Handle any errors
            if isinstance(details, Exception):
                logger.error(f"❌ Failed to fetch meeting details: {details}")
                details = {'error': str(details)}
            
            if isinstance(transcript, Exception):
                logger.error(f"❌ Failed to fetch transcript: {transcript}")
                transcript = {'error': str(transcript)}
            
            # Combine data
            complete_data = {
                'meeting_id': meeting_id,
                'fetched_at': datetime.now().isoformat(),
                'details': details,
                'transcript': transcript
            }
            
            logger.info(f"✅ Complete meeting data retrieved")
            return complete_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching complete meeting data: {e}")
            raise
    
    def format_transcript_for_ai(self, transcript_data: Dict[str, Any]) -> str:
        """
        Format transcript into clean text for AI processing
        
        Args:
            transcript_data: Raw transcript from Fathom API
            
        Returns:
            Formatted transcript string with speaker labels and timestamps
        """
        try:
            segments = transcript_data.get('segments', [])
            
            if not segments:
                logger.warning("⚠️ No transcript segments found")
                return ""
            
            # Format as: [Speaker] Text
            formatted_lines = []
            current_speaker = None
            
            for segment in segments:
                speaker = segment.get('speaker', 'Unknown')
                text = segment.get('text', '').strip()
                
                if not text:
                    continue
                
                # Only add speaker label when speaker changes
                if speaker != current_speaker:
                    formatted_lines.append(f"\n[{speaker}]")
                    current_speaker = speaker
                
                formatted_lines.append(text)
            
            formatted_transcript = "\n".join(formatted_lines).strip()
            
            logger.info(f"✅ Formatted transcript: {len(formatted_transcript)} characters")
            return formatted_transcript
            
        except Exception as e:
            logger.error(f"❌ Error formatting transcript: {e}")
            return ""

# Convenience functions for external use
async def fetch_meeting(meeting_id: str) -> Dict[str, Any]:
    """Convenience function to fetch complete meeting data"""
    handler = FathomHandler()
    return await handler.get_complete_meeting_data(meeting_id)

async def verify_fathom_webhook(body: bytes, timestamp: str, signature: str) -> bool:
    """Convenience function to verify webhook signatures"""
    handler = FathomHandler()
    return handler.verify_webhook_signature(body, timestamp, signature)