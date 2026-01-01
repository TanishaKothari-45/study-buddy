"""
Dimension-based Content Scraper

Scrapes full article content for filtered articles.
Reuses existing newspaper3k infrastructure.
"""

import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Import existing content extractor
try:
    from mcp_current_affairs.fetcher.content_extractor import (
        ensure_content,
        extract_content,
        get_article_text,
    )
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    logger.warning("Could not import content_extractor from mcp_current_affairs")


# ============================================================================
# Configuration
# ============================================================================

MIN_CONTENT_LENGTH = 200    # Minimum chars before scraping needed
MAX_CONTENT_LENGTH = 2500   # Truncate scraped content to this


# ============================================================================
# Main Scraper Function
# ============================================================================

async def scrape_articles_content(
    articles: List[Dict[str, Any]],
    min_length: int = MIN_CONTENT_LENGTH,
    max_scrape_per_dimension: int = 3,
    concurrent_limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Scrape full content for articles that need it.
    
    Args:
        articles: List of articles with dimension metadata
        min_length: Minimum content length before scraping (default: 200)
        max_scrape_per_dimension: Max articles to scrape per dimension (default: 3)
        concurrent_limit: Max concurrent scrape requests (default: 5)
    
    Returns:
        Articles with full content populated
    """
    if not SCRAPER_AVAILABLE:
        logger.error("Scraper not available")
        return articles
    
    if not articles:
        return []
    
    # Group by dimension to apply per-dimension limits
    by_dimension: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        dim = article.get("_dimension", "Unknown")
        if dim not in by_dimension:
            by_dimension[dim] = []
        by_dimension[dim].append(article)
    
    # Identify articles needing scraping
    to_scrape = []
    for dim_name, dim_articles in by_dimension.items():
        # Sort by similarity score (highest first)
        sorted_articles = sorted(
            dim_articles,
            key=lambda x: x.get("_similarity_score", 0),
            reverse=True
        )
        
        # Check each article, add to scrape list if needed
        dim_scraped = 0
        for article in sorted_articles:
            content = article.get("content") or article.get("description") or ""
            
            if len(content) >= min_length:
                continue  # Already has content
            
            if dim_scraped >= max_scrape_per_dimension:
                continue  # Hit limit for this dimension
            
            url = article.get("url")
            if not url:
                continue
            
            to_scrape.append(article)
            dim_scraped += 1
    
    if not to_scrape:
        logger.info("📄 All articles already have sufficient content")
        return articles
    
    logger.info(f"📰 Scraping content for {len(to_scrape)} articles...")
    
    # Scrape with concurrency control
    semaphore = asyncio.Semaphore(concurrent_limit)
    
    async def scrape_one(article: Dict[str, Any]):
        async with semaphore:
            url = article.get("url")
            try:
                content = await extract_content(url)
                if content:
                    # Truncate if too long
                    article["content"] = content[:MAX_CONTENT_LENGTH]
                    article["_content_scraped"] = True
                    logger.debug(f"   ✓ Scraped: {url[:50]}...")
                else:
                    article["_content_scraped"] = False
            except Exception as e:
                logger.warning(f"   ✗ Failed: {url[:40]}... - {e}")
                article["_content_scraped"] = False
    
    # Run all scrapes
    await asyncio.gather(*[scrape_one(a) for a in to_scrape])
    
    # Count results
    scraped_count = sum(1 for a in articles if a.get("_content_scraped"))
    logger.info(f"✅ Scraped {scraped_count} articles successfully")
    
    return articles


# ============================================================================
# Utility Functions
# ============================================================================

def get_best_content(article: Dict[str, Any]) -> str:
    """
    Get best available content from article.
    Priority: content > description > title
    
    Args:
        article: Article dict
    
    Returns:
        Best available text content
    """
    return (
        article.get("content") or
        article.get("description") or
        article.get("title") or
        ""
    )


def filter_by_content_length(
    articles: List[Dict[str, Any]],
    min_length: int = MIN_CONTENT_LENGTH
) -> List[Dict[str, Any]]:
    """
    Filter to only articles with sufficient content.
    
    Args:
        articles: List of articles
        min_length: Minimum content length
    
    Returns:
        Filtered list
    """
    filtered = []
    for article in articles:
        content = get_best_content(article)
        if len(content) >= min_length:
            filtered.append(article)
    
    logger.info(f"📝 Content filter: {len(articles)} → {len(filtered)} articles")
    return filtered
