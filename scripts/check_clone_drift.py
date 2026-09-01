#!/usr/bin/env python3
"""Clone-drift gate: a registered function PAIR whose live normalized-AST
similarity falls below its registered floor is a CI failure.

Full motivation, mechanism, and what this deliberately does NOT catch are
in ``scripts/clone_drift_registry.py``'s module docstring — read that
first. In short: ``check_duplicate_predicates.py`` catches a NEW
independent copy of an already-consolidated predicate; ``check_fact_
registry_drift.py`` catches a scalar fact disagreeing across its declared
homes. This gate catches the third shape from the 2026-08-17 stitch-
congestion incident: two functions that WERE clones of one another
drifting apart structurally because a fix landed in one twin and never
propagated to the other (``_power_islands.py``'s ``_blocked``/via-drop
stub, cloned from a pre-fix ``_ground_plane.py`` and missing an entire
foreign-copper collision check for most of a day before PR #1332).

Usage
-----
  uv run --no-sync python scripts/check_clone_drift.py

Exit codes (mirrors check_duplicate_predicates.py / check_fact_registry_drift.py)
------------------------------------------------------------------------------------------
  0 - CLEAN: registry non-empty, every twin resolved in both files, every
      pair's live similarity >= its registered floor.
  3 - VIOLATION: at least one pair's live similarity fell below its floor.
  5 - TOOL ERROR: registry empty (vacuous), a home file missing, a
      qualname not found, or a qualname ambiguous. Never conflated with
      "0 violations".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clone_drift_registry as registry  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


def run(repo_root: Path) -> list[registry.PairResult]:
    if not registry.PAIRED_FUNCTIONS:
        raise registry.RegistryError(
            "PAIRED_FUNCTIONS is empty -- vacuous run, refusing to report clean"
        )
    return [registry.scan_pair(pair, repo_root) for pair in registry.PAIRED_FUNCTIONS]


def _print_report(results: list[registry.PairResult]) -> tuple[bool, bool]:
    has_violation = False
    has_tool_error = False

    for r in results:
        pair = r.pair
        print(f"=== {pair.name} ===")
        print(f"  A: {pair.file_a}::{pair.qualname_a}")
        print(f"  B: {pair.file_b}::{pair.qualname_b}")
        print(f"  Floor: {pair.min_similarity:.3f}")
        if r.error is not None:
            has_tool_error = True
            print(f"  TOOL ERROR  {r.error}")
        else:
            assert r.live_similarity is not None
            tag = "OK  " if r.passed else "DIFF"
            if not r.passed:
                has_violation = True
            print(f"  {tag}  live similarity: {r.live_similarity:.3f}")
        if pair.notes:
            print(f"  Notes: {pair.notes}")
        print()

    return has_violation, has_tool_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        results = run(repo_root)
    except registry.RegistryError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(EXIT_TOOL_ERROR)

    has_violation, has_tool_error = _print_report(results)

    if has_tool_error:
        state = "tool_error"
    elif has_violation:
        state = "violation"
    else:
        state = "clean"

    if state == "clean":
        print(
            f"PASS -- {len(registry.PAIRED_FUNCTIONS)} registered clone "
            f"pair(s), 0 below their similarity floor."
        )
    elif state == "violation":
        print(
            "FAILED -- a registered clone pair's live similarity fell "
            "below its registered floor. Either a fix landed in one twin "
            "and needs to be propagated to the other (the #1329 shape -- "
            "see scripts/clone_drift_registry.py's module docstring), or "
            "this is a genuinely new, intentional divergence that needs "
            "its own reviewed registry entry with a reason (the #1332 "
            "shape). Do not lower the floor to match an unreviewed "
            "divergence."
        )
    else:
        print(
            "TOOL ERROR -- a home file or qualname could not be resolved "
            "(missing, renamed, or ambiguous); the scan cannot be trusted "
            "as-is."
        )

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Clone-drift gate: {state}\n")
            f.write(f"- Pairs checked: {len(registry.PAIRED_FUNCTIONS)}\n")

    if state == "tool_error":
        sys.exit(EXIT_TOOL_ERROR)
    sys.exit(EXIT_VIOLATION if has_violation else EXIT_CLEAN)


if __name__ == "__main__":
    main()
