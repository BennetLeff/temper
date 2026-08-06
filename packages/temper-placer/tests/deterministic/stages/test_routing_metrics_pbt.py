"""Property-based + metamorphic tests for the migrated routing_metrics model.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_routing_metrics_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. add_net totals: each counter equals the sum of the added nets' fields.
- P2. finalize denominators: the rates are the exact oracle ratios (or 0.0
  with zero segments).
- P3. is_fully_routed: a net is fully routed iff completed == total.
- P4. net_metrics membership: every added net is recorded under its name.
- P5. to_dict shape: the six top-level keys exist with the typed leaves.

Three metamorphic relations (R1d):

- MR1. add-order commutativity: adding the same nets in a different order
  yields equal totals.
- MR2. finalize idempotence: finalize twice equals finalize once.
- MR3. to_json round-trip: json.loads(to_json()) equals to_dict().
"""

from __future__ import annotations

import json

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

NM = _tdb.NetMetrics
RM = _tdb.RoutingMetrics

_NAMES = st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ+_-0123456789")
_NETS = st.lists(
    st.tuples(
        _NAMES,
        st.integers(min_value=0, max_value=5),   # segments_total
        st.integers(min_value=0, max_value=5),   # segments_completed
        st.integers(min_value=0, max_value=5),   # segments_timeout
        st.integers(min_value=0, max_value=50),  # total_iterations
    ),
    min_size=0,
    max_size=6,
)


def _mk(name, total, completed, timeout, iterations):
    return NM(name, "S", 2, total, completed, total - completed, timeout, iterations,
              1.5, 1, 0.1)


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_p1_add_net_totals(nets):
    r = RM()
    for name, total, completed, timeout, iterations in nets:
        r.add_net(_mk(name, total, completed, timeout, iterations))
    assert r.segments_total == sum(n[1] for n in nets)
    assert r.segments_completed == sum(n[2] for n in nets)
    assert r.segments_timeout == sum(n[3] for n in nets)
    assert r.total_iterations == sum(n[4] for n in nets)
    assert r.nets_total == len(nets)


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_p2_finalize_denominators(nets):
    r = RM()
    for name, total, completed, timeout, iterations in nets:
        r.add_net(_mk(name, total, completed, timeout, iterations))
    r.finalize()
    total = sum(n[1] for n in nets)
    if total == 0:
        assert r.avg_iterations_per_segment == 0.0
        assert r.timeout_rate == 0.0
    else:
        assert r.avg_iterations_per_segment == sum(n[4] for n in nets) / total
        assert r.timeout_rate == sum(n[3] for n in nets) / total


@given(st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=5))
@settings(max_examples=50, deadline=None)
def test_p3_is_fully_routed(total, completed):
    m = NM("N", "S", 2, total, completed, total - completed, 0, 1, 0.0, 0, 0.0)
    assert m.is_fully_routed == (completed == total)


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_p4_net_metrics_membership(nets):
    r = RM()
    for name, total, completed, timeout, iterations in nets:
        r.add_net(_mk(name, total, completed, timeout, iterations))
    names = {n[0] for n in nets}
    assert set(r.net_metrics.keys()) == names


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_p5_to_dict_shape(nets):
    r = RM()
    for name, total, completed, timeout, iterations in nets:
        r.add_net(_mk(name, total, completed, timeout, iterations))
    d = r.to_dict()
    assert set(d) == {"summary", "segments", "search", "output", "timing", "failures"}
    assert isinstance(d["summary"]["nets_total"], int)
    assert isinstance(d["search"]["avg_iterations_per_segment"], float)
    assert isinstance(d["failures"]["failed_nets"], list)


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_mr1_add_order_commutativity(nets):
    r1, r2 = RM(), RM()
    for name, total, completed, timeout, iterations in nets:
        r1.add_net(_mk(name, total, completed, timeout, iterations))
    for name, total, completed, timeout, iterations in reversed(nets):
        r2.add_net(_mk(name, total, completed, timeout, iterations))
    assert r1.segments_total == r2.segments_total
    assert r1.total_iterations == r2.total_iterations
    assert r1.nets_failed == r2.nets_failed


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_mr2_finalize_idempotent(nets):
    r1, r2 = RM(), RM()
    for name, total, completed, timeout, iterations in nets:
        r1.add_net(_mk(name, total, completed, timeout, iterations))
        r2.add_net(_mk(name, total, completed, timeout, iterations))
    r1.finalize()
    r2.finalize()
    r2.finalize()
    assert r1.avg_iterations_per_segment == r2.avg_iterations_per_segment
    assert r1.timeout_rate == r2.timeout_rate


@given(_NETS)
@settings(max_examples=100, deadline=None)
def test_mr3_to_json_round_trip(nets):
    r = RM()
    for name, total, completed, timeout, iterations in nets:
        r.add_net(_mk(name, total, completed, timeout, iterations))
    assert json.loads(r.to_json()) == r.to_dict()
