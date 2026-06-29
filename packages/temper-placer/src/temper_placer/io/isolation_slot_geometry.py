"""Helpers for converting IsolationSlot component-local geometry into board-coords rectangles.

Used by ZoneAwareSlotGenerationStage to filter candidate placement slots that
overlap milled cutouts. We assume axis-aligned rectangles: the cutout is the
AABB of (start_offset, end_offset) extruded by width_mm/2 on the axis
perpendicular to (end - start). See plan 2026-06-23-007 R2 — if a future
slot uses non-rectangular geometry, the AABB intersection test will silently
let overlaps through. Test that all current slots are axis-aligned before
relying on this helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.io.config_loader import IsolationSlot


def isolation_slot_aabb(
    slot: IsolationSlot,
    component_xy: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return board-coords ((x_min, y_min), (x_max, y_max)) of the cutout footprint.

    The cutout's `width_mm` is the dimension perpendicular to the slot's
    axis. For an axis-aligned slot the perpendicular axis is the one that
    does NOT carry the (end - start) vector. We expand the AABB only on
    that perpendicular axis.
    """
    cx, cy = component_xy
    sx, sy = slot.start_offset
    ex, ey = slot.end_offset
    x_lo, x_hi = min(sx, ex), max(sx, ex)
    y_lo, y_hi = min(sy, ey), max(sy, ey)
    dx, dy = ex - sx, ey - sy
    half_w = slot.width_mm / 2.0
    if abs(dx) >= abs(dy):
        # Slot runs along x — width is in y.
        y_lo -= half_w
        y_hi += half_w
    else:
        # Slot runs along y — width is in x.
        x_lo -= half_w
        x_hi += half_w
    return ((cx + x_lo, cy + y_lo), (cx + x_hi, cy + y_hi))
