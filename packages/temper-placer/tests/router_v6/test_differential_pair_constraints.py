"""
Tests for Router V6 Stage 3.4: Add Differential Pair Constraints

Part of temper-42yx
"""


from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.differential_pair_constraints import (
    DifferentialPairConstraint,
    add_differential_pair_constraints,
)
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo


def _create_pcb_with_diff_pairs() -> ParsedPCB:
    """Create test PCB with differential pairs."""
    pcb = ParsedPCB(
        components=[],
        nets={},
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )

    # Add differential pairs
    pcb.differential_pairs = [
        DiffPair(base_name="USB_D", p_net="USB_DP", n_net="USB_DN"),
        DiffPair(base_name="PCIE_TX0", p_net="PCIE_TX0_P", n_net="PCIE_TX0_N"),
    ]

    return pcb


def test_add_differential_pair_constraints_basic():
    """Test basic differential pair constraint generation."""
    pcb = _create_pcb_with_diff_pairs()
    constraints = add_differential_pair_constraints(pcb)

    assert constraints.pair_count == 2
    assert len(constraints.constraints) == 2


def test_constraint_net_names():
    """Test constraint net name property."""
    pcb = _create_pcb_with_diff_pairs()
    constraints = add_differential_pair_constraints(pcb)

    usb_constraint = constraints.constraints[0]
    assert usb_constraint.net_names == ("USB_DP", "USB_DN")


def test_impedance_inference():
    """Test impedance inference from net names."""
    pcb = _create_pcb_with_diff_pairs()
    constraints = add_differential_pair_constraints(pcb)

    # USB should be 90 ohms
    usb_constraint = next(c for c in constraints.constraints if "USB" in c.positive_net)
    assert usb_constraint.target_impedance == 90.0

    # PCIe should be 100 ohms
    pcie_constraint = next(c for c in constraints.constraints if "PCIE" in c.positive_net)
    assert pcie_constraint.target_impedance == 100.0


def test_constraint_defaults():
    """Test default constraint parameters."""
    pcb = _create_pcb_with_diff_pairs()
    constraints = add_differential_pair_constraints(pcb)

    for constraint in constraints.constraints:
        assert constraint.max_length_mismatch == 0.5
        assert constraint.min_coupling_ratio == 0.7


def test_custom_defaults():
    """Test custom default parameters."""
    pcb = _create_pcb_with_diff_pairs()
    constraints = add_differential_pair_constraints(
        pcb,
        default_max_mismatch=1.0,
        default_min_coupling=0.8,
    )

    for constraint in constraints.constraints:
        assert constraint.max_length_mismatch == 1.0
        assert constraint.min_coupling_ratio == 0.8


def test_differential_pair_constraint_dataclass():
    """Test DifferentialPairConstraint dataclass."""
    constraint = DifferentialPairConstraint(
        positive_net="SIG_P",
        negative_net="SIG_N",
        target_impedance=100.0,
        max_length_mismatch=0.5,
        min_coupling_ratio=0.75,
    )

    assert constraint.net_names == ("SIG_P", "SIG_N")
    assert constraint.target_impedance == 100.0


def test_no_differential_pairs():
    """Test constraints with PCB having no differential pairs."""
    pcb = ParsedPCB(
        components=[],
        nets={},
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        zones=[],
        board=None,
        source_path=None,
    )

    constraints = add_differential_pair_constraints(pcb)

    assert constraints.pair_count == 0
    assert len(constraints.constraints) == 0


# ---------------------------------------------------------------------------
# route_diff_pair (U5) tests
# ---------------------------------------------------------------------------


def test_route_diff_pair_usb_defaults():
    """USB pair gets JLC04161H-7628 defaults from diff_impedance module."""
    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu")
    assert spec["pair"] == ("USB_D+", "USB_D-")
    geom = spec["geometry"]
    assert geom.target_impedance == 90.0
    assert geom.layer == "F.Cu"
    assert geom.reference_plane == "In1.Cu"
    assert geom.track_width_mm > 0
    assert geom.track_spacing_mm > 0
    assert geom.predicted_impedance > 0


def test_route_diff_pair_length_matching():
    """Length-matching skew tolerance is 0.5mm."""
    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu")
    assert spec["length_matching"]["max_skew_mm"] == 0.5
    assert spec["length_matching"]["tolerance"] == "skew"


def test_route_diff_pair_hv_keepaway():
    """HV keep-away is 3mm from ACMains/HighVoltage/HighCurrent."""
    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu")
    ka = spec["keepaway"]
    assert ka["distance_mm"] == 3.0
    assert "ACMains" in ka["from_classes"]
    assert "HighVoltage" in ka["from_classes"]
    assert "HighCurrent" in ka["from_classes"]
    assert ka["layer"] == "F.Cu"


def test_route_diff_pair_custom_skew():
    """Custom max_skew_mm is honoured."""
    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu", max_skew_mm=0.25)
    assert spec["length_matching"]["max_skew_mm"] == 0.25


def test_route_diff_pair_custom_keepaway():
    """Custom hv_keepaway_mm is honoured."""
    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    spec = route_diff_pair("USB_D+", "USB_D-", "F.Cu", hv_keepaway_mm=5.0)
    assert spec["keepaway"]["distance_mm"] == 5.0


def test_route_diff_pair_explicit_geometry():
    """Explicit geometry is passed through."""
    from temper_placer.router_v6.differential_pair_constraints import (
        DifferentialPairGeometry,
        route_diff_pair,
    )

    geom = DifferentialPairGeometry(
        track_width_mm=0.4,
        track_spacing_mm=0.25,
        target_impedance=85.0,
        layer="F.Cu",
        reference_plane="In1.Cu",
        predicted_impedance=84.5,
    )
    spec = route_diff_pair("NET_P", "NET_N", "F.Cu", geometry=geom)
    assert spec["geometry"].track_width_mm == 0.4
    assert spec["geometry"].target_impedance == 85.0


def test_route_diff_pair_no_usb_no_geometry_raises():
    """Non-USB nets without geometry raise ValueError."""
    import pytest

    from temper_placer.router_v6.differential_pair_constraints import route_diff_pair

    with pytest.raises(ValueError, match="No geometry provided"):
        route_diff_pair("CLK_P", "CLK_N", "F.Cu")
