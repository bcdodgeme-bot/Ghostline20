# modules/integrations/google_workspace/gmail_client.py
"""
Gmail Client - REFACTORED FOR AIOGOOGLE
Multi-Account Email Intelligence with True Async Support
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
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
        self._email_account = None
        self._last_summary_emails = {}  # NEW: user_id -> {index: message_id} mapping
        logger.info("📧 Gmail client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str, email: Optional[str] = None):
        """Initialize with aiogoogle credentials"""
        try:
            logger.debug(f"📧 Gmail.initialize() called with user_id={user_id}, email={email}")
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, email)
            
            if not self._user_creds:
                logger.error(f"❌ No credentials found for user_id={user_id}, email={email}")
                raise Exception("No valid credentials available")
            
            # Store email account for database
            if email:
                self._email_account = email
            else:
                # Try to get email from creds
                self._email_account = "default"
            
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
                logger.debug(f"📧 No credentials loaded, initializing for email={email}")
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
                
                # Determine priority from labels
                labels = message.get('labels', [])
                priority_level = 'normal'
                if 'IMPORTANT' in labels:
                    priority_level = 'high'
                elif 'STARRED' in labels:
                    priority_level = 'high'
                
                # Determine category from labels
                category = 'inbox'
                if 'SENT' in labels:
                    category = 'sent'
                elif 'DRAFT' in labels:
                    category = 'draft'
                elif 'SPAM' in labels:
                    category = 'spam'
                
                # Check if requires response (heuristic)
                requires_response = 'UNREAD' in labels and 'INBOX' in labels
                
                await conn.execute('''
                    INSERT INTO google_gmail_analysis 
                    (user_id, email_account, message_id, thread_id, sender_email, 
                     subject_line, priority_level, category, requires_response, 
                     email_date, analyzed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                    ON CONFLICT (user_id, message_id) DO UPDATE SET
                        priority_level = EXCLUDED.priority_level,
                        category = EXCLUDED.category,
                        requires_response = EXCLUDED.requires_response,
                        analyzed_at = NOW()
                ''',
                self._user_id,
                self._email_account or 'default',
                message['id'],
                message['thread_id'],
                message['from'],
                message['subject'],
                priority_level,
                category,
                requires_response,
                email_date
                )
                
                logger.debug(f"💾 Stored email: {message['subject'][:50]}")
                
            finally:
                await db_manager.release_connection(conn)
            
        except Exception as e:
            logger.error(f"❌ Failed to store email data: {e}", exc_info=True)
            # Don't raise - storing is optional, continue even if it fails
    
    async def get_emails_requiring_response(self, days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get list of emails that require a response
        
        Args:
            days: Number of days to look back
            limit: Maximum number of emails to return
            
        Returns:
            List of email dictionaries with sender, subject, date, message_id
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            conn = await db_manager.get_connection()
            try:
                rows = await conn.fetch('''
                    SELECT 
                        message_id,
                        sender_email,
                        subject_line,
                        email_date,
                        priority_level
                    FROM google_gmail_analysis
                    WHERE user_id = $1 
                    AND email_date >= $2
                    AND requires_response = true
                    ORDER BY email_date DESC
                    LIMIT $3
                ''', self._user_id, cutoff_date, limit)
                
                emails = []
                for row in rows:
                    emails.append({
                        'message_id': row['message_id'],
                        'from': row['sender_email'],
                        'subject': row['subject_line'],
                        'date': row['email_date'],
                        'priority': row['priority_level']
                    })
                
                logger.info(f"📋 Found {len(emails)} emails requiring response")
                return emails
                
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"❌ Failed to get emails requiring response: {e}", exc_info=True)
            return []
    
    async def get_email_summary(self, email: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
        """
        Get email summary from database - WITH AUTO-FETCH AND DETAILED BREAKDOWN
        
        This method:
        1. Checks database for recent emails
        2. If database is empty or stale, fetches from API first
        3. Returns summary statistics WITH list of emails requiring response
        4. Stores index mapping for later email detail requests
        """
        try:
            logger.info(f"📊 Getting email summary: email={email}, days={days}")
            
            # Check if we have recent data in database
            cutoff_date = datetime.now() - timedelta(days=days)
            
            conn = await db_manager.get_connection()
            try:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM google_gmail_analysis
                    WHERE user_id = $1 
                    AND email_date >= $2
                ''', self._user_id, cutoff_date)

                logger.debug(f"📊 Found {count} emails in database for last {days} days")

                # Check if we need to fetch fresh data
                # Get the most recent email date in database
                latest_email = await conn.fetchval('''
                    SELECT MAX(email_date) FROM google_gmail_analysis
                    WHERE user_id = $1 
                    AND email_date >= $2
                ''', self._user_id, cutoff_date)

                # If no data OR latest email is older than 1 hour, fetch fresh
                from datetime import timezone
                needs_refresh = (count == 0) or (latest_email and datetime.now(timezone.utc) - latest_email > timedelta(hours=1))

                logger.debug(f"🔍 Refresh check: count={count}, latest={latest_email}, needs_refresh={needs_refresh}")

                if needs_refresh:
                    logger.info(f"🔄 Fetching fresh data from Gmail API...")
                    try:
                        await self.get_recent_messages(email, max_results=50, days=days)
                        logger.info(f"✅ Fresh data fetched from API")
                    except Exception as fetch_error:
                        logger.error(f"⚠️ Failed to fetch from API: {fetch_error}")
                        # Continue anyway - maybe we can still provide partial data
                
                # Now query database for summary using actual schema columns
                logger.debug(f"🔍 Querying database for email summary...")
                
                summary_data = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_emails,
                        COUNT(CASE WHEN priority_level = 'high' THEN 1 END) as important,
                        COUNT(CASE WHEN requires_response = true THEN 1 END) as needs_response,
                        COUNT(CASE WHEN category = 'inbox' THEN 1 END) as inbox,
                        COUNT(CASE WHEN category = 'sent' THEN 1 END) as sent,
                        COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative_sentiment
                    FROM google_gmail_analysis
                    WHERE user_id = $1 
                    AND email_date >= $2
                ''', self._user_id, cutoff_date)
                
                if not summary_data or summary_data['total_emails'] == 0:
                    logger.warning(f"⚠️ No email data available after fetch attempt")
                    return {
                        'total_emails': 0,
                        'important': 0,
                        'needs_response': 0,
                        'inbox': 0,
                        'sent': 0,
                        'negative_sentiment': 0,
                        'days': days,
                        'emails_requiring_response': [],
                        'note': 'No emails found in the specified period'
                    }
                
                # Get the actual emails that need responses
                emails_needing_response = await self.get_emails_requiring_response(days=days, limit=10)
                
                # Store email index mapping for later detail requests
                if emails_needing_response:
                    self._last_summary_emails[self._user_id] = {
                        i+1: email['message_id']
                        for i, email in enumerate(emails_needing_response[:10])
                    }
                    logger.debug(f"💾 Stored index mapping for {len(emails_needing_response)} emails")
                
                summary = {
                    'total_emails': summary_data['total_emails'],
                    'important': summary_data['important'],
                    'needs_response': summary_data['needs_response'],
                    'inbox': summary_data['inbox'],
                    'sent': summary_data['sent'],
                    'negative_sentiment': summary_data['negative_sentiment'],
                    'days': days,
                    'emails_requiring_response': emails_needing_response
                }
                
                logger.info(f"✅ Email summary generated: {summary['total_emails']} total emails, {len(emails_needing_response)} need response")
                return summary
                
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"❌ Failed to get email summary: {e}", exc_info=True)
            raise
    
    async def get_email_by_index(self, email_index: int) -> Optional[Dict[str, Any]]:
        """
        Get full email details by summary list index
        
        Args:
            email_index: The number shown in the summary list (1-10)
            
        Returns:
            Full email details or None if not found
        """
        try:
            # Get message_id from stored mapping
            message_id = self._last_summary_emails.get(self._user_id, {}).get(email_index)
            
            if not message_id:
                logger.warning(f"No email found at index {email_index}. Run 'google email summary' first.")
                return None
            
            # FIX #1: Fetch the actual email details using the message_id
            return await self.get_email_details(message_id)
            
        except Exception as e:
            logger.error(f"Failed to get email by index: {e}")
            return None
    
    async def get_email_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full email content including body
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Full email details with body text
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                gmail_v1 = await aiogoogle.discover('gmail', 'v1')
                
                # Get full message including body
                msg = await aiogoogle.as_user(
                    gmail_v1.users.messages.get(
                        userId='me',
                        id=message_id,
                        format='full'
                    )
                )
                
                # Extract headers
                headers = {
                    h['name']: h['value']
                    for h in msg.get('payload', {}).get('headers', [])
                }
                
                # Extract body
                body_text = self._extract_email_body(msg.get('payload', {}))
                
                return {
                    'message_id': message_id,
                    'thread_id': msg.get('threadId'),
                    'from': headers.get('From', 'Unknown'),
                    'to': headers.get('To', ''),
                    'subject': headers.get('Subject', '(No Subject)'),
                    'date': headers.get('Date', ''),
                    'body': body_text,
                    'snippet': msg.get('snippet', ''),
                    'labels': msg.get('labelIds', [])
                }
                
        except Exception as e:
            logger.error(f"Failed to get email details: {e}")
            return None
    
    def _extract_email_body(self, payload: Dict) -> str:
        """
        Extract text body from email payload
        
        Args:
            payload: Gmail API message payload
            
        Returns:
            Email body as plain text
        """
        try:
            # Check for plain text in body
            if 'body' in payload and payload['body'].get('data'):
                body_data = payload['body']['data']
                body_bytes = base64.urlsafe_b64decode(body_data)
                return body_bytes.decode('utf-8', errors='ignore')
            
            # Check parts for text/plain
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain':
                        if part.get('body', {}).get('data'):
                            body_data = part['body']['data']
                            body_bytes = base64.urlsafe_b64decode(body_data)
                            return body_bytes.decode('utf-8', errors='ignore')
                    
                    # Recursive check for nested parts
                    if 'parts' in part:
                        nested_body = self._extract_email_body(part)
                        if nested_body:
                            return nested_body
            
            return ""
            
        except Exception as e:
            logger.error(f"Body extraction failed: {e}")
            return ""
    
    async def summarize_email(self, email_index: int) -> str:
        """
        Generate summary of email by index
        
        Args:
            email_index: The number from the summary list
            
        Returns:
            Formatted email summary with key points
        """
        try:
            email = await self.get_email_by_index(email_index)
            
            if not email:
                return f"Email #{email_index} not found. Run `google email summary` first to see the list."
            
            # Truncate body if too long
            body_preview = email['body'][:2000] if len(email['body']) > 2000 else email['body']
            
            # Extract key points
            key_points = self._extract_key_points(body_preview)
            
            return f"""**Email #{email_index} Details**

**From:** {email['from']}
**Subject:** {email['subject']}
**Date:** {email['date']}

**Key Points:**
{key_points}

**Body Preview:**
{body_preview[:500]}...

---

**Actions:**
- `reply to email {email_index}` - Draft a response
- `read email {email_index}` - See full email body"""
            
        except Exception as e:
            logger.error(f"Email summary failed: {e}")
            return f"Failed to summarize email: {str(e)}"
    
    def _extract_key_points(self, body_text: str) -> str:
        """
        Simple key point extraction from email body
        
        Args:
            body_text: Email body text
            
        Returns:
            Bullet points of key information
        """
        # Split into sentences
        sentences = [s.strip() for s in body_text.split('.') if s.strip()]
        
        # Return first 3 meaningful sentences as key points
        key_points = []
        for i, sentence in enumerate(sentences[:5], 1):
            if len(sentence) > 20:  # Skip very short sentences
                key_points.append(f"• {sentence}")
                if len(key_points) >= 3:
                    break
        
        return '\n'.join(key_points) if key_points else "• [No clear key points detected]"
    
    async def create_draft(self, email: Optional[str], to: str,
                          subject: str, body: str) -> Dict[str, Any]:
        """Create email draft - TRULY ASYNC"""
        try:
            logger.info(f"✉️ Creating draft: to={to}, subject={subject[:50]}")
            
            if not self._user_creds:
                logger.debug(f"📧 No credentials loaded, initializing...")
                await self.initialize(self._user_id, email)
            
            # Create message
            message = f"To: {to}\nSubject: {subject}\n\n{body}"
            encoded_message = base64.urlsafe_b64encode(message.encode()).decode()
            
            logger.debug(f"🔍 Encoded message length: {len(encoded_message)} chars")
            
            # FIX #2: Need client_creds for token refresh
            from .oauth_manager import google_auth_manager
            
            client_creds = {
                'client_id': google_auth_manager.client_id,
                'client_secret': google_auth_manager.client_secret
            }
            
            async with Aiogoogle(user_creds=self._user_creds, client_creds=client_creds) as aiogoogle:
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
    logger.debug(f"📧 get_recent_emails() called: user_id={user_id}, email={email}, days={days}")
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_recent_messages(email, max_results=20, days=days)

async def get_email_summary(user_id: str, email: Optional[str] = None, days: int = 7):
    """Get email summary with auto-fetch if needed"""
    logger.debug(f"📧 get_email_summary() called: user_id={user_id}, email={email}, days={days}")
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_email_summary(email, days)
