"""Tests for traced routing functions."""

import pytest
from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.routing.traced_routing import (
    route_net_with_trace,
    route_all_with_trace,
    analyze_route_path,
    explain_layer_assignment,
    explain_via,
)
from temper_placer.explainability.trace import Trace


class TestExplanationGeneration:
    """Tests for explanation generation functions."""
    
    def test_explain_layer_assignment_hv(self):
        """GIVEN HV net class
        WHEN explaining layer assignment
        THEN mentions 2oz copper"""
        explanation = explain_layer_assignment("HighVoltage", [0])
        
        assert "HV" in explanation
        assert "2oz copper" in explanation
    
    def test_explain_layer_assignment_power(self):
        """GIVEN Power net class
        WHEN explaining layer assignment
        THEN lists signal layers"""
        explanation = explain_layer_assignment("Power", [0, 3])
        
        assert "Power" in explanation
        assert "signal layers" in explanation
    
    def test_explain_via(self):
        """GIVEN via from L1 to L2
        WHEN explaining
        THEN shows layer transition"""
        explanation = explain_via(0, 1, "obstacle")
        
        assert "L1" in explanation
        assert "L2" in explanation
        assert "obstacle" in explanation


class TestRouteNetWithTrace:
    """Tests for route_net_with_trace function."""
    
    def test_simple_route_returns_trace(self):
        """GIVEN simple routing scenario
        WHEN routing with trace
        THEN returns path and trace"""
        router = MazeRouter(grid_size=(100, 100))
        
        path, trace = route_net_with_trace(
            router, "VCC", (10, 10), (20, 20)
        )
        
        assert path is not None
        assert isinstance(trace, Trace)
        assert len(trace) > 0
    
    def test_route_with_layer_change(self):
        """GIVEN routing with layer change allowed
        WHEN routing
        THEN trace includes layer assignment"""
        router = MazeRouter(grid_size=(100, 100), num_layers=2)
        
        path, trace = route_net_with_trace(
            router, "VCC", (10, 10), (20, 20),
            allow_layer_change=True,
            net_class="Power"
        )
        
        # Should have layer assignment entry
        assert len(trace) > 0
        # Check for layer assignment explanation
        explanation = trace.why("VCC")
        assert "VCC" in explanation
    
    def test_route_failure_traced(self):
        """GIVEN blocked path
        WHEN routing fails
        THEN trace explains failure"""
        router = MazeRouter(grid_size=(20, 20))
        
        # Block entire path
        router.block_rect(5, 0, 10, 20, layer=0)
        
        path, trace = route_net_with_trace(
            router, "BLOCKED", (0, 10), (19, 10)
        )
        
        assert path is None
        assert len(trace) > 0
        explanation = trace.why("BLOCKED")
        assert "Failed" in explanation or "BLOCKED" in explanation
    
    def test_via_placement_traced(self):
        """GIVEN route requiring via
        WHEN routing with layer change
        THEN trace includes via decisions"""
        router = MazeRouter(grid_size=(50, 50), num_layers=2, via_cost=0.5)
        
        # Block path on layer 0 to force via
        router.block_rect(20, 0, 5, 50, layer=0)
        
        path, trace = route_net_with_trace(
            router, "NET1", (10, 25), (40, 25),
            allow_layer_change=True
        )
        
        if path and any(path[i].layer != path[i+1].layer for i in range(len(path)-1)):
            # Via was used
            explanation = trace.why("NET1")
            assert "Via" in explanation or "NET1" in explanation


class TestRouteAllWithTrace:
    """Tests for route_all_with_trace function."""
    
    def test_route_multiple_nets(self):
        """GIVEN multiple nets to route
        WHEN routing all
        THEN returns routes and combined trace"""
        router = MazeRouter(grid_size=(100, 100))
        
        net_routes = [
            ("VCC", (10, 10), (20, 20)),
            ("GND", (30, 30), (40, 40)),
            ("SIG1", (50, 50), (60, 60)),
        ]
        
        routes, trace = route_all_with_trace(router, net_routes)
        
        assert len(routes) == 3
        assert all(net in routes for net, _, _ in net_routes)
        assert isinstance(trace, Trace)
    
    def test_combined_trace_has_all_nets(self):
        """GIVEN multiple nets
        WHEN routing all
        THEN combined trace has entries for all nets"""
        router = MazeRouter(grid_size=(100, 100))
        
        net_routes = [
            ("VCC", (10, 10), (20, 20)),
            ("GND", (30, 30), (40, 40)),
        ]
        
        routes, trace = route_all_with_trace(router, net_routes)
        
        # Should be able to query each net
        vcc_explanation = trace.why("VCC")
        gnd_explanation = trace.why("GND")
        
        assert "VCC" in vcc_explanation
        assert "GND" in gnd_explanation
    
    def test_trace_composition(self):
        """GIVEN multiple nets
        WHEN routing all
        THEN traces compose via monoid operation"""
        router = MazeRouter(grid_size=(100, 100))
        
        net_routes = [
            ("NET1", (10, 10), (20, 20)),
            ("NET2", (30, 30), (40, 40)),
            ("NET3", (50, 50), (60, 60)),
        ]
        
        routes, trace = route_all_with_trace(router, net_routes)
        
        # Trace should have entries from all nets
        assert len(trace) >= 3  # At least one entry per net


class TestAnalyzeRoutePath:
    """Tests for analyze_route_path function."""
    
    def test_analyze_simple_path(self):
        """GIVEN simple path without vias
        WHEN analyzing
        THEN trace shows path length"""
        path = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),
            GridCell(2, 0, 0),
        ]
        
        trace = analyze_route_path(path, "NET1")
        
        assert len(trace) > 0
        explanation = trace.why("NET1")
        assert "NET1" in explanation
        assert "3" in explanation  # Path length
    
    def test_analyze_path_with_vias(self):
        """GIVEN path with layer transitions
        WHEN analyzing
        THEN trace shows via count"""
        path = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),
            GridCell(1, 0, 1),  # Via!
            GridCell(2, 0, 1),
        ]
        
        trace = analyze_route_path(path, "NET1")
        
        explanation = trace.why("NET1")
        assert "via" in explanation.lower()
    
    def test_analyze_path_multiple_vias(self):
        """GIVEN path with multiple vias
        WHEN analyzing
        THEN trace shows correct via count"""
        path = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 1),  # Via 1
            GridCell(2, 0, 1),
            GridCell(2, 0, 0),  # Via 2
            GridCell(3, 0, 0),
        ]
        
        trace = analyze_route_path(path, "NET1")
        
        explanation = trace.why("NET1")
        assert "2" in explanation  # 2 vias


class TestIntegration:
    """Integration tests showing full workflow."""
    
    def test_full_routing_workflow(self):
        """GIVEN board with components
        WHEN routing nets with trace
        THEN can query routing decisions"""
        # Create router
        router = MazeRouter(grid_size=(100, 100), num_layers=2)
        
        # Block some components
        router.block_rect(20, 20, 10, 10, layer=0)
        router.block_rect(60, 60, 10, 10, layer=0)
        
        # Route nets
        net_routes = [
            ("VCC", (10, 10), (90, 90)),
            ("GND", (15, 15), (85, 85)),
        ]
        
        routes, trace = route_all_with_trace(
            router, net_routes,
            allow_layer_change=True
        )
        
        # Verify routing succeeded
        assert routes["VCC"] is not None
        assert routes["GND"] is not None
        
        # Query trace
        vcc_explanation = trace.why("VCC")
        gnd_explanation = trace.why("GND")
        
        assert "VCC" in vcc_explanation
        assert "GND" in gnd_explanation
