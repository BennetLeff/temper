from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
import pytest

def test_empty_grid_all_available():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    assert grid.is_available(25, 25) == True
    assert grid.blocked_count == 0

def test_block_pad_with_clearance():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    
    # Block a 1mm pad at (25, 25) with 0.3mm clearance
    grid.block_circle(center=(25, 25), radius_mm=0.5, clearance_mm=0.3)
    
    # Center should be blocked
    assert grid.is_available(25, 25) == False
    
    # 0.5mm away (within pad) should be blocked
    assert grid.is_available(25.4, 25) == False
    
    # 0.9mm away (within clearance) should be blocked
    assert grid.is_available(25.7, 25) == False
    
    # 1.0mm away (outside clearance) should be available
    assert grid.is_available(26.0, 25) == True

def test_grid_is_deterministic():
    '''Same input produces same blocked cells.'''
    def build_grid():
        grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
        grid.block_circle(center=(25, 25), radius_mm=0.5, clearance_mm=0.3)
        return grid.blocked_cells
    
    result1 = build_grid()
    result2 = build_grid()
    assert result1 == result2
