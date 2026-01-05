
import pytest
from temper_placer.deterministic.geometry.courtyard import Courtyard, check_overlap

def test_courtyard_creation():
    points = [(0,0), (10,0), (10,10), (0,10)]
    c = Courtyard("Test", points)
    assert c._polygon.area == 100.0

def test_courtyard_overlap():
    # Two 10x10 squares
    # c1 centered at 0,0 (points relative to center)
    p1 = [(-5,-5), (5,-5), (5,5), (-5,5)]
    c1 = Courtyard("C1", p1)
    
    # c2 identical
    c2 = Courtyard("C2", p1)
    
    # Case 1: Massive overlap (same pos)
    assert check_overlap(c1, (0,0), 0, c2, (0,0), 0) == True
    
    # Case 2: No overlap (far away)
    assert check_overlap(c1, (0,0), 0, c2, (20,20), 0) == False
    
    # Case 3: Partial overlap
    # C1 at 0,0, C2 at 8,0 (width 10, so edges are at +/-5)
    # C1 x-range: [-5, 5]
    # C2 x-range: [3, 13] (8-5, 8+5)
    # Overlap interval [3, 5] -> YES
    assert check_overlap(c1, (0,0), 0, c2, (8,0), 0) == True
    
    # Case 4: Touching (should not be overlap)
    # C2 at 10,0 -> Edge at 5 vs Edge at 5
    # check_overlap returns False for touches by default in implementation
    assert check_overlap(c1, (0,0), 0, c2, (10,0), 0) == False

def test_courtyard_rotation():
    # Rectangle 10x2
    points = [(-5,-1), (5,-1), (5,1), (-5,1)]
    c = Courtyard("R1", points)
    
    # At 0 rotation: Width 10, Height 2
    # At 90 rotation: Width 2, Height 10
    
    # Check bounds of rotated polygon
    poly_0 = c.get_global_polygon(0, 0, 0)
    b0 = poly_0.bounds # minx, miny, maxx, maxy
    assert b0[2] - b0[0] == 10.0
    assert b0[3] - b0[1] == 2.0
    
    poly_90 = c.get_global_polygon(0, 0, 1)
    b90 = poly_90.bounds
    assert abs((b90[2] - b90[0]) - 2.0) < 1e-6
    assert abs((b90[3] - b90[1]) - 10.0) < 1e-6
