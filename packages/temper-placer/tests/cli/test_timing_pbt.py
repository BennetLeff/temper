"""Property-based + metamorphic tests for the migrated cli/timing.py compute.

Wave 4, Phase 5 (cli/adapters/temper-workflow slice). These properties
exercise the migrated ``temper_orchestration.compare_stage`` and
``temper_orchestration.p95`` (the delegation shim
``temper_placer/cli/timing.py`` calls them); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_timing_rust_differential.py``.

Five properties (R1c) plus the error-behaviour property, all non-vacuously
guarded:

- T1. Verdict consistency: ``passed == (current_ms <= threshold_ms)``.
- T2. Floor monotonicity: for a fixed baseline/current/margin, raising
  ``floor_ms`` never lowers ``threshold_ms`` (IEEE multiply by the
  non-negative ``1 + margin`` is monotone; margin bounded to ``>= 0``).
- T3. Verdict monotone in current: ``passed`` is non-increasing in
  ``current_ms`` — a larger current never passes when a smaller one fails.
- T4. Zero/negative-baseline guard: ``baseline_ms <= 0`` ⇒ ``delta_pct``
  is exactly ``0.0``.
- T5. p95 of a constant list is the decimal-rounded constant
  (``round(c, 3)`` — CPython decimal round-half-to-even).
- T7. Empty ``p95`` raises ``IndexError`` exactly like the bare expression.

Three metamorphic relations (R1d):

- MT1. Zero-margin identity: with ``margin == 0.0``, ``threshold_ms`` is
  bit-exactly ``effective_baseline`` (IEEE ``x * 1.0 == x``).
- MT2. Floor dominance: with ``floor_ms > baseline_ms`` (strict —
  CPython ``max`` returns its first argument on a ``-0.0``/``+0.0`` tie, so
  the equality case is excluded), ``effective_baseline`` is bit-exactly
  ``floor_ms``.
- MT3. NaN-floor asymmetry (CPython ``max``): with a NaN ``floor_ms`` and
  positive baseline, ``effective_baseline`` is bit-exactly the baseline.

Every property carries a G4 vacuity mutant: a degenerate kernel is swapped
in via the ``_kernels`` indirection and the property's inner test is
re-run, asserting it fails. A property no mutant can break is not a
property.
"""

from __future__ import annotations

import pytest
import temper_orchestration as _to
from hypothesis import assume, given, settings
from hypothesis import strategies as st

_MS = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False, width=64
)
_MARGIN = st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
_FLOOR = st.floats(min_value=0.0, max_value=1e5, allow_nan=False, allow_infinity=False)
_VALUES = st.lists(
    st.floats(
        min_value=-1e4, max_value=1e5, allow_nan=False, allow_infinity=False, width=64
    ),
    min_size=1,
    max_size=40,
)

_SETTINGS = settings(max_examples=120, deadline=None)


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _Kernels:
    compare_stage = staticmethod(lambda *a: _to.compare_stage(*a))
    p95 = staticmethod(lambda *a: _to.p95(*a))


_kernels = _Kernels()
_KERNEL_NAMES = ("compare_stage", "p95")


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _assert_property_fails(property_fn, *args):
    """Run a hypothesis-wrapped property's inner test and require a failure."""
    with pytest.raises(
        (AssertionError, KeyError, AttributeError, TypeError, IndexError, pytest.fail.Exception)
    ):
        property_fn.hypothesis.inner_test(*args)


def _hex(x: float) -> str:
    return x.hex()


# ---------------------------------------------------------------------------
# compare_stage — properties
# ---------------------------------------------------------------------------


@_SETTINGS
@given(_MS, _MS, _MARGIN, _FLOOR)
def test_t1_verdict_consistency(baseline_ms, current_ms, margin, floor_ms):
    """T1: passed is exactly the comparison current_ms <= threshold_ms."""
    _, _, effective, threshold, passed = _kernels.compare_stage(
        baseline_ms, current_ms, margin, floor_ms
    )
    assert passed == (current_ms <= threshold)
    # threshold is derived from the floored baseline
    expected_effective = max(baseline_ms, floor_ms)
    assert effective.hex() == expected_effective.hex()


@_SETTINGS
@given(_MS, _MS, _MARGIN, _FLOOR, _FLOOR)
def test_t2_floor_monotonicity(baseline_ms, current_ms, margin, floor1, floor2):
    """T2: a higher floor never lowers the threshold (margins >= 0)."""
    _, _, eff1, thr1, _ = _kernels.compare_stage(baseline_ms, current_ms, margin, floor1)
    _, _, eff2, thr2, _ = _kernels.compare_stage(baseline_ms, current_ms, margin, floor2)
    if floor2 >= floor1:
        assert eff2 >= eff1
        assert thr2 >= thr1


@_SETTINGS
@given(_MS, _MS, _MS, _MARGIN, _FLOOR)
def test_t3_verdict_monotone_in_current(baseline_ms, current1, current2, margin, floor_ms):
    """T3: passed is non-increasing in current_ms."""
    _, _, _, _, p1 = _kernels.compare_stage(baseline_ms, current1, margin, floor_ms)
    _, _, _, _, p2 = _kernels.compare_stage(baseline_ms, current2, margin, floor_ms)
    if current1 <= current2:
        # non-increasing: it is never the case that a smaller current fails
        # while a larger one passes (p1 >= p2 as booleans)
        assert not ((not p1) and p2)


@_SETTINGS
@given(_MS, _MS, _MARGIN, _FLOOR)
def test_t4_zero_baseline_guard(baseline_ms, current_ms, margin, floor_ms):
    """T4: non-positive baselines short-circuit delta_pct to exactly 0.0."""
    _, delta_pct, _, _, _ = _kernels.compare_stage(
        baseline_ms, current_ms, margin, floor_ms
    )
    if baseline_ms <= 0.0:
        assert delta_pct == 0.0


# ---------------------------------------------------------------------------
# p95 — properties
# ---------------------------------------------------------------------------


@_SETTINGS
@given(st.floats(min_value=-1e4, max_value=1e5, allow_nan=False, allow_infinity=False), st.integers(min_value=1, max_value=20))
def test_t5_p95_constant_list(c, n):
    """T5: p95 of a constant list is round(c, 3) — the decimal rounding is
    part of the contract, so the property asserts the exact rounded value."""
    expected = round(c, 3)
    assert _kernels.p95([c] * n).hex() == expected.hex()


@_SETTINGS
@given(_VALUES)
def test_t7_p95_empty_raises(values):
    """T7: p95([]) raises IndexError exactly like the bare expression; a
    non-empty list never raises. Both arms run inside the inner test so a
    degenerate empty-tolerant kernel is caught by the vacuity mutant."""
    assert isinstance(_kernels.p95(values), float)
    with pytest.raises(IndexError):
        _kernels.p95([])


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@_SETTINGS
@given(_MS, _MS, _FLOOR)
def test_mt1_zero_margin_identity(baseline_ms, current_ms, floor_ms):
    """MT1: margin 0.0 -> threshold is bit-exactly effective_baseline."""
    _, _, effective, threshold, passed = _kernels.compare_stage(
        baseline_ms, current_ms, 0.0, floor_ms
    )
    assert threshold.hex() == effective.hex()
    assert passed == (current_ms <= effective)


@_SETTINGS
@given(_MS, _MS, _MARGIN, _FLOOR)
def test_mt2_floor_dominance(baseline_ms, current_ms, margin, floor_ms):
    """MT2: floor > baseline -> effective_baseline is bit-exactly floor."""
    assume(floor_ms > baseline_ms)
    _, _, effective, _, _ = _kernels.compare_stage(baseline_ms, current_ms, margin, floor_ms)
    assert effective.hex() == floor_ms.hex()


@_SETTINGS
@given(_MS, _MARGIN, _FLOOR)
def test_mt3_nan_floor_asymmetry(baseline_ms, margin, floor_ms):
    """MT3: CPython max(baseline, nan) == baseline — the Rust port must not
    use f64::max (which would return the NaN)."""
    import math

    _, _, effective, _, _ = _kernels.compare_stage(baseline_ms, 0.0, margin, math.nan)
    assert effective.hex() == max(baseline_ms, float("nan")).hex()
    # and the floor, when finite and dominant, is used exactly
    _, _, effective2, _, _ = _kernels.compare_stage(baseline_ms, 0.0, margin, floor_ms)
    assert effective2.hex() == max(baseline_ms, floor_ms).hex()


@_SETTINGS
@given(_VALUES, st.integers(min_value=0, max_value=10))
def test_mp1_p95_permutation_invariance(values, seed):
    """MP1: p95 is invariant under permutation of its input (sort is
    multiset-deterministic; equal values are indistinguishable)."""
    import random

    perm = list(values)
    rng = random.Random(seed)
    rng.shuffle(perm)
    assert _kernels.p95(perm).hex() == _kernels.p95(values).hex()


# ---------------------------------------------------------------------------
# G4 vacuity mutants — one per property. A degenerate kernel that the
# property tolerates means the property is vacuous.
# ---------------------------------------------------------------------------


def test_t1_fails_for_constant_threshold_kernel(_restore_kernels):
    """A kernel that always reports threshold = 0.0 breaks T1."""

    def constant_threshold(b, c, m, f):
        return (c - b, 0.0, 0.0, 0.0, c <= 0.0)

    _kernels.compare_stage = constant_threshold
    _assert_property_fails(test_t1_verdict_consistency, 100.0, 110.0, 0.2, 10.0)


def test_t2_fails_for_anti_monotone_floor_kernel(_restore_kernels):
    """A kernel whose threshold DECREASES with the floor breaks T2."""

    def anti_monotone(b, c, m, f):
        eff = max(b, f)
        return (c - b, 0.0, eff, eff * (1.0 + m) * (1.0 / (1.0 + f)), c <= 0.0)

    _kernels.compare_stage = anti_monotone
    _assert_property_fails(test_t2_floor_monotonicity, 100.0, 110.0, 0.2, 10.0, 20.0)


def test_t3_fails_for_non_monotone_verdict_kernel(_restore_kernels):
    """A kernel whose verdict is not monotone in current (passes only for
    exactly 100.0) breaks T3: a larger current (110) must not fail while a
    smaller one (100) passes."""

    def equality_verdict(b, c, m, f):
        eff = max(b, f)
        return (c - b, 0.0, eff, eff * (1.0 + m), c == 100.0)

    _kernels.compare_stage = equality_verdict
    _assert_property_fails(test_t3_verdict_monotone_in_current, 100.0, 90.0, 100.0, 0.2, 10.0)


def test_t4_fails_for_unconditional_division_kernel(_restore_kernels):
    """A kernel that divides even for a zero baseline breaks T4 (or raises)."""

    def unguarded(b, c, m, f):
        eff = max(b, f)
        return ((c - b) / b * 100.0 if b != 0 else float("nan"), (c - b), eff, eff * (1.0 + m), c <= eff * (1.0 + m))

    _kernels.compare_stage = unguarded
    _assert_property_fails(test_t4_zero_baseline_guard, 0.0, 5.0, 0.2, 10.0)


def test_t5_fails_for_no_rounding_kernel(_restore_kernels):
    """A p95 that skips the decimal rounding breaks T5."""

    def no_round(values):
        return sorted(values)[int(len(values) * 0.95)]

    _kernels.p95 = no_round
    _assert_property_fails(test_t5_p95_constant_list, 0.1234, 3)


def test_t7_fails_for_empty_tolerant_kernel(_restore_kernels):
    """A p95 that returns 0.0 for an empty list breaks T7 (the bare
    expression raises IndexError; only the timing_tighten call site guards
    empties with 0.0 in Python)."""

    def empty_tolerant(values):
        if not values:
            return 0.0
        return round(sorted(values)[int(len(values) * 0.95)], 3)

    _kernels.p95 = empty_tolerant
    _assert_property_fails(test_t7_p95_empty_raises, [1.0, 2.0])
