# modules/integrations/marketing_scraper/content_analyzer.py
"""
AI-Powered Content Analysis Engine
Uses SyntaxPrime personality to analyze scraped content for marketing insights
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import existing AI components from Syntax Prime V2
from modules.ai.openrouter_client import get_openrouter_client
from modules.ai.personality_engine import get_personality_engine

logger = logging.getLogger(__name__)

class ContentAnalyzer:
    """
    AI-powered analysis of scraped website content using SyntaxPrime personality
    Provides comprehensive marketing insights, technical analysis, and strategic recommendations
    """
    
    def __init__(self):
        self.personality_id = 'syntaxprime'
        self.analysis_model = 'anthropic/claude-3.5-sonnet'  # High-quality analysis
        
    async def analyze_scraped_content(self, scraped_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main analysis method that processes scraped content and returns comprehensive insights
        
        Args:
            scraped_data: Output from MarketingScraperClient.scrape_website()
            
        Returns:
            Dict containing all analysis results
        """
        try:
            # Skip analysis if scraping failed
            if scraped_data.get('scrape_status') != 'completed':
                return {
                    'analysis_status': 'skipped',
                    'reason': 'scraping_failed',
                    'competitive_insights': {},
                    'marketing_angles': {},
                    'technical_details': {},
                    'cta_analysis': {},
                    'tone_analysis': {}
                }
            
            url = scraped_data.get('url', '')
            domain = scraped_data.get('domain', '')
            title = scraped_data.get('title', '')
            cleaned_content = scraped_data.get('cleaned_content', '')
            page_structure = scraped_data.get('page_structure', {})
            
            # Perform different types of analysis
            competitive_insights = await self._analyze_competitive_positioning(
                url, domain, title, cleaned_content
            )
            
            marketing_angles = await self._analyze_marketing_approach(
                title, cleaned_content, page_structure
            )
            
            technical_details = await self._analyze_technical_implementation(
                page_structure, scraped_data
            )
            
            cta_analysis = await self._analyze_cta_strategy(
                page_structure.get('ctas', []), cleaned_content
            )
            
            tone_analysis = await self._analyze_tone_and_voice(
                title, cleaned_content
            )
            
            return {
                'analysis_status': 'completed',
                'competitive_insights': competitive_insights,
                'marketing_angles': marketing_angles,
                'technical_details': technical_details,
                'cta_analysis': cta_analysis,
                'tone_analysis': tone_analysis
            }
            
        except Exception as e:
            logger.error(f"Content analysis failed for {scraped_data.get('url', 'unknown')}: {e}")
            return {
                'analysis_status': 'failed',
                'error': str(e),
                'competitive_insights': {},
                'marketing_angles': {},
                'technical_details': {},
                'cta_analysis': {},
                'tone_analysis': {}
            }
    
    async def _analyze_competitive_positioning(self, url: str, domain: str, title: str, content: str) -> Dict[str, Any]:
        """Analyze competitive positioning and unique value propositions"""
        
        analysis_prompt = f"""Analyze this competitor website for competitive positioning insights:

URL: {url}
Domain: {domain}
Title: {title}

Content Sample: {content[:2000]}...

Please provide a detailed competitive analysis focusing on:

1. **Unique Value Proposition**: What makes them different from competitors?
2. **Target Market**: Who are they clearly targeting?
3. **Key Messaging**: What are their main marketing messages?
4. **Competitive Advantages**: What strengths do they emphasize?
5. **Market Positioning**: How do they position themselves in the market?
6. **Brand Promise**: What do they promise customers?

Respond in JSON format with detailed insights that I can use for my own marketing strategy."""

        try:
            response = await self._get_ai_analysis(analysis_prompt, "competitive_positioning")
            return self._parse_json_response(response, {
                'value_proposition': '',
                'target_market': '',
                'key_messaging': [],
                'competitive_advantages': [],
                'market_positioning': '',
                'brand_promise': '',
                'strategic_insights': []
            })
        except Exception as e:
            logger.error(f"Competitive analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_marketing_approach(self, title: str, content: str, structure: Dict) -> Dict[str, Any]:
        """Analyze marketing approach and content strategy"""
        
        headings = structure.get('headings', [])
        heading_text = ' | '.join([h['text'] for h in headings[:10]])
        
        analysis_prompt = f"""Analyze this website's marketing approach and content strategy:

Title: {title}
Headings: {heading_text}
Content: {content[:2000]}...

Please analyze their marketing strategy focusing on:

1. **Content Strategy**: How do they structure and present information?
2. **Messaging Hierarchy**: How do they prioritize their messages?
3. **Emotional Appeals**: What emotions do they target?
4. **Social Proof**: How do they build credibility?
5. **Content Angles**: What angles do they use to engage visitors?
6. **Conversion Strategy**: How do they guide visitors toward action?
7. **Differentiation**: How do they stand out from competitors?

Respond in JSON format with actionable insights I can apply to my own marketing."""

        try:
            response = await self._get_ai_analysis(analysis_prompt, "marketing_approach")
            return self._parse_json_response(response, {
                'content_strategy': '',
                'messaging_hierarchy': [],
                'emotional_appeals': [],
                'social_proof_tactics': [],
                'content_angles': [],
                'conversion_strategy': '',
                'differentiation_approach': '',
                'actionable_insights': []
            })
        except Exception as e:
            logger.error(f"Marketing analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_technical_implementation(self, structure: Dict, scraped_data: Dict) -> Dict[str, Any]:
        """Analyze technical implementation and UX patterns"""
        
        technical_elements = structure.get('technical_elements', {})
        forms = structure.get('forms', [])
        images = structure.get('images', {})
        
        analysis_prompt = f"""Analyze the technical implementation and user experience of this website:

Technical Elements: {json.dumps(technical_elements, indent=2)}
Forms: {json.dumps(forms, indent=2)}
Images: {json.dumps(images, indent=2)}
Page Load Time: {scraped_data.get('processing_time_ms', 0)}ms
Content Length: {scraped_data.get('content_length', 0)} characters

Analyze:

1. **UX Patterns**: What user experience patterns do they use?
2. **Technical SEO**: How well optimized is their technical implementation?
3. **Conversion Optimization**: What technical elements support conversions?
4. **Performance**: How do they optimize for speed and user experience?
5. **Accessibility**: How accessible is their website?
6. **Mobile Experience**: How do they handle mobile users?
7. **Technical Best Practices**: What can we learn from their implementation?

Respond in JSON format with technical insights and recommendations."""

        try:
            response = await self._get_ai_analysis(analysis_prompt, "technical_implementation")
            return self._parse_json_response(response, {
                'ux_patterns': [],
                'technical_seo_score': '',
                'conversion_elements': [],
                'performance_insights': [],
                'accessibility_notes': [],
                'mobile_optimization': '',
                'best_practices_learned': [],
                'implementation_recommendations': []
            })
        except Exception as e:
            logger.error(f"Technical analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_cta_strategy(self, ctas: List[Dict], content: str) -> Dict[str, Any]:
        """Analyze call-to-action strategy and effectiveness"""
        
        cta_text = [cta.get('text', '') for cta in ctas[:10]]
        
        analysis_prompt = f"""Analyze the call-to-action strategy of this website:

CTAs Found: {json.dumps(cta_text, indent=2)}
Content Context: {content[:1500]}...

Analyze their CTA strategy:

1. **CTA Placement**: Where and how do they position CTAs?
2. **CTA Copy**: What language and psychology do they use?
3. **CTA Hierarchy**: How do they prioritize different actions?
4. **Urgency Tactics**: How do they create urgency or scarcity?
5. **Value Proposition**: How do they communicate value in CTAs?
6. **Conversion Funnel**: How do they guide users through actions?
7. **A/B Test Insights**: What variations might they be testing?

Respond in JSON format with CTA insights and recommendations."""

        try:
            response = await self._get_ai_analysis(analysis_prompt, "cta_strategy")
            return self._parse_json_response(response, {
                'cta_placement_strategy': '',
                'copy_psychology': [],
                'action_hierarchy': [],
                'urgency_tactics': [],
                'value_communication': [],
                'conversion_funnel_design': '',
                'optimization_opportunities': [],
                'recommended_tests': []
            })
        except Exception as e:
            logger.error(f"CTA analysis failed: {e}")
            return {'error': str(e)}
    
    async def _analyze_tone_and_voice(self, title: str, content: str) -> Dict[str, Any]:
        """Analyze brand tone, voice, and communication style"""
        
        analysis_prompt = f"""Analyze the brand tone and voice of this website:

Title: {title}
Content: {content[:2000]}...

Analyze their communication style:

1. **Brand Voice**: How would you describe their overall voice?
2. **Tone Characteristics**: What tone do they use (professional, casual, authoritative)?
3. **Language Patterns**: What language patterns and word choices stand out?
4. **Personality Traits**: What personality does their brand convey?
5. **Emotional Tone**: What emotions do they evoke?
6. **Communication Style**: How formal/informal, direct/indirect are they?
7. **Audience Connection**: How do they connect with their target audience?

Respond in JSON format with detailed voice and tone analysis."""

        try:
            response = await self._get_ai_analysis(analysis_prompt, "tone_and_voice")
            return self._parse_json_response(response, {
                'brand_voice_description': '',
                'tone_characteristics': [],
                'language_patterns': [],
                'personality_traits': [],
                'emotional_tone': [],
                'communication_style': '',
                'audience_connection_methods': [],
                'voice_differentiation': ''
            })
        except Exception as e:
            logger.error(f"Tone analysis failed: {e}")
            return {'error': str(e)}
    
    async def _get_ai_analysis(self, prompt: str, analysis_type: str) -> str:
        """Get AI analysis using SyntaxPrime personality"""
        try:
            # Get personality engine and OpenRouter client
            personality_engine = get_personality_engine()
            openrouter_client = get_openrouter_client()
            
            # Get SyntaxPrime personality configuration
            personality_config = personality_engine.get_personality(self.personality_id)
            
            # Build full prompt with personality context
            full_prompt = f"""{personality_config['system_prompt']}

You are analyzing competitor website content for marketing insights. 
Be thorough, strategic, and actionable in your analysis.

{prompt}

Provide detailed, JSON-formatted insights that can be used for strategic marketing decisions."""

            # Get AI response
            response = await openrouter_client.get_completion(
                model=self.analysis_model,
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=2000
            )
            
            return response
            
        except Exception as e:
            logger.error(f"AI analysis failed for {analysis_type}: {e}")
            raise
    
    def _parse_json_response(self, response: str, fallback_structure: Dict) -> Dict[str, Any]:
        """Parse JSON response from AI with fallback structure"""
        try:
            # Try to extract JSON from response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                return parsed
            else:
                # No JSON found, create structured response from text
                return self._structure_text_response(response, fallback_structure)
                
        except json.JSONDecodeError:
            # JSON parsing failed, structure the text response
            return self._structure_text_response(response, fallback_structure)
    
    def _structure_text_response(self, text: str, structure: Dict) -> Dict[str, Any]:
        """Convert text response to structured format"""
        # This is a simplified approach - in practice you might want more sophisticated parsing
        structured = structure.copy()
        structured['raw_analysis'] = text
        structured['parsed_from_text'] = True
        return structured
    
    def create_analysis_summary(self, analysis_results: Dict[str, Any], url: str) -> str:
        """Create a human-readable summary of the analysis for chat context"""
        
        if analysis_results.get('analysis_status') != 'completed':
            return f"❌ Analysis failed for {url}: {analysis_results.get('error', 'Unknown error')}"
        
        summary_parts = [
            f"🔍 **Marketing Analysis for {url}**\n",
        ]
        
        # Competitive insights
        competitive = analysis_results.get('competitive_insights', {})
        if competitive and 'value_proposition' in competitive:
            summary_parts.append(f"**Value Proposition:** {competitive['value_proposition']}")
        
        # Marketing angles
        marketing = analysis_results.get('marketing_angles', {})
        if marketing and 'content_strategy' in marketing:
            summary_parts.append(f"**Content Strategy:** {marketing['content_strategy']}")
        
        # CTA insights
        cta = analysis_results.get('cta_analysis', {})
        if cta and 'cta_placement_strategy' in cta:
            summary_parts.append(f"**CTA Strategy:** {cta['cta_placement_strategy']}")
        
        # Technical insights
        technical = analysis_results.get('technical_details', {})
        if technical and 'ux_patterns' in technical:
            patterns = technical.get('ux_patterns', [])
            if patterns:
                summary_parts.append(f"**UX Patterns:** {', '.join(patterns[:3])}")
        
        # Tone analysis
        tone = analysis_results.get('tone_analysis', {})
        if tone and 'brand_voice_description' in tone:
            summary_parts.append(f"**Brand Voice:** {tone['brand_voice_description']}")
        
        summary_parts.append("\n💡 *Full analysis stored for future reference and context.*")
        
        return "\n\n".join(summary_parts)