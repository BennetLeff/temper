"""
Ground-truth geometry tests with analytically known answers.

These tests verify the mathematical correctness of geometry functions
by comparing outputs against analytically computed expected values.
All expected values are computed from first principles, not from the
functions being tested.

Test categories:
1. Point operations (distance, midpoint)
2. Polygon operations (area, centroid, perimeter)
3. AABB operations (intersection, overlap area)
4. Distance functions (point-to-line, point-to-rect)
"""

import math

# Enable 64-bit precision for accurate tests
import jax
import jax.numpy as jnp
import pytest

jax.config.update("jax_enable_x64", True)


class TestPointDistanceGroundTruth:
    """Ground-truth tests for point_distance."""

    def test_3_4_5_triangle(self):
        """Classic 3-4-5 right triangle: distance should be exactly 5."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([3.0, 4.0])

        result = float(point_distance(p1, p2))

        # Expected: sqrt(3^2 + 4^2) = sqrt(25) = 5.0
        assert result == pytest.approx(5.0, rel=1e-10)

    def test_5_12_13_triangle(self):
        """5-12-13 right triangle."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([5.0, 12.0])

        result = float(point_distance(p1, p2))

        # Expected: sqrt(5^2 + 12^2) = sqrt(169) = 13.0
        assert result == pytest.approx(13.0, rel=1e-10)

    def test_horizontal_distance(self):
        """Pure horizontal distance."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([10.0, 5.0])
        p2 = jnp.array([25.0, 5.0])

        result = float(point_distance(p1, p2))

        # Expected: |25 - 10| = 15.0
        assert result == pytest.approx(15.0, rel=1e-10)

    def test_vertical_distance(self):
        """Pure vertical distance."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([5.0, 10.0])
        p2 = jnp.array([5.0, 30.0])

        result = float(point_distance(p1, p2))

        # Expected: |30 - 10| = 20.0
        assert result == pytest.approx(20.0, rel=1e-10)

    def test_unit_diagonal(self):
        """Unit diagonal: sqrt(2)."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([1.0, 1.0])

        result = float(point_distance(p1, p2))

        # Expected: sqrt(2) ≈ 1.41421356
        assert result == pytest.approx(math.sqrt(2), rel=1e-10)


class TestPolygonAreaGroundTruth:
    """Ground-truth tests for polygon_area."""

    def test_unit_square(self):
        """Unit square has area 1."""
        from temper_placer.geometry.polygon import polygon_area

        # Counter-clockwise unit square
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        result = float(polygon_area(vertices))

        assert result == pytest.approx(1.0, rel=1e-10)

    def test_rectangle_10x5(self):
        """10x5 rectangle has area 50."""
        from temper_placer.geometry.polygon import polygon_area

        vertices = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 5.0],
                [0.0, 5.0],
            ]
        )

        result = float(polygon_area(vertices))

        assert result == pytest.approx(50.0, rel=1e-10)

    def test_right_triangle(self):
        """Right triangle with base=6, height=4 has area 12."""
        from temper_placer.geometry.polygon import polygon_area

        # Right triangle: (0,0), (6,0), (0,4)
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [6.0, 0.0],
                [0.0, 4.0],
            ]
        )

        result = float(polygon_area(vertices))

        # Expected: 0.5 * base * height = 0.5 * 6 * 4 = 12
        assert result == pytest.approx(12.0, rel=1e-10)

    def test_equilateral_triangle_side_2(self):
        """Equilateral triangle with side 2."""
        from temper_placer.geometry.polygon import polygon_area

        # Equilateral triangle with side 2, base at origin
        # Height = sqrt(3)
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [2.0, 0.0],
                [1.0, math.sqrt(3)],
            ]
        )

        result = float(polygon_area(vertices))

        # Expected: (sqrt(3)/4) * side^2 = (sqrt(3)/4) * 4 = sqrt(3) ≈ 1.732
        expected = math.sqrt(3)
        assert result == pytest.approx(expected, rel=1e-10)

    def test_clockwise_square(self):
        """Clockwise square should still give positive area (absolute value)."""
        from temper_placer.geometry.polygon import polygon_area

        # Clockwise unit square
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
            ]
        )

        result = float(polygon_area(vertices))

        # polygon_area returns absolute value, so still 1.0
        assert result == pytest.approx(1.0, rel=1e-10)


class TestPolygonCentroidGroundTruth:
    """Ground-truth tests for polygon_centroid."""

    def test_square_centroid(self):
        """Centroid of unit square is at (0.5, 0.5)."""
        from temper_placer.geometry.polygon import polygon_centroid

        vertices = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        result = polygon_centroid(vertices)

        assert float(result[0]) == pytest.approx(0.5, rel=1e-10)
        assert float(result[1]) == pytest.approx(0.5, rel=1e-10)

    def test_rectangle_centroid(self):
        """Centroid of 10x4 rectangle at (5,15) to (15,19) is at (10, 17)."""
        from temper_placer.geometry.polygon import polygon_centroid

        vertices = jnp.array(
            [
                [5.0, 15.0],
                [15.0, 15.0],
                [15.0, 19.0],
                [5.0, 19.0],
            ]
        )

        result = polygon_centroid(vertices)

        # Expected: center of rectangle = (5+15)/2, (15+19)/2 = (10, 17)
        assert float(result[0]) == pytest.approx(10.0, rel=1e-10)
        assert float(result[1]) == pytest.approx(17.0, rel=1e-10)

    def test_right_triangle_centroid(self):
        """Centroid of right triangle is at (base/3, height/3) from right angle."""
        from temper_placer.geometry.polygon import polygon_centroid

        # Right triangle: (0,0), (9,0), (0,6)
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [9.0, 0.0],
                [0.0, 6.0],
            ]
        )

        result = polygon_centroid(vertices)

        # Centroid of triangle is at mean of vertices
        # Expected: ((0+9+0)/3, (0+0+6)/3) = (3, 2)
        assert float(result[0]) == pytest.approx(3.0, rel=1e-10)
        assert float(result[1]) == pytest.approx(2.0, rel=1e-10)


class TestAABBOverlapGroundTruth:
    """Ground-truth tests for AABB overlap calculations."""

    def test_no_overlap(self):
        """Two non-overlapping boxes have zero overlap area."""
        from temper_placer.geometry.primitives import aabb_overlap_area

        # Box 1: (0,0) to (10,10)
        min1 = jnp.array([0.0, 0.0])
        max1 = jnp.array([10.0, 10.0])

        # Box 2: (20,20) to (30,30) - no overlap
        min2 = jnp.array([20.0, 20.0])
        max2 = jnp.array([30.0, 30.0])

        result = float(aabb_overlap_area(min1, max1, min2, max2))

        assert result == pytest.approx(0.0, abs=1e-10)

    def test_50_percent_overlap(self):
        """Two 10x10 boxes offset by 5 in both dimensions."""
        from temper_placer.geometry.primitives import aabb_overlap_area

        # Box 1: (0,0) to (10,10) - area 100
        min1 = jnp.array([0.0, 0.0])
        max1 = jnp.array([10.0, 10.0])

        # Box 2: (5,5) to (15,15) - overlaps in 5x5 region
        min2 = jnp.array([5.0, 5.0])
        max2 = jnp.array([15.0, 15.0])

        result = float(aabb_overlap_area(min1, max1, min2, max2))

        # Overlap region: (5,5) to (10,10) = 5x5 = 25
        assert result == pytest.approx(25.0, rel=1e-10)

    def test_one_inside_other(self):
        """Small box fully inside large box."""
        from temper_placer.geometry.primitives import aabb_overlap_area

        # Large box: (0,0) to (20,20)
        min1 = jnp.array([0.0, 0.0])
        max1 = jnp.array([20.0, 20.0])

        # Small box: (5,5) to (10,10) - fully inside
        min2 = jnp.array([5.0, 5.0])
        max2 = jnp.array([10.0, 10.0])

        result = float(aabb_overlap_area(min1, max1, min2, max2))

        # Overlap is the entire small box: 5x5 = 25
        assert result == pytest.approx(25.0, rel=1e-10)

    def test_identical_boxes(self):
        """Identical boxes have overlap equal to their area."""
        from temper_placer.geometry.primitives import aabb_overlap_area

        min1 = jnp.array([0.0, 0.0])
        max1 = jnp.array([7.0, 8.0])

        result = float(aabb_overlap_area(min1, max1, min1, max1))

        # Overlap is the entire box: 7x8 = 56
        assert result == pytest.approx(56.0, rel=1e-10)


class TestPointToLineDistanceGroundTruth:
    """Ground-truth tests for point_to_line_distance."""

    def test_point_on_perpendicular(self):
        """Point directly above line midpoint."""
        from temper_placer.geometry.primitives import point_to_line_distance

        # Horizontal line from (0,0) to (10,0)
        line_start = jnp.array([0.0, 0.0])
        line_end = jnp.array([10.0, 0.0])

        # Point at (5, 7) - directly above midpoint
        point = jnp.array([5.0, 7.0])

        result = float(point_to_line_distance(point, line_start, line_end))

        # Expected: perpendicular distance = 7.0
        assert result == pytest.approx(7.0, rel=1e-6)

    def test_point_at_endpoint(self):
        """Point closest to line endpoint."""
        from temper_placer.geometry.primitives import point_to_line_distance

        # Horizontal line from (0,0) to (10,0)
        line_start = jnp.array([0.0, 0.0])
        line_end = jnp.array([10.0, 0.0])

        # Point at (13, 4) - closest to endpoint (10, 0)
        point = jnp.array([13.0, 4.0])

        result = float(point_to_line_distance(point, line_start, line_end))

        # Expected: distance from (13,4) to (10,0) = sqrt(9 + 16) = 5
        assert result == pytest.approx(5.0, rel=1e-6)

    def test_point_on_line(self):
        """Point exactly on line segment."""
        from temper_placer.geometry.primitives import point_to_line_distance

        line_start = jnp.array([0.0, 0.0])
        line_end = jnp.array([10.0, 10.0])

        # Point at (5, 5) - on the line
        point = jnp.array([5.0, 5.0])

        result = float(point_to_line_distance(point, line_start, line_end))

        # Expected: 0 (or very close due to epsilon)
        assert result == pytest.approx(0.0, abs=1e-5)


class TestPolygonPerimeterGroundTruth:
    """Ground-truth tests for polygon_perimeter."""

    def test_unit_square_perimeter(self):
        """Unit square has perimeter 4."""
        from temper_placer.geometry.polygon import polygon_perimeter

        vertices = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        result = float(polygon_perimeter(vertices))

        assert result == pytest.approx(4.0, rel=1e-10)

    def test_rectangle_perimeter(self):
        """10x5 rectangle has perimeter 30."""
        from temper_placer.geometry.polygon import polygon_perimeter

        vertices = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 5.0],
                [0.0, 5.0],
            ]
        )

        result = float(polygon_perimeter(vertices))

        # Expected: 2*(10 + 5) = 30
        assert result == pytest.approx(30.0, rel=1e-10)

    def test_equilateral_triangle_perimeter(self):
        """Equilateral triangle with side 3 has perimeter 9."""
        from temper_placer.geometry.polygon import polygon_perimeter

        # Equilateral triangle with side 3
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [3.0, 0.0],
                [1.5, 3.0 * math.sqrt(3) / 2],
            ]
        )

        result = float(polygon_perimeter(vertices))

        # Expected: 3 * 3 = 9
        assert result == pytest.approx(9.0, rel=1e-10)


class TestPairwiseDistancesGroundTruth:
    """Ground-truth tests for pairwise_distances."""

    def test_three_points_triangle(self):
        """Three points forming a 3-4-5 right triangle."""
        from temper_placer.geometry.primitives import pairwise_distances

        points = jnp.array(
            [
                [0.0, 0.0],  # A
                [3.0, 0.0],  # B
                [0.0, 4.0],  # C
            ]
        )

        result = pairwise_distances(points)

        # Expected distances:
        # A-A = 0 (or sqrt(eps))
        # A-B = 3
        # A-C = 4
        # B-A = 3
        # B-B = 0 (or sqrt(eps))
        # B-C = 5 (hypotenuse)
        # C-A = 4
        # C-B = 5
        # C-C = 0 (or sqrt(eps))

        assert float(result[0, 1]) == pytest.approx(3.0, rel=1e-6)  # A-B
        assert float(result[0, 2]) == pytest.approx(4.0, rel=1e-6)  # A-C
        assert float(result[1, 2]) == pytest.approx(5.0, rel=1e-6)  # B-C
        # Symmetry
        assert float(result[1, 0]) == pytest.approx(3.0, rel=1e-6)  # B-A
        assert float(result[2, 0]) == pytest.approx(4.0, rel=1e-6)  # C-A
        assert float(result[2, 1]) == pytest.approx(5.0, rel=1e-6)  # C-B
