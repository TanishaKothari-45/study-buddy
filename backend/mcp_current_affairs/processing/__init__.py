"""Processing module for article classification, selection, and summarization."""

from .classifier import detect_type, topic_score, mark_corroboration, set_topic_keywords
from .selector import select_articles_and_editorials
from .summary_builder import make_one_liner, extract_lead, extract_editorial_snippet
from .relevance_filter import compute_relevance_scores, filter_by_relevance
from .cache import get_cached_summary, set_cached_summary
from .editorial_processor import process_editorials

__all__ = [
    "detect_type",
    "topic_score",
    "mark_corroboration",
    "set_topic_keywords",
    "select_articles_and_editorials",
    "make_one_liner",
    "extract_lead",
    "extract_editorial_snippet",
    "compute_relevance_scores",
    "filter_by_relevance",
    "get_cached_summary",
    "set_cached_summary",
    "process_editorials",
]
