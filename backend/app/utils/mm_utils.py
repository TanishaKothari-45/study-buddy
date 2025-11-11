"""
MMR and diversity utilities for retrieval pipeline
"""
import logging
from typing import List, Dict
from random import shuffle

logger = logging.getLogger(__name__)


def enforce_source_diversity(chunks: List[Dict], max_per_file: int = 2) -> List[Dict]:
    """
    Ensure no file dominates retrieval. Limits number of chunks per filename.
    
    This prevents a single large document from dominating the retrieved context,
    ensuring better diversity across different sources.
    
    Args:
        chunks: List of chunk dicts with 'metadata' containing 'filename'
        max_per_file: Maximum chunks to keep per file (default: 2)
    
    Returns:
        List of chunks with enforced source diversity (shuffled)
    """
    if not chunks:
        return []
    
    file_map = {}
    for chunk in chunks:
        filename = chunk.get("metadata", {}).get("filename", "unknown")
        file_map.setdefault(filename, []).append(chunk)
    
    balanced = []
    for file, group in file_map.items():
        # Keep up to max_per_file chunks per file
        balanced.extend(group[:max_per_file])
        if len(group) > max_per_file:
            logger.debug(f"   📊 Limited {file}: {len(group)} → {max_per_file} chunks")
    
    # Shuffle to avoid file ordering bias
    shuffle(balanced)
    
    logger.info(f"✅ Source diversity enforced: {len(chunks)} → {len(balanced)} chunks across {len(file_map)} files")
    return balanced

