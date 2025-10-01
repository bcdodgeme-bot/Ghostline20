# modules/integrations/google_workspace/gmail_client.py
"""
Gmail Client - Multi-Account Email Intelligence
Privacy-First Email Analysis with Personality-Driven Summaries

This module:
1. Analyzes emails across multiple accounts (service account + OAuth)
2. Classifies by priority, category, and sentiment
3. Generates AI-powered response suggestions
4. Creates email drafts with personality integration
5. Respects privacy (metadata only, 30-day retention)

Privacy Philosophy:
- NO email content stored in database
- Metadata only (sender, subject, date, labels)
- Analysis results stored, not content
- 30-day retention for privacy
- User controls what gets analyzed

Email Intelligence:
- Priority detection (urgent/high/normal/low)
- Category classification (business/personal/marketing/social)
- Sentiment analysis (positive/neutral/negative)
- Response suggestions via AI personality system
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import base64
import re

logger = logging.getLogger(__name__)

# Import after logger setup
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("⚠️ Gmail API client not installed")

from .oauth_manager import get_google_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class GmailClient:
    """
    Gmail API client with multi-account email intelligence
    Privacy-first approach with metadata-only storage
    """
    
    def __init__(self):
        """Initialize Gmail client"""
        if not GMAIL_AVAILABLE:
            logger.error("❌ Gmail API client not available")
            raise RuntimeError("Gmail API client required - run: pip install google-api-python-client")
        
        self._services = {}  # email -> service instance
        self._user_id = None
        
        logger.info("📧 Gmail client initialized")
    
    async def initialize(self, user_id: str, email: Optional[str] = None):
        """
        Initialize Gmail service with credentials
        
        Args:
            user_id: User ID for credential lookup
            email: Specific email account, or None for service account
        """
        try:
            self._user_id = user_id
            
            # Get credentials from auth manager
            credentials = await get_google_credentials(user_id, email)
            
            if not credentials:
                raise Exception("No valid credentials available")
            
            # Build Gmail service
            service = build('gmail', 'v1', credentials=credentials)
            
            # Cache service by email
            account_key = email or 'service_account'
            self._services[account_key] = service
            
            logger.info(f"✅ Gmail service initialized for {account_key}")
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Gmail initialization failed: {e}")
            raise
    
    async def get_recent_messages(self, email: Optional[str] = None,
                                  max_results: int = 20,
                                  days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent email messages with metadata
        
        Args:
            email: Email account to check (None for service account)
            max_results: Maximum number of messages to retrieve
            days: Number of days to look back
            
        Returns:
            List of email metadata dictionaries
        """
        try:
            account_key = email or 'service_account'
            
            if account_key not in self._services:
                await self.initialize(self._user_id, email)
            
            service = self._services[account_key]
            
            # Calculate date query
            after_date = datetime.now() - timedelta(days=days)
            query = f"after:{int(after_date.timestamp())}"
            
            logger.info(f"📧 Fetching recent messages for {account_key}...")
            
            # Get message list
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                logger.info(f"ℹ️ No recent messages found for {account_key}")
                return []
            
            # Get message details
            detailed_messages = []
            
            for msg in messages:
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'To', 'Subject', 'Date']
                ).execute()
                
                # Extract metadata
                headers = {h['name']: h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}
                
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
            
            logger.info(f"✅ Retrieved {len(detailed_messages)} messages for {account_key}")
            
            return detailed_messages
            
        except HttpError as e:
            logger.error(f"❌ Gmail API error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Failed to get recent messages: {e}")
            return []
    
    async def analyze_email(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze email and classify priority, category, sentiment
        
        Args:
            message: Email metadata dictionary
            
        Returns:
            Analysis results
        """
        try:
            analysis = {
                'message_id': message['id'],
                'priority_level': self._detect_priority(message),
                'category': self._classify_category(message),
                'sentiment': self._analyze_sentiment(message),
                'requires_response': self._needs_response(message),
                'sender_email': self._extract_email(message['from']),
                'subject_line': message['subject']
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Failed to analyze email: {e}")
            return {}
    
    def _detect_priority(self, message: Dict[str, Any]) -> str:
        """Detect email priority level"""
        subject = message.get('subject', '').lower()
        snippet = message.get('snippet', '').lower()
        labels = message.get('labels', [])
        
        # Urgent indicators
        urgent_keywords = ['urgent', 'asap', 'immediate', 'emergency', 'critical', 'important']
        if any(keyword in subject or keyword in snippet for keyword in urgent_keywords):
            return 'urgent'
        
        # High priority indicators
        if 'IMPORTANT' in labels:
            return 'high'
        
        high_keywords = ['deadline', 'today', 'meeting', 'call', 'review', 'approval']
        if any(keyword in subject for keyword in high_keywords):
            return 'high'
        
        # Low priority indicators
        if 'CATEGORY_PROMOTIONS' in labels or 'CATEGORY_SOCIAL' in labels:
            return 'low'
        
        return 'normal'
    
    def _classify_category(self, message: Dict[str, Any]) -> str:
        """Classify email category"""
        labels = message.get('labels', [])
        subject = message.get('subject', '').lower()
        from_email = message.get('from', '').lower()
        
        # Gmail's built-in categories
        if 'CATEGORY_PROMOTIONS' in labels:
            return 'marketing'
        if 'CATEGORY_SOCIAL' in labels:
            return 'social'
        if 'CATEGORY_UPDATES' in labels:
            return 'updates'
        if 'CATEGORY_FORUMS' in labels:
            return 'forums'
        
        # Business indicators
        business_keywords = ['project', 'meeting', 'client', 'proposal', 'contract', 'invoice']
        if any(keyword in subject for keyword in business_keywords):
            return 'business'
        
        # Check for common business domains
        if any(domain in from_email for domain in ['.com', '.org', '.io', '.co']):
            return 'business'
        
        return 'personal'
    
    def _analyze_sentiment(self, message: Dict[str, Any]) -> str:
        """Analyze email sentiment (basic keyword-based)"""
        subject = message.get('subject', '').lower()
        snippet = message.get('snippet', '').lower()
        
        # Positive indicators
        positive_keywords = ['thank', 'great', 'excellent', 'appreciate', 'congratulations', 'love', 'perfect']
        positive_score = sum(1 for keyword in positive_keywords if keyword in subject or keyword in snippet)
        
        # Negative indicators
        negative_keywords = ['problem', 'issue', 'concern', 'complaint', 'error', 'failed', 'wrong', 'disappointed']
        negative_score = sum(1 for keyword in negative_keywords if keyword in subject or keyword in snippet)
        
        if positive_score > negative_score:
            return 'positive'
        elif negative_score > positive_score:
            return 'negative'
        else:
            return 'neutral'
    
    def _needs_response(self, message: Dict[str, Any]) -> bool:
        """Determine if email needs a response"""
        subject = message.get('subject', '').lower()
        snippet = message.get('snippet', '').lower()
        labels = message.get('labels', [])
        
        # Auto-responses and newsletters don't need replies
        if 'CATEGORY_PROMOTIONS' in labels or 'noreply' in message.get('from', '').lower():
            return False
        
        # Questions need responses
        question_indicators = ['?', 'can you', 'could you', 'would you', 'please', 'need', 'help']
        if any(indicator in subject or indicator in snippet for indicator in question_indicators):
            return True
        
        # FYI emails don't need responses
        if 'fyi' in subject or 'for your information' in subject:
            return False
        
        return True
    
    def _extract_email(self, from_field: str) -> str:
        """Extract email address from 'From' field"""
        match = re.search(r'<(.+?)>', from_field)
        if match:
            return match.group(1)
        
        # If no brackets, assume entire field is email
        if '@' in from_field:
            return from_field.strip()
        
        return 'unknown@example.com'
    
    async def generate_response_suggestion(self, message: Dict[str, Any],
                                          analysis: Dict[str, Any],
                                          personality: str = 'syntax') -> str:
        """
        Generate AI-powered response suggestion
        
        Args:
            message: Email metadata
            analysis: Email analysis results
            personality: AI personality to use
            
        Returns:
            Suggested response text
        """
        try:
            # Build context for AI
            context = f"""
Email Analysis:
From: {message.get('from', 'Unknown')}
Subject: {message.get('subject', 'No subject')}
Category: {analysis.get('category', 'unknown')}
Priority: {analysis.get('priority_level', 'normal')}
Sentiment: {analysis.get('sentiment', 'neutral')}

Snippet: {message.get('snippet', '')}

Generate a brief, professional response suggestion for this email.
"""
            
            # TODO: Integrate with AI personality system
            # For now, return a template-based suggestion
            
            if analysis.get('sentiment') == 'positive':
                suggestion = f"Thank you for your email regarding {message.get('subject', 'your message')}. I appreciate your feedback and will get back to you shortly."
            elif analysis.get('sentiment') == 'negative':
                suggestion = f"Thank you for bringing this to my attention. I understand your concern about {message.get('subject', 'this issue')} and I'm looking into it right away."
            else:
                suggestion = f"Thank you for your email about {message.get('subject', 'your message')}. I'll review this and respond soon."
            
            return suggestion
            
        except Exception as e:
            logger.error(f"❌ Failed to generate response suggestion: {e}")
            return "Thank you for your email. I'll respond shortly."
    
    async def create_draft(self, email: Optional[str], to: str,
                          subject: str, body: str) -> Dict[str, Any]:
        """
        Create an email draft
        
        Args:
            email: Account to create draft in (None for service account)
            to: Recipient email
            subject: Email subject
            body: Email body
            
        Returns:
            Draft info dict
        """
        try:
            account_key = email or 'service_account'
            
            if account_key not in self._services:
                await self.initialize(self._user_id, email)
            
            service = self._services[account_key]
            
            # Create message
            message = f"To: {to}\nSubject: {subject}\n\n{body}"
            encoded_message = base64.urlsafe_b64encode(message.encode()).decode()
            
            # Create draft
            draft = service.users().drafts().create(
                userId='me',
                body={'message': {'raw': encoded_message}}
            ).execute()
            
            logger.info(f"✅ Created draft in {account_key}")
            
            return {
                'id': draft['id'],
                'message_id': draft['message']['id'],
                'to': to,
                'subject': subject
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create draft: {e}")
            raise
    
    async def store_analysis(self, email_account: str, analysis: Dict[str, Any]):
        """
        Store email analysis in database (metadata only)
        
        Args:
            email_account: Email account
            analysis: Analysis results
        """
        try:
            # Extract email date from message
            email_date = datetime.now()  # Would parse from message in production
            
            conn = await db_manager.get_connection()
            try:
                await conn.execute('''
                    INSERT INTO google_gmail_analysis
                    (user_id, email_account, message_id, thread_id, sender_email,
                     subject_line, priority_level, category, sentiment, requires_response,
                     email_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (message_id) DO UPDATE SET
                        priority_level = EXCLUDED.priority_level,
                        category = EXCLUDED.category,
                        sentiment = EXCLUDED.sentiment,
                        requires_response = EXCLUDED.requires_response
                ''',
                self._user_id,
                email_account,
                analysis.get('message_id'),
                analysis.get('thread_id', ''),
                analysis.get('sender_email'),
                analysis.get('subject_line'),
                analysis.get('priority_level'),
                analysis.get('category'),
                analysis.get('sentiment'),
                analysis.get('requires_response', False),
                email_date
                )
            finally:
                await db_manager.release_connection(conn)
            
            logger.info(f"✅ Stored email analysis for {email_account}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store email analysis: {e}")
    
    async def get_email_summary(self, email: Optional[str] = None,
                               days: int = 7) -> Dict[str, Any]:
        """
        Get personality-driven email summary
        
        Args:
            email: Email account (None for all)
            days: Number of days to summarize
            
        Returns:
            Email summary with statistics and highlights
        """
        try:
            conn = await db_manager.get_connection()
            try:
                if email:
                    # Single account summary
                    stats = await conn.fetchrow('''
                        SELECT 
                            COUNT(*) as total_emails,
                            SUM(CASE WHEN priority_level = 'urgent' THEN 1 ELSE 0 END) as urgent,
                            SUM(CASE WHEN priority_level = 'high' THEN 1 ELSE 0 END) as high_priority,
                            SUM(CASE WHEN requires_response THEN 1 ELSE 0 END) as needs_response,
                            SUM(CASE WHEN category = 'business' THEN 1 ELSE 0 END) as business,
                            SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_sentiment
                        FROM google_gmail_analysis
                        WHERE user_id = $1 
                            AND email_account = $2
                            AND analyzed_at >= NOW() - INTERVAL '$3 days'
                    ''', self._user_id, email, days)
                else:
                    # All accounts summary
                    stats = await conn.fetchrow('''
                        SELECT 
                            COUNT(*) as total_emails,
                            SUM(CASE WHEN priority_level = 'urgent' THEN 1 ELSE 0 END) as urgent,
                            SUM(CASE WHEN priority_level = 'high' THEN 1 ELSE 0 END) as high_priority,
                            SUM(CASE WHEN requires_response THEN 1 ELSE 0 END) as needs_response,
                            SUM(CASE WHEN category = 'business' THEN 1 ELSE 0 END) as business,
                            SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_sentiment
                        FROM google_gmail_analysis
                        WHERE user_id = $1
                            AND analyzed_at >= NOW() - INTERVAL '$2 days'
                    ''', self._user_id, days)
                
                summary = {
                    'total_emails': stats['total_emails'] or 0,
                    'urgent': stats['urgent'] or 0,
                    'high_priority': stats['high_priority'] or 0,
                    'needs_response': stats['needs_response'] or 0,
                    'business': stats['business'] or 0,
                    'negative_sentiment': stats['negative_sentiment'] or 0,
                    'days': days
                }
                
                return summary
            finally:
                await db_manager.release_connection(conn)
                
        except Exception as e:
            logger.error(f"❌ Failed to get email summary: {e}")
            return {}

# Global instance
gmail_client = GmailClient()

# Convenience functions for other modules
async def get_recent_emails(user_id: str, email: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
    """Get recent emails with analysis"""
    await gmail_client.initialize(user_id, email)
    messages = await gmail_client.get_recent_messages(email, max_results=20, days=days)
    
    analyzed = []
    for msg in messages:
        analysis = await gmail_client.analyze_email(msg)
        analyzed.append({**msg, 'analysis': analysis})
    
    return analyzed

async def get_email_summary(user_id: str, email: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
    """Get email summary with personality"""
    await gmail_client.initialize(user_id, email)
    return await gmail_client.get_email_summary(email, days)

async def create_email_draft(user_id: str, email: Optional[str], to: str, subject: str, body: str) -> Dict[str, Any]:
    """Create an email draft"""
    await gmail_client.initialize(user_id, email)
    return await gmail_client.create_draft(email, to, subject, body)
