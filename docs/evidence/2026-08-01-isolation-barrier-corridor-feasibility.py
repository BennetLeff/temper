#!/usr/bin/env python3
"""Corridor-feasibility probe for the mains<->SELV isolation barrier.

Runs the CP-SAT corridor-constrained placement on the PRODUCTION board
(``pcb/temper.kicad_pcb``, parsed via ``io.kicad_parser.parse_kicad_pcb`` --
the same path the pipeline's InputStage uses) for every cell of the
experiment matrix in plan ``docs/plans/2026-08-01-002-*``:

    orientation  x  variant  x  stage
    {X, Y}       x  {as-is, K3-relaxed}  x  {1 soft min-displacement, 2 + hard budget<=25mm}

and writes a machine-readable results JSON (used to build the decision
record table). Numbers are measured, never fabricated: an infeasible cell
reports the solver's own UNSAT core (which assumption literals conflict),
and a cell that times out is reported as ``unknown`` (not feasible).

Stage 1 carries a SOFT minimum-displacement objective (plan OQ-B: the
displacement number is only meaningful if the solver is steering toward
current positions); stage 2 adds the HARD ``max_displacement_mm`` bound via
the existing bounded-repair formulation (issue #504).

Measurements:
  - Displacement is Manhattan |dx| + |dy| of component centers, measured
    vs each component's ``initial_position`` (the footprint's current board
    position as parsed from ``pcb/temper.kicad_pcb``).
  - Staged parts (``C27``, whose pads sit outside the board outline) are
    EXCLUDED from the budget constraint and from the measurement, matching
    the gate's treatment (docs/evidence/2026-08-01-isolation-barrier-feasibility.md
    "Board edge constraints").
  - ``max_displacement_mm`` reuses the existing bounded-repair formulation
    (issue #504, ``solve_placement``): a HARD per-component Manhattan bound
    applied to every ref in ``minimize_displacement_to``.

Run from the repo root:
    uv run --no-sync python docs/evidence/2026-08-01-isolation-barrier-corridor-feasibility.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
PCB = REPO / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO / "elec" / "domain_manifest.yaml"
RESULTS_JSON = Path(__file__).with_suffix(".json")

CORRIDOR_WIDTH_MM = 8.0
BUDGET_MM = 25.0
DEFAULT_TIMEOUT_MS = 300_000
SEED = 0
# Staged parts: pads outside the board outline, excluded from budget + measurement.
STAGED_EXCLUDED = frozenset({"C27"})

ORIENTATIONS = ["X", "Y"]
VARIANTS = ["as-is", "k3-relaxed"]
STAGES = [1, 2]

ORIENTATION_KWARG = {"X": "vertical", "Y": "horizontal"}


@dataclass
class CellResult:
    orientation: str
    variant: str
    stage: int
    status: str = "unknown"  # feasible | infeasible | unknown
    solve_time_ms: float = 0.0
    unsat_core: list[str] = field(default_factory=list)
    # displacement stats (only for feasible solves)
    max_displacement_mm: float | None = None
    total_displacement_mm: float | None = None
    n_moved_gt_1mm: int | None = None
    n_measured: int | None = None
    top_movers: list[dict] = field(default_factory=list)
    # full placement for reproducibility (feasible solves only)
    positions: dict[str, list[float]] = field(default_factory=dict)
    rotations: dict[str, int] = field(default_factory=dict)
    # corridor report facts
    corridor_position_mm: float | None = None
    infeasible_isolators: list[str] = field(default_factory=list)
    relaxed_isolator_straddle: list[str] = field(default_factory=list)
    note: str = ""


def _load_production():
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    pr = parse_kicad_pcb(PCB)
    board = pr.board
    netlist = pr.netlist
    assert board is not None
    return board, netlist


def _measure(netlist, positions, excluded: frozenset[str]) -> dict:
    """Displacement stats vs current board positions (Manhattan centers)."""
    comp_by_ref = {c.ref: c for c in netlist.components}
    rows: list[tuple[str, float]] = []
    for ref, (x, y) in positions.items():
        if ref in excluded:
            continue
        comp = comp_by_ref.get(ref)
        if comp is None or comp.initial_position is None:
            continue
        cx, cy = comp.initial_position
        d = abs(x - cx) + abs(y - cy)
        rows.append((ref, d))
    if not rows:
        return {"max": None, "total": None, "moved_gt_1mm": None, "n": 0, "top": []}
    rows.sort(key=lambda r: r[1], reverse=True)
    return {
        "max": round(rows[0][1], 3),
        "total": round(sum(d for _, d in rows), 3),
        "moved_gt_1mm": sum(1 for _, d in rows if d > 1.0),
        "n": len(rows),
        "top": [{"ref": ref, "mm": round(d, 3)} for ref, d in rows[:12]],
    }


def run_cell(
    orientation: str,
    variant: str,
    stage: int,
    timeout_ms: int,
    board,
    netlist,
    seed: int = SEED,
) -> CellResult:
    from temper_placer.placer.cp_sat._encoder_solve import solve_placement

    cell = CellResult(orientation=orientation, variant=variant, stage=stage)

    isolation_barrier = {
        "manifest_path": MANIFEST,
        "corridor_width_mm": CORRIDOR_WIDTH_MM,
        "orientation": ORIENTATION_KWARG[orientation],
    }
    if variant == "k3-relaxed":
        isolation_barrier["relax_isolator_straddle"] = {"K3"}

    hint_positions = {
        c.ref: (c.initial_position[0], c.initial_position[1], c.initial_rotation or 0)
        for c in netlist.components
        if c.initial_position is not None
    }

    kwargs = dict(
        netlist=netlist,
        board=board,
        timeout_ms=timeout_ms,
        seed=seed,
        isolation_barrier=isolation_barrier,
        hint_positions=hint_positions,
    )
    # Stage 1: soft minimum-displacement OBJECTIVE (preference, not a bound)
    # so the reported displacement is the solver's best near-current placement
    # (plan OQ-B: displacement is the metric of interest; a pure-feasibility
    # solve would report an arbitrary far-away packing). Stage 2 adds the HARD
    # per-component <= BUDGET_MM bound on top via the existing bounded-repair
    # formulation (issue #504). Both pass every in-board ref's current
    # position as the reference.
    kwargs["minimize_displacement_to"] = {
        c.ref: c.initial_position
        for c in netlist.components
        if c.initial_position is not None and c.ref not in STAGED_EXCLUDED
    }
    if stage == 2:
        kwargs["max_displacement_mm"] = BUDGET_MM

    t0 = time.monotonic()
    result = solve_placement(**kwargs)
    cell.solve_time_ms = round((time.monotonic() - t0) * 1000.0, 1)
    cell.status = result.status

    report = getattr(result, "isolation_barrier_report", None)
    if report is not None:
        cell.corridor_position_mm = round(report.corridor_position_mm, 3)
        cell.infeasible_isolators = list(report.infeasible_isolators)
        cell.relaxed_isolator_straddle = sorted(str(r) for r in report.relaxed_isolator_straddle)

    if result.status == "infeasible":
        cell.unsat_core = [u.get("name", "") for u in result.unsat_core]
    if result.status in ("feasible", "optimal"):
        stats = _measure(netlist, result.positions, STAGED_EXCLUDED)
        cell.max_displacement_mm = stats["max"]
        cell.total_displacement_mm = stats["total"]
        cell.n_moved_gt_1mm = stats["moved_gt_1mm"]
        cell.n_measured = stats["n"]
        cell.top_movers = stats["top"]
        cell.positions = {ref: [x, y] for ref, (x, y) in result.positions.items()}
        cell.rotations = dict(result.rotations)
        cell.note = f"solve objective={result.objective_value:.1f}"
    return cell


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--orientation", choices=ORIENTATIONS + ["all"], default="all")
    ap.add_argument("--variant", choices=VARIANTS + ["all"], default="all")
    ap.add_argument("--stage", choices=["1", "2", "all"], default="all")
    ap.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    ap.add_argument("--out", type=Path, default=RESULTS_JSON)
    ap.add_argument("--force", action="store_true", help="re-run even if results JSON exists")
    args = ap.parse_args()

    # Load cached results if present (per-cell; only re-run requested cells).
    cache: dict[str, dict] = {}
    if args.out.exists() and not args.force:
        cache = json.loads(args.out.read_text())

    board, netlist = _load_production()
    print(
        f"board {board.width}x{board.height}mm, {len(netlist.components)} components, "
        f"corridor {CORRIDOR_WIDTH_MM}mm, budget {BUDGET_MM}mm (stage 2), "
        f"staged-excluded={sorted(STAGED_EXCLUDED)}, timeout {args.timeout_ms}ms"
    )

    orientations = ORIENTATIONS if args.orientation == "all" else [args.orientation]
    variants = VARIANTS if args.variant == "all" else [args.variant]
    stages = STAGES if args.stage == "all" else [int(args.stage)]
    results = dict(cache)
    for orientation in orientations:
        for variant in variants:
            for stage in stages:
                key = f"{orientation}|{variant}|s{stage}"
                if key in results and not args.force:
                    print(f"  [cached] {key}")
                    continue
                print(f"  [running] {key} (timeout {args.timeout_ms}ms) ...", flush=True)
                cell = run_cell(orientation, variant, stage, args.timeout_ms, board, netlist)
                results[key] = asdict(cell)
                summary = (
                    f"status={cell.status} time={cell.solve_time_ms:.0f}ms"
                    + (f" max_disp={cell.max_displacement_mm}mm total={cell.total_displacement_mm}mm" if cell.max_displacement_mm is not None else "")
                    + (f" unsat={cell.unsat_core[:4]}" if cell.unsat_core else "")
                )
                print(f"    -> {summary}")
                args.out.write_text(json.dumps(results, indent=2))
                print(f"    (cached to {args.out})")

    # Print a compact decision table.
    print("\n=== decision table ===")
    header = f"{'cell':<22} {'status':<10} {'time_s':>7} {'max_mm':>8} {'total_mm':>9} {'movers>1':>8} {'unsat_core':<40}"
    print(header)
    for orientation in orientations:
        for variant in variants:
            for stage in stages:
                key = f"{orientation}|{variant}|s{stage}"
                r = results.get(key)
                if r is None:
                    continue
                core = ",".join(r["unsat_core"][:3]) if r["unsat_core"] else ""
                print(
                    f"{key:<22} {r['status']:<10} {r['solve_time_ms']/1000:>7.1f} "
                    f"{str(r['max_displacement_mm']):>8} {str(r['total_displacement_mm']):>9} "
                    f"{str(r['n_moved_gt_1mm']):>8} {core:<40}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
