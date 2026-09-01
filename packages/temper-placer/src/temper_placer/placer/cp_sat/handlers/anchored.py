"""Anchored constraint handler — fix component to position or region."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import AnchoredConstraint
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_anchored(
    constraint: AnchoredConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Fix a component to an exact position or region."""
    labels: list[AssumptionLiteral] = []
    v = components.get(constraint.component)
    if v is None:
        raise UnresolvedConstraintRefsError(
            f"Anchored constraint {constraint.id!r} references missing component "
            f"{constraint.component!r}"
        )

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
