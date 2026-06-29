#!/usr/bin/env python3
"""Type-check gate: fail CI if any file has more mypy errors than its allowlist baseline.

Per-file monotonic-shrink: each file in scope has an allowlist entry recording
its current mypy error count.  CI fails if a file grows beyond its baseline.
CI warns if a file has fewer errors (stale entry — reward for shrinking).

Modes:
  --init        Populate .typecheck-allowlist with current mypy error counts.
                CI passes on this commit.
  (default)     Run mypy, compare per-file error counts against allowlist.
                Fail on any file exceeding its baseline.
                Warn on stale entries (files now with fewer errors).
  --check-shrink  Compare allowlist vs origin/main. Fail if entries removed
                  without corresponding error reduction.

Usage:
  python3 scripts/check_typecheck_gate.py
  python3 scripts/check_typecheck_gate.py --init
  python3 scripts/check_typecheck_gate.py --check-shrink
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ALLOWLIST_PATH = Path(".typecheck-allowlist")
SCOPE = ["packages/temper-placer/src", "packages/temper-workflow/src", "packages/temper-tools/src"]

# mypy error line format: path:line: error: message  [code]
MYPY_LINE_RE = re.compile(r"^(.+?):(\d+): error: (.+?)(?:\[([a-z-]+)\])?$")


def run_mypy() -> dict[str, int]:
    """Run mypy and return per-file error counts."""
    counts: dict[str, int] = defaultdict(int)
    for scope in SCOPE:
        scope_path = Path(scope)
        if not scope_path.exists():
            continue
        result = subprocess.run(
            ["uv", "run", "mypy", str(scope_path), "--ignore-missing-imports"],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            m = MYPY_LINE_RE.match(line.strip())
            if m:
                filepath = m.group(1)
                counts[filepath] += 1
    return dict(counts)


def load_allowlist() -> dict[str, int]:
    """Load the allowlist: file -> error count."""
    if not ALLOWLIST_PATH.exists():
        return {}
    entries = {}
    with open(ALLOWLIST_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                filepath = parts[0]
                try:
                    count = int(parts[1])
                    entries[filepath] = count
                except ValueError:
                    continue
    return entries


def init_allowlist() -> dict[str, int]:
    """Populate allowlist from current mypy error counts."""
    current = run_mypy()
    with open(ALLOWLIST_PATH, "w") as f:
        f.write("# Type-check allowlist — monotonic-shrink baseline\n")
        f.write(f"# {sum(current.values())} total errors across {len(current)} files\n")
        f.write("# <filepath> <max-allowed-error-count>\n")
        f.write("# Do not increase these numbers. Fix the errors.\n\n")
        for filepath in sorted(current.keys()):
            f.write(f"{filepath} {current[filepath]}\n")
    print(f"Initialized {ALLOWLIST_PATH} with {sum(current.values())} errors across {len(current)} files")
    return current


def check_shrink(allowlist: dict[str, int]) -> int:
    """Check that allowlist entries removed from origin/main had corresponding error fixes."""
    result = subprocess.run(
        ["git", "diff", "origin/main", "--", str(ALLOWLIST_PATH)],
        capture_output=True, text=True,
    )
    removed = []
    added = []
    for line in result.stdout.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("#"):
                parts = stripped.split()
                if len(parts) >= 2 and parts[0] not in added:
                    removed.append(parts[0])
        elif line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("#"):
                parts = stripped.split()
                if len(parts) >= 2:
                    added.append(parts[0])

    if not removed:
        print("Allowlist unchanged or only additions — OK")
        return 0

    # Check each removed entry against current errors
    current = run_mypy()
    allowlist_current = load_allowlist()
    violations = 0
    for filepath in removed:
        current_count = current.get(filepath, 0)
        old_allowed = allowlist.get(filepath, 0)
        if filepath in allowlist_current:
            # Entry still exists — was just reduced. Verify reduction matches.
            new_allowed = allowlist_current[filepath]
            if new_allowed > old_allowed:
                print(f"FAIL: {filepath} allowlist grew: {old_allowed} -> {new_allowed}")
                violations += 1
        else:
            # Entry removed entirely — verify errors are actually gone
            if current_count > 0:
                print(f"FAIL: {filepath} removed from allowlist but still has {current_count} errors")
                violations += 1
            else:
                print(f"OK: {filepath} removed — errors fixed")

    if violations:
        print(f"\n{violations} allowlist shrink violation(s)")
    return violations


def main():
    parser = argparse.ArgumentParser(description="Type-check monotonic-shrink gate")
    parser.add_argument("--init", action="store_true", help="Populate allowlist from current errors")
    parser.add_argument("--check-shrink", action="store_true", help="Verify allowlist shrinkage is legitimate")
    args = parser.parse_args()

    if args.init:
        init_allowlist()
        return 0

    if args.check_shrink:
        allowlist = load_allowlist()
        if not allowlist:
            print("No allowlist found. Run --init first.")
            return 0
        return check_shrink(allowlist)

    # Default mode: gate check
    current = run_mypy()
    allowlist = load_allowlist()

    if not allowlist:
        print("No allowlist found. Run --init first.")
        return 0

    violations = 0
    stale = 0

    # Check current files against allowlist
    all_files = set(list(current.keys()) + list(allowlist.keys()))
    for filepath in sorted(all_files):
        current_count = current.get(filepath, 0)
        allowed = allowlist.get(filepath, 0)

        if filepath not in allowlist:
            if current_count > 0:
                print(f"NEW: {filepath} has {current_count} errors (not in allowlist)")
                violations += 1
        elif current_count > allowed:
            print(f"REGRESSION: {filepath}: {current_count} errors > {allowed} allowed")
            violations += 1
        elif current_count < allowed:
            print(f"STALE: {filepath}: {current_count} errors < {allowed} allowed — update allowlist!")
            stale += 1

    total_current = sum(current.values())
    total_allowed = sum(allowlist.values())

    print(f"\nTotal: {total_current} errors in {len(current)} files (baseline: {total_allowed})")
    if stale:
        print(f"  {stale} stale allowlist entries — update with --init to lock in improvements")
    if violations:
        print(f"  {violations} regression(s) — fix the errors or update the allowlist")
        return 1

    print("OK — all files within allowlist baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
