#!/usr/bin/env python3
"""Gap-2 measurement: solver box-bar vs REQ-SAFE-01 exact-copper bar.

# provenance: commit=dc8accd5bb12c20f5afe7f0840e74ab9d7e8daaf dirty=false

Companion to ``docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md``.

Reproduces the #523 scoped solve (FREE={K3, C27} + 12,022 domain-clearance +
530 keepaway + fixed-copper constraints) on ``pcb/temper.kicad_pcb`` at the
committed board state, extracts the unsat core, and for every pair the core
names (plus the K3/C27 domain pairs) computes:

  (a) solver box-bar distance  -- the Chebyshev box gap the SeparatedConstraint
      handler actually encodes, on the solver's even-rounded integer grid,
      with rotation-aware half-extents (exact same geometry as
      ``handlers/separated.py`` + ``model.py``);
  (b) required margin mm        -- the constraint's ``min_distance_mm``;
  (c) exact-copper distance     -- the REQ-SAFE-01 validator's pad-to-pad
      distance for that pair (``clearance._CopperModel.copper_distance`` with
      the same per-domain pad restriction the validator applies).

Verdict per pair:
  box_dist < margin AND copper_dist >= margin  -> box bar is the blocker,
      copper satisfied: gap-2 premise HOLDS for this pair.
  copper_dist < margin                         -> genuine copper violation:
      no placement fixes it without moving something (or a slot / the
      validator reconciliation).

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/gap2_wall_measure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

# The `tests` package under packages/temper-placer is a regular package
# (empty __init__.py) but `import tests` only resolves when `tests` is
# reachable from a sys.path entry that contains it. Chdir into
# packages/temper-placer and put THAT directory (not the tests dir itself)
# on sys.path, so `import tests.requirements...` resolves the same way it
# does under pytest.
import os  # noqa: E402

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
PD2_BAR_MM = 8.0  # 12.6 on PD3; 8.0 on PD2 (operative on main)


def load():
    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    placement, _vd, stats = load_real_board_placement()
    full = stats["full_placement"]
    full_vd = stats["full_voltage_domains"]
    all_refs = {c.ref for c in pcb.netlist.components}
    return pcb, full, full_vd, all_refs


def build_constraints(full, full_vd, all_refs):
    dc = generate_domain_clearance_constraints(full, full_vd, component_refs=all_refs)
    kw = generate_unclassified_hv_keepaway_constraints(full, full_vd, component_refs=all_refs)
    return dc, kw


def parse_result_without_zones(pcb):
    """A fixed-copper parse_result whose board carries no zone items
    (the run-B recipe drops zone obstacles; see the fixed-copper evidence doc)."""
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


def run_variant(
    pcb,
    extra,
    *,
    label,
    fixed_positions=None,
    minimize_displacement_to=None,
    max_displacement_mm=None,
    fixed_rotations=None,
    fc=None,
    timeout_ms=90_000,
):
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
    res = solve_placement(
        netlist=pcb.netlist,
        board=pcb.board,
        extra_constraints=extra,
        timeout_ms=timeout_ms,
        seed=SEED,
        hint_positions=hints,
        fixed_positions=fixed_positions,
        minimize_displacement_to=minimize_displacement_to,
        max_displacement_mm=max_displacement_mm,
        fixed_rotations=fixed_rotations,
        fixed_copper=fc,
    )
    names = [u["name"] for u in res.unsat_core]
    print(f"[{label}] status={res.status} time={res.solve_time_ms:.1f}ms core={len(names)}")
    return res, names


def main():
    pcb, full, full_vd, all_refs = load()
    dc, kw = build_constraints(full, full_vd, all_refs)
    extra = dc + kw
    print(f"refs={len(all_refs)} domain={len(dc)} keepaway={len(kw)} total={len(extra)}")

    pinned = all_refs - FREE
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    fixed_positions = {ref: (*pos[ref], rot[ref]) for ref in pinned}
    fixed_rotations = {ref: rot[ref] for ref in pinned}

    fc_zones = {"parse_result": pcb, "free_refs": FREE, "margin_mm": MARGIN_FC_MM}
    fc_nozones = {
        "parse_result": parse_result_without_zones(pcb),
        "free_refs": FREE,
        "margin_mm": MARGIN_FC_MM,
    }

    results = {}

    # Variant A: task-brief scoped solve -- everything else hard-pinned.
    res, names = run_variant(
        pcb,
        extra,
        label="A pinned",
        fixed_positions=fixed_positions,
        fixed_rotations=fixed_rotations,
        fc=fc_zones,
    )
    results["A_pinned"] = {"status": res.status, "core": names}

    # Variant A0: pinned, no extra constraints, no fixed-copper (isolate walls).
    res, names = run_variant(
        pcb,
        [],
        label="A0 pinned no-extra",
        fixed_positions=fixed_positions,
        fixed_rotations=fixed_rotations,
    )
    results["A0_pinned_no_extra"] = {"status": res.status, "core": names}

    # Variant B: production repair recipe -- nothing pinned, min-displacement,
    # max 60mm, fixed-copper WITHOUT zone items.
    min_disp = {ref: (x, y) for ref, (x, y) in pos.items()}
    res, names = run_variant(
        pcb,
        extra,
        label="B repair no-zones",
        minimize_displacement_to=min_disp,
        max_displacement_mm=60.0,
        fixed_rotations={ref: rot[ref] for ref in all_refs},
        fc=fc_nozones,
        timeout_ms=180_000,
    )
    results["B_repair_no_zones"] = {"status": res.status, "core": names}

    # Variant C: same as B but fixed-copper WITH zone items.
    res, names = run_variant(
        pcb,
        extra,
        label="C repair with-zones",
        minimize_displacement_to=min_disp,
        max_displacement_mm=60.0,
        fixed_rotations={ref: rot[ref] for ref in all_refs},
        fc=fc_zones,
        timeout_ms=180_000,
    )
    results["C_repair_with_zones"] = {"status": res.status, "core": names}

    out = REPO / "docs" / "evidence" / "gap2_wall_solve_cores.json"
    out.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
