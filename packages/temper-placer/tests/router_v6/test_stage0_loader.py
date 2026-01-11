"""
Tests for Router V6 Stage 0.1: Load KiCad PCB File

Part of temper-y7j2
"""

from pathlib import Path

import pytest

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6


def test_parse_kicad_pcb_v6_basic():
    """Test basic PCB loading and validation."""
    # This will be run against actual test PCB files
    pass


def test_parsed_pcb_validation():
    """Test ParsedPCB validation checks."""
    from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules, StackupInfo, NetClassRules, LayerInfo
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Pin

    # Create a valid PCB
    component = Component(
        ref="U1",
        footprint="QFN-48",
        bounds=(7.0, 7.0),
        pins=[
            Pin(name="1", number="1", position=(0, 0), net="GND", width=0.25, height=0.25, shape="rect", layer="F.Cu")
        ],
        initial_position=(50.0, 50.0),
    )

    valid_pcb = ParsedPCB(
        components=[component],
        nets=[Net(name="GND", pins=[("U1", "1")])],
        zones=[],
        board=Board(width=100, height=100, origin=(0, 0)),
        design_rules=DesignRules(
            net_classes={"Signal": NetClassRules(
                name="Signal",
                clearance_mm=0.2,
                trace_width_mm=0.25,
                via_diameter_mm=0.8,
                via_drill_mm=0.4,
            )},
            net_class_assignments={},
            default_clearance_mm=0.2,
            default_trace_width_mm=0.25,
            default_via_diameter_mm=0.8,
            default_via_drill_mm=0.4,
        ),
        stackup=StackupInfo(
            layers=[
                LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35.0),
                LayerInfo(index=1, name="B.Cu", layer_type="signal", thickness_um=35.0),
            ],
            total_thickness_mm=0.8,
            layer_count=2,
        ),
        source_path=Path("/tmp/test.kicad_pcb"),
    )

    # Should pass validation
    errors = valid_pcb.validate_placement()
    assert len(errors) == 0, f"Valid PCB should have no errors, got: {errors}"


def test_parsed_pcb_validation_failures():
    """Test that validation catches invalid PCBs."""
    from temper_placer.router_v6.stage0_data import ParsedPCB, DesignRules, StackupInfo, NetClassRules, LayerInfo
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component

    # PCB with no components
    empty_pcb = ParsedPCB(
        components=[],
        nets=[],
        zones=[],
        board=Board(width=100, height=100, origin=(0, 0)),
        design_rules=DesignRules(
            net_classes={},
            net_class_assignments={},
            default_clearance_mm=0.2,
            default_trace_width_mm=0.25,
            default_via_diameter_mm=0.8,
            default_via_drill_mm=0.4,
        ),
        stackup=StackupInfo(layers=[], total_thickness_mm=0, layer_count=0),
        source_path=Path("/tmp/empty.kicad_pcb"),
    )

    errors = empty_pcb.validate_placement()
    assert len(errors) > 0, "Empty PCB should fail validation"
    assert any("No components" in e for e in errors)
    assert any("No layers" in e for e in errors)


def test_stackup_helper_methods():
    """Test StackupInfo helper methods."""
    from temper_placer.router_v6.stage0_data import StackupInfo, LayerInfo

    # 4-layer board with planes
    stackup = StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35.0),
            LayerInfo(index=1, name="In1.Cu", layer_type="plane", thickness_um=35.0, plane_net="GND"),
            LayerInfo(index=2, name="In2.Cu", layer_type="plane", thickness_um=35.0, plane_net="+15V"),
            LayerInfo(index=3, name="B.Cu", layer_type="signal", thickness_um=35.0),
        ],
        total_thickness_mm=1.6,
        layer_count=4,
    )

    # Test signal_layers
    assert stackup.signal_layers == [0, 3], "Should identify outer signal layers"

    # Test plane_layers
    planes = stackup.plane_layers
    assert planes == {1: "GND", 2: "+15V"}, "Should identify plane layers with nets"

    # Test get_reference_plane
    ref_plane = stackup.get_reference_plane(0)  # For F.Cu, nearest plane should be In1.Cu (index 1)
    assert ref_plane == 1, "Should return nearest plane layer"


def test_design_rules_get_rules_for_net():
    """Test DesignRules.get_rules_for_net method."""
    from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

    rules = DesignRules(
        net_classes={
            "Signal": NetClassRules(
                name="Signal",
                clearance_mm=0.2,
                trace_width_mm=0.25,
                via_diameter_mm=0.8,
                via_drill_mm=0.4,
            ),
            "Power": NetClassRules(
                name="Power",
                clearance_mm=0.3,
                trace_width_mm=1.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
            ),
        },
        net_class_assignments={"GND": "Power", "3V3": "Signal"},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.25,
        default_via_diameter_mm=0.8,
        default_via_drill_mm=0.4,
    )

    # Test assigned net
    gnd_rules = rules.get_rules_for_net("GND")
    assert gnd_rules.name == "Power"
    assert gnd_rules.trace_width_mm == 1.0

    # Test unassigned net (should get default class rules)
    unknown_rules = rules.get_rules_for_net("UNKNOWN_NET")
    assert unknown_rules.name == "Default"
    assert unknown_rules.clearance_mm == 0.2  # Default values
