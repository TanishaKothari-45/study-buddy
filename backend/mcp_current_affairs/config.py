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
TIME_WINDOW_DAYS = 90                      # 3 months for better coverage
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
# CACHE TTLs
# -----------------------------
KEYWORD_CACHE_TTL = 24 * 3600              # 24 hours
SUMMARY_CACHE_TTL = 4 * 3600               # 4 hours
BREAKING_NEWS_TTL = 30 * 60                # 30 minutes

# -----------------------------
# EDITORIAL RSS FEEDS
# -----------------------------
RSS_FEEDS = [
    "https://indianexpress.com/section/opinion/feed/",
    "https://www.thehindu.com/opinion/editorial/feeder/default.rss",
    "https://www.livemint.com/rss/opinion"
]

