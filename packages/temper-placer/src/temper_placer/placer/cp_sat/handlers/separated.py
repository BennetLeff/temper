"""Separated constraint handler — pairwise Chebyshev clearance encoding."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral
from temper_placer.placer.cp_sat.handlers._registry import register_handler
from temper_placer.placer.cp_sat.handlers._shared import resolve_refs

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

logger = logging.getLogger(__name__)


@register_handler(ConstraintType.SEPARATED)
def encode_separated(
    constraint: SeparatedConstraint,
    components: dict[str, ComponentVars],
    model: CpSatModel,
    ctx: EncoderContext,
) -> list[AssumptionLiteral]:
    """Enforce Chebyshev clearance between every component in group A and B.

    Each pair (a, b) gets a pairwise Chebyshev disjunction — exactly the
    margin required on **either** the x-axis **or** the y-axis — using 6
    Boolean auxiliary variables per pair.  This is strictly stronger than
    the previous ``AddNoOverlap2D`` with one-sided interval inflation,
    which allowed components to touch on one axis while being disjoint
    on the other and consequently under-delivered the stated clearance.

    Encoding for a single pair (bounding boxes in model units):

        margin = mm_to_units(min_distance_mm)

        left   ⇔  a.x_end + margin ≤ b.x_start
        right  ⇔  b.x_end + margin ≤ a.x_start
        below  ⇔  a.y_end + margin ≤ b.y_start
        above  ⇔  b.y_end + margin ≤ a.y_start

        x_ok   ⇔  left ∨ right         (BoolVar, not reified — via BoolOr)
        y_ok   ⇔  below ∨ above

        AddBoolOr([x_ok, y_ok])         # at least one axis has the gap

    Soundness: SAT ⇒ Chebyshev(L∞) gap ≥ margin (by case analysis over
    which of left/right/below/above holds).  Induction: base n≤1 vacuously
    true; step adds constraints for (i, k+1) that are linear on existing
    variables — previous constraints are unaffected.
    """
    labels: list[AssumptionLiteral] = []
    margin = model.mm_to_units(constraint.min_distance_mm)

    refs_a = resolve_refs(constraint.a, components, ctx)
    refs_b = resolve_refs(constraint.b, components, ctx)
    if not refs_a or not refs_b:
        logger.warning("Separated %s: cannot resolve refs", constraint.id)
        return labels

    for ra in refs_a:
        for rb in refs_b:
            if ra == rb:
                continue
            va = components[ra]
            vb = components[rb]
            label = f"sep_{constraint.id}_{ra}_{rb}"

            # ---- direction Booleans (each enforced by a linear bound) ----
            left = model.new_bool_var(f"sep_left_{ra}_{rb}")
            right = model.new_bool_var(f"sep_right_{ra}_{rb}")
            below = model.new_bool_var(f"sep_below_{ra}_{rb}")
            above = model.new_bool_var(f"sep_above_{ra}_{rb}")

            model.model_ref.Add(va.x_end + margin <= vb.x_start).OnlyEnforceIf(left)
            model.model_ref.Add(vb.x_end + margin <= va.x_start).OnlyEnforceIf(right)
            model.model_ref.Add(va.y_end + margin <= vb.y_start).OnlyEnforceIf(below)
            model.model_ref.Add(vb.y_end + margin <= va.y_start).OnlyEnforceIf(above)

            # ---- axis Booleans ----
            x_ok = model.new_bool_var(f"sep_x_ok_{ra}_{rb}")
            y_ok = model.new_bool_var(f"sep_y_ok_{ra}_{rb}")

            model.model_ref.AddBoolOr([x_ok.Not(), left, right])
            model.model_ref.AddBoolOr([y_ok.Not(), below, above])

            # ---- final disjunction — at least one axis separated ----
            model.model_ref.AddBoolOr([x_ok, y_ok])

            labels.append(model.new_assumption(label))
    return labels
