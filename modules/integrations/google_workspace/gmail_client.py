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
            logger.debug(f"🔧 Gmail.initialize() called with user_id={user_id}, email={email}")
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, email)
            
            if not self._user_creds:
                logger.error(f"❌ No credentials found for user_id={user_id}, email={email}")
                raise Exception("No valid credentials available")
            
            logger.info(f"✅ Gmail initialized for {email or 'default account'}")
            
        except Exception as e:
            logger.error(f"❌ Gmail initialization failed: {e}", exc_info=True)
            raise
    
    async def get_recent_messages(self, email: Optional[str] = None,
                                  max_results: int = 20,
                                  days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent email messages - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing for email={email}")
                await self.initialize(self._user_id, email)
            
            # Calculate date query
            after_date = datetime.now() - timedelta(days=days)
            query = f"after:{int(after_date.timestamp())}"
            
            logger.info(f"📧 Fetching messages (async): max={max_results}, days={days}, query={query}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                gmail_v1 = await aiogoogle.discover('gmail', 'v1')
                
                logger.debug(f"🔍 Calling Gmail API: users.messages.list")
                
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
                    logger.info(f"ℹ️ No recent messages found for query: {query}")
                    return []
                
                logger.info(f"📬 Found {len(messages)} messages, fetching details...")
                
                # Get message details (batch these in production)
                detailed_messages = []
                
                for idx, msg in enumerate(messages):
                    logger.debug(f"🔍 Fetching details for message {idx+1}/{len(messages)}: {msg['id']}")
                    
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
                    
                    message_data = {
                        'id': msg_detail['id'],
                        'thread_id': msg_detail['threadId'],
                        'from': headers.get('From', 'Unknown'),
                        'to': headers.get('To', ''),
                        'subject': headers.get('Subject', '(No Subject)'),
                        'date': headers.get('Date', ''),
                        'labels': msg_detail.get('labelIds', []),
                        'snippet': msg_detail.get('snippet', ''),
                        'internal_date': msg_detail.get('internalDate', '')
                    }
                    
                    detailed_messages.append(message_data)
                    
                    # Store in database for later analysis
                    await self._store_email_data(message_data)
                
                logger.info(f"✅ Retrieved and stored {len(detailed_messages)} messages")
                return detailed_messages
                
        except Exception as e:
            logger.error(f"❌ Failed to get messages: {e}", exc_info=True)
            raise
    
    async def _store_email_data(self, message: Dict[str, Any]):
        """Store email data in database for analysis"""
        try:
            conn = await db_manager.get_connection()
            try:
                # Parse date
                try:
                    email_date = datetime.fromtimestamp(int(message['internal_date']) / 1000)
                except:
                    email_date = datetime.now()
                
                await conn.execute('''
                    INSERT INTO gmail_messages 
                    (user_id, message_id, thread_id, subject, sender, recipient, 
                     email_date, labels, snippet, fetched_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (user_id, message_id) DO UPDATE SET
                        labels = EXCLUDED.labels,
                        snippet = EXCLUDED.snippet,
                        fetched_at = NOW()
                ''',
                self._user_id,
                message['id'],
                message['thread_id'],
                message['subject'],
                message['from'],
                message['to'],
                email_date,
                message['labels'],
                message['snippet']
                )
                
                logger.debug(f"💾 Stored email: {message['subject'][:50]}")
                
            finally:
                await db_manager.release_connection(conn)
            
        except Exception as e:
            logger.error(f"❌ Failed to store email data: {e}", exc_info=True)
            # Don't raise - storing is optional, continue even if it fails
    
    async def get_email_summary(self, email: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
        """
        Get email summary from database - WITH AUTO-FETCH
        
        This method:
        1. Checks database for recent emails
        2. If database is empty or stale, fetches from API first
        3. Returns summary statistics
        """
        try:
            logger.info(f"📊 Getting email summary: email={email}, days={days}")
            
            # Check if we have recent data in database
            cutoff_date = datetime.now() - timedelta(days=days)
            
            conn = await db_manager.get_connection()
            try:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM gmail_messages
                    WHERE user_id = $1 
                    AND email_date >= $2
                ''', self._user_id, cutoff_date)
                
                logger.debug(f"📊 Found {count} emails in database for last {days} days")
                
                # If no data or stale data, fetch from API first
                if count == 0:
                    logger.info(f"🔄 No recent data in DB, fetching from Gmail API...")
                    try:
                        await self.get_recent_messages(email, max_results=50, days=days)
                        logger.info(f"✅ Fresh data fetched from API")
                    except Exception as fetch_error:
                        logger.error(f"⚠️ Failed to fetch from API: {fetch_error}")
                        # Continue anyway - maybe we can still provide partial data
                
                # Now query database for summary
                logger.debug(f"🔍 Querying database for email summary...")
                
                summary_data = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_emails,
                        COUNT(CASE WHEN 'IMPORTANT' = ANY(labels) THEN 1 END) as important,
                        COUNT(CASE WHEN 'UNREAD' = ANY(labels) THEN 1 END) as unread,
                        COUNT(CASE WHEN 'INBOX' = ANY(labels) THEN 1 END) as inbox,
                        COUNT(CASE WHEN 'SENT' = ANY(labels) THEN 1 END) as sent
                    FROM gmail_messages
                    WHERE user_id = $1 
                    AND email_date >= $2
                ''', self._user_id, cutoff_date)
                
                if not summary_data or summary_data['total_emails'] == 0:
                    logger.warning(f"⚠️ No email data available after fetch attempt")
                    return {
                        'total_emails': 0,
                        'important': 0,
                        'unread': 0,
                        'inbox': 0,
                        'sent': 0,
                        'days': days,
                        'note': 'No emails found in the specified period'
                    }
                
                summary = {
                    'total_emails': summary_data['total_emails'],
                    'important': summary_data['important'],
                    'unread': summary_data['unread'],
                    'inbox': summary_data['inbox'],
                    'sent': summary_data['sent'],
                    'days': days
                }
                
                logger.info(f"✅ Email summary generated: {summary['total_emails']} total emails")
                return summary
                
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"❌ Failed to get email summary: {e}", exc_info=True)
            raise
    
    async def create_draft(self, email: Optional[str], to: str,
                          subject: str, body: str) -> Dict[str, Any]:
        """Create email draft - TRULY ASYNC"""
        try:
            logger.info(f"✉️ Creating draft: to={to}, subject={subject[:50]}")
            
            if not self._user_creds:
                logger.debug(f"🔧 No credentials loaded, initializing...")
                await self.initialize(self._user_id, email)
            
            # Create message
            message = f"To: {to}\nSubject: {subject}\n\n{body}"
            encoded_message = base64.urlsafe_b64encode(message.encode()).decode()
            
            logger.debug(f"📝 Encoded message length: {len(encoded_message)} chars")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                gmail_v1 = await aiogoogle.discover('gmail', 'v1')
                
                logger.debug(f"🔍 Calling Gmail API: users.drafts.create")
                
                draft = await aiogoogle.as_user(
                    gmail_v1.users.drafts.create(
                        userId='me',
                        json={'message': {'raw': encoded_message}}
                    )
                )
                
                draft_result = {
                    'id': draft['id'],
                    'message_id': draft['message']['id'],
                    'to': to,
                    'subject': subject
                }
                
                logger.info(f"✅ Created draft: id={draft['id']}")
                return draft_result
                
        except Exception as e:
            logger.error(f"❌ Failed to create draft: {e}", exc_info=True)
            raise

# Global instance
gmail_client = GmailClient()

# Convenience functions
async def get_recent_emails(user_id: str, email: Optional[str] = None, days: int = 7):
    """Fetch recent emails from Gmail API"""
    logger.debug(f"🔧 get_recent_emails() called: user_id={user_id}, email={email}, days={days}")
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_recent_messages(email, max_results=20, days=days)

async def get_email_summary(user_id: str, email: Optional[str] = None, days: int = 7):
    """Get email summary with auto-fetch if needed"""
    logger.debug(f"🔧 get_email_summary() called: user_id={user_id}, email={email}, days={days}")
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_email_summary(email, days)
