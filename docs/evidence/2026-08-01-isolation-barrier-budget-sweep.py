"""Budget-floor sweep for the straight corridor at its geometric-best position.

Continuation of the NO-GO corridor-feasibility probe: the NO-GO ran the
straight corridor at the board centreline (machinery default). This sweep
runs the same straight corridor at the geometric-best positions from
docs/evidence/2026-08-01-isolation-barrier-feasibility.md (X: c=36.25,
Y: c=127.00, HV_lo) and relaxes the stage-2 budget (25/50/100/150 mm) to
quantify the straight corridor's displacement floor. If even 150 mm is
infeasible at the best position, the straight-corridor family is dead and
the boundary-following (polyline) corridor is confirmed necessary.

K3-relaxed variant only: as-is is straddle-infeasible (K3 -0.5 mm).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
PCB = REPO / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO / "elec" / "domain_manifest.yaml"
RESULTS_JSON = Path(__file__).with_suffix(".json")

CORRIDOR_WIDTH_MM = 8.0
TIMEOUT_MS = 300_000
SEED = 0
STAGED_EXCLUDED = frozenset({"C27"})
# Geometric-best positions (HV_lo) from the feasibility evidence, W=8.0.
BEST_POSITION = {"X": 36.25, "Y": 127.00}
BUDGETS_MM = [25.0, 50.0, 100.0, 150.0]
ORIENTATION_KWARG = {"X": "vertical", "Y": "horizontal"}


@dataclass
class CellResult:
    orientation: str
    budget_mm: float | None
    status: str = "unknown"
    solve_time_ms: float = 0.0
    max_displacement_mm: float | None = None
    total_displacement_mm: float | None = None
    n_moved_gt_1mm: int | None = None
    unsat_core: list[str] = field(default_factory=list)


def _load_production():
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    pr = parse_kicad_pcb(PCB)
    board = pr.board
    netlist = pr.netlist
    assert board is not None
    return board, netlist


def _measure(netlist, positions, excluded: frozenset[str]) -> dict:
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
        return {"max": None, "total": None, "moved_gt_1mm": None}
    rows.sort(key=lambda r: r[1], reverse=True)
    return {
        "max": round(rows[0][1], 3),
        "total": round(sum(d for _, d in rows), 3),
        "moved_gt_1mm": sum(1 for _, d in rows if d > 1.0),
    }


def run_cell(orientation, budget_mm, board, netlist):
    from temper_placer.placer.cp_sat._encoder_solve import solve_placement

    cell = CellResult(orientation=orientation, budget_mm=budget_mm)
    isolation_barrier = {
        "manifest_path": MANIFEST,
        "corridor_width_mm": CORRIDOR_WIDTH_MM,
        "orientation": ORIENTATION_KWARG[orientation],
        "corridor_position_mm": BEST_POSITION[orientation],
        "relax_isolator_straddle": {"K3"},
    }
    hint_positions = {
        c.ref: (c.initial_position[0], c.initial_position[1], c.initial_rotation or 0)
        for c in netlist.components
        if c.initial_position is not None
    }
    minimize_displacement_to = {
        c.ref: c.initial_position
        for c in netlist.components
        if c.initial_position is not None and c.ref not in STAGED_EXCLUDED
    }
    kwargs = dict(
        netlist=netlist,
        board=board,
        timeout_ms=TIMEOUT_MS,
        seed=SEED,
        isolation_barrier=isolation_barrier,
        hint_positions=hint_positions,
        minimize_displacement_to=minimize_displacement_to,
    )
    if budget_mm is not None:
        kwargs["max_displacement_mm"] = budget_mm

    t0 = time.monotonic()
    result = solve_placement(**kwargs)
    cell.solve_time_ms = round((time.monotonic() - t0) * 1000.0, 1)
    cell.status = result.status
    if result.status == "infeasible":
        cell.unsat_core = [u.get("name", "") for u in result.unsat_core]
    if result.status in ("feasible", "optimal"):
        stats = _measure(netlist, result.positions, STAGED_EXCLUDED)
        cell.max_displacement_mm = stats["max"]
        cell.total_displacement_mm = stats["total"]
        cell.n_moved_gt_1mm = stats["moved_gt_1mm"]
    return cell


def main():
    board, netlist = _load_production()
    print(f"board {PCB.name}: {len(netlist.components)} components; best positions {BEST_POSITION}")
    results: dict[str, dict] = {}
    for orientation in ("X", "Y"):
        # Stage 1: no budget (baseline at best position).
        key = f"{orientation}|k3-relaxed|s1|bestpos"
        print(f"[running] {key} ...", flush=True)
        cell = run_cell(orientation, None, board, netlist)
        results[key] = asdict(cell)
        print(f"    -> {cell.status} time={cell.solve_time_ms/1000:.1f}s max={cell.max_displacement_mm} total={cell.total_displacement_mm}")
        RESULTS_JSON.write_text(json.dumps(results, indent=2))
        # Stage 2: budget sweep.
        for budget in BUDGETS_MM:
            key = f"{orientation}|k3-relaxed|s2|{budget:.0f}mm"
            print(f"[running] {key} ...", flush=True)
            cell = run_cell(orientation, budget, board, netlist)
            results[key] = asdict(cell)
            print(f"    -> {cell.status} time={cell.solve_time_ms/1000:.1f}s max={cell.max_displacement_mm} unsat={cell.unsat_core[:3]}")
            RESULTS_JSON.write_text(json.dumps(results, indent=2))

    print("\n=== decision table ===")
    print(f"{'cell':<28} {'status':<10} {'time_s':>7} {'max_mm':>9} {'total_mm':>10} {'movers':>6}")
    for k, r in results.items():
        print(f"{k:<28} {r['status']:<10} {r['solve_time_ms']/1000:>7.1f} "
              f"{str(r['max_displacement_mm']):>9} {str(r['total_displacement_mm']):>10} "
              f"{str(r['n_moved_gt_1mm']):>6}")
    print(f"\nresults cached to {RESULTS_JSON}")


if __name__ == "__main__":
    main()
