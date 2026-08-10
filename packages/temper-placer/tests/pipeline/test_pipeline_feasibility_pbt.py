"""Property-based tests (G4) and metamorphic relations (G5) for the
pipeline-feasibility Rust kernels (temper_orchestration), the verification
unit being the CLUSTER of pipeline/convergence.py + preflight.py +
derivation.py (per the 2026-08-05 G4 cluster ruling: one oracle, one corpus,
>=5 non-vacuous properties counted across the unit).

Module-to-property map (G4 — every module reached):
- convergence.py  -> P1 (record_loss), P2 (check_success), P3 (is_converged)
- preflight.py    -> P4 (component_area_ratio), P5 (proximity_rule_impossible)
- derivation.py   -> P6 (mains_voltage_to_class_code)
Plus MR1..MR4 metamorphic relations covering all three modules.

Reachability (G4): each property's generated input class genuinely reaches
the kernel branch it names — pinned by `test_property_input_classes_are_discriminating`
below, which asserts a concrete reachable witness for every property (a
property that cannot fail is worse than an absent one).

Non-vacuity: every property has a `test_pN_fails_for_<mutant>` companion
re-running the property via `hypothesis.inner_test` against a mutated kernel
(delegated through the `_KERNELS` indirection below) and asserting
AssertionError.

Exactness claims (G5): all four metamorphic relations are claimed BIT-EXACT.
MR1/MR3/MR4 use power-of-two scaling (exact in IEEE for finite inputs inside
the claimed range — no overflow, no denormals); MR2 appends a zero product to
the compensated sum, which is a bit-exact no-op (`t = hi + 0.0 = hi`,
`c += (hi - hi) + 0.0 = 0.0`, hi unchanged).
"""

from __future__ import annotations

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

# The kernels under test, routed through an indirection so mutation guards
# can swap in degenerate Python stand-ins (hypothesis.inner_test) and restore.
_KERNELS = {
    "record_loss": _to.record_loss,
    "check_success": _to.check_success,
    "is_converged": _to.is_converged,
    "component_area_ratio": _to.component_area_ratio,
    "proximity_rule": _to.proximity_rule_impossible,
    "zone_over_capacity": _to.zone_over_capacity,
    "mains_class": _to.mains_voltage_to_class_code,
    "thermal_clearance": _to.derive_thermal_clearance,
}

_FINITE = {"allow_nan": False, "allow_infinity": False}


@pytest.fixture
def _restore_kernels():
    saved = dict(_KERNELS)
    yield
    _KERNELS.clear()
    _KERNELS.update(saved)


# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

_POSITIVE = st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False)
_NONNEG = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)


@st.composite
def loss_triple(draw):
    """(best, loss, min_imp) with best > 0, min_imp in (0,1)."""
    best = draw(_POSITIVE)
    loss = draw(_NONNEG)
    min_imp = draw(st.floats(min_value=0.01, max_value=0.99, **_FINITE))
    return (best, loss, min_imp)


@st.composite
def metric_quad(draw):
    """(overlap, boundary, routing, margin) — arbitrary non-negative values."""
    return (
        draw(_NONNEG),
        draw(_NONNEG),
        draw(_NONNEG),
        draw(_NONNEG),
    )


@st.composite
def result_pairs(draw):
    """A non-empty list of (success, length) pairs."""
    n = draw(st.integers(min_value=1, max_value=8))
    return [
        (draw(st.booleans()), draw(_NONNEG)) for _ in range(n)
    ]


@st.composite
def board_case(draw):
    """(component_dims, board_w, board_h, keepout_dims) with usable > 0."""
    n_comp = draw(st.integers(min_value=0, max_value=8))
    dims = [(draw(_NONNEG), draw(_NONNEG)) for _ in range(n_comp)]
    bw = draw(st.floats(min_value=1.0, max_value=1e4, **_FINITE))
    bh = draw(st.floats(min_value=1.0, max_value=1e4, **_FINITE))
    keepout = [(draw(_NONNEG), draw(_NONNEG)) for _ in range(draw(st.integers(min_value=0, max_value=3)))]
    # ensure usable > 0 (the oracle's `ratio = total/usable if usable > 0 else 1.0`)
    usable = bw * bh - sum(w * h for w, h in keepout)
    if usable <= 0:
        keepout = []
    return (dims, bw, bh, keepout)


@st.composite
def proximity_case(draw):
    """(wa, ha, wb, hb, max_d) with the pair's widths/heights bounded."""
    return (
        draw(_NONNEG),
        draw(_NONNEG),
        draw(_NONNEG),
        draw(_NONNEG),
        draw(_NONNEG),
    )


@st.composite
def voltage_case(draw):
    # Explicit bounds exclude infinity (Hypothesis forbids allow_infinity with
    # min/max); NaN/infinity are pinned separately in the reachability test.
    return draw(st.floats(min_value=-1e4, max_value=1e5, allow_nan=False, allow_infinity=False))


# ---------------------------------------------------------------------------
# G4 — P1: record_loss improvement consistency
# ---------------------------------------------------------------------------


@given(loss_triple())
@settings(max_examples=200, deadline=30000)
def test_p1_record_loss_improvement_consistent(triple):
    """P1. record_loss's improvement flag and new-best are exactly the
    oracle's `(best - loss) / best >= min_improvement` decision.

    A degenerate kernel that never reports improvement (or always reports
    it) violates the consistency pin: whenever the recomputed ratio is at
    least `min_improvement`, the kernel must return `(loss, True)`, and
    otherwise `(best, False)`.
    """
    best, loss, min_imp = triple
    improved = (best - loss) / best >= min_imp
    new_best, flagged = _KERNELS["record_loss"](best, loss, min_imp)
    if improved:
        assert flagged is True and new_best == loss
    else:
        assert flagged is False and new_best == best


def test_p1_fails_for_never_improves_mutant(_restore_kernels):
    _KERNELS["record_loss"] = lambda best, loss, min_imp: (best, False)  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p1_record_loss_improvement_consistent.hypothesis.inner_test((100.0, 90.0, 0.01))


def test_p1_fails_for_always_improves_mutant(_restore_kernels):
    _KERNELS["record_loss"] = lambda best, loss, min_imp: (loss, True)  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p1_record_loss_improvement_consistent.hypothesis.inner_test((100.0, 99.5, 0.01))


# ---------------------------------------------------------------------------
# G4 — P2: check_success boundary equality
# ---------------------------------------------------------------------------


_CRITERIA = (0.01, 0.01, 1.0, 0.05)  # max_overlap, max_boundary, min_routing, min_margin


@given(metric_quad())
@settings(max_examples=200, deadline=30000)
def test_p2_check_success_boundary_and_beyond(quad):
    """P2. check_success uses strict comparisons: at-boundary values pass
    (equal is not greater/less) and every strictly-beyond value fails.

    A kernel that flips any comparison to `>=`/`<=` (or returns a constant)
    violates one of the two halves.
    """
    overlap, boundary, routing, margin = quad
    mo, mb, mr, mm = _CRITERIA
    # at-boundary: all exactly at their thresholds -> must pass
    assert _KERNELS["check_success"](mo, mb, mr, mm, mo, mb, mr, mm) is True
    # each metric strictly beyond its threshold alone -> must fail
    assert _KERNELS["check_success"](overlap + mo + 0.001, mb, mr, mm, mo, mb, mr, mm) is False
    assert _KERNELS["check_success"](mo, boundary + mb + 0.001, mr, mm, mo, mb, mr, mm) is False
    assert _KERNELS["check_success"](mo, mb, max(mr - 0.001, 0.0), mm, mo, mb, mr, mm) is False
    assert _KERNELS["check_success"](mo, mb, mr, max(mm - 0.001, 0.0), mo, mb, mr, mm) is False


def test_p2_fails_for_always_true_mutant(_restore_kernels):
    _KERNELS["check_success"] = lambda *a: True  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_check_success_boundary_and_beyond.hypothesis.inner_test((0.5, 0.5, 0.5, 0.5))


def test_p2_fails_for_ge_overlap_mutant(_restore_kernels):
    def ge_overlap(overlap, boundary, routing, margin, mo, mb, mr, mm):
        return not (overlap >= mo) and boundary <= mb and routing >= mr and margin >= mm

    _KERNELS["check_success"] = ge_overlap
    with pytest.raises(AssertionError):
        test_p2_check_success_boundary_and_beyond.hypothesis.inner_test((0.5, 0.5, 0.5, 0.5))


# ---------------------------------------------------------------------------
# G4 — P3: is_converged stagnation on identical pairs
# ---------------------------------------------------------------------------


@given(result_pairs())
@settings(max_examples=200, deadline=30000)
def test_p3_is_converged_identical_pairs(pairs):
    """P3. Identical non-all-success pair lists converge (equal success count
    AND equal compensated length within 1e-6), and the same success counts
    with shifted lengths do NOT converge.

    A degenerate kernel that always returns False (never converges) or one
    that compares success counts only (ignoring the length band) violates one
    of the two halves.
    """
    assert _KERNELS["is_converged"](pairs, pairs) is True
    shifted = [(s, length + 1.0) for s, length in pairs]
    if all(s for s, _ in pairs):
        # all-success short-circuits regardless of the previous iteration.
        assert _KERNELS["is_converged"](pairs, shifted) is True
    else:
        assert _KERNELS["is_converged"](pairs, shifted) is False


def test_p3_fails_for_never_converges_mutant(_restore_kernels):
    _KERNELS["is_converged"] = lambda current, previous: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p3_is_converged_identical_pairs.hypothesis.inner_test([(False, 100.0), (False, 200.0)])


def test_p3_fails_for_success_count_only_mutant(_restore_kernels):
    def count_only(current, previous):
        if not current:
            return False
        return sum(1 for s, _ in current if s) == sum(1 for s, _ in previous if s)

    _KERNELS["is_converged"] = count_only
    # non-all-success pairs, equal success counts, lengths differ by 1.0:
    # the real kernel must NOT converge; the count-only mutant wrongly does.
    with pytest.raises(AssertionError):
        test_p3_is_converged_identical_pairs.hypothesis.inner_test([(False, 100.0)])


# ---------------------------------------------------------------------------
# G4 — P4: component_area_ratio bounded when the board is under-filled
# ---------------------------------------------------------------------------


@given(board_case())
@settings(max_examples=200, deadline=30000)
def test_p4_component_area_ratio_bounded(case):
    """P4. With no keepouts and component area at most the board area, the
    fill ratio lies in (0, 1].

    A degenerate kernel that inflates the ratio (e.g. adds a constant) breaks
    the bound on a board that is genuinely under-filled.
    """
    dims, bw, bh, keepout = case
    assert keepout == [] or (bw * bh - sum(w * h for w, h in keepout)) > 0
    total = sum(w * h for w, h in dims)
    usable = bw * bh - sum(w * h for w, h in keepout)
    if total <= usable:
        ratio, code = _KERNELS["component_area_ratio"](dims, bw, bh, keepout)
        assert 0.0 <= ratio <= 1.0
        # classification bands are consistent with the ratio
        assert (code == 0) == (ratio <= 0.7)
        assert (code == 1) == (0.7 < ratio <= 0.85)
        assert (code == 2) == (ratio > 0.85)


def test_p4_fails_for_inflated_ratio_mutant(_restore_kernels):
    def inflated(dims, bw, bh, keepout):
        total = sum(w * h for w, h in dims)
        usable = bw * bh - sum(w * h for w, h in keepout)
        ratio = total / usable if usable > 0 else 1.0
        return (ratio + 1.0, 0)

    _KERNELS["component_area_ratio"] = inflated
    with pytest.raises(AssertionError):
        test_p4_component_area_ratio_bounded.hypothesis.inner_test(
            ([(2.0, 2.0)], 10.0, 10.0, [])
        )


# ---------------------------------------------------------------------------
# G4 — P5: proximity_rule_impossible symmetric in the two components
# ---------------------------------------------------------------------------


@given(proximity_case())
@settings(max_examples=200, deadline=30000)
def test_p5_proximity_rule_symmetric(case):
    """P5. The min-spacing decision is symmetric in the two components:
    swapping (wa, ha) <-> (wb, hb) yields the identical (min_d, impossible).

    This is bit-exact: the width and height averages are the same additions
    in the same order, and the min is of identical values. A kernel that
    confuses the two components' dimensions (e.g. `wa * wb`) breaks it.
    """
    wa, ha, wb, hb, max_d = case
    a = _KERNELS["proximity_rule"](wa, ha, wb, hb, max_d)
    b = _KERNELS["proximity_rule"](wb, hb, wa, ha, max_d)
    assert a == b


def test_p5_fails_for_asymmetric_mutant(_restore_kernels):
    def asymmetric(wa, ha, wb, hb, max_d):
        # a genuine cross-term: ha * wb is NOT invariant under swapping the
        # two components, unlike the plus/average forms.
        min_d = min((wa + wb) / 2.0, (ha * wb) / 2.0)
        return (min_d, max_d < min_d)

    _KERNELS["proximity_rule"] = asymmetric
    with pytest.raises(AssertionError):
        test_p5_proximity_rule_symmetric.hypothesis.inner_test((3.0, 5.0, 7.0, 2.0, 1.0))


# ---------------------------------------------------------------------------
# G4 — P6: mains_voltage_to_class_code is a threshold partition
# ---------------------------------------------------------------------------


@given(voltage_case())
@settings(max_examples=200, deadline=30000)
def test_p6_mains_class_threshold_partition(v):
    """P6. The voltage classification is an exact threshold partition:
    code 0 iff v <= 50, code 1 iff 50 < v <= 130, code 2 iff 130 < v <= 264,
    code 3 otherwise (including NaN, which falls through every comparison).

    A kernel with a shifted boundary (e.g. `v <= 51`) violates the partition
    at a value between 50 and 51.
    """
    code = _KERNELS["mains_class"](v)
    if v <= 50.0:
        assert code == 0
    elif v <= 130.0:
        assert code == 1
    elif v <= 264.0:
        assert code == 2
    else:
        assert code == 3


def test_p6_fails_for_shifted_boundary_mutant(_restore_kernels):
    def shifted(v):
        if v <= 51.0:
            return 0
        elif v <= 130.0:
            return 1
        elif v <= 264.0:
            return 2
        return 3

    _KERNELS["mains_class"] = shifted
    with pytest.raises(AssertionError):
        test_p6_mains_class_threshold_partition.hypothesis.inner_test(50.5)


# ---------------------------------------------------------------------------
# Reachability (G4): the generated input classes genuinely reach the branch
# each property names. Each property has a concrete witness.
# ---------------------------------------------------------------------------


def test_property_input_classes_are_discriminating() -> None:
    # P1 improvement branch reachable: (100.0, 90.0, 0.01) has ratio 0.1 >= 0.01.
    best, loss, min_imp = 100.0, 90.0, 0.01
    assert (best - loss) / best >= min_imp
    new_best, flagged = _to.record_loss(best, loss, min_imp)
    assert flagged is True and new_best == loss
    # P1 non-improvement branch reachable.
    new_best, flagged = _to.record_loss(100.0, 99.5, 0.01)
    assert flagged is False and new_best == 100.0

    # P2 both halves reachable: at-boundary passes, beyond fails.
    assert _to.check_success(0.01, 0.01, 1.0, 0.05, 0.01, 0.01, 1.0, 0.05) is True
    assert _to.check_success(0.02, 0.01, 1.0, 0.05, 0.01, 0.01, 1.0, 0.05) is False

    # P3 identical non-success pairs converge.
    assert _to.is_converged([(False, 100.0), (False, 200.0)], [(False, 100.0), (False, 200.0)]) is True

    # P4 under-filled board bound reachable.
    ratio, code = _to.component_area_ratio([(2.0, 2.0)], 10.0, 10.0, [])
    assert 0.0 < ratio <= 1.0

    # P5 asymmetric-capable inputs: a cross-term asymmetry is genuinely
    # detectable on this input (the real kernel is symmetric, so this asserts
    # the INPUT class discriminates, not that the kernel differs from itself).
    cross_a = min((3.0 + 7.0) / 2.0, (5.0 * 7.0) / 2.0)
    cross_b = min((7.0 + 3.0) / 2.0, (2.0 * 3.0) / 2.0)
    assert cross_a != cross_b

    # P6 every band reachable, plus the NaN/inf fall-through to HIGH_VOLTAGE
    # (pinned outside the finite strategy).
    assert [_to.mains_voltage_to_class_code(v) for v in (50.0, 100.0, 200.0, 300.0)] == [0, 1, 2, 3]
    assert _to.mains_voltage_to_class_code(float("nan")) == 3
    assert _to.mains_voltage_to_class_code(float("inf")) == 3
    assert _to.mains_voltage_to_class_code(float("-inf")) == 0


# ---------------------------------------------------------------------------
# G5 — metamorphic relations (bit-exactness claimed explicitly)
# ---------------------------------------------------------------------------


@given(loss_triple())
@settings(max_examples=200, deadline=30000)
def test_mr1_record_loss_power_of_two_scale_invariance(triple):
    """MR1 (convergence.py). record_loss is invariant under power-of-two
    scaling of best and loss: the improvement flag is unchanged and the
    returned best scales exactly by 2. BIT-EXACT (power-of-two multiply and
    divide are exact for the finite, in-range values this strategy draws)."""
    best, loss, min_imp = triple
    flag = _KERNELS["record_loss"](best, loss, min_imp)[1]
    new_best, flag2 = _KERNELS["record_loss"](2.0 * best, 2.0 * loss, min_imp)
    assert flag == flag2
    assert new_best == 2.0 * _KERNELS["record_loss"](best, loss, min_imp)[0]


def test_mr1_fails_for_no_division_mutant(_restore_kernels):
    def no_division(best, loss, min_imp):
        # a kernel whose "improvement" test does NOT scale with the inputs:
        # `(best - loss) >= min_imp` doubles when the inputs double, so the
        # improvement flag flips across the scaling — violating MR1.
        if (best - loss) >= min_imp:
            return (loss, True)
        return (best, False)

    _KERNELS["record_loss"] = no_division
    with pytest.raises(AssertionError):
        # base: (100-50) = 50 < 60 -> not improved; scaled: (200-100) = 100 >= 60 -> improved
        test_mr1_record_loss_power_of_two_scale_invariance.hypothesis.inner_test(
            (100.0, 50.0, 60.0)
        )


@st.composite
def zone_case(draw):
    w = draw(st.floats(min_value=1.0, max_value=1e3, **_FINITE))
    h = draw(st.floats(min_value=1.0, max_value=1e3, **_FINITE))
    dims = [(draw(_NONNEG), draw(_NONNEG)) for _ in range(draw(st.integers(min_value=0, max_value=6)))]
    return (w, h, dims)


@given(zone_case())
@settings(max_examples=200, deadline=30000)
def test_mr2_zone_zero_product_append_is_noop(case):
    """MR2 (preflight.py). Appending a zero-area component to a zone's
    content is a bit-exact no-op: a `0.0 * h == 0.0` product enters the
    compensated sum without changing hi or the compensation. BIT-EXACT."""
    w, h, dims = case
    assert _KERNELS["zone_over_capacity"](w, h, dims) == _KERNELS["zone_over_capacity"](
        w, h, dims + [(0.0, 123.5)]
    )


def test_mr2_fails_for_wrong_area_formula_mutant(_restore_kernels):
    def wrong_area(w, h, dims):
        # content computed as sum(w) + sum(h) instead of sum(w*h): appending a
        # zero-width component adds 123.5 to this "content", flipping the
        # over-capacity decision — violating the append-is-noop relation.
        cap = w * h
        content = sum(cw for cw, _ in dims) + sum(ch for _, ch in dims)
        return content > cap * 0.9

    _KERNELS["zone_over_capacity"] = wrong_area
    with pytest.raises(AssertionError):
        # (10,10) zone, 90% = 90: base content 0.0 -> not over; appended
        # content 123.5 -> over.
        test_mr2_zone_zero_product_append_is_noop.hypothesis.inner_test(
            (10.0, 10.0, [(0.0, 0.0)])
        )


@given(board_case())
@settings(max_examples=200, deadline=30000)
def test_mr3_component_area_ratio_power_of_two_scale(case):
    """MR3 (preflight.py). Scaling every component dim, board dim and keepout
    dim by 2 leaves the fill ratio and its classification bit-identical.
    BIT-EXACT (power-of-two scaling; the compensated sums scale exactly)."""
    dims, bw, bh, keepout = case
    scale2 = lambda d: [(2.0 * w, 2.0 * h) for w, h in d]  # noqa: E731
    a = _KERNELS["component_area_ratio"](dims, bw, bh, keepout)
    b = _KERNELS["component_area_ratio"](scale2(dims), 2.0 * bw, 2.0 * bh, scale2(keepout))
    assert a == b


def test_mr3_fails_for_absolute_usable_mutant(_restore_kernels):
    def with_slack(dims, bw, bh, keepout):
        total = sum(w * h for w, h in dims)
        usable = bw * bh - sum(w * h for w, h in keepout) + 1.0
        ratio = total / usable if usable > 0 else 1.0
        return (ratio, 2 if ratio > 0.85 else (1 if ratio > 0.7 else 0))

    _KERNELS["component_area_ratio"] = with_slack
    with pytest.raises(AssertionError):
        test_mr3_component_area_ratio_power_of_two_scale.hypothesis.inner_test(
            ([(2.0, 2.0)], 10.0, 10.0, [])
        )


@given(st.floats(min_value=0.0, max_value=1e6, **_FINITE))
@settings(max_examples=200, deadline=30000)
def test_mr4_thermal_clearance_output_scale(power):
    """MR4 (derivation.py). Doubling the power dissipation doubles the
    derived clearance exactly: `derive_thermal_clearance(2p) == 2 *
    derive_thermal_clearance(p)`. BIT-EXACT (both multiplies are by exact
    powers of two)."""
    assert _KERNELS["thermal_clearance"](2.0 * power) == 2.0 * _KERNELS["thermal_clearance"](power)


def test_mr4_fails_for_additive_mutant(_restore_kernels):
    def additive(p):
        # `p * 2.0 + 0.5` breaks exact output-doubling: kernel(2p) = 4p + 0.5
        # but 2 * kernel(p) = 4p + 1.0.
        return p * 2.0 + 0.5

    _KERNELS["thermal_clearance"] = additive
    with pytest.raises(AssertionError):
        test_mr4_thermal_clearance_output_scale.hypothesis.inner_test(5.0)
