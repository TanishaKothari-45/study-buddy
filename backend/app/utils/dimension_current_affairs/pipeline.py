"""
Unified Dimension-Based Current Affairs Pipeline

Orchestrates:
1. Dimension Planning (Planner)
2. Priority-Based News Fetching (Fetcher)
3. Soft Relevance Filtering (Local Filter)
4. Asymmetric Selection (Priority-based)
5. Content Scraping (Scraper)
6. Batch LLM Judging & Summarization (Summarizer)
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

from .dimension_planner import generate_dimension_plan
from .dimension_news_fetcher import fetch_articles_dimension_research
from .dimension_relevance_filter import filter_articles_by_dimensions, get_top_articles_per_dimension
from .dimension_content_scraper import scrape_articles_content
from .dimension_summarizer import generate_dimension_bullets

logger = logging.getLogger(__name__)

async def run_dimension_pipeline(
    topic: str,
    gemini_api_key: Optional[str] = None,
    max_total_bullets: int = 12
) -> List[str]:
    """
    Run the full dimension-based current affairs pipeline.
    
    Args:
        topic: The question or topic to search for
        gemini_api_key: Optional API key
        max_total_bullets: Maximum bullets to return across all dimensions
        
    Returns:
        List of 30-40 word factual UPSC bullets.
    """
    try:
        # Step 1: Planner
        logger.info(f"📐 Stage 1: Planning dimensions for: {topic[:50]}...")
        plan = await generate_dimension_plan(topic, gemini_api_key=gemini_api_key)
        logger.info(f"   ✅ Generated {len(plan.dimensions)} dimensions:")
        for i, dim in enumerate(plan.dimensions, 1):
            logger.info(f"      {i}. {dim.dimension} (Priority: {dim.priority})")
            if hasattr(dim, 'search_queries') and dim.search_queries:
                logger.info(f"         🔍 Queries: {', '.join(dim.search_queries)}")
        
        # Step 2: Fetcher
        logger.info(f"📰 Stage 2: Fetching news according to dimension priorities...")
        articles = await fetch_articles_dimension_research(plan, gemini_api_key=gemini_api_key)
        logger.info(f"   ✅ Fetched {len(articles)} total candidate articles")
        
        if not articles:
            logger.warning("⚠️ No articles fetched across any dimension")
            return []
            
        # Step 3: Soft Filter
        logger.info(f"🔍 Stage 3: Applying local embedding-based soft filter (Threshold: 0.30)...")
        filtered = filter_articles_by_dimensions(articles, threshold=0.30)
        logger.info(f"   ✅ {len(filtered)}/{len(articles)} articles passed soft filter")
        
        # Step 4: Asymmetric Selection
        logger.info("⭐ Stage 4: Performing asymmetric Top-N selection per dimension...")
        top_candidates = get_top_articles_per_dimension(filtered, use_priority=True)
        logger.info(f"   ✅ Selected {len(top_candidates)} final candidate articles for scraping")
        
        # Step 5: Scraper
        logger.info(f"📝 Stage 5: Scraping full content for top candidates...")
        scraped = await scrape_articles_content(top_candidates, concurrent_limit=5)
        scraped_success = sum(1 for a in scraped if a.get("_content_scraped"))
        logger.info(f"   ✅ Successfully scraped {scraped_success}/{len(scraped)} articles")
        
        # Step 6: Batch Summarizer
        logger.info(f"✨ Stage 6: Running LLM Batch Judge & Summarizer (1 API Call)...")
        bullets = await generate_dimension_bullets(scraped, gemini_api_key=gemini_api_key)
        logger.info(f"   ✅ Final UPSC Enrichment: Generated {len(bullets)} high-signal bullets")
        for i, bullet in enumerate(bullets, 1):
            logger.info(f"      {i}. {bullet}")
        
        return bullets[:max_total_bullets]
        
    except Exception as e:
        logger.error(f"❌ Dimension pipeline failed: {e}", exc_info=True)
        return []

async def fetch_dimension_current_affairs_structured(
    topic: str,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Wrapper for MCP server that returns structured data.
    """
    bullets = await run_dimension_pipeline(topic, gemini_api_key=gemini_api_key)
    
    return {
        "current_affairs": [{"summary": b, "type": "article"} for b in bullets],
        "metadata": {
            "topic": topic,
            "pipeline": "dimension_v1",
            "bullet_count": len(bullets)
        }
    }
