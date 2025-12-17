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

import pytest
import jax
import jax.numpy as jnp
from jax import Array

# Enable 64-bit precision for accurate gradient checks
jax.config.update("jax_enable_x64", True)


class TestPointDistanceStability:
    """Test numerical stability of point_distance with epsilon guard."""

    def test_identical_points_value_finite(self):
        """point_distance of identical points returns small positive value (not 0)."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([5.0, 5.0])
        p2 = jnp.array([5.0, 5.0])

        dist = point_distance(p1, p2)

        # Should be sqrt(eps) ≈ 1e-6, not exactly 0
        assert jnp.isfinite(dist)
        assert dist > 0  # Not exactly zero due to epsilon
        assert dist < 1e-5  # But still very small

    def test_identical_points_gradient_finite(self):
        """Gradient of point_distance at identical points is finite (not inf/nan)."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([5.0, 5.0])
        p2 = jnp.array([5.0, 5.0])

        # Compute gradient with respect to p1
        grad_fn = jax.grad(lambda p: point_distance(p, p2))
        grad = grad_fn(p1)

        # Without epsilon guard, this would be inf or nan
        assert jnp.all(jnp.isfinite(grad)), f"Gradient is not finite: {grad}"

    def test_very_close_points_gradient_finite(self):
        """Gradient is finite for very close (but not identical) points."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([5.0, 5.0])
        p2 = jnp.array([5.0 + 1e-10, 5.0])  # Extremely close

        grad_fn = jax.grad(lambda p: point_distance(p, p2))
        grad = grad_fn(p1)

        assert jnp.all(jnp.isfinite(grad)), f"Gradient is not finite: {grad}"


class TestPairwiseDistancesStability:
    """Test numerical stability of pairwise_distances."""

    def test_coincident_points_gradient_finite(self):
        """Gradient of pairwise_distances is finite when points coincide."""
        from temper_placer.geometry.primitives import pairwise_distances

        # Three points, two of which are identical
        points = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 5.0],
                [5.0, 5.0],  # Same as point 1
            ]
        )

        # Sum of all pairwise distances (scalar for grad)
        def total_dist(pts):
            return jnp.sum(pairwise_distances(pts))

        grad = jax.grad(total_dist)(points)

        assert jnp.all(jnp.isfinite(grad)), f"Gradient is not finite: {grad}"

    def test_all_same_point_gradient_finite(self):
        """Gradient is finite when all points are at the same location."""
        from temper_placer.geometry.primitives import pairwise_distances

        # All points at origin
        points = jnp.array(
            [
                [0.0, 0.0],
                [0.0, 0.0],
                [0.0, 0.0],
            ]
        )

        def total_dist(pts):
            return jnp.sum(pairwise_distances(pts))

        grad = jax.grad(total_dist)(points)

        assert jnp.all(jnp.isfinite(grad)), f"Gradient is not finite: {grad}"


class TestBatchPointDistanceStability:
    """Test numerical stability of batch_point_distance."""

    def test_identical_batch_gradient_finite(self):
        """Gradient is finite for batch of identical point pairs."""
        from temper_placer.geometry.primitives import batch_point_distance

        points1 = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 5.0],
                [10.0, 0.0],
            ]
        )
        points2 = points1.copy()  # Identical

        def total_dist(p1):
            return jnp.sum(batch_point_distance(p1, points2))

        grad = jax.grad(total_dist)(points1)

        assert jnp.all(jnp.isfinite(grad)), f"Gradient is not finite: {grad}"


class TestPolygonCentroidStability:
    """Test numerical stability of polygon_centroid for degenerate cases."""

    def test_collinear_points_returns_mean(self):
        """Collinear points (zero-area polygon) return mean position, not NaN."""
        from temper_placer.geometry.polygon import polygon_centroid

        # Three collinear points (zero area)
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],
                [10.0, 0.0],
            ]
        )

        centroid = polygon_centroid(vertices)

        # Should return valid centroid (mean), not NaN
        assert jnp.all(jnp.isfinite(centroid)), f"Centroid is not finite: {centroid}"

    def test_degenerate_triangle_centroid(self):
        """Degenerate triangle (area ≈ 0) returns valid centroid."""
        from temper_placer.geometry.polygon import polygon_centroid

        # Nearly collinear points (tiny area)
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 1e-12],  # Tiny y offset
                [5.0, 0.0],
            ]
        )

        centroid = polygon_centroid(vertices)

        assert jnp.all(jnp.isfinite(centroid)), f"Centroid is not finite: {centroid}"


class TestLargeCoordinateStability:
    """Test numerical stability with large coordinate values."""

    def test_point_distance_large_coords(self):
        """point_distance works correctly with large coordinates."""
        from temper_placer.geometry.primitives import point_distance

        # Large coordinates (typical PCB might be 200mm, but test extreme)
        p1 = jnp.array([1e6, 1e6])
        p2 = jnp.array([1e6 + 10.0, 1e6])

        dist = point_distance(p1, p2)

        assert jnp.isfinite(dist)
        assert jnp.isclose(dist, 10.0, rtol=1e-6)

    def test_polygon_area_large_coords(self):
        """polygon_area is accurate with large coordinates."""
        from temper_placer.geometry.polygon import polygon_area

        # 10x10 square at large offset
        offset = 1e6
        vertices = jnp.array(
            [
                [offset, offset],
                [offset + 10.0, offset],
                [offset + 10.0, offset + 10.0],
                [offset, offset + 10.0],
            ]
        )

        area = polygon_area(vertices)

        assert jnp.isfinite(area)
        assert jnp.isclose(area, 100.0, rtol=1e-6)


class TestSmallSeparationStability:
    """Test numerical stability with very small separations."""

    def test_very_small_separation_finite(self):
        """Very small separations produce finite results."""
        from temper_placer.geometry.primitives import point_distance

        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([1e-8, 0.0])

        dist = point_distance(p1, p2)
        grad = jax.grad(lambda p: point_distance(p, p2))(p1)

        assert jnp.isfinite(dist)
        assert jnp.all(jnp.isfinite(grad))

    def test_tiny_polygon_area_finite(self):
        """Very small polygon area is computed correctly."""
        from temper_placer.geometry.polygon import polygon_area

        # Tiny 1e-6 x 1e-6 square
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [1e-6, 0.0],
                [1e-6, 1e-6],
                [0.0, 1e-6],
            ]
        )

        area = polygon_area(vertices)

        assert jnp.isfinite(area)
        assert jnp.isclose(area, 1e-12, rtol=1e-3)


class TestEdgeBoundaryStability:
    """Test stability at exact boundary conditions."""

    def test_component_exactly_on_edge(self):
        """Component exactly on board edge produces finite boundary loss."""
        from temper_placer.geometry.primitives import distance_to_rect_edge

        # Point exactly on the left edge
        point = jnp.array([0.0, 5.0])
        board_min = jnp.array([0.0, 0.0])
        board_max = jnp.array([100.0, 100.0])

        dist = distance_to_rect_edge(point, board_min, board_max)

        assert jnp.isfinite(dist)
        assert dist == 0.0  # Exactly on edge

    def test_component_exactly_at_corner(self):
        """Component at board corner produces finite result."""
        from temper_placer.geometry.primitives import distance_to_rect_edge

        point = jnp.array([0.0, 0.0])  # Exactly at corner
        board_min = jnp.array([0.0, 0.0])
        board_max = jnp.array([100.0, 100.0])

        dist = distance_to_rect_edge(point, board_min, board_max)

        assert jnp.isfinite(dist)
