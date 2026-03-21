# -*- coding: utf-8 -*-
"""LRU cache implementation for page caching.

Provides size-limited caching with automatic eviction of least recently
used items. Prevents unbounded memory growth in large notebooks.
"""

from collections import OrderedDict
import threading
import logging

logger = logging.getLogger("moonstone.cache")


class LRUCache:
    """Least-Recently-Used (LRU) cache with fixed maximum size.

    When the cache is full and a new item is added, the least recently
    used item is automatically evicted.

    Usage:
        cache = LRUCache(maxsize=1000)

        # Get item
        value = cache.get(key)

        # Put item
        cache.put(key, value)

        # Remove item
        cache.pop(key, None)

        # Check membership
        if key in cache:
            ...

        # Delete item
        del cache[key]

    Thread-safe: Uses RLock for concurrent access.
    """

    def __init__(self, maxsize=1000):
        """Initialize LRU cache.

        Args:
            maxsize: Maximum number of items to cache (default: 1000)
                    Set to None for unlimited size (not recommended)
        """
        self.maxsize = maxsize
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key, default=None):
        """Get item from cache and mark as recently used.

        Args:
            key: Cache key
            default: Value to return if key not found (default: None)

        Returns:
            Cached value or default if not found
        """
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return self._cache[key]
            return default

    def put(self, key, value):
        """Put item in cache, evicting LRU item if full.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            if key in self._cache:
                # Update existing and move to end
                self._cache.move_to_end(key)
            else:
                # Check if we need to evict
                if self.maxsize is not None and len(self._cache) >= self.maxsize:
                    # Remove first (least recently used) item
                    self._cache.popitem(last=False)
                    logger.debug(
                        "LRU cache evicted item (cache full: %d/%d)",
                        len(self._cache),
                        self.maxsize,
                    )

            self._cache[key] = value

    def pop(self, key, default=None):
        """Remove item from cache and return its value.

        Args:
            key: Cache key
            default: Value to return if key not found (default: None)

        Returns:
            Cached value or default if not found
        """
        with self._lock:
            return self._cache.pop(key, default)

    def __contains__(self, key):
        """Check if key is in cache."""
        with self._lock:
            return key in self._cache

    def __delitem__(self, key):
        """Delete item from cache."""
        with self._lock:
            del self._cache[key]

    def __len__(self):
        """Return number of items in cache."""
        with self._lock:
            return len(self._cache)

    def clear(self):
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()

    def keys(self):
        """Return cache keys (for debugging/testing)."""
        with self._lock:
            return list(self._cache.keys())

    def __getitem__(self, key):
        """Get item from cache (synonym for get)."""
        return self.get(key)

    def __setitem__(self, key, value):
        """Set item in cache (synonym for put)."""
        self.put(key, value)
