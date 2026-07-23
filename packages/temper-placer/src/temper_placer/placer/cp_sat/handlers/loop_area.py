"""LoopArea constraint handler — hard ceiling on AABB area of loop components."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType, LoopAreaConstraint
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.LOOP_AREA)
def encode_loop_area(
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
        logger.warning(
            "LoopArea %s: no components in loop '%s'", constraint.id, constraint.loop_name
        )
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
        0,
        max_dim * max_dim,
        f"loop_area_{constraint.id}",
    )
    model.add_multiplication_equality(area, loop_w, loop_h)
    max_area_units = model.mm_to_units(constraint.max_area_mm2) * model.units_per_mm
    model.add_constraint_enforced(area <= max_area_units, assumption)
    labels.append(assumption)
    return labels
