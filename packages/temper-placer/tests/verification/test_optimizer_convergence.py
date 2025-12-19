"""
Optimizer convergence tests with known optimal solutions.

These tests verify that gradient-based optimization can solve trivial placement
problems where the optimal solution is known analytically. This validates that:
1. Loss functions have correct gradient direction (negative gradient reduces loss)
2. The optimizer can actually minimize the loss
3. The system converges to physically valid solutions

Test Philosophy:
- Use extremely simple scenarios (2 components, single constraint)
- Known optimal solutions with analytical verification
- Fast convergence (< 1000 steps)
- No curriculum, no complex scheduling - just raw optimization

These are NOT performance tests. They verify mathematical correctness of the
optimization pipeline. If these fail, there's a fundamental bug in the loss
functions or gradients.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import pytest
from jax import Array
import optax

# Import loss functions
from temper_placer.losses.overlap import compute_overlap_penalty
from temper_placer.losses.boundary import compute_boundary_penalty


# =============================================================================
# Helper Functions
# =============================================================================


def simple_gradient_descent(
    loss_fn,
    initial_params: Array,
    learning_rate: float = 0.1,
    max_steps: int = 1000,
    convergence_threshold: float = 1e-6,
    loss_threshold: float = 0.01,
) -> tuple[Array, float, int]:
    """
    Run simple gradient descent until convergence.

    Args:
        loss_fn: Scalar loss function taking params array
        initial_params: Starting point
        learning_rate: Step size
        max_steps: Maximum iterations
        convergence_threshold: Stop if loss change < this
        loss_threshold: Stop if loss < this (problem solved)

    Returns:
        Tuple of (final_params, final_loss, steps_taken)
    """
    optimizer = optax.adam(learning_rate)
    opt_state = optimizer.init(initial_params)
    params = initial_params

    grad_fn = jax.grad(loss_fn)
    prev_loss = float("inf")

    for step in range(max_steps):
        loss = float(loss_fn(params))

        # Check if solved
        if loss < loss_threshold:
            return params, loss, step

        # Check convergence
        if abs(prev_loss - loss) < convergence_threshold and loss < 1.0:
            return params, loss, step

        # Gradient step
        grads = grad_fn(params)
        updates, opt_state = optimizer.update(grads, opt_state, params)
        params = optax.apply_updates(params, updates)

        prev_loss = loss

    return params, float(loss_fn(params)), max_steps


# =============================================================================
# Test: Two Overlapping Components Must Separate
# =============================================================================


class TestOverlapConvergence:
    """
    Test that overlapping components are pushed apart by gradient descent.

    Scenario:
    - Two 20x20mm components on a 100x100mm board
    - Both start at the center (fully overlapping)
    - Optimal solution: Any placement where they don't overlap
    """

    def test_overlapping_boxes_separate(self):
        """Two overlapping boxes should separate after optimization."""
        # Setup: Two 20x20 boxes at the same location
        widths = jnp.array([20.0, 20.0])
        heights = jnp.array([20.0, 20.0])

        # Start both at center (maximum overlap = 400 mm²)
        initial_positions = jnp.array([[50.0, 50.0], [50.0, 50.0]])

        def loss_fn(positions):
            return compute_overlap_penalty(positions, widths, heights)

        # Verify initial overlap is large
        initial_loss = float(loss_fn(initial_positions))
        assert initial_loss > 100, f"Expected large initial overlap, got {initial_loss}"

        # Run optimization
        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=500,
            loss_threshold=0.01,
        )

        # Verify overlap is essentially zero
        assert final_loss < 0.1, f"Expected overlap < 0.1, got {final_loss} after {steps} steps"

        # Verify components actually moved apart
        distance = jnp.linalg.norm(final_positions[0] - final_positions[1])
        min_separation = 20.0  # Need at least 20mm apart (sum of half-widths)
        assert distance >= min_separation - 0.5, (
            f"Components only {distance:.1f}mm apart, need {min_separation}"
        )

    def test_three_overlapping_boxes(self):
        """Three overlapping boxes should all separate."""
        widths = jnp.array([15.0, 15.0, 15.0])
        heights = jnp.array([15.0, 15.0, 15.0])

        # All start at center
        initial_positions = jnp.array(
            [
                [50.0, 50.0],
                [50.0, 50.0],
                [50.0, 50.0],
            ]
        )

        def loss_fn(positions):
            return compute_overlap_penalty(positions, widths, heights)

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=500,
            loss_threshold=0.1,
        )

        assert final_loss < 1.0, f"Expected overlap < 1.0, got {final_loss}"

    def test_partial_overlap_resolves(self):
        """Partially overlapping boxes should fully separate."""
        widths = jnp.array([20.0, 20.0])
        heights = jnp.array([20.0, 20.0])

        # Start with partial overlap (centers 10mm apart, boxes are 20mm wide)
        initial_positions = jnp.array([[45.0, 50.0], [55.0, 50.0]])

        def loss_fn(positions):
            return compute_overlap_penalty(positions, widths, heights)

        # Should have some overlap initially
        initial_loss = float(loss_fn(initial_positions))
        assert initial_loss > 0, "Expected some initial overlap"

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=200,
            loss_threshold=0.01,
        )

        assert final_loss < 0.1, f"Expected overlap resolved, got {final_loss}"


# =============================================================================
# Test: Out-of-Bounds Component Returns Inside
# =============================================================================


class TestBoundaryConvergence:
    """
    Test that out-of-bounds components are pushed back inside the board.

    Scenario:
    - Single component partially outside the board
    - Optimal solution: Component fully inside board
    """

    def test_component_pushed_inside_from_left(self):
        """Component violating left boundary should move right."""
        widths = jnp.array([20.0])
        heights = jnp.array([20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Start with left edge at -5mm (center at x=5, half-width=10)
        initial_positions = jnp.array([[5.0, 50.0]])

        def loss_fn(positions):
            return compute_boundary_penalty(positions, widths, heights, board_bounds)

        # Should have boundary violation
        initial_loss = float(loss_fn(initial_positions))
        assert initial_loss > 0, "Expected boundary violation"

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=200,
            loss_threshold=0.01,
        )

        # Verify no violation
        assert final_loss < 0.1, f"Expected no boundary violation, got {final_loss}"

        # Verify component moved right (x >= 10 for left edge at 0)
        assert final_positions[0, 0] >= 9.5, f"Expected x >= 10, got {final_positions[0, 0]}"

    def test_component_pushed_inside_from_right(self):
        """Component violating right boundary should move left."""
        widths = jnp.array([20.0])
        heights = jnp.array([20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Start with right edge at 105mm (center at x=95, half-width=10)
        initial_positions = jnp.array([[95.0, 50.0]])

        def loss_fn(positions):
            return compute_boundary_penalty(positions, widths, heights, board_bounds)

        initial_loss = float(loss_fn(initial_positions))
        assert initial_loss > 0, "Expected boundary violation"

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=200,
            loss_threshold=0.01,
        )

        assert final_loss < 0.1, f"Expected no boundary violation, got {final_loss}"
        # x <= 90 for right edge at 100
        assert final_positions[0, 0] <= 90.5, f"Expected x <= 90, got {final_positions[0, 0]}"

    def test_component_pushed_inside_from_corner(self):
        """Component violating corner should move diagonally inside."""
        widths = jnp.array([20.0])
        heights = jnp.array([20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Start at corner (violates both left and bottom)
        initial_positions = jnp.array([[5.0, 5.0]])

        def loss_fn(positions):
            return compute_boundary_penalty(positions, widths, heights, board_bounds)

        initial_loss = float(loss_fn(initial_positions))
        assert initial_loss > 0, "Expected boundary violation"

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=200,
            loss_threshold=0.01,
        )

        assert final_loss < 0.1, f"Expected no boundary violation, got {final_loss}"
        # Should be at least (10, 10) to be fully inside
        assert final_positions[0, 0] >= 9.5 and final_positions[0, 1] >= 9.5, (
            f"Expected position >= (10, 10), got {final_positions[0]}"
        )


# =============================================================================
# Test: Combined Overlap and Boundary
# =============================================================================


class TestCombinedConstraints:
    """
    Test optimization with multiple constraints active simultaneously.

    This is closer to real-world scenarios where components must both
    avoid each other AND stay inside the board.
    """

    def test_overlap_and_boundary_combined(self):
        """Components should separate AND stay inside board."""
        widths = jnp.array([20.0, 20.0])
        heights = jnp.array([20.0, 20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Start overlapping near left edge
        initial_positions = jnp.array([[15.0, 50.0], [15.0, 50.0]])

        def loss_fn(positions):
            overlap = compute_overlap_penalty(positions, widths, heights)
            boundary = compute_boundary_penalty(positions, widths, heights, board_bounds)
            return overlap + boundary

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=500,
            loss_threshold=0.1,
        )

        # Check overlap resolved
        overlap_loss = compute_overlap_penalty(final_positions, widths, heights)
        assert float(overlap_loss) < 1.0, f"Overlap not resolved: {float(overlap_loss)}"

        # Check boundary satisfied
        boundary_loss = compute_boundary_penalty(final_positions, widths, heights, board_bounds)
        assert float(boundary_loss) < 1.0, f"Boundary violated: {float(boundary_loss)}"

    def test_many_components_feasible(self):
        """
        Many small components should find a feasible arrangement.

        This tests that the optimizer can handle more complex scenarios
        without getting stuck in local minima too badly.
        """
        n_components = 4
        widths = jnp.array([15.0] * n_components)
        heights = jnp.array([15.0] * n_components)
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        # Start all at center
        initial_positions = jnp.array([[50.0, 50.0]] * n_components)

        def loss_fn(positions):
            overlap = compute_overlap_penalty(positions, widths, heights)
            boundary = compute_boundary_penalty(positions, widths, heights, board_bounds)
            return overlap + boundary

        final_positions, final_loss, steps = simple_gradient_descent(
            loss_fn,
            initial_positions,
            learning_rate=1.0,
            max_steps=1000,
            loss_threshold=1.0,
        )

        # Relaxed threshold - we just want feasibility, not perfection
        assert final_loss < 10.0, f"Could not find feasible placement: loss={final_loss}"


# =============================================================================
# Test: Gradient Descent Direction Sanity
# =============================================================================


class TestGradientDirection:
    """
    Verify that a single gradient step moves in the right direction.

    These are sanity checks that don't require full convergence - just
    one step should reduce the loss (for sufficiently small step size).
    """

    def test_single_step_reduces_overlap(self):
        """One gradient step should reduce overlap loss."""
        widths = jnp.array([20.0, 20.0])
        heights = jnp.array([20.0, 20.0])
        positions = jnp.array([[50.0, 50.0], [55.0, 50.0]])  # Overlapping

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        initial_loss = float(loss_fn(positions))
        grad = jax.grad(loss_fn)(positions)

        # Take a small step in negative gradient direction
        lr = 0.1
        new_positions = positions - lr * grad
        new_loss = float(loss_fn(new_positions))

        assert new_loss < initial_loss, (
            f"Gradient step increased loss: {initial_loss} -> {new_loss}"
        )

    def test_single_step_reduces_boundary_violation(self):
        """One gradient step should reduce boundary violation."""
        widths = jnp.array([20.0])
        heights = jnp.array([20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])
        positions = jnp.array([[5.0, 50.0]])  # Violating left boundary

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        initial_loss = float(loss_fn(positions))
        grad = jax.grad(loss_fn)(positions)

        # Take a small step in negative gradient direction
        lr = 0.1
        new_positions = positions - lr * grad
        new_loss = float(loss_fn(new_positions))

        assert new_loss < initial_loss, (
            f"Gradient step increased loss: {initial_loss} -> {new_loss}"
        )


# =============================================================================
# Test: Non-Overlapping Components Stay Put
# =============================================================================


class TestStability:
    """
    Verify that already-feasible placements have zero/small gradients.

    If components are already well-placed, optimization shouldn't move them.
    """

    def test_separated_components_stable(self):
        """Non-overlapping components should have zero overlap gradient."""
        widths = jnp.array([20.0, 20.0])
        heights = jnp.array([20.0, 20.0])
        # Well separated - 30mm apart, need 20mm
        positions = jnp.array([[30.0, 50.0], [70.0, 50.0]])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        loss = float(loss_fn(positions))
        grad = jax.grad(loss_fn)(positions)

        assert loss < 0.01, f"Expected zero loss, got {loss}"
        assert jnp.allclose(grad, 0.0, atol=1e-6), f"Expected zero gradient, got {grad}"

    def test_inside_component_stable(self):
        """Component fully inside board should have zero boundary gradient."""
        widths = jnp.array([20.0])
        heights = jnp.array([20.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])
        positions = jnp.array([[50.0, 50.0]])  # Centered, fully inside

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds)

        loss = float(loss_fn(positions))
        grad = jax.grad(loss_fn)(positions)

        assert loss < 0.01, f"Expected zero loss, got {loss}"
        assert jnp.allclose(grad, 0.0, atol=1e-6), f"Expected zero gradient, got {grad}"
