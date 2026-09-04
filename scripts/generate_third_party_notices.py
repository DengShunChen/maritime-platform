#!/usr/bin/env python3
"""Generate third-party dependency notices from lockfiles.

The output is intentionally conservative. It records declared licenses from
npm lock metadata and marks Python requirements for manual review because plain
requirements files do not contain license metadata.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "THIRD_PARTY_NOTICES.md"
PACKAGE_LOCK = ROOT / "web-client" / "package-lock.json"
PY_REQUIREMENTS = [
    ROOT / "backend-service" / "requirements.txt",
    ROOT / "backend-service" / "requirements-dev.txt",
    ROOT / "etl" / "requirements.txt",
]
REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
VERSION_RE = re.compile(r"==\s*([^\s;]+)")


@dataclass(frozen=True)
class Notice:
    ecosystem: str
    name: str
    version: str
    license: str
    scope: str

    @property
    def review_required(self) -> bool:
        normalized = self.license.upper()
        return (
            not self.license
            or "UNKNOWN" in normalized
            or "SEE LICENSE" in normalized
            or "GPL" in normalized
            or "REVIEW MANUALLY" in normalized
        )


def npm_package_name(lock_path: str) -> str:
    return lock_path.split("node_modules/")[-1]


def read_npm_notices() -> list[Notice]:
    data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    root = packages.get("", {})
    runtime_dependencies = set(root.get("dependencies", {}))
    dev_dependencies = set(root.get("devDependencies", {}))
    notices: list[Notice] = []

    for lock_path, info in packages.items():
        if not lock_path.startswith("node_modules/"):
            continue
        name = npm_package_name(lock_path)
        version = str(info.get("version", "unknown"))
        license_value = info.get("license", "unknown")
        if isinstance(license_value, list):
            license_text = " OR ".join(str(item) for item in license_value)
        else:
            license_text = str(license_value)
        if name in runtime_dependencies:
            scope = "runtime-direct"
        elif name in dev_dependencies:
            scope = "development-direct"
        elif info.get("dev"):
            scope = "development-transitive"
        else:
            scope = "runtime-transitive"
        notices.append(Notice("npm", name, version, license_text, scope))

    return sorted(notices, key=lambda item: (item.ecosystem, item.scope, item.name.lower()))


def read_python_notices() -> list[Notice]:
    notices: dict[tuple[str, str], Notice] = {}
    for path in PY_REQUIREMENTS:
        if not path.exists():
            continue
        scope = "development-direct" if path.name == "requirements-dev.txt" else "runtime-direct"
        for line in path.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or clean.startswith("-"):
                continue
            match = REQUIREMENT_RE.match(clean)
            if not match:
                continue
            name = match.group(1)
            version_match = VERSION_RE.search(clean)
            version = version_match.group(1) if version_match else "unpinned"
            notices[(name.lower(), scope)] = Notice(
                "python",
                name,
                version,
                "Review manually",
                scope,
            )
    return sorted(notices.values(), key=lambda item: (item.ecosystem, item.scope, item.name.lower()))


def render_table(notices: list[Notice]) -> str:
    rows = ["| Ecosystem | Package | Version | License | Scope |", "|---|---:|---:|---|---|"]
    for item in notices:
        rows.append(f"| {item.ecosystem} | `{item.name}` | `{item.version}` | {item.license} | {item.scope} |")
    return "\n".join(rows)


def render(notices: list[Notice]) -> str:
    review_items = [item for item in notices if item.review_required]
    review_lines = "\n".join(
        f"- {item.ecosystem}: `{item.name}` `{item.version}` ({item.license})"
        for item in review_items
    )
    if not review_lines:
        review_lines = "- None detected by the offline lockfile scanner."

    return f"""# Third-Party Notices

Generated from lockfiles by `scripts/generate_third_party_notices.py`.

This file is a release artifact for customer handoff and legal review. It is not
a substitute for counsel review of commercial licensing terms.

## Manual Review Required

{review_lines}

## Dependency Inventory

{render_table(notices)}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the notice file is out of date")
    args = parser.parse_args()

    notices = read_npm_notices() + read_python_notices()
    content = render(notices)

    if args.check:
        if not OUTPUT.exists():
            print(f"{OUTPUT.relative_to(ROOT)} is missing")
            return 1
        existing = OUTPUT.read_text(encoding="utf-8")
        if existing != content:
            print(f"{OUTPUT.relative_to(ROOT)} is out of date; run scripts/generate_third_party_notices.py")
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is up to date ({len(notices)} packages)")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(notices)} packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
