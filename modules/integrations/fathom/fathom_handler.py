# modules/integrations/fathom/fathom_handler.py
"""
Fathom API Client
Handles all interactions with Fathom's API for fetching meeting data

Key Features:
- Authenticate with Fathom API using Bearer token
- Fetch recording details and metadata
- Download full recording transcripts
- Handle API errors and rate limiting
- Verify webhook signatures for security

API Documentation: https://docs.fathom.video/docs/api-reference
Base URL: https://api.fathom.video/v1
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
        # ✅ FIXED: Correct base URL
        self.base_url = 'https://api.fathom.video/v1'
        
        if not self.api_key:
            logger.error("❌ FATHOM_API_KEY not found in environment variables")
            raise ValueError("FATHOM_API_KEY is required")
        
        if not self.webhook_secret:
            logger.warning("⚠️ FATHOM_WEBHOOK_SECRET not found - webhook verification disabled")
        
        # ✅ FIXED: Use Bearer token format
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
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
    
    # ✅ FIXED: Changed to use /recordings endpoint and recording_id
    async def get_recording_details(self, recording_id: int) -> Dict[str, Any]:
        """
        Fetch recording details from Fathom API
        
        Args:
            recording_id: Fathom recording ID (integer)
            
        Returns:
            Dict with recording metadata (title, date, duration, participants, etc.)
        """
        try:
            logger.info(f"📥 Fetching recording details: {recording_id}")
            
            async with httpx.AsyncClient() as client:
                # ✅ FIXED: Get from /recordings list and find the specific one
                response = await client.get(
                    f"{self.base_url}/recordings",
                    headers=self.headers,
                    params={'limit': 100},
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                recordings = data.get('recordings', [])
                
                # Find the specific recording
                recording = None
                for rec in recordings:
                    if rec.get('id') == recording_id:
                        recording = rec
                        break
                
                if not recording:
                    logger.error(f"❌ Recording {recording_id} not found")
                    raise ValueError(f"Recording {recording_id} not found")
                
                logger.info(f"✅ Recording details retrieved: {recording.get('title', 'Untitled')}")
                return recording
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error fetching recording: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error fetching recording details: {e}")
            raise
    
    # ✅ FIXED: Changed to use correct transcript endpoint
    async def get_recording_transcript(self, recording_id: int) -> Dict[str, Any]:
        """
        Fetch full recording transcript from Fathom API
        
        Args:
            recording_id: Fathom recording ID (integer)
            
        Returns:
            Dict with transcript data (full text, not segments)
        """
        try:
            logger.info(f"📝 Fetching transcript for recording: {recording_id}")
            
            async with httpx.AsyncClient() as client:
                # ✅ FIXED: Use correct endpoint
                response = await client.get(
                    f"{self.base_url}/recordings/{recording_id}/transcript",
                    headers=self.headers,
                    timeout=60.0  # Transcripts can be large
                )
                
                response.raise_for_status()
                transcript_data = response.json()
                
                # ✅ FIXED: Transcript is in 'transcript' field, not 'segments'
                transcript_text = transcript_data.get('transcript', '')
                word_count = len(transcript_text.split())
                
                logger.info(f"✅ Transcript retrieved: {word_count} words")
                return transcript_data
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error fetching transcript: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error fetching transcript: {e}")
            raise
    
    # ✅ FIXED: Changed to use /recordings endpoint
    async def list_recent_recordings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recent recordings from Fathom
        
        Args:
            limit: Maximum number of recordings to return
            
        Returns:
            List of recording dictionaries
        """
        try:
            logger.info(f"📋 Listing {limit} recent recordings")
            
            async with httpx.AsyncClient() as client:
                # ✅ FIXED: Use /recordings endpoint
                response = await client.get(
                    f"{self.base_url}/recordings",
                    headers=self.headers,
                    params={'limit': limit},
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                recordings = data.get('recordings', [])
                
                logger.info(f"✅ Retrieved {len(recordings)} recordings")
                return recordings
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error listing recordings: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"❌ Error listing recordings: {e}")
            raise
    
    # ✅ FIXED: Changed parameter name and logic
    async def get_complete_recording_data(self, recording_id: int) -> Dict[str, Any]:
        """
        Fetch complete recording data (details + transcript) in one call
        
        Args:
            recording_id: Fathom recording ID (integer)
            
        Returns:
            Dict with both recording details and full transcript
        """
        try:
            logger.info(f"📦 Fetching complete data for recording: {recording_id}")
            
            # Fetch both details and transcript in parallel
            import asyncio
            details, transcript = await asyncio.gather(
                self.get_recording_details(recording_id),
                self.get_recording_transcript(recording_id),
                return_exceptions=True
            )
            
            # Handle any errors
            if isinstance(details, Exception):
                logger.error(f"❌ Failed to fetch recording details: {details}")
                details = {'error': str(details)}
            
            if isinstance(transcript, Exception):
                logger.error(f"❌ Failed to fetch transcript: {transcript}")
                transcript = {'error': str(transcript)}
            
            # Combine data
            complete_data = {
                'recording_id': recording_id,
                'fetched_at': datetime.now().isoformat(),
                'details': details,
                'transcript': transcript
            }
            
            logger.info(f"✅ Complete recording data retrieved")
            return complete_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching complete recording data: {e}")
            raise
    
    # ✅ FIXED: Updated to handle new transcript format
    def format_transcript_for_ai(self, transcript_data: Dict[str, Any]) -> str:
        """
        Format transcript into clean text for AI processing
        
        Args:
            transcript_data: Raw transcript from Fathom API
            
        Returns:
            Formatted transcript string (already formatted by Fathom)
        """
        try:
            # ✅ FIXED: Transcript is in 'transcript' field, already formatted
            transcript_text = transcript_data.get('transcript', '')
            
            if not transcript_text:
                logger.warning("⚠️ No transcript text found")
                return ""
            
            logger.info(f"✅ Formatted transcript: {len(transcript_text)} characters")
            return transcript_text
            
        except Exception as e:
            logger.error(f"❌ Error formatting transcript: {e}")
            return ""

# ✅ FIXED: Updated convenience functions
async def fetch_recording(recording_id: int) -> Dict[str, Any]:
    """Convenience function to fetch complete recording data"""
    handler = FathomHandler()
    return await handler.get_complete_recording_data(recording_id)

async def verify_fathom_webhook(body: bytes, timestamp: str, signature: str) -> bool:
    """Convenience function to verify webhook signatures"""
    handler = FathomHandler()
    return handler.verify_webhook_signature(body, timestamp, signature)
