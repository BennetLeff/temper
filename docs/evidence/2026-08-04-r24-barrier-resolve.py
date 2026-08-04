#!/usr/bin/env python3
"""R24 barrier-admitting re-solve: scoped CP-SAT candidates (issue #690 follow-up).

# provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=false

What this runs
--------------
``docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`` (PR #690)
proved that the committed placement admits no ``MAINS_SELV_ISOLATION_BARRIER``
of any shape, and that ``R24`` alone is why: the widest copper-free channel
joining its two HV pads to the other 99 is 5.727mm against the 8.000mm bar,
a 2.273mm shortfall. #690 Sec 5 item 1 names the fix -- move ``R24`` -- but
does not say where to, and the CP-SAT model has no constraint that expresses
the barrier's *connectivity* requirement, so a plain min-displacement repair
solve returns ``R24`` unmoved (it already satisfies every pairwise bar).

So this is a two-stage search, geometry proposing and CP-SAT disposing:

  STAGE 1 (``2026-08-04-r24-barrier-frontier.py``): raster-scan candidate
  ``R24`` origins and keep those that satisfy BOTH #690's Part-C
  HV-reachability test (at 0.4mm and 0.25mm, verdicts must agree) AND the
  REQ-SAFE-01 / keepaway clearance bars. The connectivity test is evaluated
  *with R24's own copper present at the candidate position* -- load-bearing,
  because R24's pads are what close the channel they sit in, so evaluating
  the map with R24 removed answers a different question and wrongly marks its
  current position admissible.

  STAGE 2 (this script): hand the surviving candidates to CP-SAT and let the
  real constraint set have a say -- courtyard/edge margins, the full
  domain-clearance + unclassified-HV keepaway set, and ``fixed_copper`` so
  R24's pads may not come to rest on another net's routed copper.

Recipe is ``de59c0458``'s Run B (the variant that was written to the board,
``docs/evidence/k3_swap_board_write_variantB.py``), with one deliberate
change: ``minimize_displacement_to`` gives ``R24`` a TARGET rather than its
current position, so the objective pulls it toward the admissible position
while every other ref is still pulled to where it already is.

WHAT THIS SCRIPT ACTUALLY ESTABLISHES -- and it is a negative result. On
today's board the Run-B recipe no longer produces a scoped solve: the
``control-no-retarget`` run, which is de59c0458's recipe VERBATIM asking for
"change as little as possible", still terminates at the 180s timeout with
status ``feasible`` having moved 167 refs by 7,069mm in total. The churn is
therefore intrinsic to the recipe on this board, not an artifact of
retargeting R24. Its cause is visible separately: the committed placement is
not a feasible point of the encoder's own base model (pinning every ref at
its current position with ``fixed_positions`` and NO extra constraints is
reported ``infeasible``), so CP-SAT must move things, and 180s is not enough
to converge the displacement objective over 169 components and 12,101
constraints. de59c0458 measured exactly this failure mode for its Run A:
166 refs moved and the written board regressed to 1428-1437 total DRC errors
against a 1356 ceiling. Accordingly the CP-SAT output here is REPORTED, and
the board write takes the single-component frontier candidate instead.

Determinism (``docs/evidence/2026-08-01-ortools-cpsat-spike.md``): CP-SAT is
bit-identical only for solves that terminate BEFORE ``max_time_in_seconds``.
Each candidate records ``timed_out``; a timed-out candidate is usable but is
NOT reproducible across machines and is labelled so.

Usage:
    uv run --no-sync python docs/evidence/2026-08-04-r24-barrier-resolve.py
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

PCB = REPO / "pcb" / "temper.kicad_pcb"
OUT = REPO / "docs" / "evidence" / "2026-08-04-r24-barrier-resolve.json"

PROVENANCE_COMMIT = "f2b09d84673b3a18d8fabe454230f1b240148f3d"

FREE = {"R24"}
MARGIN_FC_MM = 0.05
SEED = 0
TIMEOUT_MS = 180_000
MAX_DISP_MM = 60.0

# Targets in the CP-SAT LOCAL frame (absolute minus board origin (20,20)).
#
# "control" re-runs de59c0458's Run B VERBATIM -- R24's displacement reference
# is its own current position, i.e. the recipe is asked for "change as little
# as possible". It is the diagnostic that separates "the retarget caused the
# churn" from "this recipe churns on today's board", and it is the reason the
# CP-SAT output is reported rather than written (see the doc's Sec 3).
#
# The other two are the candidates the geometric frontier search produced
# (docs/evidence/2026-08-04-r24-barrier-frontier.py), handed to CP-SAT so the
# real constraint set gets a say:
#   candidate-1 -- absolute (57.50, 38.50), Manhattan 43.28mm
#   candidate-2 -- absolute (81.00, 21.50), Manhattan 49.78mm  [RECOMMENDED]
CANDIDATES: dict[str, tuple[float, float] | None] = {
    "control-no-retarget": None,
    "candidate-1": (37.5, 18.5),
    "candidate-2": (61.0, 1.5),
}


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


def run_candidate(
    name: str, target: tuple[float, float] | None, pcb, extra, full, full_vd
) -> dict:
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}

    # The one change from de59c0458's Run B: R24's displacement reference is
    # the frontier TARGET, not its current position. Everything else is still
    # pulled to where it already sits, so the objective's minimum is "nobody
    # moves except R24, which goes as close to the target as the constraints
    # allow". target=None is the verbatim control.
    min_disp = dict(pos)
    hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
    if target is not None:
        min_disp["R24"] = target
        hints["R24"] = (target[0], target[1], rot["R24"])

    res = solve_placement(
        netlist=pcb.netlist,
        board=pcb.board,
        extra_constraints=extra,
        timeout_ms=TIMEOUT_MS,
        seed=SEED,
        hint_positions=hints,
        minimize_displacement_to=min_disp,
        max_displacement_mm=MAX_DISP_MM,
        fixed_rotations=dict(rot),
        fixed_copper={
            "parse_result": parse_result_without_zones(pcb),
            "free_refs": FREE,
            "margin_mm": MARGIN_FC_MM,
        },
        validator_input={"placement": full, "voltage_domains": full_vd},
    )

    # Determinism class (2026-08-01-ortools-cpsat-spike.md): bit-identical
    # only when the solve terminated before the wall clock ran out.
    timed_out = res.solve_time_ms >= TIMEOUT_MS * 0.98
    moved = sorted(
        ref
        for ref, (x, y) in pos.items()
        if ref in res.positions
        and (abs(res.positions[ref][0] - x) > 0.02 or abs(res.positions[ref][1] - y) > 0.02)
    )
    per_ref = {
        ref: round(
            abs(res.positions[ref][0] - pos[ref][0]) + abs(res.positions[ref][1] - pos[ref][1]), 4
        )
        for ref in moved
    }
    total_disp = round(sum(per_ref.values()), 4)

    r24 = res.positions.get("R24")
    origin = getattr(pcb.board, "origin", (0.0, 0.0))
    print(f"\n--- {name}: target(local)={target}")
    print(f"    status={res.status} time={res.solve_time_ms:.0f}ms timed_out={timed_out}")
    print(f"    R24 local {pos['R24']} -> {r24}  rot={res.rotations.get('R24')}")
    if r24:
        print(
            f"    R24 absolute ({pos['R24'][0]+origin[0]:.3f},{pos['R24'][1]+origin[1]:.3f}) -> "
            f"({r24[0]+origin[0]:.3f},{r24[1]+origin[1]:.3f})"
        )
    print(f"    refs moved >0.02mm: {len(moved)}  total displacement {total_disp}mm")
    for ref, d in sorted(per_ref.items(), key=lambda kv: -kv[1])[:10]:
        print(f"        {ref}: {d}mm")

    va = res.validator_audit
    audit = None
    if va is not None:
        audit = {
            "hard_failures": len(va.hard_failures),
            "intra_footprint": len(va.intra_footprint),
            "coverage_gaps": len(va.coverage_gaps),
            "covered_pair_count": va.covered_pair_count,
            "validator_violation_count": va.validator_violation_count,
            "geometry_trusted": bool(va.geometry_trusted),
            "clean": bool(va.clean),
        }
        print(f"    validator_audit: {audit}")

    return {
        "name": name,
        "target_local": list(target) if target else None,
        "status": res.status,
        "solve_time_ms": res.solve_time_ms,
        "timeout_ms": TIMEOUT_MS,
        "timed_out": timed_out,
        "determinism_class": (
            "NOT reproducible (timeout-terminated)" if timed_out else "reproducible (terminated before timeout)"
        ),
        "seed": SEED,
        "R24_from_local": list(pos["R24"]),
        "R24_to_local": list(r24) if r24 else None,
        "R24_to_absolute": [r24[0] + origin[0], r24[1] + origin[1]] if r24 else None,
        "R24_rotation_idx": res.rotations.get("R24"),
        "moved_refs": moved,
        "per_ref_displacement_mm": per_ref,
        "total_displacement_mm": total_disp,
        "validator_audit": audit,
        "placement": {
            ref: {"position": list(p), "rotation_idx": res.rotations.get(ref, 0)}
            for ref, p in res.positions.items()
        },
    }


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

    results = [
        run_candidate(name, target, pcb, extra, full, full_vd)
        for name, target in CANDIDATES.items()
    ]

    OUT.write_text(
        json.dumps(
            {
                "provenance": {"commit": PROVENANCE_COMMIT, "dirty": False},
                "recipe": (
                    "de59c0458 Run B (solve_placement + fixed_copper free_refs={R24}, "
                    "margin 0.05, fixed rotations, min-displacement, max_displacement_mm=60, "
                    f"seed {SEED}, {TIMEOUT_MS}ms) with R24's displacement reference retargeted"
                ),
                "board": str(PCB.relative_to(REPO)),
                "candidates": results,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    )
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
