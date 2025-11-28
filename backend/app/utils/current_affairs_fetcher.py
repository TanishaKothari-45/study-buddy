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
    # Returns: ["India launches...", "Global summit...", ...]
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

# Import MCP server class directly (not via MCP protocol)
try:
    from mcp_current_affairs_server import CurrentAffairsMCPServer
    MCP_AVAILABLE = True
except ImportError as e:
    MCP_AVAILABLE = False
    logger.warning(f"Could not import MCP server: {e}")


async def fetch_current_affairs_for_question(
    parsed_keywords: Dict[str, Any],
    max_bullets: int = 5,
    time_range: str = "3months"
) -> List[str]:
    """
    Fetch current affairs for a question using parsed keywords.
    
    Args:
        parsed_keywords: Dict with main_topic, sub_topics, search_query
        max_bullets: Maximum number of bullet points to return (default: 5)
        time_range: Time range for news (default: 3months)
    
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
        logger.warning("Empty search query")
        return []
    
    try:
        logger.info(f"🗞️ Fetching current affairs for: {search_query[:50]}...")
        
        # Create MCP server instance (reuses cached results)
        server = CurrentAffairsMCPServer()
        
        # Fetch diversified current affairs with pre-parsed keywords
        result = await server.fetch_diversified_current_affairs(
            topic=search_query,
            time_range=time_range,
            total_articles=30,
            pre_parsed_keywords=parsed_keywords
        )
        
        # Extract summary bullets from result
        summary_bullets = result.get("summary_bullets", [])
        
        if summary_bullets:
            logger.info(f"✅ Retrieved {len(summary_bullets)} current affairs bullets")
            return summary_bullets[:max_bullets]
        
        # Fallback: generate bullets from categories if summary_bullets not present
        logger.info("⚠️ No summary_bullets in result, generating from categories...")
        bullets = _extract_bullets_from_categories(result, max_bullets)
        
        return bullets
        
    except Exception as e:
        logger.error(f"❌ Current affairs fetch failed: {e}", exc_info=True)
        return []


def _extract_bullets_from_categories(result: Dict[str, Any], max_bullets: int) -> List[str]:
    """
    Fallback: Extract bullets from categorized articles if summary_bullets not present.
    """
    bullets = []
    categories = result.get("categories", {})
    
    priority_order = ['india_initiatives', 'india_issues', 'global_initiatives', 'global_issues', 'developments']
    
    for cat_key in priority_order:
        if cat_key in categories:
            articles = categories[cat_key].get('articles', [])
            for article in articles[:2]:
                summary = article.get('summary', '')
                source = article.get('source', 'Unknown')
                date = article.get('date', '')[:10] if article.get('date') else ''
                
                if summary:
                    words = summary.split()
                    if len(words) > 45:
                        truncated = ' '.join(words[:45]) + '...'
                    else:
                        truncated = summary
                    
                    bullet = f"{truncated} (Source: {source}, {date})"
                    bullets.append(bullet)
                
                if len(bullets) >= max_bullets:
                    break
        
        if len(bullets) >= max_bullets:
            break
    
    return bullets


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

