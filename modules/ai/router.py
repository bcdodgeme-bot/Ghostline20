# modules/ai/router.py
"""
AI Brain Main Router for Syntax Prime V2 - SECTIONED AND UPDATED
Ties together all AI components into FastAPI endpoints
Date: 9/23/25, Updated: 9/24/25 - Added Weather Integration, Updated: 9/24/25 - Added Bluesky Integration
Updated: 9/25/25 - FIXED Marketing Scraper Integration Order
"""

#-- Section 1: Core Imports and Dependencies - 9/23/25
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import time
import logging
import os
import httpx  # Added for weather API calls

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

# Import our AI brain components
from .openrouter_client import get_openrouter_client, cleanup_openrouter_client
from .inception_client import get_inception_client, cleanup_inception_client
from .conversation_manager import get_memory_manager, cleanup_memory_managers
from .knowledge_query import get_knowledge_engine
from .personality_engine import get_personality_engine
from .feedback_processor import get_feedback_processor

logger = logging.getLogger(__name__)

#-- NEW Section 1a: RSS Learning Integration Import - added 9/25/25
try:
    from ..integrations.rss_learning.marketing_insights import MarketingInsightsExtractor
    RSS_LEARNING_AVAILABLE = True
except ImportError:
    RSS_LEARNING_AVAILABLE = False
    logger.warning("RSS Learning integration not available")

#-- NEW Section 1b: Marketing Scraper Integration Import - added 9/25/25
#-- NEW Section 1b: Marketing Scraper Integration Import - added 9/25/25
# TEMPORARY DEBUG - Remove after fixing
print("🔍 DEBUG: Testing marketing scraper imports...")
import os
import sys
print(f"🔍 DEBUG: Current working directory: {os.getcwd()}")

# Test each import individually
try:
    print("🔍 DEBUG: Trying scraper_client import...")
    from ..integrations.marketing_scraper.scraper_client import MarketingScraperClient
    print("✅ MarketingScraperClient imported successfully")
    scraper_client_ok = True
except Exception as e:
    print(f"❌ MarketingScraperClient import failed: {e}")
    import traceback
    traceback.print_exc()
    scraper_client_ok = False

try:
    print("🔍 DEBUG: Trying content_analyzer import...")
    from ..integrations.marketing_scraper.content_analyzer import ContentAnalyzer
    print("✅ ContentAnalyzer imported successfully")
    content_analyzer_ok = True
except Exception as e:
    print(f"❌ ContentAnalyzer import failed: {e}")
    content_analyzer_ok = False

try:
    print("🔍 DEBUG: Trying database_manager import...")
    from ..integrations.marketing_scraper.database_manager import ScrapedContentDatabase
    print("✅ ScrapedContentDatabase imported successfully")
    database_manager_ok = True
except Exception as e:
    print(f"❌ ScrapedContentDatabase import failed: {e}")
    database_manager_ok = False

MARKETING_SCRAPER_AVAILABLE = scraper_client_ok and content_analyzer_ok and database_manager_ok
print(f"🔍 DEBUG: MARKETING_SCRAPER_AVAILABLE = {MARKETING_SCRAPER_AVAILABLE}")
# END TEMPORARY DEBUG

#-- Section 2: Pydantic Request/Response Models - 9/23/25
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    personality_id: str = Field(default='syntaxprime', description="Personality to use")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    platform: str = Field(default='web', description="Platform (web/ios)")
    include_knowledge: bool = Field(default=True, description="Include knowledge base search")
    max_tokens: int = Field(default=4000, description="Maximum response tokens")
    temperature: float = Field(default=0.7, description="Response creativity")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI response")
    thread_id: str = Field(..., description="Conversation thread ID")
    message_id: str = Field(..., description="Response message ID")
    personality_id: str = Field(..., description="Personality used")
    model_used: str = Field(..., description="AI model used")
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    knowledge_sources: List[Dict] = Field(default_factory=list, description="Knowledge sources used")
    conversation_context: Dict = Field(..., description="Context metadata")

class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="Message ID to rate")
    feedback_type: str = Field(..., description="good, bad, or personality")
    feedback_text: Optional[str] = Field(None, description="Optional text feedback")

class FeedbackResponse(BaseModel):
    feedback_id: str
    feedback_type: str
    emoji: str
    learning_result: Dict
    message: str

#-- Section 3: Router Setup and Configuration - 9/23/25
router = APIRouter(prefix="/ai", tags=["ai"])

#-- Section 4: AI Brain Orchestrator Class - Updated 9/25/25 with FIXED Command Order
class AIBrainOrchestrator:
    """
    Main orchestrator that coordinates all AI brain components
    FIXED: Proper command detection order
    """
    
    def __init__(self):
        # FIXED: Use proper UUID format for default user
        self.default_user_id = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"  # Carl's user ID
        logger.info(f"AI Brain initialized with default user ID: {self.default_user_id}")
        self.fallback_attempts = 2

#-- Section 5: Weather Integration Methods - Added 9/24/25
    def _detect_weather_request(self, message: str) -> bool:
        """Detect if user is asking about weather"""
        print(f"🌦️ WEATHER DEBUG: Checking message '{message}'")
        weather_keywords = [
            "weather", "temperature", "forecast", "rain", "snow", "sunny",
            "cloudy", "storm", "wind", "humidity", "barometric pressure",
            "headache weather", "pressure change", "uv index"
        ]
        message_lower = message.lower()
        result = any(keyword in message_lower for keyword in weather_keywords)
        print(f"🌦️ WEATHER DEBUG: Detection result = {result}")
        return result

    async def _get_weather_for_user(self, user_id: str, location: str = None) -> Dict:
        """Get current weather data for the user"""
        print(f"🌦️ WEATHER DEBUG: Getting weather for user {user_id}")
        try:
            # Use dedicated environment variable for internal API base URL
            base_url = os.getenv("INTERNAL_API_BASE_URL", "http://localhost:8000")
            params = {"user_id": user_id}
            if location:
                params["location"] = location
                
            async with httpx.AsyncClient() as client:
                print(f"🌦️ WEATHER DEBUG: Calling {base_url}/integrations/weather/current")
                response = await client.get(
                    f"{base_url}/integrations/weather/current",
                    params=params,
                    timeout=30
                )
                
                print(f"🌦️ WEATHER DEBUG: Weather API response status: {response.status_code}")
                
                if response.status_code == 200:
                    weather_data = response.json()
                    print(f"🌦️ WEATHER DEBUG: Weather data received successfully")
                    return weather_data
                else:
                    print(f"🌦️ WEATHER DEBUG: Weather API returned {response.status_code}")
                    return {"error": f"Weather API returned {response.status_code}"}
                    
        except Exception as e:
            print(f"🌦️ WEATHER DEBUG: Weather fetch error: {e}")
            logger.error(f"Weather fetch error: {e}")
            return {"error": f"Failed to get weather: {str(e)}"}

    def _build_weather_context(self, weather_info: Dict) -> str:
        """Build weather context for AI"""
        print(f"🌦️ WEATHER DEBUG: Building weather context")
        weather_context = f"""
CURRENT WEATHER DATA:
Current conditions: {weather_info.get('current_conditions', 'N/A')}
Temperature: {weather_info.get('temperature_f', 'N/A')}°F
Barometric Pressure: {weather_info.get('pressure', 'N/A')} mbar
Pressure Change (3h): {weather_info.get('pressure_change_3h', 'N/A')} mbar
UV Index: {weather_info.get('uv_index', 'N/A')}
Headache Risk: {weather_info.get('headache_risk', 'N/A')}
UV Risk: {weather_info.get('uv_risk', 'N/A')}
Health Alerts: {', '.join(weather_info.get('health_alerts', ['None']))}

Please respond naturally about the weather using this current data. Focus on health implications if relevant (headaches from pressure changes, UV protection needs, etc.).
"""
        return weather_context

#-- Section 5a: Bluesky Command Detection - Added 9/24/25
    def _detect_bluesky_command(self, message: str) -> bool:
        """Detect if user is issuing a Bluesky command"""
        bluesky_keywords = [
            "bluesky", "blue sky", "social media", "engagement", "opportunities",
            "post to bluesky", "scan bluesky", "bluesky scan", "bluesky opportunities",
            "bluesky high priority", "bluesky approve", "bluesky health",
            "bluesky accounts", "bluesky status", "social assistant"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in bluesky_keywords)

    async def _process_bluesky_command(self, message: str, user_id: str) -> str:
        """Process Bluesky command and return response"""
        try:
            # Import Bluesky components (lazy import to avoid circular dependencies)
            from ..integrations.bluesky.multi_account_client import get_bluesky_multi_client
            from ..integrations.bluesky.approval_system import get_approval_system
            from ..integrations.bluesky.notification_manager import get_notification_manager
            
            multi_client = get_bluesky_multi_client()
            approval_system = get_approval_system()
            notification_manager = get_notification_manager()
            
            # Track user activity
            await notification_manager.track_user_activity(user_id, 'chat_bluesky_command')
            
            message_lower = message.lower()
            
            if 'bluesky scan' in message_lower or 'scan bluesky' in message_lower:
                # Get account status and initiate scan
                accounts_status = multi_client.get_all_accounts_status()
                configured_count = len([a for a in accounts_status.values() if a.get('password')])
                authenticated_count = len([a for a in accounts_status.values() if a.get('authenticated')])
                
                return f"""🔵 **Bluesky Scan Initiated**

📱 **Status:** {authenticated_count}/{configured_count} accounts ready
⏳ **Scanning:** All authenticated accounts for engagement opportunities
🧠 **AI Analysis:** Keyword matching + conversation detection active

I'm analyzing your timelines now. Check back in a few minutes with `bluesky opportunities`!"""

            elif 'bluesky opportunities' in message_lower:
                # Get pending opportunities
                opportunities = await approval_system.get_pending_approvals(limit=5)
                
                if not opportunities:
                    return "🔭 **No pending opportunities** found. Try `bluesky scan` to check for new content!"
                
                response_lines = [f"🎯 **{len(opportunities)} Engagement Opportunities**\n"]
                
                for i, opp in enumerate(opportunities, 1):
                    account_name = opp['account_id'].replace('_', ' ').title()
                    score = int(opp.get('keyword_score', 0) * 100)
                    
                    response_lines.append(f"**{i}. {account_name}** ({score}% keyword match)")
                    response_lines.append(f"   📝 **Draft:** {opp['draft_text'][:100]}...")
                    response_lines.append("")
                
                response_lines.append("Use the Bluesky dashboard to approve opportunities!")
                return "\n".join(response_lines)
                
            elif 'bluesky accounts' in message_lower or 'bluesky status' in message_lower:
                # Show account status
                accounts_status = multi_client.get_all_accounts_status()
                
                response_lines = ["🔵 **Bluesky Accounts Status**\n"]
                
                for account_id, info in accounts_status.items():
                    account_name = account_id.replace('_', ' ').title()
                    status_emoji = "✅" if info.get('authenticated') else "❌"
                    keyword_count = info.get('keyword_count', 0)
                    
                    response_lines.append(f"{status_emoji} **{account_name}** ({keyword_count} keywords)")
                
                return "\n".join(response_lines)
                
            elif 'bluesky health' in message_lower:
                # Test system health
                try:
                    auth_results = await multi_client.authenticate_all_accounts()
                    working_count = sum(auth_results.values())
                    total_count = len(auth_results)
                    
                    return f"""🔵 **Bluesky System Health**

📱 **Accounts:** {working_count}/{total_count} connected
🤖 **AI Assistant:** All personalities loaded
⚙️ **Status:** {'Healthy' if working_count > 0 else 'Needs Attention'}"""
                    
                except Exception as e:
                    return f"❌ **Health Check Failed:** {str(e)}"
            
            else:
                # General Bluesky info
                return """🔵 **Bluesky Social Media Assistant**

Your 5-account AI management system with keyword intelligence.

**Commands:**
• `bluesky scan` - Scan all accounts for opportunities
• `bluesky opportunities` - View engagement suggestions  
• `bluesky accounts` - Check account status
• `bluesky health` - System health check

Ready to manage your social media intelligently?"""
                
        except Exception as e:
            logger.error(f"Bluesky command processing failed: {e}")
            return f"❌ **Bluesky Error:** {str(e)}"

#-- NEW Section 5b: Marketing Scraper Command Detection - Added 9/25/25
    def _detect_scraper_command(self, message: str) -> bool:
        """Detect marketing scraper commands"""
        print(f"🔍 SCRAPER DEBUG: Checking message '{message}'")
        scraper_keywords = [
            "scrape", "scraper", "analyze website", "competitor analysis", "scrape url",
            "scrape site", "website analysis", "marketing analysis", "content analysis",
            "scrape history", "scrape insights", "scrape data"
        ]
        message_lower = message.lower()
        result = any(keyword in message_lower for keyword in scraper_keywords)
        print(f"🔍 SCRAPER DEBUG: Detection result = {result}")
        return result

    def _extract_url_from_message(self, message: str) -> str:
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

    async def _process_scraper_command(self, message: str, user_id: str) -> str:
        """Process marketing scraper commands"""
        print(f"🔍 SCRAPER DEBUG: Processing command: {message}")
        
        if not MARKETING_SCRAPER_AVAILABLE:
            return "❌ **Marketing Scraper Not Available** - Missing dependencies or configuration"
            
        try:
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
                url = self._extract_url_from_message(message)
                
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
                
                print(f"🔍 SCRAPER DEBUG: Extracted URL: {url}")
                
                # Perform the scrape
                scraper = MarketingScraperClient()
                analyzer = ContentAnalyzer()
                db = ScrapedContentDatabase()
                
                try:
                    # Scrape the website
                    print(f"🔍 SCRAPER DEBUG: Starting scrape for {url}")
                    scraped_data = await scraper.scrape_website(url)
                    print(f"🔍 SCRAPER DEBUG: Scrape completed with status: {scraped_data.get('scrape_status')}")
                    
                    if scraped_data.get('scrape_status') != 'completed':
                        return f"""❌ **Scraping Failed**
                        
Unable to analyze {url}
Error: {scraped_data.get('error_message', 'Unknown error')}

Please verify the URL is accessible and try again."""
                    
                    # Analyze the content
                    print(f"🔍 SCRAPER DEBUG: Starting AI analysis")
                    analysis = await analyzer.analyze_scraped_content(scraped_data)
                    print(f"🔍 SCRAPER DEBUG: Analysis completed with status: {analysis.get('analysis_status')}")
                    
                    # Store in database
                    print(f"🔍 SCRAPER DEBUG: Storing in database")
                    content_id = await db.store_scraped_content(
                        user_id=user_id,
                        scraped_data=scraped_data,
                        analysis_results=analysis
                    )
                    print(f"🔍 SCRAPER DEBUG: Stored with ID: {content_id}")
                    
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
                    print(f"🔍 SCRAPER DEBUG: Processing failed: {e}")
                    return f"""❌ **Analysis Failed**
                    
Error analyzing {url}: {str(e)}

Please try again or contact support if the issue persists."""
        
        except Exception as e:
            logger.error(f"Scraper command processing failed: {e}")
            print(f"🔍 SCRAPER DEBUG: Command processing failed: {e}")
            return f"❌ **Scraper Command Error:** {str(e)}\n\nTry `scrape https://example.com` to analyze a website."

#-- Section 5c: RSS Learning Integration Methods - Added 9/25/25
    def _detect_marketing_writing_request(self, message: str) -> tuple[bool, str]:
        """Detect marketing writing requests and determine content type"""
        message_lower = message.lower()
        
        # Marketing writing indicators
        marketing_indicators = [
            'write', 'draft', 'create', 'help me', 'content', 'campaign',
            'marketing', 'blog', 'email', 'social', 'copy'
        ]
        
        # Content type detection
        if any(term in message_lower for term in ['email', 'newsletter', 'email campaign', 'email marketing']):
            return any(indicator in message_lower for indicator in marketing_indicators), 'email'
        elif any(term in message_lower for term in ['blog post', 'blog', 'article', 'write blog']):
            return any(indicator in message_lower for indicator in marketing_indicators), 'blog'
        elif any(term in message_lower for term in ['social media', 'social post', 'tweet', 'linkedin', 'instagram']):
            return any(indicator in message_lower for indicator in marketing_indicators), 'social'
        elif any(term in message_lower for term in ['marketing trends', 'content ideas', 'marketing insights']):
            return True, 'general'
        elif any(indicator in message_lower for indicator in marketing_indicators):
            return True, 'blog'  # Default for general writing requests
        
        return False, ''

    async def _get_rss_marketing_context(self, message: str, content_type: str = None) -> str:
        """Get marketing context from RSS learning system"""
        if not RSS_LEARNING_AVAILABLE:
            return ""
            
        try:
            insights_extractor = MarketingInsightsExtractor()
            
            # Detect content type if not provided
            is_writing_request, detected_type = self._detect_marketing_writing_request(message)
            final_content_type = content_type or detected_type or 'blog'
            
            if not is_writing_request and 'marketing' not in message.lower():
                return ""
            
            # Get writing inspiration and trends
            inspiration_task = insights_extractor.get_writing_inspiration(
                content_type=final_content_type,
                topic=None,
                target_audience="digital marketers"
            )
            
            trends_task = insights_extractor.get_latest_trends(limit=3)
            
            # Execute both requests concurrently
            inspiration, trends = await asyncio.gather(inspiration_task, trends_task, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(inspiration, Exception):
                logger.warning(f"RSS inspiration failed: {inspiration}")
                inspiration = {}
            if isinstance(trends, Exception):
                logger.warning(f"RSS trends failed: {trends}")
                trends = {}
            
            # Build context
            context_parts = [
                "CURRENT MARKETING INTELLIGENCE FROM RSS LEARNING SYSTEM:",
                ""
            ]
            
            # Add trends
            if trends.get('trends_summary'):
                context_parts.extend([
                    "CURRENT MARKETING TRENDS:",
                    trends['trends_summary'][:300] + "...",
                    ""
                ])
            
            # Add content inspiration
            if inspiration.get('content_ideas') and is_writing_request:
                context_parts.extend([
                    f"CONTENT IDEAS FOR {final_content_type.upper()}:",
                    *[f"• {idea}" for idea in inspiration['content_ideas'][:3]],
                    ""
                ])
            
            # Add actionable insights
            if trends.get('actionable_insights'):
                context_parts.extend([
                    "CURRENT BEST PRACTICES:",
                    *[f"• {insight}" for insight in trends['actionable_insights'][:3]],
                    ""
                ])
            
            # Add trending keywords
            if trends.get('trending_keywords'):
                context_parts.extend([
                    "TRENDING TOPICS:",
                    f"Current focus areas: {', '.join(trends['trending_keywords'][:6])}",
                    ""
                ])
            
            context_parts.append("Use this current marketing intelligence naturally to enhance your response with up-to-date insights and best practices.")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"RSS marketing context failed: {e}")
            return ""

#-- Section 6: Chat Message Processing - Updated 9/25/25 with FIXED Command Order
    async def process_chat_message(self,
                                 chat_request: ChatRequest,
                                 user_id: str = None) -> ChatResponse:
        """
        Process a chat message through the complete AI brain pipeline
        FIXED: Proper command detection order
        """
        user_id = user_id or self.default_user_id
        start_time = time.time()
        
        print(f"🚀 DEBUG: process_chat_message called with message: '{chat_request.message}'")
        
        # Get components
        memory_manager = get_memory_manager(user_id)
        knowledge_engine = get_knowledge_engine()
        personality_engine = get_personality_engine()
        
        # Handle conversation thread
        thread_id = chat_request.thread_id
        if not thread_id:
            thread_id = await memory_manager.create_conversation_thread(
                platform=chat_request.platform,
                title=None  # Will be auto-generated
            )
        
        # Store user message
        user_message_id = await memory_manager.add_message(
            thread_id=thread_id,
            role='user',
            content=chat_request.message
        )
        
        try:
            # FIXED COMMAND ORDER: Check commands in correct priority order
            
            # 1. Check for Bluesky commands first
            if self._detect_bluesky_command(chat_request.message):
                print(f"🔵 BLUESKY DEBUG: Bluesky command detected")
                
                bluesky_response = await self._process_bluesky_command(chat_request.message, user_id)
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Store Bluesky response
                ai_message_id = await memory_manager.add_message(
                    thread_id=thread_id,
                    role='assistant',
                    content=bluesky_response,
                    model_used='bluesky_assistant',
                    response_time_ms=response_time_ms
                )
                
                return ChatResponse(
                    response=bluesky_response,
                    thread_id=thread_id,
                    message_id=ai_message_id,
                    personality_id="bluesky_assistant",
                    model_used="bluesky_assistant",
                    response_time_ms=response_time_ms,
                    knowledge_sources=[],
                    conversation_context={
                        'thread_id': thread_id,
                        'command_type': 'bluesky',
                        'message_count': 2
                    }
                )
            
            # 2. Check for weather requests second
            weather_context = None
            weather_detected = self._detect_weather_request(chat_request.message)
            if weather_detected:
                print(f"🌦️ WEATHER DEBUG: Weather detected for user {user_id}")
                weather_data = await self._get_weather_for_user(user_id)
                
                if weather_data and "data" in weather_data:
                    weather_context = self._build_weather_context(weather_data["data"])
                    print(f"🌦️ WEATHER DEBUG: Weather context built successfully")
                elif weather_data and "error" in weather_data:
                    weather_context = f"""
WEATHER REQUEST DETECTED: Unfortunately, I'm having trouble accessing current weather data: {weather_data['error']}
Please respond appropriately about being unable to access weather information.
"""
                    print(f"🌦️ WEATHER DEBUG: Weather API error: {weather_data['error']}")
                else:
                    weather_context = """
WEATHER REQUEST DETECTED: Weather service is currently unavailable. Please respond appropriately.
"""
                    print(f"🌦️ WEATHER DEBUG: Weather service returned unexpected response")
            
            # 3. FIXED: Check for Marketing Scraper commands BEFORE regular AI processing
            if self._detect_scraper_command(chat_request.message):
                print(f"🔍 SCRAPER DEBUG: Marketing scraper command detected")
                
                try:
                    scraper_response = await self._process_scraper_command(chat_request.message, user_id)
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    # Store scraper response
                    ai_message_id = await memory_manager.add_message(
                        thread_id=thread_id,
                        role='assistant',
                        content=scraper_response,
                        model_used='marketing_scraper',
                        response_time_ms=response_time_ms
                    )
                    
                    print(f"🔍 SCRAPER DEBUG: Response generated and stored")
                    
                    return ChatResponse(
                        response=scraper_response,
                        thread_id=thread_id,
                        message_id=ai_message_id,
                        personality_id="marketing_scraper",
                        model_used="marketing_scraper",
                        response_time_ms=response_time_ms,
                        knowledge_sources=[],
                        conversation_context={
                            'thread_id': thread_id,
                            'command_type': 'marketing_scraper',
                            'message_count': 2
                        }
                    )
                    
                except Exception as e:
                    logger.error(f"🔍 Scraper processing failed with exception: {e}")
                    print(f"🔍 SCRAPER DEBUG: Exception during processing: {e}")
                    # Fall through to regular AI processing on scraper failure
            
            # 4. Regular AI processing (only if no special commands detected)
            print(f"🤖 DEBUG: Proceeding with regular AI processing")
            
            # Get conversation context for AI
            conversation_messages, context_info = await memory_manager.get_context_for_ai(
                thread_id, max_tokens=200000  # Leave room for knowledge and response
            )
            
            # Search knowledge base if requested
            knowledge_sources = []
            if chat_request.include_knowledge:
                knowledge_sources = await knowledge_engine.search_knowledge(
                    query=chat_request.message,
                    conversation_context=conversation_messages,
                    personality_id=chat_request.personality_id,
                    limit=5
                )
            
            # Get personality-enhanced system prompt
            system_prompt = personality_engine.get_personality_system_prompt(
                personality_id=chat_request.personality_id,
                conversation_context=conversation_messages,
                knowledge_context=knowledge_sources
            )
            
            # Get RSS marketing context for writing assistance
            rss_context = None
            if RSS_LEARNING_AVAILABLE:
                rss_context = await self._get_rss_marketing_context(chat_request.message)
                if rss_context:
                    print(f"📰 RSS marketing context added for writing assistance")
            
            # Build messages for AI
            ai_messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # Add weather context as system message if weather request detected
            if weather_context:
                ai_messages.append({
                    "role": "system",
                    "content": weather_context
                })
                print(f"🌦️ WEATHER DEBUG: Weather context added to AI messages")
            
            # Add RSS marketing context if available
            if rss_context:
                ai_messages.append({
                    "role": "system",
                    "content": rss_context
                })
                print(f"📊 RSS context added to AI messages")
            
            # Add knowledge context if available
            if knowledge_sources:
                knowledge_context = self._build_knowledge_context(knowledge_sources)
                ai_messages.append({
                    "role": "system",
                    "content": f"RELEVANT KNOWLEDGE:\n{knowledge_context}"
                })
            
            # Add conversation history
            ai_messages.extend(conversation_messages)
            
            # Add current user message
            ai_messages.append({
                "role": "user",
                "content": chat_request.message
            })
            
            # Get AI response with fallback
            ai_response, model_used = await self._get_ai_response_with_fallback(
                messages=ai_messages,
                max_tokens=chat_request.max_tokens,
                temperature=chat_request.temperature
            )
            
            # Process response through personality engine
            final_response = personality_engine.process_ai_response(
                response=ai_response,
                personality_id=chat_request.personality_id,
                conversation_context=conversation_messages
            )
            
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Store AI response
            knowledge_source_ids = [source['id'] for source in knowledge_sources]
            ai_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role='assistant',
                content=final_response,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources_used=knowledge_source_ids
            )
            
            # Build response
            chat_response = ChatResponse(
                response=final_response,
                thread_id=thread_id,
                message_id=ai_message_id,
                personality_id=chat_request.personality_id,
                model_used=model_used,
                response_time_ms=response_time_ms,
                knowledge_sources=[
                    {
                        'id': source['id'],
                        'title': source['title'],
                        'snippet': source['snippet'],
                        'score': source['final_score']
                    }
                    for source in knowledge_sources
                ],
                conversation_context={
                    'thread_id': thread_id,
                    'message_count': context_info.get('total_messages', 0),
                    'tokens_used': context_info.get('estimated_tokens', 0),
                    'has_long_term_memory': context_info.get('has_memory_context', False),
                    'weather_detected': weather_detected
                }
            )
            
            logger.info(f"Chat processed: {response_time_ms}ms, model: {model_used}, "
                       f"personality: {chat_request.personality_id}, "
                       f"weather: {'Yes' if weather_detected else 'No'}, "
                       f"rss: {'Yes' if rss_context else 'No'}")
            
            return chat_response
            
        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            
            # Store error message
            error_message = f"Sorry, I encountered an error processing your message: {str(e)}"
            error_message_id = await memory_manager.add_message(
                thread_id=thread_id,
                role='assistant',
                content=error_message,
                model_used='error'
            )
            
            raise HTTPException(status_code=500, detail=str(e))

#-- Section 7: AI Response Helper Methods - 9/23/25
    def _build_knowledge_context(self, knowledge_sources: List[Dict]) -> str:
        """Build knowledge context string for AI prompt"""
        if not knowledge_sources:
            return "No specific knowledge context available."
        
        context_parts = []
        for i, source in enumerate(knowledge_sources[:3], 1):  # Top 3 sources
            context_parts.append(
                f"{i}. {source['title']} (Score: {source['final_score']:.2f})\n"
                f"   {source['snippet']}\n"
                f"   Project: {source.get('project_name', 'Unknown')}"
            )
        
        return "\n\n".join(context_parts)
    
    async def _get_ai_response_with_fallback(self,
                                           messages: List[Dict],
                                           max_tokens: int,
                                           temperature: float) -> tuple[str, str]:
        """Get AI response with fallback between providers"""
        
        # Try OpenRouter first (primary)
        try:
            openrouter_client = await get_openrouter_client()
            response = await openrouter_client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            content = response['choices'][0]['message']['content']
            model_used = response.get('_metadata', {}).get('model_used', 'unknown')
            
            return content, model_used
            
        except Exception as e:
            logger.warning(f"OpenRouter failed, trying fallback: {e}")
            
            # Fallback to Inception Labs
            try:
                inception_client = await get_inception_client()
                response = await inception_client.chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                content = response['choices'][0]['message']['content']
                model_used = response.get('_metadata', {}).get('model_used', 'inception-fallback')
                
                return content, model_used
                
            except Exception as fallback_error:
                logger.error(f"Both AI providers failed: {fallback_error}")
                raise Exception(f"All AI providers failed. Primary: {e}, Fallback: {fallback_error}")

#-- Section 8: FIXED Feedback Processing with Proper Thread ID Lookup - 9/23/25
    async def process_feedback(self,
                             feedback_request: FeedbackRequest,
                             user_id: str = None) -> FeedbackResponse:
        """Process user feedback for learning"""
        user_id = user_id or self.default_user_id
        
        # Get feedback processor
        feedback_processor = get_feedback_processor()
        
        # FIXED: Get the actual thread_id from the message instead of hardcoded string
        try:
            from ..core.database import db_manager
            
            thread_lookup_query = """
            SELECT thread_id FROM conversation_messages 
            WHERE id = $1
            """
            
            message_result = await db_manager.fetch_one(thread_lookup_query, feedback_request.message_id)
            
            if not message_result:
                # If message not found, generate a proper UUID for feedback storage
                thread_id = str(uuid.uuid4())
                logger.warning(f"Message {feedback_request.message_id} not found, using generated UUID: {thread_id}")
            else:
                thread_id = message_result['thread_id']

        except Exception as e:
            # Fallback: generate a proper UUID instead of invalid string
            thread_id = str(uuid.uuid4())
            logger.warning(f"Could not lookup thread_id for message {feedback_request.message_id}, using generated UUID: {e}")
        
        try:
            feedback_result = await feedback_processor.record_feedback(
                user_id=user_id,
                message_id=feedback_request.message_id,
                thread_id=thread_id,
                feedback_type=feedback_request.feedback_type,
                feedback_text=feedback_request.feedback_text
            )
            
            # Generate response message
            emoji = feedback_result['emoji']
            feedback_type = feedback_request.feedback_type
            
            if feedback_type == 'personality':
                message = f"{emoji} Perfect personality! I'll remember this energy."
            elif feedback_type == 'good':
                message = f"{emoji} Thanks! I'll reinforce this approach."
            elif feedback_type == 'bad':
                message = f"{emoji} Got it, I'll avoid this approach next time."
            else:
                message = f"{emoji} Feedback received."
            
            return FeedbackResponse(
                feedback_id=feedback_result['feedback_id'],
                feedback_type=feedback_result['feedback_type'],
                emoji=emoji,
                learning_result=feedback_result['learning_result'],
                message=message
            )
            
        except Exception as e:
            logger.error(f"Feedback processing failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

#-- Section 9: Global Orchestrator Instance - 9/23/25
orchestrator = AIBrainOrchestrator()

#-- Section 10: Main API Endpoints - 9/23/25
@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(chat_request: ChatRequest):
    """
    Main chat endpoint - processes message through complete AI brain with FIXED command order
    """
    return await orchestrator.process_chat_message(chat_request)

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback_request: FeedbackRequest):
    """
    Submit feedback for AI learning (👍👎🖕)
    """
    return await orchestrator.process_feedback(feedback_request)

@router.get("/personalities")
async def get_personalities():
    """Get list of available personalities"""
    personality_engine = get_personality_engine()
    personalities = personality_engine.get_available_personalities()
    
    return {
        "personalities": [
            {
                "id": pid,
                "name": config.get('name', pid),
                "description": config.get('description', ''),
                "is_default": pid == 'syntaxprime'
            }
            for pid, config in personalities.items()
        ],
        "default_personality": "syntaxprime"
    }

#-- Section 11: Conversation Management Endpoints - 9/23/25
@router.get("/conversations")
async def get_conversations(limit: int = 50):
    """Get conversation threads"""
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    
    try:
        # Get conversations using the proper database approach
        conversations_query = """
        SELECT id, title, platform, status, message_count, 
               created_at, updated_at, last_message_at
        FROM conversation_threads
        WHERE user_id = $1
        ORDER BY last_message_at DESC
        LIMIT $2
        """
        
        from ..core.database import db_manager
        threads = await db_manager.fetch_all(conversations_query, orchestrator.default_user_id, limit)
        
        conversations = []
        for thread in threads:
            conversations.append({
                'thread_id': thread['id'],
                'title': thread['title'] or f"Conversation {thread['created_at'].strftime('%m/%d')}" if thread['created_at'] else 'New Conversation',
                'platform': thread['platform'],
                'status': thread['status'],
                'message_count': thread['message_count'] or 0,
                'created_at': thread['created_at'].isoformat() if thread['created_at'] else None,
                'updated_at': thread['updated_at'].isoformat() if thread['updated_at'] else None,
                'last_message_at': thread['last_message_at'].isoformat() if thread['last_message_at'] else None
            })
        
        return {
            "conversations": conversations,
            "total_available": len(conversations)
        }
        
    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        return {
            "conversations": [],
            "total_available": 0
        }

@router.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str, include_metadata: bool = False):
    """Get specific conversation history"""
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    
    try:
        messages = await memory_manager.get_conversation_history(
            thread_id,
            include_metadata=include_metadata
        )
        
        return {
            "thread_id": thread_id,
            "messages": messages,
            "message_count": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {e}")

#-- Section 12: Knowledge Search and Statistics Endpoints - 9/23/25
@router.get("/knowledge/search")
async def search_knowledge(q: str,
                          personality: str = 'syntaxprime',
                          limit: int = 10):
    """Search knowledge base"""
    knowledge_engine = get_knowledge_engine()
    
    results = await knowledge_engine.search_knowledge(
        query=q,
        personality_id=personality,
        limit=limit
    )
    
    return {
        "query": q,
        "results": results,
        "count": len(results)
    }

@router.get("/stats")
async def get_ai_stats():
    """Get AI brain statistics"""
    memory_manager = get_memory_manager(orchestrator.default_user_id)
    personality_engine = get_personality_engine()
    feedback_processor = get_feedback_processor()
    
    try:
        # Get conversation stats from database
        from ..core.database import db_manager
        
        conversation_stats_query = """
        SELECT 
            COUNT(DISTINCT ct.id) as total_conversations,
            COUNT(cm.id) as total_messages,
            COUNT(CASE WHEN cm.role = 'user' THEN 1 END) as user_messages,
            COUNT(CASE WHEN cm.role = 'assistant' THEN 1 END) as assistant_messages,
            AVG(cm.response_time_ms) as avg_response_time_ms,
            MAX(ct.last_message_at) as last_conversation_at
        FROM conversation_threads ct
        LEFT JOIN conversation_messages cm ON ct.id = cm.thread_id
        WHERE ct.user_id = $1
        """
        
        stats_result = await db_manager.fetch_one(conversation_stats_query, orchestrator.default_user_id)
        
        # Get personality stats
        personality_stats = personality_engine.get_personality_stats()
        
        # Get feedback summary
        feedback_summary = await feedback_processor.get_feedback_summary(
            orchestrator.default_user_id
        )
        
        return {
            "conversation_stats": {
                "total_conversations": stats_result['total_conversations'] or 0,
                "total_messages": stats_result['total_messages'] or 0,
                "user_messages": stats_result['user_messages'] or 0,
                "assistant_messages": stats_result['assistant_messages'] or 0,
                "average_response_time_ms": float(stats_result['avg_response_time_ms']) if stats_result['avg_response_time_ms'] else 0,
                "last_conversation_at": stats_result['last_conversation_at'].isoformat() if stats_result['last_conversation_at'] else None
            },
            "personality_stats": personality_stats,
            "feedback_stats": feedback_summary,
            "system_health": {
                "memory_active": True,
                "knowledge_engine_active": True,
                "learning_active": feedback_summary.get('learning_active', False),
                "bluesky_integration_active": True,
                "weather_integration_active": True,
                "marketing_scraper_integration_active": MARKETING_SCRAPER_AVAILABLE,  # NEW
                "rss_learning_integration_active": RSS_LEARNING_AVAILABLE,
                "default_user_id": orchestrator.default_user_id
            }
        }
        
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

#-- Section 13: System Testing and Health Check Endpoints - 9/23/25
@router.post("/test")
async def test_ai_connection():
    """Test AI provider connections"""
    results = {}
    
    # Test OpenRouter
    try:
        from .openrouter_client import test_openrouter_connection
        results['openrouter'] = await test_openrouter_connection()
    except Exception as e:
        results['openrouter'] = {'status': 'error', 'message': str(e)}
    
    # Test Inception Labs
    try:
        inception_client = await get_inception_client()
        results['inception_labs'] = await inception_client.test_connection()
    except Exception as e:
        results['inception_labs'] = {'status': 'error', 'message': str(e)}
    
    # Overall health
    primary_healthy = results.get('openrouter', {}).get('status') == 'success'
    fallback_available = results.get('inception_labs', {}).get('status') in ['success', 'placeholder']
    
    return {
        "providers": results,
        "system_status": "healthy" if primary_healthy or fallback_available else "degraded",
        "primary_provider": "openrouter",
        "fallback_provider": "inception_labs",
        "default_user_id": orchestrator.default_user_id
    }

#-- Section 14: Cleanup and Shutdown Handlers - 9/23/25
@router.on_event("shutdown")
async def shutdown_ai_brain():
    """Cleanup AI brain components"""
    logger.info("Shutting down AI brain components...")
    
    await cleanup_openrouter_client()
    await cleanup_inception_client()
    await cleanup_memory_managers()
    
    logger.info("AI brain shutdown complete")

#-- Section 15: Module Information and Health Check Functions - Updated 9/25/25 with Marketing Scraper
def get_integration_info():
    """Get information about the AI brain integration"""
    return {
        "name": "AI Brain",
        "version": "2.0.0",
        "components": [
            "OpenRouter Client",
            "Inception Labs Client",
            "Digital Elephant Memory",
            "Knowledge Query Engine",
            "Personality Engine",
            "Feedback Processor",
            "Weather Integration",
            "Bluesky Integration",
            "RSS Learning Integration",
            "Marketing Scraper Integration"  # NEW
        ],
        "endpoints": {
            "chat": "/ai/chat",
            "feedback": "/ai/feedback",
            "personalities": "/ai/personalities",
            "conversations": "/ai/conversations",
            "knowledge_search": "/ai/knowledge/search",
            "stats": "/ai/stats",
            "test": "/ai/test"
        },
        "features": [
            "250K context window",
            "500 conversation memory",
            "21K knowledge base integration",
            "4 personality system",
            "👍👎🖕 feedback learning",
            "Provider fallback system",
            "UUID-based user management",
            "Weather integration with health monitoring",
            "Bluesky social media command processing",
            "RSS learning integration for marketing writing assistance",
            "Marketing scraper for competitive analysis"  # NEW
        ],
        "default_user_id": orchestrator.default_user_id
    }

def check_module_health():
    """Check AI brain module health"""
    missing_vars = []
    
    # Check required environment variables
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        missing_vars.append("OPENROUTER_API_KEY")
    
    # Weather integration is optional
    weather_available = bool(os.getenv("TOMORROW_IO_API_KEY"))
    
    # Bluesky integration is optional
    bluesky_available = any([
        os.getenv("BLUESKY_PERSONAL_PASSWORD"),
        os.getenv("BLUESKY_ROSE_ANGEL_PASSWORD"),
        os.getenv("BLUESKY_BINGE_TV_PASSWORD"),
        os.getenv("BLUESKY_MEALS_FEELZ_PASSWORD"),
        os.getenv("BLUESKY_DAMN_IT_CARL_PASSWORD")
    ])
    
    # RSS learning integration is optional
    rss_learning_available = RSS_LEARNING_AVAILABLE and bool(os.getenv("DATABASE_URL"))
    
    # Marketing scraper integration is optional - NEW
    marketing_scraper_available = MARKETING_SCRAPER_AVAILABLE and bool(os.getenv("DATABASE_URL"))
    
    return {
        "healthy": len(missing_vars) == 0,
        "missing_vars": missing_vars,
        "status": "ready" if len(missing_vars) == 0 else "needs_configuration",
        "default_user_id": orchestrator.default_user_id,
        "weather_integration_available": weather_available,
        "bluesky_integration_available": bluesky_available,
        "rss_learning_integration_available": rss_learning_available,
        "marketing_scraper_integration_available": marketing_scraper_available  # NEW
    }
