#!/usr/bin/env python3
"""K3/tank3 resolve — exact wall-spike variant B with validator_input wired (issue #523).

# provenance: commit=87df36a223472967624648372bde8a21c61ba02a dirty=false

Runs the wall-spike-proven production repair recipe (variant B,
`docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md` §6) EXACTLY as the
spike script `gap2_wall_measure.py` ran it — direct ``solve_placement`` with:

- nothing hard-pinned; min-displacement toward current positions
- ``max_displacement_mm=60.0``
- ``fixed_rotations`` = every ref pinned to its current rotation
- ``fixed_copper`` = WITHOUT zone items, free_refs={K3, C27}, margin 0.05
- full domain-clearance (12,022) + keepaway (530), no chain exemption
- seed 0, 180s, hints = current positions

PLUS ``validator_input={"placement": ..., "voltage_domains": ...}`` — the
gap-2 wiring under test — so the REQ-SAFE-01 validator itself re-runs on the
solved placement and classifies its violations (hard / intra / coverage-gap).

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/k3_resolve_gated_variantB.py
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
from temper_placer.placer.cp_sat import solve_placement  # noqa: E402
from temper_placer.placer.cp_sat.domain_clearance import (  # noqa: E402
    generate_domain_clearance_constraints,
    generate_unclassified_hv_keepaway_constraints,
)

FREE = {"K3", "C27"}
MARGIN_FC_MM = 0.05
SEED = 0
PCB = REPO / "pcb" / "temper.kicad_pcb"


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
    all_refs = {c.ref for c in pcb.netlist.components}

    dc = generate_domain_clearance_constraints(full, full_vd, component_refs=all_refs)
    kw = generate_unclassified_hv_keepaway_constraints(full, full_vd, component_refs=all_refs)
    extra = dc + kw
    print(f"refs={len(all_refs)} domain={len(dc)} keepaway={len(kw)} total={len(extra)}")

    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    min_disp = {ref: (x, y) for ref, (x, y) in pos.items()}
    hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
    fc_nozones = {
        "parse_result": parse_result_without_zones(pcb),
        "free_refs": FREE,
        "margin_mm": MARGIN_FC_MM,
    }

    res = solve_placement(
        netlist=pcb.netlist,
        board=pcb.board,
        extra_constraints=extra,
        timeout_ms=180_000,
        seed=SEED,
        hint_positions=hints,
        minimize_displacement_to=min_disp,
        max_displacement_mm=60.0,
        fixed_rotations={ref: rot[ref] for ref in all_refs},
        fixed_copper=fc_nozones,
        validator_input={"placement": full, "voltage_domains": full_vd},
    )
    print(f"status={res.status} time={res.solve_time_ms:.1f}ms")

    k3 = res.positions.get("K3")
    c27 = res.positions.get("C27")
    print(f"K3  -> {k3} rot={res.rotations.get('K3')}  (current: {pos['K3']})")
    print(f"C27 -> {c27} rot={res.rotations.get('C27')}  (current: {pos['C27']})")

    disp = sum(
        abs(res.positions[ref][0] - x) + abs(res.positions[ref][1] - y)
        for ref, (x, y) in min_disp.items()
        if ref in res.positions
    )
    print(f"total_displacement_mm = {disp:.2f}")

    va = res.validator_audit
    print("-" * 78)
    if va is None:
        print("validator_audit = NONE")
    else:
        print(f"  hard_failures        = {len(va.hard_failures)}")
        print(f"  intra_footprint      = {len(va.intra_footprint)}")
        print(f"  coverage_gaps        = {len(va.coverage_gaps)}")
        print(f"  covered_pair_count   = {va.covered_pair_count}")
        print(f"  validator_violation_count = {va.validator_violation_count}")
        print(f"  geometry_trusted     = {va.geometry_trusted}")
        print(f"  clean                = {va.clean}")
        for v in va.hard_failures[:5]:
            print(f"  HARD {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.intra_footprint[:8]:
            print(f"  INTRA {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.coverage_gaps[:8]:
            print(f"  GAP {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")

    out = {
        "status": res.status,
        "K3": list(k3) if k3 else None,
        "K3_rot": res.rotations.get("K3"),
        "C27": list(c27) if c27 else None,
        "C27_rot": res.rotations.get("C27"),
        "total_displacement_mm": disp,
        "domain": len(dc),
        "keepaway": len(kw),
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
        # Full solved placement (positions + rotation indices) for the
        # gate-verification pass (courtyard-overlap counting, fixed-copper
        # audit, REQ-SAFE-01 re-run) without writing the board.
        "placement": {
            ref: {"position": list(p), "rotation_idx": res.rotations.get(ref, 0)}
            for ref, p in res.positions.items()
        },
    }
    out_path = REPO / "docs" / "evidence" / "k3_resolve_gated_variantB_summary.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
