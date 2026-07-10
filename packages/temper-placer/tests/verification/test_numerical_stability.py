"""
Numerical stability edge case tests for temper-placer.

These tests verify that edge cases don't produce NaN/Inf values in
outputs or gradients. Critical for robust optimization.

Test categories:
1. Identical/coincident points (sqrt(0) gradient issue)
2. Zero-area polygons (divide-by-zero issue)
3. Components at exact boundaries
4. Large/small coordinate values
5. Overlapping components
"""

import numpy as np

# Enable 64-bit precision for accurate gradient checks


class TestPointDistanceStability:
    """Test numerical stability of point_distance with epsilon guard."""

    def test_identical_points_value_finite(self):
        """point_distance of identical points returns small positive value (not 0)."""
        from temper_placer.geometry.primitives import point_distance

        p1 = np.array([5.0, 5.0])
        p2 = np.array([5.0, 5.0])

        dist = point_distance(p1, p2)

        # Should be sqrt(eps) ≈ 1e-6, not exactly 0
        assert np.isfinite(dist)
        assert dist > 0  # Not exactly zero due to epsilon
        assert dist < 1e-5  # But still very small

class TestPairwiseDistancesStability:
    """Test numerical stability of pairwise_distances."""

class TestBatchPointDistanceStability:
    """Test numerical stability of batch_point_distance."""

class TestPolygonCentroidStability:
    """Test numerical stability of polygon_centroid for degenerate cases."""

    def test_collinear_points_returns_mean(self):
        """Collinear points (zero-area polygon) return mean position, not NaN."""
        from temper_placer.geometry.polygon import polygon_centroid

        # Three collinear points (zero area)
        vertices = np.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],
                [10.0, 0.0],
            ]
        )

        centroid = polygon_centroid(vertices)

        # Should return valid centroid (mean), not NaN
        assert np.all(np.isfinite(centroid)), f"Centroid is not finite: {centroid}"

    def test_degenerate_triangle_centroid(self):
        """Degenerate triangle (area ≈ 0) returns valid centroid."""
        from temper_placer.geometry.polygon import polygon_centroid

        # Nearly collinear points (tiny area)
        vertices = np.array(
            [
                [0.0, 0.0],
                [10.0, 1e-12],  # Tiny y offset
                [5.0, 0.0],
            ]
        )

        centroid = polygon_centroid(vertices)

        assert np.all(np.isfinite(centroid)), f"Centroid is not finite: {centroid}"


class TestLargeCoordinateStability:
    """Test numerical stability with large coordinate values."""

    def test_point_distance_large_coords(self):
        """point_distance works correctly with large coordinates."""
        from temper_placer.geometry.primitives import point_distance

        # Large coordinates (typical PCB might be 200mm, but test extreme)
        p1 = np.array([1e6, 1e6])
        p2 = np.array([1e6 + 10.0, 1e6])

        dist = point_distance(p1, p2)

        assert np.isfinite(dist)
        assert np.isclose(dist, 10.0, rtol=1e-6)

    def test_polygon_area_large_coords(self):
        """polygon_area is accurate with large coordinates."""
        from temper_placer.geometry.polygon import polygon_area

        # 10x10 square at large offset
        offset = 1e6
        vertices = np.array(
            [
                [offset, offset],
                [offset + 10.0, offset],
                [offset + 10.0, offset + 10.0],
                [offset, offset + 10.0],
            ]
        )

        area = polygon_area(vertices)

        assert np.isfinite(area)
        assert np.isclose(area, 100.0, rtol=1e-6)


class TestSmallSeparationStability:
    """Test numerical stability with very small separations."""

    def test_tiny_polygon_area_finite(self):
        """Very small polygon area is computed correctly."""
        from temper_placer.geometry.polygon import polygon_area

        # Tiny 1e-6 x 1e-6 square
        vertices = np.array(
            [
                [0.0, 0.0],
                [1e-6, 0.0],
                [1e-6, 1e-6],
                [0.0, 1e-6],
            ]
        )

        area = polygon_area(vertices)

        assert np.isfinite(area)
        assert np.isclose(area, 1e-12, rtol=1e-3)


class TestEdgeBoundaryStability:
    """Test stability at exact boundary conditions."""

    def test_component_exactly_on_edge(self):
        """Component exactly on board edge produces finite boundary loss."""
        from temper_placer.geometry.primitives import distance_to_rect_edge

        # Point exactly on the left edge
        point = np.array([0.0, 5.0])
        board_min = np.array([0.0, 0.0])
        board_max = np.array([100.0, 100.0])

        dist = distance_to_rect_edge(point, board_min, board_max)

        assert np.isfinite(dist)
        assert dist == 0.0  # Exactly on edge

    def test_component_exactly_at_corner(self):
        """Component at board corner produces finite result."""
        from temper_placer.geometry.primitives import distance_to_rect_edge

        point = np.array([0.0, 0.0])  # Exactly at corner
        board_min = np.array([0.0, 0.0])
        board_max = np.array([100.0, 100.0])

        dist = distance_to_rect_edge(point, board_min, board_max)

        assert np.isfinite(dist)
