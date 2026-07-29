"""
Router V6 Stage 4.4: Assign Trace Widths

Assigns trace widths based on net class and current requirements.
Part of temper-eixu (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
) -> TraceWidthAssignment:
    """
    Assign trace widths based on net class and requirements.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        default_width: Default trace width (mm)
        power_width: Width for power nets (mm)
        hv_width: Width for high-voltage nets (mm)

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
        )

        assignments[net_name] = width

    return TraceWidthAssignment(assignments=assignments)


def _determine_trace_width(
    net_name: str,
    default_width: float,
    power_width: float,
    hv_width: float,
) -> TraceWidth:
    """
    Determine appropriate trace width for a net.

    Args:
        net_name: Net name
        default_width: Default width
        power_width: Power net width
        hv_width: High voltage width

    Returns:
        TraceWidth assignment
    """
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
