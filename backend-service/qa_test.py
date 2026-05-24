"""
API smoke tests — run against a live backend before deploy.

Usage:
  BACKEND_URL=http://localhost:6000 python qa_test.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:5000").rstrip("/")


def test_endpoint(
    path: str,
    name: str,
    expected_content_type: str | None = None,
    *,
    min_bytes: int = 0,
) -> tuple[bool, int, str]:
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as response:
            code = response.getcode()
            content_type = response.headers.get("Content-Type", "")

            if code != 200:
                return False, code, f"Expected 200, got {code}"

            if expected_content_type and expected_content_type not in content_type:
                return False, code, f"Expected Content-Type {expected_content_type}, got {content_type}"

            body = response.read()
            if len(body) < min_bytes:
                return False, code, f"Response too small ({len(body)} bytes)"

            if "application/json" in content_type:
                json.loads(body.decode("utf-8"))

            return True, code, "OK"
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_body = ""
        return False, e.code, error_body
    except Exception as e:
        return False, 500, str(e)


def run_qa() -> None:
    print(f"QA smoke tests → {BASE_URL}")

    max_retries = 15
    healthy = False
    for i in range(max_retries):
        success, _, _ = test_endpoint("/health", "Health Check")
        if success:
            healthy = True
            break
        print(f"Waiting for backend... ({i + 1}/{max_retries})")
        time.sleep(2)

    if not healthy:
        print("Backend unhealthy — aborting QA")
        sys.exit(1)

    endpoints: list[tuple[str, str, str | None, int]] = [
        ("/health", "Health Check", "application/json", 0),
        ("/variables", "Variables List", "application/json", 0),
        ("/time_points", "Time Points", "application/json", 0),
        ("/netcdf_files", "NetCDF Files List", "application/json", 0),
        ("/cog_manifest", "COG Manifest", "application/json", 0),
        ("/variable_stats?variable=T2&time=0", "Stats: T2", "application/json", 0),
        ("/variable_stats?variable=PSFC&time=0", "Stats: PSFC", "application/json", 0),
        ("/variable_stats?variable=WSPD&time=0", "Stats: WSPD", "application/json", 0),
        ("/probe?lat=24&lon=121&variable=T2&time=0", "Probe: T2", "application/json", 0),
        ("/probe?lat=24&lon=121&variable=WSPD&time=0", "Probe: WSPD", "application/json", 0),
        ("/contours?variable=PSFC&time=0", "Contours: PSFC", "application/json", 0),
        ("/tiles/3/6/3?variable=T2&time=0&vmin=-20&vmax=40", "Tile: T2", "image/png", 100),
        ("/wind_texture?time=0&metadata=true", "Wind Metadata", "application/json", 0),
        ("/wind_texture?time=0", "Wind Texture PNG", "image/png", 100),
        ("/coords_texture?time=0", "Coords Texture", "application/octet-stream", 16),
    ]

    all_passed = True
    print("\nEndpoint coverage:")
    print("-" * 80)

    for path, name, expected_ct, min_bytes in endpoints:
        success, code, msg = test_endpoint(path, name, expected_ct, min_bytes=min_bytes)
        status = "PASS" if success else f"FAIL ({code})"
        print(f"{status:12} | {name:<28} | {path}")
        if not success:
            print(f"             -> {msg[:200]}")
            all_passed = False

    print("-" * 80)
    if all_passed:
        print("QA passed — deployment gate open")
        sys.exit(0)

    print("QA failed — fix errors before deploy")
    sys.exit(1)


if __name__ == "__main__":
    run_qa()
