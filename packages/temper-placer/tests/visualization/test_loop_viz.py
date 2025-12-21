import pytest
from temper_placer.visualization.loop_viz import calculate_loop_area, get_loop_points
from temper_placer.core.loop import Loop, LoopType, LoopPin
from temper_placer.visualization.model import BoardView, ComponentView, Point

def test_calculate_loop_area_square():
    """Test area calculation for a simple 10x10 square."""
    points = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    assert calculate_loop_area(points) == 100.0

def test_calculate_loop_area_triangle():
    """Test area calculation for a right triangle."""
    points = [(0, 0), (10, 0), (0, 10), (0, 0)]
    assert calculate_loop_area(points) == 50.0

def test_get_loop_points_fallback():
    """Test that points fallback to component centers if pads missing."""
    loop = Loop(
        name="test", 
        loop_type=LoopType.CUSTOM, 
        description="",
        components=["U1", "R1"]
    )
    
    board_view = BoardView(
        width=100, height=100,
        components=(
            ComponentView(ref="U1", position=Point(10, 10), rotation=0, width=5, height=5),
            ComponentView(ref="R1", position=Point(20, 10), rotation=0, width=2, height=1)
        ),
        pads=()
    )
    
    points = get_loop_points(loop, board_view)
    # Should be [(10,10), (20,10), (10,10)]
    assert len(points) == 3
    assert points[0] == (10, 10)
    assert points[1] == (20, 10)
    assert points[2] == (10, 10)