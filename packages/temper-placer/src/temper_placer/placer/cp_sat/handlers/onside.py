"""OnSide constraint handler — pin components to a board edge."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType, OnSideConstraint
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.ON_SIDE)
def encode_onside(
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
