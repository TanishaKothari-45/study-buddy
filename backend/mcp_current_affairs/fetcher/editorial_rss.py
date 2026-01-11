# fetcher/editorial_rss.py
"""
Editorial RSS fetcher with bucket-based source diversification.
Supports India/Global region detection and title deduplication.
"""

import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from ..config import (
    RSS_BUCKETS, RSS_PER_FEED, EDITORIAL_TIME_WINDOW_DAYS, MIN_CONTENT_LENGTH
)
from .utils import normalize_url


def detect_region_from_keywords(keywords: List[str]) -> str:
    """
    Detect region from keywords.
    If 'india' or 'India' in keywords -> 'india'
    Else -> 'global'
    """
    if not keywords:
        return "global"
    
    kws_lower = [k.lower() for k in keywords]
    
    # Check for India-related keywords
    for kw in kws_lower:
        if "india" in kw:
            return "india"
    
    return "global"


def choose_feeds_for_topic(keywords: List[str], topic_region: Optional[str] = None) -> List[str]:
    """
    Return feed URLs based on region detection.
    
    Args:
        keywords: Topic keywords
        topic_region: Optional explicit region override
    
    Returns:
        List of feed URLs to query
    """
    region = topic_region or detect_region_from_keywords(keywords)
    
    feeds = []
    if region == "india":
        feeds += RSS_BUCKETS.get("india_opinion", [])
        feeds += RSS_BUCKETS.get("policy_journals", [])
    else:  # global or general
        feeds += RSS_BUCKETS.get("global_opinion", [])
        feeds += RSS_BUCKETS.get("policy_journals", [])
        # Also include India for broader coverage
        feeds += RSS_BUCKETS.get("india_opinion", [])
    
    # Dedupe while preserving order
    seen = set()
    chosen = []
    for f in feeds:
        if f not in seen:
            seen.add(f)
            chosen.append(f)
    
    return chosen


def title_similarity(title1: str, title2: str) -> float:
    """
    Simple Jaccard similarity on normalized tokens.
    Used to detect duplicate editorials across feeds.
    """
    if not title1 or not title2:
        return 0.0
    
    # Normalize and tokenize
    tokens1 = set(title1.lower().split())
    tokens2 = set(title2.lower().split())
    
    # Remove common stopwords
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "for", "on", "with", "at", "by"}
    tokens1 = tokens1 - stopwords
    tokens2 = tokens2 - stopwords
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)


def dedupe_by_title(editorials: List[Dict[str, Any]], threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    Remove editorials with similar titles (Jaccard > threshold).
    Keeps the first occurrence.
    """
    if not editorials:
        return []
    
    deduped = []
    
    for editorial in editorials:
        title = editorial.get("title", "")
        is_duplicate = False
        
        for existing in deduped:
            if title_similarity(title, existing.get("title", "")) > threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            deduped.append(editorial)
    
    return deduped


def fetch_rss_editorials_for_topic(
    keywords: List[str], 
    topic_region: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch editorials from RSS feeds based on topic region.
    
    Args:
        keywords: Topic keywords for region detection
        topic_region: Optional explicit region override
    
    Returns:
        List of editorial dicts with source, title, description, url, published_at, content
    """
    feeds = choose_feeds_for_topic(keywords, topic_region)
    cutoff = datetime.utcnow() - timedelta(days=EDITORIAL_TIME_WINDOW_DAYS)
    results = []
    
    print(f"📡 Fetching from {len(feeds)} RSS feeds (region: {topic_region or detect_region_from_keywords(keywords)})")
    
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url, agent='StudyBuddy/1.0')
        except Exception as e:
            print(f"⚠️ Failed to parse {feed_url}: {e}")
            continue
        
        source_name = feed.feed.get("title", feed_url)
        
        # Take top N items per feed
        for entry in (feed.entries or [])[:RSS_PER_FEED]:
            # Parse published date
            published = None
            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
            except Exception:
                pass
            
            # Skip if too old
            if published and published < cutoff:
                continue
            
            # Get content - some feeds include full content
            content = ""
            if hasattr(entry, "content") and entry.content:
                # Some feeds have content as list
                if isinstance(entry.content, list):
                    content = entry.content[0].get("value", "")
                else:
                    content = str(entry.content)
            
            # Fallback to summary/description
            description = entry.get("summary", "") or entry.get("description", "")
            if not content:
                content = description
            
            # Check if we have enough content
            has_full_content = len(content) >= MIN_CONTENT_LENGTH
            
            item = {
                "source": source_name,
                "title": entry.get("title", ""),
                "description": description[:500] if description else "",
                "content": content,
                "url": normalize_url(entry.get("link", "")),
                "published_at": published.isoformat() if published else None,
                "has_full_content": has_full_content,
                "type": "editorial"
            }
            results.append(item)
    
    print(f"   Fetched {len(results)} raw editorials")
    
    # Dedupe by URL first
    seen_urls = set()
    url_deduped = []
    for item in results:
        url = item.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            url_deduped.append(item)
    
    # Then dedupe by title similarity
    deduped = dedupe_by_title(url_deduped)
    print(f"   After dedupe: {len(deduped)} editorials")
    
    return deduped


# Legacy function for backward compatibility
def fetch_editorial_rss() -> List[Dict[str, Any]]:
    """Legacy function - fetches from all feeds without region filtering."""
    return fetch_rss_editorials_for_topic(keywords=[], topic_region=None)
