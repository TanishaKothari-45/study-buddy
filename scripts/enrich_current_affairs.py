#!/usr/bin/env python3
"""
Enrich Current Affairs chunks with metadata (major_domain, sub_domain, difficulty, summary)
"""

import os
import sys
import logging
from pathlib import Path
from tqdm import tqdm
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).resolve().parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add backend to path
sys.path.insert(0, str(project_root / "backend"))

from app.utils.metadata_enricher import enrich_metadata
from app.utils.chroma_handler import ChromaHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION_NAME = "geography_docs_enriched"
BATCH_SIZE = 50  # Process in batches

def enrich_current_affairs_chunks():
    """Enrich only Current Affairs chunks (filtered by filename)"""
    chroma = ChromaHandler()
    chroma.switch_to_collection(COLLECTION_NAME)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        return
    client = OpenAI(api_key=api_key)

    # Get all documents
    logger.info("📥 Fetching all chunks...")
    all_docs = chroma.get_all_documents_paginated()
    logger.info(f"   ✅ Retrieved {len(all_docs)} total chunks")
    
    # Filter for Current Affairs chunks that are missing enrichment
    current_affairs_keywords = ["current affairs", "current_affairs"]
    docs_to_enrich = [
        d for d in all_docs
        if not d["metadata"].get("major_domain")  # Missing enrichment
        and any(
            keyword in d["metadata"].get("filename", "").lower()
            for keyword in current_affairs_keywords
        )
    ]
    
    logger.info(f"📚 Found {len(docs_to_enrich)} Current Affairs chunks missing enrichment")
    
    if not docs_to_enrich:
        logger.info("✅ All Current Affairs chunks already enriched!")
        return

    # Show filename distribution
    filenames = {}
    for doc in docs_to_enrich:
        filename = doc["metadata"].get("filename", "Unknown")
        filenames[filename] = filenames.get(filename, 0) + 1
    
    logger.info(f"\n📁 Current Affairs files to enrich:")
    for filename, count in sorted(filenames.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"   • {filename}: {count} chunks")

    # Enrich chunks
    enriched = []
    errors = []
    
    logger.info(f"\n🔄 Starting enrichment process...")
    for i, doc in enumerate(tqdm(docs_to_enrich, desc="Enriching Current Affairs chunks"), 1):
        try:
            text = doc["content"]
            filename = doc["metadata"].get("filename", "unknown")
            chapter = doc["metadata"].get("chapter", "unknown")
            section = doc["metadata"].get("section", "unknown")

            # Enrich metadata
            new_meta = enrich_metadata(text, filename, chapter, section, client)
            
            # Merge with existing metadata (don't overwrite existing fields)
            existing_meta = doc["metadata"].copy()
            existing_meta.update(new_meta)
            
            enriched.append({"id": doc["id"], "metadata": existing_meta})

            # Batch update
            if len(enriched) >= BATCH_SIZE:
                chroma.update_metadata_batch(enriched)
                logger.info(f"   ✅ Updated batch of {len(enriched)} chunks")
                enriched = []
                
        except Exception as e:
            logger.warning(f"⚠️ Error enriching chunk {i} ({doc.get('id', 'unknown')}): {e}")
            errors.append({"id": doc.get("id"), "error": str(e)})
            continue

    # Final batch update
    if enriched:
        chroma.update_metadata_batch(enriched)
        logger.info(f"   ✅ Updated final batch of {len(enriched)} chunks")

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info(f"✨ Enrichment Complete!")
    logger.info(f"{'='*80}")
    logger.info(f"✅ Successfully enriched: {len(docs_to_enrich) - len(errors)} chunks")
    if errors:
        logger.warning(f"⚠️ Errors: {len(errors)} chunks")
        logger.warning(f"   First few errors:")
        for err in errors[:5]:
            logger.warning(f"   • {err['id']}: {err['error']}")
    
    # Verify enrichment
    logger.info(f"\n🔍 Verifying enrichment...")
    all_docs_after = chroma.get_all_documents_paginated()
    ca_enriched = [
        d for d in all_docs_after
        if d["metadata"].get("major_domain")  # Has enrichment
        and any(
            keyword in d["metadata"].get("filename", "").lower()
            for keyword in current_affairs_keywords
        )
    ]
    logger.info(f"✅ Current Affairs chunks with enrichment: {len(ca_enriched)}")
    
    # Show sample enriched metadata
    if ca_enriched:
        logger.info(f"\n📋 Sample enriched metadata:")
        sample = ca_enriched[0]
        logger.info(f"   Filename: {sample['metadata'].get('filename')}")
        logger.info(f"   Major Domain: {sample['metadata'].get('major_domain')}")
        logger.info(f"   Sub Domain: {sample['metadata'].get('sub_domain')}")
        logger.info(f"   Difficulty: {sample['metadata'].get('difficulty')}")
        summary = sample['metadata'].get('summary', '')[:100]
        logger.info(f"   Summary: {summary}...")

if __name__ == "__main__":
    enrich_current_affairs_chunks()

