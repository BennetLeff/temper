"""Adjacent constraint handler — pairwise proximity encoding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import AdjacentConstraint, DistanceMetric
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers._protocol import AssumptionLiteral

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.handlers._model_protocol import (
        ComponentVarsProtocol,
        ModelProtocol,
    )

def encode_adjacent(
    constraint: AdjacentConstraint,
    components: dict[str, ComponentVarsProtocol],
    model: ModelProtocol,
    ctx: EncoderContext,  # noqa: ARG001
) -> list[AssumptionLiteral]:
    """Constrain two components to be within max_distance_mm of each other.

    Honors ``constraint.metric``:

    * ``EDGE_TO_EDGE`` (the default, and what the config's ``metric:
      edge_to_edge`` selects): the *gap between bounding boxes* on each
      axis must be ≤ max_distance. For a part of width w, edge-to-edge
      distance d permits centers up to ``w + d`` apart — center-to-center
      would wrongly demand centers within ``d``, which for a 25 mm part
      and d=10 mm is unsatisfiable against no-overlap. This mismatch made
      the temper power stage falsely infeasible.
    * ``CENTER_TO_CENTER``: centroid Chebyshev distance ≤ max_distance.
    * ``PIN_TO_PIN``: approximated as edge-to-edge (pin geometry is not
      modelled in the placement grid).
    """
    labels: list[AssumptionLiteral] = []
    va = components.get(constraint.a)
    vb = components.get(constraint.b)
    if va is None or vb is None:
        missing = [ref for ref, value in ((constraint.a, va), (constraint.b, vb)) if value is None]
        raise UnresolvedConstraintRefsError(
            f"Adjacent constraint {constraint.id!r} references missing component(s): "
            + ", ".join(repr(ref) for ref in missing)
        )

    max_d = model.mm_to_units(constraint.max_distance_mm)
    label = f"adj_{constraint.id}"
    assumption = model.new_assumption(label)

    metric = getattr(constraint, "metric", DistanceMetric.EDGE_TO_EDGE)
    if metric == DistanceMetric.CENTER_TO_CENTER:
        model.add_constraint_enforced(va.x_center - vb.x_center <= max_d, assumption)
        model.add_constraint_enforced(vb.x_center - va.x_center <= max_d, assumption)
        model.add_constraint_enforced(va.y_center - vb.y_center <= max_d, assumption)
        model.add_constraint_enforced(vb.y_center - va.y_center <= max_d, assumption)
    else:
        model.add_constraint_enforced(va.x_start - vb.x_end <= max_d, assumption)
        model.add_constraint_enforced(vb.x_start - va.x_end <= max_d, assumption)
        model.add_constraint_enforced(va.y_start - vb.y_end <= max_d, assumption)
        model.add_constraint_enforced(vb.y_start - va.y_end <= max_d, assumption)
    labels.append(assumption)
    return labels
