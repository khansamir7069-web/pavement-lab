"""Intelligent calculation caching framework for high-performance computations."""
from __future__ import annotations

import threading
from typing import Any


class CalculationCache:
    """Memory-safe thread-safe cache with eviction, statistics, and invalidation."""

    def __init__(self, max_size: int = 50000) -> None:
        self.max_size = max_size
        self._cache: dict[str, dict[Any, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, category: str, key: Any) -> Any | None:
        """Retrieve a cached value for a specific category and key."""
        with self._lock:
            cat_dict = self._cache.get(category)
            if cat_dict and key in cat_dict:
                self.hits += 1
                return cat_dict[key]
            self.misses += 1
            return None

    def set(self, category: str, key: Any, value: Any) -> None:
        """Store a value in the cache with automatic size eviction."""
        with self._lock:
            if category not in self._cache:
                self._cache[category] = {}
            cat_dict = self._cache[category]
            
            # Simple eviction when size is exceeded
            if len(cat_dict) >= self.max_size:
                # Evict the first key (oldest inserted in Python 3.7+)
                oldest_key = next(iter(cat_dict))
                cat_dict.pop(oldest_key)
                
            cat_dict[key] = value

    def invalidate(self, category: str | None = None) -> None:
        """Invalidate/clear the cache. If category is specified, clears only that category."""
        with self._lock:
            if category is None:
                self._cache.clear()
            elif category in self._cache:
                self._cache[category].clear()
            self.hits = 0
            self.misses = 0

    def get_statistics(self) -> dict[str, Any]:
        """Compute statistics for the cache."""
        with self._lock:
            total = self.hits + self.misses
            ratio = self.hits / total if total > 0 else 0.0
            sizes = {cat: len(self._cache[cat]) for cat in self._cache}
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio": ratio,
                "total_queries": total,
                "category_sizes": sizes
            }


# Global calculation cache instance
global_cache = CalculationCache()
