#!/usr/bin/env python3
"""Corpus-fixture <-> real-board divergence gate.

Motivating defect (2026-08-11,
docs/evidence/2026-08-11-golden-fixture-regeneration-decision.md):
``power_pcb_dataset/corpus/temper/temper.kicad_pcb`` (33 components,
100x150mm) was frozen 2026-07-11 while the real ship target,
``pcb/temper.kicad_pcb``, grew to 169 components on a 152x234mm outline.
Nothing compared the two, so:

  1. ``test_golden_board_drc_regression`` kept solving against the frozen
     fixture, which still matched the PCL config's stale 100x150mm zone
     assumptions -- so config drift against the real board was
     undetectable from CI.
  2. Three independent CP-SAT spikes called the fixture "the real
     golden-board corpus" in code/docs and drew conclusions ("OR-Tools
     wins on the real board") that inverted at true 169-component scale.

A check comparing component count / outline dimensions between a corpus
fixture and its real-board counterpart, run on every PR touching either
file, would have caught the drift the day it started (2026-07-15, when the
real board's component count jumped 33 -> 169) rather than 27 days later.

Deliberately NOT prescriptive about whether a fixture should track its real
board -- see docs/evidence/2026-08-11-golden-fixture-regeneration-decision.md
for the full argument. A fixture can legitimately be:

  - ``role: real-board-snapshot`` -- MUST track the real board's component
    count (exact match required). A mismatch here is exactly the class of
    drift this gate exists to catch: BLOCKING.
  - ``role: independent-fixture`` -- deliberately small/fast/frozen (e.g.
    because CP-SAT cannot decide feasibility on the real board within the
    consuming test's timeout budget -- see the decision doc's own
    solve-time measurement). Divergence from the real board is EXPECTED
    and reported for information only, never a failure.

Every board entry in ``power_pcb_dataset/corpus/manifest.yaml`` that
declares a ``real_board_path`` MUST also declare a ``role`` -- an
undeclared role is a GATE ERROR (fail closed), not a silent skip: the
2026-08-11 incident was exactly a fixture nobody had ever committed, in
writing, to "this does or doesn't track the real board".

Exit codes:
  0 - PASSED: every real-board-snapshot fixture matches its real board's
      component count; no undeclared roles.
  3 - VIOLATION: a real-board-snapshot fixture has drifted from its real
      board's component count.
  5 - GATE ERROR: manifest/board missing or malformed, or a board declares
      real_board_path without a role.

Usage:
  uv run python scripts/check_corpus_fixture_realboard_divergence.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the dependency-free KiCad s-expression reader from the sibling
# correspondence gate rather than duplicating a tokenizer -- both gates
# need exactly the same two facts (Reference designators, Edge.Cuts bbox)
# out of a board file, for the same "no compiled-extension dependency, no
# solving" reasons documented there.
import check_pcl_config_board_correspondence as _corr  # noqa: E402
import yaml  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "power_pcb_dataset" / "corpus" / "manifest.yaml"

ROLE_SNAPSHOT = "real-board-snapshot"
ROLE_INDEPENDENT = "independent-fixture"
KNOWN_ROLES = frozenset({ROLE_SNAPSHOT, ROLE_INDEPENDENT})


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass
class BoardFacts:
    path: str
    n_components: int
    outline_wh_mm: tuple[float, float] | None


@dataclass
class DivergenceRecord:
    board_id: str
    role: str
    fixture: BoardFacts
    real: BoardFacts
    component_count_mismatch: bool


@dataclass
class Report:
    checked: list[DivergenceRecord] = field(default_factory=list)
    violations: list[DivergenceRecord] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    undeclared_role_boards: list[str] = field(default_factory=list)


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.is_file():
        raise GateError(f"corpus manifest not found: {manifest_path}")
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{manifest_path} is not valid YAML: {e}") from e
    if not isinstance(data, dict) or not data.get("boards"):
        raise GateError(f"{manifest_path} has no non-empty 'boards' list")
    return data["boards"]


def _facts(board_path: Path) -> BoardFacts:
    refs, bbox = _corr.parse_board(board_path)
    wh = None
    if bbox is not None:
        x_min, y_min, x_max, y_max = bbox
        wh = (x_max - x_min, y_max - y_min)
    return BoardFacts(path=str(board_path), n_components=len(refs), outline_wh_mm=wh)


def run(repo_root: Path, manifest_path: Path) -> tuple[str, Report]:
    report = Report()
    try:
        boards = load_manifest(manifest_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    for entry in boards:
        board_id = str(entry.get("id", "<unknown>"))
        real_board_rel = entry.get("real_board_path")
        if not real_board_rel:
            # No declared real-board counterpart -- this board makes no
            # claim about tracking anything, nothing to check.
            continue

        role = entry.get("role")
        if role not in KNOWN_ROLES:
            report.undeclared_role_boards.append(
                f"{board_id}: declares real_board_path={real_board_rel!r} but role="
                f"{role!r} is not one of {sorted(KNOWN_ROLES)} -- every board with a "
                "real-board counterpart must explicitly commit to whether it tracks it"
            )
            continue

        fixture_rel = entry.get("pcb")
        if not fixture_rel:
            report.tool_errors.append(f"{board_id}: manifest entry has no 'pcb' path")
            continue

        fixture_path = repo_root / "power_pcb_dataset" / "corpus" / fixture_rel
        real_path = repo_root / real_board_rel

        try:
            fixture_facts = _facts(fixture_path)
            real_facts = _facts(real_path)
        except _corr.GateError as e:
            report.tool_errors.append(f"{board_id}: {e}")
            continue

        mismatch = fixture_facts.n_components != real_facts.n_components
        record = DivergenceRecord(
            board_id=board_id,
            role=role,
            fixture=fixture_facts,
            real=real_facts,
            component_count_mismatch=mismatch,
        )
        report.checked.append(record)
        if role == ROLE_SNAPSHOT and mismatch:
            report.violations.append(record)

    if report.tool_errors:
        return "tool_error", report
    if report.undeclared_role_boards:
        return "tool_error", report
    if report.violations:
        return "violation", report
    return "clean", report


def _fmt_wh(wh: tuple[float, float] | None) -> str:
    if wh is None:
        return "no Edge.Cuts geometry"
    return f"{wh[0]:.1f}x{wh[1]:.1f}mm"


def _print_report(state: str, report: Report) -> None:
    print(f"Corpus fixture <-> real-board divergence gate -- {len(report.checked)} board(s) checked")

    for r in report.checked:
        tag = "SNAPSHOT" if r.role == ROLE_SNAPSHOT else "independent"
        status = "MISMATCH" if r.component_count_mismatch else "ok"
        print(
            f"  [{tag}/{status}] {r.board_id}: fixture={r.fixture.n_components} comp "
            f"({_fmt_wh(r.fixture.outline_wh_mm)}) vs real={r.real.n_components} comp "
            f"({_fmt_wh(r.real.outline_wh_mm)})"
        )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
    if report.undeclared_role_boards:
        print(f"\n{len(report.undeclared_role_boards)} UNDECLARED ROLE(S)")
        for e in report.undeclared_role_boards:
            print(f"  TOOL_ERROR {e}")

    if state == "clean":
        print("\nCorpus fixture <-> real-board divergence gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- {len(report.violations)} real-board-snapshot fixture(s) have "
            "drifted from their real board's component count"
        )
    else:
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    state, report = run(REPO_ROOT, args.manifest)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Corpus Fixture <-> Real-Board Divergence Gate: {state}\n")
            f.write(f"- Boards checked: {len(report.checked)}\n")
            for r in report.checked:
                f.write(
                    f"- `{r.board_id}` (role={r.role}): fixture={r.fixture.n_components} comp "
                    f"({_fmt_wh(r.fixture.outline_wh_mm)}) vs real={r.real.n_components} comp "
                    f"({_fmt_wh(r.real.outline_wh_mm)})"
                    + (" **MISMATCH**\n" if r.component_count_mismatch else "\n")
                )
            if report.tool_errors:
                f.write("\nTool errors:\n")
                for e in report.tool_errors:
                    f.write(f"- {e}\n")
            if report.undeclared_role_boards:
                f.write("\nUndeclared roles:\n")
                for e in report.undeclared_role_boards:
                    f.write(f"- {e}\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
