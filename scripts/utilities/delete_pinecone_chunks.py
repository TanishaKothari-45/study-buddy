"""
Delete all chunks from Pinecone index
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

# Load environment variables
load_env_vars()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def delete_all_pinecone_chunks():
    """Delete all chunks from Pinecone index"""
    try:
        from pinecone import Pinecone
        
        # Get Pinecone API key
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            logger.error("❌ PINECONE_API_KEY not found in environment variables")
            return False
        
        # Get index name
        from backend.app.core.config import settings
        index_name = settings.PINECONE_INDEX_NAME
        
        logger.info(f"🔗 Connecting to Pinecone index: {index_name}")
        
        # Initialize Pinecone client
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(index_name)
        
        # Get stats before deletion
        try:
            stats = index.describe_index_stats()
            total_vectors = stats.get("total_vector_count", 0)
            logger.info(f"📊 Current index stats:")
            logger.info(f"   • Total vectors: {total_vectors}")
        except Exception as e:
            logger.warning(f"⚠️ Could not get index stats: {e}")
        
        # Confirm deletion
        logger.warning(f"\n⚠️  WARNING: This will delete ALL chunks from index '{index_name}'")
        logger.warning(f"   This action cannot be undone!")
        
        # Delete all vectors
        logger.info(f"\n🗑️  Deleting all vectors from index...")
        index.delete(delete_all=True)
        
        logger.info(f"✅ Successfully deleted all chunks from Pinecone index: {index_name}")
        
        # Verify deletion
        try:
            stats_after = index.describe_index_stats()
            remaining = stats_after.get("total_vector_count", 0)
            logger.info(f"📊 Index stats after deletion:")
            logger.info(f"   • Remaining vectors: {remaining}")
            if remaining == 0:
                logger.info(f"✅ Index is now empty - ready for fresh uploads")
        except Exception as e:
            logger.warning(f"⚠️ Could not verify deletion: {e}")
        
        return True
        
    except ImportError:
        logger.error("❌ Pinecone not installed. Please install: pip install pinecone-client")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to delete chunks: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = delete_all_pinecone_chunks()
    sys.exit(0 if success else 1)


