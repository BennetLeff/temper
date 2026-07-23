"""Anchored constraint handler — fix component to position or region."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import AnchoredConstraint, ConstraintType
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.ANCHORED)
def encode_anchored(
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
