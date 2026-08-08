#!/usr/bin/env python3
"""Corpus specificity run (STRATEGY.md build order step 5: "corpus already
exists" -- ``power_pcb_dataset/corpus/`` is that corpus).

Step 4 (``check_board_defect_corpus.py`` / ``check_component_defect_corpus.py``
/ ``check_ceiling_raise_evidence_corpus.py``) measures SENSITIVITY: does an
owning gate fire on a deliberately injected defect? Each of those corpora
also carries its own narrow specificity check (a "control violated" guard
confirming the SPECIFIC seeded ref/pad pair is clean on the CLEAN version of
the SAME board before trusting the mutated-board result). That is necessary
but not sufficient -- METHODOLOGY.md Sec. 5's "Reality" axis asks a broader
question: is the gate silent on boards it was never tuned against at all?

``power_pcb_dataset/corpus/`` already holds five independently-designed,
real KiCad boards (``manifest.yaml``): this project's own ``temper``, a
4-component ``minimal`` smoke board, the real open-source
``rp2040_designguide``, the real ``bitaxe_ultra`` (closest domain match --
power electronics), and the real ``piantor_right`` keyboard matrix. None of
these were designed BY, or FOR, this project's board-defect corpus -- they
are the false-positive oracle STRATEGY.md's step 5 rationale refers to
("corpus already exists").

What this script checks per board, and why each is scoped the way it is:

  * ``check_board_containment.py`` (the ``off-board`` class's owning gate):
    run against ALL FIVE boards. This is the one owning gate in the corpus
    that is genuinely board-agnostic (pure Edge.Cuts-vs-pad-copper
    geometry, no reference to any specific footprint ref) -- a real
    cross-board false-positive count is exactly what METHODOLOGY.md Sec. 5
    asks for here. A false positive is a ref reported outside the outline
    on a board where that is not actually true.

  * raw kicad-cli DRC category counts (``clearance``, ``courtyards_overlap``,
    ``hole_to_hole``, ``shorting_items``, ``copper_edge_clearance``) for
    the four NON-temper boards: reported as CONTEXT, not asserted as
    false-positive counts. Unlike containment, the ``clearance``/
    ``courtyard``/``hole-to-hole`` classes' actual failure signal is
    IDENTITY (``errors_naming_two_pads``/``errors_naming_both_refs``/
    ``errors_of_type_naming_both_refs`` against SPECIFIC refs seeded on the
    temper board -- R64/R67/C38/R48/C24/C2), which cannot be meaningfully
    evaluated against a foreign board's different ref set. A nonzero raw
    count on a real board is not necessarily a defect (real boards
    legitimately have some DRC findings) -- it is reported so a reader can
    judge, not treated as pass/fail. This is explicitly a scope limitation,
    not a claim that identity-level specificity was verified cross-board.

  * ``mpn_fabrication_gate.py`` / ``DrcRatchet.validate_raise_evidence``:
    NOT applicable to ``power_pcb_dataset/corpus/`` -- neither has atopile
    ``.ato`` source (mpn_fabrication_gate needs ``elec/src``-shaped
    value/mpn lines) or ceiling-raise semantics. Their specificity is
    already covered by the dedicated controls inside
    ``check_component_defect_corpus.py`` (clean fixture, 0 violations) and
    ``check_ceiling_raise_evidence_corpus.py`` (``no-op-control`` /
    ``fully-evidenced-raise-control``, both asserted zero-problems).

Exit codes:
  0 - pass: zero containment false positives across all five boards
  1 - a containment false positive was found (named in the output)
  2 - GATE ERROR: kicad-cli unavailable, corpus manifest/board missing

Usage:
  uv run --no-sync python scripts/check_corpus_specificity.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))

EXIT_PASS = 0
EXIT_FALSE_POSITIVE = 1
EXIT_GATE_ERROR = 2

CORPUS_MANIFEST = REPO_ROOT / "power_pcb_dataset" / "corpus" / "manifest.yaml"

DRC_CATEGORIES_OF_INTEREST = (
    "clearance",
    "courtyards_overlap",
    "hole_to_hole",
    "shorting_items",
    "copper_edge_clearance",
)


class GateError(RuntimeError):
    pass


@dataclass
class BoardResult:
    board_id: str
    pcb_path: str
    containment_refs_outside: list[str] = field(default_factory=list)
    containment_error: str | None = None
    drc_counts: dict[str, int] | None = None
    drc_error: str | None = None

    @property
    def containment_checked(self) -> bool:
        return self.containment_error is None


def load_manifest() -> list[dict[str, Any]]:
    import yaml

    if not CORPUS_MANIFEST.is_file():
        raise GateError(f"corpus manifest not found: {CORPUS_MANIFEST}")
    data = yaml.safe_load(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    boards = data.get("boards")
    if not boards:
        raise GateError(f"{CORPUS_MANIFEST} has no 'boards' entries")
    return boards


def run_specificity(repo_root: Path) -> tuple[bool, list[BoardResult]]:
    import shutil

    import check_board_containment

    if shutil.which("kicad-cli") is None:
        raise GateError(
            "kicad-cli is not available -- the DRC-context half of this run needs it "
            "(same constraint as check_board_defect_corpus.py)"
        )

    from collections import Counter

    from temper_placer.validation._drc_api import DrcRunnerError, run_drc

    corpus_root = repo_root / "power_pcb_dataset" / "corpus"
    results: list[BoardResult] = []

    for entry in load_manifest():
        board_id = entry["id"]
        pcb_rel = entry["pcb"]
        pcb_path = corpus_root / pcb_rel
        if not pcb_path.is_file():
            results.append(
                BoardResult(board_id=board_id, pcb_path=pcb_rel, drc_error=f"board file missing: {pcb_path}")
            )
            continue

        try:
            report = check_board_containment.analyze_board(pcb_path)
            refs_outside = sorted(report.refs_outside())
            containment_error = None
        except check_board_containment.GateError as exc:
            # An inability to CHECK is not evidence of cleanliness -- must
            # never be silently folded into "0 false positives" (the exact
            # anti-vacuity failure mode METHODOLOGY.md Sec. 4 warns against).
            refs_outside = []
            containment_error = f"containment gate error (NOT checked, NOT counted as clean): {exc}"

        try:
            drc_result = run_drc(pcb_path)
            counts = dict(Counter(e.rule for e in drc_result.errors))
            counts.update(Counter(w.rule for w in drc_result.warnings))
            drc_error = None
        except (DrcRunnerError, OSError) as exc:
            counts = None
            drc_error = f"DRC measurement failed: {exc}"

        results.append(
            BoardResult(
                board_id=board_id,
                pcb_path=pcb_rel,
                containment_refs_outside=refs_outside,
                containment_error=containment_error,
                drc_counts=counts,
                drc_error=drc_error,
            )
        )

    return specificity_ok(results), results


def specificity_ok(results: list[BoardResult]) -> bool:
    """Pure decision logic (unit-testable without kicad-cli): PASS requires
    BOTH zero containment findings among CHECKED boards AND no board
    silently skipped -- an unchecked board is a gate error, not a pass,
    exactly like check_board_defect_corpus.py's own GATE_ERROR tier. An
    empty result list is vacuously "nothing checked" and must never read as
    a pass (METHODOLOGY.md Sec. 4, anti-vacuous-truth)."""
    if not results:
        return False
    checked = [r for r in results if r.containment_checked]
    any_false_positive = any(r.containment_refs_outside for r in checked)
    any_unchecked = any(not r.containment_checked for r in results)
    return (not any_false_positive) and (not any_unchecked)


def _print_report(ok: bool, results: list[BoardResult]) -> None:
    print("Corpus specificity run (power_pcb_dataset/corpus/, 5 known-good boards):\n")
    for r in results:
        if not r.containment_checked:
            status = "UNCHECKED"
        elif r.containment_refs_outside:
            status = "FINDING"
        else:
            status = "clean"
        print(f"  [{status}] {r.board_id} ({r.pcb_path})")
        if r.containment_checked:
            print(f"      board_containment refs outside outline: {r.containment_refs_outside or 'none'}")
        else:
            print(f"      board_containment: {r.containment_error}")
        if r.drc_counts is not None:
            of_interest = {k: v for k, v in r.drc_counts.items() if k in DRC_CATEGORIES_OF_INTEREST}
            print(f"      DRC categories of interest (context only, not asserted): {of_interest or 'none'}")
        if r.drc_error:
            print(f"      [gate-error context] {r.drc_error}")

    n_boards = len(results)
    n_checked = sum(1 for r in results if r.containment_checked)
    n_clean = sum(1 for r in results if r.containment_checked and not r.containment_refs_outside)
    n_findings = sum(1 for r in results if r.containment_checked and r.containment_refs_outside)
    n_unchecked = n_boards - n_checked
    if ok:
        print(
            f"\nCorpus specificity: PASS -- 0 board_containment findings across "
            f"{n_boards} known-good boards (all {n_boards} checked)"
        )
    else:
        print(
            f"\nCorpus specificity: FAIL -- {n_findings}/{n_boards} boards have a "
            f"board_containment finding, {n_unchecked}/{n_boards} could not be checked "
            "(NOT counted as clean)"
        )


def main(argv: list[str] | None = None) -> int:
    try:
        ok, results = run_specificity(REPO_ROOT)
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    _print_report(ok, results)
    return EXIT_PASS if ok else EXIT_FALSE_POSITIVE


if __name__ == "__main__":
    sys.exit(main())
