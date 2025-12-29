"""
Cache Manager - High-level caching logic for answers, news, and maps

Caching Strategy:
1. Answer Cache: Exact match on (question + word_count + model_version)
2. News Cache: Exact match on (parsed_keywords + time_range)
3. Map Cache: Exact match on (map_json_spec)
"""
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cache TTLs (in seconds)
TTL_ANSWER = 7 * 24 * 60 * 60  # 7 days
TTL_NEWS = 60 * 60  # 1 hour
TTL_MAP = 30 * 24 * 60 * 60  # 30 days
TTL_LOCK = 30  # 30 seconds for dogpile protection


class CacheManager:
    """Manages caching for different components"""
    
    def __init__(self, namespace_prefix: str = "study_buddy"):
        """
        Initialize cache manager
        
        Args:
            namespace_prefix: Prefix for all cache keys (default: "study_buddy")
        """
        self.redis = get_redis_client()
        self.prefix = namespace_prefix
        self.enabled = self.redis is not None
        
        if not self.enabled:
            logger.warning("⚠️  Cache disabled (Redis not available)")
    
    def _make_key(self, namespace: str, identifier: str) -> str:
        """Create cache key with namespace"""
        return f"{self.prefix}:{namespace}:{identifier}"
    
    def _hash_dict(self, data: dict) -> str:
        """Create consistent hash from dictionary"""
        # Sort keys for consistency
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]
    
    def _hash_string(self, text: str) -> str:
        """Create hash from string"""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    # ============================================================
    # ANSWER CACHE
    # ============================================================
    
    def get_answer_cache_key(
        self,
        question: str,
        word_count: int,
        model_version: str = "gemini-2.5-pro-v1"
    ) -> str:
        """
        Generate cache key for answer
        
        Args:
            question: The question text (normalized)
            word_count: Target word count
            model_version: Model version string
        
        Returns:
            Cache key string
        """
        # Normalize question (lowercase, strip whitespace)
        normalized_q = question.lower().strip()
        
        # Create composite hash
        composite = f"{normalized_q}|{word_count}|{model_version}"
        hash_id = self._hash_string(composite)
        
        return self._make_key("answer", f"{model_version}:{hash_id}")
    
    def get_cached_answer(
        self,
        question: str,
        word_count: int,
        model_version: str = "gemini-2.5-pro-v1"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached answer if exists
        
        Returns:
            Cached answer dict or None
        """
        if not self.enabled:
            return None
        
        cache_key = self.get_answer_cache_key(question, word_count, model_version)
        
        try:
            cached_json = self.redis.get(cache_key)
            if cached_json:
                data = json.loads(cached_json)
                logger.info(f"✅ Answer cache HIT: {cache_key}")
                
                # Increment hit count
                data.setdefault("hit_count", 0)
                data["hit_count"] += 1
                self.redis.set(cache_key, json.dumps(data), ex=TTL_ANSWER)
                
                return data
            else:
                logger.info(f"❌ Answer cache MISS: {cache_key}")
                return None
        except Exception as e:
            logger.error(f"Error reading answer cache: {e}")
            return None
    
    def set_cached_answer(
        self,
        question: str,
        word_count: int,
        answer: str,
        sources: List[Dict[str, Any]],
        model_version: str = "gemini-2.5-pro-v1",
        compressed_answer: Optional[str] = None,
        word_count_actual: Optional[int] = None,
        word_count_compressed: Optional[int] = None
    ) -> bool:
        """
        Store answer in cache
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        cache_key = self.get_answer_cache_key(question, word_count, model_version)
        
        cache_value = {
            # Store compressed answer as primary to avoid recompressing on read
            "answer": compressed_answer or answer,
            "sources": sources,
            "question": question,
            "word_count": word_count,
            "word_count_actual": word_count_actual,
            "word_count_compressed": word_count_compressed,
            "model_version": model_version,
            "created_at": datetime.now().isoformat(),
            "hit_count": 0
        }
        
        try:
            success = self.redis.set(cache_key, json.dumps(cache_value), ex=TTL_ANSWER)
            if success:
                logger.info(f"💾 Answer cached: {cache_key} (TTL: {TTL_ANSWER}s)")
            return success
        except Exception as e:
            logger.error(f"Error writing answer cache: {e}")
            return False
    
    # ============================================================
    # NEWS CACHE
    # ============================================================
    
    def get_news_cache_key(
        self,
        parsed_keywords: Dict[str, Any],
        time_range: str = "3months"
    ) -> str:
        """
        Generate cache key for news fetch
        
        Args:
            parsed_keywords: Dict with search_query, topics, etc.
            time_range: Time range string (e.g., "3months")
        
        Returns:
            Cache key string
        """
        # Create hash from keywords
        hash_id = self._hash_dict(parsed_keywords)
        return self._make_key("news", f"query:{hash_id}:{time_range}")
    
    def get_cached_news(
        self,
        parsed_keywords: Dict[str, Any],
        time_range: str = "3months"
    ) -> Optional[List[str]]:
        """
        Retrieve cached news bullets if exists
        
        Returns:
            List of news bullets or None
        """
        if not self.enabled:
            return None
        
        cache_key = self.get_news_cache_key(parsed_keywords, time_range)
        
        try:
            cached_json = self.redis.get(cache_key)
            if cached_json:
                data = json.loads(cached_json)
                logger.info(f"✅ News cache HIT: {cache_key}")
                return data.get("bullets", [])
            else:
                logger.info(f"❌ News cache MISS: {cache_key}")
                return None
        except Exception as e:
            logger.error(f"Error reading news cache: {e}")
            return None
    
    def set_cached_news(
        self,
        parsed_keywords: Dict[str, Any],
        news_bullets: List[str],
        time_range: str = "3months"
    ) -> bool:
        """
        Store news bullets in cache
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        cache_key = self.get_news_cache_key(parsed_keywords, time_range)
        
        cache_value = {
            "bullets": news_bullets,
            "keywords": parsed_keywords,
            "time_range": time_range,
            "fetched_at": datetime.now().isoformat()
        }
        
        try:
            success = self.redis.set(cache_key, json.dumps(cache_value), ex=TTL_NEWS)
            if success:
                logger.info(f"💾 News cached: {cache_key} (TTL: {TTL_NEWS}s)")
            return success
        except Exception as e:
            logger.error(f"Error writing news cache: {e}")
            return False
    
    # ============================================================
    # MAP CACHE
    # ============================================================
    
    def get_map_cache_key(self, map_spec: Dict[str, Any]) -> str:
        """
        Generate cache key for map SVG
        
        Args:
            map_spec: Map JSON specification
        
        Returns:
            Cache key string
        """
        hash_id = self._hash_dict(map_spec)
        return self._make_key("map", f"svg:{hash_id}")
    
    def get_cached_map(self, map_spec: Dict[str, Any]) -> Optional[str]:
        """
        Retrieve cached map SVG if exists
        
        Returns:
            SVG string or None
        """
        if not self.enabled:
            return None
        
        cache_key = self.get_map_cache_key(map_spec)
        
        try:
            cached_json = self.redis.get(cache_key)
            if cached_json:
                data = json.loads(cached_json)
                logger.info(f"✅ Map cache HIT: {cache_key}")
                return data.get("svg_content")
            else:
                logger.info(f"❌ Map cache MISS: {cache_key}")
                return None
        except Exception as e:
            logger.error(f"Error reading map cache: {e}")
            return None
    
    def set_cached_map(
        self,
        map_spec: Dict[str, Any],
        svg_content: str
    ) -> bool:
        """
        Store map SVG in cache
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        cache_key = self.get_map_cache_key(map_spec)
        
        cache_value = {
            "svg_content": svg_content,
            "map_spec": map_spec,
            "generated_at": datetime.now().isoformat()
        }
        
        try:
            success = self.redis.set(cache_key, json.dumps(cache_value), ex=TTL_MAP)
            if success:
                logger.info(f"💾 Map cached: {cache_key} (TTL: {TTL_MAP}s)")
            return success
        except Exception as e:
            logger.error(f"Error writing map cache: {e}")
            return False
    
    # ============================================================
    # DOGPILE PROTECTION (Lock-based)
    # ============================================================
    
    def acquire_lock(self, resource: str, timeout: int = TTL_LOCK) -> bool:
        """
        Acquire a lock to prevent cache stampede
        
        Args:
            resource: Resource identifier (e.g., cache key)
            timeout: Lock timeout in seconds
        
        Returns:
            True if lock acquired
        """
        if not self.enabled:
            return True  # Always succeed if Redis disabled
        
        lock_key = self._make_key("lock", resource)
        return self.redis.set(lock_key, "1", ex=timeout, nx=True)
    
    def release_lock(self, resource: str):
        """Release a lock"""
        if not self.enabled:
            return
        
        lock_key = self._make_key("lock", resource)
        self.redis.delete(lock_key)
    
    # ============================================================
    # STATS & MONITORING
    # ============================================================
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False}
        
        try:
            info = self.redis.info()
            
            # Count keys by namespace
            answer_keys = len(self.redis.keys(f"{self.prefix}:answer:*"))
            news_keys = len(self.redis.keys(f"{self.prefix}:news:*"))
            map_keys = len(self.redis.keys(f"{self.prefix}:map:*"))
            
            return {
                "enabled": True,
                "total_keys": answer_keys + news_keys + map_keys,
                "answer_keys": answer_keys,
                "news_keys": news_keys,
                "map_keys": map_keys,
                "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients", 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"enabled": True, "error": str(e)}
    
    def invalidate_namespace(self, namespace: str):
        """Invalidate all keys in a namespace (use with caution!)"""
        if not self.enabled:
            return
        
        pattern = f"{self.prefix}:{namespace}:*"
        keys = self.redis.keys(pattern)
        
        if keys:
            self.redis.delete(*keys)
        if keys:
            self.redis.delete(*keys)
            logger.warning(f"🗑️  Invalidated {len(keys)} keys in namespace '{namespace}'")

    # ============================================================
    # USER HISTORY (Lists)
    # ============================================================
    
    def get_history_key(self, user_id: str) -> str:
        """Generate key for user history list"""
        return self._make_key("history", user_id)

    def add_user_history(
        self,
        user_id: str,
        question: str,
        word_count: int,
        answer_preview: Optional[str] = None,
        max_history: int = 50
    ) -> bool:
        """
        Add an item to the user's history list (LIFO).
        Trims list to max_history.
        """
        if not self.enabled:
            return False
            
        key = self.get_history_key(user_id)
        
        # Create history item (unique per normalized question)
        q_hash = hashlib.sha256(question.strip().lower().encode()).hexdigest()[:12]
        item = {
            "id": f"{q_hash}-{int(datetime.now().timestamp())}",
            "question": question,
            "word_count": word_count,
            "timestamp": datetime.now().isoformat(),
            "preview": (answer_preview[:100] + "...") if answer_preview else "",
            "q_hash": q_hash
        }
        
        try:
            # Fetch existing to dedupe by q_hash
            existing = self.redis.lrange(key, 0, max_history * 2)
            filtered = [json.loads(x) for x in existing if x]
            filtered = [h for h in filtered if h.get("q_hash") != q_hash]

            # Rebuild list with newest first
            new_list = [item] + filtered
            new_list = new_list[:max_history]

            p = self.redis.pipeline()
            p.delete(key)
            if new_list:
                p.lpush(key, *[json.dumps(h) for h in new_list])
            p.expire(key, 30 * 24 * 60 * 60)
            p.execute()
            
            logger.info(f"📜 Added to history for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding to user history: {e}")
            return False

    def get_user_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        search: Optional[str] = None
    ) -> tuple[list[Dict[str, Any]], int, bool]:
        """
        Get user's history list with optional search and pagination.
        Returns (items, total, has_more).
        """
        if not self.enabled:
            return [], 0, False
            
        key = self.get_history_key(user_id)
        
        try:
            # If searching, pull a larger window to cover all matches; otherwise a reasonable window
            fetch_count = 500 if search else min(limit + offset + 50, 500)
            raw_items = self.redis.lrange(key, 0, fetch_count - 1)
            history = [json.loads(item) for item in raw_items if item]

            if search:
                term = search.lower()
                history = [h for h in history if term in h.get("question", "").lower()]

            total = len(history)
            window = history[offset:offset + limit]
            has_more = offset + limit < total
            return window, total, has_more
        except Exception as e:
            logger.error(f"Error fetching user history: {e}")
            return [], 0, False


# Global singleton instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get singleton cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
