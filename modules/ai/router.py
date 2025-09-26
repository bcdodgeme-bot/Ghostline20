# modules/ai/chat.py
# AI Chat Integration Helper Functions for Syntax Prime V2
# Provides integration functions for router.py - NO ENDPOINTS HERE
# Clean helper module with all integration logic for weather, prayer times, scraper, etc.
# Date: 9/26/25 - Converted to helper module only

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

# File processing imports
from PIL import Image, ImageOps
import pdfplumber
import pandas as pd
import magic
import cv2
import numpy as np
from io import BytesIO
import base64

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

#-- Section 4: Bluesky Integration Functions - 9/26/25
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
            account_statuses = get_bluesky_multi_client().get_all_account_status()
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
            
            response_parts = ["🔍 **Recent Scraping History**\n"]
            
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
                    response_parts.append(f"   🎯 Value Prop: {insights['value_proposition'][:100]}...")
                if insights.get('content_strategy'):
                    response_parts.append(f"   📝 Strategy: {insights['content_strategy'][:100]}...")
                response_parts.append("")
            
            response_parts.append("🔍 Use `scrape https://newsite.com` to add more competitive intelligence!")
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
                            "**🎯 Value Proposition:**",
                            f"• {insights['value_proposition'][:200]}...",
                            ""
                        ])
                
                if analysis.get('marketing_angles'):
                    marketing = analysis.get('marketing_angles', {})
                    if marketing.get('content_strategy'):
                        response_parts.extend([
                            "**📝 Content Strategy:**",
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

#-- Section 7: Prayer Times Functions - 9/26/25
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

async def process_prayer_command(message: str, user_id: str) -> str:
    """Process prayer-related commands using the cached database system"""
    try:
        from ..integrations.prayer_times.database_manager import get_next_prayer, get_todays_prayers
        
        question_type = detect_prayer_question_type(message)
        
        if question_type == "next_prayer":
            # "How long till Dhuhr?" type questions
            next_prayer_info = await get_next_prayer()
            
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

Prayer times are calculated for Merrifield, Virginia using ISNA method."""
        
        elif question_type == "daily_schedule":
            # "What are prayer times today?" type questions
            daily_prayers = await get_todays_prayers()
            
            if not daily_prayers:
                return """🕌 **Prayer Schedule Unavailable**
                
Unable to retrieve today's prayer schedule. Please try again in a few moments."""
            
            prayer_times = daily_prayers['prayer_times']
            islamic_date = daily_prayers['islamic_date']
            formatted_date = daily_prayers.get('formatted_date', daily_prayers['date'])
            
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
                "🕐 **Daily Prayer Schedule:**",
                f"   **Fajr:** {prayer_times['fajr']}",
                f"   **Dhuhr:** {prayer_times['dhuhr']}",
                f"   **Asr:** {prayer_times['asr']}",
                f"   **Maghrib:** {prayer_times['maghrib']}",
                f"   **Isha:** {prayer_times['isha']}",
                "",
                "📍 Calculated for Merrifield, Virginia using ISNA method"
            ])
            
            return "\n".join(response_parts)
        
        elif question_type == "islamic_date":
            # Islamic calendar questions
            daily_prayers = await get_todays_prayers()
            
            if not daily_prayers or daily_prayers['islamic_date']['date'] == 'N/A':
                return """📅 **Islamic Calendar Information**
                
Islamic date information is currently unavailable. Please try again later."""
            
            islamic_date = daily_prayers['islamic_date']
            gregorian_date = daily_prayers.get('formatted_date', daily_prayers['date'])
            
            return f"""📅 **Islamic Calendar Information**
