#!/usr/bin/env python3
"""Issue #617 hoist -- the run-B fixed-copper recipe through the production caller.

# provenance: commit=<set-at-commit-time> dirty=<set-at-commit-time>

Runs the production repair recipe through ``run_clearance_repair_solve``
WITH the fixed-copper dict (the run-B values: free_refs={K3, C27},
margin 0.05, no zone items) -- the piece the pre-hoist caller could not
express. This is the Run-A-vs-Run-B comparison of
docs/evidence/2026-08-02-k3-swap-and-board-write.md Sec 3a/3b:

- Run A (pre-hoist, no fixed_copper): moved 166 refs, DRC regressed to
  1428-1437 errors vs the 1356 ceiling -- the caller's interface
  limitation, NOT a written board.
- Run B (direct solve_placement with fixed_copper): the evidence-validated
  candidate, THE written board (C27 on-board at the spike-predicted
  position, validator buckets hard=0/intra=0/gaps=0).

The hoisted caller must reproduce the Run-B class through the production
loop: C27 ~(28.62, 222.0)-class on-board, K3 RT314012 on-board, buckets
hard=0/intra=0/gaps=0, and the DRC proxy (k3_fixed_copper_repair_drc.py)
must show the Run-B-class improvement (error total well under the 1267
ceiling), never the Run-A-style 1428+ regression.

Recipe (identical to Run B through the loop interface):
- full-classification placement + full voltage-domain map (fixture)
- nothing hard-pinned; min-displacement toward current positions
- max_displacement_mm=60.0 (the <=60mm displacement envelope)
- fixed rotations for every ref
- full domain-clearance + keepaway, no chain exemption (530 keepaway)
- fixed_copper = free_refs={K3, C27}, margin 0.05, no zone items
- seed 0, 180s/round, max 4 rounds

NO src/ changes (the hoist itself is in src/, this script only measures).
Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/k3_fixed_copper_repair_solve.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.placer.cp_sat.clearance_repair import (  # noqa: E402
    run_clearance_repair_solve,
)

FREE = {"K3", "C27"}
MARGIN_FC_MM = 0.05
PCB = REPO / "pcb" / "temper.kicad_pcb"
# Set at commit time (see docs/evidence/2026-08-03-fixed-copper-repair-caller.md).
_PROVENANCE_COMMIT = "<set-at-commit-time>"
_PROVENANCE_DIRTY = False


def parse_result_without_zones(pcb):
    """Fixed-copper parse_result whose board carries no zone items (run-B)."""
    return SimpleNamespace(
        traces=pcb.traces,
        vias=pcb.vias,
        board=SimpleNamespace(
            zones=[],
            width=pcb.board.width,
            height=pcb.board.height,
            origin=getattr(pcb.board, "origin", (0.0, 0.0)),
        ),
    )


def main() -> None:
    pcb = parse_kicad_pcb(PCB)
    placement, _vd, stats = load_real_board_placement()
    full = stats["full_placement"]
    full_vd = stats["full_voltage_domains"]

    fc_nozones = {
        "parse_result": parse_result_without_zones(pcb),
        "free_refs": FREE,
        "margin_mm": MARGIN_FC_MM,
    }

    report = run_clearance_repair_solve(
        pcb_path=PCB,
        placement=full,
        voltage_domains=full_vd,
        timeout_ms=180_000,
        seed=0,
        max_rounds=4,
        max_displacement_mm=60.0,
        chain_exempt_pairs=None,  # wall-spike convention: no chain exemption (530 keepaway)
        fixed_copper=fc_nozones,
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
    print(f"fixed_copper_free_refs = {report.fixed_copper_free_refs}")
    print(f"fixed_copper_margin_mm = {report.fixed_copper_margin_mm}")
    print(f"fixed_copper_audit_violations = {report.fixed_copper_audit_violations}")
    print(f"final_inter       = {report.final_inter_violations}")
    print(f"final_intra       = {report.final_intra_violations}")
    print(f"moved_refs        = {len(report.moved_refs)}")
    print(f"total_displacement_mm = {report.total_displacement_mm:.2f}")
    print(f"K3  -> {k3}  (current board: {_current_pos(PCB, 'K3')})")
    print(f"C27 -> {c27}  (current board: {_current_pos(PCB, 'C27')})")

    va = report.validator_audit
    print("-" * 78)
    print("validator_audit (final round):")
    if va is None:
        print("  NONE -- no feasible/optimal solve completed (status != clean/intra_only)")
    else:
        print(f"  hard_failures        = {len(va.hard_failures)}")
        print(f"  intra_footprint      = {len(va.intra_footprint)}")
        print(f"  coverage_gaps        = {len(va.coverage_gaps)}")
        print(f"  covered_pair_count   = {va.covered_pair_count}")
        print(f"  validator_violation_count = {va.validator_violation_count}")
        print(f"  geometry_trusted     = {va.geometry_trusted}")
        print(f"  clean                = {va.clean}")
        for v in va.intra_footprint[:8]:
            print(f"  INTRA {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")

    out = {
        "provenance": {"commit": _PROVENANCE_COMMIT, "dirty": _PROVENANCE_DIRTY},
        "status": report.status,
        "reason": report.reason,
        "domain_constraints": report.domain_constraints,
        "keepaway_constraints": report.keepaway_constraints,
        "fixed_copper_free_refs": list(report.fixed_copper_free_refs),
        "fixed_copper_margin_mm": report.fixed_copper_margin_mm,
        "fixed_copper_audit_violations": report.fixed_copper_audit_violations,
        "final_inter": report.final_inter_violations,
        "final_intra": report.final_intra_violations,
        "moved_refs": list(report.moved_refs),
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
            }
            if va is not None
            else None
        ),
        # Full solved placement (positions + rotation indices) for the DRC
        # gate pass (k3_fixed_copper_repair_drc.py) without writing the board.
        "placement": {
            ref: {"position": list(p), "rotation_idx": report.final_rotations.get(ref, 0)}
            for ref, p in report.final_positions.items()
        },
    }
    out_path = REPO / "docs" / "evidence" / "k3_fixed_copper_repair_solve_summary.json"
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
