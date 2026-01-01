"""
Test script for full Dimension Current Affairs Pipeline

Run from backend directory:
    python -m app.utils.dimension_current_affairs.test_full_pipeline
"""

import asyncio
import sys
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
    get_best_content,
)


async def test_full_pipeline():
    """Test: Planner → Fetch → Filter pipeline."""
    
    # Test question
    question = "Discuss the impact of climate change on tribal agriculture in India. What measures can be taken to ensure food security for tribal communities?"
    
    print(f"\n{'='*80}")
    print(f"QUESTION: {question[:70]}...")
    print(f"{'='*80}")
    
    # Step 1: Generate dimension plan
    print("\n📐 Step 1: Generating dimension plan...")
    plan = await generate_dimension_plan(question)
    print(f"   Generated {len(plan.dimensions)} dimensions:")
    
    for dim in plan.dimensions:
        print(f"   • {dim.dimension} [{dim.priority}]")
    
    # Step 2: Fetch articles with priority limits
    print("\n📰 Step 2: Fetching articles (priority-based)...")
    articles = await fetch_articles_for_dimensions(plan)
    print(f"   Fetched: {len(articles)} articles")
    
    # Step 3: Soft filter by relevance
    print("\n🔍 Step 3: Soft filtering by dimension relevance...")
    filtered = filter_articles_by_dimensions(articles, threshold=0.30)
    print(f"   After filter: {len(filtered)} articles")
    
    # Step 4: Scrape full content for top articles per dimension
    print("\n📰 Step 4: Scraping full content...")
    top_articles = get_top_articles_per_dimension(filtered, top_n=2)
    scraped = await scrape_articles_content(top_articles, max_scrape_per_dimension=2)
    scraped_count = sum(1 for a in scraped if a.get("_content_scraped"))
    print(f"   Scraped: {scraped_count}/{len(scraped)} articles")
    
    # Step 5: Display results
    print("\n⭐ Step 5: Final articles per dimension:")
    
    # Group and display
    by_dim = {}
    for a in scraped:
        dim = a.get("_dimension", "Unknown")
        if dim not in by_dim:
            by_dim[dim] = []
        by_dim[dim].append(a)
    
    for dim_name, dim_articles in by_dim.items():
        priority = dim_articles[0].get("_priority", "?")
        print(f"\n   🔹 {dim_name} [{priority}]:")
        for a in dim_articles:
            title = (a.get("title") or "No title")[:45]
            score = a.get("_similarity_score", 0)
            content_len = len(get_best_content(a))
            scraped_flag = "✓" if a.get("_content_scraped") else ""
            print(f"      • [{score:.3f}] {title}... ({content_len} chars) {scraped_flag}")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 PIPELINE SUMMARY")
    print(f"{'='*80}")
    print(f"   Dimensions: {len(plan.dimensions)}")
    print(f"   Articles fetched: {len(articles)}")
    print(f"   After soft filter: {len(filtered)}")
    print(f"   Top articles: {len(scraped)}")
    print(f"   Content scraped: {scraped_count}")
    print(f"{'='*80}")
    
    return scraped


async def main():
    """Run the test."""
    print("🧪 Testing Full Dimension Current Affairs Pipeline")
    print("="*80)
    
    try:
        articles = await test_full_pipeline()
        print(f"\n✅ Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
