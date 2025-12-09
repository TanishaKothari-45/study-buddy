"""
Delete all chunks from SQLite content store database.

This script clears all chunks from the content_store.db database.
Use this when you want to re-upload files with updated metadata.
"""
import sqlite3
import logging
from pathlib import Path
import sys

# Add backend directory to path (parent of scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def delete_all_chunks():
    """Delete all chunks from content store database"""
    db_path = settings.DB_DIR / "content_store.db"
    
    if not db_path.exists():
        logger.warning(f"⚠️ Content store database not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM chunks")
        count_before = cursor.fetchone()[0]
        
        logger.info(f"📊 Current chunks in database: {count_before}")
        
        if count_before == 0:
            logger.info("✅ Database is already empty")
            conn.close()
            return
        
        # Confirm deletion (skip if --yes flag provided)
        import sys
        skip_confirmation = '--yes' in sys.argv or '-y' in sys.argv
        
        if not skip_confirmation:
            logger.warning(f"⚠️ About to delete {count_before} chunks from content store")
            response = input("Are you sure you want to delete all chunks? (yes/no): ")
            
            if response.lower() != 'yes':
                logger.info("❌ Deletion cancelled")
                conn.close()
                return
        else:
            logger.info(f"⚠️ Deleting {count_before} chunks (--yes flag provided)")
        
        # Delete all chunks
        cursor.execute("DELETE FROM chunks")
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Successfully deleted {deleted_count} chunks from content store")
        logger.info(f"   Database: {db_path}")
        
    except Exception as e:
        logger.error(f"❌ Failed to delete chunks: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    delete_all_chunks()

