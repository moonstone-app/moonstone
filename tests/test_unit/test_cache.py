# -*- coding: utf-8 -*-
"""Unit tests for LRUCache.

Tests LRU eviction behavior, thread safety, and API compatibility
with the existing page cache usage patterns.
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest


class TestLRUCacheBasic:
    """Test basic LRUCache functionality."""

    def test_cache_initialization(self):
        """Cache initializes with correct maxsize."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=10)
        assert cache.maxsize == 10
        assert len(cache) == 0

    def test_put_and_get(self):
        """Put item in cache and retrieve it."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("key1", "value1")

        assert "key1" in cache
        assert cache.get("key1") == "value1"
        assert cache["key1"] == "value1"  # Test __getitem__

    def test_get_nonexistent_key(self):
        """Get returns default for nonexistent key."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        assert cache.get("nonexistent") is None
        assert cache.get("nonexistent", "default") == "default"

    def test_lru_eviction(self):
        """Least recently used item is evicted when cache is full."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)

        # Fill cache
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")

        # All three should be in cache
        assert len(cache) == 3
        assert "key1" in cache
        assert "key2" in cache
        assert "key3" in cache

        # Add one more - should evict key1 (least recently used)
        cache.put("key4", "value4")

        assert len(cache) == 3
        assert "key1" not in cache  # Evicted
        assert "key2" in cache
        assert "key3" in cache
        assert "key4" in cache

    def test_update_existing_key(self):
        """Updating existing key moves it to most recently used."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)

        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key4 - should evict key2 (now least recently used)
        cache.put("key4", "value4")

        assert "key1" in cache  # Still there (was accessed)
        assert "key2" not in cache  # Evicted
        assert "key3" in cache
        assert "key4" in cache

    def test_pop(self):
        """Pop removes and returns item."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("key1", "value1")

        assert cache.pop("key1") == "value1"
        assert "key1" not in cache
        assert len(cache) == 0

    def test_pop_with_default(self):
        """Pop returns default for nonexistent key."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        assert cache.pop("nonexistent", "default") == "default"

    def test_delitem(self):
        """del removes item from cache."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("key1", "value1")

        del cache["key1"]
        assert "key1" not in cache
        assert len(cache) == 0

    def test_clear(self):
        """Clear empties the cache."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_setitem_syntax(self):
        """Cache supports []= syntax for putting items."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache["key1"] = "value1"

        assert "key1" in cache
        assert cache["key1"] == "value1"

    def test_unlimited_cache(self):
        """Cache with maxsize=None grows without limit."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=None)

        # Add many items
        for i in range(1000):
            cache.put(f"key{i}", f"value{i}")

        # All should still be there
        assert len(cache) == 1000
        assert cache.get("key0") == "value0"
        assert cache.get("key999") == "value999"


class TestLRUCacheThreadSafety:
    """Test thread-safe concurrent access."""

    def test_concurrent_get_and_put(self):
        """Multiple threads can get and put concurrently."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=100)
        errors = []

        def worker(thread_id):
            try:
                for i in range(50):
                    key = f"thread{thread_id}_key{i}"
                    cache.put(key, f"value_{thread_id}_{i}")
                    value = cache.get(key)
                    if value != f"value_{thread_id}_{i}":
                        errors.append(f"Expected value_{thread_id}_{i}, got {value}")
            except Exception as e:
                errors.append(f"Exception: {e}")

        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(cache) <= 100  # Should respect maxsize

    def test_concurrent_lru_behavior(self):
        """LRU eviction works correctly under concurrent access."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=10)

        # Fill cache from multiple threads
        def fill_cache(start):
            for i in range(20):
                key = f"key{start + i}"
                cache.put(key, f"value{start + i}")
                time.sleep(0.001)  # Small delay to interleave

        threads = []
        for i in range(4):
            t = threading.Thread(target=fill_cache, args=(i * 20,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Cache should never exceed maxsize
        assert len(cache) <= 10

        # Most recently accessed keys should be present
        keys = cache.keys()
        assert len(keys) <= 10


class TestLRUCachePagePattern:
    """Test patterns used by Notebook page cache."""

    def test_check_membership_then_get(self):
        """Pattern: if key in cache: value = cache[key]."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("page1", "content1")

        # Notebook pattern
        if "page1" in cache:
            cached = cache["page1"]
            assert cached == "content1"

    def test_delete_key(self):
        """Pattern: del cache[key]."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)
        cache.put("page1", "content1")

        # Notebook pattern for stale cache
        del cache["page1"]
        assert "page1" not in cache

    def test_pop_with_none_default(self):
        """Pattern: cache.pop(key, None)."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)

        # Notebook pattern for cleanup
        result = cache.pop("nonexistent", None)
        assert result is None

        cache.put("page1", "content1")
        result = cache.pop("page1", None)
        assert result == "content1"
        assert "page1" not in cache

    def test_direct_assignment(self):
        """Pattern: cache[key] = value."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)

        # Notebook pattern for storing page
        cache["HomePage"] = "Home content"
        assert cache["HomePage"] == "Home content"

    def test_access_pattern_mru(self):
        """Accessing item makes it most recently used."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=3)

        cache["page1"] = "content1"
        cache["page2"] = "content2"
        cache["page3"] = "content3"

        # Access page1 to bump it to MRU
        _ = cache["page1"]

        # Add page4 - should evict page2 (now LRU)
        cache["page4"] = "content4"

        assert "page1" in cache  # Still there (was accessed)
        assert "page2" not in cache  # Evicted
        assert "page3" in cache
        assert "page4" in cache


class TestLRUCacheIntegration:
    """Integration tests with Notebook-like usage."""

    def test_cache_hit_ratio(self):
        """Simulate cache access patterns."""
        from notebook.cache import LRUCache

        cache = LRUCache(maxsize=100)

        # Access 1000 pages, but only 100 unique ones
        hits = 0
        misses = 0

        for i in range(1000):
            page_id = i % 100  # Only 100 unique pages
            page_name = f"Page{page_id}"

            if page_name in cache:
                content = cache[page_name]
                hits += 1
            else:
                content = f"Content for page {page_id}"
                cache[page_name] = content
                misses += 1

        # Should have high hit rate after initial miss
        assert hits > 800  # 80%+ hit rate
        assert len(cache) <= 100

    def test_cache_with_object_values(self):
        """Cache works with arbitrary objects (like Page objects)."""
        from notebook.cache import LRUCache

        class MockPage:
            def __init__(self, name):
                self.name = name
                self.content = f"Content for {name}"

        cache = LRUCache(maxsize=5)

        # Store page objects
        page1 = MockPage("Page1")
        page2 = MockPage("Page2")

        cache["Page1"] = page1
        cache["Page2"] = page2

        # Retrieve and verify
        retrieved = cache["Page1"]
        assert retrieved.name == "Page1"
        assert retrieved.content == "Content for Page1"
        assert retrieved is page1  # Same object
