"""Bounded CP-SAT packing for the components of one partition.

This is intentionally a plain-data solver boundary.  The caller supplies the
partition identity, component rectangles, and the already-reduced pair
separation requirements.  No electrical classes, nets, or policy are inferred
here.  A solve is useful only when every component has a verified local bound;
invalid, infeasible, and timed-out solves therefore return no geometry.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import cast

from ortools.sat.python import cp_model

ComponentSpec = tuple[str, float, float]
ComponentPairRequirement = tuple[str, str, float]
_DEFAULT_NUM_SEARCH_WORKERS = 4
_MAX_NUM_SEARCH_WORKERS = 64
_CP_SAT_INT_LIMIT = 2**60


class LocalSubEnvelopeSolveStatus(str, Enum):
    """Terminal status returned by :func:`solve_local_sub_envelope`."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    MODEL_INVALID = "model_invalid"
    UNKNOWN = "unknown"


LocalSubEnvelopeStatus = LocalSubEnvelopeSolveStatus


@dataclass(frozen=True, slots=True)
class LocalComponentBounds:
    """A solved component rectangle in local, lower-left coordinates."""

    ref: str
    x_min_mm: float
    y_min_mm: float
    x_max_mm: float
    y_max_mm: float

    @property
    def width_mm(self) -> float:
        return self.x_max_mm - self.x_min_mm

    @property
    def height_mm(self) -> float:
        return self.y_max_mm - self.y_min_mm


@dataclass(frozen=True, slots=True)
class LocalSubEnvelopeSolveResult:
    """Complete result of a local sub-envelope solve.

    ``component_bounds`` and envelope dimensions are empty/zero for every
    non-feasible status.  This makes a timeout impossible to mistake for a
    partially safe placement.
    """

    status: LocalSubEnvelopeSolveStatus
    partition_id: str
    width_mm: float
    height_mm: float
    component_bounds: dict[str, LocalComponentBounds]
    solve_time_s: float
    objective_value: float = 0.0
    message: str | None = None

    @property
    def feasible(self) -> bool:
        return self.status in (
            LocalSubEnvelopeSolveStatus.OPTIMAL,
            LocalSubEnvelopeSolveStatus.FEASIBLE,
        )

    @property
    def components(self) -> dict[str, LocalComponentBounds]:
        """Short alias for the solved component bounds."""

        return self.component_bounds

    @property
    def envelope_width_mm(self) -> float:
        return self.width_mm

    @property
    def envelope_height_mm(self) -> float:
        return self.height_mm


def _is_real(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _finite_positive(value: object, label: str) -> float:
    if not _is_real(value):
        raise ValueError(f"{label} must be a finite positive number")
    converted = float(cast(Real, value))
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{label} must be a finite positive number")
    return converted


def _finite_nonnegative(value: object, label: str) -> float:
    if not _is_real(value):
        raise ValueError(f"{label} must be a finite non-negative number")
    converted = float(cast(Real, value))
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return converted


def _ceil_units(mm: float, units_per_mm: int) -> int:
    # Keep ordinary decimal values such as 12.6 from acquiring an extra unit
    # solely from binary floating-point noise.  Rounding dimensions/gaps up is
    # conservative: the integer model can never weaken a requested clearance.
    return max(1, math.ceil(mm * units_per_mm - 1e-9))


def _ceil_even_units(mm: float, units_per_mm: int) -> int:
    """Round a positive dimension up to the encoder's even-size grid."""

    units = _ceil_units(mm, units_per_mm)
    return units if units % 2 == 0 else units + 1


def _ceil_nonnegative_even_units(mm: float, units_per_mm: int) -> int:
    """Round a non-negative margin up without turning zero into a margin."""

    if mm == 0.0:
        return 0
    return _ceil_even_units(mm, units_per_mm)


def _floor_units(mm: float, units_per_mm: int) -> int:
    return math.floor(mm * units_per_mm + 1e-9)


def _to_mm(units: int, units_per_mm: int) -> float:
    return round(units / units_per_mm, 10)


def _normalise_inputs(
    partition_id: str,
    components: Sequence[ComponentSpec],
    pair_requirements: Sequence[ComponentPairRequirement],
    max_width_mm: float,
    max_height_mm: float,
    base_gap_mm: float,
    units_per_mm: int,
) -> tuple[str, list[ComponentSpec], list[ComponentPairRequirement], float, float, float]:
    if not isinstance(partition_id, str) or not partition_id.strip():
        raise ValueError("partition_id must be a non-empty string")
    if isinstance(components, (str, bytes)):
        raise ValueError("components must be a sequence of (ref, width_mm, height_mm)")
    if isinstance(pair_requirements, (str, bytes)):
        raise ValueError("pair_requirements must be a sequence of pair tuples")
    max_width = _finite_positive(max_width_mm, "max_width_mm")
    max_height = _finite_positive(max_height_mm, "max_height_mm")
    base_gap = _finite_nonnegative(base_gap_mm, "base_gap_mm")
    if isinstance(units_per_mm, bool) or not isinstance(units_per_mm, int):
        raise ValueError("units_per_mm must be a positive integer")
    if units_per_mm <= 0:
        raise ValueError("units_per_mm must be a positive integer")

    canonical_components: list[ComponentSpec] = []
    refs: set[str] = set()
    try:
        raw_components = list(components)
    except TypeError as exc:
        raise ValueError("components must be a sequence of component tuples") from exc
    if not raw_components:
        raise ValueError("components must contain at least one component")
    for index, raw in enumerate(raw_components):
        try:
            ref, width_raw, height_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(f"component {index} must be (ref, width_mm, height_mm)") from exc
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f"component {index} has an invalid ref")
        if ref in refs:
            raise ValueError(f"duplicate component ref: {ref!r}")
        width = _finite_positive(width_raw, f"component {ref!r} width_mm")
        height = _finite_positive(height_raw, f"component {ref!r} height_mm")
        refs.add(ref)
        canonical_components.append((ref, width, height))
    canonical_components.sort(key=lambda item: item[0])

    requirements: dict[tuple[str, str], float] = {}
    try:
        raw_requirements = list(pair_requirements)
    except TypeError as exc:
        raise ValueError("pair_requirements must be a sequence of pair tuples") from exc
    for index, raw_requirement in enumerate(raw_requirements):
        try:
            requirement_ref_a, requirement_ref_b, required_raw = raw_requirement
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"pair requirement {index} must be (ref_a, ref_b, required_mm)"
            ) from exc
        if not isinstance(requirement_ref_a, str) or not isinstance(requirement_ref_b, str):
            raise ValueError(f"pair requirement {index} has invalid refs")
        if requirement_ref_a == requirement_ref_b:
            raise ValueError(f"pair requirement {index} cannot refer to one component")
        if requirement_ref_a not in refs or requirement_ref_b not in refs:
            raise ValueError(f"pair requirement {index} references an unknown component")
        required = _finite_nonnegative(required_raw, f"pair requirement {index} required_mm")
        key = (min(requirement_ref_a, requirement_ref_b), max(requirement_ref_a, requirement_ref_b))
        if key in requirements:
            raise ValueError(f"duplicate pair requirement for {key[0]!r}, {key[1]!r}")
        requirements[key] = required
    canonical_requirements = [
        (first, second, requirements[(first, second)])
        for first, second in sorted(requirements)
    ]
    return (
        partition_id,
        canonical_components,
        canonical_requirements,
        max_width,
        max_height,
        base_gap,
    )


def _empty_result(
    status: LocalSubEnvelopeSolveStatus,
    partition_id: str,
    *,
    solve_time_s: float = 0.0,
    objective_value: float = 0.0,
    message: str | None = None,
) -> LocalSubEnvelopeSolveResult:
    return LocalSubEnvelopeSolveResult(
        status=status,
        partition_id=partition_id,
        width_mm=0.0,
        height_mm=0.0,
        component_bounds={},
        solve_time_s=solve_time_s,
        objective_value=objective_value,
        message=message,
    )


def _verify_solution(
    bounds: dict[str, LocalComponentBounds],
    components: Sequence[ComponentSpec],
    requirements: Sequence[ComponentPairRequirement],
    base_gap_mm: float,
    width_mm: float,
    height_mm: float,
    max_width_mm: float,
    max_height_mm: float,
) -> str | None:
    if not (0.0 < width_mm <= max_width_mm and 0.0 < height_mm <= max_height_mm):
        return "local envelope exceeds its maximum dimensions"
    if set(bounds) != {ref for ref, _width, _height in components}:
        return "solver omitted one or more component bounds"
    dimensions = {ref: (width, height) for ref, width, height in components}
    for ref, bound in bounds.items():
        width, height = dimensions[ref]
        if not (
            0.0 <= bound.x_min_mm <= bound.x_max_mm <= width_mm + 1e-9
            and 0.0 <= bound.y_min_mm <= bound.y_max_mm <= height_mm + 1e-9
            and bound.width_mm + 1e-9 >= width
            and bound.height_mm + 1e-9 >= height
        ):
            return f"component {ref!r} is outside the local envelope"
    # ``bounds`` is a mapping assembled from solver output.  Do not let its
    # insertion order choose the order of pair checks: project through the
    # canonical component sequence supplied by the caller instead.
    refs = [ref for ref, _width, _height in components]
    values = [bounds[ref] for ref in refs]
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            separation = max(
                second.x_min_mm - first.x_max_mm,
                first.x_min_mm - second.x_max_mm,
                second.y_min_mm - first.y_max_mm,
                first.y_min_mm - second.y_max_mm,
            )
            if separation + 1e-9 < base_gap_mm:
                return f"components {first.ref!r} and {second.ref!r} violate base gap"
    requirement_map = {
        (min(ref_a, ref_b), max(ref_a, ref_b)): required
        for ref_a, ref_b, required in requirements
    }
    for index, ref_a in enumerate(refs):
        for ref_b in refs[index + 1 :]:
            required = max(base_gap_mm, requirement_map.get((min(ref_a, ref_b), max(ref_a, ref_b)), 0.0))
            first, second = bounds[ref_a], bounds[ref_b]
            separation = max(
                second.x_min_mm - first.x_max_mm,
                first.x_min_mm - second.x_max_mm,
                second.y_min_mm - first.y_max_mm,
                first.y_min_mm - second.y_max_mm,
            )
            if separation + 1e-9 < required:
                return f"components {ref_a!r} and {ref_b!r} violate {required:g} mm separation"
    actual_width = max(bound.x_max_mm for bound in values)
    actual_height = max(bound.y_max_mm for bound in values)
    if actual_width > width_mm + 1e-9 or actual_height > height_mm + 1e-9:
        return "reported envelope dimensions are smaller than component bounds"
    return None


def solve_local_sub_envelope(
    partition_id: str,
    components: Sequence[ComponentSpec],
    pair_requirements: Sequence[ComponentPairRequirement],
    max_width_mm: float,
    max_height_mm: float,
    base_gap_mm: float,
    *,
    timeout_s: float = 10.0,
    time_limit_s: float | None = None,
    units_per_mm: int = 100,
    num_search_workers: int = _DEFAULT_NUM_SEARCH_WORKERS,
    headroom_mm: float = 0.0,
) -> LocalSubEnvelopeSolveResult:
    """Pack one partition's rectangles inside a bounded local envelope.

    Every component pair receives a four-way separation disjunction.  Listed
    requirements raise that pair's gap above ``base_gap_mm``; unlisted pairs
    still receive the global base gap.  ``time_limit_s`` is accepted as a
    compatibility spelling for callers that use the coarse solver API.
    ``headroom_mm`` is an optional extra extent added to both reported
    dimensions after solving.  It is placed on the local envelope's right and
    top edges; component bounds and all internal gaps remain unchanged.  The
    margin is conservatively rounded up to the even consumer grid.  A margin
    that would exceed either maximum dimension fails closed as
    ``MODEL_INVALID``.
    """

    if time_limit_s is not None:
        timeout_s = time_limit_s
    try:
        if not _is_real(timeout_s):
            raise ValueError("timeout_s must be a finite positive number")
        timeout = float(cast(Real, timeout_s))
        if not math.isfinite(timeout) or timeout <= 0.0:
            raise ValueError("timeout_s must be a finite positive number")
        if (
            isinstance(num_search_workers, bool)
            or not isinstance(num_search_workers, int)
            or not 1 <= num_search_workers <= _MAX_NUM_SEARCH_WORKERS
        ):
            raise ValueError(
                f"num_search_workers must be an integer in [1, {_MAX_NUM_SEARCH_WORKERS}]"
            )
        headroom = _finite_nonnegative(headroom_mm, "headroom_mm")
        (
            partition,
            normalized_components,
            normalized_requirements,
            max_width,
            max_height,
            base_gap,
        ) = _normalise_inputs(
            partition_id,
            components,
            pair_requirements,
            max_width_mm,
            max_height_mm,
            base_gap_mm,
            units_per_mm,
        )
    except (TypeError, ValueError) as exc:
        safe_partition = partition_id if isinstance(partition_id, str) else ""
        return _empty_result(LocalSubEnvelopeSolveStatus.MODEL_INVALID, safe_partition, message=str(exc))

    try:
        max_width = _floor_units(max_width, units_per_mm)
        max_height = _floor_units(max_height, units_per_mm)
        headroom_units = _ceil_nonnegative_even_units(headroom, units_per_mm)
        sizes = {
            # ``CpSatModel.mm_to_units`` rounds component sizes to an even
            # integer because its midpoint equation requires even parity.
            # Match that consumer contract conservatively here; an odd local
            # dimension can otherwise become one unit smaller in the main
            # model and make a restricted envelope spuriously infeasible.
            ref: (_ceil_even_units(width, units_per_mm), _ceil_even_units(height, units_per_mm))
            for ref, width, height in normalized_components
        }
        refs = [ref for ref, _width, _height in normalized_components]
        all_pairs = [(refs[i], refs[j]) for i in range(len(refs)) for j in range(i + 1, len(refs))]
        requested = {
            (ref_a, ref_b): required for ref_a, ref_b, required in normalized_requirements
        }
        gaps = {
            pair: _ceil_even_units(max(base_gap, requested.get(pair, 0.0)), units_per_mm)
            for pair in all_pairs
        }
    except (OverflowError, ValueError):
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            message="dimensions overflow the model grid",
        )
    if (
        max_width <= 0
        or max_height <= 0
        or max_width > _CP_SAT_INT_LIMIT
        or max_height > _CP_SAT_INT_LIMIT
        or any(width > max_width or height > max_height for width, height in sizes.values())
        or any(gap > _CP_SAT_INT_LIMIT for gap in gaps.values())
    ):
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            message="a component or gap does not fit inside the maximum envelope",
        )

    # Minimize normalized perimeter-like extent.  Weighting width by the
    # available height and height by the available width makes the objective
    # invariant to the aspect ratio of the caller's maximum envelope; unlike
    # width-first lexicographic minimization, it does not prefer pathological
    # one-component-wide strips.  Check the largest possible objective before
    # adding it so a huge caller-provided grid cannot overflow CP-SAT's int64
    # objective arithmetic.
    objective_bound = 2 * max_width * max_height
    if objective_bound > _CP_SAT_INT_LIMIT:
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            message="compactness objective overflows the model integer range",
        )

    model = cp_model.CpModel()
    starts_x: dict[str, cp_model.IntVar] = {}
    starts_y: dict[str, cp_model.IntVar] = {}
    ends_x: dict[str, cp_model.IntVar] = {}
    ends_y: dict[str, cp_model.IntVar] = {}
    intervals_x: list[cp_model.IntervalVar] = []
    intervals_y: list[cp_model.IntervalVar] = []
    for index, ref in enumerate(refs):
        component_width, component_height = sizes[ref]
        x_start = model.NewIntVar(0, max_width - component_width, f"local_x_{index}")
        y_start = model.NewIntVar(0, max_height - component_height, f"local_y_{index}")
        x_end = model.NewIntVar(component_width, max_width, f"local_x_end_{index}")
        y_end = model.NewIntVar(component_height, max_height, f"local_y_end_{index}")
        model.Add(x_end == x_start + component_width)
        model.Add(y_end == y_start + component_height)
        starts_x[ref], starts_y[ref] = x_start, y_start
        ends_x[ref], ends_y[ref] = x_end, y_end
        intervals_x.append(
            model.NewIntervalVar(
                x_start, model.NewConstant(component_width), x_end, f"local_ix_{index}"
            )
        )
        intervals_y.append(
            model.NewIntervalVar(
                y_start, model.NewConstant(component_height), y_end, f"local_iy_{index}"
            )
        )
    envelope_width = model.NewIntVar(1, max_width, "local_envelope_width")
    envelope_height = model.NewIntVar(1, max_height, "local_envelope_height")
    # The runtime exposes AddMaxEquality; the local OR-Tools typing stubs do
    # not yet declare it.
    model.AddMaxEquality(envelope_width, list(ends_x.values()))  # type: ignore[attr-defined]
    model.AddMaxEquality(envelope_height, list(ends_y.values()))  # type: ignore[attr-defined]
    model.AddNoOverlap2D(intervals_x, intervals_y)
    for index, (ref_a, ref_b) in enumerate(all_pairs):
        gap = gaps[(ref_a, ref_b)]
        left = model.NewBoolVar(f"pair_left_{index}")
        right = model.NewBoolVar(f"pair_right_{index}")
        below = model.NewBoolVar(f"pair_below_{index}")
        above = model.NewBoolVar(f"pair_above_{index}")
        model.AddBoolOr([left, right, below, above])
        model.Add(ends_x[ref_a] + gap <= starts_x[ref_b]).OnlyEnforceIf(left)
        model.Add(ends_x[ref_b] + gap <= starts_x[ref_a]).OnlyEnforceIf(right)
        model.Add(ends_y[ref_a] + gap <= starts_y[ref_b]).OnlyEnforceIf(below)
        model.Add(ends_y[ref_b] + gap <= starts_y[ref_a]).OnlyEnforceIf(above)
    model.Minimize(max_height * envelope_width + max_width * envelope_height)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    solver.parameters.num_search_workers = num_search_workers
    solver.parameters.random_seed = 0
    try:
        status_code = solver.Solve(model)
    except Exception as exc:  # pragma: no cover - defensive backend boundary
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            message=f"local CP-SAT solve failed: {exc}",
        )
    statuses = {
        cp_model.OPTIMAL: LocalSubEnvelopeSolveStatus.OPTIMAL,
        cp_model.FEASIBLE: LocalSubEnvelopeSolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: LocalSubEnvelopeSolveStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: LocalSubEnvelopeSolveStatus.MODEL_INVALID,
        cp_model.UNKNOWN: LocalSubEnvelopeSolveStatus.UNKNOWN,
    }
    status = statuses.get(status_code, LocalSubEnvelopeSolveStatus.UNKNOWN)
    solve_time = solver.WallTime()
    if status not in (
        LocalSubEnvelopeSolveStatus.OPTIMAL,
        LocalSubEnvelopeSolveStatus.FEASIBLE,
    ):
        return _empty_result(
            status,
            partition,
            solve_time_s=solve_time,
            objective_value=solver.ObjectiveValue(),
            message="local sub-envelope solve did not produce a complete feasible plan",
        )

    solved = {
        ref: LocalComponentBounds(
            ref=ref,
            x_min_mm=_to_mm(solver.Value(starts_x[ref]), units_per_mm),
            y_min_mm=_to_mm(solver.Value(starts_y[ref]), units_per_mm),
            x_max_mm=_to_mm(solver.Value(ends_x[ref]), units_per_mm),
            y_max_mm=_to_mm(solver.Value(ends_y[ref]), units_per_mm),
        )
        for ref in refs
    }
    # The downstream model converts envelope edges with the same even-parity
    # rule as component sizes.  A max end can be odd because a component's
    # origin is unconstrained to even parity; round the reported envelope
    # extent up to the next even grid unit so consumer conversion cannot
    # shrink the available box by one unit.
    raw_width_units = solver.Value(envelope_width)
    raw_height_units = solver.Value(envelope_height)
    raw_reported_width_units = (
        raw_width_units if raw_width_units % 2 == 0 else raw_width_units + 1
    )
    raw_reported_height_units = (
        raw_height_units if raw_height_units % 2 == 0 else raw_height_units + 1
    )
    if (
        raw_reported_width_units + headroom_units > max_width
        or raw_reported_height_units + headroom_units > max_height
    ):
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            solve_time_s=solve_time,
            objective_value=solver.ObjectiveValue(),
            message="headroom exceeds the maximum envelope dimensions",
        )
    solved_width = _to_mm(raw_reported_width_units + headroom_units, units_per_mm)
    solved_height = _to_mm(raw_reported_height_units + headroom_units, units_per_mm)
    model_width = _to_mm(
        raw_reported_width_units,
        units_per_mm,
    )
    model_height = _to_mm(
        raw_reported_height_units,
        units_per_mm,
    )
    if model_width > solved_width + 1e-9 or model_height > solved_height + 1e-9:
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            solve_time_s=solve_time,
            objective_value=solver.ObjectiveValue(),
            message="reported envelope dimensions are smaller than model extents",
        )
    error = _verify_solution(
        solved,
        normalized_components,
        normalized_requirements,
        base_gap,
        solved_width,
        solved_height,
        max_width_mm=float(max_width_mm),
        max_height_mm=float(max_height_mm),
    )
    if error is not None:
        return _empty_result(
            LocalSubEnvelopeSolveStatus.MODEL_INVALID,
            partition,
            solve_time_s=solve_time,
            objective_value=solver.ObjectiveValue(),
            message=f"solver output failed defensive validation: {error}",
        )
    return LocalSubEnvelopeSolveResult(
        status=status,
        partition_id=partition,
        width_mm=solved_width,
        height_mm=solved_height,
        component_bounds=solved,
        solve_time_s=solve_time,
        objective_value=solver.ObjectiveValue(),
    )


# Readable aliases for callers using the shorter local-envelope terminology.
solve_local_envelope = solve_local_sub_envelope
pack_local_sub_envelope = solve_local_sub_envelope


__all__ = [
    "ComponentPairRequirement",
    "ComponentSpec",
    "LocalComponentBounds",
    "LocalSubEnvelopeSolveResult",
    "LocalSubEnvelopeSolveStatus",
    "LocalSubEnvelopeStatus",
    "pack_local_sub_envelope",
    "solve_local_envelope",
    "solve_local_sub_envelope",
]
