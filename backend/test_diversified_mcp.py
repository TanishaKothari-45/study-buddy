#!/usr/bin/env python3
"""
Test script for MCP Diversified Current Affairs Server

This script tests the new fetch_diversified_current_affairs functionality.

Usage:
    python test_diversified_mcp.py "forest fires"
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_current_affairs_server import CurrentAffairsMCPServer


async def test_diversified_current_affairs(topic: str):
    """Test the fetch_diversified_current_affairs functionality"""
    print(f"🧪 Testing MCP Diversified Current Affairs Server")
    print(f"📝 Topic: {topic}")
    print("=" * 80)
    
    server = CurrentAffairsMCPServer()
    
    try:
        result = await server.fetch_diversified_current_affairs(
            topic=topic,
            time_range="3months",
            total_articles=30,  # Reduced for faster testing
            api_provider=None  # Auto-select
        )
        
        print(f"\n✅ Success!")
        print(f"📰 Provider: {result.get('provider', 'Unknown')}")
        print(f"🔧 Strategy: {result.get('strategy', 'Unknown')}")
        print(f"📊 Statistics:")
        stats = result.get('statistics', {})
        print(f"   - Total Fetched: {stats.get('total_fetched', 0)}")
        print(f"   - Total Categorized: {stats.get('total_categorized', 0)}")
        print(f"   - India Focused: {stats.get('india_focused', 0)}")
        print(f"   - Global Focused: {stats.get('global_focused', 0)}")
        print(f"   - Categories Covered: {stats.get('categories_covered', 0)}")
        
        print(f"\n📂 Categories:")
        print("=" * 80)
        
        categories = result.get('categories', {})
        for cat_key, cat_data in categories.items():
            print(f"\n🔹 {cat_key.upper().replace('_', ' ')}")
            print(f"   Description: {cat_data.get('description', 'N/A')}")
            print(f"   Articles Found: {cat_data.get('count', 0)}")
            
            if cat_data.get('error'):
                print(f"   ⚠️ Error: {cat_data.get('error')}")
            
            articles = cat_data.get('articles', [])
            if articles:
                print(f"   📄 Sample Articles:")
                for i, article in enumerate(articles[:2], 1):  # Show first 2
                    print(f"      {i}. {article.get('title', 'No title')[:70]}...")
                    print(f"         📅 {article.get('date', 'Unknown date')}")
                    print(f"         📰 {article.get('source', 'Unknown source')}")
        
        print("\n" + "=" * 80)
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await server.http_client.aclose()


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "forest fires"
    print(f"🚀 Starting diversified test for topic: {topic}\n")
    asyncio.run(test_diversified_current_affairs(topic))

