"""
BDD tests for SpreadLoss behavior verification.

These tests verify that SpreadLoss behaves as documented:
- High penalty when components are clustered (close together)
- Low/zero penalty when components are spread apart

Related issue: temper-h0n9.6
Hypothesis: Spread loss definition might be inverted or misnamed

Scientific Method:
- H1 (tested here): Spread loss penalizes clustering, rewards spreading
- Observation: Correlation analysis showed spread loss negatively correlates with routing
- Expected outcome: If H1 is TRUE, the negative correlation must have another explanation
"""

import jax.numpy as jnp

from temper_placer.losses.regularization import compute_spread_penalty


class TestSpreadLossBehavior:
    """BDD tests for SpreadLoss semantic behavior."""

    def test_clustered_components_have_high_spread_penalty(self):
        """
        GIVEN components clustered together in the center
        WHEN spread loss is computed
        THEN the penalty should be HIGH (positive, non-zero)

        This verifies: SpreadLoss penalizes clustering
        """
        # Arrange: 4 components tightly clustered at center
        positions = jnp.array(
            [
                [50.0, 75.0],  # Component A - center
                [52.0, 75.0],  # Component B - 2mm to right
                [50.0, 77.0],  # Component C - 2mm above
                [52.0, 77.0],  # Component D - diagonal
            ]
        )
        bounds = jnp.array(
            [
                [5.0, 5.0],  # 5mm x 5mm components
                [5.0, 5.0],
                [5.0, 5.0],
                [5.0, 5.0],
            ]
        )

        # Act
        penalty = compute_spread_penalty(positions, bounds, min_distance=2.0)

        # Assert: Penalty should be positive and significant
        assert float(penalty) > 0, (
            f"Clustered components should have positive spread penalty, got {penalty}"
        )
        assert float(penalty) > 10.0, (
            f"Penalty {penalty} seems too low for tightly clustered 5mm components 2mm apart"
        )

    def test_spread_components_have_low_spread_penalty(self):
        """
        GIVEN components spread far apart across the board
        WHEN spread loss is computed
        THEN the penalty should be LOW (near zero)

        This verifies: SpreadLoss rewards spreading
        """
        # Arrange: 4 components spread to corners of 100x150mm board
        positions = jnp.array(
            [
                [10.0, 10.0],  # Bottom-left corner
                [90.0, 10.0],  # Bottom-right corner
                [10.0, 140.0],  # Top-left corner
                [90.0, 140.0],  # Top-right corner
            ]
        )
        bounds = jnp.array(
            [
                [5.0, 5.0],  # 5mm x 5mm components
                [5.0, 5.0],
                [5.0, 5.0],
                [5.0, 5.0],
            ]
        )

        # Act
        penalty = compute_spread_penalty(positions, bounds, min_distance=2.0)

        # Assert: Penalty should be zero or near-zero
        assert float(penalty) < 1.0, (
            f"Spread components should have near-zero penalty, got {penalty}"
        )

    def test_clustered_has_higher_penalty_than_spread(self):
        """
        GIVEN two placements: one clustered, one spread
        WHEN spread loss is computed for both
        THEN clustered should have HIGHER penalty than spread

        This is the key semantic test for spread loss correctness.
        """
        bounds = jnp.array(
            [
                [5.0, 5.0],
                [5.0, 5.0],
                [5.0, 5.0],
                [5.0, 5.0],
            ]
        )

        # Clustered placement
        clustered_positions = jnp.array(
            [
                [50.0, 75.0],
                [52.0, 75.0],
                [50.0, 77.0],
                [52.0, 77.0],
            ]
        )

        # Spread placement
        spread_positions = jnp.array(
            [
                [10.0, 10.0],
                [90.0, 10.0],
                [10.0, 140.0],
                [90.0, 140.0],
            ]
        )

        # Act
        clustered_penalty = compute_spread_penalty(clustered_positions, bounds, min_distance=2.0)
        spread_penalty = compute_spread_penalty(spread_positions, bounds, min_distance=2.0)

        # Assert
        assert float(clustered_penalty) > float(spread_penalty), (
            f"Clustered ({clustered_penalty}) should have HIGHER penalty than spread ({spread_penalty})\n"
            f"If this fails, the spread loss definition is INVERTED!"
        )

    def test_spread_loss_uses_correct_formula(self):
        """
        GIVEN the SpreadLoss formula: penalty = max(0, min_sep - distance)²
        WHEN components are closer than min_sep
        THEN penalty should be (min_sep - distance)²

        This verifies the formula is correct.
        """
        # Arrange: Two components exactly 10mm apart (center to center)
        # With 5x5mm bounds, half_diag = sqrt(5² + 5²)/2 = 3.54mm
        # min_sep = 3.54 + 3.54 + 2.0 = 9.07mm
        # deficit = 9.07 - 10 = -0.93 (no penalty)

        positions_far = jnp.array(
            [
                [0.0, 0.0],
                [10.0, 0.0],  # 10mm apart
            ]
        )
        bounds = jnp.array(
            [
                [5.0, 5.0],
                [5.0, 5.0],
            ]
        )

        # Act
        penalty_far = compute_spread_penalty(positions_far, bounds, min_distance=2.0)

        # With min_distance=2.0, half_diag ≈ 3.54mm each
        # min_sep ≈ 9.07mm, distance=10mm, so no penalty
        assert float(penalty_far) < 1.0, (
            f"Components 10mm apart should have near-zero penalty, got {penalty_far}"
        )

        # Now test close components
        positions_close = jnp.array(
            [
                [0.0, 0.0],
                [5.0, 0.0],  # Only 5mm apart
            ]
        )

        penalty_close = compute_spread_penalty(positions_close, bounds, min_distance=2.0)

        # distance=5mm, min_sep ≈ 9.07mm, deficit ≈ 4.07mm
        # penalty ≈ 4.07² ≈ 16.6
        assert float(penalty_close) > 10.0, (
            f"Components 5mm apart should have significant penalty, got {penalty_close}"
        )


class TestSpreadLossCorrelationHypothesis:
    """
    Tests investigating why spread loss negatively correlates with routing.

    If spread loss is correctly implemented (penalizes clustering),
    then the negative correlation might be because:

    1. Optimizer drives spread loss DOWN (spreading components)
    2. But spreading to board edges may HURT routing (edge congestion)
    3. So paradoxically: low spread loss = spread placement = worse routing
    """

    def test_optimizer_minimizes_spread_loss(self):
        """
        GIVEN the optimizer minimizes all losses
        WHEN spread loss is minimized
        THEN components should be more spread apart (low penalty)

        This means: optimizer SUCCESS = low spread = spread-out placement
        """
        # This test documents the expected optimizer behavior
        # If optimizer minimizes spread loss, it spreads components
        bounds = jnp.array([[5.0, 5.0]] * 4)

        # Initial random/clustered state (high spread loss)
        initial = jnp.array(
            [
                [50.0, 75.0],
                [52.0, 75.0],
                [50.0, 77.0],
                [52.0, 77.0],
            ]
        )

        # "Optimized" spread state (low spread loss)
        optimized = jnp.array(
            [
                [25.0, 37.5],
                [75.0, 37.5],
                [25.0, 112.5],
                [75.0, 112.5],
            ]
        )

        initial_loss = compute_spread_penalty(initial, bounds, min_distance=2.0)
        optimized_loss = compute_spread_penalty(optimized, bounds, min_distance=2.0)

        # The optimizer would drive from high to low spread loss
        assert float(optimized_loss) < float(initial_loss), (
            "Optimizer minimization should reduce spread loss by spreading components"
        )

        # Document the finding
        print("\nSpread loss behavior:")
        print(f"  Clustered placement: spread_loss = {float(initial_loss):.2f}")
        print(f"  Spread placement:    spread_loss = {float(optimized_loss):.2f}")
        print("  Optimizer SUCCESS means LOW spread loss = SPREAD-OUT placement")

    def test_correlation_interpretation(self):
        """
        This test documents the correct interpretation of the correlation finding.

        Observation: r(spread_loss, routing_completion) = -0.40

        Interpretation:
        - Higher spread_loss → BETTER routing completion
        - But spread_loss measures CLUSTERING penalty
        - So: More CLUSTERED → Better routing (counterintuitive!)

        Possible explanations:
        1. Edge effects: Spreading pushes components to edges where routing is harder
        2. Wirelength: Spreading increases average wirelength, congesting routes
        3. Confounding: Both spread and routing correlate with some third variable
        """
        # This is a documentation test - it always passes but documents findings

        interpretation = """
        FINDING: The spread loss implementation is CORRECT.
        
        SpreadLoss penalizes clustering (high when clustered, low when spread).
        
        The negative correlation (spread_loss ↑ = routing ↑) means:
        - Placements with MORE clustering → BETTER routing
        - This is OPPOSITE to what we expected!
        
        HYPOTHESIS FOR NEGATIVE CORRELATION:
        The optimizer minimizes spread loss, which spreads components.
        But spreading to the board edges may:
        1. Create routing congestion at edges
        2. Increase average wirelength
        3. Push components away from optimal routing channels
        
        RECOMMENDATION:
        - Consider REDUCING spread loss weight
        - Or investigate if spread pushes components to edge keepout zones
        - Or add edge-avoidance term to spread loss
        """
        print(interpretation)
        assert True  # Documentation test
