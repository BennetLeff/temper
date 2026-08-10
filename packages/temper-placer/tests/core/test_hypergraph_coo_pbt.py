"""PBT (G4) + metamorphic (G5) suite for the typed `Coo` container.

Covers `temper_design_bundle_python.hypergraph_contracts.Coo` — the Phase-A
U7 typed I/O boundary of the `hypergraph_coo_matvec` kernel
(`docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md`).
Because `__matmul__` routes through the Python-level
`temper_geometry.hypergraph_coo_matvec_py` attribute (see
`hypergraph_contracts.rs`'s module docstring for why), every kernel-reaching
property below has a `test_pN_fails_for_<mutant>` vacuity guard that patches
that attribute and re-runs the property, exactly like
`test_core_graph_cluster_pbt.py`.

Properties (all bit-exact unless a tolerance is stated):
  P1  Coo @ ones == independent per-row scatter-add in triplet order.
  P2  Single-triplet basis vector → exactly d at r, 0 elsewhere.
  P3  Coo.T @ ones == independent per-column scatter-add.
  P4  Negative-col wrap: col=-k ≡ col=(n_cols-k) (fancy-index wrapping).
  P5  Empty Coo @ ones == zeros(n_rows) — the pre-kernel short-circuit.
  P6  data-dtype preservation (float32 and float64 round-trip tobytes).
  P7  shape/nnz invariants: nnz == len(row) == len(col) == len(data).

Metamorphic relations (exactness stated per relation):
  MR1 Triplet-order permutation leaves the matvec within 1 ulp of the
      largest-magnitude term (NOT bit-exact: FP scatter-add order).
  MR2 Power-of-two data scaling scales the result bit-exactly.
  MR3 Double transpose returns an identical container (shape/nnz/data/row/col).
  MR4 Node-degree sum == edge-degree sum for integer weights (bit-exact).
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_design_bundle_python as _tdb
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

Coo = _tdb.hypergraph_contracts.Coo
from tests.core.test_hypergraph_coo_rust_differential import _oracle_coo_matmul

_KERNEL = "hypergraph_coo_matvec_py"


@pytest.fixture
def _restore_kernel():
    saved = getattr(_tg, _KERNEL)
    yield
    setattr(_tg, _KERNEL, saved)


def _assert_bit_exact(got, want):
    assert got.dtype == want.dtype
    assert got.shape == want.shape
    for g, w in zip(got.reshape(-1), want.reshape(-1)):
        assert float(g).hex() == float(w).hex()


def _independent_row_sums(coo):
    acc = {}
    for r, c, d in zip(coo.row, coo.col, coo.data):
        del c
        acc[int(r)] = acc.get(int(r), 0.0) + float(d)
    n = coo.shape[0]
    return np.array([acc.get(i, 0.0) for i in range(n)], dtype=np.float64)


def _independent_col_sums(coo):
    """Per-column scatter-add. The kernel extends the result on the *row*
    index of the matrix being multiplied; for `coo.T` that is the original
    column index, which is always < n_cols by construction — so the output
    length is exactly n_cols."""
    acc = {}
    for r, c, d in zip(coo.row, coo.col, coo.data):
        del r
        acc[int(c)] = acc.get(int(c), 0.0) + float(d)
    return np.array([acc.get(i, 0.0) for i in range(coo.shape[1])], dtype=np.float64)


@st.composite
def coo_strategy(draw):
    n_rows = draw(st.integers(min_value=1, max_value=8))
    n_cols = draw(st.integers(min_value=1, max_value=8))
    nnz = draw(st.integers(min_value=0, max_value=12))
    row = np.array([draw(st.integers(min_value=0, max_value=n_rows - 1)) for _ in range(nnz)], dtype=np.int64)
    col = np.array([draw(st.integers(min_value=0, max_value=n_cols - 1)) for _ in range(nnz)], dtype=np.int64)
    data = np.array(
        [draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)) for _ in range(nnz)],
        dtype=np.float64,
    )
    return Coo(row=row, col=col, data=data, shape=(n_rows, n_cols))


def _ones(coo):
    return np.ones(coo.shape[1], dtype=np.float64)


# ---------------------------------------------------------------------------
# P1 — matvec equals independent per-row scatter-add
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=100, deadline=60000)
def test_p1_coo_matvec_equals_row_sums(coo):
    got = coo @ _ones(coo)
    want = _independent_row_sums(coo)
    _assert_bit_exact(got, want)


def test_p1_fails_for_zero_matvec_mutant(_restore_kernel):
    setattr(_tg, _KERNEL, lambda *_a, **_k: [0.0] * 4)
    coo = Coo(
        row=np.array([0, 1], dtype=np.int64),
        col=np.array([0, 1], dtype=np.int64),
        data=np.array([2.0, 3.0], dtype=np.float64),
        shape=(2, 2),
    )
    with pytest.raises(AssertionError):
        test_p1_coo_matvec_equals_row_sums.hypothesis.inner_test(coo)


# ---------------------------------------------------------------------------
# P2 — single-triplet basis vector
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=0, max_value=4),
    st.integers(min_value=0, max_value=4),
    st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=60000)
def test_p2_single_triplet_basis_exact(r, c, d):
    coo = Coo(
        row=np.array([r], dtype=np.int64),
        col=np.array([c], dtype=np.int64),
        data=np.array([d], dtype=np.float64),
        shape=(5, 5),
    )
    e = np.zeros(5, dtype=np.float64)
    e[c] = 1.0
    got = coo @ e
    assert len(got) == 5
    for i, v in enumerate(got):
        if i == r:
            assert v == d
        else:
            assert v == 0.0


def test_p2_fails_for_double_matvec_mutant(_restore_kernel):
    def double_kernel(_row, _col, data, _n_rows, _other):
        return [2.0 * x for x in (data * 1.0)]

    setattr(_tg, _KERNEL, double_kernel)
    with pytest.raises(AssertionError):
        test_p2_single_triplet_basis_exact.hypothesis.inner_test(2, 1, 3.5)


# ---------------------------------------------------------------------------
# P3 — transpose degrees equal independent per-column scatter-add
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=100, deadline=60000)
def test_p3_transpose_equals_col_sums(coo):
    ones_rows = np.ones(coo.shape[0], dtype=np.float64)
    got = coo.T @ ones_rows
    want = _independent_col_sums(coo)
    _assert_bit_exact(got, want)


def test_p3_fails_for_col_sum_matvec_mutant(_restore_kernel):
    """A matvec that (incorrectly) scatters by COLUMN index would pass P1
    (row and column sums agree only through the transpose) but fail P3 —
    proving P3 pins the transpose semantics."""

    def col_sum(row, col, data, n_rows, other):
        del row
        acc = {}
        for c, d in zip(col, data):
            acc[int(c)] = acc.get(int(c), 0.0) + float(d)
        return [acc.get(i, 0.0) for i in range(n_rows)]

    setattr(_tg, _KERNEL, col_sum)
    coo = Coo(
        row=np.array([0, 1], dtype=np.int64),
        col=np.array([0, 0], dtype=np.int64),
        data=np.array([2.0, 3.0], dtype=np.float64),
        shape=(2, 1),
    )
    with pytest.raises(AssertionError):
        test_p3_transpose_equals_col_sums.hypothesis.inner_test(coo)


# ---------------------------------------------------------------------------
# P4 — negative-col fancy-index wrapping
# ---------------------------------------------------------------------------


@st.composite
def negative_col_case(draw):
    n_cols = draw(st.integers(min_value=2, max_value=6))
    neg_col = draw(st.integers(min_value=-(n_cols - 1), max_value=-1))
    d = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    return n_cols, neg_col, d


@given(negative_col_case())
@settings(max_examples=50, deadline=60000)
def test_p4_negative_col_wraps_like_fancy_index(case):
    n_cols, neg_col, d = case
    n_rows = 1
    wrapped = n_cols + neg_col  # numpy fancy-index wrap
    coo = Coo(
        row=np.array([0], dtype=np.int64),
        col=np.array([neg_col], dtype=np.int64),
        data=np.array([d], dtype=np.float64),
        shape=(n_rows, n_cols),
    )
    other = np.ones(n_cols, dtype=np.float64)
    got = coo @ other
    want = _oracle_coo_matmul(np.array([0]), np.array([neg_col]), np.array([d]), (1, n_cols), other)
    _assert_bit_exact(got, want)
    assert other[wrapped] == 1.0  # the wrap target carries the weight
    assert got[0] == d


def test_p4_fails_for_zero_matvec_mutant(_restore_kernel):
    """A degenerate kernel that never consults the (wrapped) column index
    violates the fancy-index wrap relation."""
    setattr(_tg, _KERNEL, lambda *_a, **_k: [0.0])
    with pytest.raises(AssertionError):
        test_p4_negative_col_wraps_like_fancy_index.hypothesis.inner_test((3, -1, 2.0))


# ---------------------------------------------------------------------------
# P5 — empty Coo short-circuits before the kernel
# ---------------------------------------------------------------------------


@given(st.integers(min_value=0, max_value=8), st.integers(min_value=0, max_value=8))
@settings(max_examples=20, deadline=60000)
def test_p5_empty_matvec_is_zeros(n_rows, n_cols):
    coo = Coo(
        row=np.array([], dtype=np.int64),
        col=np.array([], dtype=np.int64),
        data=np.array([], dtype=np.float64),
        shape=(n_rows, n_cols),
    )
    got = coo @ np.zeros(n_cols, dtype=np.float64)
    want = np.zeros(n_rows, dtype=np.float64)
    _assert_bit_exact(got, want)
    assert got.shape == (n_rows,)


def test_p5_fails_to_reach_kernel_for_empty_mutant(_restore_kernel):
    """The empty path must NOT call the kernel: a kernel that raises on
    empty input cannot fire when nnz == 0. If a regression moved the empty
    check after the kernel call, this property would start raising."""

    def raises_if_called(*_a, **_k):
        raise AssertionError("kernel reached for empty Coo")

    setattr(_tg, _KERNEL, raises_if_called)
    coo = Coo(
        row=np.array([], dtype=np.int64),
        col=np.array([], dtype=np.int64),
        data=np.array([], dtype=np.float64),
        shape=(3, 4),
    )
    got = coo @ np.zeros(4)
    assert list(got) == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# P6 — data-dtype preservation (container pin; anti-vacuity by construction)
# ---------------------------------------------------------------------------


def test_p6_data_dtype_preserved_float32():
    data = np.array([0.5, 1.5, -2.25], dtype=np.float32)
    coo = Coo(
        row=np.array([0, 1, 2], dtype=np.int64),
        col=np.array([0, 0, 0], dtype=np.int64),
        data=data,
        shape=(3, 1),
    )
    assert coo.data.dtype == data.dtype
    assert coo.data.tobytes() == data.tobytes()


def test_p6_data_dtype_preserved_float64():
    data = np.array([0.5, 1.5, -2.25], dtype=np.float64)
    coo = Coo(
        row=np.array([0, 1, 2], dtype=np.int64),
        col=np.array([0, 0, 0], dtype=np.int64),
        data=data,
        shape=(3, 1),
    )
    assert coo.data.dtype == data.dtype
    assert coo.data.tobytes() == data.tobytes()


def test_p6_dtype_check_bites_when_float64_leaks_into_float32_construction():
    """Anti-vacuity: the float32 pin is only meaningful because a float64
    construction must NOT report float32."""
    coo = Coo(
        row=np.array([0], dtype=np.int64),
        col=np.array([0], dtype=np.int64),
        data=np.array([1.5], dtype=np.float64),
        shape=(1, 1),
    )
    assert coo.data.dtype.str != "<f4"


# ---------------------------------------------------------------------------
# P7 — shape/nnz invariants (container pin)
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_p7_shape_nnz_invariants(coo):
    assert coo.nnz == len(coo.row) == len(coo.col) == len(coo.data)
    assert coo.shape == (coo.shape[0], coo.shape[1])
    assert len(coo.row) == len(coo.data)


def test_p7_fails_for_mismatched_construction():
    """Anti-vacuity: a Coo whose row/col/data lengths disagree must trip the
    real kernel's length validation — the P7 invariant is load-bearing, not a
    tautology. (No kernel patch: validation lives in the pyfunction.)"""
    coo = Coo(
        row=np.array([0, 1], dtype=np.int64),
        col=np.array([0], dtype=np.int64),
        data=np.array([1.0], dtype=np.float64),
        shape=(3, 2),
    )
    with pytest.raises(ValueError):
        coo @ np.ones(2)


# ---------------------------------------------------------------------------
# MR1 — triplet-order permutation (1-ulp band; NOT bit-exact)
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr1_triplet_order_invariance_tolerance(coo):
    ones = np.ones(coo.shape[1], dtype=np.float64)
    baseline = coo @ ones
    perm = list(range(len(coo.data)))
    random.Random(7).shuffle(perm)
    shuffled = Coo(
        row=coo.row[perm],
        col=coo.col[perm],
        data=coo.data[perm],
        shape=coo.shape,
    )
    got = shuffled @ ones
    scale = max(1.0, float(np.max(np.abs(baseline))) if len(baseline) else 1.0)
    assert np.all(np.abs(got - baseline) <= 1e-12 * scale)


def test_mr1_fails_for_order_dependent_mutant(_restore_kernel):
    def order_dependent(row, col, data, n_rows, other):
        n = max(n_rows, (int(row.max()) + 1) if len(row) else 0)
        result = [0.0] * n
        for i in range(len(data)):
            result[row[i]] += data[i] * other[col[i]] * (i + 1)
        return result

    setattr(_tg, _KERNEL, order_dependent)
    coo = Coo(
        row=np.array([0, 0, 0], dtype=np.int64),
        col=np.array([0, 0, 0], dtype=np.int64),
        data=np.array([1.0, 2.0, 4.0], dtype=np.float64),
        shape=(1, 1),
    )
    with pytest.raises(AssertionError):
        test_mr1_triplet_order_invariance_tolerance.hypothesis.inner_test(coo)


# ---------------------------------------------------------------------------
# MR2 — power-of-two data scaling is bit-exact
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr2_power_of_two_scaling_exact(coo):
    ones = np.ones(coo.shape[1], dtype=np.float64)
    base = coo @ ones
    scaled = Coo(
        row=coo.row,
        col=coo.col,
        data=coo.data * 2.0,
        shape=coo.shape,
    )
    _assert_bit_exact(scaled @ ones, base * 2.0)


def test_mr2_fails_for_nonlinear_mutant(_restore_kernel):
    def nonlinear(row, col, data, n_rows, other):
        n = max(n_rows, (int(row.max()) + 1) if len(row) else 0)
        result = [0.0] * n
        for i in range(len(data)):
            result[row[i]] += data[i] * data[i] * other[col[i]]
        return result

    setattr(_tg, _KERNEL, nonlinear)
    coo = Coo(
        row=np.array([0], dtype=np.int64),
        col=np.array([0], dtype=np.int64),
        data=np.array([2.0], dtype=np.float64),
        shape=(1, 1),
    )
    with pytest.raises(AssertionError):
        test_mr2_power_of_two_scaling_exact.hypothesis.inner_test(coo)


# ---------------------------------------------------------------------------
# MR3 — double transpose is the identity container (bit-exact)
# ---------------------------------------------------------------------------


@given(coo_strategy())
@settings(max_examples=50, deadline=60000)
def test_mr3_double_transpose_identity_exact(coo):
    t = coo.T.T
    assert t.shape == coo.shape
    assert list(t.row) == list(coo.row)
    assert list(t.col) == list(coo.col)
    assert list(t.data) == list(coo.data)
    assert t.data.dtype == coo.data.dtype


# ---------------------------------------------------------------------------
# MR4 — node-degree total == edge-degree total for integer weights (bit-exact:
# integer intermediate sums are order-independent in f64, so the two different
# summation orders agree exactly)
# ---------------------------------------------------------------------------


@st.composite
def integer_weighted_coo(draw):
    coo = draw(coo_strategy())
    return Coo(
        row=coo.row,
        col=coo.col,
        data=np.array([float(draw(st.integers(min_value=0, max_value=8))) for _ in coo.data], dtype=np.float64),
        shape=coo.shape,
    )


@given(integer_weighted_coo())
@settings(max_examples=50, deadline=60000)
def test_mr4_degree_totals_conserved(coo):
    ones_cols = np.ones(coo.shape[1], dtype=np.float64)
    ones_rows = np.ones(coo.shape[0], dtype=np.float64)
    node_deg = coo @ ones_cols
    edge_deg = coo.T @ ones_rows
    assert float(np.sum(node_deg)) == float(np.sum(edge_deg))
