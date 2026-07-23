"""
Router V6 Pipeline: Grid preparation and resource analysis.

Extracted from ``_pipeline_stages.py`` — contains Stage 2 channel
analysis, resource bound computation, and related helpers.
"""

from __future__ import annotations

import logging as _logging
from contextlib import nullcontext
from typing import Any

from temper_placer.router_v6._pipeline_types import Stage2Output
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator


def _net_pad_positions(net, comp_by_ref: dict) -> list[tuple[float, float]]:
    """Resolve a Net's pads to world coordinates via component lookup.

    ``Net`` carries ``pins`` as ``[(component_ref, pin_name), ...]``; this
    helper joins each pair with the corresponding component's
    ``initial_position`` plus the pin's local ``position`` offset to produce
    a list of (x, y) world coordinates. Pads whose component is missing
    from ``comp_by_ref`` or which lack a resolvable position are skipped
    silently so the caller's fallback logic can decide what to do.
    """
    positions: list[tuple[float, float]] = []
    for comp_ref, pin_name in getattr(net, "pins", []):
        comp = comp_by_ref.get(comp_ref)
        if comp is None:
            continue
        comp_pos = getattr(comp, "initial_position", None)
        if comp_pos is None:
            continue
        pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
        if pin is None:
            positions.append((float(comp_pos[0]), float(comp_pos[1])))
            continue
        px, py = pin.position
        positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
    return positions


def _last_skeleton(skeletons: dict[str, Any]) -> Any:
    """Return the last inserted skeleton (insertion-ordered dict since 3.7)."""
    return next(reversed(skeletons.values()), None)


def _run_stage2(self, pcb: ParsedPCB, escape_vias: list[EscapeVia]) -> Stage2Output:
    """Run Stage 2: Channel Analysis (delegated to Stage2Orchestrator)."""
    if self.verbose:
        print("Stage 2 (Orchestrated): Channel analysis...")

    ctx = self.profiler.stage("stage2") if self.profiler else nullcontext()
    with ctx:
        orchestrator = Stage2Orchestrator(verbose=self.verbose)
        state = orchestrator.run(pcb, escape_vias)
        stage2 = Stage2Orchestrator.assemble_stage2_output(state)

    if self.verbose and stage2.bottleneck_analysis.has_critical_bottlenecks:
        print(f"    Warning: {len(stage2.bottleneck_analysis.bottlenecks)} bottlenecks identified")

    return stage2


def _compute_resource_bound(self, pcb: ParsedPCB, stage2: Stage2Output) -> None:
    """Compute and log the resource exhaustion upper bound.

    Uses the EDT occupancy grid from Stage 2 and net bounding boxes
    to compute the theoretical maximum number of simultaneously
    routable nets (bin-packing lower bound).
    """
    if not stage2.occupancy_grids:
        if self.verbose:
            print("    Resource bound: no occupancy grids available, skipping")
        return

    grid = stage2.occupancy_grids.get("F.Cu") or next(iter(stage2.occupancy_grids.values()))
    if grid is None:
        return

    trace_width = pcb.design_rules.default_trace_width_mm
    from temper_placer.router_v6.resource_bound import _net_bboxes_from_pcb, demand_budget_summary

    bboxes = _net_bboxes_from_pcb(pcb)
    summary = demand_budget_summary(grid, bboxes, trace_width)

    if self.verbose:
        print(
            f"    Resource bound: {summary['max_routable']}/{summary['total_nets']} "
            f"nets routable "
            f"(fill_factor={summary['fill_factor']:.3f}, "
            f"capacity={summary['total_capacity_mm2']:.1f} mm^2, "
            f"demand={summary['total_demand_mm2']:.1f} mm^2, "
            f"utilization={summary['utilization']:.2f})"
        )

        if summary["max_routable"] < summary["total_nets"]:
            shortage = summary["total_nets"] - summary["max_routable"]
            print(
                f"    WARNING: Resource bound predicts at least {shortage} "
                f"net(s) will fail regardless of algorithm"
            )

    _logging.getLogger(__name__).info(
        "Resource exhaustion bound: %d/%d routable "
        "(fill_factor=%.3f, %d clusters, capacity=%.1f mm^2, "
        "demand=%.1f mm^2)",
        summary["max_routable"],
        summary["total_nets"],
        summary["fill_factor"],
        summary["cluster_count"],
        summary["total_capacity_mm2"],
        summary["total_demand_mm2"],
    )
