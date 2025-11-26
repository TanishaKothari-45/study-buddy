#!/usr/bin/env python3
"""
Test script for MCP Current Affairs Server

This script tests the MCP server functionality directly without requiring
the full MCP protocol setup.

Usage:
    python test_mcp_server.py "climate change"
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_current_affairs_server import CurrentAffairsMCPServer


async def test_fetch_current_affairs(topic: str):
    """Test the fetch_current_affairs functionality"""
    print(f"🧪 Testing MCP Current Affairs Server")
    print(f"📝 Topic: {topic}")
    print("-" * 60)
    
    server = CurrentAffairsMCPServer()
    
    try:
        result = await server.fetch_current_affairs(
            topic=topic,
            time_range="3months",
            region="India",
            count=5
        )
        
        print(f"\n✅ Success! Retrieved {result.get('total_results', 0)} results")
        print(f"📰 Provider: {result.get('provider', 'Unknown')}")
        print(f"\n📄 Articles ({len(result.get('articles', []))}):")
        print("-" * 60)
        
        for i, article in enumerate(result.get('articles', [])[:5], 1):
            print(f"\n{i}. {article.get('title', 'No title')}")
            print(f"   📅 Date: {article.get('date', 'Unknown')}")
            print(f"   📰 Source: {article.get('source', 'Unknown')}")
            print(f"   📝 Summary: {article.get('summary', 'No summary')[:100]}...")
            if article.get('url'):
                print(f"   🔗 URL: {article.get('url')}")
        
        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await server.http_client.aclose()


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "climate change India"
    print(f"🚀 Starting test for topic: {topic}\n")
    asyncio.run(test_fetch_current_affairs(topic))

