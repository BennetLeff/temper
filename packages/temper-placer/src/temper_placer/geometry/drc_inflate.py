"""
Precompute Minkowski-inflated pad dimensions for DRC proxy loss.

The Minkowski inflation (pad_polygon.buffer(trace_width/2)) is done once per
component using Shapely. The inflated polygons are simplified to axis-aligned
bounding box dimensions (widths, heights).

At evaluation time, only pairwise AABB distance checks run — lightweight and
amortizes the expensive Shapely inflation.

Design Decision: Precompute at import, check at evaluation.

Wave 4, Phase 4 — what is Rust-backed here and what is not
-----------------------------------------------------------
``_smooth_relu_array``, ``compute_inflated_half_dims_from_bounds`` and
``compute_drc_proxy_score`` delegate to ``temper_geometry`` (Rust:
``packages/temper-geometry/src/drc_inflate.rs``), pinned bit-exactly against
the verbatim pre-migration oracle by
``tests/geometry/test_drc_inflate_rust_differential.py``.

``inflate_pad_polygon``, ``precompute_inflated_dims`` and
``precompute_from_pad_polygons`` deliberately **keep Shapely** (Wave 4 R3
JUSTIFIED-KEEP; blocker recorded in ``packages/temper-geometry/VERIFICATION.md``
and measured by the differential suite's ``TestGeosBlockedSurfacesStayPython``).
The blocker is not "porting is hard": ``buffer(r, resolution=16)`` is GEOS's
*polygonal approximation* of the round offset, so the inflated bounds are not
the closed form ``bounds ± r``. Measured on 169 random polygons at
``ebf9326ff``: 169/169 differ from the closed form, worst deviation 2.4e-3 mm
— three orders of magnitude above a rounding artefact, and about 1% of a
0.2 mm clearance. Even axis-aligned rectangles differ in 12/400 cases (1 ulp).
Reproducing that in Rust means vendoring GEOS's buffer algorithm; approximating
it is a behaviour change no differential on shipped fixtures would catch.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import numpy as np
import temper_geometry as _tg

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

# The dtypes the Rust kernels model exactly. Anything else falls back to the
# numpy expression the oracle itself uses, so the fallback cannot deviate from
# pre-migration behaviour by construction.
_RUST_DTYPES = (np.dtype(np.float32), np.dtype(np.float64))


def _is_rust_array(a: object) -> bool:
    """True when the Rust kernels model this array's dtype exactly."""
    return isinstance(a, np.ndarray) and a.dtype in _RUST_DTYPES


def inflate_pad_polygon(
    pad_vertices: Sequence[tuple[float, float]],
    trace_width_mm: float,
) -> tuple[float, float, float, float]:
    """
    Inflate a pad polygon by trace_width/2 and return AABB (min_x, min_y, max_x, max_y).

    Uses Shapely's buffer operation for the Minkowski sum, then extracts the
    axis-aligned bounding box of the inflated polygon.

    Kept in Python under Wave 4 R3 — see the module docstring for the named
    blocker (GEOS's polygonal round-join approximation) and its measurement.

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
    inflated dimensions.

    Kept in Python under Wave 4 R3 — it is a loop over
    :func:`inflate_pad_polygon`, so it inherits that function's GEOS blocker.

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

    Kept in Python under Wave 4 R3 — the argument type *is* a Shapely object,
    so the GEOS blocker is in the signature, not just the body.

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

    Array formulation of the scalar `temper_placer.geometry.smooth.smooth_relu`.
    The Rust scalar binding is scalar-only (`smooth_relu(x: f64, ...)`), so
    array evaluation needs its own kernel; that kernel is now Rust too
    (`temper_geometry.smooth_relu_array`, `drc_inflate.rs`), not numpy.

    The pre-migration numpy formulation widened its input to float64 on entry
    and kept the stable branch split (evaluate only the taken branch, so no
    overflow/underflow from the untaken one):
      - ax > 0:  (ax + log(1 + exp(-ax))) / alpha
      - ax <= 0: log(1 + exp(ax)) / alpha
    Both properties are preserved by the Rust port, which is pinned bit-exactly
    against the numpy original — verified across 4096-sample sweeps at five
    alphas plus subnormal, infinite and NaN inputs.
    """
    arr = np.asarray(x, dtype=np.float64)
    flat = _tg.smooth_relu_array(np.ascontiguousarray(arr).ravel().tolist(), alpha)
    return np.asarray(flat, dtype=np.float64).reshape(arr.shape)


def compute_inflated_half_dims_from_bounds(
    component_bounds: np.ndarray,
    trace_width_mm: float = 0.25,
) -> np.ndarray:
    """
    Compute inflated half-dimensions from raw component bounds.

    Takes existing (N, 2) component (width, height) bounds and adds
    trace inflation. This is a fast path when full polygon inflation
    is unnecessary (rectangular components).

    Rust-backed (`temper_geometry.inflated_half_dims_from_bounds`). The
    arithmetic runs in the *input array's own width*: fed the float32 output of
    :func:`precompute_inflated_dims` — which is the documented pipeline — it
    rounds in float32, and the result differs from the float64 answer in the
    bits. That width is preserved, not normalised to f64.

    Args:
        component_bounds: (N, 2) array of (width, height) per component in mm.
        trace_width_mm: Trace width to inflate by (mm).

    Returns:
        (N, 2) array of (inflated_half_width, inflated_half_height).
    """
    inflation = trace_width_mm  # double-sided: trace_width/2 on each side
    if not _is_rust_array(component_bounds):
        # Containers/dtypes the Rust kernel does not model. This is the
        # pre-migration expression verbatim, so the fallback is the oracle.
        inflated_dims = component_bounds + inflation
        return inflated_dims / 2.0

    as_f32 = component_bounds.dtype == np.dtype(np.float32)
    flat = _tg.inflated_half_dims_from_bounds(
        np.ascontiguousarray(component_bounds, dtype=np.float64).ravel().tolist(),
        float(inflation),
        as_f32,
    )
    return np.asarray(flat, dtype=component_bounds.dtype).reshape(component_bounds.shape)


def compute_drc_proxy_score(
    positions: Array,
    inflated_half_widths: Array,
    inflated_half_heights: Array,
    clearance_mm: float = 0.2,
    beta: float = 10.0,
) -> Array | np.float64:
    """
    Compute DRC proxy score using inflated pairwise clearance check.

    Computes the sum of clearance violation penalties across all component
    pairs, using the precomputed inflated dimensions.

    Rust-backed (`temper_geometry.drc_proxy_score`). Two properties of the
    numpy original are load-bearing and are reproduced exactly rather than
    "fixed":

    * **dtype width.** The pairwise gap arithmetic runs in the callers' dtypes
      (float32 at every shipped call site), and only the softplus onward is
      float64. Computing the gaps in f64 would be numerically close and
      bit-wrong.
    * **reduction order.** ``np.sum`` is a blocked pairwise reduction, not a
      naive left-to-right accumulation, and float addition is not associative.
      The Rust kernel replicates numpy's blocking; the differential suite pins
      that the two orders genuinely disagree, so that pin cannot go vacuous.

    Args:
        positions: (N, 2) component center positions.
        inflated_half_widths: (N,) half-widths after Minkowski inflation.
        inflated_half_heights: (N,) half-heights after Minkowski inflation.
        clearance_mm: Required track-to-track clearance (mm).
        beta: Smoothness parameter for smooth_relu. (`smooth_relu`'s own
            parameter is named `alpha`; same default, same role. See
            docs/evidence/2026-07-26-api-signature-drift-gate.md.)

    Returns:
        Scalar proxy score (sum of squared clearance violations).
    """
    n = positions.shape[0]
    if n < 2:
        return np.array(0.0)

    # Written as three explicit checks rather than an `all(...)` over a
    # sequence: `all()` is vacuously True over an empty collection, and
    # scripts/check_vacuous_gates.py rejects the unguarded form on principle
    # even where the collection is a fixed-length literal.
    if (
        not _is_rust_array(positions)
        or not _is_rust_array(inflated_half_widths)
        or not _is_rust_array(inflated_half_heights)
    ):
        return _proxy_score_numpy(
            positions, inflated_half_widths, inflated_half_heights, clearance_mm, beta
        )

    f32 = np.dtype(np.float32)
    return np.float64(
        _tg.drc_proxy_score(
            np.ascontiguousarray(positions, dtype=np.float64).ravel().tolist(),
            np.ascontiguousarray(inflated_half_widths, dtype=np.float64).tolist(),
            np.ascontiguousarray(inflated_half_heights, dtype=np.float64).tolist(),
            float(clearance_mm),
            float(beta),
            positions.dtype == f32,
            inflated_half_widths.dtype == f32,
            inflated_half_heights.dtype == f32,
        )
    )


def _proxy_score_numpy(
    positions: Array,
    inflated_half_widths: Array,
    inflated_half_heights: Array,
    clearance_mm: float,
    beta: float,
) -> Array:
    """The pre-migration numpy pipeline, verbatim.

    Reached only for dtypes/containers the Rust kernel does not model (integer
    or float16 arrays, masked arrays, ...). Keeping the original expression
    here means the residual path cannot drift from the oracle.
    """
    n = positions.shape[0]
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

    violations = _smooth_relu_array(clearance_mm - distances, alpha=beta)
    squared_violations = violations**2

    i_upper, j_upper = np.triu_indices(n, k=1)
    return np.sum(squared_violations[i_upper, j_upper])
