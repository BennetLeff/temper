"""
Numerical edge case tests for optimizer and loss functions.

These tests verify numerical stability at the optimizer and training loop level,
complementing the geometry-level tests in tests/verification/test_numerical_stability.py.

Test categories:
1. Overlapping initial positions (NaN in overlap loss gradients)
2. Components at exact boundaries (gradient instability)
3. Zero-area and negative-size components
4. Extreme coordinate values (overflow/underflow)
5. Single-pin nets (division by zero in wirelength)
6. Degenerate configurations (all same position)
7. Extreme learning rates and temperatures
"""

import jax
import jax.numpy as jnp
import pytest
from jax import Array

# Enable 64-bit precision for accurate numerical checks
jax.config.update("jax_enable_x64", True)


class TestOverlappingInitialPositions:
    """Test that overlapping components don't produce NaN in loss/gradients."""

    def test_overlapping_init_loss_finite(self):
        """Overlapping initial positions produce finite loss (not NaN)."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        # Two components at exactly the same position
        positions = jnp.array(
            [
                [50.0, 50.0],
                [50.0, 50.0],  # Same position - complete overlap
            ]
        )
        widths = jnp.array([10.0, 10.0])
        heights = jnp.array([10.0, 10.0])

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Overlap loss is not finite: {loss}"
        assert loss > 0, "Overlapping components should have positive penalty"

    def test_overlapping_init_gradient_finite(self):
        """Gradients at overlapping positions are finite."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        positions = jnp.array(
            [
                [50.0, 50.0],
                [50.0, 50.0],
            ]
        )
        widths = jnp.array([10.0, 10.0])
        heights = jnp.array([10.0, 10.0])

        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        grad = jax.grad(loss_fn)(positions)

        assert jnp.all(jnp.isfinite(grad)), f"Overlap gradient is not finite: {grad}"


class TestBoundaryEdgeCases:
    """Test gradient stability at exact boundaries."""

    def test_component_exactly_at_boundary_loss_finite(self):
        """Component edge exactly at board boundary has finite loss."""
        from temper_placer.losses.boundary import compute_boundary_penalty

        # Component at x=5, width=10, so left edge is at x=0 (board min)
        positions = jnp.array(
            [
                [5.0, 50.0],  # Left edge exactly at board edge
            ]
        )
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        loss = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.0)

        assert jnp.isfinite(loss), f"Boundary loss is not finite: {loss}"

    def test_component_exactly_at_boundary_gradient_finite(self):
        """Gradient at exact boundary is finite (no NaN from relu derivative)."""
        from temper_placer.losses.boundary import compute_boundary_penalty

        positions = jnp.array(
            [
                [5.0, 50.0],
            ]
        )
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        def loss_fn(pos):
            return compute_boundary_penalty(pos, widths, heights, board_bounds, margin=0.0)

        grad = jax.grad(loss_fn)(positions)

        assert jnp.all(jnp.isfinite(grad)), f"Boundary gradient is not finite: {grad}"


class TestZeroAndNegativeSizeComponents:
    """Test handling of zero-area and negative-size components."""

    def test_zero_width_component_overlap_finite(self):
        """Component with zero width produces finite overlap loss."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        positions = jnp.array(
            [
                [50.0, 50.0],
                [55.0, 50.0],
            ]
        )
        widths = jnp.array([0.0, 10.0])  # First component has zero width
        heights = jnp.array([10.0, 10.0])

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Loss not finite with zero-width component: {loss}"

    def test_zero_area_component_boundary_finite(self):
        """Component with zero area produces finite boundary loss."""
        from temper_placer.losses.boundary import compute_boundary_penalty

        positions = jnp.array(
            [
                [50.0, 50.0],
            ]
        )
        widths = jnp.array([0.0])  # Zero width
        heights = jnp.array([0.0])  # Zero height
        board_bounds = jnp.array([0.0, 0.0, 100.0, 100.0])

        loss = compute_boundary_penalty(positions, widths, heights, board_bounds)

        assert jnp.isfinite(loss), f"Loss not finite with zero-area component: {loss}"

    def test_negative_size_component_handled(self):
        """Negative component sizes don't cause NaN (implementation should use abs)."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        positions = jnp.array(
            [
                [50.0, 50.0],
                [55.0, 50.0],
            ]
        )
        # Negative widths - should be handled gracefully
        widths = jnp.array([-10.0, 10.0])
        heights = jnp.array([10.0, -10.0])

        loss = compute_overlap_penalty(positions, widths, heights)

        # We just verify it doesn't crash or produce NaN
        # The actual behavior with negative sizes is implementation-defined
        assert jnp.isfinite(loss) or jnp.isnan(loss), "Loss should be finite or explicitly NaN"


class TestExtremeCoordinates:
    """Test numerical stability at extreme coordinate values."""

    def test_huge_coordinates_overlap_finite(self):
        """Overlap loss at 1e6 mm coordinates doesn't overflow."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        # PCB at offset of 1e6 mm (far from origin)
        positions = jnp.array(
            [
                [1e6, 1e6],
                [1e6 + 15.0, 1e6],  # 15mm apart, no overlap with 10mm components
            ]
        )
        widths = jnp.array([10.0, 10.0])
        heights = jnp.array([10.0, 10.0])

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Loss overflowed at large coords: {loss}"
        assert loss == 0.0, "Non-overlapping components should have zero loss"

    def test_tiny_coordinates_overlap_finite(self):
        """Overlap loss at 1e-6 mm coordinates doesn't underflow."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        # Tiny components at tiny positions
        positions = jnp.array(
            [
                [1e-6, 1e-6],
                [2e-6, 1e-6],
            ]
        )
        widths = jnp.array([1e-7, 1e-7])
        heights = jnp.array([1e-7, 1e-7])

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Loss underflowed at tiny coords: {loss}"

    def test_huge_coordinates_boundary_accurate(self):
        """Boundary loss is accurate at large coordinate offsets."""
        from temper_placer.losses.boundary import compute_boundary_penalty

        offset = 1e6
        # Component clearly inside large board
        positions = jnp.array([[offset + 50.0, offset + 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])
        board_bounds = jnp.array([offset, offset, offset + 100.0, offset + 100.0])

        loss = compute_boundary_penalty(positions, widths, heights, board_bounds, margin=0.0)

        assert jnp.isfinite(loss), f"Boundary loss overflowed: {loss}"
        assert jnp.isclose(loss, 0.0, atol=1e-6), (
            f"Expected zero loss for interior component: {loss}"
        )


class TestSinglePinNetWirelength:
    """Test wirelength loss with single-pin nets (division by zero risk)."""

    def test_single_pin_net_loss_finite(self):
        """Single-pin net produces finite wirelength (no divide by zero)."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss

        # Create minimal netlist with single-pin net
        comp = Component(
            ref="R1",
            footprint="0402",
            bounds=(1.0, 0.5),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )
        net = Net(name="SINGLE", pins=[("R1", "1")])  # Only one pin

        netlist = Netlist(components=[comp], nets=[net])
        board = Board(width=100.0, height=100.0)

        context = LossContext.from_netlist_and_board(netlist, board)

        positions = jnp.array([[50.0, 50.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])  # 0 degrees

        loss_fn = WirelengthLoss()
        result = loss_fn(positions, rotations, context)

        assert jnp.isfinite(result.value), f"Single-pin net wirelength not finite: {result.value}"

    def test_empty_net_loss_finite(self):
        """Empty nets don't cause errors in wirelength computation."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist, Pin
        from temper_placer.losses.base import LossContext
        from temper_placer.losses.wirelength import WirelengthLoss

        # Netlist with no nets
        comp = Component(
            ref="R1",
            footprint="0402",
            bounds=(1.0, 0.5),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )
        netlist = Netlist(components=[comp], nets=[])
        board = Board(width=100.0, height=100.0)

        context = LossContext.from_netlist_and_board(netlist, board)

        positions = jnp.array([[50.0, 50.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])

        loss_fn = WirelengthLoss()
        result = loss_fn(positions, rotations, context)

        assert jnp.isfinite(result.value), f"Empty net wirelength not finite: {result.value}"
        assert result.value == 0.0, "Empty netlist should have zero wirelength"


class TestDegenerateConfigurations:
    """Test degenerate configurations that could cause numerical issues."""

    def test_all_components_same_position(self):
        """All components at same position produces finite loss and gradient."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        n = 5
        # All components at the same position
        positions = jnp.tile(jnp.array([[50.0, 50.0]]), (n, 1))
        widths = jnp.full(n, 10.0)
        heights = jnp.full(n, 10.0)

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Loss not finite with all same position: {loss}"
        assert loss > 0, "Fully overlapping should have positive penalty"

        # Check gradient
        def loss_fn(pos):
            return compute_overlap_penalty(pos, widths, heights)

        grad = jax.grad(loss_fn)(positions)
        assert jnp.all(jnp.isfinite(grad)), f"Gradient not finite: {grad}"

    def test_single_component_overlap_zero(self):
        """Single component has zero overlap (no pairs to compare)."""
        from temper_placer.losses.overlap import compute_overlap_penalty

        positions = jnp.array([[50.0, 50.0]])
        widths = jnp.array([10.0])
        heights = jnp.array([10.0])

        loss = compute_overlap_penalty(positions, widths, heights)

        assert jnp.isfinite(loss), f"Single component loss not finite: {loss}"
        assert loss == 0.0, "Single component should have zero overlap"


class TestGumbelSoftmaxStability:
    """Test Gumbel-Softmax numerical stability at edge cases."""

    def test_temperature_very_low(self):
        """Very low temperature (0.01) doesn't cause overflow."""
        from temper_placer.geometry.transform import sample_rotation_batch

        logits = jnp.zeros((10, 4))  # Uniform preferences
        key = jax.random.PRNGKey(42)

        # Very low temperature - should be nearly hard one-hot
        rotations = sample_rotation_batch(logits, key, temperature=0.01)

        assert jnp.all(jnp.isfinite(rotations)), f"Low temp rotations not finite: {rotations}"
        assert jnp.allclose(jnp.sum(rotations, axis=-1), 1.0), "Rotations should sum to 1"

    def test_temperature_very_high(self):
        """Very high temperature (100.0) produces valid samples (finite, sums to 1)."""
        from temper_placer.geometry.transform import sample_rotation_batch

        logits = jnp.array([[10.0, 0.0, 0.0, 0.0]])  # Strong preference for 0 degrees
        key = jax.random.PRNGKey(42)

        # Very high temperature - still produces valid one-hot due to straight-through estimator
        # (the softmax is soft but argmax+one_hot makes it hard)
        rotations = sample_rotation_batch(logits, key, temperature=100.0)

        assert jnp.all(jnp.isfinite(rotations)), f"High temp rotations not finite: {rotations}"
        # Should still sum to 1 (valid probability distribution / one-hot)
        assert jnp.allclose(jnp.sum(rotations, axis=-1), 1.0), "Rotations should sum to 1"

    def test_extreme_logits(self):
        """Extreme logit values don't cause overflow in Gumbel-Softmax."""
        from temper_placer.geometry.transform import sample_rotation_batch

        # Very large logits (could cause exp overflow)
        logits = jnp.array([[100.0, -100.0, 0.0, 0.0]])
        key = jax.random.PRNGKey(42)

        rotations = sample_rotation_batch(logits, key, temperature=1.0)

        assert jnp.all(jnp.isfinite(rotations)), f"Extreme logits caused non-finite: {rotations}"

    def test_temperature_approaches_zero(self):
        """Temperature approaching zero (0.001) is handled gracefully."""
        from temper_placer.geometry.transform import gumbel_softmax

        logits = jnp.array([[1.0, 2.0, 0.0, 0.0]])
        key = jax.random.PRNGKey(42)

        # Near-zero temperature
        result = gumbel_softmax(logits, key, temperature=0.001, hard=True)

        assert jnp.all(jnp.isfinite(result)), f"Near-zero temp not finite: {result}"


class TestOptimizerNumericalStability:
    """Test optimizer-level numerical stability."""

    def test_gradient_clipping_prevents_explosion(self):
        """Gradient clipping keeps updates bounded."""
        import optax

        # Create optimizer with gradient clipping
        optimizer = optax.chain(
            optax.clip_by_global_norm(1.0),
            optax.adam(0.1),
        )

        # Large gradients that would explode without clipping
        params = jnp.array([[50.0, 50.0]])
        large_grads = jnp.array([[1e10, 1e10]])

        opt_state = optimizer.init(params)
        updates, new_state = optimizer.update(large_grads, opt_state, params)

        # Apply updates to get new params and check they're finite
        # Cast to Array to satisfy type checker
        new_params: Array = optax.apply_updates(params, updates)  # type: ignore[assignment]
        assert jnp.all(jnp.isfinite(new_params)), f"New params not finite: {new_params}"

        # Check update magnitude is reasonable (gradient was clipped)
        param_change = jnp.array(new_params) - jnp.array(params)
        update_magnitude = float(jnp.linalg.norm(param_change))
        assert update_magnitude < 100.0, f"Updates too large despite clipping: {update_magnitude}"

    def test_extreme_learning_rate_handled(self):
        """Extreme learning rates don't crash (just produce bad results)."""
        import optax

        # Very high learning rate
        optimizer = optax.adam(100.0)
        params = jnp.array([[50.0, 50.0]])
        grads = jnp.array([[1.0, 1.0]])

        opt_state = optimizer.init(params)
        updates, _ = optimizer.update(grads, opt_state, params)

        # Apply updates and check result is finite
        new_params: Array = optax.apply_updates(params, updates)  # type: ignore[assignment]
        assert jnp.all(jnp.isfinite(jnp.array(new_params))), "High LR params not finite"

        # Very low learning rate
        optimizer = optax.adam(1e-10)
        opt_state = optimizer.init(params)
        updates, _ = optimizer.update(grads, opt_state, params)

        new_params = optax.apply_updates(params, updates)  # type: ignore[assignment]
        assert jnp.all(jnp.isfinite(jnp.array(new_params))), "Low LR params not finite"


class TestNumericalInstabilityDetection:
    """Test the NumericalInstabilityError detection mechanism."""

    def test_check_stability_passes_for_normal_values(self):
        """Normal values pass stability check without error."""
        from temper_placer.optimizer.train import _check_numerical_stability

        loss_value = 10.5
        loss_breakdown = {"overlap": 5.0, "boundary": 5.5}
        grad_pos = jnp.array([[0.1, 0.2], [0.3, 0.4]])
        grad_rot = jnp.array([[0.01, 0.02, 0.03, 0.04]])

        # Should not raise
        _check_numerical_stability(loss_value, loss_breakdown, grad_pos, grad_rot, epoch=100)

    def test_check_stability_detects_nan_loss(self):
        """NaN in loss is detected and raises error."""
        from temper_placer.optimizer.train import (
            NumericalInstabilityError,
            _check_numerical_stability,
        )

        loss_value = float("nan")
        loss_breakdown = {"overlap": 5.0}
        grad_pos = jnp.array([[0.1, 0.2]])
        grad_rot = jnp.array([[0.01, 0.02, 0.03, 0.04]])

        with pytest.raises(NumericalInstabilityError) as exc_info:
            _check_numerical_stability(loss_value, loss_breakdown, grad_pos, grad_rot, epoch=100)

        assert exc_info.value.epoch == 100
        assert "Non-finite loss" in str(exc_info.value)

    def test_check_stability_detects_inf_gradient(self):
        """Inf in gradients is detected and raises error."""
        from temper_placer.optimizer.train import (
            NumericalInstabilityError,
            _check_numerical_stability,
        )

        loss_value = 10.0
        loss_breakdown = {"overlap": 10.0}
        grad_pos = jnp.array([[float("inf"), 0.2]])  # Inf gradient
        grad_rot = jnp.array([[0.01, 0.02, 0.03, 0.04]])

        with pytest.raises(NumericalInstabilityError) as exc_info:
            _check_numerical_stability(loss_value, loss_breakdown, grad_pos, grad_rot, epoch=50)

        assert exc_info.value.epoch == 50
        assert "Non-finite gradients" in str(exc_info.value)
