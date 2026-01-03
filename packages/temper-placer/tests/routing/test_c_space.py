
import pytest
import numpy as np
from temper_placer.routing.c_space_builder import CSpaceBuilder, CSpaceConfig
from temper_placer.routing.constraints.spatial_index import Pad
from temper_placer.routing.constraints.geometry import Point

class MockBoard:
    def __init__(self):
        self.footprints = []

def test_c_space_builder_rasterization():
    """Verify that obstacles are rasterized and inflated."""
    builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
    
    pad = Pad(
        center=Point(5.0, 5.0),
        size=(2.0, 2.0),
        shape="rect",
        rotation=0.0,
        net="GND",
        layer=0 
    )
    builder.pads.append(pad)
    
    # Build grid: Clearance 1mm, Trace Width 1mm
    # Inflation = 1.0 + (1.0/2) = 1.5mm
    # Rect was 2mm wide (1mm radius from center).
    # New effective 'radius' from center = 1mm + 1.5mm = 2.5mm.
    # So box should be blocked approx from 2.5mm to 7.5mm.
    # Grid resolution 0.1mm => indices 25 to 75.
    
    grid = builder.build_grid(clearance=1.0, trace_width=1.0, exclude_nets=set())
    
    mid_idx = 50 # 5.0mm
    assert grid[mid_idx, mid_idx, 0] == True # Center should be blocked (Layer 0)
    assert not np.any(grid[:, :, 1]) # Layer 1 should be empty
    
    # Check edge of inflation
    # 2.5mm from center is limit. 
    # Center 50. 50-25=25. 50+25=75.
    assert grid[50, 25, 0] == True
    assert grid[50, 75, 0] == True
    
    # Just outside
    assert grid[50, 20, 0] == False # 2.0mm -> 3mm from center -> outside 2.5mm limit
    assert grid[50, 80, 0] == False

def test_c_space_builder_exclusion():
    """Verify net exclusion works."""
    builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
    pad = Pad(
        center=Point(5.0, 5.0),
        size=(2.0, 2.0),
        shape="rect",
        rotation=0.0,
        net="GND",
        layer=0 
    )
    builder.pads.append(pad)
    
    # Exclude "GND"
    grid = builder.build_grid(1.0, 1.0, exclude_nets={"GND"})
    assert not np.any(grid) # Should be completely empty
