# mcp_current_affairs_server.py
"""
MCP Current Affairs Server
Provides intelligent current affairs fetching with LLM summarization.

OPTIMIZED FLOW (Articles Only):
1. Extract keywords from topic (LLM)
2. Build 4 diversified queries
3. Fetch candidates (10 per query = 40 total)
4. **NEW: Cheap keyword pre-filter** (reject before scraping)
5. **NEW: Enhanced deduplication** (URL + title similarity)
6. **NEW: Smart top-8 selection** (recency, keywords, content, diversity)
7. Scrape top 8 for full content
8. **NEW: Batch compute embeddings** (1 API call for all)
9. Filter by relevance threshold
10. Apply time filter with fallback
11. Select best 3-4 articles (1 per query with fallback)
12. Summarize articles (batch LLM call)
13. Output JSON
"""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .fetcher.news_fetcher import fetch_articles_for_query
from .fetcher.utils import (
    dedupe_articles, within_time_window, 
    cheap_keyword_match, calculate_title_similarity,
    select_top_candidates, normalize_url
)
from .fetcher.content_extractor import ensure_content, get_article_text
from .llm.keyword_parser import get_keywords, build_search_queries
from .processing.classifier import detect_type, topic_score, mark_corroboration, set_topic_keywords
from .processing.relevance_filter import compute_relevance_scores, filter_by_relevance
from .processing.summary_builder import extract_lead
from .llm.summarizer import summarize_articles_only
from .processing.cache import get_cached_summary, set_cached_summary
from .config import (
    SUMMARY_CACHE_TTL, RELEVANCE_THRESHOLD,
    MAX_CANDIDATES_FOR_SCORING, MIN_CONTENT_LENGTH,
    FINAL_ARTICLE_COUNT, KEYWORD_MATCH_MIN_COUNT,
    URL_SIMILARITY_THRESHOLD
)

# Import new dimension pipeline
try:
    from app.utils.dimension_current_affairs.pipeline import fetch_dimension_current_affairs_structured
except ImportError:
    # Fallback for different path structures
    import sys
    from pathlib import Path
    backend_root = Path(__file__).resolve().parent.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.utils.dimension_current_affairs.pipeline import fetch_dimension_current_affairs_structured

# Initialize MCP server
server = Server("current-affairs-mcp")


@server.list_tools()
async def list_tools():
    """List available MCP tools."""
    return [
        Tool(
            name="fetch_diversified_current_affairs",
            description="Fetch diversified current affairs articles with intelligent summarization for UPSC preparation. Returns 3-4 factual articles (one per query angle) with optimized filtering and batch processing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic or question for current affairs (e.g., 'climate change policies', 'India-US relations')"
                    }
                },
                "required": ["topic"]
            }
        ),
        Tool(
            name="fetch_dimension_current_affairs",
            description="Fetch deep, high-quality current affairs using dimension-based planning. Best for UPSC Mains answer enrichment. Breaks topic into 5-7 dimensions and fetches targeted evidence for each.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The UPSC question or topic to research"
                    }
                },
                "required": ["topic"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    if name == "fetch_diversified_current_affairs":
        topic = arguments.get("topic", "")
        if not topic:
            return [TextContent(type="text", text="Error: topic is required")]
        
        keywords = arguments.get("keywords")  # Optional pre-parsed keywords
        result = await fetch_diversified_current_affairs(topic, keywords=keywords)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    if name == "fetch_dimension_current_affairs":
        topic = arguments.get("topic", "")
        if not topic:
            return [TextContent(type="text", text="Error: topic is required")]
        
        result = await fetch_dimension_current_affairs_structured(topic)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    raise ValueError(f"Unknown tool: {name}")


async def fetch_diversified_current_affairs(topic: str, keywords: list = None, api_key: str = None) -> dict:
    """
    Main function: Fetch diversified current affairs with intelligent summarization.
    OPTIMIZED: No editorials, early filtering, batch embeddings, smart selection.
    
    Args:
        topic: Topic or question for current affairs
        keywords: Optional pre-parsed keywords (skips LLM extraction if provided)
    """
    print(f"\n🔍 Processing topic: {topic}")
    
    # Step 1: Check cache first
    cache_key = f"summary:{topic.lower().strip()}"
    cached = await asyncio.to_thread(get_cached_summary, cache_key)
    if cached:
        print("📦 Returning cached result")
        return cached

    # Step 2: Extract keywords (or use provided)
    if keywords:
        print(f"🎯 Using pre-parsed keywords: {keywords}")
    else:
        print("🔑 Extracting keywords...")
        keywords = await get_keywords(topic)
    
    set_topic_keywords(keywords)
    print(f"   Keywords: {keywords}")

    # Step 3: Build 4 diversified queries
    queries = build_search_queries(keywords, topic)
    print(f"📝 Queries: {queries}")

    # Step 4: Fetch candidates (parallel)
    print("📰 Fetching articles...")
    tasks = [fetch_articles_for_query(q) for q in queries]
    results = await asyncio.gather(*tasks)
    
    # Track which query each article came from
    all_articles = []
    for i, (query, batch) in enumerate(zip(queries, results)):
        for article in batch:
            article["_query_index"] = i
            article["_query"] = query
            all_articles.append(article)
    
    print(f"   Fetched: {len(all_articles)} candidates")

    # Step 5: EARLY KEYWORD PRE-FILTER (cheap substring matching)
    print("🎯 Early keyword filtering...")
    keyword_matched = []
    for article in all_articles:
        has_match, match_count = cheap_keyword_match(article, keywords)
        if has_match and match_count >= KEYWORD_MATCH_MIN_COUNT:
            article["_keyword_matches"] = match_count
            keyword_matched.append(article)
    
    print(f"   Keyword matched: {len(keyword_matched)}/{len(all_articles)}")
    
    if not keyword_matched:
        print("   ⚠️ No articles matched keywords. Returning empty result.")
        return {
            "current_affairs": [],
            "metadata": {
                "keywords": keywords,
                "message": "No relevant articles found matching topic keywords"
            }
        }

    # Step 6: ENHANCED DEDUPLICATION (URL normalization + title similarity)
    print("🔗 Enhanced deduplication...")
    seen_urls = set()
    seen_titles = []
    deduped = []
    
    for article in keyword_matched:
        # Check URL
        url = normalize_url(article.get("url", ""))
        if url and url in seen_urls:
            continue
        
        # Check title similarity
        title = article.get("title", "").strip()
        is_duplicate = False
        if title:
            for seen_title in seen_titles:
                similarity = calculate_title_similarity(title, seen_title)
                if similarity >= URL_SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            if url:
                seen_urls.add(url)
            if title:
                seen_titles.append(title)
            deduped.append(article)
    
    print(f"   After dedupe: {len(deduped)}")

    # Step 7: SMART TOP-8 SELECTION (recency + keywords + content + diversity)
    print("⭐ Selecting top candidates...")
    top_candidates = select_top_candidates(deduped, keywords, max_candidates=MAX_CANDIDATES_FOR_SCORING)
    # Keep only top 5 to reduce scraping/summary load; if keyword matches were 0, allow up to 3 fallback items
    top_candidates = top_candidates[:5]
    print(f"   Selected top {len(top_candidates)} for scraping")
    
    if not top_candidates:
        print("   ⚠️ No candidates selected. Returning empty result.")
        return {
            "current_affairs": [],
            "metadata": {
                "keywords": keywords,
                "message": "No quality candidates found after selection"
            }
        }

    # Step 8: Scrape for full content
    print("📄 Ensuring content...")
    top_candidates = await ensure_content(
        top_candidates, 
        min_length=MIN_CONTENT_LENGTH,
        max_to_scrape=5
    )

    # Step 9: Drop articles without usable content (post-scrape)
    content_ready = []
    for a in top_candidates:
        text = get_article_text(a)
        if text and len(text) >= MIN_CONTENT_LENGTH:
            content_ready.append(a)
    print(f"   After content filter: {len(content_ready)}")

    if not content_ready:
        print("   ⚠️ No articles with sufficient content. Returning empty result.")
        return {
            "current_affairs": [],
            "metadata": {
                "keywords": keywords,
                "message": "No articles with sufficient content after scraping"
            }
        }

    # Step 10: Apply time filter (keep recent first, then backfill)
    time_filtered = []
    older = []
    for a in content_ready:
        pub_date = a.get("published_at")
        if pub_date and within_time_window(pub_date):
            time_filtered.append(a)
        else:
            older.append(a)
    if len(time_filtered) < 3 and older:
        need = 3 - len(time_filtered)
        time_filtered.extend(older[:need])
    print(f"   After time filter (with fallback): {len(time_filtered)}")

    # Step 11: Classify articles
    for a in time_filtered:
        a["type"] = detect_type(a)
        a["topic_score"] = topic_score(a)
    time_filtered = mark_corroboration(time_filtered)

    # Step 12: Select best articles (1 per query with fallback)
    articles_only = [a for a in time_filtered if a["type"] == "article"]
    final_articles = select_articles_with_fallback(articles_only, num_queries=4)
    
    print(f"   ✅ Selected: {len(final_articles)} articles")

    # Handle empty results
    if not final_articles:
        return {
            "current_affairs": [],
            "metadata": {
                "keywords": keywords,
                "message": "No final articles selected despite finding candidates"
            }
        }

    # Step 13: Prepare extracts for summarization
    article_leads = [get_article_text(a)[:500] for a in final_articles]

    # Step 14: Summarize (batch LLM call - articles only)
    print("✍️ Generating summaries...")
    article_summaries = await asyncio.to_thread(
        summarize_articles_only,
        article_leads,
        api_key
    )

    # Step 15: Build output JSON (articles only, no editorial)
    out = {"current_affairs": []}

    for a, summary in zip(final_articles, article_summaries):
        out["current_affairs"].append({
            "type": "article",
            "summary": summary.strip(),
            "source": a.get("source"),
            "url": a.get("url"),
            "published_at": a.get("published_at"),
            "corroborated": a.get("corroborated", False),
            "relevance_score": a.get("relevance_score", 0)
        })

    out["metadata"] = {
        "keywords": keywords,
        "queries_used": queries,
        "candidates_fetched": len(all_articles),
        "keyword_matched": len(keyword_matched),
        "after_dedup": len(deduped),
        "top_selected": len(top_candidates),
        "relevant_found": len(content_ready),
        "final_count": len(final_articles)
    }

    # Step 17: Cache result
    await asyncio.to_thread(set_cached_summary, cache_key, out)
    print("✅ Done!")

    return out


def select_articles_with_fallback(articles: list, num_queries: int = 4) -> list:
    """
    Select best articles: try 1 per query, fallback to top 3 overall.
    
    Args:
        articles: List of articles with _query_index (pre-filtered to type=article)
        num_queries: Number of queries (4)
    
    Returns:
        Up to 4 articles
    """
    if not articles:
        return []
    
    # Group by query index
    by_query = {i: [] for i in range(num_queries)}
    for a in articles:
        idx = a.get("_query_index", 0)
        if idx < num_queries:
            by_query[idx].append(a)
    
    # Try to select best from each query
    selected = []
    selected_urls = set()
    
    for i in range(num_queries):
        candidates = by_query[i]
        if not candidates:
            continue
        
        # Sort by (corroborated, relevance_score, topic_score)
        candidates.sort(
            key=lambda x: (
                x.get("corroborated", False),
                x.get("relevance_score", 0),
                x.get("topic_score", 0)
            ),
            reverse=True
        )
        
        # Take best article from this query (avoid duplicates)
        for candidate in candidates:
            url = candidate.get("url")
            if url and url not in selected_urls:
                selected.append(candidate)
                selected_urls.add(url)
                break
    
    # Fallback: if < 3 selected, fill with top overall by relevance
    if len(selected) < 3:
        print(f"   Fallback: only {len(selected)} per-query, filling to 3...")
        all_sorted = sorted(
            articles,
            key=lambda x: x.get("relevance_score", 0),
            reverse=True
        )
        for a in all_sorted:
            if len(selected) >= 3:
                break
            url = a.get("url")
            if url and url not in selected_urls:
                selected.append(a)
                selected_urls.add(url)
    
    return selected[:FINAL_ARTICLE_COUNT]


async def main():
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
