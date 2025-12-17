"""
Edge case tests for temper-placer.

These tests verify graceful handling of edge cases that may occur in real usage:
- Empty netlists (0 components)
- Single component placement
- Components larger than board
- Empty nets
- Boundary conditions

Reference: temper-r2i.7 - Add defensive edge-case tests
"""

import pytest
import jax
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.overlap import OverlapLoss, compute_overlap_penalty
from temper_placer.losses.boundary import BoundaryLoss, compute_boundary_penalty
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.regularization import SpreadLoss, compute_spread_penalty


class TestEmptyNetlist:
    """Tests for handling empty netlists (0 components)."""

    @pytest.fixture
    def empty_netlist(self):
        """Create an empty netlist."""
        return Netlist(components=[], nets=[])

    @pytest.fixture
    def simple_board(self):
        """Create a simple board."""
        return Board(width=100.0, height=100.0)

    def test_empty_positions_overlap(self):
        """Test overlap computation with empty positions."""
        positions = jnp.zeros((0, 2), dtype=jnp.float32)
        widths = jnp.zeros((0,), dtype=jnp.float32)
        heights = jnp.zeros((0,), dtype=jnp.float32)

        result = compute_overlap_penalty(positions, widths, heights)
        assert jnp.isfinite(result)
        assert float(result) == 0.0

    def test_empty_positions_boundary(self, simple_board):
        """Test boundary computation with empty positions."""
        positions = jnp.zeros((0, 2), dtype=jnp.float32)
        widths = jnp.zeros((0,), dtype=jnp.float32)
        heights = jnp.zeros((0,), dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        assert float(result) == 0.0

    def test_empty_positions_spread(self):
        """Test spread computation with empty positions."""
        positions = jnp.zeros((0, 2), dtype=jnp.float32)
        bounds = jnp.zeros((0, 2), dtype=jnp.float32)

        result = compute_spread_penalty(positions, bounds)
        assert jnp.isfinite(result)
        assert float(result) == 0.0

    def test_placement_state_empty(self):
        """Test PlacementState with 0 components."""
        positions = jnp.zeros((0, 2), dtype=jnp.float32)
        rotation_logits = jnp.zeros((0, 4), dtype=jnp.float32)

        state = PlacementState(positions=positions, rotation_logits=rotation_logits)
        assert state.n_components == 0

        # to_discrete should work
        pos, rot = state.to_discrete()
        assert pos.shape == (0, 2)
        assert rot.shape == (0,)


class TestSingleComponent:
    """Tests for handling single-component placements."""

    @pytest.fixture
    def single_component_netlist(self):
        """Create a netlist with a single component."""
        comp = Component(
            ref="U1",
            footprint="Test",
            bounds=(10.0, 10.0),
            pins=[Pin(name="1", number="1", position=(0, 0))],
        )
        return Netlist(components=[comp], nets=[])

    @pytest.fixture
    def simple_board(self):
        """Create a simple board."""
        return Board(width=100.0, height=100.0)

    def test_single_component_overlap(self):
        """Test overlap loss with single component returns 0."""
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        widths = jnp.array([10.0], dtype=jnp.float32)
        heights = jnp.array([10.0], dtype=jnp.float32)

        result = compute_overlap_penalty(positions, widths, heights)
        assert jnp.isfinite(result)
        assert float(result) == 0.0  # No overlaps possible with 1 component

    def test_single_component_spread(self):
        """Test spread loss with single component returns 0."""
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        bounds = jnp.array([[10.0, 10.0]], dtype=jnp.float32)

        result = compute_spread_penalty(positions, bounds)
        assert jnp.isfinite(result)
        assert float(result) == 0.0  # No spread penalty with 1 component

    def test_single_component_boundary(self, simple_board):
        """Test boundary loss with single component inside board."""
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        widths = jnp.array([10.0], dtype=jnp.float32)
        heights = jnp.array([10.0], dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        assert float(result) == 0.0  # Component inside board

    def test_single_component_gradient(self, simple_board):
        """Test that gradients work for single component."""
        widths = jnp.array([10.0], dtype=jnp.float32)
        heights = jnp.array([10.0], dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        def loss_fn(positions):
            return compute_boundary_penalty(positions, widths, heights, board_bounds)

        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        grad = jax.grad(loss_fn)(positions)

        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))


class TestOversizedComponent:
    """Tests for components larger than the board."""

    @pytest.fixture
    def small_board(self):
        """Create a small board."""
        return Board(width=50.0, height=50.0)

    def test_oversized_component_boundary(self, small_board):
        """Test boundary loss with component larger than board."""
        # Component is 100x100, board is 50x50
        positions = jnp.array([[25.0, 25.0]], dtype=jnp.float32)  # Centered
        widths = jnp.array([100.0], dtype=jnp.float32)
        heights = jnp.array([100.0], dtype=jnp.float32)
        board_bounds = small_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        assert float(result) > 0  # Should have significant boundary violation

    def test_oversized_component_gradient(self, small_board):
        """Test that gradients are finite for oversized component."""
        widths = jnp.array([100.0], dtype=jnp.float32)
        heights = jnp.array([100.0], dtype=jnp.float32)
        board_bounds = small_board.get_bounds_array()

        def loss_fn(positions):
            return compute_boundary_penalty(positions, widths, heights, board_bounds)

        positions = jnp.array([[25.0, 25.0]], dtype=jnp.float32)
        grad = jax.grad(loss_fn)(positions)

        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))


class TestEmptyNets:
    """Tests for handling netlists with no nets."""

    @pytest.fixture
    def no_nets_netlist(self):
        """Create a netlist with components but no nets."""
        components = [
            Component(
                ref=f"C{i}",
                footprint="Test",
                bounds=(5.0, 5.0),
                pins=[Pin(name="1", number="1", position=(0, 0))],
            )
            for i in range(5)
        ]
        return Netlist(components=components, nets=[])

    @pytest.fixture
    def simple_board(self):
        """Create a simple board."""
        return Board(width=100.0, height=100.0)

    def test_wirelength_no_nets(self, no_nets_netlist, simple_board):
        """Test wirelength loss with no nets returns 0."""
        positions = jax.random.uniform(jax.random.PRNGKey(0), (5, 2)) * 80 + 10
        rotations = jnp.zeros((5, 4)).at[:, 0].set(1.0)  # All 0° rotation

        context = LossContext(
            netlist=no_nets_netlist,
            board=simple_board,
            bounds=jnp.full((5, 2), 5.0),
            fixed_mask=jnp.zeros(5, dtype=jnp.bool_),
        )

        loss_fn = WirelengthLoss()
        result = loss_fn(positions, rotations, context)

        assert jnp.isfinite(result.value)
        # With no nets, wirelength should be 0 or near-0
        assert float(result.value) >= 0


class TestAllComponentsSameNet:
    """Tests for edge case where all components are on the same net."""

    @pytest.fixture
    def single_net_netlist(self):
        """Create a netlist with all components on one net."""
        components = [
            Component(
                ref=f"C{i}",
                footprint="Test",
                bounds=(5.0, 5.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="NET1")],
            )
            for i in range(10)
        ]
        pins = [(f"C{i}", "1") for i in range(10)]
        nets = [Net(name="NET1", pins=pins)]
        return Netlist(components=components, nets=nets)

    @pytest.fixture
    def simple_board(self):
        """Create a simple board."""
        return Board(width=100.0, height=100.0)

    def test_wirelength_single_large_net(self, single_net_netlist, simple_board):
        """Test wirelength loss with all components on one net."""
        positions = jax.random.uniform(jax.random.PRNGKey(0), (10, 2)) * 80 + 10
        rotations = jnp.zeros((10, 4)).at[:, 0].set(1.0)

        context = LossContext(
            netlist=single_net_netlist,
            board=simple_board,
            bounds=jnp.full((10, 2), 5.0),
            fixed_mask=jnp.zeros(10, dtype=jnp.bool_),
        )

        loss_fn = WirelengthLoss()
        result = loss_fn(positions, rotations, context)

        assert jnp.isfinite(result.value)
        assert float(result.value) >= 0

    def test_wirelength_gradient_single_net(self, single_net_netlist, simple_board):
        """Test gradients work for single-net case."""
        rotations = jnp.zeros((10, 4)).at[:, 0].set(1.0)

        context = LossContext(
            netlist=single_net_netlist,
            board=simple_board,
            bounds=jnp.full((10, 2), 5.0),
            fixed_mask=jnp.zeros(10, dtype=jnp.bool_),
        )

        loss_fn = WirelengthLoss()

        def loss_wrapper(pos):
            return loss_fn(pos, rotations, context).value

        positions = jax.random.uniform(jax.random.PRNGKey(0), (10, 2)) * 80 + 10
        grad = jax.grad(loss_wrapper)(positions)

        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))


class TestBoundaryConditions:
    """Tests for boundary condition edge cases."""

    @pytest.fixture
    def simple_board(self):
        """Create a simple board."""
        return Board(width=100.0, height=100.0)

    def test_component_exactly_on_boundary(self, simple_board):
        """Test component placed exactly on board boundary."""
        # Component edge exactly at board edge (no violation)
        positions = jnp.array([[5.0, 50.0]], dtype=jnp.float32)  # 5mm from left edge
        widths = jnp.array([10.0], dtype=jnp.float32)  # 5mm half-width
        heights = jnp.array([10.0], dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        # Should be at or very near 0 (component edge at board edge)
        assert float(result) < 1.0

    def test_component_at_corner(self, simple_board):
        """Test component placed at board corner."""
        # Component centered at corner (will violate both x and y)
        positions = jnp.array([[0.0, 0.0]], dtype=jnp.float32)
        widths = jnp.array([10.0], dtype=jnp.float32)
        heights = jnp.array([10.0], dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        assert float(result) > 0  # Should have boundary violation

    def test_component_completely_outside(self, simple_board):
        """Test component placed completely outside board."""
        positions = jnp.array([[-100.0, -100.0]], dtype=jnp.float32)
        widths = jnp.array([10.0], dtype=jnp.float32)
        heights = jnp.array([10.0], dtype=jnp.float32)
        board_bounds = simple_board.get_bounds_array()

        result = compute_boundary_penalty(positions, widths, heights, board_bounds)
        assert jnp.isfinite(result)
        assert float(result) > 0  # Large boundary violation


class TestRandomStateInitialization:
    """Tests for PlacementState random initialization edge cases."""

    def test_random_init_zero_margin(self):
        """Test random init with zero margin."""
        key = jax.random.PRNGKey(0)
        state = PlacementState.random_init(
            n_components=10,
            board_width=100.0,
            board_height=100.0,
            key=key,
            margin=0.0,
        )

        assert state.n_components == 10
        assert jnp.all(jnp.isfinite(state.positions))
        # Positions should be within [0, 100] range
        assert jnp.all(state.positions >= 0)
        assert jnp.all(state.positions <= 100)

    def test_random_init_large_margin(self):
        """Test random init with margin larger than half the board."""
        key = jax.random.PRNGKey(0)
        # margin=60 on a 100mm board leaves only a 40mm center strip
        # but the minval would be 60, maxval would be 40 (inverted!)
        # This should still produce valid results due to JAX uniform behavior
        state = PlacementState.random_init(
            n_components=5,
            board_width=100.0,
            board_height=100.0,
            key=key,
            margin=60.0,  # Very large margin
        )

        assert state.n_components == 5
        # Positions should still be finite
        assert jnp.all(jnp.isfinite(state.positions))

    def test_random_init_small_board(self):
        """Test random init with very small board."""
        key = jax.random.PRNGKey(0)
        state = PlacementState.random_init(
            n_components=3,
            board_width=10.0,
            board_height=10.0,
            key=key,
            margin=2.0,
        )

        assert state.n_components == 3
        assert jnp.all(jnp.isfinite(state.positions))
        # Positions should be within margin bounds
        assert jnp.all(state.positions >= 2.0)
        assert jnp.all(state.positions <= 8.0)
