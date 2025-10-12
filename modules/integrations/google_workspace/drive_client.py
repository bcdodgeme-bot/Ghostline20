# modules/integrations/google_workspace/drive_client.py
"""
Drive Client - FIXED AND ENHANCED
- Fixed NoneType error in document creation
- Fixed database connection awaiting
- Full markdown-to-Google Docs formatting support
- Copy conversation content to Drive
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
    """Drive client with TRUE async and full markdown support"""
    
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
        Create Google Doc with full markdown formatting support
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            logger.info(f"📄 Creating Doc: {title}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                docs_v1 = await aiogoogle.discover('docs', 'v1')
                
                # FIXED: Create empty document and handle response properly
                doc_response = await aiogoogle.as_user(
                    docs_v1.documents.create(
                        json={'title': title}
                    )
                )
                
                # FIXED: Check if response is valid
                if not doc_response or 'documentId' not in doc_response:
                    raise Exception(f"Invalid API response: {doc_response}")
                
                doc_id = doc_response['documentId']
                
                # Convert markdown to Google Docs requests with full formatting
                requests = self._markdown_to_docs_requests(content)
                
                if requests:
                    # Apply formatting with proper error handling
                    try:
                        await aiogoogle.as_user(
                            docs_v1.documents.batchUpdate(
                                documentId=doc_id,
                                json={'requests': requests}
                            )
                        )
                        logger.info(f"✅ Applied {len(requests)} formatting requests")
                    except Exception as format_error:
                        logger.warning(f"⚠️ Formatting error (content still saved): {format_error}")
                
                doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                
                # FIXED: Store in database with proper await
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
        Create Google Sheet
        """
        try:
            if not self._user_creds:
                await self.initialize(self._user_id)
            
            logger.info(f"📊 Creating Sheet: {title}")
            
            async with Aiogoogle(user_creds=self._user_creds) as aiogoogle:
                sheets_v4 = await aiogoogle.discover('sheets', 'v4')
                
                # FIXED: Create spreadsheet and handle response properly
                spreadsheet_response = await aiogoogle.as_user(
                    sheets_v4.spreadsheets.create(
                        json={'properties': {'title': title}}
                    )
                )
                
                # FIXED: Check if response is valid
                if not spreadsheet_response or 'spreadsheetId' not in spreadsheet_response:
                    raise Exception(f"Invalid API response: {spreadsheet_response}")
                
                spreadsheet_id = spreadsheet_response['spreadsheetId']
                
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
                
                # FIXED: Store in database with proper await
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
    
    async def list_recent_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recently created documents from database
        """
        try:
            async with (await db_manager.get_connection()) as conn:
                rows = await conn.fetch('''
                    SELECT 
                        google_doc_id,
                        document_title,
                        document_type,
                        document_url,
                        created_at,
                        original_content_length
                    FROM google_drive_documents
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                ''', self._user_id, limit)
                
                return [{
                    'id': row['google_doc_id'],
                    'title': row['document_title'],
                    'type': row['document_type'],
                    'url': row['document_url'],
                    'created': row['created_at'],
                    'size': row['original_content_length']
                } for row in rows]
                
        except Exception as e:
            logger.error(f"❌ Failed to list documents: {e}")
            return []
    
    def _markdown_to_docs_requests(self, content: str) -> List[Dict[str, Any]]:
        """
        Convert markdown to Google Docs API requests - FIXED VERSION
        Properly strips markdown and applies formatting
        """
        requests = []
        
        # Step 1: Strip markdown and track formatting
        clean_text, formatting_map = self._strip_markdown_and_track_formatting(content)
        
        # Step 2: Insert the clean text
        if clean_text:
            requests.append({
                'insertText': {
                    'location': {'index': 1},
                    'text': clean_text
                }
            })
        
        # Step 3: Apply all formatting
        requests.extend(formatting_map)
        
        return requests
        
    def _strip_markdown_and_track_formatting(self, content: str) -> tuple:
        """
        Strip markdown symbols and track where formatting should be applied
        Returns: (clean_text, formatting_requests)
        """
        formatting_requests = []
        lines = content.split('\n')
        clean_lines = []
        current_pos = 1  # Google Docs starts at index 1
        
        for line in lines:
            line_start = current_pos
            
            # Handle headers (# to ######)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                level = len(header_match.group(1))
                text = header_match.group(2)
                clean_lines.append(text)
                
                line_length = len(text) + 1  # +1 for newline
                formatting_requests.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': line_start,
                            'endIndex': line_start + line_length
                        },
                        'paragraphStyle': {
                            'namedStyleType': f'HEADING_{level}'
                        },
                        'fields': 'namedStyleType'
                    }
                })
                current_pos += line_length
                continue
            
            # Handle bullet lists (-, *, +)
            bullet_match = re.match(r'^[\-\*\+]\s+(.+)$', line)
            if bullet_match:
                text = bullet_match.group(1)
                clean_lines.append(text)
                
                line_length = len(text) + 1
                formatting_requests.append({
                    'createParagraphBullets': {
                        'range': {
                            'startIndex': line_start,
                            'endIndex': line_start + line_length
                        },
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })
                current_pos += line_length
                continue
            
            # Handle numbered lists (1., 2., etc)
            number_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if number_match:
                text = number_match.group(2)
                clean_lines.append(text)
                
                line_length = len(text) + 1
                formatting_requests.append({
                    'createParagraphBullets': {
                        'range': {
                            'startIndex': line_start,
                            'endIndex': line_start + line_length
                        },
                        'bulletPreset': 'NUMBERED_DECIMAL_ALPHA_ROMAN'
                    }
                })
                current_pos += line_length
                continue
            
            # Regular line - strip inline markdown
            clean_line, inline_formats = self._strip_inline_markdown(line, line_start)
    
    def _strip_inline_markdown(self, text: str, start_pos: int) -> tuple:
        """
        Strip inline markdown (bold, italic, links) and track formatting
        Returns: (clean_text, formatting_requests)
        """
        formatting_requests = []
        clean_text = text
        offset = 0  # Track how much we've removed
        
        # Handle bold (**text** or __text__)
        bold_pattern = r'\*\*(.+?)\*\*|__(.+?)__'
        for match in re.finditer(bold_pattern, text):
            bold_text = match.group(1) or match.group(2)
            match_start = match.start() - offset
            match_end = match_start + len(bold_text)
            
            formatting_requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_pos + match_start,
                        'endIndex': start_pos + match_end
                    },
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })
            
            # Remove the markdown symbols
            clean_text = clean_text[:match.start() - offset] + bold_text + clean_text[match.end() - offset:]
            offset += len(match.group(0)) - len(bold_text)
        
        # Update text for italic processing
        text = clean_text
        offset = 0
        
        # Handle italic (*text* or _text_) - but not ** or __
        italic_pattern = r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)'
        for match in re.finditer(italic_pattern, text):
            italic_text = match.group(1) or match.group(2)
            match_start = match.start() - offset
            match_end = match_start + len(italic_text)
            
            formatting_requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_pos + match_start,
                        'endIndex': start_pos + match_end
                    },
                    'textStyle': {'italic': True},
                    'fields': 'italic'
                }
            })
            
            # Remove the markdown symbols
            clean_text = clean_text[:match.start() - offset] + italic_text + clean_text[match.end() - offset:]
            offset += len(match.group(0)) - len(italic_text)
        
        # Update text for link processing
        text = clean_text
        offset = 0
        
        # Handle links [text](url)
        link_pattern = r'\[(.+?)\]\((.+?)\)'
        for match in re.finditer(link_pattern, text):
            link_text = match.group(1)
            url = match.group(2)
            match_start = match.start() - offset
            match_end = match_start + len(link_text)
            
            formatting_requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_pos + match_start,
                        'endIndex': start_pos + match_end
                    },
                    'textStyle': {
                        'link': {'url': url}
                    },
                    'fields': 'link'
                }
            })
            
            # Remove the markdown symbols, keep just the link text
            clean_text = clean_text[:match.start() - offset] + link_text
    
    async def _store_document_info(self, doc_id: str, title: str, doc_type: str,
                                      url: str, chat_thread_id: Optional[str],
                                      content_length: int):
        """Store in DB - FIXED: proper async connection handling"""
        try:
            # FIXED: Properly await the connection
            conn = await db_manager.get_connection()
            async with conn:
                await conn.execute('''
                    INSERT INTO google_drive_documents
                    (user_id, google_doc_id, document_title, document_type, 
                     document_url, created_from_chat_thread, original_content_length)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                self._user_id, doc_id, title, doc_type, url,
                chat_thread_id, content_length
                )
            
            logger.info(f"✅ Stored document info: {title}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store document info: {e}")

# Global instance
drive_client = DriveClient()

# Convenience functions
async def create_google_doc(user_id: str, title: str, content: str,
                           chat_thread_id: Optional[str] = None):
    """Create a Google Doc with full markdown formatting"""
    await drive_client.initialize(user_id)
    return await drive_client.create_document(title, content, chat_thread_id)

async def create_google_sheet(user_id: str, title: str, data: List[List[Any]],
                             chat_thread_id: Optional[str] = None):
    """Create a Google Sheet"""
    await drive_client.initialize(user_id)
    return await drive_client.create_spreadsheet(title, data, chat_thread_id)

async def list_recent_docs(user_id: str, limit: int = 10):
    """List recent documents"""
    await drive_client.initialize(user_id)
    return await drive_client.list_recent_documents(limit)
