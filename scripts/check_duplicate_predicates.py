#!/usr/bin/env python3
"""Duplicate-predicate consolidation gate: a NEW independent copy of a
registered-as-consolidated predicate is a CI failure.

Motivating pattern (2026-08-13, docs/evidence/2026-08-13-defect-multiplier-
duplication-audit.md): four separate defect families investigated the same
day were all the same shape -- the identical logic independently
reimplemented in several places, so one defect became N (10 pad-resolution
call sites, 3+3 net-name boundary matchers, a Rust/Python oracle pair that
agreed only because they shared a bug, and 5 files each independently
carrying the rotation-quadrant trap). In each case the fix required finding
every copy, and in each case at least one copy was initially missed. A test
suite proves a *known* copy is correct; it does not stop someone from
writing copy N+1 six months later.

What this checks
-----------------
``scripts/duplicate_predicate_registry.py`` is the SSOT: for every
``ConsolidatedFamily`` it registers (an accidental-duplication family that
HAS been fixed -- one shared implementation, with every other copy reduced
to a thin delegating shim), this gate AST-scans the family's declared
``scan_paths`` for a definition of any of its ``def_names``. A definition
whose body does not call the family's ``delegate_call_name`` anywhere is a
violation: either a brand-new independent reimplementation, or a regression
where someone re-inlined logic that used to delegate.

This is deliberately an enumerated-scope gate (mirrors
``check_no_raw_rotation_trig.py``'s ``GUARDED_FILES`` rationale in that
script's own docstring), not a whole-repo AST sweep: a family's
``scan_paths`` names exactly the files that have already proven capable of
hosting an independent copy of that predicate, so the gate's coverage is a
visible, falsifiable, reviewable decision rather than "wherever the scan
happened to look today."

What this does NOT check
--------------------------
- It does not detect a BRAND NEW duplication family that has never been
  registered -- that is a measurement/audit exercise (see the evidence
  doc), not a mechanical gate. Registering a family here is itself the act
  of consolidating it.
- It does not touch ``OPEN_FINDINGS`` (identified-but-not-yet-consolidated
  duplication) or ``DELIBERATE_DUPLICATE_REGISTRIES`` (pinned oracles,
  already gated by ``check_oracle_hashes.py``) -- both are registered for
  visibility only, not scanned, per the registry module's own docstring.

Exit codes (mirrors scripts/check_no_raw_rotation_trig.py):
  0 - clean: no registered family has a non-delegating copy outside its SSOT.
  3 - violation: at least one new/regressed copy found.
  5 - tool_error: a registry entry has drifted from the repo (missing SSOT,
      missing scan path, empty scan_paths, or a scanned file no longer
      parses) -- never conflated with "0 violations".

Usage:
  uv run --no-sync python scripts/check_duplicate_predicates.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duplicate_predicate_registry as registry  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


def run(repo_root: Path) -> list[registry.Violation]:
    if not registry.CONSOLIDATED_FAMILIES:
        raise registry.RegistryError(
            "CONSOLIDATED_FAMILIES is empty -- vacuous run, refusing to report clean"
        )
    violations: list[registry.Violation] = []
    for family in registry.CONSOLIDATED_FAMILIES:
        violations.extend(registry.scan_family(family, repo_root))
    return violations


def _print_report(violations: list[registry.Violation]) -> None:
    families_checked = len(registry.CONSOLIDATED_FAMILIES)
    if violations:
        print(f"=== VIOLATIONS: {len(violations)} ===\n")
        for v in violations:
            print(f"  [{v.family}] {v.path}:{v.lineno}: {v.detail}")
        print(
            "\nFAILED -- a registered duplicate-predicate family has a copy "
            "that does not delegate to its SSOT. Either delegate to the "
            "registered implementation, or if this is a genuinely new "
            "independent implementation, update "
            "scripts/duplicate_predicate_registry.py deliberately (as an "
            "OpenFinding, not silently)."
        )
    else:
        print(
            f"PASS -- {families_checked} consolidated predicate famil"
            f"{'y' if families_checked == 1 else 'ies'} checked, 0 "
            "non-delegating copies found."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        violations = run(repo_root)
    except registry.RegistryError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(EXIT_TOOL_ERROR)

    _print_report(violations)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            state = "violation" if violations else "clean"
            f.write(f"\n### Duplicate-predicate consolidation gate: {state}\n")
            f.write(
                f"- Families checked: {len(registry.CONSOLIDATED_FAMILIES)}\n"
                f"- Violations: {len(violations)}\n"
            )

    sys.exit(EXIT_VIOLATION if violations else EXIT_CLEAN)


if __name__ == "__main__":
    main()
