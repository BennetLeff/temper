
import pytest
from temper_placer.routing.c_space_builder import CSpaceBuilder, CSpaceCache, CSpaceConfig
from temper_placer.routing.constraints.spatial_index import Pad
from temper_placer.routing.constraints.geometry import Point

def test_cache_hits():
    """Verify that repeating requests hits the cache."""
    builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
    # Add obstacle so clearance diff is visible
    builder.pads.append(Pad(
        center=Point(5.0, 5.0),
        size=(2.0, 2.0),
        shape="rect",
        rotation=0.0,
        net="GND",
        layer=0 
    ))
    cache = CSpaceCache(builder)
    
    # First request: Miss
    grid1 = cache.get_grid(clearance=0.2, trace_width=0.2)
    assert cache.stats.misses == 1
    assert cache.stats.hits == 0
    
    # Second request (same params): Hit
    grid2 = cache.get_grid(clearance=0.2, trace_width=0.2)
    assert cache.stats.misses == 1
    assert cache.stats.hits == 1
    
    # Third request (different params): Miss
    grid3 = cache.get_grid(clearance=2.0, trace_width=0.2)
    assert cache.stats.misses == 2
    assert cache.stats.hits == 1
    
    # Verify content equality (Identity is no longer guaranteed due to copy-on-write)
    import numpy as np
    assert np.array_equal(grid1.grid, grid2.grid)
    assert not np.array_equal(grid1.grid, grid3.grid)

def test_cache_exclusion_differentiation():
    """Verify that different exclusion sets reuse the same base grid (Hit)."""
    builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
    # Add dummy pad
    builder.pads.append(Pad(
        center=Point(5.0, 5.0),
        size=(2.0, 2.0),
        shape="rect",
        rotation=0.0,
        net="GND",
        layer=0 
    ))
    if "GND" not in builder.pads_by_net:
        builder.pads_by_net["GND"] = [builder.pads[-1]]
    
    cache = CSpaceCache(builder)
    
    # Grid A: No exclusion (Miss -> Build Base)
    gridA = cache.get_grid(0.2, 0.2, exclude_nets=set())
    
    # Grid B: Exclude GND (Hit Base -> Subtraction)
    gridB = cache.get_grid(0.2, 0.2, exclude_nets={"GND"})
    
    # Stats: 1 Miss (Base Build), 1 Hit (Base Reuse)
    assert cache.stats.misses == 1
    assert cache.stats.hits == 1
    
    assert gridA is not gridB
    
    # Content check: Grid A should verify blocked center, B should be free
    # (Assuming 5,5 is blocked in A)
    mid = 50
    assert gridA.grid[mid, mid, 0] == True
    assert gridB.grid[mid, mid, 0] == False
