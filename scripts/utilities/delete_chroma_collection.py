"""
Delete the broken ChromaDB collection
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path (2 levels up from scripts/utilities/)
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.core.env import load_env_vars
from backend.app.utils.chroma_handler import ChromaHandler

# Load environment variables
load_env_vars()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def delete_all_collections():
    """Delete all ChromaDB collections"""
    try:
        logger.info("🗑️  Deleting all ChromaDB collections...")
        
        chroma_handler = ChromaHandler()
        
        # Get all collections
        collections = chroma_handler.client.list_collections()
        collection_names = [col.name for col in collections]
        
        if not collection_names:
            logger.info("ℹ️  No collections found to delete")
            return True
        
        logger.info(f"📋 Found {len(collection_names)} collections: {collection_names}")
        
        # Delete each collection
        deleted_count = 0
        for collection_name in collection_names:
            try:
                chroma_handler.delete_collection(collection_name)
                deleted_count += 1
                logger.info(f"   ✅ Deleted: {collection_name}")
            except Exception as e:
                logger.error(f"   ❌ Failed to delete {collection_name}: {e}")
        
        logger.info(f"✅ Successfully deleted {deleted_count}/{len(collection_names)} collections")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to delete collections: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def delete_collection(collection_name: str = "geography_docs_enriched"):
    """Delete the specified ChromaDB collection"""
    try:
        logger.info(f"🗑️  Deleting ChromaDB collection: {collection_name}")
        
        chroma_handler = ChromaHandler()
        chroma_handler.delete_collection(collection_name)
        
        logger.info(f"✅ Successfully deleted collection: {collection_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to delete collection: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Delete ChromaDB collection(s)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all collections"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Collection name to delete (default: geography_docs_enriched)"
    )
    
    args = parser.parse_args()
    
    if args.all:
        success = delete_all_collections()
    else:
        collection_name = args.collection or "geography_docs_enriched"
        success = delete_collection(collection_name)
    
    sys.exit(0 if success else 1)

