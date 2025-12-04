# fetcher/editorial_rss.py

import feedparser
from datetime import datetime, timedelta
from ..config import RSS_FEEDS, TIME_WINDOW_DAYS
from .utils import normalize_url

def fetch_editorial_rss():
    results = []
    cutoff = datetime.utcnow() - timedelta(days=TIME_WINDOW_DAYS)

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                published = None
                if hasattr(e, "published_parsed") and e.published_parsed:
                    published = datetime(*e.published_parsed[:6])
                else:
                    continue

                if published >= cutoff:
                    results.append({
                        "source": feed.feed.get("title"),
                        "title": e.title,
                        "description": e.get("summary"),
                        "content": e.get("summary"),
                        "url": e.link,
                        "published_at": published.isoformat(),
                    })
        except:
            continue

    return results
