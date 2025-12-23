"""
Unit tests for layer-specific component blocking.

Tests verify that components can be blocked on their actual layer only,
allowing routing to pass under/over components on different layers.
"""

import pytest
import jax.numpy as jnp

from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.netlist import Component, Pin
from temper_placer.core.board import Board


@pytest.fixture
def board():
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0))


@pytest.fixture
def router(board):
    return MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)


@pytest.fixture
def top_layer_component():
    """Component on top layer (L1)."""
    return Component(
        ref="U1",
        footprint="QFP",
        bounds=(10.0, 10.0),
        layer=0,  # Top layer
        pins=[Pin(name="1", number="1", position=(5.0, 0.0))],
    )


@pytest.fixture
def bottom_layer_component():
    """Component on bottom layer (L4)."""
    return Component(
        ref="U2",
        footprint="QFP",
        bounds=(10.0, 10.0),
        layer=1,  # Bottom layer
        pins=[Pin(name="1", number="1", position=(5.0, 0.0))],
    )


class TestLayerSpecificBlocking:
    """Tests for layer-specific component blocking."""

    def test_block_all_layers_default(self, router, top_layer_component):
        """Default behavior should block all layers."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components([top_layer_component], positions, margin=0.1)
        
        # Should block both layers
        assert int(router.occupancy[50, 50, 0]) == 1, "Top layer should be blocked"
        assert int(router.occupancy[50, 50, 1]) == 1, "Bottom layer should be blocked"

    def test_block_single_layer_top(self, router, top_layer_component):
        """Layer-specific blocking should only block component's layer."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Should only block top layer
        assert int(router.occupancy[50, 50, 0]) == 1, "Top layer should be blocked"
        assert int(router.occupancy[50, 50, 1]) == 0, "Bottom layer should be free"

    def test_block_single_layer_bottom(self, router, bottom_layer_component):
        """Layer-specific blocking on bottom layer."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [bottom_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Should only block bottom layer
        assert int(router.occupancy[50, 50, 0]) == 0, "Top layer should be free"
        assert int(router.occupancy[50, 50, 1]) == 1, "Bottom layer should be blocked"

    def test_mixed_layer_components(self, router, top_layer_component, bottom_layer_component):
        """Multiple components on different layers with layer-specific blocking."""
        positions = jnp.array([[30.0, 30.0], [70.0, 70.0]])
        components = [top_layer_component, bottom_layer_component]
        
        router.block_components(components, positions, margin=0.1, layer_specific=True)
        
        # First component (top layer) at (30, 30)
        assert int(router.occupancy[30, 30, 0]) == 1, "First comp top layer blocked"
        assert int(router.occupancy[30, 30, 1]) == 0, "First comp bottom layer free"
        
        # Second component (bottom layer) at (70, 70)
        assert int(router.occupancy[70, 70, 0]) == 0, "Second comp top layer free"
        assert int(router.occupancy[70, 70, 1]) == 1, "Second comp bottom layer blocked"

    def test_routing_under_component(self, router, top_layer_component):
        """Verify routing can pass under component on different layer."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Try to find path on bottom layer through component area
        start = (45, 50)  # Left of component
        end = (55, 50)    # Right of component
        
        path = router.find_path(start, end, layer=1, allow_layer_change=False)
        
        assert path is not None, "Should find path on bottom layer under component"
        # Verify path goes through component area on layer 1
        path_cells = [(cell.x, cell.y) for cell in path]
        assert (50, 50) in path_cells, "Path should go through component center"

    def test_routing_blocked_on_component_layer(self, router, top_layer_component):
        """Verify routing is blocked on component's actual layer."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Try to find path on top layer through component area
        start = (45, 50)  # Left of component
        end = (55, 50)    # Right of component
        
        path = router.find_path(start, end, layer=0, allow_layer_change=False)
        
        # Path should either not exist or route around component
        if path is not None:
            path_cells = [(cell.x, cell.y) for cell in path]
            assert (50, 50) not in path_cells, "Path should not go through component on its layer"


class TestLayerSpecificEscapeRoutes:
    """Tests for escape routes with layer-specific blocking."""

    def test_escape_routes_on_component_layer(self, router, top_layer_component):
        """Escape routes should exist on component's layer."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Pin at (55, 50) should have escape route on layer 0
        pin_gx, pin_gy = router._world_to_grid(55.0, 50.0)
        
        # Check cells in escape direction (right)
        free_cells = 0
        for i in range(5):
            gx = pin_gx + i
            if 0 <= gx < router.grid_size[0]:
                if int(router.occupancy[gx, pin_gy, 0]) == 0:
                    free_cells += 1
        
        assert free_cells >= 3, "Should have escape route on component layer"

    def test_escape_routes_on_other_layer(self, router, top_layer_component):
        """Escape routes should also exist on other layer with layer-specific blocking."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        
        # Same pin location on layer 1 should be completely free
        pin_gx, pin_gy = router._world_to_grid(55.0, 50.0)
        
        # All cells should be free on layer 1
        assert int(router.occupancy[pin_gx, pin_gy, 1]) == 0, "Pin cell free on other layer"
        assert int(router.occupancy[pin_gx + 1, pin_gy, 1]) == 0, "Adjacent cells free"


class TestLayerSpecificPerformance:
    """Performance tests for layer-specific blocking."""

    def test_layer_specific_reduces_blocked_cells(self, router, top_layer_component):
        """Layer-specific blocking should reduce total blocked cells by ~50%."""
        positions = jnp.array([[50.0, 50.0]])
        
        # Block all layers
        router_all = MazeRouter.from_board(router.board, cell_size_mm=1.0, num_layers=2)
        router_all.block_components([top_layer_component], positions, margin=0.1)
        blocked_all = jnp.sum(router_all.occupancy == 1)
        
        # Block single layer
        router_single = MazeRouter.from_board(router.board, cell_size_mm=1.0, num_layers=2)
        router_single.block_components(
            [top_layer_component], 
            positions, 
            margin=0.1, 
            layer_specific=True
        )
        blocked_single = jnp.sum(router_single.occupancy == 1)
        
        # Should be approximately half
        ratio = float(blocked_single) / float(blocked_all)
        assert 0.45 <= ratio <= 0.55, f"Expected ~50% reduction, got {ratio:.2%}"
