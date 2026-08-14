"""
Router V6 Pipeline: Grid preparation and resource analysis.

Extracted from ``_pipeline_stages.py`` — contains Stage 2 channel
analysis, resource bound computation, and related helpers.
"""

from __future__ import annotations

import logging as _logging
from contextlib import nullcontext
from typing import Any

from temper_placer.core.pad_identity import net_pad_positions as _pad_identity_net_pad_positions
from temper_placer.router_v6._pipeline_types import Stage2Output
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator


def _net_pad_positions(net, comp_by_ref: dict) -> list[tuple[float, float]]:
    """Resolve a Net's pads to world coordinates via component lookup.

    ``Net`` carries ``pins`` as ``[(component_ref, pin_name), ...]``; this
    helper joins each pair with the corresponding component's pin to
    produce a list of (x, y) world coordinates, via
    ``pin_world_position`` -- "the single source of truth for all
    pad-position computation" (its own module docstring), which applies
    the component's rotation and side-mirror to the pin's local offset.

    This used to add ``pin.position`` (the pin's LOCAL, unrotated offset --
    see ``Component``/``Pin`` construction in ``parse_engine.rs``, which
    stores it pad-centroid-relative and pre-rotation, with rotation applied
    separately) directly to ``comp.initial_position``, silently skipping
    rotation entirely. MEASURED on ``pcb/temper.kicad_pcb`` (2026-08-08):
    148 of 169 components (87.6%) have a nonzero ``initial_rotation`` --
    for any of them, the naive sum was wrong by exactly the pin's rotated-
    vs-unrotated offset delta (e.g. C1, rotated 90 degrees: naive gave
    (43.99, 206.72) for pin 1 where the correct, KiCad-matching world
    position is (51.49, 214.22) -- a 7.5mm error). This function's output
    feeds both ``fallback_channel_path`` and
    ``expand_channel_path_terminals`` (via ``_run_stage4``'s ``pads``
    parameter) as the router's "ground truth" for where a net's own pads
    are, so this bug directly undermined the reliability of the terminal
    validation this module's ``_validated_two_pad_terminals`` performs, for
    the large majority of this board's components.

    Pads whose component is missing from ``comp_by_ref`` or which lack a
    resolvable position are skipped silently so the caller's fallback
    logic can decide what to do.

    Duplicate ``(component_ref, pin_name)`` occurrences within *net*'s own
    pins are resolved to DISTINCT physical pads via
    :func:`temper_placer.core.pad_identity.net_pad_positions`
    (occurrence-indexed), not the same first match every time -- see that
    module's docstring for why a naive ``comp.get_pin(pin_name)`` call
    silently collapses a real multi-terminal net (this board's
    manufacturer-duplicated relay contact pads) into what looks like a
    trivial single-point one. This function used to carry its own copy of
    that occurrence-indexed lookup (``_nth_matching_pin``, added by the
    fix this docstring describes) and its own component-lookup/rotation
    loop; both are now the single, canonical implementation in
    ``pad_identity``, which this function's contract (fallback to the
    component's own position for an unresolvable pin, skip entirely when
    the component or its position is missing) matches exactly.
    """
    return _pad_identity_net_pad_positions(net, comp_by_ref)


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
