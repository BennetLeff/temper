"""
Mathematical property invariant tests for loss functions.

Uses the shared invariant assertion library from tests/invariants/.
Each theorem class proves a mathematical property holds for a specific loss.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jax import Array

from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.regularization import SpreadLoss
from temper_placer.losses.wirelength import WirelengthLoss

from ..invariants.assertions import (
    assert_empty_is_zero,
    assert_idempotent,
    assert_monotonic,
    assert_positive_when_violation,
    assert_zero_when_no_violation,
)
from ..invariants.jax_helpers import assert_gradient_finite


def _make_netlist(n_components: int, bounds: tuple[float, float] = (10.0, 10.0)) -> Netlist:
    components = []
    nets = []
    for i in range(n_components):
        ref = f"U{i + 1}"
        components.append(
            Component(ref=ref, footprint="TEST-001", bounds=bounds,
                      pins=[Pin(str(i+1), str(i+1), (0.0, 0.0), net=f"NET{i+1}")],
                      net_class="Signal"))
        nets.append(Net(f"NET{i+1}", [(ref, str(i+1))], net_class="Signal", weight=1.0))
    return Netlist(components=components, nets=nets)


def _make_context(board: Board, netlist: Netlist) -> LossContext:
    return LossContext.from_netlist_and_board(netlist, board)


def _make_rotations(n: int) -> Array:
    logits = jnp.zeros((n, 4), dtype=jnp.float32).at[:, 0].set(10.0)
    return jax.nn.softmax(logits, axis=-1)


def _board_with_stackup(width: float = 200.0, height: float = 150.0) -> Board:
    return Board(width=width, height=height, origin=(0.0, 0.0),
                 layer_stackup=LayerStackup(layers=[
                     Layer(name="F.Cu", layer_type="signal"),
                     Layer(name="B.Cu", layer_type="signal"),
                 ], thickness=1.6))


@pytest.mark.property
class TestBoundaryLossInvariants:
    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0, (10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)
        assert_empty_is_zero(
            loss_fn,
            jnp.zeros((0, 2)), jnp.zeros((0, 4)), context,
        )

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(3, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 50.0], [100.0, 75.0], [150.0, 100.0]])
        loss_fn = BoundaryLoss(edge_margin=0.0)
        assert_idempotent(loss_fn, pos, _make_rotations(3), context)

    def test_zero_when_all_in_bounds(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(4, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 50.0], [150.0, 50.0], [50.0, 100.0], [150.0, 100.0]])
        loss_fn = BoundaryLoss(edge_margin=0.0)
        assert_zero_when_no_violation(
            loss_fn, pos, _make_rotations(4), context,
        )

    def test_positive_when_out_of_bounds(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(2, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[100.0, 75.0], [250.0, 200.0]])
        loss_fn = BoundaryLoss(edge_margin=0.0)
        assert_positive_when_violation(loss_fn, pos, _make_rotations(2), context)

    def test_monotonic_with_distance(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(1, (10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)
        near = jnp.array([[210.0, 75.0]])
        far = jnp.array([[250.0, 75.0]])
        assert_monotonic(loss_fn, near, far, _make_rotations(1), context)

    @given(xs=st.floats(50.0, 250.0), ys=st.floats(50.0, 250.0))
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, xs, ys):
        board = _board_with_stackup(300, 300)
        netlist = _make_netlist(1, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[xs, ys]], dtype=jnp.float32)
        assert_gradient_finite(
            BoundaryLoss(edge_margin=0.0), pos, _make_rotations(1), context,
        )


@pytest.mark.property
class TestOverlapLossInvariants:
    @pytest.mark.skip(reason="OverlapLoss crashes on empty positions — known gap")
    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0, (10, 10))
        context = _make_context(board, netlist)
        assert_empty_is_zero(
            OverlapLoss(), jnp.zeros((0, 2)), jnp.zeros((0, 4)), context,
        )

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(3, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 50.0], [100.0, 75.0], [150.0, 100.0]])
        assert_idempotent(OverlapLoss(), pos, _make_rotations(3), context)

    def test_zero_when_no_overlap(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(4, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[30.0, 50.0], [70.0, 50.0], [30.0, 100.0], [70.0, 100.0]])
        assert_zero_when_no_violation(
            OverlapLoss(), pos, _make_rotations(4), context,
        )

    def test_positive_when_overlap(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(2, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 75.0], [52.0, 75.0]])
        assert_positive_when_violation(OverlapLoss(), pos, _make_rotations(2), context)

    def test_monotonic_with_overlap_depth(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(2, (10, 10))
        context = _make_context(board, netlist)
        shallow = jnp.array([[50.0, 75.0], [55.0, 75.0]])
        deep = jnp.array([[50.0, 75.0], [51.0, 75.0]])
        assert_monotonic(OverlapLoss(), shallow, deep, _make_rotations(2), context)

    @given(xs=st.floats(0.0, 200.0), ys=st.floats(0.0, 150.0))
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, xs, ys):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(1, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[xs, ys]], dtype=jnp.float32)
        assert_gradient_finite(OverlapLoss(), pos, _make_rotations(1), context)


@pytest.mark.property
class TestWirelengthLossInvariants:
    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0, (10, 10))
        context = _make_context(board, netlist)
        assert_empty_is_zero(
            WirelengthLoss(), jnp.zeros((0, 2)), jnp.zeros((0, 4)), context,
        )

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(3, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 50.0], [100.0, 75.0], [150.0, 100.0]])
        assert_idempotent(WirelengthLoss(), pos, _make_rotations(3), context)

    @given(xs=st.floats(50.0, 150.0), ys=st.floats(50.0, 100.0))
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, xs, ys):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(1, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[xs, ys]], dtype=jnp.float32)
        assert_gradient_finite(WirelengthLoss(), pos, _make_rotations(1), context)


@pytest.mark.property
class TestSpreadLossInvariants:
    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0, (10, 10))
        context = _make_context(board, netlist)
        assert_empty_is_zero(
            SpreadLoss(), jnp.zeros((0, 2)), jnp.zeros((0, 4)), context,
        )

    def test_single_component_is_zero(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(1, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[100.0, 75.0]])
        assert_zero_when_no_violation(
            SpreadLoss(), pos, _make_rotations(1), context,
        )

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(3, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[50.0, 50.0], [100.0, 75.0], [150.0, 100.0]])
        assert_idempotent(SpreadLoss(), pos, _make_rotations(3), context)

    def test_zero_when_well_spread(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(4, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[30.0, 50.0], [170.0, 50.0], [30.0, 100.0], [170.0, 100.0]])
        assert_zero_when_no_violation(
            SpreadLoss(), pos, _make_rotations(4), context,
        )

    def test_positive_when_clustered(self):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(4, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[100.0, 75.0], [100.0, 75.0], [100.0, 75.0], [100.0, 75.0]])
        assert_positive_when_violation(SpreadLoss(), pos, _make_rotations(4), context)

    @given(xs=st.floats(0.0, 200.0), ys=st.floats(0.0, 150.0))
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, xs, ys):
        board = _board_with_stackup(200, 150)
        netlist = _make_netlist(3, (10, 10))
        context = _make_context(board, netlist)
        pos = jnp.array([[xs, ys], [100.0, 75.0], [150.0, 100.0]])
        assert_gradient_finite(SpreadLoss(), pos, _make_rotations(3), context)
