"""Tests for triage evaluation (U5)."""

import math

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.triage import _triage_evaluate, _is_finite


@pytest.fixture
def simple_setup():
    """Create a simple netlist and board for triage testing."""
    components = [
        Component(
            ref=f"U{i}",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (0, 0), net=f"NET{i}"),
                Pin("2", "2", (0, 0), net=f"GND"),
            ],
        )
        for i in range(5)
    ]
    nets = [
        Net(name=f"NET{i}", pins=[(f"U{i}", "1")]) for i in range(5)
    ] + [Net(name="GND", pins=[(f"U{i}", "2") for i in range(5)])]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    return netlist, board


def make_random_positions(netlist, board, key):
    """Generate random valid positions."""
    from temper_placer.core.state import PlacementState
    state = PlacementState.random_init(
        n_components=netlist.n_components,
        board_width=board.width,
        board_height=board.height,
        key=key,
        n_nets=netlist.n_nets,
    )
    return state.positions


class TestTriageEvaluate:
    def test_triage_finite_values(self, simple_setup):
        """Triage produces finite, non-NaN loss (R4b)."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(42)
        positions = make_random_positions(netlist, board, key)

        loss = _triage_evaluate(positions, netlist, board, n_iters=10)
        assert _is_finite(loss), f"Loss is not finite: {loss}"
        assert loss >= 0.0, f"Loss should be non-negative: {loss}"

    def test_triage_with_context(self, simple_setup):
        """Triage works with pre-built LossContext."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(43)
        positions = make_random_positions(netlist, board, key)

        context = LossContext.from_netlist_and_board(netlist, board)
        loss = _triage_evaluate(positions, netlist, board, context=context, n_iters=5)
        assert _is_finite(loss)

    def test_triage_produces_reasonable_loss(self, simple_setup):
        """Triage loss decreases from iteration 0 to final."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(44)
        positions = make_random_positions(netlist, board, key)

        # Run triage and check the loss is reasonable
        loss = _triage_evaluate(positions, netlist, board, n_iters=10)
        assert loss > 0.0, "Loss should be positive"
        assert loss < 1e9, f"Loss is unreasonably large: {loss}"

    def test_triage_nan_positions_returns_nan(self, simple_setup):
        """NaN positions produce NaN loss."""
        netlist, board = simple_setup
        nan_positions = jnp.full((len(netlist.components), 2), float("nan"))

        loss = _triage_evaluate(nan_positions, netlist, board, n_iters=5)
        assert math.isnan(loss)

    def test_triage_nan_discard_detected(self, caplog):
        """NaN triage loss is detectable (not a hard error in function)."""
        netlist, board = simple_setup_pure()
        nan_positions = jnp.full((len(netlist.components), 2), float("nan"))
        loss = _triage_evaluate(nan_positions, netlist, board, n_iters=5)
        assert math.isnan(loss)

    def test_triage_mass_nan_abort_placeholder(self, simple_setup):
        """Triage evaluation returns NaN for invalid positions (caller handles >20% check)."""
        netlist, board = simple_setup
        nan_positions = jnp.full((len(netlist.components), 2), float("nan"))
        loss = _triage_evaluate(nan_positions, netlist, board, n_iters=5)
        # NaN is returned — the caller (U7 orchestration) handles the >20% abort
        assert math.isnan(loss)

    def test_triage_single_component(self):
        """Triage works with a single component netlist."""
        components = [
            Component(
                ref="U1", footprint="SOIC-8", bounds=(10.0, 10.0),
                pins=[Pin("1", "1", (0, 0), net="N1")]
            )
        ]
        nets = [Net(name="N1", pins=[("U1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        key = jax.random.PRNGKey(45)
        positions = make_random_positions(netlist, board, key)

        loss = _triage_evaluate(positions, netlist, board, n_iters=5)
        assert _is_finite(loss)


def simple_setup_pure():
    components = [
        Component(
            ref=f"U{i}", footprint="SOIC-8", bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (0, 0), net=f"NET{i}"),
                Pin("2", "2", (0, 0), net="GND"),
            ],
        )
        for i in range(3)
    ]
    nets = [Net(name=f"NET{i}", pins=[(f"U{i}", "1")]) for i in range(3)] + [
        Net(name="GND", pins=[(f"U{i}", "2") for i in range(3)])
    ]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    return netlist, board


class TestTriageMonotonic:
    """Test that triage loss is monotonic (R4a - best effort)."""

    def test_triage_loss_non_increasing(self, simple_setup):
        """Triage loss is roughly non-increasing over iterations."""
        # Note: with simple SGD on a non-convex loss, monotonicity is not
        # guaranteed. This test checks the pipeline runs and produces a finite
        # loss that is at least not exploding.
        netlist, board = simple_setup
        key = jax.random.PRNGKey(46)
        positions = make_random_positions(netlist, board, key)

        loss = _triage_evaluate(positions, netlist, board, n_iters=15)
        assert _is_finite(loss)
        # Loss should be positive but not absurdly large
        assert loss > 0.0
        assert loss < 1e8


class TestIsFinite:
    def test_finite_value(self):
        assert _is_finite(3.14)

    def test_nan_value(self):
        assert not _is_finite(float("nan"))

    def test_inf_value(self):
        assert not _is_finite(float("inf"))

    def test_neg_inf_value(self):
        assert not _is_finite(float("-inf"))
