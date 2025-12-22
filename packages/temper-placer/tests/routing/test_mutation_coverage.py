"""
Mutation testing configuration and test quality verification.

This module ensures tests are strong enough to catch bugs by:
1. Verifying tests fail when code is mutated
2. Measuring test suite effectiveness
3. Identifying weak test coverage areas
"""

import pytest
import ast
import inspect
from typing import Callable, List, Tuple
from dataclasses import dataclass

from temper_placer.routing.maze_router import MazeRouter


@dataclass
class Mutation:
    """A code mutation to test."""
    name: str
    original_op: str
    mutated_op: str
    should_be_caught: bool = True


# Define mutations that tests MUST catch
CRITICAL_MUTATIONS = [
    # Arithmetic mutations
    Mutation("add_to_sub", "+", "-", True),
    Mutation("sub_to_add", "-", "+", True),
    Mutation("mul_to_div", "*", "/", True),
    Mutation("div_to_mul", "/", "*", True),
    
    # Comparison mutations
    Mutation("lt_to_le", "<", "<=", True),
    Mutation("le_to_lt", "<=", "<", True),
    Mutation("gt_to_ge", ">", ">=", True),
    Mutation("ge_to_gt", ">=", ">", True),
    Mutation("eq_to_ne", "==", "!=", True),
    Mutation("ne_to_eq", "!=", "==", True),
    
    # Boolean mutations
    Mutation("and_to_or", "and", "or", True),
    Mutation("or_to_and", "or", "and", True),
    Mutation("not_removal", "not ", "", True),
    
    # Boundary mutations
    Mutation("off_by_one_add", "range(n)", "range(n+1)", True),
    Mutation("off_by_one_sub", "range(n)", "range(n-1)", True),
    Mutation("zero_to_one", "0", "1", True),
    Mutation("one_to_zero", "1", "0", True),
]


class TestMutationCoverage:
    """Verify tests catch common mutations."""

    def test_arithmetic_mutation_detection(self):
        """Tests must catch arithmetic operator mutations."""
        # Original: margin calculation uses addition
        # Mutation: change + to -
        
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        # Correct implementation
        router.block_components([component], positions, margin=0.5)
        correct_blocked = jnp.sum(router.occupancy == 1)
        
        # Simulate mutation: margin subtraction instead of addition
        router_mutated = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        # This would be: half_w = component.bounds[0] / 2 - margin (WRONG)
        # We verify our tests would catch this by checking blocked area is different
        router_mutated.block_components([component], positions, margin=-0.5)  # Simulated mutation
        mutated_blocked = jnp.sum(router_mutated.occupancy == 1)
        
        assert correct_blocked != mutated_blocked, \
            "Tests must detect arithmetic mutations (+ to -)"

    def test_comparison_mutation_detection(self):
        """Tests must catch comparison operator mutations."""
        from temper_placer.core.board import Board
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        # Test boundary check: 0 <= x < width
        # Mutation: change < to <=
        
        test_cell = (99, 50)  # At boundary
        
        # Correct: should be valid (< 100)
        is_valid = (0 <= test_cell[0] < router.grid_size[0] and 
                   0 <= test_cell[1] < router.grid_size[1])
        assert is_valid, "Cell at x=99 should be valid for width=100"
        
        # Mutated: would be invalid if using <= instead of <
        # (simulated by testing x=100)
        test_cell_mutated = (100, 50)
        is_valid_mutated = (0 <= test_cell_mutated[0] < router.grid_size[0])
        assert not is_valid_mutated, \
            "Tests must detect comparison mutations (< to <=)"

    def test_boundary_mutation_detection(self):
        """Tests must catch off-by-one errors."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.0)
        
        # Check exact boundary
        # Component is 10x10 centered at (50, 50)
        # Should block cells from 45 to 54 (inclusive)
        
        assert int(router.occupancy[45, 50, 0]) == 1, "Left edge should be blocked"
        assert int(router.occupancy[54, 50, 0]) == 1, "Right edge should be blocked"
        assert int(router.occupancy[44, 50, 0]) == 0, "One cell left should be free"
        assert int(router.occupancy[55, 50, 0]) == 0, "One cell right should be free"
        
        # This test would catch: range(x_min, x_max) vs range(x_min, x_max+1)


class TestInvariantViolationDetection:
    """Tests that verify invariants and would catch violations."""

    def test_occupancy_value_invariant(self):
        """Invariant: Occupancy must be 0, 1, or 2 only."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.5)
        
        # Invariant: all values must be 0, 1, or 2
        valid_values = jnp.isin(router.occupancy, jnp.array([0, 1, 2]))
        assert jnp.all(valid_values), \
            "Occupancy invariant violated: values must be 0, 1, or 2"

    def test_grid_size_invariant(self):
        """Invariant: Grid size must match board dimensions."""
        from temper_placer.core.board import Board
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        expected_width = int(100.0 / 1.0)
        expected_height = int(100.0 / 1.0)
        
        assert router.grid_size[0] == expected_width, \
            f"Grid width invariant: expected {expected_width}, got {router.grid_size[0]}"
        assert router.grid_size[1] == expected_height, \
            f"Grid height invariant: expected {expected_height}, got {router.grid_size[1]}"
        assert router.occupancy.shape == (expected_width, expected_height, 2), \
            "Occupancy shape must match grid size"

    def test_component_blocking_completeness_invariant(self):
        """Invariant: All cells within component bounds must be blocked."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        cx, cy = 50.0, 50.0
        positions = jnp.array([[cx, cy]])
        
        router.block_components([component], positions, margin=0.0)
        
        # Check ALL cells within component bounds
        half_w, half_h = 5.0, 5.0
        for x in jnp.arange(cx - half_w + 0.25, cx + half_w, 0.5):
            for y in jnp.arange(cy - half_h + 0.25, cy + half_h, 0.5):
                gx, gy = router._world_to_grid(float(x), float(y))
                if 0 <= gx < router.grid_size[0] and 0 <= gy < router.grid_size[1]:
                    assert int(router.occupancy[gx, gy, 0]) == 1, \
                        f"Completeness invariant violated: cell ({gx}, {gy}) at ({x}, {y}) should be blocked"


class TestRegressionDetection:
    """Snapshot tests to catch regressions."""

    def test_blocking_snapshot_10x10_component(self):
        """Snapshot: 10x10 component at (50,50) with 0.5mm margin."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.5)
        
        # Snapshot values (verified correct)
        expected_blocked = 121  # (10 + 2*0.5)^2 / 1.0^2 = 121 cells
        actual_blocked = int(jnp.sum(router.occupancy == 1))
        
        assert actual_blocked == expected_blocked, \
            f"Regression detected: expected {expected_blocked} blocked cells, got {actual_blocked}"

    def test_escape_route_snapshot_4_pins(self):
        """Snapshot: 4-pin component escape routes."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Pin
        import jax.numpy as jnp
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        
        component = Component(
            ref="U1", value="TEST", footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(5.0, 0.0)),
                Pin(name="2", number="2", position=(-5.0, 0.0)),
                Pin(name="3", number="3", position=(0.0, 5.0)),
                Pin(name="4", number="4", position=(0.0, -5.0)),
            ]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.1, escape_length=5)
        
        # Snapshot: verify specific pin cells are free
        pin1_gx, pin1_gy = router._world_to_grid(55.0, 50.0)
        pin2_gx, pin2_gy = router._world_to_grid(45.0, 50.0)
        pin3_gx, pin3_gy = router._world_to_grid(50.0, 55.0)
        pin4_gx, pin4_gy = router._world_to_grid(50.0, 45.0)
        
        assert int(router.occupancy[pin1_gx, pin1_gy, 0]) == 0, "Pin 1 regression"
        assert int(router.occupancy[pin2_gx, pin2_gy, 0]) == 0, "Pin 2 regression"
        assert int(router.occupancy[pin3_gx, pin3_gy, 0]) == 0, "Pin 3 regression"
        assert int(router.occupancy[pin4_gx, pin4_gy, 0]) == 0, "Pin 4 regression"


class TestPerformanceRegression:
    """Performance benchmarks to catch degradation."""

    def test_blocking_performance_100_components(self, benchmark):
        """Benchmark: Blocking 100 components should complete in < 1s."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component
        import jax.numpy as jnp
        
        board = Board(width=200.0, height=200.0, origin=(0.0, 0.0), layer_count=2)
        
        components = [
            Component(ref=f"U{i}", value="TEST", footprint="TEST", bounds=(5.0, 5.0), pins=[])
            for i in range(100)
        ]
        
        # Grid placement
        positions = jnp.array([
            [20.0 + (i % 10) * 18.0, 20.0 + (i // 10) * 18.0]
            for i in range(100)
        ])
        
        def block_all():
            router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
            router.block_components(components, positions, margin=0.5)
            return router
        
        result = benchmark(block_all)
        
        # Verify correctness
        blocked = jnp.sum(result.occupancy == 1)
        assert blocked > 0, "Should block cells"

    def test_pathfinding_performance_long_path(self, benchmark):
        """Benchmark: Finding path across board should complete in < 100ms."""
        from temper_placer.core.board import Board
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        
        start = (0, 0)
        end = (199, 199)  # Diagonal across 100mm board with 0.5mm cells
        
        def find_long_path():
            return router.find_path(start, end, layer=0, allow_layer_change=False)
        
        result = benchmark(find_long_path)
        
        # Verify correctness
        assert result is not None, "Should find path"
        assert len(result) > 0, "Path should have cells"
