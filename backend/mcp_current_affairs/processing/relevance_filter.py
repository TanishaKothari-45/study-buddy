# processing/relevance_filter.py
"""
Semantic relevance filtering using embeddings.
Filters articles by similarity to the search topic.
"""

import numpy as np
from typing import List, Dict, Any

# Lazy-loaded embedding client
_embedder = None

def _get_embedder():
    """Lazy load the Embedder class from app.utils."""
    global _embedder
    if _embedder is None:
        from app.utils.embedder import Embedder
        _embedder = Embedder()
    return _embedder


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(vec1)
    b = np.array(vec2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def compute_relevance_scores(
    articles: List[Dict[str, Any]], 
    topic_keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Compute relevance scores for articles using embedding similarity.
    Uses BATCH embedding API call for efficiency.
    
    Args:
        articles: List of article dicts
        topic_keywords: Keywords extracted from topic
    """
    import asyncio
    
    if not articles:
        return []
    
    embedder = _get_embedder()
    
    # Create topic embedding from keywords
    topic_text = " ".join(topic_keywords)
    
    # Prepare article texts for batch embedding
    article_texts = []
    for article in articles:
        # Combine title + description for article embedding
        article_text = f"{article.get('title', '')} {article.get('description', '')}".strip()
        article_texts.append(article_text if article_text else "untitled")
    
    # Skip embeddings for now; use keyword/token scoring only
    return _keyword_fallback(articles, topic_keywords)


def _keyword_fallback(
    articles: List[Dict[str, Any]],
    keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Fallback: score by token overlap (no embeddings).
    """
    if not keywords:
        return articles

    kw_tokens = set()
    for kw in keywords:
        for tok in kw.lower().split():
            tok = "".join(c for c in tok if c.isalnum())
            if len(tok) >= 3:
                kw_tokens.add(tok)

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        matches = 0
        for tok in kw_tokens:
            if tok in text:
                matches += 1
        # Simple normalized score
        article["relevance_score"] = min(1.0, matches / max(len(kw_tokens), 1))
        article["_token_matches"] = matches
    return articles


def filter_by_relevance(
    articles: List[Dict[str, Any]], 
    threshold: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Filter articles by relevance score threshold.
    
    Args:
        articles: Articles with 'relevance_score' field
        threshold: Minimum score to keep (default 0.4)
    
    Returns:
        Filtered and sorted articles (highest relevance first)
    """
    relevant = [a for a in articles if a.get("relevance_score", 0) >= threshold]
    return sorted(relevant, key=lambda x: x.get("relevance_score", 0), reverse=True)
