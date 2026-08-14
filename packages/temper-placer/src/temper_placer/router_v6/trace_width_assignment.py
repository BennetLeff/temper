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

Current-derived width follow-up (2026-08-13, `hb-gnd` under-sizing fix):
``_determine_trace_width`` above is a pure function of the net NAME
(``determine_trace_width_py``) -- structurally incapable of expressing a
current-appropriate width, because current is never part of its input.
``assign_trace_widths`` (this module's orchestration entrypoint, the one
actually called by ``_pipeline_route.py`` Stage 4.4/4.5 for the real
router) now calls ``_determine_trace_width_ipc_aware`` instead, which
widens (never narrows) the keyword-bucket result to the IPC-2221B
current-derived floor for any net in
``temper_geometry``'s ``ipc2221b_current_width::KNOWN_NET_CURRENTS``
registry (currently just ``hb-gnd``; see that module's doc comment for the
full derivation and for why ``hb.gate_hs-vdd``/``hb.gate_ls-vdd`` are
deliberately not registered). ``_determine_trace_width`` itself is left
unchanged so its pinned keyword-only differential test
(``test_determine_trace_width_matches_reference``) keeps testing exactly
what it always tested.
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
        # Determine appropriate width for this net. Current-aware: widens
        # (never narrows) the keyword-bucket result to the net's
        # IPC-2221B current-derived requirement when the current is known
        # -- see this module's docstring and
        # ``ipc2221b_current_width.rs``'s doc comment.
        width = _determine_trace_width_ipc_aware(
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


def _determine_trace_width_ipc_aware(
    net_name: str,
    default_width: float,
    power_width: float,
    hv_width: float,
) -> TraceWidth:
    """Current-aware trace width: the production entrypoint.

    Identical to :func:`_determine_trace_width` for any net whose current
    is not derivable from ``elec/src`` (i.e. not registered in
    ``temper_geometry``'s ``ipc2221b_current_width::KNOWN_NET_CURRENTS``).
    For a registered net (currently just ``hb-gnd``), widens the
    keyword-bucket width to the IPC-2221B floor computed from that net's
    documented worst-case current -- never narrows.

    Args:
        net_name: Net name
        default_width: Default width
        power_width: Power net width
        hv_width: High voltage width

    Returns:
        TraceWidth assignment
    """
    width_mm, reason = _tg.determine_trace_width_ipc_aware_py(
        net_name, default_width, power_width, hv_width
    )
    return TraceWidth(
        net_name=net_name,
        width_mm=width_mm,
        reason=reason,
    )
