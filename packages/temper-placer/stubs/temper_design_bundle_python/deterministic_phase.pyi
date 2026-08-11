"""Type stubs for `temper_design_bundle_python.deterministic_phase`.

Compiled from `packages/temper-design-bundle/src/deterministic_phase.rs` — the
Wave 4 Phase 5 final-leaves slice migration of the phased-placement mixin
kernels and the zone-aware slot geometry
(`temper_placer/deterministic/stages/{_phase_rotation,_phase_zones,
_phase_validation,zone_aware_slot_generation}.py`). Keep in sync with that
file.

These are kernels only: the Python mixins/stages keep their public API and
delegate the compute here. `slots` is a list of `(sx0, sy0, sx1, sy1)`
isolation-slot tuples; `net_pins` is a dict of net -> `[(ref, pin_name), ...]`
(only the VALUES are read); `bottlenecks` is a list of
`(x, y, layer, severity, score)` tuples; `iso_aabbs` is a list of
`((x_lo, y_lo), (x_hi, y_hi))`.
"""

from __future__ import annotations

from typing import Any


def effective_ghost_pad_radius_py(
    base_radius: float,
    current_pin_absolute: tuple[float, float],
    nearest_other_hv_pin_absolute: tuple[float, float],
    slots: list[tuple[float, float, float, float]],
) -> float: ...


def compute_wirelength_py(
    component_ref: str,
    candidate_slot: tuple[float, float],
    net_pins: dict[Any, list[tuple[str, str]]],
    current_placements: dict[str, tuple[float, float]],
) -> float: ...


def find_critical_bottleneck_violations_py(
    placements: dict[str, Any],
    bottlenecks: list[tuple[int, int, str, str, float]],
    cell_um: float,
    width: int,
    height: int,
) -> list[dict[str, Any]]: ...


def point_in_polygon_py(
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
) -> bool: ...


def slot_intersects_iso_py(
    slot: tuple[float, float],
    iso_aabbs: list[tuple[tuple[float, float], tuple[float, float]]],
) -> bool: ...


def min_distance_to_polygon_py(
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
) -> float: ...
