"""Type stubs for `temper_design_bundle_python.deterministic_stages`.

Compiled from `packages/temper-design-bundle/src/deterministic_stages.rs` —
the Wave 4 Phase 5 first-slice migration of the deterministic leaf-stage
kernels (`slot_generation.py`, `zone_geometry.py`, `zone_assignment.py`).
Keep in sync with that file.

Return-shape notes:
- `define_zone_layout` rows are `(name, xmin, ymin, xmax, ymax)` tuples;
  `HV.x_min` and every `y_min` are Python `int` `0` (the oracle stores
  `((0, 0), ...)` — type-carrying differential canon pins int-vs-float).
  The board DIMS pass through with the caller's type: `y_max` everywhere
  and `MCU.x_max` are `int` for integer board dims, `float` for float
  dims; the boundary products (`x_max` of HV/Power/Signal) are always
  `float`.
- `assign_component_zones` accepts the `Netlist` pyclass from
  `temper_placer.core.netlist` and returns `(ref, zone)` pairs in
  `netlist.components` order.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

def generate_slots_for_zone(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    spacing: float,
) -> list[tuple[float, float]]: ...


def define_zone_layout(
    board_width: int | float,
    board_height: int | float,
) -> list[tuple[str, int | float, int, int | float, int | float]]: ...


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
