from concurrent.futures import ThreadPoolExecutor

from tile_cache import TileLRUCache


def test_get_or_set_single_render_under_concurrency():
    cache = TileLRUCache(max_size=10)
    key = ("f", "T2", 0, 4, 1, 1, -20.0, 40.0)
    calls = {"n": 0}

    def factory() -> bytes:
        calls["n"] += 1
        return b"png"

    def worker() -> bytes:
        return cache.get_or_set(key, factory)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: worker(), range(16)))

    assert all(r == b"png" for r in results)
    assert calls["n"] == 1
    assert cache.stats()["hits"] == 15
    assert cache.stats()["misses"] == 1
