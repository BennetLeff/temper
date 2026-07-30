"""
Router V6 Stage 4.4: Assign Trace Widths

Assigns trace widths based on net class and current requirements.
Part of temper-eixu (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from temper_placer.router_v6.astar_pathfinding import PathfindingResult


def _kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by "_" or start/end of the
    uppercased net name.

    Bug history (2026-07-27): ``_determine_trace_width`` used to match
    ``"AC_"``/``"HV_"``/``"HIGH_VOLTAGE"``/``"GATE"``/``"DRIVE"`` as plain
    substrings (``kw in name_upper``) -- the same defect class confirmed
    three times elsewhere in this repo (``creepage_check.py``,
    ``clearance_check.py``, ``clearance_engine.py``; see
    ``docs/evidence/2026-07-27-net-classification-gate.md``). Found by
    ``scripts/check_net_classification.py`` auditing every net-name
    classifier for the same shape. ``"AC_"``/``"HV_"`` collapse to bare
    ``"AC"``/``"HV"`` here because the boundary regex already requires a
    trailing ``"_"``/digit/end, making the explicit trailing ``"_"`` in
    the original keyword redundant.
    """
    for kw in keywords:
        kw = kw[:-1] if kw.endswith("_") else kw
        if re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper):
            return True
    return False


@dataclass
class TraceWidth:
    """Trace width assignment for a net."""

    net_name: str
    width_mm: float
    reason: str  # Why this width was chosen


@dataclass
class TraceWidthAssignment:
    """Collection of trace width assignments."""

    assignments: dict[str, TraceWidth]  # net_name -> TraceWidth

    @property
    def assignment_count(self) -> int:
        """Number of trace width assignments."""
        return len(self.assignments)

    def get_width(self, net_name: str) -> float | None:
        """Get assigned width for a net."""
        assignment = self.assignments.get(net_name)
        return assignment.width_mm if assignment else None


def assign_trace_widths(
    pathfinding_result: PathfindingResult,
    default_width: float = 0.127,  # 5mil standard
    power_width: float = 0.508,  # 20mil for power
    hv_width: float = 0.635,  # 25mil for HV
    design_rules: Any | None = None,
) -> TraceWidthAssignment:
    """
    Assign trace widths based on net class and requirements.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        default_width: Default trace width (mm)
        power_width: Width for power nets (mm)
        hv_width: Width for high-voltage nets (mm)
        design_rules: Optional netclass-aware design rules (duck-typed:
            needs ``.net_class_assignments`` and ``.net_classes`` dicts,
            e.g. ``router_v6.stage0_data.DesignRules`` as populated by
            ``route_pcb()``'s ``design_rules``/``net_classes`` injection).
            When a routed net has an *explicit* netclass assignment here,
            that class's ``trace_width_mm`` is authoritative and wins over
            the keyword heuristic below -- see ``_determine_trace_width``.

    Returns:
        TraceWidthAssignment with all width assignments

    Example:
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> assignment = assign_trace_widths(result)
        >>> assignment.assignment_count >= 0
        True
    """
    assignments = {}

    # Tree geometry is branch-aware rather than serial RoutePath data, but
    # width is a net-class property.  Include complete and partial trees so
    # experimental output receives the same board-derived assignment as every
    # conventional route.
    routed_net_names = (
        set(pathfinding_result.routed_paths)
        | set(pathfinding_result.partial_paths)
        | set(pathfinding_result.tree_routes)
        | set(pathfinding_result.partial_tree_routes)
    )
    for net_name in routed_net_names:
        # Determine appropriate width for this net
        width = _determine_trace_width(
            net_name,
            default_width,
            power_width,
            hv_width,
            design_rules,
        )

        assignments[net_name] = width

    return TraceWidthAssignment(assignments=assignments)


def _determine_trace_width(
    net_name: str,
    default_width: float,
    power_width: float,
    hv_width: float,
    design_rules: Any | None = None,
) -> TraceWidth:
    """
    Determine appropriate trace width for a net.

    Args:
        net_name: Net name
        default_width: Default width
        power_width: Power net width
        hv_width: High voltage width
        design_rules: Optional netclass-aware design rules -- see
            ``assign_trace_widths``. Consulted first; the keyword
            heuristic below is only a fallback for nets with no explicit
            netclass assignment (e.g. callers with no design_rules
            threaded at all, which keeps existing behavior/tests
            unchanged).

    Returns:
        TraceWidth assignment

    Bug history (2026-07-29): this function used to be the *only* source
    of truth for routed trace width -- pure net-name substring/keyword
    matching against three hardcoded literals (default/power/hv_width),
    with zero knowledge of the real per-netclass minimums in
    ``core/design_rules.py`` (``TEMPER_NET_CLASSES``). GATE_H/GATE_L/
    GATE_HS/GATE_LS matched the "GATE"/"DRIVE" keyword branch and got
    ``power_width * 0.6`` = 0.3048mm (12 mil) -- a router-internal
    heuristic constant that happens to be exactly the DRC minimum-width
    violation width measured for GateDriveHV (0.4mm minimum,
    ``design_rules.py:391-403``) on every one of the 39 GATE_LS segments
    already on the board. The 0.3048mm figure was never derived from any
    netclass minimum at all; it was a coincidence of the 60%-of-power-
    width heuristic. Fixed by consulting the caller's netclass-aware
    ``design_rules`` (threaded from ``pcb.design_rules`` in
    ``_pipeline_route.py``'s Stage 4.4 call, itself populated by
    ``route_pcb()``'s ``net_classes``/``net_class_assignments``
    injection in ``_pipeline_core.py``) before ever falling back to the
    keyword heuristic.
    """
    if design_rules is not None:
        class_assignments = getattr(design_rules, "net_class_assignments", None) or {}
        net_classes = getattr(design_rules, "net_classes", None) or {}
        class_name = class_assignments.get(net_name)
        if class_name and class_name in net_classes:
            rules = net_classes[class_name]
            trace_width_mm = getattr(rules, "trace_width_mm", None)
            if trace_width_mm is not None:
                return TraceWidth(
                    net_name=net_name,
                    width_mm=trace_width_mm,
                    reason=f"Netclass minimum ({class_name})",
                )

    name_upper = net_name.upper()

    # High voltage nets (AC, HV)
    if _kw_boundary_match(name_upper, ("AC_", "HV_", "HIGH_VOLTAGE")):
        return TraceWidth(
            net_name=net_name,
            width_mm=hv_width,
            reason="High voltage net requires wider trace",
        )

    # Power nets (GND, VCC, etc.)
    # FIXED 2026-07-28: this branch was still a bare `kw in name_upper`
    # substring test even though the HV/gate-drive branches above and
    # below it had already been anchored via _kw_boundary_match for the
    # identical reason on 2026-07-27. A bare "+" matched almost any net
    # with a "+" anywhere in its name (e.g. "DC_BUS+"'s HV classification
    # above already short-circuits it, but a hypothetical non-HV net
    # merely containing "+" would have been silently over-widened).
    # Found completing the audit scripts/check_net_classification.py's
    # 2026-07-28 vocabulary extension prompted -- see
    # docs/evidence/2026-07-28-zone-layer-classification-fix.md.
    if _kw_boundary_match(name_upper, ("GND", "VCC", "VDD", "VSS", "POWER")) or re.search(
        r"^\+", name_upper
    ):
        return TraceWidth(
            net_name=net_name,
            width_mm=power_width,
            reason="Power net requires wider trace for current capacity",
        )

    # Gate drive signals (medium current)
    if _kw_boundary_match(name_upper, ("GATE", "DRIVE")):
        return TraceWidth(
            net_name=net_name,
            width_mm=power_width * 0.6,  # 60% of power width
            reason="Gate drive signal requires medium-width trace",
        )

    # Default signal nets
    return TraceWidth(
        net_name=net_name,
        width_mm=default_width,
        reason="Standard signal trace",
    )
