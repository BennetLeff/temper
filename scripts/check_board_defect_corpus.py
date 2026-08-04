#!/usr/bin/env python3
"""Board-defect mutation corpus runner (plan 2026-08-02-024, R38).

For each of the three real defect classes (component off-board, pad short,
creepage crossing) this runner:

  1. re-derives a mutated copy of the committed ``pcb/temper.kicad_pcb``
     from the seed manifest (``scripts/board_defect_corpus.yaml``) via
     ``scripts/board_defect_mutator.py`` -- the committed board is never
     modified (KTD1, KTD3);
  2. runs the class's OWNING gate(s) against the mutated board (KTD2) and
     asserts the class's failure signal -- a count-delta: the mutated
     board's count must exceed the clean board's count and, for DRC
     categories, the recorded ``drc_ceiling.json`` ceiling;
  3. fails the run if any class has no failing gate (uncovered class), or
     if the clean board violates the anti-vacuity control.

The clean-board anti-vacuity control is scoped to the corpus's DRC gate
categories that are GREEN on the committed board today
(``courtyards_overlap``/``copper_edge_clearance``/``shorting_items`` at or
below their ``drc_ceiling.json`` ceilings). The REQ-SAFE-01 creepage gate
is RED on main today (99 DC_BUS<->LV_CONTROL creepage violations measured
2026-08-02), so it is excluded from the anti-vacuity control and its class
is asserted via per-class count-delta against the clean measurement as the
documented known-finding baseline -- see ``scripts/board_defect_corpus.yaml``
``classes.creepage.baseline_note``.

Measurement paths are the canonical ones: DRC via
``temper_placer.validation._drc_api.run_drc`` (which bakes in
``--all-track-errors`` -- see that module's comment for why bare kicad-cli
is not reproducible), and creepage via the REQ-SAFE-01 validator itself
(``tests.requirements.safety._real_board_fixture.load_real_board_placement``
+ ``verify_iec60335_compliance``), pointed at the mutated board copy.

Exit codes:
  0 - pass: all classes covered, clean board anti-vacuity control green
  1 - corpus failure: an uncovered class, or a clean-board anti-vacuity
      violation (the defect class is named in the output)
  2 - GATE ERROR: kicad-cli unavailable, board missing, netlist/manifest
      missing, or a measurement failed -- never reported as a pass

Usage:
  uv run --no-sync python scripts/check_board_defect_corpus.py
  uv run --no-sync python scripts/check_board_defect_corpus.py --update-manifest
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))
# The REQ-SAFE-01 fixture imports `tests.requirements.validators.clearance`
# as a package, so packages/temper-placer must be importable.
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer"))

EXIT_PASS = 0
EXIT_CORPUS_FAIL = 1
EXIT_GATE_ERROR = 2

MANIFEST_PATH = REPO_ROOT / "scripts" / "board_defect_corpus.yaml"
BOARD_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
CEILING_PATH = REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json"

# The corpus's DRC owning-gate categories (part of the class-to-gate table,
# KTD2). Every one of these must be at or below its drc_ceiling.json
# ceiling on the clean board (anti-vacuity control); the creepage gate is
# handled separately (red on main -- see module docstring).
DRC_GATE_CATEGORIES = ("courtyards_overlap", "copper_edge_clearance", "shorting_items")


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
    board_sha256: str
    manifest_board_sha256: str
    board_matches_manifest: bool
    clean_drc: dict[str, int] = field(default_factory=dict)
    clean_creepage_dc_lv: int | None = None
    anti_vacuity_violations: list[str] = field(default_factory=list)
    class_verdicts: list[ClassVerdict] = field(default_factory=list)
    mutation_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    workdir: str | None = None


# ---------------------------------------------------------------------------
# canonical measurement paths
# ---------------------------------------------------------------------------


def regenerate_dru(repo_root: Path) -> Path:
    """Regenerate ``pcb/temper.kicad_dru`` from its SSOT generator -- same
    convention as ``ci_check_drc.py``, so the corpus measures against the one
    canonical rules file, never whatever is (or isn't) on disk."""
    import generate_kicad_dru

    content = generate_kicad_dru.generate_dru()
    generate_kicad_dru.OUTPUT_PATH.write_text(content, encoding="utf-8")
    return generate_kicad_dru.OUTPUT_PATH


def measure_drc_counts(pcb_path: Path, dru_path: Path | None) -> dict[str, int]:
    """Per-violation-type DRC counts for *pcb_path* via run_drc.

    kicad-cli resolves ``<stem>.kicad_dru`` next to the board file (verified:
    placing the regenerated SSOT dru beside a copy makes the custom
    ``creepage`` DRU category appear), so the dru is copied next to the
    mutated copy to keep the measurement byte-for-byte the ratchet's.
    """
    if dru_path is not None and dru_path.exists():
        shutil.copyfile(dru_path, pcb_path.with_suffix(".kicad_dru"))
    from temper_placer.validation._drc_api import DrcRunnerError, run_drc

    try:
        result = run_drc(pcb_path)
    except (DrcRunnerError, OSError) as exc:
        raise GateError(f"DRC measurement failed on {pcb_path.name}: {exc}") from exc
    return dict(Counter(e.rule for e in result.errors))


def measure_creepage_dc_lv(pcb_path: Path) -> int:
    """DC_BUS<->LV_CONTROL creepage violation count via the REQ-SAFE-01
    validator, pointed at *pcb_path* (a run-time board copy)."""
    from tests.requirements.safety import _real_board_fixture as fixture

    from temper_placer.requirements.validators.clearance import (
        verify_iec60335_compliance,
    )

    fixture._PCB_PATH = Path(pcb_path)
    try:
        placement, voltage_domains, _stats = fixture.load_real_board_placement()
    except fixture.RealBoardUnavailable as exc:
        raise GateError(f"REQ-SAFE-01 inputs unavailable: {exc}") from exc
    result = verify_iec60335_compliance(placement, voltage_domains)
    return sum(
        1
        for v in result.violations
        if v.metric == "creepage" and v.boundary == "DC_BUS<->LV_CONTROL"
    )


def load_drc_ceilings(repo_root: Path) -> dict[str, int]:
    """Per-type error ceilings for the corpus's DRC gate categories, from
    the DRC ratchet's SSOT (``power_pcb_dataset/drc_ceiling.json``). A
    category absent from the file is not part of the corpus contract."""
    if not (repo_root / "power_pcb_dataset" / "drc_ceiling.json").exists():
        raise GateError(
            "power_pcb_dataset/drc_ceiling.json not found -- the corpus's "
            "anti-vacuity control reads its ceilings from the DRC ratchet SSOT"
        )
    data = json.loads((repo_root / "power_pcb_dataset" / "drc_ceiling.json").read_text())
    for entry in data.get("boards", []):
        if entry.get("board_id") == "temper":
            by_type = entry.get("violations_by_type") or {}
            return {k: int(v) for k, v in by_type.items() if k in DRC_GATE_CATEGORIES}
    raise GateError("drc_ceiling.json has no 'temper' board entry")


# ---------------------------------------------------------------------------
# pure decision logic (unit-testable without kicad-cli)
# ---------------------------------------------------------------------------


def _baseline(category: str, clean_count: int, ceilings: dict[str, int]) -> int:
    """The count a mutation must exceed: the clean measurement, or the
    recorded ceiling, whichever is higher -- a mutation that only beats a
    stale low clean number while staying under a recorded ceiling has not
    demonstrated anything."""
    ceiling = ceilings.get(category)
    if ceiling is None:
        return clean_count
    return max(clean_count, ceiling)


def evaluate_class(
    class_name: str,
    mutation: str,
    clean_drc: dict[str, int],
    mutated_drc: dict[str, int],
    ceilings: dict[str, int],
    clean_creepage: int | None,
    mutated_creepage: int | None,
) -> ClassVerdict:
    """Decide whether a mutated board fails its owning gate.

    A class is COVERED (ok) iff at least one of its owning gates fired --
    the count-delta assertion (mutated > clean, and > recorded ceiling for
    DRC categories). A class with no firing gate is a corpus error, not a
    pass (KTD2), and the returned verdict names the class and the measured
    numbers so the failure is actionable.
    """
    if mutation == "off-board":
        for gate in ("courtyards_overlap", "copper_edge_clearance"):
            baseline = _baseline(gate, clean_drc.get(gate, 0), ceilings)
            mutated = mutated_drc.get(gate, 0)
            if mutated > baseline:
                return ClassVerdict(
                    name=class_name,
                    ok=True,
                    message=(
                        f"{class_name}: owning gate {gate} fired: {mutated} > "
                        f"baseline {baseline} (clean {clean_drc.get(gate, 0)}, "
                        f"ceiling {ceilings.get(gate)})"
                    ),
                )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- no owning gate fired: "
                "courtyards_overlap "
                f"{clean_drc.get('courtyards_overlap', 0)} -> {mutated_drc.get('courtyards_overlap', 0)}, "
                "copper_edge_clearance "
                f"{clean_drc.get('copper_edge_clearance', 0)} -> {mutated_drc.get('copper_edge_clearance', 0)}"
            ),
        )
    if mutation == "pad-short":
        gate = "shorting_items"
        baseline = _baseline(gate, clean_drc.get(gate, 0), ceilings)
        mutated = mutated_drc.get(gate, 0)
        if mutated > baseline:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate {gate} fired: {mutated} > "
                    f"baseline {baseline} (clean {clean_drc.get(gate, 0)}, "
                    f"ceiling {ceilings.get(gate)})"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- shorting_items did not rise "
                f"({clean_drc.get(gate, 0)} -> {mutated})"
            ),
        )
    if mutation == "creepage":
        if clean_creepage is None or mutated_creepage is None:
            return ClassVerdict(
                name=class_name,
                ok=False,
                gate_error=True,
                message=(
                    f"{class_name}: gate error -- REQ-SAFE-01 creepage "
                    "measurement unavailable (netlist/manifest missing or "
                    "measurement failed)"
                ),
            )
        if mutated_creepage > clean_creepage:
            return ClassVerdict(
                name=class_name,
                ok=True,
                message=(
                    f"{class_name}: owning gate req-safe-01-creepage-dc-lv "
                    f"fired: DC_BUS<->LV_CONTROL creepage {clean_creepage} -> "
                    f"{mutated_creepage} (documented known-finding baseline: "
                    "gate red on main; class asserted via per-class delta)"
                ),
            )
        return ClassVerdict(
            name=class_name,
            ok=False,
            message=(
                f"{class_name}: uncovered class -- DC_BUS<->LV_CONTROL "
                f"creepage did not rise ({clean_creepage} -> {mutated_creepage})"
            ),
        )
    raise GateError(f"manifest class {class_name!r} has unknown mutation {mutation!r}")


def check_anti_vacuity(
    clean_drc: dict[str, int],
    ceilings: dict[str, int],
    gate_categories: tuple[str, ...] = DRC_GATE_CATEGORIES,
) -> list[str]:
    """Clean-board anti-vacuity control: every corpus DRC gate category must
    be at or below its recorded ceiling on the unmutated board. The creepage
    gate is deliberately NOT in *gate_categories* (red on main today -- see
    module docstring); its class uses a per-class delta instead."""
    violations: list[str] = []
    for category in gate_categories:
        ceiling = ceilings.get(category)
        if ceiling is None:
            # Category not part of the ratchet's recorded contract -- the
            # corpus does not invent a ceiling for it.
            continue
        clean = clean_drc.get(category, 0)
        if clean > ceiling:
            violations.append(
                f"clean-board {category} {clean} > recorded ceiling {ceiling}"
            )
    return violations


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    import yaml

    if not manifest_path.exists():
        raise GateError(f"corpus manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "classes" not in data:
        raise GateError(f"corpus manifest {manifest_path} has no 'classes' section")
    return data


def run_corpus(
    repo_root: Path,
    manifest_path: Path | None = None,
    workdir: Path | None = None,
    update_manifest: bool = False,
) -> CorpusReport:
    manifest_path = manifest_path or REPO_ROOT / "scripts" / "board_defect_corpus.yaml"
    manifest = load_manifest(manifest_path)
    meta = manifest.get("_meta", {})

    board_path = repo_root / "pcb" / "temper.kicad_pcb"
    if not board_path.exists():
        raise GateError(f"committed board not found: {board_path}")
    if shutil.which("kicad-cli") is None:
        raise GateError(
            "kicad-cli is not available -- the corpus measures through "
            "run_drc (--all-track-errors), the same constraint as the DRC "
            "ratchet; without it the corpus fails closed"
        )

    from board_defect_mutator import apply_mutation, board_content_hash, copy_board

    actual_board_hash = board_content_hash(board_path)
    recorded_board_hash = meta.get("board_sha256")
    board_matches = recorded_board_hash is None or actual_board_hash == recorded_board_hash

    ceilings = load_drc_ceilings(repo_root)
    dru_path = regenerate_dru(repo_root)

    workdir_path = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="board-defect-corpus-"))
    workdir_path.mkdir(parents=True, exist_ok=True)

    # --- clean-board control (byte-identical copy of the committed board) ---
    clean_copy = workdir_path / "clean.kicad_pcb"
    copy_board(board_path, clean_copy)
    clean_drc = measure_drc_counts(clean_copy, dru_path)
    try:
        clean_creepage = measure_creepage_dc_lv(clean_copy)
    except GateError as exc:
        clean_creepage = None
        print(f"  [gate-error] clean-board creepage measurement: {exc}")

    anti_vacuity_violations = check_anti_vacuity(clean_drc, ceilings)

    # --- per-class mutations + owning-gate assertion ---
    class_verdicts: list[ClassVerdict] = []
    mutation_summaries: dict[str, dict[str, Any]] = {}
    for class_name, class_def in manifest["classes"].items():
        mutation = class_def["mutation"]
        seed = int(class_def["seed"])
        out_path = workdir_path / f"{class_name}_mutated.kicad_pcb"
        mutation_result = apply_mutation(
            board_path, mutation, class_def["params"], seed, out_path
        )
        report_mutation = {
            "seed": seed,
            "mutated_sha256": mutation_result.mutated_sha256,
            "seed_board_sha256": mutation_result.seed_board_sha256,
            "summary": mutation_result.summary,
        }

        mutated_drc: dict[str, int] | None = None
        mutated_creepage: int | None = None
        if mutation == "creepage":
            if clean_creepage is None:
                verdict = ClassVerdict(
                    name=class_name,
                    ok=False,
                    gate_error=True,
                    message=(
                        "gate error: clean-board REQ-SAFE-01 baseline "
                        "unavailable, cannot assert the class delta"
                    ),
                )
                class_verdicts.append(verdict)
                continue
            try:
                mutated_creepage = measure_creepage_dc_lv(out_path)
            except GateError as exc:
                class_verdicts.append(
                    ClassVerdict(
                        name=class_name,
                        ok=False,
                        gate_error=True,
                        message=f"gate error: {exc}",
                    )
                )
                continue
        else:
            mutated_drc = measure_drc_counts(out_path, dru_path)

        verdict = evaluate_class(
            class_name,
            mutation,
            clean_drc,
            mutated_drc or {},
            ceilings,
            clean_creepage,
            mutated_creepage,
        )
        class_verdicts.append(verdict)
        mutation_summaries[class_name] = report_mutation

    # --- aggregate ---
    any_gate_error = any(v.gate_error for v in class_verdicts)
    any_uncovered = any(not v.ok and not v.gate_error for v in class_verdicts)
    anti_vacuity_ok = not anti_vacuity_violations
    ok = anti_vacuity_ok and not any_uncovered and not any_gate_error

    report = CorpusReport(
        ok=ok,
        exit_code=EXIT_GATE_ERROR if any_gate_error else (EXIT_PASS if ok else EXIT_CORPUS_FAIL),
        board_sha256=actual_board_hash,
        manifest_board_sha256=recorded_board_hash or "",
        board_matches_manifest=board_matches,
        clean_drc=clean_drc,
        clean_creepage_dc_lv=clean_creepage,
        anti_vacuity_violations=anti_vacuity_violations,
        class_verdicts=class_verdicts,
        mutation_summaries=mutation_summaries,
        workdir=str(workdir_path),
    )

    if update_manifest and ok and not board_matches and recorded_board_hash is not None:
        _stamp_manifest_hash(manifest_path, actual_board_hash)
        report.board_matches_manifest = True
        report.manifest_board_sha256 = actual_board_hash

    return report


def _stamp_manifest_hash(manifest_path: Path, board_sha256: str) -> None:
    """Rewrite the manifest's recorded board hash after a green run on a
    changed board -- the only manifest mutation the corpus performs.

    Deliberately a line-targeted replacement, NOT a yaml round-trip: the
    seed manifest's comments are load-bearing documentation (the
    defect-to-gate mapping notes and the creepage baseline_note), and
    ``yaml.safe_dump`` would drop every one of them.
    """
    import re

    text = manifest_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(  board_sha256: )[0-9a-f]{64}$", re.MULTILINE)
    new_text, n = pattern.subn(rf"\g<1>{board_sha256}", text, count=1)
    if n != 1:
        raise GateError(
            f"could not stamp board_sha256 into {manifest_path.name}: the "
            "'  board_sha256: <64-hex>' line was not found"
        )
    manifest_path.write_text(new_text, encoding="utf-8")
    print(f"  [manifest] stamped board_sha256 {board_sha256} into {manifest_path.name}")


def _print_report(report: CorpusReport) -> None:
    print(f"board sha256: {report.board_sha256[:16]}...")
    if report.board_matches_manifest:
        print("  matches manifest seed hash (corpus validated against this board)")
    else:
        print(
            "  WARNING: committed board hash differs from the manifest's "
            "recorded hash -- board changed since the corpus was seeded; "
            "this run re-validates every seed. After a green run, stamp the "
            "new hash with --update-manifest."
        )
    print(f"clean-board DRC: {json.dumps(report.clean_drc)}")
    print(
        "clean-board DC_BUS<->LV_CONTROL creepage: "
        f"{report.clean_creepage_dc_lv if report.clean_creepage_dc_lv is not None else '<unavailable>'}"
    )

    print("\nanti-vacuity control (clean board at/below recorded ceilings):")
    if report.anti_vacuity_violations:
        for violation in report.anti_vacuity_violations:
            print(f"  FAIL: {violation}")
    else:
        print("  PASS")

    print("\ndefect classes:")
    for verdict in report.class_verdicts:
        status = "GATE-ERROR" if verdict.gate_error else ("PASS" if verdict.ok else "FAIL")
        print(f"  [{status}] {verdict.name}: {verdict.message}")
        mut = report.mutation_summaries.get(verdict.name)
        if mut is not None:
            print(
                f"      mutation seed={mut['seed']} "
                f"mutated_sha256={mut['mutated_sha256'][:16]}... "
                f"seed+board_sha256={mut['seed_board_sha256'][:16]}... "
                f"summary={json.dumps(mut['summary'])}"
            )

    n_covered = sum(1 for v in report.class_verdicts if v.ok)
    n_total = len(report.class_verdicts)
    if report.ok:
        print(
            f"\nBoard-defect corpus: PASS -- {n_covered}/{n_total} classes "
            "covered, clean board green (mutated boards in "
            f"{report.workdir})"
        )
    else:
        print(
            f"\nBoard-defect corpus: FAIL -- {n_covered}/{n_total} classes "
            f"covered (mutated boards left in {report.workdir} for inspection)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--workdir", type=Path, default=None,
                        help="persistent directory for mutated boards (default: temp)")
    parser.add_argument("--update-manifest", action="store_true",
                        help="stamp the manifest's board_sha256 after a green "
                             "run on a changed board")
    args = parser.parse_args(argv)

    try:
        report = run_corpus(
            args.repo_root,
            manifest_path=args.manifest,
            workdir=args.workdir,
            update_manifest=args.update_manifest,
        )
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    _print_report(report)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
