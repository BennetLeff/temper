"""
Unit types and conversions for temper-placer.

This module provides NewType wrappers for common physical units to prevent bugs:
- Angle units: Degrees vs Radians
- Spatial units: Millimeters vs CellIndex (prevents unit confusion in grid operations)
- Layer & Net identifiers: LayerIndex, NetId (prevents mixing with arbitrary ints)

Using NewType provides compile-time type checking with zero runtime overhead.

Example of bug prevented by type system:
    # Before (bug):
    cell_x = int(x_mm / cell_size)
    grid.is_available(cell_x, cell_y)  # WRONG! is_available expects mm, not cell index

    # After (type-safe):
    cell_x = mm_to_cell(Millimeters(x_mm), Millimeters(cell_size))
    grid.is_available(cell_x, cell_y)  # TYPE ERROR caught by mypy!
    grid.is_available(Millimeters(x_mm), Millimeters(y_mm))  # OK
"""

from typing import NewType, TypeAlias

import jax.numpy as jnp
from jax import Array

# ============================================================================
# Angle Units
# ============================================================================

Degrees = NewType("Degrees", float)
"""Rotation angle in degrees [0, 360). Primarily used for KiCad I/O and visualization."""

Radians = NewType("Radians", float)
"""Rotation angle in radians [0, 2π). Primarily used for internal math and JAX operations."""

# Array variants for JAX
DegreesArray: TypeAlias = Array
RadiansArray: TypeAlias = Array


def deg_to_rad(degrees: float | Array) -> float | Array:
    """Convert degrees to radians."""
    return degrees * jnp.pi / 180.0


def rad_to_deg(radians: float | Array) -> float | Array:
    """Convert radians to degrees."""
    return radians * 180.0 / jnp.pi


# ============================================================================
# Spatial Units (NEW)
# ============================================================================

Millimeters = NewType("Millimeters", float)
"""Distance in millimeters (physical coordinates on PCB)."""

CellIndex = NewType("CellIndex", int)
"""Grid cell index (0-based, unitless)."""


# ============================================================================
# Layer & Net Identifiers (NEW)
# ============================================================================

LayerIndex = NewType("LayerIndex", int)
"""PCB layer index (0 = top, 1 = inner1, 2 = inner2, 3 = bottom)."""

NetId = NewType("NetId", int)
"""Unique identifier for a net (0 = no net, -1 = conflict, -2 = obstacle, >0 = net ID)."""


# ============================================================================
# Helper Functions for Spatial Conversions (NEW)
# ============================================================================


def mm_to_cell(mm: Millimeters, cell_size_mm: Millimeters) -> CellIndex:
    """Convert millimeter coordinate to cell index.

    Args:
        mm: Position in millimeters
        cell_size_mm: Size of one grid cell in millimeters

    Returns:
        Cell index (0-based)

    Example:
        >>> x_mm = Millimeters(10.5)
        >>> cell_size = Millimeters(0.1)
        >>> cell = mm_to_cell(x_mm, cell_size)
        >>> cell
        105
    """
    return CellIndex(int(mm / cell_size_mm))


def cell_to_mm(cell: CellIndex, cell_size_mm: Millimeters) -> Millimeters:
    """Convert cell index to millimeter coordinate (cell center).

    Args:
        cell: Cell index (0-based)
        cell_size_mm: Size of one grid cell in millimeters

    Returns:
        Position in millimeters (center of cell)

    Example:
        >>> cell = CellIndex(105)
        >>> cell_size = Millimeters(0.1)
        >>> mm = cell_to_mm(cell, cell_size)
        >>> mm
        10.5
    """
    return Millimeters(cell * cell_size_mm)


def distance_mm(x1: Millimeters, y1: Millimeters, x2: Millimeters, y2: Millimeters) -> Millimeters:
    """Calculate Euclidean distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Distance in millimeters
    """
    import math

    dx = x2 - x1
    dy = y2 - y1
    return Millimeters(math.sqrt(dx * dx + dy * dy))


def manhattan_distance_mm(
    x1: Millimeters, y1: Millimeters, x2: Millimeters, y2: Millimeters
) -> Millimeters:
    """Calculate Manhattan distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Manhattan distance in millimeters
    """
    return Millimeters(abs(x2 - x1) + abs(y2 - y1))


# ============================================================================
# Type Guards (NEW)
# ============================================================================


def is_valid_layer(layer: LayerIndex, max_layers: int = 4) -> bool:
    """Check if layer index is valid.

    Args:
        layer: Layer index to check
        max_layers: Maximum number of layers

    Returns:
        True if 0 <= layer < max_layers
    """
    return 0 <= layer < max_layers


def is_valid_net_id(net_id: NetId) -> bool:
    """Check if net ID is valid (not conflict/obstacle markers).

    Args:
        net_id: Net ID to check

    Returns:
        True if net_id >= 0 (0 = no net, >0 = actual net)
    """
    return net_id >= 0
