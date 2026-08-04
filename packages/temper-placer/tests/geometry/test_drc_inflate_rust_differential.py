"""R1a differential: the Rust DRC-inflation kernels vs the pinned Python oracle.

Wave 4, Phase 4 (geometry remainder). Every assertion here is **bit-exact**,
never a tolerance:

* floats are compared via :meth:`float.hex`, so a 1-ulp drift fails;
* every leaf carries its concrete ``type`` in the comparison key, so an
  ``int``/``float`` swap or an ``f32``/``f64`` width change cannot hide behind
  numeric equality. Geometry is exactly where dtype width bites: the
  pre-migration ``compute_drc_proxy_score`` is **dtype-polymorphic** — it does
  its pairwise gap arithmetic in the *caller's* dtype (the shipped call sites
  in ``tests/geometry/test_drc_inflate.py`` pass ``float32``) and only then
  widens to ``float64`` for the softplus. A Rust port that computed everything
  in ``f64`` would be numerically "close" and bit-wrong, so the dtype matrix
  below is not decoration.

The oracle is ``_drc_inflate_py_oracle.py``, a verbatim copy of the module at
``ebf9326ff``. ``benchmarks/perf_ab.py`` imports the *same* file, so the
behavioural and performance gates cannot drift apart.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from temper_placer.geometry import drc_inflate as rust_backed

_ORACLE_PATH = Path(__file__).parent / "_drc_inflate_py_oracle.py"
_spec = importlib.util.spec_from_file_location("_drc_inflate_py_oracle", _ORACLE_PATH)
assert _spec is not None and _spec.loader is not None
oracle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oracle)


# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def _leaf(v: object) -> tuple[str, str]:
    """A comparison key that carries the leaf's concrete type alongside its
    exact bits.

    ``float.hex()`` alone would let ``1`` and ``1.0`` compare equal, and would
    let a ``float32`` result that happens to round-trip compare equal to a
    ``float64`` one. Pairing the bits with ``type(v).__name__`` closes both.
    """
    if isinstance(v, (np.floating, float)):
        return (type(v).__name__, float(v).hex())
    return (type(v).__name__, repr(v))


def assert_bit_identical(got: object, want: object, ctx: str) -> None:
    """Assert two results are bit-identical, including dtype and shape."""
    assert type(got) is type(want), f"{ctx}: type {type(got)!r} != {type(want)!r}"

    if isinstance(got, np.ndarray):
        assert isinstance(want, np.ndarray)
        assert got.dtype == want.dtype, f"{ctx}: dtype {got.dtype} != {want.dtype}"
        assert got.shape == want.shape, f"{ctx}: shape {got.shape} != {want.shape}"
        g = [_leaf(x) for x in got.ravel().tolist()]
        w = [_leaf(x) for x in want.ravel().tolist()]
        assert g == w, f"{ctx}: element bits differ"
        return

    if isinstance(got, tuple):
        assert isinstance(want, tuple)
        assert len(got) == len(want), f"{ctx}: arity {len(got)} != {len(want)}"
        for i, (a, b) in enumerate(zip(got, want)):
            assert _leaf(a) == _leaf(b), f"{ctx}[{i}]: {_leaf(a)} != {_leaf(b)}"
        return

    assert _leaf(got) == _leaf(want), f"{ctx}: {_leaf(got)} != {_leaf(want)}"


# ---------------------------------------------------------------------------
# Corpora
# ---------------------------------------------------------------------------

DTYPES = [np.float32, np.float64]


def _random_case(rng: np.random.Generator, n: int, dtype) -> tuple:
    positions = rng.uniform(-40.0, 40.0, size=(n, 2)).astype(dtype)
    hw = rng.uniform(0.05, 6.0, size=(n,)).astype(dtype)
    hh = rng.uniform(0.05, 6.0, size=(n,)).astype(dtype)
    return positions, hw, hh


# ---------------------------------------------------------------------------
# _smooth_relu_array
# ---------------------------------------------------------------------------


class TestSmoothReluArrayDifferential:
    """The vectorised softplus is the kernel every proxy score is built on."""

    @pytest.mark.parametrize("alpha", [1.0, 3.0, 10.0, 50.0, 0.25])
    def test_random_sweep(self, alpha: float) -> None:
        rng = np.random.default_rng(20260804)
        xs = rng.uniform(-8.0, 8.0, size=4096)
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=alpha),
            oracle._smooth_relu_array(xs, alpha=alpha),
            f"_smooth_relu_array(alpha={alpha})",
        )

    def test_branch_boundary_and_extremes(self) -> None:
        """``ax > 0`` is the branch split; straddle it exactly, and push both
        arms into the regime where the *other* arm would overflow."""
        xs = np.array(
            [
                0.0,
                -0.0,
                5e-324,  # smallest subnormal, ax > 0
                -5e-324,
                1e-300,
                -1e-300,
                0.1,
                -0.1,
                70.0,  # exp(+ax) would overflow; taken branch must not
                -70.0,
                1e308,
                -1e308,
                float("inf"),
                float("-inf"),
                float("nan"),
            ]
        )
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=10.0),
            oracle._smooth_relu_array(xs, alpha=10.0),
            "_smooth_relu_array(edge)",
        )

    @pytest.mark.parametrize("n", [0, 1, 2, 3, 7, 8, 9, 15, 16, 17, 127, 128, 129])
    def test_length_sensitivity(self, n: int) -> None:
        """numpy dispatches different inner loops by length; sweep the seams."""
        rng = np.random.default_rng(1000 + n)
        xs = rng.uniform(-3.0, 3.0, size=n)
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=10.0),
            oracle._smooth_relu_array(xs, alpha=10.0),
            f"_smooth_relu_array(len={n})",
        )

    def test_shape_is_preserved(self) -> None:
        rng = np.random.default_rng(5)
        xs = rng.uniform(-2.0, 2.0, size=(4, 5, 2))
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=10.0),
            oracle._smooth_relu_array(xs, alpha=10.0),
            "_smooth_relu_array(3d)",
        )

    def test_float32_input_is_widened_to_float64(self) -> None:
        """The oracle's ``np.asarray(x, dtype=np.float64)`` widens on entry;
        the result is ``float64`` even for a ``float32`` argument."""
        xs = np.linspace(-2.0, 2.0, 33, dtype=np.float32)
        want = oracle._smooth_relu_array(xs, alpha=10.0)
        assert want.dtype == np.float64
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=10.0), want, "_smooth_relu_array(f32 in)"
        )

    def test_python_list_input(self) -> None:
        xs = [-1.5, -0.25, 0.0, 0.25, 1.5]
        assert_bit_identical(
            rust_backed._smooth_relu_array(xs, alpha=10.0),
            oracle._smooth_relu_array(xs, alpha=10.0),
            "_smooth_relu_array(list)",
        )


# ---------------------------------------------------------------------------
# compute_inflated_half_dims_from_bounds
# ---------------------------------------------------------------------------


class TestInflatedHalfDimsDifferential:
    @pytest.mark.parametrize("dtype", DTYPES)
    @pytest.mark.parametrize("n", [0, 1, 2, 17, 64])
    def test_random_bounds(self, dtype, n: int) -> None:
        rng = np.random.default_rng(7 * n + hash(str(dtype)) % 1000)
        bounds = rng.uniform(0.0, 30.0, size=(n, 2)).astype(dtype)
        assert_bit_identical(
            rust_backed.compute_inflated_half_dims_from_bounds(bounds, 0.25),
            oracle.compute_inflated_half_dims_from_bounds(bounds, 0.25),
            f"half_dims({dtype}, n={n})",
        )

    @pytest.mark.parametrize("dtype", DTYPES)
    def test_dtype_is_load_bearing(self, dtype) -> None:
        """float32 and float64 give *different* bits for the same numbers.

        This is the trap the R1a gate exists for: ``(w + 0.25) / 2`` rounds in
        the input's own width. If this assertion ever stops holding, the
        dtype-matrix coverage above has become vacuous and must be revisited.
        """
        bounds = np.array([[1.5499999523162842, 0.949999988079071]], dtype=dtype)
        got = oracle.compute_inflated_half_dims_from_bounds(bounds, 0.25)
        assert got.dtype == dtype
        wide = oracle.compute_inflated_half_dims_from_bounds(
            bounds.astype(np.float64), 0.25
        )
        if dtype is np.float32:
            assert float(got[0, 1]).hex() != float(wide[0, 1]).hex()

    @pytest.mark.parametrize("trace_width", [0.0, 0.1, 0.25, 1.0, 2.5, -0.25])
    def test_trace_width_sweep(self, trace_width: float) -> None:
        bounds = np.array(
            [[10.0, 5.0], [8.0, 4.0], [0.0, 0.0], [1e-6, 1e6]], dtype=np.float32
        )
        assert_bit_identical(
            rust_backed.compute_inflated_half_dims_from_bounds(bounds, trace_width),
            oracle.compute_inflated_half_dims_from_bounds(bounds, trace_width),
            f"half_dims(tw={trace_width})",
        )

    def test_trace_width_must_narrow_before_the_add(self) -> None:
        """The weak scalar is cast to the array's dtype *before* the addition.

        Added after a mutation survived: narrowing only the sum (rather than
        the trace width first) passed every other case here. 0.1 differs
        between f32 and f64, and this bound is the smallest searched value at
        which the two orders of rounding disagree.
        """
        bounds = np.array([[0.14703835546970367, 3.0]], dtype=np.float32)
        want = oracle.compute_inflated_half_dims_from_bounds(bounds, 0.1)
        # Guard that this input really does discriminate, so the assertion
        # below cannot pass for the trivial reason.
        naive = np.float32((np.float32(bounds[0, 0]) + np.float64(0.1)) / np.float32(2.0))
        assert float(want[0, 0]).hex() != float(naive).hex()
        assert_bit_identical(
            rust_backed.compute_inflated_half_dims_from_bounds(bounds, 0.1),
            want,
            "half_dims(tw=0.1, discriminating bound)",
        )

    def test_default_trace_width(self) -> None:
        bounds = np.array([[3.0, 2.0]], dtype=np.float32)
        assert_bit_identical(
            rust_backed.compute_inflated_half_dims_from_bounds(bounds),
            oracle.compute_inflated_half_dims_from_bounds(bounds),
            "half_dims(default)",
        )

    def test_arbitrary_shape_is_preserved(self) -> None:
        """The oracle is shape-agnostic — it never indexes, it broadcasts."""
        bounds = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
        assert_bit_identical(
            rust_backed.compute_inflated_half_dims_from_bounds(bounds, 0.25),
            oracle.compute_inflated_half_dims_from_bounds(bounds, 0.25),
            "half_dims(3d)",
        )


# ---------------------------------------------------------------------------
# compute_drc_proxy_score
# ---------------------------------------------------------------------------


class TestDRCProxyScoreDifferential:
    @pytest.mark.parametrize("dtype", DTYPES)
    @pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 5, 9, 13, 20, 40])
    def test_random_placements(self, dtype, n: int) -> None:
        """n=13 gives 78 pairs, n=20 gives 190, n=40 gives 780 — straddling
        numpy's pairwise-summation blocksize (128) and its 8-way unroll, where
        float addition is *not* associative."""
        rng = np.random.default_rng(31 * n + (1 if dtype is np.float32 else 2))
        positions, hw, hh = _random_case(rng, n, dtype)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh),
            oracle.compute_drc_proxy_score(positions, hw, hh),
            f"proxy_score({dtype}, n={n})",
        )

    @pytest.mark.parametrize("dtype", DTYPES)
    def test_dense_overlap(self, dtype) -> None:
        """Every pair overlapping drives the *other* arm of the
        ``both_negative`` select, which random sparse placements rarely hit."""
        rng = np.random.default_rng(99)
        n = 12
        positions = rng.uniform(-1.0, 1.0, size=(n, 2)).astype(dtype)
        hw = np.full(n, 5.0, dtype=dtype)
        hh = np.full(n, 5.0, dtype=dtype)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2),
            oracle.compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2),
            f"proxy_score(dense, {dtype})",
        )

    @pytest.mark.parametrize("clearance", [0.0, 0.05, 0.2, 1.0, 10.0])
    @pytest.mark.parametrize("beta", [1.0, 10.0, 40.0])
    def test_parameter_grid(self, clearance: float, beta: float) -> None:
        rng = np.random.default_rng(int(clearance * 1000) + int(beta))
        positions, hw, hh = _random_case(rng, 8, np.float32)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(
                positions, hw, hh, clearance_mm=clearance, beta=beta
            ),
            oracle.compute_drc_proxy_score(
                positions, hw, hh, clearance_mm=clearance, beta=beta
            ),
            f"proxy_score(c={clearance}, b={beta})",
        )

    def test_mixed_dtypes_promote_like_numpy(self) -> None:
        """positions float32 with half-dims float64 (and the reverse): the gap
        subtraction promotes, the ``abs`` before it does not."""
        rng = np.random.default_rng(4242)
        for pos_dt, hw_dt, hh_dt in [
            (np.float32, np.float64, np.float64),
            (np.float64, np.float32, np.float32),
            (np.float32, np.float32, np.float64),
            (np.float32, np.float64, np.float32),
        ]:
            positions = rng.uniform(-20.0, 20.0, size=(6, 2)).astype(pos_dt)
            hw = rng.uniform(0.5, 5.0, size=(6,)).astype(hw_dt)
            hh = rng.uniform(0.5, 5.0, size=(6,)).astype(hh_dt)
            assert_bit_identical(
                rust_backed.compute_drc_proxy_score(positions, hw, hh),
                oracle.compute_drc_proxy_score(positions, hw, hh),
                f"proxy_score(mixed {pos_dt}/{hw_dt}/{hh_dt})",
            )

    def test_degenerate_return_type_for_n_lt_2(self) -> None:
        """n<2 returns a 0-d ``ndarray``; n>=2 returns a ``np.float64`` scalar.

        The asymmetry is oracle behaviour and is preserved, not fixed.
        """
        for n in (0, 1):
            positions = np.zeros((n, 2), dtype=np.float32)
            hw = np.zeros((n,), dtype=np.float32)
            hh = np.zeros((n,), dtype=np.float32)
            want = oracle.compute_drc_proxy_score(positions, hw, hh)
            assert isinstance(want, np.ndarray) and want.ndim == 0
            assert_bit_identical(
                rust_backed.compute_drc_proxy_score(positions, hw, hh),
                want,
                f"proxy_score(n={n})",
            )

        positions = np.zeros((2, 2), dtype=np.float32)
        hw = np.zeros((2,), dtype=np.float32)
        hh = np.zeros((2,), dtype=np.float32)
        want2 = oracle.compute_drc_proxy_score(positions, hw, hh)
        assert isinstance(want2, np.floating)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh), want2, "proxy_score(n=2)"
        )

    def test_coincident_components(self) -> None:
        """All components stacked at one point: gap_x == gap_y, both negative,
        so ``min`` and ``max`` of the select agree — the tie branch."""
        n = 6
        positions = np.zeros((n, 2), dtype=np.float64)
        hw = np.full(n, 1.0, dtype=np.float64)
        hh = np.full(n, 1.0, dtype=np.float64)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh),
            oracle.compute_drc_proxy_score(positions, hw, hh),
            "proxy_score(coincident)",
        )

    def test_zero_size_components(self) -> None:
        rng = np.random.default_rng(77)
        n = 7
        positions = rng.uniform(-5.0, 5.0, size=(n, 2)).astype(np.float64)
        hw = np.zeros(n, dtype=np.float64)
        hh = np.zeros(n, dtype=np.float64)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh),
            oracle.compute_drc_proxy_score(positions, hw, hh),
            "proxy_score(zero-size)",
        )

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_positions_propagate_like_numpy(self, bad: float) -> None:
        """``np.maximum`` propagates a NaN from *either* operand; Rust's
        ``f64::max`` silently discards it and returns the other.

        Added after a mutation survived: swapping in ``f64::max`` passed every
        other case in this file, because nothing else here ever produced a
        non-finite gap. Note the ``np.minimum`` side is unreachable with a NaN
        by construction — it is guarded by ``gap_x < 0 and gap_y < 0``, which
        is False whenever a gap is NaN — so only the maximum arm is pinned
        here, and the Rust unit tests cover the helper directly.
        """
        positions = np.array([[0.0, 0.0], [3.0, 1.0], [bad, 2.0]], dtype=np.float64)
        hw = np.array([1.0, 1.0, 1.0], dtype=np.float64)
        hh = np.array([1.0, 1.0, 1.0], dtype=np.float64)
        want = oracle.compute_drc_proxy_score(positions, hw, hh)
        if np.isnan(bad):
            # A NaN must reach the result; if it did not, this case would not
            # be exercising the propagation the mutation exposed.
            assert np.isnan(want), "the NaN did not reach the score"
        else:
            # +/-inf gaps saturate the softplus to exactly 0 rather than
            # propagating, so the score stays finite. What is pinned here is
            # that Rust saturates identically.
            assert np.isfinite(want)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh),
            want,
            f"proxy_score(non-finite {bad})",
        )

    def test_non_finite_half_dims_propagate_like_numpy(self) -> None:
        positions = np.array([[0.0, 0.0], [3.0, 1.0]], dtype=np.float64)
        hw = np.array([float("nan"), 1.0], dtype=np.float64)
        hh = np.array([1.0, 1.0], dtype=np.float64)
        want = oracle.compute_drc_proxy_score(positions, hw, hh)
        assert not np.isfinite(want)
        assert_bit_identical(
            rust_backed.compute_drc_proxy_score(positions, hw, hh),
            want,
            "proxy_score(nan half-width)",
        )

    def test_summation_order_is_load_bearing(self) -> None:
        """Anti-vacuity for the pairwise-sum port.

        ``np.sum`` uses pairwise summation, not naive accumulation. If the two
        agreed, replicating numpy's blocked reduction in Rust would be
        pointless and the differential above would pass for the wrong reason.
        This pins that they genuinely differ on the corpus we test.
        """
        rng = np.random.default_rng(3)
        n = 40  # 780 pairs — well past the 128-element blocksize
        positions, hw, hh = _random_case(rng, n, np.float64)
        # Reproduce the oracle's array pipeline, then sum the two ways.
        center_diff = positions[:, None, :] - positions[None, :, :]
        gap_x = np.abs(center_diff[:, :, 0]) - (hw[:, None] + hw[None, :])
        gap_y = np.abs(center_diff[:, :, 1]) - (hh[:, None] + hh[None, :])
        both_negative = (gap_x < 0) & (gap_y < 0)
        distances = np.where(
            both_negative, np.minimum(gap_x, gap_y), np.maximum(gap_x, gap_y)
        )
        sq = oracle._smooth_relu_array(0.2 - distances, alpha=10.0) ** 2
        i_u, j_u = np.triu_indices(n, k=1)
        flat = sq[i_u, j_u]

        pairwise = float(np.sum(flat))
        naive = 0.0
        for v in flat.tolist():
            naive += v
        assert pairwise.hex() != naive.hex(), (
            "np.sum and naive accumulation agree on this corpus — the "
            "differential can no longer detect a wrong reduction order"
        )


# ---------------------------------------------------------------------------
# R3 boundary: the surfaces that are NOT migrated must still be the Python ones
# ---------------------------------------------------------------------------


class TestGeosBlockedSurfacesStayPython:
    """``inflate_pad_polygon`` / ``precompute_*`` keep GEOS as their engine.

    Recorded as JUSTIFIED-KEEP with a named blocker (see
    ``packages/temper-geometry/VERIFICATION.md``): shapely's
    ``buffer(r, resolution=16)`` is a *polygonal approximation* of the round
    offset, so its bounds are not the closed form ``bounds ± r`` and cannot be
    reproduced without vendoring GEOS. These tests pin the measurement that
    justifies the verdict, so the verdict is re-decidable rather than folklore.
    """

    def test_buffer_bounds_are_not_the_closed_form(self) -> None:
        shapely_geom = pytest.importorskip("shapely.geometry")
        rng = np.random.default_rng(2026)
        mismatched = 0
        total = 0
        worst = 0.0
        for _ in range(200):
            pts = rng.uniform(-10.0, 10.0, size=(5, 2)).tolist()
            poly = shapely_geom.Polygon(pts)
            if not poly.is_valid or poly.area == 0.0:
                continue
            r = 0.5
            got = poly.buffer(r, resolution=16).bounds
            ob = poly.bounds
            closed_form = (ob[0] - r, ob[1] - r, ob[2] + r, ob[3] + r)
            total += 1
            if any(a.hex() != b.hex() for a, b in zip(got, closed_form)):
                mismatched += 1
                worst = max(worst, max(abs(a - b) for a, b in zip(got, closed_form)))
        assert total > 0
        assert mismatched == total, (
            "GEOS buffer bounds now match the closed form exactly — the named "
            "blocker for the inflate_pad_polygon JUSTIFIED-KEEP no longer "
            "holds and the verdict must be re-decided"
        )
        assert worst > 1e-6, f"deviation collapsed to {worst}; re-decide the verdict"

    def test_python_surfaces_still_delegate_to_shapely(self) -> None:
        pytest.importorskip("shapely")
        pad = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
        assert_bit_identical(
            rust_backed.inflate_pad_polygon(pad, 0.25),
            oracle.inflate_pad_polygon(pad, 0.25),
            "inflate_pad_polygon",
        )
        assert_bit_identical(
            rust_backed.precompute_inflated_dims([pad, pad], 0.25),
            oracle.precompute_inflated_dims([pad, pad], 0.25),
            "precompute_inflated_dims",
        )
