import pytest
import math
from temper_placer.deterministic.pipeline import DeterministicPipeline
from tests.deterministic.fixtures import RoutingTestBoard

def _near(p1, p2, tolerance=1.0):
    dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
    return dist <= tolerance

def _passes_through(segment, point, radius=2.0):
    # Check if point is near segment start or end
    if _near(segment.start, point, radius) or _near(segment.end, point, radius):
        return True
    
    # Distance from point to line segment
    px, py = point
    x1, y1 = segment.start
    x2, y2 = segment.end
    
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return _near(segment.start, point, radius)
    
    t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    dist = ((px - closest_x)**2 + (py - closest_y)**2)**0.5
    return dist <= radius

def test_route_single_net_between_two_components():
    '''MVP-0 integration test: route one net on minimal board.'''
    
    # Setup: Two 0805 resistors, one net between them
    board = RoutingTestBoard(width_mm=50, height_mm=50)
    board.add_component('R1', footprint='0805', position=(10, 25))
    board.add_component('R2', footprint='0805', position=(40, 25))
    board.add_net('TEST_NET', pins=[('R1', '1'), ('R2', '1')])
    
    # Run the deterministic pipeline (MVP-0 scope)
    pipeline = DeterministicPipeline()
    result = pipeline.route_single_net(board, 'TEST_NET')
    
    # Verify
    assert result.success == True
    assert result.route is not None
    assert len(result.route.segments) > 0
    
    # Route should connect the pins
    start = result.route.segments[0].start
    end = result.route.segments[-1].end
    assert _near(start, (10 - 0.75, 25), tolerance=1.0)  # Near R1 pad 1
    assert _near(end, (40 - 0.75, 25), tolerance=1.0)    # Near R2 pad 1

def test_route_avoids_obstacle_component():
    '''Route should go around components in the way.'''
    
    board = RoutingTestBoard(width_mm=50, height_mm=50)
    board.add_component('R1', footprint='0805', position=(10, 25))
    board.add_component('R2', footprint='0805', position=(40, 25))
    board.add_component('C1', footprint='0805', position=(25, 25))  # In the way!
    board.add_net('TEST_NET', pins=[('R1', '1'), ('R2', '1')])
    
    pipeline = DeterministicPipeline()
    result = pipeline.route_single_net(board, 'TEST_NET')
    
    assert result.success == True
    # Route should not pass through C1's position
    for segment in result.route.segments:
        # Pad center is (25-0.75, 25) and (25+0.75, 25)
        assert not _passes_through(segment, (25 - 0.75, 25), radius=0.7)
        assert not _passes_through(segment, (25 + 0.75, 25), radius=0.7)

def test_routing_is_deterministic():
    '''Same board produces identical route every time.'''
    
    def run_routing():
        board = RoutingTestBoard(width_mm=50, height_mm=50)
        board.add_component('R1', footprint='0805', position=(10, 25))
        board.add_component('R2', footprint='0805', position=(40, 25))
        board.add_net('TEST_NET', pins=[('R1', '1'), ('R2', '1')])
        pipeline = DeterministicPipeline()
        return pipeline.route_single_net(board, 'TEST_NET')
    
    result1 = run_routing()
    result2 = run_routing()
    
    assert result1.route.segments == result2.route.segments