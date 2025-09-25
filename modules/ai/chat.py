# modules/ai/chat.py
# AI Chat Router for Syntax Prime V2 - COMPLETE REWRITE WITH RSS LEARNING + MARKETING SCRAPER
# Clean, sectioned chat endpoint with file upload, weather, Bluesky, RSS Learning, and Marketing Scraper integration
# Date: 9/25/25

#-- Section 1: Core Imports - 9/25/25
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
import httpx

# File processing imports
from PIL import Image, ImageOps
import pdfplumber
import pandas as pd
import magic
import cv2
import numpy as np
from io import BytesIO
import base64

#-- Section 2: Internal Module Imports - 9/25/25
from modules.core.database import db_manager
from modules.ai.personality_engine import get_personality_engine
from modules.ai.openrouter_client import get_openrouter_client
from modules.ai.conversation_manager import get_memory_manager
from modules.ai.knowledge_query import get_knowledge_engine

#-- Section 2a: Bluesky Integration Import - 9/24/25
from modules.integrations.bluesky.multi_account_client import get_bluesky_multi_client
from modules.integrations.bluesky.engagement_analyzer import get_engagement_analyzer
from modules.integrations.bluesky.approval_system import get_approval_system
from modules.integrations.bluesky.notification_manager import get_notification_manager

#-- NEW Section 2b: Marketing Scraper Integration Import - 9/25/25
from modules.integrations.marketing_scraper.scraper_client import MarketingScraperClient
from modules.integrations.marketing_scraper.content_analyzer import ContentAnalyzer
from modules.integrations.marketing_scraper.database_manager import ScrapedContentDB

#-- Section 3: Request/Response Models - 9/25/25
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

#-- Section 4: Router Setup - 9/25/25
router = APIRouter(prefix="/ai", tags=["AI Chat"])
logger = logging.getLogger(__name__)

# File upload configuration
UPLOAD_DIR = Path("/home/app/uploads/chat_files")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.txt', '.md', '.csv'}

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

_upload_dir_created = False

def get_upload_dir():
    """Get upload directory, creating it if necessary"""
    global _upload_dir_created
    if not _upload_dir_created:
        _upload_dir_created = ensure_upload_dir()
    return UPLOAD_DIR if _upload_dir_created else None

#-- Section 5: Helper Functions - 9/25/25
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    return "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

async def get_weather_for_user(user_id: str, location: str = None) -> Dict:
    """Get current weather data for the user"""
    try:
        base_url = "https://api.tomorrow.io/v4/weather/realtime"
        api_key = os.getenv("TOMORROW_IO_API_KEY")
        
        if not api_key:
            return {"error": "Weather API key not configured"}
            
        # Default location if not provided
        location = location or "27519"  # Default to Cary, NC
        
        params = {
            "location": location,
            "apikey": api_key,
            "units": "imperial"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                weather_data = data.get('data', {}).get('values', {})
                
                return {
                    "success": True,
                    "data": {
                        "location": location,
                        "temperature_f": weather_data.get('temperature', 'N/A'),
                        "humidity": weather_data.get('humidity', 'N/A'),
                        "wind_speed": weather_data.get('windSpeed', 'N/A'),
                        "weather_code": weather_data.get('weatherCode', 'N/A'),
                        "pressure": weather_data.get('pressureSeaLevel', 'N/A'),
                        "uv_index": weather_data.get('uvIndex', 'N/A'),
                        "visibility": weather_data.get('visibility', 'N/A')
                    }
                }
            else:
                return {"error": f"Weather API returned status {response.status_code}"}
                
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return {"error": str(e)}

def detect_weather_request(message: str) -> bool:
    """Detect weather-related requests"""
    weather_keywords = [
        "weather", "temperature", "forecast", "rain", "snow", "sunny",
        "cloudy", "storm", "wind", "humidity", "barometric pressure",
        "headache weather", "pressure change", "uv index"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in weather_keywords)

#-- Section 5a: Bluesky Integration Functions - 9/24/25
def detect_bluesky_command(message: str) -> bool:
    """Detect Bluesky management commands"""
    bluesky_keywords = [
        "bluesky scan", "bluesky opportunities", "bluesky accounts",
        "bluesky health", "bluesky status", "bluesky", "social media opportunities"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in bluesky_keywords)

async def process_bluesky_command(message: str, user_id: str) -> str:
    """Process Bluesky-related commands"""
    try:
        message_lower = message.lower()
        
        if 'scan' in message_lower:
            await trigger_background_scan(user_id)
            return """🔵 **Bluesky Account Scan Initiated**

✅ Scanning all configured accounts for engagement opportunities...
🔍 Analyzing posts from the last 24 hours
🤖 AI-powered engagement suggestions incoming
📝 Draft posts will be generated for approval

Results will be available in a few moments. Use `bluesky opportunities` to view suggestions."""
        
        elif 'opportunities' in message_lower or 'suggestion' in message_lower:
            approval_system = get_approval_system()
            pending_items = await approval_system.get_pending_approvals(limit=5)
            
            if not pending_items:
                return """🔵 **No Current Opportunities**

No engagement opportunities found at this time.
• Use `bluesky scan` to search for new opportunities
• Check back in a few hours for automatic updates"""
            
            response_parts = ["🔵 **Current Bluesky Engagement Opportunities**\n"]
            
            for i, item in enumerate(pending_items, 1):
                account_info = item.get('account_info', {})
                opportunity = item.get('opportunity_analysis', {})
                
                response_parts.append(f"""**{i}. {account_info.get('username', 'Unknown Account')}**
📊 Engagement Score: {opportunity.get('engagement_potential', 0):.0%}
💡 Why: {opportunity.get('opportunity_reason', 'High engagement potential')}
⏰ Post Time: {opportunity.get('post_time', 'Recently')}

""")
            
            response_parts.append("Use the Bluesky dashboard to review and approve these opportunities.")
            return "\n".join(response_parts)
        
        elif 'accounts' in message_lower or 'status' in message_lower:
            multi_client = get_bluesky_multi_client()
            account_statuses = multi_client.get_all_account_status()
            configured_count = len([s for s in account_statuses.values() if s.get('configured', False)])
            
            response_parts = ["🔵 **Bluesky Account Status**\n"]
            
            for account_id, status in account_statuses.items():
                emoji = "✅" if status.get('authenticated', False) else "❌"
                username = status.get('username', f'Account {account_id}')
                last_scan = status.get('last_scan', 'Never')
                
                response_parts.append(f"{emoji} **{username}**")
                response_parts.append(f"   Last scan: {last_scan}")
                response_parts.append("")
            
            response_parts.append(f"📊 **Summary:** {configured_count}/5 accounts configured and ready")
            return "\n".join(response_parts)
        
        else:
            return f"""🔵 **Bluesky Social Media Intelligence**

📱 **Configured Accounts:** {len(account_statuses)}/5
🤖 **Features:** Keyword intelligence, engagement suggestions, approval workflow
⏰ **Auto-Scan:** Every 3.5 hours across all accounts

**Available Commands:**
• `bluesky scan` - Force scan all accounts  
• `bluesky opportunities` - View engagement suggestions
• `bluesky accounts` - Check account status

Ready to find your next great engagement opportunity?"""
    
    except Exception as e:
        logger.error(f"Bluesky command processing failed: {e}")
        return f"❌ **Bluesky Command Error:** {str(e)}\n\nTry `bluesky health` to check system status."

async def trigger_background_scan(user_id: str):
    """Trigger a background scan of all Bluesky accounts"""
    try:
        multi_client = get_bluesky_multi_client()
        engagement_analyzer = get_engagement_analyzer()
        approval_system = get_approval_system()
        
        await multi_client.authenticate_all_accounts()
        timelines = await multi_client.get_all_timelines()
        
        all_opportunities = []
        for account_id, timeline in timelines.items():
            account_config = multi_client.get_account_info(account_id)
            
            for post in timeline[:20]:
                analysis = await engagement_analyzer.analyze_post_for_account(
                    post, account_id, account_config
                )
                
                if analysis and analysis.get('engagement_potential', 0) >= 0.3:
                    draft_result = await approval_system.generate_draft_post(analysis, "reply")
                    
                    if draft_result['success']:
                        await approval_system.create_approval_item(
                            analysis, draft_result, analysis.get('priority_level', 'medium')
                        )
                        all_opportunities.append(analysis)
        
        logger.info(f"Background scan complete: {len(all_opportunities)} opportunities found")
        
    except Exception as e:
        logger.error(f"Background scan failed: {e}")

#-- Section 5b: RSS Learning Command Processing - 9/25/25
def detect_rss_command(message: str) -> bool:
    """Detect if user is asking for RSS/marketing insights"""
    rss_keywords = [
        "marketing trends", "content ideas", "writing inspiration", "blog ideas",
        "social media trends", "seo trends", "marketing insights", "campaign ideas",
        "content strategy", "latest marketing", "marketing news",
        "industry trends", "rss insights", "marketing research", "content research", "writing help"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in rss_keywords)

def detect_writing_assistance_request(message: str) -> tuple[bool, str]:
    """Detect writing assistance requests and determine content type"""
    message_lower = message.lower()
    
    if any(term in message_lower for term in ['email', 'newsletter', 'email campaign', 'email marketing']):
        return True, 'email'
    elif any(term in message_lower for term in ['blog post', 'blog', 'article', 'write blog']):
        return True, 'blog'
    elif any(term in message_lower for term in ['social media', 'social post', 'tweet', 'linkedin post', 'instagram']):
        return True, 'social'
    elif any(term in message_lower for term in ['help me write', 'writing help', 'content ideas', 'what should i write']):
        return True, 'blog'
    
    return False, ''

async def get_rss_marketing_context(message: str, content_type: str = None) -> str:
    """Get marketing context from RSS learning system for AI writing assistance"""
    try:
        from modules.integrations.rss_learning.marketing_insights import MarketingInsightsExtractor
        
        insights_extractor = MarketingInsightsExtractor()
        
        is_writing_request, detected_type = detect_writing_assistance_request(message)
        final_content_type = content_type or detected_type or 'blog'
        
        if is_writing_request or detect_rss_command(message):
            inspiration = await insights_extractor.get_writing_inspiration(
                content_type=final_content_type,
                topic=None,
                target_audience="digital marketers"
            )
            
            trends = await insights_extractor.get_latest_trends(limit=3)
            
            context_parts = [
                "CURRENT MARKETING INSIGHTS FROM RSS LEARNING SYSTEM:",
                ""
            ]
            
            if trends.get('trends_summary'):
                context_parts.extend([
                    "CURRENT TRENDS:",
                    trends['trends_summary'],
                    ""
                ])
            
            if inspiration.get('content_ideas'):
                context_parts.extend([
                    f"CONTENT IDEAS FOR {final_content_type.upper()}:",
                    *[f"• {idea}" for idea in inspiration['content_ideas'][:3]],
                    ""
                ])
            
            if inspiration.get('key_messages'):
                context_parts.extend([
                    "KEY MESSAGES TO CONSIDER:",
                    *[f"• {msg}" for msg in inspiration['key_messages'][:3]],
                    ""
                ])
            
            if trends.get('actionable_insights'):
                context_parts.extend([
                    "ACTIONABLE MARKETING INSIGHTS:",
                    *[f"• {insight}" for insight in trends['actionable_insights'][:3]],
                    ""
                ])
            
            if trends.get('trending_keywords'):
                context_parts.extend([
                    "TRENDING KEYWORDS:",
                    f"Consider incorporating: {', '.join(trends['trending_keywords'][:5])}",
                    ""
                ])
            
            if inspiration.get('call_to_action_ideas'):
                context_parts.extend([
                    "CALL-TO-ACTION IDEAS:",
                    *[f"• {cta}" for cta in inspiration['call_to_action_ideas'][:2]],
                    ""
                ])
            
            context_parts.extend([
                "Use these insights naturally in your response. Don't simply list them - integrate them into helpful, actionable advice for the user's specific request.",
                "Focus on current marketing best practices and trending approaches."
            ])
            
            return "\n".join(context_parts)
        
        elif detect_rss_command(message):
            trends = await insights_extractor.get_latest_trends(limit=5)
            
            context_parts = [
                "CURRENT MARKETING INSIGHTS:",
                "",
                "TRENDS SUMMARY:",
                trends.get('trends_summary', 'No current trends available'),
                ""
            ]
            
            if trends.get('trending_keywords'):
                context_parts.extend([
                    "TRENDING TOPICS:",
                    f"{', '.join(trends['trending_keywords'][:8])}",
                    ""
                ])
            
            context_parts.append("Provide insights based on these current marketing trends and data.")
            return "\n".join(context_parts)
        
        return ""
        
    except Exception as e:
        logger.error(f"RSS marketing context generation failed: {e}")
        return "RSS_CONTEXT_ERROR: Unable to retrieve current marketing insights. Proceed with general knowledge."

#-- NEW Section 5c: Marketing Scraper Command Processing - 9/25/25
def detect_scraper_command(message: str) -> bool:
    """Detect marketing scraper commands"""
    scraper_keywords = [
        "scrape", "scraper", "analyze website", "competitor analysis", "scrape url",
        "scrape site", "website analysis", "marketing analysis", "content analysis",
        "scrape history", "scrape insights", "scrape data"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in scraper_keywords)

def extract_url_from_message(message: str) -> str:
    """Extract URL from scrape command message"""
    import re
    
    # Look for URLs in the message
    url_pattern = r'https?://[^\s<>"{\}|\\^`\[\]]+'
    urls = re.findall(url_pattern, message)
    
    if urls:
        return urls[0]  # Return first URL found
    
    # If no full URL, look for domain patterns
    domain_pattern = r'(?:^|\s)([a-zA-Z0-9-]+\.(?:com|org|net|edu|gov|io|co\.uk))'
    domains = re.findall(domain_pattern, message)
    
    if domains:
        return f"https://{domains[0]}"
    
    return None

async def process_scraper_command(message: str, user_id: str) -> str:
    """Process marketing scraper commands"""
    try:
        message_lower = message.lower()
        
        if 'scrape history' in message_lower:
            # Get scrape history
            db = ScrapedContentDB()
            history = await db.get_scrape_history(user_id=user_id, limit=10)
            
            if not history:
                return """🔍 **Marketing Scraper History**

No scraping history found. Start analyzing competitors with:
• `scrape https://example.com` - Analyze any website
• `scrape insights` - Get analysis from previous scrapes"""
            
            response_parts = ["🔍 **Recent Scraping History**\n"]
            
            for i, item in enumerate(history, 1):
                domain = item.get('domain', 'Unknown')
                scraped_at = item.get('scraped_at', 'Unknown time')
                insights_count = len(item.get('insights', []))
                
                response_parts.append(f"**{i}. {domain}**")
                response_parts.append(f"   📅 Scraped: {scraped_at}")
                response_parts.append(f"   🧠 Insights: {insights_count}")
                response_parts.append("")
            
            response_parts.append("💡 Use `scrape insights` to get AI analysis of all scraped content.")
            return "\n".join(response_parts)
        
        elif 'scrape insights' in message_lower:
            # Get competitive insights from all scraped content
            db = ScrapedContentDB()
            analyzer = ContentAnalyzer()
            
            recent_content = await db.get_recent_scraped_content(user_id=user_id, limit=20)
            
            if not recent_content:
                return """🔍 **Marketing Scraper Insights**

No scraped content available for analysis. 

Start building your competitive intelligence with:
• `scrape https://competitor.com` - Analyze competitor sites
• `scrape https://industry-blog.com` - Analyze industry content"""
            
            # Generate competitive insights
            insights = await analyzer.generate_competitive_insights(recent_content)
            
            response_parts = [
                "🧠 **Competitive Intelligence Report**",
                f"📊 Based on {len(recent_content)} recently analyzed websites",
                ""
            ]
            
            if insights.get('key_trends'):
                response_parts.extend([
                    "**🔥 Key Market Trends:**",
                    *[f"• {trend}" for trend in insights['key_trends'][:5]],
                    ""
                ])
            
            if insights.get('competitive_advantages'):
                response_parts.extend([
                    "**💪 Competitive Opportunities:**",
                    *[f"• {advantage}" for advantage in insights['competitive_advantages'][:3]],
                    ""
                ])
            
            if insights.get('content_gaps'):
                response_parts.extend([
                    "**🎯 Content Gap Analysis:**",
                    *[f"• {gap}" for gap in insights['content_gaps'][:3]],
                    ""
                ])
            
            response_parts.extend([
                "**📈 Strategic Recommendations:**",
                *[f"• {rec}" for rec in insights.get('recommendations', ['Continue monitoring competitor activity'])[:3]]
            ])
            
            return "\n".join(response_parts)
        
        else:
            # Extract URL and scrape content
            url = extract_url_from_message(message)
            
            if not url:
                return """🔍 **Marketing Scraper Commands**

**Usage:**
• `scrape https://example.com` - Analyze any website for marketing insights
• `scrape history` - View your scraping history  
• `scrape insights` - Get competitive intelligence report

**Examples:**
• `scrape https://hubspot.com/blog` - Analyze HubSpot's content strategy
• `scrape https://competitor.com` - Competitive analysis
• `scrape https://industry-news.com` - Industry trend analysis

Ready to analyze your competition? 🕵️"""
            
            # Perform the scrape
            scraper = MarketingScraperClient()
            analyzer = MarketingContentAnalyzer()
            db = ScrapedContentDB()
            
            # Show initial processing message
            processing_msg = f"""🔍 **Analyzing Website: {url}**

⏳ Extracting content...
🧠 AI analysis in progress...
💾 Storing insights for future reference...

This may take a moment..."""
            
            try:
                # Scrape the website
                scraped_data = await scraper.scrape_url(url)
                
                if not scraped_data.get('success'):
                    return f"""❌ **Scraping Failed**
                    
Unable to analyze {url}
Error: {scraped_data.get('error', 'Unknown error')}

Please verify the URL is accessible and try again."""
                
                # Analyze the content
                analysis = await analyzer.analyze_content(
                    scraped_data['content'],
                    scraped_data['metadata']
                )
                
                # Store in database
                await db.store_scraped_content(
                    url=url,
                    content=scraped_data['content'],
                    metadata=scraped_data['metadata'],
                    analysis=analysis,
                    user_id=user_id
                )
                
                # Generate response
                domain = scraped_data['metadata'].get('domain', url)
                word_count = len(scraped_data['content'].split())
                
                response_parts = [
                    f"✅ **Successfully Analyzed: {domain}**",
                    f"📄 Content extracted: {word_count:,} words",
                    ""
                ]
                
                if analysis.get('key_insights'):
                    response_parts.extend([
                        "**🎯 Key Marketing Insights:**",
                        *[f"• {insight}" for insight in analysis['key_insights'][:4]],
                        ""
                    ])
                
                if analysis.get('content_strategy'):
                    response_parts.extend([
                        "**📝 Content Strategy Observed:**",
                        f"• {analysis['content_strategy'][:200]}...",
                        ""
                    ])
                
                if analysis.get('competitive_intel'):
                    response_parts.extend([
                        "**🕵️ Competitive Intelligence:**",
                        *[f"• {intel}" for intel in analysis['competitive_intel'][:3]],
                        ""
                    ])
                
                response_parts.extend([
                    f"💾 **Stored for Analysis** - Use `scrape insights` for competitive intelligence",
                    f"📈 **View History** - Use `scrape history` to see all analyzed sites"
                ])
                
                return "\n".join(response_parts)
                
            except Exception as e:
                logger.error(f"Scraper processing failed: {e}")
                return f"""❌ **Analysis Failed**
                
Error analyzing {url}: {str(e)}

Please try again or contact support if the issue persists."""
    
    except Exception as e:
        logger.error(f"Scraper command processing failed: {e}")
        return f"❌ **Scraper Command Error:** {str(e)}\n\nTry `scrape https://example.com` to analyze a website."

#-- Section 5d: File Processing Functions - 9/25/25
async def process_uploaded_files(files: List[UploadFile]) -> List[Dict]:
    """Process uploaded files and return file information"""
    processed_files = []
    
    for file in files:
        if not file.filename:
            continue
            
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} too large. Max size: 10MB"
            )
        
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        file_info = {
            'file_id': file_id,
            'filename': file.filename,
            'file_type': file_ext,
            'file_size': len(content),
            'file_path': str(file_path),
            'analysis': await analyze_file_content(file_path, file_ext)
        }
        
        processed_files.append(file_info)
        await file.seek(0)
    
    return processed_files

async def analyze_file_content(file_path: Path, file_type: str) -> Dict:
    """Analyze file content and extract information"""
    analysis = {
        'type': 'unknown',
        'description': '',
        'extracted_text': '',
        'metadata': {},
        'key_insights': []
    }
    
    try:
        if file_type in ['.png', '.jpg', '.jpeg', '.gif']:
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
    """Analyze image file"""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            format_name = img.format
            mode = img.mode
            
        return {
            'type': 'image',
            'description': f'{format_name} image ({width}x{height}, {mode})',
            'metadata': {
                'width': width,
                'height': height,
                'format': format_name,
                'mode': mode
            },
            'extracted_text': f"Image file: {width}x{height} {format_name}"
        }
    except Exception as e:
        return {
            'type': 'image',
            'description': f'Image analysis failed: {e}',
            'extracted_text': ''
        }

async def analyze_pdf_file(file_path: Path) -> Dict:
    """Analyze PDF file"""
    try:
        text_content = ""
        page_count = 0
        
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages[:5]:  # First 5 pages
                if page.extract_text():
                    text_content += page.extract_text() + "\n"
        
        return {
            'type': 'pdf',
            'description': f'PDF document with {page_count} pages',
            'extracted_text': text_content[:2000],  # First 2000 chars
            'metadata': {'page_count': page_count}
        }
    except Exception as e:
        return {
            'type': 'pdf',
            'description': f'PDF analysis failed: {e}',
            'extracted_text': ''
        }

async def analyze_text_file(file_path: Path) -> Dict:
    """Analyze text file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        line_count = len(content.splitlines())
        word_count = len(content.split())
        
        return {
            'type': 'text',
            'description': f'Text file ({line_count} lines, {word_count} words)',
            'extracted_text': content[:2000],  # First 2000 chars
            'metadata': {'line_count': line_count, 'word_count': word_count}
        }
    except Exception as e:
        return {
            'type': 'text',
            'description': f'Text analysis failed: {e}',
            'extracted_text': ''
        }

async def analyze_csv_file(file_path: Path) -> Dict:
    """Analyze CSV file"""
    try:
        df = pd.read_csv(file_path)
        rows, cols = df.shape
        columns = df.columns.tolist()
        
        preview = df.head().to_string()
        
        return {
            'type': 'csv',
            'description': f'CSV file ({rows} rows, {cols} columns)',
            'extracted_text': f"CSV Preview:\n{preview}",
            'metadata': {'rows': rows, 'columns': cols, 'column_names': columns}
        }
    except Exception as e:
        return {
            'type': 'csv',
            'description': f'CSV analysis failed: {e}',
            'extracted_text': ''
        }

#-- Section 6: Main Chat Endpoints - updated 9/25/25 with Marketing Scraper
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    files: List[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id)
):
    """
    Main chat endpoint with complete integration: files, weather, Bluesky, RSS Learning, and Marketing Scraper
    """
    start_time = datetime.now()
    logger.info(f"🔍 DEBUG: chat_with_ai called with message: '{request.message}'")
    
    try:
        # Process uploaded files
        processed_files = []
        if files and files[0].filename:
            processed_files = await process_uploaded_files(files)
            logger.info(f"Processed {len(processed_files)} uploaded files")
        
        # Check for Marketing Scraper commands first - NEW
        if detect_scraper_command(request.message):
            logger.info(f"🔍 Marketing scraper command detected: {request.message}")
            
            scraper_response = await process_scraper_command(request.message, user_id)
            
            memory_manager = get_memory_manager(user_id)
            
            if request.thread_id:
                thread_id = request.thread_id
            else:
                thread_id = await memory_manager.create_conversation_thread(
                    platform="web_interface",
                    title="Marketing Scraper Analysis"
                )
            
            user_message_id = str(uuid.uuid4())
            await memory_manager.add_message(
                thread_id=thread_id,
                role="user",
                content=request.message
            )
            
            response_message_id = str(uuid.uuid4())
            await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=scraper_response
            )
            
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return ChatResponse(
                message_id=response_message_id,
                thread_id=thread_id,
                response=scraper_response,
                personality_used="syntaxprime",
                response_time_ms=response_time_ms,
                timestamp=end_time
            )
        
        # Check for Bluesky commands
        if detect_bluesky_command(request.message):
            logger.info(f"🔵 Bluesky command detected: {request.message}")
            
            bluesky_response = await process_bluesky_command(request.message, user_id)
            
            memory_manager = get_memory_manager(user_id)
            
            if request.thread_id:
                thread_id = request.thread_id
            else:
                thread_id = await memory_manager.create_conversation_thread(
                    platform="web_interface",
                    title="Bluesky Social Media Management"
                )
            
            user_message_id = str(uuid.uuid4())
            await memory_manager.add_message(
                thread_id=thread_id,
                role="user",
                content=request.message
            )
            
            response_message_id = str(uuid.uuid4())
            await memory_manager.add_message(
                thread_id=thread_id,
                role="assistant",
                content=bluesky_response
            )
            
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return ChatResponse(
                message_id=response_message_id,
                thread_id=thread_id,
                response=bluesky_response,
                personality_used="syntaxprime",
                response_time_ms=response_time_ms,
                timestamp=end_time
            )
        
        # Continue with regular AI chat processing...
        memory_manager = get_memory_manager(user_id)
        knowledge_engine = get_knowledge_engine()
        personality_engine = get_personality_engine()
        
        # Handle conversation thread
        thread_id = request.thread_id
        if not thread_id:
            thread_id = await memory_manager.create_conversation_thread(
                platform="web_interface",
                title=None
            )
        
        # Build message content with files if present
        message_content = request.message
        if processed_files:
            file_descriptions = []
            for file_info in processed_files:
                desc = f"📎 {file_info['filename']} ({file_info['analysis']['type']}): {file_info['analysis']['description']}"
                file_descriptions.append(desc)
                
                if file_info['analysis']['extracted_text']:
                    message_content += f"\n\n--- Content from {file_info['filename']} ---\n"
                    message_content += file_info['analysis']['extracted_text'][:1000]  # Limit content
            
            message_content = f"{request.message}\n\nFiles uploaded:\n" + "\n".join(file_descriptions) + "\n\n" + message_content
        
        # Store user message
        user_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role="user",
            content=message_content,
            content_type="text_with_files" if processed_files else "text"
        )
        
        # Get conversation context
        conversation_history, context_info = await memory_manager.get_context_for_ai(
            thread_id=thread_id,
            max_tokens=200000
        )
        
        # Check for RSS/marketing insights requests
        rss_context = None
        if detect_rss_command(request.message) or detect_writing_assistance_request(request.message)[0]:
            logger.info(f"📰 RSS/Marketing request detected: {request.message}")
            rss_context = await get_rss_marketing_context(request.message)
            
            if rss_context and not rss_context.startswith("RSS_CONTEXT_ERROR"):
                logger.info("📊 RSS marketing context added successfully")
            else:
                logger.warning("⚠️ RSS marketing context failed to load")
        
        # Check for weather requests
        weather_context = None
        if detect_weather_request(request.message):
            logger.info(f"🌦️ Weather request detected for user {user_id}")
            weather_data = await get_weather_for_user(user_id)
            
            if weather_data and weather_data.get("success"):
                weather_info = weather_data["data"]
                weather_context = f"""
CURRENT WEATHER DATA:
Location: {weather_info.get('location', 'Current location')}
Temperature: {weather_info.get('temperature_f', 'N/A')}°F
Humidity: {weather_info.get('humidity', 'N/A')}%
Wind Speed: {weather_info.get('wind_speed', 'N/A')} mph
Barometric Pressure: {weather_info.get('pressure', 'N/A')} mbar
UV Index: {weather_info.get('uv_index', 'N/A')}
Visibility: {weather_info.get('visibility', 'N/A')} miles

Please respond naturally about the weather using this current data.
"""
                logger.info("🌤️ Weather context added to AI conversation")
            elif weather_data and "error" in weather_data:
                weather_context = f"""
WEATHER REQUEST DETECTED: Unfortunately, I'm having trouble accessing current weather data: {weather_data['error']}
Please respond appropriately about being unable to access weather information.
"""
                logger.warning(f"Weather API error: {weather_data['error']}")
        
        # Get knowledge sources if enabled
        knowledge_sources = []
        if request.include_knowledge:
            knowledge_sources = await knowledge_engine.search_knowledge(
                query=request.message,
                max_results=5
            )
        
        # Build AI messages
        ai_messages = []
        
        # Add system message with personality and context
        system_parts = []
        
        # Get personality prompt
        personality_prompt = personality_engine.get_personality_prompt(request.personality_id)
        system_parts.append(personality_prompt)
        
        # Add RSS marketing context if available
        if rss_context:
            system_parts.append(rss_context)
        
        # Add weather context if available
        if weather_context:
            system_parts.append(weather_context)
        
        # Add knowledge context if available
        if knowledge_sources:
            knowledge_context = "RELEVANT KNOWLEDGE BASE INFORMATION:\n"
            for source in knowledge_sources:
                knowledge_context += f"- {source['title']}: {source['content'][:200]}...\n"
            system_parts.append(knowledge_context)
        
        ai_messages.append({
            "role": "system",
            "content": "\n\n".join(system_parts)
        })
        
        # Add conversation history
        ai_messages.extend(conversation_history)
        
        # Add current user message
        ai_messages.append({
            "role": "user",
            "content": message_content
        })
        
        # Get AI response
        openrouter_client = await get_openrouter_client()
        ai_response = await openrouter_client.get_completion(
            messages=ai_messages,
            model="anthropic/claude-3.5-sonnet:beta",
            max_tokens=4000,
            temperature=0.7
        )
        
        # Process through personality engine
        final_response = personality_engine.process_ai_response(
            response=ai_response,
            personality_id=request.personality_id,
            conversation_context=conversation_history
        )
        
        # Store AI response
        knowledge_source_ids = [source.get('id', '') for source in knowledge_sources]
        response_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role="assistant",
            content=final_response,
            model_used="anthropic/claude-3.5-sonnet:beta",
            knowledge_sources_used=knowledge_source_ids
        )
        
        # Calculate response time
        end_time = datetime.now()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        logger.info(f"✅ Chat response generated in {response_time_ms}ms")
        
        return ChatResponse(
            message_id=response_message_id,
            thread_id=thread_id,
            response=final_response,
            personality_used=request.personality_id,
            response_time_ms=response_time_ms,
            knowledge_sources=knowledge_sources,
            timestamp=end_time
        )
        
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

#-- Section 7: Integration Info and Health Check Functions - updated 9/25/25 with Marketing Scraper
def get_integration_info():
    """Get information about the chat integration"""
    return {
        "name": "AI Chat System",
        "version": "2.0.0",
        "description": "Advanced chat system with file processing, weather, Bluesky, RSS Learning, and Marketing Scraper integration",
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
            "Conversation management",
            "Weather integration",
            "Bluesky social media commands",
            "RSS learning integration for writing assistance",
            "Marketing scraper for competitive analysis"  # NEW
        ],
        "file_upload_support": True,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "supported_file_types": list(ALLOWED_EXTENSIONS),
        "weather_integration": True,
        "bluesky_integration": True,
        "rss_learning_integration": True,
        "marketing_scraper_integration": True  # NEW
    }

def check_module_health() -> Dict[str, Any]:
    """Check the health of the AI chat module"""
    missing_vars = []
    warnings = []
    
    if not UPLOAD_DIR.exists():
        warnings.append("Upload directory not found")
    
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    if not os.getenv("TOMORROW_IO_API_KEY"):
        warnings.append("Weather integration not configured (TOMORROW_IO_API_KEY missing)")
    
    bluesky_configured = any([
        os.getenv("BLUESKY_PERSONAL_PASSWORD"),
        os.getenv("BLUESKY_ROSE_ANGEL_PASSWORD"),
        os.getenv("BLUESKY_BINGE_TV_PASSWORD"),
        os.getenv("BLUESKY_MEALS_FEELZ_PASSWORD"),
        os.getenv("BLUESKY_DAMN_IT_CARL_PASSWORD")
    ])
    
    if not bluesky_configured:
        warnings.append("Bluesky integration not configured (account passwords missing)")
    
    rss_configured = bool(os.getenv("DATABASE_URL"))
    
    if not rss_configured:
        warnings.append("RSS Learning integration not configured (DATABASE_URL missing)")
    
    # NEW: Check marketing scraper configuration
    scraper_configured = bool(os.getenv("DATABASE_URL"))  # Uses same DB as RSS
    
    if not scraper_configured:
        warnings.append("Marketing Scraper integration not configured (DATABASE_URL missing)")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "warnings": warnings,
        "upload_directory": str(UPLOAD_DIR),
        "max_file_size": f"{MAX_FILE_SIZE // (1024 * 1024)}MB",
        "weather_integration_available": bool(os.getenv("TOMORROW_IO_API_KEY")),
        "bluesky_integration_available": bluesky_configured,
        "rss_learning_integration_available": rss_configured,
        "marketing_scraper_integration_available": scraper_configured  # NEW
    }
