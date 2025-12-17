"""
text_processing.py

Shared utilities for text processing, chunking, and deduplication.
"""

import logging
import re
from typing import List
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def deduplicate_chunks(chunks: List[str], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """
    Combine chunks while removing overlapping text portions using fuzzy matching.
    
    This is a safer, less aggressive approach that:
    - Uses fuzzy matching (SequenceMatcher) to handle slight variations
    - Requires minimum overlap (20 words) and similarity threshold (60%)
    - Works on any chunks, not just split ones
    - Preserves content while removing redundant overlap
    
    Args:
        chunks: List of text chunks to combine (strings)
        min_overlap_words: Minimum number of words to consider for overlap (default: 20)
        similarity_threshold: Minimum similarity ratio to consider overlap (default: 0.6)
        
    Returns:
        Combined text with overlapping portions removed
    """
    if not chunks:
        return ""
    
    # Ensure all chunks are strings (handle LangChain Documents if passed by mistake)
    # The caller context_retriever handles abstraction but good to be safe.
    # Actually type hint says List[str].
    
    if len(chunks) == 1:
        return chunks[0]
    
    combined = chunks[0]
    overlap_removed_count = 0
    total_overlap_words = 0
    
    for i, next_chunk in enumerate(chunks[1:], 1):
        # Find overlap between tail of combined and head of next_chunk
        # Check up to 100 words or half of combined text (whichever is smaller)
        overlap_size = min(100, len(combined.split()) // 2, len(next_chunk.split()))
        
        if overlap_size < min_overlap_words:
            # Not enough text to check for overlap, just append
            combined += " " + next_chunk
            continue
        
        tail = " ".join(combined.split()[-overlap_size:])
        head = " ".join(next_chunk.split()[:overlap_size])
        
        # Fuzzy match overlap (case-insensitive)
        ratio = SequenceMatcher(None, tail.lower(), head.lower()).ratio()
        
        if ratio > similarity_threshold:
            # Found overlap - remove overlapping part from next_chunk
            overlap_end = int(len(head.split()) * ratio)
            if overlap_end > 0:
                next_chunk_cleaned = " ".join(next_chunk.split()[overlap_end:])
                combined += " " + next_chunk_cleaned
                overlap_removed_count += 1
                total_overlap_words += overlap_end
                logger.debug(f"      → Removed ~{overlap_end} overlapping words between chunk {i} and {i+1} (similarity: {ratio:.2f})")
            else:
                # Overlap too small, keep as-is
                combined += " " + next_chunk
        else:
            # No significant overlap found, keep as-is
            combined += " " + next_chunk
    
    if overlap_removed_count > 0:
        logger.debug(f"   → Removed overlap from {overlap_removed_count} chunk pairs (~{total_overlap_words} words total)")
    
    # Final cleanup of whitespace
    return re.sub(r'\s+', ' ', combined).strip()
