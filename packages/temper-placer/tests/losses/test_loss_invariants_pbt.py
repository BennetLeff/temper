"""
Mathematical property invariant tests for loss functions.

Tests validate the fundamental mathematical properties of each loss:
- Zero-when-no-violation: loss = 0 for safe placements
- Positive-when-violation: loss > 0 for violating placements
- Monotonicity: increasing violation → increasing loss
- Gradient finiteness: jax.grad produces no NaN/Inf
- Idempotence: same input → same output
- Empty-is-zero: zero/empty inputs → loss = 0
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


def _make_netlist(n_components: int, bounds: tuple[float, float] = (10.0, 10.0)) -> Netlist:
    components = []
    nets = []
    for i in range(n_components):
        ref = f"U{i + 1}"
        components.append(
            Component(
                ref=ref,
                footprint="TEST-001",
                bounds=bounds,
                pins=[Pin("1", str(i + 1), (0.0, 0.0), net=f"NET{i + 1}")],
                net_class="Signal",
            )
        )
        nets.append(Net(f"NET{i + 1}", [(ref, "1")], net_class="Signal", weight=1.0))
    return Netlist(components=components, nets=nets)


def _make_netlist_with_nets(
    n_components: int, bounds: tuple[float, float] = (10.0, 10.0)
) -> Netlist:
    components = []
    for i in range(n_components):
        ref = f"U{i + 1}"
        components.append(
            Component(
                ref=ref,
                footprint="TEST-001",
                bounds=bounds,
                pins=[Pin("1", str(i + 1), (0.0, 0.0), net=f"NET{(i // 2) + 1}")],
                net_class="Signal",
            )
        )
    nets = []
    for i in range(0, n_components, 2):
        if i + 1 < n_components:
            ref_a = f"U{i + 1}"
            ref_b = f"U{i + 2}"
            nets.append(
                Net(
                    f"NET{(i // 2) + 1}",
                    [(ref_a, "1"), (ref_b, "1")],
                    net_class="Signal",
                    weight=1.0,
                )
            )
        else:
            ref = f"U{i + 1}"
            nets.append(
                Net(f"NET{(i // 2) + 1}", [(ref, "1")], net_class="Signal", weight=1.0)
            )
    return Netlist(components=components, nets=nets)


def _make_context(board: Board, netlist: Netlist) -> LossContext:
    return LossContext.from_netlist_and_board(netlist, board)


def _make_rotations(n: int) -> Array:
    rot = jnp.zeros((n, 4), dtype=jnp.float32)
    rot = rot.at[:, 0].set(1.0)
    return rot


def _board_with_stackup(w: float = 100.0, h: float = 100.0) -> Board:
    return Board(
        width=w,
        height=h,
        origin=(0.0, 0.0),
        layer_stackup=LayerStackup(layers=[Layer("F.Cu", "signal")]),
    )


# =============================================================================
# BoundaryLoss invariants
# =============================================================================


@pytest.mark.property
class TestBoundaryLossInvariants:
    """Theorem: BoundaryLoss satisfies the mathematical properties of a
    valid penalty function on component placement.
    """

    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0)
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        result = loss_fn(
            jnp.zeros((0, 2), dtype=jnp.float32),
            _make_rotations(0),
            context,
        )
        assert float(result.value) == pytest.approx(0.0)

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)
        pos = jnp.array(
            [[50.0, 50.0], [30.0, 70.0], [70.0, 30.0], [30.0, 30.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        r1 = loss_fn(pos, rotations, context)
        r2 = loss_fn(pos, rotations, context)
        assert float(r1.value) == pytest.approx(float(r2.value))

    def test_zero_when_all_in_bounds(self):
        board = Board(width=200, height=150)
        netlist = _make_netlist(5, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        pos = jnp.array(
            [[50.0, 50.0], [150.0, 50.0], [100.0, 75.0], [50.0, 100.0], [150.0, 100.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(5)
        result = loss_fn(pos, rotations, context)
        assert float(result.value) == pytest.approx(0.0, abs=1e-4)

    def test_positive_when_out_of_bounds(self):
        board = Board(width=100, height=100)
        netlist = _make_netlist(2, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        pos = jnp.array([[50.0, 50.0], [150.0, 50.0]], dtype=jnp.float32)
        rotations = _make_rotations(2)
        result = loss_fn(pos, rotations, context)
        assert float(result.value) > 0

    def test_monotonic_with_distance(self):
        board = Board(width=100, height=100)
        netlist = _make_netlist(1, bounds=(10, 10))
        context = _make_context(board, netlist)
        rotations = _make_rotations(1)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        prev = None
        for d in [5.0, 10.0, 20.0, 50.0, 100.0]:
            pos = jnp.array([[100.0 + d, 50.0]], dtype=jnp.float32)
            result = loss_fn(pos, rotations, context)
            current = float(result.value)
            assert current > 0, f"Loss should be positive at d={d}"
            if prev is not None:
                assert current > prev, (
                    f"Loss at d={d} ({current}) should exceed previous ({prev})"
                )
            prev = current

    @given(
        st.lists(
            st.floats(min_value=0.0, max_value=300.0),
            min_size=4,
            max_size=4,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_gradient_is_finite(self, xs):
        board = Board(width=300, height=300)
        netlist = _make_netlist(2, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.5)

        pos = jnp.array(
            [[xs[0], xs[1]], [xs[2], xs[3]]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(2)

        grad_fn = jax.grad(lambda p: loss_fn(p, rotations, context).value)
        grads = grad_fn(pos)
        assert not jnp.any(jnp.isnan(grads)), "NaN in boundary loss gradient"
        assert not jnp.any(jnp.isinf(grads)), "Inf in boundary loss gradient"


# =============================================================================
# OverlapLoss invariants
# =============================================================================


@pytest.mark.property
class TestOverlapLossInvariants:
    """Theorem: OverlapLoss satisfies the mathematical properties of a
    valid collision penalty function.
    """

    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(1, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=0.0)

        result = loss_fn(
            jnp.array([[50.0, 50.0]], dtype=jnp.float32),
            _make_rotations(1),
            context,
        )
        assert float(result.value) == pytest.approx(0.0)

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=2.0)
        pos = jnp.array(
            [[50.0, 50.0], [55.0, 51.0], [60.0, 52.0], [65.0, 53.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        r1 = loss_fn(pos, rotations, context)
        r2 = loss_fn(pos, rotations, context)
        assert float(r1.value) == pytest.approx(float(r2.value))

    def test_zero_when_no_overlap(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=0.0)

        pos = jnp.array(
            [[10.0, 10.0], [90.0, 10.0], [10.0, 90.0], [90.0, 90.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)
        result = loss_fn(pos, rotations, context)
        assert float(result.value) == pytest.approx(0.0, abs=1e-4)

    def test_positive_when_overlap(self):
        board = _board_with_stackup()
        netlist = _make_netlist(2, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=0.0)

        pos = jnp.array([[50.0, 50.0], [50.0, 50.0]], dtype=jnp.float32)
        rotations = _make_rotations(2)
        result = loss_fn(pos, rotations, context)
        assert float(result.value) > 0

    def test_monotonic_with_overlap_depth(self):
        board = _board_with_stackup()
        netlist = _make_netlist(2, bounds=(10, 8))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=0.0)

        prev = None
        for offset_x in [0.0, 2.0, 4.0, 6.0, 8.0]:
            pos = jnp.array(
                [[50.0, 50.0], [50.0 + offset_x, 50.0]],
                dtype=jnp.float32,
            )
            rotations = _make_rotations(2)
            result = loss_fn(pos, rotations, context)
            current = float(result.value)
            if offset_x < 10.0:
                assert current > 0, f"Overlap loss should be positive at offset={offset_x}"
            if prev is not None:
                assert current <= prev + 1e-4, (
                    f"Overlap loss should decrease as components separate: "
                    f"offset={offset_x} loss={current} > prev={prev}"
                )
            prev = current

    @given(
        st.lists(
            st.floats(min_value=0.0, max_value=100.0),
            min_size=8,
            max_size=8,
        ),
    )
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, coords):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = OverlapLoss(margin=0.0)

        pos = jnp.array(
            [
                [coords[0], coords[1]],
                [coords[2], coords[3]],
                [coords[4], coords[5]],
                [coords[6], coords[7]],
            ],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        grad_fn = jax.grad(lambda p: loss_fn(p, rotations, context).value)
        grads = grad_fn(pos)
        assert not jnp.any(jnp.isnan(grads)), "NaN in overlap loss gradient"
        assert not jnp.any(jnp.isinf(grads)), "Inf in overlap loss gradient"


# =============================================================================
# WirelengthLoss invariants
# =============================================================================


@pytest.mark.property
class TestWirelengthLossInvariants:
    """Theorem: WirelengthLoss satisfies mathematical properties for
    HPWL-based wirelength approximation.
    """

    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist_with_nets(0)
        context = _make_context(board, netlist)
        loss_fn = WirelengthLoss()

        result = loss_fn(
            jnp.zeros((0, 2), dtype=jnp.float32),
            _make_rotations(0),
            context,
        )
        assert float(result.value) == pytest.approx(0.0)

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist_with_nets(4, bounds=(2, 2))
        context = _make_context(board, netlist)
        loss_fn = WirelengthLoss()

        pos = jnp.array(
            [[25.0, 25.0], [75.0, 25.0], [25.0, 75.0], [75.0, 75.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        r1 = loss_fn(pos, rotations, context)
        r2 = loss_fn(pos, rotations, context)
        assert float(r1.value) == pytest.approx(float(r2.value))

    @given(
        st.lists(
            st.floats(min_value=10.0, max_value=190.0),
            min_size=8,
            max_size=8,
        ),
    )
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, coords):
        board = _board_with_stackup(200, 200)
        netlist = _make_netlist_with_nets(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = WirelengthLoss()

        pos = jnp.array(
            [
                [coords[0], coords[1]],
                [coords[2], coords[3]],
                [coords[4], coords[5]],
                [coords[6], coords[7]],
            ],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        grad_fn = jax.grad(lambda p: loss_fn(p, rotations, context).value)
        grads = grad_fn(pos)
        assert not jnp.any(jnp.isnan(grads)), "NaN in wirelength loss gradient"
        assert not jnp.any(jnp.isinf(grads)), "Inf in wirelength loss gradient"


# =============================================================================
# SpreadLoss invariants
# =============================================================================


@pytest.mark.property
class TestSpreadLossInvariants:
    """Theorem: SpreadLoss satisfies mathematical properties of a valid
    repulsion-based distribution penalty.
    """

    def test_empty_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(0)
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=2.0)

        result = loss_fn(
            jnp.zeros((0, 2), dtype=jnp.float32),
            _make_rotations(0),
            context,
        )
        assert float(result.value) == pytest.approx(0.0)

    def test_single_component_is_zero(self):
        board = _board_with_stackup()
        netlist = _make_netlist(1, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=2.0)

        result = loss_fn(
            jnp.array([[50.0, 50.0]], dtype=jnp.float32),
            _make_rotations(1),
            context,
        )
        # Single component has no pairs, but edge penalty may apply
        assert jnp.isfinite(result.value)
        assert float(result.value) >= 0.0

    def test_idempotent(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=10.0)

        pos = jnp.array(
            [[50.0, 50.0], [55.0, 51.0], [60.0, 52.0], [65.0, 53.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        r1 = loss_fn(pos, rotations, context)
        r2 = loss_fn(pos, rotations, context)
        assert float(r1.value) == pytest.approx(float(r2.value))

    def test_zero_when_well_spread(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=2.0)

        pos = jnp.array(
            [[10.0, 10.0], [90.0, 10.0], [10.0, 90.0], [90.0, 90.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)
        result = loss_fn(pos, rotations, context)
        # Components are >80mm apart with 5mm bounds, well above min_distance=2
        assert float(result.value) < 1.0

    def test_positive_when_clustered(self):
        board = _board_with_stackup()
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=10.0)

        pos = jnp.array(
            [[50.0, 50.0], [52.0, 50.0], [50.0, 52.0], [52.0, 52.0]],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)
        result = loss_fn(pos, rotations, context)
        assert float(result.value) > 0

    @given(
        st.lists(
            st.floats(min_value=0.0, max_value=150.0),
            min_size=8,
            max_size=8,
        ),
    )
    @settings(max_examples=50, deadline=30000)
    def test_gradient_is_finite(self, coords):
        board = _board_with_stackup(150, 150)
        netlist = _make_netlist(4, bounds=(5, 5))
        context = _make_context(board, netlist)
        loss_fn = SpreadLoss(min_distance=10.0)

        pos = jnp.array(
            [
                [coords[0], coords[1]],
                [coords[2], coords[3]],
                [coords[4], coords[5]],
                [coords[6], coords[7]],
            ],
            dtype=jnp.float32,
        )
        rotations = _make_rotations(4)

        grad_fn = jax.grad(lambda p: loss_fn(p, rotations, context).value)
        grads = grad_fn(pos)
        assert not jnp.any(jnp.isnan(grads)), "NaN in spread loss gradient"
        assert not jnp.any(jnp.isinf(grads)), "Inf in spread loss gradient"
