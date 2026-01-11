"""
Dimension-based Current Affairs Pipeline

New approach for UPSC-aligned current affairs fetching:
1. Break question into answer-oriented dimensions
2. Generate news-style search queries per dimension
3. Fetch and scrape relevant articles
4. Filter by relevance
5. Summarize per dimension
"""

from .dimension_planner import (
    DimensionQuery,
    DimensionQueryPlan,
    generate_dimension_plan,
    get_all_search_queries,
    get_dimension_names,
)

from .dimension_news_fetcher import (
    fetch_articles_dimension_research,
    get_articles_by_dimension,
    filter_by_time_window,
    build_news_query,
)

from .dimension_relevance_filter import (
    filter_articles_by_dimensions,
    soft_filter_articles,
    get_top_articles_per_dimension,
    DEFAULT_SIMILARITY_THRESHOLD,
)

from .dimension_content_scraper import (
    scrape_articles_content,
    get_best_content,
    filter_by_content_length,
)

from .dimension_summarizer import (
    ArticleRelevance,
    generate_dimension_bullets,
)

__all__ = [
    # Dimension Planner
    "DimensionQuery",
    "DimensionQueryPlan", 
    "generate_dimension_plan",
    "get_all_search_queries",
    "get_dimension_names",
    # News Fetcher
    "fetch_articles_dimension_research",
    "get_articles_by_dimension",
    "filter_by_time_window",
    "build_news_query",
    # Relevance Filter
    "filter_articles_by_dimensions",
    "soft_filter_articles",
    "get_top_articles_per_dimension",
    "DEFAULT_SIMILARITY_THRESHOLD",
    # Content Scraper
    "scrape_articles_content",
    "get_best_content",
    "filter_by_content_length",
    # Summarizer
    "ArticleRelevance",
    "generate_dimension_bullets",
]
