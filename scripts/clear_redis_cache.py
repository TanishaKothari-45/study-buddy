#!/usr/bin/env python3
"""
Clear Redis Cache Script

This script clears all data from the Redis cache database.
Use with caution - this will delete all cached data!
"""
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.utils.redis_client import get_redis_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_redis_cache():
    """Clear all data from Redis cache"""
    try:
        redis_client = get_redis_client()
        
        if redis_client is None:
            logger.error("❌ Redis is not enabled or not available")
            logger.info("💡 Make sure REDIS_ENABLED=true in your .env file")
            return False
        
        # Get info before clearing
        info = redis_client.info()
        db_size = info.get('db0', {}).get('keys', 0) if 'db0' in info else 0
        
        logger.info(f"📊 Current Redis database size: {db_size} keys")
        
        if db_size == 0:
            logger.info("✅ Redis cache is already empty")
            return True
        
        # Confirm before clearing
        logger.warning("⚠️  About to clear ALL Redis cache data!")
        response = input("Are you sure you want to continue? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            logger.info("❌ Cache clear cancelled")
            return False
        
        # Clear the database
        redis_client.flush_db()
        
        # Verify it's cleared
        info_after = redis_client.info()
        db_size_after = info_after.get('db0', {}).get('keys', 0) if 'db0' in info_after else 0
        
        logger.info(f"✅ Redis cache cleared successfully!")
        logger.info(f"📊 Keys before: {db_size}, Keys after: {db_size_after}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error clearing Redis cache: {e}")
        return False


if __name__ == "__main__":
    success = clear_redis_cache()
    sys.exit(0 if success else 1)

