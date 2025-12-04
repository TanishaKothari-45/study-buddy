# fetcher/news_fetcher.py

import httpx
import asyncio
from ..config import (
    GNEWS_API_KEY, NEWSDATA_API_KEY, THENEWSAPI_KEY,
    ARTICLES_PER_QUERY, HTTP_TIMEOUT, MAX_CONCURRENT_REQUESTS
)
from .utils import normalize_url, within_time_window

sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

async def fetch_json(url, params, client):
    async with sem:
        try:
            r = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            return None
    return None


# -----------------------------
# GNEWS PRIMARY FETCH
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
        data = await fetch_json(url, params, client)
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
# NEWSDATA.IO FALLBACK
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
        data = await fetch_json(url, params, client)
        if not data or "results" not in data:
            return []

    out = []
    for a in data["results"]:
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
# THENEWSAPI FALLBACK
# -----------------------------
async def fetch_from_thenewsapi(query: str):
    if not THENEWSAPI_KEY:
        return []

    url = "https://api.thenewsapi.com/v1/news/all"
    params = {
        "api_token": THENEWSAPI_KEY,
        "language": "en",
        "search": query
    }

    async with httpx.AsyncClient() as client:
        data = await fetch_json(url, params, client)
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
# UNIVERSAL FETCH (GNews → NewsData → TheNewsAPI)
# -----------------------------
async def fetch_articles_for_query(query: str):
    # try GNews first
    articles = await fetch_from_gnews(query)
    if articles:
        return articles

    # fallback 1: NewsData.io
    articles = await fetch_from_newsdata(query)
    if articles:
        return articles

    # fallback 2: TheNewsAPI
    articles = await fetch_from_thenewsapi(query)
    return articles

