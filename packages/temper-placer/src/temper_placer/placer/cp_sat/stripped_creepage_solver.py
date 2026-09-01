"""Exact feasibility model for component-box creepage requirements.

Rust validates and canonicalises the complete instance and verifies every
returned placement.  This module owns only the OR-Tools model construction,
because CP-SAT is a Python dependency in the placer.  The model has no
objective or production heuristics: board bounds, rectangle dimensions, and
the exact pairwise L-infinity gaps are its entire constraint set.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import cast

import temper_orchestration as _to
from ortools.sat.python import cp_model

ComponentSpec = tuple[str, float, float]
PairRequirement = tuple[str, str, float]
Placement = tuple[float, float, int]
_MAX_SEARCH_WORKERS = 64
_MAX_GRID_UNITS = 2**60


class StrippedCreepageSolveStatus(StrEnum):
    """Terminal statuses of the exact feasibility solve."""

    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    MODEL_INVALID = "model_invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class StrippedCreepageSolveResult:
    """A complete placement is present only after Rust verification succeeds."""

    status: StrippedCreepageSolveStatus
    placements: dict[str, Placement]
    solve_time_s: float
    message: str | None = None

    @property
    def feasible(self) -> bool:
        return self.status in (
            StrippedCreepageSolveStatus.OPTIMAL,
            StrippedCreepageSolveStatus.FEASIBLE,
        )

    @property
    def positions(self) -> dict[str, tuple[float, float]]:
        """Lower-left positions, for compatibility with probe callbacks."""

        return {ref: (x, y) for ref, (x, y, _rotation) in self.placements.items()}

    @property
    def rotations(self) -> dict[str, int]:
        return {ref: rotation for ref, (_x, _y, rotation) in self.placements.items()}


def _empty(
    status: StrippedCreepageSolveStatus,
    message: str,
    solve_time_s: float = 0.0,
) -> StrippedCreepageSolveResult:
    return StrippedCreepageSolveResult(status, {}, solve_time_s, message)


def _real(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{label} must be a finite {qualifier} number")
    result = float(cast(Real, value))
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "positive" if positive else "finite"
        raise ValueError(f"{label} must be a finite {qualifier} number")
    return result


def _normalise(
    components: Sequence[ComponentSpec],
    requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    units_per_mm: int,
) -> tuple[list[tuple[str, int, int]], list[tuple[str, str, int]], int, int]:
    if isinstance(components, (str, bytes)) or isinstance(requirements, (str, bytes)):
        raise ValueError("components and requirements must be sequences")
    if isinstance(units_per_mm, bool) or not isinstance(units_per_mm, int) or units_per_mm <= 0:
        raise ValueError("units_per_mm must be a positive integer")
    # The Rust call is the authoritative validation and quantisation step.
    result = _to.normalize_stripped_creepage_py(
        list(components),
        list(requirements),
        _real(board_width_mm, "board_width_mm", positive=True),
        _real(board_height_mm, "board_height_mm", positive=True),
        units_per_mm,
    )
    normalized_components, normalized_requirements, width_units, height_units = result
    if (
        width_units <= 0
        or height_units <= 0
        or width_units > _MAX_GRID_UNITS
        or height_units > _MAX_GRID_UNITS
    ):
        raise ValueError("board dimensions exceed the model integer range")
    return list(normalized_components), list(normalized_requirements), width_units, height_units


def solve_stripped_creepage(
    components: Sequence[ComponentSpec],
    requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    *,
    allow_rotations: bool = False,
    timeout_s: float = 30.0,
    units_per_mm: int = 100,
    num_search_workers: int = 4,
) -> StrippedCreepageSolveResult:
    """Solve the stripped exact model and fail closed on every bad outcome.

    Rotations are restricted to 90 degrees.  The returned lower-left
    coordinates are in mm and are independently checked by the Rust verifier
    against the original (unrounded) component dimensions and requirements.
    """

    try:
        timeout = _real(timeout_s, "timeout_s", positive=True)
        if (
            isinstance(num_search_workers, bool)
            or not isinstance(num_search_workers, int)
            or not 1 <= num_search_workers <= _MAX_SEARCH_WORKERS
        ):
            raise ValueError(f"num_search_workers must be an integer in [1, {_MAX_SEARCH_WORKERS}]")
        if not isinstance(allow_rotations, bool):
            raise ValueError("allow_rotations must be a bool")
        raw_components = list(components)
        raw_requirements = list(requirements)
        normalized, pair_rows, board_width, board_height = _normalise(
            raw_components, raw_requirements, board_width_mm, board_height_mm, units_per_mm
        )
    except Exception as exc:  # fail closed at the foreign-function boundary
        return _empty(StrippedCreepageSolveStatus.MODEL_INVALID, str(exc))

    dimensions = {ref: (width, height) for ref, width, height in normalized}
    if any(
        value > _MAX_GRID_UNITS
        for width, height in dimensions.values()
        for value in (width, height)
    ) or any(gap > _MAX_GRID_UNITS for _left, _right, gap in pair_rows):
        return _empty(
            StrippedCreepageSolveStatus.MODEL_INVALID,
            "component dimensions or gaps exceed the model integer range",
        )
    if any(
        (width > board_width or height > board_height)
        if not allow_rotations
        else not (
            (width <= board_width and height <= board_height)
            or (height <= board_width and width <= board_height)
        )
        for width, height in dimensions.values()
    ):
        return _empty(
            StrippedCreepageSolveStatus.MODEL_INVALID,
            "a component cannot fit the board in either orientation",
        )
    refs = [ref for ref, _width, _height in normalized]
    model = cp_model.CpModel()
    starts_x: dict[str, cp_model.IntVar] = {}
    starts_y: dict[str, cp_model.IntVar] = {}
    ends_x: dict[str, cp_model.IntVar] = {}
    ends_y: dict[str, cp_model.IntVar] = {}
    rotations: dict[str, cp_model.IntVar | None] = {}
    for index, ref in enumerate(refs):
        width, height = dimensions[ref]
        max_size = max(width, height)
        x_start = model.NewIntVar(0, board_width - min(width, height), f"stripped_x_{index}")
        y_start = model.NewIntVar(0, board_height - min(width, height), f"stripped_y_{index}")
        x_size = model.NewIntVar(min(width, height), max_size, f"stripped_w_{index}")
        y_size = model.NewIntVar(min(width, height), max_size, f"stripped_h_{index}")
        x_end = model.NewIntVar(0, board_width, f"stripped_x_end_{index}")
        y_end = model.NewIntVar(0, board_height, f"stripped_y_end_{index}")
        model.Add(x_end == x_start + x_size)
        model.Add(y_end == y_start + y_size)
        if allow_rotations and width != height:
            rotation = model.NewBoolVar(f"stripped_rotation_{index}")
            model.Add(x_size == width).OnlyEnforceIf(rotation.Not())
            model.Add(y_size == height).OnlyEnforceIf(rotation.Not())
            model.Add(x_size == height).OnlyEnforceIf(rotation)
            model.Add(y_size == width).OnlyEnforceIf(rotation)
            rotations[ref] = rotation
        else:
            model.Add(x_size == width)
            model.Add(y_size == height)
            rotations[ref] = None
        model.Add(x_end <= board_width)
        model.Add(y_end <= board_height)
        starts_x[ref], starts_y[ref] = x_start, y_start
        ends_x[ref], ends_y[ref] = x_end, y_end

    for index, (left, right, gap) in enumerate(pair_rows):
        left_of = model.NewBoolVar(f"stripped_left_{index}")
        right_of = model.NewBoolVar(f"stripped_right_{index}")
        below = model.NewBoolVar(f"stripped_below_{index}")
        above = model.NewBoolVar(f"stripped_above_{index}")
        model.AddBoolOr([left_of, right_of, below, above])
        model.Add(ends_x[left] + gap <= starts_x[right]).OnlyEnforceIf(left_of)
        model.Add(ends_x[right] + gap <= starts_x[left]).OnlyEnforceIf(right_of)
        model.Add(ends_y[left] + gap <= starts_y[right]).OnlyEnforceIf(below)
        model.Add(ends_y[right] + gap <= starts_y[left]).OnlyEnforceIf(above)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    solver.parameters.num_search_workers = num_search_workers
    solver.parameters.random_seed = 0
    try:
        status_code = solver.Solve(model)
    except Exception as exc:  # pragma: no cover - defensive backend boundary
        return _empty(StrippedCreepageSolveStatus.MODEL_INVALID, f"CP-SAT solve failed: {exc}")
    status = {
        cp_model.OPTIMAL: StrippedCreepageSolveStatus.OPTIMAL,
        cp_model.FEASIBLE: StrippedCreepageSolveStatus.FEASIBLE,
        cp_model.INFEASIBLE: StrippedCreepageSolveStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: StrippedCreepageSolveStatus.MODEL_INVALID,
        cp_model.UNKNOWN: StrippedCreepageSolveStatus.UNKNOWN,
    }.get(status_code, StrippedCreepageSolveStatus.UNKNOWN)
    solve_time = solver.WallTime()
    if status not in (StrippedCreepageSolveStatus.OPTIMAL, StrippedCreepageSolveStatus.FEASIBLE):
        return _empty(status, "CP-SAT did not produce a complete feasible placement", solve_time)

    solved: dict[str, Placement] = {}
    for ref in refs:
        x = solver.Value(starts_x[ref]) / units_per_mm
        y = solver.Value(starts_y[ref]) / units_per_mm
        rotation_var = rotations[ref]
        rotation = int(solver.Value(rotation_var)) if rotation_var is not None else 0
        solved[ref] = (x, y, rotation)
    try:
        _to.verify_stripped_creepage_py(
            raw_components,
            raw_requirements,
            float(board_width_mm),
            float(board_height_mm),
            [(ref, x, y, rotation) for ref, (x, y, rotation) in solved.items()],
            allow_rotations,
        )
    except Exception as exc:  # fail closed if the Rust oracle is unavailable
        return _empty(
            StrippedCreepageSolveStatus.MODEL_INVALID,
            f"Rust exhaustive verification rejected solver output: {exc}",
            solve_time,
        )
    return StrippedCreepageSolveResult(status, solved, solve_time)


__all__ = [
    "ComponentSpec",
    "PairRequirement",
    "Placement",
    "StrippedCreepageSolveResult",
    "StrippedCreepageSolveStatus",
    "solve_stripped_creepage",
]
