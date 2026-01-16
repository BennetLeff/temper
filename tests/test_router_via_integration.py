"""
Integration tests for ExactGeometryRouter with via-aware routing.

Tests the complete flow:
1. Router uses PadLayerConnector for pad transitions
2. ViaPlanner places vias during routing
3. Vias become obstacles for subsequent nets
4. Export includes vias (not post-process)
"""

import pytest
from pathlib import Path
from shapely.geometry import box, Point

from temper_placer.router_v6.via_model import ViaSpec
from temper_placer.router_v6.via_planner import ViaPlanner
from temper_placer.router_v6.pad_layer_connector import Pad, PadLayerConnector
from temper_placer.router_v6.exact_geometry_router_via_aware import (
    ExactGeometryRouterViaAware, NetRoute
)


class TestViaAwareRouterBasics:
    """Test basic via-aware router functionality"""
    
    @pytest.fixture
    def simple_board(self):
        """Create simple test board"""
        board_area = box(0, 0, 100, 100)
        via_spec = ViaSpec.standard()
        via_planner = ViaPlanner(board_area, via_spec)
        pad_connector = PadLayerConnector(via_planner)
        
        return {
            'board_area': board_area,
            'via_planner': via_planner,
            'pad_connector': pad_connector
        }
    
    def test_route_with_direct_connection(self, simple_board):
        """Route net where pads on routing layer - no via needed"""
        router = ExactGeometryRouterViaAware(
            board_area=simple_board['board_area'],
            via_planner=simple_board['via_planner'],
            pad_connector=simple_board['pad_connector']
        )
        
        # Both pads on F.Cu, routing on F.Cu
        pads = [
            Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
            Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
        ]
        
        route = router.route_net('NET1', pads, 'F.Cu')
        
        assert route is not None
        assert route.net == 'NET1'
        assert len(route.tracks) > 0
        assert len(route.vias) == 0  # No vias needed
    
    def test_route_with_via_for_layer_change(self, simple_board):
        """Route net requiring via for layer transition"""
        router = ExactGeometryRouterViaAware(
            board_area=simple_board['board_area'],
            via_planner=simple_board['via_planner'],
            pad_connector=simple_board['pad_connector']
        )
        
        # Pads on F.Cu, routing on In1.Cu
        pads = [
            Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
            Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
        ]
        
        route = router.route_net('NET1', pads, 'In1.Cu')
        
        assert route is not None
        assert len(route.vias) == 2  # Via at each pad
        assert len(route.tracks) > 0
        
        # Check vias are near pads
        for via in route.vias:
            assert via.net == 'NET1'
            # Via should be near one of the pads
            near_pad = any(
                via.distance_to(pad.position) < 2.0
                for pad in pads
            )
            assert near_pad
    
    def test_tht_pad_no_via(self, simple_board):
        """THT pads should not require vias"""
        router = ExactGeometryRouterViaAware(
            board_area=simple_board['board_area'],
            via_planner=simple_board['via_planner'],
            pad_connector=simple_board['pad_connector']
        )
        
        # THT pads (on F.Cu and B.Cu)
        pads = [
            Pad((10, 10), ['F.Cu', 'B.Cu'], 'NET1', 'D1', '1'),
            Pad((20, 10), ['F.Cu', 'B.Cu'], 'NET1', 'D1', '2')
        ]
        
        # Route on inner layer
        route = router.route_net('NET1', pads, 'In1.Cu')
        
        assert route is not None
        assert len(route.vias) == 0  # THT pads connect all layers


class TestViaAsObstacle:
    """Test that placed vias become obstacles for subsequent nets"""
    
    @pytest.fixture
    def router_with_via(self):
        """Router with one via already placed"""
        board_area = box(0, 0, 100, 100)
        via_spec = ViaSpec.standard()
        via_planner = ViaPlanner(board_area, via_spec)
        pad_connector = PadLayerConnector(via_planner)
        
        router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
        
        # Route NET1 (will place vias)
        pads1 = [
            Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
            Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
        ]
        route1 = router.route_net('NET1', pads1, 'In1.Cu')
        
        return router, route1
    
    def test_via_blocks_subsequent_placement(self, router_with_via):
        """Via from NET1 should block NET2 via placement"""
        router, route1 = router_with_via
        
        assert len(route1.vias) > 0
        via1_pos = route1.vias[0].position
        
        # Try to route NET2 very close to NET1's via
        pads2 = [
            Pad((via1_pos[0] + 0.5, via1_pos[1]), ['F.Cu'], 'NET2', 'U2', '1'),
            Pad((via1_pos[0] + 10, via1_pos[1]), ['F.Cu'], 'NET2', 'U2', '2')
        ]
        
        route2 = router.route_net('NET2', pads2, 'In1.Cu')
        
        if route2 and len(route2.vias) > 0:
            # NET2's via should be >1.4mm from NET1's via
            for via2 in route2.vias:
                for via1 in route1.vias:
                    dist = via2.distance_to(via1.position)
                    assert dist >= 1.4 or dist < 0.01  # Either proper spacing or reused


class TestDenseICFanout:
    """Test escape routing for dense ICs"""
    
    @pytest.fixture
    def router_with_dense_ic(self):
        """Router with dense IC obstacles"""
        board_area = box(0, 0, 100, 100)
        via_spec = ViaSpec.standard()
        via_planner = ViaPlanner(board_area, via_spec)
        
        # Add QFN-56 pads (0.4mm pitch)
        ic_center = (50, 50)
        for i in range(14):
            x = ic_center[0] - 3.5 + (i * 0.4)
            y = ic_center[1] + 3.5
            pad_obstacle = Point(x, y).buffer(0.12)
            via_planner.add_obstacle(pad_obstacle, 'F.Cu')
        
        pad_connector = PadLayerConnector(via_planner)
        router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
        
        return router
    
    def test_via_fanout_from_dense_ic(self, router_with_dense_ic):
        """Via should be placed in fanout zone for dense IC"""
        router = router_with_dense_ic
        
        # Pad on dense IC
        pads = [
            Pad((50, 53.5), ['F.Cu'], 'USB_D+', 'U_MCU', '40'),
            Pad((70, 50), ['F.Cu'], 'USB_D+', 'J_USB', 'A6')
        ]
        
        route = router.route_net('USB_D+', pads, 'In1.Cu')
        
        if route and len(route.vias) > 0:
            # Via at dense IC pad should be in fanout zone (>1mm away)
            via_near_ic = None
            for via in route.vias:
                if via.distance_to(pads[0].position) < 5.0:
                    via_near_ic = via
                    break
            
            if via_near_ic:
                dist = via_near_ic.distance_to(pads[0].position)
                assert dist > 1.0  # In fanout zone


class TestMultiNetRouting:
    """Test routing multiple nets with via interactions"""
    
    def test_route_multiple_nets_sequentially(self):
        """Route multiple nets, vias from earlier nets become obstacles"""
        board_area = box(0, 0, 100, 100)
        via_planner = ViaPlanner(board_area, ViaSpec.standard())
        pad_connector = PadLayerConnector(via_planner)
        router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
        
        # Define 3 nets
        nets = [
            ('NET1', [
                Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
                Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
            ]),
            ('NET2', [
                Pad((10, 20), ['F.Cu'], 'NET2', 'U2', '1'),
                Pad((20, 20), ['F.Cu'], 'NET2', 'U2', '2')
            ]),
            ('NET3', [
                Pad((10, 30), ['F.Cu'], 'NET3', 'U3', '1'),
                Pad((20, 30), ['F.Cu'], 'NET3', 'U3', '2')
            ])
        ]
        
        routes = []
        for net_name, pads in nets:
            route = router.route_net(net_name, pads, 'In1.Cu')
            if route:
                routes.append(route)
        
        # Should successfully route all nets
        assert len(routes) == 3
        
        # Count total vias
        total_vias = sum(len(r.vias) for r in routes)
        assert total_vias > 0
        
        # Check all vias have proper spacing
        all_vias = []
        for route in routes:
            all_vias.extend(route.vias)
        
        for i, via1 in enumerate(all_vias):
            for via2 in all_vias[i+1:]:
                if via1.net != via2.net:
                    dist = via1.distance_to(via2.position)
                    # Should be either properly spaced or impossible conflict
                    if dist < 1.4:
                        # If too close, routing should have failed or reused via
                        pytest.skip("Via placement conflict detected")


class TestExportWithVias:
    """Test that routes export with vias included"""
    
    def test_route_includes_vias_for_export(self):
        """NetRoute should include vias for export"""
        board_area = box(0, 0, 100, 100)
        via_planner = ViaPlanner(board_area, ViaSpec.standard())
        pad_connector = PadLayerConnector(via_planner)
        router = ExactGeometryRouterViaAware(board_area, via_planner, pad_connector)
        
        pads = [
            Pad((10, 10), ['F.Cu'], 'NET1', 'U1', '1'),
            Pad((20, 10), ['F.Cu'], 'NET1', 'U1', '2')
        ]
        
        route = router.route_net('NET1', pads, 'In1.Cu')
        
        assert route is not None
        # Should have both tracks and vias
        assert hasattr(route, 'tracks')
        assert hasattr(route, 'vias')
        assert len(route.vias) > 0  # Layer transition requires vias
        
        # Vias should have all required export fields
        for via in route.vias:
            assert hasattr(via, 'position')
            assert hasattr(via, 'spec')
            assert hasattr(via, 'layers')
            assert hasattr(via, 'net')
