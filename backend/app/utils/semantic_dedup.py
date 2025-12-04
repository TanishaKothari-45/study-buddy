"""
Semantic Deduplication using Embeddings
"""
import logging
import asyncio
from typing import List, Dict, Any, Set
import numpy as np

logger = logging.getLogger(__name__)


async def semantic_deduplicate(
    questions: List[Dict[str, Any]],
    embedder,
    threshold: float = 0.88
) -> List[Dict[str, Any]]:
    """
    Remove semantically similar questions using embeddings
    
    Args:
        questions: List of question dictionaries
        embedder: Embedder instance (from app.state.vector_handler.embedder)
        threshold: Cosine similarity threshold (0.88 = 88% similar)
    
    Returns:
        Deduplicated list of questions
    """
    if len(questions) <= 1:
        return questions
    
    logger.info(f"🔍 Semantic deduplication: {len(questions)} questions, threshold={threshold}")
    
    try:
        # Extract question texts
        texts = [q.get("question", "") for q in questions]
        
        # Batch embed all questions (single API call)
        logger.info(f"   📝 Embedding {len(texts)} questions...")
        # Run synchronous embedding in thread pool to avoid blocking event loop
        embeddings = await asyncio.to_thread(embedder.get_embeddings, texts)
        
        if not embeddings or len(embeddings) != len(questions):
            logger.warning("⚠️ Embedding failed, falling back to hash-based deduplication")
            return hash_based_deduplicate(questions)
        
        # Convert to numpy array for efficient computation
        embeddings_array = np.array(embeddings)
        
        # Compute pairwise cosine similarity (vectorized)
        # Normalize embeddings
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        normalized = embeddings_array / norms
        
        # Cosine similarity matrix (vectorized - much faster than nested loops)
        similarity_matrix = np.dot(normalized, normalized.T)
        
        # Find duplicates using vectorized operations
        # Create upper triangle mask (exclude diagonal and lower triangle)
        upper_triangle_mask = np.triu(np.ones_like(similarity_matrix, dtype=bool), k=1)
        
        # Find all pairs above threshold
        duplicate_mask = (similarity_matrix > threshold) & upper_triangle_mask
        duplicate_indices = np.argwhere(duplicate_mask)
        
        # For each duplicate pair, keep the one with longer explanation
        duplicates: Set[int] = set()
        duplicate_pairs = []
        
        for i, j in duplicate_indices:
            if i in duplicates or j in duplicates:
                continue
            
            # Keep the one with longer explanation (quality heuristic)
            exp_i = len(str(questions[i].get("explanation", "")))
            exp_j = len(str(questions[j].get("explanation", "")))
            
            worse_idx = i if exp_i < exp_j else j
            duplicates.add(worse_idx)
            duplicate_pairs.append((i, j, similarity_matrix[i][j]))

        
        # Log duplicate pairs
        if duplicate_pairs:
            logger.info(f"   🔍 Found {len(duplicate_pairs)} duplicate pairs:")
            for i, j, sim in duplicate_pairs[:3]:  # Show first 3
                q_i = questions[i].get("question", "")[:50]
                q_j = questions[j].get("question", "")[:50]
                logger.info(f"      - Q{i+1} ≈ Q{j+1} (similarity={sim:.3f})")
                logger.debug(f"        Q{i+1}: {q_i}...")
                logger.debug(f"        Q{j+1}: {q_j}...")
            if len(duplicate_pairs) > 3:
                logger.info(f"      - ... and {len(duplicate_pairs) - 3} more pairs")
        
        # Return non-duplicates
        unique = [q for i, q in enumerate(questions) if i not in duplicates]
        logger.info(f"   ✅ Removed {len(duplicates)} duplicates, {len(unique)} unique questions remain")
        
        return unique
    
    except Exception as e:
        logger.error(f"❌ Semantic deduplication failed: {e}")
        logger.warning("⚠️ Falling back to hash-based deduplication")
        return hash_based_deduplicate(questions)


def hash_based_deduplicate(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Simple hash-based deduplication (fallback)
    
    Removes exact duplicates based on first 100 chars of question text
    """
    seen = set()
    unique = []
    
    for q in questions:
        # Hash based on first 100 chars of question (case-insensitive, stripped)
        q_text = str(q.get("question", ""))[:100].lower().strip()
        q_hash = hash(q_text)
        
        if q_hash not in seen:
            seen.add(q_hash)
            unique.append(q)
    
    removed = len(questions) - len(unique)
    if removed > 0:
        logger.info(f"   ✅ Hash-based dedup: Removed {removed} exact duplicates")
    
    return unique


def simple_deduplicate_sync(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Synchronous simple deduplication (for backward compatibility)
    """
    return hash_based_deduplicate(questions)
