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

from typing import Sequence

import numpy as np
from jax import Array
import jax.numpy as jnp


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
    except ImportError:
        raise ImportError(
            "Shapely is required for DRC inflation. "
            "Install with: pip install shapely"
        )

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

        min_x, min_y, max_x, max_y = inflate_pad_polygon(
            pad_vertices, trace_width_mm
        )
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
    try:
        from shapely.geometry import Polygon as ShapelyPolygon
    except ImportError:
        raise ImportError("Shapely is required for DRC inflation.")

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
    from temper_placer.geometry.smooth import smooth_relu

    n = positions.shape[0]
    if n < 2:
        return jnp.array(0.0)

    center_diff = positions[:, None, :] - positions[None, :, :]
    center_dist_x = jnp.abs(center_diff[:, :, 0])
    center_dist_y = jnp.abs(center_diff[:, :, 1])

    sum_half_w = inflated_half_widths[:, None] + inflated_half_widths[None, :]
    sum_half_h = inflated_half_heights[:, None] + inflated_half_heights[None, :]

    gap_x = center_dist_x - sum_half_w
    gap_y = center_dist_y - sum_half_h

    both_negative = (gap_x < 0) & (gap_y < 0)
    overlap_dist = jnp.minimum(gap_x, gap_y)
    separated_dist = jnp.maximum(gap_x, gap_y)
    distances = jnp.where(both_negative, overlap_dist, separated_dist)

    violations = smooth_relu(clearance_mm - distances, beta=beta)
    squared_violations = violations ** 2

    i_upper, j_upper = jnp.triu_indices(n, k=1)
    return jnp.sum(squared_violations[i_upper, j_upper])
