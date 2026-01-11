"""
Tests for Router V6 Stage 2.2: Compute Routing Space

Part of temper-643u
"""

import pytest
from shapely.geometry import box

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.routing_space import RoutingSpace, compute_routing_space
from temper_placer.router_v6.stage0_data import LayerInfo, ParsedPCB, StackupInfo


def _create_test_pcb() -> ParsedPCB:
    """Create a minimal test PCB."""
    # Create a simple component with a few pins
    pins = [
        Pin(
            name="1",
            number="1",
            position=(5.0, 5.0),
            net="GND",
            width=1.0,
            height=1.0,
            shape="rect",
            layer="F.Cu",
        ),
        Pin(
            name="2",
            number="2",
            position=(10.0, 5.0),
            net="VCC",
            width=1.0,
            height=1.0,
            shape="rect",
            layer="F.Cu",
        ),
    ]

    comp = Component(
        ref="U1",
        footprint="SOIC-8",
        bounds=(15.0, 10.0),
        pins=pins,
        initial_position=(50.0, 50.0),
    )

    # Create stackup with 2 signal layers
    stackup = StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35),
            LayerInfo(index=3, name="B.Cu", layer_type="signal", thickness_um=35),
        ]
    )

    # Create mock board geometry
    class MockBoardGeometry:
        def __init__(self):
            self.bounds = (0, 0, 100, 100)
            self.width = 100
            self.height = 100

    pcb = ParsedPCB(
        components=[comp],
        nets={},
        design_rules=None,
        stackup=stackup,
        zones=[],
    )
    pcb.board_geometry = MockBoardGeometry()

    return pcb


def test_compute_routing_space_basic():
    """Test basic routing space computation."""
    pcb = _create_test_pcb()
    routing_space = compute_routing_space(pcb)

    assert "F.Cu" in routing_space
    assert "B.Cu" in routing_space

    # Board area should be 100x100 = 10000 mm²
    assert routing_space["F.Cu"].total_area == pytest.approx(10000, abs=1)


def test_routing_space_has_obstacles():
    """Test that routing space accounts for obstacles."""
    pcb = _create_test_pcb()
    routing_space = compute_routing_space(pcb)

    # F.Cu has component pads, so obstacle area > 0
    assert routing_space["F.Cu"].obstacle_area > 0

    # Routing area should be less than total area
    assert routing_space["F.Cu"].routing_area < routing_space["F.Cu"].total_area


def test_routing_space_available_ratio():
    """Test available ratio calculation."""
    pcb = _create_test_pcb()
    routing_space = compute_routing_space(pcb)

    # Most of the board should be available (>90%)
    assert routing_space["F.Cu"].available_ratio > 0.9

    # Utilization should be small (<10%)
    assert routing_space["F.Cu"].utilization_ratio < 0.1


def test_routing_space_dataclass_properties():
    """Test RoutingSpace dataclass properties."""
    from shapely.geometry import MultiPolygon, Polygon

    space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 90, 90)]),
        total_area=100 * 100,
        obstacle_area=1000,
        routing_area=9000,
    )

    assert space.utilization_ratio == pytest.approx(0.1, abs=0.01)
    assert space.available_ratio == pytest.approx(0.9, abs=0.01)


def test_routing_space_with_escape_vias():
    """Test routing space with escape vias as additional obstacles."""
    pcb = _create_test_pcb()

    # Create simple escape via mock
    class MockVia:
        def __init__(self):
            self.position = (20.0, 20.0)
            self.diameter = 0.5

    vias = [MockVia()]

    routing_space = compute_routing_space(pcb, escape_vias=vias)

    # Should still compute successfully
    assert "F.Cu" in routing_space
    assert routing_space["F.Cu"].total_area > 0


def test_routing_space_empty_board():
    """Test routing space computation with minimal board."""
    stackup = StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35),
        ]
    )

    pcb = ParsedPCB(
        components=[],
        nets={},
        design_rules=None,
        stackup=stackup,
        zones=[],
    )

    class MockBoardGeometry:
        def __init__(self):
            self.bounds = (0, 0, 50, 50)

    pcb.board_geometry = MockBoardGeometry()

    routing_space = compute_routing_space(pcb)

    # Empty board should have full routing area available
    assert routing_space["F.Cu"].available_ratio == pytest.approx(1.0, abs=0.01)
    assert routing_space["F.Cu"].obstacle_area == pytest.approx(0.0, abs=0.1)
