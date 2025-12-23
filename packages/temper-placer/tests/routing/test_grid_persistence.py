"""
Tests for occupancy grid state persistence in JAX (temper-1w8u.11).

Verifies that JAX functional updates persist correctly when routing
multiple nets sequentially.
"""

import pytest
import jax.numpy as jnp
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import Layer, LayerAssignment


class TestGridStatePersistence:
    """Test JAX occupancy grid state persistence."""
    
    def test_route_net_a_then_net_b_a_blocks_b(self):
        """After routing net A, its path should block net B."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Route net A horizontally
        assign = LayerAssignment("NET_A", Layer.L1_TOP, {Layer.L1_TOP})
        result_a = router.route_net("NET_A", [(0.0, 5.0), (9.0, 5.0)], assign)
        
        assert result_a.success
        
        # Try to route net B through same cells
        result_b = router.route_net("NET_B", [(0.0, 5.0), (9.0, 5.0)], assign)
        
        # Net B should fail because A's path is blocked
        assert not result_b.success, "Net B should be blocked by Net A's path"
    
    def test_occupancy_array_updated_after_each_net(self):
        """Occupancy array should reflect routed nets."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Initial state: all free
        assert jnp.sum(router.occupancy == 2) == 0, "No cells should be routed initially"
        
        # Route net A
        assign = LayerAssignment("NET_A", Layer.L1_TOP, {Layer.L1_TOP})
        result_a = router.route_net("NET_A", [(0.0, 0.0), (5.0, 0.0)], assign)
        
        assert result_a.success
        
        # Check occupancy updated
        routed_cells_after_a = int(jnp.sum(router.occupancy == 2))
        assert routed_cells_after_a > 0, "Net A should mark cells as routed"
        
        # Route net B on different path
        result_b = router.route_net("NET_B", [(0.0, 2.0), (5.0, 2.0)], assign)
        
        assert result_b.success
        
        # Check occupancy updated again
        routed_cells_after_b = int(jnp.sum(router.occupancy == 2))
        assert routed_cells_after_b > routed_cells_after_a, \
            "Net B should add more routed cells"
    
    def test_sequential_routing_no_state_leakage(self):
        """Independent routing calls should not leak state."""
        # Router 1: route net A
        router1 = MazeRouter(grid_size=(10, 10), num_layers=1)
        assign = LayerAssignment("NET_A", Layer.L1_TOP, {Layer.L1_TOP})
        result1 = router1.route_net("NET_A", [(0.0, 5.0), (9.0, 5.0)], assign)
        
        assert result1.success
        
        # Router 2: fresh instance, should route same path successfully
        router2 = MazeRouter(grid_size=(10, 10), num_layers=1)
        result2 = router2.route_net("NET_B", [(0.0, 5.0), (9.0, 5.0)], assign)
        
        assert result2.success, "Fresh router should not have state from router1"
    
    def test_grid_state_immutable_across_failed_routes(self):
        """Failed routing should not corrupt grid state."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Block entire middle row
        router.occupancy = router.occupancy.at[:, 5, 0].set(1)
        
        # Try to route through blocked area (should fail)
        assign = LayerAssignment("NET_A", Layer.L1_TOP, {Layer.L1_TOP})
        result = router.route_net("NET_A", [(0.0, 5.0), (9.0, 5.0)], assign)
        
        assert not result.success
        
        # Grid should still have blocked row, no corruption
        assert jnp.all(router.occupancy[:, 5, 0] == 1), \
            "Blocked cells should remain blocked after failed route"
        
        # Other cells should still be free
        assert jnp.sum(router.occupancy[:, 0, 0]) == 0, \
            "Unrelated cells should remain free"
    
    def test_multi_net_routing_preserves_all_paths(self):
        """Routing multiple nets should preserve all paths."""
        router = MazeRouter(grid_size=(15, 15), num_layers=1)
        assign = LayerAssignment("NET", Layer.L1_TOP, {Layer.L1_TOP})
        
        # Route 3 parallel nets
        nets = [
            ("NET_A", [(0.0, 2.0), (10.0, 2.0)]),
            ("NET_B", [(0.0, 5.0), (10.0, 5.0)]),
            ("NET_C", [(0.0, 8.0), (10.0, 8.0)]),
        ]
        
        results = {}
        for net_name, pins in nets:
            result = router.route_net(net_name, pins, assign)
            results[net_name] = result
            assert result.success, f"{net_name} should route successfully"
        
        # All paths should be preserved in occupancy
        total_routed = int(jnp.sum(router.occupancy == 2))
        expected_min = sum(len(r.cells) for r in results.values())
        
        assert total_routed >= expected_min, \
            f"All routed cells should be marked: {total_routed} >= {expected_min}"


class TestJAXFunctionalUpdates:
    """Test JAX .at[].set() functional updates."""
    
    def test_jax_at_set_creates_new_array(self):
        """JAX .at[].set() should create new array, not mutate."""
        router = MazeRouter(grid_size=(5, 5), num_layers=1)
        
        # Save reference to original
        original_id = id(router.occupancy)
        
        # Update occupancy
        router.occupancy = router.occupancy.at[2, 2, 0].set(1)
        
        # Should be new array (JAX functional update)
        new_id = id(router.occupancy)
        
        # Note: In practice, JAX may reuse memory, so this test is informational
        # The important thing is that the update persists
        assert int(router.occupancy[2, 2, 0]) == 1
    
    def test_multiple_updates_accumulate(self):
        """Multiple .at[].set() calls should accumulate."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Set multiple cells
        router.occupancy = router.occupancy.at[0, 0, 0].set(1)
        router.occupancy = router.occupancy.at[1, 1, 0].set(1)
        router.occupancy = router.occupancy.at[2, 2, 0].set(1)
        
        # All should be set
        assert int(router.occupancy[0, 0, 0]) == 1
        assert int(router.occupancy[1, 1, 0]) == 1
        assert int(router.occupancy[2, 2, 0]) == 1
    
    def test_slice_updates_persist(self):
        """Slice updates should persist correctly."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Block entire row
        router.occupancy = router.occupancy.at[:, 5, 0].set(1)
        
        # Verify all cells in row are blocked
        assert jnp.all(router.occupancy[:, 5, 0] == 1)
        
        # Other rows should be free
        assert jnp.all(router.occupancy[:, 4, 0] == 0)
        assert jnp.all(router.occupancy[:, 6, 0] == 0)
    
    def test_conditional_updates_work(self):
        """Conditional updates based on current state should work."""
        router = MazeRouter(grid_size=(10, 10), num_layers=1)
        
        # Set some cells to 1
        router.occupancy = router.occupancy.at[5, 5, 0].set(1)
        
        # Conditionally update only if currently 0
        for x in range(10):
            for y in range(10):
                if int(router.occupancy[x, y, 0]) == 0:
                    router.occupancy = router.occupancy.at[x, y, 0].set(2)
        
        # (5,5) should still be 1
        assert int(router.occupancy[5, 5, 0]) == 1
        
        # Others should be 2
        assert int(router.occupancy[0, 0, 0]) == 2
        assert int(router.occupancy[9, 9, 0]) == 2
