"""Fetcher module for news and editorial content."""

from .news_fetcher import fetch_articles_for_query
from .editorial_rss import fetch_editorial_rss, fetch_rss_editorials_for_topic
from .utils import (
    normalize_url,
    dedupe_articles,
    within_time_window,
)
from .content_extractor import ensure_content, extract_content, get_article_text

__all__ = [
    "fetch_articles_for_query",
    "fetch_editorial_rss",
    "fetch_rss_editorials_for_topic",
    "normalize_url",
    "dedupe_articles",
    "within_time_window",
    "ensure_content",
    "extract_content",
    "get_article_text",
]
