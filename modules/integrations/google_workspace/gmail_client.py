# modules/integrations/google_workspace/gmail_client.py
"""
Gmail Client - REFACTORED FOR AIOGOOGLE
Multi-Account Email Intelligence with True Async Support
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import base64

logger = logging.getLogger(__name__)

try:
    from aiogoogle import Aiogoogle
    from aiogoogle.auth.creds import UserCreds
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("⚠️ aiogoogle not installed - run: pip install aiogoogle")

from .oauth_manager import get_aiogoogle_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class GmailClient:
    """
    Gmail API client with TRUE async support via aiogoogle
    """
    
    def __init__(self):
        if not GMAIL_AVAILABLE:
            raise RuntimeError("aiogoogle required - run: pip install aiogoogle")
        
        self._user_id = None
        self._user_creds = None
        logger.info("📧 Gmail client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str, email: Optional[str] = None):
        """Initialize with aiogoogle credentials"""
        try:
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, email)
            
            if not self._user_creds:
                raise Exception("No valid credentials available")
            
            logger.info(f"✅ Gmail initialized for {email or 'default account'}")
            
        except Exception as e:
            logger.error(f"❌ Gmail initialization failed: {e}")
            raise
    
    async def get_recent_messages(self, email: Optional[str] = None,
                                  max_results: int = 20,
                                  days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent email messages - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id, email)
            
            # Calculate date query
            after_date = datetime.now() - timedelta(days=days)
            query = f"after:{int(after_date.timestamp())}"
            
            logger.info(f"📧 Fetching messages (async)...")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                gmail_v1 = await aiogoogle.discover('gmail', 'v1')
                
                # THIS IS TRULY ASYNC - NO BLOCKING
                results = await aiogoogle.as_user(
                    gmail_v1.users.messages.list(
                        userId='me',
                        q=query,
                        maxResults=max_results
                    )
                )
                
                messages = results.get('messages', [])
                
                if not messages:
                    logger.info(f"ℹ️ No recent messages found")
                    return []
                
                # Get message details (batch these in production)
                detailed_messages = []
                
                for msg in messages:
                    msg_detail = await aiogoogle.as_user(
                        gmail_v1.users.messages.get(
                            userId='me',
                            id=msg['id'],
                            format='metadata',
                            metadataHeaders=['From', 'To', 'Subject', 'Date']
                        )
                    )
                    
                    # Extract metadata
                    headers = {
                        h['name']: h['value']
                        for h in msg_detail.get('payload', {}).get('headers', [])
                    }
                    
                    detailed_messages.append({
                        'id': msg_detail['id'],
                        'thread_id': msg_detail['threadId'],
                        'from': headers.get('From', 'Unknown'),
                        'to': headers.get('To', ''),
                        'subject': headers.get('Subject', '(No Subject)'),
                        'date': headers.get('Date', ''),
                        'labels': msg_detail.get('labelIds', []),
                        'snippet': msg_detail.get('snippet', ''),
                        'internal_date': msg_detail.get('internalDate', '')
                    })
                
                logger.info(f"✅ Retrieved {len(detailed_messages)} messages")
                return detailed_messages
                
        except Exception as e:
            logger.error(f"❌ Failed to get messages: {e}")
            # Don't swallow - let the error bubble up for debugging
            raise
    
    async def create_draft(self, email: Optional[str], to: str,
                          subject: str, body: str) -> Dict[str, Any]:
        """Create email draft - TRULY ASYNC"""
        try:
            if not self._user_creds:
                await self.initialize(self._user_id, email)
            
            # Create message
            message = f"To: {to}\nSubject: {subject}\n\n{body}"
            encoded_message = base64.urlsafe_b64encode(message.encode()).decode()
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                gmail_v1 = await aiogoogle.discover('gmail', 'v1')
                
                draft = await aiogoogle.as_user(
                    gmail_v1.users.drafts.create(
                        userId='me',
                        json={'message': {'raw': encoded_message}}
                    )
                )
                
                logger.info(f"✅ Created draft")
                
                return {
                    'id': draft['id'],
                    'message_id': draft['message']['id'],
                    'to': to,
                    'subject': subject
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to create draft: {e}")
            raise
    
    # Keep all your analyze_email, get_email_summary, etc. methods as-is
    # Those don't make API calls, just process data

# Global instance
gmail_client = GmailClient()

# Convenience functions stay the same
async def get_recent_emails(user_id: str, email: Optional[str] = None, days: int = 7):
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_recent_messages(email, max_results=20, days=days)

async def get_email_summary(user_id: str, email: Optional[str] = None, days: int = 7):
    await gmail_client.initialize(user_id, email)
    # This queries DB, not API, so it stays as-is
    return await gmail_client.get_email_summary(email, days)
