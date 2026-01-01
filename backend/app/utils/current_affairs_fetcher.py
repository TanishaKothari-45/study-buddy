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

# Import new dimension pipeline
try:
    from .dimension_current_affairs.pipeline import run_dimension_pipeline
    PIPELINE_AVAILABLE = True
except ImportError as e:
    PIPELINE_AVAILABLE = False
    logger.warning(f"Could not import dimension pipeline: {e}")

from .langsmith_tracer import trace_chain


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


@trace_chain("fetch_current_affairs")
async def fetch_current_affairs_for_question(
    question_text: str,
    max_bullets: int = 5,
    gemini_api_key: Optional[str] = None,
    # Kept for backward compatibility if needed by old calls
    parsed_keywords: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[str]:
    """
    Fetch current affairs using the new dimension-based pipeline.
    
    Args:
        question_text: The UPSC question or topic
        max_bullets: Maximum number of bullet points to return (default: 5)
        gemini_api_key: Optional API key
    
    Returns:
        List of formatted bullet strings (30-40 words each)
    """
    if not PIPELINE_AVAILABLE:
        logger.warning("Dimension pipeline not available, skipping current affairs fetch")
        return []
    
    # If question_text is actually parsed_keywords (old call format)
    if isinstance(question_text, dict):
        parsed_keywords = question_text
        question_text = parsed_keywords.get("main_topic") or parsed_keywords.get("search_query", "")
    elif not question_text and parsed_keywords:
        question_text = parsed_keywords.get("main_topic") or parsed_keywords.get("search_query", "")

    if not question_text:
        logger.warning("No question text provided for dimension pipeline")
        return []
    
    # Check Research Cache
    from .cache_manager import get_cache_manager
    cache = get_cache_manager()
    cached_bullets = cache.get_cached_research(question_text)
    if cached_bullets:
        logger.info(f"✅ [CACHE] Using cached research bullets for: {question_text[:50]}...")
        return cached_bullets[:max_bullets]
    
    try:
        logger.info(f"🗞️ Running dimension-based research for: {question_text[:50]}...")
        
        # Run the full dimension pipeline
        bullets = await run_dimension_pipeline(
            topic=question_text,
            gemini_api_key=gemini_api_key,
            max_total_bullets=max_bullets
        )
        
        if bullets:
            logger.info(f"✅ Retrieved {len(bullets)} research-backed bullets")
            for i, bullet in enumerate(bullets, 1):
                logger.info(f"      {i}. {bullet}")
            
            # Store in Research Cache
            cache.set_cached_research(question_text, bullets)
            return bullets
        
        logger.info("⚠️ No relevant research found for topic")
        return []
        
    except Exception as e:
        logger.error(f"❌ Research pipeline failed: {e}", exc_info=True)
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

