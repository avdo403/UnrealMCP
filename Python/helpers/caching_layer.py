"""
Caching layer for Unreal MCP Server.

Provides Redis-based caching with TTL, LRU eviction, and cache invalidation.
"""

import json
import logging
import hashlib
from typing import Any, Optional, Dict, Callable
from functools import wraps
import time

logger = logging.getLogger(__name__)

# Try to import Redis, fall back to in-memory cache
try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using in-memory cache")


class CacheBackend:
    """Base class for cache backends."""
    
    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        raise NotImplementedError
    
    def delete(self, key: str):
        raise NotImplementedError
    
    def clear(self):
        raise NotImplementedError


class InMemoryCache(CacheBackend):
    """Simple in-memory LRU cache."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            value, expiry = self.cache[key]
            
            # Check if expired
            if expiry > 0 and time.time() > expiry:
                del self.cache[key]
                del self.access_times[key]
                return None
            
            # Update access time
            self.access_times[key] = time.time()
            return value
        
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        # Evict oldest if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times, key=self.access_times.get)
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        
        expiry = time.time() + ttl if ttl > 0 else 0
        self.cache[key] = (value, expiry)
        self.access_times[key] = time.time()
    
    def delete(self, key: str):
        self.cache.pop(key, None)
        self.access_times.pop(key, None)
    
    def clear(self):
        self.cache.clear()
        self.access_times.clear()


class RedisCache(CacheBackend):
    """Redis-based cache backend."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None
    ):
        self.client = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True
        )
    
    def get(self, key: str) -> Optional[Any]:
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        try:
            serialized = json.dumps(value)
            if ttl > 0:
                self.client.setex(key, ttl, serialized)
            else:
                self.client.set(key, serialized)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    def delete(self, key: str):
        try:
            self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
    
    def clear(self):
        try:
            self.client.flushdb()
        except Exception as e:
            logger.error(f"Redis clear error: {e}")


class CacheManager:
    """
    Unified cache manager with automatic backend selection.
    
    Features:
    - Automatic Redis/in-memory fallback
    - Cache key generation
    - TTL management
    - Cache invalidation patterns
    - Statistics tracking
    """
    
    def __init__(
        self,
        use_redis: bool = True,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        default_ttl: int = 3600
    ):
        self.default_ttl = default_ttl
        
        # Select backend
        if use_redis and REDIS_AVAILABLE:
            try:
                self.backend = RedisCache(host=redis_host, port=redis_port)
                logger.info("Using Redis cache backend")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}, using in-memory cache")
                self.backend = InMemoryCache()
        else:
            self.backend = InMemoryCache()
            logger.info("Using in-memory cache backend")
        
        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
    
    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        # Create deterministic key from arguments
        key_parts = [prefix]
        
        for arg in args:
            key_parts.append(str(arg))
        
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        key_string = ":".join(key_parts)
        
        # Hash if too long
        if len(key_string) > 200:
            key_hash = hashlib.md5(key_string.encode()).hexdigest()
            return f"{prefix}:{key_hash}"
        
        return key_string
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = self.backend.get(key)
        
        if value is not None:
            self.stats["hits"] += 1
        else:
            self.stats["misses"] += 1
        
        return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache."""
        ttl = ttl if ttl is not None else self.default_ttl
        self.backend.set(key, value, ttl)
        self.stats["sets"] += 1
    
    def delete(self, key: str):
        """Delete value from cache."""
        self.backend.delete(key)
        self.stats["deletes"] += 1
    
    def clear(self):
        """Clear entire cache."""
        self.backend.clear()
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern (Redis only)."""
        if isinstance(self.backend, RedisCache):
            try:
                keys = self.backend.client.keys(pattern)
                if keys:
                    self.backend.client.delete(*keys)
                    logger.info(f"Invalidated {len(keys)} keys matching '{pattern}'")
            except Exception as e:
                logger.error(f"Pattern invalidation error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            self.stats["hits"] / total_requests * 100
            if total_requests > 0
            else 0
        )
        
        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate": hit_rate
        }


# Global cache instance
_cache_manager: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """Get global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def cached(
    prefix: str,
    ttl: int = 3600,
    key_func: Optional[Callable] = None
):
    """
    Decorator for caching function results.
    
    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        key_func: Optional custom key generation function
    
    Example:
        @cached("blueprint_info", ttl=1800)
        def get_blueprint_info(blueprint_name: str):
            # Expensive operation
            return fetch_blueprint_data(blueprint_name)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._make_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Execute function
            logger.debug(f"Cache miss: {cache_key}")
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def invalidate_cache(pattern: str):
    """Invalidate cache entries matching pattern."""
    cache = get_cache()
    cache.invalidate_pattern(pattern)
