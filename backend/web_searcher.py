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

# Log configuration status at module load
logger.info(f"📁 [WEB] Cache file: {os.path.abspath(CACHE_PATH)}")
if SERPAPI_KEY:
    logger.info(f"✅ [WEB] SERPAPI_API_KEY found (length: {len(SERPAPI_KEY)})")
else:
    logger.warning("⚠️ [WEB] SERPAPI_API_KEY not found in environment - will use HTML fallback")

# Try to load cache
try:
    if os.path.exists(CACHE_PATH):
        _CACHE = json.load(open(CACHE_PATH, "r", encoding="utf-8"))
        # Clean up empty cache entries on load
        empty_count = 0
        for key in list(_CACHE.keys()):
            bullets = _CACHE[key].get("bullets", [])
            if not bullets or len(bullets) == 0:
                logger.debug(f"Removing empty cache entry for: {key[:50]}")
                del _CACHE[key]
                empty_count += 1
        if empty_count > 0:
            _save_cache()
            logger.info(f"🧹 [WEB] Cleaned {empty_count} empty cache entries on startup")
    else:
        _CACHE = {}
        logger.info(f"Cache file {CACHE_PATH} does not exist, starting fresh")
except Exception as e:
    logger.warning(f"Failed to load cache from {CACHE_PATH}: {e}, starting fresh")
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
    logger.info(f"📤 [WEB] SerpAPI request params: engine=google, q='{query}', num={max_results}")
    search = GoogleSearch(params)
    logger.info(f"🔄 [WEB] Executing SerpAPI search...")
    res = search.get_dict()
    logger.info(f"📥 [WEB] SerpAPI response received, processing results...")
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
    cached_bullets = []
    if key in _CACHE and (time.time() - _CACHE[key].get("timestamp", 0) < 60 * 60 * 24):
        cached_bullets = _CACHE[key].get("bullets", [])
        if cached_bullets and len(cached_bullets) > 0:
            logger.info(f"✅ [WEB] Using cached web results for: {topic[:80]} ({len(cached_bullets)} bullets)")
            return cached_bullets
        else:
            logger.warning(f"⚠️ [WEB] Cached results are empty for: {topic[:80]}, forcing fresh search")
            # Remove empty cache entry to force fresh search
            if key in _CACHE:
                del _CACHE[key]
                _save_cache()

    # Build search query: prioritize India + world + reports
    query = f"recent {topic} related latest Indian or world events and reports or summits or global bodies and conferences"
    logger.info(f"🔍 [WEB] Search query: '{query}'")
    results = []
    
    # Check SERPAPI_KEY availability
    if SERPAPI_KEY:
        logger.info(f"🗞️ [WEB] SERPAPI_KEY found, using SerpAPI for: {topic[:80]}")
        try:
            results = serpapi_search(query, max_results=8)
            logger.info(f"✅ [WEB] SerpAPI returned {len(results)} results")
        except Exception as e:
            logger.warning(f"⚠️ [WEB] SerpAPI search failed: {e}, falling back to HTML search")
            try:
                results = html_fallback_search(query, max_results=8)
                logger.info(f"✅ [WEB] HTML fallback returned {len(results)} results")
            except Exception as e2:
                logger.error(f"❌ [WEB] HTML fallback also failed: {e2}")
                results = []
    else:
        logger.warning(f"⚠️ [WEB] SERPAPI_API_KEY not found in environment, using HTML fallback for: {topic}")
        try:
            results = html_fallback_search(query, max_results=8)
            logger.info(f"✅ [WEB] HTML fallback returned {len(results)} results")
        except Exception as e:
            logger.error(f"❌ [WEB] HTML fallback failed: {e}")
            results = []

    bullets = []
    logger.info(f"📝 [WEB] Processing {len(results)} search results into bullets...")
    for i, r in enumerate(results):
        s = (r.get("snippet") or "").strip()
        if not s:
            logger.debug(f"   Result {i+1}: No snippet found, skipping")
            continue
        # Fast cleaning
        s = s.replace("\n", " ").strip()
        words = s.split()
        word_count = len(words)
        
        # Skip snippets that are too short (less than 8 words) - they're not meaningful
        if word_count < 8:
            logger.debug(f"   Result {i+1}: Too short ({word_count} words), skipping")
            continue
        
        # Trim to ~12-18 words for UPSC-style bullets
        if word_count > 18:
            bullet = " ".join(words[:18]) + "..."
        else:
            bullet = s
        
        bullets.append(bullet)
        logger.debug(f"   Result {i+1}: Added bullet ({min(word_count, 18)} words): {bullet[:60]}...")

        if len(bullets) >= max_points:
            break
    
    if len(bullets) == 0:
        logger.warning(f"⚠️ [WEB] No valid bullets extracted from {len(results)} search results")
    else:
        logger.info(f"✅ [WEB] Extracted {len(bullets)} bullets from {len(results)} results")

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
