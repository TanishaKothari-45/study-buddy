#!/usr/bin/env python3
"""
Test script for MCP Current Affairs server (v2)
Tests the improved flow with relevance filtering.
Run with: python test_mcp_flow.py
"""

import asyncio
import json
import sys
import os

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv('/Users/tanishakothari/Documents/Personal/study-buddy/.env')

sys.path.insert(0, '/Users/tanishakothari/Documents/Personal/study-buddy/backend')

from datetime import datetime

# Output file
OUTPUT_FILE = "mcp_test_output_v2.md"

def log(step: str, data, to_file=True):
    """Log step output to console and file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    separator = "=" * 60
    
    output = f"\n{separator}\n## Step: {step}\n**Time:** {timestamp}\n{separator}\n"
    
    if isinstance(data, (dict, list)):
        output += f"```json\n{json.dumps(data, indent=2, ensure_ascii=False, default=str)}\n```\n"
    else:
        output += f"```\n{data}\n```\n"
    
    print(output)
    
    if to_file:
        with open(OUTPUT_FILE, "a") as f:
            f.write(output + "\n")


async def test_mcp_flow(topic: str):
    """Run the full MCP flow with step-by-step output."""
    
    # Clear output file
    with open(OUTPUT_FILE, "w") as f:
        f.write(f"# MCP Current Affairs Test Output (v2)\n\n")
        f.write(f"**Topic:** {topic}\n")
        f.write(f"**Started:** {datetime.now().isoformat()}\n\n")
    
    log("0. Starting Test", f"Topic: {topic}")
    
    # Import modules
    from mcp_current_affairs.llm.keyword_parser import get_keywords, build_search_queries
    from mcp_current_affairs.processing.classifier import (
        detect_type, topic_score, mark_corroboration, set_topic_keywords
    )
    from mcp_current_affairs.fetcher.news_fetcher import fetch_articles_for_query
    from mcp_current_affairs.fetcher.editorial_rss import fetch_editorial_rss
    from mcp_current_affairs.fetcher.utils import dedupe_articles, within_time_window
    from mcp_current_affairs.fetcher.content_extractor import ensure_content, get_article_text
    from mcp_current_affairs.processing.relevance_filter import compute_relevance_scores, filter_by_relevance
    from mcp_current_affairs.llm.summarizer import summarize_articles_and_editorial_sync
    from mcp_current_affairs.config import (
        RELEVANCE_THRESHOLD, TOP_CANDIDATES_FOR_SCRAPING, MIN_CONTENT_LENGTH, FINAL_ARTICLE_COUNT
    )
    
    # Step 1: Get keywords
    log("1. Keyword Extraction", "Calling OpenAI GPT-4o-mini...")
    try:
        keywords = await get_keywords(topic)
        set_topic_keywords(keywords)
        log("1. Keywords Result", {"keywords": keywords})
    except Exception as e:
        log("1. Keywords ERROR", str(e))
        return
    
    # Step 2: Build queries
    queries = build_search_queries(keywords, topic)
    log("2. Search Queries", queries)
    
    # Step 3: Fetch candidates
    log("3. Fetching Candidates", f"10 per query × 4 queries = 40 max")
    tasks = [fetch_articles_for_query(q) for q in queries]
    results = await asyncio.gather(*tasks)
    
    all_articles = []
    for i, (query, batch) in enumerate(zip(queries, results)):
        for article in batch:
            article["_query_index"] = i
            article["_query"] = query
            all_articles.append(article)
        log(f"3.{i+1} Query: {query[:40]}...", {
            "count": len(batch),
            "sample_titles": [a.get("title", "")[:50] for a in batch[:3]]
        })
    
    log("3. Total Fetched", len(all_articles))
    
    # Step 4: Dedupe
    articles = dedupe_articles(all_articles)
    log("4. After Dedupe", {"count": len(articles), "removed": len(all_articles) - len(articles)})
    
    # Step 5: Ensure content (lazy scrape)
    log("5. Content Extraction", f"Scraping top {TOP_CANDIDATES_FOR_SCRAPING} if needed...")
    articles = await ensure_content(articles, min_length=MIN_CONTENT_LENGTH, max_to_scrape=TOP_CANDIDATES_FOR_SCRAPING)
    
    content_stats = {
        "scraped": sum(1 for a in articles if a.get("content_scraped")),
        "avg_content_len": sum(len(get_article_text(a)) for a in articles) // max(len(articles), 1)
    }
    log("5. Content Stats", content_stats)
    
    # Step 6: Compute relevance
    log("6. Computing Relevance Scores", "Using embedding similarity...")
    articles = await compute_relevance_scores(articles, keywords)
    
    top_5_relevance = sorted(articles, key=lambda x: x.get("relevance_score", 0), reverse=True)[:5]
    log("6. Top 5 by Relevance", [
        {"title": a.get("title", "")[:40], "score": a.get("relevance_score", 0)}
        for a in top_5_relevance
    ])
    
    # Step 7: Filter by relevance
    relevant_articles = filter_by_relevance(articles, threshold=RELEVANCE_THRESHOLD)
    log("7. Relevance Filter", {
        "threshold": RELEVANCE_THRESHOLD,
        "passed": len(relevant_articles),
        "dropped": len(articles) - len(relevant_articles)
    })
    
    # Step 8: Time filter with fallback
    time_filtered = []
    old_high_relevance = []
    for a in relevant_articles:
        pub_date = a.get("published_at")
        if pub_date and within_time_window(pub_date):
            time_filtered.append(a)
        elif a.get("relevance_score", 0) > 0.5:
            old_high_relevance.append(a)
            
    if len(time_filtered) < 3:
        needed = 3 - len(time_filtered)
        if old_high_relevance:
            old_high_relevance.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            time_filtered.extend(old_high_relevance[:needed])
    
    log("8. Time Filter (90 days + fallback)", {
        "total_kept": len(time_filtered),
        "recent": len([a for a in time_filtered if within_time_window(a.get("published_at"))]),
        "old_filled": len(time_filtered) - len([a for a in time_filtered if within_time_window(a.get("published_at"))])
    })
    
    # Step 9: Classify
    for a in time_filtered:
        a["type"] = detect_type(a)
        a["topic_score"] = topic_score(a)
    time_filtered = mark_corroboration(time_filtered)
    
    type_counts = {}
    for a in time_filtered:
        t = a["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    log("9. Classification", type_counts)
    
    # Step 10: Select with fallback
    def select_articles_with_fallback(articles, num_queries=4):
        by_query = {i: [] for i in range(num_queries)}
        for a in articles:
            idx = a.get("_query_index", 0)
            if idx < num_queries:
                by_query[idx].append(a)
        
        selected = []
        selected_urls = set()
        
        for i in range(num_queries):
            candidates = by_query[i]
            if not candidates:
                continue
            candidates.sort(
                key=lambda x: (x.get("corroborated", False), x.get("relevance_score", 0)),
                reverse=True
            )
            for candidate in candidates:
                url = candidate.get("url")
                if url and url not in selected_urls and candidate["type"] == "article":
                    selected.append(candidate)
                    selected_urls.add(url)
                    break
        
        # Fallback: fill to 3 if needed
        if len(selected) < 3:
            print(f"   Fallback: only {len(selected)} per-query, filling to 3...")
            all_sorted = sorted([a for a in articles if a["type"] == "article"], 
                              key=lambda x: x.get("relevance_score", 0), reverse=True)
            for a in all_sorted:
                if len(selected) >= 3:
                    break
                url = a.get("url")
                if url and url not in selected_urls:
                    selected.append(a)
                    selected_urls.add(url)
        return selected[:FINAL_ARTICLE_COUNT]
    
    final_articles = select_articles_with_fallback(time_filtered)
    
    # Get editorial using new processor with quality scoring
    from mcp_current_affairs.processing.editorial_processor import process_editorials
    
    log("10. Processing Editorials (New Pipeline)", "Using quality scoring + recency boost...")
    final_editorial = await process_editorials(keywords)
    
    log("10. Selection", {
        "articles_selected": len(final_articles),
        "articles": [{"title": a.get("title", "")[:40], "query": a.get("_query_index"), "relevance": a.get("relevance_score")} for a in final_articles],
        "editorial": {"title": final_editorial.get("title", "")[:40], "relevance": final_editorial.get("relevance_score"), "quality": final_editorial.get("quality_score")} if final_editorial else None
    })
    
    if not final_articles and not final_editorial:
        log("RESULT", "No relevant articles found!")
        return
    
    # Step 11: Summarize
    article_leads = [get_article_text(a)[:500] for a in final_articles]
    editorial_extract = get_article_text(final_editorial)[:1000] if final_editorial else None
    
    log("11. Extracts for Summarization", {
        "article_lead_lengths": [len(l) for l in article_leads],
        "editorial_extract_length": len(editorial_extract) if editorial_extract else 0
    })
    
    log("11. Calling Summarizer", "Batch LLM call...")
    article_summaries, editorial_summary = await asyncio.to_thread(
        summarize_articles_and_editorial_sync,
        article_leads,
        editorial_extract
    )
    
    log("11. Summaries Generated", {
        "article_summaries": article_summaries,
        "editorial_summary": editorial_summary
    })
    
    # Step 12: Build output
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
        "queries_used": queries
    }
    
    log("12. FINAL OUTPUT", out)
    
    print(f"\n\n✅ Test complete! Full output saved to: {OUTPUT_FILE}")
    return out


if __name__ == "__main__":
    topic = "why forest fires increasing per year"
    print(f"\n🔥 Testing MCP Current Affairs (v2) with topic: '{topic}'\n")
    asyncio.run(test_mcp_flow(topic))
