"""Thread-safe LRU cache for dynamically rendered map tiles (PNG bytes)."""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Callable


class TileLRUCache:
    def __init__(self, max_size: int = 512) -> None:
        self.max_size = max_size
        self._lock = threading.Lock()
        self._store: OrderedDict[tuple[Any, ...], bytes] = OrderedDict()
        self._key_locks: dict[tuple[Any, ...], threading.Lock] = {}
        self._key_locks_guard = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(
        file_stem: str,
        variable: str,
        time_idx: int,
        z: int,
        x: int,
        y: int,
        vmin: float | None,
        vmax: float | None,
    ) -> tuple[Any, ...]:
        return (
            file_stem,
            variable,
            time_idx,
            z,
            x,
            y,
            round(vmin, 3) if vmin is not None else None,
            round(vmax, 3) if vmax is not None else None,
        )

    def _peek(self, key: tuple[Any, ...]) -> bytes | None:
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def _lock_for_key(self, key: tuple[Any, ...]) -> threading.Lock:
        with self._key_locks_guard:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: tuple[Any, ...]) -> bytes | None:
        with self._lock:
            if key not in self._store:
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]

    def get_or_set(self, key: tuple[Any, ...], factory: Callable[[], bytes]) -> bytes:
        """Cache lookup with per-key lock to avoid duplicate renders (stampede)."""
        cached = self._peek(key)
        if cached is not None:
            with self._lock:
                self.hits += 1
            return cached

        key_lock = self._lock_for_key(key)
        with key_lock:
            cached = self._peek(key)
            if cached is not None:
                with self._lock:
                    self.hits += 1
                return cached
            data = factory()
            self.set(key, data)
            with self._lock:
                self.misses += 1
            return data

    def set(self, key: tuple[Any, ...], png_bytes: bytes) -> None:
        with self._lock:
            self._store[key] = png_bytes
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = round(self.hits / total, 4) if total else 0.0
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "worker_pid": os.getpid(),
            }


def _max_size(env_key: str, default: int) -> int:
    return int(__import__("os").getenv(env_key, str(default)))


# Shared singletons for app_v2
tile_cache = TileLRUCache(max_size=_max_size("TILE_CACHE_SIZE", 512))
wind_texture_cache = TileLRUCache(max_size=_max_size("WIND_CACHE_SIZE", 64))
coords_texture_cache = TileLRUCache(max_size=_max_size("WIND_CACHE_SIZE", 64))


def clear_all_caches() -> None:
    tile_cache.clear()
    wind_texture_cache.clear()
    coords_texture_cache.clear()
