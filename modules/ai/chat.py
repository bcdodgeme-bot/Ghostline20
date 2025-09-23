# modules/ai/chat.py
# AI Chat Router for Syntax Prime V2
# Clean, sectioned chat endpoint with file upload support
# Date: 9/23/25

#-- Section 1: Core Imports - 9/23/25
import os
import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
import logging

# File processing imports
from PIL import Image, ImageOps
import pdfplumber
import pandas as pd
import magic
import cv2
import numpy as np
from io import BytesIO
import base64

#-- Section 2: Internal Module Imports - 9/23/25
from modules.core.database import db_manager
from modules.ai.personality_engine import get_personality_engine
from modules.ai.openrouter_client import get_openrouter_client
from modules.ai.conversation_manager import get_memory_manager
from modules.ai.knowledge_query import get_knowledge_engine

#-- Section 3: Request/Response Models - 9/23/25
class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None

class ChatRequest(BaseModel):
    message: str
    personality_id: Optional[str] = 'syntaxprime'
    thread_id: Optional[str] = None
    include_knowledge: Optional[bool] = True
    stream: Optional[bool] = False

class BookmarkRequest(BaseModel):
    message_id: str
    bookmark_name: str
    thread_id: str

class ChatResponse(BaseModel):
    message_id: str
    thread_id: str
    response: str
    personality_used: str
    response_time_ms: int
    knowledge_sources: List[Dict] = []
    timestamp: datetime

#-- Section 4: Router Setup - 9/23/25
#-- Section 4: Router Setup - 9/23/25
router = APIRouter(prefix="/ai", tags=["AI Chat"])
logger = logging.getLogger(__name__)

# File upload configuration - FIXED for Docker permissions
UPLOAD_DIR = Path("/home/app/uploads/chat_files")  # Use user's home directory
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.txt', '.md', '.csv'}

# Create upload directory safely (not at import time)
def ensure_upload_dir():
    """Ensure upload directory exists with proper error handling"""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except PermissionError as e:
        logger.error(f"Cannot create upload directory: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error creating upload directory: {e}")
        return False

# Call this function instead of doing it at import time
_upload_dir_created = False

def get_upload_dir():
    """Get upload directory, creating it if necessary"""
    global _upload_dir_created
    if not _upload_dir_created:
        _upload_dir_created = ensure_upload_dir()
    return UPLOAD_DIR if _upload_dir_created else None

#-- Section 5: Helper Functions - 9/23/25
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    # TODO: Implement proper authentication
    return "temp-user-id"

async def process_uploaded_files(files: List[UploadFile]) -> List[Dict]:
    """Process uploaded files and return file information"""
    processed_files = []
    
    for file in files:
        if not file.filename:
            continue
            
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Validate file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} too large. Max size: 10MB"
            )
        
        # Save file with unique name
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Analyze file content (basic)
        file_info = {
            'file_id': file_id,
            'filename': file.filename,
            'file_type': file_ext,
            'file_size': len(content),
            'file_path': str(file_path),
            'analysis': await analyze_file_content(file_path, file_ext)
        }
        
        processed_files.append(file_info)
        
        # Reset file pointer for potential reuse
        await file.seek(0)
    
    return processed_files

async def analyze_file_content(file_path: Path, file_type: str) -> Dict:
    """
    Comprehensive file analysis with real processing capabilities
    """
    analysis = {
        'type': 'unknown',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        if file_type in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
            analysis.update(await analyze_image_file(file_path))
            
        elif file_type == '.pdf':
            analysis.update(await analyze_pdf_file(file_path))
            
        elif file_type in ['.txt', '.md']:
            analysis.update(await analyze_text_file(file_path))
            
        elif file_type == '.csv':
            analysis.update(await analyze_csv_file(file_path))
            
        else:
            analysis['description'] = f"Unsupported file type: {file_type}"
            
    except Exception as e:
        logger.error(f"File analysis failed for {file_path}: {e}")
        analysis['description'] = f"Analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

async def analyze_image_file(file_path: Path) -> Dict:
    """
    Advanced image analysis including OCR, object detection, and metadata
    """
    analysis = {
        'type': 'image',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        # Open and analyze image
        with Image.open(file_path) as img:
            # Basic image metadata
            analysis['metadata'] = {
                'format': img.format,
                'mode': img.mode,
                'size': img.size,
                'width': img.width,
                'height': img.height,
                'has_transparency': img.mode in ('RGBA', 'LA') or 'transparency' in img.info,
                'file_size': file_path.stat().st_size
            }
            
            # Enhance image for better processing
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Extract EXIF data if available
            if hasattr(img, '_getexif') and img._getexif():
                exif_data = img._getexif()
                if exif_data:
                    analysis['metadata']['exif'] = dict(exif_data)
            
            # OCR Text Extraction using pytesseract (if available)
            try:
                import pytesseract
                # Enhance image for OCR
                enhanced_img = ImageOps.grayscale(img)
                enhanced_img = ImageOps.autocontrast(enhanced_img)
                
                extracted_text = pytesseract.image_to_string(enhanced_img, config='--psm 6')
                analysis['extracted_text'] = extracted_text.strip()
                
                if analysis['extracted_text']:
                    analysis['key_insights'].append(f"Contains text: {len(analysis['extracted_text'])} characters")
                    
            except ImportError:
                logger.warning("pytesseract not available - skipping OCR")
            except Exception as ocr_error:
                logger.warning(f"OCR failed: {ocr_error}")
            
            # Image analysis using OpenCV (if available)
            try:
                import cv2
                # Convert PIL to OpenCV
                cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                
                # Color analysis
                analysis['metadata']['dominant_colors'] = await analyze_dominant_colors(cv_image)
                
                # Edge detection for content analysis
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
                
                if edge_density > 0.1:
                    analysis['key_insights'].append("High detail/complexity image")
                elif edge_density < 0.02:
                    analysis['key_insights'].append("Simple/minimal image")
                
                # Face detection (if available)
                try:
                    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                    if len(faces) > 0:
                        analysis['key_insights'].append(f"Contains {len(faces)} face(s)")
                        analysis['metadata']['faces_detected'] = len(faces)
                except:
                    pass
                
            except ImportError:
                logger.warning("OpenCV not available - skipping advanced image analysis")
            
            # Generate AI description based on analysis
            insights = []
            w, h = img.size
            
            if w > 1920 or h > 1080:
                insights.append("high-resolution")
            
            aspect_ratio = w / h
            if aspect_ratio > 2:
                insights.append("panoramic/wide format")
            elif aspect_ratio < 0.5:
                insights.append("portrait/tall format")
            else:
                insights.append("standard aspect ratio")
            
            if analysis['extracted_text']:
                insights.append("contains readable text")
            
            analysis['ai_description'] = f"Image: {w}x{h} pixels, {', '.join(insights)}"
            analysis['description'] = f"Image analysis: {analysis['ai_description']}"
            
    except Exception as e:
        analysis['description'] = f"Image analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

async def analyze_dominant_colors(cv_image, k=5):
    """Extract dominant colors from image"""
    try:
        # Reshape image to be a list of pixels
        data = cv_image.reshape((-1, 3))
        data = np.float32(data)
        
        # Apply k-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # Convert back to uint8 and return dominant colors
        centers = np.uint8(centers)
        dominant_colors = [color.tolist() for color in centers]
        
        return dominant_colors
    except:
        return []

async def analyze_pdf_file(file_path: Path) -> Dict:
    """
    Comprehensive PDF analysis with text extraction and metadata
    """
    analysis = {
        'type': 'document',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        with pdfplumber.open(file_path) as pdf:
            # PDF metadata
            analysis['metadata'] = {
                'pages': len(pdf.pages),
                'title': pdf.metadata.get('Title', ''),
                'author': pdf.metadata.get('Author', ''),
                'creator': pdf.metadata.get('Creator', ''),
                'producer': pdf.metadata.get('Producer', ''),
                'creation_date': str(pdf.metadata.get('CreationDate', '')),
                'file_size': file_path.stat().st_size
            }
            
            # Extract text from all pages
            full_text = []
            tables_found = 0
            images_found = 0
            
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                page_text = page.extract_text()
                if page_text:
                    full_text.append(f"--- Page {page_num} ---\n{page_text}")
                
                # Look for tables
                tables = page.extract_tables()
                if tables:
                    tables_found += len(tables)
                    for table_num, table in enumerate(tables, 1):
                        table_text = f"\n--- Table {table_num} on Page {page_num} ---\n"
                        for row in table:
                            if row:
                                table_text += " | ".join(str(cell) if cell else "" for cell in row) + "\n"
                        full_text.append(table_text)
                
                # Count images
                if page.images:
                    images_found += len(page.images)
            
            analysis['extracted_text'] = '\n'.join(full_text)
            analysis['metadata']['word_count'] = len(analysis['extracted_text'].split())
            analysis['metadata']['char_count'] = len(analysis['extracted_text'])
            analysis['metadata']['tables_found'] = tables_found
            analysis['metadata']['images_found'] = images_found
            
            # Generate insights
            if tables_found > 0:
                analysis['key_insights'].append(f"Contains {tables_found} table(s)")
            if images_found > 0:
                analysis['key_insights'].append(f"Contains {images_found} image(s)")
            if analysis['metadata']['word_count'] > 5000:
                analysis['key_insights'].append("Long document (>5000 words)")
            
            # AI description
            analysis['ai_description'] = f"PDF document: {len(pdf.pages)} pages, {analysis['metadata']['word_count']} words"
            analysis['description'] = f"PDF analysis: {analysis['ai_description']}"
            
    except Exception as e:
        analysis['description'] = f"PDF analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

async def analyze_text_file(file_path: Path) -> Dict:
    """
    Advanced text file analysis with encoding detection and content analysis
    """
    analysis = {
        'type': 'text',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        # Detect encoding
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                encoding_result = chardet.detect(raw_data)
                encoding = encoding_result['encoding']
                confidence = encoding_result['confidence']
                analysis['metadata']['encoding'] = encoding
                analysis['metadata']['encoding_confidence'] = confidence
        except ImportError:
            encoding = 'utf-8'
            analysis['metadata']['encoding'] = 'utf-8 (assumed)'
        
        # Read file content
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
            analysis['extracted_text'] = content
        
        # Text analysis
        lines = content.split('\n')
        words = content.split()
        
        analysis['metadata'].update({
            'file_size': file_path.stat().st_size,
            'line_count': len(lines),
            'word_count': len(words),
            'char_count': len(content),
            'blank_lines': sum(1 for line in lines if not line.strip()),
            'average_line_length': sum(len(line) for line in lines) / len(lines) if lines else 0,
            'file_extension': file_path.suffix
        })
        
        # Content type detection
        if file_path.suffix.lower() == '.md':
            # Markdown analysis
            headers = [line for line in lines if line.strip().startswith('#')]
            code_blocks = content.count('```')
            links = content.count('[') and content.count('](')
            
            analysis['metadata']['markdown_headers'] = len(headers)
            analysis['metadata']['code_blocks'] = code_blocks // 2  # Opening and closing
            analysis['metadata']['has_links'] = links > 0
            
            if headers:
                analysis['key_insights'].append(f"Markdown with {len(headers)} headers")
            if code_blocks:
                analysis['key_insights'].append("Contains code blocks")
        
        # Programming language detection (basic)
        elif file_path.suffix.lower() in ['.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml']:
            analysis['key_insights'].append(f"Programming/markup file ({file_path.suffix})")
        
        # General text insights
        if analysis['metadata']['word_count'] > 10000:
            analysis['key_insights'].append("Long text document")
        elif analysis['metadata']['word_count'] < 100:
            analysis['key_insights'].append("Short text snippet")
        
        analysis['ai_description'] = f"Text file: {analysis['metadata']['word_count']} words, {analysis['metadata']['line_count']} lines"
        analysis['description'] = f"Text analysis: {analysis['ai_description']}"
        
    except Exception as e:
        analysis['description'] = f"Text analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

async def analyze_csv_file(file_path: Path) -> Dict:
    """
    Comprehensive CSV analysis with data profiling and insights
    """
    analysis = {
        'type': 'data',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'ai_description': '',
        'key_insights': []
    }
    
    try:
        # Try different encodings and delimiters
        encodings = ['utf-8', 'latin-1', 'cp1252']
        delimiters = [',', ';', '\t', '|']
        
        df = None
        used_encoding = None
        used_delimiter = None
        
        for encoding in encodings:
            for delimiter in delimiters:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, delimiter=delimiter, nrows=1000)  # Limit for performance
                    if len(df.columns) > 1:  # Successfully parsed multiple columns
                        used_encoding = encoding
                        used_delimiter = delimiter
                        break
                except:
                    continue
            if df is not None:
                break
        
        if df is None:
            raise ValueError("Could not parse CSV file")
        
        # Reload with full data (up to reasonable limit)
        df = pd.read_csv(file_path, encoding=used_encoding, delimiter=used_delimiter, nrows=10000)
        
        # Basic metadata
        analysis['metadata'] = {
            'rows': len(df),
            'columns': len(df.columns),
            'file_size': file_path.stat().st_size,
            'encoding': used_encoding,
            'delimiter': used_delimiter,
            'column_names': df.columns.tolist(),
            'data_types': df.dtypes.astype(str).to_dict()
        }
        
        # Data profiling
        profile = {
            'numeric_columns': [],
            'text_columns': [],
            'date_columns': [],
            'missing_data': {},
            'unique_values': {},
            'sample_data': {}
        }
        
        for column in df.columns:
            col_data = df[column]
            
            # Missing data
            missing_count = col_data.isnull().sum()
            missing_percent = (missing_count / len(col_data)) * 100
            profile['missing_data'][column] = {
                'count': int(missing_count),
                'percentage': round(missing_percent, 2)
            }
            
            # Unique values
            unique_count = col_data.nunique()
            profile['unique_values'][column] = int(unique_count)
            
            # Sample data (first 3 non-null values)
            sample_values = col_data.dropna().head(3).tolist()
            profile['sample_data'][column] = sample_values
            
            # Data type classification
            if pd.api.types.is_numeric_dtype(col_data):
                profile['numeric_columns'].append(column)
                # Add statistical info for numeric columns
                if not col_data.empty:
                    stats = col_data.describe()
                    profile[f'{column}_stats'] = {
                        'mean': round(stats['mean'], 2) if 'mean' in stats else None,
                        'min': stats['min'] if 'min' in stats else None,
                        'max': stats['max'] if 'max' in stats else None,
                        'std': round(stats['std'], 2) if 'std' in stats else None
                    }
            elif pd.api.types.is_datetime64_any_dtype(col_data):
                profile['date_columns'].append(column)
            else:
                profile['text_columns'].append(column)
                # Try to detect if it might be a date column
                sample_str = str(sample_values[0]) if sample_values else ""
                if any(indicator in sample_str.lower() for indicator in ['date', '2024', '2023', '2022', '/']):
                    try:
                        pd.to_datetime(col_data.head(10), errors='coerce')
                        profile['date_columns'].append(column)
                        profile['text_columns'].remove(column)
                    except:
                        pass
        
        analysis['metadata']['data_profile'] = profile
        
        # Generate insights
        if len(profile['numeric_columns']) > 0:
            analysis['key_insights'].append(f"Contains {len(profile['numeric_columns'])} numeric columns")
        
        if len(profile['date_columns']) > 0:
            analysis['key_insights'].append(f"Contains {len(profile['date_columns'])} date columns")
        
        high_missing = [col for col, info in profile['missing_data'].items() if info['percentage'] > 50]
        if high_missing:
            analysis['key_insights'].append(f"High missing data in: {', '.join(high_missing)}")
        
        if analysis['metadata']['rows'] > 1000:
            analysis['key_insights'].append("Large dataset")
        elif analysis['metadata']['rows'] < 50:
            analysis['key_insights'].append("Small dataset")
        
        # Create summary text
        summary_lines = [
            f"CSV Data Analysis Summary:",
            f"- {analysis['metadata']['rows']} rows × {analysis['metadata']['columns']} columns",
            f"- Column types: {len(profile['numeric_columns'])} numeric, {len(profile['text_columns'])} text, {len(profile['date_columns'])} date",
            f"- Columns: {', '.join(df.columns.tolist()[:5])}{'...' if len(df.columns) > 5 else ''}"
        ]
        
        # Add sample of first few rows
        summary_lines.append("\nFirst 3 rows:")
        for i in range(min(3, len(df))):
            row_data = []
            for col in df.columns[:5]:  # Limit columns shown
                value = str(df.iloc[i][col])[:50]  # Limit value length
                row_data.append(f"{col}: {value}")
            summary_lines.append(f"Row {i+1}: {', '.join(row_data)}")
        
        analysis['extracted_text'] = '\n'.join(summary_lines)
        analysis['ai_description'] = f"CSV dataset: {analysis['metadata']['rows']} rows, {analysis['metadata']['columns']} columns"
        analysis['description'] = f"CSV analysis: {analysis['ai_description']}"
        
    except Exception as e:
        analysis['description'] = f"CSV analysis failed: {str(e)}"
        analysis['error'] = str(e)
    
    return analysis

#-- Section 6: Main Chat Endpoints - 9/23/25
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id)
):
    """
    Main chat endpoint with file upload support
    Handles text messages, file uploads, personality switching, and knowledge integration
    """
    start_time = datetime.now()
    
    try:
        # Process any uploaded files
        processed_files = []
        if files and files[0].filename:  # Check if files were actually uploaded
            processed_files = await process_uploaded_files(files)
            logger.info(f"Processed {len(processed_files)} uploaded files")
        
        # Get or create conversation thread
        memory_manager = get_memory_manager(user_id)
        
        if request.thread_id:
            thread_id = request.thread_id
        else:
            thread_id = await memory_manager.create_conversation_thread(
                platform="web_interface",
                title=None  # Will be auto-generated
            )
        
        # Store user message with file references
        user_message_id = str(uuid.uuid4())
        
        # Prepare message content with file context
        message_content = request.message
        if processed_files:
            file_context = "\n\nUploaded files:\n"
            for file_info in processed_files:
                file_context += f"- {file_info['filename']} ({file_info['file_type']}, {file_info['file_size']} bytes)\n"
                if file_info['analysis']['extracted_text']:
                    file_context += f"  Content preview: {file_info['analysis']['extracted_text'][:200]}...\n"
                else:
                    file_context += f"  {file_info['analysis']['description']}\n"
            message_content += file_context
        
        await memory_manager.add_message(
            thread_id=thread_id,
            role="user",
            content=message_content,
            content_type="text_with_files" if processed_files else "text"
        )
        
        # Get conversation context
        conversation_history, context_info = await memory_manager.get_context_for_ai(
            thread_id=thread_id,
            max_tokens=200000  # Use full 250K context
        )
        
        # Search knowledge base if requested
        knowledge_sources = []
        if request.include_knowledge:
            knowledge_engine = get_knowledge_engine()
            knowledge_results = await knowledge_engine.search_knowledge(
                query=request.message,
                conversation_context=conversation_history,
                personality_id=request.personality_id,
                limit=5
            )
            knowledge_sources = knowledge_results
        
        # Get personality system prompt
        personality_engine = get_personality_engine()
        system_prompt = personality_engine.get_personality_system_prompt(
            personality_id=request.personality_id,
            conversation_context=conversation_history,
            knowledge_context=knowledge_sources
        )
        
        # Prepare messages for OpenRouter
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 10 messages)
        for msg in conversation_history[-10:]:
            if msg['role'] in ['user', 'assistant']:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": message_content
        })
        
        # Get AI response
        openrouter_client = await get_openrouter_client()
        ai_response = await openrouter_client.chat_completion(
            messages=messages,
            model=None,  # Auto-select best model
            max_tokens=4000,
            temperature=0.7
        )
        
        # Extract response content
        response_content = ai_response.get('choices', [{}])[0].get('message', {}).get('content', '')
        model_used = ai_response.get('_metadata', {}).get('model_used')
        
        # Process response through personality engine
        processed_response = personality_engine.process_ai_response(
            response=response_content,
            personality_id=request.personality_id,
            conversation_context=conversation_history
        )
        
        # Store AI response
        ai_message_id = str(uuid.uuid4())
        response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        await memory_manager.add_message(
            thread_id=thread_id,
            role="assistant",
            content=processed_response,
            response_time_ms=response_time_ms,
            model_used=model_used,
            knowledge_sources_used=[source.get('id') for source in knowledge_sources]
        )
        
        logger.info(f"Chat completed - Thread: {thread_id}, Response time: {response_time_ms}ms")
        
        return ChatResponse(
            message_id=ai_message_id,
            thread_id=thread_id,
            response=processed_response,
            personality_used=request.personality_id,
            response_time_ms=response_time_ms,
            knowledge_sources=knowledge_sources,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

#-- Section 7: Streaming Chat Endpoint - 9/23/25
@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id)
):
    """
    Streaming chat endpoint for real-time responses
    """
    async def generate_stream():
        try:
            # Set up streaming request
            request.stream = True
            
            # Process the chat request (most logic same as main chat)
            # This is a simplified version - in production, you'd want to
            # refactor the common logic into shared functions
            
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting response...'})}\n\n"
            
            # TODO: Implement actual streaming with OpenRouter
            # For now, just simulate streaming
            response_text = "This would be a streaming response..."
            
            for i, char in enumerate(response_text):
                yield f"data: {json.dumps({'type': 'chunk', 'content': char})}\n\n"
                await asyncio.sleep(0.05)  # Simulate typing delay
            
            yield f"data: {json.dumps({'type': 'end', 'message': 'Response complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

#-- Section 8: Bookmark Management - 9/23/25
@router.post("/bookmarks")
async def create_bookmark(
    request: BookmarkRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a bookmark for a specific message
    Implements the "Remember This" -> "What should we name this?" flow
    """
    try:
        # Get memory manager for user
        memory_manager = get_memory_manager(user_id)
        
        # Get the original message (we'll need to query directly since it's not in the memory manager API)
        original_message_query = """
        SELECT content, created_at FROM conversation_messages 
        WHERE id = $1 AND user_id = $2
        """
        original_message = await db_manager.fetch_one(original_message_query, request.message_id, user_id)
        
        if not original_message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Create bookmark entry
        bookmark_content = {
            "bookmark_name": request.bookmark_name,
            "original_message_id": request.message_id,
            "original_content": original_message['content'][:200] + "..." if len(original_message['content']) > 200 else original_message['content'],
            "created_by": user_id,
            "original_timestamp": original_message['created_at'].isoformat()
        }
        
        bookmark_message_id = await memory_manager.add_message(
            thread_id=request.thread_id,
            role="system",
            content=json.dumps(bookmark_content),
            content_type="bookmark"
        )
        
        logger.info(f"Bookmark created: {request.bookmark_name} for message {request.message_id}")
        
        return {
            "bookmark_id": bookmark_message_id,
            "bookmark_name": request.bookmark_name,
            "message": "Bookmark created successfully"
        }
        
    except Exception as e:
        logger.error(f"Bookmark creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create bookmark: {str(e)}")

@router.get("/bookmarks/{thread_id}")
async def get_thread_bookmarks(
    thread_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get all bookmarks for a conversation thread
    """
    try:
        # Query bookmarks directly from database since it's not in memory_manager API
        bookmarks_query = """
        SELECT id, content, created_at 
        FROM conversation_messages 
        WHERE thread_id = $1 AND user_id = $2 AND content_type = 'bookmark'
        ORDER BY created_at DESC
        """
        
        bookmarks = await db_manager.fetch_all(bookmarks_query, thread_id, user_id)
        
        # Format bookmark data
        formatted_bookmarks = []
        for bookmark in bookmarks:
            try:
                bookmark_data = json.loads(bookmark['content'])
                formatted_bookmarks.append({
                    'bookmark_id': bookmark['id'],
                    'bookmark_name': bookmark_data['bookmark_name'],
                    'original_message_id': bookmark_data['original_message_id'],
                    'preview': bookmark_data['original_content'],
                    'created_at': bookmark['created_at'].isoformat() if bookmark['created_at'] else None,
                    'created_by': bookmark_data['created_by'],
                    'original_timestamp': bookmark_data.get('original_timestamp')
                })
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid bookmark data for {bookmark['id']}: {e}")
                continue
        
        return {
            "thread_id": thread_id,
            "bookmarks": formatted_bookmarks,
            "total_bookmarks": len(formatted_bookmarks)
        }
        
    except Exception as e:
        logger.error(f"Get bookmarks error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get bookmarks: {str(e)}")

#-- Section 9: Conversation Management - 9/23/25
@router.get("/conversations")
async def get_user_conversations(
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    offset: int = 0
):
    """
    Get user's conversation threads
    """
    try:
        threads_query = """
        SELECT id, title, summary, platform, status, message_count, 
               created_at, updated_at, last_message_at
        FROM conversation_threads
        WHERE user_id = $1
        ORDER BY last_message_at DESC
        LIMIT $2 OFFSET $3
        """
        
        threads = await db_manager.fetch_all(threads_query, user_id, limit, offset)
        
        # Format threads for frontend
        formatted_threads = []
        for thread in threads:
            formatted_threads.append({
                'thread_id': thread['id'],
                'title': thread['title'],
                'summary': thread['summary'],
                'platform': thread['platform'],
                'status': thread['status'],
                'message_count': thread['message_count'],
                'created_at': thread['created_at'].isoformat() if thread['created_at'] else None,
                'updated_at': thread['updated_at'].isoformat() if thread['updated_at'] else None,
                'last_message_at': thread['last_message_at'].isoformat() if thread['last_message_at'] else None
            })
        
        return {
            "conversations": formatted_threads,
            "total": len(formatted_threads),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Get conversations error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get conversations: {str(e)}")

@router.get("/conversations/{thread_id}/messages")
async def get_conversation_messages(
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
    limit: int = 50
):
    """
    Get messages for a specific conversation thread
    """
    try:
        memory_manager = get_memory_manager(user_id)
        messages = await memory_manager.get_conversation_history(
            thread_id=thread_id,
            limit=limit,
            include_metadata=True
        )
        
        return {
            "thread_id": thread_id,
            "messages": messages,
            "total_messages": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")

#-- Section 10: Personality and System Info - 9/23/25
@router.get("/personalities")
async def get_available_personalities():
    """
    Get list of available AI personalities
    """
    try:
        personality_engine = get_personality_engine()
        personalities = personality_engine.get_available_personalities()
        
        # Format for frontend consumption
        formatted_personalities = []
        for pid, config in personalities.items():
            formatted_personalities.append({
                'id': pid,
                'name': config.get('name', pid.title()),
                'description': config.get('description', ''),
                'is_default': pid == 'syntaxprime'
            })
        
        return {
            "personalities": formatted_personalities,
            "default_personality": "syntaxprime"
        }
        
    except Exception as e:
        logger.error(f"Get personalities error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get personalities: {str(e)}")

@router.get("/stats")
async def get_ai_stats(user_id: str = Depends(get_current_user_id)):
    """
    Get AI system statistics and performance metrics
    """
    try:
        personality_engine = get_personality_engine()
        
        # Get personality stats
        personality_stats = personality_engine.get_personality_stats()
        
        # Get conversation stats from database
        conversation_stats_query = """
        SELECT 
            COUNT(DISTINCT ct.id) as total_conversations,
            COUNT(cm.id) as total_messages,
            COUNT(CASE WHEN cm.role = 'user' THEN 1 END) as user_messages,
            COUNT(CASE WHEN cm.role = 'assistant' THEN 1 END) as assistant_messages,
            AVG(cm.response_time_ms) as avg_response_time_ms,
            COUNT(CASE WHEN cm.content_type = 'bookmark' THEN 1 END) as total_bookmarks,
            MAX(ct.last_message_at) as last_conversation_at
        FROM conversation_threads ct
        LEFT JOIN conversation_messages cm ON ct.id = cm.thread_id
        WHERE ct.user_id = $1
        """
        
        stats_result = await db_manager.fetch_one(conversation_stats_query, user_id)
        
        conversation_stats = {
            'total_conversations': stats_result['total_conversations'] or 0,
            'total_messages': stats_result['total_messages'] or 0,
            'user_messages': stats_result['user_messages'] or 0,
            'assistant_messages': stats_result['assistant_messages'] or 0,
            'average_response_time_ms': float(stats_result['avg_response_time_ms']) if stats_result['avg_response_time_ms'] else 0,
            'total_bookmarks': stats_result['total_bookmarks'] or 0,
            'last_conversation_at': stats_result['last_conversation_at'].isoformat() if stats_result['last_conversation_at'] else None
        }
        
        return {
            "personality_performance": personality_stats,
            "conversation_statistics": conversation_stats,
            "system_status": "healthy",
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get stats error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

#-- Section 11: File Management - 9/23/25
@router.delete("/files/{file_id}")
async def delete_uploaded_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete an uploaded file
    """
    try:
        # Find and delete the file
        for file_path in UPLOAD_DIR.glob(f"{file_id}_*"):
            file_path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return {"message": f"File {file_id} deleted successfully"}
        
        raise HTTPException(status_code=404, detail="File not found")
        
    except Exception as e:
        logger.error(f"Delete file error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

#-- Section 12: Export Functions - 9/23/25
def get_integration_info() -> Dict[str, Any]:
    """Get information about the AI chat integration"""
    return {
        "name": "AI Chat System",
        "version": "2.0.0",
        "endpoints": [
            "/ai/chat",
            "/ai/chat/stream",
            "/ai/bookmarks",
            "/ai/conversations",
            "/ai/personalities",
            "/ai/stats"
        ],
        "features": [
            "Multi-personality chat",
            "File upload support",
            "Bookmark system",
            "Knowledge integration",
            "Streaming responses",
            "Conversation management"
        ],
        "file_upload_support": True,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "supported_file_types": list(ALLOWED_EXTENSIONS)
    }

def check_module_health() -> Dict[str, Any]:
    """Check the health of the AI chat module"""
    missing_vars = []
    warnings = []
    
    # Check required directories
    if not UPLOAD_DIR.exists():
        warnings.append("Upload directory not found")
    
    # Check OpenRouter configuration
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "warnings": warnings,
        "upload_directory": str(UPLOAD_DIR),
        "max_file_size": f"{MAX_FILE_SIZE // (1024 * 1024)}MB"
    }
