# fetcher/news_fetcher.py
"""
News fetcher with fallback sources and retry logic.
Priority: TheNewsAPI → NewsData → GNews
"""

import httpx
import asyncio
import time
from ..config import (
    GNEWS_API_KEY, NEWSDATA_API_KEY, THENEWSAPI_KEY,
    ARTICLES_PER_QUERY, HTTP_TIMEOUT, MAX_CONCURRENT_REQUESTS
)
from .utils import normalize_url, within_time_window
from ..metrics import metrics

sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


async def fetch_with_retry(url: str, params: dict, client: httpx.AsyncClient, max_retries: int = 1):
    """
    Fetch JSON with retry and exponential backoff.
    
    Args:
        url: API endpoint
        params: Query parameters
        client: httpx client
        max_retries: Number of retries (default: 1)
    
    Returns:
        JSON response or None
    """
    for attempt in range(max_retries + 1):
        async with sem:
            try:
                start = time.time()
                r = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
                latency = (time.time() - start) * 1000
                metrics.record_api_latency(latency)
                
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429:  # Rate limited
                    metrics.record_api_failure("rate_limited")
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                        continue
                else:
                    metrics.record_api_failure(f"http_{r.status_code}")
                    
            except httpx.TimeoutException:
                metrics.record_api_failure("timeout")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except Exception as e:
                metrics.record_api_failure(f"error_{type(e).__name__}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
    
    return None


# -----------------------------
# THENEWSAPI (PRIMARY)
# -----------------------------
async def fetch_from_thenewsapi(query: str):
    if not THENEWSAPI_KEY:
        return []

    url = "https://api.thenewsapi.com/v1/news/all"
    params = {
        "api_token": THENEWSAPI_KEY,
        "language": "en",
        "search": query,
        "limit": ARTICLES_PER_QUERY
    }

    async with httpx.AsyncClient() as client:
        data = await fetch_with_retry(url, params, client)
        if not data or "data" not in data:
            return []

    out = []
    for a in data["data"]:
        out.append({
            "source": a.get("source"),
            "title": a.get("title"),
            "description": a.get("description"),
            "content": a.get("snippet"),
            "url": a.get("url"),
            "published_at": a.get("published_at")
        })
    return out


# -----------------------------
# NEWSDATA.IO (FALLBACK 1)
# -----------------------------
async def fetch_from_newsdata(query: str):
    if not NEWSDATA_API_KEY:
        return []

    url = "https://newsdata.io/api/1/news"
    params = {
        "apikey": NEWSDATA_API_KEY,
        "q": query,
        "language": "en",
        "country": "in"
    }

    async with httpx.AsyncClient() as client:
        data = await fetch_with_retry(url, params, client)
        if not data or "results" not in data:
            return []

    out = []
    for a in data.get("results", []):
        out.append({
            "source": a.get("source_id"),
            "title": a.get("title"),
            "description": a.get("description"),
            "content": a.get("content"),
            "url": a.get("link"),
            "published_at": a.get("pubDate")
        })
    return out


# -----------------------------
# GNEWS (FALLBACK 2)
# -----------------------------
async def fetch_from_gnews(query: str):
    if not GNEWS_API_KEY:
        return []

    url = "https://gnews.io/api/v4/search"
    params = {
        "q": query,
        "lang": "en",
        "max": ARTICLES_PER_QUERY,
        "token": GNEWS_API_KEY
    }

    async with httpx.AsyncClient() as client:
        data = await fetch_with_retry(url, params, client)
        if not data or "articles" not in data:
            return []

    out = []
    for a in data["articles"]:
        out.append({
            "source": a.get("source", {}).get("name"),
            "title": a.get("title"),
            "description": a.get("description"),
            "content": a.get("content"),
            "url": a.get("url"),
            "published_at": a.get("publishedAt")
        })
    return out


# -----------------------------
# UNIVERSAL FETCH (TheNewsAPI → NewsData → GNews)
# -----------------------------
async def fetch_articles_for_query(query: str):
    """
    Fetch articles with fallback chain: TheNewsAPI → NewsData → GNews
    """
    # Primary: TheNewsAPI
    articles = await fetch_from_thenewsapi(query)
    if articles:
        metrics.record_source_used("thenewsapi")
        return articles

    # Fallback 1: NewsData.io
    articles = await fetch_from_newsdata(query)
    if articles:
        metrics.record_source_used("newsdata")
        return articles

    # Fallback 2: GNews
    articles = await fetch_from_gnews(query)
    if articles:
        metrics.record_source_used("gnews")
    
    return articles
