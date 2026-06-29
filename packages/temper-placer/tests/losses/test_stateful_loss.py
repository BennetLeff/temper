"""Unit tests for StatefulLossFunction ABC."""

import jax.numpy as jnp
import pytest

from temper_placer.losses.base import LossContext, LossResult, StatefulLossFunction


class _ConcreteStateful(StatefulLossFunction):
    def __init__(self):
        self._scores = None

    @property
    def name(self) -> str:
        return "test_stateful"

    def blend(self, state: dict) -> None:
        self._scores = jnp.asarray(state["scores"])

    def compute_loss(self, _positions, _rotations, _context, _epoch=0, _total_epochs=1, _net_virtual_nodes=None):
        return LossResult(value=jnp.sum(self._scores))


def test_stateful_loss_isinstance_loss_function():
    """Concrete subclass should be an instance of LossFunction."""
    loss = _ConcreteStateful()
    from temper_placer.losses.base import LossFunction
    assert isinstance(loss, LossFunction)


def test_call_delegates_to_compute_loss():
    """__call__ should delegate to compute_loss()."""
    loss = _ConcreteStateful()
    loss.blend({"scores": jnp.array([1.0, 2.0, 3.0])})

    result = loss(jnp.zeros((3, 2)), jnp.zeros((3, 4)), LossContext())
    assert float(result.value) == pytest.approx(6.0)


def test_name_property():
    """name property is inherited from StatefulLossFunction via LossFunction."""
    loss = _ConcreteStateful()
    assert loss.name == "test_stateful"


def test_blend_compute_loss_separation():
    """blend() and compute_loss() are separate; blend updates state."""
    loss = _ConcreteStateful()
    loss.blend({"scores": jnp.array([5.0])})
    result = loss.compute_loss(
        jnp.zeros((1, 2)), jnp.zeros((1, 4)), LossContext()
    )
    assert float(result.value) == pytest.approx(5.0)

    loss.blend({"scores": jnp.array([3.0])})
    result2 = loss.compute_loss(
        jnp.zeros((1, 2)), jnp.zeros((1, 4)), LossContext()
    )
    assert float(result2.value) == pytest.approx(3.0)
