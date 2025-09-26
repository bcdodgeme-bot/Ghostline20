# modules/integrations/marketing_scraper/scraper_client.py
"""
Website Content Extraction Client for Syntax Prime V2
Handles the technical aspects of scraping competitor websites with comprehensive debugging
Updated: 9/26/25 - Fixed syntax error and enhanced debugging capabilities
"""

#-- Section 1: Core Imports and Dependencies - 9/26/25
import os
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, List, Any, Tuple
from urllib.parse import urlparse, urljoin
from datetime import datetime
from bs4 import BeautifulSoup
import json
import time
import traceback

#-- Section 2: Logger Configuration - 9/26/25
logger = logging.getLogger(__name__)

# Enhanced debugging configuration
DEBUG_MODE = os.getenv('SCRAPER_DEBUG_MODE', 'true').lower() == 'true'
VERBOSE_DEBUG = os.getenv('SCRAPER_VERBOSE_DEBUG', 'false').lower() == 'true'

def debug_log(message: str, level: str = "info", verbose_only: bool = False):
    """Enhanced debug logging with levels and verbose control"""
    if not DEBUG_MODE:
        return
    if verbose_only and not VERBOSE_DEBUG:
        return
    
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    prefix = f"🔍 SCRAPER [{timestamp}]"
    
    if level == "error":
        prefix = f"❌ SCRAPER ERROR [{timestamp}]"
        print(f"{prefix} {message}")
        logger.error(message)
    elif level == "warning":
        prefix = f"⚠️  SCRAPER WARN [{timestamp}]"
        print(f"{prefix} {message}")
        logger.warning(message)
    elif level == "success":
        prefix = f"✅ SCRAPER SUCCESS [{timestamp}]"
        print(f"{prefix} {message}")
        logger.info(message)
    else:
        print(f"{prefix} {message}")
        logger.info(message)

#-- Section 3: Main MarketingScraperClient Class - 9/26/25
class MarketingScraperClient:
    """
    Handles website content extraction with intelligent cleaning and structure analysis
    Enhanced with comprehensive debugging and error handling
    """
    
    def __init__(self):
        debug_log("Initializing MarketingScraperClient")
        
        self.user_agent = os.getenv(
            'SCRAPER_USER_AGENT',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        )
        self.timeout = int(os.getenv('SCRAPER_TIMEOUT_SECONDS', '30'))
        self.max_content_length = 1000000  # 1MB max content
        self.retry_attempts = int(os.getenv('SCRAPER_RETRY_ATTEMPTS', '3'))
        self.retry_delay = float(os.getenv('SCRAPER_RETRY_DELAY', '1.0'))
        
        debug_log(f"Configuration loaded:")
        debug_log(f"  - Timeout: {self.timeout}s")
        debug_log(f"  - Max content: {self.max_content_length} bytes")
        debug_log(f"  - Retry attempts: {self.retry_attempts}")
        debug_log(f"  - User agent: {self.user_agent[:50]}...", verbose_only=True)
        
    #-- Section 4: Main Scraping Method - 9/26/25
    async def scrape_website(self, url: str) -> Dict[str, Any]:
        """
        Main scraping method that extracts and analyzes website content
        Enhanced with comprehensive error handling and debugging
        
        Returns:
            Dict containing raw content, cleaned content, and structural analysis
        """
        debug_log(f"Starting website scrape for: {url}")
        start_time = datetime.now()
        
        try:
            # Validate URL
            debug_log("Step 1: Validating URL format")
            parsed_url = self._validate_url(url)
            if not parsed_url:
                raise ValueError(f"Invalid URL format: {url}")
            debug_log(f"URL validation successful - Domain: {parsed_url.netloc}", "success")
            
            # Fetch website content with retry logic
            debug_log("Step 2: Fetching website content")
            raw_html, response_info = await self._fetch_content_with_retry(url)
            debug_log(f"Content fetched successfully - Size: {len(raw_html)} chars", "success")
            
            # Parse HTML and extract content
            debug_log("Step 3: Parsing HTML content")
            parse_start = time.time()
            soup = BeautifulSoup(raw_html, 'html.parser')
            parse_time = (time.time() - parse_start) * 1000
            debug_log(f"HTML parsed in {parse_time:.2f}ms", "success")
            
            # Extract basic metadata
            debug_log("Step 4: Extracting page metadata")
            metadata = self._extract_metadata(soup, parsed_url)
            debug_log(f"Metadata extracted - Title: '{metadata.get('title', 'N/A')[:50]}...'", "success")
            
            # Clean and extract main content
            debug_log("Step 5: Extracting and cleaning main content")
            cleaned_content = self._extract_clean_content(soup)
            word_count = len(cleaned_content.split()) if cleaned_content else 0
            debug_log(f"Content cleaned - Word count: {word_count}", "success")
            
            # Analyze page structure
            debug_log("Step 6: Analyzing page structure and elements")
            page_structure = self._analyze_page_structure(soup)
            debug_log("Page structure analysis completed", "success")
            
            # Calculate final processing metrics
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = {
                'url': url,
                'domain': parsed_url.netloc,
                'title': metadata.get('title', ''),
                'meta_description': metadata.get('description', ''),
                'raw_content': raw_html[:self.max_content_length],  # Truncate if too long
                'cleaned_content': cleaned_content,
                'page_structure': page_structure,
                'response_info': response_info,
                'processing_time_ms': int(processing_time),
                'content_length': len(raw_html),
                'word_count': word_count,
                'scrape_status': 'completed',
                'scraped_at': start_time.isoformat(),
                'debug_info': {
                    'parse_time_ms': round(parse_time, 2),
                    'retry_attempts_used': getattr(self, '_last_retry_count', 0),
                    'content_truncated': len(raw_html) > self.max_content_length
                }
            }
            
            debug_log(f"Scraping completed successfully in {processing_time:.0f}ms", "success")
            debug_log(f"Final stats: {word_count} words, {len(page_structure.get('headings', []))} headings, {len(page_structure.get('ctas', []))} CTAs")
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            debug_log(f"Scraping failed: {error_msg}", "error")
            debug_log(f"Full traceback: {traceback.format_exc()}", "error", verbose_only=True)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                'url': url,
                'domain': urlparse(url).netloc if self._validate_url(url) else 'unknown',
                'scrape_status': 'failed',
                'error_message': error_msg,
                'error_type': type(e).__name__,
                'processing_time_ms': int(processing_time),
                'failed_at': start_time.isoformat(),
                'debug_info': {
                    'retry_attempts_used': getattr(self, '_last_retry_count', 0),
                    'traceback': traceback.format_exc() if VERBOSE_DEBUG else None
                }
            }
    
    #-- Section 5: URL Validation - 9/26/25
    def _validate_url(self, url: str) -> Optional[Any]:
        """Validate URL format and return parsed URL with enhanced debugging"""
        debug_log(f"Validating URL: {url}", verbose_only=True)
        
        try:
            parsed = urlparse(url)
            
            if not parsed.scheme:
                debug_log("URL validation failed: Missing scheme (http/https)", "warning")
                return None
            if not parsed.netloc:
                debug_log("URL validation failed: Missing domain", "warning")
                return None
            if parsed.scheme not in ['http', 'https']:
                debug_log(f"URL validation failed: Invalid scheme '{parsed.scheme}'", "warning")
                return None
                
            debug_log(f"URL components: scheme={parsed.scheme}, domain={parsed.netloc}, path={parsed.path}", verbose_only=True)
            return parsed
            
        except Exception as e:
            debug_log(f"URL parsing error: {e}", "error")
            return None
    
    #-- Section 6: Content Fetching with Retry Logic - 9/26/25
    async def _fetch_content_with_retry(self, url: str) -> Tuple[str, Dict]:
        """Fetch content with retry logic and enhanced error handling"""
        debug_log(f"Fetching content with up to {self.retry_attempts} attempts")
        
        last_exception = None
        self._last_retry_count = 0
        
        for attempt in range(self.retry_attempts):
            try:
                debug_log(f"Attempt {attempt + 1}/{self.retry_attempts}")
                content, response_info = await self._fetch_content(url)
                
                if attempt > 0:
                    debug_log(f"Retry successful on attempt {attempt + 1}", "success")
                
                self._last_retry_count = attempt
                return content, response_info
                
            except Exception as e:
                last_exception = e
                self._last_retry_count = attempt + 1
                
                debug_log(f"Attempt {attempt + 1} failed: {str(e)}", "warning")
                
                if attempt < self.retry_attempts - 1:
                    debug_log(f"Waiting {self.retry_delay}s before retry...")
                    await asyncio.sleep(self.retry_delay)
                    
        debug_log(f"All {self.retry_attempts} attempts failed", "error")
        raise last_exception
    
    async def _fetch_content(self, url: str) -> Tuple[str, Dict]:
        """Fetch website content with proper headers and error handling"""
        debug_log(f"Making HTTP request to: {url}", verbose_only=True)
        
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        request_start = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    request_time = (time.time() - request_start) * 1000
                    
                    debug_log(f"HTTP {response.status} received in {request_time:.2f}ms", verbose_only=True)
                    
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}: {response.reason}")
                    
                    content_type = response.headers.get('content-type') or ''
                    if 'text/html' not in content_type.lower():
                        debug_log(f"Warning: Unexpected content type: {content_type}", "warning")
                    
                    content = await response.text()
                    
                    response_info = {
                        'status_code': response.status,
                        'content_type': content_type,
                        'content_length': len(content),
                        'response_headers': dict(response.headers),
                        'request_time_ms': round(request_time, 2)
                    }
                    
                    debug_log(f"Content received - Type: {content_type}, Size: {len(content)} chars", verbose_only=True)
                    
                    return content, response_info
                    
        except asyncio.TimeoutError:
            debug_log(f"Request timeout after {self.timeout}s", "error")
            raise Exception(f"Request timeout after {self.timeout} seconds")
        except Exception as e:
            debug_log(f"HTTP request failed: {str(e)}", "error")
            raise
    
    #-- Section 7: Metadata Extraction - 9/26/25
    def _extract_metadata(self, soup: BeautifulSoup, parsed_url: Any) -> Dict[str, str]:
        """Extract basic page metadata with detailed debugging"""
        debug_log("Extracting page metadata", verbose_only=True)
        metadata = {}
        
        # Title extraction
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)
            debug_log(f"Title found: '{metadata['title'][:100]}...'", verbose_only=True)
        else:
            debug_log("No title tag found", "warning", verbose_only=True)
            metadata['title'] = ''
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            metadata['description'] = meta_desc.get('content', '')
            debug_log(f"Meta description found: '{metadata['description'][:100]}...'", verbose_only=True)
        else:
            debug_log("No meta description found", verbose_only=True)
            metadata['description'] = ''
        
        # Open Graph data fallbacks
        og_title = soup.find('meta', property='og:title')
        if og_title and not metadata['title']:
            metadata['title'] = og_title.get('content', '')
            debug_log("Using OG:title as fallback", verbose_only=True)
            
        og_desc = soup.find('meta', property='og:description')
        if og_desc and not metadata['description']:
            metadata['description'] = og_desc.get('content', '')
            debug_log("Using OG:description as fallback", verbose_only=True)
        
        # Additional metadata
        metadata['canonical_url'] = ''
        canonical = soup.find('link', rel='canonical')
        if canonical:
            metadata['canonical_url'] = canonical.get('href', '')
            debug_log(f"Canonical URL: {metadata['canonical_url']}", verbose_only=True)
        
        return metadata
    
    #-- Section 8: Content Cleaning and Extraction - 9/26/25
    def _extract_clean_content(self, soup: BeautifulSoup) -> str:
        """Extract and clean main content from page with detailed debugging"""
        debug_log("Starting content extraction and cleaning")
        
        # Remove unwanted elements
        unwanted_elements = ['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']
        removed_count = 0
        for element_type in unwanted_elements:
            elements = soup.find_all(element_type)
            removed_count += len(elements)
            for element in elements:
                element.decompose()
        
        debug_log(f"Removed {removed_count} unwanted elements", verbose_only=True)
        
        # Try to find main content area
        main_content = None
        content_selectors = [
            'main', 'article', '[role="main"]',
            '.content', '.main-content', '.post-content',
            '.entry-content', '.article-content'
        ]
        
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                debug_log(f"Main content found using selector: {selector}", verbose_only=True)
                break
        
        # Fallback hierarchy
        if not main_content:
            main_content = soup.find('body')
            if main_content:
                debug_log("Using body as main content (fallback)", verbose_only=True)
            else:
                main_content = soup
                debug_log("Using entire soup as main content (last resort)", "warning", verbose_only=True)
        
        # Extract text content
        text_content = []
        element_count = 0
        
        for element in main_content.find_all(text=True):
            element_count += 1
            if element.parent.name not in ['script', 'style']:
                text = element.strip()
                if text and len(text) > 10:  # Only meaningful text
                    text_content.append(text)
        
        debug_log(f"Processed {element_count} text elements, kept {len(text_content)} meaningful ones", verbose_only=True)
        
        # Clean and join content
        raw_joined = ' '.join(text_content)
        cleaned = re.sub(r'\s+', ' ', raw_joined)  # Normalize whitespace
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)  # Clean line breaks
        final_content = cleaned.strip()
        
        debug_log(f"Content cleaning complete - Final length: {len(final_content)} chars")
        
        return final_content
    
    #-- Section 9: Page Structure Analysis - FIXED SYNTAX ERROR - 9/26/25
    def _analyze_page_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page structure for technical insights - FIXED VERSION"""
        debug_log("Starting comprehensive page structure analysis")
        analysis_start = time.time()
        
        try:
            # Extract all structural components
            debug_log("Extracting headings structure")
            headings = self._extract_headings(soup)
            
            debug_log("Extracting call-to-action elements")
            ctas = self._extract_ctas(soup)
            
            debug_log("Extracting form elements")
            forms = self._extract_forms(soup)
            
            debug_log("Extracting image information")
            images = self._extract_images(soup)
            
            debug_log("Extracting link structure")
            links = self._extract_links(soup)
            
            debug_log("Extracting social media signals")
            social_signals = self._extract_social_signals(soup)
            
            debug_log("Extracting technical SEO elements")
            technical_elements = self._extract_technical_elements(soup)
            
            # **FIXED: Proper indentation and structure inside try block**
            structure = {
                'headings': headings,
                'ctas': ctas,
                'forms': forms,
                'images': images,
                'links': links,
                'social_signals': social_signals,
                'technical_elements': technical_elements,
                'analysis_metadata': {
                    'total_analysis_time_ms': round((time.time() - analysis_start) * 1000, 2),
                    'elements_analyzed': {
                        'headings_count': len(headings),
                        'ctas_count': len(ctas),
                        'forms_count': len(forms),
                        'social_platforms': len(social_signals)
                    }
                }
            }
            
            debug_log(f"Structure analysis completed in {structure['analysis_metadata']['total_analysis_time_ms']}ms", "success")
            return structure
            
        except Exception as e:
            debug_log(f"Error in page structure analysis: {str(e)}", "error")
            debug_log(f"Full traceback: {traceback.format_exc()}", "error", verbose_only=True)
            
            # Return safe fallback structure on error
            return {
                'headings': [],
                'ctas': [],
                'forms': [],
                'images': {'total_images': 0, 'images_with_alt': 0, 'hero_images': 0},
                'links': {'total_links': 0, 'external_links_count': 0, 'external_domains': []},
                'social_signals': [],
                'technical_elements': {},
                'analysis_metadata': {
                    'error': str(e),
                    'analysis_failed': True
                }
            }
    
    #-- Section 10: Heading Structure Extraction - 9/26/25
    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract heading structure with comprehensive analysis"""
        debug_log("Analyzing heading structure", verbose_only=True)
        headings = []
        
        for level in range(1, 7):  # h1 to h6
            level_headings = soup.find_all(f'h{level}')
            debug_log(f"Found {len(level_headings)} H{level} headings", verbose_only=True)
            
            for heading in level_headings:
                text = heading.get_text(strip=True)
                if text:
                    heading_data = {
                        'level': level,
                        'text': text,
                        'length': len(text),
                        'word_count': len(text.split()),
                        'classes': ' '.join(heading.get('class', [])),
                        'id': heading.get('id', '')
                    }
                    headings.append(heading_data)
        
        debug_log(f"Total headings extracted: {len(headings)}")
        return headings
    
    #-- Section 11: Call-to-Action Extraction - 9/26/25
    def _extract_ctas(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract call-to-action elements with enhanced pattern recognition"""
        debug_log("Extracting CTA elements", verbose_only=True)
        ctas = []
        
        # Button elements
        button_count = 0
        for button in soup.find_all(['button', 'input']):
            if button.name == 'input' and button.get('type') not in ['submit', 'button']:
                continue
                
            text = button.get_text(strip=True) or button.get('value', '')
            if text:
                button_count += 1
                ctas.append({
                    'type': 'button',
                    'text': text,
                    'element': button.name,
                    'classes': ' '.join(button.get('class', [])),
                    'id': button.get('id', '')
                })
        
        debug_log(f"Found {button_count} button CTAs", verbose_only=True)
        
        # Link-based CTAs with enhanced patterns
        cta_patterns = [
            r'sign\s*up', r'get\s*started', r'try\s*(free|now)', r'download',
            r'buy\s*now', r'order\s*now', r'subscribe', r'register',
            r'learn\s*more', r'contact\s*us', r'book\s*demo', r'request\s*demo',
            r'get\s*quote', r'free\s*trial', r'start\s*free', r'join\s*now'
        ]
        
        link_cta_count = 0
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True).lower()
            classes = ' '.join(link.get('class', [])).lower()
            
            is_cta = any(re.search(pattern, text) for pattern in cta_patterns)
            is_cta = is_cta or any(word in classes for word in ['btn', 'button', 'cta', 'call-to-action'])
            
            if is_cta and text:
                link_cta_count += 1
                ctas.append({
                    'type': 'link',
                    'text': text,
                    'href': link['href'],
                    'classes': classes,
                    'id': link.get('id', ''),
                    'target': link.get('target', '')
                })
        
        debug_log(f"Found {link_cta_count} link CTAs", verbose_only=True)
        debug_log(f"Total CTAs extracted: {len(ctas)}")
        
        return ctas
    
    #-- Section 12: Form Analysis - 9/26/25
    def _extract_forms(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract comprehensive form information"""
        debug_log("Extracting form elements", verbose_only=True)
        forms = []
        
        for i, form in enumerate(soup.find_all('form')):
            form_data = {
                'form_index': i,
                'action': form.get('action', ''),
                'method': form.get('method', 'get').upper(),
                'id': form.get('id', ''),
                'classes': ' '.join(form.get('class', [])),
                'fields': []
            }
            
            # Analyze form fields
            for input_field in form.find_all(['input', 'textarea', 'select']):
                field_type = input_field.get('type', input_field.name)
                field_name = input_field.get('name', '')
                placeholder = input_field.get('placeholder', '')
                
                if field_type not in ['hidden']:  # Include submit buttons in analysis
                    field_data = {
                        'type': field_type,
                        'name': field_name,
                        'placeholder': placeholder,
                        'required': input_field.get('required') is not None,
                        'id': input_field.get('id', ''),
                        'classes': ' '.join(input_field.get('class', []))
                    }
                    form_data['fields'].append(field_data)
            
            form_data['field_count'] = len(form_data['fields'])
            forms.append(form_data)
            
            debug_log(f"Form {i}: {form_data['field_count']} fields, method={form_data['method']}", verbose_only=True)
        
        debug_log(f"Total forms extracted: {len(forms)}")
        return forms
    
    #-- Section 13: Image Analysis - 9/26/25
    def _extract_images(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract comprehensive image information"""
        debug_log("Analyzing image elements", verbose_only=True)
        images = soup.find_all('img')
        
        images_with_alt = [img for img in images if img.get('alt')]
        hero_images = [img for img in images if 'hero' in ' '.join(img.get('class', [])).lower()]
        lazy_images = [img for img in images if img.get('loading') == 'lazy']
        
        image_data = {
            'total_images': len(images),
            'images_with_alt': len(images_with_alt),
            'hero_images': len(hero_images),
            'lazy_loading_images': len(lazy_images),
            'alt_text_coverage': round((len(images_with_alt) / len(images)) * 100, 1) if images else 0,
            'common_formats': self._analyze_image_formats(images)
        }
        
        debug_log(f"Image analysis: {image_data['total_images']} total, {image_data['alt_text_coverage']}% have alt text")
        return image_data
    
    def _analyze_image_formats(self, images: List) -> Dict[str, int]:
        """Analyze image formats from src attributes"""
        formats = {}
        for img in images:
            src = img.get('src', '').lower()
            if '.jpg' in src or '.jpeg' in src:
                formats['jpeg'] = formats.get('jpeg', 0) + 1
            elif '.png' in src:
                formats['png'] = formats.get('png', 0) + 1
            elif '.svg' in src:
                formats['svg'] = formats.get('svg', 0) + 1
            elif '.webp' in src:
                formats['webp'] = formats.get('webp', 0) + 1
            elif '.gif' in src:
                formats['gif'] = formats.get('gif', 0) + 1
        return formats
    
    #-- Section 14: Link Analysis - 9/26/25
    def _extract_links(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract comprehensive link information"""
        debug_log("Analyzing link structure", verbose_only=True)
        links = soup.find_all('a', href=True)
        
        external_links = []
        internal_links = []
        anchor_links = []
        
        base_domain = getattr(soup, 'base_url', '')
        
        for link in links:
            href = link.get('href') or ''
            
            if href.startswith('#'):
                anchor_links.append(href)
            elif href.startswith(('http://', 'https://')):
                if base_domain and base_domain not in href:
                    external_links.append(href)
                else:
                    internal_links.append(href)
            else:
                internal_links.append(href)
        
        # Analyze external domains
        external_domains = []
        for url in external_links:
            try:
                domain = urlparse(url).netloc
                if domain not in external_domains:
                    external_domains.append(domain)
            except:
                continue
        
        link_data = {
            'total_links': len(links),
            'internal_links': len(internal_links),
            'external_links_count': len(external_links),
            'anchor_links': len(anchor_links),
            'external_domains': external_domains,
            'external_domain_count': len(external_domains),
            'link_distribution': {
                'internal_percentage': round((len(internal_links) / len(links)) * 100, 1) if links else 0,
                'external_percentage': round((len(external_links) / len(links)) * 100, 1) if links else 0,
                'anchor_percentage': round((len(anchor_links) / len(links)) * 100, 1) if links else 0
            }
        }
        
        debug_log(f"Link analysis: {link_data['total_links']} total ({link_data['internal_links']} internal, {link_data['external_links_count']} external)")
        return link_data
    
    #-- Section 15: Social Media Signal Detection - 9/26/25
    def _extract_social_signals(self, soup: BeautifulSoup) -> List[str]:
        """Extract social media signals with enhanced detection"""
        debug_log("Detecting social media signals", verbose_only=True)
        social_platforms = []
        
        social_domains = {
            'facebook.com': 'facebook',
            'twitter.com': 'twitter',
            'x.com': 'twitter',
            'linkedin.com': 'linkedin',
            'instagram.com': 'instagram',
            'youtube.com': 'youtube',
            'tiktok.com': 'tiktok',
            'pinterest.com': 'pinterest',
            'snapchat.com': 'snapchat',
            'discord.gg': 'discord',
            'telegram.me': 'telegram',
            'whatsapp.com': 'whatsapp'
        }
        
        # Check links
        for link in soup.find_all('a', href=True):
            href = (link.get('href') or '').lower()
            for domain, platform in social_domains.items():
                if domain in href and platform not in social_platforms:
                    social_platforms.append(platform)
                    debug_log(f"Found {platform} link", verbose_only=True)
        
        # Check for social media meta tags
        social_meta_tags = soup.find_all('meta', property=lambda x: x and 'og:' in x)
        if social_meta_tags and 'opengraph' not in social_platforms:
            social_platforms.append('opengraph')
            debug_log("Found Open Graph meta tags", verbose_only=True)
        
        twitter_cards = soup.find_all('meta', attrs={'name': lambda x: x and 'twitter:' in x})
        if twitter_cards and 'twitter_cards' not in social_platforms:
            social_platforms.append('twitter_cards')
            debug_log("Found Twitter Card meta tags", verbose_only=True)
        
        debug_log(f"Social signals detected: {len(social_platforms)} platforms")
        return social_platforms
    
    #-- Section 16: Technical SEO Analysis - 9/26/25
    def _extract_technical_elements(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract technical SEO and structure elements with comprehensive analysis"""
        debug_log("Analyzing technical SEO elements", verbose_only=True)
        
        # Schema markup analysis
        schema_scripts = soup.find_all('script', type='application/ld+json')
        structured_data_types = self._extract_structured_data(soup)
        
        # Meta tag analysis
        meta_tags = soup.find_all('meta')
        meta_analysis = self._analyze_meta_tags(meta_tags)
        
        # Technical elements
        technical_data = {
            'has_schema_markup': bool(schema_scripts),
            'schema_scripts_count': len(schema_scripts),
            'structured_data_types': structured_data_types,
            'meta_tags_count': len(meta_tags),
            'meta_analysis': meta_analysis,
            'canonical_url': soup.find('link', rel='canonical').get('href') if soup.find('link', rel='canonical') else None,
            'viewport_meta': bool(soup.find('meta', attrs={'name': 'viewport'})),
            'robots_meta': soup.find('meta', attrs={'name': 'robots'}).get('content') if soup.find('meta', attrs={'name': 'robots'}) else None,
            'lang_attribute': soup.find('html').get('lang') if soup.find('html') else None,
            'title_tag_present': bool(soup.find('title')),
            'h1_count': len(soup.find_all('h1')),
            'performance_hints': self._analyze_performance_hints(soup)
        }
        
        debug_log(f"Technical analysis: {len(structured_data_types)} schema types, {technical_data['meta_tags_count']} meta tags")
        return technical_data
    
    def _analyze_meta_tags(self, meta_tags: List) -> Dict[str, Any]:
        """Analyze meta tags for SEO insights"""
        analysis = {
            'total_count': len(meta_tags),
            'has_description': False,
            'has_keywords': False,
            'has_author': False,
            'has_viewport': False,
            'open_graph_count': 0,
            'twitter_card_count': 0
        }
        
        for meta in meta_tags:
            name = meta.get('name', '').lower()
            prop = meta.get('property', '').lower()
            
            if name == 'description':
                analysis['has_description'] = True
            elif name == 'keywords':
                analysis['has_keywords'] = True
            elif name == 'author':
                analysis['has_author'] = True
            elif name == 'viewport':
                analysis['has_viewport'] = True
            elif prop.startswith('og:'):
                analysis['open_graph_count'] += 1
            elif name.startswith('twitter:'):
                analysis['twitter_card_count'] += 1
        
        return analysis
    
    def _analyze_performance_hints(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze performance optimization hints"""
        return {
            'preload_links': len(soup.find_all('link', rel='preload')),
            'prefetch_links': len(soup.find_all('link', rel='prefetch')),
            'dns_prefetch_links': len(soup.find_all('link', rel='dns-prefetch')),
            'preconnect_links': len(soup.find_all('link', rel='preconnect')),
            'lazy_loading_images': len(soup.find_all('img', loading='lazy')),
            'async_scripts': len(soup.find_all('script', attrs={'async': True})),
            'defer_scripts': len(soup.find_all('script', attrs={'defer': True}))
        }
    
    #-- Section 17: Structured Data Extraction - 9/26/25
    def _extract_structured_data(self, soup: BeautifulSoup) -> List[str]:
        """Extract structured data types with error handling"""
        debug_log("Extracting structured data", verbose_only=True)
        structured_types = []
        
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or '{}')
                if isinstance(data, dict) and '@type' in data:
                    structured_types.append(data['@type'])
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and '@type' in item:
                            structured_types.append(item['@type'])
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                debug_log(f"Error parsing structured data: {e}", "warning", verbose_only=True)
                continue
        
        unique_types = list(set(structured_types))
        debug_log(f"Structured data types found: {unique_types}", verbose_only=True)
        return unique_types
