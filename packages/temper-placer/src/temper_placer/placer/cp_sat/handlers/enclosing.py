"""Enclosing constraint handler — constrain components within a zone rectangle."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from temper_placer.pcl.constraints import EnclosingConstraint
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_enclosing(
    constraint: EnclosingConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Constrain inner components to lie within the outer zone rectangle."""
    labels: list[AssumptionLiteral] = []
    zone = ctx.zones.get(constraint.outer)
    if zone is None:
        raise UnresolvedConstraintRefsError(
            f"Enclosing constraint {constraint.id!r} references missing zone "
            f"{constraint.outer!r}"
        )

    missing = [ref for ref in constraint.inner if ref not in components]
    if missing:
        raise UnresolvedConstraintRefsError(
            f"Enclosing constraint {constraint.id!r} references missing component(s): "
            + ", ".join(repr(ref) for ref in missing)
        )

    zx_min, zy_min, zx_max, zy_max = zone
    zx_min_u = model.mm_to_units(zx_min)
    zy_min_u = model.mm_to_units(zy_min)
    zx_max_u = model.mm_to_units(zx_max)
    zy_max_u = model.mm_to_units(zy_max)
    margin_u = model.mm_to_units(constraint.margin_mm)

    for ref in constraint.inner:
        v = components[ref]
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
        labels.append(cast(AssumptionLiteral, assumption))
    return labels
