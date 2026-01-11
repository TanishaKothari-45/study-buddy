"""
Redis Client - Connection management and basic operations
"""
import os
import logging
import redis
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper with connection pooling"""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = 0,
        password: str = None,
        decode_responses: bool = True,
        max_connections: int = 50
    ):
        """
        Initialize Redis client
        
        Args:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            db: Redis database number (default: 0)
            password: Redis password (optional)
            decode_responses: Decode responses to strings (default: True)
            max_connections: Max connections in pool (default: 50)
        """
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db or int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD")
        
        # Create connection pool
        self.pool = redis.ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=decode_responses,
            max_connections=max_connections,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        
        self.client = redis.Redis(connection_pool=self.pool)
        self._test_connection()
    
    def _test_connection(self):
        """Test Redis connection on initialization"""
        try:
            self.client.ping()
            logger.info(f"✅ Redis connected: {self.host}:{self.port} (db={self.db})")
        except redis.ConnectionError as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        try:
            return self.client.get(key)
        except redis.RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None
    
    def set(
        self,
        key: str,
        value: str,
        ex: int = None,
        nx: bool = False
    ) -> bool:
        """
        Set key-value pair
        
        Args:
            key: Key name
            value: Value to store
            ex: Expiration time in seconds (optional)
            nx: Only set if key doesn't exist (default: False)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.client.set(key, value, ex=ex, nx=nx)
        except redis.RedisError as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        try:
            return self.client.delete(*keys)
        except redis.RedisError as e:
            logger.error(f"Redis DELETE error: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.client.exists(key))
        except redis.RedisError as e:
            logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False
    
    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment key by amount"""
        try:
            return self.client.incr(key, amount)
        except redis.RedisError as e:
            logger.error(f"Redis INCR error for key '{key}': {e}")
            return None
    
    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key"""
        try:
            return self.client.expire(key, seconds)
        except redis.RedisError as e:
            logger.error(f"Redis EXPIRE error for key '{key}': {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """Get time-to-live for key (in seconds)"""
        try:
            return self.client.ttl(key)
        except redis.RedisError as e:
            logger.error(f"Redis TTL error for key '{key}': {e}")
            return -2  # Key doesn't exist
    
    def keys(self, pattern: str = "*") -> list:
        """Get all keys matching pattern (use cautiously in production)"""
        try:
            return self.client.keys(pattern)
        except redis.RedisError as e:
            logger.error(f"Redis KEYS error for pattern '{pattern}': {e}")
            return []
    
    def flush_db(self):
        """Flush current database (use with caution!)"""
        try:
            self.client.flushdb()
            logger.warning("⚠️  Redis database flushed")
        except redis.RedisError as e:
            logger.error(f"Redis FLUSHDB error: {e}")
    
    def info(self) -> dict:
        """Get Redis server info"""
        try:
            return self.client.info()
        except redis.RedisError as e:
            logger.error(f"Redis INFO error: {e}")
            return {}
    
    def close(self):
        """Close connection pool"""
        self.pool.disconnect()
        logger.info("Redis connection pool closed")

    # ============================================================
    # LIST OPERATIONS & PIPELINE
    # ============================================================
    
    def pipeline(self, transaction: bool = True, shard_hint: str = None):
        """Get a pipeline object"""
        return self.client.pipeline(transaction=transaction, shard_hint=shard_hint)
        
    def lpush(self, key: str, *values: str) -> Optional[int]:
        """Prepend values to list"""
        try:
            return self.client.lpush(key, *values)
        except redis.RedisError as e:
            logger.error(f"Redis LPUSH error for key '{key}': {e}")
            return None
            
    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to range"""
        try:
            return self.client.ltrim(key, start, end)
        except redis.RedisError as e:
            logger.error(f"Redis LTRIM error for key '{key}': {e}")
            return False
            
    def lrange(self, key: str, start: int, end: int) -> list:
        """Get range of elements from list"""
        try:
            return self.client.lrange(key, start, end)
        except redis.RedisError as e:
            logger.error(f"Redis LRANGE error for key '{key}': {e}")
            return []


# Global singleton instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> Optional[RedisClient]:
    """
    Get singleton Redis client instance
    
    Returns None if Redis is not configured (graceful degradation)
    """
    global _redis_client
    
    if _redis_client is None:
        # Check if Redis is configured
        redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
        
        if not redis_enabled:
            logger.warning("⚠️  Redis is disabled (REDIS_ENABLED=false)")
            return None
        
        try:
            _redis_client = RedisClient()
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis client: {e}")
            return None
    
    return _redis_client


def close_redis_client():
    """Close global Redis client"""
    global _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
