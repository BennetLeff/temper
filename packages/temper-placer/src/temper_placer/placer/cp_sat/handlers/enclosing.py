"""Enclosing constraint handler — constrain components within a zone rectangle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType, EnclosingConstraint
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.ENCLOSING)
def encode_enclosing(
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
            v.x_start >= zx_min_u + margin_u,
            assumption,
        )
        model.add_constraint_enforced(
            v.y_start >= zy_min_u + margin_u,
            assumption,
        )
        model.add_constraint_enforced(
            v.x_end <= zx_max_u - margin_u,
            assumption,
        )
        model.add_constraint_enforced(
            v.y_end <= zy_max_u - margin_u,
            assumption,
        )
        labels.append(assumption)
    return labels
