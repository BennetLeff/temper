"""
Property-based tests for the Rust geometry extraction via Hypothesis.

These tests verify invariants on the compiled ``temper_geometry`` native module
(the PyO3 bridge), not the Python wrapper layer.  Each test exercises a
mathematical property that must hold for a wide range of random inputs:

- Point distance symmetry & non-negativity
- Rotate + inverse-rotate identity
- Polygon area positivity & invariance
- SDF circle at-boundary identity
- Smooth min/max bounds
- Projection containment
"""

from __future__ import annotations

import math as _math

from hypothesis import given, note, settings, strategies as st
from hypothesis import Phase

import temper_geometry as tg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOL = 1e-9
_MAX_EXAMPLES = 200

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Finite floats in a range that avoids overflow / extreme subnormals.
_coords = st.floats(
    min_value=-1e5,
    max_value=1e5,
    allow_nan=False,
    allow_infinity=False,
)

_nonneg = st.floats(
    min_value=0.0,
    max_value=1e5,
    allow_nan=False,
    allow_infinity=False,
)

_pos = st.floats(
    min_value=1e-3,
    max_value=1e4,
    allow_nan=False,
    allow_infinity=False,
)

# A flat list of [x, y, x, y, ...] pairs for polygon vertices.
def convex_polygon_vertices(n: int):
    """Generate a convex CCW polygon as a flat ``[x1, y1, x2, y2, ...]`` list.

    Places ``n`` vertices on a circle of random radius, guaranteeing convexity
    and non-zero area.
    """
    angles = [2.0 * _math.pi * i / n for i in range(n)]
    return st.lists(
        st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=n,
        max_size=n,
    ).map(lambda radii: [v for a, r in zip(angles, radii) for v in (r * _math.cos(a), r * _math.sin(a))])


# =============================================================================
# Point distance invariants
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords)
def test_point_distance_symmetry(x1, y1, x2, y2):
    d1 = tg.point_distance(x1, y1, x2, y2)
    d2 = tg.point_distance(x2, y2, x1, y1)
    assert abs(d1 - d2) < _TOL, f"distance not symmetric: {d1} vs {d2}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords)
def test_point_distance_non_negative(x1, y1, x2, y2):
    d = tg.point_distance(x1, y1, x2, y2)
    assert d >= 0.0, f"distance should be >= 0, got {d}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords, _coords, _coords)
def test_point_distance_triangle_inequality(x1, y1, x2, y2, x3, y3):
    d12 = tg.point_distance(x1, y1, x2, y2)
    d23 = tg.point_distance(x2, y2, x3, y3)
    d13 = tg.point_distance(x1, y1, x3, y3)
    assert d13 <= d12 + d23 + 1e-9, (
        f"triangle inequality: {d13} > {d12} + {d23}"
    )


# =============================================================================
# Rotate + inverse-rotate = identity
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords)
def test_rotate_inverse_identity(x, y, angle):
    """rotate(p, a) then rotate(p, -a) should return p."""
    rx, ry = tg.rotate_point(x, y, angle)
    rx2, ry2 = tg.rotate_point(rx, ry, -angle)
    assert abs(rx2 - x) < _TOL, f"x drifted: {rx2} vs {x}"
    assert abs(ry2 - y) < _TOL, f"y drifted: {ry2} vs {y}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords, _coords)
def test_rotate_about_center_inverse(x, y, cx, cy, angle):
    """rotate-around-center then reverse around same center is identity."""
    rx, ry = tg.rotate_point(x, y, angle, center_x=cx, center_y=cy)
    rx2, ry2 = tg.rotate_point(rx, ry, -angle, center_x=cx, center_y=cy)
    assert abs(rx2 - x) < _TOL, f"x drifted: {rx2} vs {x}"
    assert abs(ry2 - y) < _TOL, f"y drifted: {ry2} vs {y}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords, _coords)
def test_rotate_preserves_distance(x1, y1, x2, y2, angle):
    d_before = tg.point_distance(x1, y1, x2, y2)
    rx1, ry1 = tg.rotate_point(x1, y1, angle)
    rx2, ry2 = tg.rotate_point(x2, y2, angle)
    d_after = tg.point_distance(rx1, ry1, rx2, ry2)
    assert abs(d_before - d_after) < _TOL, (
        f"rotation changed distance: {d_before} -> {d_after}"
    )


# =============================================================================
# Polygon area invariants
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(convex_polygon_vertices(3))
def test_polygon_area_non_negative(verts):
    area = tg.polygon_area(verts)
    assert area >= 0.0, f"area should be >= 0, got {area}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(convex_polygon_vertices(3))
def test_polygon_signed_area_matches_area(verts):
    signed = tg.polygon_signed_area(verts)
    area = tg.polygon_area(verts)
    assert abs(area - abs(signed)) < _TOL, (
        f"area {area} != |signed| {abs(signed)}"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(convex_polygon_vertices(3), _coords, _coords)
def test_polygon_area_translation_invariant(verts, dx, dy):
    area_before = tg.polygon_area(verts)
    # translate: add dx, dy to each vertex
    translated = [verts[i] + (dx if i % 2 == 0 else dy) for i in range(len(verts))]
    area_after = tg.polygon_area(translated)
    assert abs(area_before - area_after) < 1e-6, (
        f"area changed {area_before} -> {area_after} after translation"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(convex_polygon_vertices(3), _coords)
def test_polygon_area_rotation_invariant(verts, angle):
    area_before = tg.polygon_area(verts)
    rotated = tg.rotate_polygon(verts, angle)
    area_after = tg.polygon_area(rotated)
    assert abs(area_before - area_after) < 1e-6, (
        f"area changed {area_before} -> {area_after} after rotation"
    )


# =============================================================================
# SDF invariants
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos)
def test_sdf_circle_center_is_negative_radius(cx, cy, r):
    """sdf_circle at center should equal -r."""
    d = tg.sdf_circle(cx, cy, cx, cy, r)
    assert abs(d - (-r)) < _TOL, f"expected {-r}, got {d}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos, _coords, _coords)
def test_sdf_circle_on_boundary_zero(cx, cy, r, dx, dy):
    """sdf_circle on the circle boundary should be approximately 0."""
    # Place point on the boundary
    dist = _math.hypot(dx, dy)
    if dist < 1e-6:
        return  # skip degenerate
    px = cx + r * dx / dist
    py = cy + r * dy / dist
    d = tg.sdf_circle(px, py, cx, cy, r)
    assert abs(d) < 1e-6, f"on-boundary SDF should be ~0, got {d}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos, _coords, _coords)
def test_sdf_circle_outside_positive(cx, cy, r, dx, dy):
    dist = _math.hypot(dx, dy)
    if dist < 1.0:
        return  # skip points near center
    px = cx + (r + abs(dist)) * dx / dist
    py = cy + (r + abs(dist)) * dy / dist
    d = tg.sdf_circle(px, py, cx, cy, r)
    assert d > 0.0, f"outside SDF should be > 0, got {d}"


# =============================================================================
# Smooth min/max invariants
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos)
def test_smooth_max_ge_true_max(a, b, alpha):
    result = tg.smooth_max(a, b, alpha)
    true_max = max(a, b)
    assert result >= true_max - 1e-12, (
        f"smooth_max({a}, {b}, {alpha}) = {result} < true_max {true_max}"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos)
def test_smooth_min_le_true_min(a, b, alpha):
    result = tg.smooth_min(a, b, alpha)
    true_min = min(a, b)
    assert result <= true_min + 1e-12, (
        f"smooth_min({a}, {b}, {alpha}) = {result} > true_min {true_min}"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos)
def test_smooth_max_symmetric(a, b, alpha):
    ab = tg.smooth_max(a, b, alpha)
    ba = tg.smooth_max(b, a, alpha)
    assert abs(ab - ba) < 1e-12, (
        f"smooth_max not symmetric: {ab} vs {ba}"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos)
def test_smooth_min_minus_identity(a, b, alpha):
    """Verify min(a,b) = -max(-a, -b)."""
    min_val = tg.smooth_min(a, b, alpha)
    neg_max = -tg.smooth_max(-a, -b, alpha)
    assert abs(min_val - neg_max) < 1e-12, (
        f"identity failed: min={min_val}, -max(-a,-b)={neg_max}"
    )


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords)
def test_smooth_max_converges(a, b):
    """At high alpha, smooth_max should closely approximate true max."""
    result = tg.smooth_max(a, b, 1e6)
    true_max = max(a, b)
    assert abs(result - true_max) < 1e-3, (
        f"smooth_max should converge at high alpha: {result} vs {true_max}"
    )


# =============================================================================
# Projection invariants
# =============================================================================

@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _pos, _pos, _nonneg)
def test_project_onto_board_within_bounds(px, py, board_w, board_h, margin):
    """Projected point must stay within [margin, board_dim - margin]."""
    if 2.0 * margin > min(board_w, board_h):
        return  # skip invalid configuration
    rx, ry = tg.project_onto_board(px, py, board_w, board_h, margin)
    assert rx >= margin - 1e-9, f"x {rx} below margin {margin}"
    assert rx <= board_w - margin + 1e-9, f"x {rx} above board_w - margin {board_w - margin}"
    assert ry >= margin - 1e-9, f"y {ry} below margin {margin}"
    assert ry <= board_h - margin + 1e-9, f"y {ry} above board_h - margin {board_h - margin}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords, _coords, _coords, _pos, _pos, _coords, _coords)
def test_project_onto_zone_containment(px, py, zx, zy, zw, zh, _hint_x, _hint_y):
    """Project onto a zone: result must be inside the zone."""
    rx, ry = tg.project_onto_zone(px, py, zx, zy, zw, zh)
    assert rx >= zx - 1e-9, f"x {rx} < zone left {zx}"
    assert rx <= zx + zw + 1e-9, f"x {rx} > zone right {zx + zw}"
    assert ry >= zy - 1e-9, f"y {ry} < zone bottom {zy}"
    assert ry <= zy + zh + 1e-9, f"y {ry} > zone top {zy + zh}"


@settings(max_examples=_MAX_EXAMPLES, phases=[Phase.generate, Phase.shrink])
@given(_coords, _coords)
def test_identity_projection_unchanged(x, y):
    rx, ry = tg.identity_projection(x, y)
    assert abs(rx - x) < _TOL, f"x changed: {rx} vs {x}"
    assert abs(ry - y) < _TOL, f"y changed: {ry} vs {y}"
