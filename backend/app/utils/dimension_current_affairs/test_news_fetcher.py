"""
Test script for Dimension News Fetcher

Run from backend directory:
    python -m app.utils.dimension_current_affairs.test_news_fetcher
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
    get_articles_by_dimension,
)


async def test_full_pipeline():
    """Test dimension planner + news fetcher together."""
    
    # Test question
    question = "Identify and discuss the factors responsible for diversity of natural vegetation in India. Assess the significance of wildlife sanctuaries in rain forests regions of India."
    
    print(f"\n{'='*80}")
    print(f"QUESTION: {question[:70]}...")
    print(f"{'='*80}")
    
    # Step 1: Generate dimension plan
    print("\n📐 Step 1: Generating dimension plan...")
    plan = await generate_dimension_plan(question)
    print(f"   Generated {len(plan.dimensions)} dimensions")
    
    for dim in plan.dimensions:
        print(f"   • {dim.dimension} [{dim.priority}] ({len(dim.search_queries)} queries)")
    
    # Step 2: Fetch articles for all dimensions
    print("\n📰 Step 2: Fetching articles...")
    articles = await fetch_articles_for_dimensions(plan, concurrent_queries=3)
    
    print(f"\n📊 Results Summary:")
    print(f"   Total articles: {len(articles)}")
    
    # Group by dimension
    by_dimension = get_articles_by_dimension(articles)
    
    print(f"\n📋 Articles per dimension:")
    for dim_name, dim_articles in by_dimension.items():
        print(f"\n   🔹 {dim_name}: {len(dim_articles)} articles")
        
        # Show first 2 articles
        for i, article in enumerate(dim_articles[:2], 1):
            title = article.get("title", "No title")[:60]
            source = article.get("source", "Unknown")
            print(f"      {i}. [{source}] {title}...")
    
    return articles


async def main():
    """Run the test."""
    print("🧪 Testing Dimension News Fetcher")
    print("="*80)
    
    try:
        articles = await test_full_pipeline()
        print(f"\n✅ Test completed! Fetched {len(articles)} articles total.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
