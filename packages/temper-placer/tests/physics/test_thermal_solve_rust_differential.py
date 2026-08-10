"""Differential tests: the temper-thermal faer sparse-LU solve vs the
retired scipy `spsolve` (SuperLU) oracle, with the pinned tolerance
contract.

The KTD9 spike (2026-07-31) measured max|T_faer - T_scipy| = 5.1e-13 K;
the 2026-08-09 re-measurement over a 144-case U5+U7 corpus (grid sizes
up to the 2500-cell `max_cells` ceiling, all four heatsink edges, with
and without the vertical-sink `h_field`) recorded max = 5.7e-12 K.

This suite pins the documented-tolerance migration bound:

    max|T_faer - T_scipy| <= 1e-10 K  over the FDM corpus

— ~175x above the observed maximum and 10x below the tightest consumer
tolerance (`atol=1e-9` in the ambient-field checks). Every consumer of
the temperature field compares via a physics tolerance >= 1e-9 K (see
`packages/temper-thermal/VERIFICATION.md`, "Sparse solve kernel (U5/U7)
— characterization and migration decision", KTD9 overturn 2026-08-09).

Both solvers are deterministic (same matrix + flags -> bit-identical
output); determinism is asserted here alongside the tolerance bound.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_thermal as _tt
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

# Pinned tolerance: max|T_faer - T_scipy| over the corpus.
# Observed 2026-08-09: 5.7e-12 K. Bound: 17x above observed, 10x below
# the tightest consumer tolerance (atol=1e-9).
PINNED_MAX_DIVERGENCE_K = 1e-10

_HS_CODES = {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}


def _hs_code(edge: str) -> int:
    return _HS_CODES.get(edge.upper().strip(), 99)


def _solve_scipy(rows, cols, values, b, n):
    """The pre-migration solve path, verbatim: COO -> CSR -> spsolve
    (SuperLU). This is the oracle the faer kernel is measured against."""
    A = coo_matrix((values, (rows, cols)), shape=(n, n), dtype=np.float64).tocsr()
    return spsolve(A, np.asarray(b, dtype=np.float64))


def _solve_faer(rows, cols, values, b, n):
    raw = _tt.solve_sparse_lu_py(
        list(rows), list(cols), list(values), np.asarray(b, dtype=np.float64).tobytes(), n
    )
    return np.frombuffer(raw, dtype=np.float64).copy()


def _corpus():
    """Deterministic U5+U7 corpus: grid sizes up to the 2500-cell
    max_cells ceiling, all heatsink edges, with/without h_field."""
    rng = random.Random(20260809)
    sizes = [(1, 1), (2, 3), (5, 5), (12, 16), (25, 25), (50, 50), (25, 100), (1, 50)]
    cases = []
    for h, w in sizes:
        for edge in _HS_CODES:
            for with_h in (False, True):
                n = h * w
                cs = rng.choice([0.25, 0.5, 1.0])
                k = np.asarray([0.3 + rng.random() * 380 for _ in range(n)]).reshape(h, w)
                q = np.asarray([rng.random() * 0.05 for _ in range(n)]).reshape(h, w)
                hf = (
                    None
                    if not with_h
                    else np.asarray([rng.random() * 2.0 for _ in range(n)]).reshape(h, w)
                )
                cases.append((h, w, edge, cs, k, q, hf))
    return cases


@pytest.mark.parametrize("system_kind", ["u5", "u7"])
def test_faer_within_pinned_tolerance_over_corpus(system_kind):
    """max|T_faer - T_scipy| <= PINNED_MAX_DIVERGENCE_K over the corpus.

    The pinned bound is 17x above the observed maximum (5.7e-12 K) and
    10x below the tightest consumer tolerance (1e-9 K), so this is a
    documented-tolerance migration, not an unmeasured one.
    """
    max_diff = 0.0
    worst = None
    for h, w, edge, cs, k, q, hf in _corpus():
        n = h * w
        if system_kind == "u5":
            rows, cols, values, b = _tt.assemble_system_py(
                np.ascontiguousarray(k, dtype=np.float64).tobytes(),
                np.ascontiguousarray(q, dtype=np.float64).tobytes(),
                None if hf is None else np.ascontiguousarray(hf, dtype=np.float64).tobytes(),
                h,
                w,
                40.0,
                cs,
                _hs_code(edge),
            )
        else:
            rows, cols, values, b = _tt.assemble_convective_system_py(
                np.ascontiguousarray(k, dtype=np.float64).tobytes(),
                np.ascontiguousarray(q, dtype=np.float64).tobytes(),
                None if hf is None else np.ascontiguousarray(hf, dtype=np.float64).tobytes(),
                h,
                w,
                40.0,
                cs,
                1.6,
                10.0,
                _hs_code(edge),
            )
        t_scipy = _solve_scipy(rows, cols, values, b, n)
        t_faer = _solve_faer(rows, cols, values, b, n)
        d = float(np.max(np.abs(t_scipy - t_faer)))
        if d > max_diff:
            max_diff = d
            worst = f"{system_kind} h={h} w={w} edge={edge} cs={cs} with_h={hf is not None}"
    assert max_diff <= PINNED_MAX_DIVERGENCE_K, (
        f"faer divergence {max_diff:.3e} K exceeds pinned bound "
        f"{PINNED_MAX_DIVERGENCE_K:.1e} K at {worst}"
    )


def test_faer_solve_is_deterministic_bit_identical():
    """The faer solve is deterministic: repeated solves on identical input
    are bit-identical (float.hex equality). The retired scipy spsolve was
    deterministic too — determinism, not bit-parity with scipy, is the
    property the consumers rely on."""
    rng = random.Random(7)
    h, w = 50, 50
    n = h * w
    k = np.asarray([rng.random() * 380 + 0.1 for _ in range(n)]).reshape(h, w)
    q = np.asarray([rng.random() * 0.05 for _ in range(n)]).reshape(h, w)
    rows, cols, values, b = _tt.assemble_system_py(
        np.ascontiguousarray(k, dtype=np.float64).tobytes(),
        np.ascontiguousarray(q, dtype=np.float64).tobytes(),
        None,
        h,
        w,
        40.0,
        0.5,
        _hs_code("TOP"),
    )
    t1 = _solve_faer(rows, cols, values, b, n)
    t2 = _solve_faer(rows, cols, values, b, n)
    assert t1.shape == (n,)
    for a, c in zip(t1, t2):
        assert a.hex() == c.hex()


def test_scipy_solve_was_deterministic_too():
    """Documented baseline: the retired scipy spsolve was deterministic
    (bit-identical on repeat) — so the migration preserves determinism."""
    rng = random.Random(42)
    h, w = 50, 50
    n = h * w
    k = np.asarray([rng.random() * 380 + 0.1 for _ in range(n)]).reshape(h, w)
    q = np.asarray([rng.random() * 0.05 for _ in range(n)]).reshape(h, w)
    rows, cols, values, b = _tt.assemble_system_py(
        np.ascontiguousarray(k, dtype=np.float64).tobytes(),
        np.ascontiguousarray(q, dtype=np.float64).tobytes(),
        None,
        h,
        w,
        40.0,
        0.5,
        _hs_code("TOP"),
    )
    t1 = _solve_scipy(rows, cols, values, b, n)
    t2 = _solve_scipy(rows, cols, values, b, n)
    np.testing.assert_array_equal(t1, t2)


def test_faer_solve_matches_scipy_to_machine_precision_on_small_grid():
    """A tighter, well-conditioned regression case: on small grids the two
    direct solvers agree to ~1e-13 K (machine precision for these
    magnitudes) — well inside the pinned bound, and far below every
    consumer tolerance."""
    rng = random.Random(3)
    h, w = 12, 16
    n = h * w
    k = np.asarray([rng.random() * 380 + 0.1 for _ in range(n)]).reshape(h, w)
    q = np.asarray([rng.random() * 0.05 for _ in range(n)]).reshape(h, w)
    for edge in _HS_CODES:
        rows, cols, values, b = _tt.assemble_system_py(
            np.ascontiguousarray(k, dtype=np.float64).tobytes(),
            np.ascontiguousarray(q, dtype=np.float64).tobytes(),
            None,
            h,
            w,
            40.0,
            1.0,
            _hs_code(edge),
        )
        t_scipy = _solve_scipy(rows, cols, values, b, n)
        t_faer = _solve_faer(rows, cols, values, b, n)
        assert float(np.max(np.abs(t_scipy - t_faer))) < 1e-12
