"""Aligned constraint handler — pairwise axis alignment within tolerance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import AlignedConstraint
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_aligned(
    constraint: AlignedConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Align components pairwise along an axis within tolerance."""
    labels: list[AssumptionLiteral] = []
    tol_u = model.mm_to_units(constraint.tolerance_mm)
    axis = constraint.axis.value  # "x" or "y"

    comp_refs = constraint.components
    missing = [ref for ref in comp_refs if ref not in components]
    if missing:
        raise UnresolvedConstraintRefsError(
            f"Aligned constraint {constraint.id!r} references missing component(s): "
            + ", ".join(repr(ref) for ref in missing)
        )
    for i in range(len(comp_refs)):
        for j in range(i + 1, len(comp_refs)):
            va = components.get(comp_refs[i])
            vb = components.get(comp_refs[j])
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
