"""Keepout constraint handler — add keepout zone to global NoOverlap2D."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType, KeepoutConstraint
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.KEEPOUT)
def encode_keepout(
    constraint: KeepoutConstraint,
    components: dict[str, ComponentVars],  # noqa: ARG001
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Add a keepout zone interval to the global NoOverlap2D.

    All components must not overlap the keepout rectangle.
    Uses the model's add_keepout_interval + add_no_overlap_2d with extra intervals.
    """
    labels: list[AssumptionLiteral] = []
    zone = ctx.zones.get(constraint.zone_name)
    if zone is None:
        logger.warning("KEEPOUT %s: zone '%s' not found", constraint.id, constraint.zone_name)
        return labels

    zx_min, zy_min, zx_max, zy_max = zone
    margin_u = model.mm_to_units(constraint.margin_mm)
    kx_s = model.mm_to_units(zx_min) - margin_u
    ky_s = model.mm_to_units(zy_min) - margin_u
    kx_w = model.mm_to_units(zx_max - zx_min) + 2 * margin_u
    ky_h = model.mm_to_units(zy_max - zy_min) + 2 * margin_u

    ix, iy = model.add_keepout_interval(
        f"keepout_{constraint.id}", kx_s, ky_s, kx_w, ky_h,
    )
    label = f"keepout_{constraint.id}"
    assumption = model.new_assumption(label)
    model.model_ref.AddNoOverlap2D(
        [*[model.model_ref.NewIntervalVar(
            v.x_start, v.x_size, v.x_end, f"kx_comp_{v.ref}"
        ) for v in model.components],
         ix],
        [*[model.model_ref.NewIntervalVar(
            v.y_start, v.y_size, v.y_end, f"ky_comp_{v.ref}"
        ) for v in model.components],
         iy],
    )
    labels.append(assumption)
    return labels
