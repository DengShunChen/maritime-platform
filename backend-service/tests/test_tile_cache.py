from tile_cache import TileLRUCache


def test_lru_eviction():
    cache = TileLRUCache(max_size=2)
    k1 = cache.make_key("a", "T2", 0, 3, 1, 1, 0.0, 10.0)
    k2 = cache.make_key("a", "T2", 0, 3, 1, 2, 0.0, 10.0)
    k3 = cache.make_key("a", "T2", 0, 3, 2, 1, 0.0, 10.0)
    cache.set(k1, b"one")
    cache.set(k2, b"two")
    cache.set(k3, b"three")
    assert cache.get(k1) is None
    assert cache.get(k2) == b"two"
    assert cache.get(k3) == b"three"


def test_clear_resets_stats():
    cache = TileLRUCache(max_size=10)
    key = cache.make_key("f", "PSFC", 1, 4, 5, 6, None, None)
    cache.set(key, b"png")
    cache.get(key)
    cache.clear()
    stats = cache.stats()
    assert stats["size"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
