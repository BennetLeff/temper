#!/usr/bin/env python3
"""Declared signal-layer count <-> routing-demand utilisation gate.

WHY THIS EXISTS
---------------
This is the gate that would have caught the defect
``docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md`` and
``docs/evidence/2026-08-13-layer-architecture-decision.md`` had to measure
after the fact: nothing connected "the board declares N signal layers" to
"the netlist demands M mm^2 of routing channel" until a router actually ran
and 40/139 nets came back with zero legal path. The board's
``(layers ...)`` declaration and the netlist's routing demand were two
numbers nobody ever compared -- this gate is that comparison, computed
BEFORE a 450-second router run, not after one.

**Method, and what it deliberately reuses rather than re-derives.**
Demand is a LIVE recomputation against the real, committed board and
netlist -- ``temper_placer.router_v6.resource_bound._net_bboxes_from_pcb``
(per-net bounding-box geometry from real pin positions) and
``_compute_fill_factor`` (the same trace-width-vs-bbox-area estimate
``resource_bound.demand_budget_summary`` uses in production, at
``router_v6/_pipeline_grid.py``'s ``_compute_resource_bound``) -- both pure
geometry, no occupancy grid, no A* search, sub-second. Reproduces
``docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md``'s cited
11236.6 mm^2 demand figure to within rounding (11236.57 mm^2, measured
2026-08-13 against the same board lineage) as a sanity check on this
gate's own method, not merely asserted.

Capacity is NOT re-measured live per signal layer here -- building a real
occupancy grid for a layer that carries no copper yet (this repo's newly-
declared ``In3.Cu``/``In4.Cu``, see the evidence doc Sec 6.4) has nothing
to measure. Instead this gate uses a CITED, SOURCED per-layer capacity
constant (``CAPACITY_PER_SIGNAL_LAYER_MM2``, see that constant's own
docstring) derived from the same resource-bound measurement the 11236.6 mm^2
demand figure came from, on the honest, explicit, and NOT independently
re-verified assumption that additional signal layers of the same board
outline contribute roughly equal free-channel area. This is a real,
disclosed approximation -- a live per-layer capacity re-measurement would
be more rigorous and is deferred, not silently assumed away (see this
script's own module-level ``# LIMITATION`` comment below).

DECLARED SIGNAL-LAYER COUNT comes from
``temper_placer.core.board_layer_roles.signal_layer_names`` -- the board's
own ``(layers ...)`` ARCHITECTURE declaration, not the router engine's
current capability ceiling (``routable_signal_layers``/
``ENGINE_SUPPORTED_SIGNAL_LAYERS``). This is deliberate: this gate exists
to catch a mismatch between the declared ARCHITECTURE and the netlist's
DEMAND -- collapsing "declared" down to "what the engine currently
supports" would silently hide exactly the gap this gate exists to surface
(see ``board_layer_roles``'s own module docstring for the two-accessor
argument in full).

FAIL-CLOSED CONTRACT
---------------------
Exit codes:
  0 - PASSED: utilisation is below the WARN threshold
  2 - WARNING (not a failure): utilisation is between WARN and FAIL
  3 - VIOLATION: utilisation at or above the FAIL threshold -- the
      bin-packing lower bound this repo's own resource_bound.py proves
      (aggregate demand cannot fit in aggregate capacity, so SOME nets are
      guaranteed to fail regardless of algorithm)
  5 - GATE ERROR: the gate could not run a trustworthy check at all (board
      missing/unparsable, no declared signal layer, netlist parse failure)

Usage:
  uv run python scripts/check_layer_utilization_gate.py
  uv run python scripts/check_layer_utilization_gate.py --board PATH
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_WARNING = 2
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# Sourced from docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md
# Sec 4 (channel capacity 8546 mm^2 measured against this board's real,
# committed 2-signal-layer stackup, via
# router_v6.resource_bound.demand_budget_summary, citing
# docs/evidence/2026-08-13-clearance-1085-remediation-exec-steps-1-2.md
# Sec 2.5 for the original live measurement) divided by the 2 signal
# layers that measurement was taken against (F.Cu + B.Cu).
#
# LIMITATION, stated plainly rather than hidden in a comment nobody reads:
# this is a CITED CONSTANT, not a live per-run measurement -- it assumes
# every signal layer of this board's outline contributes roughly the same
# free-channel area, which was true for the 2 layers actually measured
# (both outer, same obstacle density from double-sided component mounting)
# but is NOT independently verified for the 2 newly-declared inner signal
# layers (In3.Cu/In4.Cu), which have different physical obstacles (no
# through-hole component footprints, but every via barrel and internal
# keepout instead). A live per-layer capacity re-measurement, once real
# occupancy-grid support exists for inner layers (see the evidence doc Sec
# 6.4), would be strictly more rigorous than this constant and should
# replace it then -- this is deferred, not silently assumed permanent.
CAPACITY_PER_SIGNAL_LAYER_MM2 = 8546.0 / 2

# utilization = demand / (CAPACITY_PER_SIGNAL_LAYER_MM2 * signal_layer_count).
# FAIL_THRESHOLD = 1.0 is not an arbitrary round number: it is the point
# resource_bound.py's own bin-packing lower bound proves infeasible --
# aggregate demand exceeding aggregate capacity guarantees at least one net
# fails, regardless of router algorithm, iteration budget, or net order
# (see that module's own docstring, "Soundness" paragraph). WARN_THRESHOLD
# gives visible headroom before that proven bound, since
# CAPACITY_PER_SIGNAL_LAYER_MM2 is itself an approximation (see above) --
# a board sitting between the two thresholds is not yet proven infeasible
# but has given up the margin that approximation needs to be trusted.
WARN_THRESHOLD = 0.85
FAIL_THRESHOLD = 1.0


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass
class UtilizationReport:
    signal_layers: list[str]
    signal_layer_count: int
    total_nets: int
    total_demand_mm2: float
    total_capacity_mm2: float
    utilization: float


def _load_signal_layers(board_path: Path) -> list[str]:
    from temper_placer.core.board_layer_roles import signal_layer_names

    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    content = board_path.read_text(encoding="utf-8")
    try:
        layers = signal_layer_names(content)
    except ValueError as e:
        raise GateError(f"could not read declared signal layers: {e}") from e
    if not layers:
        raise GateError("board declares zero signal layers -- nothing is routable")
    return layers


def _compute_demand_mm2(board_path: Path) -> tuple[float, int]:
    """Returns ``(total_demand_mm2, total_net_count)``, live, from the real
    board+netlist -- pure geometry (bounding boxes + fill-factor estimate),
    no occupancy grid, no A* search. See module docstring for the method
    and its cross-check against the cited 11236.6 mm^2 figure.
    """
    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.router_v6.resource_bound import (
            _compute_fill_factor,
            _net_bboxes_from_pcb,
        )
    except ImportError as e:
        raise GateError(f"could not import router_v6 demand-computation machinery: {e}") from e

    try:
        pcb = parse_kicad_pcb_v6(board_path)
    except Exception as e:  # noqa: BLE001 - any parse failure must fail this gate closed
        raise GateError(f"could not parse board for demand computation: {e}") from e

    bboxes = _net_bboxes_from_pcb(pcb)
    areas = {name: (b[2] - b[0]) * (b[3] - b[1]) for name, b in bboxes.items()}
    nonzero_areas = {name: a for name, a in areas.items() if a > 0}

    trace_width = pcb.design_rules.default_trace_width_mm
    fill_factor = _compute_fill_factor(trace_width, nonzero_areas)
    demand = sum(a * fill_factor for a in nonzero_areas.values())
    return demand, len(bboxes)


def run(board_path: Path) -> tuple[str, UtilizationReport | None, list[str]]:
    """Returns ``(state, report_or_None, tool_errors)``.

    ``state`` is one of ``"clean"``, ``"warning"``, ``"violation"``,
    ``"tool_error"``.
    """
    try:
        signal_layers = _load_signal_layers(board_path)
        demand_mm2, total_nets = _compute_demand_mm2(board_path)
    except GateError as e:
        return "tool_error", None, [str(e)]

    capacity_mm2 = CAPACITY_PER_SIGNAL_LAYER_MM2 * len(signal_layers)
    utilization = demand_mm2 / capacity_mm2 if capacity_mm2 > 0 else float("inf")

    report = UtilizationReport(
        signal_layers=signal_layers,
        signal_layer_count=len(signal_layers),
        total_nets=total_nets,
        total_demand_mm2=demand_mm2,
        total_capacity_mm2=capacity_mm2,
        utilization=utilization,
    )

    if utilization >= FAIL_THRESHOLD:
        return "violation", report, []
    if utilization >= WARN_THRESHOLD:
        return "warning", report, []
    return "clean", report, []


def _print_report(state: str, report: UtilizationReport | None, tool_errors: list[str]) -> None:
    print("Layer utilisation gate: declared signal-layer count vs. live routing demand")
    if tool_errors:
        print(f"\n{len(tool_errors)} TOOL ERROR(S)")
        for e in tool_errors:
            print(f"  TOOL_ERROR {e}")
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate could not "
            "run a trustworthy check.",
            file=sys.stderr,
        )
        return

    assert report is not None
    print(f"  Declared signal layers ({report.signal_layer_count}): {report.signal_layers}")
    print(f"  Total nets (bbox-derived): {report.total_nets}")
    print(f"  Demand (live, real board+netlist):  {report.total_demand_mm2:.1f} mm^2")
    print(
        f"  Capacity ({report.signal_layer_count} x "
        f"{CAPACITY_PER_SIGNAL_LAYER_MM2:.1f} mm^2/layer, cited): "
        f"{report.total_capacity_mm2:.1f} mm^2"
    )
    print(f"  Utilization: {report.utilization:.3f}")
    print(f"  Thresholds: WARN >= {WARN_THRESHOLD}, FAIL >= {FAIL_THRESHOLD}")

    if state == "clean":
        print("\nLayer utilisation gate passed")
    elif state == "warning":
        print(
            f"\nWARNING -- utilization {report.utilization:.3f} is above {WARN_THRESHOLD} "
            "but below the proven-infeasible bound. Not a failure; a signal this repo's "
            "own capacity margin is thinning."
        )
    elif state == "violation":
        print(
            f"\nFAILED -- utilization {report.utilization:.3f} >= {FAIL_THRESHOLD}. "
            "resource_bound.py's bin-packing lower bound proves at least one net MUST "
            "fail to route regardless of algorithm at this declared signal-layer count. "
            "Either declare more signal layers, or reduce routing demand (fewer nets, "
            "narrower default trace width, tighter placement) -- see "
            "docs/evidence/2026-08-13-layer-architecture-decision.md for the analysis "
            "this gate's threshold and method are drawn from."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    args = parser.parse_args()

    state, report, tool_errors = run(args.board)
    _print_report(state, report, tool_errors)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Layer Utilisation Gate: {state}\n")
            if report is not None:
                f.write(
                    f"- Declared signal layers: {report.signal_layers}\n"
                    f"- Demand: {report.total_demand_mm2:.1f} mm^2\n"
                    f"- Capacity: {report.total_capacity_mm2:.1f} mm^2\n"
                    f"- Utilization: {report.utilization:.3f}\n"
                )
            for e in tool_errors:
                f.write(f"- TOOL_ERROR: {e}\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    if state == "warning":
        sys.exit(EXIT_WARNING)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
