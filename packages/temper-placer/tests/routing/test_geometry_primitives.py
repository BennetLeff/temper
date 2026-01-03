
import math
import pytest
from temper_placer.routing.constraints.geometry import Point, LineSegment, RotatedRect, point_to_rotated_rect_distance, segment_to_rotated_rect_distance

def test_point_to_rotated_rect_distance():
    # 2x4 rect at (10,10), rotated 0 degrees
    # Corners: (9,8), (11,8), (11,12), (9,12)
    rect = RotatedRect(center=Point(10, 10), size=(2, 4), rotation=0.0)
    
    # Inside
    assert point_to_rotated_rect_distance(Point(10, 10), rect) < 0
    assert point_to_rotated_rect_distance(Point(10.9, 11), rect) < 0
    
    # Edges
    assert abs(point_to_rotated_rect_distance(Point(11, 10), rect)) < 1e-6 # Right edge (x+1)
    assert abs(point_to_rotated_rect_distance(Point(10, 12), rect)) < 1e-6 # Top edge (y+2)
    
    # Outside
    assert abs(point_to_rotated_rect_distance(Point(12, 10), rect) - 1.0) < 1e-6 # 1mm right
    assert abs(point_to_rotated_rect_distance(Point(10, 13), rect) - 1.0) < 1e-6 # 1mm up

def test_rotated_rect_90_degrees():
    # 2x4 rect at (10,10), rotated 90 degrees
    # Effectively 4x2 rect. x[8,12], y[9,11]
    rect = RotatedRect(center=Point(10, 10), size=(2, 4), rotation=90.0)
    
    # Check boundaries
    assert abs(point_to_rotated_rect_distance(Point(12, 10), rect)) < 1e-6 # x+2
    assert abs(point_to_rotated_rect_distance(Point(13, 10), rect) - 1.0) < 1e-6
    
    # Point inside
    assert point_to_rotated_rect_distance(Point(11, 10), rect) < 0

def test_segment_to_rotated_rect():
    rect = RotatedRect(center=Point(10, 10), size=(2, 2), rotation=0.0)
    # Rect boundaries: x[9,11], y[9,11]
    
    # Segment crossing through
    seg_cross = LineSegment(Point(0, 10), Point(20, 10))
    assert segment_to_rotated_rect_distance(seg_cross, rect) < 0 # Intersection
    
    # Segment nearby (1mm away)
    seg_near = LineSegment(Point(12, 0), Point(12, 20)) # x=12, 1mm from x=11
    assert abs(segment_to_rotated_rect_distance(seg_near, rect) - 1.0) < 1e-6
