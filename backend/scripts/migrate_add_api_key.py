"""
Database Migration: Add encrypted_gemini_api_key column to users table

Run this script to update your existing database schema.
"""
import sys
from pathlib import Path

# Add backend directory to path (parent of scripts/)
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.core.database import engine, SessionLocal
from app.models.user import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add encrypted_gemini_api_key column to users table if it doesn't exist"""
    
    logger.info("=" * 70)
    logger.info("🔄 Starting database migration...")
    logger.info("=" * 70)
    
    try:
        with engine.connect() as conn:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "encrypted_gemini_api_key" in columns:
                logger.info("✅ Column 'encrypted_gemini_api_key' already exists - skipping migration")
                return
            
            # Add the column
            logger.info("📝 Adding 'encrypted_gemini_api_key' column to users table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN encrypted_gemini_api_key TEXT"))
            conn.commit()
            
            logger.info("✅ Migration completed successfully!")
            logger.info("=" * 70)
            logger.info("📌 IMPORTANT: Set ENCRYPTION_KEY in your .env file")
            logger.info("   Generate one with:")
            logger.info("   python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
            logger.info("=" * 70)
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate()
