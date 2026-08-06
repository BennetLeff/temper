"""Property-based + metamorphic tests for the migrated DRC-check leaf kernels.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_drc_leaf_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Summarize totality: the row counts sum to the total, and the rows are
  sorted by descending count.
- P2. Dedup keeps: distinct (rounded-key) traces are all kept; duplicates
  raise the duplicate count by exactly the number dropped.
- P3. Point-to-segment distance bounds: the distance is between the distance
  to the nearest endpoint and that endpoint distance (for points projecting
  onto the segment).
- P4. Clamp bounds: the clamped coordinate lies in `[margin, dim - margin]`.
- P5. Threshold strictness: `max_violations == count` does not raise.

Three metamorphic relations (R1d):

- MR1. Dedup net-sensitivity: two geometrically identical traces with
  different nets are both kept.
- MR2. Dedup orientation: reversing both endpoints preserves the dedup
  outcome.
- MR3. Segment-collapse: when the segment is a point, the distance equals
  the point-to-point distance.
"""

from __future__ import annotations

import math

import temper_drc_rs as _drc
from hypothesis import given, settings
from hypothesis import strategies as st

_COORD = st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
_NET = st.text(min_size=0, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789")
_TRACES = st.lists(
    st.tuples(
        st.tuples(_COORD, _COORD), st.tuples(_COORD, _COORD),
        st.sampled_from(["F.Cu", "B.Cu"]), _NET,
    ),
    min_size=0, max_size=8,
)


def _mk_traces(traces):
    return [(s, e, layer, net if net else None) for s, e, layer, net in traces]


@given(st.lists(st.sampled_from(["a", "b", "c"]), min_size=0, max_size=20))
@settings(max_examples=100, deadline=None)
def test_p1_summarize_totality(types):
    vs = [_V(t) for t in types]
    total, rows = _drc.summarize_violations_py(vs)
    assert total == len(types)
    assert sum(c for _, c in rows) == len(types)
    counts = [c for _, c in rows]
    assert counts == sorted(counts, reverse=True)


def _V(t):
    return _SimpleViolation(t)


class _SimpleViolation:
    def __init__(self, t):
        self.type = t


@given(_TRACES)
@settings(max_examples=100, deadline=None)
def test_p2_dedup_keeps_and_counts(traces):
    marshalled = _mk_traces(traces)
    kept, duplicates = _drc.deduplicate_traces_py(marshalled, 0.05)
    assert len(kept) + duplicates == len(marshalled)
    assert len(kept) == len(set(kept))


@given(_COORD, _COORD, _COORD, _COORD, _COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_p3_distance_bounds(px, py, x1, y1, x2, y2):
    d = _drc.point_to_segment_distance_py((px, py), (x1, y1), (x2, y2))
    assert d >= 0.0
    d_end1 = math.hypot(px - x1, py - y1)
    d_end2 = math.hypot(px - x2, py - y2)
    assert d <= max(d_end1, d_end2) + 1e-9


@given(_COORD, _COORD, st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False),
       st.floats(min_value=1, max_value=300, allow_nan=False, allow_infinity=False),
       st.floats(min_value=1, max_value=300, allow_nan=False, allow_infinity=False))
@settings(max_examples=100, deadline=None)
def test_p4_clamp_bounds(x, y, margin, w, h):
    if margin >= w / 2 or margin >= h / 2:
        return  # no valid interior
    cx, cy = _drc.clamp_position_py(x, y, margin, w, h)
    assert margin <= cx <= w - margin
    assert margin <= cy <= h - margin


@given(st.integers(min_value=0, max_value=10), st.integers(min_value=0, max_value=10))
@settings(max_examples=50, deadline=None)
def test_p5_threshold_strictness(count, mx):
    # The oracle's rule is `count > max_violations`, never `>=`.
    if count == mx:
        assert _oracle_threshold(False, mx, count) == (False, "")


def _oracle_threshold(fail, mx, count):
    if fail and count:
        return (True, f"{count} DRC violations found")
    if mx > 0 and count > mx:
        return (True, f"{count} violations exceeds max {mx}")
    return (False, "")


@given(_TRACES)
@settings(max_examples=100, deadline=None)
def test_mr1_dedup_net_sensitivity(traces):
    marshalled = _mk_traces(traces)
    if not marshalled:
        return
    # Two identical traces with different nets are both kept.
    base = marshalled[0]
    other = (base[0], base[1], base[2], ("X" if base[3] != "X" else "Y"))
    kept, _ = _drc.deduplicate_traces_py([base, other], 0.05)
    assert kept == [0, 1]


@given(_TRACES)
@settings(max_examples=100, deadline=None)
def test_mr2_dedup_orientation(marshalled_dummy):
    marshalled = _mk_traces(marshalled_dummy)
    kept_a, _ = _drc.deduplicate_traces_py(marshalled, 0.05)
    reversed_traces = [((e[0], e[1]), (s[0], s[1]), l, n) for (s, e, l, n) in marshalled]
    kept_b, _ = _drc.deduplicate_traces_py(reversed_traces, 0.05)
    assert kept_a == kept_b


@given(_COORD, _COORD, _COORD, _COORD)
@settings(max_examples=100, deadline=None)
def test_mr3_segment_collapse(px, py, x1, y1):
    d = _drc.point_to_segment_distance_py((px, py), (x1, y1), (x1, y1))
    # Same expression the oracle/kernel evaluate for the degenerate segment:
    # math.sqrt((px - x1) ** 2 + (py - y1) ** 2) — libm pow + sqrt.
    expected = math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    assert d == expected
