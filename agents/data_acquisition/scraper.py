"""
HTML Content Scraper for Data Acquisition Agent
Extracts clean text content from web pages for PDF conversion
"""

import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class ContentScraper:
    """Scrapes and cleans content from HTML pages"""

    def __init__(self):
        """Initialize content scraper"""
        pass

    def scrape_content(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Extract clean content from HTML

        Args:
            html_content: Raw HTML content
            url: Source URL for context

        Returns:
            Dictionary with extracted content and metadata
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Extract title
            title = self._extract_title(soup, url)

            # Extract main content
            main_content = self._extract_main_content(soup)

            # Clean and structure content
            cleaned_content = self._clean_content(main_content)

            # Extract metadata
            metadata = self._extract_metadata(soup, url)

            return {
                'title': title,
                'content': cleaned_content,
                'metadata': metadata,
                'word_count': len(cleaned_content.split()),
                'url': url
            }

        except Exception as e:
            logger.error(f"Failed to scrape content from {url}: {str(e)}")
            return {
                'title': 'Scraping Error',
                'content': f'Error extracting content: {str(e)}',
                'metadata': {'error': str(e)},
                'word_count': 0,
                'url': url
            }

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extract page title"""
        # Try multiple title extraction methods
        title = None

        # Method 1: Standard title tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Method 2: h1 tag if no title
        if not title:
            h1_tag = soup.find('h1')
            if h1_tag:
                title = h1_tag.get_text(strip=True)

        # Method 3: Use URL as fallback
        if not title:
            title = url.split('/')[-1].replace('-', ' ').replace('_', ' ').title()

        return title or "Untitled Document"

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from the page"""
        # Try to find main content areas
        content_selectors = [
            'main',
            'article',
            '.content',
            '.post-content',
            '.entry-content',
            '#content',
            '.main-content',
            'body'  # Fallback to entire body
        ]

        for selector in content_selectors:
            content_area = soup.select_one(selector)
            if content_area:
                return content_area.get_text(separator=' ', strip=True)

        return soup.get_text(separator=' ', strip=True)

    def _clean_content(self, content: str) -> str:
        """Clean and format extracted content"""
        if not content:
            return ""

        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)

        # Remove common noise patterns
        noise_patterns = [
            r'Cookie Policy.*?Accept',
            r'Privacy Policy.*?Accept',
            r'Advertisement.*?Continue',
            r'Subscribe to.*?Newsletter',
            r'Loading.*?Please wait',
            r'Error.*?retry',
        ]

        for pattern in noise_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)

        # Clean up common formatting issues
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Multiple newlines
        content = re.sub(r'^\s+', '', content, flags=re.MULTILINE)  # Leading spaces

        return content.strip()

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract metadata from the page"""
        metadata = {
            'url': url,
            'description': '',
            'author': '',
            'date': '',
            'tags': []
        }

        # Extract description
        desc_tag = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
        if desc_tag and desc_tag.get('content'):
            metadata['description'] = desc_tag['content'][:200]  # Limit length

        # Extract author
        author_tag = soup.find('meta', {'name': 'author'}) or soup.find('meta', {'property': 'article:author'})
        if author_tag and author_tag.get('content'):
            metadata['author'] = author_tag['content']

        # Extract publish date
        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="publishdate"]',
            'time[datetime]',
            '.published',
            '.date'
        ]

        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                if date_elem.get('datetime'):
                    metadata['date'] = date_elem['datetime']
                elif date_elem.get('content'):
                    metadata['date'] = date_elem['content']
                elif date_elem.get_text(strip=True):
                    metadata['date'] = date_elem.get_text(strip=True)
                break

        return metadata

    def is_study_material(self, content: Dict[str, Any], min_word_count: int = 100) -> bool:
        """
        Determine if scraped content is likely study material

        Args:
            content: Scraped content dictionary
            min_word_count: Minimum word count threshold

        Returns:
            True if content appears to be study material
        """
        word_count = content.get('word_count', 0)

        # Check word count
        if word_count < min_word_count:
            return False

        # Check for study-related keywords in title or content
        study_keywords = [
            'upsc', 'ias', 'study', 'notes', 'material', 'geography',
            'prelims', 'mains', 'civil services', 'competitive exam'
        ]

        title = content.get('title', '').lower()
        content_preview = content.get('content', '')[:500].lower()

        keyword_matches = sum(1 for keyword in study_keywords if keyword in title or keyword in content_preview)

        return keyword_matches >= 1
