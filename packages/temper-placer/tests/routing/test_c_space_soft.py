
import numpy as np
import pytest
from temper_placer.routing.c_space_builder import SoftCSpaceBuilder
from temper_placer.routing.constraints.spatial_index import Pad
from temper_placer.routing.constraints.geometry import Point

from temper_placer.routing.c_space_builder import SoftCSpaceBuilder, CSpaceConfig

def test_soft_c_space_gradients():
    """Verify that cost grid has gradients around obstacles."""
    builder = SoftCSpaceBuilder(width_mm=10.0, height_mm=10.0, config=CSpaceConfig(resolution_mm=0.1))
    
    # Add a single pad in center
    builder.pads.append(Pad(
        center=Point(5.0, 5.0),
        size=(2.0, 2.0),
        shape="rect",
        rotation=0.0,
        net="GND",
        layer=0 
    ))
    
    # Build cost grid
    cost_grid = builder.build_cost_grid(net_class="Signal", exclude_nets=set())
    
    # Center should be MAX cost (technically inside obstacle, distance=0)
    # Actually build_grid blocks it. ~raw_grid makes it 0. distanceTransform to nearest 0 is 0.
    # So dist at center should be 0.
    # Cost = 50 * exp(-0) = 50.
    # Cost = 50 * exp(-0) = 50.
    w, h, l = cost_grid.shape
    center_cost = cost_grid[w//2, h//2, 0]
    assert np.isclose(center_cost, 50.0, atol=1.0)
    
    # Point far away (0,0) -> dist ~ 5mm * sqrt(2) ~ 7mm
    # Cost = 50 * exp(-7) ~ very small
    corner_cost = cost_grid[0, 0, 0]
    assert corner_cost < 1.0
    
    # Point near but outside (6.5mm, 5.0mm) -> Pad edge is at 6.0mm (5 + 2/2).
    # Dist 0.5mm.
    # Cost = 50 * exp(-0.5) = 50 * 0.606 = 30.3
    # Grid coords: 6.5mm / 0.1 = 65. x=65. y=50.
    near_cost = cost_grid[65, 50, 0]
    assert 20.0 < near_cost < 40.0
