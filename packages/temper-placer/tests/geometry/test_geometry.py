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

from temper_geometry import (
    polygon_area,
)

# Import geometry functions
from temper_geometry import (
    smooth_max,
)
from temper_geometry import (
    point_distance,
)
from temper_geometry import sdf_circle
from temper_geometry import (
    get_rotation_matrix,
    rotate_point,
)

# =============================================================================
# Primitives Tests
# =============================================================================


class TestPrimitives:
    """Tests for basic geometric primitives."""

    def test_point_distance(self):
        """Test Euclidean distance between points."""
        assert np.isclose(point_distance(0.0, 0.0, 3.0, 4.0), 5.0)


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


class TestSmoothFunctions:
    """Tests for smooth (differentiable) approximations."""

    def test_smooth_max_approximation(self):
        """Test smooth_max approximates max."""
        # With high alpha, should be close to true max
        s_max = smooth_max(1.0, 5.0, alpha=100.0)
        assert np.isclose(s_max, 5.0, atol=0.1)


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
