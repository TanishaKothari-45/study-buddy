"""
Script to update existing Content Store (SQLite) chunks with source_type and source_subtype metadata.

This script:
1. Reads all chunks from Content Store
2. Detects source_type from filename
3. Updates metadata with source_type and source_subtype
"""
import os
import sys
import logging
import sqlite3
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Add backend directory to path (parent of scripts/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.metadata_enricher import detect_source_type
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def update_content_store_chunks_with_source_type():
    """
    Update all Content Store chunks with source_type and source_subtype metadata.
    """
    logger.info("🚀 Starting Content Store metadata update for source_type...")
    
    # Get database path
    db_path = settings.DB_DIR / "content_store.db"
    
    if not db_path.exists():
        logger.warning(f"⚠️ Content Store database not found at {db_path}")
        logger.info("   Content Store will be initialized on first use.")
        return
    
    logger.info(f"📂 Content Store database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns exist, if not add them
        cursor.execute("PRAGMA table_info(chunks)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "source_type" not in columns:
            logger.info("   Adding source_type column...")
            cursor.execute("ALTER TABLE chunks ADD COLUMN source_type TEXT")
        
        if "source_subtype" not in columns:
            logger.info("   Adding source_subtype column...")
            cursor.execute("ALTER TABLE chunks ADD COLUMN source_subtype TEXT")
        
        # Create indexes if they don't exist
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_type ON chunks(source_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_subtype ON chunks(source_subtype)")
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        
        # Get all chunks
        cursor.execute("SELECT chunk_id, filename FROM chunks")
        all_chunks = cursor.fetchall()
        
        logger.info(f"📊 Found {len(all_chunks)} chunks in Content Store")
        
        if not all_chunks:
            logger.info("   No chunks to update.")
            conn.close()
            return
        
        # Process chunks
        updated_count = 0
        skipped_count = 0
        
        for chunk_id, filename in all_chunks:
            try:
                # Check if already has source_type
                cursor.execute("SELECT source_type FROM chunks WHERE chunk_id = ? AND filename = ?", 
                             (chunk_id, filename))
                result = cursor.fetchone()
                
                if result and result[0]:
                    # Already has source_type, verify it's correct
                    existing_source_type = result[0]
                    detected_info = detect_source_type(filename)
                    if existing_source_type == detected_info.get("source_type"):
                        skipped_count += 1
                        continue  # Already correct
                
                # Detect source_type
                source_info = detect_source_type(filename)
                
                # Update chunk
                cursor.execute("""
                    UPDATE chunks 
                    SET source_type = ?, source_subtype = ?
                    WHERE chunk_id = ? AND filename = ?
                """, (
                    source_info.get("source_type"),
                    source_info.get("source_subtype"),
                    chunk_id,
                    filename
                ))
                
                updated_count += 1
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to update chunk {chunk_id} ({filename}): {e}")
                continue
        
        conn.commit()
        conn.close()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Update complete!")
        logger.info(f"   • Total chunks: {len(all_chunks)}")
        logger.info(f"   • Updated: {updated_count}")
        logger.info(f"   • Skipped (already correct): {skipped_count}")
        logger.info(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"❌ Error during update: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Run update
    update_content_store_chunks_with_source_type()


