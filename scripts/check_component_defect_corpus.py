#!/usr/bin/env python3
"""Component-value/MPN-fabrication defect corpus runner (STRATEGY.md build
order step 4, 2026-08-07).

A second constraint family alongside ``check_board_defect_corpus.py``'s PCB
geometry classes: this one exercises ``scripts/mpn_fabrication_gate.py``
(the fabricated/wrong-value passive-component gate) against synthetic
fixtures, never against ``elec/src`` (task rule: do not modify elec/). Both
defect classes are real, previously-found incidents in this project's own
history (docs/STRATEGY.md, 2026-07-27 entries) -- "prefer classes drawn
from real incidents over invented ones."

For each class this runner:

  1. re-derives a mutated fixture from the committed clean fixture
     (``scripts/component_defect_fixtures/clean.ato``) via
     ``scripts/component_defect_mutator.py`` -- the clean fixture is never
     modified;
  2. independently re-parses the mutated fixture with
     ``mpn_fabrication_gate.parse_ato_file`` (the SAME parser the gate
     itself uses, but called directly here, before any gate-level pass/fail
     decision) and asserts the target ref's declared value/MPN actually
     changed -- injector self-verification, independent of the gate's own
     verdict (METHODOLOGY.md Sec. 5);
  3. runs the REAL gate logic (``mpn_fabrication_gate.analyze()``, not a
     reimplementation) against both the clean fixture's parts and the
     mutated fixture's parts, and asserts the class's failure signal: the
     gate must report a NEW violation naming the target ref on the mutated
     fixture, of the expected ``kind`` ("eseries" or "decode"), and must
     report ZERO violations on the clean fixture (both halves of R9).

Exit codes:
  0 - pass: both classes covered, clean fixture green
  1 - corpus failure: an uncovered class, or the clean fixture is not green
  2 - GATE ERROR: fixture missing, mutation failed, or a measurement error
      -- never reported as a pass

Usage:
  uv run --no-sync python scripts/check_component_defect_corpus.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

EXIT_PASS = 0
EXIT_CORPUS_FAIL = 1
EXIT_GATE_ERROR = 2

CLEAN_FIXTURE = REPO_ROOT / "scripts" / "component_defect_fixtures" / "clean.ato"

# class name -> expected Finding.kind ("eseries" or "decode") that class's
# mutation must produce -- part of the class-to-gate mapping (mirrors
# check_board_defect_corpus.py's owning_gates table for the PCB family).
EXPECTED_KIND = {
    "fabricated-mpn": "eseries",
    "mpn-value-mismatch": "decode",
}


class GateError(RuntimeError):
    """A corpus input or measurement is unavailable -- fail closed (exit 2),
    never reported as a pass."""


@dataclass
class ClassVerdict:
    name: str
    ok: bool
    message: str
    gate_error: bool = False


@dataclass
class CorpusReport:
    ok: bool
    exit_code: int
    clean_violation_count: int
    class_verdicts: list[ClassVerdict] = field(default_factory=list)
    workdir: str | None = None


def _parts_for_fixture(fixture_path: Path, workdir: Path) -> list[Any]:
    """Parse *fixture_path* via the REAL gate parser, using *workdir* as the
    ``repo_root`` argument so ``ParsedPart.file`` is relative to something
    sensible -- the parser itself does not care what "repo_root" means, it
    only uses it to compute a display-friendly relative path."""
    import mpn_fabrication_gate as gate

    return gate.parse_ato_file(fixture_path, workdir)


def run_corpus(repo_root: Path, workdir: Path | None = None) -> CorpusReport:
    import mpn_fabrication_gate as gate
    from component_defect_mutator import MutationError, apply_mutation

    if not CLEAN_FIXTURE.is_file():
        raise GateError(f"clean fixture not found: {CLEAN_FIXTURE}")

    workdir_path = (
        Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="component-defect-corpus-"))
    )
    workdir_path.mkdir(parents=True, exist_ok=True)

    empty_allowlist = workdir_path / "no-such-allowlist.yaml"  # load_allowlist([]) on a missing path
    allowlist = gate.load_allowlist(empty_allowlist)
    if allowlist is None:
        raise GateError("gate.load_allowlist() returned None for a nonexistent path -- should be []")

    clean_parts = _parts_for_fixture(CLEAN_FIXTURE, REPO_ROOT)
    if not clean_parts:
        raise GateError(
            f"0 parts parsed from the clean fixture {CLEAN_FIXTURE} -- fixture syntax has "
            "drifted from mpn_fabrication_gate.VALUE_RE/MPN_RE"
        )
    clean_analysis = gate.analyze(clean_parts, allowlist)
    clean_violation_count = len(clean_analysis.new_violations)

    class_verdicts: list[ClassVerdict] = []

    if clean_violation_count != 0:
        # Anti-vacuity control: the clean fixture must itself be violation-
        # free, or no mutated-fixture comparison proves anything.
        class_verdicts.append(
            ClassVerdict(
                name="clean-fixture-control",
                ok=False,
                message=(
                    f"clean fixture {CLEAN_FIXTURE} already reports "
                    f"{clean_violation_count} violation(s): "
                    f"{[f.detail for f in clean_analysis.new_violations]} -- "
                    "no mutated-fixture comparison below can be trusted "
                    "until this is fixed"
                ),
            )
        )

    for class_name, expected_kind in EXPECTED_KIND.items():
        out_path = workdir_path / f"{class_name}.ato"
        try:
            mutation_result = apply_mutation(class_name, out_path, seed=1)
        except MutationError as exc:
            class_verdicts.append(
                ClassVerdict(
                    name=class_name,
                    ok=False,
                    gate_error=True,
                    message=f"gate error: injector failed: {exc}",
                )
            )
            continue

        ref = mutation_result.summary["ref"]

        # --- injector self-verification, independent of the gate's verdict ---
        mutated_parts = _parts_for_fixture(out_path, workdir_path)
        mutated_target = next((p for p in mutated_parts if p.ref == ref), None)
        clean_target = next((p for p in clean_parts if p.ref == ref), None)
        if mutated_target is None or clean_target is None:
            class_verdicts.append(
                ClassVerdict(
                    name=class_name,
                    ok=False,
                    gate_error=True,
                    message=(
                        f"gate error: independent re-parse of the mutated fixture found no "
                        f"part named {ref!r} (clean_target={clean_target!r}, "
                        f"mutated_target={mutated_target!r})"
                    ),
                )
            )
            continue
        if (
            mutated_target.declared_value == clean_target.declared_value
            and mutated_target.mpn == clean_target.mpn
        ):
            class_verdicts.append(
                ClassVerdict(
                    name=class_name,
                    ok=False,
                    gate_error=True,
                    message=(
                        f"gate error: injector no-op -- independent re-parse shows {ref}'s "
                        "declared value AND mpn are unchanged from the clean fixture "
                        f"(value={mutated_target.declared_value}, mpn={mutated_target.mpn!r})"
                    ),
                )
            )
            continue

        # --- the real gate, run against the mutated fixture's parts ---
        mutated_analysis = gate.analyze(mutated_parts, allowlist)
        matching = [
            f
            for f in mutated_analysis.new_violations
            if f.part.ref == ref and f.kind == expected_kind
        ]

        if clean_violation_count != 0:
            # Already reported above; don't also report every class as
            # uncovered because of an unrelated control failure.
            continue

        if matching:
            class_verdicts.append(
                ClassVerdict(
                    name=class_name,
                    ok=True,
                    message=(
                        f"{class_name}: owning gate mpn_fabrication_gate fired: "
                        f"{len(matching)} finding(s) of kind {expected_kind!r} name {ref} "
                        f"on the mutated fixture and none on the clean fixture "
                        f"[{matching[0].detail}]"
                    ),
                )
            )
        else:
            all_kinds = [(f.part.ref, f.kind, f.detail) for f in mutated_analysis.new_violations]
            class_verdicts.append(
                ClassVerdict(
                    name=class_name,
                    ok=False,
                    message=(
                        f"{class_name}: uncovered class -- no {expected_kind!r} finding names "
                        f"{ref} on the mutated fixture (all findings: {all_kinds})"
                    ),
                )
            )

    any_gate_error = any(v.gate_error for v in class_verdicts)
    any_uncovered = any(not v.ok and not v.gate_error for v in class_verdicts)
    ok = not any_gate_error and not any_uncovered

    return CorpusReport(
        ok=ok,
        exit_code=EXIT_GATE_ERROR if any_gate_error else (EXIT_PASS if ok else EXIT_CORPUS_FAIL),
        clean_violation_count=clean_violation_count,
        class_verdicts=class_verdicts,
        workdir=str(workdir_path),
    )


def _print_report(report: CorpusReport) -> None:
    print(f"clean fixture violations: {report.clean_violation_count}")
    print("\ndefect classes:")
    for verdict in report.class_verdicts:
        status = "GATE-ERROR" if verdict.gate_error else ("PASS" if verdict.ok else "FAIL")
        print(f"  [{status}] {verdict.name}: {verdict.message}")

    n_covered = sum(1 for v in report.class_verdicts if v.ok)
    n_total = len(EXPECTED_KIND)
    if report.ok:
        print(f"\nComponent-defect corpus: PASS -- {n_covered}/{n_total} classes covered")
    else:
        print(
            f"\nComponent-defect corpus: FAIL -- {n_covered}/{n_total} classes covered "
            f"(fixtures left in {report.workdir} for inspection)"
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--workdir", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        report = run_corpus(args.repo_root, workdir=args.workdir)
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    _print_report(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
