"""
Tests for Router V6 Stage 3.6: Add Reference Plane Constraints

Part of temper-blqt
"""


from temper_placer.core.netlist import Net
from temper_placer.router_v6.reference_plane_constraints import (
    ReferencePlaneConstraint,
    add_reference_plane_constraints,
)
from temper_placer.router_v6.stage0_data import LayerInfo, ParsedPCB, StackupInfo


def _create_pcb_with_planes() -> ParsedPCB:
    """Create test PCB with plane layers."""
    stackup = StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35),
            LayerInfo(index=1, name="In1.Cu", layer_type="plane", thickness_um=35, plane_net="GND"),
            LayerInfo(index=2, name="In2.Cu", layer_type="plane", thickness_um=35, plane_net="VCC"),
            LayerInfo(index=3, name="B.Cu", layer_type="signal", thickness_um=35),
        ],
        total_thickness_mm=1.6,
        layer_count=4,
    )

    nets = {
        "GND": Net("GND", "power"),
        "VCC": Net("VCC", "power"),
        "USB_DP": Net("USB_DP", "signal"),
        "CLK": Net("CLK", "signal"),
        "SIG1": Net("SIG1", "signal"),
    }

    pcb = ParsedPCB(
        components=[],
        nets=nets,
        design_rules=None,
        stackup=stackup,
        zones=[],
        board=None,
        source_path=None,
    )

    return pcb


def test_add_reference_plane_constraints_basic():
    """Test basic reference plane constraint generation."""
    pcb = _create_pcb_with_planes()
    constraints = add_reference_plane_constraints(pcb)

    # Should have constraints for signal nets (not power/ground)
    assert constraints.constraint_count > 0


def test_power_ground_nets_excluded():
    """Test that power and ground nets don't get plane constraints."""
    pcb = _create_pcb_with_planes()
    constraints = add_reference_plane_constraints(pcb)

    # No constraints for GND or VCC themselves
    gnd_constraints = constraints.get_constraints_for_net("GND")
    vcc_constraints = constraints.get_constraints_for_net("VCC")

    assert len(gnd_constraints) == 0
    assert len(vcc_constraints) == 0


def test_signal_nets_get_constraints():
    """Test that signal nets get plane constraints."""
    pcb = _create_pcb_with_planes()
    constraints = add_reference_plane_constraints(pcb)

    # Signal nets should have constraints
    usb_constraints = constraints.get_constraints_for_net("USB_DP")
    clk_constraints = constraints.get_constraints_for_net("CLK")

    assert len(usb_constraints) > 0
    assert len(clk_constraints) > 0


def test_high_speed_signals_use_gnd():
    """Test that high-speed signals reference GND plane."""
    pcb = _create_pcb_with_planes()
    constraints = add_reference_plane_constraints(pcb)

    usb_constraints = constraints.get_constraints_for_net("USB_DP")

    # USB should reference GND
    for constraint in usb_constraints:
        assert constraint.required_plane == "GND"


def test_plane_type_classification():
    """Test plane type classification."""
    gnd_constraint = ReferencePlaneConstraint(
        signal_net="SIG1",
        required_plane="GND",
        layer_name="F.Cu",
        is_mandatory=True,
    )

    vcc_constraint = ReferencePlaneConstraint(
        signal_net="SIG2",
        required_plane="VCC",
        layer_name="F.Cu",
        is_mandatory=True,
    )

    assert gnd_constraint.plane_type == "ground"
    assert vcc_constraint.plane_type == "power"


def test_constraint_dataclass():
    """Test ReferencePlaneConstraint dataclass."""
    constraint = ReferencePlaneConstraint(
        signal_net="TEST_NET",
        required_plane="GND",
        layer_name="F.Cu",
        is_mandatory=True,
    )

    assert constraint.signal_net == "TEST_NET"
    assert constraint.required_plane == "GND"
    assert constraint.is_mandatory is True
    assert constraint.plane_type == "ground"


def test_no_stackup():
    """Test constraints with PCB having no stackup."""
    pcb = ParsedPCB(
        components=[],
        nets={"SIG1": Net("SIG1", "signal")},
        design_rules=None,
        stackup=None,
        zones=[],
        board=None,
        source_path=None,
    )

    constraints = add_reference_plane_constraints(pcb)

    assert constraints.constraint_count == 0
