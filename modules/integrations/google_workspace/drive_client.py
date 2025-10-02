# modules/integrations/google_workspace/drive_client.py
"""
Drive Client - REFACTORED FOR AIOGOOGLE
Document creation with true async
"""

import logging
from typing import Dict, List, Optional, Any
import re

logger = logging.getLogger(__name__)

try:
    from aiogoogle import Aiogoogle
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False
    logger.warning("⚠️ aiogoogle not installed")

from .oauth_manager import get_aiogoogle_credentials, GoogleTokenExpiredError
from ...core.database import db_manager

class DriveClient:
    """Drive client with TRUE async"""
    
    def __init__(self):
        if not DRIVE_AVAILABLE:
            raise RuntimeError("aiogoogle required")
        
        self._user_id = None
        self._user_creds = None
        logger.info("📄 Drive client initialized (aiogoogle)")
    
    async def initialize(self, user_id: str):
        try:
            self._user_id = user_id
            self._user_creds = await get_aiogoogle_credentials(user_id, None)
            
            if not self._user_creds:
                raise Exception("No valid credentials")
            
            logger.info("✅ Drive initialized")
            
        except Exception as e:
            logger.error(f"❌ Drive init failed: {e}")
            raise
    
    async def create_document(self, title: str, content: str,
                            chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create Google Doc - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            logger.info(f"📄 Creating Doc: {title}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                docs_v1 = await aiogoogle.discover('docs', 'v1')
                
                # Create empty document
                doc = await aiogoogle.as_user(
                    docs_v1.documents.create(
                        json={'title': title}
                    )
                )
                
                doc_id = doc['documentId']
                
                # Convert markdown to Google Docs requests
                requests = self._markdown_to_docs_requests(content)
                
                if requests:
                    # Apply formatting
                    await aiogoogle.as_user(
                        docs_v1.documents.batchUpdate(
                            documentId=doc_id,
                            json={'requests': requests}
                        )
                    )
                
                doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                
                # Store in database
                await self._store_document_info(
                    doc_id, title, 'document', doc_url,
                    chat_thread_id, len(content)
                )
                
                logger.info(f"✅ Created Doc: {title}")
                
                return {
                    'id': doc_id,
                    'title': title,
                    'url': doc_url,
                    'type': 'document'
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to create document: {e}")
            raise
    
    async def create_spreadsheet(self, title: str, data: List[List[Any]],
                                chat_thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create Google Sheet - TRULY ASYNC
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            logger.info(f"📊 Creating Sheet: {title}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                sheets_v4 = await aiogoogle.discover('sheets', 'v4')
                
                # Create spreadsheet
                spreadsheet = await aiogoogle.as_user(
                    sheets_v4.spreadsheets.create(
                        json={'properties': {'title': title}}
                    )
                )
                
                spreadsheet_id = spreadsheet['spreadsheetId']
                
                # Add data if provided
                if data:
                    await aiogoogle.as_user(
                        sheets_v4.spreadsheets.values.update(
                            spreadsheetId=spreadsheet_id,
                            range='A1',
                            valueInputOption='RAW',
                            json={'values': data}
                        )
                    )
                
                sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                
                # Store in database
                await self._store_document_info(
                    spreadsheet_id, title, 'spreadsheet', sheet_url,
                    chat_thread_id, len(str(data))
                )
                
                logger.info(f"✅ Created Sheet: {title}")
                
                return {
                    'id': spreadsheet_id,
                    'title': title,
                    'url': sheet_url,
                    'type': 'spreadsheet'
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to create spreadsheet: {e}")
            raise
    
    def _markdown_to_docs_requests(self, content: str) -> List[Dict[str, Any]]:
        """
        Convert markdown to Google Docs API requests
        """
        requests = []
        
        # Insert text first
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': self._strip_markdown(content)
            }
        })
        
        return requests
    
    def _strip_markdown(self, text: str) -> str:
    """Remove markdown formatting"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)  # ← This line is probably broken
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    return text
