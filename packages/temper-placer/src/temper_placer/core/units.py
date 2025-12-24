"""
Unit types and conversions for temper-placer.

This module provides TypeAliases for common physical units used in the project,
specifically targeting the ambiguity between degrees and radians for rotations.
"""

from typing import NewType, TypeAlias

import jax.numpy as jnp
from jax import Array

# Type Aliases for documentation and clarity
# We use NewType to create distinct types that can be caught by type checkers,
# although in practice JAX treats them all as Arrays.
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
