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


def _nth_matching_pin(comp: Any, name_or_number: str, occurrence: int) -> Any:
    """Return the *occurrence*-th (0-indexed) pin on *comp* whose ``name``
    or ``number`` equals *name_or_number*, in ``comp.pins`` iteration
    order, or ``None`` if fewer than ``occurrence + 1`` pins match.

    ``Component.get_pin`` (the Rust pyclass method, ``netlist_contracts.rs``)
    always returns the FIRST name/number match -- correct for the common
    case of one physical pad per pin name, but silently WRONG whenever a
    footprint has more than one physical pad sharing a pad number/name.
    That shape is real and documented on this board, not hypothetical: K2/K3
    (the discharge relays, ``temper:Relay_SPDT_Schrack-RT314012``) each have
    a manufacturer-duplicated pad "3"/"4"/"1" -- two physical solder holes
    7.5mm apart per logical contact, for 16A current sharing (see the
    footprint's own embedded datasheet comment in ``pcb/temper.kicad_pcb``).
    A net whose *only* pins are two occurrences of the identical
    ``(component_ref, pin_name)`` pair (e.g. ``discharge.k_dis1-no``,
    ``pins == [('K2', '3'), ('K2', '3')]``) is NOT a 1-terminal net --
    ``pad_connectivity_audit`` confirms 2 genuinely distinct physical pad
    positions, 7.5mm apart, on the real board. Calling ``comp.get_pin(name)``
    naively for every occurrence collapses those 2 distinct terminals onto
    1 coordinate, which turns a real 2-terminal net into what looks like a
    trivial self-referential one -- A* then "routes" a zero-length path
    between two identical points, reports success, and never actually joins
    the real second pad. MEASURED: this is the entire mechanism behind
    ``discharge.k_dis1-no``/``discharge.k_dis2-no`` silently landing in
    ``pad_connectivity_audit``'s no-copper bucket while Stage 4 prints
    "routed successfully" for them.

    ``net.pins`` and ``comp.pins`` are both built by the same encounter-order
    iteration over a component's raw pad list (``extract_nets_pure`` /
    ``parse_engine.rs``), so the Nth occurrence of ``(comp_ref, pin_name)``
    within a given net's ``pins`` corresponds exactly to the Nth
    name/number-matching pin in that component's own ``pins`` list --
    this function resolves that correspondence explicitly instead of
    relying on ``get_pin``'s first-match shortcut.
    """
    seen = 0
    for pin in getattr(comp, "pins", None) or ():
        if pin is None:
            continue
        if getattr(pin, "name", None) == name_or_number or getattr(pin, "number", None) == name_or_number:
            if seen == occurrence:
                return pin
            seen += 1
    return None


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
    pins are resolved to DISTINCT physical pads via :func:`_nth_matching_pin`
    (occurrence-indexed), not the same first match every time -- see that
    function's docstring for why a naive ``comp.get_pin(pin_name)`` call
    silently collapses a real multi-terminal net (this board's
    manufacturer-duplicated relay contact pads) into what looks like a
    trivial single-point one.
    """
    from temper_placer.core.pin_geometry import pin_world_position

    positions: list[tuple[float, float]] = []
    occurrence_by_key: dict[tuple[str, str], int] = {}
    for comp_ref, pin_name in getattr(net, "pins", []):
        comp = comp_by_ref.get(comp_ref)
        if comp is None:
            continue
        comp_pos = getattr(comp, "initial_position", None)
        if comp_pos is None:
            continue
        key = (comp_ref, pin_name)
        occurrence = occurrence_by_key.get(key, 0)
        occurrence_by_key[key] = occurrence + 1
        pin = _nth_matching_pin(comp, pin_name, occurrence) if hasattr(comp, "get_pin") else None
        if pin is None:
            positions.append((float(comp_pos[0]), float(comp_pos[1])))
            continue
        wx, wy = pin_world_position(pin, comp)
        positions.append((float(wx), float(wy)))
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
