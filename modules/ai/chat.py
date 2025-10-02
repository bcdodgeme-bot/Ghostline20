# modules/ai/chat.py
# AI Chat Integration Helper Functions for Syntax Prime V2
# Provides integration functions for router.py - NO ENDPOINTS HERE
# Clean helper module with all integration logic for weather, prayer times, scraper, etc.
# Date: 9/26/25 - Converted to helper module only
# Date: 9/27/25 - Added Google Trends integration and Prayer Notifications
# Date: 9/28/25 - Added Voice Synthesis and Image Generation detection

#-- Section 1: Core Imports - 9/26/25
import os
import uuid
import json
import asyncio
from datetime import datetime
import pytz
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging
import httpx
import os
database_url = os.getenv('DATABASE_URL')

# File processing imports
from PIL import Image, ImageOps
import pdfplumber
import pandas as pd
import magic
import cv2
import numpy as np
from io import BytesIO
import base64

# Add to the existing imports section:
from .pattern_fatigue import get_pattern_fatigue_tracker, handle_duplicate_complaint, handle_time_joke_complaint

# Google Trends integration imports - 9/27/25
from ..integrations.google_trends.opportunity_detector import OpportunityDetector
from ..integrations.google_trends.opportunity_training import OpportunityTraining
from ..integrations.google_trends.integration_info import check_module_health

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

#-- Section 2: DateTime Helper Functions - 9/26/25
def get_current_datetime_context() -> dict:
    """
    Get comprehensive current date/time context for AI personalities
    Returns properly formatted date/time info in multiple formats
    """
    now = datetime.now()
    
    # Get user's timezone (defaulting to EST if not available)
    try:
        user_timezone = pytz.timezone('America/New_York')  # Default to Eastern
        now_user_tz = now.astimezone(user_timezone)
    except:
        now_user_tz = now
    
    return {
        "current_date": now_user_tz.strftime("%Y-%m-%d"),  # 2025-09-26
        "current_time_24h": now_user_tz.strftime("%H:%M"),  # 15:19
        "current_time_12h": now_user_tz.strftime("%I:%M %p"),  # 3:19 PM
        "day_of_week": now_user_tz.strftime("%A"),  # Friday
        "month_name": now_user_tz.strftime("%B"),  # September
        "full_datetime": now_user_tz.strftime("%A, %B %d, %Y at %H:%M"),  # Friday, September 26, 2025 at 15:19
        "timezone": str(now_user_tz.tzinfo),
        "iso_timestamp": now_user_tz.isoformat(),
        "unix_timestamp": int(now_user_tz.timestamp())
    }

#-- Section 3: Weather Integration Functions - 9/26/25
def detect_weather_request(message: str) -> bool:
    """Detect weather-related requests"""
    weather_keywords = [
        "weather", "temperature", "forecast", "rain", "snow", "sunny",
        "cloudy", "storm", "wind", "humidity", "barometric pressure",
        "headache weather", "pressure change", "uv index"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in weather_keywords)

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
            response = await client.get(f"{base_url}/google/auth/start?user_id={user_id}")
            
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

#-- Section 4: Bluesky Integration Functions - 9/26/25
#-- Section 4: Bluesky Integration Functions updated for posting - 9/30/25
import re
from typing import Tuple, Optional

def detect_bluesky_post_command(message: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Detect V1-style Bluesky posting commands
    
    Returns: (is_post_command, command_type, account, text)
    command_type: 'direct', 'write', 'improve', 'smart'
    """
    message_lower = message.lower().strip()
    
    # Pattern 1: bluesky post [account] "text"
    direct_pattern = r'bluesky post (\w+)\s+["\'](.+?)["\']'
    match = re.search(direct_pattern, message, re.IGNORECASE)
    if match:
        account = match.group(1)
        text = match.group(2)
        return True, 'direct', account, text
    
    # Pattern 2: write bluesky post about [topic] for [account]
    write_pattern = r'write bluesky post about (.+?) for (\w+)'
    match = re.search(write_pattern, message, re.IGNORECASE)
    if match:
        topic = match.group(1).strip()
        account = match.group(2).strip()
        return True, 'write', account, topic
    
    # Pattern 3: improve bluesky post: [text]
    improve_pattern = r'improve bluesky post:\s*(.+)'
    match = re.search(improve_pattern, message, re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(1).strip()
        return True, 'improve', None, text
    
    # Pattern 4: bluesky post smart "text"
    smart_pattern = r'bluesky post smart\s+["\'](.+?)["\']'
    match = re.search(smart_pattern, message, re.IGNORECASE)
    if match:
        text = match.group(1)
        return True, 'smart', None, text
    
    return False, '', None, None

def detect_bluesky_command(message: str) -> bool:
    """Detect ALL Bluesky commands including V1-style posting"""
    
    # Check for V1-style posting commands first
    is_post, _, _, _ = detect_bluesky_post_command(message)
    if is_post:
        return True
    
    # Original detection for management commands
    bluesky_keywords = [
        "bluesky scan", "bluesky opportunities", "bluesky accounts",
        "bluesky health", "bluesky status", "bluesky", "social media opportunities"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in bluesky_keywords)

async def process_bluesky_post_command(command_type: str, account: Optional[str],
                                      text: str, user_id: str) -> str:
    """Process V1-style Bluesky posting commands"""
    try:
        from ..integrations.bluesky.multi_account_client import get_bluesky_multi_client
        
        multi_client = get_bluesky_multi_client()
        
        # Account name mapping
        account_map = {
            'syntaxprime': 'personal',
            'personal': 'personal',
            'roseangel': 'rose_angel',
            'rose': 'rose_angel',
            'rose_angel': 'rose_angel',
            'bingetv': 'binge_tv',
            'tv': 'binge_tv',
            'binge_tv': 'binge_tv',
            'mealsfeelz': 'meals_feelz',
            'meals': 'meals_feelz',
            'meals_feelz': 'meals_feelz',
            'carl': 'damn_it_carl',
            'damnitcarl': 'damn_it_carl',
            'damn_it_carl': 'damn_it_carl'
        }
        
        # Command 1: Direct Post
        if command_type == 'direct':
            account_id = account_map.get(account.lower())
            
            if not account_id:
                return f"❌ Unknown account: {account}\n\nAvailable: syntaxprime, roseangel, bingetv, mealsfeelz, damnitcarl"
            
            if len(text) > 300:
                return f"❌ Post too long! ({len(text)}/300 characters)\n\nPlease shorten your post."
            
            result = await multi_client.create_post(account_id, text)
            
            if result['success']:
                account_info = multi_client.get_account_info(account_id)
                return f"""✅ Posted to {account_info['handle']}!

📝 "{text}"

Character count: {len(text)}/300"""
            else:
                return f"❌ Failed to post: {result.get('error', 'Unknown error')}"
        
        # Command 2: AI Write Post
        elif command_type == 'write':
            account_id = account_map.get(account.lower())
            
            if not account_id:
                return f"❌ Unknown account: {account}\n\nAvailable: syntaxprime, roseangel, bingetv, mealsfeelz, damnitcarl"
            
            account_info = multi_client.get_account_info(account_id)
            personality = account_info['personality']
            
            ai_post = await _generate_ai_post(text, personality, account_id)
            
            return f"""🤖 AI-Generated Post for {account_info['handle']}

📝 **Draft:**
"{ai_post}"

Character count: {len(ai_post)}/300

To post this, say:
`bluesky post {account} "{ai_post}"`

Or edit it first!"""
        
        # Command 3: Improve Post
        elif command_type == 'improve':
            improved_text = await _improve_post_text(text)
            
            return f"""✨ Improved Version:

"{improved_text}"

Character count: {len(improved_text)}/300

Original:
"{text}"

To post this, choose an account:
`bluesky post [account] "{improved_text}"`"""
        
        # Command 4: Smart Post
        elif command_type == 'smart':
            best_account = await _pick_best_account(text, multi_client)
            
            if len(text) > 300:
                return f"❌ Post too long! ({len(text)}/300 characters)\n\nPlease shorten your post."
            
            result = await multi_client.create_post(best_account, text)
            
            if result['success']:
                account_info = multi_client.get_account_info(best_account)
                return f"""🎯 Smart Post - Selected {account_info['handle']}

📝 "{text}"

Why this account: {_get_account_reasoning(best_account, text)}

Character count: {len(text)}/300"""
            else:
                return f"❌ Failed to post: {result.get('error', 'Unknown error')}"
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

async def _generate_ai_post(topic: str, personality: str, account_id: str) -> str:
    """Generate AI post based on topic and personality"""
    
    if 'coding' in topic.lower() or 'web' in topic.lower() or 'python' in topic.lower():
        posts = {
            'syntaxprime': f"Hot take: {topic} is actually way simpler than everyone makes it sound. Here's why... 🧵",
            'professional': f"Key insights on {topic} for modern development practices. Worth considering for your next project.",
            'compassionate': f"Learning about {topic}? Remember: everyone starts somewhere. You've got this! 💚"
        }
    else:
        posts = {
            'syntaxprime': f"Real talk about {topic} - it's not what you think. (Spoiler: it's better) ✨",
            'professional': f"Important considerations regarding {topic}. Essential reading for professionals in the field.",
            'compassionate': f"Thinking about {topic} today. It's important to approach this with empathy and understanding. 🌟"
        }
    
    return posts.get(personality, posts['syntaxprime'])

async def _improve_post_text(original_text: str) -> str:
    """Improve post text while maintaining meaning"""
    
    improved = original_text.strip()
    
    # Add emoji if missing and appropriate
    if not any(char in improved for char in '😀😁😂🤣😃😄😅😆😉😊😋😎✨🚀💚🌟'):
        if 'great' in improved.lower() or 'awesome' in improved.lower():
            improved += " ✨"
        elif 'think' in improved.lower() or 'consider' in improved.lower():
            improved += " 🤔"
    
    # Ensure proper capitalization
    if improved and improved[0].islower():
        improved = improved[0].upper() + improved[1:]
    
    # Trim if too long
    if len(improved) > 280:
        improved = improved[:277] + "..."
    
    return improved

async def _pick_best_account(text: str, multi_client) -> str:
    """Analyze text content and pick best account"""
    
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['code', 'coding', 'python', 'javascript', 'web', 'dev', 'tech']):
        return 'personal'
    
    elif any(word in text_lower for word in ['business', 'nonprofit', 'consulting', 'strategy', 'professional']):
        return 'rose_angel'
    
    elif any(word in text_lower for word in ['tv', 'show', 'movie', 'watch', 'streaming', 'netflix', 'series']):
        return 'binge_tv'
    
    elif any(word in text_lower for word in ['food', 'meal', 'recipe', 'cooking', 'hunger', 'charity', 'giving']):
        return 'meals_feelz'
    
    elif any(word in text_lower for word in ['creative', 'burnout', 'therapy', 'art', 'design']):
        return 'damn_it_carl'
    
    return 'personal'

def _get_account_reasoning(account_id: str, text: str) -> str:
    """Explain why this account was chosen"""
    
    reasons = {
        'personal': "Content matches your tech/coding expertise",
        'rose_angel': "Professional consulting/business content",
        'binge_tv': "Entertainment and streaming content",
        'meals_feelz': "Food, charity, or community focus",
        'damn_it_carl': "Creative and personal expression"
    }
    
    return reasons.get(account_id, "Best match for your content")

async def process_bluesky_command(message: str, user_id: str) -> str:
    """Process Bluesky-related commands"""
    try:
        # Check for V1-style posting commands FIRST
        is_post, cmd_type, account, text = detect_bluesky_post_command(message)
        if is_post:
            return await process_bluesky_post_command(cmd_type, account, text, user_id)
        
        # Original management commands
        from ..integrations.bluesky.multi_account_client import get_bluesky_multi_client
        from ..integrations.bluesky.engagement_analyzer import get_engagement_analyzer
        from ..integrations.bluesky.approval_system import get_approval_system
        from ..integrations.bluesky.notification_manager import get_notification_manager
        
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
            
            response_parts = ["📊 **Current Bluesky Engagement Opportunities**\n"]
            
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
            account_statuses = multi_client.get_all_accounts_status()
            configured_count = len([s for s in account_statuses.values() if s.get('configured', False)])
            
            response_parts = ["**Bluesky Account Status**\n"]
            
            for account_id, status in account_statuses.items():
                emoji = "✅" if status.get('authenticated', False) else "❌"
                username = status.get('username', f'Account {account_id}')
                last_scan = status.get('last_scan', 'Never')
                
                response_parts.append(f"{emoji} **{username}**")
                response_parts.append(f"   Last scan: {last_scan}")
                response_parts.append("")
            
            response_parts.append(f"**Summary:** {configured_count}/5 accounts configured and ready")
            return "\n".join(response_parts)
        
        else:
            account_statuses = get_bluesky_multi_client().get_all_account_status()
            return f"""🔵 **Bluesky Social Media Intelligence**

📱 **Configured Accounts:** {len(account_statuses)}/5
🤖 **Features:** Keyword intelligence, engagement suggestions, approval workflow
⏰ **Auto-Scan:** Every 3.5 hours across all accounts

**Available Commands:**
• `bluesky scan` - Force scan all accounts  
• `bluesky opportunities` - View engagement suggestions
• `bluesky accounts` - Check account status
• `bluesky post [account] "text"` - Post directly
• `write bluesky post about [topic] for [account]` - AI generates post
• `improve bluesky post: [text]` - AI improves your draft
• `bluesky post smart "text"` - AI picks best account

Ready to find your next great engagement opportunity?"""
    
    except Exception as e:
        logger.error(f"Bluesky command processing failed: {e}")
        return f"❌ **Bluesky Command Error:** {str(e)}\n\nTry `bluesky health` to check system status."

async def trigger_background_scan(user_id: str):
    """Trigger a background scan of all Bluesky accounts"""
    try:
        from ..integrations.bluesky.multi_account_client import get_bluesky_multi_client
        from ..integrations.bluesky.engagement_analyzer import get_engagement_analyzer
        from ..integrations.bluesky.approval_system import get_approval_system
        
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

#-- Section 5: RSS Learning Functions - 9/26/25
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
        from ..integrations.rss_learning.marketing_insights import MarketingInsightsExtractor
        
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

#-- Section 6: Marketing Scraper Functions - 9/26/25
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
        from ..integrations.marketing_scraper.scraper_client import MarketingScraperClient
        from ..integrations.marketing_scraper.content_analyzer import ContentAnalyzer
        from ..integrations.marketing_scraper.database_manager import ScrapedContentDatabase
        
        message_lower = message.lower()
        
        if 'scrape history' in message_lower:
            # Get scrape history
            db = ScrapedContentDatabase()
            history = await db.get_user_scrape_history(user_id=user_id, limit=10)
            
            if not history:
                return """🔍 **Marketing Scraper History**

No scraping history found. Start analyzing competitors with:
• `scrape https://example.com` - Analyze any website
• `scrape insights` - Get analysis from previous scrapes"""
            
            response_parts = ["**Recent Scraping History**\n"]
            
            for i, item in enumerate(history, 1):
                domain = item.get('domain', 'Unknown')
                scraped_at = item.get('created_at', 'Unknown time')
                word_count = item.get('word_count', 0)
                
                response_parts.append(f"**{i}. {domain}**")
                response_parts.append(f"   📅 Scraped: {scraped_at}")
                response_parts.append(f"   📄 Words: {word_count}")
                response_parts.append("")
            
            response_parts.append("💡 Use `scrape insights` to get AI analysis of all scraped content.")
            return "\n".join(response_parts)
        
        elif 'scrape insights' in message_lower:
            # Get competitive insights from all scraped content
            db = ScrapedContentDatabase()
            
            # Search for recent content using empty topic to get all
            recent_content = await db.search_scraped_insights(user_id=user_id, topic="", limit=20)
            
            if not recent_content:
                return """🔍 **Marketing Scraper Insights**

No scraped content available for analysis. 

Start building your competitive intelligence with:
• `scrape https://competitor.com` - Analyze competitor sites
• `scrape https://industry-blog.com` - Analyze industry content"""
            
            # Generate competitive insights summary
            response_parts = [
                "🧠 **Competitive Intelligence Report**",
                f"📊 Based on {len(recent_content)} recently analyzed websites",
                ""
            ]
            
            # Show key insights from stored content
            for i, content in enumerate(recent_content[:5], 1):
                insights = content.get('key_insights', {})
                response_parts.append(f"**{i}. {content['domain']}**")
                if insights.get('value_proposition'):
                    response_parts.append(f"   💎 Value Prop: {insights['value_proposition'][:100]}...")
                if insights.get('content_strategy'):
                    response_parts.append(f"   📄 Strategy: {insights['content_strategy'][:100]}...")
                response_parts.append("")
            
            response_parts.append("📈 Use `scrape https://newsite.com` to add more competitive intelligence!")
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
            analyzer = ContentAnalyzer()
            db = ScrapedContentDatabase()
            
            try:
                # Scrape the website
                scraped_data = await scraper.scrape_website(url)
                
                if not scraped_data.get('scrape_status') == 'completed':
                    return f"""❌ **Scraping Failed**
                    
Unable to analyze {url}
Error: {scraped_data.get('error_message', 'Unknown error')}

Please verify the URL is accessible and try again."""
                
                # Analyze the content
                analysis = await analyzer.analyze_scraped_content(scraped_data)
                
                # Store in database
                await db.store_scraped_content(
                    user_id=user_id,
                    scraped_data=scraped_data,
                    analysis_results=analysis
                )
                
                # Generate response
                domain = scraped_data.get('domain', url)
                word_count = scraped_data.get('word_count', 0)
                
                response_parts = [
                    f"✅ **Successfully Analyzed: {domain}**",
                    f"📄 Content extracted: {word_count:,} words",
                    ""
                ]
                
                if analysis.get('competitive_insights'):
                    insights = analysis.get('competitive_insights', {})
                    if insights.get('value_proposition'):
                        response_parts.extend([
                            "**💎 Value Proposition:**",
                            f"• {insights['value_proposition'][:200]}...",
                            ""
                        ])
                
                if analysis.get('marketing_angles'):
                    marketing = analysis.get('marketing_angles', {})
                    if marketing.get('content_strategy'):
                        response_parts.extend([
                            "**📄 Content Strategy:**",
                            f"• {marketing['content_strategy'][:200]}...",
                            ""
                        ])
                
                if analysis.get('cta_analysis'):
                    cta = analysis.get('cta_analysis', {})
                    if cta.get('cta_placement_strategy'):
                        response_parts.extend([
                            "**🔥 CTA Strategy:**",
                            f"• {cta['cta_placement_strategy'][:200]}...",
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

#-- Section 7: Prayer Times Functions - 9/26/25 (Updated 9/27/25)
def detect_prayer_command(message: str) -> bool:
    """Detect prayer-related requests"""
    prayer_keywords = [
        "prayer", "prayers", "salah", "namaz", "fajr", "dhuhr", "asr", "maghrib", "isha",
        "prayer time", "prayer times", "next prayer", "when is prayer", "how long until",
        "how long till", "time until prayer", "prayer schedule", "islamic time", "islamic date"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in prayer_keywords)

def detect_prayer_question_type(message: str) -> str:
    """Determine what type of prayer question the user is asking"""
    message_lower = message.lower()
    
    if any(phrase in message_lower for phrase in ["how long", "time until", "time till", "when is next"]):
        return "next_prayer"
    elif any(phrase in message_lower for phrase in ["prayer times today", "today's prayer", "prayer schedule", "all prayer"]):
        return "daily_schedule"
    elif any(phrase in message_lower for phrase in ["islamic date", "hijri", "islamic calendar"]):
        return "islamic_date"
    else:
        return "general_prayer"

async def process_prayer_command(message: str, user_id: str, ip_address: str = None) -> str:
    """Process prayer-related commands using the cached database system"""
    try:
        from ..integrations.prayer_times.database_manager import get_prayer_database_manager
        
        question_type = detect_prayer_question_type(message)
        
        # Get prayer manager and pass IP address for location detection
        prayer_manager = await get_prayer_database_manager()
        
        if question_type == "next_prayer":
            # "How long till Dhuhr?" type questions
            prayer_data = await prayer_manager.get_todays_prayer_times(ip_address)
            if not prayer_data:
                return """🕌 **Prayer Time Service Unavailable**
                
Unable to retrieve prayer times at the moment. Please try again in a few moments."""
            
            next_prayer_info = await prayer_manager.get_next_prayer_info()
            location_name = prayer_data['location']['name']
            
            if not next_prayer_info:
                return """🕌 **Prayer Time Service Unavailable**
                
Unable to retrieve prayer times at the moment. Please try again in a few moments."""
            
            prayer_name = next_prayer_info['prayer_name']
            prayer_time = next_prayer_info['prayer_time']
            time_until_text = next_prayer_info['time_until_text']
            is_today = next_prayer_info['is_today']
            
            day_text = "today" if is_today else "tomorrow"
            
            return f"""🕌 **Next Prayer: {prayer_name}**

⏰ **Time:** {prayer_time} ({day_text})
⏳ **Time Until:** {time_until_text}

Prayer times are calculated for {location_name} using ISNA method."""
        
        elif question_type == "daily_schedule":
            # "What are prayer times today?" type questions
            prayer_data = await prayer_manager.get_todays_prayer_times(ip_address)
            
            if not prayer_data:
                return """🕌 **Prayer Schedule Unavailable**
                
Unable to retrieve today's prayer schedule. Please try again in a few moments."""
            
            prayer_times = prayer_data['prayer_times']
            islamic_date = prayer_data['islamic_date']
            formatted_date = prayer_data.get('formatted_date', prayer_data['date'])
            location_name = prayer_data['location']['name']
            
            response_parts = [
                f"🕌 **Prayer Times for {formatted_date}**",
                ""
            ]
            
            # Add Islamic date if available
            if islamic_date['date'] != 'N/A':
                response_parts.extend([
                    f"📅 **Islamic Date:** {islamic_date['date']} {islamic_date['month']} {islamic_date['year']}",
                    ""
                ])
            
            response_parts.extend([
                "🕌 **Daily Prayer Schedule:**",
                f"   **Fajr:** {prayer_times['fajr']}",
                f"   **Dhuhr:** {prayer_times['dhuhr']}",
                f"   **Asr:** {prayer_times['asr']}",
                f"   **Maghrib:** {prayer_times['maghrib']}",
                f"   **Isha:** {prayer_times['isha']}",
                "",
                f"📍 Calculated for {location_name} using ISNA method"
            ])
            
            return "\n".join(response_parts)
        
        elif question_type == "islamic_date":
            # Islamic calendar questions
            prayer_data = await prayer_manager.get_todays_prayer_times(ip_address)
            
            if not prayer_data or prayer_data['islamic_date']['date'] == 'N/A':
                return """📅 **Islamic Calendar Information**
                
Islamic date information is currently unavailable. Please try again later."""
            
            islamic_date = prayer_data['islamic_date']
            gregorian_date = prayer_data.get('formatted_date', prayer_data['date'])
            
            return f"""📅 **Islamic Calendar Information**

**Today's Date:**
📆 Gregorian: {gregorian_date}
🗓️ Islamic: {islamic_date['date']} {islamic_date['month']} {islamic_date['year']}

Islamic dates are calculated using the AlAdhan calendar system."""
        
        else:
            # General prayer information
            prayer_data = await prayer_manager.get_todays_prayer_times(ip_address)
            next_prayer_info = await prayer_manager.get_next_prayer_info()
            
            if not next_prayer_info or not prayer_data:
                return """🕌 **Prayer Time Information**
                
Prayer time service is currently unavailable. Please try again in a few moments."""
            
            next_prayer = next_prayer_info['prayer_name']
            time_until = next_prayer_info['time_until_text']
            islamic_date = prayer_data['islamic_date']
            location_name = prayer_data['location']['name']
            
            response_parts = [
                "🕌 **Prayer Time Information**",
                "",
                f"⏰ **Next Prayer:** {next_prayer} in {time_until}",
                f"📍 **Location:** {location_name}",
                ""
            ]
            
            if islamic_date['date'] != 'N/A':
                response_parts.extend([
                    f"📅 **Islamic Date:** {islamic_date['date']} {islamic_date['month']} {islamic_date['year']}",
                    ""
                ])
            
            response_parts.extend([
                "**Available Commands:**",
                "• 'How long till [prayer name]?' - Next prayer countdown",
                "• 'What are prayer times today?' - Full daily schedule",
                "• 'Islamic date' - Current Hijri calendar date"
            ])
            
            return "\n".join(response_parts)
    
    except Exception as e:
        logger.error(f"Prayer command processing failed: {e}")
        return f"""🕌 **Prayer Time Service Error**
        
An error occurred while retrieving prayer information: {str(e)}

Please try again or contact support if the issue persists."""

#-- Section 8: File Processing Functions - 9/26/25
async def process_uploaded_files(files) -> List[Dict]:
    """Process uploaded files and return file information"""
    from fastapi import UploadFile
    
    processed_files = []
    
    for file in files:
        if not file.filename:
            continue
            
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise Exception(f"File type {file_ext} not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")
        
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise Exception(f"File {file.filename} too large. Max size: 10MB")
        
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

#-- Section 9: Voice Synthesis Functions - 9/28/25
def detect_voice_command(message: str) -> bool:
    """Detect voice synthesis commands"""
    voice_keywords = [
        "voice synthesize", "voice generate", "say this", "speak this",
        "voice this", "read this", "voice history", "voice personalities",
        "text to speech", "tts", "synthesize voice", "generate audio"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in voice_keywords)

def extract_text_for_voice(message: str) -> str:
    """Extract text to synthesize from voice command"""
    message_lower = message.lower()
    
    # Common patterns for voice commands
    patterns = [
        r'voice synthesize (.+)',
        r'voice generate (.+)',
        r'say this[:\s]+(.+)',
        r'speak this[:\s]+(.+)',
        r'voice this[:\s]+(.+)',
        r'read this[:\s]+(.+)',
        r'synthesize (.+)',
        r'tts (.+)'
    ]
    
    import re
    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            return match.group(1).strip()
    
    # If no pattern matches, check if message is short enough to be direct synthesis
    if len(message.split()) <= 50:  # Reasonable voice synthesis length
        return message
    
    return None

async def process_voice_command(message: str, user_id: str) -> str:
    """Process voice synthesis commands"""
    try:
        from ..integrations.voice_synthesis import (
            get_voice_client,
            get_personality_voice_manager,
            get_audio_cache_manager
        )
        
        message_lower = message.lower()
        
        if 'voice history' in message_lower:
            # Get voice synthesis history
            audio_manager = get_audio_cache_manager()
            stats = await audio_manager.get_cache_statistics()
            
            recent_generations = stats.get('recent_generations_24h', 0)
            total_files = stats.get('total_files', 0)
            total_size_mb = stats.get('total_size_mb', 0.0)
            
            return f"""🎤 **Voice Synthesis History**

📊 **Recent Activity:** {recent_generations} audio files generated today
💾 **Total Generated:** {total_files} audio files
📈 **Storage Used:** {total_size_mb:.1f} MB

**Available Commands:**
• `voice synthesize [text]` - Generate speech from text
• `voice personalities` - View available voices
• Click speaker buttons on AI responses for instant audio

Ready to give your words a voice?"""
        
        elif 'voice personalities' in message_lower or 'voice list' in message_lower:
            # Show personality voice mappings
            personality_manager = get_personality_voice_manager()
            mappings = await personality_manager.get_all_personality_mappings()
            
            response_parts = ["🎭 **Personality Voice Mappings**\n"]
            
            for personality_id, mapping in mappings.items():
                primary_voice = mapping.get('primary_voice', 'Unknown')
                style = mapping.get('voice_settings', {}).get('style', 'Standard')
                
                response_parts.append(f"**{personality_id.title()}:** {primary_voice}")
                response_parts.append(f"   Style: {style.replace('_', ' ').title()}")
                response_parts.append("")
            
            response_parts.append("Each personality has been carefully matched with voices chosen by SyntaxPrime for optimal expression!")
            return "\n".join(response_parts)
        
        else:
            # Extract text to synthesize
            text_to_synthesize = extract_text_for_voice(message)
            
            if not text_to_synthesize:
                return """🎤 **Voice Synthesis Commands**

**Usage:**
• `voice synthesize [your text here]` - Generate speech from text
• `voice history` - View synthesis history
• `voice personalities` - See available voices

**Examples:**
• `voice synthesize Hello everyone, welcome to the presentation`
• `say this: Thanks for joining our meeting today`
• `read this: The quarterly results show significant growth`

**Features:**
✅ Personality-specific voices (SyntaxPrime's choices)
✅ High-quality MP3 generation
✅ Instant inline playback
✅ Database caching for re-use

Ready to bring your words to life?"""
            
            # Synthesize the audio
            voice_client = get_voice_client()
            personality_manager = get_personality_voice_manager()
            audio_manager = get_audio_cache_manager()
            
            # Get voice for current context (default to syntaxprime)
            personality_id = 'syntaxprime'  # Could be determined from context
            voice_id = personality_manager.get_voice_for_personality(personality_id)
            
            # Generate speech
            synthesis_result = await voice_client.generate_speech(
                text=text_to_synthesize,
                voice_id=voice_id,
                personality_id=personality_id
            )
            
            if not synthesis_result.get('success'):
                return f"""❌ **Voice Synthesis Failed**

Unable to generate audio for: "{text_to_synthesize[:50]}..."

Error: {synthesis_result.get('error', 'Unknown error')}

Please try again or contact support if the issue persists."""
            
            # Create a message ID for caching
            message_id = str(uuid.uuid4())
            
            # Cache the audio
            cache_result = await audio_manager.cache_audio(
                message_id=message_id,
                audio_data=synthesis_result['audio_data'],
                metadata={
                    'personality_id': personality_id,
                    'voice_id': voice_id,
                    'text_length': len(text_to_synthesize),
                    'generation_time_ms': synthesis_result.get('generation_time_ms'),
                    'file_format': 'mp3'
                }
            )
            
            generation_time = synthesis_result.get('generation_time_seconds', 0)
            file_size = len(synthesis_result['audio_data'])
            voice_name = personality_manager._get_voice_name_from_id(voice_id)
            
            return f"""✅ **Voice Synthesis Complete**

🎤 **Text:** "{text_to_synthesize[:100]}{'...' if len(text_to_synthesize) > 100 else ''}"
🗣️ **Voice:** {voice_name} ({personality_id} personality)
⏱️ **Generation Time:** {generation_time:.1f} seconds
📁 **File Size:** {file_size:,} bytes

🔊 **Audio URL:** `/api/voice/audio/{message_id}`

The audio has been generated and cached for playback. Use the audio URL in your frontend to play the synthesized speech!"""
    
    except Exception as e:
        logger.error(f"Voice command processing failed: {e}")
        return f"❌ **Voice Synthesis Error:** {str(e)}\n\nTry `voice synthesize hello world` to test the system."

#-- Section 10: Image Generation Functions - 9/28/25
def detect_image_command(message: str) -> bool:
    """Detect image generation commands"""
    image_keywords = [
        "image create", "image generate", "generate image", "create image",
        "image blog", "image social", "image marketing", "image history",
        "image download", "make image", "draw image", "picture of",
        "visualize this", "show me", "image style", "mockup"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in image_keywords)

def extract_image_prompt(message: str) -> tuple[str, str]:
    """Extract image prompt and content type from command"""
    message_lower = message.lower()
    
    # Detect content type from command
    content_type = 'general'
    if 'blog' in message_lower:
        content_type = 'blog'
    elif 'social' in message_lower:
        content_type = 'social'
    elif 'marketing' in message_lower:
        content_type = 'marketing'
    elif 'illustration' in message_lower:
        content_type = 'illustration'
    
    # Extract prompt text
    import re
    patterns = [
        r'image create (.+)',
        r'image generate (.+)',
        r'generate image (.+)',
        r'create image (.+)',
        r'image blog (.+)',
        r'image social (.+)',
        r'image marketing (.+)',
        r'make image (.+)',
        r'draw (.+)',
        r'picture of (.+)',
        r'visualize (.+)',
        r'show me (.+)'
        r'mockup (.+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            return match.group(1).strip(), content_type
    
    # If no pattern matches but it's an image command, use whole message as prompt
    if detect_image_command(message):
        return message.strip(), content_type
    
    return None, content_type

async def process_image_command(message: str, user_id: str) -> str:
    """Process image generation commands"""
    try:
        from ..integrations.image_generation import (
            generate_image_for_chat,
            get_image_history_for_chat
        )
        from ..integrations.image_generation.database_manager import ImageDatabase
        
        message_lower = message.lower()
        
        if 'image history' in message_lower:
            # Get image generation history
            history = await get_image_history_for_chat(user_id, limit=10)
            
            if not history:
                return """🎨 **Image Generation History**

No images generated yet. Start creating with:
• `image create [description]` - Generate any image
• `image blog [topic]` - Create blog header image
• `image social [content]` - Generate social media graphic

Ready to bring your ideas to life?"""
            
            response_parts = ["🖼️ **Recent Generated Images**\n"]
            
            for i, img in enumerate(history, 1):
                response_parts.append(f"**{i}. {img['content_type'].title()} Image**")
                response_parts.append(f"   📝 Prompt: {img['prompt']}")
                response_parts.append(f"   🗓️ Created: {img['created_at']}")
                response_parts.append(f"   📥 Downloads: {img['download_count']}")
                response_parts.append("")
            
            response_parts.append("💡 Use `image create [new prompt]` to generate more images!")
            return "\n".join(response_parts)
        
        else:
            # Extract prompt and generate image
            prompt, content_type = extract_image_prompt(message)
            
            if not prompt:
                return """🎨 **Image Generation Commands**

**Usage:**
• `image create [description]` - Generate image from description
• `image blog [topic]` - Create blog featured image
• `image social [content]` - Generate social media graphic
• `image marketing [campaign]` - Create marketing visual
• `image history` - View generated images

**Examples:**
• `image create a professional business meeting in a modern office`
• `image blog content marketing trends for 2024`
• `image social new product announcement celebration`
• `image marketing email campaign header design`

**Features:**
✅ Inline base64 display (no external URLs)
✅ Smart model selection for quality
✅ Multiple download formats
✅ Content-type optimization
✅ Style templates available

Ready to create stunning visuals?"""
            
            # Generate the image
            generation_result = await generate_image_for_chat(
                prompt=prompt,
                content_type=content_type,
                user_id=user_id
            )
            
            if not generation_result.get('success'):
                return f"""❌ **Image Generation Failed**

Unable to create image for: "{prompt[:50]}..."

Error: {generation_result.get('error', 'Unknown error')}

Please try a different prompt or contact support if the issue persists."""
            
            # Successful generation
            image_id = generation_result.get('image_id', 'unknown')
            model_used = generation_result.get('model_used', 'Unknown')
            generation_time = generation_result.get('generation_time_seconds', 0)
            enhanced_prompt = generation_result.get('enhanced_prompt', prompt)
            resolution = generation_result.get('resolution', '1024x1024')
            image_base64 = generation_result.get('image_base64', '')
            
            return f"""✅ **Image Generated Successfully**

🎨 **Original Prompt:** "{prompt}"
🧠 **Enhanced Prompt:** "{enhanced_prompt[:100]}{'...' if len(enhanced_prompt) > 100 else ''}"
🤖 **Model Used:** {model_used}
📐 **Resolution:** {resolution}
⏱️ **Generation Time:** {generation_time:.1f} seconds
💾 **Image ID:** {image_id}

🖼️ **Image displayed below**

<IMAGE_DATA>{image_base64}</IMAGE_DATA>

**Download Options:**
📥 PNG: `/integrations/image-generation/download/{image_id}?format=png`
📥 JPG: `/integrations/image-generation/download/{image_id}?format=jpg`
📥 WebP: `/integrations/image-generation/download/{image_id}?format=webp`

Your visual idea has been brought to life! 🌟"""
    
    except Exception as e:
        logger.error(f"Image command processing failed: {e}")
        return f"❌ **Image Generation Error:** {str(e)}\n\nTry `image create blue circle` to test the system."

#-- Section 11: Google Trends Integration Functions - 9/27/25
def detect_trends_command(message: str) -> tuple[bool, str]:
    """Detect Google Trends commands and determine command type"""
    trends_keywords = [
        'trends', 'trending', 'google trends', 'opportunities',
        'good match', 'bad match', 'train trends', 'trends status',
        'trends health', 'trend opportunities', 'trends scan'
    ]
    
    message_lower = message.lower()
    
    # Check if it's a trends-related command
    is_trends_command = any(keyword in message_lower for keyword in trends_keywords)
    
    if not is_trends_command:
        return False, ''
    
    # Determine command type
    if any(term in message_lower for term in ['good match', 'bad match']):
        return True, 'training_feedback'
    elif 'opportunities' in message_lower:
        return True, 'view_opportunities'
    elif 'scan' in message_lower:
        return True, 'scan_trends'
    elif 'status' in message_lower or 'health' in message_lower:
        return True, 'status_check'
    else:
        return True, 'general_trends'

async def process_training_feedback(message: str, user_id: str) -> str:
    """Process Good Match/Bad Match training feedback"""
    try:
        training = OpportunityTraining()
        message_lower = message.lower()
        
        if 'good match' in message_lower:
            # User is providing positive feedback
            feedback_result = await training.record_feedback(
                user_id=user_id,
                feedback_type='positive',
                message_context=message
            )
            
            return f"""✅ **Training Feedback Recorded**

💎 **Feedback Type:** Good Match
📈 **Impact:** This helps improve trend opportunity detection
🤖 **ML Effect:** Future similar opportunities will be prioritized

**Your Training Stats:**
• Total Feedback: {feedback_result.get('total_feedback', 0)}
• Good Matches: {feedback_result.get('positive_feedback', 0)}
• Bad Matches: {feedback_result.get('negative_feedback', 0)}

Keep the feedback coming to improve accuracy!"""
        
        elif 'bad match' in message_lower:
            # User is providing negative feedback
            feedback_result = await training.record_feedback(
                user_id=user_id,
                feedback_type='negative',
                message_context=message
            )
            
            return f"""❌ **Training Feedback Recorded**

💎 **Feedback Type:** Bad Match
📉 **Impact:** This helps filter out irrelevant opportunities
🤖 **ML Effect:** Future similar opportunities will be deprioritized

**Your Training Stats:**
• Total Feedback: {feedback_result.get('total_feedback', 0)}
• Good Matches: {feedback_result.get('positive_feedback', 0)}
• Bad Matches: {feedback_result.get('negative_feedback', 0)}

Your feedback helps make the system smarter!"""
        
        else:
            return """🤖 **Training Feedback System**

Help improve trend opportunity detection with feedback:

**Available Commands:**
• `Good Match` - Mark current opportunity as relevant
• `Bad Match` - Mark current opportunity as irrelevant
• `trends opportunities` - View current opportunities to evaluate

**How Training Works:**
📈 Good Match feedback increases similar opportunity scores
📉 Bad Match feedback decreases similar opportunity scores
💎 More feedback = Better opportunity detection accuracy"""
    
    except Exception as e:
        logger.error(f"Training feedback processing failed: {e}")
        return f"❌ **Training Error:** {str(e)}\n\nTry `trends status` to check system health."

async def check_for_trend_opportunities(user_id: str) -> Optional[str]:
    """Check for proactive trend opportunities and return notification message"""
    try:
        detector = OpportunityDetector(database_url)
        
        # Get current trending opportunities
        opportunities = await detector.detect_current_opportunities(hours_lookback=24)
        
        if not opportunities:
            return None
        
        # Filter for high-confidence opportunities only
        high_confidence_ops = [
            op for op in opportunities
            if op.get('confidence_score', 0) >= 0.75
        ]
        
        if not high_confidence_ops:
            return None
        
        # Create proactive notification
        top_opportunity = high_confidence_ops[0]
        
        notification_message = f"""📈 **Trending Opportunity Alert**

**{top_opportunity.get('keyword', 'Unknown Trend')}** is gaining momentum!

📊 **Trend Score:** {top_opportunity.get('trend_score', 0):.1f}/10
💎 **Relevance:** {top_opportunity.get('confidence_score', 0):.0%}
📅 **Peak Expected:** {top_opportunity.get('peak_timing', 'Soon')}

**Why This Matters:**
{top_opportunity.get('opportunity_reason', 'High engagement potential detected')}

**Suggested Actions:**
• {top_opportunity.get('suggested_action_1', 'Create content around this trend')}
• {top_opportunity.get('suggested_action_2', 'Monitor for additional opportunities')}

Use `Good Match` or `Bad Match` to train the system!"""
        
        return notification_message
        
    except Exception as e:
        logger.error(f"Trend opportunity check failed: {e}")
        return None

async def process_trends_command(message: str, user_id: str) -> str:
    """Process Google Trends commands"""
    try:
        is_trends_cmd, cmd_type = detect_trends_command(message)
        
        if not is_trends_cmd:
            return ""
        
        if cmd_type == 'training_feedback':
            return await process_training_feedback(message, user_id)
        
        elif cmd_type == 'view_opportunities':
            detector = OpportunityDetector(database_url)
            opportunities = await detector.detect_current_opportunities(hours_lookback=24)
            
            if not opportunities:
                return """📈 **Google Trends Opportunities**

No trending opportunities found at this time.

**Available Commands:**
• `trends scan` - Force scan for new opportunities
• `trends status` - Check system health
• Use `Good Match`/`Bad Match` to train the system"""
            
            response_parts = ["📈 **Current Trending Opportunities**\n"]
            
            for i, opp in enumerate(opportunities, 1):
                response_parts.append(f"""**{i}. {opp.keyword}**
            📊 Trend Score: {opp.trend_score}/10
            💎 Relevance: {opp.opportunity_score:.0%}
            💡 Why: {opp.reasoning}

            """)
            
            response_parts.append("Respond with `Good Match` or `Bad Match` to help train the system!")
            return "\n".join(response_parts)
        
        elif cmd_type == 'scan_trends':
            # Force a new scan
            detector = OpportunityDetector(database_url)
            scan_result = await detector.force_scan_update()
            
            return f"""🔍 **Trends Scan Complete**

✅ Scanned {scan_result.get('trends_analyzed', 0)} trending topics
📈 Found {scan_result.get('opportunities_detected', 0)} new opportunities
⏰ Scan completed at {datetime.now().strftime('%H:%M')}

Use `trends opportunities` to view the latest findings!"""
        
        elif cmd_type == 'status_check':
            health_status = check_module_health()
            
            return f"""📈 **Google Trends System Status**

📡 **Service:** {'Running' if health_status.get('trends_healthy', False) else 'Issues Detected'}
⏰ **Last Scan:** {health_status.get('last_trends_scan', 'Unknown')}
📊 **Opportunities Found:** {health_status.get('total_opportunities', 0)}
🤖 **Training Data:** {health_status.get('training_samples', 0)} feedback samples

**Available Commands:**
• `trends opportunities` - View current opportunities
• `trends scan` - Force new scan
• `Good Match`/`Bad Match` - Provide training feedback"""
        
        else:
            # General trends information
            return """📈 **Google Trends Intelligence System**

🤖 **AI-Powered Opportunity Detection**
💎 **Personalized Content Suggestions**
📊 **Real-Time Trend Analysis**

**Available Commands:**
• `trends opportunities` - View current trending opportunities
• `trends scan` - Force scan for new trends
• `trends status` - Check system health
• `Good Match` - Mark opportunity as relevant (training)
• `Bad Match` - Mark opportunity as irrelevant (training)

**How It Works:**
1. Continuously monitors Google Trends
2. AI analyzes relevance to your interests
3. Presents high-potential opportunities
4. Learns from your feedback to improve accuracy

Ready to discover your next trending opportunity?"""
    
    except Exception as e:
        logger.error(f"Trends command processing failed: {e}")
        return f"❌ **Trends System Error:** {str(e)}\n\nTry `trends status` to check system health."

#-- Section 12: Prayer Notification Functions - 9/27/25
def detect_prayer_notification_command(message: str) -> bool:
    """Detect prayer notification management commands"""
    notification_keywords = [
        "prayer notifications", "prayer alerts", "prayer reminder",
        "notification status", "notification test", "prayer service",
        "disable prayer", "enable prayer", "prayer settings"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in notification_keywords)

async def process_prayer_notification_command(message: str, user_id: str, ip_address: str = None) -> str:
    """Process prayer notification management commands"""
    try:
        from ..integrations.prayer_times.notification_manager import (
            get_prayer_notification_manager,
            test_prayer_notification
        )
        
        message_lower = message.lower()
        notification_manager = get_prayer_notification_manager()
        
        if 'status' in message_lower:
            # Get notification service status
            status = notification_manager.get_notification_status()
            
            return f"""🕌 **Prayer Notification Service Status**

📡 **Service:** {'Running' if status['running'] else 'Stopped'}
⏰ **Check Interval:** {status['check_interval_seconds']} seconds
📅 **Advance Notice:** {status['advance_minutes']} minutes
📊 **Notifications Sent Today:** {status['sent_today']}

**Preferences:**
- Enabled: {'Yes' if status['preferences']['enabled'] else 'No'}
- Advance Time: {status['preferences']['advance_minutes']} minutes
- Personality: {'Enabled' if status['preferences']['personality_enabled'] else 'Disabled'}
- Prayers: {', '.join(status['preferences']['prayers_to_notify']).title()}

Use `prayer notifications test` to test the system."""
        
        elif 'test' in message_lower:
            # Test the notification system
            test_message = await test_prayer_notification()
            
            return f"""🧪 **Prayer Notification Test**

Here's what a notification would look like:

---

{test_message}

---

If the service is running properly, you should receive automatic notifications 15 minutes before each prayer time."""
        
        else:
            # General prayer notification info
            return """🕌 **Prayer Notification System**

**Available Commands:**
- `prayer notifications status` - Check service status
- `prayer notifications test` - Test notification format
- `prayer times` - Get today's prayer schedule
- `next prayer` - See time until next prayer

**Features:**
✅ Automatic 15-minute advance notifications
✅ AI personality integration for natural messages
✅ All 5 daily prayers included
✅ No duplicate notifications

The service runs automatically in the background."""
            
    except Exception as e:
        logger.error(f"Prayer notification command processing failed: {e}")
        return f"❌ **Prayer Notification Error:** {str(e)}\n\nTry `prayer notifications status` to check the system."

def detect_location_command(message: str) -> bool:
    """Detect location-related commands"""
    location_keywords = [
        "my location", "where am i", "current location", "detect location",
        "prayer location", "location for prayers", "change location",
        "location settings", "ip location", "auto location"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in location_keywords)

async def process_location_command(message: str, user_id: str, ip_address: str = None) -> str:
    """Process location detection and management commands"""
    try:
        from ..integrations.prayer_times.location_detector import (
            get_location_detector,
            detect_user_location
        )
        
        message_lower = message.lower()
        detector = get_location_detector()
        
        if any(term in message_lower for term in ['where am i', 'current location', 'my location']):
            # Detect and show current location
            location = await detect_user_location(ip_address)
            
            return f"""📍 **Your Current Location**

🌐 **Detected from IP:** {location.get('source', 'IP Service')}
🏙️ **City:** {location['city']}
📍 **Region:** {location['region']}
🌍 **Country:** {location['country']}
📊 **Coordinates:** {location['latitude']:.4f}, {location['longitude']:.4f}
🕐 **Timezone:** {location['timezone']}

This location will be used automatically for prayer time calculations."""
        
        elif 'prayer location' in message_lower:
            # Get location specifically formatted for prayers
            from ..integrations.prayer_times.location_detector import get_prayer_location
            location_name, lat, lng = await get_prayer_location(user_id, ip_address)
            
            return f"""🕌 **Prayer Times Location**

📍 **Location:** {location_name}
📊 **Coordinates:** {lat:.4f}, {lng:.4f}

Prayer times are automatically calculated for your current location based on your IP address. 

**Available Commands:**
- `prayer times` - Get today's schedule for your location
- `next prayer` - Time until next prayer
- `my location` - See detected location details"""
        
        else:
            # General location information
            return f"""📍 **Location Detection System**

Your prayer times are automatically calculated based on your IP address location.

**Available Commands:**
- `my location` - See your detected location
- `prayer location` - View location used for prayers  
- `location settings` - Check auto-detection settings
- `prayer times` - Get schedule for your current location

**Features:**
✅ Automatic IP-based location detection
✅ 24-hour location caching for performance
✅ Multiple geolocation services for accuracy
✅ Fallback to default location if needed"""
            
    except Exception as e:
        logger.error(f"Location command processing failed: {e}")
        return f"❌ **Location Detection Error:** {str(e)}\n\nTry `my location` to test location detection."

async def post_system_message_to_chat(message: str, message_type: str = "system_notification") -> bool:
    """
    Post a system-generated message to the chat interface
    This is used by background services like prayer notifications
    """
    try:
        from .conversation_manager import get_memory_manager
        
        # Get the default user ID and create a system thread if needed
        DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
        
        # Get memory manager
        memory_manager = get_memory_manager(DEFAULT_USER_ID)
        
        # Create or get system notification thread
        system_thread_id = await get_or_create_system_thread(memory_manager)
        
        # Add system message to conversation history
        system_message_id = await memory_manager.add_message(
            thread_id=system_thread_id,
            role="assistant",  # System messages appear as assistant responses
            content=message,
            metadata={
                "type": message_type,
                "timestamp": datetime.now().isoformat(),
                "source": "prayer_notification_service"
            }
        )
        
        logger.info(f"✅ System message posted to chat: {system_message_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to post system message to chat: {e}")
        return False

async def get_or_create_system_thread(memory_manager) -> str:
    """Get or create a dedicated thread for system notifications"""
    try:
        # Create a new thread titled "Prayer Notifications"
        thread_id = await memory_manager.create_conversation_thread(
            platform='system',
            title='Prayer Notifications'
        )
        
        return thread_id
        
    except Exception as e:
        logger.error(f"Failed to create system thread: {e}")
        raise

#-- Section 13: Module Information Functions - 9/26/25 (Updated 9/28/25)
def get_integration_info():
    """Get information about the chat integration helper module"""
    return {
        "name": "AI Chat Integration Helper",
        "version": "2.3.0",
        "description": "Helper functions for weather, prayer times, scraper, RSS, Bluesky, Google Trends, Voice Synthesis, Image Generation, and file processing",
        "note": "This module provides helper functions only - endpoints are handled by router.py",
        "features": [
            "Weather integration with Tomorrow.io API",
            "Prayer times with AlAdhan API integration and notifications",
            "Marketing scraper for competitive analysis",
            "RSS learning integration for marketing insights",
            "Bluesky social media command processing",
            "Google Trends opportunity detection and training",
            "Voice synthesis with ElevenLabs integration",
            "Image generation with Replicate AI",
            "Google Workspace integration (Analytics, Search Console, Gmail, Calendar, Drive)",
            "Self-evolving Intelligence Engine with pattern recognition",
            "Multi-account Google authentication with OAuth device flow",
            "File upload processing (images, PDFs, CSVs, text)",
            "Real-time datetime context generation",
            "Location detection for prayer times",
            "Prayer notification management"
        ],
        "integrations_provided": [
            "weather_detection_and_processing",
            "prayer_times_detection_and_processing",
            "prayer_notification_management",
            "location_detection_and_processing",
            "marketing_scraper_detection_and_processing",
            "rss_learning_context_generation",
            "bluesky_command_processing",
            "google_trends_integration",
            "voice_synthesis_detection_and_processing",
            "image_generation_detection_and_processing",
            "google_workspace_command_processing",
            "file_upload_and_analysis"
        ]
    }

def check_module_health() -> Dict[str, Any]:
    """Check the health of the AI chat helper module"""
    missing_vars = []
    warnings = []
    
    if not UPLOAD_DIR.exists():
        warnings.append("Upload directory not found")
    
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
    
    # Check marketing scraper configuration
    scraper_configured = bool(os.getenv("DATABASE_URL"))  # Uses same DB as RSS
    
    if not scraper_configured:
        warnings.append("Marketing Scraper integration not configured (DATABASE_URL missing)")
    
    # Check prayer times configuration
    prayer_configured = bool(os.getenv("DATABASE_URL"))  # Uses same DB as others
    
    if not prayer_configured:
        warnings.append("Prayer Times integration not configured (DATABASE_URL missing)")
    
    # Check Google Trends configuration
    trends_configured = bool(os.getenv("DATABASE_URL"))  # Uses same DB as others
    
    if not trends_configured:
        warnings.append("Google Trends integration not configured (DATABASE_URL missing)")
    
    # Check Voice Synthesis configuration - NEW 9/28/25
    voice_configured = bool(os.getenv("ELEVENLABS_API_KEY"))
    
    if not voice_configured:
        warnings.append("Voice Synthesis integration not configured (ELEVENLABS_API_KEY missing)")
    
    # Check Image Generation configuration - NEW 9/28/25
    image_configured = bool(os.getenv("REPLICATE_API_TOKEN"))
    
    if not image_configured:
        warnings.append("Image Generation integration not configured (REPLICATE_API_TOKEN missing)")
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "warnings": warnings,
        "upload_directory": str(UPLOAD_DIR),
        "max_file_size": f"{MAX_FILE_SIZE // (1024 * 1024)}MB",
        "weather_integration_available": bool(os.getenv("TOMORROW_IO_API_KEY")),
        "bluesky_integration_available": bluesky_configured,
        "rss_learning_integration_available": rss_configured,
        "marketing_scraper_integration_available": scraper_configured,
        "prayer_times_integration_available": prayer_configured,
        "google_trends_integration_available": trends_configured,
        "voice_synthesis_integration_available": voice_configured,
        "image_generation_integration_available": image_configured,
        "prayer_notifications_available": prayer_configured,
        "location_detection_available": True,
        "file_processing_available": True,
        "note": "This is a helper module - endpoints are handled by router.py"
    }
#-- Section 13: Pattern Fatigue Detection Functions 9/29/25
def detect_pattern_complaint(message: str) -> tuple[bool, str, str]:
    """Detect if user is complaining about repetitive patterns"""
    message_lower = message.lower()
    
    duplicate_triggers = ["stop mentioning duplicate", "ignore duplicate", "stop pointing out double", "enough with the double", "stop saying twice", "stop being annoying", "quit that", "enough", "stop that"]
    time_joke_triggers = ["stop with the 2am", "enough 2am jokes", "quit asking about 2am", "stop time jokes", "no more 2am"]
    
    for trigger in duplicate_triggers:
        if trigger in message_lower:
            return True, "duplicate_callouts", message
    
    for trigger in time_joke_triggers:
        if trigger in message_lower:
            return True, "2am_jokes", message
    
    return False, "", ""

async def handle_pattern_complaint(user_id: str, pattern_type: str, complaint_text: str) -> str:
    """Handle user complaints about annoying patterns"""
    try:
        if pattern_type == "duplicate_callouts":
            return await handle_duplicate_complaint(user_id, complaint_text)
        elif pattern_type == "2am_jokes":
            return await handle_time_joke_complaint(user_id, complaint_text)
        else:
            return "Got it! I'll try to be less repetitive with that pattern."
    except Exception as e:
        logger.error(f"Failed to handle pattern complaint: {e}")
        return "I'll try to be less repetitive with that pattern."

def detect_pattern_fatigue_command(message: str) -> bool:
    """Detect pattern fatigue management commands"""
    return any(keyword in message.lower() for keyword in ["pattern fatigue", "pattern stats", "fatigue status"])

#-- Section 14: Google Workspace Integration Functions - 9/30/25
#-- Section 14: Google Workspace Integration Functions - 9/30/25
#-- Section 14: Google Workspace Integration Functions - 9/30/25
#-- Section 14: Google Workspace Integration Functions updated for web autho - 10/1/25
#-- Section 14: Google Workspace Integration Functions - OAuth web flow + Keywords/Analytics handlers
def detect_google_command(message: str) -> tuple[bool, str]:
    """Detect Google Workspace commands and determine command type"""
    google_keywords = [
        'google auth', 'google status', 'google sites', 'google accounts',
        'google keywords', 'google analytics', 'google drive', 'google email',
        'google gmail', 'google calendar', 'google suggest', 'google patterns',
        'google predict', 'google intelligence', 'google optimal'
    ]
    
    message_lower = message.lower()
    
    # Check if it's a Google command
    is_google_command = any(keyword in message_lower for keyword in google_keywords)
    
    if not is_google_command:
        return False, ''
    
    # Determine command type
    if 'auth' in message_lower:
        if 'setup' in message_lower or 'start' in message_lower:
            return True, 'auth_setup'
        elif 'status' in message_lower:
            return True, 'auth_status'
        elif 'accounts' in message_lower:
            return True, 'auth_accounts'
        else:
            return True, 'auth_help'
    
    elif 'keywords' in message_lower or 'keyword' in message_lower:
        if 'pending' in message_lower:
            return True, 'keywords_pending'
        elif 'approve' in message_lower:
            return True, 'keywords_approve'
        elif 'ignore' in message_lower:
            return True, 'keywords_ignore'
        else:
            return True, 'keywords_view'
    
    elif 'analytics' in message_lower:
        if 'all' in message_lower:
            return True, 'analytics_all'
        else:
            return True, 'analytics_site'
    
    elif 'optimal' in message_lower and 'timing' in message_lower:
        return True, 'optimal_timing'
    
    elif 'drive' in message_lower:
        if 'create' in message_lower and 'doc' in message_lower:
            return True, 'drive_create_doc'
        elif 'create' in message_lower and 'sheet' in message_lower:
            return True, 'drive_create_sheet'
        elif 'recent' in message_lower:
            return True, 'drive_recent'
        else:
            return True, 'drive_help'
    
    elif 'email' in message_lower or 'gmail' in message_lower:
        if 'summary' in message_lower:
            return True, 'email_summary'
        elif 'draft' in message_lower:
            return True, 'email_draft'
        else:
            return True, 'email_account'
    
    elif 'calendar' in message_lower:
        if 'today' in message_lower:
            return True, 'calendar_today'
        elif 'week' in message_lower:
            return True, 'calendar_week'
        elif 'feeds' in message_lower:
            return True, 'calendar_feeds'
        elif 'windows' in message_lower:
            return True, 'calendar_windows'
        else:
            return True, 'calendar_help'
    
    elif 'suggest' in message_lower or 'intelligence' in message_lower:
        return True, 'intelligence_suggest'
    
    elif 'patterns' in message_lower:
        return True, 'intelligence_patterns'
    
    elif 'predict' in message_lower:
        return True, 'intelligence_predict'
    
    elif 'status' in message_lower:
        return True, 'status_check'
    
    elif 'sites' in message_lower:
        return True, 'sites_list'
    
    else:
        return True, 'general_help'

async def process_google_command(message: str, user_id: str) -> str:
    """Process Google Workspace commands and return personality-driven responses"""
    try:
        import httpx
        
        is_google, command_type = detect_google_command(message)
        
        if not is_google:
            return "I didn't recognize that as a Google Workspace command. Try `google status` to see what's available!"
        
        # Get base URL for API calls
        base_url = "http://localhost:8000"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            
            # ============================================================
            # AUTHENTICATION COMMANDS
            # ============================================================
            
            if command_type == 'auth_setup':
                response = await client.get(f"{base_url}/google/auth/start?user_id={user_id}")
                data = response.json()
                
                if data.get('success'):
                    auth_url = data['authorization_url']
                    
                    return f"""🔐 **Google Workspace Authentication**

Click this link to authorize access:
{auth_url}

After you approve, you'll be redirected back to the chat.

This will give me access to:
- Google Analytics (read-only)
- Search Console (read-only)  
- Google Drive (create/edit documents)
- Gmail (read + compose)
- Your email and profile info

All tokens are encrypted and stored securely."""
                else:
                    return f"❌ **Authentication Failed**\n\n{data.get('message', 'Unknown error')}"
            
            elif command_type == 'auth_status':
                # Check OAuth status
                response = await client.get(f"{base_url}/google/auth/accounts?user_id={user_id}")
                data = response.json()
                
                if data.get('count', 0) > 0:
                    accounts = data['accounts']
                    account_list = "\n".join([f"   • {acc['email']} - {'✅ Active' if not acc.get('is_expired') else '⚠️ Expired'}" for acc in accounts])
                    return f"""Google Auth Status

Connected Accounts ({data['count']}):
{account_list}

Use `google auth setup` to add more accounts!"""
                else:
                    return "No Google accounts connected yet. Use `google auth setup` to connect!"
            
            elif command_type == 'auth_accounts':
                response = await client.get(f"{base_url}/google/auth/accounts")
                data = response.json()
                
                if data.get('count', 0) > 0:
                    accounts = data['accounts']
                    account_details = []
                    for acc in accounts:
                        status = "✅ Active" if not acc.get('is_expired') else '⚠️ Expired'
                        account_details.append(f"""Account: {acc['email']}
Status: {status}
Scopes: {len(acc.get('scopes', []))} permissions
Connected: {acc.get('authenticated_at', 'Unknown')}""")
                    
                    return f"""Connected Google Accounts

{chr(10).join(account_details)}

Total: {data['count']} account(s)"""
                else:
                    return "No Google accounts connected yet. Use `google auth setup` to connect!"
            
            # ============================================================
            # KEYWORDS/SEARCH CONSOLE COMMANDS
            # ============================================================
            
            elif command_type == 'keywords_view':
                # Extract site name from message
                site_name = None
                for site in ['bcdodge', 'rose_angel', 'meals_feelz', 'tv_signals', 'damn_it_carl']:
                    if site in message.lower() or site.replace('_', '') in message.lower():
                        site_name = site
                        break
                
                if not site_name:
                    return """Keyword Opportunities

Please specify which site you want to check:
- `google keywords bcdodge`
- `google keywords rose_angel`  
- `google keywords meals_feelz`
- `google keywords tv_signals`
- `google keywords damn_it_carl`"""
                
                try:
                    response = await client.get(f"{base_url}/google/keywords/opportunities?site_name={site_name}")
                    data = response.json()
                    
                    opportunities = data.get('opportunities', [])
                    
                    if not opportunities:
                        return f"""Keyword Opportunities: {site_name}

No new keyword opportunities found for this site.

This means:
- All high-value keywords (100+ impressions, positions 11-30) are already tracked
- Keep creating content and check back later!

Use `google keywords pending` to see opportunities across all sites."""
                    
                    result = f"""Keyword Opportunities: {site_name}

Found {len(opportunities)} new opportunities:

"""
                    for i, opp in enumerate(opportunities[:10], 1):  # Show top 10
                        result += f"""{i}. **{opp['keyword']}**
   📊 Impressions: {opp['impressions']} | Clicks: {opp['clicks']}
   📍 Position: {opp['position']:.1f} | Type: {opp['opportunity_type']}
   
"""
                    
                    result += "\nThese keywords have high impressions but aren't being tracked yet. Ready to add them?"
                    return result
                    
                except Exception as e:
                    logger.error(f"Keywords command failed: {e}")
                    return f"Error fetching keyword opportunities: {str(e)}"
            
            elif command_type == 'keywords_pending':
                return """Pending Keywords Across All Sites

This feature shows keyword opportunities across all your sites.

For now, check each site individually:
- `google keywords bcdodge`
- `google keywords rose_angel`
- `google keywords meals_feelz`
- `google keywords tv_signals`
- `google keywords damn_it_carl`"""
            
            # ============================================================
            # ANALYTICS COMMANDS
            # ============================================================
            
            elif command_type == 'analytics_site':
                # Extract site name from message
                site_name = None
                for site in ['bcdodge', 'rose_angel', 'meals_feelz', 'tv_signals', 'damn_it_carl']:
                    if site in message.lower() or site.replace('_', '') in message.lower():
                        site_name = site
                        break
                
                if not site_name:
                    return """Analytics Summary

Please specify which site you want to check:
- `google analytics bcdodge`
- `google analytics rose_angel`
- `google analytics meals_feelz`
- `google analytics tv_signals`
- `google analytics damn_it_carl`

Or use `google analytics all` for an overview."""
                
                try:
                    response = await client.get(f"{base_url}/google/analytics/summary?site_name={site_name}")
                    data = response.json()
                    
                    stats = data.get('summary', {})
                    
                    return f"""Analytics Summary: {site_name}
Last 30 Days

👥 **Visitors:** {stats.get('sessions', 0):,}
📄 **Page Views:** {stats.get('pageviews', 0):,}
⏱️ **Avg. Session:** {stats.get('avg_session_duration', 0):.1f}s
📊 **Bounce Rate:** {stats.get('bounce_rate', 0):.1f}%

**Top Pages:**
{chr(10).join([f"  {i+1}. {page}" for i, page in enumerate(stats.get('top_pages', [])[:5])])}

**Traffic Sources:**
{chr(10).join([f"  • {source}: {count}" for source, count in stats.get('traffic_sources', {}).items()])}

Use `google analytics all` to compare across all sites!"""
                    
                except Exception as e:
                    logger.error(f"Analytics command failed: {e}")
                    return f"Error fetching analytics: {str(e)}"
            
            elif command_type == 'analytics_all':
                return """Analytics Overview - All Sites

Feature coming soon! For now, check each site individually:
- `google analytics bcdodge`
- `google analytics rose_angel`
- `google analytics meals_feelz`
- `google analytics tv_signals`
- `google analytics damn_it_carl`"""
            
            # ============================================================
            # EMAIL/GMAIL COMMANDS
            # ============================================================
            
            elif command_type == 'email_summary':
                from ..integrations.google_workspace.gmail_client import get_email_summary
                
                try:
                    summary = await get_email_summary(user_id, days=7)
                    
                    if not summary or summary.get('total_emails', 0) == 0:
                        return """Email Summary

No emails found in the last 7 days, or Gmail is not yet connected.

Use `google auth setup` to connect your Gmail account."""
                    
                    # Build the base summary
                    response_parts = [
                        f"""Email Summary (Last 7 Days)

Total Emails: {summary.get('total_emails', 0)}
Important: {summary.get('important', 0)}
Needs Response: {summary.get('needs_response', 0)}
Inbox: {summary.get('inbox', 0)}
Sent: {summary.get('sent', 0)}
Negative Sentiment: {summary.get('negative_sentiment', 0)}"""
                    ]
                    
                    # Add emails requiring response if any exist
                    emails_needing_response = summary.get('emails_requiring_response', [])
                    if emails_needing_response:
                        response_parts.append("\n\n📧 **Emails Requiring Response:**\n")
                        
                        for i, email in enumerate(emails_needing_response[:5], 1):  # Show max 5
                            priority_emoji = "🔥" if email.get('priority') == 'high' else "📨"
                            response_parts.append(f"""{i}. {priority_emoji} **From:** {email['from']}
   **Subject:** {email['subject']}
   **Date:** {email['date'].strftime('%b %d, %I:%M %p') if hasattr(email['date'], 'strftime') else email['date']}
""")
                    
                    response_parts.append("\nUse `google email draft` to create responses!")
                    
                    return "".join(response_parts)
                    
                except Exception as e:
                    logger.error(f"Email summary failed: {e}")
                    return f"""Email Summary Error

Could not retrieve email summary: {str(e)}

Make sure your Gmail account is connected with `google auth setup`"""
            
            elif command_type == 'email_draft':
                return """Create Email Draft

To create an email draft, I need more information:

Example format:
"Create an email draft to john@example.com about meeting tomorrow"

Or provide:
- To: Recipient email
- Subject: Email subject
- Body: Your message

Once you provide these details, I'll create a draft in your Gmail account that you can review and send."""
            
            elif command_type == 'email_account':
                return """Gmail Account Management

Your Gmail integration provides:
- Email analysis and prioritization
- Smart filtering (urgent, business, needs response)
- Sentiment analysis
- Draft creation with AI assistance
- Privacy-first (metadata only, 30-day retention)

Commands:
- `google email summary` - See last 7 days
- `google email draft` - Create a draft

Connected Accounts: Check with `google auth accounts`"""
            
            # ============================================================
            # STATUS & HELP COMMANDS
            # ============================================================
            
            elif command_type == 'status_check':
                response = await client.get(f"{base_url}/google/status")
                data = response.json()
                
                health = "Healthy" if data.get('overall_health') == 'healthy' else "Issues Detected"
                oauth_count = len(data.get('oauth_authentication', {}).get('accounts', []))
                analytics_count = len(data.get('analytics_sites', []))
                
                return f"""Google Workspace Status

System Health: {health}
OAuth Accounts: {oauth_count} connected
Analytics Sites: {analytics_count} configured
Features Active:
   - Search Console keyword tracking
   - Analytics insights
   - Gmail intelligence (multi-account)
   - Calendar integration (11 feeds)
   - Self-evolving Intelligence Engine
   - Drive document creation

Use `google auth accounts` to see connected accounts."""
            
            elif command_type == 'sites_list':
                return """Configured Sites

Active Sites:
   1. bcdodge - Primary site
   2. rose_angel - Meditation & wellness
   3. meals_feelz - Food & recipes
   4. tv_signals - TV & entertainment
   5. damn_it_carl - Personal blog

Each site has Analytics and Search Console tracking enabled. Use `google keywords [site]` to see opportunities!"""
            
            else:
                return """Google Workspace Commands

Authentication:
   - `google auth setup` - Connect your Google accounts
   - `google auth status` - Check connection status
   - `google auth accounts` - List connected accounts

Keywords (Search Console):
   - `google keywords [site]` - View opportunities for a site
   - `google keywords pending` - See all pending across sites

Analytics:
   - `google analytics [site]` - Traffic summary
   - `google analytics all` - All sites overview

Email:
   - `google email summary` - Last 7 days of email
   - `google email draft` - Create email draft
   - `google email account` - Gmail integration info

Status:
   - `google status` - Integration health check
   - `google sites` - List configured sites

More features coming: Calendar, Drive, and Intelligence commands!"""
    
    except Exception as e:
        logger.error(f"Google command processing failed: {e}")
        return f"Google Workspace Error: {str(e)}\n\nUse `google auth setup` to connect!"

def get_integration_info() -> Dict[str, Any]:
    """Get Google Workspace integration information"""
    return {
        "name": "Google Workspace Integration",
        "version": "2.0.0",
        "status": "active",
        "features": [
            "OAuth web flow authentication",
            "Search Console keyword opportunities",
            "Google Analytics insights",
            "Gmail multi-account intelligence",
            "Drive document creation"
        ]
    }

def check_module_health() -> Dict[str, Any]:
    """Check Google Workspace module health"""
    return {
        "healthy": True,
        "module": "google_workspace",
        "status": "operational"
    }
