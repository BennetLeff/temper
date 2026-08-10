"""Property-based + metamorphic tests for the mm/mil/inch unit kernels.

Wave 4 Phase A (plan ``docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md``,
``core/units.py`` row: ``Mm``, ``Mil``, ``Inch`` newtype wrappers over f64).
Bit-identical parity against the pinned reference expressions is asserted by
``test_units_rust_differential.py``; these properties exercise the kernels
through the ``temper_placer.core.units`` delegation shim (shim →
``temper_geometry`` → kernel), so reachability is through the production
entry point the plan's Phase A migration creates.

Properties (all non-vacuously guarded by a ``test_pN_fails_for_<mutant>``
companion re-running the property against a mutated kernel via
``hypothesis.inner_test``):

- P1. ``mil_to_mm`` is bit-identical to ``mil * 0.0254`` (the pinned
  reference), and doubling is exact.
- P2. ``mm_to_mil`` is bit-identical to ``mm / 0.0254`` — and is NOT the
  ``mm * 40.0`` shortcut, which diverges on every sampled value.
- P3. ``inch_to_mm`` / ``mm_to_inch`` are bit-identical to
  ``x * 25.4`` / ``x / 25.4``.
- P4. ``mil_to_inch`` / ``inch_to_mil`` are bit-identical to
  ``x / 1000.0`` / ``x * 1000.0`` — and NOT ``x * 0.001`` (division and
  multiplication by the reciprocal are different roundings).
- P5. Power-of-two scale invariance: ``f(2^k x) == 2^k f(x)`` bit-for-bit
  for all six kernels (rounding commutes with an exact scale).
- P6. Monotonicity: ``x1 <= x2 -> f(x1) <= f(x2)`` for all six kernels.
- P7. Round-trip bound: ``mil_to_mm(mm_to_mil(x))`` stays within the
  two-rounding band (relative error <= 2.3e-16); the identity is NOT
  claimed (double rounding).

Module → property map (every kernel reached): ``mil_to_mm`` P1/P5/P6/P7,
``mm_to_mil`` P2/P5/P6/P7, ``inch_to_mm`` P3/P5/P6, ``mm_to_inch`` P3/P5/P6,
``mil_to_inch`` P4/P5/P6, ``inch_to_mil`` P4/P5/P6.

Metamorphic relations (all in this file, exactness claims stated):

- M1. Sign symmetry (EXACT): ``f(-x) == -f(x)`` bit-for-bit for all six
  kernels — negation is a sign-bit flip and a positive scale commutes with
  it exactly.
- M2. Power-of-two scale (EXACT, same claim as P5): ``f(2^k x) == 2^k f(x)``.
- M3. Composition triangle (TIGHT TOLERANCE, stated band):
  ``inch_to_mm(mil_to_inch(x)) ~= mil_to_mm(x)`` within 2.3e-16 relative —
  exactness is NOT claimed because the composition double-rounds.
- M4. Round-trip is NOT the identity (documented): a witness exists where
  ``mm_to_mil(mil_to_mm(x)) != x``, and every sample stays within the
  derived two-rounding band.
"""

from __future__ import annotations

import math
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.units import (
    inch_to_mil,
    inch_to_mm,
    mil_to_inch,
    mil_to_mm,
    mm_to_inch,
    mm_to_mil,
)

MAX_EXAMPLES = 100

# Two-rounding band: each rounding contributes relative error <= 2^-53, so
# the composed error is <= 2^-53 + 2^-53 + 2^-106 ~= 2.221e-16. 2.3e-16 is
# the stated bound used everywhere a composition is asserted.
_TWO_ROUNDING_REL = 2.3e-16

# Three-rounding band: M3 compares a two-rounding composition against a
# one-rounding direct path, so up to three roundings separate them
# (~3.33e-16). 3.4e-16 is the stated bound.
_THREE_ROUNDING_REL = 3.4e-16

# Precondition floors: the relative-error bands hold only while every
# intermediate is a *normal* f64 (subnormal rounding error can be much
# larger than 2^-53 relative). Denormal behaviour is pinned separately by
# the differential's crafted edge cases; these properties assert the band
# on the normal domain and state the boundary.
_SCALE_FLOOR = 1e-150  # |scale * x| below this can underflow to subnormal
_BAND_FLOOR = 1e-100  # |x| below this can push intermediates into the denormal band


def _moderate() -> st.SearchStrategy[float]:
    return st.floats(
        min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False,
        allow_subnormal=False,
    )


def _hex(value: float) -> str:
    return float(value).hex()


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern). The
# seam delegates to the production shim; a vacuity mutant replaces one
# kernel and the property must FAIL.
# ---------------------------------------------------------------------------


class _UnitsKernels:
    mil_to_mm = staticmethod(mil_to_mm)
    mm_to_mil = staticmethod(mm_to_mil)
    inch_to_mm = staticmethod(inch_to_mm)
    mm_to_inch = staticmethod(mm_to_inch)
    mil_to_inch = staticmethod(mil_to_inch)
    inch_to_mil = staticmethod(inch_to_mil)


_kernels = _UnitsKernels()

_KERNEL_NAMES = (
    "mil_to_mm",
    "mm_to_mil",
    "inch_to_mm",
    "mm_to_inch",
    "mil_to_inch",
    "inch_to_mil",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


# ---------------------------------------------------------------------------
# P1 — mil_to_mm == x * 0.0254, bit-exact; doubling exact
# ---------------------------------------------------------------------------


@st.composite
def _lengths(draw):
    return draw(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
    )


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_mil_to_mm_matches_reference(x):
    if abs(x) < _BAND_FLOOR:
        return  # subnormal products break the exact-doubling guard (see doc)
    got = _kernels.mil_to_mm(x)
    want = x * 0.0254
    assert _hex(got) == _hex(want), f"mil_to_mm({x!r}): {got!r} vs {want!r}"
    # Vacuity guard: doubling (exact power-of-two scale) must be exact.
    assert _hex(_kernels.mil_to_mm(2.0 * x)) == _hex(2.0 * got)


def test_p1_fails_for_constant_mil_to_mm(_restore_kernels):
    _kernels.mil_to_mm = lambda *_a, **_k: 1.0
    with pytest.raises(AssertionError):
        test_p1_mil_to_mm_matches_reference.hypothesis.inner_test(5.0)


# ---------------------------------------------------------------------------
# P2 — mm_to_mil == x / 0.0254, bit-exact; NOT x * 40.0
# ---------------------------------------------------------------------------


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_mm_to_mil_matches_reference(x):
    got = _kernels.mm_to_mil(x)
    want = x / 0.0254
    assert _hex(got) == _hex(want), f"mm_to_mil({x!r}): {got!r} vs {want!r}"
    # Vacuity: the reference is genuinely the division — the x*40.0 shortcut
    # diverges from it (pinned by test_p2_fails_for_mm_times_40_shortcut and
    # the differential's test_oracle_discriminates_wrong_scale).


def test_p2_fails_for_mm_times_40_shortcut(_restore_kernels):
    _kernels.mm_to_mil = lambda x: x * 40.0
    with pytest.raises(AssertionError):
        test_p2_mm_to_mil_matches_reference.hypothesis.inner_test(1.0)


# ---------------------------------------------------------------------------
# P3 — inch_to_mm / mm_to_inch == x * 25.4 / x / 25.4, bit-exact
# ---------------------------------------------------------------------------


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_inch_conversions_match_reference(x):
    got_in = _kernels.inch_to_mm(x)
    want_in = x * 25.4
    assert _hex(got_in) == _hex(want_in), f"inch_to_mm({x!r}): {got_in!r} vs {want_in!r}"
    got_mm = _kernels.mm_to_inch(x)
    want_mm = x / 25.4
    assert _hex(got_mm) == _hex(want_mm), f"mm_to_inch({x!r}): {got_mm!r} vs {want_mm!r}"


def test_p3_fails_for_wrong_inch_factor(_restore_kernels):
    _kernels.inch_to_mm = lambda x: x * 25.3
    with pytest.raises(AssertionError):
        test_p3_inch_conversions_match_reference.hypothesis.inner_test(2.0)


# ---------------------------------------------------------------------------
# P4 — mil_to_inch / inch_to_mil == x / 1000 / x * 1000, bit-exact
# ---------------------------------------------------------------------------


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_mil_inch_conversions_match_reference(x):
    got = _kernels.mil_to_inch(x)
    want = x / 1000.0
    assert _hex(got) == _hex(want), f"mil_to_inch({x!r}): {got!r} vs {want!r}"
    got2 = _kernels.inch_to_mil(x)
    want2 = x * 1000.0
    assert _hex(got2) == _hex(want2), f"inch_to_mil({x!r}): {got2!r} vs {want2!r}"


def test_p4_fails_for_multiplicative_inverse_shortcut(_restore_kernels):
    # x / 1000.0 is NOT x * 0.001 (different roundings) — the two agree at
    # x == 1.0 but diverge at large exponents; use a measured discriminator.
    _kernels.mil_to_inch = lambda x: x * 0.001
    with pytest.raises(AssertionError):
        test_p4_mil_inch_conversions_match_reference.hypothesis.inner_test(
            4.998506083577941e32
        )


# ---------------------------------------------------------------------------
# P5 — power-of-two scale invariance, bit-exact for all six kernels
# ---------------------------------------------------------------------------


@given(_moderate(), st.integers(min_value=-20, max_value=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_power_of_two_scale_is_exact(x, k):
    scale = 2.0**k
    scaled = scale * x
    # Precondition: the exactness claim needs every intermediate normal and
    # finite — a scaled input underflowing to a subnormal breaks the
    # power-of-two argument (see _BAND_FLOOR doc).
    if not math.isfinite(scaled) or scaled == 0.0 or abs(scaled) < _SCALE_FLOOR:
        return
    for name in _KERNEL_NAMES:
        kernel = getattr(_kernels, name)
        assert _hex(kernel(scaled)) == _hex(scale * kernel(x)), (
            f"{name}: scale={scale} x={x!r}"
        )


def test_p5_fails_for_scale_insensitive_kernel(_restore_kernels):
    _kernels.mil_to_mm = lambda x: 1.0
    with pytest.raises(AssertionError):
        test_p5_power_of_two_scale_is_exact.hypothesis.inner_test(1.0, 3)


# ---------------------------------------------------------------------------
# P6 — monotonicity for all six kernels
# ---------------------------------------------------------------------------


@given(_lengths(), _lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_all_kernels_monotonic(a, b):
    x1, x2 = (a, b) if a <= b else (b, a)
    for name in _KERNEL_NAMES:
        kernel = getattr(_kernels, name)
        assert kernel(x1) <= kernel(x2), (
            f"{name}: {x1!r} <= {x2!r} but {kernel(x1)!r} > {kernel(x2)!r}"
        )


def test_p6_fails_for_non_monotone_kernel(_restore_kernels):
    _kernels.mm_to_mil = lambda x: -x
    with pytest.raises(AssertionError):
        test_p6_all_kernels_monotonic.hypothesis.inner_test(1.0, 2.0)


# ---------------------------------------------------------------------------
# P7 — round-trip stays inside the two-rounding band (identity NOT claimed)
# ---------------------------------------------------------------------------


@given(_moderate())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p7_round_trip_within_two_rounding_bound(x):
    if x == 0.0:
        # Zero round-trips exactly; assert it rather than skipping it.
        assert _kernels.mil_to_mm(_kernels.mm_to_mil(0.0)) == 0.0
        return
    if abs(x) < _BAND_FLOOR:
        return  # subnormal intermediates break the relative band (see doc)
    back = _kernels.mil_to_mm(_kernels.mm_to_mil(x))
    assert abs(back - x) <= _TWO_ROUNDING_REL * abs(x), (
        f"mm->mil->mm({x!r}) = {back!r}"
    )
    back2 = _kernels.mm_to_mil(_kernels.mil_to_mm(x))
    assert abs(back2 - x) <= _TWO_ROUNDING_REL * abs(x), (
        f"mil->mm->mil({x!r}) = {back2!r}"
    )


def test_p7_fails_for_identity_round_trip(_restore_kernels):
    # A degenerate "round trip" that skips the mil step entirely is not a
    # conversion: mm_to_mil(x) = x makes mil_to_mm(x) = x * 0.0254, which
    # violates the band.
    _kernels.mm_to_mil = lambda x: x
    with pytest.raises(AssertionError):
        test_p7_round_trip_within_two_rounding_bound.hypothesis.inner_test(1.0)


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_m1_sign_symmetry_exact(x):
    """M1 (EXACT): ``f(-x) == -f(x)`` bit-for-bit for all six kernels."""
    for name in _KERNEL_NAMES:
        kernel = getattr(_kernels, name)
        assert _hex(kernel(-x)) == _hex(-kernel(x)), (
            f"{name}: sign symmetry broken at x={x!r}"
        )


@given(_moderate(), st.integers(min_value=-20, max_value=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_m2_power_of_two_scale_exact(x, k):
    """M2 (EXACT): ``f(2^k x) == 2^k f(x)`` bit-for-bit for all six kernels."""
    scale = 2.0**k
    scaled = scale * x
    if not math.isfinite(scaled) or scaled == 0.0 or abs(scaled) < _SCALE_FLOOR:
        return  # same normal-domain precondition as P5
    for name in _KERNEL_NAMES:
        kernel = getattr(_kernels, name)
        assert _hex(kernel(scaled)) == _hex(scale * kernel(x)), (
            f"{name}: scale={scale} x={x!r}"
        )


@given(_moderate())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_m3_composition_triangle_within_band(x):
    """M3 (TIGHT TOLERANCE, band stated): ``inch_to_mm(mil_to_inch(x))``
    stays within the three-rounding band of ``mil_to_mm(x)``. Exactness is
    NOT claimed — the composition double-rounds against the direct path's
    single rounding, which is why this relation has a tolerance (3.4e-16)
    while M1/M2 are bit-exact."""
    direct = _kernels.mil_to_mm(x)
    composed = _kernels.inch_to_mm(_kernels.mil_to_inch(x))
    if x == 0.0:
        assert direct == 0.0 and composed == 0.0
        return
    if abs(x) < _BAND_FLOOR:
        return  # subnormal intermediates break the relative band (see doc)
    denom = max(abs(direct), abs(composed))
    assert denom > 0.0
    assert abs(composed - direct) <= _THREE_ROUNDING_REL * denom, (
        f"x={x!r}: direct {direct!r} vs composed {composed!r}"
    )


@given(_lengths())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_m4_round_trip_not_identity_within_band(x):
    """M4 (documented non-identity, bounded): ``mm_to_mil(mil_to_mm(x))`` is
    NOT ``x`` in general — double rounding — but every sample stays inside
    the derived band. This mirrors the deg→rad→deg precedent: the relation
    is recorded as NOT exact, and the band is the honest bound."""
    back = _kernels.mm_to_mil(_kernels.mil_to_mm(x))
    assert abs(back - x) <= _TWO_ROUNDING_REL * max(abs(back), abs(x), 1e-300), (
        f"x={x!r}: round trip {back!r}"
    )


def test_m4_witness_of_non_identity_exists():
    """A concrete witness that the round trip is not the identity (so the
    non-exactness claim in M4 is pinned, not assumed)."""
    witness = next(x for x in (0.1, 0.2, 0.3, 0.7, 1.1, 3.7) if mm_to_mil(mil_to_mm(x)) != x)
    assert witness is not None


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_UNITS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(__import__("temper_geometry"), "mil_to_mm"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_UNITS=1 but temper_geometry does not expose the "
        "units kernels — the Rust extension is stale or missing.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(__import__("temper_geometry"), "mil_to_mm"),
    reason="temper_geometry units kernels not installed "
    "(set TEMPER_REQUIRE_RUST_UNITS=1 to make this fatal instead of a skip)",
)
