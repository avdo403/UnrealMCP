"""
Tests for caching layer.
"""

import pytest
from helpers.caching_layer import (
    CacheManager,
    InMemoryCache,
    cached,
    get_cache
)


def test_in_memory_cache():
    """Test in-memory cache operations."""
    cache = InMemoryCache(max_size=10)
    
    # Test set and get
    cache.set("key1", "value1", ttl=3600)
    assert cache.get("key1") == "value1"
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    
    # Test delete
    cache.delete("key1")
    assert cache.get("key1") is None


def test_cache_manager():
    """Test cache manager."""
    manager = CacheManager(use_redis=False)
    
    # Test set and get
    manager.set("test_key", {"data": "value"}, ttl=3600)
    result = manager.get("test_key")
    assert result == {"data": "value"}
    
    # Test statistics
    stats = manager.get_stats()
    assert stats["hits"] >= 1
    assert stats["sets"] >= 1


def test_cache_key_generation():
    """Test cache key generation."""
    manager = CacheManager(use_redis=False)
    
    key1 = manager._make_key("prefix", "arg1", "arg2", param1="value1")
    key2 = manager._make_key("prefix", "arg1", "arg2", param1="value1")
    key3 = manager._make_key("prefix", "arg1", "arg3", param1="value1")
    
    # Same arguments should produce same key
    assert key1 == key2
    
    # Different arguments should produce different key
    assert key1 != key3


def test_cached_decorator():
    """Test cached decorator."""
    call_count = 0
    
    @cached("test_func", ttl=3600)
    def expensive_function(x):
        nonlocal call_count
        call_count += 1
        return x * 2
    
    # First call should execute function
    result1 = expensive_function(5)
    assert result1 == 10
    assert call_count == 1
    
    # Second call should use cache
    result2 = expensive_function(5)
    assert result2 == 10
    assert call_count == 1  # Should not increment
    
    # Different argument should execute function
    result3 = expensive_function(10)
    assert result3 == 20
    assert call_count == 2


def test_cache_stats():
    """Test cache statistics."""
    manager = CacheManager(use_redis=False)
    
    # Generate some hits and misses
    manager.set("key1", "value1")
    manager.get("key1")  # Hit
    manager.get("key2")  # Miss
    
    stats = manager.get_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["total_requests"] >= 2
    assert 0 <= stats["hit_rate"] <= 100
