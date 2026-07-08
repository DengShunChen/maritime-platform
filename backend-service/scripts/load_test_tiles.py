#!/usr/bin/env python3
"""Concurrent load test for /tiles endpoint (matplotlib thread-safety + LRU cache)."""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import urllib.error
    import urllib.request
except ImportError:
    sys.exit(1)

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:6000").rstrip("/")


def fetch_tile(z: int, x: int, y: int, variable: str, time_idx: int) -> tuple[bool, float, int]:
    url = f"{BASE_URL}/tiles/{z}/{x}/{y}?variable={variable}&time={time_idx}&vmin=-20&vmax=40"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read()
            ok = resp.status == 200 and len(body) > 100
            return ok, time.perf_counter() - start, resp.status
    except urllib.error.HTTPError as e:
        return False, time.perf_counter() - start, e.code
    except Exception:
        return False, time.perf_counter() - start, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test dynamic map tiles")
    parser.add_argument("-c", "--concurrency", type=int, default=20)
    parser.add_argument("-n", "--requests", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=0, help="Sequential warm-up requests first")
    parser.add_argument("--variable", default="T2")
    parser.add_argument("--time", type=int, default=0)
    args = parser.parse_args()

    tiles = [(4, 13 + (i % 3), 6 + (i % 2)) for i in range(args.requests)]
    unique_tiles = len({t for t in tiles})

    print(f"Target: {BASE_URL}  concurrency={args.concurrency}  requests={args.requests}")
    print(f"Unique tile keys: {unique_tiles} (expect hit_rate → 1 - {unique_tiles}/{args.requests} after warm-up)")

    if args.warmup > 0:
        print(f"Warm-up: {args.warmup} sequential requests...")
        for i in range(min(args.warmup, len(tiles))):
            z, x, y = tiles[i]
            fetch_tile(z, x, y, args.variable, args.time)

    results: list[tuple[bool, float, int]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(fetch_tile, z, x, y, args.variable, args.time)
            for z, x, y in tiles
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    ok = [r for r in results if r[0]]
    fail = len(results) - len(ok)
    durations = [r[1] for r in ok]

    if durations:
        print(f"OK: {len(ok)}/{len(results)}  FAIL: {fail}")
        print(f"  avg={statistics.mean(durations):.3f}s  p50={statistics.median(durations):.3f}s  max={max(durations):.3f}s")
    else:
        print(f"All requests failed ({fail})")
        sys.exit(1)

    try:
        with urllib.request.urlopen(f"{BASE_URL}/cache/stats") as resp:
            print(f"Cache: {resp.read().decode()}")
    except Exception:
        pass

    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
