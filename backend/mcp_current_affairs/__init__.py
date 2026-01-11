"""
MCP Current Affairs Package
Modular current affairs fetcher with intelligent summarization
"""

from .config import *
from .fetcher import *
from .processing import *
from .llm import *

__version__ = "2.0.0"
__all__ = [
    # Config
    "NEWS_API_KEY",
    "GNEWS_API_KEY",
    "THENEWSAPI_KEY",
    "get_best_provider",
    # Fetcher
    "NewsFetcher",
    "EditorialRSSFetcher",
    # Processing
    "ArticleClassifier",
    "ArticleSelector",
    "SummaryBuilder",
    "CacheManager",
    # LLM
    "KeywordParser",
    "Summarizer",
]
