# modules/integrations/marketing_scraper/scraper_client.py
"""
Website Content Extraction Client
Handles the technical aspects of scraping competitor websites
"""

import os
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, List, Any
from urllib.parse import urlparse, urljoin
from datetime import datetime
from bs4 import BeautifulSoup
import json

logger = logging.getLogger(__name__)

class MarketingScraperClient:
    """
    Handles website content extraction with intelligent cleaning and structure analysis
    """
    
    def __init__(self):
        self.user_agent = os.getenv(
            'SCRAPER_USER_AGENT', 
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        )
        self.timeout = int(os.getenv('SCRAPER_TIMEOUT_SECONDS', '30'))
        self.max_content_length = 1000000  # 1MB max content
        
    async def scrape_website(self, url: str) -> Dict[str, Any]:
        """
        Main scraping method that extracts and analyzes website content
        
        Returns:
            Dict containing raw content, cleaned content, and structural analysis
        """
        start_time = datetime.now()
        
        try:
            # Validate URL
            parsed_url = self._validate_url(url)
            if not parsed_url:
                raise ValueError(f"Invalid URL format: {url}")
            
            # Fetch website content
            print(f"🔍 SCRAPER DEBUG: Fetching content")
            raw_html, response_info = await self._fetch_content(url)
            
            # Parse HTML and extract content
            print(f"🔍 SCRAPER DEBUG: Parsing HTML")
            soup = BeautifulSoup(raw_html, 'html.parser')
            
            # Extract basic metadata
            print(f"🔍 SCRAPER DEBUG: Extracting metadata")
            metadata = self._extract_metadata(soup, parsed_url)
            
            # Clean and extract main content
            print(f"🔍 SCRAPER DEBUG: Extracting clean content")
            cleaned_content = self._extract_clean_content(soup)
            
            # Analyze page structure
            print(f"🔍 SCRAPER DEBUG: Analyzing page structure")
            page_structure = self._analyze_page_structure(soup)
            
            # Calculate processing metrics
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            word_count = len(cleaned_content.split()) if cleaned_content else 0
            
            return {
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
                'scrape_status': 'completed'
            }
            
        except Exception as e:
            logger.error(f"Scraping failed for {url}: {e}")
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                'url': url,
                'domain': urlparse(url).netloc if self._validate_url(url) else 'unknown',
                'scrape_status': 'failed',
                'error_message': str(e),
                'processing_time_ms': int(processing_time)
            }
    
    def _validate_url(self, url: str) -> Optional[Any]:
        """Validate URL format and return parsed URL"""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return None
            if parsed.scheme not in ['http', 'https']:
                return None
            return parsed
        except Exception:
            return None
    
    async def _fetch_content(self, url: str) -> tuple[str, Dict]:
        """Fetch website content with proper headers and error handling"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: {response.reason}")
                
                content_type = response.headers.get('content-type') or ''
                if 'text/html' not in content_type.lower():
                    raise Exception(f"Invalid content type: {content_type}")
                
                content = await response.text()
                
                response_info = {
                    'status_code': response.status,
                    'content_type': content_type,
                    'content_length': len(content),
                    'response_headers': dict(response.headers)
                }
                
                return content, response_info
    
    def _extract_metadata(self, soup: BeautifulSoup, parsed_url: Any) -> Dict[str, str]:
        """Extract basic page metadata"""
        metadata = {}
        
        # Title
        title_tag = soup.find('title')
        metadata['title'] = title_tag.get_text(strip=True) if title_tag else ''
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            metadata['description'] = meta_desc.get('content', '')
        
        # Open Graph data
        og_title = soup.find('meta', property='og:title')
        if og_title and not metadata['title']:
            metadata['title'] = og_title.get('content', '')
            
        og_desc = soup.find('meta', property='og:description') 
        if og_desc and not metadata['description']:
            metadata['description'] = og_desc.get('content', '')
        
        return metadata
    
    def _extract_clean_content(self, soup: BeautifulSoup) -> str:
        """Extract and clean main content from page"""
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']):
            element.decompose()
        
        # Try to find main content area
        main_content = None
        
        # Look for main content selectors
        content_selectors = [
            'main', 'article', '[role="main"]', 
            '.content', '.main-content', '.post-content',
            '.entry-content', '.article-content'
        ]
        
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # If no main content found, use body
        if not main_content:
            main_content = soup.find('body')
        
        if not main_content:
            main_content = soup
        
        # Extract text content
        text_content = []
        for element in main_content.find_all(text=True):
            if element.parent.name not in ['script', 'style']:
                text = element.strip()
                if text and len(text) > 10:  # Only meaningful text
                    text_content.append(text)
        
        # Clean and join content
        cleaned = ' '.join(text_content)
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)  # Clean line breaks
        
        return cleaned.strip()
    
    def _analyze_page_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page structure for technical insights"""
        print(f"🔍 SCRAPER DEBUG: Starting _analyze_page_structure")
        
        try:
            print(f"🔍 SCRAPER DEBUG: Extracting headings")
            headings = self._extract_headings(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting CTAs")
            ctas = self._extract_ctas(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting forms")
            forms = self._extract_forms(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting images")
            images = self._extract_images(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting links")
            links = self._extract_links(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting social signals")
            social_signals = self._extract_social_signals(soup)
            
            print(f"🔍 SCRAPER DEBUG: Extracting technical elements")
            technical_elements = self._extract_technical_elements(soup)
        
        structure = {
            'headings': self._extract_headings(soup),
            'ctas': self._extract_ctas(soup), 
            'forms': self._extract_forms(soup),
            'images': self._extract_images(soup),
            'links': self._extract_links(soup),
            'social_signals': self._extract_social_signals(soup),
            'technical_elements': self._extract_technical_elements(soup)
        }
        
        return structure
        
    except Exception as e:
        print(f"🔍 SCRAPER DEBUG: Error in _analyze_page_structure: {e}")
        raise
    
    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract heading structure"""
        headings = []
        for level in range(1, 7):  # h1 to h6
            for heading in soup.find_all(f'h{level}'):
                text = heading.get_text(strip=True)
                if text:
                    headings.append({
                        'level': level,
                        'text': text,
                        'length': len(text)
                    })
        return headings
    
    def _extract_ctas(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract call-to-action elements"""
        ctas = []
        
        # Buttons
        for button in soup.find_all(['button', 'input']):
            if button.name == 'input' and button.get('type') not in ['submit', 'button']:
                continue
                
            text = button.get_text(strip=True) or button.get('value', '')
            if text:
                ctas.append({
                    'type': 'button',
                    'text': text,
                    'element': button.name
                })
        
        # Links that look like CTAs
        cta_patterns = [
            r'sign\s*up', r'get\s*started', r'try\s*(free|now)', r'download',
            r'buy\s*now', r'order\s*now', r'subscribe', r'register',
            r'learn\s*more', r'contact\s*us', r'book\s*demo'
        ]
        
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True).lower()
            classes = ' '.join(link.get('class', [])).lower()
            
            is_cta = any(re.search(pattern, text) for pattern in cta_patterns)
            is_cta = is_cta or any(word in classes for word in ['btn', 'button', 'cta'])
            
            if is_cta and text:
                ctas.append({
                    'type': 'link',
                    'text': text,
                    'href': link['href'],
                    'classes': classes
                })
        
        return ctas
    
    def _extract_forms(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract form information"""
        forms = []
        for form in soup.find_all('form'):
            form_data = {
                'action': form.get('action', ''),
                'method': form.get('method', 'get').upper(),
                'fields': []
            }
            
            for input_field in form.find_all(['input', 'textarea', 'select']):
                field_type = input_field.get('type', input_field.name)
                field_name = input_field.get('name', '')
                placeholder = input_field.get('placeholder', '')
                
                if field_type not in ['hidden', 'submit']:
                    form_data['fields'].append({
                        'type': field_type,
                        'name': field_name,
                        'placeholder': placeholder
                    })
            
            forms.append(form_data)
        
        return forms
    
    def _extract_images(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract image information"""
        images = soup.find_all('img')
        return {
            'total_images': len(images),
            'images_with_alt': len([img for img in images if img.get('alt')]),
            'hero_images': len([img for img in images if 'hero' in ' '.join(img.get('class', []))])
        }
    
    def _extract_links(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract link information"""
        links = soup.find_all('a', href=True)
        external_links = []
        
        for link in links:
            href = link.get('href') or ''
            if href.startswith(('http://', 'https://')) and not href.startswith(soup.base_url if hasattr(soup, 'base_url') else ''):
                external_links.append(href)
        
        return {
            'total_links': len(links),
            'external_links_count': len(set(external_links)),
            'external_domains': list(set([urlparse(url).netloc for url in external_links]))
        }
    
    def _extract_social_signals(self, soup: BeautifulSoup) -> List[str]:
        """Extract social media signals"""
        social_platforms = []
        social_domains = [
            'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
            'youtube.com', 'tiktok.com', 'pinterest.com'
        ]
        
        for link in soup.find_all('a', href=True):
            href = (link.get('href') or '').lower()
            for domain in social_domains:
                if domain in href:
                    platform = domain.split('.')[0]
                    if platform not in social_platforms:
                        social_platforms.append(platform)
        
        return social_platforms
    
    def _extract_technical_elements(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract technical SEO and structure elements"""
        return {
            'has_schema_markup': bool(soup.find_all(['script'], type='application/ld+json')),
            'meta_tags_count': len(soup.find_all('meta')),
            'canonical_url': soup.find('link', rel='canonical').get('href') if soup.find('link', rel='canonical') else None,
            'viewport_meta': bool(soup.find('meta', attrs={'name': 'viewport'})),
            'structured_data_types': self._extract_structured_data(soup)
        }
    
    def _extract_structured_data(self, soup: BeautifulSoup) -> List[str]:
        """Extract structured data types"""
        structured_types = []
        
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and '@type' in data:
                    structured_types.append(data['@type'])
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and '@type' in item:
                            structured_types.append(item['@type'])
            except (json.JSONDecodeError, TypeError):
                continue
        
        return list(set(structured_types))
