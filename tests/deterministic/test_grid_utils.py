import pytest
from temper_placer.deterministic.geometry.grid_utils import snap_to_grid, add_endpoint_nudge

def test_snap_to_grid():
    assert snap_to_grid((12.37, 8.91), 0.25) == (12.25, 9.0)
    assert snap_to_grid((12.12, 8.87), 0.25) == (12.0, 8.75) # 12.12 is closer to 12.0
    assert snap_to_grid((0.0, 0.0), 0.25) == (0.0, 0.0)
    assert snap_to_grid((0.12, 0.13), 0.25) == (0.0, 0.25)

def test_endpoint_nudge():
    path = [(12.25, 9.0), (15.0, 9.0), (15.0, 12.0)]
    actual_start = (12.37, 8.91)
    actual_end = (15.1, 12.05)
    result = add_endpoint_nudge(path, actual_start, actual_end)
    
    assert result[0] == actual_start
    assert result[1] == (12.25, 9.0)
    assert result[-2] == (15.0, 12.0)
    assert result[-1] == actual_end
    assert len(result) == 5

def test_endpoint_nudge_no_path():
    assert add_endpoint_nudge([], (0,0), (1,1)) == []

def test_endpoint_nudge_zero_dist():
    path = [(0.0, 0.0), (1.0, 1.0)]
    result = add_endpoint_nudge(path, (0.0, 0.0), (1.0, 1.0))
    assert result == path
    assert len(result) == 2
