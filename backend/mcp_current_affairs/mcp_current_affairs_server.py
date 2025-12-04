# mcp_current_affairs_server.py
"""
MCP Current Affairs Server
Provides intelligent current affairs fetching with LLM summarization.

Flow:
1. Extract keywords from topic (LLM)
2. Build 4 diversified queries
3. Fetch candidates (10 per query)
4. Dedupe by URL
5. Ensure content (lazy scrape if needed)
6. Compute relevance scores (embeddings)
7. Filter by relevance threshold
8. Apply time filter (90 days)
9. Select 1 article per query + 1 editorial
10. Summarize batch (LLM)
11. Output JSON
"""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .fetcher.news_fetcher import fetch_articles_for_query
from .fetcher.utils import dedupe_articles, within_time_window
from .fetcher.content_extractor import ensure_content, get_article_text
from .llm.keyword_parser import get_keywords, build_search_queries
from .processing.classifier import detect_type, topic_score, mark_corroboration, set_topic_keywords
from .processing.relevance_filter import compute_relevance_scores, filter_by_relevance
from .processing.editorial_processor import process_editorials
from .processing.summary_builder import extract_lead, extract_editorial_snippet
from .llm.summarizer import summarize_articles_and_editorial_sync
from .processing.cache import get_cached_summary, set_cached_summary
from .config import (
    SUMMARY_CACHE_TTL, RELEVANCE_THRESHOLD,
    TOP_CANDIDATES_FOR_SCRAPING, MIN_CONTENT_LENGTH,
    FINAL_ARTICLE_COUNT
)

# Initialize MCP server
server = Server("current-affairs-mcp")


@server.list_tools()
async def list_tools():
    """List available MCP tools."""
    return [
        Tool(
            name="fetch_diversified_current_affairs",
            description="Fetch diversified current affairs with intelligent summarization for UPSC preparation. Returns 4 factual articles (one per query angle) and 1 editorial with detailed analysis.",
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
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    if name == "fetch_diversified_current_affairs":
        topic = arguments.get("topic", "")
        if not topic:
            return [TextContent(type="text", text="Error: topic is required")]
        
        result = await fetch_diversified_current_affairs(topic)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    raise ValueError(f"Unknown tool: {name}")


async def fetch_diversified_current_affairs(topic: str) -> dict:
    """
    Main function: Fetch diversified current affairs with intelligent summarization.
    """
    print(f"\n🔍 Processing topic: {topic}")
    
    # Step 1: Check cache first
    cache_key = f"summary:{topic.lower().strip()}"
    cached = await asyncio.to_thread(get_cached_summary, cache_key)
    if cached:
        print("📦 Returning cached result")
        return cached

    # Step 2: Extract keywords
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

    # Step 5: Dedupe by URL
    articles = dedupe_articles(all_articles)
    print(f"   After dedupe: {len(articles)}")

    # Step 6: Ensure content (lazy scrape top N)
    print("📄 Ensuring content...")
    articles = await ensure_content(
        articles, 
        min_length=MIN_CONTENT_LENGTH,
        max_to_scrape=TOP_CANDIDATES_FOR_SCRAPING
    )

    # Step 7: Compute relevance scores
    print("🎯 Computing relevance scores...")
    articles = await compute_relevance_scores(articles, keywords)
    
    # Step 8: Filter by relevance
    relevant_articles = filter_by_relevance(articles, threshold=RELEVANCE_THRESHOLD)
    print(f"   Relevant (>={RELEVANCE_THRESHOLD}): {len(relevant_articles)}")

    # Step 9: Apply time filter with fallback for high relevance
    time_filtered = []
    old_high_relevance = []
    
    for a in relevant_articles:
        pub_date = a.get("published_at")
        if pub_date and within_time_window(pub_date):
            time_filtered.append(a)
        elif a.get("relevance_score", 0) > 0.5:
            old_high_relevance.append(a)
            
    # If we have fewer than 3 recent articles, fill up with old high-relevance ones
    if len(time_filtered) < 3:
        needed = 3 - len(time_filtered)
        if old_high_relevance:
            print(f"   Only {len(time_filtered)} recent articles. Filling with up to {needed} old high-relevance (>0.5) articles.")
            # Sort old ones by relevance just in case
            old_high_relevance.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            time_filtered.extend(old_high_relevance[:needed])
        
    print(f"   After time filter (with fallback): {len(time_filtered)}")

    # Step 10: Classify articles
    for a in time_filtered:
        a["type"] = detect_type(a)
        a["topic_score"] = topic_score(a)
    time_filtered = mark_corroboration(time_filtered)

    # Step 11: Select best articles (1 per query with fallback)
    articles_only = [a for a in time_filtered if a["type"] == "article"]
    final_articles = select_articles_with_fallback(articles_only, num_queries=4)
    
    # Step 12: Process editorials using the new pipeline
    print("\n📰 Processing editorials with quality scoring...")
    final_editorial = await process_editorials(keywords)
    
    print(f"   Selected: {len(final_articles)} articles, {1 if final_editorial else 0} editorial")

    # Handle empty results
    if not final_articles and not final_editorial:
        return {
            "current_affairs": [],
            "metadata": {
                "keywords": keywords,
                "message": "No relevant articles found for this topic"
            }
        }

    # Step 12: Prepare extracts for summarization
    article_leads = [get_article_text(a)[:500] for a in final_articles]
    editorial_extract = get_article_text(final_editorial)[:1000] if final_editorial else None

    # Step 13: Summarize (batch LLM call)
    print("✍️ Generating summaries...")
    article_summaries, editorial_summary = await asyncio.to_thread(
        summarize_articles_and_editorial_sync,
        article_leads,
        editorial_extract
    )

    # Step 14: Build output JSON
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

    if editorial_summary and final_editorial:
        out["current_affairs"].append({
            "type": "editorial",
            "summary": editorial_summary.strip(),
            "source": final_editorial.get("source"),
            "url": final_editorial.get("url"),
            "published_at": final_editorial.get("published_at"),
            "opinion_flag": True,
            "relevance_score": final_editorial.get("relevance_score", 0)
        })

    out["metadata"] = {
        "keywords": keywords,
        "queries_used": queries,
        "candidates_fetched": len(all_articles),
        "relevant_found": len(relevant_articles)
    }

    # Step 15: Cache result
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
