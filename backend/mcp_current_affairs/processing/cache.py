# processing/cache.py
"""
Redis caching with metrics tracking for MCP Current Affairs.
"""

import json
from ..config import SUMMARY_CACHE_TTL, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, REDIS_PREFIX
from ..metrics import metrics

# Lazy-loaded Redis client
_redis_client = None

def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST, 
            port=REDIS_PORT, 
            db=REDIS_DB, 
            password=REDIS_PASSWORD, 
            decode_responses=True
        )
    return _redis_client

def _full_key(key: str) -> str:
    return f"{REDIS_PREFIX}:{key}"

def get_cached_summary(key: str):
    """Get cached summary from Redis."""
    try:
        r = _get_redis_client()
        data = r.get(_full_key(key))
        if not data:
            metrics.record_cache_miss()
            return None
        metrics.record_cache_hit()
        return json.loads(data)
    except Exception as e:
        # Log or ignore - do not break pipeline
        print("cache get error:", e)
        metrics.record_cache_miss()
        return None

def set_cached_summary(key: str, value, ttl: int = SUMMARY_CACHE_TTL):
    """Set cached summary in Redis."""
    try:
        r = _get_redis_client()
        r.setex(_full_key(key), ttl, json.dumps(value))
    except Exception as e:
        print("cache set error:", e)
        return False
    return True
