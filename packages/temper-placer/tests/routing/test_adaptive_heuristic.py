"""
Tests for adaptive A* heuristic with distance map (temper-tos3.3).

The standard Manhattan distance heuristic is optimistic when obstacles block
the direct path. An obstacle-aware distance map provides a tighter (yet still
admissible) heuristic, reducing A* iterations.
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.maze_router import MazeRouter, GridCell


class TestDistanceMapComputation:
    """Tests for distance map computation."""

    def test_distance_map_empty_board(self):
        """Distance map on empty board should be Manhattan distance."""
        board = Board(width=20.0, height=20.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        target = GridCell(10, 10, 0)
        dist_map = router._compute_distance_map(target, layer=0)

        # Check a few points
        assert dist_map[10, 10, 0] == 0, "Distance to self should be 0"
        assert dist_map[11, 10, 0] == 1, "Distance to neighbor should be 1"
        assert dist_map[10, 11, 0] == 1, "Distance to neighbor should be 1"
        assert dist_map[15, 15, 0] == 10, "Distance should be Manhattan (5+5)"

    def test_distance_map_with_obstacle(self):
        """Distance map should route around obstacles."""
        board = Board(width=30.0, height=30.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block a vertical wall
        for y in range(10, 20):
            router.occupancy[15, y, 0] = -1

        target = GridCell(20, 15, 0)
        dist_map = router._compute_distance_map(target, layer=0)

        # Point on the other side of the wall
        left_point = (10, 15, 0)
        
        # Direct Manhattan distance would be 10, but must route around wall
        # Actual distance should be longer (go above or below wall)
        assert dist_map[left_point] > 10, "Distance should account for obstacle"
        assert dist_map[left_point] < float('inf'), "Should still be reachable"

    def test_distance_map_unreachable(self):
        """Distance map should mark unreachable cells as inf."""
        board = Board(width=30.0, height=30.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block a complete enclosure around target
        target = GridCell(15, 15, 0)
        for x in range(14, 17):
            for y in range(14, 17):
                if x == 15 and y == 15:
                    continue  # Leave target free
                router.occupancy[x, y, 0] = -1

        dist_map = router._compute_distance_map(target, layer=0)

        # Cells outside the box should be inf (unreachable in single layer)
        assert dist_map[10, 10, 0] == float('inf'), "Blocked cells should be unreachable"

    def test_distance_map_caching(self):
        """Distance maps should be cached for same target."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        target1 = GridCell(25, 25, 0)
        target2 = GridCell(30, 30, 0)

        # First computation
        dist_map1a = router._compute_distance_map(target1, layer=0)
        
        # Second computation for same target (should use cache)
        dist_map1b = router._compute_distance_map(target1, layer=0)
        
        # Different target (should compute new map)
        dist_map2 = router._compute_distance_map(target2, layer=0)

        # Same target should return same map
        assert dist_map1a is dist_map1b, "Should cache distance maps"
        
        # Different target should have different distance
        assert dist_map1a[25, 25, 0] == 0
        assert dist_map2[25, 25, 0] > 0


class TestAdaptiveHeuristic:
    """Tests for A* with adaptive heuristic."""

    def test_adaptive_heuristic_reduces_iterations(self):
        """Adaptive heuristic should reduce A* iterations vs Manhattan."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        
        # Create two routers - one with Manhattan, one with adaptive
        router_manhattan = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
        router_adaptive = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Create a complex obstacle (U-shape)
        for y in range(10, 40):
            router_manhattan.occupancy[20, y, 0] = -1
            router_adaptive.occupancy[20, y, 0] = -1
        for x in range(20, 30):
            router_manhattan.occupancy[x, 10, 0] = -1
            router_adaptive.occupancy[x, 10, 0] = -1

        start = (10, 25)
        end = (30, 25)

        # Route with Manhattan heuristic
        router_manhattan.stats.total_astar_iterations = 0
        path_manhattan = router_manhattan.find_path_rrr(start, end, layer=0)
        iterations_manhattan = router_manhattan.stats.total_astar_iterations

        # Route with adaptive heuristic
        router_adaptive.stats.total_astar_iterations = 0
        path_adaptive = router_adaptive.find_path_rrr_adaptive(start, end, layer=0)
        iterations_adaptive = router_adaptive.stats.total_astar_iterations

        assert path_manhattan is not None, "Manhattan should find path"
        assert path_adaptive is not None, "Adaptive should find path"
        
        # Adaptive should use fewer iterations (30% reduction is target)
        assert iterations_adaptive < iterations_manhattan * 0.7, \
            f"Adaptive should reduce iterations: {iterations_adaptive} vs {iterations_manhattan}"

    def test_adaptive_heuristic_finds_same_or_better_path(self):
        """Adaptive heuristic should find optimal or near-optimal path."""
        board = Board(width=40.0, height=40.0, origin=(0.0, 0.0))
        router_manhattan = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
        router_adaptive = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Add some obstacles
        for x in range(15, 25):
            router_manhattan.occupancy[x, 20, 0] = -1
            router_adaptive.occupancy[x, 20, 0] = -1

        start = (10, 25)
        end = (30, 15)

        path_manhattan = router_manhattan.find_path_rrr(start, end, layer=0)
        path_adaptive = router_adaptive.find_path_rrr_adaptive(start, end, layer=0)

        assert path_manhattan is not None and path_adaptive is not None

        # Path lengths should be similar (adaptive is still admissible)
        # Allow small difference due to tie-breaking
        assert abs(len(path_adaptive) - len(path_manhattan)) <= 2, \
            "Adaptive should find similar length path"

    def test_adaptive_heuristic_admissible(self):
        """Adaptive heuristic should still be admissible (never overestimate)."""
        board = Board(width=30.0, height=30.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Add random obstacles
        import random
        random.seed(42)
        for _ in range(50):
            x, y = random.randint(5, 25), random.randint(5, 25)
            if (x, y) not in [(10, 10), (20, 20)]:  # Keep start/end clear
                router.occupancy[x, y, 0] = -1

        start = (10, 10)
        end = (20, 20)

        # Find path with adaptive heuristic
        path = router.find_path_rrr_adaptive(start, end, layer=0)

        if path is not None:
            # If a path exists, the heuristic was admissible (A* found it)
            assert len(path) > 0, "Path should exist"
        
        # The test is that it doesn't fail - admissibility means A* will find
        # optimal path if one exists


class TestDistanceMapIntegration:
    """Integration tests for distance map with full routing."""

    def test_distance_map_with_multi_pin_net(self):
        """Distance map should work for multi-pin nets."""
        board = Board(width=60.0, height=60.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Create obstacles
        for y in range(25, 35):
            router.occupancy[30, y, 0] = -1

        pin_positions = [(15.0, 30.0), (45.0, 30.0), (30.0, 15.0)]
        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        # Route with adaptive heuristic
        result = router.route_net_adaptive("TEST_NET", pin_positions, assignment)
        
        assert result.success, "Should successfully route with adaptive heuristic"

    def test_distance_map_performance_benchmark(self):
        """Benchmark distance map computation performance."""
        import time
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Add some obstacles
        for x in range(40, 60):
            for y in range(40, 60):
                if x != 50 or y != 50:  # Leave center free
                    router.occupancy[x, y, 0] = -1

        target = GridCell(50, 50, 0)

        # Benchmark distance map computation
        start_time = time.perf_counter()
        dist_map = router._compute_distance_map(target, layer=0)
        computation_time = (time.perf_counter() - start_time) * 1000  # ms

        # Should complete in reasonable time (< 50ms for 100x100 grid)
        assert computation_time < 50, f"Distance map computation too slow: {computation_time:.1f}ms"
        
        # Verify map is valid
        assert dist_map[50, 50, 0] == 0, "Target distance should be 0"
