#!/usr/bin/env python3
"""K3/tank3 resolve — validator-gated production repair recipe (issue #523).

# provenance: commit=87df36a223472967624648372bde8a21c61ba02a dirty=false

Companion to ``docs/evidence/2026-08-01-k3-resolve-validator-gated.md``.

Runs the production repair recipe through the gap-2-wired production caller
``run_clearance_repair_solve`` (which now passes ``validator_input`` into
every ``solve_placement`` round, so each feasible/optimal solve re-runs the
REQ-SAFE-01 validator itself on the solved placement and classifies its
violations into hard / intra-footprint / coverage-gap buckets).

Recipe (the wall-spike's feasible variant B, through the repair-loop caller):

- nothing hard-pinned; min-displacement objective toward the current board
  positions (the loop's default)
- ``max_displacement_mm=60.0`` (the ≤60mm displacement envelope variant B
  proved feasible)
- fixed rotations for every ref (routed copper is pad-anchored)
- full domain-clearance set + unclassified-near-HV keep-away, generated from
  the fixture's FULL-classification placement, no chain-sibling exemption
  (matches the wall spike's 12,022 + 530 constraint counts)
- seed 0, 180s/round, max 4 rounds
- NOTE: ``run_clearance_repair_solve`` does not take ``fixed_copper``; the
  wall-spike variant B's fixed-copper-without-zone-items piece is NOT part of
  this caller's interface, so this run omits it (documented in the evidence
  doc; a follow-up hoists fixed-copper into the repair loop or wires
  validator_input at a direct solve_placement caller).

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/k3_resolve_gated_solve.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

# Same sys.path dance as gap2_wall_measure.py so `import tests.requirements`
# resolves the way it does under pytest.
_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.placer.cp_sat.clearance_repair import (  # noqa: E402
    run_clearance_repair_solve,
)

PCB = REPO / "pcb" / "temper.kicad_pcb"


def main() -> None:
    placement, _vd, stats = load_real_board_placement()
    full = stats["full_placement"]
    full_vd = stats["full_voltage_domains"]

    report = run_clearance_repair_solve(
        pcb_path=PCB,
        placement=full,
        voltage_domains=full_vd,
        timeout_ms=180_000,
        seed=0,
        max_rounds=4,
        max_displacement_mm=60.0,
        chain_exempt_pairs=None,  # wall-spike convention: no chain exemption (530 keepaway)
    )

    k3 = report.final_positions.get("K3")
    c27 = report.final_positions.get("C27")
    print("=" * 78)
    print(f"status            = {report.status}")
    print(f"reason            = {report.reason}")
    print(f"rounds            = {len(report.rounds)}")
    for r in report.rounds:
        print(
            f"  round {r.index}: solve={r.solve_status} time={r.solve_time_ms:.0f}ms "
            f"inter_after={r.checker_after_inter} intra_after={r.checker_after_intra} "
            f"disp={r.displacement_mm:.1f}mm moved={len(r.moved_refs)}"
        )
    print(f"domain_constraints = {report.domain_constraints}")
    print(f"keepaway_constraints = {report.keepaway_constraints}")
    print(f"final_inter       = {report.final_inter_violations}")
    print(f"final_intra       = {report.final_intra_violations}")
    print(f"intra_blockers    = {sorted(report.intra_blocker_refs)}")
    print(f"total_displacement_mm = {report.total_displacement_mm:.2f}")
    print(f"K3  -> {k3}  (current board: {_current_pos(PCB, 'K3')})")
    print(f"C27 -> {c27}  (current board: {_current_pos(PCB, 'C27')})")

    va = report.validator_audit
    print("-" * 78)
    print("validator_audit (final round):")
    if va is None:
        print("  NONE — no feasible/optimal solve completed (status != clean/intra_only)")
    else:
        print(f"  hard_failures        = {len(va.hard_failures)}")
        print(f"  intra_footprint      = {len(va.intra_footprint)}")
        print(f"  coverage_gaps        = {len(va.coverage_gaps)}")
        print(f"  covered_pair_count   = {va.covered_pair_count}")
        print(f"  validator_violation_count = {va.validator_violation_count}")
        print(f"  geometry_trusted     = {va.geometry_trusted}")
        print(f"  clean                = {va.clean}")
        print(f"  stats                = {va.stats}")
        for v in va.hard_failures[:5]:
            print(f"  HARD {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.intra_footprint[:8]:
            print(f"  INTRA {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.coverage_gaps[:8]:
            print(f"  GAP {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")

    # report-level convenience counts
    print("-" * 78)
    print(
        f"report counts: hard={report.validator_hard_failures} "
        f"intra={report.validator_intra_footprint} "
        f"gaps={report.validator_coverage_gaps} "
        f"geometry_trusted={report.validator_geometry_trusted}"
    )

    out = {
        "status": report.status,
        "reason": report.reason,
        "domain_constraints": report.domain_constraints,
        "keepaway_constraints": report.keepaway_constraints,
        "final_inter": report.final_inter_violations,
        "final_intra": report.final_intra_violations,
        "intra_blockers": sorted(report.intra_blocker_refs),
        "total_displacement_mm": report.total_displacement_mm,
        "K3": k3,
        "C27": c27,
        "validator_audit": (
            {
                "hard_failures": len(va.hard_failures),
                "intra_footprint": len(va.intra_footprint),
                "coverage_gaps": len(va.coverage_gaps),
                "covered_pair_count": va.covered_pair_count,
                "validator_violation_count": va.validator_violation_count,
                "geometry_trusted": bool(va.geometry_trusted),
                "clean": bool(va.clean),
                "stats": va.stats,
            }
            if va is not None
            else None
        ),
    }
    out_path = REPO / "docs" / "evidence" / "k3_resolve_gated_solve_summary.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {out_path}")


def _current_pos(pcb: Path, ref: str):
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    pr = parse_kicad_pcb(pcb)
    for c in pr.netlist.components:
        if c.ref == ref:
            return c.initial_position
    return None


if __name__ == "__main__":
    main()
