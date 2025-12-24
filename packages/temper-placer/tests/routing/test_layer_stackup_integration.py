"""Tests for layer-aware routing with LayerStackup integration.

Tests verify that MazeRouter respects layer stackup configuration:
- Routable vs non-routable layers (signal vs plane)
- Net class layer restrictions (HV, Power, Signal)
- Ground plane preservation
- Backward compatibility
"""

import pytest
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.board import LayerStackup, Layer


class TestLayerStackupIntegration:
    """Tests for LayerStackup integration with MazeRouter."""
    
    def test_router_has_default_stackup(self):
        """GIVEN router without explicit stackup
        WHEN creating router
        THEN uses default 4-layer stackup"""
        router = MazeRouter(grid_size=(100, 100), num_layers=4)
        
        assert router.layer_stackup is not None
        assert len(router.layer_stackup.layers) == 4
    
    def test_router_accepts_custom_stackup(self):
        """GIVEN custom layer stackup
        WHEN creating router with stackup
        THEN uses provided stackup"""
        stackup = LayerStackup(
            layers=[
                Layer("L1", "signal", copper_weight=2.0, is_routable=True),
                Layer("L2", "plane", copper_weight=1.0, is_routable=False),
            ]
        )
        
        router = MazeRouter(
            grid_size=(100, 100),
            num_layers=2,
            layer_stackup=stackup
        )
        
        assert router.layer_stackup == stackup


class TestLayerFiltering:
    """Tests for layer filtering in pathfinding."""
    
    def test_find_path_with_allowed_layers(self):
        """GIVEN router with multiple layers
        WHEN routing with allowed_layers restriction
        THEN path only uses allowed layers"""
        router = MazeRouter(grid_size=(100, 100), num_layers=4)
        
        # Route with only layers 0 and 3 allowed (signal layers)
        path = router.find_path(
            start=(10, 10),
            end=(50, 50),
            layer=0,
            allow_layer_change=True,
            allowed_layers=[0, 3]
        )
        
        assert path is not None
        # Verify path only uses layers 0 or 3
        for cell in path:
            assert cell.layer in [0, 3], f"Cell {cell} uses disallowed layer"
    
    def test_find_path_blocks_power_plane(self):
        """GIVEN 4-layer stackup with L2/L3 as planes
        WHEN routing signal net
        THEN path avoids plane layers (L2, L3)"""
        stackup = LayerStackup.default_4layer()
        router = MazeRouter(
            grid_size=(100, 100),
            num_layers=4,
            layer_stackup=stackup
        )
        
        # Get routable layers for Signal net class
        allowed_layers = stackup.routable_layers("Signal")
        assert allowed_layers == [0, 3]  # L1 and L4 only
        
        # Route with layer restrictions
        path = router.find_path(
            start=(10, 10),
            end=(90, 90),
            layer=0,
            allow_layer_change=True,
            allowed_layers=allowed_layers
        )
        
        assert path is not None
        # Verify no cells use plane layers (1, 2)
        for cell in path:
            assert cell.layer not in [1, 2], f"Path uses plane layer {cell.layer}"
    
    def test_hv_routes_only_on_l1(self):
        """GIVEN HV net class
        WHEN routing
        THEN path only uses L1 (2oz copper)"""
        stackup = LayerStackup.default_4layer()
        router = MazeRouter(
            grid_size=(100, 100),
            num_layers=4,
            layer_stackup=stackup
        )
        
        # Get allowed layers for HV net
        allowed_layers = stackup.routable_layers("HighVoltage")
        assert allowed_layers == [0]  # L1 only
        
        # Route HV net
        path = router.find_path(
            start=(10, 10),
            end=(50, 50),
            layer=0,
            allow_layer_change=False,  # HV can't change layers
            allowed_layers=allowed_layers
        )
        
        assert path is not None
        # Verify all cells are on L1
        for cell in path:
            assert cell.layer == 0, f"HV path uses layer {cell.layer}, expected L1 (0)"
    
    def test_power_net_routing(self):
        """GIVEN Power net class
        WHEN routing
        THEN uses routable layers (L1, L4), avoids planes"""
        stackup = LayerStackup.default_4layer()
        router = MazeRouter(
            grid_size=(100, 100),
            num_layers=4,
            layer_stackup=stackup
        )
        
        # Get allowed layers for Power net
        allowed_layers = stackup.routable_layers("Power")
        assert allowed_layers == [0, 3]  # L1 and L4
        
        # Route power net
        path = router.find_path(
            start=(10, 10),
            end=(90, 90),
            layer=0,
            allow_layer_change=True,
            allowed_layers=allowed_layers
        )
        
        assert path is not None
        # Verify path only uses L1 or L4
        for cell in path:
            assert cell.layer in [0, 3], f"Power net uses layer {cell.layer}"


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""
    
    def test_find_path_without_allowed_layers(self):
        """GIVEN router
        WHEN calling find_path without allowed_layers
        THEN works as before (all layers allowed)"""
        router = MazeRouter(grid_size=(100, 100), num_layers=2)
        
        # Old-style call without allowed_layers
        path = router.find_path(
            start=(10, 10),
            end=(50, 50),
            layer=0,
            allow_layer_change=True
        )
        
        assert path is not None
    
    def test_router_without_stackup(self):
        """GIVEN router created without stackup
        WHEN routing
        THEN uses default stackup"""
        router = MazeRouter(grid_size=(100, 100), num_layers=4)
        
        path = router.find_path(
            start=(10, 10),
            end=(50, 50),
            layer=0
        )
        
        assert path is not None
        assert router.layer_stackup is not None


class TestLayerRestrictionEdgeCases:
    """Tests for edge cases in layer restrictions."""
    
    def test_no_path_when_all_layers_blocked(self):
        """GIVEN path blocked on all allowed layers
        WHEN routing
        THEN returns None"""
        router = MazeRouter(grid_size=(50, 50), num_layers=4)
        
        # Block path on layers 0 and 3 (signal layers)
        router.block_rect(20, 0, 5, 50, layer=0)
        router.block_rect(20, 0, 5, 50, layer=3)
        
        # Try to route with only signal layers allowed
        path = router.find_path(
            start=(10, 25),
            end=(40, 25),
            layer=0,
            allow_layer_change=True,
            allowed_layers=[0, 3]
        )
        
        assert path is None
    
    def test_via_only_between_allowed_layers(self):
        """GIVEN allowed_layers restriction
        WHEN path needs via
        THEN via only goes to allowed layers"""
        router = MazeRouter(grid_size=(50, 50), num_layers=4, via_cost=0.5)
        
        # Block path on layer 0 to force via
        router.block_rect(20, 0, 5, 50, layer=0)
        
        # Route with only layers 0 and 3 allowed
        path = router.find_path(
            start=(10, 25),
            end=(40, 25),
            layer=0,
            allow_layer_change=True,
            allowed_layers=[0, 3]
        )
        
        if path:
            # If via was used, verify it's only to layer 3
            layers_used = set(cell.layer for cell in path)
            assert layers_used.issubset({0, 3}), f"Path uses disallowed layers: {layers_used}"
    
    def test_single_allowed_layer(self):
        """GIVEN only one allowed layer
        WHEN routing
        THEN path stays on that layer"""
        router = MazeRouter(grid_size=(100, 100), num_layers=4)
        
        # Route with only layer 0 allowed
        path = router.find_path(
            start=(10, 10),
            end=(50, 50),
            layer=0,
            allow_layer_change=True,
            allowed_layers=[0]
        )
        
        assert path is not None
        # Verify all cells are on layer 0
        for cell in path:
            assert cell.layer == 0


class TestNetClassScenarios:
    """Integration tests for different net class scenarios."""
    
    def test_mixed_net_classes_on_same_board(self):
        """GIVEN board with HV, Power, and Signal nets
        WHEN routing each with appropriate restrictions
        THEN each respects its layer constraints"""
        stackup = LayerStackup.default_4layer()
        router = MazeRouter(
            grid_size=(100, 100),
            num_layers=4,
            layer_stackup=stackup
        )
        
        # Route HV net (L1 only)
        hv_path = router.find_path(
            start=(10, 10),
            end=(30, 10),
            layer=0,
            allowed_layers=stackup.routable_layers("HighVoltage")
        )
        assert hv_path is not None
        assert all(cell.layer == 0 for cell in hv_path)
        
        # Mark HV path as routed
        for cell in hv_path:
            router.occupancy = router.occupancy.at[cell.x, cell.y, cell.layer].set(2)
        
        # Route Power net (L1, L4)
        power_path = router.find_path(
            start=(40, 10),
            end=(60, 10),
            layer=0,
            allow_layer_change=True,
            allowed_layers=stackup.routable_layers("Power")
        )
        assert power_path is not None
        assert all(cell.layer in [0, 3] for cell in power_path)
        
        # Mark power path as routed
        for cell in power_path:
            router.occupancy = router.occupancy.at[cell.x, cell.y, cell.layer].set(2)
        
        # Route Signal net (L1, L4)
        signal_path = router.find_path(
            start=(70, 10),
            end=(90, 10),
            layer=0,
            allow_layer_change=True,
            allowed_layers=stackup.routable_layers("Signal")
        )
        assert signal_path is not None
        assert all(cell.layer in [0, 3] for cell in signal_path)
