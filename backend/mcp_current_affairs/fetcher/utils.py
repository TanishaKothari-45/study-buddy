# fetcher/utils.py

import hashlib
from datetime import datetime, timedelta
from ..config import TIME_WINDOW_DAYS

def normalize_url(url: str) -> str:
    if not url: 
        return ""
    return url.split("?")[0].strip().lower()

def dedupe_articles(articles):
    seen = set()
    result = []
    for a in articles:
        url = normalize_url(a.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(a)
    return result

def within_time_window(published_at: str):
    try:
        dt = datetime.fromisoformat(published_at.replace("Z",""))
    except:
        return False
    return dt >= datetime.utcnow() - timedelta(days=TIME_WINDOW_DAYS)

