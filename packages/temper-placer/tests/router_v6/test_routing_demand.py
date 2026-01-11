"""
Tests for Router V6 Stage 2.7: Estimate Routing Demand

Part of temper-eccz
"""

import pytest

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.routing_demand import RoutingDemand, estimate_routing_demand
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo


def _create_test_pcb() -> ParsedPCB:
    """Create a test PCB with some nets."""
    # Create components with pins
    comp1_pins = [
        Pin("1", "1", (0, 0), "GND", 1.0, 1.0, "circle", "F.Cu"),
        Pin("2", "2", (2, 0), "VCC", 1.0, 1.0, "circle", "F.Cu"),
        Pin("3", "3", (4, 0), "SIG_1", 1.0, 1.0, "circle", "F.Cu"),
    ]
    comp1 = Component("U1", "IC", (10, 10), comp1_pins)

    comp2_pins = [
        Pin("1", "1", (0, 0), "GND", 1.0, 1.0, "circle", "F.Cu"),
        Pin("2", "2", (2, 0), "SIG_1", 1.0, 1.0, "circle", "F.Cu"),
        Pin("3", "3", (4, 0), "SIG_2", 1.0, 1.0, "circle", "F.Cu"),
    ]
    comp2 = Component("U2", "IC", (10, 10), comp2_pins)

    nets = {
        "GND": Net("GND", "power"),
        "VCC": Net("VCC", "power"),
        "SIG_1": Net("SIG_1", "signal"),
        "SIG_2": Net("SIG_2", "signal"),
    }

    return ParsedPCB(
        components=[comp1, comp2],
        nets=nets,
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )


def test_estimate_demand_basic():
    """Test basic demand estimation."""
    pcb = _create_test_pcb()
    demand = estimate_routing_demand(pcb)

    assert demand.total_nets == 4
    assert demand.total_pins == 6
    assert demand.routable_nets > 0  # GND and SIG_1 have >1 pin


def test_demand_net_classification():
    """Test net classification."""
    pcb = _create_test_pcb()
    demand = estimate_routing_demand(pcb)

    # Should classify some power and signal nets
    assert demand.power_nets > 0  # GND, VCC
    assert demand.signal_nets > 0  # SIG_1, SIG_2


def test_demand_statistics():
    """Test demand statistics."""
    pcb = _create_test_pcb()
    demand = estimate_routing_demand(pcb)

    assert demand.avg_pins_per_net >= 0.0
    assert demand.max_pins_per_net > 0


def test_demand_complexity_score():
    """Test routing complexity score."""
    pcb = _create_test_pcb()
    demand = estimate_routing_demand(pcb)

    # Complexity should be between 0 and 1
    assert 0.0 <= demand.routing_complexity <= 1.0


def test_demand_dataclass():
    """Test RoutingDemand dataclass."""
    demand = RoutingDemand(
        total_nets=100,
        routable_nets=80,
        total_pins=500,
        signal_nets=70,
        power_nets=10,
        diff_pair_nets=5,
        avg_pins_per_net=5.0,
        max_pins_per_net=20,
    )

    assert demand.routing_complexity > 0.0


def test_demand_empty_pcb():
    """Test demand with minimal PCB."""
    pcb = ParsedPCB(
        components=[],
        nets={},
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )

    demand = estimate_routing_demand(pcb)

    assert demand.total_nets == 0
    assert demand.routable_nets == 0
    assert demand.routing_complexity == 0.0
