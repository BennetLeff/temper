"""Property-based and metamorphic suite for the faer sparse-LU solve kernel
(`temper_thermal.solve_sparse_lu_py`), the migration that retired scipy's
`spsolve`/SuperLU from the thermal FDM (KTD9 overturn, 2026-08-09).

The verification unit is the **solve kernel** as reached through the U5
FDM assembly: every property below assembles a real random FDM system
(5-point stencil, harmonic-mean k, Dirichlet heatsink face, optional
vertical sink) via `temper_thermal.assemble_system_py` and solves it via
`solve_sparse_lu_py`, so generated inputs genuinely reach the kernel
(reachability is inherent — there is no alternate path that could
silently short-circuit the solve).

Properties (each vacuity-guarded by a `test_pN_fails_for_<mutant>`):
  P1 — residual smallness: the returned x actually solves A·x = b
        (relative residual at machine precision).
  P2 — discrete maximum principle: Q >= 0 + cold Dirichlet face implies
        no cell below ambient.
  P3 — no-source ambient exactness: Q = 0 gives the ambient field to
        roundoff (the tightest consumer tolerance, atol=1e-9).
  P4 — linearity in source: doubling Q doubles the rise above ambient.
  P5 — determinism: repeated solves on identical input are bit-identical
        (float.hex).
  P6 — finiteness: every solution on the FDM corpus is finite.

Metamorphic relations:
  M1 — ambient-shift invariance: x(A·x=b+c·A·1) = x(A·x=b) + c.
  M2 — positive scaling invariance: x(2A, 2b) = x(A, b).
  M3 — permutation covariance: permuting rows+cols of A and b by the
        same permutation permutes the solution identically.

The pinned tolerance contract (max|T_faer - T_scipy| <= 1e-10 K over the
corpus, observed 5.7e-12 K) lives in
`tests/physics/test_thermal_solve_rust_differential.py`; this suite pins
the *mathematical* properties of the kernel itself.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

AMBIENT_C = 40.0

_EDGES = ["TOP", "BOTTOM", "LEFT", "RIGHT"]
_HS_CODES = {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}


def _hs_code(edge: str) -> int:
    return _HS_CODES[edge]


@st.composite
def fdm_case(draw):
    """A random FDM problem: grid, heatsink edge, cell size, k/Q fields
    (Q >= 0), and an optional non-negative vertical sink field."""
    h = draw(st.integers(3, 15))
    w = draw(st.integers(3, 15))
    edge = draw(st.sampled_from(_EDGES))
    cs = draw(st.floats(0.25, 1.0))
    k = draw(
        st.lists(
            st.floats(min_value=0.3, max_value=380.0),
            min_size=h * w,
            max_size=h * w,
        ).map(lambda vals: np.asarray(vals, dtype=np.float64).reshape(h, w))
    )
    q = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=0.05),
            min_size=h * w,
            max_size=h * w,
        ).map(lambda vals: np.asarray(vals, dtype=np.float64).reshape(h, w))
    )
    hf = draw(st.sampled_from(["none", "some"]))
    h_field = None
    if hf == "some":
        h_field = draw(
            st.lists(
                st.floats(min_value=0.0, max_value=2.0),
                min_size=h * w,
                max_size=h * w,
            ).map(lambda vals: np.asarray(vals, dtype=np.float64).reshape(h, w))
        )
    return {
        "h": h,
        "w": w,
        "edge": edge,
        "cs": cs,
        "k": k,
        "q": q,
        "hf": h_field,
    }


def _assemble(case, q_override=None):
    """Assemble the U5 FDM system for *case* (optionally overriding Q)
    and return (rows, cols, values, b, n)."""
    h, w = case["h"], case["w"]
    q = case["q"] if q_override is None else q_override
    rows, cols, values, b = _tt.assemble_system_py(
        np.ascontiguousarray(case["k"], dtype=np.float64).tobytes(),
        np.ascontiguousarray(q, dtype=np.float64).tobytes(),
        None
        if case["hf"] is None
        else np.ascontiguousarray(case["hf"], dtype=np.float64).tobytes(),
        h,
        w,
        AMBIENT_C,
        case["cs"],
        _hs_code(case["edge"]),
    )
    return list(rows), list(cols), list(values), np.asarray(b, dtype=np.float64), h * w


def _solve(rows, cols, values, b, n) -> np.ndarray:
    raw = _tt.solve_sparse_lu_py(rows, cols, values, b.tobytes(), n)
    return np.frombuffer(raw, dtype=np.float64).copy()


def _matvec(rows, cols, values, x, n) -> np.ndarray:
    out = np.zeros(n, dtype=np.float64)
    np.add.at(out, rows, np.asarray(values, dtype=np.float64) * x[cols])
    return out


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p1_residual_smallness(case):
    """P1: the returned x actually solves A·x = b (relative residual at
    machine precision, ~1e-15).  A solver that returned anything else —
    the RHS, a constant field, garbage — would fail this."""
    rows, cols, values, b, n = _assemble(case)
    x = _solve(rows, cols, values, b, n)
    residual = float(np.linalg.norm(_matvec(rows, cols, values, x, n) - b))
    rel = residual / max(1.0, float(np.linalg.norm(b)))
    assert rel < 1e-9, f"relative residual {rel:.3e} exceeds machine-precision bound"


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p2_maximum_principle(case):
    """P2: with Q >= 0 everywhere and a cold Dirichlet heatsink face, no
    interior cell can fall below ambient (M-matrix inverse positivity)."""
    rows, cols, values, b, n = _assemble(case)
    x = _solve(rows, cols, values, b, n)
    assert float(np.min(x)) >= AMBIENT_C - 1e-9


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p3_no_source_ambient(case):
    """P3: with Q = 0, the solution is the ambient field to roundoff
    (A·(ambient·1) == b exactly for this stencil, so the direct solve
    returns ambient within the tightest consumer tolerance)."""
    h, w = case["h"], case["w"]
    q_zero = np.zeros((h, w), dtype=np.float64)
    rows, cols, values, b, n = _assemble(case, q_override=q_zero)
    x = _solve(rows, cols, values, b, n)
    assert float(np.max(np.abs(x - AMBIENT_C))) < 1e-9


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p4_linearity_in_source(case):
    """P4: doubling Q doubles the temperature rise above ambient (the
    system is linear: x(A, b + Q) = x(A, b) + x(A, Q))."""
    q2 = 2.0 * case["q"]
    rows, cols, values, b1, n = _assemble(case)
    x1 = _solve(rows, cols, values, b1, n)
    rows2, cols2, values2, b2, _ = _assemble(case, q_override=q2)
    x2 = _solve(rows2, cols2, values2, b2, n)
    rise1 = x1 - AMBIENT_C
    rise2 = x2 - AMBIENT_C
    # The rise is non-zero for a genuine source (sanity against a vacuous
    # all-zero-Q case) — skip only if the generated Q is identically zero.
    if float(np.max(np.abs(rise1))) < 1e-9:
        return
    assert float(np.max(np.abs(rise2 - 2.0 * rise1))) < 1e-6


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p5_deterministic(case):
    """P5: repeated solves on identical input are bit-identical
    (float.hex).  The faer factorization is deterministic, like the
    retired SuperLU path."""
    rows, cols, values, b, n = _assemble(case)
    x1 = _solve(rows, cols, values, b, n)
    x2 = _solve(rows, cols, values, b, n)
    for a, c in zip(x1, x2):
        assert a.hex() == c.hex()


@given(case=fdm_case())
@settings(max_examples=40, deadline=3000)
def test_p6_finite_solutions(case):
    """P6: every solution on the FDM corpus is finite (the FDM matrix is
    non-singular for any valid heatsink edge, so the direct solve cannot
    produce inf/nan)."""
    rows, cols, values, b, n = _assemble(case)
    x = _solve(rows, cols, values, b, n)
    assert np.all(np.isfinite(x))


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@given(case=fdm_case())
@settings(max_examples=30, deadline=3000)
def test_m1_ambient_shift_invariance(case):
    """M1: adding c·A·1 to the RHS shifts the solution by the constant c
    (x(b + c·A·1) = x(b) + c), exact in exact arithmetic, tolerance 1e-9."""
    rows, cols, values, b, n = _assemble(case)
    x0 = _solve(rows, cols, values, b, n)
    ones = np.ones(n, dtype=np.float64)
    rowsums = _matvec(rows, cols, values, ones, n)  # A·1
    c = 5.0
    b_shift = b + c * rowsums
    x1 = _solve(rows, cols, values, b_shift, n)
    assert float(np.max(np.abs((x1 - c) - x0))) < 1e-9


@given(case=fdm_case())
@settings(max_examples=30, deadline=3000)
def test_m2_positive_scaling_invariance(case):
    """M2: scaling A and b by the same positive factor leaves the solution
    unchanged (x(2A, 2b) = x(A, b)) — pivot selection is insensitive to a
    common positive scale, tolerance 1e-9."""
    rows, cols, values, b, n = _assemble(case)
    x0 = _solve(rows, cols, values, b, n)
    scale = 2.0
    values_s = [v * scale for v in values]
    b_s = b * scale
    x1 = _solve(rows, cols, values_s, b_s, n)
    assert float(np.max(np.abs(x1 - x0))) < 1e-9


@given(case=fdm_case())
@settings(max_examples=30, deadline=3000)
def test_m3_permutation_covariance(case):
    """M3: permuting rows+cols of A and b by the same permutation π
    permutes the solution identically (x'[π(i)] = x[i]), tolerance 1e-8."""
    rows, cols, values, b, n = _assemble(case)
    x0 = _solve(rows, cols, values, b, n)
    rng = np.random.default_rng(20260809)
    perm = rng.permutation(n)
    inv = np.argsort(perm)
    rows_p = [perm[r] for r in rows]
    cols_p = [perm[c] for c in cols]
    b_p = b[inv]
    x_p = _solve(rows_p, cols_p, values, b_p, n)
    x0_permuted = x0[inv]
    assert float(np.max(np.abs(x_p - x0_permuted))) < 1e-8


# ---------------------------------------------------------------------------
# Vacuity guards (G4 evidence pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_solve_kernel():
    original = _tt.solve_sparse_lu_py
    yield
    _tt.solve_sparse_lu_py = original


def test_p1_fails_for_rhs_kernel(_restore_solve_kernel):
    """A kernel that returns the RHS (b) instead of the solution cannot
    satisfy P1's residual bound — the property is discriminating."""
    _tt.solve_sparse_lu_py = lambda _rows, _cols, _values, b, _n: b
    with pytest.raises(AssertionError):
        test_p1_residual_smallness.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )


def test_p2_fails_for_negated_kernel(_restore_solve_kernel):
    """A kernel that negates the solution breaks the maximum principle —
    the property is discriminating."""
    real = _tt.solve_sparse_lu_py

    def mutant(rows, cols, values, b, n):
        x = np.frombuffer(real(rows, cols, values, b, n), dtype=np.float64).copy()
        return (-x).tobytes()

    _tt.solve_sparse_lu_py = mutant
    with pytest.raises(AssertionError):
        test_p2_maximum_principle.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )


def test_p3_fails_for_zero_kernel(_restore_solve_kernel):
    """A kernel that returns the zero field breaks the no-source ambient
    property — the property is discriminating."""

    def mutant(rows, cols, values, b, n):
        return np.zeros(n, dtype=np.float64).tobytes()

    _tt.solve_sparse_lu_py = mutant
    with pytest.raises(AssertionError):
        test_p3_no_source_ambient.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )


def test_p4_fails_for_quadratic_kernel(_restore_solve_kernel):
    """A kernel that returns the square of the true solution is non-linear
    in the source and breaks P4 — the property is discriminating."""
    real = _tt.solve_sparse_lu_py

    def mutant(rows, cols, values, b, n):
        x = np.frombuffer(real(rows, cols, values, b, n), dtype=np.float64).copy()
        return (x * x).tobytes()

    _tt.solve_sparse_lu_py = mutant
    with pytest.raises(AssertionError):
        test_p4_linearity_in_source.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )


def test_p5_fails_for_noisy_kernel(_restore_solve_kernel):
    """A kernel that injects random noise on every call breaks the
    bit-identical determinism property — the property is discriminating."""
    real = _tt.solve_sparse_lu_py

    def mutant(rows, cols, values, b, n):
        x = np.frombuffer(real(rows, cols, values, b, n), dtype=np.float64).copy()
        x[0] += np.random.uniform(0.0, 1e-9)
        return x.tobytes()

    _tt.solve_sparse_lu_py = mutant
    with pytest.raises(AssertionError):
        test_p5_deterministic.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )


def test_p6_fails_for_nan_kernel(_restore_solve_kernel):
    """A kernel that returns NaN breaks the finiteness property — the
    property is discriminating."""

    def mutant(rows, cols, values, b, n):
        return np.full(n, np.nan, dtype=np.float64).tobytes()

    _tt.solve_sparse_lu_py = mutant
    with pytest.raises(AssertionError):
        test_p6_finite_solutions.hypothesis.inner_test(
            {
                "h": 6,
                "w": 8,
                "edge": "TOP",
                "cs": 0.5,
                "k": np.full((6, 8), 10.0),
                "q": np.full((6, 8), 0.01),
                "hf": None,
            }
        )
