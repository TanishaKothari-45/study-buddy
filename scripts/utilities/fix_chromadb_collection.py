#!/usr/bin/env python3
"""
Fix ChromaDB collection metadata corruption issue.

This script exports all data from the corrupted collection, deletes it,
creates a fresh collection, and re-imports the data.
"""
import sys
from pathlib import Path

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import os
import logging
from backend.app.core.config import settings
from backend.app.utils.chroma_handler import ChromaHandler
from backend.app.utils.embedder import Embedder

# Disable telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_collection():
    """Export, delete, recreate, and re-import collection"""
    logger.info("=" * 80)
    logger.info("ChromaDB Collection Metadata Fix Script")
    logger.info("=" * 80)
    logger.info(f"Collection: {settings.COLLECTION_NAME}")
    logger.info(f"DB Directory: {settings.DB_DIR}")
    logger.info()
    
    # Create handler (this will fail on corrupted collection, but we'll handle it)
    try:
        handler = ChromaHandler()
        collection = handler.collection
    except AttributeError as e:
        if "dimensionality" in str(e).lower():
            logger.error(f"❌ Collection metadata corruption confirmed: {e}")
            logger.info("   Proceeding with fix...")
        else:
            raise
    
    # Try to get collection count (might fail)
    try:
        count = collection.count()
        logger.info(f"📊 Collection has {count} chunks")
    except Exception as e:
        logger.warning(f"⚠️ Could not get collection count: {e}")
        count = 0
    
    if count == 0:
        logger.info("✅ Collection is empty - no data to migrate")
        logger.info("   You can safely delete and recreate it")
        return
    
    logger.info()
    logger.info("Step 1: Exporting all documents from collection...")
    try:
        # Export all documents
        all_docs = handler.get_all_documents_paginated()
        logger.info(f"✅ Exported {len(all_docs)} documents")
        
        # Save to temporary file (optional - for backup)
        import json
        backup_file = settings.DB_DIR.parent / f"{settings.COLLECTION_NAME}_backup.json"
        with open(backup_file, 'w') as f:
            json.dump(all_docs, f, indent=2)
        logger.info(f"✅ Backup saved to: {backup_file}")
        
    except Exception as e:
        logger.error(f"❌ Failed to export documents: {e}")
        logger.error("   Cannot proceed without exporting data first")
        return
    
    logger.info()
    logger.info("Step 2: Deleting corrupted collection...")
    try:
        handler.client.delete_collection(name=settings.COLLECTION_NAME)
        logger.info(f"✅ Deleted corrupted collection: {settings.COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"❌ Failed to delete collection: {e}")
        return
    
    logger.info()
    logger.info("Step 3: Creating fresh collection...")
    try:
        handler.collection = handler.client.create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": settings.DISTANCE_METRIC}
        )
        logger.info(f"✅ Created fresh collection: {settings.COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"❌ Failed to create collection: {e}")
        return
    
    logger.info()
    logger.info("Step 4: Re-importing documents...")
    try:
        # Prepare chunks for re-import
        chunks_with_metadata = []
        for doc in all_docs:
            chunks_with_metadata.append({
                'content': doc['content'],
                'metadata': doc['metadata']
            })
        
        # Re-add documents
        handler.add_documents(chunks_with_metadata)
        logger.info(f"✅ Re-imported {len(chunks_with_metadata)} documents")
        
    except Exception as e:
        logger.error(f"❌ Failed to re-import documents: {e}")
        logger.error(f"   Backup is available at: {backup_file}")
        return
    
    logger.info()
    logger.info("=" * 80)
    logger.info("✅ Collection fix completed successfully!")
    logger.info(f"   • Exported: {len(all_docs)} documents")
    logger.info(f"   • Backup saved: {backup_file}")
    logger.info(f"   • Re-imported: {len(chunks_with_metadata)} documents")
    logger.info("=" * 80)

if __name__ == "__main__":
    try:
        fix_collection()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Script interrupted by user")
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


