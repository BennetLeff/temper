"""
Precompute Minkowski-inflated pad dimensions for DRC proxy loss.

The Minkowski inflation (pad_polygon.buffer(trace_width/2)) is done once per
component using Shapely (non-JAX). The inflated polygons are simplified to
axis-aligned bounding box dimensions (widths, heights) stored as JAX arrays.

At evaluation time, only pairwise AABB distance checks run in JAX — lightweight,
differentiable, and amortizes the expensive Shapely inflation.

Design Decision: Precompute at import, check at evaluation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

import numpy as np


def inflate_pad_polygon(
    pad_vertices: Sequence[tuple[float, float]],
    trace_width_mm: float,
) -> tuple[float, float, float, float]:
    """
    Inflate a pad polygon by trace_width/2 and return AABB (min_x, min_y, max_x, max_y).

    Uses Shapely's buffer operation for the Minkowski sum, then extracts the
    axis-aligned bounding box of the inflated polygon.

    Args:
        pad_vertices: List of (x, y) tuples defining the pad polygon vertices.
        trace_width_mm: Width of traces connecting to this pad (mm).

    Returns:
        Tuple of (min_x, min_y, max_x, max_y) for the inflated polygon AABB.
    """
    try:
        from shapely.geometry import Polygon as ShapelyPolygon
    except ImportError as e:
        raise ImportError(
            "Shapely is required for DRC inflation. Install with: pip install shapely"
        ) from e

    poly = ShapelyPolygon(pad_vertices)
    radius = trace_width_mm / 2.0
    inflated = poly.buffer(radius, resolution=16)

    min_x, min_y, max_x, max_y = inflated.bounds
    return (min_x, min_y, max_x, max_y)


def precompute_inflated_dims(
    pad_vertices_list: Sequence[Sequence[tuple[float, float]]],
    trace_width_mm: float = 0.25,
) -> np.ndarray:
    """
    Precompute inflated pad dimensions for all components.

    For each component's pad polygon, inflates by trace_width/2 and extracts
    the bounding box dimensions. Returns a (N, 2) array of (width, height)
    inflated dimensions suitable for JAX loss computation.

    Args:
        pad_vertices_list: List of pad polygons, each a list of (x, y) tuples.
        trace_width_mm: Width of traces (mm). Default 0.25mm for standard traces.

    Returns:
        np.ndarray of shape (N, 2) with (inflated_width, inflated_height)
        for each component, in mm.
    """
    dims = []
    for pad_vertices in pad_vertices_list:
        if not pad_vertices:
            dims.append([0.0, 0.0])
            continue

        min_x, min_y, max_x, max_y = inflate_pad_polygon(pad_vertices, trace_width_mm)
        width = max_x - min_x
        height = max_y - min_y
        dims.append([width, height])

    if not dims:
        return np.zeros((0, 2), dtype=np.float32)
    return np.array(dims, dtype=np.float32)


def precompute_from_pad_polygons(
    pad_polygons: Sequence,
    trace_width_mm: float = 0.25,
) -> np.ndarray:
    """
    Precompute inflated dimensions from Shapely Polygon objects.

    Convenience wrapper when caller already has Shapely Polygon instances.

    Args:
        pad_polygons: Sequence of Shapely Polygon objects.
        trace_width_mm: Width of traces (mm).

    Returns:
        np.ndarray of shape (N, 2) with (inflated_width, inflated_height).
    """
    dims = []
    for poly in pad_polygons:
        if poly.is_empty:
            dims.append([0.0, 0.0])
            continue

        radius = trace_width_mm / 2.0
        inflated = poly.buffer(radius, resolution=16)
        min_x, min_y, max_x, max_y = inflated.bounds
        width = max_x - min_x
        height = max_y - min_y
        dims.append([width, height])

    return np.array(dims, dtype=np.float32)


def _smooth_relu_array(x: np.ndarray, alpha: float = 10.0) -> np.ndarray:
    """Vectorized smooth ReLU: softplus(alpha * x) / alpha.

    Array formulation of the scalar `temper_placer.geometry.smooth.smooth_relu`
    (which delegates to the temper_geometry Rust crate). The Rust binding is
    scalar-only (`smooth_relu(x: f64, ...)` in packages/temper-geometry/src/
    bridge.rs:670), so array evaluation needs a numpy equivalent here.

    The formula mirrors packages/temper-geometry/src/smooth.rs:151-161 exactly,
    including its stable branch split (evaluate only the taken branch, so no
    overflow/underflow from the untaken one):
      - ax > 0:  (ax + log(1 + exp(-ax))) / alpha
      - ax <= 0: log(1 + exp(ax)) / alpha
    """
    x = np.asarray(x, dtype=np.float64)
    ax = alpha * x
    out = np.empty_like(ax)
    pos = ax > 0.0
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        out[pos] = (ax[pos] + np.log1p(np.exp(-ax[pos]))) / alpha
        out[~pos] = np.log1p(np.exp(ax[~pos])) / alpha
    return out


def compute_inflated_half_dims_from_bounds(
    component_bounds: np.ndarray,
    trace_width_mm: float = 0.25,
) -> np.ndarray:
    """
    Compute inflated half-dimensions from raw component bounds.

    Takes existing (N, 2) component (width, height) bounds and adds
    trace inflation. This is a fast path when full polygon inflation
    is unnecessary (rectangular components).

    Args:
        component_bounds: (N, 2) array of (width, height) per component in mm.
        trace_width_mm: Trace width to inflate by (mm).

    Returns:
        (N, 2) array of (inflated_half_width, inflated_half_height).
    """
    inflation = trace_width_mm  # double-sided: trace_width/2 on each side
    inflated_dims = component_bounds + inflation
    return inflated_dims / 2.0


def compute_drc_proxy_score(
    positions: Array,
    inflated_half_widths: Array,
    inflated_half_heights: Array,
    clearance_mm: float = 0.2,
    beta: float = 10.0,
) -> Array:
    """
    Compute DRC proxy score using inflated pairwise clearance check.

    This is a standalone JAX function that computes the sum of clearance
    violation penalties across all component pairs, using the precomputed
    inflated dimensions.

    Args:
        positions: (N, 2) component center positions.
        inflated_half_widths: (N,) half-widths after Minkowski inflation.
        inflated_half_heights: (N,) half-heights after Minkowski inflation.
        clearance_mm: Required track-to-track clearance (mm).
        beta: Smoothness parameter for smooth_relu.

    Returns:
        Scalar proxy score (sum of squared clearance violations).
    """
    n = positions.shape[0]
    if n < 2:
        return np.array(0.0)

    center_diff = positions[:, None, :] - positions[None, :, :]
    center_dist_x = np.abs(center_diff[:, :, 0])
    center_dist_y = np.abs(center_diff[:, :, 1])

    sum_half_w = inflated_half_widths[:, None] + inflated_half_widths[None, :]
    sum_half_h = inflated_half_heights[:, None] + inflated_half_heights[None, :]

    gap_x = center_dist_x - sum_half_w
    gap_y = center_dist_y - sum_half_h

    both_negative = (gap_x < 0) & (gap_y < 0)
    overlap_dist = np.minimum(gap_x, gap_y)
    separated_dist = np.maximum(gap_x, gap_y)
    distances = np.where(both_negative, overlap_dist, separated_dist)

    # `smooth_relu`'s smoothing parameter is named `alpha` (geometry/smooth.py:114),
    # not `beta`. This call passed `beta=` and raised TypeError on every
    # invocation. Same default (10.0) and same role, so the value carries over
    # unchanged. See docs/evidence/2026-07-26-api-signature-drift-gate.md.
    #
    # The scalar `smooth_relu` binding is scalar-only (f64 extraction) and
    # crashes on the (N, N) pairwise distance matrix for N >= 2, so the
    # vectorized array formulation `_smooth_relu_array` is applied here.
    # It reproduces the Rust scalar math branch-for-branch (see its docstring).
    violations = _smooth_relu_array(clearance_mm - distances, alpha=beta)
    squared_violations = violations**2

    i_upper, j_upper = np.triu_indices(n, k=1)
    return np.sum(squared_violations[i_upper, j_upper])
