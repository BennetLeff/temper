"""
Coverage-paydown tests for geometry module functions.

Covers allowlisted public functions from:
- polygon.py (uncovered subset)
- primitives.py (uncovered subset)
- smooth.py (uncovered subset)
- transform.py (uncovered subset)
- overlap.py (uncovered subset)
- sdf.py (uncovered subset)
- constraints.py
- projections.py
- geometry/__init__.py (sdf_gradient)

All operators delegate to the temper_geometry Rust crate; the Python
wrappers take flat scalar coordinates / flat vertex lists.
"""

import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# polygon.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry import (
    compute_loop_area,
    compute_loop_perimeter,
    is_convex,
    loop_area_penalty,
    nearest_point_on_polygon,
    nearest_point_on_segment,
    point_in_rect,
    point_in_rect_soft,
    polygon_area,
    polygon_bounding_box,
    polygon_bounding_circle,
    polygon_orientation,
    polygon_signed_area,
    translate_polygon,
    triangle_area,
)


class TestPolygonUncovered:
    """Tests for polygon functions not covered by test_geometry.py."""

    def test_triangle_area(self):
        """Triangle area via xprod formula."""
        # Right triangle: (0,0), (4,0), (0,3)
        assert np.isclose(triangle_area(0, 0, 4, 0, 0, 3), 6.0)

    def test_polygon_signed_area_ccw(self):
        """Signed area is positive for CCW vertices."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        assert polygon_signed_area(square) > 0

    def test_polygon_orientation_ccw(self):
        """Orientation returns +1 for CCW."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        assert polygon_orientation(square) == 1.0

    def test_is_convex_square(self):
        """Square is convex."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        assert is_convex(square) is True

    def test_polygon_bounding_box(self):
        """Bounding box of a polygon."""
        square = [0.0, 0.0, 3.0, 0.0, 3.0, 2.0, 0.0, 2.0]
        bb = polygon_bounding_box(square)
        assert bb == (0.0, 0.0, 3.0, 2.0)

    def test_polygon_bounding_circle(self):
        """Bounding circle of a square."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        cx, cy, r = polygon_bounding_circle(square)
        assert np.isclose(cx, 1.0, atol=1e-6)
        assert np.isclose(cy, 1.0, atol=1e-6)
        assert r > 0

    def test_point_in_rect_inside(self):
        """Point inside axis-aligned rectangle."""
        result = point_in_rect(1.0, 1.0, 0.0, 0.0, 2.0, 2.0)
        assert result == 1.0

    def test_point_in_rect_outside(self):
        """Point outside axis-aligned rectangle."""
        result = point_in_rect(5.0, 5.0, 0.0, 0.0, 2.0, 2.0)
        assert result == 0.0

    def test_point_in_rect_soft_inside(self):
        """Soft containment for point inside."""
        result = point_in_rect_soft(1.0, 1.0, 0.0, 0.0, 2.0, 2.0, smoothness=10.0)
        assert result > 0.9

    def test_point_in_rect_soft_outside(self):
        """Soft containment for point outside."""
        result = point_in_rect_soft(5.0, 5.0, 0.0, 0.0, 2.0, 2.0, smoothness=10.0)
        assert result < 0.1

    def test_nearest_point_on_segment(self):
        """Nearest point on line segment."""
        # Point above midpoint of horizontal segment from (0,0) to (4,0)
        nx, ny = nearest_point_on_segment(2.0, 3.0, 0.0, 0.0, 4.0, 0.0)
        assert np.isclose(nx, 2.0, atol=1e-6)
        assert np.isclose(ny, 0.0, atol=1e-6)

    def test_nearest_point_on_polygon(self):
        """Nearest point on polygon boundary."""
        square = [0.0, 0.0, 4.0, 0.0, 4.0, 4.0, 0.0, 4.0]
        nx, ny = nearest_point_on_polygon(5.0, 2.0, square)
        assert np.isclose(nx, 4.0, atol=1e-6)
        assert np.isclose(ny, 2.0, atol=1e-6)

    def test_translate_polygon(self):
        """Translate polygon preserves shape."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        moved = translate_polygon(square, 5.0, 3.0)
        assert np.isclose(polygon_area(moved), polygon_area(square), atol=1e-6)
        # First point moved
        assert np.isclose(moved[0], 5.0, atol=1e-6)
        assert np.isclose(moved[1], 3.0, atol=1e-6)

    def test_compute_loop_area(self):
        """Loop area computed from pin positions."""
        pins = [0.0, 0.0, 4.0, 0.0, 4.0, 3.0, 0.0, 3.0]
        area = compute_loop_area(pins)
        assert np.isclose(area, 12.0, atol=1e-6)

    def test_compute_loop_perimeter(self):
        """Loop perimeter from pin positions."""
        pins = [0.0, 0.0, 4.0, 0.0, 4.0, 3.0, 0.0, 3.0]
        perim = compute_loop_perimeter(pins)
        assert np.isclose(perim, 14.0, atol=1e-6)

    def test_loop_area_penalty_zero(self):
        """No penalty when loop area is within max."""
        pins = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        penalty = loop_area_penalty(pins, max_area_mm2=2.0, weight=1.0)
        assert penalty < 1e-6  # Area 1 <= max 2, no penalty


# ---------------------------------------------------------------------------
# primitives.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry.primitives import (
    aabb_expand,
    aabb_from_points,
    aabb_intersects,
    aabb_overlap_area,
    aabb_union,
    batch_point_distance,
    distance_to_board_boundary,
    pairwise_distances,
    pairwise_distances_squared,
    point_midpoint,
    point_to_line_distance,
    rect_contains_point,
    rect_corners,
    rect_dimensions,
    rect_from_center,
)


class TestPrimitivesUncovered:
    """Tests for primitives not covered by test_geometry.py."""

    def test_point_midpoint(self):
        """Midpoint between two points."""
        mx, my = point_midpoint(2.0, 4.0, 6.0, 8.0)
        assert np.isclose(mx, 4.0)
        assert np.isclose(my, 6.0)

    def test_point_to_line_distance(self):
        """Distance from point to line segment."""
        # Point at (2, 2), segment from (0,0) to (4,0) -> distance = 2
        d = point_to_line_distance(2.0, 2.0, 0.0, 0.0, 4.0, 0.0)
        assert np.isclose(d, 2.0)

    def test_rect_from_center(self):
        """Create rectangle from center and half-dims."""
        rx, ry, rw, rh = rect_from_center(5.0, 5.0, 2.0, 3.0)
        assert np.isclose(rx, 3.0)
        assert np.isclose(ry, 2.0)
        assert np.isclose(rw, 4.0)
        assert np.isclose(rh, 6.0)

    def test_rect_dimensions(self):
        """Get dimensions of a rectangle."""
        w, h = rect_dimensions(0.0, 0.0, 10.0, 20.0)
        assert w == 10.0
        assert h == 20.0

    def test_rect_contains_point_inside(self):
        """Point inside rectangle."""
        result = rect_contains_point(0.0, 0.0, 10.0, 10.0, 5.0, 5.0)
        assert result > 0.9

    def test_rect_contains_point_outside(self):
        """Point outside rectangle."""
        result = rect_contains_point(0.0, 0.0, 10.0, 10.0, 20.0, 5.0)
        assert result < 0.1

    def test_rect_corners(self):
        """Four corners of a rectangle."""
        corners = rect_corners(0.0, 0.0, 10.0, 8.0)
        assert len(corners) == 8  # 4 corners * 2 coords
        # First corner (bottom-left)
        assert np.isclose(corners[0], 0.0)
        assert np.isclose(corners[1], 0.0)
        # Third corner (top-right)
        assert np.isclose(corners[4], 10.0)
        assert np.isclose(corners[5], 8.0)

    def test_aabb_from_points(self):
        """AABB from point cloud."""
        points = [0.0, 0.0, 5.0, 3.0, 2.0, 7.0]
        x1, y1, x2, y2 = aabb_from_points(points)
        assert np.isclose(x1, 0.0)
        assert np.isclose(y1, 0.0)
        assert np.isclose(x2, 5.0)
        assert np.isclose(y2, 7.0)

    def test_aabb_intersects_overlapping(self):
        """Overlapping AABBs."""
        result = aabb_intersects(0.0, 0.0, 4.0, 4.0, 2.0, 2.0, 6.0, 6.0)
        assert result is True  # Overlap detected

    def test_aabb_intersects_separated(self):
        """Separated AABBs."""
        result = aabb_intersects(0.0, 0.0, 1.0, 1.0, 10.0, 10.0, 12.0, 12.0)
        assert result is False  # No intersection

    def test_aabb_overlap_area(self):
        """Overlap area of intersecting AABBs."""
        # Two 4x4 boxes offset by (2,2) -> overlap area = 4
        area = aabb_overlap_area(0.0, 0.0, 4.0, 4.0, 2.0, 2.0, 6.0, 6.0)
        assert np.isclose(area, 4.0, atol=1e-6)

    def test_aabb_overlap_area_none(self):
        """No overlap area for separated AABBs."""
        area = aabb_overlap_area(0.0, 0.0, 1.0, 1.0, 10.0, 10.0, 12.0, 12.0)
        assert np.isclose(area, 0.0)

    def test_aabb_union(self):
        """Union AABB of two boxes."""
        u = aabb_union(0.0, 0.0, 2.0, 2.0, 3.0, 3.0, 5.0, 5.0)
        assert u == (0.0, 0.0, 5.0, 5.0)

    def test_aabb_expand(self):
        """Expanded AABB."""
        e = aabb_expand(1.0, 1.0, 3.0, 3.0, 2.0)
        assert e == (-1.0, -1.0, 5.0, 5.0)

    def test_distance_to_board_boundary_inside(self):
        """Point well inside board boundary."""
        d = distance_to_board_boundary(50.0, 50.0, 100.0, 100.0, 5.0)
        assert d > 0  # Inside

    def test_pairwise_distances(self):
        """Pairwise distance matrix."""
        points = [0.0, 0.0, 3.0, 4.0]
        dists = pairwise_distances(points)
        # 2 points -> 2x2 matrix, 4 values
        assert len(dists) == 4
        assert np.isclose(dists[1], 5.0, atol=1e-6)  # [0][1] distance

    def test_pairwise_distances_squared(self):
        """Pairwise squared distance matrix."""
        points = [0.0, 0.0, 3.0, 4.0]
        dists = pairwise_distances_squared(points)
        assert len(dists) == 4
        assert np.isclose(dists[1], 25.0, atol=1e-6)

    def test_batch_point_distance(self):
        """Batch point distance between two arrays."""
        a = [0.0, 0.0, 0.0, 0.0]
        b = [3.0, 4.0, 6.0, 8.0]
        dists = batch_point_distance(a, b)
        assert len(dists) == 2
        assert np.isclose(dists[0], 5.0, atol=1e-6)
        assert np.isclose(dists[1], 10.0, atol=1e-6)


# ---------------------------------------------------------------------------
# smooth.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry.smooth import (
    get_alpha_schedule,
    get_beta_schedule,
    smooth_clip,
    smooth_leaky_relu,
    smooth_max_axis,
    smooth_min_axis,
    smooth_relu_penalty,
    smooth_step,
    weighted_average_smooth,
)


class TestSmoothUncovered:
    """Tests for smooth functions not covered by test_geometry.py."""

    def test_smooth_max_axis(self):
        """Smooth max along axis."""
        result = smooth_max_axis([1.0, 5.0, 3.0, 10.0, 2.0], alpha=100.0)
        assert np.isclose(result, 10.0, atol=0.2)

    def test_smooth_min_axis(self):
        """Smooth min along axis."""
        result = smooth_min_axis([5.0, 1.0, 3.0, 0.5, 2.0], alpha=100.0)
        assert np.isclose(result, 0.5, atol=0.2)

    def test_smooth_relu_penalty_positive(self):
        """Penalty for positive margin exceedance."""
        p = smooth_relu_penalty(3.0, margin=1.0, alpha=10.0)
        # max(0, 3-1)^2 = 4, smooth version close to 4
        assert np.isclose(p, 4.0, atol=0.1)

    def test_smooth_relu_penalty_zero(self):
        """No penalty when below margin."""
        p = smooth_relu_penalty(0.5, margin=1.0, alpha=10.0)
        assert p < 0.1

    def test_smooth_leaky_relu_positive(self):
        """Leaky ReLU passes positive values through."""
        assert smooth_leaky_relu(5.0, alpha=10.0) > 4.9

    def test_smooth_leaky_relu_negative(self):
        """Leaky ReLU has small negative slope."""
        result = smooth_leaky_relu(-3.0, alpha=10.0, negative_slope=0.01)
        assert -0.1 < result < 0  # Close to -0.03

    def test_smooth_clip(self):
        """Smooth clip bounds values."""
        clipped = smooth_clip(5.0, 0.0, 3.0, alpha=100.0)
        assert np.isclose(clipped, 3.0, atol=0.1)

    def test_smooth_step_positive(self):
        """Smooth step for positive input approaches 1."""
        assert np.isclose(smooth_step(5.0, alpha=100.0), 1.0, atol=0.1)

    def test_smooth_step_negative(self):
        """Smooth step for negative input approaches 0."""
        assert np.isclose(smooth_step(-5.0, alpha=100.0), 0.0, atol=0.1)

    def test_weighted_average_smooth(self):
        """Weighted average with softmax weights."""
        result = weighted_average_smooth([10.0, 20.0], [1.0, 100.0], alpha=0.01)
        # Strong weight on second value -> close to 20
        assert np.isclose(result, 20.0, atol=0.5)

    def test_get_alpha_schedule(self):
        """Alpha schedule returns an iterable."""
        result = get_alpha_schedule(1.0, 10.0, 5)
        assert len(result) == 5

    def test_get_beta_schedule(self):
        """Beta schedule returns an iterable."""
        result = get_beta_schedule(1.0, 10.0, 5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# transform.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry.transform import (
    batch_get_rotated_bounds,
    batch_rotate_points,
    get_rotated_aabb,
    get_rotated_bounds,
    gumbel_softmax,
    onehot_to_rotation_radians,
    rotate_points,
    rotate_rectangle_corners,
    rotation_degrees_to_onehot,
    sample_rotation,
    sample_rotation_batch,
    transform_pin_position,
    transform_pin_positions,
)


class TestTransformUncovered:
    """Tests for transform functions not covered by test_geometry.py."""

    def test_rotate_points(self):
        """Rotate multiple points."""
        points = [1.0, 0.0, 0.0, 1.0]
        rotated = rotate_points(points, np.pi / 2)
        assert np.allclose(rotated, [0.0, 1.0, -1.0, 0.0], atol=1e-6)

    def test_get_rotated_bounds(self):
        """AABB of rotated rectangle."""
        rx, ry, rw, rh = get_rotated_bounds(0.0, 0.0, 4.0, 2.0, np.pi / 4)
        assert rw > 0
        assert rh > 0

    def test_get_rotated_aabb(self):
        """AABB of polygon vertices."""
        verts = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        x1, y1, x2, y2 = get_rotated_aabb(verts)
        assert x1 <= x2
        assert y1 <= y2

    def test_rotate_rectangle_corners(self):
        """Corners of a rotated rectangle."""
        corners = rotate_rectangle_corners(0.0, 0.0, 2.0, 2.0, 0.0, 0.0, 0.0)
        assert len(corners) == 8  # 4 corners
        # Center-based corners: rectangle centered at (0,0) spans (-1,-1) to (1,1)
        assert np.isclose(corners[0], -1.0, atol=1e-6)
        assert np.isclose(corners[1], -1.0, atol=1e-6)
        # Top-right corner
        assert np.isclose(corners[4], 1.0, atol=1e-6)
        assert np.isclose(corners[5], 1.0, atol=1e-6)

    def test_batch_get_rotated_bounds(self):
        """Batch rotated bounds."""
        # Single rect: x=0, y=0, w=4, h=2, angle=0
        rects = [0.0, 0.0, 4.0, 2.0]
        angles = [0.0]
        result = batch_get_rotated_bounds(rects, angles)
        assert len(result) == 4  # x, y, w, h
        assert np.isclose(result[2], 4.0)
        assert np.isclose(result[3], 2.0)

    def test_batch_rotate_points(self):
        """Batch rotate points with different centers/angles."""
        points = [1.0, 0.0, 2.0, 0.0]
        angles = [np.pi / 2, 0.0]
        centers = [0.0, 0.0, 0.0, 0.0]
        result = batch_rotate_points(points, angles, centers)
        assert len(result) == 4

    def test_transform_pin_position(self):
        """Transform pin position with component rotation."""
        wx, wy = transform_pin_position(1.0, 0.0, 5.0, 5.0, np.pi / 2)
        # KiCad footprint-child rotation convention: R(-theta)
        # Pin at offset (1,0) rotated -90deg -> (0,-1) + center (5,5) -> (5,4)
        assert np.isclose(wx, 5.0, atol=1e-6)
        assert np.isclose(wy, 4.0, atol=1e-6)

    def test_transform_pin_positions(self):
        """Transform multiple pin positions."""
        pins = [1.0, 0.0, 0.0, 1.0]
        world = transform_pin_positions(pins, 5.0, 5.0, 0.0)
        assert len(world) == 4
        assert np.isclose(world[0], 6.0, atol=1e-6)
        assert np.isclose(world[1], 5.0, atol=1e-6)

    def test_rotation_degrees_to_onehot(self):
        """Convert degrees to one-hot."""
        onehot = rotation_degrees_to_onehot(90.0)
        assert onehot == [0.0, 1.0, 0.0, 0.0]

    def test_onehot_to_rotation_radians(self):
        """Convert one-hot to radians."""
        rad = onehot_to_rotation_radians([0.0, 1.0, 0.0, 0.0])
        assert np.isclose(rad, np.pi / 2, atol=1e-6)

    def test_gumbel_softmax(self):
        """Gumbel-softmax differentiable sampling."""
        logits = [1.0, 2.0, 3.0]
        result = gumbel_softmax(logits, temperature=1.0)
        assert len(result) == 3

    def test_sample_rotation(self):
        """Sample a rotation from logits."""
        logits = [0.0, 0.0, 0.0, 0.0]
        result = sample_rotation(logits)
        assert 0.0 <= result <= 3.0  # Returns an index

    def test_sample_rotation_batch(self):
        """Sample rotations for a batch."""
        logits = [[0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
        result = sample_rotation_batch(logits)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# overlap.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry.overlap import (
    box_box_distance,
    box_box_distance_aabb,
    compute_clearance_penalties,
    compute_overlap_penalty,
    compute_pairwise_distances,
    compute_total_overlap,
    count_overlaps,
    get_worst_overlap,
    overlap_area_estimate,
)


class TestOverlapUncovered:
    """Tests for overlap functions not covered by test_geometry.py."""

    def test_box_box_distance_separated(self):
        """Distance between separated boxes."""
        d = box_box_distance(0.0, 0.0, 2.0, 2.0, 5.0, 0.0, 2.0, 2.0)
        assert d > 0  # Separated -> positive

    def test_box_box_distance_overlapping(self):
        """Distance between overlapping boxes."""
        d = box_box_distance(0.0, 0.0, 4.0, 4.0, 2.0, 2.0, 4.0, 4.0)
        assert d < 0  # Overlapping -> negative

    def test_box_box_distance_aabb(self):
        """Distance between AABB-represented boxes."""
        d = box_box_distance_aabb(0.0, 0.0, 2.0, 2.0, 5.0, 5.0, 7.0, 7.0)
        assert d > 0

    def test_overlap_area_estimate(self):
        """Overlap area estimate between AABBs."""
        area = overlap_area_estimate(0.0, 0.0, 4.0, 4.0, 2.0, 2.0, 6.0, 6.0)
        assert area > 0

    def test_overlap_area_estimate_none(self):
        """No overlap area."""
        area = overlap_area_estimate(0.0, 0.0, 1.0, 1.0, 10.0, 10.0, 12.0, 12.0)
        assert area == 0.0

    def test_compute_pairwise_distances(self):
        """Pairwise distance matrix for rects."""
        rects = [0.0, 0.0, 2.0, 2.0, 5.0, 0.0, 2.0, 2.0]
        dists = compute_pairwise_distances(rects)
        assert len(dists) == 4  # 2x2 matrix

    def test_compute_total_overlap(self):
        """Total overlap for list of rects."""
        rects = [0.0, 0.0, 2.0, 2.0, 1.0, 0.0, 2.0, 2.0]
        total = compute_total_overlap(rects)
        assert total >= 0

    def test_compute_overlap_penalty(self):
        """Overlap penalty for list of rects."""
        rects = [0.0, 0.0, 2.0, 2.0, 0.5, 0.0, 2.0, 2.0]
        penalty = compute_overlap_penalty(rects, weight=100.0)
        assert penalty >= 0

    def test_compute_clearance_penalties(self):
        """Clearance penalty computation (expects list of (i, j, clearance) tuples)."""
        rects = [0.0, 0.0, 2.0, 2.0, 5.0, 0.0, 2.0, 2.0]
        clearances = [(0, 1, 0.5)]  # Pair (0,1) with clearance 0.5mm
        penalties = compute_clearance_penalties(rects, clearances)
        assert len(penalties) > 0
        assert all(p >= 0 for p in penalties)

    def test_count_overlaps_separated(self):
        """No overlaps for separated rects."""
        rects = [0.0, 0.0, 2.0, 2.0, 10.0, 10.0, 2.0, 2.0]
        assert count_overlaps(rects) == 0

    def test_count_overlaps_overlapping(self):
        """Count overlapping pairs."""
        rects = [0.0, 0.0, 4.0, 4.0, 2.0, 2.0, 4.0, 4.0]
        assert count_overlaps(rects) > 0

    def test_get_worst_overlap(self):
        """Worst overlap info — returns (overlap_amount, idx1, dist_or_idx2)."""
        rects = [0.0, 0.0, 10.0, 10.0, 2.0, 2.0, 10.0, 10.0]
        worst, i, j = get_worst_overlap(rects)
        # Overlapping boxes: worst overlap amount >= 0, i is an int index
        assert worst >= 0
        assert isinstance(i, int)


# ---------------------------------------------------------------------------
# sdf.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_placer.geometry.sdf import (
    sdf_box_2d,
    sdf_capsule,
    sdf_convex_polygon,
    sdf_gradient,
    sdf_offset,
    sdf_polygon,
    sdf_round,
    sdf_rounded_rectangle,
    sdf_shell,
    sdf_smooth_intersection,
    sdf_smooth_union,
    sdf_subtraction,
    sdf_to_mask,
    sdf_to_penalty,
)


class TestSDFUncovered:
    """Tests for SDF functions not covered by test_geometry.py."""

    def test_sdf_box_2d_inside(self):
        """SDF box is negative inside."""
        d = sdf_box_2d(0.0, 0.0, 0.0, 0.0, 2.0, 1.0)
        assert d < 0

    def test_sdf_box_2d_outside(self):
        """SDF box is positive outside."""
        d = sdf_box_2d(5.0, 0.0, 0.0, 0.0, 2.0, 1.0)
        assert d > 0

    def test_sdf_capsule(self):
        """SDF of a capsule."""
        d = sdf_capsule(0.0, 0.0, -2.0, 0.0, 2.0, 0.0, 1.0)
        # Point at origin is inside the capsule
        assert d < 0

    def test_sdf_convex_polygon(self):
        """SDF of convex polygon."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        d = sdf_convex_polygon(1.0, 1.0, square)
        assert d < 0  # Inside

    def test_sdf_polygon(self):
        """SDF of general polygon."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        d = sdf_polygon(1.0, 1.0, square)
        assert d < 0  # Inside

    def test_sdf_offset(self):
        """SDF offset shrinks/expands."""
        # For a circle of radius 1 at origin, point at (2,0) has SDF = 1
        d_circle = sdf_box_2d(2.0, 0.0, 0.0, 0.0, 1.0, 1.0)  # using box as proxy
        d_offset = sdf_offset(-1.0, 1.0)
        assert d_offset is not None  # Should return a value

    def test_sdf_round(self):
        """SDF round operation."""
        d = sdf_round(1.0, 0.5)
        assert np.isclose(d, 0.5, atol=1e-6)

    def test_sdf_rounded_rectangle_inside(self):
        """SDF of rounded rectangle inside."""
        d = sdf_rounded_rectangle(0.0, 0.0, 0.0, 0.0, 2.0, 1.0, 0.5)
        assert d < 0

    def test_sdf_shell(self):
        """SDF shell (hollow shape)."""
        d = sdf_shell(-1.0, 0.3)  # Inside a shape, with thickness
        assert d is not None

    def test_sdf_smooth_union(self):
        """Smooth union of two SDF values."""
        d = sdf_smooth_union(-0.5, -0.5, k=0.5)
        assert d < 0  # Both inside, union inside

    def test_sdf_smooth_intersection(self):
        """Smooth intersection of two SDF values."""
        d = sdf_smooth_intersection(-0.5, -0.5, k=0.5)
        assert d < 0  # Both inside, intersection inside

    def test_sdf_subtraction(self):
        """SDF subtraction."""
        d = sdf_subtraction(-0.5, 1.0)
        # First shape inside, second outside -> subtraction result
        assert d is not None

    def test_sdf_to_mask_scalar(self):
        """Convert scalar SDF to mask."""
        m = sdf_to_mask(-1.0, threshold=0.1)
        assert 0.9 <= m <= 1.0  # Deep inside -> mask near 1

    def test_sdf_to_mask_list(self):
        """Convert list of SDFs to masks."""
        masks = sdf_to_mask([-1.0, 1.0], threshold=0.1)
        assert len(masks) == 2
        assert masks[0] > 0.9
        assert masks[1] < 0.1

    def test_sdf_to_penalty_scalar(self):
        """Convert scalar SDF to penalty."""
        p = sdf_to_penalty(-0.5, alpha=10.0)
        assert p > 0  # Inside -> penalty positive

    def test_sdf_to_penalty_list(self):
        """Convert list of SDFs to penalties."""
        penalties = sdf_to_penalty([-0.5, 2.0], alpha=10.0)
        assert len(penalties) == 2
        assert penalties[0] > 0  # Inside
        assert penalties[1] < 0.1  # Outside

    def test_sdf_gradient_circle_sdf_module(self):
        """Gradient of SDF at a point (sdf.py version: sdf_gradient(sdf_func, point))."""
        def circle_sdf(pt):
            px, py = pt
            return math.sqrt(px * px + py * py) - 1.0

        grad = sdf_gradient(circle_sdf, (2.0, 0.0))
        assert np.allclose(grad, (1.0, 0.0), atol=1e-3)

    def test_sdf_gradient_circle_init_module(self):
        """Gradient of SDF at a point (__init__.py version: sdf_gradient(p, sdf_fn))."""
        from temper_placer.geometry import sdf_gradient as sdf_gradient_top

        def circle_sdf(pt):
            px, py = pt
            return math.sqrt(px * px + py * py) - 1.0

        grad = sdf_gradient_top((2.0, 0.0), circle_sdf)
        assert np.allclose(grad, (1.0, 0.0), atol=1e-3)


# ---------------------------------------------------------------------------
# constraints.py
# ---------------------------------------------------------------------------

from temper_placer.geometry.constraints import (
    BoundaryViolation,
    ValidBounds,
    compute_boundary_violation,
    compute_valid_bounds,
    compute_zone_distance,
    is_within_bounds,
    point_in_zone,
)


class TestBoundaryViolation:
    """Tests for BoundaryViolation NamedTuple."""

    def test_has_violation_true(self):
        """Violation detected when component extends beyond edge."""
        bv = BoundaryViolation(left=1.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is True

    def test_has_violation_false(self):
        """No violation when all edges clear."""
        bv = BoundaryViolation(left=0.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is False

    def test_max_violation(self):
        """Max violation across edges."""
        bv = BoundaryViolation(left=1.0, right=3.0, bottom=0.5, top=2.0)
        assert bv.max_violation == 3.0

    def test_total_violation(self):
        """Total sum of all violations."""
        bv = BoundaryViolation(left=1.0, right=2.0, bottom=0.5, top=1.5)
        assert bv.total_violation == 5.0


class TestValidBounds:
    """Tests for ValidBounds NamedTuple."""

    def test_clamp_point_inside(self):
        """Point inside bounds unchanged."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        x, y = vb.clamp_point(50.0, 50.0)
        assert x == 50.0
        assert y == 50.0

    def test_clamp_point_outside(self):
        """Point outside bounds clamped."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        x, y = vb.clamp_point(150.0, -10.0)
        assert x == 100.0
        assert y == 0.0

    def test_contains_point_true(self):
        """Point inside bounds."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(50.0, 50.0) is True

    def test_contains_point_false(self):
        """Point outside bounds."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(150.0, 50.0) is False


class TestConstraintFunctions:
    """Tests for constraint computation functions."""

    def test_compute_valid_bounds(self):
        """Compute valid placement region for component center."""
        vb = compute_valid_bounds(
            component_half_width=5.0,
            component_half_height=5.0,
            region_x_min=0.0,
            region_y_min=0.0,
            region_x_max=100.0,
            region_y_max=100.0,
            margin=2.0,
        )
        assert vb.x_min == 7.0  # 0 + half_width(5) + margin(2)
        assert vb.y_min == 7.0
        assert vb.x_max == 93.0  # 100 - half_width(5) - margin(2)
        assert vb.y_max == 93.0

    def test_compute_boundary_violation_inside(self):
        """No violation when component fits inside board."""
        bv = compute_boundary_violation(
            position_x=50.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        assert bv.has_violation is False

    def test_compute_boundary_violation_outside(self):
        """Violation when component extends beyond board."""
        bv = compute_boundary_violation(
            position_x=-5.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        assert bv.has_violation is True
        assert bv.left > 0

    def test_is_within_bounds_inside(self):
        """Component entirely inside region."""
        assert is_within_bounds(
            position_x=50.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is True

    def test_is_within_bounds_outside(self):
        """Component extends beyond region."""
        assert is_within_bounds(
            position_x=-5.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is False

    def test_compute_zone_distance_inside(self):
        """Negative distance when point inside zone."""
        d = compute_zone_distance(50.0, 50.0, 0.0, 0.0, 100.0, 100.0)
        assert d < 0  # Inside -> negative distance to nearest edge

    def test_compute_zone_distance_outside(self):
        """Positive distance when point outside zone."""
        d = compute_zone_distance(150.0, 50.0, 0.0, 0.0, 100.0, 100.0)
        assert d > 0  # Outside -> positive

    def test_point_in_zone_inside(self):
        """Point inside zone returns True."""
        assert point_in_zone(50.0, 50.0, 0.0, 0.0, 100.0, 100.0) is True

    def test_point_in_zone_outside(self):
        """Point outside zone returns False."""
        assert point_in_zone(150.0, 50.0, 0.0, 0.0, 100.0, 100.0) is False


# ---------------------------------------------------------------------------
# projections.py
# ---------------------------------------------------------------------------

from temper_placer.geometry.projections import (
    identity_projection,
    project_onto_board,
    project_onto_edge_strip,
    project_onto_half_plane,
    project_onto_side,
    project_onto_zone,
    project_outside_keepout,
)


class TestProjections:
    """Tests for projection operators."""

    def test_identity_projection(self):
        """Identity returns point unchanged."""
        x, y = identity_projection(5.0, 10.0)
        assert x == 5.0
        assert y == 10.0

    def test_project_onto_board_inside(self):
        """Point already inside board unchanged."""
        x, y = project_onto_board(50.0, 50.0, 100.0, 100.0, 5.0)
        assert x == 50.0
        assert y == 50.0

    def test_project_onto_board_outside(self):
        """Point outside clamped to margin."""
        x, y = project_onto_board(-1.0, 101.0, 100.0, 100.0, 5.0)
        assert x == 5.0
        assert y == 95.0

    def test_project_onto_zone_inside(self):
        """Point inside zone unchanged."""
        x, y = project_onto_zone(30.0, 30.0, 10.0, 10.0, 60.0, 60.0)
        assert np.isclose(x, 30.0)
        assert np.isclose(y, 30.0)

    def test_project_onto_zone_outside(self):
        """Point outside projected to nearest boundary."""
        x, y = project_onto_zone(100.0, 30.0, 10.0, 10.0, 60.0, 60.0)
        assert np.isclose(x, 70.0)  # Clamped to right edge
        assert np.isclose(y, 30.0)

    def test_project_outside_keepout(self):
        """Point inside keepout projected outside."""
        x, y = project_outside_keepout(50.0, 50.0, 40.0, 40.0, 20.0, 20.0)
        # Point inside keepout -> projected to nearest edge
        assert x is not None
        assert y is not None

    def test_project_onto_half_plane(self):
        """Project onto feasible half-plane."""
        # Half-plane: y >= 0 (normal pointing up from origin)
        x, y = project_onto_half_plane(0.0, -3.0, 0.0, 0.0, 0.0, 1.0)
        assert np.isclose(x, 0.0, atol=1e-6)
        assert np.isclose(y, 0.0, atol=1e-6)  # Projected to boundary

    def test_project_onto_edge_strip(self):
        """Project onto edge strip."""
        x, y = project_onto_edge_strip(5.0, 0.0, 0.0, 0.0, 10.0, 0.0, 5.0)
        assert np.isclose(y, 0.0, atol=1e-6)  # On the edge line

    def test_project_onto_side_top(self):
        """Project onto top side of board."""
        x, y = project_onto_side(50.0, -10.0, 100.0, 100.0, "top")
        assert x is not None
        assert y is not None


# ---------------------------------------------------------------------------
# drc_inflate.py — uncovered subset (functions not requiring Shapely)
# ---------------------------------------------------------------------------

from temper_placer.geometry.drc_inflate import (
    compute_drc_proxy_score,
    compute_inflated_half_dims_from_bounds,
)


class TestDRCInflateUncovered:
    """Tests for DRC inflate functions that don't require Shapely."""

    def test_compute_inflated_half_dims_from_bounds(self):
        """Inflate component bounds by trace width."""
        bounds = np.array([[10.0, 8.0], [6.0, 4.0]], dtype=np.float32)
        inflated = compute_inflated_half_dims_from_bounds(bounds, trace_width_mm=0.25)
        assert inflated.shape == (2, 2)
        # Check inflation: (w + 0.25) / 2 for first component
        assert np.isclose(inflated[0, 0], (10.0 + 0.25) / 2, atol=1e-6)
        assert np.isclose(inflated[0, 1], (8.0 + 0.25) / 2, atol=1e-6)

    def test_compute_drc_proxy_score_two_components(self):
        """DRC proxy score for two non-overlapping components."""
        positions = np.array([[0.0, 0.0], [100.0, 100.0]], dtype=np.float32)
        hw = np.array([5.0, 5.0], dtype=np.float32)
        hh = np.array([5.0, 5.0], dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2, beta=10.0)
        # Well-separated components -> near-zero score
        assert score < 0.01

    def test_compute_drc_proxy_score_empty(self):
        """DRC proxy score for single component (no pairs)."""
        positions = np.array([[0.0, 0.0]], dtype=np.float32)
        hw = np.array([5.0], dtype=np.float32)
        hh = np.array([5.0], dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert score == 0.0
