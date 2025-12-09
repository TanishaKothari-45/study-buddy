"""
Script to update existing Pinecone chunks with source_type and source_subtype metadata.

This script:
1. Queries all chunks from Pinecone
2. Detects source_type from filename
3. Updates metadata with source_type and source_subtype
4. Upserts updated chunks back to Pinecone
"""
import os
import sys
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add backend directory to path (parent of scripts/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.metadata_enricher import detect_source_type
from app.utils.pinecone_handler import PineconeHandler
from backend.app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_pinecone_chunks_with_source_type(batch_size: int = 100):
    """
    Update all Pinecone chunks with source_type and source_subtype metadata.
    
    Args:
        batch_size: Number of chunks to process in each batch
    """
    logger.info("🚀 Starting Pinecone metadata update for source_type...")
    
    # Initialize Pinecone handler
    try:
        pinecone_handler = PineconeHandler()
        logger.info("✅ Pinecone handler initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Pinecone handler: {e}")
        return
    
    # Query all chunks (using a broad query to get all chunks)
    logger.info("🔍 Querying all chunks from Pinecone...")
    
    try:
        # Get retriever
        retriever = pinecone_handler.get_retriever(
            search_type="similarity",
            k=1000,  # Get as many as possible
            use_content_store=False  # We don't need content store for this
        )
        
        # Try multiple query terms to get more chunks
        query_terms = [
            "geography", "physical", "human", "indian", "world",
            "climate", "monsoon", "agriculture", "drainage", "physiography"
        ]
        
        all_chunks = []
        seen_ids = set()
        
        for term in query_terms:
            docs = retriever.get_relevant_documents(term)
            for doc in docs:
                # Use chunk_id or id as unique identifier
                chunk_id = doc.metadata.get("chunk_id") or doc.metadata.get("id")
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(doc)
        
        logger.info(f"📊 Total unique chunks found: {len(all_chunks)}")
        
        if not all_chunks:
            logger.warning("⚠️ No chunks found. Make sure Pinecone index has data.")
            return
        
        # Process chunks in batches
        updated_count = 0
        skipped_count = 0
        
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(all_chunks) + batch_size - 1) // batch_size
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
            
            updated_batch = []
            for doc in batch:
                metadata = doc.metadata.copy()
                filename = metadata.get("filename", "")
                
                if not filename:
                    logger.warning(f"⚠️ Chunk missing filename, skipping: {metadata.get('chunk_id', 'unknown')}")
                    skipped_count += 1
                    continue
                
                # Detect source_type
                source_info = detect_source_type(filename)
                
                # Check if already has source_type (skip if already updated)
                if "source_type" in metadata:
                    if metadata["source_type"] == source_info["source_type"]:
                        skipped_count += 1
                        continue  # Already updated
                
                # Update metadata
                metadata.update(source_info)
                
                # Create chunk dict in format expected by add_documents
                updated_chunk = {
                    "content": doc.page_content,
                    "metadata": metadata
                }
                updated_batch.append(updated_chunk)
            
            # Upsert updated chunks back to Pinecone using PineconeHandler's method
            if updated_batch:
                try:
                    # Use PineconeHandler's add_documents method
                    pinecone_handler.add_documents(updated_batch, batch_size=len(updated_batch))
                    
                    updated_count += len(updated_batch)
                    logger.info(f"   ✅ Updated {len(updated_batch)} chunks in batch {batch_num}")
                    
                except Exception as e:
                    logger.error(f"   ❌ Failed to update batch {batch_num}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Update complete!")
        logger.info(f"   • Total chunks processed: {len(all_chunks)}")
        logger.info(f"   • Updated: {updated_count}")
        logger.info(f"   • Skipped (already updated or missing filename): {skipped_count}")
        logger.info(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"❌ Error during update: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Check if Pinecone is enabled
    if not settings.USE_PINECONE:
        logger.error("❌ Pinecone is not enabled. Set USE_PINECONE=true in config.")
        sys.exit(1)
    
    # Run update
    update_pinecone_chunks_with_source_type(batch_size=100)

