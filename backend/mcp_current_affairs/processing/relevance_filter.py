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
    
    try:
        # BATCH EMBEDDING CALL: Get all embeddings in one API request
        print(f"   🔢 Batch embedding: 1 topic + {len(article_texts)} articles...")
        all_texts = [topic_text] + article_texts
        
        all_embeddings = await asyncio.to_thread(
            embedder.get_embeddings, all_texts
        )
        
        if not all_embeddings or len(all_embeddings) < len(all_texts):
            print("⚠️ Failed to get batch embeddings, using keyword matching fallback")
            return _keyword_fallback(articles, topic_keywords)
        
        # Extract topic embedding (first one)
        topic_vec = all_embeddings[0]
        
        # Compute similarity for each article
        for i, article in enumerate(articles):
            article_vec = all_embeddings[i + 1]  # Offset by 1 (topic was first)
            
            if article_vec:
                similarity = cosine_similarity(topic_vec, article_vec)
                article["relevance_score"] = round(similarity, 3)
            else:
                article["relevance_score"] = 0.0
        
        print(f"   ✅ Batch embedding complete!")
        
    except Exception as e:
        print(f"⚠️ Batch embedding error: {e}, using fallback")
        return _keyword_fallback(articles, topic_keywords)
    
    return articles


def _keyword_fallback(
    articles: List[Dict[str, Any]], 
    keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Fallback: Score articles by keyword density if embeddings fail.
    """
    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        score = 0
        for kw in keywords:
            score += text.count(kw.lower())
        # Normalize to 0-1 range (rough approximation)
        article["relevance_score"] = min(1.0, score / max(len(keywords) * 2, 1))
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
