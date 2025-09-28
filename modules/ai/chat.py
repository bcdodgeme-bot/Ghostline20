# modules/ai/chat.py
# AI Chat Integration Helper Functions for Syntax Prime V2
# Provides integration functions for router.py - NO ENDPOINTS HERE
# Clean helper module with all integration logic for weather, prayer times, scraper, etc.
# Date: 9/26/25 - Converted to helper module only
# Date: 9/27/25 - Added Google Trends integration and Prayer Notifications

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
                return """📁 **Marketing Scraper History**

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
                response_parts.append(f"   📝 Words: {word_count}")
                response_parts.append("")
            
            response_parts.append("💡 Use `scrape insights` to get AI analysis of all scraped content.")
            return "\n".join(response_parts)
        
        elif 'scrape insights' in message_lower:
            # Get competitive insights from all scraped content
            db = ScrapedContentDatabase()
            
            # Search for recent content using empty topic to get all
            recent_content = await db.search_scraped_insights(user_id=user_id, topic="", limit=20)
            
            if not recent_content:
                return """📁 **Marketing Scraper Insights**

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
                    response_parts.append(f"   📝 Strategy: {insights['content_strategy'][:100]}...")
                response_parts.append("")
            
            response_parts.append("📈 Use `scrape https://newsite.com` to add more competitive intelligence!")
            return "\n".join(response_parts)
        
        else:
            # Extract URL and scrape content
            url = extract_url_from_message(message)
            
            if not url:
                return """📁 **Marketing Scraper Commands**

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
                    f"📝 Content extracted: {word_count:,} words",
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
                            "**📝 Content Strategy:**",
                            f"• {marketing['content_strategy'][:200]}...",
                            ""
                        ])
                
                if analysis.get('cta_analysis'):
                    cta = analysis.get('cta_analysis', {})
                    if cta.get('cta_placement_strategy'):
                        response_parts.extend([
                            "**📥 CTA Strategy:**",
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

#-- Section 10: Google Trends Integration Functions - 9/27/25
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
                response_parts.append(f"""**{i}. {opp.get('keyword', 'Unknown')}**
📊 Trend Score: {opp.get('trend_score', 0):.1f}/10
💎 Relevance: {opp.get('confidence_score', 0):.0%}
💡 Why: {opp.get('opportunity_reason', 'High potential')}

""")
            
            response_parts.append("Respond with `Good Match` or `Bad Match` to help train the system!")
            return "\n".join(response_parts)
        
        elif cmd_type == 'scan_trends':
            # Force a new scan
            detector = OpportunityDetector(database_url)
            scan_result = await detector.force_scan_update()
            
            return f"""📝 **Trends Scan Complete**

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

#-- Section 11: Prayer Notification Functions - 9/27/25
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
🌏 **Country:** {location['country']}
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

#-- Section 12: Module Information Functions - 9/26/25 (Updated 9/27/25)
def get_integration_info():
    """Get information about the chat integration helper module"""
    return {
        "name": "AI Chat Integration Helper",
        "version": "2.1.0",
        "description": "Helper functions for weather, prayer times, scraper, RSS, Bluesky, Google Trends, and file processing",
        "note": "This module provides helper functions only - endpoints are handled by router.py",
        "features": [
            "Weather integration with Tomorrow.io API",
            "Prayer times with AlAdhan API integration and notifications",
            "Marketing scraper for competitive analysis",
            "RSS learning integration for marketing insights",
            "Bluesky social media command processing",
            "Google Trends opportunity detection and training",
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
        "prayer_notifications_available": prayer_configured,
        "location_detection_available": True,
        "file_processing_available": True,
        "note": "This is a helper module - endpoints are handled by router.py"
    }
