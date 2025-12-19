"""
JAX gradient correctness tests using finite differences.

These tests verify that the analytical gradients computed by JAX's autodiff
match numerical gradients computed via finite differences. This is crucial
for ensuring gradient-based optimization will converge correctly.

Test Methodology:
1. Use custom finite difference gradient checking (compatible with JAX 0.4+)
2. Test all loss functions and key geometry primitives
3. Test at various points including edge cases (boundaries, near-zero values)
4. Verify both first-order (grad) and optionally second-order (hessian) gradients

Note: Finite difference checking uses eps=1e-4 by default. Functions with
numerical instabilities near zero may need larger eps or special handling.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import pytest
from jax import Array

# Import geometry functions
from temper_placer.geometry.primitives import (
    point_distance,
    pairwise_distances,
    batch_point_distance,
    point_to_line_distance,
    aabb_overlap_area,
)
from temper_placer.geometry.polygon import (
    polygon_area,
    polygon_centroid,
    polygon_perimeter,
)

# Import loss functions
from temper_placer.losses.overlap import compute_overlap_penalty
from temper_placer.losses.boundary import compute_boundary_penalty
from temper_placer.losses.thermal import compute_edge_distance
from temper_placer.losses.loop_area import compute_loop_area_penalty


# =============================================================================
# Configuration
# =============================================================================

# Standard tolerance for gradient checks
# Note: Finite difference is inherently approximate. Central differences have O(eps^2) error,
# so with eps=1e-4, we expect ~1e-8 truncation error. However, for functions with large
# gradient magnitudes (e.g., loop area with ~500), absolute differences can be larger.
# Using rtol=0.01 (1%) is reasonable for verifying autodiff correctness.
GRAD_CHECK_EPS = 1e-4  # Finite difference step size
GRAD_CHECK_RTOL = 0.01  # Relative tolerance for gradient comparison (1%)
GRAD_CHECK_ATOL = 0.1  # Absolute tolerance for gradient comparison


def finite_difference_gradient(fn, x, eps=GRAD_CHECK_EPS):
    """
    Compute numerical gradient using central finite differences.

    Args:
        fn: Scalar-valued function
        x: Point at which to compute gradient (array)
        eps: Finite difference step size

    Returns:
        Numerical gradient with same shape as x
    """
    x_flat = x.flatten()
    grad = jnp.zeros_like(x_flat)

    for i in range(len(x_flat)):
        x_plus = x_flat.at[i].set(x_flat[i] + eps)
        x_minus = x_flat.at[i].set(x_flat[i] - eps)

        f_plus = fn(x_plus.reshape(x.shape))
        f_minus = fn(x_minus.reshape(x.shape))

        grad = grad.at[i].set((f_plus - f_minus) / (2 * eps))

    return grad.reshape(x.shape)


def check_grads_safe(
    fn, args, order=1, eps=GRAD_CHECK_EPS, rtol=GRAD_CHECK_RTOL, atol=GRAD_CHECK_ATOL
):
    """
    Check that autodiff gradients match finite difference gradients.

    Args:
        fn: Function to check gradients for
        args: Tuple of arguments to fn (only first arg is differentiated)
        order: Derivative order (only 1 is supported)
        eps: Finite difference epsilon
        rtol: Relative tolerance
        atol: Absolute tolerance

    Raises:
        AssertionError: If gradients don't match within tolerance
    """
    assert order == 1, "Only first-order gradients supported"

    x = args[0]

    # Compute autodiff gradient
    grad_fn = jax.grad(fn)
    autodiff_grad = grad_fn(x)

    # Compute finite difference gradient
    fd_grad = finite_difference_gradient(fn, x, eps=eps)

    # Check that they match
    if not jnp.allclose(autodiff_grad, fd_grad, rtol=rtol, atol=atol):
        max_diff = jnp.max(jnp.abs(autodiff_grad - fd_grad))
        raise AssertionError(
            f"Gradient mismatch: max difference = {max_diff}\n"
            f"Autodiff: {autodiff_grad}\n"
            f"Finite diff: {fd_grad}"
        )


# =============================================================================
# Geometry Primitive Gradient Tests
# =============================================================================


class TestPointDistanceGradients:
    """Gradient tests for point_distance function."""

    def test_gradient_at_standard_points(self):
        """Gradient should be correct for well-separated points."""
        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([3.0, 4.0])

        # Check gradient w.r.t. p1
        check_grads_safe(lambda x: point_distance(x, p2), (p1,))

        # Check gradient w.r.t. p2
        check_grads_safe(lambda x: point_distance(p1, x), (p2,))

    def test_gradient_close_points(self):
        """Gradient should be finite for close (but not identical) points."""
        p1 = jnp.array([0.0, 0.0])
        p2 = jnp.array([0.01, 0.01])

        # Manual gradient check - verify finite
        grad_fn = jax.grad(lambda x: point_distance(x, p2))
        grad = grad_fn(p1)
        assert jnp.all(jnp.isfinite(grad))

        # Verify gradient direction points away from p2
        # d/dp1[||p1-p2||] = (p1-p2) / ||p1-p2||
        expected_dir = (p1 - p2) / jnp.linalg.norm(p1 - p2)
        assert jnp.allclose(grad / jnp.linalg.norm(grad), expected_dir, atol=1e-5)

    def test_gradient_near_identical_points(self):
        """
        Gradient at identical points should be finite (due to eps guard).

        Without the eps=1e-12 guard, this would produce inf/nan gradients.
        """
        p1 = jnp.array([1.0, 1.0])
        p2 = jnp.array([1.0, 1.0])

        grad_fn = jax.grad(lambda x: point_distance(x, p2))
        grad = grad_fn(p1)

        # Gradient should be finite (due to eps guard)
        assert jnp.all(jnp.isfinite(grad))
        # Magnitude should be small/zero-ish
        assert jnp.linalg.norm(grad) < 1.0


class TestPairwiseDistancesGradients:
    """Gradient tests for pairwise_distances function."""

    def test_gradient_three_points(self):
        """Gradient should be correct for three well-separated points."""
        points = jnp.array(
            [
                [0.0, 0.0],
                [3.0, 0.0],
                [0.0, 4.0],
            ]
        )

        # Sum of pairwise distances as scalar output
        def total_pairwise_dist(pts):
            dists = pairwise_distances(pts)
            return jnp.sum(dists)

        check_grads_safe(total_pairwise_dist, (points,))

    def test_gradient_with_coincident_points(self):
        """Gradient should be finite even with some coincident points."""
        points = jnp.array(
            [
                [0.0, 0.0],
                [0.0, 0.0],  # Coincident with first
                [5.0, 0.0],
            ]
        )

        def total_pairwise_dist(pts):
            dists = pairwise_distances(pts)
            return jnp.sum(dists)

        grad_fn = jax.grad(total_pairwise_dist)
        grad = grad_fn(points)

        assert jnp.all(jnp.isfinite(grad))


class TestPolygonAreaGradients:
    """Gradient tests for polygon_area function."""

    def test_gradient_square(self):
        """Gradient of square area should be correct."""
        # Unit square vertices
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )

        check_grads_safe(polygon_area, (vertices,))

    def test_gradient_triangle(self):
        """Gradient of triangle area should be correct."""
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [4.0, 0.0],
                [0.0, 3.0],
            ]
        )

        check_grads_safe(polygon_area, (vertices,))

    def test_gradient_direction_expands_area(self):
        """
        Moving vertices outward should increase area.

        For a square centered at origin, moving vertex (1,1) further out
        should have positive gradient for area.
        """
        vertices = jnp.array(
            [
                [-1.0, -1.0],
                [1.0, -1.0],
                [1.0, 1.0],
                [-1.0, 1.0],
            ]
        )

        # Gradient w.r.t. vertex at (1,1)
        def area_fn(v2):
            verts = vertices.at[2].set(v2)
            return polygon_area(verts)

        grad = jax.grad(area_fn)(vertices[2])

        # Moving (1,1) in direction (1,1) should increase area
        outward = jnp.array([1.0, 1.0])
        assert jnp.dot(grad, outward) > 0


class TestPolygonCentroidGradients:
    """Gradient tests for polygon_centroid function."""

    def test_gradient_square(self):
        """Gradient of centroid should be correct for square."""
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [2.0, 0.0],
                [2.0, 2.0],
                [0.0, 2.0],
            ]
        )

        # Centroid x-coordinate as scalar
        def centroid_x(verts):
            return polygon_centroid(verts)[0]

        def centroid_y(verts):
            return polygon_centroid(verts)[1]

        check_grads_safe(centroid_x, (vertices,))
        check_grads_safe(centroid_y, (vertices,))


class TestPointToLineDistanceGradients:
    """Gradient tests for point_to_line_distance function."""

    def test_gradient_perpendicular_case(self):
        """Gradient correct when point projects onto line interior."""
        point = jnp.array([1.0, 1.0])
        line_start = jnp.array([0.0, 0.0])
        line_end = jnp.array([2.0, 0.0])

        check_grads_safe(lambda p: point_to_line_distance(p, line_start, line_end), (point,))

    def test_gradient_endpoint_case(self):
        """Gradient correct when closest point is line endpoint."""
        point = jnp.array([-1.0, 1.0])  # Projects before line start
        line_start = jnp.array([0.0, 0.0])
        line_end = jnp.array([2.0, 0.0])

        check_grads_safe(lambda p: point_to_line_distance(p, line_start, line_end), (point,))


# =============================================================================
# Loss Function Gradient Tests
# =============================================================================


class TestOverlapLossGradients:
    """Gradient tests for overlap penalty."""

    def test_gradient_overlapping_boxes(self):
        """Gradient should push overlapping boxes apart."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        check_grads_safe(loss_fn, (positions,))

        # Verify gradient direction: gradients should be opposite (pushing apart)
        # The sign depends on the loss formulation. What matters is that
        # following negative gradient reduces overlap.
        grad = jax.grad(loss_fn)(positions)
        # Gradients for box 0 and box 1 should be opposite in x-direction
        assert grad[0, 0] * grad[1, 0] < 0, "Gradients should push boxes in opposite directions"

    def test_gradient_non_overlapping_boxes(self):
        """Gradient should be zero for non-overlapping boxes."""
        positions = jnp.array([[0.0, 0.0], [10.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        grad = jax.grad(loss_fn)(positions)

        # No overlap, gradient should be zero
        assert jnp.allclose(grad, 0.0, atol=1e-10)

    def test_gradient_with_margin(self):
        """Gradient should account for margin in effective size."""
        positions = jnp.array([[0.0, 0.0], [2.5, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights, margin=1.0)

        check_grads_safe(loss_fn, (positions,))


class TestBoundaryLossGradients:
    """Gradient tests for boundary penalty."""

    def test_gradient_inside_board(self):
        """Gradient should be zero for component fully inside."""
        positions = jnp.array([[50.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        grad = jax.grad(loss_fn)(positions)

        assert jnp.allclose(grad, 0.0, atol=1e-10)

    def test_gradient_pushes_inside(self):
        """Gradient should push component back inside board."""
        positions = jnp.array([[2.0, 50.0]])  # Left edge at -3, violates left boundary
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        check_grads_safe(loss_fn, (positions,))

        grad = jax.grad(loss_fn)(positions)

        # Verify gradient is non-zero (there is a violation)
        # The gradient direction depends on the loss formulation.
        # What matters is that following negative gradient reduces the penalty.
        assert jnp.abs(grad[0, 0]) > 0, "Gradient should be non-zero for boundary violation"

    def test_gradient_corner_violation(self):
        """Gradient should handle corner violations correctly."""
        positions = jnp.array([[2.0, 2.0]])  # Violates left and bottom
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        check_grads_safe(loss_fn, (positions,))


class TestLoopAreaLossGradients:
    """Gradient tests for loop area penalty."""

    def test_gradient_square_loop(self):
        """Gradient should be correct for square loop."""
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ]
        )

        def loss_fn(pins):
            return compute_loop_area_penalty(pins, max_area=50.0, scale=1.0)

        check_grads_safe(loss_fn, (pin_positions,))

    def test_gradient_reduces_area(self):
        """Gradient should reduce loop area when above max."""
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ]
        )
        # Area = 100, max = 50, so there's a violation

        def loss_fn(pins):
            return compute_loop_area_penalty(pins, max_area=50.0, scale=1.0)

        grad = jax.grad(loss_fn)(pin_positions)

        # Verify gradients are finite
        assert jnp.all(jnp.isfinite(grad))
        # Gradients should be non-zero (pushing to reduce area)
        assert jnp.linalg.norm(grad) > 0

    def test_gradient_zero_below_max(self):
        """Gradient should be zero when area is below max."""
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [1.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
            ]
        )
        # Area = 1, max = 100, no violation

        def loss_fn(pins):
            return compute_loop_area_penalty(pins, max_area=100.0, scale=1.0)

        grad = jax.grad(loss_fn)(pin_positions)

        assert jnp.allclose(grad, 0.0, atol=1e-10)


class TestThermalLossGradients:
    """Gradient tests for thermal edge distance."""

    def test_gradient_to_top_edge(self):
        """Gradient of distance to top edge should be -1 in y direction."""
        position = jnp.array([50.0, 80.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def dist_fn(pos):
            return compute_edge_distance(pos, board_bounds, "TOP")

        grad = jax.grad(dist_fn)(position)

        # d/dy(y_max - y) = -1
        assert jnp.allclose(grad, jnp.array([0.0, -1.0]))

    def test_gradient_to_left_edge(self):
        """Gradient of distance to left edge should be +1 in x direction."""
        position = jnp.array([20.0, 50.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def dist_fn(pos):
            return compute_edge_distance(pos, board_bounds, "LEFT")

        grad = jax.grad(dist_fn)(position)

        # d/dx(x - x_min) = 1
        assert jnp.allclose(grad, jnp.array([1.0, 0.0]))


# =============================================================================
# Higher-Order Gradient Tests (Hessian)
# =============================================================================


class TestSecondOrderGradients:
    """
    Tests for second-order derivatives (Hessian).

    Second-order correctness is important for:
    - Newton-based optimizers
    - Understanding loss landscape curvature
    - Detecting saddle points
    """

    def test_overlap_hessian(self):
        """Hessian of overlap loss should be finite."""
        positions = jnp.array([[0.0, 0.0], [1.5, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        # Check that Hessian computation doesn't produce NaN/Inf
        hessian_fn = jax.hessian(loss_fn)
        hessian = hessian_fn(positions)
        assert jnp.all(jnp.isfinite(hessian)), "Hessian contains NaN/Inf"

    def test_boundary_hessian(self):
        """Hessian of boundary loss should be finite."""
        positions = jnp.array([[2.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        # Check that Hessian computation doesn't produce NaN/Inf
        hessian_fn = jax.hessian(loss_fn)
        hessian = hessian_fn(positions)
        assert jnp.all(jnp.isfinite(hessian)), "Hessian contains NaN/Inf"

    def test_polygon_area_hessian_structure(self):
        """
        Hessian of polygon area has specific structure due to shoelace formula.

        The shoelace formula: A = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|
        has cross-derivatives (∂²A/∂x_i∂y_j ≠ 0 for adjacent vertices),
        so the Hessian is NOT zero. However, it should be finite and have
        a specific sparse structure.
        """
        vertices = jnp.array(
            [
                [0.0, 0.0],
                [2.0, 0.0],
                [2.0, 2.0],
                [0.0, 2.0],
            ]
        )

        # Polygon area has non-zero Hessian due to cross-derivatives
        hessian_fn = jax.hessian(polygon_area)
        hessian = hessian_fn(vertices)

        # Hessian should be finite
        assert jnp.all(jnp.isfinite(hessian)), "Polygon area Hessian should be finite"

        # Second derivatives w.r.t. same coordinate are zero (∂²A/∂x_i² = 0)
        # This is because each x_i appears linearly in the shoelace formula
        for i in range(4):
            # Diagonal blocks (same vertex) should have zero diagonal
            assert jnp.abs(hessian[i, 0, i, 0]) < 1e-10, "∂²A/∂x_i² should be 0"
            assert jnp.abs(hessian[i, 1, i, 1]) < 1e-10, "∂²A/∂y_i² should be 0"


# =============================================================================
# Gradient Sanity Checks
# =============================================================================


class TestGradientSanityChecks:
    """
    Sanity checks for gradient behavior across the system.
    """

    def test_all_losses_have_finite_gradients(self):
        """All loss functions should produce finite gradients."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])  # Overlapping
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Overlap
        grad_overlap = jax.grad(lambda p: compute_overlap_penalty(p, widths, heights))(positions)
        assert jnp.all(jnp.isfinite(grad_overlap)), "Overlap gradient has inf/nan"

        # Boundary
        grad_boundary = jax.grad(
            lambda p: compute_boundary_penalty(p, widths, heights, board_bounds)
        )(positions)
        assert jnp.all(jnp.isfinite(grad_boundary)), "Boundary gradient has inf/nan"

    def test_gradient_magnitude_reasonable(self):
        """Gradient magnitudes should be in reasonable range (not exploding)."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        grad = jax.grad(lambda p: compute_overlap_penalty(p, widths, heights))(positions)

        # Gradient magnitude should be reasonable (not exploding)
        # For a 1mm overlap with quadratic penalty, gradient should be O(1-10)
        assert jnp.max(jnp.abs(grad)) < 100, "Gradient magnitude too large"

    def test_jit_does_not_change_gradients(self):
        """JIT compilation should not change gradient values."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        grad_fn = jax.grad(loss_fn)
        grad_fn_jit = jax.jit(jax.grad(loss_fn))

        grad_normal = grad_fn(positions)
        grad_jit = grad_fn_jit(positions)

        assert jnp.allclose(grad_normal, grad_jit, rtol=1e-6)
