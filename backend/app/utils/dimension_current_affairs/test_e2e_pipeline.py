"""
Complete End-to-End Test for Dimension Current Affairs Pipeline

Pipeline stages:
1. Planner: Breaking question into dimensions + priorities
2. Fetcher: Priority-based news search
3. Soft Filter: Embedding-based similarity check (0.30)
4. Selection: Asymmetric top N selection (3=high, 2=medium, 1=low)
5. Scraper: full article text extraction
6. Summarizer: Hard relevance judge + 40-word UPSC bullet
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.utils.dimension_current_affairs import (
    generate_dimension_plan,
    fetch_articles_for_dimensions,
    filter_articles_by_dimensions,
    get_top_articles_per_dimension,
    scrape_articles_content,
    generate_dimension_bullets,
    get_best_content,
)


async def test_complete_pipeline():
    """Run E2E pipeline test."""
    
    question = "Elucidate the relationship between globalization and new technology in a world of scarce resources, with special reference to India."
    
    print(f"\n{'='*80}")
    print(f"QUESTION: {question[:70]}...")
    print(f"{'='*80}")
    
    # 📐 Stage 1: Planner
    print("\n📐 Stage 1: Generating dimension plan...")
    plan = await generate_dimension_plan(question)
    print(f"   Generated {len(plan.dimensions)} dimensions")
    
    for i, dim in enumerate(plan.dimensions, 1):
        print(f"\n   [{i}] Dimension: {dim.dimension} ({dim.priority})")
        print(f"       Queries: {', '.join(dim.search_queries)}")
        print(f"       Goal: {dim.dimension_description}")
    
    # 📰 Stage 2: Fetcher
    print("\n📰 Stage 2: Fetching news (priority-based limits)...")
    articles = await fetch_articles_for_dimensions(plan)
    print(f"   Fetched: {len(articles)} articles total")
    
    # 🔍 Stage 3 & 4: Soft Filter + Asymmetric Selection
    print("\n🔍 Stage 3: Soft filtering & Asymmetric Selection...")
    # First filter for quality
    filtered = filter_articles_by_dimensions(articles, threshold=0.30)
    # Then select top N based on priority (high=3, med=2, low=1)
    top_articles = get_top_articles_per_dimension(filtered, use_priority=True)
    print(f"   Selected top: {len(top_articles)} articles")
    
    # 📝 Stage 5: Scraper
    print("\n📝 Stage 5: Scraping full content...")
    scraped = await scrape_articles_content(top_articles, concurrent_limit=5)
    scraped_count = sum(1 for a in scraped if a.get("_content_scraped"))
    print(f"   Scraped: {scraped_count}/{len(scraped)} articles")
    
    # ✨ Stage 6: Hard Judge & Summarizer (Batch Call)
    print("\n✨ Stage 6: LLM Batch Relevance Judge & Summarization (1 API Call)...")
    # This will return a flat list of summary bullets for articles judged as "STRONG" in a single call
    bullets = await generate_dimension_bullets(scraped)
    print(f"   Final STRONG bullets: {len(bullets)}/{len(scraped)}")
    
    # 📋 Output Results
    print(f"\n{'='*80}")
    print(f"🎯 FINAL UPSC CURRENT AFFAIRS ENRICHMENT (FOR LLM)")
    print(f"{'='*80}")
    
    for i, bullet in enumerate(bullets, 1):
        print(f"  {i}. {bullet}")
    
    # Final Stats
    print(f"\n{'='*80}")
    print(f"📊 PIPELINE STATS")
    print(f"{'='*80}")
    print(f"   Dimensions: {len(plan.dimensions)}")
    print(f"   Initial articles: {len(articles)}")
    print(f"   Selected (asymmetric): {len(top_articles)}")
    print(f"   Success (Strong): {len(bullets)}")
    print(f"{'='*80}")
    
    return bullets


async def main():
    """Run E2E test."""
    print("🧪 Testing Complete Dimension Current Affairs Pipeline")
    print("="*80)
    
    try:
        results = await test_complete_pipeline()
        print(f"\n✅ Pipeline test completed successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
