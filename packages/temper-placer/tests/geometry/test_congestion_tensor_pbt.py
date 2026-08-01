"""Property-based tests for the Rust-backed CongestionTensor.

Each property is a mathematical invariant of the PathFinder history
cost that must hold for arbitrary inputs (per the migration roadmap's
PBT discipline — 5 properties for this module):

1. ``cost`` is monotonically non-decreasing in usage
2. ``cost >= 1.0`` for every cell
3. ``increment`` followed by ``decay(1.0)`` is the identity
4. ``increment`` is linear in the weight argument
5. ``reset`` zeroes the tensor

The properties exercise the wrapper (``temper_placer.router_v6.
congestion_tensor``), which is the consumer surface the router sees.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.congestion_tensor import CongestionTensor

MAX_EXAMPLES = 200

_nonneg = st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False)
_weight = st.floats(min_value=-1e2, max_value=1e2, allow_nan=False, allow_infinity=False)


@given(st.integers(1, 32), st.integers(1, 32))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_cost_monotonic_in_usage(rows: int, cols: int) -> None:
    t = CongestionTensor.zeros(rows, cols)
    prev = t.cost(0, 0)
    for _ in range(1, 200):
        t.increment(0, 0, 0.5)
        cur = t.cost(0, 0)
        assert cur >= prev
        prev = cur


@given(st.integers(1, 32), st.integers(1, 32), _nonneg)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_cost_never_below_one(rows: int, cols: int, usage: float) -> None:
    t = CongestionTensor.zeros(rows, cols)
    t.increment(0, 0, usage)
    assert t.cost(0, 0) >= 1.0


@given(st.integers(1, 32), st.integers(1, 32), _nonneg)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_increment_then_decay_factor_one_is_identity(
    rows: int, cols: int, usage: float
) -> None:
    t = CongestionTensor.zeros(rows, cols)
    t.increment(3 % rows, 5 % cols, usage)
    before = t.array.copy()
    t.decay(1.0)
    assert (t.array == before).all()


@given(st.integers(1, 32), st.integers(1, 32), _weight, _weight)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_increment_linear_in_weight(rows: int, cols: int, w1: float, w2: float) -> None:
    t = CongestionTensor.zeros(rows, cols)
    t.increment(0, 0, w1)
    t.increment(0, 0, w2)
    # f32 accumulation: each add rounds at ~2^-24 relative, so the bound
    # scales with the operands, not the (possibly near-zero) sum.
    eps = 2.0 ** -24
    tol = 1e-6 + eps * 2.0 * (abs(w1) + abs(w2))
    assert abs(t.array[0, 0] - (w1 + w2)) <= tol


@given(st.integers(1, 32), st.integers(1, 32), _nonneg)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_reset_zeroes_every_cell(rows: int, cols: int, usage: float) -> None:
    t = CongestionTensor.zeros(rows, cols)
    for i in range(rows):
        for j in range(cols):
            t.increment(i, j, usage + (i + j) % 7)
    t.reset()
    assert (t.array == 0.0).all()
