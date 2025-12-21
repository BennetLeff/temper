"""Unit tests for manufacturing margin loss function.

Tests the differentiable loss that penalizes tight manufacturing margins,
encouraging the optimizer to maximize safety margins beyond minimum DRC.

Related issues: temper-6vj.6
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.losses.manufacturing_margin import (
    ManufacturingMarginConfig,
    ManufacturingMarginLoss,
    compute_manufacturability_score,
    compute_margin_loss,
    compute_pairwise_clearances,
    create_manufacturing_margin_loss,
)


class TestComputeMarginLoss:
    """Tests for the core margin loss computation."""

    def test_zero_loss_for_comfortable_margins(self):
        """Loss should be near zero when margins exceed target."""
        actual = jnp.array([1.0, 1.5, 2.0])  # Large clearances
        required = jnp.array([0.2, 0.2, 0.2])  # Small requirements
        target_margin = 0.1

        loss = compute_margin_loss(actual, required, target_margin)

        # Should be very small (near zero)
        assert float(loss) < 0.1

    def test_loss_increases_for_tight_margins(self):
        """Loss should increase as margins get tighter."""
        required = jnp.array([0.2])
        target_margin = 0.1

        # Comfortable margin
        loss_comfortable = compute_margin_loss(jnp.array([0.5]), required, target_margin)

        # Tight margin (just above requirement)
        loss_tight = compute_margin_loss(jnp.array([0.25]), required, target_margin)

        # Very tight margin
        loss_very_tight = compute_margin_loss(jnp.array([0.21]), required, target_margin)

        assert float(loss_comfortable) < float(loss_tight)
        assert float(loss_tight) < float(loss_very_tight)

    def test_high_loss_for_violations(self):
        """Loss should be very high for negative margins (violations)."""
        required = jnp.array([0.2])
        target_margin = 0.1

        # Passing with margin
        loss_passing = compute_margin_loss(jnp.array([0.35]), required, target_margin)

        # Violation (actual < required)
        loss_violation = compute_margin_loss(jnp.array([0.15]), required, target_margin)

        # Violations should have much higher loss
        assert float(loss_violation) > float(loss_passing) * 10

    def test_violation_penalty_scale(self):
        """Violation penalty should scale with violation_penalty_scale."""
        actual = jnp.array([0.1])  # Clear violation
        required = jnp.array([0.2])
        target_margin = 0.1

        loss_default = compute_margin_loss(
            actual, required, target_margin, violation_penalty_scale=100.0
        )
        loss_high = compute_margin_loss(
            actual, required, target_margin, violation_penalty_scale=500.0
        )

        assert float(loss_high) > float(loss_default)


class TestComputePairwiseClearances:
    """Tests for pairwise clearance computation."""

    def test_two_separated_components(self):
        """Clearance between two well-separated components."""
        positions = jnp.array([[0.0, 0.0], [10.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        clearances, idx_i, idx_j = compute_pairwise_clearances(positions, widths, heights)

        # Components are 10mm apart center-to-center
        # Each is 2mm wide, so edge-to-edge = 10 - 1 - 1 = 8mm
        assert clearances.shape == (1,)
        assert float(clearances[0]) == pytest.approx(8.0, abs=0.01)
        assert int(idx_i[0]) == 0
        assert int(idx_j[0]) == 1

    def test_overlapping_components(self):
        """Clearance should be negative for overlapping components."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        clearances, _, _ = compute_pairwise_clearances(positions, widths, heights)

        # Components overlap: 1mm apart center-to-center, 2mm total width
        # Edge-to-edge = 1 - 1 - 1 = -1mm (overlap)
        assert float(clearances[0]) == pytest.approx(-1.0, abs=0.01)

    def test_diagonal_separation(self):
        """Components separated diagonally use corner distance."""
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        clearances, _, _ = compute_pairwise_clearances(positions, widths, heights)

        # Diagonal distance from edges
        # Center-to-center diagonal = sqrt(200) ≈ 14.14
        # Each component extends 1mm from center
        # Edge separations: 10 - 1 - 1 = 8 in both x and y
        # Corner distance = sqrt(8^2 + 8^2) = sqrt(128) ≈ 11.31
        expected = jnp.sqrt(128.0)
        assert float(clearances[0]) == pytest.approx(float(expected), abs=0.1)

    def test_multiple_components(self):
        """Correct number of pairs for multiple components."""
        n = 5
        positions = jnp.zeros((n, 2))  # Doesn't matter for count
        widths = jnp.ones(n)
        heights = jnp.ones(n)

        clearances, idx_i, idx_j = compute_pairwise_clearances(positions, widths, heights)

        # Should have n*(n-1)/2 unique pairs
        expected_pairs = n * (n - 1) // 2
        assert clearances.shape[0] == expected_pairs
        assert idx_i.shape[0] == expected_pairs
        assert idx_j.shape[0] == expected_pairs


class TestManufacturingMarginConfig:
    """Tests for configuration dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = ManufacturingMarginConfig()

        assert config.target_margin_mm == 0.1
        assert config.min_margin_mm == 0.05
        assert config.weight == 10.0
        assert config.violation_penalty_scale == 100.0
        assert config.use_tolerances is True
        assert config.etch_tolerance_mm == 0.05

    def test_custom_values(self):
        """Config accepts custom values."""
        config = ManufacturingMarginConfig(
            target_margin_mm=0.2,
            weight=50.0,
            use_tolerances=False,
        )

        assert config.target_margin_mm == 0.2
        assert config.weight == 50.0
        assert config.use_tolerances is False


class TestManufacturingMarginLoss:
    """Tests for the ManufacturingMarginLoss class."""

    @pytest.fixture
    def simple_context(self):
        """Create a minimal context for testing."""
        # We need to import here to avoid circular imports
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist, Pin
        from temper_placer.losses.base import LossContext

        # Create simple components
        components = [
            Component(
                ref=f"U{i}",
                footprint="Package_SO:SOIC-8",
                bounds=(2.0, 2.0),
                pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
            )
            for i in range(4)
        ]

        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)

        return LossContext.from_netlist_and_board(netlist, board)

    def test_loss_name(self):
        """Loss has correct name."""
        loss = ManufacturingMarginLoss()
        assert loss.name == "manufacturing_margin"

    def test_loss_with_well_separated_components(self, simple_context):
        """Loss should be low for well-separated components."""
        # Place components far apart
        positions = jnp.array(
            [
                [10.0, 10.0],
                [50.0, 10.0],
                [10.0, 50.0],
                [50.0, 50.0],
            ]
        )
        rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (4, 1))

        loss_fn = ManufacturingMarginLoss(min_clearance_mm=0.2)
        result = loss_fn(positions, rotations, simple_context)

        # Should have low loss - components are ~40mm apart
        assert float(result.value) < 10.0

    def test_loss_with_tight_clearances(self, simple_context):
        """Loss should be higher for tight clearances."""
        # Place components very close together
        # Components are 2mm wide, so at 2.3mm center-to-center:
        # clearance = 2.3 - 1 - 1 = 0.3mm
        # With min_clearance=0.2 and tolerance margin 2*0.05=0.1:
        # required = 0.3mm, so margin = 0.3 - 0.3 = 0
        positions = jnp.array(
            [
                [10.0, 10.0],
                [12.3, 10.0],  # 0.3mm clearance, equals required with tolerances
                [10.0, 15.0],
                [50.0, 50.0],
            ]
        )
        rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (4, 1))

        # Use higher min_clearance to make clearances "tight"
        loss_fn = ManufacturingMarginLoss(
            config=ManufacturingMarginConfig(
                target_margin_mm=0.1,
                use_tolerances=False,  # Don't add tolerance margin
            ),
            min_clearance_mm=0.25,  # Required is 0.25, actual is 0.3
        )
        result = loss_fn(positions, rotations, simple_context)

        # Margin = 0.3 - 0.25 = 0.05, which is below target (0.1)
        # Should have some loss due to tight margin
        assert float(result.value) > 0.01
        # And breakdown should show tight margins
        assert result.breakdown is not None
        assert int(result.breakdown["n_tight_margins"]) >= 1

    def test_breakdown_contains_statistics(self, simple_context):
        """Result breakdown should contain margin statistics."""
        positions = jnp.array(
            [
                [10.0, 10.0],
                [50.0, 10.0],
                [10.0, 50.0],
                [50.0, 50.0],
            ]
        )
        rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (4, 1))

        loss_fn = ManufacturingMarginLoss()
        result = loss_fn(positions, rotations, simple_context)

        assert result.breakdown is not None
        assert "min_margin" in result.breakdown
        assert "mean_margin" in result.breakdown
        assert "n_violations" in result.breakdown
        assert "n_tight_margins" in result.breakdown
        assert "n_pairs" in result.breakdown

    def test_weight_schedule(self):
        """Weight schedule should ramp up over training."""
        loss_fn = ManufacturingMarginLoss()

        # Early in training
        w_early = loss_fn.weight_schedule(0, 1000)
        # Mid training
        w_mid = loss_fn.weight_schedule(300, 1000)
        # Late training
        w_late = loss_fn.weight_schedule(800, 1000)

        assert w_early < w_late
        assert w_mid >= w_early
        assert w_late == pytest.approx(1.0, abs=0.01)

    def test_differentiable(self, simple_context):
        """Loss should be differentiable with respect to positions."""
        # Place components with tight margins to get non-zero gradients
        # Components are 2mm wide, at 2.4mm center-to-center:
        # clearance = 2.4 - 1 - 1 = 0.4mm
        positions = jnp.array(
            [
                [10.0, 10.0],
                [12.4, 10.0],  # 0.4mm clearance
                [10.0, 12.4],  # 0.4mm clearance to U0
                [12.4, 12.4],  # 0.4mm clearance to all neighbors
            ]
        )
        rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (4, 1))

        # Use high min_clearance to make all margins "tight"
        loss_fn = ManufacturingMarginLoss(
            config=ManufacturingMarginConfig(
                target_margin_mm=0.2,
                use_tolerances=False,
            ),
            min_clearance_mm=0.35,  # required = 0.35, actual = 0.4, margin = 0.05 < target
        )

        def loss_wrapper(pos):
            result = loss_fn(pos, rotations, simple_context)
            return result.value

        # Should be able to compute gradients
        grad_fn = jax.grad(loss_wrapper)
        grads = grad_fn(positions)

        assert grads.shape == positions.shape
        # Gradients should not be all zero when margins are tight
        # (Some gradients push components apart to increase margins)
        assert jnp.any(jnp.abs(grads) > 1e-6)


class TestCreateManufacturingMarginLoss:
    """Tests for the factory function."""

    def test_creates_loss_with_defaults(self):
        """Factory creates loss with default config."""
        loss = create_manufacturing_margin_loss()

        assert isinstance(loss, ManufacturingMarginLoss)
        assert loss.config.target_margin_mm == 0.1
        assert loss.min_clearance_mm == 0.2

    def test_creates_loss_with_custom_config(self):
        """Factory creates loss with custom config."""
        config = ManufacturingMarginConfig(target_margin_mm=0.15, weight=20.0)
        loss = create_manufacturing_margin_loss(
            config=config,
            min_clearance_mm=0.25,
        )

        assert loss.config.target_margin_mm == 0.15
        assert loss.config.weight == 20.0
        assert loss.min_clearance_mm == 0.25


class TestComputeManufacturabilityScore:
    """Tests for the manufacturability score function."""

    def test_excellent_score_for_large_margins(self):
        """Score > 1.0 when all margins exceed target."""
        positions = jnp.array([[0.0, 0.0], [20.0, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        score = compute_manufacturability_score(
            positions,
            widths,
            heights,
            min_clearance_mm=0.2,
            target_margin_mm=0.1,
        )

        # Clearance = 20 - 1 - 1 = 18mm
        # Margin = 18 - 0.2 = 17.8mm
        # Score = 17.8 / 0.1 = 178
        assert score > 100.0

    def test_score_one_at_target_margin(self):
        """Score = 1.0 when minimum margin equals target."""
        # Position components to get exactly target margin
        # Clearance = 0.3, required = 0.2, margin = 0.1 = target
        # Need: clearance = 0.3, so edge-to-edge = 0.3
        # For 2mm wide components: center-to-center = 2 + 0.3 = 2.3
        positions = jnp.array([[0.0, 0.0], [2.3, 0.0]])
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        score = compute_manufacturability_score(
            positions,
            widths,
            heights,
            min_clearance_mm=0.2,
            target_margin_mm=0.1,
        )

        assert score == pytest.approx(1.0, abs=0.1)

    def test_zero_score_for_violation(self):
        """Score = 0 when there's a clearance violation."""
        positions = jnp.array([[0.0, 0.0], [1.5, 0.0]])  # Overlap
        widths = jnp.array([2.0, 2.0])
        heights = jnp.array([2.0, 2.0])

        score = compute_manufacturability_score(
            positions,
            widths,
            heights,
            min_clearance_mm=0.2,
            target_margin_mm=0.1,
        )

        assert score == 0.0

    def test_score_with_no_pairs(self):
        """Score = 1.0 for single component (no pairs)."""
        positions = jnp.array([[0.0, 0.0]])
        widths = jnp.array([2.0])
        heights = jnp.array([2.0])

        score = compute_manufacturability_score(
            positions,
            widths,
            heights,
            min_clearance_mm=0.2,
            target_margin_mm=0.1,
        )

        assert score == 1.0
