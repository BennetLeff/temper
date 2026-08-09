"""Property-based and metamorphic tests for the Rust aesthetic kernel
(Wave 4 — ``temper-quality-oracle::aesthetic``, migrating
``temper_placer/metrics/aesthetic.py``).

Module-to-property map (G4): this is a **single-module unit** — the only
kernel is ``aesthetic_score_py``.  All five properties (P1..P5) and all
three metamorphic relations (MR1..MR3) exercise that one kernel; the
alignment sub-score is a constant (the module's own vacuous default after
the JAX-retired prefix-group machinery), which the properties record
rather than work around.

Gate coverage:

- **R1c** — five properties (P1..P5), each paired with a
  ``test_pN_fails_for_<mutant>`` that swaps in a degenerate kernel and
  asserts the property *fails*.
- **R1d** — three metamorphic relations, each with its exactness claim
  stated honestly:

  | Relation | Claim |
  |---|---|
  | MR1 grid-aligned translation | **bit-exact**, bounded to quarter-integer coordinates and integer multiples of the grid — dyadic operands where every add is exact |
  | MR2 component permutation | **bit-exact** — grid snap is a count and orientation is a 4-bin histogram, both order-free |
  | MR3 coordinate reflection (x → -x) | **bit-exact** — floored mod mirrors exactly and the comparison status is preserved |

- **Reachability (G4 condition 2)**: each property names what a degenerate
  implementation would satisfy trivially, and a companion test records that
  the generated input class genuinely reaches discriminating behaviour
  (grid and orientation both vary, rotation splits reach unsaturated
  orientations, off-grid components occur).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import temper_quality_oracle as _tqo
from hypothesis import given, settings
from hypothesis import strategies as st

GRID = 0.5

coord = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
logit = st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)


@st.composite
def placement(draw, min_size=1, max_size=12):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    positions = [(draw(coord), draw(coord)) for _ in range(n)]
    rotations = [tuple(draw(logit) for _ in range(4)) for _ in range(n)]
    return positions, rotations


def score(positions, rotations, grid_size=GRID, as_f32=False):
    return _tqo.aesthetic_score_py(
        [tuple(r) for r in positions],
        [tuple(r) for r in rotations],
        grid_size,
        as_f32,
        as_f32,
    )


# ---------------------------------------------------------------------------
# P1 — every sub-score is a probability
# ---------------------------------------------------------------------------


@given(p=placement(), as_f32=st.booleans())
@settings(max_examples=200, deadline=None)
def test_p1_all_scores_are_probabilities(p, as_f32):
    """P1: every returned score lands in [0, 1] in both dtype modes.

    A kernel that dropped the ``np.clip`` on orientation goes negative for
    entropy above ``1.386`` (uniform rotations reach ~1.3863), and a kernel
    that dropped the weighted-sum normalization can push the index above 1
    or below 0.  The grid snap score is a fraction by construction.
    """
    positions, rotations = p
    s = score(positions, rotations, as_f32=as_f32)
    for k, v in s.items():
        assert 0.0 <= v <= 1.0, (k, v, as_f32)


def test_p1_inputs_reach_varied_scores():
    """Reachability: the generated class is not a constant-input class —
    grid snap and orientation both genuinely vary across samples."""
    rng = np.random.default_rng(11)
    grids, orients = [], []
    for _ in range(200):
        n = int(rng.integers(2, 9))
        positions = rng.uniform(-100.0, 100.0, size=(n, 2)).tolist()
        rotations = rng.uniform(-5.0, 5.0, size=(n, 4)).tolist()
        s = score(positions, rotations)
        grids.append(s["grid_snap_score"])
        orients.append(s["orientation_score"])
    assert min(grids) < 1.0, "grid snap never dropped below 1 — inputs don't reach off-grid"
    assert min(orients) < 1.0, "orientation never dropped below 1 — inputs don't reach mixed rotation"


def test_p1_fails_for_out_of_range_kernel(_restore):
    """Vacuity guard: a kernel that emits scores above 1.0 breaks P1."""
    _tqo.aesthetic_score_py = lambda *_a, **_k: {
        "grid_snap_score": 1.5,
        "orientation_score": 0.5,
        "prefix_alignment_score": 1.0,
        "aesthetic_index": 1.0,
    }
    with pytest.raises(AssertionError):
        test_p1_all_scores_are_probabilities.hypothesis.inner_test(
            ([(0.0, 0.0)], [(1.0, 0.0, 0.0, 0.0)]), False
        )


# ---------------------------------------------------------------------------
# P2 — grid snap score is exactly the snapped fraction
# ---------------------------------------------------------------------------


def _f64_snapped_count(positions, grid_size):
    """Independent count of on-grid components, straight from the formula
    in f64: `min(mod(x, g), g - mod(x, g)) < 0.01` on both axes."""
    count = 0
    for x, y in positions:
        x_off = x - grid_size * math.floor(x / grid_size)
        y_off = y - grid_size * math.floor(y / grid_size)
        if min(x_off, grid_size - x_off) < 0.01 and min(y_off, grid_size - y_off) < 0.01:
            count += 1
    return count


@given(p=placement())
@settings(max_examples=200, deadline=None)
def test_p2_grid_score_is_the_exact_snapped_fraction(p):
    """P2: grid_snap_score equals `count / n` bit-for-bit, with `count`
    computed independently from the floored-mod formula.

    A kernel that used `<= 0.01` instead of `< 0.01`, or rounded the
    distance, or applied the 0.01 threshold on the wrong axis, fails on
    boundary cases this strategy reaches.
    """
    positions, rotations = p
    n = len(positions)
    s = score(positions, rotations)
    expected = _f64_snapped_count(positions, GRID) / n
    assert s["grid_snap_score"].hex() == expected.hex(), (
        s["grid_snap_score"],
        expected,
        positions,
    )


def test_p2_inputs_reach_unsnapped_components():
    """Reachability: most generated coordinates are off the 0.5 grid, so the
    snapped fraction is rarely 1.0 (not a constant-input property)."""
    rng = np.random.default_rng(12)
    unsnapped = 0
    for _ in range(200):
        positions = rng.uniform(-100.0, 100.0, size=(5, 2)).tolist()
        if _f64_snapped_count(positions, GRID) < 5:
            unsnapped += 1
    assert unsnapped > 100, "fewer than half the samples had an off-grid component"


def test_p2_fails_for_inclusive_threshold_kernel(_restore):
    """Vacuity guard: `<= 0.01` (off-by-one bin membership) breaks P2."""

    def mutant(positions, rotations, grid_size=GRID, *a):
        def snapped_incl(x, y):
            x_off = x - grid_size * math.floor(x / grid_size)
            y_off = y - grid_size * math.floor(y / grid_size)
            return (
                min(x_off, grid_size - x_off) <= 0.01
                and min(y_off, grid_size - y_off) <= 0.01
            )

        n = len(positions)
        cnt = sum(1 for (x, y) in positions if snapped_incl(x, y))
        return {
            "grid_snap_score": cnt / n,
            "orientation_score": 0.5,
            "prefix_alignment_score": 1.0,
            "aesthetic_index": 0.5,
        }

    _tqo.aesthetic_score_py = mutant
    with pytest.raises(AssertionError):
        # x = 0.01 lands exactly on the threshold: exclusive says off-grid
        # (0.0), inclusive says snapped (1.0).
        test_p2_grid_score_is_the_exact_snapped_fraction.hypothesis.inner_test(
            ([(0.01, 0.0)], [(1.0, 0.0, 0.0, 0.0)])
        )


# ---------------------------------------------------------------------------
# P3 — orientation rises as the rotation split becomes more extreme
# ---------------------------------------------------------------------------


def _orientation_for_split(k, n):
    """Orientation with k components in rotation class 0 and n-k in class 1."""
    rotations = [[1.0, 0.0, 0.0, 0.0]] * k + [[0.0, 1.0, 0.0, 0.0]] * (n - k)
    positions = [(i * 0.125, i * 0.125) for i in range(n)]
    return score(positions, rotations)["orientation_score"]


@given(
    n=st.integers(min_value=4, max_value=12),
    k1=st.integers(min_value=1, max_value=11),
    k2=st.integers(min_value=1, max_value=11),
)
@settings(max_examples=200, deadline=None)
def test_p3_orientation_rises_with_split_extremeness(n, k1, k2):
    """P3: the farther a rotation split sits from balanced (n/2), the higher
    its orientation score — entropy is maximal at the balanced split and the
    score inverts it.

    A kernel that inverted the entropy-to-score mapping, or used the wrong
    normalization constant, breaks the ordering on the mid-range splits this
    generates (which stay below the 1.0 clip: 1-of-6 gives ~0.675, the
    balanced split ~0.5).
    """
    if not (1 <= k1 < n and 1 <= k2 < n):
        return
    o1 = _orientation_for_split(k1, n)
    o2 = _orientation_for_split(k2, n)
    if abs(k1 - n / 2) > abs(k2 - n / 2):
        assert o1 >= o2, (n, k1, k2, o1, o2)
    else:
        assert o2 >= o1, (n, k1, k2, o1, o2)


def test_p3_splits_reach_unsaturated_orientations():
    """Reachability: mid-range splits produce strictly ordered,
    non-saturated orientations (1-of-6 ≈ 0.675 > balanced ≈ 0.5) — the
    ordering is measured, not clamped into a constant."""
    n = 6
    values = [_orientation_for_split(k, n) for k in range(1, 4)]
    assert values[0] > values[1] > values[2]
    assert values[2] < 0.99, "balanced split saturated at 1.0"


def test_p3_fails_for_inverted_kernel(_restore):
    """Vacuity guard: inverting the score-to-entropy mapping reverses the
    ordering."""

    _original = _tqo.aesthetic_score_py

    def mutant(positions, rotations, grid_size=GRID, *a):
        s = _original(
            [tuple(r) for r in positions],
            [tuple(r) for r in rotations],
            grid_size,
            False,
            False,
        )
        s["orientation_score"] = 1.0 - s["orientation_score"]
        return s

    _tqo.aesthetic_score_py = mutant
    with pytest.raises(AssertionError):
        # n=6, k1=1 (extreme, ~0.675), k2=3 (balanced, ~0.5): the property
        # demands the extreme split score higher; the inverted kernel fails.
        test_p3_orientation_rises_with_split_extremeness.hypothesis.inner_test(6, 1, 3)


# ---------------------------------------------------------------------------
# P4 — the aggregate is exactly the weighted sum
# ---------------------------------------------------------------------------


@given(p=placement(), as_f32=st.booleans())
@settings(max_examples=200, deadline=None)
def test_p4_index_is_the_weighted_sum(p, as_f32):
    """P4: aesthetic_index is bit-exactly `0.4*grid + 0.3*orientation +
    0.3*alignment`, recomputed from the returned component scores.

    This pins the aggregate's expression shape (B7 — the oracle groups the
    additions left to right); a kernel with wrong weights, or a
    differently-grouped sum, fails bit-exactly even where the values agree
    numerically.
    """
    positions, rotations = p
    s = score(positions, rotations, as_f32=as_f32)
    expected = (s["grid_snap_score"] * 0.4) + (s["orientation_score"] * 0.3) + (
        s["prefix_alignment_score"] * 0.3
    )
    assert s["aesthetic_index"].hex() == expected.hex(), (s, expected)


def test_p4_fails_for_wrong_weights(_restore):
    """Vacuity guard: equal weights change the index in the low bits."""

    _original = _tqo.aesthetic_score_py

    def mutant(positions, rotations, grid_size=GRID, *a):
        s = _original(
            [tuple(r) for r in positions],
            [tuple(r) for r in rotations],
            grid_size,
            False,
            False,
        )
        s["aesthetic_index"] = (s["grid_snap_score"] / 3) + (s["orientation_score"] / 3) + (
            s["prefix_alignment_score"] / 3
        )
        return s

    _tqo.aesthetic_score_py = mutant
    with pytest.raises(AssertionError):
        test_p4_index_is_the_weighted_sum.hypothesis.inner_test(
            ([(0.0, 0.0), (1.0, 1.0)], [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)]), False
        )


# ---------------------------------------------------------------------------
# P5 — orientation is a function of the argmax multiset, not the logits
# ---------------------------------------------------------------------------


@given(p=placement())
@settings(max_examples=200, deadline=None)
def test_p5_orientation_ignores_logit_magnitudes(p):
    """P5: perturbing logits without changing any argmax index leaves the
    orientation bit-identical.

    Orientation is entropy over the argmax histogram; a kernel that leaked
    raw logit magnitudes into the score fails this on the first perturbed
    input.  The perturbation adds a strictly smaller value to every element
    of the winning logit and subtracts from every loser, so argmax cannot
    move.
    """
    positions, rotations = p
    base = score(positions, rotations)
    perturbed = []
    for row in rotations:
        best = max(range(4), key=row.__getitem__)
        new = list(row)
        for i in range(4):
            if i == best:
                new[i] += 0.25
            else:
                new[i] -= 0.25
        perturbed.append(tuple(new))
    got = score(positions, perturbed)
    assert got["orientation_score"].hex() == base["orientation_score"].hex()
    assert got["aesthetic_index"].hex() == base["aesthetic_index"].hex()


def test_p5_fails_for_raw_logit_kernel(_restore):
    """Vacuity guard: a kernel whose orientation leaks raw logit magnitudes
    changes under the magnitude perturbation (the winners grow by 0.25 and
    the losers shrink by 0.25, so any magnitude-dependent score moves)."""

    _original = _tqo.aesthetic_score_py

    def mutant(positions, rotations, grid_size=GRID, *a):
        s = _original(
            [tuple(r) for r in positions],
            [tuple(r) for r in rotations],
            grid_size,
            False,
            False,
        )
        flat = [v for row in rotations for v in row]
        mean = (sum(flat) / len(flat)) if flat else 0.0
        s["orientation_score"] = min(1.0, max(0.0, mean + 0.5))
        return s

    _tqo.aesthetic_score_py = mutant
    with pytest.raises(AssertionError):
        test_p5_orientation_ignores_logit_magnitudes.hypothesis.inner_test(
            ([(0.0, 0.0), (1.0, 1.0)], [(1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)])
        )


# ---------------------------------------------------------------------------
# MR1 — grid-aligned translation, bit-exact on dyadic coordinates
# ---------------------------------------------------------------------------


@given(
    a=st.integers(min_value=-800, max_value=800),
    b=st.integers(min_value=-800, max_value=800),
    k=st.integers(min_value=-400, max_value=400),
    n=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=200, deadline=None)
def test_mr1_grid_aligned_translation_is_bit_exact(a, b, k, n):
    """MR1: translating every component by an integer multiple of the grid
    (0.5) leaves the whole result **bit-identical**.

    Exactness claim, honestly bounded: coordinates are quarter-integers
    (`x = a/4`) and the offset is `k*0.5 = k/2`, so `x + k/2 = (a + 2k)/4`
    is another quarter-integer — every add is exact, and `mod(x + k/2, 0.5)`
    depends only on `a mod 2`, which the offset cannot change.  The snapped
    set is therefore identical bit-for-bit.  Outside the dyadic domain the
    relation holds only to within rounding; this test does not claim it
    there.
    """
    positions = [(a / 4, b / 4)] * n
    rotations = [(1.0, 0.0, 0.0, 0.0)] * n
    offset = k * 0.5
    moved = [(x + offset, y + offset) for x, y in positions]
    base = score(positions, rotations)
    got = score(moved, rotations)
    assert key_equal(base, got), (a, b, k, base, got)


def key_equal(left, right):
    return all(float(left[k]).hex() == float(right[k]).hex() for k in left)


# ---------------------------------------------------------------------------
# MR2 — component permutation, bit-exact
# ---------------------------------------------------------------------------


@given(p=placement(min_size=2, max_size=6))
@settings(max_examples=200, deadline=None)
def test_mr2_component_permutation_is_bit_exact(p):
    """MR2: reordering the (position, rotation) pairs together leaves the
    whole result **bit-identical**.

    Exact, and structurally so: grid snap aggregates a count, orientation
    aggregates a 4-bin histogram, and the aggregate is a weighted sum of
    those two order-free quantities (alignment is constant).  No float sum
    over components exists, so no reassociation error can hide in a
    permutation — unlike `thermal_score`, this kernel is genuinely
    permutation-invariant.
    """
    positions, rotations = p
    order = list(range(len(positions)))
    order.reverse()
    base = score(positions, rotations)
    got = score([positions[i] for i in order], [rotations[i] for i in order])
    assert key_equal(base, got), (positions, rotations, base, got)


# ---------------------------------------------------------------------------
# MR3 — coordinate reflection, bit-exact
# ---------------------------------------------------------------------------


@given(p=placement())
@settings(max_examples=200, deadline=None)
def test_mr3_coordinate_reflection_is_bit_exact(p):
    """MR3: negating every coordinate leaves the whole result **bit-identical**.

    Exact, by the exactness of the floored mod: `mod(-x, 0.5)` is the exact
    mirror `0.5 - mod(x, 0.5)` (or `0` on the grid), so `dist(-x) =
    min(0.5 - mod, mod)` returns the same value as `dist(x)` and the
    `< 0.01` membership cannot differ.  Both the f64 chain and (on the
    mirrored f32 inputs) the f32 chain preserve this.
    """
    positions, rotations = p
    base = score(positions, rotations)
    reflected = [(-x, -y) for x, y in positions]
    got = score(reflected, rotations)
    assert key_equal(base, got), (positions, reflected, base, got)


# ---------------------------------------------------------------------------
# Kernel-restoring fixture for the vacuity guards
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore():
    original = _tqo.aesthetic_score_py
    yield
    _tqo.aesthetic_score_py = original
