"""Bounded CP-SAT placement of coarse partition envelopes.

The partitioning policy and the creepage requirements are deliberately not
implemented here.  Rust produces those two plain collections; this module
only turns them into a small, bounded rectangular CP-SAT model.  Keeping that
boundary explicit makes it possible to change partition ownership without
silently changing the safety constraints in the Python layer.

Envelope coordinates are lower-left/upper-right bounds in millimetres.  The
model uses an integer grid (``units_per_mm``) and rounds dimensions and gaps
upwards, so quantisation cannot make a requested separation smaller.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import cast

from ortools.sat.python import cp_model

PartitionPlan = tuple[str, Sequence[str], float, float]
PairRequirement = tuple[str, str, float]
_CP_SAT_INT_LIMIT = 2**60
_DEFAULT_NUM_SEARCH_WORKERS = 4
_MAX_NUM_SEARCH_WORKERS = 64


class EnvelopeSolveStatus(str, Enum):
    """Terminal status returned by :func:`solve_envelopes`."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    MODEL_INVALID = "model_invalid"
    UNKNOWN = "unknown"


# Short alias for callers that use the less verbose name.
EnvelopeStatus = EnvelopeSolveStatus


@dataclass(frozen=True, slots=True)
class EnvelopeBounds:
    """Solved bounds for one partition, expressed in millimetres."""

    partition_id: str
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
class EnvelopeSolveResult:
    """Result of a bounded coarse-envelope solve.

    No bounds are returned for ``UNKNOWN``, ``INFEASIBLE`` or
    ``MODEL_INVALID``.  In particular, a timeout can never accidentally be
    interpreted as a safe partial envelope plan.
    """

    status: EnvelopeSolveStatus
    envelopes: dict[str, EnvelopeBounds]
    solve_time_s: float
    objective_value: float = 0.0
    message: str | None = None

    @property
    def feasible(self) -> bool:
        return self.status in (
            EnvelopeSolveStatus.OPTIMAL,
            EnvelopeSolveStatus.FEASIBLE,
        )

    @property
    def bounds(self) -> dict[str, EnvelopeBounds]:
        """Compatibility/readability alias for ``envelopes``."""

        return self.envelopes


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


def _normalise_inputs(
    partitions: Sequence[PartitionPlan],
    pair_requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    units_per_mm: int,
    rotatable_partition_ids: Collection[str] | None,
) -> tuple[list[PartitionPlan], list[PairRequirement], float, float, int, set[str]]:
    """Validate and canonicalise the Rust/Python boundary data."""

    board_width = _finite_positive(board_width_mm, "board_width_mm")
    board_height = _finite_positive(board_height_mm, "board_height_mm")
    if isinstance(units_per_mm, bool) or not isinstance(units_per_mm, int):
        raise ValueError("units_per_mm must be a positive integer")
    if units_per_mm <= 0:
        raise ValueError("units_per_mm must be a positive integer")
    if isinstance(partitions, (str, bytes)):
        raise ValueError("partitions must be a sequence of partition tuples")
    if isinstance(pair_requirements, (str, bytes)):
        raise ValueError("pair_requirements must be a sequence of pair tuples")

    canonical_partitions: list[PartitionPlan] = []
    partition_ids: set[str] = set()
    refs_seen: set[str] = set()
    for index, raw in enumerate(partitions):
        try:
            partition_id, refs, width_raw, height_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"partition {index} must be (partition_id, refs, width_mm, height_mm)"
            ) from exc
        if not isinstance(partition_id, str) or not partition_id.strip():
            raise ValueError(f"partition {index} has an invalid partition_id")
        if partition_id in partition_ids:
            raise ValueError(f"duplicate partition_id: {partition_id!r}")
        if isinstance(refs, (str, bytes)):
            raise ValueError(f"partition {partition_id!r} refs must be a sequence")
        try:
            ref_tuple = tuple(refs)
        except TypeError as exc:
            raise ValueError(f"partition {partition_id!r} refs must be a sequence") from exc
        if not ref_tuple:
            raise ValueError(f"partition {partition_id!r} must contain at least one ref")
        for ref in ref_tuple:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"partition {partition_id!r} contains an invalid ref")
            if ref in refs_seen:
                raise ValueError(f"component ref belongs to multiple partitions: {ref!r}")
            refs_seen.add(ref)
        width = _finite_positive(width_raw, f"partition {partition_id!r} width_mm")
        height = _finite_positive(height_raw, f"partition {partition_id!r} height_mm")
        partition_ids.add(partition_id)
        canonical_partitions.append((partition_id, tuple(ref_tuple), width, height))

    if rotatable_partition_ids is None:
        rotatable_ids = set(partition_ids)
    else:
        if isinstance(rotatable_partition_ids, (str, bytes)):
            raise ValueError("rotatable_partition_ids must be a collection of partition IDs")
        try:
            rotatable_ids = set(rotatable_partition_ids)
        except TypeError as exc:
            raise ValueError(
                "rotatable_partition_ids must be a collection of partition IDs"
            ) from exc
        if any(not isinstance(partition_id, str) or not partition_id.strip() for partition_id in rotatable_ids):
            raise ValueError("rotatable_partition_ids contains an invalid partition ID")
        unknown_rotatable_ids = rotatable_ids - partition_ids
        if unknown_rotatable_ids:
            raise ValueError(
                "rotatable_partition_ids contains unknown partition IDs: "
                f"{sorted(unknown_rotatable_ids)!r}"
            )
    for partition_id, _refs, width, height in canonical_partitions:
        fits_normal = width <= board_width and height <= board_height
        fits_rotated = height <= board_width and width <= board_height
        fits = fits_normal or fits_rotated if partition_id in rotatable_ids else fits_normal
        if not fits:
            orientation = "or its 90-degree rotation " if partition_id in rotatable_ids else ""
            raise ValueError(
                f"partition {partition_id!r} does not fit within the board {orientation}"
            )

    canonical_partitions.sort(key=lambda item: item[0])
    canonical_requirements: list[PairRequirement] = []
    requirement_keys: set[tuple[str, str]] = set()
    for index, raw_req in enumerate(pair_requirements):
        try:
            req_id_a, req_id_b, required_raw = raw_req
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"pair requirement {index} must be (id_a, id_b, required_mm)"
            ) from exc
        if not isinstance(req_id_a, str) or not isinstance(req_id_b, str):
            raise ValueError(f"pair requirement {index} has invalid partition IDs")
        if req_id_a == req_id_b:
            raise ValueError(f"pair requirement {index} cannot refer to one partition")
        if req_id_a not in partition_ids or req_id_b not in partition_ids:
            raise ValueError(
                f"pair requirement {index} references an unknown partition: {req_id_a!r}, {req_id_b!r}"
            )
        required = _finite_nonnegative(required_raw, f"pair requirement {index} required_mm")
        key = (
            min(req_id_a, req_id_b),
            max(req_id_a, req_id_b),
        )
        if key in requirement_keys:
            raise ValueError(f"duplicate pair requirement for {key[0]!r}, {key[1]!r}")
        requirement_keys.add(key)
        canonical_requirements.append((key[0], key[1], required))
    canonical_requirements.sort(key=lambda item: (item[0], item[1]))

    return (
        canonical_partitions,
        canonical_requirements,
        board_width,
        board_height,
        units_per_mm,
        rotatable_ids,
    )


def _ceil_units(mm: float, units_per_mm: int) -> int:
    # The small epsilon avoids turning ordinary decimal values such as 12.6
    # into a surprising extra grid unit solely because of binary float noise.
    return max(1, math.ceil(mm * units_per_mm - 1e-9))


def _gap_units(mm: float, units_per_mm: int) -> int:
    if mm == 0.0:
        return 0
    return math.ceil(mm * units_per_mm - 1e-9)


def _floor_board_units(mm: float, units_per_mm: int) -> int:
    return math.floor(mm * units_per_mm + 1e-9)


def _normalise_position_hints(
    hints: Mapping[str, tuple[float, float]] | None,
    partition_ids: set[str],
    quantized_sizes: Mapping[str, tuple[int, int]],
    rotatable_partition_ids: set[str],
    board_width_units: int,
    board_height_units: int,
    units_per_mm: int,
) -> dict[str, tuple[int, int, int | None]]:
    """Validate origin hints and derive a forced orientation when possible."""

    if hints is None:
        return {}
    if not isinstance(hints, Mapping):
        raise ValueError("initial_position_hints must be a mapping")
    normalised: dict[str, tuple[int, int, int | None]] = {}
    for partition_id_raw, raw_position in hints.items():
        if not isinstance(partition_id_raw, str) or partition_id_raw not in partition_ids:
            raise ValueError("initial_position_hints contains an unknown partition ID")
        if isinstance(raw_position, (str, bytes)):
            raise ValueError(f"initial hint for {partition_id_raw!r} must be an (x, y) pair")
        try:
            x_mm, y_mm = raw_position
        except (TypeError, ValueError) as exc:
            raise ValueError(f"initial hint for {partition_id_raw!r} must be an (x, y) pair") from exc
        if not _is_real(x_mm) or not _is_real(y_mm):
            raise ValueError(f"initial hint for {partition_id_raw!r} must be finite numbers")
        x_value = float(cast(Real, x_mm))
        y_value = float(cast(Real, y_mm))
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ValueError(f"initial hint for {partition_id_raw!r} must be finite numbers")
        x_units = round(x_value * units_per_mm)
        y_units = round(y_value * units_per_mm)
        if x_units < 0 or y_units < 0 or x_units > board_width_units or y_units > board_height_units:
            raise ValueError(f"initial hint for {partition_id_raw!r} is outside the board")
        width, height = quantized_sizes[partition_id_raw]
        possible_orientations = (
            ((width, height), (height, width))
            if partition_id_raw in rotatable_partition_ids
            else ((width, height),)
        )
        fits = [
            rotation
            for rotation, (candidate_width, candidate_height) in enumerate(
                possible_orientations
            )
            if x_units + candidate_width <= board_width_units
            and y_units + candidate_height <= board_height_units
        ]
        if not fits:
            raise ValueError(f"initial hint for {partition_id_raw!r} cannot fit an orientation")
        normalised[partition_id_raw] = (
            x_units,
            y_units,
            fits[0] if len(fits) == 1 else None,
        )
    return normalised


def _add_model_hint(model: cp_model.CpModel, variable: cp_model.IntVar, value: int) -> None:
    """Apply a hint across OR-Tools versions with either method spelling."""

    add_hint = getattr(model, "add_hint", None) or getattr(model, "AddHint", None)
    if add_hint is None:
        raise ValueError("the CP-SAT backend does not support initial hints")
    add_hint(variable, value)


def _hinted_direction(
    first_hint: tuple[int, int, int | None],
    first_size: tuple[int, int],
    second_hint: tuple[int, int, int | None],
    second_size: tuple[int, int],
) -> int:
    """Choose a deterministic separation direction for two origin hints.

    A hint that does not force an orientation represents both possible
    rectangles.  Score each direction by its worst signed edge separation
    over those possibilities, then choose the largest score with the stable
    left/right/below/above tie-break.  This is only a search hint; the model's
    BoolOr and exact edge constraints remain authoritative.
    """

    def orientations(
        hint: tuple[int, int, int | None], size: tuple[int, int]
    ) -> tuple[tuple[int, int], ...]:
        if hint[2] is None:
            return (size, size[::-1])
        return (size if hint[2] == 0 else size[::-1],)

    first_x, first_y, _first_rotation = first_hint
    second_x, second_y, _second_rotation = second_hint
    direction_scores: list[int] = []
    for direction in range(4):
        scores: list[int] = []
        for first_width, first_height in orientations(first_hint, first_size):
            for second_width, second_height in orientations(second_hint, second_size):
                scores.append(
                    second_x - (first_x + first_width)
                    if direction == 0
                    else first_x - (second_x + second_width)
                    if direction == 1
                    else second_y - (first_y + first_height)
                    if direction == 2
                    else first_y - (second_y + second_height)
                )
        direction_scores.append(min(scores))
    return max(range(4), key=lambda direction: (direction_scores[direction], -direction))


def _mm(units: int, units_per_mm: int) -> float:
    return round(units / units_per_mm, 10)


def _verify_solution(
    envelopes: dict[str, EnvelopeBounds],
    requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    quantized_sizes: Mapping[str, tuple[int, int]],
    rotatable_partition_ids: set[str],
    units_per_mm: int,
) -> str | None:
    """Defensively verify solver output before exposing it to callers."""

    values = list(envelopes.values())
    for bound in values:
        if not (
            0.0 <= bound.x_min_mm <= bound.x_max_mm <= board_width_mm
            and 0.0 <= bound.y_min_mm <= bound.y_max_mm <= board_height_mm
        ):
            return f"envelope {bound.partition_id!r} is outside board bounds"
        expected_sizes = quantized_sizes.get(bound.partition_id)
        if expected_sizes is None:
            return f"envelope {bound.partition_id!r} has no declared partition size"
        actual_size = (
            round(bound.width_mm * units_per_mm),
            round(bound.height_mm * units_per_mm),
        )
        valid_sizes = (
            (expected_sizes, expected_sizes[::-1])
            if bound.partition_id in rotatable_partition_ids
            else (expected_sizes,)
        )
        if actual_size not in valid_sizes:
            return (
                f"envelope {bound.partition_id!r} has invalid extent "
                f"{actual_size!r}; expected one of {valid_sizes!r}"
            )
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            overlap_x = first.x_min_mm < second.x_max_mm and second.x_min_mm < first.x_max_mm
            overlap_y = first.y_min_mm < second.y_max_mm and second.y_min_mm < first.y_max_mm
            if overlap_x and overlap_y:
                return f"envelopes {first.partition_id!r} and {second.partition_id!r} overlap"
    for id_a, id_b, required in requirements:
        first = envelopes[id_a]
        second = envelopes[id_b]
        separated = max(
            second.x_min_mm - first.x_max_mm,
            first.x_min_mm - second.x_max_mm,
            second.y_min_mm - first.y_max_mm,
            first.y_min_mm - second.y_max_mm,
        )
        if separated + 1e-9 < required:
            return f"envelopes {id_a!r} and {id_b!r} violate {required:g} mm separation"
    return None


def solve_envelopes(
    partitions: Sequence[PartitionPlan],
    pair_requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    *,
    time_limit_s: float = 10.0,
    units_per_mm: int = 100,
    num_search_workers: int = _DEFAULT_NUM_SEARCH_WORKERS,
    optimize_layout: bool = False,
    initial_position_hints: Mapping[str, tuple[float, float]] | None = None,
    rotatable_partition_ids: Collection[str] | None = None,
) -> EnvelopeSolveResult:
    """Solve bounded rectangular partition envelopes.

    ``pair_requirements`` contains the already-reduced maximum requirement for
    each partition pair.  This function never derives requirements from refs
    or net names.  The default is feasibility-only: once CP-SAT has found a
    complete feasible plan, no optimization proof is required.  Set
    ``optimize_layout=True`` for the optional stable lower-left objective.
    Invalid input and solver timeouts return no envelopes, which is the
    fail-closed contract needed by the eventual decomposed placement
    orchestrator. ``num_search_workers`` is bounded to avoid accidental
    machine-wide oversubscription in production probes. ``initial_position_hints``
    is an optional partial mapping from partition ID to a lower-left origin
    in millimetres. Missing IDs are allowed; malformed or out-of-board hints
    fail closed as ``MODEL_INVALID``. ``rotatable_partition_ids`` controls
    which partition envelopes may use the 90-degree orientation. ``None``
    preserves the historical behavior where every partition may rotate; an
    empty collection forbids rotation for every partition, and a non-empty
    collection permits it only for the listed IDs.
    """

    try:
        if not _is_real(time_limit_s):
            raise ValueError("time_limit_s must be a finite positive number")
        timeout = float(time_limit_s)
        if not math.isfinite(timeout) or timeout <= 0.0:
            raise ValueError("time_limit_s must be a finite positive number")
        if (
            isinstance(num_search_workers, bool)
            or not isinstance(num_search_workers, int)
            or not 1 <= num_search_workers <= _MAX_NUM_SEARCH_WORKERS
        ):
            raise ValueError(
                f"num_search_workers must be an integer in [1, {_MAX_NUM_SEARCH_WORKERS}]"
            )
        if not isinstance(optimize_layout, bool):
            raise ValueError("optimize_layout must be a boolean")
        (
            normalized_partitions,
            normalized_requirements,
            board_width,
            board_height,
            scale,
            rotatable_partition_ids_normalized,
        ) = _normalise_inputs(
            partitions,
            pair_requirements,
            board_width_mm,
            board_height_mm,
            units_per_mm,
            rotatable_partition_ids,
        )
    except (TypeError, ValueError) as exc:
        return EnvelopeSolveResult(
            status=EnvelopeSolveStatus.MODEL_INVALID,
            envelopes={},
            solve_time_s=0.0,
            message=str(exc),
        )

    try:
        board_w = _floor_board_units(board_width, scale)
        board_h = _floor_board_units(board_height, scale)
        quantized_sizes = [
            (
                _ceil_units(width_mm, scale),
                _ceil_units(height_mm, scale),
            )
            for _partition_id, _refs, width_mm, height_mm in normalized_partitions
        ]
        quantized_gaps = [
            _gap_units(required_mm, scale)
            for _id_a, _id_b, required_mm in normalized_requirements
        ]
    except (OverflowError, ValueError):
        return EnvelopeSolveResult(
            status=EnvelopeSolveStatus.MODEL_INVALID,
            envelopes={},
            solve_time_s=0.0,
            message="board or partition dimensions overflow the model grid",
        )
    if (
        board_w <= 0
        or board_h <= 0
        or board_w > _CP_SAT_INT_LIMIT
        or board_h > _CP_SAT_INT_LIMIT
        or any(
            not ((width <= board_w and height <= board_h) or (height <= board_w and width <= board_h))
            or width > _CP_SAT_INT_LIMIT
            or height > _CP_SAT_INT_LIMIT
            for width, height in quantized_sizes
        )
        or any(gap > _CP_SAT_INT_LIMIT for gap in quantized_gaps)
    ):
        return EnvelopeSolveResult(
            status=EnvelopeSolveStatus.MODEL_INVALID,
            envelopes={},
            solve_time_s=0.0,
            message="board or partition dimensions collapse under the model grid",
        )
    try:
        quantized_by_id = {
            partition_id: quantized_sizes[index]
            for index, (partition_id, _refs, _width, _height) in enumerate(
                normalized_partitions
            )
        }
        normalised_hints = _normalise_position_hints(
            initial_position_hints,
            {partition_id for partition_id, *_rest in normalized_partitions},
            quantized_by_id,
            rotatable_partition_ids_normalized,
            board_w,
            board_h,
            scale,
        )
    except (TypeError, ValueError) as exc:
        return EnvelopeSolveResult(
            status=EnvelopeSolveStatus.MODEL_INVALID,
            envelopes={},
            solve_time_s=0.0,
            message=str(exc),
        )
    model = cp_model.CpModel()
    starts_x: dict[str, cp_model.IntVar] = {}
    starts_y: dict[str, cp_model.IntVar] = {}
    ends_x: dict[str, cp_model.IntVar] = {}
    ends_y: dict[str, cp_model.IntVar] = {}
    interval_x: list[cp_model.IntervalVar] = []
    interval_y: list[cp_model.IntervalVar] = []

    for index, (partition_id, _refs, _width_mm, _height_mm) in enumerate(normalized_partitions):
        width, height = quantized_sizes[index]
        min_width, max_width = min(width, height), max(width, height)
        orientation = model.NewBoolVar(f"envelope_rot90_{index}")
        if partition_id not in rotatable_partition_ids_normalized:
            model.Add(orientation == 0)
        width_var = model.NewIntVar(min_width, max_width, f"envelope_width_{index}")
        height_var = model.NewIntVar(min_width, max_width, f"envelope_height_{index}")
        model.Add(width_var == width).OnlyEnforceIf(orientation.Not())
        model.Add(height_var == height).OnlyEnforceIf(orientation.Not())
        model.Add(width_var == height).OnlyEnforceIf(orientation)
        model.Add(height_var == width).OnlyEnforceIf(orientation)
        x_start = model.NewIntVar(0, board_w - min_width, f"envelope_x_{index}")
        y_start = model.NewIntVar(0, board_h - min_width, f"envelope_y_{index}")
        x_end = model.NewIntVar(min_width, board_w, f"envelope_x_end_{index}")
        y_end = model.NewIntVar(min_width, board_h, f"envelope_y_end_{index}")
        model.Add(x_end == x_start + width_var)
        model.Add(y_end == y_start + height_var)
        model.Add(x_end <= board_w)
        model.Add(y_end <= board_h)
        starts_x[partition_id] = x_start
        starts_y[partition_id] = y_start
        ends_x[partition_id] = x_end
        ends_y[partition_id] = y_end
        interval_x.append(model.NewIntervalVar(x_start, width_var, x_end, f"envelope_ix_{index}"))
        interval_y.append(model.NewIntervalVar(y_start, height_var, y_end, f"envelope_iy_{index}"))
        hint = normalised_hints.get(partition_id)
        if hint is not None:
            hint_x, hint_y, hint_rotation = hint
            _add_model_hint(model, x_start, hint_x)
            _add_model_hint(model, y_start, hint_y)
            if hint_rotation is not None:
                _add_model_hint(model, orientation, hint_rotation)

    if interval_x:
        model.AddNoOverlap2D(interval_x, interval_y)

    for index, (id_a, id_b, _required_mm) in enumerate(normalized_requirements):
        gap = quantized_gaps[index]
        left = model.NewBoolVar(f"separation_left_{index}")
        right = model.NewBoolVar(f"separation_right_{index}")
        below = model.NewBoolVar(f"separation_below_{index}")
        above = model.NewBoolVar(f"separation_above_{index}")
        model.AddBoolOr([left, right, below, above])
        model.Add(ends_x[id_a] + gap <= starts_x[id_b]).OnlyEnforceIf(left)
        model.Add(ends_x[id_b] + gap <= starts_x[id_a]).OnlyEnforceIf(right)
        model.Add(ends_y[id_a] + gap <= starts_y[id_b]).OnlyEnforceIf(below)
        model.Add(ends_y[id_b] + gap <= starts_y[id_a]).OnlyEnforceIf(above)
        hint_a = normalised_hints.get(id_a)
        hint_b = normalised_hints.get(id_b)
        if hint_a is not None and hint_b is not None:
            direction = _hinted_direction(
                hint_a,
                quantized_by_id[id_a],
                hint_b,
                quantized_by_id[id_b],
            )
            for direction_index, literal in enumerate((left, right, below, above)):
                _add_model_hint(model, literal, int(direction_index == direction))

    if optimize_layout:
        # A simple stable objective picks the lower-left feasible layout.  A
        # single worker and fixed model insertion order make repeated solves
        # deterministic while leaving the envelope policy in the Rust plan.
        objective = sum([*starts_x.values(), *starts_y.values()])
        model.Minimize(objective)  # type: ignore[arg-type]
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    solver.parameters.num_search_workers = num_search_workers
    solver.parameters.random_seed = 0
    status_code = solver.Solve(model)
    status_map = {
        cp_model.OPTIMAL: EnvelopeSolveStatus.OPTIMAL,
        cp_model.FEASIBLE: EnvelopeSolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: EnvelopeSolveStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: EnvelopeSolveStatus.MODEL_INVALID,
        cp_model.UNKNOWN: EnvelopeSolveStatus.UNKNOWN,
    }
    status = status_map.get(status_code, EnvelopeSolveStatus.UNKNOWN)
    if status not in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE):
        return EnvelopeSolveResult(
            status=status,
            envelopes={},
            solve_time_s=solver.WallTime(),
            objective_value=solver.ObjectiveValue(),
            message="coarse envelope solve did not produce a complete feasible plan",
        )

    solved: dict[str, EnvelopeBounds] = {}
    for partition_id, _refs, _width, _height in normalized_partitions:
        solved[partition_id] = EnvelopeBounds(
            partition_id=partition_id,
            x_min_mm=_mm(solver.Value(starts_x[partition_id]), scale),
            y_min_mm=_mm(solver.Value(starts_y[partition_id]), scale),
            x_max_mm=_mm(solver.Value(ends_x[partition_id]), scale),
            y_max_mm=_mm(solver.Value(ends_y[partition_id]), scale),
        )
    verification_error = _verify_solution(
        solved,
        normalized_requirements,
        board_width,
        board_height,
        quantized_by_id,
        rotatable_partition_ids_normalized,
        scale,
    )
    if verification_error is not None:
        return EnvelopeSolveResult(
            status=EnvelopeSolveStatus.MODEL_INVALID,
            envelopes={},
            solve_time_s=solver.WallTime(),
            objective_value=solver.ObjectiveValue(),
            message=f"solver output failed defensive validation: {verification_error}",
        )
    return EnvelopeSolveResult(
        status=status,
        envelopes=solved,
        solve_time_s=solver.WallTime(),
        objective_value=solver.ObjectiveValue(),
    )


__all__ = [
    "EnvelopeBounds",
    "EnvelopeSolveResult",
    "EnvelopeSolveStatus",
    "EnvelopeStatus",
    "PairRequirement",
    "PartitionPlan",
    "solve_envelopes",
]
