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

Bug history (2026-08-13, ``docs/evidence/2026-08-13-router-netclass-trace-widths.md``):
this stage used to pick every emitted width from the three hardcoded keyword
buckets below (``default_width``/``power_width``/``hv_width``), with **no**
reference to ``TEMPER_NET_CLASSES`` / ``design_rules.get_rules_for_net`` --
the project's actual, authoritative per-netclass ``trace_width`` table, the
same table ``scripts/generate_kicad_dru.py`` compiles into the enforced
``track_width`` DRC rules and the same table ``via_placement.py`` (Stage 4.3,
the call immediately above this one) already consults for via sizing.  The
two tables disagreed by 4-12x: 490 true ``track_width`` violations
(``scripts/measure_uncapped_drc.py``; kicad-cli reports a capped 199) across
10 nets, at 8.3%-50.8% of their required minimum.  Two of those nets --
``w1_2`` and ``power_in.ntc-no``, the K1 bypass-relay contact pair -- carry
100% of the appliance's AC mains input current (15A design / 16A fuse / 20A
relay contact) and were being emitted at 0.25mm, an IPC-2221B ampacity of
~2-2.7A against a 15A requirement.

The fix: ``assign_trace_widths`` now takes ``design_rules`` and reads
``get_rules_for_net(net).trace_width`` -- the SSOT -- for every net that has a
real class.  The keyword cascade survives only as the no-class fallback, and
**every** fallback firing is logged at WARNING with the net name.  A silent
fallback is exactly how the original defect survived three prior audits of
this same "net-name keyword classifier drifts from the SSOT" defect class
(``creepage_check.py``, ``clearance_check.py``, ``clearance_engine.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import temper_geometry as _tg

from temper_placer.router_v6.astar_pathfinding import PathfindingResult

logger = logging.getLogger(__name__)

# ``DesignRules.get_rules_for_net`` never returns ``None``: its last tier is a
# synthesized catch-all ``NetClassRules(name="Default", ...)`` built from the
# board's ``default_trace_width`` (``packages/temper-design-bundle/src/
# design_rules.rs::default_net_class_rules``).  "This net has no class" is
# therefore spelled as "the resolved class is the catch-all", not as a null
# check -- the distinction the pre-fix code had no way to make at all.
_CATCH_ALL_CLASS_NAME = "Default"


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


def _netclass_trace_width(design_rules: Any, net_name: str) -> TraceWidth | None:
    """The SSOT width for *net_name*, or ``None`` if it has no real class.

    Returns ``None`` (so the caller falls back, loudly) in exactly three
    cases: no ``design_rules`` was threaded in, the net resolves only to the
    synthesized ``Default`` catch-all, or the resolved class carries a
    non-positive width.  Any *other* failure is re-raised rather than
    swallowed -- a broad ``except`` here would recreate the silent-fallback
    shape this function exists to remove.
    """
    if design_rules is None:
        return None
    get_rules = getattr(design_rules, "get_rules_for_net", None)
    if get_rules is None:
        return None

    rules = get_rules(net_name)
    if rules is None:
        return None
    class_name = getattr(rules, "name", None)
    if class_name is None or class_name == _CATCH_ALL_CLASS_NAME:
        return None

    width_mm = getattr(rules, "trace_width", None)
    if width_mm is None:
        width_mm = getattr(rules, "trace_width_mm", None)
    if width_mm is None or float(width_mm) <= 0.0:
        return None

    return TraceWidth(
        net_name=net_name,
        width_mm=float(width_mm),
        reason=f"netclass {class_name} trace_width",
    )


def assign_trace_widths(
    pathfinding_result: PathfindingResult,
    default_width: float = 0.127,  # 5mil standard
    power_width: float = 0.508,  # 20mil for power
    hv_width: float = 0.635,  # 25mil for HV
    design_rules: Any = None,
) -> TraceWidthAssignment:
    """
    Assign trace widths from the netclass table, falling back to keywords.

    ``design_rules.get_rules_for_net(net).trace_width`` is the single source
    of truth and is used whenever the net resolves to a real class.  The
    three keyword buckets are a fallback for classless nets ONLY, and each
    use is logged at WARNING (see the module docstring's bug history).

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        default_width: Fallback default trace width (mm), classless nets only
        power_width: Fallback width for power nets (mm), classless nets only
        hv_width: Fallback width for high-voltage nets (mm), classless only
        design_rules: Board ``DesignRules``; when omitted, EVERY net takes
            the keyword fallback and a single aggregate WARNING is emitted.

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
    fallback_nets: list[str] = []
    for net_name in routed_net_names:
        width = _netclass_trace_width(design_rules, net_name)
        if width is None:
            # No real netclass for this net -- keyword cascade, logged.
            fallback_nets.append(net_name)
            width = _determine_trace_width(
                net_name,
                default_width,
                power_width,
                hv_width,
            )

        assignments[net_name] = width

    if fallback_nets:
        if design_rules is None:
            logger.warning(
                "trace-width: no design_rules threaded into Stage 4.4 -- all "
                "%d routed net(s) fell back to the keyword buckets "
                "(default=%.4gmm power=%.4gmm hv=%.4gmm) instead of the "
                "netclass trace_width table. This is the shape of the defect "
                "in docs/evidence/2026-08-13-router-netclass-trace-widths.md.",
                len(fallback_nets),
                default_width,
                power_width,
                hv_width,
            )
        else:
            logger.warning(
                "trace-width: %d of %d routed net(s) have no netclass "
                "assignment and fell back to the keyword buckets: %s",
                len(fallback_nets),
                len(routed_net_names),
                ", ".join(sorted(fallback_nets)),
            )

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
