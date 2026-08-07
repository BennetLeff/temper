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

R7's taxonomy (MIGRATE / RETIRE / JUSTIFIED-KEEP) answers "should this compute
move to Rust?" The goal has since changed to "remove Python entirely" (R1),
which is a different question with a different taxonomy: BLOCKER-ORTOOLS /
BLOCKER-SCIPY / PORT / REPLACE / DELETE / OUT-OF-RUNTIME, recorded under the
ledger's ``removal_surfaces:`` list (docs/plans/2026-08-06-001-docs-python-
removal-retriage-plan.md and docs/evidence/2026-08-06-never-port-triage.md are
the source). Both axes are measured independently against the same file
inventory: a file can carry an R7 verdict, a removal verdict, both, or
(honestly) neither yet. ``removal_surfaces:`` is a second list rather than a
second field on the R7 ``surfaces:`` entries because the two taxonomies split
the tree at different granularities -- e.g. one R7 MIGRATE entry
(``router_v6/**``) covers clusters that land in three different removal
categories. Forcing one field per R7 entry would mean either fragmenting the
R7 entries to match removal-cluster boundaries (rewriting entries that are
already correct answers to the R7 question) or coarsening the removal
verdicts to fit the R7 grain (hiding real distinctions like the OR-Tools
blocker inside a MIGRATE-shaped bucket). A second list, checked against the
same roots, keeps both axes honest without touching the other's entries.

Exit codes:
    0  every file matches an entry on both axes, and every entry is well-formed
    1  a file matches no entry (on either axis), a file matches more than one
       entry (on either axis), or an entry is malformed

``--report`` prints both coverage tables and exits 0 regardless, for use in a
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

# R1 removal-question taxonomy (docs/plans/2026-08-06-001-docs-python-removal-
# retriage-plan.md). BLOCKER is split into its two named third-party
# dependencies rather than a single generic BLOCKER, because the two blockers
# have unrelated remediations (an OR-Tools FFI project vs. a scipy EDT port)
# and collapsing them would hide that difference exactly the way D6 forbids
# collapsing JUSTIFIED-KEEP reasons into "consolidation".
REMOVAL_VALID = {
    "BLOCKER-ORTOOLS",
    "BLOCKER-SCIPY",
    "PORT",
    "REPLACE",
    "DELETE",
    "OUT-OF-RUNTIME",
    "UNDECIDED",
}
REMOVAL_ORDER = (
    "BLOCKER-ORTOOLS",
    "BLOCKER-SCIPY",
    "PORT",
    "REPLACE",
    "DELETE",
    "OUT-OF-RUNTIME",
    "UNDECIDED",
)
REMOVAL_NEEDS_BLOCKER = {"BLOCKER-ORTOOLS", "BLOCKER-SCIPY"}
REMOVAL_NEEDS_NOTE = {"REPLACE", "DELETE", "OUT-OF-RUNTIME"}


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


def entry_pattern_matches(rel: str, surface: dict) -> bool:
    """``pattern:`` glob match, or exact membership in a ``paths:`` list.

    ``paths:`` is an explicit list of repo-relative file paths -- used
    (mainly by ``removal_surfaces:``) for clusters that are a handful of
    named files scattered across a directory, where a glob would either miss
    siblings or over-claim them. A surface carries exactly one of the two.
    """
    if "paths" in surface:
        return rel in set(surface["paths"])
    return matches(rel, surface["pattern"])


def entry_matches(rel: str, surface: dict) -> bool:
    """``entry_pattern_matches()`` plus an optional ``exclude:`` carve-out list.

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
    if not entry_pattern_matches(rel, surface):
        return False
    return rel not in set(surface.get("exclude", []) or [])


def _surface_desc(s: dict) -> str:
    """Human-readable identifier for a surface, for the 'owed' listing."""
    if s.get("pattern"):
        return s["pattern"]
    return ", ".join(s.get("paths", []))


def _label(surface: dict, i: int) -> str:
    if surface.get("pattern"):
        return surface["pattern"]
    paths = surface.get("paths", [])
    if paths:
        more = f" (+{len(paths) - 1} more)" if len(paths) > 1 else ""
        return f"{paths[0]}{more}"
    return f"<entry {i}>"


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


def validate_removal_entries(surfaces: list[dict]) -> list[str]:
    """Same shape as ``validate_entries``, for the removal-question axis.

    Every verdict except PORT and UNDECIDED requires a written reason: a
    BLOCKER needs the third-party dependency named (R1 D6's "consolidation is
    never sufficient" applies here too -- a blocker without a name is not
    checkable), and REPLACE/DELETE/OUT-OF-RUNTIME need a `note:` saying what
    replaces the surface, why it disappears, or why it is out of scope. PORT
    needs neither: "mechanical orchestration/glue, must move" is the default,
    unmarked case in the re-triage's own taxonomy.
    """
    errors: list[str] = []
    for i, s in enumerate(surfaces):
        label = _label(s, i)
        has_pattern = bool(s.get("pattern"))
        has_paths = bool(s.get("paths"))
        if not has_pattern and not has_paths:
            errors.append(f"{label}: entry needs a `pattern:` or a `paths:` list")
            continue
        if has_pattern and has_paths:
            errors.append(f"{label}: entry cannot have both `pattern:` and `paths:`")
        verdict = s.get("verdict")
        if verdict not in REMOVAL_VALID:
            errors.append(
                f"{label}: unknown removal verdict {verdict!r} "
                f"(expected one of {sorted(REMOVAL_VALID)})"
            )
            continue
        if verdict in REMOVAL_NEEDS_BLOCKER and not str(s.get("blocker", "")).strip():
            errors.append(
                f"{label}: {verdict} requires a `blocker:` naming the third-party "
                f"dependency and why no in-process Rust path exists"
            )
        if verdict in REMOVAL_NEEDS_NOTE and not str(s.get("note", "")).strip():
            errors.append(f"{label}: {verdict} requires a `note:` explaining the disposition")
        if verdict == "UNDECIDED" and not str(s.get("owed", "")).strip():
            errors.append(f"{label}: UNDECIDED requires an `owed:` naming what decision is missing")
        if has_pattern:
            for ex in s.get("exclude", []) or []:
                if not matches(ex, s["pattern"]):
                    errors.append(
                        f"{label}: exclude entry {ex!r} does not match this pattern -- a "
                        f"carve-out that excludes nothing is a stale or typo'd path"
                    )
    return errors


def compute_coverage(
    files: list[Path], surfaces: list[dict]
) -> tuple[dict[str, list[Path]], dict[str, int], list[str], list[str]]:
    by_verdict: dict[str, list[Path]] = defaultdict(list)
    loc_by_verdict: dict[str, int] = defaultdict(int)
    unmatched: list[str] = []
    multi: list[str] = []

    for f in files:
        rel = str(f.relative_to(REPO_ROOT))
        hit_idx = [i for i, s in enumerate(surfaces) if entry_matches(rel, s)]
        if not hit_idx:
            unmatched.append(rel)
            continue
        if len(hit_idx) > 1:
            labels = [_label(surfaces[i], i) for i in hit_idx]
            multi.append(f"{rel}  ->  {labels}")
            continue
        v = surfaces[hit_idx[0]]["verdict"]
        by_verdict[v].append(f)
        try:
            loc_by_verdict[v] += len(f.read_text(errors="ignore").splitlines())
        except OSError:
            pass

    return by_verdict, loc_by_verdict, unmatched, multi


def print_r7_report(files: list[Path], surfaces: list[dict], errors: list[str]) -> bool:
    by_verdict, loc_by_verdict, unmatched, multi = compute_coverage(files, surfaces)

    total_loc = sum(loc_by_verdict.values())
    print("Wave 4 residual verdict coverage (R7 -- 'should this move to Rust?')")
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
                print(f"    - {_surface_desc(s)}")

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
    return ok


def print_removal_report(files: list[Path], surfaces: list[dict], errors: list[str]) -> bool:
    by_verdict, loc_by_verdict, unmatched, multi = compute_coverage(files, surfaces)

    total_loc = sum(loc_by_verdict.values())
    all_loc = sum(len(f.read_text(errors="ignore").splitlines()) for f in files)
    print()
    print("Python removal coverage (R1 -- 'what has to happen before the")
    print("interpreter can go away?')")
    print()
    print(f"  {'verdict':<16} {'files':>6} {'LOC':>9}  {'share':>7}")
    for v in REMOVAL_ORDER:
        n, loc = len(by_verdict[v]), loc_by_verdict[v]
        share = (loc / total_loc * 100) if total_loc else 0.0
        print(f"  {v:<16} {n:>6} {loc:>9} {share:>6.1f}%")
    print(f"  {'recorded':<16} {sum(len(v) for v in by_verdict.values()):>6} {total_loc:>9}")
    print(f"  {'unmatched':<16} {len(unmatched):>6} {all_loc - total_loc:>9}")

    decided = total_loc - loc_by_verdict["UNDECIDED"]
    denom = all_loc
    pct = (decided / denom * 100) if denom else 0.0
    print()
    print(
        f"  R1 removal-verdict coverage: {pct:.1f}% of the {denom} LOC under the "
        f"ledger's roots has a recorded removal disposition"
    )
    print(
        "  (this is necessarily a floor, not a ceiling: it is scored against "
        "every *.py file under the roots, and the removal re-triage only "
        "ever scored the temper_placer/temper_workflow residual surface --"
        " scripts/, benchmarks/, and the test suite are UNDECIDED by omission,"
        " not by a recorded verdict, until someone triages them.)"
    )

    if by_verdict["UNDECIDED"]:
        print()
        print("  Owed decisions (explicitly UNDECIDED entries):")
        for s in surfaces:
            if s["verdict"] == "UNDECIDED":
                print(f"    - {_surface_desc(s)}: {s.get('owed', '')}")

    ok = True
    if unmatched:
        ok = False
        print()
        print(f"  FAIL: {len(unmatched)} file(s) carry no removal verdict:")
        for u in unmatched[:20]:
            print(f"    {u}")
        if len(unmatched) > 20:
            print(f"    ... and {len(unmatched) - 20} more")
    if multi:
        ok = False
        print()
        print(f"  FAIL: {len(multi)} file(s) match more than one removal entry:")
        for m in multi[:20]:
            print(f"    {m}")
    if errors:
        ok = False
        print()
        print("  FAIL: malformed removal_surfaces entries:")
        for e in errors:
            print(f"    {e}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print coverage and always exit 0")
    ap.add_argument(
        "--removal",
        action="store_true",
        help=(
            "also gate the exit code on R1 removal-axis coverage, not just R7. "
            "Opt-in: the removal_surfaces backlog is large and honestly "
            "UNDECIDED by design (see docs/wave4-verdicts.yaml), so the "
            "existing CI wiring (a bare, no-flag invocation) intentionally "
            "keeps failing only on R7 until that backlog is worked down."
        ),
    )
    args = ap.parse_args()

    ledger = load_ledger()
    surfaces = ledger.get("surfaces", [])
    removal_surfaces = ledger.get("removal_surfaces", [])
    roots = ledger.get("roots", [])

    errors = validate_entries(surfaces)
    removal_errors = validate_removal_entries(removal_surfaces)

    files = python_files(roots)

    r7_ok = print_r7_report(files, surfaces, errors)
    removal_ok = print_removal_report(files, removal_surfaces, removal_errors)

    if args.report:
        return 0
    gate_ok = r7_ok and (removal_ok if args.removal else True)
    if not gate_ok:
        return 1
    print()
    if args.removal:
        print(
            "  Ledger is well-formed and covers every Python file under its "
            "roots on both axes."
        )
    else:
        print(
            "  Ledger is well-formed and covers every Python file under its "
            "roots on the R7 axis. (R1 removal-axis coverage is reported "
            "above but not gated here; pass --removal to enforce it too.)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
