"""
Dimension-based News Fetcher

Fetches news articles for each dimension's search queries.
Reuses existing news API infrastructure with dimension metadata.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .dimension_planner import DimensionQueryPlan

logger = logging.getLogger(__name__)

# Import existing news fetcher
try:
    from mcp_current_affairs.fetcher.news_fetcher import fetch_articles_for_query
    NEWS_FETCHER_AVAILABLE = True
except ImportError as e:
    NEWS_FETCHER_AVAILABLE = False
    logger.warning(f"Could not import news fetcher from mcp_current_affairs: {e}")


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_TIME_WINDOW_DAYS = 120  # 4 months for dimension-based search


# ============================================================================
# Query Building
# ============================================================================

def build_news_query(planner_query: str) -> str:
    """
    Enhance search query with India focus if not already present.
    
    Args:
        planner_query: Raw query from dimension planner
    
    Returns:
        Enhanced query string
    """
    if "India" not in planner_query and "Indian" not in planner_query:
        return planner_query + " India"
    return planner_query


# ============================================================================
# Metadata Attachment
# ============================================================================

def attach_dimension_metadata(
    articles: List[Dict[str, Any]],
    dimension_name: str,
    dimension_description: str,
    query: str,
    dimension_index: int
) -> List[Dict[str, Any]]:
    """
    Attach dimension metadata to each article.
    
    Args:
        articles: List of article dicts from news API
        dimension_name: Name of the dimension
        dimension_description: Description of the dimension
        query: The search query used
        dimension_index: Index of the dimension (0-based)
    
    Returns:
        Articles with added metadata
    """
    for article in articles:
        article["_dimension"] = dimension_name
        article["_dimension_description"] = dimension_description
        article["_dimension_index"] = dimension_index
        article["_search_query"] = query
    
    return articles


# ============================================================================
# Priority-Based Fetch Configuration
# ============================================================================

# Fetch limits by priority level
PRIORITY_CONFIG = {
    "high": {
        "queries_to_use": None,  # Use all queries (2-3)
        "per_query_limit": 5,
        "max_total": 12
    },
    "medium": {
        "queries_to_use": 2,  # First 2 queries only
        "per_query_limit": 4,
        "max_total": 8
    },
    "low": {
        "queries_to_use": 1,  # First query only
        "per_query_limit": 3,
        "max_total": 3
    }
}


# ============================================================================
# Main Fetcher Function (Priority-Based)
# ============================================================================

async def fetch_articles_dimension_research(
    plan: DimensionQueryPlan,
    concurrent_queries: int = 4,
    gemini_api_key: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Fetch news articles for all dimensions with priority-based limits.
    """
    if not NEWS_FETCHER_AVAILABLE:
        logger.error("News fetcher not available")
        return []
    
    logger.info(f"🚀 [DEBUG] fetch_articles_for_dimensions started. API Key present: {bool(gemini_api_key)}")
    
    all_articles = []
    
    # Calculate expected queries based on priorities
    total_queries = 0
    for dim in plan.dimensions:
        config = PRIORITY_CONFIG.get(dim.priority, PRIORITY_CONFIG["medium"])
        queries_to_use = config["queries_to_use"] or len(dim.search_queries)
        total_queries += min(queries_to_use, len(dim.search_queries))
    
    logger.info(f"📰 Fetching articles for {len(plan.dimensions)} dimensions ({total_queries} queries, priority-based)")
    
    # Process each dimension with its priority limits
    for dim_idx, dimension in enumerate(plan.dimensions):
        dim_articles = await fetch_articles_for_dimension(
            dimension=dimension,
            dimension_index=dim_idx,
            concurrent_limit=concurrent_queries
        )
        all_articles.extend(dim_articles)
        
        priority = dimension.priority
        logger.info(f"   • {dimension.dimension} [{priority}]: {len(dim_articles)} articles")
    
    logger.info(f"✅ Fetched {len(all_articles)} total articles across {len(plan.dimensions)} dimensions")
    
    return all_articles


async def fetch_articles_for_dimension(
    dimension,
    dimension_index: int,
    concurrent_limit: int = 4
) -> List[Dict[str, Any]]:
    """
    Fetch articles for a single dimension with priority-based limits.
    
    Args:
        dimension: DimensionQuery object with priority
        dimension_index: Index of the dimension
        concurrent_limit: Max concurrent API calls
    
    Returns:
        List of articles (capped by priority limits)
    """
    # Get priority configuration
    priority = getattr(dimension, 'priority', 'medium')
    config = PRIORITY_CONFIG.get(priority, PRIORITY_CONFIG["medium"])
    
    queries_to_use = config["queries_to_use"]
    per_query_limit = config["per_query_limit"]
    max_total = config["max_total"]
    
    # Select queries based on priority
    queries = dimension.search_queries
    if queries_to_use is not None:
        queries = queries[:queries_to_use]
    
    logger.debug(f"   [{priority}] Using {len(queries)}/{len(dimension.search_queries)} queries, max {max_total} articles")
    
    # Fetch articles for each query
    semaphore = asyncio.Semaphore(concurrent_limit)
    articles = []
    
    async def fetch_query(query: str):
        async with semaphore:
            try:
                enhanced_query = build_news_query(query)
                results = await fetch_articles_for_query(enhanced_query)
                # Apply per-query limit
                return results[:per_query_limit], query
            except Exception as e:
                logger.warning(f"⚠️ Query failed: {query[:40]}... - {e}")
                return [], query
    
    # Execute all queries for this dimension
    tasks = [fetch_query(q) for q in queries]
    results = await asyncio.gather(*tasks)
    
    # Collect articles with metadata
    for fetched_articles, query in results:
        tagged = attach_dimension_metadata(
            articles=fetched_articles,
            dimension_name=dimension.dimension,
            dimension_description=dimension.dimension_description,
            query=query,
            dimension_index=dimension_index
        )
        # Add priority to metadata
        for article in tagged:
            article["_priority"] = priority
        
        articles.extend(tagged)
        
        # Stop if we've hit the max for this dimension
        if len(articles) >= max_total:
            break
    
    # Enforce max total limit
    return articles[:max_total]


# ============================================================================
# Utility Functions
# ============================================================================

def get_articles_by_dimension(
    articles: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group articles by their dimension.
    
    Args:
        articles: List of articles with dimension metadata
    
    Returns:
        Dict mapping dimension name to list of articles
    """
    by_dimension = {}
    for article in articles:
        dim = article.get("_dimension", "Unknown")
        if dim not in by_dimension:
            by_dimension[dim] = []
        by_dimension[dim].append(article)
    
    return by_dimension


def filter_by_time_window(
    articles: List[Dict[str, Any]],
    days: int = DEFAULT_TIME_WINDOW_DAYS
) -> List[Dict[str, Any]]:
    """
    Filter articles to only those within the time window.
    
    Args:
        articles: List of articles
        days: Number of days to look back
    
    Returns:
        Filtered list of articles
    """
    from mcp_current_affairs.fetcher.utils import within_time_window
    
    cutoff = datetime.now() - timedelta(days=days)
    
    filtered = []
    for article in articles:
        pub_date = article.get("published_at")
        if pub_date:
            # Use existing utility that handles date parsing
            if within_time_window(pub_date, days=days):
                filtered.append(article)
        else:
            # Include articles without dates (can't filter them)
            filtered.append(article)
    
    logger.info(f"🕐 Time filter: {len(filtered)}/{len(articles)} articles within {days} days")
    return filtered
