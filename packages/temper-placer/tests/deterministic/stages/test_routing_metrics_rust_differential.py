"""Differential test: routing_metrics data model, Rust pyclasses vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The three dataclasses
and their aggregation compute from ``deterministic/stages/routing_metrics.py``
move to the ``temper-design-bundle`` crate; the Python module becomes a
delegation shim. The pre-migration implementation is pinned VERBATIM as the
oracle (``_routing_metrics_py_oracle.py``).

R1a: construction/defaults, the `completion_rate`/`is_fully_routed`
properties, `add_net` aggregation, `finalize`, and `to_dict`/`to_json`
compare bit-identically (floats via `float.hex()`, round-half-to-even
`round(x, ndigits)` pinned by the `.25` cases).
"""

from __future__ import annotations

import json

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._routing_metrics_py_oracle as _oracle
from tests.core._contract_canon import canon

SM = _tdb.SegmentMetrics
NM = _tdb.NetMetrics
RM = _tdb.RoutingMetrics


def _mk_segment(completed=True, timeout=False):
    return _oracle.SegmentMetrics(
        net_name="NET", segment_idx=0, start_pin="U1.1", end_pin="R2.2",
        distance_mm=3.5, distance_cells=14, success=completed, method="single_layer",
        iterations_used=25, iterations_limit=100, timeout=timeout,
    )


def _mk_net(oracle, name="NET", total=3, completed=3, timeout=0, iterations=40,
            path=12.5, vias=2, elapsed=0.7, failed=0):
    return oracle.NetMetrics(
        net_name=name, net_class="Signal", pin_count=4,
        segments_total=total, segments_completed=completed,
        segments_failed=failed, segments_timeout=timeout,
        total_iterations=iterations, total_path_length_mm=path,
        total_vias=vias, elapsed_seconds=elapsed,
    )


def test_segment_defaults():
    a = SM("NET", 0, "U1.1", "R2.2", 3.5, 14, True, "single_layer", 25, 100, False)
    b = _oracle.SegmentMetrics("NET", 0, "U1.1", "R2.2", 3.5, 14, True, "single_layer", 25, 100, False)
    assert canon(a) == canon(b)
    assert a.path_length_mm == 0.0 and a.via_count == 0 and a.layers_used == []


def test_net_properties():
    a_full = NM("NET", "S", 4, 3, 3, 0, 0, 40, 12.5, 2, 0.7)
    b_full = _mk_net(_oracle, total=3, completed=3)
    assert a_full.completion_rate == b_full.completion_rate
    assert a_full.is_fully_routed is b_full.is_fully_routed
    a_part = NM("NET", "S", 4, 3, 2, 1, 0, 40, 12.5, 2, 0.7)
    b_part = _mk_net(_oracle, total=3, completed=2, failed=1)
    assert a_part.completion_rate == b_part.completion_rate
    assert a_part.is_fully_routed is b_part.is_fully_routed
    a_zero = NM("NET", "S", 0, 0, 0, 0, 0, 0, 0.0, 0, 0.0)
    b_zero = _oracle.NetMetrics("NET", "S", 0, 0, 0, 0, 0, 0, 0.0, 0, 0.0)
    assert a_zero.completion_rate == 1.0 == b_zero.completion_rate


def test_add_net_aggregation():
    a = RM()
    b = _oracle.RoutingMetrics()
    for i in range(3):
        name = f"N{i}"
        a.add_net(NM(name, "S", 4, 2, 2, 0, 0, 10, 3.3, 1, 0.1))
        b.add_net(_mk_net(_oracle, name=name, total=2, completed=2, iterations=10, path=3.3, vias=1, elapsed=0.1))
    assert a.nets_total == b.nets_total == 3
    assert a.nets_fully_routed == b.nets_fully_routed
    assert a.segments_total == b.segments_total
    assert a.total_iterations == b.total_iterations
    assert a.failed_nets == b.failed_nets
    assert a.timeout_nets == b.timeout_nets


def test_add_net_failed_and_timeout():
    a = RM()
    b = _oracle.RoutingMetrics()
    a.add_net(NM("F", "S", 4, 1, 0, 1, 0, 5, 0.0, 0, 0.1))
    b.add_net(_mk_net(_oracle, name="F", total=1, completed=0, failed=1, iterations=5, path=0.0, vias=0, elapsed=0.1))
    assert a.nets_failed == 1 and a.failed_nets == ["F"]
    a.add_net(NM("T", "S", 4, 2, 1, 0, 1, 200, 4.0, 1, 0.2))
    b.add_net(_mk_net(_oracle, name="T", total=2, completed=1, timeout=1, iterations=200, path=4.0, vias=1, elapsed=0.2))
    assert a.timeout_nets == ["T"] == b.timeout_nets


def test_finalize_derived_rates():
    a = RM()
    b = _oracle.RoutingMetrics()
    a.add_net(NM("A", "S", 2, 2, 1, 0, 0, 10, 5.0, 1, 0.3))
    b.add_net(_mk_net(_oracle, name="A", total=2, completed=1, iterations=10, path=5.0, vias=1, elapsed=0.3))
    a.finalize()
    b.finalize()
    assert a.avg_iterations_per_segment == b.avg_iterations_per_segment
    assert a.timeout_rate == b.timeout_rate
    c = RM()
    d = _oracle.RoutingMetrics()
    c.finalize()
    d.finalize()
    assert c.avg_iterations_per_segment == 0.0 == d.avg_iterations_per_segment


def test_to_dict_parity():
    a = RM()
    b = _oracle.RoutingMetrics()
    a.add_net(NM("A", "S", 2, 2, 1, 0, 0, 10, 5.25, 1, 0.345))
    b.add_net(_mk_net(_oracle, name="A", total=2, completed=1, iterations=10, path=5.25, vias=1, elapsed=0.345))
    a.finalize()
    b.finalize()
    assert canon(a.to_dict()) == canon(b.to_dict())


def test_to_dict_round_half_even():
    """round(2.25, 1) == 2.2 (half-to-even) is pinned by the average."""
    a = RM()
    b = _oracle.RoutingMetrics()
    # avg = total_iterations / segments_total = 9 / 4 = 2.25 -> round -> 2.2.
    a.add_net(NM("A", "S", 2, 4, 2, 0, 0, 9, 2.25, 1, 0.35))
    b.add_net(_mk_net(_oracle, name="A", total=4, completed=2, iterations=9, path=2.25, vias=1, elapsed=0.35))
    a.finalize()
    b.finalize()
    got = a.to_dict()
    exp = b.to_dict()
    assert got["search"]["avg_iterations_per_segment"] == exp["search"]["avg_iterations_per_segment"]
    assert got["output"]["total_trace_length_mm"] == exp["output"]["total_trace_length_mm"]
    assert got["search"]["avg_iterations_per_segment"] == 2.2  # half-to-even, not 2.3


def test_to_json_parity():
    a = RM()
    b = _oracle.RoutingMetrics()
    a.add_net(NM("A", "S", 2, 2, 1, 0, 0, 10, 5.25, 1, 0.345))
    b.add_net(_mk_net(_oracle, name="A", total=2, completed=1, iterations=10, path=5.25, vias=1, elapsed=0.345))
    a.finalize()
    b.finalize()
    assert a.to_json() == b.to_json()
    assert a.to_json() == json.dumps(b.to_dict(), indent=2)


def test_empty_routing_metrics_to_dict():
    a = RM()
    b = _oracle.RoutingMetrics()
    assert canon(a.to_dict()) == canon(b.to_dict())
    # Division by zero guarded: max(nets_total, 1).
    assert a.to_dict()["summary"]["net_completion_rate"] == 0.0


def _build_pair(with_failures=False):
    a = RM()
    b = _oracle.RoutingMetrics()
    a.add_net(NM("F", "S", 4, 1, 0, 1, 0, 5, 0.0, 0, 0.1))
    b.add_net(_mk_net(_oracle, name="F", total=1, completed=0, failed=1, iterations=5, path=0.0, vias=0, elapsed=0.1))
    a.add_net(NM("N1", "S", 4, 2, 2, 0, 0, 10, 3.3, 1, 0.1))
    b.add_net(_mk_net(_oracle, name="N1", total=2, completed=2, iterations=10, path=3.3, vias=1, elapsed=0.1))
    a.finalize()
    b.finalize()
    return a, b


def test_print_summary_parity(capsys):
    import io as _io
    import contextlib as _ctx

    a, b = _build_pair()
    buf_a, buf_b = _io.StringIO(), _io.StringIO()
    with _ctx.redirect_stdout(buf_a):
        a.print_summary()
    with _ctx.redirect_stdout(buf_b):
        b.print_summary()
    assert buf_a.getvalue() == buf_b.getvalue()


def test_print_summary_long_failed_nets():
    import io as _io
    import contextlib as _ctx

    a = RM()
    b = _oracle.RoutingMetrics()
    for i in range(15):
        name = f"FN{i}"
        a.add_net(NM(name, "S", 1, 1, 0, 1, 0, 1, 0.0, 0, 0.0))
        b.add_net(_mk_net(_oracle, name=name, total=1, completed=0, failed=1, iterations=1, path=0.0, vias=0, elapsed=0.0))
    buf_a, buf_b = _io.StringIO(), _io.StringIO()
    with _ctx.redirect_stdout(buf_a):
        a.print_summary()
    with _ctx.redirect_stdout(buf_b):
        b.print_summary()
    assert buf_a.getvalue() == buf_b.getvalue()
    assert "Failed nets (15):" in buf_a.getvalue()
    assert "... and 5 more" in buf_a.getvalue()
