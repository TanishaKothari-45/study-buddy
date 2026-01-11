"""
text_processing.py

Shared utilities for text processing, chunking, and deduplication.
"""

import logging
import re
from typing import List, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def deduplicate_chunks(chunks: List[Any], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """
    Combine chunks while removing overlapping text portions using fuzzy matching.
    
    This is a safer, less aggressive approach that:
    - Uses fuzzy matching (SequenceMatcher) to handle slight variations
    - Requires minimum overlap (20 words) and similarity threshold (60%)
    - Works on any chunks, including strings and LangChain Document objects
    - Preserves content while removing redundant overlap
    
    Args:
        chunks: List of text chunks or Document objects to combine
        min_overlap_words: Minimum number of words to consider for overlap (default: 20)
        similarity_threshold: Minimum similarity ratio to consider overlap (default: 0.6)
        
    Returns:
        Combined text with overlapping portions removed
    """
    if not chunks:
        return ""
    
    # Pre-process chunks to ensure they are all strings
    processed_chunks = []
    for chunk in chunks:
        if hasattr(chunk, 'page_content'):
            processed_chunks.append(chunk.page_content)
        else:
            processed_chunks.append(str(chunk))
    
    if len(processed_chunks) == 1:
        return processed_chunks[0]
    
    combined = processed_chunks[0]
    overlap_removed_count = 0
    total_overlap_words = 0
    
    for i, next_chunk in enumerate(processed_chunks[1:], 1):
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

def count_words_excluding_visuals(text: str) -> int:
    """
    Count words in text, EXCLUDING all visual content:
    - Mermaid diagram blocks (```mermaid ... ```)
    - Map JSON blocks (```map-json ... ```)
    - Any code blocks (``` ... ```)
    - Base64 images (![...](data:image/...))
    - Inline base64 data strings
    
    This gives accurate word count for the actual prose content only.
    """
    if not text:
        return 0
        
    cleaned_text = text
    
    # Remove ```mermaid ... ``` blocks
    cleaned_text = re.sub(r'```mermaid[\s\S]*?```', '', cleaned_text)
    
    # Remove ```map-json ... ``` blocks
    cleaned_text = re.sub(r'```map-json[\s\S]*?```', '', cleaned_text)
    
    # Remove any other code blocks
    cleaned_text = re.sub(r'```[\s\S]*?```', '', cleaned_text)
    
    # Remove base64 images: ![alt](data:image/...) 
    cleaned_text = re.sub(r'!\[[^\]]*\]\(data:image[^\)]+\)', '', cleaned_text)
    
    # Remove any remaining base64 data strings
    cleaned_text = re.sub(r'data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+', '', cleaned_text)
    
    # Count words in remaining prose
    return len(cleaned_text.split())
