"""LoopArea constraint handler — hard ceiling on AABB area of loop components."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import LoopAreaConstraint
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_loop_area(
    constraint: LoopAreaConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Hard ceiling: AABB area of loop components <= max_area_mm2.

    Uses cp_model.AddMultiplicationEquality for width*height <= max_area.

    **Soundness proof (R24 item 1) — conservative bound.** The encoding
    bounds the AABB (axis-aligned bounding box) area of the union of the
    loop's component boxes: ``loop_w = loop_x_max - loop_x_min`` and
    ``loop_h = loop_y_max - loop_y_min`` over every loop component, then
    ``area = loop_w * loop_h <= max_area_units`` via
    ``AddMultiplicationEquality`` plus a linear bound.  CP-SAT's
    multiplication equality is exact for bounded integer variables, so

        SAT of the encoding  =>  area(AABB) <= max_area_units

    where ``max_area_units = mm_to_units(max_area_mm2) * units_per_mm`` —
    dimensionally ``mm^2 * (units/mm)^2``, the same unit square the AABB
    area (``loop_w``, ``loop_h`` in units) is expressed in.  ``mm_to_units``
    even-rounds to the nearest integer unit, so the effective ceiling differs
    from the nominal ``max_area_mm2`` by at most one unit in the mm^2
    conversion (0.01 mm^2 at the default 100 units/mm) — a stated rounding
    quantum, not a silent approximation.

    Classification: ``conservative-bound``.  The AABB is an upper envelope of
    the loop components' boxes, and the post-solve audit
    (``audit.py::PlacementAuditor._check_loop_area``) recomputes exactly this
    AABB area from resolved coordinates and hard-fails if it exceeds the
    ceiling — the encoder's promise is re-derived from coordinates, not
    trusted.  What the encoding does NOT promise: the current-loop polygon
    measured by the physics gate (``ViolationType.LOOP_INDUCTANCE``) is a
    separate loop-model quantity — trace segments can wander outside the
    component AABBs, so the encoding controls the component-envelope area.
    The feedback path (``delta_mapper.py``) derives ``max_area_mm2`` from the
    *measured* loop inductance, so the bound is physics-derived while the
    envelope-to-measured-loop relationship is a stated loop-model limitation,
    not a silent assumption.

    **Physics-gated surface (KTD4):** ``physics_gated: true`` — the encoded
    ``max_area_mm2`` bound is derived from measured loop inductance
    (``delta_mapper.py`` LOOP_INDUCTANCE branch). See the register entry in
    ``power_pcb_dataset/physics_soundness_register.yaml``.
    """
    labels: list[AssumptionLiteral] = []
    loop_comps = ctx.loop_components.get(constraint.loop_name, [])
    if not loop_comps:
        if ctx.unresolved_ref_policy == "warn":
            return labels
        raise UnresolvedConstraintRefsError(
            f"LoopArea constraint {constraint.id!r} references missing or empty loop "
            f"{constraint.loop_name!r}"
        )

    missing = [ref for ref in loop_comps if ref not in components]
    if missing:
        if ctx.unresolved_ref_policy == "warn":
            return labels
        raise UnresolvedConstraintRefsError(
            f"LoopArea constraint {constraint.id!r} references missing component(s): "
            + ", ".join(repr(ref) for ref in missing)
        )

    comp_vars = [components[r] for r in loop_comps]

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
        0,
        max_dim * max_dim,
        f"loop_area_{constraint.id}",
    )
    model.add_multiplication_equality(area, loop_w, loop_h)
    max_area_units = model.mm_to_units(constraint.max_area_mm2) * model.units_per_mm
    model.add_constraint_enforced(area <= max_area_units, assumption)
    labels.append(assumption)
    return labels
