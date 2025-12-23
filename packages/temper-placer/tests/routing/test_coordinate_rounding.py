"""
Tests for coordinate rounding at cell boundaries (temper-1w8u.9).

Verifies that floating-point coordinates near cell boundaries are
consistently mapped to the correct grid cells.
"""

import pytest
import jax.numpy as jnp
from temper_placer.routing.maze_router import MazeRouter


class TestCoordinateRounding:
    """Test coordinate conversion with boundary conditions."""
    
    def test_exact_cell_center_maps_correctly(self):
        """Coordinates at exact cell centers should map to that cell."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # Cell (5, 5) has center at (5.5, 5.5) with 1mm cells
        gx, gy = router._world_to_grid(5.5, 5.5)
        assert gx == 6  # round(5.5) = 6
        assert gy == 6
    
    def test_cell_boundary_rounds_to_nearest(self):
        """Coordinates exactly on cell boundaries should round to nearest."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # Boundary at x=5.0 is between cells 5 and 6
        gx1, _ = router._world_to_grid(4.99, 5.0)
        gx2, _ = router._world_to_grid(5.01, 5.0)
        
        # Should round consistently
        assert gx1 == 5  # round(4.99) = 5
        assert gx2 == 5  # round(5.01) = 5
    
    def test_half_cell_offset_rounds_up(self):
        """Coordinates at x.5 should round up (Python's round behavior)."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # 5.5 should round to 6 (banker's rounding in Python 3)
        gx, _ = router._world_to_grid(5.5, 0.0)
        assert gx == 6
    
    def test_negative_coordinates_handled(self):
        """Negative coordinates should clamp to 0."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, origin=(0.0, 0.0))
        
        gx, gy = router._world_to_grid(-1.0, -1.0)
        assert gx == 0
        assert gy == 0
    
    def test_out_of_bounds_coordinates_clamp(self):
        """Coordinates beyond grid should clamp to max."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        gx, gy = router._world_to_grid(100.0, 100.0)
        assert gx == 9  # max index for size 10
        assert gy == 9
    
    def test_origin_offset_handled_correctly(self):
        """Non-zero origin should be accounted for."""
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, origin=(10.0, 10.0))
        
        # World (10.0, 10.0) should map to grid (0, 0)
        gx, gy = router._world_to_grid(10.0, 10.0)
        assert gx == 0
        assert gy == 0
        
        # World (15.5, 15.5) should map to grid (6, 6)
        gx, gy = router._world_to_grid(15.5, 15.5)
        assert gx == 6
        assert gy == 6
    
    def test_small_cell_size_precision(self):
        """Small cell sizes should maintain precision."""
        router = MazeRouter(grid_size=(100, 100), cell_size_mm=0.1)
        
        # 5.05mm with 0.1mm cells should map to cell 51 (round(50.5) = 50, but round(5.05/0.1) = round(50.5) = 50)
        gx, _ = router._world_to_grid(5.05, 0.0)
        assert gx == 50 or gx == 51  # Allow either due to floating point
    
    def test_component_blocking_uses_consistent_rounding(self):
        """Component blocking should use same rounding as world_to_grid."""
        from temper_placer.core.netlist import Component, Pin
        
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # Component at (10.0, 10.0) with 4x4mm bounds
        comp = Component(ref="U1", footprint="TEST", bounds=(4.0, 4.0), pins=[])
        positions = jnp.array([[10.0, 10.0]])
        
        router.block_components([comp], positions, margin=0.0)
        
        # Component should block cells around (10, 10)
        # With 4mm width centered at 10mm: 8mm to 12mm
        # Grid cells: round(8/1) to round(12/1) = 8 to 12
        assert int(router.occupancy[10, 10, 0]) == 1  # Center should be blocked
        assert int(router.occupancy[8, 10, 0]) == 1   # Left edge
        assert int(router.occupancy[12, 10, 0]) == 1  # Right edge


class TestBoundaryEdgeCases:
    """Test edge cases at grid boundaries."""
    
    def test_pin_exactly_on_grid_line(self):
        """Pin exactly on a grid line should be accessible."""
        from temper_placer.core.netlist import Component, Pin
        
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # Pin at exact grid coordinate (5.0, 5.0)
        comp = Component(
            ref="U1",
            footprint="TEST",
            bounds=(2.0, 2.0),
            pins=[Pin("1", "1", (0.0, 0.0))]  # Pin at component center
        )
        positions = jnp.array([[5.0, 5.0]])
        
        router.block_components([comp], positions, margin=0.0, escape_length=2)
        
        # Pin cell should be unblocked (escape route)
        gx, gy = router._world_to_grid(5.0, 5.0)
        assert int(router.occupancy[gx, gy, 0]) == 0
    
    def test_component_at_board_edge(self):
        """Component at board edge should not cause out-of-bounds."""
        from temper_placer.core.netlist import Component
        
        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0)
        
        # Component at edge (0.0, 0.0) with 2x2mm bounds
        comp = Component(ref="U1", footprint="TEST", bounds=(2.0, 2.0), pins=[])
        positions = jnp.array([[0.0, 0.0]])
        
        # Should not crash
        router.block_components([comp], positions, margin=0.0)
        
        # Should block some cells near origin
        assert int(router.occupancy[0, 0, 0]) == 1
