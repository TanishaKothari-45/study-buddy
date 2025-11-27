import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from google import genai


class GeminiCacheManager:
    """Manages context caching for Gemini API."""
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        cache_ttl_minutes: int = 300
    ):
        """
        Initialize the cache manager.
        
        Args:
            api_key: Google AI API key
            model_name: Gemini model to use (default: gemini-2.0-flash-exp)
            cache_ttl_minutes: Cache time-to-live in minutes (default: 300 = 5 hours)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.cache_ttl_minutes = cache_ttl_minutes
        self.client = genai.Client(api_key=api_key)
        
        # Track created caches
        self.caches: Dict[str, Dict[str, Any]] = {}
    
    async def create_cache(
        self,
        system_prompt: str,
        few_shot_examples: Optional[List[Dict[str, str]]] = None,
        cache_key: Optional[str] = None
    ) -> str:
        """
        Create a context cache for reuse across multiple requests.
        
        Args:
            system_prompt: System-level instructions to cache
            few_shot_examples: Optional list of example conversations
                              Each dict should have 'user' and 'assistant' keys
            cache_key: Optional key to track this cache (for internal use)
            
        Returns:
            Cache name to use in GeminiClient.generate_response()
            
        Example:
            cache_name = await cache_mgr.create_cache(
                system_prompt="You are an expert in electrical products...",
                few_shot_examples=[
                    {
                        "user": "Extract attributes from: LED bulb, 60W",
                        "assistant": '{"type": "LED", "power": "60W"}'
                    }
                ]
            )
        """
        try:
            # Build cache content
            cache_content = []
            
            # Add system prompt
            cache_content.append({
                "role": "user",
                "parts": [{"text": system_prompt}]
            })
            
            cache_content.append({
                "role": "model",
                "parts": [{"text": "Understood. I'm ready to help."}]
            })
            
            # Add few-shot examples if provided
            if few_shot_examples:
                for example in few_shot_examples:
                    cache_content.append({
                        "role": "user",
                        "parts": [{"text": example.get("user", "")}]
                    })
                    cache_content.append({
                        "role": "model",
                        "parts": [{"text": example.get("assistant", "")}]
                    })
            
            # Create cache
            loop = asyncio.get_event_loop()
            cache_response = await loop.run_in_executor(
                None,
                lambda: self.client.caches.create(
                    model=self.model_name,
                    config={
                        "contents": cache_content,
                        "ttl": f"{self.cache_ttl_minutes * 60}s"
                    }
                )
            )
            
            if cache_response.name:
                # Track cache info
                cache_info = {
                    "name": cache_response.name,
                    "created_at": datetime.now().isoformat(),
                    "ttl_minutes": self.cache_ttl_minutes,
                    "token_count": getattr(
                        cache_response.usage_metadata, 
                        'total_token_count', 
                        0
                    ) if cache_response.usage_metadata else 0
                }
                
                # Store with cache key if provided
                if cache_key:
                    self.caches[cache_key] = cache_info
                
                print(f"Cache created: {cache_response.name}")
                print(f"Cache tokens: {cache_info['token_count']}")
                
                return cache_response.name
            else:
                raise Exception("Failed to create cache - no cache name returned")
                
        except Exception as e:
            print(f"Error creating cache: {e}")
            raise
    
    async def delete_cache(self, cache_name: str):
        """
        Delete a context cache.
        
        Args:
            cache_name: Name of the cache to delete
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.caches.delete(name=cache_name)
            )
            print(f"Cache deleted: {cache_name}")
            
            # Remove from tracking
            for key, info in list(self.caches.items()):
                if info['name'] == cache_name:
                    del self.caches[key]
                    break
                    
        except Exception as e:
            print(f"Error deleting cache: {e}")
    
    async def get_cache(self, cache_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a cache.
        
        Args:
            cache_name: Name of the cache
            
        Returns:
            Cache information dict or None if not found
        """
        try:
            loop = asyncio.get_event_loop()
            cache_info = await loop.run_in_executor(
                None,
                lambda: self.client.caches.get(name=cache_name)
            )
            
            return {
                "name": cache_info.name,
                "model": cache_info.model,
                "create_time": str(cache_info.create_time) if cache_info.create_time else None,
                "expire_time": str(cache_info.expire_time) if cache_info.expire_time else None
            }
            
        except Exception as e:
            print(f"Error getting cache info: {e}")
            return None
    
    async def list_caches(self) -> List[Dict[str, Any]]:
        """
        List all active caches.
        
        Returns:
            List of cache information dicts
        """
        try:
            loop = asyncio.get_event_loop()
            caches_list = await loop.run_in_executor(
                None,
                lambda: list(self.client.caches.list())
            )
            
            result = []
            for cache in caches_list:
                result.append({
                    "name": cache.name,
                    "model": cache.model,
                    "create_time": str(cache.create_time) if cache.create_time else None,
                    "expire_time": str(cache.expire_time) if cache.expire_time else None
                })
            
            return result
            
        except Exception as e:
            print(f"Error listing caches: {e}")
            return []
    
    def get_tracked_cache(self, cache_key: str) -> Optional[str]:
        """
        Get cache name by cache key (for internally tracked caches).
        
        Args:
            cache_key: The key used when creating the cache
            
        Returns:
            Cache name or None if not found
        """
        cache_info = self.caches.get(cache_key)
        return cache_info['name'] if cache_info else None
