"""
Canonical pad-position math for the placer.

This module is the single source of truth for computing a pin's world
position, layer, and radius. It supersedes the two divergent patterns
that previously appeared in call sites: `pin.absolute_position(...)` (the
correct rotation-and-side-aware version) and `comp_pos + pin.position`
(the simplified, rotation-blind version that silently produced wrong
positions for rotated and bottom-side components).

The functions here are pure-Python and JAX-free so they can be called
from any context (closure tests, validation, DSN export, etc.) without
incurring JAX's ~5s import cost.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Pin


def _rotation_to_radians(rotation: int | float | None) -> float:
    """Convert a Component.rotation value to radians.

    The dataclass field is `initial_rotation: int | None` (0-3 for the
    four orthogonal orientations) or a float (radians). We treat ints
    as quarter-turn indices and floats as already-in-radians values.
    """
    if rotation is None:
        return 0.0
    if isinstance(rotation, int):
        return float(rotation) * (math.pi / 2.0)
    return float(rotation)


def pin_world_position(pin: Pin, comp: Component) -> tuple[float, float]:
    """Return the world (x, y) of a pin given its parent Component.

    Applies the component's rotation and mirrors the X coordinate for
    bottom-side components (side == 1), matching standard KiCad semantics.
    This is the rotation-aware counterpart to the inlined
    `comp_pos + pin.position` pattern, which silently ignored rotation
    and side-mirror and produced wrong pad positions for any component
    with `initial_rotation != 0` or `initial_side == 1`.
    """
    comp_pos = comp.initial_position or (0.0, 0.0)
    rotation_radians = _rotation_to_radians(comp.initial_rotation)
    side = comp.initial_side if comp.initial_side is not None else 0
    cos_r = math.cos(rotation_radians)
    sin_r = math.sin(rotation_radians)
    px, py = pin.position

    if side == 1:
        px = -px

    rx = px * cos_r - py * sin_r
    ry = px * sin_r + py * cos_r
    return (comp_pos[0] + rx, comp_pos[1] + ry)


def pin_world_layer(pin: Pin) -> str:
    """Return the layer name for a pin (e.g., "F.Cu", "all" for TH)."""
    return pin.layer


def pin_world_radius(pin: Pin) -> float:
    """Return the effective pad radius for a pin: max(width, height) / 2."""
    return max(pin.width, pin.height) / 2.0
