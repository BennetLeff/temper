#!/usr/bin/env python3
"""LOC cap gate: enforce a 1000-line ceiling on source .py/.c files.

Exit 0 if all files pass; exit 1 with named failure messages otherwise.

Violation classes:
  UNLISTED_OVER_CAP   - file over cap not on the allowlist
  ALLOWLIST_GREW      - allowlisted file grew past its baseline
  NEW_ENTRY_NO_REMOVAL - allowlist entry added without any removal
  REMOVED_STILL_OVER_CAP - allowlist entry removed but file still over cap
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CAP = 1000
ALLOWLIST_PATH = REPO_ROOT / ".loc-allowlist.txt"

INCLUDE_GLOBS: list[str] = [
    "packages/*/src/temper_*/**/*.py",
    "firmware/**/*.c",
]

EXCLUDE_GLOBS: list[str] = [
    "packages/*/tests/**",
    "packages/*/experiments/**",
    "packages/*/benchmarks/**",
    "firmware/test/**",
    "firmware/test/build/**",
    "**/__pycache__/**",
    "**/build/**",
]


def _matches_any_exclude(path: Path) -> bool:
    for pattern in EXCLUDE_GLOBS:
        if _path_matches_glob(path, REPO_ROOT / pattern):
            return True
    return False


def _path_matches_glob(path: Path, pattern: Path) -> bool:
    return path.match(str(pattern))


def _collect_source_files() -> list[tuple[str, int]]:
    """Return [(relative_path, line_count), ...] for included source files."""
    files: dict[str, int] = {}
    seen: set[str] = set()

    for pattern in INCLUDE_GLOBS:
        for f in sorted(REPO_ROOT.glob(pattern)):
            rel = str(f.relative_to(REPO_ROOT))
            if rel in seen:
                continue
            if _matches_any_exclude(f):
                continue
            if not f.is_file():
                continue
            seen.add(rel)
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    lines = sum(1 for _ in fh)
                files[rel] = lines
            except (OSError, UnicodeDecodeError):
                continue

    return sorted(files.items())


def _parse_allowlist() -> dict[str, tuple[int, str]]:
    """Read .loc-allowlist.txt, return {path: (baseline_lines, ticket_id)}."""
    if not ALLOWLIST_PATH.exists():
        return {}
    entries: dict[str, tuple[int, str]] = {}
    seen: set[str] = set()
    with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                print(f"[WARN] malformed allowlist line (need <path> <baseline> <ticket>): {line}",
                      file=sys.stderr)
                continue
            path, baseline_str, ticket = parts[0], parts[1], parts[2]
            if path in seen:
                print(f"[WARN] duplicate allowlist entry for {path}", file=sys.stderr)
                continue
            seen.add(path)
            try:
                baseline = int(baseline_str)
            except ValueError:
                print(f"[WARN] non-integer baseline in allowlist: {line}", file=sys.stderr)
                continue
            entries[path] = (baseline, ticket)
    return entries


def _get_previous_allowlist_lines() -> Optional[set[str]]:
    """Attempt to get the previous commit's allowlist non-comment lines.

    On push to main: compare HEAD~1.
    On pull_request: compare origin/main.
    Else: return None and skip the NEW_ENTRY_NO_REMOVAL check.
    """
    ref = _resolve_diff_base()
    if ref is None:
        return None
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:.loc-allowlist.txt"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            return None
        lines: set[str] = set()
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                lines.add(line)
        return lines
    except (subprocess.SubprocessError, OSError):
        return None


def _resolve_diff_base() -> Optional[str]:
    """Find the comparison base for allowlist diff."""
    env = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    branch = env.stdout.strip()
    if branch == "main":
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD~1"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            if r.returncode == 0:
                return "HEAD~1"
        except (subprocess.SubprocessError, OSError):
            pass
        return None

    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "origin/main"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if r.returncode == 0:
            return "origin/main"
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _previous_allowlist_entry_set(ref: Optional[str]) -> set[str]:
    """Return the set of entry prefix strings (path baseline ticket) from the
    previous revision's allowlist, so we can compare adds vs removes.

    An 'entry' is the first three whitespace-delimited tokens of each
    non-comment line.
    """
    if ref is None:
        return set()
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:.loc-allowlist.txt"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            return set()
        entries: set[str] = set()
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 3:
                    entries.add(" ".join(parts[:3]))
        return entries
    except (subprocess.SubprocessError, OSError):
        return set()


def main() -> int:
    errors: list[str] = []

    source_files = _collect_source_files()
    allowlist = _parse_allowlist()

    over_cap: dict[str, int] = {
        path: lines for path, lines in source_files if lines > CAP
    }

    # --- UNLISTED_OVER_CAP ---
    for path, lines in over_cap.items():
        if path not in allowlist:
            errors.append(
                f"[LOC-CAP-FAIL] UNLISTED_OVER_CAP: {path} {lines} lines "
                f"(cap {CAP}, not in allowlist)"
            )

    # --- ALLOWLIST_GREW ---
    for path, (baseline, ticket) in allowlist.items():
        if path in over_cap:
            current = over_cap[path]
            if current > baseline:
                errors.append(
                    f"[LOC-CAP-FAIL] ALLOWLIST_GREW: {path} {current} lines "
                    f"(cap {CAP}, baseline {baseline}, ticket {ticket})"
                )

    # --- ALLOWLIST_MISSING ---
    for path in allowlist:
        actual = dict(source_files)
        if path not in actual:
            errors.append(
                f"[LOC-CAP-FAIL] ALLOWLIST_MISSING: {path} listed in "
                f"allowlist but file does not exist"
            )

    # --- NEW_ENTRY_NO_REMOVAL ---
    ref = _resolve_diff_base()
    prev_entries = _previous_allowlist_entry_set(ref)
    if prev_entries:
        current_entries: set[str] = set()
        for path, (baseline, ticket) in allowlist.items():
            current_entries.add(f"{path} {baseline} {ticket}")
        added = current_entries - prev_entries
        removed = prev_entries - current_entries
        if added and not removed:
            for entry in sorted(added):
                errors.append(
                    f"[LOC-CAP-FAIL] NEW_ENTRY_NO_REMOVAL: {entry} "
                    f"(added without removal; strict-shrink policy: "
                    f"must remove a larger/comparable entry first)"
                )

    # --- REMOVED_STILL_OVER_CAP ---
    if prev_entries:
        current_paths = set(allowlist.keys())
        prev_paths = {p.split()[0] for p in prev_entries}
        removed_paths = prev_paths - current_paths
        for path in sorted(removed_paths):
            if path in over_cap:
                errors.append(
                    f"[LOC-CAP-FAIL] REMOVED_STILL_OVER_CAP: {path} "
                    f"{over_cap[path]} lines (remove from allowlist but still over cap {CAP})"
                )

    if errors:
        for e in errors:
            print(e)
        return 1

    count = len(over_cap)
    print(f"[LOC-CAP-OK] {len(source_files)} source files scanned, "
          f"{count} over cap (all allowlisted), {len(allowlist)} allowlist entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
