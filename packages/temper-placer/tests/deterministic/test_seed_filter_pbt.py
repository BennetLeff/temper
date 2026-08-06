"""Property-based + metamorphic tests for the migrated seed_filter kernel.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs.filter_seed_kernel``
through the ``temper_placer.deterministic.seed_filter`` shim; bit-identical
parity against the pinned pre-migration Python is asserted separately by
``test_seed_filter_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Outcome totality: any seed/map/threshold combination returns a bool
  and never raises (bounded inputs).
- P2. Empty-seed vacuity: an empty seed accepts regardless of the map.
- P3. Zero-map acceptance: every ref on a zero-score map accepts under any
  non-negative threshold.
- P4. Threshold boundary: a ref whose cell score equals the threshold rejects.
- P5. HV strictness: with ``hv_refs`` containing a ref, that ref is evaluated
  against ``hv_threshold`` (stricter) — swapping a ref between sets flips the
  outcome on a discriminating map.

Three metamorphic relations (R1d):

- MR1. Outcome permutation invariance: shuffling the seed dict does not change
  accept/reject.
- MR2. HV-ref extension: adding a ref to ``hv_refs`` that is not in the seed
  never changes the outcome.
- MR3. Scale invariance: scaling map cell size, origin and all positions by a
  common factor maps cell membership to the same cells, preserving the
  outcome.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.bottleneck_map import BottleneckMap
from temper_placer.deterministic.seed_filter import filter_seed


@st.composite
def args(draw):
    w = draw(st.integers(1, 8))
    h = draw(st.integers(1, 8))
    cell = draw(st.floats(0.5, 5.0, allow_nan=False, allow_infinity=False))
    ox = draw(st.floats(-10.0, 10.0, allow_nan=False, allow_infinity=False))
    oy = draw(st.floats(-10.0, 10.0, allow_nan=False, allow_infinity=False))
    scores = tuple(
        draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)) for _ in range(w * h)
    )
    m = BottleneckMap(cell_size_mm=cell, width=w, height=h, origin_xy=(ox, oy), scores=scores)
    n = draw(st.integers(0, 8))
    seed = {
        draw(st.text(min_size=1, max_size=3)): (
            draw(st.floats(-20.0, 20.0, allow_nan=False, allow_infinity=False)),
            draw(st.floats(-20.0, 20.0, allow_nan=False, allow_infinity=False)),
        )
        for _ in range(n)
    }
    threshold = draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    hv_threshold = draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    hv_refs = frozenset(
        draw(st.sampled_from(sorted(seed))) if seed else []
    )
    return seed, m, threshold, hv_threshold, hv_refs


class TestProperties:
    @given(args())
    @settings(max_examples=100, deadline=None)
    def test_p1_totality(self, a):
        seed, m, t, ht, hv = a
        assert filter_seed(seed, m, t, ht, hv) in (True, False)

    @given(args())
    @settings(max_examples=100, deadline=None)
    def test_p2_empty_seed_accepts(self, a):
        _, m, t, ht, hv = a
        assert filter_seed({}, m, t, ht, hv) is True

    @given(args())
    @settings(max_examples=100, deadline=None)
    def test_p3_zero_map_accepts(self, a):
        seed, m, t, ht, hv = a
        zero = BottleneckMap(
            cell_size_mm=m.cell_size_mm,
            width=m.width,
            height=m.height,
            origin_xy=m.origin_xy,
            scores=tuple(0.0 for _ in m.scores),
        )
        # score >= limit rejects at EQUALITY, so a zero map accepts only under
        # strictly positive thresholds (0.0 >= 0.0 rejects — pinned separately).
        assert filter_seed(seed, zero, max(t, 1e-6), max(ht, 1e-6), hv) is True

    @given(args())
    @settings(max_examples=100, deadline=None)
    def test_p4_equality_rejects(self, a):
        seed, m, t, ht, hv = a
        assume(seed)
        ref = next(iter(seed))
        # Force the ref's cell score to exactly equal the LV threshold.
        x, y = seed[ref]
        if not (m.width > 0 and m.height > 0):
            return
        score = m.score_at(x, y)
        assume(0.0 <= score <= 1.0)
        t = score
        ht = 0.0
        assert filter_seed(seed, m, t, ht, frozenset()) is False

    @given(
        st.floats(0.01, 1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_p5_hv_refs_stricter(self, score):
        """A ref at a mid-grid cell score is accepted under an LV threshold
        above it and rejected under an HV threshold below it."""
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=(score, 0.0, 0.0, 0.0),
        )
        x = 0.5
        y = 0.5
        single = {"U_X": (x, y)}
        t = score + 0.01
        ht = score - 0.01
        assert filter_seed(single, m, t, ht, frozenset()) is True
        assert filter_seed(single, m, t, ht, frozenset({"U_X"})) is False


class TestMetamorphic:
    @given(args())
    @settings(max_examples=80, deadline=None)
    def test_mr1_seed_order_invariant(self, a):
        seed, m, t, ht, hv = a
        items = list(seed.items())
        assume(len(items) >= 2)
        shuffled = dict(reversed(items))
        assert filter_seed(shuffled, m, t, ht, hv) == filter_seed(seed, m, t, ht, hv)

    @given(args())
    @settings(max_examples=80, deadline=None)
    def test_mr2_absent_hv_ref_noop(self, a):
        seed, m, t, ht, hv = a
        base = filter_seed(seed, m, t, ht, hv)
        extended = frozenset(hv) | {"__NOT_IN_SEED__"}
        assert filter_seed(seed, m, t, ht, extended) == base

    @given(args())
    @settings(max_examples=80, deadline=None)
    def test_mr3_scale_invariance(self, a):
        seed, m, t, ht, hv = a
        assume(m.cell_size_mm > 0.0)
        scale = 2.0
        scaled = BottleneckMap(
            cell_size_mm=m.cell_size_mm * scale,
            width=m.width,
            height=m.height,
            origin_xy=(m.origin_xy[0] * scale, m.origin_xy[1] * scale),
            scores=m.scores,
        )
        scaled_seed = {ref: (x * scale, y * scale) for ref, (x, y) in seed.items()}
        assert filter_seed(scaled_seed, scaled, t, ht, hv) == filter_seed(
            seed, m, t, ht, hv
        )
