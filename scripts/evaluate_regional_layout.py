#!/usr/bin/env python3
"""Compare a regional PCB layout candidate against a baseline, fail closed.

The measurement adapters in this file call the repository's existing owners.
The acceptance contract and routed-pad identity comparison live in Rust at
``temper_quality_oracle.regional_feasibility``.
"""

from __future__ import annotations

# The repository's sibling scripts are importable only after SCRIPT_DIR is
# added below; keep that explicit rather than duplicating their logic here.
# ruff: noqa: E402
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_stale_extensions
import generate_kicad_dru
import measure_cross_domain_creepage as creepage
import temper_design_bundle_python as _tdb
import temper_quality_oracle as _quality

from temper_placer.io.fab_body_extraction import extract_fab_bodies
from temper_placer.placer.cp_sat.body_collision import (
    EMPTY_ALLOWLIST,
    audit_body_collisions,
)
from temper_placer.validation._drc_api import run_drc

EXIT_ACCEPTED = 0
EXIT_REJECTED = 1
EXIT_TOOL_ERROR = 2
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"


def _body_overlaps(board_path: Path) -> dict[str, float]:
    bodies = extract_fab_bodies(board_path)
    info = _tdb.parse_engine.extract_footprint_info_py(board_path.read_text(encoding="utf-8"))
    positions: dict[str, tuple[float, float]] = {}
    rotations: dict[str, int] = {}
    for fp in info:
        angle = float(fp["angle"])
        quadrant = round(angle / 90.0)
        if abs(angle - quadrant * 90.0) > 1e-9:
            raise RuntimeError(
                f"{fp['ref']} has non-quadrant angle {angle}; the canonical F.Fab "
                "collision audit accepts quadrant rotations only"
            )
        positions[str(fp["ref"])] = (float(fp["x"]), float(fp["y"]))
        rotations[str(fp["ref"])] = quadrant % 4
    result = audit_body_collisions(bodies, positions, rotations, EMPTY_ALLOWLIST)
    return {
        "<->".join(sorted((v.ref_a, v.ref_b))): v.overlap_mm2
        for v in result.violations
    }


def _routing_observations(board_path: Path) -> tuple[list[tuple[str, float, float]], list[tuple[float, float]]]:
    parsed = _tdb.parse_engine.parse_kicad_pcb(
        board_path.read_text(encoding="utf-8"), False, None
    )
    pads = [
        (f"{pad.component_ref}.{pad.number}", float(pad.position[0]), float(pad.position[1]))
        for pad in parsed.pads
    ]
    endpoints = [
        point
        for trace in parsed.traces
        for point in (
            (float(trace.start[0]), float(trace.start[1])),
            (float(trace.end[0]), float(trace.end[1])),
        )
    ]
    return pads, endpoints


def _instrument_errors(board_path: Path, report, drc) -> list[str]:
    errors: list[str] = []
    expected_dru = generate_kicad_dru.generate_dru()
    dru_path = board_path.with_suffix(".kicad_dru")
    if not dru_path.exists():
        errors.append(f"missing generated rules file: {dru_path}")
    elif dru_path.read_text(encoding="utf-8") != expected_dru:
        errors.append(f"stale or non-canonical generated rules file: {dru_path}")
    if not board_path.with_suffix(".kicad_pro").exists():
        errors.append(f"missing KiCad project sidecar for {board_path}")
    if not (board_path.parent / "fp-lib-table").exists():
        errors.append(f"missing fp-lib-table beside {board_path}")
    if report.pairs_examined == 0 or report.hv_pads_total == 0 or report.selv_pads_total == 0:
        errors.append("cross-domain measurement has an empty denominator")

    error_counts = Counter(item.rule for item in drc.errors)
    warning_counts = Counter(item.rule for item in drc.warnings)
    for rule, count in error_counts.items():
        if count in {199, 499}:
            errors.append(f"{rule} count {count} is a kicad-cli reporting cap")
    if warning_counts["lib_footprint_issues"] == report.footprints_total and warning_counts["lib_footprint_mismatch"] == 0:
        errors.append(
            "footprint libraries did not resolve: lib_footprint_issues equals "
            "the footprint census while lib_footprint_mismatch is zero"
        )
    return errors


def _measure(board_path: Path, manifest_path: Path, threshold_mm: float) -> dict:
    report, _, _ = creepage.measure(board_path, manifest_path, threshold_mm)
    drc = run_drc(board_path)
    pads, endpoints = _routing_observations(board_path)
    return {
        "pairs": [f"{v.hv.label}<->{v.selv.label}" for v in report.violations],
        "drc": {
            **dict(Counter(item.rule for item in drc.errors)),
            **{
                f"warning:{rule}": count
                for rule, count in Counter(item.rule for item in drc.warnings).items()
            },
        },
        "body_overlaps": _body_overlaps(board_path),
        "pads": pads,
        "endpoints": endpoints,
        "instrument_errors": _instrument_errors(board_path, report, drc),
        "pair_count": len(report.violations),
        "drc_total": len(drc.errors),
        "drc_warnings": len(drc.warnings),
    }


def evaluate(
    baseline_path: Path,
    candidate_path: Path,
    manifest_path: Path,
    threshold_mm: float,
    endpoint_tolerance_mm: float,
) -> dict:
    extension_report = check_stale_extensions.run(REPO_ROOT)
    extension_errors = [
        result.status.detail
        for result in extension_report.results
        if result.status.state != "fresh"
    ]
    baseline = _measure(baseline_path, manifest_path, threshold_mm)
    candidate = _measure(candidate_path, manifest_path, threshold_mm)
    instrument_errors = [
        *(f"extension: {error}" for error in extension_errors),
        *(f"baseline: {error}" for error in baseline["instrument_errors"]),
        *(f"candidate: {error}" for error in candidate["instrument_errors"]),
    ]
    verdict = dict(
        _quality.evaluate_regional_candidate_py(
            baseline["pairs"],
            candidate["pairs"],
            baseline["drc"],
            candidate["drc"],
            baseline["body_overlaps"],
            candidate["body_overlaps"],
            baseline["pads"],
            baseline["endpoints"],
            candidate["pads"],
            candidate["endpoints"],
            endpoint_tolerance_mm,
            instrument_errors,
        )
    )
    verdict["baseline"] = {
        "board": str(baseline_path),
        "cross_domain_pairs": baseline["pair_count"],
        "drc_errors": baseline["drc_total"],
        "drc_warnings": baseline["drc_warnings"],
    }
    verdict["candidate"] = {
        "board": str(candidate_path),
        "cross_domain_pairs": candidate["pair_count"],
        "drc_errors": candidate["drc_total"],
        "drc_warnings": candidate["drc_warnings"],
    }
    return verdict


def _print(verdict: dict) -> None:
    status = "ACCEPT" if verdict["accepted"] else "REJECT"
    print(f"REGIONAL LAYOUT VERDICT: {status}")
    print(
        f"  cross-domain pairs: {verdict['baseline']['cross_domain_pairs']} -> "
        f"{verdict['candidate']['cross_domain_pairs']}"
    )
    print(
        f"  total DRC errors:   {verdict['baseline']['drc_errors']} -> "
        f"{verdict['candidate']['drc_errors']}"
    )
    print(
        f"  total DRC warnings: {verdict['baseline']['drc_warnings']} -> "
        f"{verdict['candidate']['drc_warnings']}"
    )
    print(f"  removed pairs:      {len(verdict['removed_cross_domain_pairs'])}")
    print(f"  new pairs:          {len(verdict['new_cross_domain_pairs'])}")
    print(f"  endpoint drift:     {len(verdict['routed_pad_endpoint_drift'])}")
    if verdict["reasons"]:
        print("Reasons:")
        for reason in verdict["reasons"]:
            print(f"  - {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--min-creepage-mm", type=float, default=12.6)
    parser.add_argument("--endpoint-tolerance-mm", type=float, default=0.01)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        verdict = evaluate(
            args.baseline,
            args.candidate,
            args.manifest,
            args.min_creepage_mm,
            args.endpoint_tolerance_mm,
        )
    except Exception as exc:
        print(f"REGIONAL LAYOUT VERDICT: TOOL ERROR\n  {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    _print(verdict)
    if args.json:
        args.json.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return EXIT_ACCEPTED if verdict["accepted"] else EXIT_REJECTED


if __name__ == "__main__":
    raise SystemExit(main())
