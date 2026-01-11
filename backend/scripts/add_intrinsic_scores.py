#!/usr/bin/env python3
"""
Script to add intrinsic_label and intrinsic_score to existing chunks in the database.

This script:
1. Retrieves all chunks from Pinecone/ChromaDB
2. Gets full content from content store (if available)
3. Classifies each chunk using LLM (gpt-4o-mini)
4. Updates metadata with intrinsic_label and intrinsic_score in both vector store and content store

Usage:
    # First, activate virtual environment:
    source ../venv/bin/activate  # or: source venv/bin/activate (if venv is in backend/)
    
    # Then run the script:
    python3 add_intrinsic_scores.py [--batch-size 10] [--limit 100] [--filename FILENAME]
    
    # Or use the helper script (recommended):
    ../run_add_intrinsic_scores.sh [--batch-size 10] [--limit 100] [--filename FILENAME]
    
Examples:
    # Process all chunks (default batch size 10)
    python3 add_intrinsic_scores.py
    
    # Process first 100 chunks only (for testing)
    python3 add_intrinsic_scores.py --limit 100
    
    # Process chunks from specific file
    python3 add_intrinsic_scores.py --filename "NCERT_Geography_Class_11.pdf"
    
    # Use larger batch size (faster but more API calls)
    python3 add_intrinsic_scores.py --batch-size 20
    
    # Skip content store update (only update vector store)
    python3 add_intrinsic_scores.py --skip-content-store
"""
import os
import sys
import argparse
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add backend directory to path (parent of scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.core.config import settings
from app.utils.intrinsic_scorer import classify_chunks_batch_intrinsic, LABEL_TO_SCORE
from app.utils.content_store import ContentStore
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_chunks_from_vector_store(vector_handler, limit: Optional[int] = None, 
                                 filename: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve chunks from vector store.
    
    Args:
        vector_handler: PineconeHandler or ChromaHandler instance
        limit: Maximum number of chunks to retrieve (None for all)
        filename: Optional filename filter (supports partial matching)
    
    Returns:
        List of chunk dicts with 'id', 'content', and 'metadata'
    """
    logger.info("📚 Retrieving chunks from vector store...")
    
    try:
        # For Pinecone with filename filter
        if filename and settings.USE_PINECONE:
            logger.info(f"   Filtering by filename: {filename} (partial match, case-insensitive)")
            
            # Try native method first (exact match only)
            if hasattr(vector_handler, 'fetch_all_chunks_native'):
                try:
                    chunks_exact = vector_handler.fetch_all_chunks_native(filename=filename)
                    logger.info(f"   Found {len(chunks_exact)} chunks with exact filename match")
                    
                    # Convert to expected format
                    formatted_chunks = []
                    for chunk in chunks_exact:
                        formatted_chunk = {
                            "id": chunk.get("id"),
                            "metadata": chunk.get("metadata", {}),
                            "content": chunk.get("metadata", {}).get("content_preview", "")
                        }
                        formatted_chunks.append(formatted_chunk)
                    chunks = formatted_chunks
                    
                    # If no exact match, try partial matching
                    if len(chunks) == 0:
                        logger.info("   No exact match found, trying partial match...")
                        # Use native method to get all chunks for partial matching
                        try:
                            all_chunks_raw = vector_handler.fetch_all_chunks_native(filename=None)
                            all_chunks = []
                            for chunk in all_chunks_raw:
                                formatted_chunk = {
                                    "id": chunk.get("id"),
                                    "metadata": chunk.get("metadata", {}),
                                    "content": chunk.get("metadata", {}).get("content_preview", "")
                                }
                                all_chunks.append(formatted_chunk)
                        except Exception as e:
                            logger.warning(f"   ⚠️ Native method failed for partial match: {e}, using fallback")
                            all_chunks = vector_handler.get_all_documents_paginated()
                        
                        chunks = [
                            c for c in all_chunks 
                            if filename.lower() in c.get("metadata", {}).get("filename", "").lower()
                        ]
                        logger.info(f"   Found {len(chunks)} chunks with partial filename match")
                    else:
                        logger.info(f"   ✅ Using exact match results")
                except Exception as e:
                    logger.warning(f"   ⚠️ Native method failed: {e}, using fallback")
                    try:
                        # Try to get all chunks using native method for partial matching
                        all_chunks_raw = vector_handler.fetch_all_chunks_native(filename=None)
                        all_chunks = []
                        for chunk in all_chunks_raw:
                            formatted_chunk = {
                                "id": chunk.get("id"),
                                "metadata": chunk.get("metadata", {}),
                                "content": chunk.get("metadata", {}).get("content_preview", "")
                            }
                            all_chunks.append(formatted_chunk)
                    except Exception as e2:
                        logger.warning(f"   ⚠️ Fallback native method also failed: {e2}, using get_all_documents_paginated")
                        all_chunks = vector_handler.get_all_documents_paginated()
                    
                    chunks = [
                        c for c in all_chunks 
                        if filename.lower() in c.get("metadata", {}).get("filename", "").lower()
                    ]
                    logger.info(f"   Found {len(chunks)} chunks with partial filename match")
            else:
                # Fallback: get all and filter
                logger.info("   Using fallback method (get all and filter)...")
                all_chunks = vector_handler.get_all_documents_paginated()
                chunks = [
                    c for c in all_chunks 
                    if filename.lower() in c.get("metadata", {}).get("filename", "").lower()
                ]
                logger.info(f"   Found {len(chunks)} chunks matching filename (partial match)")
        else:
            # No filename filter or ChromaDB
            if filename:
                logger.info(f"   Filtering by filename: {filename}")
                # Try native method first for Pinecone
                if settings.USE_PINECONE and hasattr(vector_handler, 'fetch_all_chunks_native'):
                    try:
                        all_chunks_raw = vector_handler.fetch_all_chunks_native(filename=None)
                        # Convert to expected format
                        all_chunks = []
                        for chunk in all_chunks_raw:
                            formatted_chunk = {
                                "id": chunk.get("id"),
                                "metadata": chunk.get("metadata", {}),
                                "content": chunk.get("metadata", {}).get("content_preview", "")
                            }
                            all_chunks.append(formatted_chunk)
                    except Exception as e:
                        logger.warning(f"   ⚠️ Native method failed: {e}, using fallback")
                        all_chunks = vector_handler.get_all_documents_paginated()
                else:
                    all_chunks = vector_handler.get_all_documents_paginated()
                
                # Support partial matching for filename
                chunks = [
                    c for c in all_chunks 
                    if filename.lower() in c.get("metadata", {}).get("filename", "").lower()
                ]
                logger.info(f"   Found {len(chunks)} chunks matching filename (partial match)")
            else:
                # No filename filter - use native method for Pinecone
                if settings.USE_PINECONE and hasattr(vector_handler, 'fetch_all_chunks_native'):
                    logger.info("   Using Pinecone native method to fetch all chunks...")
                    try:
                        chunks_raw = vector_handler.fetch_all_chunks_native(filename=None)
                        # Convert to expected format
                        chunks = []
                        for chunk in chunks_raw:
                            formatted_chunk = {
                                "id": chunk.get("id"),
                                "metadata": chunk.get("metadata", {}),
                                "content": chunk.get("metadata", {}).get("content_preview", "")
                            }
                            chunks.append(formatted_chunk)
                        logger.info(f"   ✅ Retrieved {len(chunks)} total chunks using native method")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Native method failed: {e}, using fallback")
                        chunks = vector_handler.get_all_documents_paginated()
                        logger.info(f"   Retrieved {len(chunks)} total chunks using fallback method")
                else:
                    chunks = vector_handler.get_all_documents_paginated()
                    logger.info(f"   Retrieved {len(chunks)} total chunks")
        
        if not chunks:
            logger.warning("   ⚠️ No chunks found!")
            if filename:
                logger.info("   💡 Tip: Try listing available filenames first:")
                logger.info("      python3 add_intrinsic_scores.py --list-filenames")
            return []
        
        # Apply limit if specified
        if limit:
            chunks = chunks[:limit]
            logger.info(f"   Limited to {len(chunks)} chunks")
        
        # Filter out chunks that already have intrinsic_score and intrinsic_label
        chunks_to_process = [
            chunk for chunk in chunks
            if "intrinsic_score" not in chunk.get("metadata", {}) 
            or "intrinsic_label" not in chunk.get("metadata", {})
        ]
        
        already_scored = len(chunks) - len(chunks_to_process)
        if already_scored > 0:
            logger.info(f"   ⏭️ Skipping {already_scored} chunks that already have intrinsic_score and intrinsic_label")
        
        logger.info(f"   ✅ {len(chunks_to_process)} chunks need processing")
        return chunks_to_process
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve chunks: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def enrich_chunks_with_content_store(chunks: List[Dict[str, Any]], 
                                     content_store: ContentStore) -> List[Dict[str, Any]]:
    """
    Enrich chunks with full content from content store.
    
    Args:
        chunks: List of chunk dicts (may have preview content only)
        content_store: ContentStore instance
    
    Returns:
        List of chunks with full content from content store
    """
    logger.info("💾 Enriching chunks with full content from content store...")
    
    enriched_count = 0
    preview_count = 0
    
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        chunk_id = metadata.get("chunk_id")
        filename = metadata.get("filename")
        chapter = metadata.get("chapter")
        
        # Try to get full content from content store
        if chunk_id and filename:
            try:
                full_content = content_store.get_chunk(
                    chunk_id=chunk_id,
                    filename=filename,
                    chapter=chapter
                )
                
                if full_content and len(full_content.strip()) > 0:
                    # Use full content for classification (more accurate)
                    chunk["content"] = full_content
                    enriched_count += 1
                else:
                    # Fallback to preview content
                    preview_content = chunk.get("content", "")
                    if not preview_content:
                        # Try metadata preview
                        preview_content = metadata.get("content_preview", "")
                    chunk["content"] = preview_content
                    preview_count += 1
            except Exception as e:
                logger.debug(f"   ⚠️ Content store lookup failed for {chunk_id}: {e}")
                # Use preview content
                preview_content = chunk.get("content", "")
                if not preview_content:
                    preview_content = metadata.get("content_preview", "")
                chunk["content"] = preview_content
                preview_count += 1
        else:
            # No chunk_id, use preview content
            preview_content = chunk.get("content", "")
            if not preview_content:
                preview_content = metadata.get("content_preview", "")
            chunk["content"] = preview_content
            preview_count += 1
    
    logger.info(f"   ✅ Enriched {enriched_count} chunks from content store")
    logger.info(f"   📄 Using preview content for {preview_count} chunks")
    
    return chunks


def update_vector_store_metadata(vector_handler, chunks_with_scores: List[Dict[str, Any]]):
    """
    Update metadata in vector store with intrinsic_label and intrinsic_score.
    
    Args:
        vector_handler: PineconeHandler or ChromaHandler instance
        chunks_with_scores: List of chunks with intrinsic_label and intrinsic_score in metadata
    """
    logger.info("💾 Updating metadata in vector store...")
    
    if settings.USE_PINECONE:
        # Pinecone: Update metadata using update_document_metadata
        updated_count = 0
        for chunk in chunks_with_scores:
            chunk_id = chunk.get("id")
            metadata = chunk.get("metadata", {})
            intrinsic_label = metadata.get("intrinsic_label")
            intrinsic_score = metadata.get("intrinsic_score")
            
            if chunk_id and intrinsic_score is not None and intrinsic_label is not None:
                try:
                    vector_handler.update_document_metadata(
                        chunk_id=chunk_id,
                        new_metadata={
                            "intrinsic_label": intrinsic_label,
                            "intrinsic_score": intrinsic_score
                        }
                    )
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Failed to update {chunk_id}: {e}")
        
        logger.info(f"   ✅ Updated {updated_count}/{len(chunks_with_scores)} chunks in Pinecone")
    else:
        # ChromaDB: Use batch update
        try:
            # Prepare data for batch update
            docs_to_update = [
                {
                    "id": chunk.get("id"),
                    "metadata": chunk.get("metadata", {})
                }
                for chunk in chunks_with_scores
            ]
            
            # Use update_metadata_batch if available, otherwise update individually
            if hasattr(vector_handler, 'update_metadata_batch'):
                vector_handler.update_metadata_batch(docs_to_update)
                logger.info(f"   ✅ Updated {len(docs_to_update)} chunks in ChromaDB (batch)")
            else:
                # Fallback: update individually
                updated_count = 0
                for doc in docs_to_update:
                    try:
                        vector_handler.collection.update(
                            ids=[doc["id"]],
                            metadatas=[doc["metadata"]]
                        )
                        updated_count += 1
                    except Exception as e:
                        logger.warning(f"   ⚠️ Failed to update {doc['id']}: {e}")
                
                logger.info(f"   ✅ Updated {updated_count}/{len(docs_to_update)} chunks in ChromaDB")
        except Exception as e:
            logger.error(f"   ❌ Failed to update ChromaDB: {e}")
            import traceback
            logger.error(traceback.format_exc())


def update_content_store_metadata(content_store: ContentStore, 
                                 chunks_with_scores: List[Dict[str, Any]]):
    """
    Update metadata in content store with intrinsic_label and intrinsic_score.
    
    Args:
        content_store: ContentStore instance
        chunks_with_scores: List of chunks with intrinsic_label and intrinsic_score in metadata
    """
    logger.info("💾 Updating metadata in content store...")
    
    updated_count = 0
    for chunk in chunks_with_scores:
        metadata = chunk.get("metadata", {})
        chunk_id = metadata.get("chunk_id")
        filename = metadata.get("filename")
        chapter = metadata.get("chapter")
        intrinsic_label = metadata.get("intrinsic_label")
        intrinsic_score = metadata.get("intrinsic_score")
        
        if chunk_id and filename and intrinsic_score is not None and intrinsic_label is not None:
            try:
                # Update metadata in content store
                content_store.update_chunk_metadata(
                    chunk_id=chunk_id,
                    filename=filename,
                    new_metadata={
                        "intrinsic_label": intrinsic_label,
                        "intrinsic_score": intrinsic_score
                    },
                    chapter=chapter
                )
                updated_count += 1
            except Exception as e:
                logger.debug(f"   ⚠️ Failed to update content store for {chunk_id}: {e}")
    
    logger.info(f"   ✅ Updated {updated_count}/{len(chunks_with_scores)} chunks in content store")


def print_score_distribution(chunks_with_scores: List[Dict[str, Any]]):
    """Print distribution of intrinsic labels and scores."""
    label_counts = {}
    for chunk in chunks_with_scores:
        metadata = chunk.get("metadata", {})
        label = metadata.get("intrinsic_label", "UNKNOWN")
        score = metadata.get("intrinsic_score", 0.6)
        label_counts[label] = label_counts.get(label, {"count": 0, "score": score})
        label_counts[label]["count"] += 1
    
    logger.info("\n📊 Intrinsic Classification Distribution:")
    logger.info("=" * 70)
    
    # Sort by score (highest first)
    sorted_labels = sorted(
        label_counts.items(), 
        key=lambda x: x[1]["score"], 
        reverse=True
    )
    
    for label, data in sorted_labels:
        count = data["count"]
        score = data["score"]
        percentage = (count / len(chunks_with_scores)) * 100
        
        logger.info(f"   {label:30s} (score: {score:.1f}): {count:5d} chunks ({percentage:5.1f}%)")
    
    logger.info("=" * 70)
    logger.info(f"   Total chunks processed: {len(chunks_with_scores)}")


def list_available_filenames(vector_handler, limit: int = 50):
    """List available filenames in the vector store."""
    logger.info("📋 Listing available filenames in vector store...")
    
    try:
        filenames = set()
        
        # Try using native Pinecone method first (more reliable)
        if settings.USE_PINECONE and hasattr(vector_handler, 'fetch_all_chunks_native'):
            logger.info("   Using Pinecone native method to fetch chunks...")
            try:
                all_chunks = vector_handler.fetch_all_chunks_native(filename=None)  # Get all chunks
                logger.info(f"   ✅ Fetched {len(all_chunks)} chunks using native method")
                
                # Extract filenames from metadata
                for chunk in all_chunks:
                    metadata = chunk.get("metadata", {})
                    filename = metadata.get("filename")
                    if filename:
                        filenames.add(filename)
                        if len(filenames) >= limit:
                            break
                    
                    # Debug: show first chunk structure if no filenames found
                    if len(filenames) == 0 and len(all_chunks) > 0:
                        logger.debug(f"   🔍 Sample chunk metadata keys: {list(metadata.keys())}")
                        logger.debug(f"   🔍 Sample chunk metadata: {metadata}")
            except Exception as e:
                logger.warning(f"   ⚠️ Native method failed: {e}, trying fallback")
        
        # Fallback: use get_all_documents_paginated
        if len(filenames) == 0:
            logger.info("   Using get_all_documents_paginated() method...")
            all_chunks = vector_handler.get_all_documents_paginated()
            logger.info(f"   Retrieved {len(all_chunks)} chunks")
            
            if len(all_chunks) == 0:
                logger.warning("   ⚠️ No chunks retrieved from vector store!")
                return
            
            # Extract unique filenames
            for chunk in all_chunks[:limit * 10]:  # Check more chunks to find unique filenames
                metadata = chunk.get("metadata", {})
                filename = metadata.get("filename")
                
                # Debug first chunk structure
                if len(filenames) == 0:
                    logger.info(f"   🔍 First chunk structure:")
                    logger.info(f"      - Chunk keys: {list(chunk.keys())}")
                    logger.info(f"      - Metadata keys: {list(metadata.keys())}")
                    logger.info(f"      - Metadata sample: {dict(list(metadata.items())[:5])}")
                
                if filename:
                    filenames.add(filename)
                    if len(filenames) >= limit:
                        break
        
        if filenames:
            logger.info(f"\n📁 Found {len(filenames)} unique filenames (showing first {limit}):")
            logger.info("=" * 80)
            for i, filename in enumerate(sorted(filenames)[:limit], 1):
                logger.info(f"   {i:3d}. {filename}")
            logger.info("=" * 80)
            logger.info(f"\n💡 Tip: Use --filename with a partial match (case-insensitive)")
            logger.info(f"   Example: --filename 'Certificate' (will match any filename containing 'Certificate')")
        else:
            logger.warning("⚠️ No filenames found in chunks")
            logger.info("   💡 This might mean:")
            logger.info("      - Chunks don't have 'filename' in metadata")
            logger.info("      - Metadata structure is different than expected")
            logger.info("      - Try checking a sample chunk manually")
            
    except Exception as e:
        logger.error(f"❌ Failed to list filenames: {e}")
        import traceback
        logger.error(traceback.format_exc())


def main():
    parser = argparse.ArgumentParser(
        description="Add intrinsic scores to existing chunks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=10,
        help="Batch size for LLM classification (default: 10)"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=None,
        help="Limit number of chunks to process (for testing)"
    )
    parser.add_argument(
        "--filename",
        type=str,
        default=None,
        help="Filter chunks by filename (supports partial matching, case-insensitive)"
    )
    parser.add_argument(
        "--list-filenames",
        action="store_true",
        help="List available filenames in the database and exit"
    )
    parser.add_argument(
        "--skip-content-store",
        action="store_true",
        help="Skip updating content store (only update vector store)"
    )
    args = parser.parse_args()
    
    # Initialize handlers
    logger.info("🔧 Initializing handlers...")
    if settings.USE_PINECONE:
        from app.utils.pinecone_handler import PineconeHandler
        vector_handler = PineconeHandler()
        logger.info("   ✅ Using Pinecone")
    else:
        from app.utils.chroma_handler import ChromaHandler
        vector_handler = ChromaHandler()
        logger.info("   ✅ Using ChromaDB")
    
    # Handle list-filenames option
    if args.list_filenames:
        list_available_filenames(vector_handler, limit=50)
        return
    
    logger.info("🚀 Starting intrinsic score addition script...")
    logger.info(f"   Batch size: {args.batch_size}")
    logger.info(f"   Limit: {args.limit or 'all'}")
    if args.filename:
        logger.info(f"   Filename filter: {args.filename}")
    logger.info("")
    
    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        logger.error("   Please set OPENAI_API_KEY in your .env file")
        return
    
    # Initialize handlers
    logger.info("🔧 Initializing handlers...")
    if settings.USE_PINECONE:
        from app.utils.pinecone_handler import PineconeHandler
        vector_handler = PineconeHandler()
        logger.info("   ✅ Using Pinecone")
    else:
        from app.utils.chroma_handler import ChromaHandler
        vector_handler = ChromaHandler()
        logger.info("   ✅ Using ChromaDB")
    
    content_store = ContentStore()
    logger.info("   ✅ Content store initialized")
    
    openai_client = OpenAI(api_key=api_key)
    logger.info("   ✅ OpenAI client initialized")
    logger.info("")
    
    # Step 1: Get chunks from vector store
    chunks = get_chunks_from_vector_store(
        vector_handler, 
        limit=args.limit,
        filename=args.filename
    )
    
    if not chunks:
        logger.warning("⚠️ No chunks found or all chunks already have intrinsic_score")
        return
    
    logger.info("")
    
    # Step 2: Enrich with full content from content store
    chunks = enrich_chunks_with_content_store(chunks, content_store)
    logger.info("")
    
    # Step 3: Classify chunks and add intrinsic_score
    logger.info(f"🔍 Classifying {len(chunks)} chunks using LLM (gpt-4o-mini)...")
    logger.info(f"   This may take a while depending on batch size and number of chunks...")
    logger.info("")
    
    start_time = time.time()
    chunks_with_scores = classify_chunks_batch_intrinsic(
        chunks, 
        openai_client, 
        batch_size=args.batch_size
    )
    elapsed_time = time.time() - start_time
    
    logger.info("")
    logger.info(f"✅ Classification complete in {elapsed_time:.1f} seconds")
    logger.info(f"   Average: {elapsed_time/len(chunks_with_scores):.2f} seconds per chunk")
    logger.info("")
    
    # Step 4: Print score distribution
    print_score_distribution(chunks_with_scores)
    logger.info("")
    
    # Step 5: Update vector store
    update_vector_store_metadata(vector_handler, chunks_with_scores)
    logger.info("")
    
    # Step 6: Update content store (if not skipped)
    if not args.skip_content_store:
        update_content_store_metadata(content_store, chunks_with_scores)
        logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("✨ Intrinsic Score Addition Complete!")
    logger.info("=" * 60)
    logger.info(f"✅ Processed: {len(chunks_with_scores)} chunks")
    logger.info(f"⏱️  Time taken: {elapsed_time:.1f} seconds")
    logger.info("")
    logger.info("📝 Next steps:")
    logger.info("   • Intrinsic labels and scores are now stored in chunk metadata")
    logger.info("   • Combined scoring (0.8 * similarity + 0.2 * intrinsic) will be used in retrieval")
    logger.info("   • High-quality chunks (HIGH_GEOGRAPHY_CONTENT, score=0.9) will be preferred")
    logger.info("   • Low-quality chunks (LOW_GEOGRAPHY_CONTENT, score=0.6) will be deprioritized")
    logger.info("   • Garbage chunks (NOISE_OR_GARBAGE, score=0.1) will be heavily deprioritized")


if __name__ == "__main__":
    main()
