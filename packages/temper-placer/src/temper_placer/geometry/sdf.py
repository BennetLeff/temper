"""
Signed Distance Functions (SDF) — Rust-backed via temper_geometry.

SDFs are a powerful primitive for differentiable geometry. An SDF returns:
- Negative value: point is inside the shape (distance to nearest boundary)
- Zero: point is on the boundary
- Positive value: point is outside the shape (distance to nearest boundary)

Shim-debt cleanup (2026-08-19): the pure re-export lines (``x = _tg.x`` for
the shape / combination / modification kernels) were collapsed — importers
import those symbols from ``temper_geometry`` directly. This module keeps
only the functions that cannot be pure Rust re-exports:

- ``sdf_to_mask`` / ``sdf_to_penalty`` — wrap a scalar into a one-element
  sequence for the Rust kernels (which take ``&[f64]``) and unwrap the
  result, and carry the Python-side ``threshold`` / ``alpha`` defaults;
- ``sdf_gradient`` — takes a Python callable and cannot be ported to Rust.
"""

import numpy as np
import temper_geometry as _tg


def sdf_to_mask(distances, threshold=0.1):
    """Convert SDF to a soft mask (0 outside, 1 inside).

    The Rust implementation expects a sequence; wraps scalar in a list.

    Args:
        distances: SDF value(s)
        threshold: Width of transition region (smaller = sharper)

    Returns:
        Mask value(s) in range [0, 1]
    """
    if isinstance(distances, (int, float)):
        return _tg.sdf_to_mask([distances], threshold)[0]
    return _tg.sdf_to_mask(distances, threshold)


def sdf_to_penalty(distances, alpha=10.0):
    """Convert SDF to a penalty value for being inside a shape.

    The Rust implementation expects a sequence; wraps scalar in a list.

    Args:
        distances: SDF value
        alpha: Smoothing parameter

    Returns:
        Penalty value (0 outside, positive inside)
    """
    if isinstance(distances, (int, float)):
        return _tg.sdf_to_penalty([distances], alpha)[0]
    return _tg.sdf_to_penalty(distances, alpha)


def sdf_gradient(sdf_func, point, epsilon=1e-4):
    """Compute gradient of an SDF at a point using central finite differences.

    This function takes a Python callable and cannot be delegated to Rust.

    Args:
        sdf_func: SDF function that takes point and returns scalar
        point: Query point coordinates
        epsilon: Finite difference step size

    Returns:
        Gradient vector as (gx, gy) — finite-difference approximation
    """
    # Finite-difference gradient approximation
    px, py = point
    dx = (sdf_func((px + epsilon, py)) - sdf_func((px - epsilon, py))) / (2 * epsilon)
    dy = (sdf_func((px, py + epsilon)) - sdf_func((px, py - epsilon))) / (2 * epsilon)
    grad = np.array([dx, dy])

    # Normalize
    magnitude = np.sqrt(np.sum(grad**2) + 1e-10)
    return grad / magnitude
