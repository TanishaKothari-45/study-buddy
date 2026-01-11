"""LLM module for keyword parsing and summarization."""

from .keyword_parser import get_keywords, build_search_queries
from .summarizer import summarize_articles_and_editorial_sync
from .prompts import (
    ARTICLE_ONE_LINER_PROMPT,
    EDITORIAL_SUMMARY_PROMPT,
    BATCH_SUMMARY_PROMPT,
    KEYWORD_EXTRACTION_PROMPT,
)

__all__ = [
    "get_keywords",
    "build_search_queries",
    "summarize_articles_and_editorial_sync",
    "ARTICLE_ONE_LINER_PROMPT",
    "EDITORIAL_SUMMARY_PROMPT",
    "BATCH_SUMMARY_PROMPT",
    "KEYWORD_EXTRACTION_PROMPT",
]
