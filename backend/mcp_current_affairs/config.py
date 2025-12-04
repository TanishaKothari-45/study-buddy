# config.py

import os
from datetime import timedelta

# config.py additions near top or Redis section
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "mcp_ca")

# -----------------------------
# API KEYS (Set via env vars)
# -----------------------------
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
THENEWSAPI_KEY  = os.getenv("THENEWSAPI_KEY", "")

# -----------------------------
# FETCH LIMITS & TIME WINDOWS
# -----------------------------
ARTICLE_TIME_WINDOW_DAYS = 90              # 3 months for news articles
EDITORIAL_TIME_WINDOW_DAYS = 180           # 6 months for editorials (with recency boost)
TIME_WINDOW_DAYS = ARTICLE_TIME_WINDOW_DAYS  # Default (for backward compatibility)
ARTICLES_PER_QUERY = 10                    # fetch per query
TOTAL_ARTICLE_LIMIT = 40                   # global cap after merge
FINAL_ARTICLE_COUNT = 4                    # one per subquery
FINAL_EDITORIAL_COUNT = 1                  # editorial summary

# -----------------------------
# RELEVANCE FILTERING
# -----------------------------
RELEVANCE_THRESHOLD = 0.4                  # Semantic similarity threshold for articles
EDITORIAL_RELEVANCE_THRESHOLD = 0.4        # Threshold for editorials
TOP_CANDIDATES_FOR_SCRAPING = 10           # Lazy scrape only top N
MIN_CONTENT_LENGTH = 200                   # Scrape if content < this

# -----------------------------
# CONCURRENCY CONTROL
# -----------------------------
MAX_CONCURRENT_REQUESTS = 6
HTTP_TIMEOUT = 10                          # seconds

# -----------------------------
# CACHE TTLs (configurable via .env)
# -----------------------------
KEYWORD_CACHE_TTL = int(os.getenv("MCP_KEYWORD_CACHE_TTL", 24 * 3600))   # 24 hours default
SUMMARY_CACHE_TTL = int(os.getenv("MCP_SUMMARY_CACHE_TTL", 4 * 3600))    # 4 hours default
BREAKING_NEWS_TTL = int(os.getenv("MCP_BREAKING_NEWS_TTL", 30 * 60))     # 30 minutes default

# -----------------------------
# EDITORIAL RSS FEEDS & BUCKETS
# -----------------------------
RSS_PER_FEED = 2
SCRAPE_TOP_N = 8                           # Scrape top 8 candidates
SOFT_SIM_THRESH = 0.3                      # Initial soft filter
HARD_SIM_THRESH = 0.4                      # Final hard filter
MIN_EDITORIAL_WORDS = 350                  # Prefer longer pieces

RSS_BUCKETS = {
    "india_opinion": [
        "https://indianexpress.com/section/opinion/feed/",
        "https://www.thehindu.com/opinion/editorial/feeder/default.rss",
        "https://www.livemint.com/rss/opinion",
        "https://www.deccanherald.com/rss/opinion",
        "https://www.tribuneindia.com/rss/feed/opinion"
    ],
    "global_opinion": [
        "https://www.theguardian.com/commentisfree/rss",
        "https://www.nytimes.com/svc/collections/v1/publish/https://www.nytimes.com/column/opinion/rss.xml",
        "https://www.washingtonpost.com/arcio/rss/?outputType=xml",
        "https://www.aljazeera.com/xml/rss/all.xml"
    ],
    "policy_journals": [
        "https://www.downtoearth.org.in/rss/section/opinion-101",
        "https://economictimes.indiatimes.com/rssfeeds/1977021501.cms",
        "https://www.orfonline.org/feed",
        "https://www.epw.in/rss/feed.xml",                          # EPW
        "https://frontline.thehindu.com/feeder/default.rss",        # Frontline
        "https://caravanmagazine.in/rss"                            # Caravan
    ]
}

# Source Reliability Weights (0.0 - 1.0)
SOURCE_RELIABILITY = {
    "The Hindu": 0.9,
    "The Indian Express": 0.9,
    "LiveMint": 0.85,
    "The Guardian": 0.85,
    "The New York Times": 0.85,
    "Washington Post": 0.85,
    "Down To Earth": 0.8,
    "Economic Times": 0.8,
    "Deccan Herald": 0.8,
    "The Tribune": 0.8,
    "ORF": 0.85,
    "EPW": 0.9,                       # Economic & Political Weekly
    "Frontline": 0.88,                # The Hindu Frontline
    "Caravan": 0.85,                  # Caravan Magazine
    "default": 0.6
}

EDITORIAL_QUALITY_WEIGHTS = {"embedding": 0.5, "source": 0.3, "length": 0.2}

