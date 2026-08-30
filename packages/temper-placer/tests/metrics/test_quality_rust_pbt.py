"""Property-based and metamorphic tests for the Rust placement-metric kernels
(Wave 4 Phase 4 — ``temper-quality-oracle::placement_metrics``).

Gate coverage:

- **R1c** — eight properties (P1..P8), each paired with a
  ``test_pN_fails_for_<mutant>`` that swaps in a degenerate kernel and asserts
  the property *fails*.  A property nothing can break is not a property.
- **R1d** — four metamorphic relations (MR1..MR4), each with its exactness
  claim stated honestly:

  | Relation | Claim |
  |---|---|
  | MR1 translation invariance (clearance) | **bit-exact**, bounded to integer coordinates and integer offsets, where every `x + t` and `x - y` is exactly representable |
  | MR2 scale covariance (loop area) | **bit-exact**, bounded to power-of-two scale factors within the exponent range — binary FP scales by 2^k with no rounding |
  | MR3 permutation invariance | **bit-exact for the min/count reductions** (`dual_rail_clearance_report`); **explicitly NOT claimed** for `thermal_score`, which is a float sum and genuinely reorders — MR3b bounds that one instead of asserting a falsehood |
  | MR4 point reflection (loop area) | **bit-exact** — negating both coordinates leaves every shoelace cross term identical, sign included |

The honest bounding matters here.  ``thermal_score`` aggregates with ``+=``
over a ``set``; permutation invariance is *false* for it at the bit level and
asserting it would encode a bug as a requirement.  MR3b states what is
actually true — the spread across permutations is tiny but nonzero — and the
differential suite pins that Rust reproduces Python for each individual order.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
import temper_quality_oracle as _tqo
from hypothesis import assume, given, settings
from hypothesis import strategies as st

BOUNDS = (0.0, 0.0, 100.0, 80.0)

coord = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)
extent = st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False)
positive = st.floats(min_value=0.5, max_value=1000.0, allow_nan=False, allow_infinity=False)


@st.composite
def clearance_boxes(draw, min_size=1, max_size=5):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [
        (draw(coord), draw(coord), draw(extent) / 2, draw(extent) / 2) for _ in range(n)
    ]


@st.composite
def polygon(draw, min_size=3, max_size=12):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [(draw(coord), draw(coord)) for _ in range(n)]


# ---------------------------------------------------------------------------
# P1 — every score is a probability
# ---------------------------------------------------------------------------


on_board = st.tuples(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=80.0, allow_nan=False, allow_infinity=False),
)


@given(
    pts=st.lists(on_board, min_size=1, max_size=8),
    md=positive,
    edge=st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"]),
)
@settings(max_examples=200, deadline=None)
def test_p1_thermal_score_is_a_probability(pts, md, edge):
    """P1: for components **inside the board**, thermal_score lands in [0, 1].

    The domain restriction is not decoration — see
    `test_p1_domain_restriction_is_real` below, which records that the metric
    genuinely exceeds 1.0 outside it.  A kernel that forgot the
    `max(0.0, ...)` clamp goes negative for any component further than
    `max_distance` from the edge, which these coordinates hit constantly, so
    the lower bound is not vacuously satisfied.
    """
    s = _tqo.thermal_score_py(pts, *BOUNDS, edge, md)
    assert 0.0 <= s <= 1.0, s


def test_p1_domain_restriction_is_real():
    """A pre-existing property of the metric, recorded rather than "fixed".

    `thermal_score` has no upper clamp: a component placed *beyond* the target
    edge gets a negative distance and therefore a score above 1.0.  P1 is
    honestly scoped to on-board placements because of this — claiming a
    universal [0, 1] bound would be false.

    This behaviour predates the migration and the Rust kernel reproduces it
    exactly (the differential pins it).  Adding a clamp here would be a
    behaviour change on shipped inputs, so it is documented, not altered.
    """
    beyond_the_top_edge = [(0.0, 81.0)]
    s = _tqo.thermal_score_py(beyond_the_top_edge, *BOUNDS, "TOP", 1.0)
    assert s == 2.0, s


def test_p1_fails_for_unclamped_kernel(_restore_thermal):
    """Vacuity guard: drop the lower clamp and P1 breaks."""
    _tqo.thermal_score_py = lambda *_a, **_k: -1.0
    with pytest.raises(AssertionError):
        test_p1_thermal_score_is_a_probability.hypothesis.inner_test(
            [(0.0, 0.0)], 1.0, "TOP"
        )


# ---------------------------------------------------------------------------
# P2 — clearance score is monotone in separation
# ---------------------------------------------------------------------------


@given(gap=st.floats(min_value=0.0, max_value=40.0), extra=st.floats(min_value=0.0, max_value=40.0))
@settings(max_examples=200, deadline=None)
def test_p2_clearance_is_monotone_in_separation(gap, extra):
    """P2: pushing the LV part further away never lowers the score.

    A kernel that mixed up `dx`/`dy` or dropped the `- half_w` terms would
    lose monotonicity somewhere in this range.
    """
    hv = [(0.0, 0.0, 1.0, 1.0)]
    near = [(2.0 + gap, 0.0, 1.0, 1.0)]
    far = [(2.0 + gap + extra, 0.0, 1.0, 1.0)]
    assert _tqo.hv_lv_clearance_score_py(hv, far, 8.0) >= _tqo.hv_lv_clearance_score_py(
        hv, near, 8.0
    )


def test_p2_fails_for_inverted_kernel(_restore_clearance):
    """Vacuity guard: invert the ramp and monotonicity breaks."""
    _tqo.hv_lv_clearance_score_py = lambda _hv, lv, _mc: -abs(lv[0][0])
    with pytest.raises(AssertionError):
        test_p2_clearance_is_monotone_in_separation.hypothesis.inner_test(0.0, 5.0)


# ---------------------------------------------------------------------------
# P3 — the 6 mm rail subsumes the 3 mm rail
# ---------------------------------------------------------------------------


@given(hv=clearance_boxes(), lv=clearance_boxes())
@settings(max_examples=200, deadline=None)
def test_p3_six_mm_violations_subsume_three_mm(hv, lv):
    """P3: every pair below 3 mm is also below 6 mm, and neither count can
    exceed the number of pairs.

    This is a containment property, not an arithmetic one — a kernel that
    compared against the wrong threshold, or counted pairs twice, fails it.
    """
    s3, s6, v3, v6 = _tqo.dual_rail_clearance_report_py(hv, lv)
    assert v3 <= v6
    assert 0 <= v6 <= len(hv) * len(lv)
    # A tighter rail can never score better than a looser one.
    assert s3 >= s6


def test_p3_fails_for_swapped_thresholds(_restore_dual):
    """Vacuity guard: swap the two rails and containment inverts."""
    _tqo.dual_rail_clearance_report_py = lambda *_a, **_k: (0.0, 1.0, 5, 1)
    with pytest.raises(AssertionError):
        test_p3_six_mm_violations_subsume_three_mm.hypothesis.inner_test(
            [(0.0, 0.0, 1.0, 1.0)], [(1.0, 1.0, 1.0, 1.0)]
        )


# ---------------------------------------------------------------------------
# P4 — degenerate polygons score perfectly
# ---------------------------------------------------------------------------


@given(
    xs=st.lists(st.floats(min_value=-100.0, max_value=100.0), min_size=3, max_size=10),
    y=st.floats(min_value=-100.0, max_value=100.0),
    max_area=positive,
)
@settings(max_examples=200, deadline=None)
def test_p4_collinear_loops_have_negligible_area(xs, y, max_area):
    """P4: a loop whose vertices are collinear encloses (essentially) no area,
    so it scores 1.0 up to cancellation error.

    Collinear points are the shoelace formula's null space.  The bound is
    stated as `>= 1 - 1e-9` rather than `== 1.0` because the cross terms
    cancel *numerically*, not symbolically — for a horizontal line at
    `y = 1.0` the terms are `x_i - x_{i+1}` scaled by y, and their pairwise
    sum lands within a few ulp of zero, not exactly on it.  Claiming exact
    equality here would be false; `test_p4_axis_aligned_loops_are_exactly_one`
    covers the sub-case where it *is* exact.

    A kernel that summed `|cross|` termwise instead of `|sum(cross)|` reports
    a large area here and fails by a wide margin.
    """
    verts = [(x, y) for x in xs]
    assert _tqo.loop_area_score_py([verts], max_area) >= 1.0 - 1e-9


def test_p4_axis_aligned_loops_are_exactly_one():
    """The exact sub-case: on the line y = 0 every cross term is exactly 0."""
    verts = [(0.0, 0.0), (10.0, 0.0), (25.5, 0.0), (3.25, 0.0)]
    assert _tqo.loop_area_score_py([verts], 1.0) == 1.0


def test_p4_fails_for_abs_per_term_kernel(_restore_loop):
    """Vacuity guard: a kernel that takes |x| per term, not of the sum."""

    def mutant(loops, max_area):
        total = 0.0
        for verts in loops:
            n = len(verts)
            area = (
                sum(
                    abs(verts[i][0] * verts[(i + 1) % n][1] - verts[(i + 1) % n][0] * verts[i][1])
                    for i in range(n)
                )
                / 2.0
            )
            total += max(0.0, 1.0 - area / max_area)
        return total / len(loops) if loops else 1.0

    _tqo.loop_area_score_py = mutant
    with pytest.raises(AssertionError):
        test_p4_collinear_loops_have_negligible_area.hypothesis.inner_test(
            [0.0, 10.0, 20.0], 5.0, 1.0
        )


# ---------------------------------------------------------------------------
# P5 — compactness is a bounded utilization
# ---------------------------------------------------------------------------


@st.composite
def parts(draw, min_size=2, max_size=8):
    """Matched-length position/extent lists — avoids a post-hoc `assume`."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return (
        [(draw(coord), draw(coord)) for _ in range(n)],
        [draw(extent) for _ in range(n)],
    )


@given(pe=parts())
@settings(max_examples=200, deadline=None)
def test_p5_compactness_never_exceeds_one(pe):
    """P5: compactness_score is clamped into [0, 1] even when parts overlap.

    Overlapping placements push raw utilization above 1.0 — the strategy
    generates them freely — so the clamp is exercised, not bypassed.
    """
    pts, ext = pe
    hw = [e / 2 for e in ext]
    areas = [e * e for e in ext]
    s = _tqo.compactness_score_py(pts, hw, hw, areas)
    assert 0.0 <= s <= 1.0, s


def test_p5_fails_for_unclamped_utilization(_restore_compact):
    """Vacuity guard: return raw utilization and the upper bound breaks."""
    _tqo.compactness_score_py = lambda *_a, **_k: 12.5
    with pytest.raises(AssertionError):
        test_p5_compactness_never_exceeds_one.hypothesis.inner_test(
            ([(0.0, 0.0), (0.0, 0.0)], [1.0, 1.0])
        )


# ---------------------------------------------------------------------------
# P7 — zone compliance is exactly a fraction of counted booleans
# ---------------------------------------------------------------------------


@given(flags=st.lists(st.booleans(), min_size=1, max_size=40))
@settings(max_examples=200, deadline=None)
def test_p7_zone_compliance_is_the_exact_fraction(flags):
    """P7: the score equals correct/total computed as an exact int ratio.

    Not a tautology: an implementation that accumulated `+= 1.0` in float, or
    that divided by the wrong denominator, diverges from the int ratio for
    counts whose quotient is not representable.
    """
    got = _tqo.zone_compliance_score_py(flags)
    expected = sum(1 for f in flags if f) / len(flags)
    assert got.hex() == expected.hex()


def test_p7_fails_for_off_by_one_denominator(_restore_zone):
    """Vacuity guard: divide by total+1 and the exact ratio breaks."""
    _tqo.zone_compliance_score_py = lambda flags: sum(flags) / (len(flags) + 1)
    with pytest.raises(AssertionError):
        test_p7_zone_compliance_is_the_exact_fraction.hypothesis.inner_test([True, False, True])


# ---------------------------------------------------------------------------
# P8 — clustering ratio cannot exceed 1
# ---------------------------------------------------------------------------


@given(pe=parts(max_size=6), as_f32=st.booleans())
@settings(max_examples=200, deadline=None)
def test_p8_clustering_ratio_is_bounded(pe, as_f32):
    """P8: the clustering ratio stays in [0, 1] in both dtype modes.

    The `max(actual_area, min_possible_area)` denominator is what enforces
    this; a kernel that divided by `actual_area` unconditionally exceeds 1.0
    whenever parts overlap, which this strategy produces often.
    """
    pts, ext = pe
    half = [e / 2 for e in ext]
    areas = [e * e for e in ext]
    s = _tqo.connectivity_clustering_score_py([(pts, half, half, areas)], as_f32)
    assert 0.0 <= s <= 1.0, s


def test_p8_fails_without_the_max_denominator(_restore_cluster):
    """Vacuity guard: divide by actual_area alone and the bound breaks."""
    _tqo.connectivity_clustering_score_py = lambda *_a, **_k: 4.0
    with pytest.raises(AssertionError):
        test_p8_clustering_ratio_is_bounded.hypothesis.inner_test(
            ([(0.0, 0.0), (0.0, 0.0)], [10.0, 10.0]), False
        )


# ---------------------------------------------------------------------------
# MR1 — translation invariance (clearance), bit-exact on integer lattices
# ---------------------------------------------------------------------------


@given(
    hx=st.integers(min_value=-200, max_value=200),
    lx=st.integers(min_value=-200, max_value=200),
    ly=st.integers(min_value=-200, max_value=200),
    tx=st.integers(min_value=-200, max_value=200),
    ty=st.integers(min_value=-200, max_value=200),
)
@settings(max_examples=200, deadline=None)
def test_mr1_clearance_is_translation_invariant(hx, lx, ly, tx, ty):
    """MR1: translating both rails by the same offset leaves the score
    **bit-identical**.

    Exactness claim, honestly bounded: this holds bit-exactly *only* because
    the coordinates and the offset are integers in a range where `x + t` and
    the subsequent difference are exactly representable in f64.  For general
    float offsets the relation holds only to within rounding, and this test
    deliberately does not claim it there.
    """
    hv = [(float(hx), 0.0, 1.0, 1.0)]
    lv = [(float(lx), float(ly), 1.5, 0.5)]
    hv_t = [(float(hx + tx), float(ty), 1.0, 1.0)]
    lv_t = [(float(lx + tx), float(ly + ty), 1.5, 0.5)]
    base = _tqo.dual_rail_clearance_report_py(hv, lv)
    moved = _tqo.dual_rail_clearance_report_py(hv_t, lv_t)
    assert base[0].hex() == moved[0].hex()
    assert base[1].hex() == moved[1].hex()
    assert base[2:] == moved[2:]


# ---------------------------------------------------------------------------
# MR2 — scale covariance (loop area), bit-exact for power-of-two factors
# ---------------------------------------------------------------------------


@given(verts=polygon(), k=st.integers(min_value=-8, max_value=8), max_area=positive)
@settings(max_examples=200, deadline=None)
def test_mr2_loop_area_is_scale_covariant(verts, k, max_area):
    """MR2: scaling every vertex by 2^k scales the enclosed area by 2^2k, so
    scaling `max_area` to match leaves the score **bit-identical**.

    Exactness claim, honestly bounded: multiplication by a power of two is
    exact in binary floating point (it only shifts the exponent), so every
    shoelace cross term scales exactly and the pairwise sum reassociates
    identically.  For a non-power-of-two factor the relation would hold only
    approximately, and this test does not claim it there.  Inputs that would
    over/underflow the exponent range are discarded rather than tolerated.
    """
    s = math.ldexp(1.0, k)
    scaled = [(x * s, y * s) for x, y in verts]
    scaled_max = max_area * s * s
    assume(all(math.isfinite(v) and v != 0.0 or v == 0.0 for p in scaled for v in p))
    assume(math.isfinite(scaled_max) and scaled_max > 0.0)
    base = _tqo.loop_area_score_py([verts], max_area)
    covariant = _tqo.loop_area_score_py([scaled], scaled_max)
    assert base.hex() == covariant.hex(), (k, base, covariant)


# ---------------------------------------------------------------------------
# MR3 — permutation: exact for min/count, honestly NOT exact for the sum
# ---------------------------------------------------------------------------


@given(hv=clearance_boxes(max_size=4), lv=clearance_boxes(max_size=4))
@settings(max_examples=150, deadline=None)
def test_mr3a_dual_rail_is_permutation_invariant(hv, lv):
    """MR3a: reordering the rails leaves the report **bit-identical**.

    Exact, and provably so: the report reduces with `min` and integer
    counting, both of which are order-independent for the finite values these
    strategies produce.  This is the relation that genuinely holds.
    """
    base = _tqo.dual_rail_clearance_report_py(hv, lv)
    for hv_p in itertools.islice(itertools.permutations(hv), 6):
        for lv_p in itertools.islice(itertools.permutations(lv), 6):
            got = _tqo.dual_rail_clearance_report_py(list(hv_p), list(lv_p))
            assert got[0].hex() == base[0].hex()
            assert got[1].hex() == base[1].hex()
            assert got[2:] == base[2:]


@given(
    ys=st.lists(
        st.floats(min_value=0.0, max_value=80.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=6,
    ),
    md=st.floats(min_value=1.0, max_value=50.0),
)
@settings(max_examples=150, deadline=None)
def test_mr3b_thermal_score_permutation_is_bounded_not_exact(ys, md):
    """MR3b: thermal_score is **not** permutation-invariant, and we say so.

    It folds with `+=` over a set, and float addition does not reassociate.
    Asserting exact invariance would encode a falsehood; asserting nothing
    would leave the aggregate untested.  What is true and asserted: across
    every permutation the results agree to within a few ulp of their
    magnitude — the spread is pure reassociation error, never a different
    answer.

    The differential suite carries the complementary half: Rust reproduces
    Python bit-for-bit for each *individual* order.
    """
    pts = [(0.0, y) for y in ys]
    results = [
        _tqo.thermal_score_py(list(p), *BOUNDS, "TOP", md)
        for p in itertools.islice(itertools.permutations(pts), 24)
    ]
    lo, hi = min(results), max(results)
    assert 0.0 <= lo <= hi <= 1.0
    # Reassociation error over n terms is bounded by ~n ulp of the result.
    slack = len(pts) * max(math.ulp(hi), math.ulp(1.0))
    assert hi - lo <= slack, (lo, hi, slack)


# ---------------------------------------------------------------------------
# MR4 — point reflection (loop area), bit-exact
# ---------------------------------------------------------------------------


@given(verts=polygon(), max_area=positive)
@settings(max_examples=200, deadline=None)
def test_mr4_loop_area_is_point_reflection_invariant(verts, max_area):
    """MR4: reflecting the polygon through the origin leaves the score
    **bit-identical**.

    Exact, and structurally so: each shoelace term is
    `x_i*y_{i+1} - x_{i+1}*y_i`, and negating both coordinates negates each
    factor twice, reproducing the identical product — sign, magnitude, and
    the pairwise summation order all unchanged.  No rounding is involved, so
    this is exactness by construction rather than by tolerance.
    """
    reflected = [(-x, -y) for x, y in verts]
    base = _tqo.loop_area_score_py([verts], max_area)
    got = _tqo.loop_area_score_py([reflected], max_area)
    assert base.hex() == got.hex()


# ---------------------------------------------------------------------------
# Kernel-restoring fixtures for the vacuity guards
# ---------------------------------------------------------------------------


def _restorer(name):
    @pytest.fixture
    def _fixture():
        original = getattr(_tqo, name)
        yield
        setattr(_tqo, name, original)

    return _fixture


_restore_thermal = _restorer("thermal_score_py")
_restore_clearance = _restorer("hv_lv_clearance_score_py")
_restore_dual = _restorer("dual_rail_clearance_report_py")
_restore_loop = _restorer("loop_area_score_py")
_restore_compact = _restorer("compactness_score_py")
_restore_zone = _restorer("zone_compliance_score_py")
_restore_cluster = _restorer("connectivity_clustering_score_py")
