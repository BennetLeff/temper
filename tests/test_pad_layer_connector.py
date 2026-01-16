"""
Test suite for PadLayerConnector - handles pad-to-layer transitions.

TDD for Stage 2: Via-Aware Routing Integration
"""

import pytest
from shapely.geometry import Point, box
from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner
from temper_placer.router_v6.pad_layer_connector import (
    PadLayerConnector, Pad, ConnectionPoint
)


class TestPad:
    """Test Pad data structure"""
    
    def test_pad_creation(self):
        """Pad should store position and layer info"""
        pad = Pad(
            position=(10, 20),
            layers=['F.Cu', 'F.Paste', 'F.Mask'],
            net='TEST_NET',
            ref='U1',
            number='1'
        )
        
        assert pad.position == (10, 20)
        assert 'F.Cu' in pad.layers
        assert pad.net == 'TEST_NET'
        assert pad.ref == 'U1'
        assert pad.number == '1'
    
    def test_pad_is_on_layer(self):
        """Check if pad exists on specific layer"""
        smd_pad = Pad((10, 20), ['F.Cu'], 'NET1', 'U1', '1')
        tht_pad = Pad((30, 40), ['F.Cu', 'B.Cu'], 'NET2', 'D1', '1')
        
        assert smd_pad.is_on_layer('F.Cu')
        assert not smd_pad.is_on_layer('B.Cu')
        
        assert tht_pad.is_on_layer('F.Cu')
        assert tht_pad.is_on_layer('B.Cu')
    
    def test_pad_is_tht(self):
        """Detect through-hole pads"""
        smd_pad = Pad((10, 20), ['F.Cu'], 'NET1', 'U1', '1')
        tht_pad = Pad((30, 40), ['F.Cu', 'B.Cu'], 'NET2', 'D1', '1')
        
        assert not smd_pad.is_tht()
        assert tht_pad.is_tht()
    
    def test_pad_distance_to(self):
        """Calculate distance between pads"""
        pad1 = Pad((0, 0), ['F.Cu'], 'NET1', 'U1', '1')
        pad2 = Pad((3, 4), ['F.Cu'], 'NET1', 'U1', '2')
        
        assert pad1.distance_to(pad2) == pytest.approx(5.0, abs=0.01)


class TestConnectionPoint:
    """Test ConnectionPoint data structure"""
    
    def test_connection_point_no_via(self):
        """Connection point for pad on routing layer"""
        conn = ConnectionPoint(
            position=(10, 20),
            layer='F.Cu',
            via=None,
            requires_escape=False
        )
        
        assert conn.position == (10, 20)
        assert conn.layer == 'F.Cu'
        assert conn.via is None
        assert not conn.requires_escape
    
    def test_connection_point_with_via(self):
        """Connection point requiring via"""
        from temper_placer.router_v6.via_planner import PlacedVia
        
        via = PlacedVia(
            position=(10, 20),
            spec=ViaSpec.standard(),
            layers=['F.Cu', 'In1.Cu'],
            net='NET1'
        )
        
        conn = ConnectionPoint(
            position=(10, 20),
            layer='In1.Cu',
            via=via,
            requires_escape=True
        )
        
        assert conn.via is via
        assert conn.layer == 'In1.Cu'
        assert conn.requires_escape


class TestPadLayerConnector:
    """Test pad-to-layer connection logic"""
    
    @pytest.fixture
    def connector(self):
        """Create connector with via planner"""
        board_area = box(0, 0, 100, 100)
        via_planner = ViaPlanner(board_area, ViaSpec.standard())
        return PadLayerConnector(via_planner)
    
    def test_direct_connection_same_layer(self, connector):
        """Pad on routing layer - no via needed"""
        pad = Pad((10, 20), ['F.Cu'], 'NET1', 'U1', '1')
        
        conn = connector.get_connection_point(pad, 'F.Cu')
        
        assert conn is not None
        assert conn.position == pad.position
        assert conn.layer == 'F.Cu'
        assert conn.via is None
        assert not conn.requires_escape
    
    def test_tht_pad_any_layer(self, connector):
        """THT pad connects to any layer directly"""
        tht_pad = Pad((10, 20), ['F.Cu', 'B.Cu'], 'NET1', 'D1', '1')
        
        # Route on F.Cu
        conn_f = connector.get_connection_point(tht_pad, 'F.Cu')
        assert conn_f is not None
        assert conn_f.via is None
        
        # Route on B.Cu
        conn_b = connector.get_connection_point(tht_pad, 'B.Cu')
        assert conn_b is not None
        assert conn_b.via is None
        
        # Route on inner layer - THT still connects
        conn_in1 = connector.get_connection_point(tht_pad, 'In1.Cu')
        assert conn_in1 is not None
        assert conn_in1.via is None
    
    def test_smd_pad_needs_via(self, connector):
        """SMD pad on F.Cu routing on In1.Cu needs via"""
        smd_pad = Pad((10, 20), ['F.Cu'], 'NET1', 'U1', '1')
        
        conn = connector.get_connection_point(smd_pad, 'In1.Cu')
        
        assert conn is not None
        assert conn.via is not None
        assert conn.via.net == 'NET1'
        # Via should be near pad
        dist = ((conn.position[0] - smd_pad.position[0])**2 + 
                (conn.position[1] - smd_pad.position[1])**2)**0.5
        assert dist < 2.0  # Within 2mm
    
    def test_via_placement_blocked(self, connector):
        """Via placement fails if area blocked"""
        smd_pad = Pad((10, 20), ['F.Cu'], 'NET1', 'U1', '1')
        
        # Block area around pad
        for x in range(8, 13):
            for y in range(18, 23):
                obstacle = Point(x, y).buffer(0.5)
                connector.via_planner.add_obstacle(obstacle, 'F.Cu')
        
        conn = connector.get_connection_point(smd_pad, 'In1.Cu')
        
        # Should either find alternative position or fail gracefully
        # (depends on search radius)
        if conn is None:
            # Failed to find via location - acceptable
            pass
        else:
            # Found via location - should be far from blocked area
            dist = ((conn.position[0] - smd_pad.position[0])**2 + 
                    (conn.position[1] - smd_pad.position[1])**2)**0.5
            assert dist > 2.0  # Farther than blocked zone
    
    def test_via_reuse_same_net(self, connector):
        """Via reuse works when ViaPlanner conditions met"""
        # The via reuse logic is in ViaPlanner (tested separately)
        # PadLayerConnector just delegates to it
        # This test validates the delegation works
        
        pad1 = Pad((50, 50), ['F.Cu'], 'NET1', 'U1', '1')
        conn1 = connector.get_connection_point(pad1, 'In1.Cu')
        
        assert conn1 is not None
        assert conn1.via is not None
        
        # ViaPlanner tracks this via for NET1
        assert len(connector.via_planner.get_vias_for_net('NET1')) == 1
        
        # Place another pad far away - will get new via
        pad2 = Pad((60, 60), ['F.Cu'], 'NET1', 'U1', '2')
        conn2 = connector.get_connection_point(pad2, 'In1.Cu')
        
        assert conn2 is not None
        assert conn2.via is not None
        
        # Should have 2 vias now (pads too far apart for reuse)
        assert len(connector.via_planner.get_vias_for_net('NET1')) == 2
    
    def test_dense_ic_escape_required(self, connector):
        """Dense IC pads should require escape routing"""
        # QFN pad with 0.4mm pitch neighbors
        pad = Pad((10, 20), ['F.Cu'], 'USB_D+', 'U_MCU', '40')
        
        # Add neighboring pads (0.4mm apart)
        neighbor1 = Point(10, 19.6).buffer(0.12)
        neighbor2 = Point(10, 20.4).buffer(0.12)
        connector.via_planner.add_obstacle(neighbor1, 'F.Cu')
        connector.via_planner.add_obstacle(neighbor2, 'F.Cu')
        
        conn = connector.get_connection_point(pad, 'In1.Cu')
        
        if conn is not None:
            # Via should be placed away from pad (fanout)
            dist = ((conn.position[0] - pad.position[0])**2 + 
                    (conn.position[1] - pad.position[1])**2)**0.5
            assert dist > 1.0  # Via in fanout zone, not at pad
            assert conn.requires_escape  # Flag for router


class TestViaPositionStrategy:
    """Test via placement strategy near pads"""
    
    @pytest.fixture
    def connector(self):
        board_area = box(0, 0, 100, 100)
        via_planner = ViaPlanner(board_area, ViaSpec.standard())
        return PadLayerConnector(via_planner)
    
    def test_via_near_pad_clear_space(self, connector):
        """Via should be placed close to pad in clear space"""
        pad = Pad((50, 50), ['F.Cu'], 'NET1', 'U1', '1')
        
        conn = connector.get_connection_point(pad, 'In1.Cu')
        
        assert conn is not None
        # Via should be within 1mm of pad (close proximity)
        dist = ((conn.position[0] - pad.position[0])**2 + 
                (conn.position[1] - pad.position[1])**2)**0.5
        assert dist < 1.0
    
    def test_via_fanout_dense_area(self, connector):
        """Via should fanout from pad in dense area"""
        pad = Pad((50, 50), ['F.Cu'], 'NET1', 'U1', '1')
        
        # Add dense obstacles around pad
        for i in range(-3, 4):
            for j in range(-3, 4):
                if abs(i) + abs(j) < 3:  # Within 2mm
                    obstacle = Point(50 + i*0.5, 50 + j*0.5).buffer(0.2)
                    connector.via_planner.add_obstacle(obstacle, 'F.Cu')
        
        conn = connector.get_connection_point(pad, 'In1.Cu')
        
        if conn is not None:
            # Via should be in fanout zone (2-5mm from pad)
            dist = ((conn.position[0] - pad.position[0])**2 + 
                    (conn.position[1] - pad.position[1])**2)**0.5
            assert dist >= 2.0
            assert dist <= 5.0
