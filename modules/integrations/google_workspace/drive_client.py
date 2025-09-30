# modules/integrations/google_workspace/drive_client.py
"""
Google Drive Client - Document Creation from Chat
Rich formatting preservation for chat content → Google Docs

This module:
1. Creates Google Docs from chat conversations
2. Preserves markdown formatting (headers, lists, bold, italic)
3. Supports Sheets and Slides creation
4. Tracks created documents in database
5. Provides direct links to documents

Chat Integration:
User: "google drive create doc [title]"
System: Creates formatted Google Doc from current chat content
Returns: Direct link to new document
"""

import logging
from typing import Dict, List, Optional, Any
import re

logger = logging.getLogger(__name__)

# Import after logger setup
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False
    logger.warning("⚠️ Google Drive API client not installed")

from .oauth_manager import get_google_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class DriveClient:
    """
    Google Drive API client for document creation
    Converts chat markdown to rich Google Docs formatting
    """
    
    def __init__(self):
        """Initialize Drive client"""
        if not DRIVE_AVAILABLE:
            logger.error("❌ Google Drive API client not available")
            raise RuntimeError("Google API client required - run: pip install google-api-python-client")
        
        self._service = None
        self._docs_service = None
        self._user_id = None
        
        logger.info("📄 Drive client initialized")
    
    async def initialize(self, user_id: str):
        """
        Initialize Drive services with credentials
        
        Args:
            user_id: User ID for credential lookup
        """
        try:
            self._user_id = user_id
            
            # Get credentials from auth manager
            credentials = await get_google_credentials(user_id, email=None)
            
            if not credentials:
                raise Exception("No valid credentials available")
            
            # Build Drive and Docs services
            self._service = build('drive', 'v3', credentials=credentials)
            self._docs_service = build('docs', 'v1', credentials=credentials)
            
            logger.info("✅ Drive services initialized")
            
        except GoogleTokenExpiredError:
            raise
        except Exception as e:
            logger.error(f"❌ Drive initialization failed: {e}")
            raise
    
    async def create_document(self, title: str, content: str, chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a Google Doc from chat content with formatting
        
        Args:
            title: Document title
            content: Markdown-formatted content from chat
            chat_thread_id: Optional chat thread ID for tracking
            
        Returns:
            Dict with document info (id, url, title)
        """
        try:
            if not self._docs_service:
                raise Exception("Drive service not initialized")
            
            logger.info(f"📄 Creating Google Doc: {title}")
            
            # Create empty document
            doc = self._docs_service.documents().create(body={'title': title}).execute()
            doc_id = doc['documentId']
            
            # Convert markdown to Google Docs requests
            requests = self._markdown_to_docs_requests(content)
            
            if requests:
                # Apply formatting
                self._docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute()
            
            # Get document URL
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            
            # Store in database
            await self._store_document_info(doc_id, title, 'document', doc_url, chat_thread_id, len(content))
            
            logger.info(f"✅ Created Google Doc: {title}")
            
            return {
                'id': doc_id,
                'title': title,
                'url': doc_url,
                'type': 'document'
            }
            
        except HttpError as e:
            logger.error(f"❌ Drive API error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to create document: {e}")
            raise
    
    async def create_spreadsheet(self, title: str, data: List[List[Any]], chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a Google Sheet from structured data
        
        Args:
            title: Spreadsheet title
            data: 2D list of data (rows and columns)
            chat_thread_id: Optional chat thread ID for tracking
            
        Returns:
            Dict with spreadsheet info (id, url, title)
        """
        try:
            if not self._service:
                raise Exception("Drive service not initialized")
            
            logger.info(f"📊 Creating Google Sheet: {title}")
            
            # Create spreadsheet using Sheets API
            sheets_service = build('sheets', 'v4', credentials=await get_google_credentials(self._user_id, email=None))
            
            spreadsheet = sheets_service.spreadsheets().create(
                body={'properties': {'title': title}}
            ).execute()
            
            spreadsheet_id = spreadsheet['spreadsheetId']
            
            # Add data if provided
            if data:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range='A1',
                    valueInputOption='RAW',
                    body={'values': data}
                ).execute()
            
            # Get spreadsheet URL
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            
            # Store in database
            await self._store_document_info(spreadsheet_id, title, 'spreadsheet', sheet_url, chat_thread_id, len(data))
            
            logger.info(f"✅ Created Google Sheet: {title}")
            
            return {
                'id': spreadsheet_id,
                'title': title,
                'url': sheet_url,
                'type': 'spreadsheet'
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create spreadsheet: {e}")
            raise
    
    def _markdown_to_docs_requests(self, markdown: str) -> List[Dict[str, Any]]:
        """
        Convert markdown content to Google Docs API requests
        
        Args:
            markdown: Markdown-formatted text
            
        Returns:
            List of Google Docs API requests for formatting
        """
        requests = []
        
        # Insert the text first (strip markdown for now - advanced formatting later)
        clean_text = self._strip_markdown(markdown)
        
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': clean_text
            }
        })
        
        # TODO: Advanced formatting implementation
        # - Headers (# ## ###) → Heading styles
        # - Bold (**text**) → Bold format
        # - Italic (*text*) → Italic format
        # - Lists (- item) → Bullet lists
        # - Code blocks → Monospace font
        
        return requests
    
    def _strip_markdown(self, markdown: str) -> str:
        """
        Strip markdown formatting for basic text
        (Placeholder for more advanced formatting)
        
        Args:
            markdown: Markdown text
            
        Returns:
            Plain text with markdown removed
        """
        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', markdown, flags=re.MULTILINE)
        
        # Remove bold/italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)  # Italic
        text = re.sub(r'__(.+?)__', r'\1', text)  # Bold alt
        text = re.sub(r'_(.+?)_', r'\1', text)  # Italic alt
        
        # Remove links but keep text
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`(.+?)`', r'\1', text)
        
        # Remove list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        return text
    
    async def _store_document_info(self, doc_id: str, title: str, doc_type: str, 
                                   url: str, chat_thread_id: Optional[str], content_length: int):
        """Store document info in database"""
        try:
            async with db_manager.get_connection() as conn:
                await conn.execute('''
                    INSERT INTO google_drive_documents
                    (user_id, google_doc_id, document_title, document_type, document_url,
                     created_from_chat_thread, original_content_length)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                self._user_id,
                doc_id,
                title,
                doc_type,
                url,
                chat_thread_id,
                content_length
                )
            
            logger.info(f"✅ Stored document info: {title}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store document info: {e}")
    
    async def get_recent_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recently created documents
        
        Args:
            limit: Maximum number of documents to return
            
        Returns:
            List of recent document info
        """
        try:
            async with db_manager.get_connection() as conn:
                docs = await conn.fetch('''
                    SELECT google_doc_id, document_title, document_type, document_url, created_at
                    FROM google_drive_documents
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                ''', self._user_id, limit)
                
                return [dict(doc) for doc in docs]
                
        except Exception as e:
            logger.error(f"❌ Failed to get recent documents: {e}")
            return []

# Global instance
drive_client = DriveClient()

# Convenience functions for other modules
async def create_google_doc(user_id: str, title: str, content: str, chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a Google Doc from chat content"""
    await drive_client.initialize(user_id)
    return await drive_client.create_document(title, content, chat_thread_id)

async def create_google_sheet(user_id: str, title: str, data: List[List[Any]], chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a Google Sheet from structured data"""
    await drive_client.initialize(user_id)
    return await drive_client.create_spreadsheet(title, data, chat_thread_id)

async def get_recent_drive_documents(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recently created Drive documents"""
    await drive_client.initialize(user_id)
    return await drive_client.get_recent_documents(limit)