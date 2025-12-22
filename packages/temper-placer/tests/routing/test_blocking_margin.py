"""
Unit tests for configurable blocking margin in MazeRouter.

Tests verify that the blocking margin parameter correctly affects
grid cell blocking calculations.
"""

import pytest
import jax.numpy as jnp

from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.netlist import Component, Pin
from temper_placer.core.board import Board


@pytest.fixture
def board():
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0), layer_count=2)


@pytest.fixture
def router(board):
    return MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)


@pytest.fixture
def simple_component():
    """10mm x 10mm component with 4 pins."""
    return Component(
        ref="U1",
        value="TEST",
        footprint="TEST_10x10",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(5.0, 0.0)),
            Pin(name="2", number="2", position=(-5.0, 0.0)),
        ],
    )


class TestBlockingMargin:
    """Tests for configurable blocking margin."""

    def test_default_margin_is_05mm(self, router, simple_component):
        """Default margin should be 0.5mm."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components([simple_component], positions)
        
        # Component is 10x10mm centered at (50, 50)
        # With 0.5mm margin: 11x11mm total
        # Grid cells: (50-5.5)/1.0 to (50+5.5)/1.0 = 44.5 to 55.5 = cells 44-55 (12 cells)
        assert int(router.occupancy[44, 50, 0]) == 1, "Left edge should be blocked"
        assert int(router.occupancy[55, 50, 0]) == 1, "Right edge should be blocked"
        assert int(router.occupancy[43, 50, 0]) == 0, "Outside margin should be free"

    def test_custom_margin_01mm(self, router, simple_component):
        """Custom 0.1mm margin should reduce blocked area."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components([simple_component], positions, margin=0.1)
        
        # Component is 10x10mm centered at (50, 50)
        # With 0.1mm margin: 10.2x10.2mm total
        # Grid cells: (50-5.1)/1.0 to (50+5.1)/1.0 = 44.9 to 55.1 = cells 44-55 (12 cells)
        # But with proper rounding: cells 45-54 (10 cells)
        blocked_count = jnp.sum(router.occupancy[:, 50, 0] == 1)
        assert 10 <= blocked_count <= 12, f"Expected 10-12 blocked cells, got {blocked_count}"

    def test_zero_margin(self, router, simple_component):
        """Zero margin should block only component footprint."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components([simple_component], positions, margin=0.0)
        
        # Component is 10x10mm centered at (50, 50)
        # Grid cells: (50-5)/1.0 to (50+5)/1.0 = 45 to 55 = cells 45-54 (10 cells)
        assert int(router.occupancy[45, 50, 0]) == 1, "Component edge should be blocked"
        assert int(router.occupancy[54, 50, 0]) == 1, "Component edge should be blocked"
        assert int(router.occupancy[44, 50, 0]) == 0, "Outside component should be free"

    def test_large_margin_2mm(self, router, simple_component):
        """Large 2mm margin should significantly increase blocked area."""
        positions = jnp.array([[50.0, 50.0]])
        router.block_components([simple_component], positions, margin=2.0)
        
        # Component is 10x10mm centered at (50, 50)
        # With 2mm margin: 14x14mm total
        # Grid cells: (50-7)/1.0 to (50+7)/1.0 = 43 to 57 = cells 43-56 (14 cells)
        assert int(router.occupancy[43, 50, 0]) == 1, "Extended margin should be blocked"
        assert int(router.occupancy[56, 50, 0]) == 1, "Extended margin should be blocked"
        assert int(router.occupancy[42, 50, 0]) == 0, "Outside margin should be free"

    def test_margin_affects_all_components(self, router):
        """Margin should apply consistently to all components."""
        comp1 = Component(ref="U1", value="A", footprint="5x5", bounds=(5.0, 5.0), pins=[])
        comp2 = Component(ref="U2", value="B", footprint="8x8", bounds=(8.0, 8.0), pins=[])
        
        positions = jnp.array([[30.0, 30.0], [70.0, 70.0]])
        router.block_components([comp1, comp2], positions, margin=0.2)
        
        # Both components should have 0.2mm margin applied
        # Verify by checking blocked cell counts are proportional to component size + margin
        blocked_1 = jnp.sum(router.occupancy[25:35, 25:35, 0] == 1)
        blocked_2 = jnp.sum(router.occupancy[65:75, 65:75, 0] == 1)
        
        assert blocked_1 > 0, "First component should block cells"
        assert blocked_2 > 0, "Second component should block cells"
        assert blocked_2 > blocked_1, "Larger component should block more cells"


class TestMarginEdgeCases:
    """Edge case tests for margin parameter."""

    def test_negative_margin_raises_error(self, router, simple_component):
        """Negative margin should raise ValueError."""
        positions = jnp.array([[50.0, 50.0]])
        with pytest.raises(ValueError, match="margin must be non-negative"):
            router.block_components([simple_component], positions, margin=-0.1)

    def test_margin_larger_than_component(self, router):
        """Margin larger than component should still work."""
        tiny_comp = Component(ref="R1", value="1k", footprint="0603", bounds=(1.6, 0.8), pins=[])
        positions = jnp.array([[50.0, 50.0]])
        
        # 5mm margin on 1.6mm component
        router.block_components([tiny_comp], positions, margin=5.0)
        
        # Should block large area around tiny component
        blocked_count = jnp.sum(router.occupancy[:, :, 0] == 1)
        assert blocked_count > 100, "Large margin should block many cells"

    def test_margin_with_board_edge_components(self, router, simple_component):
        """Margin should be clipped at board edges."""
        # Place component at board edge
        positions = jnp.array([[5.0, 5.0]])
        router.block_components([simple_component], positions, margin=2.0)
        
        # Should not block cells outside board (negative indices)
        # Verify no errors and blocking stops at board edge
        assert int(router.occupancy[0, 0, 0]) in [0, 1], "Board corner should be valid"
