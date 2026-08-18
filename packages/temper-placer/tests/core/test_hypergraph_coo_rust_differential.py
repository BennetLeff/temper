"""Phase-A U7 differential: typed ``Coo`` I/O vs the pinned hypergraph oracle.

Gate G1 (``docs/wave4-discipline-contract.md``) — the Rust orchestration
plan's Phase A (``docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md``,
unit U7) moves the ``core/hypergraph.py`` ``Coo`` container — the typed I/O
boundary of the ``hypergraph_coo_matvec`` kernel — into ``temper-design-bundle``
as a frozen pyclass with typed ``Vec`` storage.

**THIS SUITE IS DELIBERATELY RED.**  The Rust arm resolves its type through
``temper_design_bundle_python.hypergraph_contracts`` and fails with an
``ImportError`` until the migration supplies the pyclass.

Arms
----
* **oracle** — ``_oracle_coo_matmul`` below: the verbatim pre-migration
  ``Coo.__matmul__`` scatter-add semantics (``np.bincount`` with
  ``minlength`` extension and negative-column fancy-index wrapping), pinned
  from commit ``edc19ffa`` of ``core/hypergraph.py`` (``test_oracle_verbatim``
  re-extracts the source and compares character for character).
* **rust** — ``temper_design_bundle_python.hypergraph_contracts.Coo``, a typed
  COO container whose ``__matmul__`` delegates to the existing
  ``temper_geometry.hypergraph_coo_matvec_py`` kernel (so the scatter-add is
  the same code path the Python shim used, and the kernel-mutation vacuity
  guards in ``test_core_graph_cluster_pbt.py`` stay live).

Comparison is bit-exact: every ``@`` result is compared as a numpy array via
``float.hex()`` elementwise (sign-of-zero preserved), plus shape/dtype.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# ===========================================================================

_RUST_MODULE = "temper_design_bundle_python"
_RUST_SUBMODULE = "hypergraph_contracts"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("Coo",)


def _tdb():
    import temper_design_bundle_python as _m  # noqa: PLC0415

    return getattr(_m, _RUST_SUBMODULE)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "edc19ffa9492ef4a752c48289242088de6b4fbd1"
_ORACLE_REL = "packages/temper-placer/src/temper_placer/core/hypergraph.py"
_ORACLE_NAMES: tuple[str, ...] = ("Coo",)

# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/hypergraph.py`'s
# `Coo.__matmul__` (origin/main @ edc19ffa, pre-migration). DO NOT EDIT.
# ============================================================================


def _oracle_coo_matmul(row, col, data, shape, other):
    n_rows = shape[0]
    if int(data.shape[0]) == 0:
        return np.zeros(n_rows, dtype=np.float64)
    contributions = data.astype(np.float64) * other[col]
    return np.bincount(row, weights=contributions, minlength=n_rows)


# ============================================================================
# Comparison helpers
# ============================================================================


def _assert_bit_exact(got, want):
    """Both arms return numpy arrays; compare dtype, shape, and every f64 bit
    via float.hex() (preserves -0.0)."""
    assert got.dtype == want.dtype, f"dtype {got.dtype} != {want.dtype}"
    assert got.shape == want.shape, f"shape {got.shape} != {want.shape}"
    for g, w in zip(got.reshape(-1), want.reshape(-1)):
        assert float(g).hex() == float(w).hex(), f"bit mismatch {g!r} != {w!r}"


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _random_coo(rng):
    n_rows = rng.randint(1, 8)
    n_cols = rng.randint(1, 8)
    nnz = rng.randint(0, 12)
    row = np.array([rng.randrange(n_rows) for _ in range(nnz)], dtype=np.int64)
    col = np.array([rng.randrange(n_cols) for _ in range(nnz)], dtype=np.int64)
    if rng.random() < 0.7:
        data = np.array([rng.uniform(-5.0, 5.0) for _ in range(nnz)], dtype=np.float64)
    else:
        data = np.array([rng.randint(0, 4) for _ in range(nnz)], dtype=np.int64)
    other = np.array([rng.uniform(-5.0, 5.0) for _ in range(n_cols)], dtype=np.float64)
    return row, col, data, (n_rows, n_cols), other


def _make_coo(row, col, data, shape):
    return _tdb().Coo(row=row, col=col, data=data, shape=shape)


# ---------------------------------------------------------------------------
# G1 evidence: the oracle is a verbatim pin of the pre-migration source
# ---------------------------------------------------------------------------


def test_oracle_verbatim():
    """The oracle block is byte-identical to the accepted verbatim pin in
    `_hypergraph_coo_py_oracle.py` (the same pre-migration `Coo.__matmul__`
    semantics, hand-copied with a DO NOT EDIT comment per the repo's
    oracle-block convention).

    The accepted pin used to live inline in
    `test_core_graph_cluster_rust_differential.py`; that file was deleted on
    2026-08-17 by the surface-area sweep (`35e3f914a`, merged as `caec25d6` /
    #1314) as collateral to removing `core/graph.py` and `core/power_topology.py`.
    The pin was moved verbatim into a registered `_*_py_oracle.py` file so it is
    covered by `scripts/check_oracle_hashes.py` -- the sweep checked that
    registry and correctly found nothing, because an inline oracle block is
    invisible to it. Same bytes, now guarded by the hash gate as well as by
    this test."""
    import inspect  # noqa: PLC0415

    from tests.core._hypergraph_coo_py_oracle import (  # noqa: PLC0415
        _oracle_coo_matmul as _accepted_oracle,
    )

    assert inspect.getsource(_oracle_coo_matmul) == inspect.getsource(_accepted_oracle)


def test_rust_symbols_exist():
    """The migration checklist. RED until the typed Coo pyclass lands."""
    try:
        _tdb()
    except ImportError as exc:  # pragma: no cover - the RED state
        pytest.fail(f"{_RUST_MODULE}.{_RUST_SUBMODULE} missing: {exc}")
    hg = _tdb()
    missing = [s for s in REQUIRED_RUST_SYMBOLS if not hasattr(hg, s)]
    assert not missing, (
        f"{_RUST_MODULE}.{_RUST_SUBMODULE} is missing "
        f"{len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} types: {missing}"
    )


# ---------------------------------------------------------------------------
# Bit-exact matmul differential
# ---------------------------------------------------------------------------


def test_coo_matmul_bit_exact_random():
    rng = random.Random(777)
    for _ in range(40):
        row, col, data, shape, other = _random_coo(rng)
        coo = _make_coo(row, col, data, shape)
        got = coo @ other
        want = _oracle_coo_matmul(row, col, data, shape, other)
        _assert_bit_exact(got, want)


def test_coo_matmul_length_extension_matches_bincount():
    row = np.array([0, 5], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([1.5, 2.5], dtype=np.float64)
    shape = (2, 2)
    other = np.array([1.0, 1.0], dtype=np.float64)
    coo = _make_coo(row, col, data, shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert got.shape[0] == 6


def test_coo_matmul_negative_col_wraps():
    row = np.array([0], dtype=np.int64)
    col = np.array([-1], dtype=np.int64)
    data = np.array([2.0], dtype=np.float64)
    shape = (1, 3)
    other = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    coo = _make_coo(row, col, data, shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert float(got[0]) == 6.0


def test_coo_matmul_nan_and_empty():
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([np.nan, 1.0], dtype=np.float64)
    shape = (2, 2)
    other = np.array([1.0, 2.0], dtype=np.float64)
    coo = _make_coo(row, col, data, shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert math.isnan(got[0]) and float(got[1]) == 2.0

    empty = _make_coo(
        np.array([], dtype=np.int64), np.array([], dtype=np.int64),
        np.array([], dtype=np.float64), (3, 4),
    )
    want = _oracle_coo_matmul(empty.row, empty.col, empty.data, empty.shape, np.zeros(4))
    _assert_bit_exact(empty @ np.zeros(4), want)


def test_coo_degrees_match_oracle():
    rng = random.Random(99)
    for _ in range(20):
        row, col, data, shape, _ = _random_coo(rng)
        coo = _make_coo(row, col, data, shape)
        other = np.ones(shape[1], dtype=np.float64)
        got = coo @ other
        want = _oracle_coo_matmul(row, col, data, shape, other)
        _assert_bit_exact(got, want)


# ---------------------------------------------------------------------------
# Error parity: the kernel's validation mirrors the oracle's numpy raises
# ---------------------------------------------------------------------------


def test_coo_matmul_length_mismatch_raises():
    """Kernel-added validation pin (documented divergence, not oracle parity):
    the kernel's `validate_matvec` raises ValueError for row/col/data length
    mismatch, where the oracle's numpy broadcasting silently allows it. The
    Rust Coo keeps the kernel's behavior — this is the pre-migration kernel
    path's own contract, unchanged by U7."""
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0], dtype=np.int64)
    data = np.array([1.0, 2.0], dtype=np.float64)
    shape = (3, 2)
    other = np.ones(2)
    b = _capture(lambda: (_make_coo(row, col, data, shape) @ other))
    assert isinstance(b, Exception)
    assert type(b) is ValueError


def test_coo_matmul_negative_row_raises_value_error():
    row = np.array([-1], dtype=np.int64)
    col = np.array([0], dtype=np.int64)
    data = np.array([1.0], dtype=np.float64)
    shape = (2, 2)
    other = np.ones(2)
    a = _capture(lambda: _oracle_coo_matmul(row, col, data, shape, other))
    b = _capture(lambda: (_make_coo(row, col, data, shape) @ other))
    assert isinstance(a, Exception) and isinstance(b, Exception)
    assert type(a) is type(b) is ValueError


def test_coo_matmul_out_of_bounds_col_raises_index_error():
    row = np.array([0], dtype=np.int64)
    col = np.array([5], dtype=np.int64)
    data = np.array([1.0], dtype=np.float64)
    shape = (2, 2)
    other = np.ones(2)
    a = _capture(lambda: _oracle_coo_matmul(row, col, data, shape, other))
    b = _capture(lambda: (_make_coo(row, col, data, shape) @ other))
    assert isinstance(a, Exception) and isinstance(b, Exception)
    assert type(a) is type(b) is IndexError


# ---------------------------------------------------------------------------
# Typed-surface parity: construction, getters, .T, nnz, dtype preservation
# ---------------------------------------------------------------------------


def test_coo_surface_attributes():
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([2.0, 3.0], dtype=np.float64)
    shape = (2, 2)
    coo = _make_coo(row, col, data, shape)
    assert coo.shape == shape
    assert coo.nnz == 2
    assert list(coo.row) == [0, 1]
    assert list(coo.col) == [0, 1]
    assert list(coo.data) == [2.0, 3.0]


def test_coo_data_dtype_preserved_float32():
    """The factory builds float32 data; the getter must return float32 so the
    existing factory differential's (dtype, shape, tobytes()) key still
    matches the scipy oracle."""
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([1.5, 2.5], dtype=np.float32)
    coo = _make_coo(row, col, data, (2, 2))
    assert coo.data.dtype.str == "<f4"
    assert coo.data.tobytes() == data.tobytes()


def test_coo_data_dtype_float64_default():
    row = np.array([0], dtype=np.int64)
    col = np.array([0], dtype=np.int64)
    data = np.array([1.5], dtype=np.float64)
    coo = _make_coo(row, col, data, (1, 1))
    assert coo.data.dtype.str == "<f8"


def test_coo_transpose_swaps_rows_cols():
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0, 0], dtype=np.int64)
    data = np.array([2.0, 3.0], dtype=np.float64)
    coo = _make_coo(row, col, data, (2, 1))
    t = coo.T
    assert t.shape == (1, 2)
    assert list(t.row) == [0, 0]
    assert list(t.col) == [0, 1]
    assert list(t.data) == [2.0, 3.0]
    assert t.data.dtype.str == coo.data.dtype.str


def test_coo_repr_matches_dataclass_layout():
    coo = _make_coo(
        np.array([0], dtype=np.int64),
        np.array([0], dtype=np.int64),
        np.array([1.0], dtype=np.float64),
        (1, 1),
    )
    r = repr(coo)
    assert r.startswith("Coo(")
    assert "row=" in r and "col=" in r and "data=" in r and "shape=" in r


def test_coo_is_frozen():
    coo = _make_coo(
        np.array([0], dtype=np.int64),
        np.array([0], dtype=np.int64),
        np.array([1.0], dtype=np.float64),
        (1, 1),
    )
    with pytest.raises(AttributeError):
        coo.shape = (5, 5)


def test_coo_construction_accepts_lists():
    """pyo3 Vec extraction accepts plain Python lists too (the dataclass's
    containers were duck-typed)."""
    coo = _make_coo([0, 1], [0, 1], [1.0, 2.0], (2, 2))
    ones = np.ones(2)
    got = coo @ ones
    want = _oracle_coo_matmul(np.array([0, 1]), np.array([0, 1]), np.array([1.0, 2.0]), (2, 2), ones)
    _assert_bit_exact(got, want)


def test_coo_accepts_pcb_style_payloads():
    """A numpy-int64 row built by the factory's np.array(rows, dtype=np.int64)
    path extracts cleanly through the typed constructor."""
    rows = [0, 1, 1, 2]
    cols = [0, 0, 1, 1]
    data = [1.0, 1.0, 1.0, 1.0]
    coo = _make_coo(
        np.array(rows, dtype=np.int64),
        np.array(cols, dtype=np.int64),
        np.array(data, dtype=np.float32),
        (3, 2),
    )
    deg = coo @ np.ones(2)
    assert list(deg) == [1.0, 2.0, 1.0]
