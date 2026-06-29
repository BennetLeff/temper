"""
Tests for Router V6 Stage 3.3: Add Connectivity Constraints

Part of temper-v02b
"""


from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.connectivity_constraints import (
    ConnectivityConstraint,
    add_connectivity_constraints,
)
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo


def _create_test_pcb() -> ParsedPCB:
    """Create a test PCB with various nets."""
    comp1_pins = [
        Pin("1", "1", (0, 0), "GND", 1.0, 1.0, "circle", "F.Cu"),
        Pin("2", "2", (2, 0), "VCC", 1.0, 1.0, "circle", "F.Cu"),
        Pin("3", "3", (4, 0), "SIG_1", 1.0, 1.0, "circle", "F.Cu"),
        Pin("4", "4", (6, 0), "NC", 1.0, 1.0, "circle", "F.Cu"),
    ]
    comp1 = Component("U1", "IC", (10, 10), comp1_pins)

    comp2_pins = [
        Pin("1", "1", (0, 0), "GND", 1.0, 1.0, "circle", "F.Cu"),
        Pin("2", "2", (2, 0), "SIG_1", 1.0, 1.0, "circle", "F.Cu"),
    ]
    comp2 = Component("U2", "IC", (10, 10), comp2_pins)

    nets = {
        "GND": Net("GND", "power"),
        "VCC": Net("VCC", "power"),
        "SIG_1": Net("SIG_1", "signal"),
        "NC": Net("NC", "signal"),
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


def test_add_connectivity_constraints_basic():
    """Test basic connectivity constraint generation."""
    pcb = _create_test_pcb()
    constraints = add_connectivity_constraints(pcb)

    assert len(constraints.constraints) == 4
    assert constraints.routable_net_count > 0


def test_constraint_routable_detection():
    """Test that constraints correctly identify routable nets."""
    pcb = _create_test_pcb()
    constraints = add_connectivity_constraints(pcb)

    # GND has 2 pins, should be routable
    gnd_constraint = next(c for c in constraints.constraints if c.net_name == "GND")
    assert gnd_constraint.is_routable
    assert gnd_constraint.pin_count == 2

    # NC has 1 pin, should not be routable
    nc_constraint = next(c for c in constraints.constraints if c.net_name == "NC")
    assert not nc_constraint.is_routable
    assert nc_constraint.pin_count == 1


def test_connectivity_constraints_statistics():
    """Test constraint collection statistics."""
    pcb = _create_test_pcb()
    constraints = add_connectivity_constraints(pcb)

    # Total pins: comp1 (4) + comp2 (2) = 6
    assert constraints.total_pin_count == 6

    # Routable nets: GND, SIG_1 (both have >1 pin)
    assert constraints.routable_net_count == 2


def test_connectivity_constraint_dataclass():
    """Test ConnectivityConstraint dataclass."""
    constraint = ConnectivityConstraint(
        net_name="TEST_NET",
        pin_count=5,
        requires_routing=True,
    )

    assert constraint.is_routable
    assert constraint.net_name == "TEST_NET"
    assert constraint.pin_count == 5


def test_connectivity_empty_pcb():
    """Test connectivity constraints with empty PCB."""
    pcb = ParsedPCB(
        components=[],
        nets={},
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )

    constraints = add_connectivity_constraints(pcb)

    assert len(constraints.constraints) == 0
    assert constraints.routable_net_count == 0
    assert constraints.total_pin_count == 0
