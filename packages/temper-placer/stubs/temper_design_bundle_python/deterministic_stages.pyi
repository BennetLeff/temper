"""Type stubs for `temper_design_bundle_python.deterministic_stages`.

Compiled from `packages/temper-design-bundle/src/deterministic_stages.rs` —
the Wave 4 Phase 5 first-slice migration of the deterministic leaf-stage
kernels (`slot_generation.py`, `zone_geometry.py`, `zone_assignment.py`).
Keep in sync with that file.

Return-shape notes:
- `define_zone_layout` rows are `(name, xmin, ymin, xmax, ymax)` tuples;
  `HV.x_min` and every `y_min` are Python `int` `0` (the oracle stores
  `((0, 0), ...)` — type-carrying differential canon pins int-vs-float).
- `assign_component_zones` accepts the `Netlist` pyclass from
  `temper_placer.core.netlist` and returns `(ref, zone)` pairs in
  `netlist.components` order.
"""

from __future__ import annotations

from typing import Any, Iterable


def generate_slots_for_zone(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    spacing: float,
) -> list[tuple[float, float]]: ...


def define_zone_layout(
    board_width: float,
    board_height: float,
) -> list[tuple[str, int | float, int | float, float, float]]: ...


def scale_zone_bounds(
    name: str,
    r0: float,
    r1: float,
    r2: float,
    r3: float,
    board_width: float,
    board_height: float,
) -> tuple[float, float, float, float]: ...


def assign_component_zones(netlist: Any) -> Iterable[tuple[str, str]]: ...
