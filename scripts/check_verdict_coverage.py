#!/usr/bin/env python3
"""Measure Wave 4 residual-verdict coverage.

Wave 4's R7 says the program "is complete only when every surface has a
recorded verdict -- migrated, retired, or kept with a written justification."
That is a completion condition nobody can check by reading, so this turns it
into a number: every Python file under the ledger's roots must match exactly
one entry in ``docs/wave4-verdicts.yaml``, and anything unmatched is UNDECIDED.

Two properties this deliberately has:

* **UNDECIDED is reported, not tolerated silently.** It is the backlog R7
  measures. Inventing verdicts to reach 100% would make the ledger a
  decoration -- the exact failure mode this program keeps finding elsewhere.
* **A JUSTIFIED-KEEP must carry a blocker.** D6: "consolidation" alone is never
  sufficient. An entry without one fails.

Exit codes:
    0  every file matches an entry, and every entry is well-formed
    1  a file matches no entry, a file matches more than one, or an entry is
       malformed (missing blocker on a keep, missing phase on a migrate,
       unknown verdict)

``--report`` prints the coverage table and exits 0 regardless, for use in a
summary step.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "docs" / "wave4-verdicts.yaml"

VALID = {"MIGRATE", "RETIRE", "JUSTIFIED-KEEP", "UNDECIDED"}


def load_ledger() -> dict:
    try:
        import yaml
    except ImportError:
        print("PyYAML is required: uv run python3 scripts/check_verdict_coverage.py")
        raise SystemExit(2) from None
    if not LEDGER.exists():
        print(f"FAIL: ledger not found at {LEDGER.relative_to(REPO_ROOT)}")
        raise SystemExit(1)
    with open(LEDGER) as f:
        return yaml.safe_load(f)


def python_files(roots: list[str]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            print(f"FAIL: ledger root does not exist: {root}")
            raise SystemExit(1)
        out.extend(p for p in base.rglob("*.py") if ".venv" not in p.parts)
    return sorted(out)


def matches(rel: str, pattern: str) -> bool:
    """Glob with path-separator semantics fnmatch does not provide.

    `a/**` is recursive: it matches `a/b.py` and `a/b/c/d.py`.
    `a/*.py` is NOT: it matches `a/b.py` but not `a/b/c.py`. Plain
    ``fnmatch`` gets the second case wrong because its ``*`` happily crosses
    ``/``, which silently made a package-root pattern shadow every subpackage.
    """
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    pat_dir, pat_base = os.path.split(pattern)
    rel_dir, rel_base = os.path.split(rel)
    return pat_dir == rel_dir and fnmatch.fnmatch(rel_base, pat_base)


def entry_matches(rel: str, surface: dict) -> bool:
    """``matches()`` plus an optional ``exclude:`` carve-out list.

    A surface may list exact repo-relative paths under ``exclude:`` that its
    pattern would otherwise claim, so a single file inside a broad surface can
    carry its own verdict (R3 splits a surface where one verdict does not fit
    all of it). This keeps the "exactly one entry per file" invariant intact
    rather than resolving overlaps by precedence, so a carve-out stays visible
    and auditable in the ledger instead of being implied by pattern ordering.

    Both mistakes fail closed: a typo'd exclude leaves the file matching both
    entries (reported as a multi-match), and excluding a file that no other
    entry claims leaves it unmatched (reported as UNDECIDED coverage failure).
    """
    if not matches(rel, surface["pattern"]):
        return False
    return rel not in set(surface.get("exclude", []) or [])


def validate_entries(surfaces: list[dict]) -> list[str]:
    errors: list[str] = []
    for i, s in enumerate(surfaces):
        pat = s.get("pattern", f"<entry {i}>")
        verdict = s.get("verdict")
        if verdict not in VALID:
            errors.append(f"{pat}: unknown verdict {verdict!r} (expected one of {sorted(VALID)})")
            continue
        if verdict == "JUSTIFIED-KEEP" and not str(s.get("blocker", "")).strip():
            errors.append(
                f"{pat}: JUSTIFIED-KEEP requires a `blocker:` naming a concrete "
                f"reason -- D6 says consolidation alone is never sufficient"
            )
        if verdict == "MIGRATE" and s.get("phase") is None:
            errors.append(f"{pat}: MIGRATE requires a `phase:`")
        if verdict == "UNDECIDED" and not str(s.get("owed", "")).strip():
            errors.append(f"{pat}: UNDECIDED requires an `owed:` naming what decision is missing")
        if verdict == "RETIRE" and not str(s.get("justification", "")).strip():
            errors.append(
                f"{pat}: RETIRE requires a `justification:` -- R3 defines RETIRE as "
                f"'dead or obsolete, deleted with justification'"
            )
        for ex in s.get("exclude", []) or []:
            if not matches(ex, s["pattern"]):
                errors.append(
                    f"{pat}: exclude entry {ex!r} does not match this pattern -- a "
                    f"carve-out that excludes nothing is a stale or typo'd path"
                )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print coverage and always exit 0")
    args = ap.parse_args()

    ledger = load_ledger()
    surfaces = ledger.get("surfaces", [])
    roots = ledger.get("roots", [])

    errors = validate_entries(surfaces)

    files = python_files(roots)
    by_verdict: dict[str, list[Path]] = defaultdict(list)
    loc_by_verdict: dict[str, int] = defaultdict(int)
    unmatched: list[str] = []
    multi: list[str] = []

    for f in files:
        rel = str(f.relative_to(REPO_ROOT))
        hits = [s for s in surfaces if entry_matches(rel, s)]
        if not hits:
            unmatched.append(rel)
            continue
        if len(hits) > 1:
            multi.append(f"{rel}  ->  {[h['pattern'] for h in hits]}")
            continue
        v = hits[0]["verdict"]
        by_verdict[v].append(f)
        try:
            loc_by_verdict[v] += len(f.read_text(errors="ignore").splitlines())
        except OSError:
            pass

    total_loc = sum(loc_by_verdict.values())
    print("Wave 4 residual verdict coverage (R7)")
    print()
    print(f"  {'verdict':<16} {'files':>6} {'LOC':>9}  {'share':>7}")
    for v in ("MIGRATE", "RETIRE", "JUSTIFIED-KEEP", "UNDECIDED"):
        n, loc = len(by_verdict[v]), loc_by_verdict[v]
        share = (loc / total_loc * 100) if total_loc else 0.0
        print(f"  {v:<16} {n:>6} {loc:>9} {share:>6.1f}%")
    print(f"  {'TOTAL':<16} {len(files):>6} {total_loc:>9}")

    decided = total_loc - loc_by_verdict["UNDECIDED"]
    pct = (decided / total_loc * 100) if total_loc else 0.0
    print()
    print(f"  R7 completion: {pct:.1f}% of LOC has a recorded verdict")

    if by_verdict["UNDECIDED"]:
        print()
        print("  Owed decisions:")
        for s in surfaces:
            if s["verdict"] == "UNDECIDED":
                print(f"    - {s['pattern']}")

    ok = True
    if unmatched:
        ok = False
        print()
        print(f"  FAIL: {len(unmatched)} file(s) match no ledger entry:")
        for u in unmatched[:20]:
            print(f"    {u}")
        if len(unmatched) > 20:
            print(f"    ... and {len(unmatched) - 20} more")
    if multi:
        ok = False
        print()
        print(f"  FAIL: {len(multi)} file(s) match more than one entry:")
        for m in multi[:20]:
            print(f"    {m}")
    if errors:
        ok = False
        print()
        print("  FAIL: malformed ledger entries:")
        for e in errors:
            print(f"    {e}")

    if args.report:
        return 0
    if not ok:
        return 1
    print()
    print("  Ledger is well-formed and covers every Python file under its roots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
