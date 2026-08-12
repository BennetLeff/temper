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

from typing import NewType

import numpy as np
import temper_geometry as _geometry
import temper_io_types as _rs
from numpy.typing import NDArray as Array

# ============================================================================
# Angle Units
# ============================================================================

Degrees = NewType("Degrees", float)
"""Rotation angle in degrees [0, 360). Primarily used for KiCad I/O and visualization."""

Radians = NewType("Radians", float)
"""Rotation angle in radians [0, 2π). Primarily used for internal math and JAX operations."""

# Array variants for JAX
def deg_to_rad(degrees: float | Array) -> float | Array:
    """Convert degrees to radians.

    Scalars go to Rust (``(x * pi) / 180`` in f64 -- the same two
    roundings, in the same order, as the numpy expression below; note
    that this is *not* ``math.radians``/``np.radians``, which disagree
    with it on ~30% of inputs by a ulp). Arrays keep the original numpy
    expression, because NEP 50 makes the result dtype depend on the
    input dtype (float32 stays float32 and is computed in float32);
    reproducing that promotion in Rust would mean reimplementing NEP 50.
    """
    if _rs.is_plain_python_scalar(degrees):
        return _rs.deg_to_rad(degrees)
    return degrees * np.pi / 180.0


def rad_to_deg(radians: float | Array) -> float | Array:
    """Convert radians to degrees.

    Same scalar/array split as :func:`deg_to_rad`.
    """
    if _rs.is_plain_python_scalar(radians):
        return _rs.rad_to_deg(radians)
    return radians * 180.0 / np.pi


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
    return CellIndex(_rs.mm_to_cell(mm, cell_size_mm))


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
    return Millimeters(_rs.cell_to_mm(cell, cell_size_mm))


def distance_mm(x1: Millimeters, y1: Millimeters, x2: Millimeters, y2: Millimeters) -> Millimeters:
    """Calculate Euclidean distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Distance in millimeters
    """
    return Millimeters(_rs.distance_mm(x1, y1, x2, y2))


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
    return Millimeters(_rs.manhattan_distance_mm(x1, y1, x2, y2))


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
    return _rs.is_valid_layer(layer, max_layers)


def is_valid_net_id(net_id: NetId) -> bool:
    """Check if net ID is valid (not conflict/obstacle markers).

    Args:
        net_id: Net ID to check

    Returns:
        True if net_id >= 0 (0 = no net, >0 = actual net)
    """
    return _rs.is_valid_net_id(net_id)


# ============================================================================
# Length Units: mm / mil / inch (Wave-4 Phase A, plan 2026-08-09-001)
# ============================================================================
#
# The `Mm`/`Mil`/`Inch` newtype-wrappers-over-f64 marshalling surface is
# implemented in Rust (packages/temper-geometry/src/units.rs). Each function
# below is a delegation shim; bit-identical parity against the pinned
# reference expressions is asserted by
# tests/core/test_units_rust_differential.py and tests/core/test_units_pbt.py.
# The conversion factors are the exact IEEE-754 doubles
# temper-design-bundle's pcl_parse.rs pins (0.0254 mm/mil, 25.4 mm/in).
#
# Note: the existing `Millimeters` NewType above is a *type-level* annotation
# (zero runtime behaviour); these functions are the runtime conversion
# surface. Full `#[pyclass]` wrappers were deliberately NOT added — see the
# Rust module doc for the recorded decision and evidence.


def mil_to_mm(mil: float) -> float:
    """Convert mils (thousandths of an inch) to millimetres.

    Exact reference expression: ``mil * 0.0254`` (single rounding).
    """
    return _geometry.mil_to_mm(mil)


def mm_to_mil(mm: float) -> float:
    """Convert millimetres to mils.

    Exact reference expression: ``mm / 0.0254`` (single rounding).
    """
    return _geometry.mm_to_mil(mm)


def inch_to_mm(inch: float) -> float:
    """Convert inches to millimetres.

    Exact reference expression: ``inch * 25.4`` (single rounding).
    """
    return _geometry.inch_to_mm(inch)


def mm_to_inch(mm: float) -> float:
    """Convert millimetres to inches.

    Exact reference expression: ``mm / 25.4`` (single rounding).
    """
    return _geometry.mm_to_inch(mm)


def mil_to_inch(mil: float) -> float:
    """Convert mils to inches.

    Exact reference expression: ``mil / 1000.0`` (single rounding).
    """
    return _geometry.mil_to_inch(mil)


def inch_to_mil(inch: float) -> float:
    """Convert inches to mils.

    Exact reference expression: ``inch * 1000.0`` (single rounding).
    """
    return _geometry.inch_to_mil(inch)
