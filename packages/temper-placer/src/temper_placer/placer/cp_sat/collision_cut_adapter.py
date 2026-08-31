"""Project Rust collision cuts into a CP-SAT model.

The collision campaign is deliberately the authority for *why* a cut exists.
This module only validates the Rust view against the already-built model and
posts the one exact assignment forbidden by that view.  In particular, it
does not classify geometry or choose a movement policy for either component.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral
from typing import TYPE_CHECKING, Any

import temper_orchestration as _rust
from ortools.sat.python import cp_model

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel


# ``CollisionCampaign::MODEL_UNITS_PER_MM`` is intentionally not inferred
# from a millimetre value at this boundary.  The Rust cut fields are exact
# integer model coordinates at this scale; accepting another scale would
# silently forbid a different placement.
RUST_MODEL_UNITS_PER_MM = _rust.collision_campaign_model_units_per_mm()


@dataclass(frozen=True)
class _Projection:
    key: tuple[str, str, int, int, int, int, int, int]
    variables: tuple[cp_model.IntVar, ...]
    assignment: tuple[int, int, int, int, int, int]


def _field(cut: object, name: str) -> Any:
    try:
        return getattr(cut, name)
    except AttributeError as exc:
        raise ValueError(f"collision cut is missing {name!r}") from exc


def _ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"collision cut {label} must be a non-empty trimmed string")
    return value


def _integer(value: object, label: str) -> int:
    # bool is an Integral in Python, but is not an exact CP-SAT coordinate.
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"collision cut {label} must be an integer model value")
    return int(value)


def _rotation(value: object, label: str) -> int:
    result = _integer(value, label)
    if result not in range(4):
        raise ValueError(f"collision cut {label} must be a quadrant in [0, 3]")
    return result


def _validate_model_scale(model: CpSatModel) -> None:
    scale = getattr(model, "units_per_mm", None)
    if isinstance(scale, bool) or not isinstance(scale, Integral) or scale <= 0:
        raise ValueError("collision cut model scale is invalid")
    if int(scale) != RUST_MODEL_UNITS_PER_MM:
        raise ValueError(
            "collision cut model scale does not match Rust model-coordinate scale "
            f"({scale} != {RUST_MODEL_UNITS_PER_MM})"
        )


def _validate_variable(model: CpSatModel, variable: object, label: str) -> cp_model.IntVar:
    if not isinstance(variable, cp_model.IntVar):
        raise ValueError(f"collision cut {label} is not an integer model variable")

    # Indexes are local to a CpModel, so checking only Index() would accept a
    # variable borrowed from another model when its index happens to exist in
    # this model too.  OR-Tools exposes the owning proto on IntVar in every
    # supported version of the placer.
    if getattr(variable, "model_proto", None) is not model.model_ref.Proto():
        raise ValueError(f"collision cut {label} refers to a foreign model variable")
    index = variable.Index()
    if index < 0 or index >= len(model.model_ref.Proto().variables):
        raise ValueError(f"collision cut {label} refers to an unknown model variable")
    return variable


def _prepare_projection(
    model: CpSatModel,
    cut: object,
    *,
    expected_candidate_digest: str | None,
) -> _Projection:
    """Validate one immutable Rust cut without changing *model*."""

    first = _ref(_field(cut, "first"), "first")
    second = _ref(_field(cut, "second"), "second")
    if first == second:
        raise ValueError("collision cut cannot reference the same component twice")

    first_pose = (
        _integer(_field(cut, "x_first"), "x_first"),
        _integer(_field(cut, "y_first"), "y_first"),
        _rotation(_field(cut, "rotation_first"), "rotation_first"),
    )
    second_pose = (
        _integer(_field(cut, "x_second"), "x_second"),
        _integer(_field(cut, "y_second"), "y_second"),
        _rotation(_field(cut, "rotation_second"), "rotation_second"),
    )
    area = _field(cut, "overlap_area_mm2")
    if (
        isinstance(area, bool)
        or not isinstance(area, (int, float))
        or not math.isfinite(float(area))
        or float(area) < 0
    ):
        raise ValueError("collision cut overlap area must be finite and non-negative")
    digest = _field(cut, "candidate_digest")
    if not isinstance(digest, str) or not digest.strip():
        raise ValueError("collision cut candidate digest must be non-empty")
    if expected_candidate_digest is not None and digest != expected_candidate_digest:
        raise ValueError("collision cut candidate digest is stale")

    # Rust canonicalizes the unordered pair.  Re-canonicalizing here keeps
    # the adapter safe for an immutable view restored from an older boundary
    # and makes pair reversal map to exactly the same assignment key.
    if first > second:
        first, second = second, first
        first_pose, second_pose = second_pose, first_pose

    pinned = getattr(model, "_rotation_pinned_refs", None)
    if not isinstance(pinned, set):
        raise ValueError("collision cut model has no rotation registration")
    for reference, pose in ((first, first_pose), (second, second_pose)):
        if reference in pinned and pose[2] != 0:
            raise ValueError(
                f"collision cut rotation for fixed component {reference!r} disagrees"
            )

    try:
        first_vars = model.get_component(first)
        second_vars = model.get_component(second)
    except (KeyError, AttributeError) as exc:
        raise ValueError("collision cut references a missing component variable") from exc

    variable_values = (
        (first_vars.x_center, first_pose[0], f"{first}.x"),
        (first_vars.y_center, first_pose[1], f"{first}.y"),
        (first_vars.rot_ref, first_pose[2], f"{first}.rotation"),
        (second_vars.x_center, second_pose[0], f"{second}.x"),
        (second_vars.y_center, second_pose[1], f"{second}.y"),
        (second_vars.rot_ref, second_pose[2], f"{second}.rotation"),
    )
    variables = tuple(
        _validate_variable(model, variable, label)
        for variable, _value, label in variable_values
    )
    indexes = tuple(variable.Index() for variable in variables)
    if len(set(indexes)) != len(indexes):
        raise ValueError("collision cut pose variables are not distinct")
    assignment = tuple(value for _variable, value, _label in variable_values)
    key = (first, second, *assignment)
    return _Projection(key=key, variables=variables, assignment=assignment)


def apply_collision_cuts(
    model: CpSatModel,
    cuts: Iterable[object],
    *,
    expected_candidate_digest: str | None = None,
) -> int:
    """Apply exact-assignment nogoods from validated Rust collision views.

    All cuts are completely preflighted before the first OR-Tools mutation.
    The return value is the number of newly posted forbidden assignments.
    """

    _validate_model_scale(model)
    if expected_candidate_digest is not None and (
        not isinstance(expected_candidate_digest, str) or not expected_candidate_digest.strip()
    ):
        raise ValueError("expected candidate digest must be a non-empty string")
    try:
        raw_cuts = list(cuts)
    except TypeError as exc:
        raise ValueError("collision cuts must be an iterable") from exc
    projections = [
        _prepare_projection(
            model, cut, expected_candidate_digest=expected_candidate_digest
        )
        for cut in raw_cuts
    ]

    applied = getattr(model, "_collision_cut_keys", None)
    if not isinstance(applied, set):
        raise ValueError("collision cut model has no application registry")
    keys = [projection.key for projection in projections]
    if len(set(keys)) != len(keys):
        raise ValueError("collision cut is duplicated in this batch")
    duplicate = next((key for key in keys if key in applied), None)
    if duplicate is not None:
        raise ValueError("collision cut was already applied")

    # This is the sole model mutation: a cut excludes only one witnessed
    # six-value pose tuple.
    for projection in projections:
        model.model_ref.AddForbiddenAssignments(
            list(projection.variables), [list(projection.assignment)]
        )
    applied.update(keys)
    return len(projections)


def apply_collision_cut(
    model: CpSatModel,
    cut: object,
    *,
    expected_candidate_digest: str | None = None,
) -> None:
    """Apply one Rust collision cut as one exact six-variable nogood."""

    apply_collision_cuts(
        model, (cut,), expected_candidate_digest=expected_candidate_digest
    )


__all__ = [
    "RUST_MODEL_UNITS_PER_MM",
    "apply_collision_cut",
    "apply_collision_cuts",
]
