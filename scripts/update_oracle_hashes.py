#!/usr/bin/env python3
"""Regenerate the oracle content-hash registry (``scripts/oracle_hashes.json``).

Every ``_*_py_oracle.py`` under ``packages/`` is a VERBATIM pin of a
pre-migration Python implementation. The Wave-4 differential suites compare
the Rust kernels against these files; an edit to an oracle that is not a
deliberate re-pin silently weakens every differential proof that reads it
(issues #754 P2-2, #758 -- the recurring "oracle drift is invisible to the
differentials" gap that ``scripts/check_oracle_hashes.py`` closes).

This generator is the human/agent step that records the pins. It is NOT
wired into CI: ``check_oracle_hashes.py`` is the gate, and it compares the
committed registry against the files. The generator only recomputes the
registry -- so a deliberate re-pin is a *visible registry diff in the same
PR as the oracle change* (the keep-in-sync convention, exactly like the
config-reference and .pyi regeneration steps). Running the generator over a
tree that already drifted would record the drifted hashes; that is why the
gate never runs it, and why the diff it produces is what a reviewer sees.

Output is deterministic: sorted paths, no timestamp, so regeneration is
idempotent and the ``git diff`` after a re-pin shows exactly the oracle
files whose pins moved -- not noise.

Exit codes:
  0 - registry written (or unchanged)
  1 - discovery/hash/io failure, or zero oracle files found (a registry with
      zero entries is the vacuous shape this tool exists to prevent, so it
      is refused rather than written)

Usage:
  uv run --no-sync python scripts/update_oracle_hashes.py
  uv run --no-sync python scripts/update_oracle_hashes.py --repo-root .
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402

REGISTRY_FILENAME = "oracle_hashes.json"
ORACLE_GLOB = "_*_py_oracle.py"

# Directories that may legitimately contain *_py_oracle.py-named files but
# are not source of truth (build artifacts, environments).
_EXCLUDED_DIRS = {".venv", "venv", "target", "build", "dist", "node_modules", "__pycache__"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_oracles(repo_root: Path) -> list[Path]:
    """Every ``_*_py_oracle.py`` under ``packages/``, sorted by relative path."""
    found: list[Path] = []
    packages_dir = repo_root / "packages"
    if not packages_dir.is_dir():
        return found
    for path in packages_dir.rglob(ORACLE_GLOB):
        if not path.is_file():
            continue
        parts = path.relative_to(packages_dir).parts
        if any(part in _EXCLUDED_DIRS for part in parts):
            continue
        found.append(path)
    return sorted(found, key=lambda p: str(p.relative_to(repo_root)))


def registry_payload(oracles: list[Path], repo_root: Path) -> dict:
    return {
        "version": 1,
        "algo": "sha256",
        "files": {
            str(p.relative_to(repo_root)): sha256_file(p) for p in oracles
        },
    }


def read_existing_registry(registry_path: Path) -> dict | None:
    if not registry_path.is_file():
        return None
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None,
                        help="Repository root (default: auto-discovered)")
    parser.add_argument("--registry", type=Path, default=None,
                        help="Registry path (default: <repo>/scripts/oracle_hashes.json)")
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    registry_path = args.registry or (repo_root / "scripts" / REGISTRY_FILENAME)

    oracles = discover_oracles(repo_root)
    if not oracles:
        print(f"ERROR: no {ORACLE_GLOB} files found under {repo_root / 'packages'} -- "
              "refusing to write a vacuous registry", file=sys.stderr)
        sys.exit(1)

    new_payload = registry_payload(oracles, repo_root)
    new_files = new_payload["files"]

    old_payload = read_existing_registry(registry_path)
    old_files = old_payload.get("files", {}) if isinstance(old_payload, dict) else {}

    changed = 0
    for rel in sorted(set(old_files) | set(new_files)):
        if rel not in old_files:
            print(f"  [NEW] {rel}")
            changed += 1
        elif rel not in new_files:
            print(f"  [REMOVED] {rel}")
            changed += 1
        elif old_files[rel] != new_files[rel]:
            print(f"  [CHANGED] {rel}\n"
                  f"      {old_files[rel][:12]}... -> {new_files[rel][:12]}...")
            changed += 1

    body = json.dumps(new_payload, indent=2, sort_keys=True) + "\n"
    if old_payload == new_payload:
        print(f"oracle_hashes.json already current ({len(new_files)} files); nothing written")
        sys.exit(0)

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry_path.with_suffix(".json.tmp")
    tmp.write_text(body)
    tmp.replace(registry_path)
    print(f"wrote {registry_path.relative_to(repo_root)}: {len(new_files)} oracle files "
          f"({changed} changed/new/removed)")


if __name__ == "__main__":
    main()
