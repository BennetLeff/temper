import jax.numpy as jnp

from temper_placer.losses.regularization import compute_spread_penalty


def test_edge_spread_penalty():
    """Test that components near boundaries get additional penalty."""
    # A single component at x=5.0, y=50.0
    # Component size is 10x10, so half-diagonal is sqrt(5^2 + 5^2) approx 7.07mm
    positions = jnp.array([[5.0, 50.0]], dtype=jnp.float32)
    bounds = jnp.array([[10.0, 10.0]], dtype=jnp.float32)
    board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0], dtype=jnp.float32)
    min_distance = 5.0

    # Without board_bounds, a single component should have exactly 0 spread penalty
    penalty_no_board = compute_spread_penalty(positions, bounds, min_distance=min_distance)
    assert float(penalty_no_board) == 0.0

    # With board_bounds, the component is close to the left edge (dist=5.0mm)
    # half_diagonal = 7.07mm
    # Required distance = 7.07 + 5.0 = 12.07mm
    # deficit = 12.07 - 5.0 = 7.07mm
    # Expected penalty = 7.07^2 approx 50.0
    penalty_with_board = compute_spread_penalty(
        positions, bounds, board_bounds=board_bounds, min_distance=min_distance
    )
    assert float(penalty_with_board) > 40.0

def test_edge_spread_stable_center():
    """Test that components in the center have zero edge penalty."""
    # Component at the exact center of 100x100 board
    positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
    bounds = jnp.array([[10.0, 10.0]], dtype=jnp.float32)
    board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0], dtype=jnp.float32)
    min_distance = 5.0

    penalty = compute_spread_penalty(
        positions, bounds, board_bounds=board_bounds, min_distance=min_distance
    )
    # Far from all edges (50mm > 12.07mm), should be 0.0
    assert float(penalty) == 0.0

def test_edge_spread_gradient_pushes_inward():
    """Test that the gradient of edge spread pushes components away from the boundary."""
    import jax

    # Component near left edge
    positions = jnp.array([[2.0, 50.0]], dtype=jnp.float32)
    bounds = jnp.array([[10.0, 10.0]], dtype=jnp.float32)
    board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0], dtype=jnp.float32)
    min_distance = 5.0

    def loss_fn(p):
        return compute_spread_penalty(p, bounds, board_bounds, min_distance)

    grad = jax.grad(loss_fn)(positions)

    # Since it's near the left edge (x=0), the loss should decrease as x increases.
    # dLoss/dx should be negative.
    assert grad[0, 0] < 0.0
    # Y should be stable
    assert jnp.abs(grad[0, 1]) < 1e-5
