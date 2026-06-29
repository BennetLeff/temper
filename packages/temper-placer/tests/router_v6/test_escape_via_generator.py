
import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


@pytest.fixture
def mock_design_rules():
    default_rules = NetClassRules(
        name="Default",
        clearance_mm=0.1,
        trace_width_mm=0.1,
        via_diameter_mm=0.3,
        via_drill_mm=0.15
    )
    return DesignRules(
        net_classes={"Default": default_rules},
        net_class_assignments={},
        default_clearance_mm=0.1,
        default_trace_width_mm=0.1,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15
    )

@pytest.fixture
def simple_bga_component():
    # 2x2 BGA at 0,0 with 1.0mm pitch
    pins = []
    # Pin 1: (-0.5, -0.5)
    pins.append(Pin(name="1", number="1", position=(-0.5, -0.5), net="NET1", width=0.4, height=0.4))
    # Pin 2: (0.5, -0.5)
    pins.append(Pin(name="2", number="2", position=(0.5, -0.5), net="NET2", width=0.4, height=0.4))
    # Pin 3: (-0.5, 0.5)
    pins.append(Pin(name="3", number="3", position=(-0.5, 0.5), net="NET3", width=0.4, height=0.4))
    # Pin 4: (0.5, 0.5)
    pins.append(Pin(name="4", number="4", position=(0.5, 0.5), net="NET4", width=0.4, height=0.4))

    comp = Component(
        ref="U1",
        footprint="BGA-4_1.0mm",
        bounds=(2.0, 2.0),
        pins=pins,
        initial_position=(10.0, 10.0), # Placed at 10,10
        initial_rotation=0
    )

    return DensePackage(
        component=comp,
        pin_count=4,
        pitch_mm=1.0,
        package_type="BGA",
        requires_escape=True
    )

def test_via_in_pad(simple_bga_component, mock_design_rules):
    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy="via-in-pad")

    assert len(vias) == 4
    for via in vias:
        assert via.via_type == "via-in-pad"
        # Check positions match pins + component offset
        # Pin 1 at (-0.5, -0.5) -> (9.5, 9.5)
        if via.pin_number == "1":
            assert via.position == pytest.approx((9.5, 9.5))

def test_dog_bone_bga(simple_bga_component, mock_design_rules):
    # Pitch 1.0mm. Half pitch 0.5mm.
    # Pin 1 at (-0.5, -0.5).
    # Candidates relative to pin: (+0.5, +0.5), etc.
    # (+0.5, +0.5) -> (0, 0) relative to center -> (10, 10) absolute.
    # (10,10) is the center of the 2x2 grid.
    # Distance to Pin 1 center (-0.5, -0.5) is sqrt(0.5^2 + 0.5^2) = 0.707mm.
    # Required clearance: ViaRadius(0.15) + PinRadius(0.2) + Clearance(0.1) = 0.45mm.
    # 0.707 > 0.45, so it's valid.

    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy="dog-bone")

    assert len(vias) == 4

    # Check Pin 1
    via1 = next(v for v in vias if v.pin_number == "1")
    # It should pick one of the valid diagonals.
    # Ideally (10.0, 10.0) is a great spot (center of component).
    # Let's see if (10.0, 10.0) is returned.
    # Pin 1 abs pos: (9.5, 9.5).
    # Offset (+0.5, +0.5) -> (10.0, 10.0).
    # Check collisions for (10.0, 10.0):
    # Dist to Pin 1: 0.707
    # Dist to Pin 2 (10.5, 9.5): 0.5. 0.5 > 0.45. Valid.
    # Dist to Pin 3 (9.5, 10.5): 0.5. Valid.
    # Dist to Pin 4 (10.5, 10.5): 0.707. Valid.

    # Wait, Dist to Pin 2 from (10, 10) is sqrt(0.5^2 + 0.5^2) = 0.707?
    # Pin 2 at (0.5, -0.5) -> (10.5, 9.5).
    # Via at (0, 0) -> (10.0, 10.0).
    # Diff: (0.5, -0.5). Dist: sqrt(0.5) = 0.707.
    # Yes, it's equidistant.

    # Use approx for position check
    assert via1.position == pytest.approx((10.0, 10.0))

def test_rotation(simple_bga_component, mock_design_rules):
    # Rotate 90 degrees (index 1)
    simple_bga_component.component.initial_rotation = 1
    # Pin 1 (-0.5, -0.5) rotates to (0.5, -0.5).
    # Abs pos: (10.5, 9.5).

    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy="via-in-pad")
    via1 = next(v for v in vias if v.pin_number == "1")
    assert via1.position == pytest.approx((10.5, 9.5))
