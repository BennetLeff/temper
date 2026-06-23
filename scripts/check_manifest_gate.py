#!/usr/bin/env python3
"""Script manifest gate: enforce manifest <-> filesystem consistency.

Per the script-triage-sunset plan (U7), every scripts/*.py file must have an
entry in scripts/manifest.yaml. CI fails if:
  - A .py file in scripts/ has no manifest entry
  - A manifest entry has category=delete but the file still exists

Warnings (not blocks):
  - An entry has empty imports list (run trace_invocations.py to populate)

Exit codes:
  0 - OK (no violations)
  3 - Manifest violation (file missing entry, or delete-marked file exists)

Usage:
  uv run python scripts/check_manifest_gate.py [--help]
"""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST = SCRIPTS_DIR / "manifest.yaml"

EXCLUDE_FROM_SCAN = {"__pycache__", "tests"}


def list_script_files() -> set[str]:
    """List all .py files in scripts/ (top-level only, not subdirs)."""
    return {
        f.name
        for f in SCRIPTS_DIR.glob("*.py")
        if f.is_file() and f.name != "__init__.py"
    }


def parse_manifest_paths(path: Path) -> set[str]:
    """Extract path: entries from the manifest YAML."""
    paths = set()
    in_imports = False
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if stripped.startswith("- path:"):
            paths.add(stripped.split(":", 1)[1].strip())
            in_imports = False
            continue
        if stripped.startswith("- "):
            continue  # imports list item
        if stripped.startswith("path:") and not stripped.startswith("-"):
            paths.add(stripped.split(":", 1)[1].strip())
            in_imports = False
        if stripped:
            in_imports = stripped.startswith("imports:") and (stripped.endswith("[]") or stripped.endswith(":"))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"[MANIFEST-ERROR] Manifest not found: {MANIFEST}", file=sys.stderr)
        sys.exit(5)

    on_disk = list_script_files()
    in_manifest = parse_manifest_paths(MANIFEST)

    # Files in scripts/ but missing from manifest -> FAIL
    missing_from_manifest = on_disk - in_manifest
    # Manifest entries with category=delete but file still exists -> FAIL
    # (Need to parse the category for each entry; do a lightweight parse.)
    text = MANIFEST.read_text()
    delete_marked_present: list[str] = []
    current_path: str | None = None
    current_category: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("- path:"):
            if current_path and current_category == "delete" and current_path in on_disk:
                delete_marked_present.append(current_path)
            current_path = stripped.split(":", 1)[1].strip()
            current_category = None
            continue
        if current_path and stripped.startswith("category:"):
            current_category = stripped.split(":", 1)[1].strip()
    if current_path and current_category == "delete" and current_path in on_disk:
        delete_marked_present.append(current_path)

    # Empty imports -> WARNING
    empty_imports: list[str] = []
    cur: dict | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("- path:"):
            if cur and cur.get("imports") is not None and len(cur["imports"]) == 0:
                empty_imports.append(cur["path"])
            cur = {"path": stripped.split(":", 1)[1].strip(), "imports": None}
            continue
        if cur is None:
            continue
        if stripped.startswith("- ") and cur.get("imports") is not None:
            cur["imports"].append(stripped[2:].strip())
            continue
        if stripped.startswith("imports:"):
            # check if value is []
            if stripped.endswith("[]"):
                cur["imports"] = []
            else:
                cur["imports"] = []  # start empty; populates from "- " lines
    if cur and cur.get("imports") is not None and len(cur["imports"]) == 0:
        empty_imports.append(cur["path"])

    failed = False
    if missing_from_manifest:
        failed = True
        print("=== MANIFEST VIOLATIONS (scripts missing manifest entry) ===")
        for f in sorted(missing_from_manifest):
            print(
                f"  FAIL: Script '{f}' has no manifest entry. "
                f"Add an entry to {MANIFEST.relative_to(REPO_ROOT)} before committing."
            )
        print()

    if delete_marked_present:
        failed = True
        print("=== MANIFEST VIOLATIONS (delete-marked but file still exists) ===")
        for f in sorted(delete_marked_present):
            print(
                f"  FAIL: Script '{f}' is marked for deletion in manifest but still tracked. "
                f"Run 'git rm scripts/{f}' before committing."
            )
        print()

    if empty_imports:
        print("=== MANIFEST WARNINGS (empty imports list) ===")
        for f in sorted(empty_imports):
            print(
                f"  WARNING: Script '{f}' has no imports listed. "
                f"Run scripts/trace_invocations.py to populate."
            )
        print()

    if failed:
        print(f"Manifest gate FAILED: {len(missing_from_manifest)} missing entries, "
              f"{len(delete_marked_present)} delete-marked files present")
        sys.exit(3)

    summary = (
        f"Manifest gate PASSED — {len(on_disk)} files, {len(in_manifest)} manifest entries, "
        f"{len(empty_imports)} empty-imports warnings"
    )
    print(summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
