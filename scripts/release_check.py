#!/usr/bin/env python3
"""Release gate for local commercial-ready builds.

This script intentionally stays dependency-free so it can run before Docker
images are built or Python app dependencies are installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def check(name: str, cmd: list[str], *, env: dict[str, str] | None = None) -> bool:
    print(f"[check] {name}")
    result = run(cmd, env=env)
    if result.returncode != 0:
        print(result.stdout.strip())
        print(f"[fail] {name}")
        return False
    print(f"[pass] {name}")
    return True


def require_git_ignored(path: str) -> bool:
    result = run(["git", "check-ignore", "-q", path])
    if result.returncode == 0:
        print(f"[pass] {path} is ignored")
        return True
    print(f"[fail] {path} is not ignored")
    return False


def ensure_env_example_has(keys: list[str]) -> bool:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    missing = [key for key in keys if f"{key}=" not in text]
    if missing:
        print(f"[fail] .env.example missing: {', '.join(missing)}")
        return False
    print("[pass] .env.example has required deployment keys")
    return True


def ensure_release_docs() -> bool:
    required = {
        "README.md": ["docs/OPERATIONS.md", "docs/SECURITY.md", "CHANGELOG.md", "docs/THIRD_PARTY_NOTICES.md"],
        "CHANGELOG.md": ["Unreleased", "Security"],
        "docs/OPERATIONS.md": ["Release Readiness", "Monitoring", "Backup And Restore", "Customer Handoff"],
        "docs/SECURITY.md": ["Secrets", "API Protection", "Dependency And Image Hygiene", "Commercial Launch Gaps"],
        "docs/THIRD_PARTY_NOTICES.md": ["Manual Review Required", "Dependency Inventory"],
    }
    missing: list[str] = []
    for path, markers in required.items():
        doc_path = ROOT / path
        if not doc_path.exists():
            missing.append(f"{path} (missing file)")
            continue
        text = doc_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{path} missing marker: {marker}")
    if missing:
        print("[fail] release documentation incomplete")
        for item in missing:
            print(f"  - {item}")
        return False
    print("[pass] release documentation complete")
    return True


def check_live_backend_contract() -> bool:
    code = """
import json
import sys
sys.path.insert(0, 'backend-service')
import app_v2
client = app_v2.app.test_client()
ready = client.get('/ready')
version = client.get('/version')
metrics = client.get('/metrics')
payload = {
    'ready_status': ready.status_code,
    'ready': ready.get_json(silent=True),
    'version_status': version.status_code,
    'version': version.get_json(silent=True),
    'metrics_status': metrics.status_code,
    'metrics_has_requests': 'maritime_http_requests_total' in metrics.get_data(as_text=True),
}
print(json.dumps(payload, ensure_ascii=False))
raise SystemExit(0 if ready.status_code == 200 and version.status_code == 200 and metrics.status_code == 200 and payload['metrics_has_requests'] else 1)
"""
    python = os.environ.get("CI_PYTHON", ".venv311/bin/python")
    result = run([python, "-c", code], env={"MPLCONFIGDIR": "/tmp/matplotlib"})
    if result.returncode == 0:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        print(
            "[pass] backend contract with real data "
            f"(version={payload['version']['version']}, dataset={payload['version']['dataset']})"
        )
        return True
    print(result.stdout.strip())
    print("[fail] backend contract with real data")
    return False


def main() -> int:
    checks = [
        check("local CI", ["make", "ci-local"]),
        check(
            "compose with release identity",
            ["docker", "compose", "config", "--quiet"],
            env={
                "BUILD_VERSION": os.environ.get("BUILD_VERSION", "release-check"),
                "BUILD_SHA": os.environ.get("BUILD_SHA", "local"),
                "BUILD_DATE": os.environ.get("BUILD_DATE", "1970-01-01T00:00:00Z"),
                "API_KEY": os.environ.get("API_KEY", "release-check-key"),
                "RATE_LIMIT_PER_MINUTE": os.environ.get("RATE_LIMIT_PER_MINUTE", "600"),
            },
        ),
        require_git_ignored(".env"),
        require_git_ignored("web-client/.env"),
        require_git_ignored("data/wrfout_d01_2026-09-02_00:00:00"),
        ensure_env_example_has(
            [
                "VITE_MAPTILER_API_KEY",
                "BUILD_VERSION",
                "BUILD_SHA",
                "BUILD_DATE",
                "NETCDF_PATH",
                "API_KEY",
                "CORS_ORIGINS",
                "RATE_LIMIT_PER_MINUTE",
            ]
        ),
        ensure_release_docs(),
        check("third-party notices are current", [sys.executable, "scripts/generate_third_party_notices.py", "--check"]),
        check_live_backend_contract(),
    ]
    if all(checks):
        print("[pass] release gate complete")
        return 0
    print("[fail] release gate failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
