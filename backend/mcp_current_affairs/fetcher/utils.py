# fetcher/utils.py

import hashlib
from datetime import datetime, timedelta
from ..config import TIME_WINDOW_DAYS

def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    - Remove protocol (http/https)
    - Remove trailing slashes
    - Remove query parameters (utm_*, etc.)
    - Lowercase domain and path
    """
    if not url: 
        return ""
    
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url.lower())
        # Extract domain + path, strip trailing slash
        normalized = f"{parsed.netloc}{parsed.path}".rstrip('/')
        return normalized
    except:
        # Fallback to simple query param removal
        return url.split("?")[0].strip().lower().rstrip('/')

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


def cheap_keyword_match(article: dict, keywords: list) -> tuple[bool, int]:
    """
    Fast substring matching in title and description.
    
    Returns:
        (has_match, match_count) - whether any keyword matches and how many
    """
    if not keywords:
        return True, 0
    
    # Combine title and description for matching
    text = (article.get("title", "") + " " + article.get("description", "")).lower()
    
    match_count = sum(1 for kw in keywords if kw.lower() in text)
    has_match = match_count > 0
    
    return has_match, match_count


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles (0.0 to 1.0).
    Uses normalized Levenshtein distance.
    """
    if not title1 or not title2:
        return 0.0
    
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()
    
    if t1 == t2:
        return 1.0
    
    distance = levenshtein_distance(t1, t2)
    max_len = max(len(t1), len(t2))
    
    if max_len == 0:
        return 0.0
    
    return 1.0 - (distance / max_len)


def select_top_candidates(articles: list, keywords: list, max_candidates: int = 8) -> list:
    """
    Smart selection of top N candidates using multi-factor scoring:
    - Recency score (newer = better)
    - Keyword match count (more matches = better)
    - Content availability (has description/summary = better)
    - Domain diversity (different sources = better)
    
    Args:
        articles: List of article dicts
        keywords: Extracted keywords for matching
        max_candidates: Maximum number to select (default 8)
    
    Returns:
        Top N candidates sorted by composite score
    """
    if not articles:
        return []
    
    from ..config import ARTICLE_TIME_WINDOW_DAYS
    
    scored_articles = []
    seen_domains = set()
    
    for article in articles:
        # Factor 1: Recency score (0.0 to 1.0)
        recency_score = 0.5  # Default for unknown dates
        pub_date = article.get("published_at")
        if pub_date:
            try:
                dt = datetime.fromisoformat(pub_date.replace("Z", ""))
                days_old = (datetime.utcnow() - dt).days
                days_old = max(0, days_old)
                
                # Normalize: newer = higher score
                if days_old <= ARTICLE_TIME_WINDOW_DAYS:
                    recency_score = 1.0 - (days_old / ARTICLE_TIME_WINDOW_DAYS)
                else:
                    recency_score = 0.0
            except:
                pass
        
        # Factor 2: Keyword match count
        _, match_count = cheap_keyword_match(article, keywords)
        keyword_score = min(match_count / len(keywords), 1.0) if keywords else 0.5
        
        # Factor 3: Content availability (has meaningful description)
        content = article.get("description", "") or article.get("content", "")
        content_score = 1.0 if len(content) > 100 else 0.5
        
        # Factor 4: Domain diversity bonus
        url = article.get("url", "")
        domain = ""
        if url:
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
            except:
                pass
        
        diversity_bonus = 0.0
        if domain and domain not in seen_domains:
            diversity_bonus = 0.2
            seen_domains.add(domain)
        
        # Composite score (weighted)
        composite_score = (
            0.3 * recency_score +
            0.4 * keyword_score +
            0.2 * content_score +
            0.1 + diversity_bonus  # Base 0.1 + up to 0.2 bonus
        )
        
        article["_selection_score"] = round(composite_score, 3)
        scored_articles.append(article)
    
    # Sort by composite score (descending) and take top N
    scored_articles.sort(key=lambda x: x.get("_selection_score", 0), reverse=True)
    
    return scored_articles[:max_candidates]
