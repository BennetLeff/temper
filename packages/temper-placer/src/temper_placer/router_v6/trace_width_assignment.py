"""
Router V6 Stage 4.4: Assign Trace Widths

Assigns trace widths based on net class and current requirements.
Part of temper-eixu (Stage 4 - Geometric Realization)

Wave 4 migration note: the per-net classification (``_kw_boundary_match`` /
``_determine_trace_width``) now delegates to ``temper_geometry``'s
``trace_width_assignment`` kernels
(``packages/temper-geometry/src/trace_width_assignment.rs``); the
``PathfindingResult``-driven orchestration (``assign_trace_widths``) and the
``TraceWidth``/``TraceWidthAssignment`` dataclasses stay here.  See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

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
    return _tg.kw_boundary_match_py(upper, list(keywords))


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
    width_mm, reason = _tg.determine_trace_width_py(
        net_name, default_width, power_width, hv_width
    )
    return TraceWidth(
        net_name=net_name,
        width_mm=width_mm,
        reason=reason,
    )
