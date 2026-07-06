"""PCL-to-CP-SAT constraint encoder.

Maps all 8 PCL constraint types to CP-SAT model constraints using a
TYPE_HANDLERS dispatch pattern mirroring sat_bridge.py.

Each handler returns a list of assumption literals for UNSAT-core extraction.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)

from .model import ComponentVars, CpSatModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

UNSUPPORTED_TYPES: set[ConstraintType] = set()


# ---------------------------------------------------------------------------
# Encoder context
# ---------------------------------------------------------------------------

class EncoderContext:
    """Context passed to each handler during encoding.

    Carries board dimensions, region definitions, and loop data needed
    by specific handlers.
    """

    def __init__(
        self,
        board_w_mm: float,
        board_h_mm: float,
        zones: dict[str, tuple[float, float, float, float]] | None = None,
        loop_components: dict[str, list[str]] | None = None,
        zone_components: dict[str, list[str]] | None = None,
        board_x_min_units: int = 0,
        board_y_min_units: int = 0,
        board_x_max_units: int = 0,
        board_y_max_units: int = 0,
    ) -> None:
        self.board_w_mm = board_w_mm
        self.board_h_mm = board_h_mm
        self.zones = zones or {}
        self.loop_components = loop_components or {}
        self.zone_components = zone_components or {}
        self.board_x_min_units = board_x_min_units
        self.board_y_min_units = board_y_min_units
        self.board_x_max_units = board_x_max_units
        self.board_y_max_units = board_y_max_units


# ---------------------------------------------------------------------------
# SEEN: Assumption literal type alias
# ---------------------------------------------------------------------------

AssumptionLiteral = int  # index of assumption BoolVar


# ---------------------------------------------------------------------------
# Separated
# ---------------------------------------------------------------------------

def _encode_separated(
    constraint: SeparatedConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Enforce chebyshev clearance between every component in group A and B.

    Each pair (a, b) gets a dedicated NoOverlap2D constraint with intervals
    inflated by ``min_distance_mm / 2`` on each side.
    """
    labels: list[AssumptionLiteral] = []
    margin = model.mm_to_units(constraint.min_distance_mm)

    refs_a = _resolve_refs(constraint.a, components, ctx)
    refs_b = _resolve_refs(constraint.b, components, ctx)
    if not refs_a or not refs_b:
        logger.warning("Separated %s: cannot resolve refs", constraint.id)
        return labels

    for ra in refs_a:
        for rb in refs_b:
            if ra == rb:
                continue
            va = components[ra]
            vb = components[rb]
            label = f"sep_{constraint.id}_{ra}_{rb}"

            # Expand a's interval by full margin on each side;
            # NoOverlap2D with unexpanded b enforces edge-to-edge gap >= margin.
            # Widen domains to accommodate the expansion (may go negative or exceed board).
            pad = margin + ctx.board_x_max_units
            x_start_a = model.new_int_var(-pad, ctx.board_x_max_units + pad, f"sep_xs_{ra}_{rb}")
            x_end_a = model.new_int_var(-pad, ctx.board_x_max_units + pad, f"sep_xe_{ra}_{rb}")
            y_start_a = model.new_int_var(-pad, ctx.board_y_max_units + pad, f"sep_ys_{ra}_{rb}")
            y_end_a = model.new_int_var(-pad, ctx.board_y_max_units + pad, f"sep_ye_{ra}_{rb}")
            x_size_a = model.new_int_var(0, ctx.board_x_max_units + 2 * pad, f"sep_xsz_{ra}_{rb}")
            y_size_a = model.new_int_var(0, ctx.board_y_max_units + 2 * pad, f"sep_ysz_{ra}_{rb}")

            model.add(x_start_a == va.x_start - margin)
            model.add(x_end_a == va.x_end + margin)
            model.add(y_start_a == va.y_start - margin)
            model.add(y_end_a == va.y_end + margin)
            model.add(x_start_a + x_size_a == x_end_a)
            model.add(y_start_a + y_size_a == y_end_a)

            ix_a = model.model_ref.NewIntervalVar(
                x_start_a, x_size_a, x_end_a, f"six_{ra}_{rb}"
            )
            iy_a = model.model_ref.NewIntervalVar(
                y_start_a, y_size_a, y_end_a, f"siy_{ra}_{rb}"
            )
            ix_b = model.model_ref.NewIntervalVar(
                vb.x_start, vb.x_size, vb.x_end, f"six_{rb}_{ra}"
            )
            iy_b = model.model_ref.NewIntervalVar(
                vb.y_start, vb.y_size, vb.y_end, f"siy_{rb}_{ra}"
            )

            model.model_ref.AddNoOverlap2D([ix_a, ix_b], [iy_a, iy_b])
            labels.append(model.new_assumption(label))
    return labels


# ---------------------------------------------------------------------------
# Enclosing
# ---------------------------------------------------------------------------

def _encode_enclosing(
    constraint: EnclosingConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Constrain inner components to lie within the outer zone rectangle."""
    labels: list[AssumptionLiteral] = []
    zone = ctx.zones.get(constraint.outer)
    if zone is None:
        logger.warning("Enclosing %s: zone '%s' not found", constraint.id, constraint.outer)
        return labels

    zx_min, zy_min, zx_max, zy_max = zone
    zx_min_u = model.mm_to_units(zx_min)
    zy_min_u = model.mm_to_units(zy_min)
    zx_max_u = model.mm_to_units(zx_max)
    zy_max_u = model.mm_to_units(zy_max)
    margin_u = model.mm_to_units(constraint.margin_mm)

    for ref in constraint.inner:
        v = components.get(ref)
        if v is None:
            logger.warning("Enclosing %s: comp '%s' not found", constraint.id, ref)
            continue
        label = f"enc_{constraint.id}_{ref}"
        assumption = model.new_assumption(label)

        model.add_constraint_enforced(
            v.x_start >= zx_min_u + margin_u, assumption,
        )
        model.add_constraint_enforced(
            v.y_start >= zy_min_u + margin_u, assumption,
        )
        model.add_constraint_enforced(
            v.x_end <= zx_max_u - margin_u, assumption,
        )
        model.add_constraint_enforced(
            v.y_end <= zy_max_u - margin_u, assumption,
        )
        labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# Adjacent
# ---------------------------------------------------------------------------

def _encode_adjacent(
    constraint: AdjacentConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Constrain two components to be within max_distance_mm of each other.

    Uses chebyshev distance: both |cx_a - cx_b| <= max_distance and same for y.
    """
    labels: list[AssumptionLiteral] = []
    va = components.get(constraint.a)
    vb = components.get(constraint.b)
    if va is None or vb is None:
        logger.warning("Adjacent %s: cannot resolve components", constraint.id)
        return labels

    max_d = model.mm_to_units(constraint.max_distance_mm)
    label = f"adj_{constraint.id}"
    assumption = model.new_assumption(label)

    model.add_constraint_enforced(va.x_center - vb.x_center <= max_d, assumption)
    model.add_constraint_enforced(vb.x_center - va.x_center <= max_d, assumption)
    model.add_constraint_enforced(va.y_center - vb.y_center <= max_d, assumption)
    model.add_constraint_enforced(vb.y_center - va.y_center <= max_d, assumption)
    labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# OnSide
# ---------------------------------------------------------------------------

def _encode_on_side(
    constraint: OnSideConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Pin components to a board edge."""
    labels: list[AssumptionLiteral] = []
    max_d_u = model.mm_to_units(constraint.max_distance_mm)
    side = constraint.side.value  # "left", "right", "top", "bottom"

    for ref in constraint.components:
        v = components.get(ref)
        if v is None:
            logger.warning("OnSide %s: comp '%s' not found", constraint.id, ref)
            continue
        label = f"oside_{constraint.id}_{ref}"
        assumption = model.new_assumption(label)

        if side == "left":
            model.add_constraint_enforced(v.x_start <= ctx.board_x_min_units + max_d_u, assumption)
        elif side == "right":
            model.add_constraint_enforced(v.x_end >= ctx.board_x_max_units - max_d_u, assumption)
        elif side == "top":
            model.add_constraint_enforced(v.y_end >= ctx.board_y_max_units - max_d_u, assumption)
        elif side == "bottom":
            model.add_constraint_enforced(v.y_start <= ctx.board_y_min_units + max_d_u, assumption)
        labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# Anchored (U4)
# ---------------------------------------------------------------------------

def _encode_anchored(
    constraint: AnchoredConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Fix a component to an exact position or region."""
    labels: list[AssumptionLiteral] = []
    v = components.get(constraint.component)
    if v is None:
        logger.warning("Anchored %s: comp '%s' not found", constraint.id, constraint.component)
        return labels

    label = f"anchor_{constraint.id}"
    assumption = model.new_assumption(label)

    if constraint.position is not None:
        px_u = model.mm_to_units(constraint.position[0])
        py_u = model.mm_to_units(constraint.position[1])
        model.add_constraint_enforced(v.x_center == px_u, assumption)
        model.add_constraint_enforced(v.y_center == py_u, assumption)
    elif constraint.region is not None:
        rx_min, ry_min, rx_max, ry_max = constraint.region
        rx_min_u = model.mm_to_units(rx_min)
        ry_min_u = model.mm_to_units(ry_min)
        rx_max_u = model.mm_to_units(rx_max)
        ry_max_u = model.mm_to_units(ry_max)
        model.add_constraint_enforced(v.x_start >= rx_min_u, assumption)
        model.add_constraint_enforced(v.y_start >= ry_min_u, assumption)
        model.add_constraint_enforced(v.x_end <= rx_max_u, assumption)
        model.add_constraint_enforced(v.y_end <= ry_max_u, assumption)
    labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# KEEPOUT (U4)
# ---------------------------------------------------------------------------

def _encode_keepout(
    constraint: KeepoutConstraint,
    components: dict[str, ComponentVars],  # noqa: ARG001
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Add a keepout zone interval to the global NoOverlap2D.

    All components must not overlap the keepout rectangle.
    Uses the model's add_keepout_interval + add_no_overlap_2d with extra intervals.
    """
    labels: list[AssumptionLiteral] = []
    zone = ctx.zones.get(constraint.zone_name)
    if zone is None:
        logger.warning("KEEPOUT %s: zone '%s' not found", constraint.id, constraint.zone_name)
        return labels

    zx_min, zy_min, zx_max, zy_max = zone
    margin_u = model.mm_to_units(constraint.margin_mm)
    kx_s = model.mm_to_units(zx_min) - margin_u
    ky_s = model.mm_to_units(zy_min) - margin_u
    kx_w = model.mm_to_units(zx_max - zx_min) + 2 * margin_u
    ky_h = model.mm_to_units(zy_max - zy_min) + 2 * margin_u

    ix, iy = model.add_keepout_interval(
        f"keepout_{constraint.id}", kx_s, ky_s, kx_w, ky_h,
    )
    label = f"keepout_{constraint.id}"
    assumption = model.new_assumption(label)
    model.model_ref.AddNoOverlap2D(
        [*[model.model_ref.NewIntervalVar(
            v.x_start, v.x_size, v.x_end, f"kx_comp_{v.ref}"
        ) for v in model.components],
         ix],
        [*[model.model_ref.NewIntervalVar(
            v.y_start, v.y_size, v.y_end, f"ky_comp_{v.ref}"
        ) for v in model.components],
         iy],
    )
    labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# ALIGNED (U4)
# ---------------------------------------------------------------------------

def _encode_aligned(
    constraint: AlignedConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Align components pairwise along an axis within tolerance."""
    labels: list[AssumptionLiteral] = []
    tol_u = model.mm_to_units(constraint.tolerance_mm)
    axis = constraint.axis.value  # "x" or "y"

    comp_refs = constraint.components
    for i in range(len(comp_refs)):
        for j in range(i + 1, len(comp_refs)):
            va = components.get(comp_refs[i])
            vb = components.get(comp_refs[j])
            if va is None or vb is None:
                continue
            label = f"align_{constraint.id}_{comp_refs[i]}_{comp_refs[j]}"
            assumption = model.new_assumption(label)

            if axis in ("x", "major"):
                cva, cvb = va.x_center, vb.x_center
            else:
                cva, cvb = va.y_center, vb.y_center

            model.add_constraint_enforced(cva - cvb <= tol_u, assumption)
            model.add_constraint_enforced(cvb - cva <= tol_u, assumption)
            labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# LOOP_AREA (U3)
# ---------------------------------------------------------------------------

def _encode_loop_area(
    constraint: LoopAreaConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Hard ceiling: AABB area of loop components <= max_area_mm2.

    Uses cp_model.AddMultiplicationEquality for width*height <= max_area.
    """
    labels: list[AssumptionLiteral] = []
    loop_comps = ctx.loop_components.get(constraint.loop_name, [])
    if not loop_comps:
        logger.warning("LoopArea %s: no components in loop '%s'", constraint.id, constraint.loop_name)
        return labels

    comp_vars = [components[r] for r in loop_comps if r in components]
    if not comp_vars:
        logger.warning("LoopArea %s: no resolved components", constraint.id)
        return labels

    label = f"loop_area_{constraint.id}"
    assumption = model.new_assumption(label)

    max_dim = max(ctx.board_x_max_units, ctx.board_y_max_units)
    loop_x_min = model.new_int_var(0, max_dim, f"loop_xmin_{constraint.id}")
    loop_x_max = model.new_int_var(0, max_dim, f"loop_xmax_{constraint.id}")
    loop_y_min = model.new_int_var(0, max_dim, f"loop_ymin_{constraint.id}")
    loop_y_max = model.new_int_var(0, max_dim, f"loop_ymax_{constraint.id}")

    # AABB: loop_{min} <= comp_start and loop_{max} >= comp_end for all comps
    for v in comp_vars:
        model.add(loop_x_min <= v.x_start)
        model.add(loop_y_min <= v.y_start)
        model.add(loop_x_max >= v.x_end)
        model.add(loop_y_max >= v.y_end)

    loop_w = model.new_int_var(0, max_dim, f"loop_w_{constraint.id}")
    loop_h = model.new_int_var(0, max_dim, f"loop_h_{constraint.id}")
    model.add(loop_w == loop_x_max - loop_x_min)
    model.add(loop_h == loop_y_max - loop_y_min)

    area = model.new_int_var(
        0, max_dim * max_dim, f"loop_area_{constraint.id}",
    )
    model.add_multiplication_equality(area, loop_w, loop_h)
    max_area_units = model.mm_to_units(constraint.max_area_mm2) * model.units_per_mm
    model.add_constraint_enforced(area <= max_area_units, assumption)
    labels.append(assumption)
    return labels


# ---------------------------------------------------------------------------
# Stub handlers (for types not yet implemented in CP-SAT)
# ---------------------------------------------------------------------------

def _encode_stub(
    constraint_type_name: str,
    constraint: BaseConstraint,
    _components: dict[str, ComponentVars],
    _model: CpSatModel,
    _ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Log a warning and return no assumptions."""
    logger.warning(
        "CP-SAT handler for %s (%s) is a stub — no constraints added.",
        constraint_type_name,
        constraint.id,
    )
    return []


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.SEPARATED: _encode_separated,
    ConstraintType.ENCLOSING: _encode_enclosing,
    ConstraintType.ADJACENT: _encode_adjacent,
    ConstraintType.ON_SIDE: _encode_on_side,
    ConstraintType.ANCHORED: _encode_anchored,
    ConstraintType.KEEPOUT: _encode_keepout,
    ConstraintType.ALIGNED: _encode_aligned,
    ConstraintType.LOOP_AREA: _encode_loop_area,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def encode_constraints(
    constraints: list[BaseConstraint],
    model: CpSatModel,
    ctx: EncoderContext | None = None,
) -> list[AssumptionLiteral]:
    """Encode all constraints into the CP-SAT model.

    Returns a flat list of assumption literal indices for downstream
    UNSAT-core inspection.
    """
    components = model.component_map
    if ctx is None:
        ctx = EncoderContext(
            board_w_mm=100.0,
            board_h_mm=100.0,
            board_x_max_units=10_000,
            board_y_max_units=10_000,
        )

    all_assumptions: list[AssumptionLiteral] = []
    for c in constraints:
        handler = TYPE_HANDLERS.get(c.constraint_type)
        if handler is None:
            UNSUPPORTED_TYPES.add(c.constraint_type)
            logger.warning(
                "No CP-SAT handler for constraint type %s (%s)",
                c.constraint_type,
                c.id,
            )
            continue
        assumptions = handler(c, components, model, ctx)
        all_assumptions.extend(assumptions)

    return all_assumptions


def _resolve_refs(
    name: str,
    components: dict[str, ComponentVars],
    ctx: EncoderContext,
) -> list[str]:
    """Resolve a ref or zone name to list of component refs."""
    if name in components:
        return [name]
    if name in ctx.zones and name in ctx.zone_components:
        return [r for r in ctx.zone_components[name] if r in components]
    return []
