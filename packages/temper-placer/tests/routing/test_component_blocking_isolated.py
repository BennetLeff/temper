"""
Tests for component blocking without escape routes (temper-1w8u.5).

Verifies that components block exactly the cells they should, with correct
margins, before adding escape route complexity.
"""

import pytest
import jax.numpy as jnp
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.core.netlist import Component
from tests.routing.grid_viz import render_grid


class TestComponentBlocking:
    """Test component blocking in isolation."""
    
    def test_component_blocks_interior_cells(self):
        """Component should block all cells within its bounds."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # 4x4mm component at (10, 10)
        comp = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[10.0, 10.0]])
        
        # Block without escape routes
        router.block_components([comp], positions, margin=0.0, escape_length=0)
        
        # Center should be blocked
        assert int(router.occupancy[10, 10, 0]) == 1
        
        # Cells within bounds should be blocked
        # 4mm width centered at 10mm: 8mm to 12mm
        for x in range(8, 13):
            for y in range(8, 13):
                assert int(router.occupancy[x, y, 0]) == 1, \
                    f"Cell ({x}, {y}) should be blocked"
    
    def test_margin_expands_blocking_by_n(self):
        """Margin should expand blocked region by specified amount."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # 4x4mm component at (10, 10) with 1mm margin
        comp = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[10.0, 10.0]])
        
        router.block_components([comp], positions, margin=1.0, escape_length=0)
        
        # With 1mm margin: 4mm + 2*1mm = 6mm total
        # Centered at 10mm: 7mm to 13mm
        # Grid cells: round(7) to round(13) = 7 to 13
        assert int(router.occupancy[7, 10, 0]) == 1, "Margin cell should be blocked"
        assert int(router.occupancy[13, 10, 0]) == 1, "Margin cell should be blocked"
        
        # Outside margin should be free
        assert int(router.occupancy[6, 10, 0]) == 0, "Outside margin should be free"
        assert int(router.occupancy[14, 10, 0]) == 0, "Outside margin should be free"
    
    def test_blocking_respects_grid_boundaries(self):
        """Component at edge should not cause out-of-bounds access."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # Component at (0, 0) with 4x4mm bounds
        comp = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[0.0, 0.0]])
        
        # Should not crash
        router.block_components([comp], positions, margin=0.0, escape_length=0)
        
        # Should block cells near origin
        assert int(router.occupancy[0, 0, 0]) == 1
        assert int(router.occupancy[1, 1, 0]) == 1
        
        # Grid should still be valid
        assert router.occupancy.shape == (10, 10, 1)
    
    def test_multiple_components_block_independently(self):
        """Multiple components should each block their own regions."""
        router = MazeRouter(grid_size=(30, 30), cell_size_mm=1.0)
        
        # Two 4x4mm components at (10, 10) and (20, 20)
        comp1 = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        comp2 = Component(ref="U2", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[10.0, 10.0], [20.0, 20.0]])
        
        router.block_components([comp1, comp2], positions, margin=0.0, escape_length=0)
        
        # Both centers should be blocked
        assert int(router.occupancy[10, 10, 0]) == 1
        assert int(router.occupancy[20, 20, 0]) == 1
        
        # Gap between components should be free
        assert int(router.occupancy[15, 15, 0]) == 0
    
    def test_component_blocking_visual_output(self):
        """Visual output should show blocked region matches expectation."""
        router = MazeRouter(grid_size=(15, 15), cell_size_mm=1.0)
        
        # 4x4mm component at (7, 7)
        comp = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[7.0, 7.0]])
        
        router.block_components([comp], positions, margin=0.5, escape_length=0)
        
        # Print visualization for manual inspection
        print("\n" + render_grid(router, layer=0))
        
        # Verify blocked region is roughly square and centered
        blocked_cells = []
        for x in range(15):
            for y in range(15):
                if int(router.occupancy[x, y, 0]) == 1:
                    blocked_cells.append((x, y))
        
        # Should have blocked cells
        assert len(blocked_cells) > 0
        
        # Center should be in blocked region
        assert (7, 7) in blocked_cells


class TestComponentBlockingEdgeCases:
    """Test edge cases in component blocking."""
    
    def test_zero_size_component_blocks_nothing(self):
        """Component with zero bounds should not block any cells."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        comp = Component(ref="U1", footprint="TEST", bounds=(0.0, 0.0), pins=[])
        positions = jnp.array([[5.0, 5.0]])
        
        router.block_components([comp], positions, margin=0.0, escape_length=0)
        
        # No cells should be blocked
        assert jnp.sum(router.occupancy) == 0
    
    def test_overlapping_components_both_blocked(self):
        """Overlapping components should both contribute to blocking."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # Two overlapping 4x4mm components
        comp1 = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        comp2 = Component(ref="U2", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[10.0, 10.0], [11.0, 11.0]])  # Overlapping
        
        router.block_components([comp1, comp2], positions, margin=0.0, escape_length=0)
        
        # Overlap region should be blocked
        assert int(router.occupancy[10, 10, 0]) == 1
        assert int(router.occupancy[11, 11, 0]) == 1
    
    def test_negative_margin_shrinks_blocking(self):
        """Negative margin should shrink blocked region."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # 6x6mm component with -1mm margin = 4x4mm effective
        comp = Component(ref="U1", footprint="TEST", bounds=(6.0, 6.0), pins=[])
        positions = jnp.array([[10.0, 10.0]])
        
        router.block_components([comp], positions, margin=-1.0, escape_length=0)
        
        # Effective size: 6 - 2*1 = 4mm
        # Should block similar to 4x4mm component
        assert int(router.occupancy[10, 10, 0]) == 1
        
        # Outer cells should be free
        assert int(router.occupancy[7, 10, 0]) == 0
        assert int(router.occupancy[13, 10, 0]) == 0
