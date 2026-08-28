"""OnSide constraint handler — pin components to a board edge."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from temper_placer.pcl.constraints import OnSideConstraint
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_onside(
    constraint: OnSideConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Pin components to a board edge."""
    labels: list[AssumptionLiteral] = []
    max_d_u = model.mm_to_units(constraint.max_distance_mm)
    side = constraint.side.value  # "left", "right", "top", "bottom"

    missing = [ref for ref in constraint.components if ref not in components]
    if missing:
        raise UnresolvedConstraintRefsError(
            f"OnSide constraint {constraint.id!r} references missing component(s): "
            + ", ".join(repr(ref) for ref in missing)
        )

    for ref in constraint.components:
        v = components[ref]
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
        labels.append(cast(AssumptionLiteral, assumption))
    return labels
