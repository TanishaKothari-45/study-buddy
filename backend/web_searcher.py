"""
web_searcher.py
Simple web search helper with SerpAPI (preferred) and HTML fallback.

Features:
- Uses SERPAPI if SERPAPI_API_KEY present (free quota possible depending on plan).
- Falls back to simple HTML search (Google result scraping via requests + BeautifulSoup) if not available.
- Caching: uses a local JSON cache (web_cache.json) to avoid repeated web calls.
- Optional summarization via OpenAI (controlled and limited).
"""

import os
import json
import time
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)
CACHE_PATH = os.getenv("WEB_CACHE_PATH", "web_cache.json")
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")  # optional
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # optional, only used for summarization

# Try to load cache
try:
    _CACHE = json.load(open(CACHE_PATH, "r", encoding="utf-8"))
except Exception:
    _CACHE = {}

def _save_cache():
    try:
        json.dump(_CACHE, open(CACHE_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Failed to save cache: {e}")

def serpapi_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Use serpapi (Google) search. Returns list of dicts: {'title','link','snippet','source','date'}
    """
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI key not configured")
    try:
        from serpapi import GoogleSearch
    except Exception as e:
        raise RuntimeError("serpapi package not installed") from e

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": max_results,
    }
    search = GoogleSearch(params)
    res = search.get_dict()
    results = []
    for item in res.get("organic_results", [])[:max_results]:
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet") or item.get("snippet_highlighted_words") or "",
            "source": item.get("displayed_link") or item.get("link"),
            "date": item.get("date")
        })
    return results

def html_fallback_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Simple HTML fallback: uses requests + bs4 to fetch Google results pages.
    NOTE: This is a brittle fallback and may return fewer results; it's only used if serpapi absent.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception as e:
        logger.warning("requests/bs4 not available for HTML fallback")
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StudyBuddy/1.0; +https://example.com/bot)"
    }
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={max_results}"
    try:
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for g in soup.select('.tF2Cxc')[:max_results]:
            title_tag = g.select_one('.DKV0Md')
            title = title_tag.get_text(strip=True) if title_tag else None
            link_tag = g.select_one('a')
            link = link_tag['href'] if link_tag and link_tag.has_attr('href') else None
            snippet_tag = g.select_one('.aCOpRe')
            snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
            results.append({"title": title, "link": link, "snippet": snippet, "source": link, "date": None})
        return results
    except Exception as e:
        logger.warning(f"HTML fallback search failed: {e}")
        return []

def fetch_current_points(
    topic: str,
    max_points: int = 3,
    use_summarize: bool = False
) -> List[str]:
    """
    Fetch short current-affairs bullets for `topic`.
    Results are cached in web_cache.json to reduce API calls.
    """
    if not topic:
        return []

    key = topic.lower().strip()
    if key in _CACHE and (time.time() - _CACHE[key].get("timestamp", 0) < 60 * 60 * 24):
        logger.info(f"Using cached web results for: {topic}")
        return _CACHE[key].get("bullets", [])

    # Build search query: prioritize India + world + reports
    query = f"recent {topic} India world reports summit IPCC NITI 2023 2024 2025 examples"
    results = []
    try:
        if SERPAPI_KEY:
            results = serpapi_search(query, max_results=8)
        else:
            results = html_fallback_search(query, max_results=8)
    except Exception as e:
        logger.warning(f"Search failed: {e}")
        results = html_fallback_search(query, max_results=8)

    bullets = []
    for r in results:
        s = (r.get("snippet") or "").strip()
        if not s:
            continue
        # Fast cleaning
        s = s.replace("\n", " ").strip()
        # Keep only meaningful short snippets
        if len(s.split()) < 8:
            bullets.append(s)
        else:
            # trim to ~12-18 words heuristically
            words = s.split()
            bullets.append(" ".join(words[:18]) + ("..." if len(words) > 18 else ""))

        if len(bullets) >= max_points:
            break

    # Optional summarization via OpenAI (use cautiously)
    if use_summarize and OPENAI_API_KEY and bullets:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            summarized = []
            for b in bullets:
                prompt = f"Summarise this into ≤14 words as a UPSC-style bullet: {b}"
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=30,
                    temperature=0
                )
                txt = resp.choices[0].message.content.strip()
                summarized.append(txt)
            bullets = summarized[:max_points]
        except Exception as e:
            logger.warning(f"OpenAI summarization failed or unavailable: {e}")

    # Save to cache
    _CACHE[key] = {"timestamp": time.time(), "query": query, "bullets": bullets, "results": results}
    _save_cache()
    logger.info(f"🗞️ Retrieved {len(bullets)} current-affairs bullets for '{topic}'")
    return bullets
