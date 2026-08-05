import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


@pytest.fixture
def mock_design_rules():
    default_rules = NetClassRules(
        name="Default", clearance_mm=0.1, trace_width_mm=0.1, via_diameter_mm=0.3, via_drill_mm=0.15
    )
    return DesignRules(
        net_classes={"Default": default_rules},
        net_class_assignments={},
        default_clearance_mm=0.1,
        default_trace_width_mm=0.1,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
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
        initial_position=(10.0, 10.0),  # Placed at 10,10
        initial_rotation=0,
    )

    return DensePackage(
        component=comp, pin_count=4, pitch_mm=1.0, package_type="BGA", requires_escape=True
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
    # Rotate 90 degrees (index 1).
    #
    # KiCad's real footprint-child rotation is R(-theta), not R(+theta) --
    # confirmed against real kicad-cli 10.0.4 pcb drc ground truth, see
    # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
    # Sec. 2. R(-90): (x, y) -> (y, -x). Pin 1 (-0.5, -0.5) -> (-0.5, 0.5).
    # Abs pos: (10-0.5, 10+0.5) = (9.5, 10.5).
    simple_bga_component.component.initial_rotation = 1

    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy="via-in-pad")
    via1 = next(v for v in vias if v.pin_number == "1")
    assert via1.position == pytest.approx((9.5, 10.5))


# ---------------------------------------------------------------------------
# Issue #752 defect 3: escape via layer must follow the component's side
#
# `generate_escape_vias` read `getattr(component, "side", 0) or 0`, but
# `Component` has no `side` attribute -- the contract field is `initial_side`
# (`core/netlist.py`, and `core/pin_geometry.py` reads it correctly). The
# `getattr` default therefore fired unconditionally and every escape via was
# labelled "F.Cu". The trap: a bottom-side component's pad coordinates ARE
# mirrored (pin_world_position honours initial_side), so the two halves of the
# same via disagreed -- mirrored geometry, front-side layer.
# ---------------------------------------------------------------------------


@pytest.fixture
def bottom_side_bga(simple_bga_component):
    simple_bga_component.component.initial_side = 1
    return simple_bga_component


def test_component_has_no_side_attribute_only_initial_side(simple_bga_component):
    """Pin the contract the buggy getattr silently defaulted around."""
    comp = simple_bga_component.component
    assert not hasattr(comp, "side")
    assert hasattr(comp, "initial_side")


@pytest.mark.parametrize("strategy", ["via-in-pad", "dog-bone"])
def test_bottom_side_component_yields_b_cu_vias(bottom_side_bga, mock_design_rules, strategy):
    vias = generate_escape_vias(bottom_side_bga, mock_design_rules, strategy=strategy)
    assert vias
    assert {v.layer for v in vias} == {"B.Cu"}


@pytest.mark.parametrize("strategy", ["via-in-pad", "dog-bone"])
def test_top_side_component_still_yields_f_cu_vias(
    simple_bga_component, mock_design_rules, strategy
):
    simple_bga_component.component.initial_side = 0
    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy=strategy)
    assert vias
    assert {v.layer for v in vias} == {"F.Cu"}


def test_unset_initial_side_defaults_to_front(simple_bga_component, mock_design_rules):
    """`initial_side=None` (the dataclass default) means front, as before."""
    simple_bga_component.component.initial_side = None
    vias = generate_escape_vias(simple_bga_component, mock_design_rules, strategy="via-in-pad")
    assert {v.layer for v in vias} == {"F.Cu"}


def test_bottom_side_via_layer_agrees_with_its_mirrored_pad(bottom_side_bga, mock_design_rules):
    """Geometry and layer must describe the same side of the board.

    Pin 1 sits at local (-0.5, -0.5); on the bottom side KiCad mirrors X, so
    its world position is (10.5, 9.5), not (9.5, 9.5). Pre-fix the position
    was already mirrored while the layer said "F.Cu".
    """
    vias = generate_escape_vias(bottom_side_bga, mock_design_rules, strategy="via-in-pad")
    via1 = next(v for v in vias if v.pin_number == "1")
    assert via1.position == pytest.approx((10.5, 9.5))
    assert via1.layer == "B.Cu"
