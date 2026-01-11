"""
Dimension-based Relevance Filter

Uses sentence-transformers for local embedding-based filtering.
Filters articles by semantic similarity to their dimension.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# Lazy-load model to avoid import overhead
_model = None


def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("📦 Loading sentence-transformers model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("✅ Model loaded")
    return _model


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_SIMILARITY_THRESHOLD = 0.30  # Recommended starting point
MIN_ARTICLES_PER_DIMENSION = 1       # Always keep at least this many


# ============================================================================
# Core Filtering Functions
# ============================================================================

def compute_similarity_scores(
    articles: List[Dict[str, Any]],
    dimension_text: str
) -> List[Tuple[Dict[str, Any], float]]:
    """
    Compute cosine similarity between articles and dimension.
    
    Args:
        articles: List of article dicts with 'title' and 'description'
        dimension_text: Dimension name + description combined
    
    Returns:
        List of (article, similarity_score) tuples, sorted by score desc
    """
    if not articles:
        return []
    
    from sklearn.metrics.pairwise import cosine_similarity
    
    model = _get_model()
    
    # Build article texts (title + description)
    article_texts = []
    for a in articles:
        title = a.get("title", "") or ""
        description = a.get("description", "") or ""
        text = f"{title} {description}".strip()
        article_texts.append(text if text else "untitled article")
    
    # Encode all at once for efficiency
    article_embeddings = model.encode(article_texts, show_progress_bar=False)
    dimension_embedding = model.encode([dimension_text], show_progress_bar=False)
    
    # Compute similarities
    similarities = cosine_similarity(article_embeddings, dimension_embedding).flatten()
    
    # Pair articles with scores and sort
    scored = list(zip(articles, similarities.tolist()))
    scored.sort(key=lambda x: x[1], reverse=True)
    
    return scored


def soft_filter_articles(
    articles: List[Dict[str, Any]],
    dimension_text: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    min_keep: int = MIN_ARTICLES_PER_DIMENSION
) -> List[Dict[str, Any]]:
    """
    Filter articles by semantic similarity to dimension.
    
    Args:
        articles: List of article dicts
        dimension_text: Combined dimension name + description
        threshold: Minimum similarity score to keep (default: 0.30)
        min_keep: Minimum articles to keep even if below threshold
    
    Returns:
        Filtered list of articles with _similarity_score added
    """
    if not articles:
        return []
    
    scored = compute_similarity_scores(articles, dimension_text)
    
    # Filter by threshold
    passed = [(a, score) for a, score in scored if score >= threshold]
    
    # Fallback: if too few passed, keep top min_keep anyway
    if len(passed) < min_keep:
        logger.warning(f"⚠️ Only {len(passed)} articles above threshold {threshold}, keeping top {min_keep}")
        passed = scored[:min_keep]
    
    # Add score to metadata and return articles
    result = []
    for article, score in passed:
        article["_similarity_score"] = round(score, 4)
        result.append(article)
    
    return result


# ============================================================================
# Dimension-Aware Filtering
# ============================================================================

def filter_articles_by_dimensions(
    articles: List[Dict[str, Any]],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    min_keep_per_dimension: int = MIN_ARTICLES_PER_DIMENSION
) -> List[Dict[str, Any]]:
    """
    Filter all articles by their respective dimensions.
    
    Uses the _dimension and _dimension_description metadata attached
    to each article by the news fetcher.
    
    Args:
        articles: List of articles with dimension metadata
        threshold: Similarity threshold (default: 0.30)
        min_keep_per_dimension: Min articles per dimension (default: 1)
    
    Returns:
        Filtered list of articles
    """
    if not articles:
        return []
    
    # Group by dimension
    by_dimension: Dict[str, List[Dict[str, Any]]] = {}
    dimension_texts: Dict[str, str] = {}
    
    for article in articles:
        dim_name = article.get("_dimension", "Unknown")
        dim_desc = article.get("_dimension_description", "")
        
        if dim_name not in by_dimension:
            by_dimension[dim_name] = []
            dimension_texts[dim_name] = f"{dim_name} {dim_desc}".strip()
        
        by_dimension[dim_name].append(article)
    
    # Filter each dimension
    filtered = []
    total_before = len(articles)
    
    for dim_name, dim_articles in by_dimension.items():
        dim_text = dimension_texts[dim_name]
        
        before_count = len(dim_articles)
        filtered_articles = soft_filter_articles(
            articles=dim_articles,
            dimension_text=dim_text,
            threshold=threshold,
            min_keep=min_keep_per_dimension
        )
        after_count = len(filtered_articles)
        
        priority = dim_articles[0].get("_priority", "?") if dim_articles else "?"
        logger.info(f"   • {dim_name} [{priority}]: {before_count} → {after_count} articles")
        
        filtered.extend(filtered_articles)
    
    logger.info(f"🔍 Soft filter: {total_before} → {len(filtered)} articles (threshold={threshold})")
    
    return filtered


# ============================================================================
# Priority-Based Article Selection
# ============================================================================

# Articles to keep per priority level (asymmetric)
PRIORITY_TOP_N = {
    "high": 3,
    "medium": 2,
    "low": 1
}


def get_top_articles_per_dimension(
    articles: List[Dict[str, Any]],
    top_n: Optional[int] = None,
    use_priority: bool = True
) -> List[Dict[str, Any]]:
    """
    Get top articles per dimension, with priority-based asymmetric selection.
    
    Priority-based (default):
    - high: 3 articles
    - medium: 2 articles  
    - low: 1 article
    
    Args:
        articles: List of articles with _similarity_score and _priority
        top_n: Override to use uniform N for all dimensions (ignores priority)
        use_priority: If True, use priority-based counts (default)
    
    Returns:
        Top articles per dimension
    """
    # Group by dimension
    by_dimension: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        dim = article.get("_dimension", "Unknown")
        if dim not in by_dimension:
            by_dimension[dim] = []
        by_dimension[dim].append(article)
    
    # Select top from each dimension
    result = []
    for dim_name, dim_articles in by_dimension.items():
        # Sort by similarity score
        sorted_articles = sorted(
            dim_articles,
            key=lambda x: x.get("_similarity_score", 0),
            reverse=True
        )
        
        # Determine how many to keep
        if top_n is not None:
            # Uniform override
            n = top_n
        elif use_priority:
            # Priority-based asymmetric selection
            priority = sorted_articles[0].get("_priority", "medium") if sorted_articles else "medium"
            n = PRIORITY_TOP_N.get(priority, 2)
        else:
            n = 2  # Default fallback
        
        selected = sorted_articles[:n]
        result.extend(selected)
        
        priority = sorted_articles[0].get("_priority", "?") if sorted_articles else "?"
        logger.debug(f"   • {dim_name} [{priority}]: selected {len(selected)}/{len(dim_articles)}")
    
    return result


def select_articles_by_priority(
    dimension_priority: str,
    ranked_articles: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Select articles based on dimension priority.
    
    Args:
        dimension_priority: "high", "medium", or "low"
        ranked_articles: Articles sorted by relevance score
    
    Returns:
        Selected articles (3 for high, 2 for medium, 1 for low)
    """
    n = PRIORITY_TOP_N.get(dimension_priority, 2)
    return ranked_articles[:n]
