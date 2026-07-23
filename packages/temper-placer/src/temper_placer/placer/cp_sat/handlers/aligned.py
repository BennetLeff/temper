"""Aligned constraint handler — pairwise axis alignment within tolerance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import AlignedConstraint, ConstraintType
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.ALIGNED)
def encode_aligned(
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
