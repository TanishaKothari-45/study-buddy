# fetcher/content_extractor.py
"""
Lazy content extraction for articles with short snippets.
Uses newspaper3k to scrape full article text when needed.
"""

import asyncio
from typing import List, Dict, Any, Optional

# Lazy-loaded newspaper
_newspaper_available = None


def _check_newspaper():
    """Check if newspaper3k is available."""
    global _newspaper_available
    if _newspaper_available is None:
        try:
            from newspaper import Article, Config
            _newspaper_available = True
        except ImportError:
            print("⚠️ newspaper3k not installed. Run: pip install newspaper3k")
            _newspaper_available = False
    return _newspaper_available


def extract_content_sync(url: str, timeout: int = 10) -> Optional[str]:
    """
    Synchronously extract full article content from URL.
    
    Args:
        url: Article URL
        timeout: Request timeout in seconds
    
    Returns:
        Extracted text or None if failed
    """
    if not _check_newspaper():
        return None
    
    try:
        from newspaper import Article, Config
        
        config = Config()
        config.request_timeout = timeout
        config.browser_user_agent = 'Mozilla/5.0 (compatible; StudyBuddy/1.0)'
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        text = article.text
        if text and len(text) > 100:
            return text[:3000]  # Limit to 3000 chars
        return None
        
    except Exception as e:
        print(f"⚠️ Content extraction failed for {url}: {e}")
        return None


async def extract_content(url: str) -> Optional[str]:
    """Async wrapper for content extraction."""
    return await asyncio.to_thread(extract_content_sync, url)


async def ensure_content(
    articles: List[Dict[str, Any]], 
    min_length: int = 200,
    max_to_scrape: int = 10
) -> List[Dict[str, Any]]:
    """
    Ensure articles have sufficient content, scraping if needed.
    
    Args:
        articles: List of article dicts
        min_length: Minimum content length before scraping
        max_to_scrape: Only scrape top N articles (lazy)
    
    Returns:
        Articles with content field populated
    """
    scraped_count = 0
    
    for article in articles:
        content = article.get("content") or article.get("description") or ""
        
        # Check if content is sufficient
        if len(content) >= min_length:
            continue
        
        # Only scrape top N candidates
        if scraped_count >= max_to_scrape:
            continue
        
        url = article.get("url")
        if not url:
            continue
        
        print(f"📰 Scraping content from: {url[:60]}...")
        extracted = await extract_content(url)
        
        if extracted:
            article["content"] = extracted
            article["content_scraped"] = True
            scraped_count += 1
    
    return articles


def get_article_text(article: Dict[str, Any]) -> str:
    """
    Get the best available text from an article.
    Priority: content > description > title
    """
    return (
        article.get("content") or 
        article.get("description") or 
        article.get("title") or 
        ""
    )
