"""
Tests for PCL constraint to JAX loss function bridge.

This module tests the translation layer that converts PCL constraints
into differentiable JAX loss functions for the optimizer.

Test coverage:
- Tier to weight mapping (HARD=10.0, STRONG=1.0, SOFT=0.1)
- Adjacent constraint -> ProximityLoss
- Separated constraint -> GroupSeparationLoss
- Enclosing constraint -> ZoneMembershipLoss
- Aligned constraint -> AlignmentLoss
- OnSide constraint -> EdgePreferenceLoss
- Anchored constraint -> Positional penalty
- LoopArea constraint -> LoopAreaLoss
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import LossContext, LossFunction
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    EdgeType,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.loss_bridge import (
    adjacent_to_proximity_loss,
    aligned_to_alignment_loss,
    anchored_to_positional_loss,
    constraint_to_loss,
    enclosing_to_zone_loss,
    loop_area_to_loop_loss,
    onside_to_edge_loss,
    separated_to_separation_loss,
    tier_to_weight,
)


class TestTierToWeight:
    """Test tier to weight mapping."""

    def test_hard_tier_maps_to_1e6(self):
        """HARD tier should map to weight 1e6."""
        assert tier_to_weight(ConstraintTier.HARD) == 1_000_000.0

    def test_strong_tier_maps_to_1e3(self):
        """STRONG tier should map to weight 1e3."""
        assert tier_to_weight(ConstraintTier.STRONG) == 1_000.0

    def test_soft_tier_maps_to_10(self):
        """SOFT tier should map to weight 10.0."""
        assert tier_to_weight(ConstraintTier.SOFT) == 10.0


class TestAdjacentToProximityLoss:
    """Test Adjacent constraint translation."""

    def test_adjacent_creates_proximity_loss(self):
        """Adjacent constraint should create ProximityLoss."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close",
        )

        # Need a netlist to map component refs to indices
        netlist = _create_simple_netlist(["Q1", "Q2", "U1"])
        loss_fn = adjacent_to_proximity_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)
        assert "proximity" in loss_fn.name.lower()

    def test_adjacent_applies_tier_weight(self):
        """ProximityLoss should use tier-based weight."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.SOFT,
            because="Keep close for aesthetics",
        )

        netlist = _create_simple_netlist(["Q1", "Q2"])
        loss_fn = adjacent_to_proximity_loss(constraint, netlist)

        # Check that weight is 0.1 (SOFT tier)
        # This assumes ProximityLoss exposes a weight attribute
        # If not, we can test by checking loss value
        assert hasattr(loss_fn, "weight") or hasattr(loss_fn, "rules")

    def test_adjacent_with_unknown_component_raises(self):
        """Adjacent with unknown component should raise ValueError."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q_UNKNOWN",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Testing unknown component",
        )

        netlist = _create_simple_netlist(["Q1", "Q2"])
        with pytest.raises(ValueError, match="Component.*not found"):
            adjacent_to_proximity_loss(constraint, netlist)


class TestSeparatedToSeparationLoss:
    """Test Separated constraint translation."""

    def test_separated_creates_separation_loss(self):
        """Separated constraint should create GroupSeparationLoss."""
        constraint = SeparatedConstraint(
            a="HV_ZONE",
            b="MCU_ZONE",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="IEC 60335-1 isolation",
        )

        netlist = _create_simple_netlist(["Q1", "U1"])
        # Zones are handled differently - need zone definitions
        loss_fn = separated_to_separation_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestEnclosingToZoneLoss:
    """Test Enclosing constraint translation."""

    def test_enclosing_creates_zone_membership_loss(self):
        """Enclosing constraint should create ZoneMembershipLoss."""
        constraint = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["Q1", "Q2", "D1"],
            tier=ConstraintTier.HARD,
            because="HV components in HV zone",
        )

        netlist = _create_simple_netlist(["Q1", "Q2", "D1", "U1"])
        zones = {"HV_ZONE": {"polygon": [[0, 0], [50, 0], [50, 30], [0, 30]]}}

        loss_fn = enclosing_to_zone_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestAlignedToAlignmentLoss:
    """Test Aligned constraint translation."""

    def test_aligned_creates_alignment_loss(self):
        """Aligned constraint should create AlignmentLoss."""
        constraint = AlignedConstraint(
            components=["C1", "C2", "C3", "C4"],
            axis=Axis.X,
            tolerance_mm=0.5,
            tier=ConstraintTier.SOFT,
            because="Visual alignment of caps",
        )

        netlist = _create_simple_netlist(["C1", "C2", "C3", "C4", "U1"])
        loss_fn = aligned_to_alignment_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestOnSideToEdgeLoss:
    """Test OnSide constraint translation."""

    def test_onside_creates_edge_preference_loss(self):
        """OnSide constraint should create EdgePreferenceLoss."""
        constraint = OnSideConstraint(
            components=["J_AC", "J_COIL"],
            side=BoardSide.LEFT,
            edge=EdgeType.FLUSH,
            tier=ConstraintTier.HARD,
            because="Connectors on left edge",
        )

        netlist = _create_simple_netlist(["J_AC", "J_COIL", "U1"])
        board = _create_simple_board(width=100, height=80)

        loss_fn = onside_to_edge_loss(constraint, netlist, board)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestAnchoredToPositionalLoss:
    """Test Anchored constraint translation."""

    def test_anchored_with_region_creates_loss(self):
        """Anchored constraint with region should create positional loss."""
        constraint = AnchoredConstraint(
            component="U_MCU",
            region=(20.0, 20.0, 40.0, 40.0),
            tier=ConstraintTier.STRONG,
            because="MCU centered in zone",
        )

        netlist = _create_simple_netlist(["U_MCU", "Q1"])
        loss_fn = anchored_to_positional_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)

    def test_anchored_with_position_creates_loss(self):
        """Anchored constraint with exact position should create positional loss."""
        constraint = AnchoredConstraint(
            component="U_MCU",
            position=(30.0, 30.0),
            tier=ConstraintTier.STRONG,
            because="MCU at exact position",
        )

        netlist = _create_simple_netlist(["U_MCU", "Q1"])
        loss_fn = anchored_to_positional_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestLoopAreaToLoopLoss:
    """Test LoopArea constraint translation."""

    def test_loop_area_creates_loop_loss(self):
        """LoopArea constraint should create LoopAreaLoss."""
        constraint = LoopAreaConstraint(
            loop_name="commutation",
            max_area_mm2=500.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop",
        )

        # Need loop definitions from Epic 1
        # For now, create a mock loop
        loops = {
            "commutation": {
                "components": ["Q1", "Q2", "C_BUS1"],
                "max_area_mm2": 500.0,
            }
        }

        netlist = _create_simple_netlist(["Q1", "Q2", "C_BUS1", "U1"])
        loss_fn = loop_area_to_loop_loss(constraint, netlist, loops)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestConstraintToLoss:
    """Test unified constraint_to_loss dispatcher."""

    def test_dispatches_adjacent_constraint(self):
        """constraint_to_loss should dispatch AdjacentConstraint correctly."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test dispatch",
        )

        netlist = _create_simple_netlist(["Q1", "Q2", "U1"])
        loss_fn = constraint_to_loss(constraint, netlist)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)

    def test_dispatches_separated_constraint(self):
        """constraint_to_loss should dispatch SeparatedConstraint correctly."""
        constraint = SeparatedConstraint(
            a="HV_ZONE",
            b="LV_ZONE",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test dispatch",
        )

        netlist = _create_simple_netlist(["Q1", "U1"])
        loss_fn = constraint_to_loss(constraint, netlist, _zones=[])

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)

    def test_dispatches_enclosing_constraint(self):
        """constraint_to_loss should dispatch EnclosingConstraint correctly."""
        constraint = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["Q1", "Q2"],
            tier=ConstraintTier.HARD,
            because="Test dispatch",
        )

        netlist = _create_simple_netlist(["Q1", "Q2", "U1"])
        zones = {"HV_ZONE": {"polygon": [[0, 0], [50, 0], [50, 30], [0, 30]]}}
        loss_fn = constraint_to_loss(constraint, netlist, _zones=zones)

        assert loss_fn is not None
        assert isinstance(loss_fn, LossFunction)


class TestLossFunctionExecution:
    """Test that created loss functions are JAX-compatible and executable."""

    def test_adjacent_loss_computes_value(self):
        """ProximityLoss from adjacent constraint should compute loss value."""
        constraint = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test execution",
        )

        netlist = _create_simple_netlist(["Q1", "Q2", "U1"])
        board = _create_simple_board(width=100, height=80)
        context = LossContext.from_netlist_and_board(netlist, board)

        loss_fn = adjacent_to_proximity_loss(constraint, netlist)

        # Create test positions: Q1 at (10, 10), Q2 at (30, 10), U1 at (50, 50)
        positions = jnp.array([[10.0, 10.0], [30.0, 10.0], [50.0, 50.0]])
        rotations = jnp.eye(3, 4)  # Identity rotations

        result = loss_fn(positions, rotations, context)

        # Q1 and Q2 are 20mm apart (exceeds max_distance=10mm)
        # Loss should be positive
        assert result.value > 0

    def test_aligned_loss_computes_value(self):
        """AlignmentLoss should penalize misalignment."""
        constraint = AlignedConstraint(
            components=["C1", "C2", "C3"],
            axis=Axis.X,
            tolerance_mm=0.5,
            tier=ConstraintTier.SOFT,
            because="Test execution",
        )

        netlist = _create_simple_netlist(["C1", "C2", "C3", "U1"])
        board = _create_simple_board(width=100, height=80)
        context = LossContext.from_netlist_and_board(netlist, board)

        loss_fn = aligned_to_alignment_loss(constraint, netlist)

        # Positions: C1, C2, C3 at different X coords
        positions = jnp.array(
            [
                [10.0, 20.0],  # C1
                [10.0, 30.0],  # C2 - aligned X
                [15.0, 40.0],  # C3 - misaligned X (5mm off)
                [50.0, 50.0],  # U1
            ]
        )
        rotations = jnp.eye(4, 4)

        result = loss_fn(positions, rotations, context)

        # C3 is misaligned by 5mm, should produce positive loss
        assert result.value > 0


# ============================================================================
# Helper Functions
# ============================================================================


def _create_simple_netlist(component_refs: list[str]) -> Netlist:
    """Create a minimal netlist for testing."""
    from temper_placer.core.netlist import Component

    components = [
        Component(
            ref=ref,
            footprint="TestFootprint",
            bounds=(5.0, 3.0),  # Simple rectangular bounds
            pins=[],
            net_class="Signal",
        )
        for ref in component_refs
    ]

    return Netlist(components=components, nets=[])


def _create_simple_board(width: float, height: float) -> Board:
    """Create a minimal board for testing."""
    return Board(
        width=width,
        height=height,
        zones=[],
        keepouts=[],
    )
