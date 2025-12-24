"""
Fuzzing and chaos testing for router robustness.

Uses random input generation to find edge cases and verify
the router handles unexpected inputs gracefully.
"""


import jax.numpy as jnp
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Pin
from temper_placer.routing.maze_router import MazeRouter


# Fuzzing strategies
@st.composite
def random_board(draw):
    """Generate random board configurations."""
    width = draw(st.floats(min_value=10.0, max_value=500.0))
    height = draw(st.floats(min_value=10.0, max_value=500.0))
    layers = draw(st.integers(min_value=1, max_value=4))
    return Board(width=width, height=height, origin=(0.0, 0.0), layer_count=layers)


@st.composite
def random_component(draw):
    """Generate random component configurations."""
    width = draw(st.floats(min_value=0.5, max_value=50.0))
    height = draw(st.floats(min_value=0.5, max_value=50.0))
    num_pins = draw(st.integers(min_value=0, max_value=20))

    pins = []
    for i in range(num_pins):
        px = draw(st.floats(min_value=-width/2, max_value=width/2))
        py = draw(st.floats(min_value=-height/2, max_value=height/2))
        pins.append(Pin(name=str(i), number=str(i), position=(px, py)))

    return Component(
        ref="FUZZ",
        footprint="FUZZ",
        bounds=(width, height),
        pins=pins,
    )


class TestFuzzingRobustness:
    """Fuzzing tests to find edge cases."""

    @given(
        board=random_board(),
        component=random_component(),
        cell_size=st.floats(min_value=0.1, max_value=5.0),
        margin=st.floats(min_value=0.0, max_value=10.0),
    )
    @settings(
        max_examples=1000,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_fuzz_block_components_never_crashes(self, board, component, cell_size, margin):
        """Fuzz: block_components should never crash on valid inputs."""
        assume(cell_size < min(board.width, board.height) / 2)  # Reasonable grid

        try:
            router = MazeRouter.from_board(board, cell_size_mm=cell_size, num_layers=board.layer_count)

            # Random position within board
            cx = board.width / 2
            cy = board.height / 2
            positions = jnp.array([[cx, cy]])

            router.block_components([component], positions, margin=margin)

            # Verify basic invariants
            assert jnp.all(router.occupancy >= 0), "No negative occupancy"
            assert jnp.all(router.occupancy <= 2), "No invalid occupancy"

        except Exception as e:
            pytest.fail(f"Fuzzing found crash: {e}")

    @given(
        width=st.floats(min_value=10.0, max_value=200.0),
        height=st.floats(min_value=10.0, max_value=200.0),
        cell_size=st.floats(min_value=0.1, max_value=5.0),
        start_x=st.integers(min_value=0, max_value=100),
        start_y=st.integers(min_value=0, max_value=100),
        end_x=st.integers(min_value=0, max_value=100),
        end_y=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=1000, deadline=None)
    def test_fuzz_pathfinding_never_crashes(self, width, height, cell_size, start_x, start_y, end_x, end_y):
        """Fuzz: pathfinding should never crash on valid inputs."""
        board = Board(width=width, height=height, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=cell_size, num_layers=2)

        # Clamp to grid bounds
        max_x = router.grid_size[0] - 1
        max_y = router.grid_size[1] - 1
        start_x = min(start_x, max_x)
        start_y = min(start_y, max_y)
        end_x = min(end_x, max_x)
        end_y = min(end_y, max_y)

        try:
            path = router.find_path((start_x, start_y), (end_x, end_y), layer=0)

            # If path found, verify it's valid
            if path is not None:
                assert len(path) > 0, "Path should have cells"
                assert path[0].x == start_x and path[0].y == start_y, "Path should start at start"
                if len(path) > 1:
                    assert path[-1].x == end_x and path[-1].y == end_y, "Path should end at end"

        except Exception as e:
            pytest.fail(f"Fuzzing found pathfinding crash: {e}")

    @given(
        num_components=st.integers(min_value=1, max_value=50),
        board_size=st.floats(min_value=50.0, max_value=200.0),
    )
    @settings(max_examples=200, deadline=None)
    def test_fuzz_dense_component_packing(self, num_components, board_size):
        """Fuzz: Dense component packing should not cause issues."""
        board = Board(width=board_size, height=board_size, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

        # Random components
        components = []
        positions_list = []

        for i in range(num_components):
            comp_size = 5.0  # Fixed size for simplicity
            component = Component(
                ref=f"U{i}",
                footprint="TEST",
                bounds=(comp_size, comp_size),
                pins=[],
            )
            components.append(component)

            # Random position
            cx = (i % 10) * (board_size / 10) + board_size / 20
            cy = (i // 10) * (board_size / 10) + board_size / 20
            positions_list.append([cx, cy])

        positions = jnp.array(positions_list)

        try:
            router.block_components(components, positions, margin=0.1)

            # Verify grid is still valid
            assert jnp.all(router.occupancy >= 0), "No negative occupancy"
            assert jnp.all(router.occupancy <= 2), "No invalid occupancy"

        except Exception as e:
            pytest.fail(f"Dense packing fuzzing found crash: {e}")


class RouterStateMachine(RuleBasedStateMachine):
    """Stateful fuzzing: random sequences of router operations."""

    def __init__(self):
        super().__init__()
        self.board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        self.router = MazeRouter.from_board(self.board, cell_size_mm=1.0, num_layers=2)
        self.components_blocked = 0
        self.paths_routed = 0

    @rule(
        comp_size=st.floats(min_value=2.0, max_value=10.0),
        cx=st.floats(min_value=10.0, max_value=90.0),
        cy=st.floats(min_value=10.0, max_value=90.0),
        margin=st.floats(min_value=0.0, max_value=2.0),
    )
    def block_component(self, comp_size, cx, cy, margin):
        """Rule: Block a random component."""
        component = Component(
            ref=f"U{self.components_blocked}",
            footprint="TEST",
            bounds=(comp_size, comp_size),
            pins=[],
        )
        positions = jnp.array([[cx, cy]])

        self.router.block_components([component], positions, margin=margin)
        self.components_blocked += 1

    @rule(
        start_x=st.integers(min_value=0, max_value=99),
        start_y=st.integers(min_value=0, max_value=99),
        end_x=st.integers(min_value=0, max_value=99),
        end_y=st.integers(min_value=0, max_value=99),
    )
    def route_path(self, start_x, start_y, end_x, end_y):
        """Rule: Try to route a path."""
        path = self.router.find_path((start_x, start_y), (end_x, end_y), layer=0)
        if path is not None:
            self.paths_routed += 1

    @invariant()
    def occupancy_is_valid(self):
        """Invariant: Occupancy must always be valid."""
        assert jnp.all(self.router.occupancy >= 0), "Occupancy must be non-negative"
        assert jnp.all(self.router.occupancy <= 2), "Occupancy must be <= 2"

    @invariant()
    def grid_size_unchanged(self):
        """Invariant: Grid size must never change."""
        assert self.router.grid_size == (100, 100), "Grid size must remain constant"


TestRouterStateMachine = RouterStateMachine.TestCase


class TestChaosEngineering:
    """Chaos testing: extreme and adversarial inputs."""

    def test_chaos_extremely_fine_grid(self):
        """Chaos: Extremely fine grid (0.01mm cells)."""
        board = Board(width=10.0, height=10.0, origin=(0.0, 0.0))

        # This creates a 1000x1000 grid
        router = MazeRouter.from_board(board, cell_size_mm=0.01, num_layers=2)

        component = Component(
            ref="U1", footprint="TEST",
            bounds=(1.0, 1.0), pins=[]
        )
        positions = jnp.array([[5.0, 5.0]])

        # Should handle without memory issues
        router.block_components([component], positions, margin=0.1)

        assert jnp.sum(router.occupancy == 1) > 0, "Should block cells"

    def test_chaos_extremely_coarse_grid(self):
        """Chaos: Extremely coarse grid (10mm cells)."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))

        # This creates a 10x10 grid
        router = MazeRouter.from_board(board, cell_size_mm=10.0, num_layers=2)

        component = Component(
            ref="U1", footprint="TEST",
            bounds=(5.0, 5.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])

        router.block_components([component], positions, margin=0.5)

        # Component smaller than cell size - should still block at least 1 cell
        assert jnp.sum(router.occupancy == 1) >= 1, "Should block at least one cell"

    def test_chaos_component_larger_than_board(self):
        """Chaos: Component larger than board."""
        board = Board(width=10.0, height=10.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

        # Huge component
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(50.0, 50.0), pins=[]
        )
        positions = jnp.array([[5.0, 5.0]])

        router.block_components([component], positions, margin=0.0)

        # Should block entire board
        total_cells = router.grid_size[0] * router.grid_size[1]
        blocked = jnp.sum(router.occupancy[:, :, 0] == 1)

        assert blocked >= total_cells * 0.9, "Should block most/all of board"

    def test_chaos_negative_coordinates(self):
        """Chaos: Negative board origin."""
        board = Board(width=100.0, height=100.0, origin=(-50.0, -50.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        # Component at origin (which is -50, -50 in world coords)
        positions = jnp.array([[0.0, 0.0]])

        router.block_components([component], positions, margin=0.5)

        assert jnp.sum(router.occupancy == 1) > 0, "Should handle negative origins"

    def test_chaos_floating_point_precision(self):
        """Chaos: Floating point precision edge cases."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.333333, num_layers=2)

        component = Component(
            ref="U1", footprint="TEST",
            bounds=(3.141592, 2.718281), pins=[]
        )
        positions = jnp.array([[50.123456, 50.654321]])

        router.block_components([component], positions, margin=0.707106)

        # Should handle floating point without errors
        assert jnp.all(jnp.isfinite(router.occupancy)), "No NaN/Inf values"
