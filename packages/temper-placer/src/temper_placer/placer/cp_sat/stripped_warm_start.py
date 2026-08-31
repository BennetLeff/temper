"""Bridge the exact stripped creepage solve into production CP-SAT hints.

The stripped solver and the component-pair reduction are authoritative Rust
boundaries.  This module only adapts the opaque production netlist objects to
their plain inputs and converts the stripped solver's lower-left boxes into
the production model's centre-coordinate hints.  Hints remain soft: the
production solver is free to move every component to satisfy its complete
constraint model.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_orchestration as _to

from temper_placer.placer.cp_sat.netclass_constraints import (
    _generated_creepage_rows,
    _pin_class_infos,
)
from temper_placer.placer.cp_sat.stripped_creepage_solver import (
    StrippedCreepageSolveResult,
    StrippedCreepageSolveStatus,
    solve_stripped_creepage,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StrippedWarmStartResult:
    """Rust-verified hints, or an explicit empty result on failure.

    ``hints`` is non-empty only when ``solve`` is FEASIBLE or OPTIMAL and
    contains every component in the input netlist.  Callers should pass it to
    ``solve_placement(hint_positions=...)``; these are deliberately not hard
    position pins.
    """

    hints: dict[str, tuple[float, float, int]]
    solve: StrippedCreepageSolveResult | None
    requirement_count: int = 0
    message: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this result is a complete, Rust-verified hint set."""

        return bool(self.hints) and self.solve is not None and self.solve.feasible


def _component_inputs(
    netlist,
) -> tuple[list[tuple[str, float, float]], dict[str, int]]:
    """Project oriented dimensions and current quadrants.

    The stripped model has no rotation variable in this mode. Consequently,
    its input dimensions must already be in the component's current board
    orientation, while the production hint still needs the absolute quadrant
    that selected that orientation.
    """

    components: list[tuple[str, float, float]] = []
    rotations: dict[str, int] = {}
    for component in netlist.components:
        width, height = (float(component.bounds[0]), float(component.bounds[1]))
        rotation = getattr(component, "initial_rotation_quadrant", 0)
        if (
            isinstance(rotation, bool)
            or not isinstance(rotation, int)
            or rotation not in range(4)
        ):
            raise ValueError(f"component {component.ref!r} has invalid initial rotation")
        if rotation % 2:
            width, height = height, width
        components.append((component.ref, width, height))
        rotations[component.ref] = rotation
    return components, rotations


def _requirement_inputs(netlist, design_rules: DesignRules) -> list[tuple[str, str, float]]:
    """Obtain exact component requirements through the Rust-backed reducer."""

    pin_cache: dict[str, tuple[str, str | None, float]] = {}
    components_pin_infos: list[
        tuple[str, list[tuple[str, str | None, float]]]
    ] = []
    for component in netlist.components:
        pin_infos = _pin_class_infos(
            getattr(component, "pins", []), design_rules, pin_cache
        )
        if pin_infos:
            components_pin_infos.append((component.ref, pin_infos))
    class_clearance = {
        cls: float(design_rules.get_rules_for_net("", net_class=cls).clearance)
        for cls in design_rules.net_classes
    }
    class_pair_overrides: list[tuple[str, str, float | None, str]] = []
    for key, value in (getattr(design_rules, "class_pairs", {}) or {}).items():
        if not (isinstance(key, tuple) and len(key) == 2 and isinstance(value, dict)):
            continue
        class_a, class_b = key
        if isinstance(class_a, str) and isinstance(class_b, str):
            class_pair_overrides.append(
                (class_a, class_b, value.get("clearance"), str(value.get("because", "")))
            )
    return [
        (str(ref_a), str(ref_b), float(required))
        for ref_a, ref_b, required in _to.netclass_creepage_requirements_py(
            components_pin_infos,
            class_clearance,
            class_pair_overrides,
            _generated_creepage_rows(),
        )
    ]


def _solve_instance(
    components: Sequence[tuple[str, float, float]],
    requirements: Sequence[tuple[str, str, float]],
    board_width_mm: float,
    board_height_mm: float,
    *,
    timeout_s: float,
    units_per_mm: int,
    num_search_workers: int,
    desired_rotations: dict[str, int] | None = None,
) -> StrippedWarmStartResult:
    """Solve one plain instance and convert its complete boxes to hints."""

    try:
        solve = solve_stripped_creepage(
            components,
            requirements,
            board_width_mm,
            board_height_mm,
            allow_rotations=False,
            timeout_s=timeout_s,
            units_per_mm=units_per_mm,
            num_search_workers=num_search_workers,
        )
    except Exception as exc:  # optional warm-start must fail closed
        _LOGGER.warning("stripped creepage warm-start unavailable: %s", exc)
        return StrippedWarmStartResult({}, None, len(requirements), str(exc))

    if solve.status not in (
        StrippedCreepageSolveStatus.OPTIMAL,
        StrippedCreepageSolveStatus.FEASIBLE,
    ):
        message = solve.message or f"stripped solve ended with {solve.status.value}"
        _LOGGER.warning("stripped creepage warm-start unavailable: %s", message)
        return StrippedWarmStartResult({}, solve, len(requirements), message)

    dimensions = {ref: (width, height) for ref, width, height in components}
    if set(solve.placements) != set(dimensions):
        message = "stripped solve returned an incomplete component mapping"
        _LOGGER.warning("stripped creepage warm-start unavailable: %s", message)
        return StrippedWarmStartResult({}, solve, len(requirements), message)

    hints: dict[str, tuple[float, float, int]] = {}
    rotations = desired_rotations or {}
    for ref, (x_min, y_min, orientation) in solve.placements.items():
        # ``allow_rotations=False`` and Rust verification guarantee orientation
        # zero.  Keep this defensive check at the adapter boundary so a future
        # solver change cannot silently feed rotated boxes as production rot=0.
        if orientation != 0:
            message = f"stripped warm-start returned rotation {orientation} for {ref}"
            _LOGGER.warning("stripped creepage warm-start unavailable: %s", message)
            return StrippedWarmStartResult({}, solve, len(requirements), message)
        width, height = dimensions[ref]
        rotation = rotations.get(ref, 0)
        if (
            isinstance(rotation, bool)
            or not isinstance(rotation, int)
            or rotation not in range(4)
        ):
            message = f"production warm-start rotation {rotation!r} for {ref} is invalid"
            _LOGGER.warning("stripped creepage warm-start unavailable: %s", message)
            return StrippedWarmStartResult({}, solve, len(requirements), message)
        hints[ref] = (x_min + width / 2.0, y_min + height / 2.0, rotation)

    return StrippedWarmStartResult(hints, solve, len(requirements))


def solve_stripped_creepage_warm_start(
    netlist,
    board: Board,
    design_rules: DesignRules,
    *,
    timeout_s: float = 30.0,
    units_per_mm: int = 100,
    num_search_workers: int = 4,
) -> StrippedWarmStartResult:
    """Produce production ``AddHint`` values from a verified fixed solve.

    The stripped model intentionally uses the supplied component orientation
    (no 90-degree choices), matching the production model's initial box
    dimensions.  Its solver returns lower-left coordinates; production
    ``CpSatModel`` variables are component centres, so this adapter performs
    the only frame conversion here.  A timeout, invalid input, incomplete
    result, or Rust verification failure yields no hints.
    """

    try:
        components, rotations = _component_inputs(netlist)
        requirements = _requirement_inputs(netlist, design_rules)
    except Exception as exc:  # optional warm-start must fail closed
        _LOGGER.warning("stripped creepage warm-start unavailable: %s", exc)
        requirement_count = len(requirements) if "requirements" in locals() else 0
        return StrippedWarmStartResult({}, None, requirement_count, str(exc))
    return _solve_instance(
        components,
        requirements,
        float(board.width),
        float(board.height),
        timeout_s=timeout_s,
        units_per_mm=units_per_mm,
        num_search_workers=num_search_workers,
        desired_rotations=rotations,
    )


def solve_production_stripped_instance_warm_start(
    instance,
    *,
    timeout_s: float = 30.0,
    units_per_mm: int = 100,
    num_search_workers: int = 4,
) -> StrippedWarmStartResult:
    """Convert a prepared production stripped instance into soft hints.

    ``ProductionStrippedInstance`` is intentionally duck-typed here to keep
    this adapter independent of the board parser.  Its fields are plain data
    and are already validated by the production-instance boundary.
    """

    try:
        components = tuple(instance.components)
        requirements = tuple(instance.requirements)
        board_width = float(instance.board_width_mm)
        board_height = float(instance.board_height_mm)
        initial_placements = instance.initial_placements
        rotations = {
            ref: int(placement[2])
            for ref, placement in initial_placements.items()
        }
    except Exception as exc:
        _LOGGER.warning("stripped creepage warm-start unavailable: %s", exc)
        return StrippedWarmStartResult({}, None, 0, str(exc))
    return _solve_instance(
        components,
        requirements,
        board_width,
        board_height,
        timeout_s=timeout_s,
        units_per_mm=units_per_mm,
        num_search_workers=num_search_workers,
        desired_rotations=rotations,
    )


__all__ = [
    "StrippedWarmStartResult",
    "solve_production_stripped_instance_warm_start",
    "solve_stripped_creepage_warm_start",
]
