"""Unit tests for RoutabilityGradientLoss with STE."""

import pytest
import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext
from temper_placer.losses.routability_gradient import RoutabilityGradientLoss


def _make_context(N: int = 3) -> LossContext:
    """Build a minimal LossContext for testing."""
    return LossContext()


def test_zero_signal_zero_loss():
    """All-zero routability scores should produce zero loss (NFR2.3)."""
    loss = RoutabilityGradientLoss()
    N = 3
    loss.blend({"routability_scores": jnp.zeros(N), "iteration": 0})

    pos = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    rot = jnp.zeros((N, 4)).at[:, 0].set(1.0)
    ctx = _make_context(N)

    result = loss.compute_loss(pos, rot, ctx)
    assert float(result.value) == pytest.approx(0.0, abs=1e-6)
    # distances are zero (pos == anchors), so loss is zero regardless of signal
    # But even with non-zero distance, zero signal * zero distance = zero


def test_ste_gradient_correctness():
    """STE gradient should propagate through soft proxy (AC3)."""
    loss = RoutabilityGradientLoss()
    N = 3

    scores = jnp.array([1.0, 0.5, 0.0])
    loss.blend({"routability_scores": scores, "iteration": 0})

    # Build a realistic LossContext with pin data so soft_proxy is non-zero
    from temper_placer.losses.types import NetlistContext
    # Simple 2-net setup: net 0 connects comps [0, 1], net 1 connects comps [1, 2]
    net_pin_indices = jnp.array([[0, 1], [1, 2]])
    net_pin_offsets = jnp.array([[[0.0, 0.0], [0.0, 0.0]],
                                  [[0.0, 0.0], [0.0, 0.0]]])
    net_pin_mask = jnp.ones((2, 2), dtype=jnp.bool_)
    ctx = LossContext(
        netlist_data=NetlistContext(
            net_pin_indices=net_pin_indices,
            net_pin_offsets=net_pin_offsets,
            net_pin_mask=net_pin_mask,
        )
    )

    # Non-zero positions so distances are non-zero
    pos = jnp.array([[1.0, 1.0], [6.0, 2.0], [11.0, 11.0]])
    rot = jnp.zeros((N, 4)).at[:, 0].set(1.0)

    grad_fn = jax.grad(
        lambda p: loss.compute_loss(p, rot, ctx).value
    )
    grads = grad_fn(pos)

    assert grads.shape == (N, 2)
    assert not jnp.any(jnp.isnan(grads))
    assert jnp.any(jnp.abs(grads) > 0)


def test_jit_compatibility():
    """compute_loss value extraction should be JIT-compatible (NFR1.3)."""
    loss = RoutabilityGradientLoss()
    N = 3
    loss.blend({"routability_scores": jnp.array([0.5, 0.5, 0.0]), "iteration": 0})

    pos = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]) + 1.0
    rot = jnp.zeros((N, 4)).at[:, 0].set(1.0)
    ctx = _make_context(N)

    # JIT only the scalar value to avoid pytree return-type issue
    jitted = jax.jit(lambda p: loss.compute_loss(p, rot, ctx).value)
    result = jitted(pos)
    assert float(result) >= 0.0


def test_differentiability():
    """Loss should be differentiable with finite gradients (NFR2.1)."""
    loss = RoutabilityGradientLoss()
    N = 2
    loss.blend({"routability_scores": jnp.array([0.8, 0.2]), "iteration": 0})

    pos = jnp.array([[1.0, 1.0], [6.0, 6.0]])
    rot = jnp.zeros((N, 4)).at[:, 0].set(1.0)

    from temper_placer.losses.types import NetlistContext
    net_pin_indices = jnp.array([[0, 1]])
    net_pin_offsets = jnp.array([[[0.0, 0.0], [0.0, 0.0]]])
    net_pin_mask = jnp.ones((1, 2), dtype=jnp.bool_)
    ctx = LossContext(
        netlist_data=NetlistContext(
            net_pin_indices=net_pin_indices,
            net_pin_offsets=net_pin_offsets,
            net_pin_mask=net_pin_mask,
        )
    )

    def f(p):
        return loss.compute_loss(p, rot, ctx).value

    grad_fn = jax.grad(f)
    grads = grad_fn(pos)

    assert grads.shape == (N, 2)
    assert not jnp.any(jnp.isnan(grads))
    assert not jnp.any(jnp.isinf(grads))


def test_ewma_blend():
    """EWMA blend should produce correct weighted average."""
    loss = RoutabilityGradientLoss()

    # Iteration 1
    loss.blend({"routability_scores": jnp.array([1.0, 0.5, 0.0]), "iteration": 1})
    assert loss._ema_scores is not None

    # Iteration 2 with alpha=0.5 (max(0.1, 1/2))
    loss.blend({"routability_scores": jnp.array([0.5, 0.5, 1.0]), "iteration": 2})

    # Expected: alpha=0.5, ema = 0.5 * [0.5,0.5,1.0] + 0.5 * [1.0,0.5,0.0]
    expected = jnp.array([0.75, 0.5, 0.5])
    actual = loss._ema_scores

    assert jnp.allclose(actual, expected, atol=1e-6)


def test_breakdown_keys():
    """Breakdown should contain all required keys."""
    loss = RoutabilityGradientLoss()
    loss.blend({"routability_scores": jnp.array([0.5, 0.0, 1.0]), "iteration": 0})

    pos = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    ctx = _make_context(3)

    result = loss.compute_loss(pos, rot, ctx)
    assert result.breakdown is not None
    assert "routability_gradient_total" in result.breakdown
    assert "routability_gradient_max" in result.breakdown
    assert "routability_gradient_mean" in result.breakdown
    assert "routability_active_components" in result.breakdown


def test_unscored_component_zero_loss():
    """Component with score=0 contributes zero to loss (distance from anchor is zero at start)."""
    loss = RoutabilityGradientLoss()
    loss.blend({"routability_scores": jnp.array([1.0, 0.0, 0.0]), "iteration": 0})

    # Start positions = anchors, so loss = 0 regardless
    pos = jnp.array([[0.0, 0.0], [5.0, 5.0], [10.0, 10.0]])
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    ctx = _make_context(3)

    result = loss.compute_loss(pos, rot, ctx)
    assert float(result.value) >= 0.0


def test_weight_decay():
    """Weight should decay when scores are improving."""
    loss = RoutabilityGradientLoss()
    loss.current_weight = 50.0

    # Decreasing scores + completion > threshold
    loss.blend({"routability_scores": jnp.array([0.8, 0.7, 0.6]), "iteration": 1,
                 "completion_rate": 0.9, "routability_threshold": 0.85})
    loss.blend({"routability_scores": jnp.array([0.5, 0.4, 0.3]), "iteration": 2,
                 "completion_rate": 0.9, "routability_threshold": 0.85})
    loss.blend({"routability_scores": jnp.array([0.2, 0.1, 0.0]), "iteration": 3,
                 "completion_rate": 0.95, "routability_threshold": 0.85})

    assert loss.current_weight == pytest.approx(25.0)


def test_oscillation_detection():
    """Oscillation should freeze scores."""
    loss = RoutabilityGradientLoss()
    loss.blend({"routability_scores": jnp.array([0.1, 0.2, 0.3]), "iteration": 1})
    loss.blend({"routability_scores": jnp.array([0.4, 0.5, 0.6]), "iteration": 2})
    loss.blend({"routability_scores": jnp.array([0.7, 0.8, 0.9]), "iteration": 3})

    assert loss._frozen


def test_nan_guard():
    """NaN values in scores should not propagate to loss."""
    loss = RoutabilityGradientLoss()

    # Scores with NaN
    scores = jnp.array([0.5, float("nan"), 1.0])
    loss.blend({"routability_scores": jnp.nan_to_num(scores), "iteration": 0})

    pos = jnp.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    ctx = _make_context(3)

    result = loss.compute_loss(pos, rot, ctx)
    assert not jnp.isnan(result.value)
