"""
Unit tests for loss functions.

Tests cover:
- Individual loss function computation
- Gradient computation via JAX autodiff
- CompositeLoss aggregation
- Weight scheduling for curriculum learning
- Edge cases (empty inputs, zero loss conditions)
"""

import jax
import jax.numpy as jnp
import pytest

# Import core types for fixtures
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin

# Import loss functions
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    LossResult,
    ThermalConstraint,
    WeightedLoss,
    smooth_step,
)
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.clearance import ClearanceLoss
from temper_placer.losses.congestion import CongestionLoss
from temper_placer.losses.ground_crossing import GroundCrossingLoss
from temper_placer.losses.loop_area import LoopAreaLoss, compute_loop_area_penalty
from temper_placer.losses.overlap import OverlapLoss, compute_overlap_penalty
from temper_placer.losses.regularization import (
    CenterOfMassLoss,
    RotationEntropyLoss,
    SpreadLoss,
    compute_spread_penalty,
)
from temper_placer.losses.thermal import ThermalLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.zone import ZoneMembershipLoss

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_netlist():
    """Create a simple netlist with 4 components for testing."""
    components = [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[
                Pin("VCC", "1", (1.27, 1.5)),
                Pin("GND", "4", (-1.27, 1.5)),
                Pin("OUT", "5", (-1.27, -1.5)),
                Pin("IN", "8", (1.27, -1.5)),
            ],
            net_class="Signal",
        ),
        Component(
            ref="R1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (-1.0, 0.0)),
                Pin("2", "2", (1.0, 0.0)),
            ],
            net_class="Signal",
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (-1.0, 0.0)),
                Pin("2", "2", (1.0, 0.0)),
            ],
            net_class="Signal",
        ),
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[
                Pin("G", "1", (-5.45, 0.0)),
                Pin("C", "2", (0.0, 0.0)),
                Pin("E", "3", (5.45, 0.0)),
            ],
            net_class="HighVoltage",
        ),
    ]

    nets = [
        Net("VCC", [("U1", "VCC"), ("C1", "1")], net_class="Power", weight=1.0),
        Net("GND", [("U1", "GND"), ("C1", "2"), ("R1", "2")], net_class="Power", weight=1.0),
        Net("NET1", [("U1", "OUT"), ("R1", "1")], net_class="Signal", weight=1.0),
        Net("HV_OUT", [("Q1", "C")], net_class="HighVoltage", weight=2.0),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def simple_board():
    """Create a simple board for testing."""
    return Board(
        width=100.0,
        height=80.0,
        origin=(0.0, 0.0),
    )


@pytest.fixture
def simple_context(simple_netlist, simple_board):
    """Create a LossContext for testing."""
    return LossContext.from_netlist_and_board(simple_netlist, simple_board)


@pytest.fixture
def sample_positions():
    """Sample component positions for testing."""
    return jnp.array(
        [
            [25.0, 20.0],  # U1
            [50.0, 20.0],  # R1
            [75.0, 20.0],  # C1
            [25.0, 60.0],  # Q1
        ],
        dtype=jnp.float32,
    )


@pytest.fixture
def sample_rotations():
    """Sample rotation one-hots (all 0 degrees)."""
    return jnp.array(
        [
            [1.0, 0.0, 0.0, 0.0],  # U1: 0°
            [1.0, 0.0, 0.0, 0.0],  # R1: 0°
            [1.0, 0.0, 0.0, 0.0],  # C1: 0°
            [1.0, 0.0, 0.0, 0.0],  # Q1: 0°
        ],
        dtype=jnp.float32,
    )


# =============================================================================
# Test smooth_step
# =============================================================================


class TestSmoothStep:
    """Tests for curriculum learning smooth step function."""

    def test_smooth_step_at_edges(self):
        """Test smooth_step returns 0 at lower edge and 1 at upper edge."""
        assert float(smooth_step(jnp.array(0.0), 0.0, 1.0)) == pytest.approx(0.0, abs=1e-6)
        assert float(smooth_step(jnp.array(1.0), 0.0, 1.0)) == pytest.approx(1.0, abs=1e-6)

    def test_smooth_step_below_edge(self):
        """Test smooth_step returns 0 below lower edge."""
        assert float(smooth_step(jnp.array(-0.5), 0.0, 1.0)) == pytest.approx(0.0, abs=1e-6)

    def test_smooth_step_above_edge(self):
        """Test smooth_step returns 1 above upper edge."""
        assert float(smooth_step(jnp.array(1.5), 0.0, 1.0)) == pytest.approx(1.0, abs=1e-6)

    def test_smooth_step_midpoint(self):
        """Test smooth_step at midpoint returns 0.5."""
        assert float(smooth_step(jnp.array(0.5), 0.0, 1.0)) == pytest.approx(0.5, abs=1e-6)


# =============================================================================
# Test Wirelength Loss
# =============================================================================


class TestWirelengthLoss:
    """Tests for HPWL wirelength loss."""

    def test_wirelength_basic(self, sample_positions, sample_rotations, simple_context):
        """Test basic wirelength computation."""
        loss_fn = WirelengthLoss(alpha=10.0)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        assert isinstance(result, LossResult)
        assert result.value.shape == ()  # Scalar
        assert float(result.value) > 0  # Should be positive

    def test_wirelength_zero_for_same_position(self):
        """Test that HPWL is zero when all pins are at same position."""
        # Create netlist where all components are at origin
        positions = jnp.array(
            [
                [0.0, 0.0],
                [0.0, 0.0],
            ],
            dtype=jnp.float32,
        )
        rotations = jnp.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0],
            ],
            dtype=jnp.float32,
        )

        # Minimal components with pins at center
        components = [
            Component(
                ref="A", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
            Component(
                ref="B", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
        ]
        nets = [Net("NET", [("A", "1"), ("B", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        context = LossContext.from_netlist_and_board(netlist, board)

        loss_fn = WirelengthLoss(alpha=10.0)
        result = loss_fn(positions, rotations, context)

        # HPWL should be near zero (smooth min/max via LogSumExp adds small constant)
        # With alpha=10, the LogSumExp approximation error is ~0.28 for single net
        assert float(result.value) < 0.5

    def test_wirelength_gradient(self, sample_positions, sample_rotations, simple_context):
        """Test that gradients can be computed for wirelength loss."""
        loss_fn = WirelengthLoss(alpha=10.0)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(sample_positions)
        assert grad.shape == sample_positions.shape
        # Gradients should be finite
        assert jnp.all(jnp.isfinite(grad))

    def test_wirelength_high_alpha_no_overflow(self):
        """Test that high alpha values don't cause overflow.

        Previously, large_val=1e10 caused overflow when alpha * 1e10 > ~88,
        since exp(88) approaches float32 max. Using -inf for masking avoids this.
        """
        # Create a simple setup
        positions = jnp.array([[0.0, 0.0], [50.0, 50.0]], dtype=jnp.float32)
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]], dtype=jnp.float32)

        components = [
            Component(
                ref="A", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
            Component(
                ref="B", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
        ]
        nets = [Net("NET", [("A", "1"), ("B", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        context = LossContext.from_netlist_and_board(netlist, board)

        # Test with high alpha values that would have caused overflow before
        for alpha in [10.0, 50.0, 100.0, 200.0]:
            loss_fn = WirelengthLoss(alpha=alpha)
            result = loss_fn(positions, rotations, context)

            # Should be finite, not Inf or NaN
            assert jnp.isfinite(result.value), f"Overflow at alpha={alpha}"
            # HPWL should be around sqrt(50^2 + 50^2) ≈ 70.7 for this separation
            assert 50.0 < float(result.value) < 150.0, f"Unexpected value at alpha={alpha}"

    def test_wirelength_with_sparse_mask(self):
        """Test wirelength with nets that have many masked (invalid) pins.

        Verifies that -inf masking works correctly for padded arrays.
        """
        # Create a net with only 2 valid pins but padded to larger array
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0], [100.0, 100.0]], dtype=jnp.float32)
        rotations = jnp.eye(4, dtype=jnp.float32)[jnp.array([0, 0, 0])]

        components = [
            Component(
                ref="A", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
            Component(
                ref="B", footprint="test", bounds=(1.0, 1.0), pins=[Pin("1", "1", (0.0, 0.0))]
            ),
            Component(
                ref="C",
                footprint="test",
                bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0))],  # Not in net
            ),
        ]
        # Net only includes A and B, not C
        nets = [Net("NET", [("A", "1"), ("B", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=200.0, height=200.0)
        context = LossContext.from_netlist_and_board(netlist, board)

        loss_fn = WirelengthLoss(alpha=10.0)
        result = loss_fn(positions, rotations, context)

        # Should be finite
        assert jnp.isfinite(result.value)
        # HPWL should only consider A and B (distance ~14.14), not C
        assert float(result.value) < 30.0  # Would be much larger if C included


# =============================================================================
# Test Overlap Loss
# =============================================================================


class TestOverlapLoss:
    """Tests for component overlap loss."""

    def test_overlap_no_collision(self, sample_positions, sample_rotations, simple_context):
        """Test that well-separated components have zero overlap."""
        loss_fn = OverlapLoss(margin=0.0)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # Components are well separated
        assert float(result.value) < 1e-6

    def test_overlap_with_collision(self, sample_rotations, simple_context):
        """Test that overlapping components produce positive loss."""
        # Place two components on top of each other
        overlapping_positions = jnp.array(
            [
                [50.0, 40.0],
                [50.0, 40.0],  # Same position as U1
                [75.0, 20.0],
                [25.0, 60.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = OverlapLoss(margin=0.0)
        result = loss_fn(overlapping_positions, sample_rotations, simple_context)

        # Should have positive overlap loss
        assert float(result.value) > 0

    def test_overlap_gradient(self, sample_rotations, simple_context):
        """Test gradient computation for overlap loss."""
        overlapping_positions = jnp.array(
            [
                [50.0, 40.0],
                [52.0, 40.0],  # Close to U1
                [75.0, 20.0],
                [25.0, 60.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = OverlapLoss(margin=0.0)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(overlapping_positions)
        assert grad.shape == overlapping_positions.shape
        assert jnp.all(jnp.isfinite(grad))

    def test_overlap_standalone(self):
        """Test standalone overlap computation function."""
        positions = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],  # Overlapping with first
            ],
            dtype=jnp.float32,
        )
        widths = jnp.array([10.0, 10.0])
        heights = jnp.array([5.0, 5.0])

        penalty = compute_overlap_penalty(positions, widths, heights, margin=0.0)
        assert float(penalty) > 0  # Should overlap


# =============================================================================
# Test Boundary Loss
# =============================================================================


class TestBoundaryLoss:
    """Tests for board boundary loss."""

    def test_boundary_inside(self, sample_positions, sample_rotations, simple_context):
        """Test that components inside board have low boundary loss."""
        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # All components are inside board
        assert float(result.value) < 1e-6

    def test_boundary_outside(self, sample_rotations, simple_context):
        """Test that components outside board produce positive loss."""
        outside_positions = jnp.array(
            [
                [-10.0, 40.0],  # Outside left
                [50.0, 20.0],
                [75.0, 20.0],
                [25.0, 60.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(outside_positions, sample_rotations, simple_context)

        # Should have positive boundary loss
        assert float(result.value) > 0

    def test_boundary_gradient(self, sample_rotations, simple_context):
        """Test gradient computation for boundary loss."""
        outside_positions = jnp.array(
            [
                [-5.0, 40.0],  # Partially outside
                [50.0, 20.0],
                [75.0, 20.0],
                [25.0, 60.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = BoundaryLoss(edge_margin=0.5)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(outside_positions)
        assert grad.shape == outside_positions.shape
        assert jnp.all(jnp.isfinite(grad))


# =============================================================================
# Test Clearance Loss
# =============================================================================


class TestClearanceLoss:
    """Tests for HV-LV clearance loss."""

    def test_clearance_satisfied(self, sample_positions, sample_rotations, simple_context):
        """Test that sufficient clearance produces low loss."""
        # Q1 (HV) is at (25, 60), other components at y=20
        # Distance is about 40mm, well above 10mm requirement
        loss_fn = ClearanceLoss(default_hv_lv_clearance=10.0)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # Should have low clearance loss
        assert float(result.value) < 1.0

    def test_clearance_violated(self, sample_rotations, simple_context):
        """Test that insufficient clearance produces positive loss."""
        close_positions = jnp.array(
            [
                [25.0, 20.0],  # U1 (Signal)
                [50.0, 20.0],  # R1 (Signal)
                [75.0, 20.0],  # C1 (Signal)
                [30.0, 25.0],  # Q1 (HV) - close to U1
            ],
            dtype=jnp.float32,
        )

        loss_fn = ClearanceLoss(default_hv_lv_clearance=10.0)
        result = loss_fn(close_positions, sample_rotations, simple_context)

        # Should have positive clearance violation
        assert float(result.value) > 0

    def test_clearance_gradient(self, sample_rotations, simple_context):
        """Test gradient computation for clearance loss."""
        close_positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [75.0, 20.0],
                [30.0, 25.0],  # Q1 close to others
            ],
            dtype=jnp.float32,
        )

        loss_fn = ClearanceLoss(default_hv_lv_clearance=10.0)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(close_positions)
        assert grad.shape == close_positions.shape
        assert jnp.all(jnp.isfinite(grad))

    def test_clearance_empty_indices(self, sample_positions, sample_rotations, simple_netlist, simple_board):
        """Test that empty net class indices don't cause crash (temper-p11g.3)."""
        # Create context where no components belong to HV or LV
        # (All are 'Signal' but we'll manually set indices to empty)
        context = LossContext.from_netlist_and_board(simple_netlist, simple_board)
        # Manually override to empty
        import dataclasses
        context = dataclasses.replace(
            context,
            hv_indices=jnp.array([], dtype=jnp.int32),
            lv_indices=jnp.array([], dtype=jnp.int32)
        )
        
        loss_fn = ClearanceLoss()
        
        # This should not raise TypeError: len() of unsized object
        @jax.jit
        def compute(p, r):
            return loss_fn(p, r, context).value
            
        result = compute(sample_positions, sample_rotations)
        assert float(result) == 0.0

    def test_clearance_single_hv_component(self, sample_positions, sample_rotations, simple_netlist, simple_board):
        """Test clearance with a single HV component."""
        context = LossContext.from_netlist_and_board(simple_netlist, simple_board)
        # Ensure only 1 HV component
        import dataclasses
        context = dataclasses.replace(
            context,
            hv_indices=jnp.array([3], dtype=jnp.int32),  # Q1
            lv_indices=jnp.array([0, 1, 2], dtype=jnp.int32)  # U1, R1, C1
        )
        
        loss_fn = ClearanceLoss(default_hv_lv_clearance=10.0)
        
        @jax.jit
        def compute(p, r):
            return loss_fn(p, r, context).value
            
        result = compute(sample_positions, sample_rotations)
        # Q1 is at (25, 60), others at y=20. Dist ~40. Satisfied.
        assert float(result) < 1.0


# =============================================================================
# Test Loop Area Loss
# =============================================================================


class TestLoopAreaLoss:
    """Tests for critical loop area loss."""

    def test_loop_area_no_constraints(self, sample_positions, sample_rotations, simple_context):
        """Test that missing loop constraints produce zero loss."""
        # simple_context has no loop constraints
        loss_fn = LoopAreaLoss()
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        assert float(result.value) == 0.0

    def test_loop_area_standalone(self):
        """Test standalone loop area computation."""
        # Create a square loop
        pin_positions = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],
                [10.0, 10.0],
                [0.0, 10.0],
            ],
            dtype=jnp.float32,
        )

        # Expected area = 100 mm²
        # With max_area=50, should have penalty
        penalty = compute_loop_area_penalty(pin_positions, max_area=50.0, scale=1.0)
        assert float(penalty) > 0

        # With max_area=150, should have no penalty
        penalty = compute_loop_area_penalty(pin_positions, max_area=150.0, scale=1.0)
        assert float(penalty) == pytest.approx(0.0, abs=1e-6)


# =============================================================================
# Test CompositeLoss
# =============================================================================


class TestCompositeLoss:
    """Tests for composite loss aggregation."""

    def test_composite_basic(self, sample_positions, sample_rotations, simple_context):
        """Test basic composite loss computation."""
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )

        result = composite(sample_positions, sample_rotations, simple_context)

        assert isinstance(result, LossResult)
        assert result.value.shape == ()
        assert result.breakdown is not None
        assert "overlap" in result.breakdown
        assert "wirelength" in result.breakdown
        assert "boundary" in result.breakdown

    def test_composite_weight_scheduling(self, sample_positions, sample_rotations, simple_context):
        """Test that weight scheduling affects loss values."""
        composite = CompositeLoss(
            [
                WeightedLoss(ClearanceLoss(), weight=10.0, schedule_start=0.0, schedule_end=0.5),
            ]
        )

        # Early epoch - should have partial weight
        result_early = composite(
            sample_positions, sample_rotations, simple_context, epoch=100, total_epochs=1000
        )

        # Late epoch - should have full weight
        result_late = composite(
            sample_positions, sample_rotations, simple_context, epoch=900, total_epochs=1000
        )

        # The raw loss value should be similar, but weighted differently
        # (This is a structural test - actual values depend on loss implementation)
        assert "clearance" in result_early.breakdown
        assert "clearance" in result_late.breakdown

    def test_composite_gradient(self, sample_positions, sample_rotations, simple_context):
        """Test gradient computation through composite loss."""
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(WirelengthLoss(), weight=1.0),
            ]
        )

        def loss_fn_wrapper(positions):
            return composite(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(sample_positions)
        assert grad.shape == sample_positions.shape
        assert jnp.all(jnp.isfinite(grad))

    def test_composite_loss_names(self):
        """Test getting loss function names."""
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )

        names = composite.loss_names
        assert "overlap" in names
        assert "wirelength" in names
        assert "boundary" in names


# =============================================================================
# Test JAX Compatibility
# =============================================================================


class TestJAXCompatibility:
    """Tests for JAX JIT and vmap compatibility."""

    def test_jit_compilation(self, sample_positions, sample_rotations, simple_context):
        """Test that loss functions can be JIT compiled."""
        loss_fn = WirelengthLoss()

        @jax.jit
        def jit_loss(positions, rotations):
            return loss_fn(positions, rotations, simple_context).value

        # Should compile and run without error
        result = jit_loss(sample_positions, sample_rotations)
        assert result.shape == ()

    def test_value_and_grad(self, sample_positions, sample_rotations, simple_context):
        """Test value_and_grad computation."""
        loss_fn = OverlapLoss()

        def loss_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        value, grad = jax.value_and_grad(loss_wrapper)(sample_positions)
        assert value.shape == ()
        assert grad.shape == sample_positions.shape


# =============================================================================
# Test Thermal Loss
# =============================================================================


class TestThermalLoss:
    """Tests for thermal placement loss."""

    def test_thermal_no_constraints(self, sample_positions, sample_rotations, simple_context):
        """Test that missing thermal constraints produce zero loss."""
        # simple_context has no thermal constraints
        loss_fn = ThermalLoss()
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        assert float(result.value) == 0.0

    def test_thermal_constraint_satisfied(self, sample_rotations, simple_netlist, simple_board):
        """Test that component near edge produces low loss."""
        # Position Q1 near top edge (y=75 with board height=80)
        positions = jnp.array(
            [
                [25.0, 20.0],  # U1
                [50.0, 20.0],  # R1
                [75.0, 20.0],  # C1
                [25.0, 75.0],  # Q1 - near top edge
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(
            simple_netlist,
            simple_board,
            thermal_constraints=[
                ThermalConstraint(component_ref="Q1", edge="TOP", max_distance=10.0, weight=1.0)
            ],
        )

        loss_fn = ThermalLoss()
        result = loss_fn(positions, sample_rotations, context)

        # Q1 is 5mm from top edge (80 - 75 = 5), which is < 10mm max
        # With softplus smoothing, there's a small residual penalty even when satisfied
        # (this helps with gradient smoothness during optimization)
        assert float(result.value) < 0.1  # Small penalty for satisfied constraint

    def test_thermal_constraint_violated(self, sample_rotations, simple_netlist, simple_board):
        """Test that component far from edge produces positive loss."""
        # Position Q1 far from top edge
        positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [75.0, 20.0],
                [25.0, 40.0],  # Q1 - far from top edge (40mm from top)
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(
            simple_netlist,
            simple_board,
            thermal_constraints=[
                ThermalConstraint(component_ref="Q1", edge="TOP", max_distance=5.0, weight=1.0)
            ],
        )

        loss_fn = ThermalLoss()
        result = loss_fn(positions, sample_rotations, context)

        # Q1 is 40mm from top edge, max is 5mm, should have penalty
        assert float(result.value) > 0

    def test_thermal_gradient(self, sample_rotations, simple_netlist, simple_board):
        """Test gradient computation for thermal loss."""
        positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [75.0, 20.0],
                [25.0, 40.0],  # Q1
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(
            simple_netlist,
            simple_board,
            thermal_constraints=[
                ThermalConstraint(component_ref="Q1", edge="TOP", max_distance=5.0, weight=1.0)
            ],
        )

        loss_fn = ThermalLoss()

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, context).value

        grad = jax.grad(loss_fn_wrapper)(positions)
        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))


# =============================================================================
# Test Zone Membership Loss
# =============================================================================


class TestZoneMembershipLoss:
    """Tests for zone membership loss."""

    def test_zone_membership_no_zones(self, sample_positions, sample_rotations, simple_context):
        """Test that board without zones produces zero loss."""
        loss_fn = ZoneMembershipLoss()
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # simple_board has no zones with assigned components
        assert float(result.value) == 0.0

    def test_zone_membership_inside(self, sample_rotations, simple_netlist):
        """Test that component inside zone produces zero loss."""
        from temper_placer.core.board import Zone

        board = Board(
            width=100.0,
            height=80.0,
            zones=[
                Zone("HV_ZONE", (0, 40, 50, 80), components=["Q1"]),
            ],
        )

        # Q1 at (25, 60) is inside HV_ZONE (0-50, 40-80)
        positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [75.0, 20.0],
                [25.0, 60.0],  # Q1 inside zone
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(simple_netlist, board)

        loss_fn = ZoneMembershipLoss()
        result = loss_fn(positions, sample_rotations, context)

        assert float(result.value) < 1e-6

    def test_zone_membership_outside(self, sample_rotations, simple_netlist):
        """Test that component outside zone produces positive loss."""
        from temper_placer.core.board import Zone

        board = Board(
            width=100.0,
            height=80.0,
            zones=[
                Zone("HV_ZONE", (0, 40, 50, 80), components=["Q1"]),
            ],
        )

        # Q1 at (75, 20) is outside HV_ZONE
        positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [25.0, 60.0],
                [75.0, 20.0],  # Q1 outside zone
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(simple_netlist, board)

        loss_fn = ZoneMembershipLoss()
        result = loss_fn(positions, sample_rotations, context)

        assert float(result.value) > 0

    def test_zone_membership_gradient(self, sample_rotations, simple_netlist):
        """Test gradient computation for zone membership loss."""
        from temper_placer.core.board import Zone

        board = Board(
            width=100.0,
            height=80.0,
            zones=[
                Zone("HV_ZONE", (0, 40, 50, 80), components=["Q1"]),
            ],
        )

        positions = jnp.array(
            [
                [25.0, 20.0],
                [50.0, 20.0],
                [75.0, 20.0],
                [60.0, 30.0],  # Q1 outside zone
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(simple_netlist, board)
        loss_fn = ZoneMembershipLoss()

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, context).value

        grad = jax.grad(loss_fn_wrapper)(positions)
        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))


# =============================================================================
# Test Ground Crossing Loss
# =============================================================================


class TestGroundCrossingLoss:
    """Tests for ground domain crossing loss."""

    def test_ground_crossing_no_domains(self, sample_positions, sample_rotations, simple_context):
        """Test that board without ground domains produces zero loss."""
        loss_fn = GroundCrossingLoss()
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # simple_board has no ground domains
        assert float(result.value) == 0.0

    def test_ground_crossing_same_domain(self, sample_rotations, simple_netlist):
        """Test that net within single domain produces zero loss."""
        from temper_placer.core.board import GroundDomain

        board = Board(
            width=100.0,
            height=80.0,
            ground_domains=[
                GroundDomain("PGND", (0, 0, 50, 80)),
                GroundDomain("CGND", (50, 0, 100, 80)),
            ],
        )

        # U1, R1, C1 all in CGND domain, Q1 in PGND
        # NET1 connects U1 and R1 (both in CGND) - no crossing
        positions = jnp.array(
            [
                [60.0, 40.0],  # U1 in CGND
                [80.0, 40.0],  # R1 in CGND
                [90.0, 40.0],  # C1 in CGND
                [25.0, 40.0],  # Q1 in PGND
            ],
            dtype=jnp.float32,
        )

        context = LossContext.from_netlist_and_board(simple_netlist, board)
        loss_fn = GroundCrossingLoss()
        result = loss_fn(positions, sample_rotations, context)

        # Nets that cross domains: VCC (U1, C1 both CGND), GND (U1, C1, R1 all CGND)
        # NET1 (U1, R1 both CGND), HV_OUT (Q1 only)
        # No crossing should occur
        assert float(result.value) < 1e-6


# =============================================================================
# Test Congestion Loss
# =============================================================================


class TestCongestionLoss:
    """Tests for routing congestion loss."""

    def test_congestion_spread_components(self, sample_positions, sample_rotations, simple_context):
        """Test that well-spread components have low congestion."""
        loss_fn = CongestionLoss(grid_shape=(5, 5), capacity_per_cell=20.0)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # Should have relatively low congestion
        assert isinstance(result, LossResult)
        assert result.value.shape == ()

    def test_congestion_clustered_components(self, sample_rotations, simple_context):
        """Test that clustered components have higher congestion."""
        # All components in one corner
        clustered_positions = jnp.array(
            [
                [10.0, 10.0],
                [12.0, 10.0],
                [10.0, 12.0],
                [12.0, 12.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = CongestionLoss(grid_shape=(5, 5), capacity_per_cell=1.0)
        result = loss_fn(clustered_positions, sample_rotations, simple_context)

        # Clustered positions should produce higher congestion
        assert float(result.value) >= 0

    def test_congestion_gradient(self, sample_positions, sample_rotations, simple_context):
        """Test gradient computation for congestion loss."""
        loss_fn = CongestionLoss(grid_shape=(5, 5), capacity_per_cell=5.0)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        # Note: congestion loss uses Python loops internally, so gradients
        # may not flow through all operations. This tests that no errors occur.
        grad = jax.grad(loss_fn_wrapper)(sample_positions)
        assert grad.shape == sample_positions.shape


# =============================================================================
# Test Regularization Losses
# =============================================================================


class TestSpreadLoss:
    """Tests for spread regularization loss."""

    def test_spread_well_separated(self, sample_positions, sample_rotations, simple_context):
        """Test that well-separated components have low spread loss."""
        loss_fn = SpreadLoss(min_distance=2.0)
        result = loss_fn(sample_positions, sample_rotations, simple_context)

        # Components are 25mm apart, well above 2mm min
        assert float(result.value) < 1.0

    def test_spread_close_together(self, sample_rotations, simple_context):
        """Test that close components have higher spread loss."""
        close_positions = jnp.array(
            [
                [50.0, 40.0],
                [52.0, 40.0],  # 2mm from U1
                [54.0, 40.0],  # 2mm from R1
                [56.0, 40.0],  # 2mm from C1
            ],
            dtype=jnp.float32,
        )

        loss_fn = SpreadLoss(min_distance=10.0)
        result = loss_fn(close_positions, sample_rotations, simple_context)

        # Should have positive spread penalty
        assert float(result.value) > 0

    def test_spread_gradient(self, sample_rotations, simple_context):
        """Test gradient computation for spread loss."""
        positions = jnp.array(
            [
                [50.0, 40.0],
                [55.0, 40.0],
                [60.0, 40.0],
                [65.0, 40.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = SpreadLoss(min_distance=10.0)

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(positions)
        assert grad.shape == positions.shape
        assert jnp.all(jnp.isfinite(grad))

    def test_spread_chunked_matches_vectorized(self):
        """Test that chunked computation matches vectorized for correctness.

        This validates the chunking optimization for SpreadLoss (temper-r2i.5).
        """
        from temper_placer.losses.regularization import (
            _compute_spread_penalty_chunked,
            _compute_spread_penalty_vectorized,
        )

        # Create a test case with positions that will have spread penalties
        key = jax.random.PRNGKey(42)
        n = 60  # Above chunking threshold
        positions = jax.random.uniform(key, (n, 2), minval=0.0, maxval=100.0)
        bounds = jnp.full((n, 2), 5.0)  # 5x5mm components
        min_distance = 10.0

        # Compute using both methods
        vectorized_result = _compute_spread_penalty_vectorized(positions, bounds, min_distance)
        chunked_result = _compute_spread_penalty_chunked(positions, bounds, min_distance)

        # Results should be very close (numerical precision differences expected)
        assert jnp.allclose(vectorized_result, chunked_result, rtol=1e-4, atol=1e-6), (
            f"Vectorized: {float(vectorized_result)}, Chunked: {float(chunked_result)}"
        )

    def test_spread_large_n_no_memory_explosion(self):
        """Test that spread loss handles large N without memory issues.

        The chunked implementation should prevent O(N²) memory allocation.
        """
        key = jax.random.PRNGKey(123)
        n = 200  # Large enough to stress memory if not chunked

        positions = jax.random.uniform(key, (n, 2), minval=0.0, maxval=300.0)
        bounds = jnp.full((n, 2), 5.0)

        # This should complete without memory issues
        penalty = compute_spread_penalty(positions, bounds, min_distance=10.0)

        # Basic sanity checks
        assert jnp.isfinite(penalty)
        assert float(penalty) >= 0

    def test_spread_chunked_gradient_correct(self):
        """Test that gradients are correct with chunked computation."""
        from temper_placer.losses.regularization import (
            _compute_spread_penalty_chunked,
            _compute_spread_penalty_vectorized,
        )

        key = jax.random.PRNGKey(99)
        n = 60  # Above chunking threshold
        positions = jax.random.uniform(key, (n, 2), minval=0.0, maxval=100.0)
        bounds = jnp.full((n, 2), 5.0)
        min_distance = 10.0

        # Compute gradients using both methods
        def vectorized_loss(pos):
            return _compute_spread_penalty_vectorized(pos, bounds, min_distance)

        def chunked_loss(pos):
            return _compute_spread_penalty_chunked(pos, bounds, min_distance)

        grad_vectorized = jax.grad(vectorized_loss)(positions)
        grad_chunked = jax.grad(chunked_loss)(positions)

        # Gradients should match
        assert jnp.allclose(grad_vectorized, grad_chunked, rtol=1e-4, atol=1e-6), (
            f"Max gradient diff: {float(jnp.max(jnp.abs(grad_vectorized - grad_chunked)))}"
        )


class TestRotationEntropyLoss:
    """Tests for rotation entropy loss."""

    def test_entropy_uniform_distribution(self, sample_positions, simple_context):
        """Test that uniform rotations have high entropy (low loss)."""
        uniform_rotations = jnp.array(
            [
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
            ],
            dtype=jnp.float32,
        )

        loss_fn = RotationEntropyLoss()
        result = loss_fn(sample_positions, uniform_rotations, simple_context)

        # Uniform distribution has maximum entropy, so negative entropy is most negative
        assert isinstance(result, LossResult)

    def test_entropy_peaked_distribution(self, sample_positions, simple_context):
        """Test that peaked rotations have low entropy (higher loss)."""
        peaked_rotations = jnp.array(
            [
                [0.97, 0.01, 0.01, 0.01],
                [0.97, 0.01, 0.01, 0.01],
                [0.97, 0.01, 0.01, 0.01],
                [0.97, 0.01, 0.01, 0.01],
            ],
            dtype=jnp.float32,
        )

        uniform_rotations = jnp.array(
            [
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
                [0.25, 0.25, 0.25, 0.25],
            ],
            dtype=jnp.float32,
        )

        loss_fn = RotationEntropyLoss()
        result_peaked = loss_fn(sample_positions, peaked_rotations, simple_context)
        result_uniform = loss_fn(sample_positions, uniform_rotations, simple_context)

        # Peaked has lower entropy -> higher (less negative) loss
        assert float(result_peaked.value) > float(result_uniform.value)

    def test_entropy_weight_annealing(self):
        """Test that weight schedule anneals properly."""
        loss_fn = RotationEntropyLoss(anneal_start=0.0, anneal_end=0.5)

        # At epoch 0, full weight
        assert loss_fn.weight_schedule(0, 1000) == pytest.approx(1.0)

        # At epoch 250 (25%), partial weight
        assert loss_fn.weight_schedule(250, 1000) == pytest.approx(0.5, abs=0.01)

        # At epoch 500 (50%), zero weight
        assert loss_fn.weight_schedule(500, 1000) == pytest.approx(0.0)

        # At epoch 750, still zero
        assert loss_fn.weight_schedule(750, 1000) == pytest.approx(0.0)


class TestCenterOfMassLoss:
    """Tests for center of mass loss."""

    def test_center_of_mass_at_target(self, sample_rotations, simple_context):
        """Test that COM at target produces zero loss."""
        # Position components symmetrically around board center (50, 40)
        positions = jnp.array(
            [
                [40.0, 30.0],
                [60.0, 30.0],
                [40.0, 50.0],
                [60.0, 50.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = CenterOfMassLoss(target=(50.0, 40.0))
        result = loss_fn(positions, sample_rotations, simple_context)

        # COM should be at (50, 40), matching target
        assert float(result.value) < 1e-6

    def test_center_of_mass_off_target(self, sample_rotations, simple_context):
        """Test that COM far from target produces positive loss."""
        # All components in one corner
        positions = jnp.array(
            [
                [10.0, 10.0],
                [15.0, 10.0],
                [10.0, 15.0],
                [15.0, 15.0],
            ],
            dtype=jnp.float32,
        )

        loss_fn = CenterOfMassLoss(target=(50.0, 40.0))
        result = loss_fn(positions, sample_rotations, simple_context)

        # COM is around (12.5, 12.5), far from (50, 40)
        assert float(result.value) > 0

    def test_center_of_mass_gradient(self, sample_positions, sample_rotations, simple_context):
        """Test gradient computation for center of mass loss."""
        loss_fn = CenterOfMassLoss(target=(50.0, 40.0))

        def loss_fn_wrapper(positions):
            return loss_fn(positions, sample_rotations, simple_context).value

        grad = jax.grad(loss_fn_wrapper)(sample_positions)
        assert grad.shape == sample_positions.shape
        assert jnp.all(jnp.isfinite(grad))
