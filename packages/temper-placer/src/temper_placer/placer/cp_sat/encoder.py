"""U3: PCL→CP-SAT Constraint Encoder.

Maps PCL constraint objects to CP-SAT model constraints via per-type
handlers, following the existing sat_bridge.py dispatch pattern.

Supported constraint types (v1):
    - SeparatedConstraint  → add_chebyshev_clearance
    - EnclosingConstraint  → add_region_membership
    - OnSideConstraint     → add_edge_anchoring
    - AdjacentConstraint   → add_proximity

Deferred (logged as warnings, skipped):
    - AlignedConstraint, LoopAreaConstraint, AnchoredConstraint, KeepoutConstraint
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ortools.sat.python import cp_model

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    BoardSide,
    ConstraintType,
    EnclosingConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)

if TYPE_CHECKING:
    from temper_placer.pcl.parser import ConstraintCollection
    from temper_placer.placer.cp_sat.model import SolveContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zone resolution helpers
# ---------------------------------------------------------------------------


def _resolve_zone_bounds(
    zone_name: str,
    board: Any,
    components: dict,
) -> tuple[float, float, float, float]:
    """Resolve a zone name to (x_min, y_min, x_max, y_max) bounds in mm.

    Tries the Board's zone registry first, then falls back to checking
    whether the zone_name appears in the *components* dict with inline
    bounding-box keys (``x_min``, ``x_max``, ``y_min``, ``y_max``).
    """
    if board is not None:
        try:
            zone = board.get_zone(zone_name)
            return zone.bounds  # (x_min, y_min, x_max, y_max)
        except (KeyError, ValueError, AttributeError):
            pass

    if zone_name in components:
        c = components[zone_name]
        x_min = c.get("x_min")
        x_max = c.get("x_max")
        y_min = c.get("y_min")
        y_max = c.get("y_max")
        if all(v is not None for v in (x_min, x_max, y_min, y_max)):
            return (x_min, y_min, x_max, y_max)

    raise ValueError(
        f"Cannot resolve zone '{zone_name}': not found in board zones "
        f"or components dict"
    )


def _board_side_to_edge(side: BoardSide) -> str:
    """Map a PCL ``BoardSide`` enum to the edge string used by model helpers."""
    mapping = {
        BoardSide.BOTTOM: "bottom",
        BoardSide.TOP: "top",
        BoardSide.LEFT: "left",
        BoardSide.RIGHT: "right",
    }
    if side not in mapping:
        raise ValueError(f"Unknown board side: {side}")
    return mapping[side]


# ---------------------------------------------------------------------------
# Per-type handlers
# ---------------------------------------------------------------------------


def _encode_separated(
    constraint: SeparatedConstraint,
    components: dict,  # noqa: ARG001  (used for signature consistency)
    model: cp_model.CpModel,
    ctx: SolveContext,
    board: Any = None,  # noqa: ARG001
) -> list[cp_model.IntVar]:
    # @req(2026-07-03-001, R2): HV↔LV creepage clearance
    """Encode a ``SeparatedConstraint`` as Chebyshev disjunctive clearance.

    Creates a 4-Boolean disjunctive constraint (left/right/below/above) via
    ``add_chebyshev_clearance``.  Collects one assumption variable for UNSAT
    core extraction (U7).
    """
    assumption = model.NewBoolVar(f"assump_{constraint.id}")
    ctx.assumption_vars.append(assumption)

    # For v1, both sides are resolved as simple component references.
    # Zone-to-component expansion is deferred.
    from temper_placer.placer.cp_sat.model import add_chebyshev_clearance

    add_chebyshev_clearance(
        model,
        ctx,
        pairs=[(constraint.a, constraint.b)],
        clearance_mm=constraint.min_distance_mm,
    )

    return [assumption]


def _encode_enclosing(
    constraint: EnclosingConstraint,
    components: dict,
    model: cp_model.CpModel,
    ctx: SolveContext,
    board: Any = None,
) -> list[cp_model.IntVar]:
    # @req(2026-07-03-001, R5): HV-region membership
    """Encode an ``EnclosingConstraint`` as region-membership bounds.

    Resolves the zone name to bounding-box coordinates and constrains every
    inner component to lie wholly within that rectangle.
    """
    assumption = model.NewBoolVar(f"assump_{constraint.id}")
    ctx.assumption_vars.append(assumption)

    x_min, y_min, x_max, y_max = _resolve_zone_bounds(
        constraint.outer, board, components
    )

    from temper_placer.placer.cp_sat.model import add_region_membership

    add_region_membership(
        model,
        ctx,
        components=constraint.inner,
        region_x_min_mm=x_min,
        region_x_max_mm=x_max,
        region_y_min_mm=y_min,
        region_y_max_mm=y_max,
        margin_mm=constraint.margin_mm,
    )

    return [assumption]


def _encode_on_side(
    constraint: OnSideConstraint,
    components: dict,  # noqa: ARG001
    model: cp_model.CpModel,
    ctx: SolveContext,
    board: Any = None,  # noqa: ARG001
) -> list[cp_model.IntVar]:
    # @req(2026-07-03-001, R3): Thermal-edge anchoring
    """Encode an ``OnSideConstraint`` as an edge-anchoring linear inequality.

    Constrains all listed components to within ``max_distance_mm`` of the
    specified board edge.
    """
    assumption = model.NewBoolVar(f"assump_{constraint.id}")
    ctx.assumption_vars.append(assumption)

    edge = _board_side_to_edge(constraint.side)

    from temper_placer.placer.cp_sat.model import add_edge_anchoring

    add_edge_anchoring(
        model,
        ctx,
        components=constraint.components,
        max_dist_mm=constraint.max_distance_mm,
        edge=edge,
    )

    return [assumption]


def _encode_adjacent(
    constraint: AdjacentConstraint,
    components: dict,  # noqa: ARG001
    model: cp_model.CpModel,
    ctx: SolveContext,
    board: Any = None,  # noqa: ARG001
) -> list[cp_model.IntVar]:
    # @req(2026-07-03-001, R4): Commutation-loop adjacency
    """Encode an ``AdjacentConstraint`` as a hard linear proximity constraint.

    Creates four linear inequalities (two per axis) to enforce that the
    Chebyshev bounding-box span between the two components is within
    ``max_distance_mm``.
    """
    assumption = model.NewBoolVar(f"assump_{constraint.id}")
    ctx.assumption_vars.append(assumption)

    from temper_placer.placer.cp_sat.model import add_proximity

    add_proximity(
        model,
        ctx,
        pairs=[(constraint.a, constraint.b, constraint.max_distance_mm)],
    )

    return [assumption]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.SEPARATED: _encode_separated,
    ConstraintType.ENCLOSING: _encode_enclosing,
    ConstraintType.ON_SIDE: _encode_on_side,
    ConstraintType.ADJACENT: _encode_adjacent,
}

UNSUPPORTED_TYPES: frozenset[ConstraintType] = frozenset({
    ConstraintType.ALIGNED,
    ConstraintType.LOOP_AREA,
    ConstraintType.ANCHORED,
    ConstraintType.KEEPOUT,
})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compile_pcl_to_cp_sat(
    constraints: ConstraintCollection,
    components: dict,
    model: cp_model.CpModel,
    ctx: SolveContext,
    netlist: Any = None,
    board: Any = None,
) -> SolveContext:
    """Iterate a ``ConstraintCollection`` and dispatch each constraint.

    For each constraint in the collection the encoder looks up the
    registered handler in ``TYPE_HANDLERS`` by constraint type.  Supported
    types compile to CP-SAT model constraints; unsupported types
    (ALIGNED, LOOP_AREA, ANCHORED, KEEPOUT) log a warning and are skipped.

    Each handler creates an assumption Boolean variable, appends it to the
    model, and records it in ``ctx.assumption_vars`` for use by U7 UNSAT
    core extraction.

    Args:
        constraints: PCL ``ConstraintCollection`` (or any iterable with a
            ``.constraints`` attribute).
        components: Dict mapping component refs to ``{width_mm, height_mm}``.
        model: The CP-SAT model (from ``build_cp_sat_model``).
        ctx: ``SolveContext`` from ``build_cp_sat_model``.
        netlist: Optional ``Netlist`` for component-reference resolution.
        board: Optional ``Board`` for zone-lookup resolution.

    Returns:
        The same ``SolveContext`` (with ``assumption_vars`` populated).
    """
    # Accept both ConstraintCollection and bare iterables.
    constraint_list = (
        constraints.constraints
        if hasattr(constraints, "constraints")
        else list(constraints)
    )

    for constraint in constraint_list:
        handler = TYPE_HANDLERS.get(constraint.constraint_type)

        if handler is None:
            if constraint.constraint_type in UNSUPPORTED_TYPES:
                logger.warning(
                    "PCL constraint type '%s' is not supported by CP-SAT v1 "
                    "encoder (constraint id='%s'), skipping. Because: %s",
                    constraint.constraint_type.label,
                    constraint.id,
                    constraint.because,
                )
            else:
                logger.warning(
                    "No CP-SAT handler registered for constraint type '%s' "
                    "(constraint id='%s'), skipping.",
                    constraint.constraint_type.label,
                    constraint.id,
                )
            continue

        try:
            handler(constraint, components, model, ctx, board=board)
        except Exception:
            logger.exception(
                "Failed to encode constraint '%s' (type=%s), skipping. "
                "Because: %s",
                constraint.id,
                constraint.constraint_type.label,
                constraint.because,
            )

    return ctx
