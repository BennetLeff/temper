"""
Tests for PCL constraint data structures.

Tests cover:
- Enum definitions and values
- BaseConstraint validation
- All constraint type creation and validation
- ID generation
- Component involvement checking
- Dictionary serialization
- Error handling for invalid inputs
"""

import pytest
from temper_placer.pcl import (
    BaseConstraint,
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
    AlignedConstraint,
    OnSideConstraint,
    AnchoredConstraint,
    LoopAreaConstraint,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    Axis,
    BoardSide,
    EdgeType,
)


# ============================================================================
# Enum Tests
# ============================================================================


def test_constraint_tier_values():
    """Test ConstraintTier enum has expected values."""
    assert ConstraintTier.HARD.value == 1
    assert ConstraintTier.STRONG.value == 2
    assert ConstraintTier.SOFT.value == 3


def test_constraint_type_values():
    """Test ConstraintType enum has expected values."""
    assert ConstraintType.ADJACENT.value == "adjacent"
    assert ConstraintType.SEPARATED.value == "separated"
    assert ConstraintType.ENCLOSING.value == "enclosing"
    assert ConstraintType.ALIGNED.value == "aligned"
    assert ConstraintType.ON_SIDE.value == "on_side"
    assert ConstraintType.ANCHORED.value == "anchored"
    assert ConstraintType.LOOP_AREA.value == "loop_area"


def test_distance_metric_values():
    """Test DistanceMetric enum has expected values."""
    assert DistanceMetric.EDGE_TO_EDGE.value == "edge_to_edge"
    assert DistanceMetric.CENTER_TO_CENTER.value == "center_to_center"
    assert DistanceMetric.PIN_TO_PIN.value == "pin_to_pin"


def test_axis_values():
    """Test Axis enum has expected values."""
    assert Axis.X.value == "x"
    assert Axis.Y.value == "y"
    assert Axis.MAJOR.value == "major"
    assert Axis.MINOR.value == "minor"


def test_board_side_values():
    """Test BoardSide enum has expected values."""
    assert BoardSide.TOP.value == "top"
    assert BoardSide.BOTTOM.value == "bottom"
    assert BoardSide.LEFT.value == "left"
    assert BoardSide.RIGHT.value == "right"


def test_edge_type_values():
    """Test EdgeType enum has expected values."""
    assert EdgeType.FLUSH.value == "flush"
    assert EdgeType.NEAR.value == "near"
    assert EdgeType.OVERHANG.value == "overhang"


# ============================================================================
# AdjacentConstraint Tests
# ============================================================================


def test_adjacent_constraint_creation():
    """Test creating an adjacent constraint with default values."""
    constraint = AdjacentConstraint(
        a="Q1",
        b="Q2",
        max_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Minimize commutation loop area",
    )

    assert constraint.a == "Q1"
    assert constraint.b == "Q2"
    assert constraint.max_distance_mm == 10.0
    assert constraint.tier == ConstraintTier.HARD
    assert constraint.because == "Minimize commutation loop area"
    assert constraint.metric == DistanceMetric.EDGE_TO_EDGE  # Default
    assert constraint.pin_a is None
    assert constraint.pin_b is None
    assert constraint.id == "adj_Q1_Q2"  # Auto-generated


def test_adjacent_constraint_with_pins():
    """Test adjacent constraint with specific pin references."""
    constraint = AdjacentConstraint(
        a="U1",
        b="Q1",
        max_distance_mm=15.0,
        tier=ConstraintTier.STRONG,
        because="Minimize gate drive loop inductance",
        metric=DistanceMetric.PIN_TO_PIN,
        pin_a="OUT",
        pin_b="GATE",
    )

    assert constraint.metric == DistanceMetric.PIN_TO_PIN
    assert constraint.pin_a == "OUT"
    assert constraint.pin_b == "GATE"


def test_adjacent_constraint_custom_id():
    """Test adjacent constraint with custom ID."""
    constraint = AdjacentConstraint(
        a="Q1",
        b="Q2",
        max_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Minimize commutation loop area",
        id="custom_half_bridge",
    )

    assert constraint.id == "custom_half_bridge"


def test_adjacent_constraint_involves_component():
    """Test checking if constraint involves a component."""
    constraint = AdjacentConstraint(
        a="Q1",
        b="Q2",
        max_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Minimize commutation loop area",
    )

    assert constraint.involves_component("Q1")
    assert constraint.involves_component("Q2")
    assert not constraint.involves_component("Q3")


def test_adjacent_constraint_to_dict():
    """Test serializing adjacent constraint to dictionary."""
    constraint = AdjacentConstraint(
        a="Q1",
        b="Q2",
        max_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Minimize commutation loop area",
        metric=DistanceMetric.CENTER_TO_CENTER,
        pin_a="DRAIN",
        pin_b="SOURCE",
    )

    d = constraint.to_dict()
    assert d["type"] == "adjacent"
    assert d["a"] == "Q1"
    assert d["b"] == "Q2"
    assert d["max_distance_mm"] == 10.0
    assert d["metric"] == "center_to_center"
    assert d["tier"] == 1
    assert d["because"] == "Minimize commutation loop area"
    assert d["pin_a"] == "DRAIN"
    assert d["pin_b"] == "SOURCE"
    assert "id" in d


def test_adjacent_constraint_short_rationale():
    """Test that short rationale raises error."""
    with pytest.raises(ValueError, match="must be ≥10 chars"):
        AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Too short",  # Only 9 chars
        )


# ============================================================================
# SeparatedConstraint Tests
# ============================================================================


def test_separated_constraint_creation():
    """Test creating a separated constraint."""
    constraint = SeparatedConstraint(
        a="HV_ZONE",
        b="MCU_ZONE",
        min_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="IEC 60335-1 reinforced isolation requirement",
    )

    assert constraint.a == "HV_ZONE"
    assert constraint.b == "MCU_ZONE"
    assert constraint.min_distance_mm == 10.0
    assert constraint.tier == ConstraintTier.HARD
    assert constraint.metric == DistanceMetric.EDGE_TO_EDGE
    assert constraint.id == "sep_HV_ZONE_MCU_ZONE"


def test_separated_constraint_involves_component():
    """Test checking component involvement in separated constraint."""
    constraint = SeparatedConstraint(
        a="HV_ZONE",
        b="LV_ZONE",
        min_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Safety isolation requirement",
    )

    assert constraint.involves_component("HV_ZONE")
    assert constraint.involves_component("LV_ZONE")
    assert not constraint.involves_component("MCU_ZONE")


def test_separated_constraint_to_dict():
    """Test serializing separated constraint to dictionary."""
    constraint = SeparatedConstraint(
        a="HV_ZONE",
        b="MCU_ZONE",
        min_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Safety isolation requirement",
    )

    d = constraint.to_dict()
    assert d["type"] == "separated"
    assert d["a"] == "HV_ZONE"
    assert d["b"] == "MCU_ZONE"
    assert d["min_distance_mm"] == 10.0
    assert d["tier"] == 1


# ============================================================================
# EnclosingConstraint Tests
# ============================================================================


def test_enclosing_constraint_creation():
    """Test creating an enclosing constraint."""
    constraint = EnclosingConstraint(
        outer="HV_ZONE",
        inner=["Q1", "Q2", "D1", "C_DC"],
        tier=ConstraintTier.HARD,
        because="All high voltage components must stay in HV safety zone",
    )

    assert constraint.outer == "HV_ZONE"
    assert constraint.inner == ["Q1", "Q2", "D1", "C_DC"]
    assert constraint.margin_mm == 0.0  # Default
    assert constraint.id == "enc_HV_ZONE"


def test_enclosing_constraint_with_margin():
    """Test enclosing constraint with margin."""
    constraint = EnclosingConstraint(
        outer="THERMAL_ZONE",
        inner=["Q1", "Q2"],
        tier=ConstraintTier.STRONG,
        because="Keep IGBTs in thermal zone with 2mm clearance",
        margin_mm=2.0,
    )

    assert constraint.margin_mm == 2.0


def test_enclosing_constraint_involves_component():
    """Test checking component involvement in enclosing constraint."""
    constraint = EnclosingConstraint(
        outer="HV_ZONE",
        inner=["Q1", "Q2", "D1"],
        tier=ConstraintTier.HARD,
        because="HV components in zone",
    )

    assert constraint.involves_component("HV_ZONE")
    assert constraint.involves_component("Q1")
    assert constraint.involves_component("Q2")
    assert constraint.involves_component("D1")
    assert not constraint.involves_component("U1")


def test_enclosing_constraint_to_dict():
    """Test serializing enclosing constraint to dictionary."""
    constraint = EnclosingConstraint(
        outer="HV_ZONE",
        inner=["Q1", "Q2"],
        tier=ConstraintTier.HARD,
        because="HV components in zone",
        margin_mm=1.5,
    )

    d = constraint.to_dict()
    assert d["type"] == "enclosing"
    assert d["outer"] == "HV_ZONE"
    assert d["inner"] == ["Q1", "Q2"]
    assert d["margin_mm"] == 1.5


# ============================================================================
# AlignedConstraint Tests
# ============================================================================


def test_aligned_constraint_creation():
    """Test creating an aligned constraint."""
    constraint = AlignedConstraint(
        components=["C1", "C2", "C3", "C4"],
        axis=Axis.X,
        tier=ConstraintTier.SOFT,
        because="Align decoupling capacitors for visual consistency",
    )

    assert constraint.components == ["C1", "C2", "C3", "C4"]
    assert constraint.axis == Axis.X
    assert constraint.tolerance_mm == 0.5  # Default
    assert constraint.id == "align_x_C1_C2_C3"


def test_aligned_constraint_with_tolerance():
    """Test aligned constraint with custom tolerance."""
    constraint = AlignedConstraint(
        components=["U1", "U2", "U3"],
        axis=Axis.Y,
        tier=ConstraintTier.SOFT,
        because="Align ICs for routing simplification",
        tolerance_mm=1.0,
    )

    assert constraint.tolerance_mm == 1.0


def test_aligned_constraint_requires_multiple_components():
    """Test that aligned constraint requires at least 2 components."""
    with pytest.raises(ValueError, match="at least 2 components"):
        AlignedConstraint(
            components=["C1"],  # Only 1 component
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because="Need multiple components",
        )


def test_aligned_constraint_involves_component():
    """Test checking component involvement in aligned constraint."""
    constraint = AlignedConstraint(
        components=["C1", "C2", "C3"],
        axis=Axis.X,
        tier=ConstraintTier.SOFT,
        because="Align capacitors",
    )

    assert constraint.involves_component("C1")
    assert constraint.involves_component("C2")
    assert constraint.involves_component("C3")
    assert not constraint.involves_component("C4")


def test_aligned_constraint_to_dict():
    """Test serializing aligned constraint to dictionary."""
    constraint = AlignedConstraint(
        components=["C1", "C2", "C3"],
        axis=Axis.Y,
        tier=ConstraintTier.SOFT,
        because="Align capacitors",
        tolerance_mm=0.8,
    )

    d = constraint.to_dict()
    assert d["type"] == "aligned"
    assert d["components"] == ["C1", "C2", "C3"]
    assert d["axis"] == "y"
    assert d["tolerance_mm"] == 0.8


# ============================================================================
# OnSideConstraint Tests
# ============================================================================


def test_on_side_constraint_creation():
    """Test creating an on-side constraint."""
    constraint = OnSideConstraint(
        components=["J1", "J2"],
        side=BoardSide.LEFT,
        edge=EdgeType.FLUSH,
        tier=ConstraintTier.HARD,
        because="Connectors must be on left edge for external access",
    )

    assert constraint.components == ["J1", "J2"]
    assert constraint.side == BoardSide.LEFT
    assert constraint.edge == EdgeType.FLUSH
    assert constraint.max_distance_mm == 5.0  # Default
    assert constraint.id == "side_left_J1_J2"


def test_on_side_constraint_near_edge():
    """Test on-side constraint with NEAR edge type."""
    constraint = OnSideConstraint(
        components=["Q1", "Q2"],
        side=BoardSide.BOTTOM,
        edge=EdgeType.NEAR,
        tier=ConstraintTier.STRONG,
        because="IGBTs near bottom edge for thermal management",
        max_distance_mm=10.0,
    )

    assert constraint.edge == EdgeType.NEAR
    assert constraint.max_distance_mm == 10.0


def test_on_side_constraint_involves_component():
    """Test checking component involvement in on-side constraint."""
    constraint = OnSideConstraint(
        components=["J1", "J2"],
        side=BoardSide.LEFT,
        edge=EdgeType.FLUSH,
        tier=ConstraintTier.HARD,
        because="Connectors on edge",
    )

    assert constraint.involves_component("J1")
    assert constraint.involves_component("J2")
    assert not constraint.involves_component("J3")


def test_on_side_constraint_to_dict():
    """Test serializing on-side constraint to dictionary."""
    constraint = OnSideConstraint(
        components=["J1", "J2"],
        side=BoardSide.RIGHT,
        edge=EdgeType.OVERHANG,
        tier=ConstraintTier.HARD,
        because="USB connectors on right edge",
        max_distance_mm=3.0,
    )

    d = constraint.to_dict()
    assert d["type"] == "on_side"
    assert d["components"] == ["J1", "J2"]
    assert d["side"] == "right"
    assert d["edge"] == "overhang"
    assert d["max_distance_mm"] == 3.0


# ============================================================================
# AnchoredConstraint Tests
# ============================================================================


def test_anchored_constraint_with_region():
    """Test creating an anchored constraint with region."""
    constraint = AnchoredConstraint(
        component="J_AC_IN",
        region=(0, 0, 10, 10),
        tier=ConstraintTier.HARD,
        because="AC inlet connector mechanically fixed by enclosure",
    )

    assert constraint.component == "J_AC_IN"
    assert constraint.region == (0, 0, 10, 10)
    assert constraint.position is None
    assert constraint.id == "anchor_J_AC_IN"


def test_anchored_constraint_with_position():
    """Test creating an anchored constraint with exact position."""
    constraint = AnchoredConstraint(
        component="DISPLAY",
        position=(50.0, 50.0),
        tier=ConstraintTier.HARD,
        because="Display must be centered for UI requirements",
    )

    assert constraint.component == "DISPLAY"
    assert constraint.position == (50.0, 50.0)
    assert constraint.region is None


def test_anchored_constraint_requires_region_or_position():
    """Test that anchored constraint requires either region or position."""
    with pytest.raises(ValueError, match="requires either region or position"):
        AnchoredConstraint(component="J1", tier=ConstraintTier.HARD, because="Mechanically fixed")


def test_anchored_constraint_cannot_have_both():
    """Test that anchored constraint cannot have both region and position."""
    with pytest.raises(ValueError, match="cannot have both"):
        AnchoredConstraint(
            component="J1",
            region=(0, 0, 10, 10),
            position=(5, 5),
            tier=ConstraintTier.HARD,
            because="Mechanically fixed",
        )


def test_anchored_constraint_involves_component():
    """Test checking component involvement in anchored constraint."""
    constraint = AnchoredConstraint(
        component="J1",
        region=(0, 0, 10, 10),
        tier=ConstraintTier.HARD,
        because="Mechanically fixed",
    )

    assert constraint.involves_component("J1")
    assert not constraint.involves_component("J2")


def test_anchored_constraint_to_dict_with_region():
    """Test serializing anchored constraint with region to dictionary."""
    constraint = AnchoredConstraint(
        component="J1",
        region=(0, 0, 10, 10),
        tier=ConstraintTier.HARD,
        because="Mechanically fixed",
    )

    d = constraint.to_dict()
    assert d["type"] == "anchored"
    assert d["component"] == "J1"
    assert d["region"] == (0, 0, 10, 10)
    assert "position" not in d


def test_anchored_constraint_to_dict_with_position():
    """Test serializing anchored constraint with position to dictionary."""
    constraint = AnchoredConstraint(
        component="DISPLAY",
        position=(50.0, 50.0),
        tier=ConstraintTier.HARD,
        because="Centered for UI",
    )

    d = constraint.to_dict()
    assert d["type"] == "anchored"
    assert d["component"] == "DISPLAY"
    assert d["position"] == (50.0, 50.0)
    assert "region" not in d


# ============================================================================
# LoopAreaConstraint Tests
# ============================================================================


def test_loop_area_constraint_creation():
    """Test creating a loop area constraint."""
    constraint = LoopAreaConstraint(
        loop_name="commutation",
        max_area_mm2=500.0,
        tier=ConstraintTier.STRONG,
        because="Minimize commutation loop to reduce voltage overshoot",
    )

    assert constraint.loop_name == "commutation"
    assert constraint.max_area_mm2 == 500.0
    assert constraint.tier == ConstraintTier.STRONG
    assert constraint.id == "loop_commutation"


def test_loop_area_constraint_involves_component():
    """Test that loop area constraints don't involve components directly."""
    constraint = LoopAreaConstraint(
        loop_name="gate_drive_high",
        max_area_mm2=50.0,
        tier=ConstraintTier.STRONG,
        because="Minimize gate loop inductance",
    )

    # Loop constraints don't directly involve components
    assert not constraint.involves_component("Q1")
    assert not constraint.involves_component("U1")


def test_loop_area_constraint_to_dict():
    """Test serializing loop area constraint to dictionary."""
    constraint = LoopAreaConstraint(
        loop_name="bootstrap",
        max_area_mm2=25.0,
        tier=ConstraintTier.STRONG,
        because="Minimize bootstrap loop for charge efficiency",
    )

    d = constraint.to_dict()
    assert d["type"] == "loop_area"
    assert d["loop_name"] == "bootstrap"
    assert d["max_area_mm2"] == 25.0
    assert d["tier"] == 2
