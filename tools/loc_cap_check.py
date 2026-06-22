#!/usr/bin/env python3
"""LOC cap gate: enforce a 1000-line ceiling on source .py/.c files.

Exit 0 if all files pass; exit 1 with named failure messages otherwise.

Violation classes:
  UNLISTED_OVER_CAP      - file over cap not on the allowlist
  ALLOWLIST_GREW         - allowlisted file grew past its baseline
  NEW_ENTRY_NO_REMOVAL   - allowlist entry added without any removal
  REMOVED_STILL_OVER_CAP - allowlist entry removed but file still over cap
  ALLOWLIST_MISSING      - allowlisted path does not exist on disk
"""

from __future__ import annotations

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


def _resolve_exclude_set() -> set[str]:
    """Resolve exclude prefix directories at script startup."""
    dirs: set[str] = set()
    for pattern in [
        "packages/*/tests",
        "firmware/test",
        "firmware/test/build",
    ]:
        for d in REPO_ROOT.glob(pattern):
            if d.is_dir():
                dirs.add(str(d.resolve()))
    return dirs


_EXCLUDE_DIRS: set[str] = _resolve_exclude_set()


def _is_excluded(path: Path) -> bool:
    rp = path.resolve()
    for prefix in _EXCLUDE_DIRS:
        try:
            rp.relative_to(prefix)
            return True
        except ValueError:
            pass
    rel = str(path.relative_to(REPO_ROOT))
    for bad in ("/__pycache__/", "/build/"):
        if bad in rel:
            return True
    return False


def _collect_source_files() -> list[tuple[str, int]]:
    """Return [(relative_path, line_count), ...] for included source files."""
    seen: set[str] = set()
    files: list[tuple[str, int]] = []
    for pattern in INCLUDE_GLOBS:
        for f in sorted(REPO_ROOT.glob(pattern)):
            if not f.is_file():
                continue
            rel = str(f.relative_to(REPO_ROOT))
            if rel in seen:
                continue
            if _is_excluded(f):
                continue
            seen.add(rel)
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    lines = sum(1 for _ in fh)
                files.append((rel, lines))
            except (OSError, UnicodeDecodeError):
                continue
    return files


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
                print(
                    f"[WARN] malformed allowlist line (need <path> <baseline> <ticket>): {line}",
                    file=sys.stderr,
                )
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


def _resolve_diff_base() -> Optional[str]:
    """Find the comparison base for allowlist diff."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    branch = r.stdout.strip()
    if branch == "main":
        try:
            r2 = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD~1"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            if r2.returncode == 0:
                return "HEAD~1"
        except (subprocess.SubprocessError, OSError):
            pass
        return None

    try:
        r3 = subprocess.run(
            ["git", "rev-parse", "--verify", "origin/main"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if r3.returncode == 0:
            return "origin/main"
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _previous_allowlist_entries(ref: Optional[str]) -> set[str]:
    """Return the set of '<path> <baseline> <ticket>' strings from the
    previous revision's allowlist."""
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

    actual: dict[str, int] = dict(source_files)

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
        if path not in actual:
            errors.append(
                f"[LOC-CAP-FAIL] ALLOWLIST_MISSING: {path} listed in "
                f"allowlist but file does not exist"
            )

    # --- NEW_ENTRY_NO_REMOVAL / REMOVED_STILL_OVER_CAP ---
    ref = _resolve_diff_base()
    prev_entries = _previous_allowlist_entries(ref)
    if prev_entries:
        current_entries: set[str] = {
            f"{p} {bl} {t}" for p, (bl, t) in allowlist.items()
        }
        added = current_entries - prev_entries
        removed = prev_entries - current_entries
        if added and not removed:
            for entry in sorted(added):
                errors.append(
                    f"[LOC-CAP-FAIL] NEW_ENTRY_NO_REMOVAL: {entry} "
                    f"(added without removal; strict-shrink policy: "
                    f"must remove a larger/comparable entry first)"
                )

        current_paths = set(allowlist.keys())
        prev_paths = {p.split()[0] for p in prev_entries}
        removed_paths = prev_paths - current_paths
        for path in sorted(removed_paths):
            if path in over_cap:
                errors.append(
                    f"[LOC-CAP-FAIL] REMOVED_STILL_OVER_CAP: {path} "
                    f"{over_cap[path]} lines "
                    f"(removed from allowlist but still over cap {CAP})"
                )

    if errors:
        for e in errors:
            print(e)
        return 1

    count = len(over_cap)
    print(
        f"[LOC-CAP-OK] {len(source_files)} source files scanned, "
        f"{count} over cap (all allowlisted), {len(allowlist)} allowlist entries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
