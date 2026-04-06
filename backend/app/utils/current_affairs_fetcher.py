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

# Import dimension pipelines
try:
    from .dimension_current_affairs.pipeline import run_dimension_pipeline
    from .dimension_current_affairs.gemini_search_pipeline import run_gemini_search_dimension_pipeline
    PIPELINE_AVAILABLE = True
except ImportError as e:
    PIPELINE_AVAILABLE = False
    logger.warning(f"Could not import dimension pipelines: {e}")

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
        from app.core.config import settings
        logger.info(f"🗞️ Running dimension-based research for: {question_text[:50]}...")
        
        # Determine which pipeline to use (default to setting if not provided)
        use_gemini_search = kwargs.get("use_gemini_search", settings.USE_GEMINI_SEARCH_FOR_CURRENT_AFFAIRS)
        
        if use_gemini_search:
            logger.info("🧪 Using Gemini Google Search Tool pipeline")
            result = await run_gemini_search_dimension_pipeline(
                topic=question_text,
                gemini_api_key=gemini_api_key
            )
            # Flatten bullets from all dimensions
            bullets = []
            for dim in result.dimensions:
                bullets.extend(dim.bullets)
        else:
            logger.info("🧪 Using Map/NewsAPI dimension pipeline")
            # Run the legacy/map dimension pipeline
            bullets = await run_dimension_pipeline(
                topic=question_text,
                gemini_api_key=gemini_api_key,
                max_total_bullets=max_bullets
            )
        
        if bullets:
            # Enforce max_bullets but keep variety from dimensions
            if len(bullets) > max_bullets:
                bullets = bullets[:max_bullets]
                
            logger.info(f"✅ Retrieved {len(bullets)} research-backed bullets")
            for i, bullet in enumerate(bullets, 1):
                logger.debug(f"      {i}. {bullet}")
            
            # Store in Research Cache
            cache.set_cached_research(question_text, bullets)
            
            logger.info(f"✨ [FINAL CA ARRAY] {len(bullets)} bullets ready for context injection")
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
    
    logger.info("📝 [CA CONTEXT SYNTAX] Final formatted section for LLM:")
    logger.info(formatted)
    
    return formatted


async def fetch_targeted_ca_bullets(
    query: str,
    subheading: str,
    gemini_client,
    max_bullets: int = 3,
) -> list[str]:
    """
    Fetch CA bullets for one specific blueprint dimension.

    Unlike fetch_current_affairs_for_question(), this function does NOT
    re-plan dimensions internally.  It takes a pre-crafted targeted query
    (from the blueprint's ca_dimension_queries), calls Gemini Flash with
    Google Search, and returns 2–3 bullets directly relevant to that
    query — no dimension re-planning, no MECE breakdown.

    Args:
        query:       Targeted Google Search query for this dimension.
        subheading:  The blueprint subheading this query serves (for logging).
        gemini_client: GeminiClient instance (should be Flash model).
        max_bullets: Max bullets to return (default 3).

    Returns:
        List of bullet strings (20–30 words each).
    """
    import json as _json
    import re as _re
    from datetime import date as _date, timedelta as _timedelta

    _today = _date.today()
    _start = _today - _timedelta(days=240)  # ~8 months back
    _date_range = f"{_start.strftime('%B %Y')} to {_today.strftime('%B %Y')}"

    system_prompt = (
        "You are a UPSC Mains research assistant. Use Google Search to find the most recent "
        "relevant facts for the given query and return 2–3 concise bullet points.\n\n"
        "Rules:\n"
        "- Each bullet: 20–30 words, must contain one hard fact (data, report, policy, year, event)\n"
        f"- Focus on developments from {_date_range} only — prioritise most recent first\n"
        "- UPSC administrative or journalistic language\n"
        "- Return ONLY a JSON array of strings: [\"bullet1\", \"bullet2\"]\n"
        "- No preamble, no explanation, no markdown wrapper"
    )
    user_prompt = (
        f"Dimension: {subheading}\n"
        f"Search query: {query}\n"
        f"Date window: {_date_range} (most recent results preferred)\n\n"
        "Find the latest relevant facts and return as JSON array of bullets."
    )

    try:
        raw = await gemini_client.generate_response(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            use_google_search=True,
            temperature=0.0,
            max_retries=1,
        )

        # Parse JSON array from response
        text = raw.strip()
        # Strip accidental code fences
        if text.startswith("```"):
            text = _re.sub(r"```[a-z]*\n?", "", text).strip().rstrip("`").strip()

        # Try JSON array first
        match = _re.search(r"\[.*\]", text, _re.DOTALL)
        if match:
            try:
                bullets = _json.loads(match.group(0))
                if isinstance(bullets, list):
                    return [str(b).strip() for b in bullets if b][:max_bullets]
            except _json.JSONDecodeError:
                pass

        # Fallback: parse markdown bullet list (* or - or •)
        lines = text.splitlines()
        bullets = []
        for line in lines:
            line = line.strip()
            if line.startswith(("* ", "- ", "• ")):
                bullet = line[2:].strip()
                if bullet:
                    bullets.append(bullet)
        if bullets:
            logger.info(f"CA bullets parsed via markdown fallback for '{subheading}'")
            return bullets[:max_bullets]

        logger.warning(f"Could not parse CA bullets for '{subheading}'. Raw: {raw[:200]}")
        return []

    except Exception as exc:
        logger.warning(f"Targeted CA fetch failed for '{subheading}': {exc}")
        return []


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

