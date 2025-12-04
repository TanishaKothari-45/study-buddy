"""
current_affairs_fetcher.py

Utility to fetch current affairs from MCP server for answer generation.
Returns formatted bullet points ready for LLM consumption.

Usage:
    from current_affairs_fetcher import fetch_current_affairs_for_question
    
    bullets = await fetch_current_affairs_for_question(
        parsed_keywords={"search_query": "climate change India", ...},
        max_bullets=5
    )
    # Returns: ["• [theprint.in] India launches...", "• [scroll.in] Global summit...", ...]
"""

import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Add backend directory to path for imports
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import MCP current affairs server
try:
    from mcp_current_affairs.mcp_current_affairs_server import fetch_diversified_current_affairs
    MCP_AVAILABLE = True
except ImportError as e:
    MCP_AVAILABLE = False
    logger.warning(f"Could not import MCP server: {e}")


def format_current_affairs_to_bullets(result: Dict[str, Any], max_bullets: int = 5) -> List[str]:
    """
    Convert MCP output JSON to bullet point list for LLM prompt.
    
    Args:
        result: MCP output with current_affairs array
        max_bullets: Maximum bullets to return
    
    Returns:
        List of summary strings (just the text, no icons/source)
        
    Example output:
        ["36% of India's forest cover is in zones vulnerable...",
         "Wildfires and flash floods are interconnected..."]
    """
    if not result or not result.get("current_affairs"):
        return []
    
    bullets = []
    for item in result["current_affairs"]:
        summary = item.get("summary", "").strip()
        if summary:
            bullets.append(summary)
    
    return bullets[:max_bullets]


async def fetch_current_affairs_for_question(
    parsed_keywords: Dict[str, Any],
    max_bullets: int = 5,
    time_range: str = "6months"
) -> List[str]:
    """
    Fetch current affairs for a question using parsed keywords.
    
    Args:
        parsed_keywords: Dict with main_topic, sub_topics, search_query
        max_bullets: Maximum number of bullet points to return (default: 5)
        time_range: Time range for news (default: 6months)
    
    Returns:
        List of formatted bullet strings (40-50 words each)
    """
    if not MCP_AVAILABLE:
        logger.warning("MCP server not available, skipping current affairs fetch")
        return []
    
    if not parsed_keywords:
        logger.warning("No parsed keywords provided")
        return []
    
    search_query = parsed_keywords.get("search_query", "")
    if not search_query:
        # Try main_topic as fallback
        search_query = parsed_keywords.get("main_topic", "")
    
    if not search_query:
        logger.warning("Empty search query")
        return []
    
    try:
        logger.info(f"🗞️ Fetching current affairs for: {search_query[:50]}...")
        
        # Call the MCP server's fetch function directly
        result = await fetch_diversified_current_affairs(topic=search_query)
        
        # Convert to bullet format for LLM
        bullets = format_current_affairs_to_bullets(result, max_bullets)
        
        if bullets:
            logger.info(f"✅ Retrieved {len(bullets)} current affairs bullets")
            return bullets
        
        logger.info("⚠️ No current affairs found for topic")
        return []
        
    except Exception as e:
        logger.error(f"❌ Current affairs fetch failed: {e}", exc_info=True)
        return []


def format_bullets_for_context(bullets: List[str], header: str = "LATEST CURRENT AFFAIRS") -> str:
    """
    Format bullet points as a context section for LLM.
    
    Args:
        bullets: List of bullet point strings
        header: Header for the section
    
    Returns:
        Formatted string ready to append to context
    """
    if not bullets:
        return ""
    
    formatted = f"\n\n**{header}** (Recent developments - last 3 months):\n"
    for bullet in bullets:
        formatted += f"• {bullet}\n"
    
    return formatted


# Synchronous wrapper for non-async contexts
def fetch_current_affairs_sync(
    parsed_keywords: Dict[str, Any],
    max_bullets: int = 5
) -> List[str]:
    """
    Synchronous wrapper - returns empty list (async required for actual fetch).
    Use this only as a fallback when async is not available.
    """
    logger.warning("Sync fetch called - current affairs requires async, returning empty")
    return []

