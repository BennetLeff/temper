"""
Unit tests for the geometry engine.

Tests cover:
- Rotation correctness at 0°, 90°, 180°, 270°
- SDF signs (negative inside, positive outside, zero on boundary)
- Overlap detection for overlapping and non-overlapping boxes
- Smooth min/max approximation accuracy
- Polygon area for known shapes

All operators delegate to the temper_geometry Rust crate; the Python
wrappers take flat scalar coordinates / flat vertex lists.
"""

import numpy as np

from temper_placer.geometry.overlap import (
    check_clearance_violation,
    component_overlap_amount,
)
from temper_placer.geometry.polygon import (
    point_in_polygon_soft,
    point_in_polygon_winding,
    polygon_area,
    polygon_centroid,
    polygon_perimeter,
    rotate_polygon,
    scale_polygon,
)

# Import geometry functions
from temper_placer.geometry.primitives import (
    distance_to_rect_edge,
    distance_to_specific_edge,
    point_distance,
    point_distance_squared,
    points_centroid,
    rect_area,
    rect_center,
)
from temper_placer.geometry.sdf import (
    sdf_circle,
    sdf_intersection,
    sdf_rectangle,
    sdf_union,
)
from temper_placer.geometry.smooth import (
    hpwl_smooth,
    smooth_abs,
    smooth_max,
    smooth_max_pair,
    smooth_min,
    smooth_min_pair,
    smooth_relu,
)
from temper_placer.geometry.transform import (
    get_rotation_matrix,
    onehot_to_rotation_degrees,
    rotate_point,
    rotation_index_to_onehot,
)

# =============================================================================
# Primitives Tests
# =============================================================================


class TestPrimitives:
    """Tests for basic geometric primitives."""

    def test_point_distance(self):
        """Test Euclidean distance between points."""
        assert np.isclose(point_distance(0.0, 0.0, 3.0, 4.0), 5.0)

    def test_point_distance_squared(self):
        """Test squared distance (avoids sqrt)."""
        assert np.isclose(point_distance_squared(0.0, 0.0, 3.0, 4.0), 25.0)

    def test_points_centroid(self):
        """Test centroid of point cloud."""
        # Flat list of [x1, y1, x2, y2, ...]
        centroid = points_centroid([0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0])
        assert centroid == (1.0, 1.0)

    def test_rect_center(self):
        """Test rectangle center from position and size."""
        center = rect_center(0.0, 0.0, 10.0, 20.0)
        assert center == (5.0, 10.0)

    def test_rect_area(self):
        """Test rectangle area calculation."""
        # rect_area takes position and size, not just width and height
        assert rect_area(0.0, 0.0, 5.0, 10.0) == 50.0

    def test_distance_to_rect_edge_inside(self):
        """Test distance to edge for point inside rectangle."""
        d = distance_to_rect_edge(5.0, 5.0, 0.0, 0.0, 10.0, 10.0)
        assert np.isclose(d, 5.0)  # Center of 10x10 box

    def test_distance_to_specific_edge(self):
        """Test distance to specific edges."""
        assert np.isclose(distance_to_specific_edge(3.0, 7.0, 0.0, 0.0, 10.0, 10.0, "LEFT"), 3.0)
        assert np.isclose(distance_to_specific_edge(3.0, 7.0, 0.0, 0.0, 10.0, 10.0, "RIGHT"), 7.0)
        assert np.isclose(distance_to_specific_edge(3.0, 7.0, 0.0, 0.0, 10.0, 10.0, "BOTTOM"), 7.0)
        assert np.isclose(distance_to_specific_edge(3.0, 7.0, 0.0, 0.0, 10.0, 10.0, "TOP"), 3.0)


# =============================================================================
# Rotation Tests
# =============================================================================


class TestRotation:
    """Tests for rotation transforms (radians API)."""

    def test_rotation_0_degrees(self):
        """Test 0° rotation (identity)."""
        rotated = rotate_point(1.0, 0.0, 0.0)
        assert np.allclose(rotated, (1.0, 0.0), atol=1e-6)

    def test_rotation_90_degrees(self):
        """Test 90° CCW rotation."""
        rotated = rotate_point(1.0, 0.0, np.pi / 2)
        assert np.allclose(rotated, (0.0, 1.0), atol=1e-6)

    def test_rotation_180_degrees(self):
        """Test 180° rotation."""
        rotated = rotate_point(1.0, 0.0, np.pi)
        assert np.allclose(rotated, (-1.0, 0.0), atol=1e-6)

    def test_rotation_270_degrees(self):
        """Test 270° CCW rotation."""
        rotated = rotate_point(1.0, 0.0, 3 * np.pi / 2)
        assert np.allclose(rotated, (0.0, -1.0), atol=1e-6)

    def test_rotation_around_center(self):
        """Test rotation around non-origin center."""
        rotated = rotate_point(2.0, 0.0, np.pi / 2, 1.0, 0.0)
        # Point is 1 unit right of center, after 90° CCW should be 1 unit above
        assert np.allclose(rotated, (1.0, 1.0), atol=1e-6)

    def test_rotation_matrix_orthogonal(self):
        """Verify rotation matrices are orthogonal (R @ R.T = I)."""
        for angle in (0.0, np.pi / 2, np.pi, 3 * np.pi / 2):
            flat = get_rotation_matrix(angle)
            R = np.array(flat).reshape(2, 2)
            assert np.allclose(R @ R.T, np.eye(2), atol=1e-6)

    def test_onehot_encoding_roundtrip(self):
        """Test one-hot encoding roundtrip."""
        for i in range(4):
            onehot = rotation_index_to_onehot(i)
            degrees = onehot_to_rotation_degrees(onehot)
            expected = i * 90.0
            assert np.isclose(degrees, expected, atol=1e-6)


class TestSDF:
    """Tests for Signed Distance Functions."""

    def test_sdf_circle_inside(self):
        """Test SDF is negative inside circle."""
        d = sdf_circle(0.3, 0.0, 0.0, 0.0, 1.0)
        assert d < 0  # Inside is negative

    def test_sdf_circle_outside(self):
        """Test SDF is positive outside circle."""
        d = sdf_circle(2.0, 0.0, 0.0, 0.0, 1.0)
        assert d > 0  # Outside is positive

    def test_sdf_circle_boundary(self):
        """Test SDF is zero on circle boundary."""
        d = sdf_circle(1.0, 0.0, 0.0, 0.0, 1.0)
        assert np.isclose(d, 0.0, atol=1e-6)

    def test_sdf_circle_distance_correct(self):
        """Test SDF returns correct distance values."""
        d = sdf_circle(3.0, 0.0, 0.0, 0.0, 1.0)
        assert np.isclose(d, 2.0)  # 3 - 1 = 2

    def test_sdf_rectangle_inside(self):
        """Test rectangle SDF is negative inside."""
        # sdf_rectangle takes point, center, half-width, half-height
        d = sdf_rectangle(0.5, 0.5, 0.0, 0.0, 2.0, 1.0)  # 4x2 rectangle (half-sizes 2x1)
        assert d < 0

    def test_sdf_rectangle_outside(self):
        """Test rectangle SDF is positive outside."""
        d = sdf_rectangle(5.0, 0.0, 0.0, 0.0, 2.0, 1.0)  # 4x2 rectangle
        assert d > 0

    def test_sdf_rectangle_boundary(self):
        """Test rectangle SDF is zero on boundary."""
        d = sdf_rectangle(2.0, 0.0, 0.0, 0.0, 2.0, 1.0)  # On right edge of 4-wide rectangle
        assert np.isclose(d, 0.0, atol=1e-4)  # Relaxed tolerance for numerical precision

    def test_sdf_union(self):
        """Test SDF union (min of two SDFs)."""
        # Point between two circles
        d1 = sdf_circle(1.5, 0.0, 0.0, 0.0, 1.0)
        d2 = sdf_circle(1.5, 0.0, 3.0, 0.0, 1.0)
        d_union = sdf_union(d1, d2)
        assert np.isclose(d_union, min(d1, d2))

    def test_sdf_intersection(self):
        """Test SDF intersection (max of two SDFs)."""
        d1 = sdf_circle(0.0, 0.0, -0.5, 0.0, 1.0)
        d2 = sdf_circle(0.0, 0.0, 0.5, 0.0, 1.0)
        d_intersection = sdf_intersection(d1, d2)
        # Point is inside both circles, intersection should be negative
        assert d_intersection < 0


class TestSmoothFunctions:
    """Tests for smooth (differentiable) approximations."""

    def test_smooth_min_approximation(self):
        """Test smooth_min approximates min."""
        # With high alpha, should be close to true min
        s_min = smooth_min(1.0, 5.0, alpha=100.0)
        assert np.isclose(s_min, 1.0, atol=0.1)

    def test_smooth_max_approximation(self):
        """Test smooth_max approximates max."""
        # With high alpha, should be close to true max
        s_max = smooth_max(1.0, 5.0, alpha=100.0)
        assert np.isclose(s_max, 5.0, atol=0.1)

    def test_smooth_min_pair(self):
        """Test pairwise smooth min (sequence input)."""
        result = smooth_min_pair([3.0], [7.0], alpha=100.0)
        assert np.isclose(result[0], 3.0, atol=0.1)

    def test_smooth_max_pair(self):
        """Test pairwise smooth max (sequence input)."""
        result = smooth_max_pair([3.0], [7.0], alpha=100.0)
        assert np.isclose(result[0], 7.0, atol=0.1)

    def test_smooth_relu(self):
        """Test smooth ReLU approximation."""
        # Positive value should pass through
        assert smooth_relu(5.0, alpha=10.0) > 4.9
        # Negative value should be near zero
        assert smooth_relu(-5.0, alpha=10.0) < 0.1

    def test_smooth_abs(self):
        """Test smooth absolute value."""
        # Should return approximate absolute value
        assert np.isclose(smooth_abs(5.0, alpha=10.0), 5.0, atol=0.1)
        assert np.isclose(smooth_abs(-5.0, alpha=10.0), 5.0, atol=0.1)

    def test_hpwl_smooth(self):
        """Test Half-Perimeter Wirelength calculation."""
        # Points forming a 4x3 rectangle (flat vertex list)
        points = [0.0, 0.0, 4.0, 0.0, 4.0, 3.0, 0.0, 3.0]
        hpwl = hpwl_smooth(points, alpha=100.0)
        # HPWL = (max_x - min_x) + (max_y - min_y) = 4 + 3 = 7
        assert np.isclose(hpwl, 7.0, atol=0.2)


class TestOverlap:
    """Tests for overlap detection functions (AABB corners API)."""

    def test_boxes_overlapping(self):
        """Test overlap detection for overlapping boxes."""
        # Box 1: center (0,0), size 4x4 -> corners (-2,-2,2,2)
        # Box 2: center (2,2), size 4x4 -> corners (0,0,4,4)
        overlap = component_overlap_amount(-2.0, -2.0, 2.0, 2.0, 0.0, 0.0, 4.0, 4.0)
        assert overlap > 0  # Should detect overlap

    def test_boxes_separated(self):
        """Test overlap detection for separated boxes."""
        # Box 1: center (0,0), size 2x2 -> corners (-1,-1,1,1)
        # Box 2: center (10,10), size 2x2 -> corners (9,9,11,11)
        overlap = component_overlap_amount(-1.0, -1.0, 1.0, 1.0, 9.0, 9.0, 11.0, 11.0)
        assert overlap == 0.0  # No overlap

    def test_clearance_violation(self):
        """Test clearance violation detection."""
        # Rect 1: center (0,0), size 2x2; Rect 2: center (3,0), size 2x2 (gap of 1mm)
        rects = [0.0, 0.0, 2.0, 2.0, 3.0, 0.0, 2.0, 2.0]

        # With required clearance of 0.5mm - should pass (gap is 1mm).
        # check_clearance_violation uses smooth_relu, so the amount is
        # tiny-but-positive rather than exactly zero; assert it is negligible.
        violations = check_clearance_violation(rects, 0.5)
        assert all(amount < 0.01 for _, _, amount in violations)

        # With required clearance of 2mm - should fail
        violations = check_clearance_violation(rects, 2.0)
        assert len(violations) == 1
        i, j, amount = violations[0]
        assert amount > 0


class TestPolygon:
    """Tests for polygon operations (flat vertex lists)."""

    def test_square_area(self):
        """Test area of unit square."""
        square = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        assert np.isclose(polygon_area(square), 1.0)

    def test_rectangle_area(self):
        """Test area of 3x4 rectangle."""
        rect = [0.0, 0.0, 4.0, 0.0, 4.0, 3.0, 0.0, 3.0]
        assert np.isclose(polygon_area(rect), 12.0)

    def test_triangle_area(self):
        """Test area of right triangle."""
        triangle = [0.0, 0.0, 4.0, 0.0, 0.0, 3.0]
        assert np.isclose(polygon_area(triangle), 6.0)  # 0.5 * 4 * 3

    def test_polygon_centroid(self):
        """Test centroid of square."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        centroid = polygon_centroid(square)
        assert np.allclose(centroid, (1.0, 1.0), atol=1e-6)

    def test_polygon_perimeter(self):
        """Test perimeter of unit square."""
        square = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        assert np.isclose(polygon_perimeter(square), 4.0)

    def test_point_in_polygon_inside(self):
        """Test point inside polygon."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        inside = point_in_polygon_soft(1.0, 1.0, square, smoothness=10.0)
        assert inside > 0.9  # Should be close to 1

    def test_point_in_polygon_outside(self):
        """Test point outside polygon."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        inside = point_in_polygon_soft(5.0, 5.0, square, smoothness=10.0)
        assert inside < 0.1  # Should be close to 0

    def test_winding_number_inside(self):
        """Test winding number for point inside."""
        square = [0.0, 0.0, 2.0, 0.0, 2.0, 2.0, 0.0, 2.0]
        winding = point_in_polygon_winding(1.0, 1.0, square)
        assert winding is True  # Non-zero winding number

    def test_rotate_polygon(self):
        """Test polygon rotation preserves area."""
        square = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        rotated = rotate_polygon(square, np.pi / 4)  # 45 degrees
        # Area should be preserved
        assert np.isclose(polygon_area(rotated), polygon_area(square), atol=1e-6)

    def test_scale_polygon(self):
        """Test polygon scaling."""
        square = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        scaled = scale_polygon(square, 2.0, 2.0)
        # Area should increase by factor of 4
        assert np.isclose(polygon_area(scaled), 4.0 * polygon_area(square), atol=1e-6)
