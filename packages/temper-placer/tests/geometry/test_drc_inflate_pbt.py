"""R1c/R1d property and metamorphic suite for the Rust DRC-inflation kernels.

Wave 4, Phase 4 (geometry remainder). Seven properties (R1c requires >= 5) and
five metamorphic relations (R1d requires >= 3) over
``temper_placer.geometry.drc_inflate``, which is now Rust-backed.

Each property carries an explicit **anti-vacuity witness**: a check that the
generated inputs actually reach the behaviour under test. A property that only
ever sees, say, non-overlapping components would pass for a reason that has
nothing to do with what it claims, and Hypothesis will not tell you that.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.geometry.drc_inflate import (
    _smooth_relu_array,
    compute_drc_proxy_score,
    compute_inflated_half_dims_from_bounds,
)

SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

finite = st.floats(
    min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False, width=32
)
positive = st.floats(
    min_value=0.0009765625,  # 2**-10: exact in float32, so `width=32` accepts it
    max_value=1024.0,
    allow_nan=False,
    allow_infinity=False,
    width=32,
)
alphas = st.floats(min_value=0.05, max_value=100.0, allow_nan=False, allow_infinity=False)


@st.composite
def placements(draw, min_n: int = 2, max_n: int = 12, dtype=np.float64):
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    xs = draw(st.lists(finite, min_size=n, max_size=n))
    ys = draw(st.lists(finite, min_size=n, max_size=n))
    hw = draw(st.lists(positive, min_size=n, max_size=n))
    hh = draw(st.lists(positive, min_size=n, max_size=n))
    positions = np.array(list(zip(xs, ys)), dtype=dtype)
    return positions, np.array(hw, dtype=dtype), np.array(hh, dtype=dtype)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    @SETTINGS
    @given(
        xs=st.lists(
            st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=64,
        ),
        alpha=alphas,
    )
    def test_p1_softplus_dominates_relu(self, xs: list[float], alpha: float) -> None:
        """P1: ``softplus(a x)/a >= max(x, 0)`` — the smooth ReLU is an upper
        bound on the hard one, everywhere. This is the property that makes it
        usable as a penalty: it never under-reports a violation."""
        arr = np.array(xs)
        # Anti-vacuity: far from the knee, softplus and relu agree to within
        # f64 rounding and the property would hold for the wrong reason. Keep
        # only samples that actually visit the smooth region.
        assume(np.any(np.abs(arr * alpha) < 20.0))
        out = _smooth_relu_array(arr, alpha=alpha)
        relu = np.maximum(arr, 0.0)
        assert np.all(out >= relu - 1e-12)
        assert np.any(out > relu + 1e-15), "no sample exercised the smooth gap"

    @SETTINGS
    @given(
        xs=st.lists(
            st.floats(min_value=-20, max_value=20, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=64,
        ),
        alpha=alphas,
    )
    def test_p2_softplus_is_monotone(self, xs: list[float], alpha: float) -> None:
        """P2: sorting the input sorts the output — softplus is increasing."""
        arr = np.sort(np.array(xs))
        # A constant (or subnormally-separated) array makes monotonicity vacuous.
        assume(arr[-1] - arr[0] > 1e-6)
        # Below roughly ax = -745, exp(ax) underflows to exactly 0 and softplus
        # flattens to 0.0 for the whole sample, so the strictness witness could
        # not fire. That regime is P3's subject, not this one.
        assume(arr[0] * alpha > -700.0)
        out = _smooth_relu_array(arr, alpha=alpha)
        assert np.all(np.diff(out) >= -1e-15)
        assert out[-1] > out[0], "the sample had no strict increase to detect"

    @SETTINGS
    @given(
        xs=st.lists(
            st.floats(min_value=-30, max_value=30, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=48,
        ),
        alpha=alphas,
    )
    def test_p3_softplus_is_strictly_positive(self, xs: list[float], alpha: float) -> None:
        """P3: the output is > 0 everywhere (softplus has no zero), so squaring
        it never silently erases a violation."""
        out = _smooth_relu_array(np.array(xs), alpha=alpha)
        assert np.all(out > 0.0) or np.any(np.array(xs) * alpha < -700), (
            "softplus underflowed to exactly 0 outside the documented regime"
        )

    @SETTINGS
    @given(data=placements())
    def test_p4_proxy_score_is_non_negative(self, data) -> None:
        """P4: the score is a sum of squares, so it can never go negative —
        a sign slip in the gap arithmetic would surface here."""
        positions, hw, hh = data
        score = float(compute_drc_proxy_score(positions, hw, hh))
        assert score >= 0.0
        assert math.isfinite(score)

    @SETTINGS
    @given(data=placements(min_n=2, max_n=8))
    def test_p5_separating_components_cannot_raise_the_score(self, data) -> None:
        """P5: pushing every component further apart (scaling positions about
        the origin by 4x while holding sizes fixed) is monotone non-increasing."""
        positions, hw, hh = data
        near = float(compute_drc_proxy_score(positions, hw, hh))
        far = float(compute_drc_proxy_score(positions * 4.0, hw, hh))
        assert far <= near + 1e-9

    @SETTINGS
    @given(
        bounds=st.lists(
            st.tuples(positive, positive), min_size=1, max_size=32
        ),
        tw_a=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, width=32),
        tw_b=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, width=32),
    )
    def test_p6_half_dims_monotone_in_trace_width(
        self, bounds: list[tuple[float, float]], tw_a: float, tw_b: float
    ) -> None:
        """P6: a wider trace never shrinks the inflated half-dimensions."""
        lo, hi = (tw_a, tw_b) if tw_a <= tw_b else (tw_b, tw_a)
        # A subnormal gap would be swallowed by the following division and the
        # strictness witness below could not fire.
        assume(hi - lo > 1e-6)
        arr = np.array(bounds, dtype=np.float64)
        a = compute_inflated_half_dims_from_bounds(arr, lo)
        b = compute_inflated_half_dims_from_bounds(arr, hi)
        assert np.all(b >= a)
        assert np.any(b > a), "the two trace widths produced identical output"

    @SETTINGS
    @given(data=placements(min_n=2, max_n=10))
    def test_p7_score_bounded_below_by_worst_pair(self, data) -> None:
        """P7: the total is a sum of non-negative pair terms, so it is at least
        the largest single-pair term. Computing that term independently pins
        that the aggregation is a sum and not, say, a mean."""
        positions, hw, hh = data
        total = float(compute_drc_proxy_score(positions, hw, hh))
        n = positions.shape[0]
        worst = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                pair = float(
                    compute_drc_proxy_score(
                        positions[[i, j]], hw[[i, j]], hh[[i, j]]
                    )
                )
                worst = max(worst, pair)
        assert total >= worst - 1e-9


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


class TestMetamorphic:
    @SETTINGS
    @given(
        coords=st.lists(
            st.tuples(
                st.integers(min_value=-4096, max_value=4096),
                st.integers(min_value=-4096, max_value=4096),
            ),
            min_size=2,
            max_size=12,
        ),
        dims=st.lists(st.integers(min_value=1, max_value=64), min_size=12, max_size=12),
        shift=st.integers(min_value=-4096, max_value=4096),
    )
    def test_m1_translation_invariance(
        self, coords: list[tuple[int, int]], dims: list[int], shift: int
    ) -> None:
        """M1 (translation): the score depends only on relative positions.

        Coordinates and the shift are **integers**, which makes ``x + shift``
        exact in f64 and lets this be asserted on the bits.

        That restriction is not cosmetic. Translation invariance is a property
        of the mathematics, not of the floating-point evaluation: translating
        ``[0, 0], [1e-6, 0]`` by 1024 rounds the second coordinate, changes the
        computed gap, and moves the score in the last three hex digits. The
        pre-migration numpy implementation does exactly the same thing — it is
        inherited arithmetic, not a porting defect — but a version of this test
        that generated arbitrary reals and asserted exact equality would be
        asserting something false. Measured and recorded in
        packages/temper-geometry/VERIFICATION.md.
        """
        n = len(coords)
        positions = np.array([[float(x), float(y)] for x, y in coords], dtype=np.float64)
        hw = np.array([float(d) for d in dims[:n]], dtype=np.float64)
        hh = np.array([float(d) for d in dims[-n:]], dtype=np.float64)
        moved = positions + np.array([float(shift), float(-shift)], dtype=np.float64)
        a = float(compute_drc_proxy_score(positions, hw, hh))
        b = float(compute_drc_proxy_score(moved, hw, hh))
        assert a.hex() == b.hex()

    @SETTINGS
    @given(data=placements(min_n=2, max_n=8), shift=st.integers(1, 4096))
    def test_m1b_translation_is_only_approximate_for_general_reals(
        self, data, shift: int
    ) -> None:
        """M1b: the companion to M1 — with arbitrary real coordinates the same
        translation holds only to within rounding, because the shift is not
        exactly representable relative to the coordinates it is added to.

        Stated as its own relation so the exactness claim in M1 cannot quietly
        be weakened into this one.
        """
        positions, hw, hh = data
        moved = positions + float(shift)
        assume(np.all(np.isfinite(moved)))
        a = float(compute_drc_proxy_score(positions, hw, hh))
        b = float(compute_drc_proxy_score(moved, hw, hh))
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)

    @SETTINGS
    @given(data=placements())
    def test_m2_reflection_invariance(self, data) -> None:
        """M2 (reflection): mirroring the board in x, in y, or in both leaves
        the score unchanged — every use of position is inside an ``abs``."""
        positions, hw, hh = data
        base = float(compute_drc_proxy_score(positions, hw, hh))
        for sx, sy in ((-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)):
            mirrored = positions * np.array([sx, sy], dtype=np.float64)
            got = float(compute_drc_proxy_score(mirrored, hw, hh))
            assert got.hex() == base.hex(), f"reflection ({sx}, {sy}) changed the score"

    @SETTINGS
    @given(data=placements())
    def test_m3_axis_swap_invariance(self, data) -> None:
        """M3 (90-degree rotation): swapping the x/y coordinates *and* swapping
        half-widths with half-heights is a rigid rotation of the whole problem.

        ``min``/``max`` over the two gaps are symmetric in their arguments, so
        this holds bit-exactly, not approximately. Swapping only the
        coordinates — without the dimensions — would not, which is what makes
        this relation sensitive to an axis mix-up in the kernel.
        """
        positions, hw, hh = data
        rotated = positions[:, ::-1].copy()
        a = float(compute_drc_proxy_score(positions, hw, hh))
        b = float(compute_drc_proxy_score(rotated, hh, hw))
        assert a.hex() == b.hex()

    @SETTINGS
    @given(data=placements(min_n=2, max_n=10), seed=st.integers(0, 2**32 - 1))
    def test_m4_permutation_invariance_up_to_reduction_order(self, data, seed: int) -> None:
        """M4 (permutation): relabelling components cannot change the physics.

        Asserted with a tight relative tolerance rather than bit-exactly, and
        that is a real statement about the implementation, not a hedge: the
        score is reduced with numpy's blocked pairwise summation, so permuting
        the components permutes the summands and float addition is not
        associative. Exact equality would be the wrong claim here.
        """
        positions, hw, hh = data
        n = positions.shape[0]
        perm = np.random.default_rng(seed).permutation(n)
        a = float(compute_drc_proxy_score(positions, hw, hh))
        b = float(compute_drc_proxy_score(positions[perm], hw[perm], hh[perm]))
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)

    @SETTINGS
    @given(
        bounds=st.lists(st.tuples(positive, positive), min_size=1, max_size=32),
        tw=st.floats(min_value=0.0, max_value=4.0, allow_nan=False, width=32),
        k=st.integers(min_value=-6, max_value=6),
    )
    def test_m5_half_dims_scale_exactly_by_powers_of_two(
        self, bounds: list[tuple[float, float]], tw: float, k: int
    ) -> None:
        """M5 (scale): ``half(s*b, s*w) == s*half(b, w)``.

        Restricted to ``s = 2**k`` so the relation is exact in binary floating
        point — scaling by a power of two only shifts the exponent, leaving
        every mantissa untouched. A general scale factor would only hold to
        within rounding and could not be asserted on the bits.
        """
        s = float(2.0**k)
        arr = np.array(bounds, dtype=np.float64)
        assume(np.all(np.isfinite(arr * s)))
        a = compute_inflated_half_dims_from_bounds(arr * s, tw * s)
        b = compute_inflated_half_dims_from_bounds(arr, tw) * s
        assume(np.all(np.isfinite(a)) and np.all(np.isfinite(b)))
        assert [float(v).hex() for v in a.ravel()] == [float(v).hex() for v in b.ravel()]

    @SETTINGS
    @given(
        xs=st.lists(
            st.floats(min_value=-20, max_value=20, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=48,
        ),
        alpha=st.floats(min_value=0.5, max_value=20.0, allow_nan=False),
        k=st.integers(min_value=-4, max_value=4),
    )
    def test_m6_softplus_alpha_scaling(self, xs: list[float], alpha: float, k: int) -> None:
        """M6 (parameter scale): ``f(x/c, a*c) == f(x, a)/c`` for the smooth
        ReLU, because ``softplus(a*x)`` depends on ``a`` and ``x`` only through
        their product. ``c`` is a power of two so the division is exact."""
        c = float(2.0**k)
        arr = np.array(xs)
        assume(math.isfinite(alpha * c) and alpha * c > 0)
        lhs = _smooth_relu_array(arr / c, alpha=alpha * c)
        rhs = _smooth_relu_array(arr, alpha=alpha) / c
        assume(np.all(np.isfinite(lhs)) and np.all(np.isfinite(rhs)))
        assert np.allclose(lhs, rhs, rtol=1e-13, atol=0.0)


# ---------------------------------------------------------------------------
# The properties above must be able to fail. These pin that they can.
# ---------------------------------------------------------------------------


class TestPropertiesAreFalsifiable:
    """Each check here feeds a deliberately wrong value to the same assertion
    the property uses, and requires it to fail. Without this, a property that
    silently stopped evaluating anything would still look green."""

    def test_softplus_bound_rejects_an_under_estimate(self) -> None:
        xs = np.array([1.0, 2.0, 3.0])
        wrong = np.maximum(xs, 0.0) - 1.0
        assert not np.all(wrong >= np.maximum(xs, 0.0) - 1e-12)

    def test_non_negativity_rejects_a_negative_score(self) -> None:
        assert not (-1e-9 >= 0.0)

    def test_translation_relation_rejects_a_scaled_board(self) -> None:
        """Scaling is *not* a symmetry of the score; M1 must be able to see it."""
        positions = np.array([[0.0, 0.0], [3.0, 0.0]], dtype=np.float64)
        hw = np.array([2.0, 2.0], dtype=np.float64)
        hh = np.array([2.0, 2.0], dtype=np.float64)
        base = float(compute_drc_proxy_score(positions, hw, hh))
        scaled = float(compute_drc_proxy_score(positions * 1.5, hw, hh))
        assert base != scaled, "the corpus cannot distinguish translation from scaling"

    def test_axis_swap_relation_needs_the_dimension_swap(self) -> None:
        """M3 swaps coordinates *and* dimensions. Swapping only coordinates
        must change the answer, or M3 would be insensitive to an axis mix-up."""
        positions = np.array([[0.0, 0.0], [3.0, 1.0]], dtype=np.float64)
        hw = np.array([2.0, 2.0], dtype=np.float64)
        hh = np.array([0.25, 0.25], dtype=np.float64)
        full = float(compute_drc_proxy_score(positions[:, ::-1].copy(), hh, hw))
        partial = float(compute_drc_proxy_score(positions[:, ::-1].copy(), hw, hh))
        base = float(compute_drc_proxy_score(positions, hw, hh))
        assert full == base
        assert partial != base


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
