"""
TDD tests for router performance optimizations.

These tests verify that numpy grid conversion doesn't break behavior
and provides performance improvements.
"""

import time
import pytest
import numpy as np
import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.maze_router import MazeRouter, GridCell, RoutePath
from temper_placer.routing.layer_assignment import LayerAssignment, Layer


class TestGridTypeConsistency:
    """Tests to verify grid operations work correctly."""
    
    def test_occupancy_starts_as_numpy(self):
        """After conversion, occupancy should be numpy array."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=2)
        
        # Check it's numpy (not JAX)
        assert isinstance(router.occupancy, np.ndarray), \
            f"Expected numpy array, got {type(router.occupancy)}"
    
    def test_history_cost_starts_as_numpy(self):
        """After conversion, history_cost should be numpy array."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=2)
        
        assert isinstance(router.history_cost, np.ndarray), \
            f"Expected numpy array, got {type(router.history_cost)}"
    
    def test_present_congestion_starts_as_numpy(self):
        """After conversion, present_congestion should be numpy array."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=2)
        
        assert isinstance(router.present_congestion, np.ndarray), \
            f"Expected numpy array, got {type(router.present_congestion)}"


class TestBlockRectBehavior:
    """Tests that blocking still works after numpy conversion."""
    
    def test_block_rect_sets_minus_one(self):
        """block_rect should set cells to -1."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        router.block_rect(5, 5, 3, 3, layer=0)
        
        # Check center cell is blocked
        assert router.occupancy[6, 6, 0] == -1
        # Check outside is not blocked
        assert router.occupancy[0, 0, 0] == 0
    
    def test_block_rect_all_layers(self):
        """block_rect with layer=-1 should block all layers."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=2)
        
        router.block_rect(5, 5, 3, 3, layer=-1)
        
        assert router.occupancy[6, 6, 0] == -1
        assert router.occupancy[6, 6, 1] == -1


class TestRipUpBehavior:
    """Tests that rip_up_net still works correctly."""
    
    def test_rip_up_clears_occupancy(self):
        """rip_up_net should clear cells from occupancy."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        # Manually add a routed path
        cells = [GridCell(5, 5, 0), GridCell(6, 5, 0), GridCell(7, 5, 0)]
        for cell in cells:
            router.occupancy[cell.x, cell.y, cell.layer] = 2
            router.net_occupancy[(cell.x, cell.y, cell.layer)] = {"TEST_NET"}
            router.present_congestion[cell.x, cell.y, cell.layer] = 1.0
        router.routed_paths["TEST_NET"] = RoutePath("TEST_NET", cells, 2.0, 0, True)
        
        # Rip up
        router.rip_up_net("TEST_NET")
        
        # Verify cleared
        for cell in cells:
            assert router.occupancy[cell.x, cell.y, cell.layer] == 0
            assert (cell.x, cell.y, cell.layer) not in router.net_occupancy
    
    def test_rip_up_decrements_congestion(self):
        """rip_up_net should decrement present_congestion."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        cells = [GridCell(5, 5, 0)]
        for cell in cells:
            router.occupancy[cell.x, cell.y, cell.layer] = 2
            router.net_occupancy[(cell.x, cell.y, cell.layer)] = {"TEST_NET"}
            router.present_congestion[cell.x, cell.y, cell.layer] = 2.0  # Was 2
        router.routed_paths["TEST_NET"] = RoutePath("TEST_NET", cells, 0.0, 0, True)
        
        router.rip_up_net("TEST_NET")
        
        # Should decrement by 1
        assert router.present_congestion[5, 5, 0] == 1.0


class TestPathfindingBehavior:
    """Tests that pathfinding still produces correct results."""
    
    def test_find_path_on_empty_grid(self):
        """Should find path on empty grid."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        path = router.find_path((0, 0), (5, 5), layer=0)
        
        assert path is not None
        assert len(path) > 0
        assert path[0].x == 0 and path[0].y == 0
        assert path[-1].x == 5 and path[-1].y == 5
    
    def test_find_path_avoids_blocked(self):
        """Should route around blocked cells."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        # Block a wall
        router.block_rect(3, 0, 1, 10, layer=0)
        
        path = router.find_path((0, 5), (10, 5), layer=0)
        
        assert path is not None
        # Path should not go through blocked cells
        for cell in path:
            assert router.occupancy[cell.x, cell.y, cell.layer] != -1


class TestCongestionUpdate:
    """Tests that congestion updates work with numpy."""
    
    def test_update_congestion_costs(self):
        """update_congestion_costs should increment history for contested cells."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)
        
        # Create contested cell
        router.present_congestion[5, 5, 0] = 2.0  # > 1.0 = contested
        
        initial = router.history_cost[5, 5, 0]
        router.update_congestion_costs(history_increment=1.0)
        
        assert router.history_cost[5, 5, 0] > initial
    
    def test_decay_history_costs(self):
        """decay_history_costs should reduce history but keep >= 1.0."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)
        
        router.history_cost[5, 5, 0] = 5.0
        
        router.decay_history_costs(decay_factor=0.5)
        
        assert router.history_cost[5, 5, 0] == 2.5
        
        # Decay again - should not go below 1.0
        for _ in range(10):
            router.decay_history_costs(decay_factor=0.5)
        
        assert router.history_cost[5, 5, 0] >= 1.0


class TestRouteNetRRR:
    """Tests that route_net_rrr works correctly."""
    
    def test_route_net_updates_occupancy(self):
        """route_net_rrr should mark cells as routed."""
        router = MazeRouter(grid_size=(30, 30), cell_size_mm=1.0, num_layers=1)
        
        # Route a net
        pin_positions = [(5.0, 5.0), (15.0, 5.0)]
        assignment = LayerAssignment("TEST", Layer.L1_TOP, {Layer.L1_TOP})
        
        result = router.route_net_rrr("TEST", pin_positions, assignment)
        
        assert result.success
        # At least some cells should be marked as routed
        routed_count = np.sum(router.occupancy == 2)
        assert routed_count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
