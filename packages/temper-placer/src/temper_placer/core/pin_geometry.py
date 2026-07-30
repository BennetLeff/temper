"""
Pad-position helpers - the canonical rotation-and-side-aware pad geometry.

This module provides pure-Python free functions for computing pin world
positions on the board, applying component rotation and side-mirror
transforms matching standard KiCad semantics.

Use pin_world_position(pin, comp) as the single source of truth
for all pad-position computation.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Pin


def _normalize_rotation(rotation: int | float | None) -> float:
    """Normalize a rotation value to radians.

    int values are treated as rotation indices (0-3 -> 0/90/180/270 deg),
    matching the convention used by Component.initial_rotation.
    float values are treated as radians and used as-is.
    None is treated as 0 (no rotation).
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
    pad-position math function.

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
    rotation_override: int | None = None,
) -> tuple[float, float]:
    """Return the world (x, y) position of a pin, with optional overrides.

    Like :func:`pin_world_position` but accepts an explicit `pos_override`
    for the component's board position and/or `rotation_override` for the
    component's rotation index (0-3). When an override is provided, it
    replaces the corresponding ``comp.initial_*`` attribute.
    When None, falls back to ``comp.initial_*``.

    This is the canonical implementation; `pin_world_position` delegates to it.

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.
        pos_override: Optional (x, y) tuple overriding the component position.
            When None, uses ``comp.initial_position``.
        rotation_override: Optional rotation index (0-3) overriding
            ``comp.initial_rotation``. When None, uses ``comp.initial_rotation``.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    rot_source = rotation_override if rotation_override is not None else comp.initial_rotation
    rotation_rad = _normalize_rotation(rot_source)
    side = comp.initial_side or 0

    cos_r = math.cos(rotation_rad)
    sin_r = math.sin(rotation_rad)
    px, py = pin.position

    # If on bottom side, mirror X coordinate before rotation (KiCad behavior)
    if side == 1:
        px = -px

    # Rotate pin offset. KiCad's real footprint-child rotation is R(-theta),
    # not R(+theta) -- confirmed against real kicad-cli 10.0.4 pcb drc
    # ground truth, see
    # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
    # Sec. 2. This was previously R(+theta), a real bug for any 90/270
    # degree rotation.
    rx = px * cos_r + py * sin_r
    ry = -px * sin_r + py * cos_r

    # Add component position (use override if provided)
    cpos = pos_override if pos_override is not None else comp.initial_position or (0.0, 0.0)
    return (cpos[0] + rx, cpos[1] + ry)


def pin_world_layer(pin: "Pin") -> str:
    """Return the layer a pin lives on.

    Returns `pin.layer` if set, otherwise `"F.Cu"` (the default for
    surface-mount pads on the top layer).
    """
    return getattr(pin, "layer", None) or "F.Cu"


def pin_world_radius(pin: "Pin") -> float:
    """Return the effective pad radius for a pin -- a fast, rotation-invariant
    conservative bound for the router's hot paths (A* grid cell sizing,
    congestion, obstacle-map fallback, escape-via clearance), NOT a
    shape-agnostic circle.

    This used to be ``max(pin.width, pin.height) / 2.0`` for every pad shape,
    which under-reports extent at the corners of a square/near-square
    rect/roundrect pad (a circle never contains a rectangle) and
    over-reports on the short axis of an elongated pad. It is now
    ``pad_geometry.pad_bounding_radius()`` -- the pad's EXACT, tight,
    rotation-invariant circumscribing radius (not a further approximation):
    for any point on the true pad boundary, its distance from the pad
    center never exceeds this value, and the bound is achieved exactly at
    the pad's true corner direction. See
    ``temper_placer.core.pad_geometry`` module docstring for the full
    closed-form derivation and never-under-reports proof (R2), and for why
    this isotropic bound needs no rotation argument (R3 is satisfied by
    proving the bound is rotation-invariant, not by ignoring rotation).

    If both dimensions are zero, returns 0.5 mm (a common default for
    zero-sized pads, unchanged from the prior behaviour).
    """
    from temper_placer.core.pad_geometry import DEFAULT_ROUNDRECT_RATIO, pad_bounding_radius

    w = getattr(pin, "width", 0.0) or 0.0
    h = getattr(pin, "height", 0.0) or 0.0
    if w == 0.0 and h == 0.0:
        return 0.5
    shape = getattr(pin, "shape", None) or "rect"
    ratio = getattr(pin, "roundrect_ratio", None) or DEFAULT_ROUNDRECT_RATIO
    return pad_bounding_radius(w, h, shape, ratio)
