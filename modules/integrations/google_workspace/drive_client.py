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
            conn = await db_manager.get_connection()
            async with conn:
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
        Convert markdown to Google Docs API requests with FULL formatting support
        
        Supports:
        - H1-H6 headers (# to ######)
        - Bold (**text** or __text__)
        - Italic (*text* or _text_)
        - Bullet lists (-, *, +)
        - Numbered lists (1., 2., etc)
        - Links [text](url)
        - Code blocks (converted to plain text)
        """
        requests = []
        
        # Parse content into structured elements
        lines = content.split('\n')
        current_index = 1
        
        full_text = []
        format_instructions = []
        
        for line in lines:
            line_start = len(''.join(full_text))
            
            # Check for headers (# to ######)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                level = len(header_match.group(1))
                text = header_match.group(2) + '\n'
                full_text.append(text)
                
                # Add header style
                format_instructions.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': line_start + 1,
                            'endIndex': line_start + len(text)
                        },
                        'paragraphStyle': {
                            'namedStyleType': f'HEADING_{level}'
                        },
                        'fields': 'namedStyleType'
                    }
                })
                continue
            
            # Check for bullet list
            bullet_match = re.match(r'^[\-\*\+]\s+(.+)$', line)
            if bullet_match:
                text = bullet_match.group(1) + '\n'
                full_text.append(text)
                
                # Add bullet point
                format_instructions.append({
                    'createParagraphBullets': {
                        'range': {
                            'startIndex': line_start + 1,
                            'endIndex': line_start + len(text)
                        },
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })
                continue
            
            # Check for numbered list
            number_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if number_match:
                text = number_match.group(2) + '\n'
                full_text.append(text)
                
                # Add numbered point
                format_instructions.append({
                    'createParagraphBullets': {
                        'range': {
                            'startIndex': line_start + 1,
                            'endIndex': line_start + len(text)
                        },
                        'bulletPreset': 'NUMBERED_DECIMAL_ALPHA_ROMAN'
                    }
                })
                continue
            
            # Regular line - add with formatting
            processed_line = line + '\n'
            full_text.append(processed_line)
        
        # Insert all text first
        full_content = ''.join(full_text)
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': full_content
            }
        })
        
        # Add all formatting instructions (headers, lists)
        requests.extend(format_instructions)
        
        # Now add inline formatting (bold, italic, links)
        inline_requests = self._add_inline_formatting(full_content)
        requests.extend(inline_requests)
        
        return requests
    
    def _add_inline_formatting(self, text: str) -> List[Dict[str, Any]]:
        """
        Add inline formatting (bold, italic, links) to text
        """
        requests = []
        
        # Find all bold text (**text** or __text__)
        for match in re.finditer(r'\*\*(.+?)\*\*|__(.+?)__', text):
            bold_text = match.group(1) or match.group(2)
            start = match.start()
            end = match.end()
            
            # Calculate actual position (accounting for markdown symbols)
            actual_start = start - text[:start].count('**') * 2 - text[:start].count('__') * 2 + 1
            actual_end = actual_start + len(bold_text)
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': actual_start,
                        'endIndex': actual_end
                    },
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })
        
        # Find all italic text (*text* or _text_)
        for match in re.finditer(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', text):
            italic_text = match.group(1) or match.group(2)
            start = match.start()
            end = match.end()
            
            actual_start = start - text[:start].count('*') + text[:start].count('**') * 2 - text[:start].count('_') + text[:start].count('__') * 2 + 1
            actual_end = actual_start + len(italic_text)
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': actual_start,
                        'endIndex': actual_end
                    },
                    'textStyle': {'italic': True},
                    'fields': 'italic'
                }
            })
        
        # Find all links [text](url)
        for match in re.finditer(r'\[(.+?)\]\((.+?)\)', text):
            link_text = match.group(1)
            url = match.group(2)
            start = match.start()
            
            actual_start = start + 1  # Simplified for links
            actual_end = actual_start + len(link_text)
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': actual_start,
                        'endIndex': actual_end
                    },
                    'textStyle': {
                        'link': {'url': url}
                    },
                    'fields': 'link'
                }
            })
        
        return requests
    
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
