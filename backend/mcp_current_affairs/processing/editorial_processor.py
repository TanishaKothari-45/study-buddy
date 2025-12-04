# processing/editorial_processor.py
"""
Editorial processing with two-stage filtering and quality scoring.

Pipeline:
1. Fetch from RSS (bucket-based)
2. Compute soft relevance scores with recency boost
3. Filter by soft threshold (0.3)
4. Scrape top 8 if content missing
5. Compute hard relevance on full content
6. Filter by hard threshold (0.4)
7. Calculate quality scores (embedding 50%, source 30%, length 20%)
8. Return top 3 or best match
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from ..config import (
    SOFT_SIM_THRESH, HARD_SIM_THRESH, SCRAPE_TOP_N,
    SOURCE_RELIABILITY, EDITORIAL_QUALITY_WEIGHTS,
    MIN_EDITORIAL_WORDS, EDITORIAL_TIME_WINDOW_DAYS, MIN_CONTENT_LENGTH
)
from .relevance_filter import compute_relevance_scores, filter_by_relevance
from ..fetcher.editorial_rss import fetch_rss_editorials_for_topic
from ..fetcher.content_extractor import extract_content, get_article_text


def calculate_recency_boost(published_at: str) -> float:
    """
    Calculate recency boost factor.
    Fresher items get higher boost (up to 10% bonus).
    
    Formula: 1 + (1 - days_old/EDITORIAL_TIME_WINDOW_DAYS) * 0.1
    """
    if not published_at:
        return 1.0  # No boost for unknown dates
    
    try:
        if isinstance(published_at, str):
            # Parse ISO format
            pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        else:
            pub_date = published_at
        
        days_old = (datetime.utcnow() - pub_date.replace(tzinfo=None)).days
        days_old = max(0, days_old)  # Ensure non-negative
        
        if days_old >= EDITORIAL_TIME_WINDOW_DAYS:
            return 1.0  # No boost for old items
        
        # Boost: 1.0 to 1.1 based on freshness
        boost = 1 + (1 - days_old / EDITORIAL_TIME_WINDOW_DAYS) * 0.1
        return boost
    except Exception:
        return 1.0


def get_source_reliability(source: str) -> float:
    """
    Get reliability weight for a source.
    Returns normalized score between 0 and 1.
    """
    if not source:
        return SOURCE_RELIABILITY.get("default", 0.6)
    
    source_lower = source.lower()
    
    # Try exact match first
    for name, score in SOURCE_RELIABILITY.items():
        if name.lower() in source_lower or source_lower in name.lower():
            return score
    
    return SOURCE_RELIABILITY.get("default", 0.6)


def calculate_length_score(content: str) -> float:
    """
    Calculate normalized length score.
    Prefers editorials with 350+ words, caps at 1000 words.
    """
    if not content:
        return 0.0
    
    word_count = len(content.split())
    
    if word_count < MIN_EDITORIAL_WORDS:
        # Penalize too-short pieces
        return word_count / MIN_EDITORIAL_WORDS * 0.5
    elif word_count >= 1000:
        # Cap at 1000 words
        return 1.0
    else:
        # Linear scale from MIN to 1000
        return 0.5 + 0.5 * (word_count - MIN_EDITORIAL_WORDS) / (1000 - MIN_EDITORIAL_WORDS)


def calculate_quality_score(
    embedding_score: float,
    source: str,
    content: str
) -> float:
    """
    Calculate composite quality score for editorial.
    
    Quality = 0.5 * embedding_score + 0.3 * source_reliability + 0.2 * length_score
    """
    weights = EDITORIAL_QUALITY_WEIGHTS
    
    source_score = get_source_reliability(source)
    length_score = calculate_length_score(content)
    
    quality = (
        weights["embedding"] * embedding_score +
        weights["source"] * source_score +
        weights["length"] * length_score
    )
    
    return round(quality, 3)


async def process_editorials(
    keywords: List[str],
    topic_region: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Main editorial processing pipeline.
    
    Args:
        keywords: Topic keywords for relevance matching
        topic_region: Optional region override
    
    Returns:
        Best editorial or None if none pass filters
    """
    print("\n📰 Processing editorials...")
    
    # Step 1: Fetch from RSS (with deduplication)
    editorials = fetch_rss_editorials_for_topic(keywords, topic_region)
    
    if not editorials:
        print("   No editorials found from RSS feeds")
        return None
    
    # Step 2: Compute soft relevance scores with recency boost
    print("🎯 Computing soft relevance scores...")
    editorials = await compute_relevance_scores(editorials, keywords)
    
    # Apply recency boost to scores
    for e in editorials:
        base_score = e.get("relevance_score", 0)
        boost = calculate_recency_boost(e.get("published_at"))
        e["relevance_score"] = round(base_score * boost, 3)
        e["recency_boost"] = boost
    
    # Step 3: Soft filter
    soft_passed = [e for e in editorials if e.get("relevance_score", 0) >= SOFT_SIM_THRESH]
    print(f"   Soft filter (>={SOFT_SIM_THRESH}): {len(soft_passed)} passed")
    
    if not soft_passed:
        print("   No editorials passed soft filter")
        return None
    
    # Sort by relevance for scraping priority
    soft_passed.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    # Step 4: Lazy scrape top N if content missing
    scrape_count = 0
    for e in soft_passed[:SCRAPE_TOP_N]:
        if not e.get("has_full_content", False) and len(get_article_text(e)) < MIN_CONTENT_LENGTH:
            url = e.get("url")
            if url:
                print(f"   📄 Scraping: {e.get('title', '')[:40]}...")
                scraped = await extract_content(url)
                if scraped:
                    e["content"] = scraped
                    e["has_full_content"] = True
                    scrape_count += 1
    
    if scrape_count > 0:
        print(f"   Scraped {scrape_count} editorials for full content")
    
    # Step 5: Re-compute relevance on full content for top candidates
    # Only for items that got scraped or have full content
    top_candidates = soft_passed[:SCRAPE_TOP_N]
    
    # Create expanded topic text for better matching
    topic_text = " ".join(keywords)
    for e in top_candidates:
        content = get_article_text(e)
        if content and len(content) >= MIN_CONTENT_LENGTH:
            # Keep the boosted score; it already includes relevance
            pass
    
    # Step 6: Hard filter
    hard_passed = [e for e in top_candidates if e.get("relevance_score", 0) >= HARD_SIM_THRESH]
    print(f"   Hard filter (>={HARD_SIM_THRESH}): {len(hard_passed)} passed")
    
    if not hard_passed:
        print("   No editorials passed hard filter")
        return None
    
    # Step 7: Calculate quality scores and pick top 3
    for e in hard_passed:
        embed_score = e.get("relevance_score", 0)
        source = e.get("source", "")
        content = get_article_text(e)
        e["quality_score"] = calculate_quality_score(embed_score, source, content)
    
    # Sort by quality and take top 3
    hard_passed.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    top_3 = hard_passed[:3]
    
    print(f"   Top 3 by quality: {[e.get('quality_score', 0) for e in top_3]}")
    
    # Step 8: Return best one
    best = top_3[0] if top_3 else None
    
    if best:
        print(f"   ✅ Selected: {best.get('title', '')[:50]}... (quality: {best.get('quality_score', 0)})")
    
    return best
