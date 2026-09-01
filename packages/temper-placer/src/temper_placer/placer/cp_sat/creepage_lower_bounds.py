"""Thin Python boundary for Rust-owned component-box lower bounds."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import temper_orchestration


@dataclass(frozen=True, slots=True)
class ThresholdCliqueBound:
    threshold_mm: float
    class_ids: tuple[int, ...]
    component_refs: tuple[str, ...]
    component_count: int
    expanded_area_mm2: float
    board_expanded_area_mm2: float
    required_board_width_mm: float
    required_board_height_mm: float


@dataclass(frozen=True, slots=True)
class CreepageLowerBoundReport:
    component_count: int
    requirement_count: int
    quotient_class_count: int
    quotient_class_sizes: tuple[int, ...]
    max_component_width_mm: float
    max_component_height_mm: float
    board_width_mm: float
    board_height_mm: float
    threshold_bounds: tuple[ThresholdCliqueBound, ...]
    passes_necessary_conditions: bool


def analyze_creepage_lower_bounds(
    component_dimensions: Sequence[tuple[str, float, float]],
    requirements: Sequence[tuple[str, str, float]],
    board_width_mm: float,
    board_height_mm: float,
) -> CreepageLowerBoundReport:
    """Return necessary-only certificates; a passing report is not feasibility."""

    raw = temper_orchestration.analyze_creepage_lower_bounds_py(
        list(component_dimensions),
        list(requirements),
        board_width_mm,
        board_height_mm,
    )
    bounds = tuple(
        ThresholdCliqueBound(
            threshold_mm=row[0],
            class_ids=tuple(row[1]),
            component_refs=tuple(row[2]),
            component_count=row[3],
            expanded_area_mm2=row[4],
            board_expanded_area_mm2=row[5],
            required_board_width_mm=row[6],
            required_board_height_mm=row[7],
        )
        for row in raw[8]
    )
    return CreepageLowerBoundReport(
        component_count=raw[0],
        requirement_count=raw[1],
        quotient_class_count=raw[2],
        quotient_class_sizes=tuple(raw[3]),
        max_component_width_mm=raw[4],
        max_component_height_mm=raw[5],
        board_width_mm=raw[6],
        board_height_mm=raw[7],
        threshold_bounds=bounds,
        passes_necessary_conditions=raw[9],
    )


__all__ = [
    "CreepageLowerBoundReport",
    "ThresholdCliqueBound",
    "analyze_creepage_lower_bounds",
]
