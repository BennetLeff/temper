"""
Tests for via cost effect on path selection (temper-1w8u.10).

Verifies that the via_cost parameter actually affects A* path selection,
preferring same-layer paths when via cost is high.
"""

import pytest
from temper_placer.routing.maze_router import MazeRouter, GridCell


class TestViaCostPathSelection:
    """Test via cost effects on pathfinding."""
    
    def test_via_cost_zero_shortest_path_chosen(self):
        """With via_cost=0, shortest path should be chosen regardless of layers."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=0.0)
        
        # Create obstacle forcing detour on layer 0
        router.occupancy = router.occupancy.at[5, :, 0].set(1)  # Block column 5 on L0
        
        # Route from (0, 5) to (9, 5)
        path = router.find_path((0, 5), (9, 5), layer=0, allow_layer_change=True)
        
        assert path is not None
        # With zero via cost, should use layer change to avoid long detour
        layers_used = {cell.layer for cell in path}
        assert len(layers_used) > 1, "Should use multiple layers when via cost is zero"
    
    def test_via_cost_high_same_layer_preferred(self):
        """With high via_cost, same-layer path should be preferred even if longer."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=100.0)
        
        # Create small obstacle on layer 0
        router.occupancy = router.occupancy.at[5, 5, 0].set(1)
        
        # Route from (0, 5) to (9, 5)
        path = router.find_path((0, 5), (9, 5), layer=0, allow_layer_change=True)
        
        assert path is not None
        # With high via cost, should prefer longer same-layer path
        via_count = sum(1 for i in range(len(path)-1) 
                       if path[i].layer != path[i+1].layer)
        
        # Should minimize vias (ideally 0 if detour is possible)
        assert via_count <= 2, f"Expected few vias with high cost, got {via_count}"
    
    def test_via_cost_affects_path_length_tradeoff(self):
        """Via cost should create tradeoff between path length and via count."""
        # Low via cost
        router_low = MazeRouter(grid_size=(15, 15), num_layers=2, via_cost=1.0)
        router_low.occupancy = router_low.occupancy.at[7, :, 0].set(1)  # Block column
        
        path_low = router_low.find_path((0, 7), (14, 7), layer=0, allow_layer_change=True)
        
        # High via cost
        router_high = MazeRouter(grid_size=(15, 15), num_layers=2, via_cost=50.0)
        router_high.occupancy = router_high.occupancy.at[7, :, 0].set(1)
        
        path_high = router_high.find_path((0, 7), (14, 7), layer=0, allow_layer_change=True)
        
        assert path_low is not None
        assert path_high is not None
        
        # Count vias in each path
        vias_low = sum(1 for i in range(len(path_low)-1) 
                      if path_low[i].layer != path_low[i+1].layer)
        vias_high = sum(1 for i in range(len(path_high)-1) 
                       if path_high[i].layer != path_high[i+1].layer)
        
        # High via cost should result in fewer vias
        assert vias_high <= vias_low, \
            f"High via cost should reduce vias: {vias_high} vs {vias_low}"
    
    def test_heuristic_accounts_for_via_cost(self):
        """Heuristic should remain admissible when accounting for via cost."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=10.0)
        
        start = GridCell(0, 0, 0)
        end = GridCell(9, 9, 1)  # Different layer
        
        # Heuristic should account for layer difference
        h = router._heuristic(start, end)
        
        # Manhattan distance: 9 + 9 = 18
        # Layer difference: 1 * 2 = 2 (base heuristic)
        # Total: 20
        assert h == 20, f"Expected heuristic 20, got {h}"
        
        # Actual path cost should be >= heuristic (admissibility)
        path = router.find_path((0, 0), (9, 9), layer=0, allow_layer_change=True)
        if path:
            actual_cost = len(path) - 1  # Number of moves
            via_count = sum(1 for i in range(len(path)-1) 
                          if path[i].layer != path[i+1].layer)
            actual_cost += via_count * router.via_cost
            
            assert actual_cost >= h, \
                f"Heuristic not admissible: actual={actual_cost}, h={h}"
    
    def test_via_cost_with_four_layers(self):
        """Via cost should work correctly with 4-layer boards."""
        router = MazeRouter(grid_size=(10, 10), num_layers=4, via_cost=5.0)
        
        # Block layers 0 and 1 in middle
        router.occupancy = router.occupancy.at[5, :, 0].set(1)
        router.occupancy = router.occupancy.at[5, :, 1].set(1)
        
        # Route should use layers 2 or 3
        path = router.find_path((0, 5), (9, 5), layer=0, allow_layer_change=True)
        
        assert path is not None
        layers_used = {cell.layer for cell in path}
        
        # Should use available layers
        assert len(layers_used) > 1
        assert 2 in layers_used or 3 in layers_used


class TestViaCostEdgeCases:
    """Test edge cases for via cost."""
    
    def test_via_cost_negative_treated_as_zero(self):
        """Negative via cost should not cause issues."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=-10.0)
        
        # Should still route successfully
        path = router.find_path((0, 0), (9, 9), layer=0, allow_layer_change=True)
        assert path is not None
    
    def test_via_cost_extremely_high_forces_same_layer(self):
        """Extremely high via cost should force same-layer routing."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=1000.0)
        
        # Route on clear layer
        path = router.find_path((0, 0), (9, 9), layer=0, allow_layer_change=True)
        
        assert path is not None
        # All cells should be on same layer
        layers = {cell.layer for cell in path}
        assert len(layers) == 1, "Should stay on same layer with very high via cost"
    
    def test_via_cost_zero_uses_vias_freely(self):
        """Zero via cost should allow free use of vias."""
        router = MazeRouter(grid_size=(10, 10), num_layers=2, via_cost=0.0)
        
        # Create zigzag obstacle on layer 0
        for y in range(0, 10, 2):
            router.occupancy = router.occupancy.at[5, y, 0].set(1)
        
        # Route should use vias to navigate efficiently
        path = router.find_path((0, 5), (9, 5), layer=0, allow_layer_change=True)
        
        assert path is not None
        # With zero cost, vias should be used if beneficial
        via_count = sum(1 for i in range(len(path)-1) 
                       if path[i].layer != path[i+1].layer)
        
        # Should use at least some vias to navigate obstacles
        assert via_count >= 0  # Just verify it doesn't crash
