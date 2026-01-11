
import pytest
from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.router_v6.escape_drc_validator import validate_escape_plan

@pytest.fixture
def mock_design_rules():
    default_rules = NetClassRules(
        name="Default",
        clearance_mm=0.2,
        trace_width_mm=0.1,
        via_diameter_mm=0.4,
        via_drill_mm=0.2
    )
    return DesignRules(
        net_classes={"Default": default_rules},
        net_class_assignments={},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.1,
        default_via_diameter_mm=0.4,
        default_via_drill_mm=0.2,
        min_hole_to_hole_mm=0.25,
        min_annular_ring_mm=0.1
    )

def test_annular_ring_violation(mock_design_rules):
    # Via diameter 0.4, drill 0.3 -> ring = 0.05. Min ring is 0.1.
    via = EscapeVia(
        position=(10, 10),
        net_name="NET1",
        pin_number="1",
        diameter=0.4,
        drill=0.3,
        via_type="dog-bone"
    )
    violations = validate_escape_plan([via], [], mock_design_rules)
    assert len(violations) == 1
    assert violations[0].violation_type == "annular"

def test_via_via_clearance_violation(mock_design_rules):
    # Two vias on different nets.
    # Diameter 0.4 -> radius 0.2.
    # Clearance 0.2.
    # Required dist: 0.2 + 0.2 + 0.2 = 0.6.
    # Dist at (10, 10) and (10.5, 10) is 0.5.
    v1 = EscapeVia(
        position=(10, 10),
        net_name="NET1",
        pin_number="1",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    v2 = EscapeVia(
        position=(10.5, 10),
        net_name="NET2",
        pin_number="2",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    violations = validate_escape_plan([v1, v2], [], mock_design_rules)
    assert any(v.violation_type == "via-via" for v in violations)

def test_hole_to_hole_violation(mock_design_rules):
    # Two vias. Same net (so clearance ignored), but hole-to-hole matters.
    # Drill 0.2 -> radius 0.1.
    # Min hole-to-hole 0.25.
    # Required dist: 0.1 + 0.1 + 0.25 = 0.45.
    # Dist 0.4 -> violation.
    v1 = EscapeVia(
        position=(10, 10),
        net_name="GND",
        pin_number="1",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    v2 = EscapeVia(
        position=(10.4, 10),
        net_name="GND",
        pin_number="2",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    violations = validate_escape_plan([v1, v2], [], mock_design_rules)
    assert any(v.violation_type == "hole-to-hole" for v in violations)

def test_via_pad_clearance_violation(mock_design_rules):
    # Via on NET1. Pad on NET2.
    # Via radius 0.2. Pad width 0.4 -> radius 0.2.
    # Clearance 0.2.
    # Required dist: 0.6.
    # Dist 0.5 -> violation.
    via = EscapeVia(
        position=(10.5, 10),
        net_name="NET1",
        pin_number="1",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    comp = Component(
        ref="U1",
        footprint="FP",
        bounds=(1, 1),
        pins=[Pin(name="2", number="2", position=(0, 0), net="NET2", width=0.4, height=0.4)],
        initial_position=(10, 10)
    )
    violations = validate_escape_plan([via], [comp], mock_design_rules)
    assert any(v.violation_type == "via-pad" for v in violations)

def test_clean_plan(mock_design_rules):
    # Dist 1.0. All good.
    v1 = EscapeVia(
        position=(10, 10),
        net_name="NET1",
        pin_number="1",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    v2 = EscapeVia(
        position=(11, 10),
        net_name="NET2",
        pin_number="2",
        diameter=0.4,
        drill=0.2,
        via_type="dog-bone"
    )
    violations = validate_escape_plan([v1, v2], [], mock_design_rules)
    assert len(violations) == 0
