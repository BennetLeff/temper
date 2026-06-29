"""
Router V6 Stage 4.4: Assign Trace Widths

Assigns trace widths based on net class and current requirements.
Part of temper-eixu (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_pathfinding import PathfindingResult


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

    for net_name, _route_path in pathfinding_result.routed_paths.items():
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
    if any(kw in name_upper for kw in ['AC_', 'HV_', 'HIGH_VOLTAGE']):
        return TraceWidth(
            net_name=net_name,
            width_mm=hv_width,
            reason="High voltage net requires wider trace",
        )

    # Power nets (GND, VCC, etc.)
    if any(kw in name_upper for kw in ['GND', 'VCC', 'VDD', 'VSS', '+', 'POWER']):
        return TraceWidth(
            net_name=net_name,
            width_mm=power_width,
            reason="Power net requires wider trace for current capacity",
        )

    # Gate drive signals (medium current)
    if any(kw in name_upper for kw in ['GATE', 'DRIVE']):
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
