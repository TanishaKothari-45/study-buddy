#!/usr/bin/env python3
"""
Test script for MCP Current Affairs Server

Run with: python backend/test_mcp_server.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path (parent of tests/)
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from mcp_current_affairs_server import CurrentAffairsMCPServer

# Test query - change this to test different questions
TEST_QUERY = """Explain the geographical factors affecting or influencing the location of large-scale digital infrastructure in India. Analyse how such investments are transforming the spatial pattern of economic activity."""


async def test_keyword_parsing():
    """Test the LLM keyword parser."""
    print("=" * 80)
    print("🧪 TEST 1: Keyword Parsing")
    print("=" * 80)
    print(f"\n📝 Input Query:\n{TEST_QUERY}\n")
    
    server = CurrentAffairsMCPServer()
    
    parsed = await server.parse_topic_keywords(TEST_QUERY)
    
    print("✅ Parsed Keywords:")
    print(f"   • Main Topic: {parsed.get('main_topic', 'N/A')}")
    print(f"   • Sub Topics: {parsed.get('sub_topics', [])}")
    print(f"   • Search Query: {parsed.get('search_query', 'N/A')}")
    
    return parsed


async def test_fetch_current_affairs(parsed_keywords=None):
    """Test fetching current affairs with parsed keywords."""
    print("\n" + "=" * 80)
    print("🧪 TEST 2: Fetch Current Affairs")
    print("=" * 80)
    
    server = CurrentAffairsMCPServer()
    
    try:
        result = await server.fetch_current_affairs(
            topic=TEST_QUERY,
            time_range="3months",
            region="India",
            count=5,
            pre_parsed_keywords=parsed_keywords
        )
        
        print(f"\n✅ Results:")
        print(f"   • Provider: {result.get('provider', 'N/A')}")
        print(f"   • Total Results: {result.get('total_results', 0)}")
        print(f"   • Articles Fetched: {len(result.get('articles', []))}")
        
        if result.get('parsed_keywords'):
            print(f"   • Parsed Search Query: {result['parsed_keywords'].get('search_query', 'N/A')}")
        
        print("\n📰 Articles:")
        for i, article in enumerate(result.get('articles', [])[:5], 1):
            print(f"\n   {i}. {article.get('title', 'No title')[:70]}...")
            print(f"      Source: {article.get('source', 'Unknown')}")
            print(f"      Date: {article.get('date', 'Unknown')}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None


async def test_diversified_current_affairs(parsed_keywords=None):
    """Test fetching diversified current affairs."""
    print("\n" + "=" * 80)
    print("🧪 TEST 3: Fetch Diversified Current Affairs")
    print("=" * 80)
    
    server = CurrentAffairsMCPServer()
    
    try:
        result = await server.fetch_diversified_current_affairs(
            topic=TEST_QUERY,
            time_range="3months",
            total_articles=30,
            pre_parsed_keywords=parsed_keywords
        )
        
        print(f"\n✅ Results:")
        print(f"   • Strategy: {result.get('strategy', 'N/A')}")
        print(f"   • Provider: {result.get('provider', 'N/A')}")
        print(f"   • Parser Used: {result.get('metadata', {}).get('parser_used', 'N/A')}")
        
        stats = result.get('statistics', {})
        print(f"\n📊 Statistics:")
        print(f"   • Total Fetched: {stats.get('total_fetched', 0)}")
        print(f"   • Unique Articles: {stats.get('unique_articles', 0)}")
        print(f"   • Total Categorized: {stats.get('total_categorized', 0)}")
        print(f"   • India Focused: {stats.get('india_focused', 0)}")
        print(f"   • Global Focused: {stats.get('global_focused', 0)}")
        
        print(f"\n📂 Categories with Article Summaries:")
        categories = result.get('categories', {})
        for cat_name, cat_data in categories.items():
            count = cat_data.get('count', 0)
            if count > 0:
                print(f"\n   📌 {cat_name.upper()} ({count} articles)")
                print(f"   {'-' * 50}")
                articles = cat_data.get('articles', [])
                for i, article in enumerate(articles[:3], 1):  # Show top 3 per category
                    title = article.get('title', 'No title')[:70]
                    summary = article.get('summary', 'No summary')
                    # Truncate summary to 2 lines (~150 chars)
                    if summary and len(summary) > 150:
                        summary = summary[:150] + "..."
                    print(f"   {i}. {title}...")
                    if summary and summary != 'No summary':
                        print(f"      💡 {summary}")
                    print()
        
        # Show diversification strategy
        div_strategy = result.get('diversification_strategy', {})
        print(f"\n🔍 Search Queries Used:")
        for query in div_strategy.get('search_queries_used', [])[:5]:
            print(f"   • {query}")
        
        # Generate usable points for answer generation
        print("\n" + "=" * 80)
        print("📝 USABLE POINTS FOR ANSWER GENERATION")
        print("=" * 80)
        
        all_points = []
        for cat_name, cat_data in categories.items():
            articles = cat_data.get('articles', [])
            for article in articles:
                title = article.get('title', '')
                summary = article.get('summary', '')
                source = article.get('source', 'Unknown')
                date = article.get('date', '')[:10] if article.get('date') else ''
                
                if summary:
                    # Create a concise point
                    point = f"• {summary[:200]}... (Source: {source}, {date})"
                    all_points.append({
                        'category': cat_name,
                        'point': point,
                        'title': title,
                        'summary': summary
                    })
        
        # Print formatted points by category
        for cat_name in ['india_initiatives', 'global_initiatives', 'india_issues', 'global_issues', 'developments']:
            cat_points = [p for p in all_points if p['category'] == cat_name]
            if cat_points:
                print(f"\n🏷️  {cat_name.replace('_', ' ').title()}:")
                for p in cat_points[:2]:  # Top 2 per category
                    print(f"   {p['point'][:250]}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    print("\n" + "🚀 " * 20)
    print("   MCP CURRENT AFFAIRS SERVER - TEST SUITE")
    print("🚀 " * 20 + "\n")
    
    # Test 1: Keyword parsing
    parsed = await test_keyword_parsing()
    
    # Test 2: Fetch current affairs (using parsed keywords)
    await test_fetch_current_affairs(parsed)
    
    # Test 3: Fetch diversified current affairs
    await test_diversified_current_affairs(parsed)
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # Allow changing the query via command line
    if len(sys.argv) > 1:
        TEST_QUERY = " ".join(sys.argv[1:])
    
    asyncio.run(main())
