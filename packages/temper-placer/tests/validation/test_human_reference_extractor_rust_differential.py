"""Differential test: human-reference RDL kernel in Rust (temper_drc_rs)
vs the pinned Python oracle (Wave 4, Phase 4 — validation remainder slice).

``temper_placer/validation/human_reference_extractor.py`` is an extraction
orchestrator: it parses a corpus board (parse engine, already Rust), builds
a ``PlacementState``, and computes metrics through the out-of-scope metric
surfaces (``validation.metrics``, ``metrics.quality``,
``metrics.aesthetic``, ``router_v6.quality.via_count`` /
``corridor``, ``io.reference_loader``, ``validation.drc_runner``) — those
stay Python per their own verdicts. The ONE in-module numeric compute is
the routed-length (RDL) loop in ``_compute_routing_metrics``: for every
trace segment, ``rdl += math.hypot(end.x - start.x, end.y - start.y)``.
That kernel moves to ``temper_drc_rs.rdl_sum`` — the same trace-kernel
family as the already-landed ``trace_length`` in that crate (home-crate
decision recorded in VERIFICATION.md). ``math.hypot`` is passed in from
Python and called back per segment: CPython inlines its own hypot into
mathmodule.c (bpo-33083), so neither the system libm nor ``f64::hypot``
matches it bit-for-bit (measured: 1 ulp low on ``math.hypot(0.1, 0.1)``
vs libm ``hypot``); the differential pins bit-parity via the callback.

Comparison convention: floats via ``float.hex()``.

Sections:
- Differential bit-exactness (random + hand-built segment sets).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

import math

import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._human_reference_extractor_py_oracle as _oracle

# Rust symbol under test — must exist or this file fails to collect (RED).
RDL_SUM = _tdrc.rdl_sum

_COORD = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


def _oracle_rdl(segments: list[tuple[float, float, float, float]]) -> float:
    """RDL via the pinned oracle's own ``_compute_routing_metrics`` (not a
    hand-copy — nothing may tie the reference arm to the kernel's formula
    except the oracle module itself). A minimal ``ParseResult`` duck-type
    carries only the traces (and the empty vias list); the via-count and
    corridor/consolidation steps fall back to their -1 sentinels inside the
    oracle, so the returned ``rdl`` MetricValue is exactly the oracle's
    ``math.hypot`` accumulation over the segment list."""

    class _Trace:
        def __init__(self, sx, sy, ex, ey):
            self.start = (sx, sy)
            self.end = (ex, ey)

    class _ParseResultStub:
        def __init__(self, segs):
            self.traces = [_Trace(*s) for s in segs]
            self.vias = []

    res = _oracle._compute_routing_metrics(_ParseResultStub(segments), "h", "now")
    return float(res["rdl"].value)


def _run_both(segments):
    return _oracle_rdl(segments), RDL_SUM(list(segments), math.hypot)


# ---------------------------------------------------------------------------
# Differential — bit-exactness
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), min_size=0, max_size=30))
def test_rdl_differential_random(segments):
    oracle, shim = _run_both(segments)
    assert shim.hex() == oracle.hex()


def test_rdl_differential_hand_built():
    cases = [
        [],  # empty -> 0.0
        [(0.0, 0.0, 0.0, 0.0)],  # zero-length segment
        [(0.0, 0.0, 3.0, 4.0)],  # 3-4-5 triangle
        [(0.0, 0.0, -3.0, -4.0)],  # sign symmetry
        [(1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0)],  # exact repeats
        [(0.0, 0.0, 0.1, 0.1), (0.0, 0.0, 0.2, 0.3)],  # awkward decimals
        [(1e-5, 0.0, 0.0, 1e-5)],  # tiny magnitudes (subnormal-adjacent)
    ]
    for segments in cases:
        oracle, shim = _run_both(segments)
        assert shim.hex() == oracle.hex(), segments


def test_rdl_matches_accumulated_hypot_identities():
    """Known identity cases: the 3-4-5 triangle, a straight run, and a
    doubled back segment (sum, not distance)."""
    assert RDL_SUM([(0.0, 0.0, 3.0, 4.0)], math.hypot).hex() == 5.0.hex()
    assert RDL_SUM([(0.0, 0.0, 5.0, 0.0)], math.hypot).hex() == 5.0.hex()
    # Doubled back: length 5 + 5 = 10 (not displacement 0).
    assert RDL_SUM([(0.0, 0.0, 5.0, 0.0), (5.0, 0.0, 0.0, 0.0)], math.hypot).hex() == 10.0.hex()


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), min_size=0, max_size=20))
def test_prop1_rdl_is_non_negative(segments):
    """hypot >= 0 and the in-order sum of non-negative terms is >= 0."""
    assert RDL_SUM(list(segments), math.hypot) >= 0.0


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), min_size=0, max_size=20))
def test_prop2_rdl_is_bounded_below_by_every_segment(segments):
    """RDL is a sum of non-negative per-segment hypot terms, so it is >=
    every individual segment length (a mutation that dropped a segment is
    caught by this bound)."""
    segments = list(segments)
    total = RDL_SUM(segments, math.hypot)
    for (sx, sy, ex, ey) in segments:
        assert total >= math.hypot(ex - sx, ey - sy)


@settings(max_examples=40, deadline=None)
@given(st.tuples(_COORD, _COORD, _COORD, _COORD))
def test_prop3_single_segment_is_hypot(seg):
    """A single segment's RDL equals math.hypot of its deltas."""
    sx, sy, ex, ey = seg
    expected = math.hypot(ex - sx, ey - sy)
    assert RDL_SUM([(sx, sy, ex, ey)], math.hypot).hex() == expected.hex()


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), min_size=0, max_size=20))
def test_prop4_zero_length_segments_do_not_change_rdl(segments):
    """Appending zero-length segments leaves the total unchanged."""
    base = RDL_SUM(list(segments), math.hypot)
    padded = RDL_SUM(list(segments) + [(0.0, 0.0, 0.0, 0.0), (5.0, 5.0, 5.0, 5.0)], math.hypot)
    assert padded.hex() == base.hex()


def test_prop5_empty_input_is_zero():
    """Empty-input semantics: RDL of no segments is exactly 0.0 (vacuity
    guard — an empty aggregate must not hide a wrong kernel)."""
    assert RDL_SUM([], math.hypot) == 0.0


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_scaling_segments_scales_rdl_exactly():
    """Scaling every coordinate by a constant factor c scales RDL by c for
    exactly-representable factors (hypot is homogeneous)."""
    segments = [(0.0, 0.0, 3.0, 4.0), (1.0, 2.0, 4.0, 6.0)]
    base = RDL_SUM(segments, math.hypot)
    scaled = RDL_SUM([(2 * s, 2 * t, 2 * u, 2 * v) for s, t, u, v in segments], math.hypot)
    assert scaled.hex() == (2.0 * base).hex()


def test_mr2_negating_all_coordinates_is_identity():
    """Negating every coordinate negates each delta; hypot(dx, dy) is
    even in both arguments, so RDL is unchanged."""
    segments = [(1.0, 2.0, 4.0, 6.0), (0.0, 0.0, -3.0, -4.0)]
    assert RDL_SUM([(-s, -t, -u, -v) for s, t, u, v in segments], math.hypot).hex() == RDL_SUM(segments, math.hypot).hex()


def test_mr3_splitting_a_segment_at_its_midpoint_preserves_rdl():
    """Replacing one segment with two collinear halves whose deltas sum to
    the original yields the same RDL when the split point is exact."""
    seg = (1.0, 2.0, 4.0, 6.0)
    mid = (2.5, 4.0)
    whole = RDL_SUM([seg], math.hypot)
    split = RDL_SUM([(1.0, 2.0, mid[0], mid[1]), (mid[0], mid[1], 4.0, 6.0)], math.hypot)
    assert split.hex() == whole.hex()
