#!/usr/bin/env python3
"""Detector for unexpected `git stash` activity (growth or disappearance).

The reference-transaction hook installed by install_git_stash_guard.py
reliably blocks `git stash push`/`save`/`clear`, but it cannot block
`git stash apply`, nor `git stash pop`/`drop` of an entry that isn't the
last one left in the stack (git rewrites the reflog directly for those
cases, bypassing the hookable ref-transaction API entirely -- see
scripts/git-hooks/reference-transaction for the full explanation and the
tested evidence). This script is the documented fallback for that gap: it
snapshots the current stash stack and diffs against the last snapshot, so
unexpected pushes, pops, or drops are visible even though they can't be
blocked outright.

This is NOT a CI gate -- CI runners are fresh clones with no shared .git
and no history to diff against. Run it manually, from a `/loop`, or on a
timer, on the actual dev machine that hosts the shared .git directory.

Usage:
  uv run python scripts/check_stash_stack_gate.py           # report + update snapshot
  uv run python scripts/check_stash_stack_gate.py --dry-run # report only, don't update
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def git_common_dir() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(out.stdout.strip())
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def current_stash_entries() -> list[str]:
    """Return reflog lines for refs/stash, oldest-safe format: 'sha subject'."""
    out = subprocess.run(
        ["git", "reflog", "show", "--format=%H\t%gs", "refs/stash"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        # No refs/stash at all (empty stack) is not an error.
        return []
    return [line for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not update the snapshot.")
    args = parser.parse_args()

    snapshot_path = git_common_dir() / "stash-guard-snapshot.json"
    current = current_stash_entries()
    is_baseline = not snapshot_path.is_file()

    previous: list[str] = []
    if not is_baseline:
        try:
            previous = json.loads(snapshot_path.read_text())
        except (json.JSONDecodeError, OSError):
            previous = []

    prev_set = set(previous)
    curr_set = set(current)
    added = [e for e in current if e not in prev_set]
    removed = [e for e in previous if e not in curr_set]

    print(f"[stash-guard-detector] current stack depth: {len(current)}")
    if is_baseline:
        print("[stash-guard-detector] no prior snapshot -- this is the baseline run")
    else:
        if added:
            print(f"[stash-guard-detector] {len(added)} entries ADDED since last snapshot:")
            for e in added:
                print(f"    + {e}")
        if removed:
            print(f"[stash-guard-detector] {len(removed)} entries REMOVED since last snapshot "
                  "(popped/dropped/cleared -- verify this was expected):")
            for e in removed:
                print(f"    - {e}")
        if not added and not removed:
            print("[stash-guard-detector] no change since last snapshot")

    if not args.dry_run:
        snapshot_path.write_text(json.dumps(current, indent=2))

    if is_baseline:
        return 0
    return 1 if (added or removed) else 0


if __name__ == "__main__":
    sys.exit(main())
