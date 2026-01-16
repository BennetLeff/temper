"""
Test suite for ViaPlanner - intelligent via placement with collision detection.

TDD for via placement during routing (not post-processing).
"""

import pytest
from shapely.geometry import Point, Polygon, box
from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner, PlacedVia


class TestViaPlanner:
    """Test intelligent via placement"""
    
    @pytest.fixture
    def planner(self):
        """Create via planner with simple board"""
        board_area = box(0, 0, 100, 100)  # 100x100mm board
        return ViaPlanner(
            board_area=board_area,
            via_spec=ViaSpec.standard()
        )
    
    @pytest.fixture
    def planner_with_obstacles(self):
        """Via planner with some existing obstacles"""
        board_area = box(0, 0, 100, 100)
        planner = ViaPlanner(board_area, ViaSpec.standard())
        
        # Add a pad obstacle at (10, 10)
        pad = Point(10, 10).buffer(0.5)
        planner.add_obstacle(pad, 'F.Cu')
        
        return planner
    
    def test_place_via_in_clear_space(self, planner):
        """Via should be placeable in clear space"""
        via = planner.place_via(
            position=(50, 50),
            from_layer='F.Cu',
            to_layer='B.Cu',
            net='TEST_NET'
        )
        
        assert via is not None
        assert via.position == (50, 50)
        assert via.net == 'TEST_NET'
        assert 'F.Cu' in via.layers
        assert 'B.Cu' in via.layers
    
    def test_place_via_too_close_to_obstacle(self, planner_with_obstacles):
        """Via should not be placeable too close to obstacle"""
        # Try to place via at (10.5, 10) - only 0.5mm from pad edge
        # With via keepout of 0.7mm, this should fail
        via = planner_with_obstacles.place_via(
            position=(10.5, 10),
            from_layer='F.Cu',
            to_layer='B.Cu',
            net='TEST_NET'
        )
        
        assert via is None  # Placement failed
    
    def test_place_via_far_from_obstacle(self, planner_with_obstacles):
        """Via should be placeable far from obstacles"""
        # Place via at (15, 10) - 4.5mm from pad center, ~4mm from edge
        via = planner_with_obstacles.place_via(
            position=(15, 10),
            from_layer='F.Cu',
            to_layer='B.Cu',
            net='TEST_NET'
        )
        
        assert via is not None
    
    def test_via_becomes_obstacle(self, planner):
        """Placed via should become obstacle for subsequent placements"""
        # Place first via
        via1 = planner.place_via((50, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via1 is not None
        
        # Try to place second via too close (1mm away, need 1.4mm)
        via2 = planner.place_via((51, 50), 'F.Cu', 'B.Cu', 'NET2')
        assert via2 is None  # Should fail
        
        # Place second via with proper spacing (2mm away)
        via3 = planner.place_via((52, 50), 'F.Cu', 'B.Cu', 'NET2')
        assert via3 is not None
    
    def test_via_reuse_same_net(self, planner):
        """Should reuse existing via for same net if close enough"""
        # Place via for NET1
        via1 = planner.place_via((50, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via1 is not None
        
        # Try to place via for NET1 at nearly same location (0.1mm away)
        via2 = planner.place_via((50.1, 50), 'F.Cu', 'B.Cu', 'NET1')
        
        # Should reuse via1, not create new via
        assert via2 is via1
        assert len(planner.placed_vias) == 1
    
    def test_via_outside_board(self, planner):
        """Via should not be placeable outside board"""
        via = planner.place_via((-5, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via is None
        
        via = planner.place_via((105, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via is None
    
    def test_via_too_close_to_edge(self, planner):
        """Via should not be placeable too close to board edge"""
        # Via keepout_radius = 0.7mm, so via at (0.5, 50) is too close to edge
        via = planner.place_via((0.5, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via is None
        
        # Via at (1.0, 50) should be legal
        via = planner.place_via((1.0, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert via is not None
    
    def test_get_via_at_position(self, planner):
        """Should be able to query vias at position"""
        planner.place_via((50, 50), 'F.Cu', 'B.Cu', 'NET1')
        
        # Exact position
        via = planner.get_via_at((50, 50))
        assert via is not None
        assert via.net == 'NET1'
        
        # Nearby position (within tolerance)
        via = planner.get_via_at((50.05, 50.05))
        assert via is not None
        
        # Far position
        via = planner.get_via_at((60, 60))
        assert via is None
    
    def test_get_vias_for_net(self, planner):
        """Should be able to query all vias for a net"""
        planner.place_via((50, 50), 'F.Cu', 'B.Cu', 'NET1')
        planner.place_via((60, 60), 'F.Cu', 'B.Cu', 'NET1')
        planner.place_via((70, 70), 'F.Cu', 'B.Cu', 'NET2')
        
        net1_vias = planner.get_vias_for_net('NET1')
        assert len(net1_vias) == 2
        
        net2_vias = planner.get_vias_for_net('NET2')
        assert len(net2_vias) == 1
    
    def test_via_count_tracking(self, planner):
        """Via planner should track via count"""
        assert planner.via_count == 0
        
        planner.place_via((50, 50), 'F.Cu', 'B.Cu', 'NET1')
        assert planner.via_count == 1
        
        planner.place_via((60, 60), 'F.Cu', 'B.Cu', 'NET2')
        assert planner.via_count == 2
        
        # Failed placement shouldn't increase count
        planner.place_via((60.5, 60), 'F.Cu', 'B.Cu', 'NET3')  # Too close
        assert planner.via_count == 2


class TestViaSearch:
    """Test finding optimal via placement locations"""
    
    @pytest.fixture
    def planner(self):
        board_area = box(0, 0, 100, 100)
        return ViaPlanner(board_area, ViaSpec.standard())
    
    def test_find_via_near_position(self, planner):
        """Find legal via location near desired position"""
        # Add obstacle at (50, 50)
        obstacle = Point(50, 50).buffer(2.0)
        planner.add_obstacle(obstacle, 'F.Cu')
        
        # Try to find via location near (50, 50) but not intersecting obstacle
        position = planner.find_via_location_near(
            target=(50, 50),
            search_radius=5.0
        )
        
        assert position is not None
        # Should be within search radius
        dist = ((position[0] - 50)**2 + (position[1] - 50)**2)**0.5
        assert dist <= 5.0
        
        # Should not intersect obstacle (check clearance)
        via_zone = Point(position).buffer(planner.via_spec.keepout_radius)
        assert not via_zone.intersects(obstacle)
    
    def test_find_via_no_space_available(self, planner):
        """Return None if no legal position found"""
        # Fill area with obstacles
        for x in range(45, 56):
            for y in range(45, 56):
                obstacle = Point(x, y).buffer(0.5)
                planner.add_obstacle(obstacle, 'F.Cu')
        
        # Try to find via location near (50, 50) - should fail
        position = planner.find_via_location_near(
            target=(50, 50),
            search_radius=3.0
        )
        
        assert position is None


class TestPlacedVia:
    """Test PlacedVia data structure"""
    
    def test_placed_via_attributes(self):
        """PlacedVia should store all necessary attributes"""
        via = PlacedVia(
            position=(50, 50),
            spec=ViaSpec.standard(),
            layers=['F.Cu', 'B.Cu'],
            net='TEST_NET'
        )
        
        assert via.position == (50, 50)
        assert via.net == 'TEST_NET'
        assert via.spec.diameter == 0.8
        assert 'F.Cu' in via.layers
        assert 'B.Cu' in via.layers
    
    def test_via_keepout_zone(self):
        """PlacedVia should provide keepout zone"""
        via = PlacedVia(
            position=(50, 50),
            spec=ViaSpec.standard(),
            layers=['F.Cu', 'B.Cu'],
            net='NET1'
        )
        
        keepout = via.keepout_zone()
        assert isinstance(keepout, Polygon)
        
        # Keepout should be centered at via position
        assert abs(keepout.centroid.x - 50) < 0.01
        assert abs(keepout.centroid.y - 50) < 0.01
        
        # Keepout radius should match spec
        # Area = π * r^2, so r = sqrt(area / π)
        import math
        expected_radius = via.spec.keepout_radius
        actual_radius = math.sqrt(keepout.area / math.pi)
        assert abs(actual_radius - expected_radius) < 0.01
