"""Pad-position helpers — the canonical rotation-and-side-aware pad geometry.

This module consolidates the two divergent implementations of "where is this
pin on the board?" that exist in the placer codebase:

1. `Pin.absolute_position(component_pos, rotation_angle, side)` — correct,
   applies rotation and side-mirror via JAX trig. Used by ~11 call sites.

2. Inlined `comp_pos + pin.position` — broken, ignores rotation and side.
   Used by ~40 call sites across ~25 files.

This module provides pure-Python free functions that all call sites should
use instead. `Pin.absolute_position` delegates here to prevent drift.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Pin


def _normalize_rotation(rotation: int | float | None) -> float:
    """Normalize a rotation value to radians.

    `int` values are treated as rotation indices (0-3 → 0°/90°/180°/270°),
    matching the convention used by `Component.initial_rotation`.
    `float` values are treated as radians and used as-is.
    `None` is treated as 0 (no rotation).
    """
    if rotation is None:
        return 0.0
    if isinstance(rotation, int):
        return rotation * math.pi / 2.0
    return float(rotation)


def pin_world_position(
    pin: "Pin",
    comp: "Component",
) -> tuple[float, float]:
    """Return the world (x, y) position of a pin on the board.

    Applies the component's rotation and side-mirror to the pin's position
    offset, matching standard KiCad semantics. This is the canonical
    pad-position math — the same logic as `Pin.absolute_position` but as
    a pure-Python free function (no JAX import required).

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    return pin_world_position_at(pin, comp)


def pin_world_position_at(
    pin: "Pin",
    comp: "Component",
    pos_override: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Return the world (x, y) position of a pin, with optional position override.

    Like :func:`pin_world_position` but accepts an explicit `pos_override`
    for the component's board position. When `pos_override` is provided, it
    replaces `comp.initial_position` in the world-position calculation.
    When None, falls back to `comp.initial_position`.

    This is the canonical implementation; `pin_world_position` delegates to it.

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.
        pos_override: Optional (x, y) tuple overriding the component position.
            When None, uses ``comp.initial_position``.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    rotation_rad = _normalize_rotation(comp.initial_rotation)
    side = comp.initial_side or 0

    cos_r = math.cos(rotation_rad)
    sin_r = math.sin(rotation_rad)
    px, py = pin.position

    # If on bottom side, mirror X coordinate before rotation (KiCad behavior)
    if side == 1:
        px = -px

    # Rotate pin offset
    rx = px * cos_r - py * sin_r
    ry = px * sin_r + py * cos_r

    # Add component position (use override if provided)
    if pos_override is not None:
        cpos = pos_override
    else:
        cpos = comp.initial_position or (0.0, 0.0)
    return (cpos[0] + rx, cpos[1] + ry)


def pin_world_layer(pin: "Pin") -> str:
    """Return the layer a pin lives on.

    Returns `pin.layer` if set, otherwise `"F.Cu"` (the default for
    surface-mount pads on the top layer).
    """
    return getattr(pin, "layer", None) or "F.Cu"


def pin_world_radius(pin: "Pin") -> float:
    """Return the effective pad radius for a pin.

    Computed as `max(pin.width, pin.height) / 2.0`. If both dimensions
    are zero, returns 0.5 mm (a common default for zero-sized pads).
    """
    w = getattr(pin, "width", 0.0) or 0.0
    h = getattr(pin, "height", 0.0) or 0.0
    radius = max(w, h) / 2.0
    if radius == 0.0:
        radius = 0.5
    return radius
