#!/usr/bin/env python3
"""Domain-first re-solve for the MAINS_SELV_ISOLATION_BARRIER keepout (#518).

# provenance: commit=PENDING dirty=false

Frees the alternating-ring refs (the 12-pad bichromatic Delaunay cycle
C6.2-R8.2-K1.A2-R8.1-R75.1-C27.2-C9.1-U5.3-Q1.1-U5.1-U10.2-R27.2 from
docs/evidence/2026-08-03-mains-selv-barrier-keepout.md §4c) so the pad
centers become separable by a simple curve (the far-side check 6 of
scripts/check_isolation_keepout.py).

RECIPE -- the PRODUCTION caller (validator-gated repair loop), with
fixed_copper hoisted (issue #617/#653):

- ``run_clearance_repair_solve(pcb_path, full, full_vd, timeout_ms=180000,
  seed=0, max_rounds=4, max_displacement_mm=60.0, chain_exempt_pairs=None,
  fixed_copper={'parse_result': <no zones>, 'free_refs': RING,
  'margin_mm': 0.05})`` -- nothing hard-pinned (min-displacement toward
  current positions), every rotation pinned, full 11,571 domain-clearance +
  530 keepaway, validator_input wired (REQ-SAFE-01 exact-copper audit,
  fail-closed), fixed-copper audit fail-closed.
- RING = {C6, R8, K1, R75, C27, C9, U5, Q1, U10, R27} is the fixed-copper
  free set: the ring refs' pads must not land on different-net fixed copper.

WHY NOT pin-everything-but-the-ring (fixed_positions): the written board is
infeasible under the current model's auto-generated netclass cross-class
constraints when pinned -- 8 cross-class pairs sit at/under the 6.0mm bar at
the written positions, two strictly below (C2<->C26, C4<->U6 at 5.995mm;
docs/evidence/2026-08-03-fixed-copper-repair-caller.md §5). Any solve that
hard-pins non-ring refs at their current positions is therefore infeasible
by construction. The production caller's min-displacement form is the
feasible class the current model admits (the hoisted run measured clean
buckets and DRC 1281-1282, docs/evidence/2026-08-03-fixed-copper-repair-
caller.md §4).

NO pcb/** write. Read-only w.r.t. pcb/temper.kicad_pcb.

Usage:
    uv run --no-sync python docs/evidence/2026-08-04_domain_first_resolve_solve.py
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

# The 12-pad alternating ring's refs (deduped; U5 and R8 appear twice).
RING = {"C6", "R8", "K1", "R75", "C27", "C9", "U5", "Q1", "U10", "R27"}

# Expanded free set for the second iteration: every ref participating in an
# alternating Delaunay cycle at the first solve's placement (45 cycle-basis
# cycles, 78 refs -- the macro-level domain interleave). Pass
# FREE_SET_JSON=/path/to/refs.json (a JSON list of refs) to override RING.
import os as _os  # noqa: E402

_FREE_SET_OVERRIDE = _os.environ.get("FREE_SET_JSON")
if _FREE_SET_OVERRIDE:
    import json as _json

    RING = set(_json.loads(Path(_FREE_SET_OVERRIDE).read_text()))
    print(f"free set overridden from {_FREE_SET_OVERRIDE}: {len(RING)} refs")
MARGIN_FC_MM = 0.05
SEED = 0
MAX_DISP_MM = 60.0
TIMEOUT_MS = 180_000
MAX_ROUNDS = 4
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
    cur = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}

    fc_nozones = {
        "parse_result": parse_result_without_zones(pcb),
        "free_refs": RING,
        "margin_mm": MARGIN_FC_MM,
    }

    report = run_clearance_repair_solve(
        pcb_path=PCB,
        placement=full,
        voltage_domains=full_vd,
        timeout_ms=TIMEOUT_MS,
        seed=SEED,
        max_rounds=MAX_ROUNDS,
        max_displacement_mm=MAX_DISP_MM,
        chain_exempt_pairs=None,
        fixed_copper=fc_nozones,
    )
    print(f"status={report.status}  reason={report.reason[:160]}")
    print(f"rounds={len(report.rounds)}  domain={report.domain_constraints}  "
          f"keepaway={report.keepaway_constraints}")
    print(f"validator buckets: hard={report.validator_hard_failures} "
          f"intra={report.validator_intra_footprint} "
          f"gaps={report.validator_coverage_gaps} "
          f"geometry_trusted={report.validator_geometry_trusted}")
    print(f"total_displacement_mm={report.total_displacement_mm:.2f}  "
          f"moved_refs={len(report.moved_refs)}")

    print("\nring refs (solved local frame vs current):")
    ring_disp = 0.0
    for ref in sorted(RING):
        new = report.final_positions.get(ref)
        c = cur.get(ref)
        if new is None or c is None:
            print(f"  {ref}: MISSING")
            continue
        d = abs(new[0] - c[0]) + abs(new[1] - c[1])
        ring_disp += d
        print(f"  {ref}: ({c[0]:7.2f},{c[1]:7.2f}) -> ({new[0]:7.2f},{new[1]:7.2f}) "
              f"d={d:6.2f}mm")
    print(f"ring total displacement = {ring_disp:.2f}mm")

    for i, r in enumerate(report.rounds):
        print(f"  round {i}: status={r.solve_status} inter={r.checker_after_inter} "
              f"intra={r.checker_after_intra} moved={len(r.moved_refs)} "
              f"disp={r.displacement_mm:.1f}")

    va = report.validator_audit
    if va is not None:
        for v in va.hard_failures[:5]:
            print(f"  HARD {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.intra_footprint[:8]:
            print(f"  INTRA {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")
        for v in va.coverage_gaps[:8]:
            print(f"  GAP {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")

    out = {
        "status": report.status,
        "reason": report.reason,
        "ring": sorted(RING),
        "recipe": {
            "caller": "run_clearance_repair_solve (validator-gated, fixed_copper hoisted #653)",
            "seed": SEED,
            "timeout_ms": TIMEOUT_MS,
            "max_rounds": MAX_ROUNDS,
            "max_displacement_mm": MAX_DISP_MM,
            "fixed_copper_free_refs": sorted(RING),
            "fixed_copper_margin_mm": MARGIN_FC_MM,
            "domain_constraints": report.domain_constraints,
            "keepaway_constraints": report.keepaway_constraints,
        },
        "final_ring_positions": {
            ref: {"position": list(report.final_positions[ref])}
            for ref in sorted(RING)
            if ref in report.final_positions
        },
        "total_displacement_mm": report.total_displacement_mm,
        "ring_total_displacement_mm": ring_disp,
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
        # post-solve verification pass (ring re-check, corridor analysis)
        # without writing the board.
        "placement": {
            ref: {
                "position": list(p),
                "rotation_idx": report.final_rotations.get(ref, rot.get(ref, 0)),
            }
            for ref, p in report.final_positions.items()
        },
    }
    out_path = REPO / "docs" / "evidence" / "2026-08-04_domain_first_resolve_solve_summary.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
