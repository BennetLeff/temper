"""Property-based tests for the U-H adapter-marshalling kernels
(temper-orchestration ``pipeline_route`` module, exercised through the
production ``router_v6/_adapter_convert.py`` shims).

Rust Orchestration Engine plan 2026-08-09-001, Phase E E6 follow-on (unit
U-H). These properties run against the delegating shims and hold over
randomized inputs. Module-to-property map (the G4 cluster rule):

- ``_write_routes_to_content`` (the pad-positions + per-route payload
  marshalling the shim delegates) -- P1..P4
- ``_build_routing_result`` (the failure-extraction assembly) -- P5, P6

Six non-vacuous properties (G4), each with a ``_guard`` companion proving a
degenerate kernel would violate it:

- P1  pad-positions totality + order: every net with >= 1 resolvable pin
      position appears, each entry lists exactly the resolvable positions in
      pin order, nets with zero resolvable positions are absent. Vacuity
      guard: a net-dropping kernel violates.
- P2  pad-positions determinism: identical pcb -> identical dict. Vacuity
      guard: a hash-order kernel violates on the duplicate-ref case.
- P3  payload guard: a path with path_length <= 0 or pad count < 2 carries
      NO path points, while vias are still extracted (the via loop is
      outside the guard). Vacuity guard: an always-emit kernel violates.
- P4  payload width snap: a width <= 0 (or missing) snaps to 0.2; a positive
      width passes through. Vacuity guard: a raw-width kernel violates.
- P5  routing-result net extraction: every failed net surfaces in
      unrouted_nets; every compiled route whose path carries
      forced_segment_count > 0 surfaces in forced_segment_nets (and only
      those). Vacuity guard: a drop-forced kernel violates.
- P6  routing-result violation/congestion extraction: every report with
      drc_violations > 0 yields exactly one violation carrying the report's
      count/net/message; every component_edge / component_keepout bottleneck
      yields exactly one region (other kinds never do). Vacuity guard: a
      kind-blind kernel violates.
"""

from __future__ import annotations

from types import SimpleNamespace

import hypothesis.strategies as st
from hypothesis import given, settings

from temper_placer.router_v6._adapter_convert import (
    _build_routing_result,
    _write_routes_to_content,
)

_SETTINGS = settings(max_examples=80, deadline=8000, suppress_health_check=[])

_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2"))'

_NET_NAME = st.text(min_size=1, max_size=8).filter(lambda s: '"' not in s)
_POS = st.floats(min_value=-5.0, max_value=5.0, allow_nan=False).map(lambda x: round(x * 2) / 2)


def _comp(ref, pins=None, position=(0.0, 0.0)):
    if pins is None:
        return SimpleNamespace(ref=ref, initial_position=position)
    return SimpleNamespace(
        ref=ref,
        initial_position=position,
        get_pin=lambda name: SimpleNamespace(position=pins[name]) if name in pins else None,
    )


def _net(name, pins):
    return SimpleNamespace(name=name, pins=pins)


def _pcb(comps, nets):
    return SimpleNamespace(components=list(comps), nets=list(nets))


def _result(pcb, compiled):
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes=dict(compiled), tree_routes={}, partial_tree_routes={}
            )
        ),
        pcb=pcb,
        enable_zone_pours=False,
    )


def _dummy_route_result(pcb):
    """A result whose routing_results is non-empty (so the shim's
    ``_write_routes_to_content`` proceeds past the nothing-routed early
    return to the pad-positions collection) but whose only compiled route
    emits nothing (zero-length path, no vias)."""
    dummy = SimpleNamespace(path=SimpleNamespace(path_length=0.0), width_mm=0.2, vias=[])
    return _result(pcb, {"__dummy__": dummy})


def _route(path, width=0.2, vias=()):
    return SimpleNamespace(path=path, width_mm=width, vias=list(vias))


# ---------------------------------------------------------------------------
# P1 — pad-positions totality + order (via _write_routes_to_content)
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(
            _NET_NAME,
            st.lists(
                st.tuples(
                    st.integers(min_value=0, max_value=5),
                    st.text(min_size=1, max_size=3).map(lambda s: s.replace('"', "")),
                ),
                min_size=0,
                max_size=6,
            ),
        ),
        min_size=0,
        max_size=5,
    )
)
@_SETTINGS
def test_p1_pad_positions_totality_and_order(net_specs):
    comps = [_comp("C0", position=(1.0, 2.0)), _comp("C1", position=(3.0, 4.0))]
    nets = []
    for name, pins in net_specs:
        resolvable = [(r, p) for (r, p) in pins if r in ("C0", "C1")]
        nets.append(_net(name, resolvable))
    pcb = _pcb(comps, nets)
    # Drive through the shim: the dummy compiled route lets the writer
    # proceed to the pad-positions collection (no emission happens).
    output, pad_positions = _write_routes_to_content(_CONTENT, _dummy_route_result(pcb))

    for name, pins in net_specs:
        resolvable = [(r, p) for (r, p) in pins if r in ("C0", "C1")]
        if not resolvable:
            assert name not in pad_positions, f"net {name} must be absent (no resolvable pins)"
        else:
            assert name in pad_positions, f"net {name} must appear"
            # comp positions: C0=(1.0,2.0), C1=(3.0,4.0), no get_pin -> comp_pos
            want = [(1.0, 2.0) if r == "C0" else (3.0, 4.0) for (r, _p) in resolvable]
            assert pad_positions[name] == want, "positions in pin order, comp-pos fallback"
    assert isinstance(output, str) and "(kicad_pcb" in output


def test_p1_guard_net_dropping_discriminates():
    pcb = _pcb([_comp("C0")], [_net("NET_A", [("C0", "1")]), _net("NET_B", [("C0", "1")])])
    _, pad_positions = _write_routes_to_content(_CONTENT, _dummy_route_result(pcb))
    assert set(pad_positions) == {"NET_A", "NET_B"}, "a net-dropping kernel would fail this"


# ---------------------------------------------------------------------------
# P2 — pad-positions determinism
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(
            _NET_NAME,
            st.lists(st.tuples(st.integers(min_value=0, max_value=2), st.integers(min_value=0, max_value=2)), min_size=0, max_size=5),
        ),
        min_size=0,
        max_size=5,
    )
)
@_SETTINGS
def test_p2_pad_positions_deterministic(net_specs):
    comps = [_comp(f"C{i}") for i in range(3)]
    nets = [_net(name, [("C1", "1")]) for name, _pins in net_specs]
    pcb = _pcb(comps, nets)
    _, first = _write_routes_to_content(_CONTENT, _dummy_route_result(pcb))
    _, second = _write_routes_to_content(_CONTENT, _dummy_route_result(pcb))
    assert first == second
    # First-seen net order preserved (dict insertion order; a duplicated
    # name keeps its first-seen slot -- the dict's last writer wins the
    # VALUE, not the position).
    seen_names = []
    for name, _p in net_specs:
        if name not in seen_names:
            seen_names.append(name)
    assert list(first.keys()) == [name for name in seen_names if name in first]


def test_p2_guard_hash_order_discriminates():
    # Duplicate refs: the dict comprehension keeps the LAST component
    # (last-writer-wins). A hash-ordered or first-writer kernel would not
    # reproduce the deterministic position.
    pcb = _pcb(
        [_comp("C0", position=(1.0, 1.0)), _comp("C0", position=(9.0, 9.0))],
        [_net("N", [("C0", "1")])],
    )
    _, pad_positions = _write_routes_to_content(_CONTENT, _dummy_route_result(pcb))
    assert pad_positions["N"] == [(9.0, 9.0)]


# ---------------------------------------------------------------------------
# P3 — payload guard (path_length <= 0 or pads < 2 => no points; vias kept)
# ---------------------------------------------------------------------------


@given(
    st.tuples(
        st.floats(min_value=-1.0, max_value=3.0, allow_nan=False),
        st.integers(min_value=0, max_value=5),
        st.lists(st.integers(min_value=0, max_value=2), min_size=0, max_size=4),
    )
)
@_SETTINGS
def test_p3_payload_guard_respects_length_and_pad_count(triple):
    path_length, pads_len, via_ys = triple
    n = max(2, len(via_ys) + 2)
    pts = [(float(i) * 0.5, 0.0, "F.Cu") for i in range(n)]
    path = SimpleNamespace(path_length=path_length, segments=pts)
    vias = [SimpleNamespace(position=(1.0, float(y)), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu") for y in via_ys]
    route = _route(path, width=0.2, vias=vias)
    pads = [(0.0, 0.0)] * pads_len
    payload = __import__("temper_orchestration").run_build_route_payload(
        path, route, "NET1", 1, pads_len
    )
    _net_name, _length, path_points, _width, _num, payload_vias, _count = payload
    if path_length > 0 and pads_len >= 2:
        assert len(path_points) >= 2, "a routable net must carry chamfered points"
    else:
        assert path_points == [], "a non-routable net must carry NO path points"
    assert len(payload_vias) == len(via_ys), "vias are extracted outside the path guard"


def test_p3_guard_always_emit_discriminates():
    path = SimpleNamespace(path_length=0.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")])
    payload = __import__("temper_orchestration").run_build_route_payload(
        path, _route(path), "NET1", 1, 2
    )
    assert payload[2] == [], "a zero-length path must carry no points"


# ---------------------------------------------------------------------------
# P4 — payload width snap
# ---------------------------------------------------------------------------


@given(
    st.one_of(
        st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
        st.floats(min_value=-2.0, max_value=-0.0001),
        st.just(0.0),
    )
)
@_SETTINGS
def test_p4_payload_width_snap(width):
    path = SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")])
    route = _route(path, width=width)
    payload = __import__("temper_orchestration").run_build_route_payload(
        path, route, "NET1", 1, 2
    )
    if width <= 0.0:
        assert payload[3] == 0.2, f"width {width!r} must snap to 0.2"
    else:
        assert payload[3] == width, f"positive width {width!r} must pass through"


def test_p4_guard_raw_width_discriminates():
    path = SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")])
    route = _route(path, width=0.0)
    payload = __import__("temper_orchestration").run_build_route_payload(
        path, route, "NET1", 1, 2
    )
    assert payload[3] == 0.2, "a zero width must be snapped to 0.2 (KiCad DRC track_width)"


# ---------------------------------------------------------------------------
# P5 — routing-result net extraction (unrouted + forced segments)
# ---------------------------------------------------------------------------


@given(
    st.lists(_NET_NAME, min_size=0, max_size=6),
    st.lists(
        st.tuples(_NET_NAME, st.booleans()),
        min_size=0,
        max_size=6,
    ),
)
@_SETTINGS
def test_p5_routing_result_net_extraction(failed, compiled_specs):
    # The compiled dict is the last-writer-wins comprehension the oracle
    # walks; the expectation must be computed from the DICT, not the raw
    # (duplicate-bearing) spec list.
    compiled = {
        name: SimpleNamespace(
            path=SimpleNamespace(forced_segment_count=1 if forced else 0)
        )
        for name, forced in compiled_specs
    }
    rr = SimpleNamespace(compiled_routes=compiled, failed_nets=list(failed), net_reports=[])
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.5)
    got = _build_routing_result(result)
    assert got.unrouted_nets == failed
    want_forced = [
        name for name, route in compiled.items() if route.path.forced_segment_count > 0
    ]
    assert got.forced_segment_nets == want_forced


def test_p5_guard_forced_segment_drop_discriminates():
    rr = SimpleNamespace(
        compiled_routes={"SW_NODE": SimpleNamespace(path=SimpleNamespace(forced_segment_count=2))},
        failed_nets=[],
        net_reports=[],
    )
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=1.0)
    got = _build_routing_result(result)
    assert got.forced_segment_nets == ["SW_NODE"]


# ---------------------------------------------------------------------------
# P6 — routing-result violation/congestion extraction
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(
            _NET_NAME,
            st.integers(min_value=0, max_value=5),
            st.sampled_from(["component_edge", "component_keepout", "component_component", None]),
        ),
        min_size=0,
        max_size=6,
    )
)
@_SETTINGS
def test_p6_routing_result_violation_extraction(report_specs):
    reports = []
    for name, drc_count, kind in report_specs:
        attrs = {"net_name": name, "drc_violations": drc_count}
        if kind is not None:
            attrs["bottleneck"] = SimpleNamespace(
                pair_kind=kind, component_pair=("A", "B"), current_gap_mm=0.5
            )
        reports.append(SimpleNamespace(**attrs))
    rr = SimpleNamespace(compiled_routes={}, failed_nets=[], net_reports=reports)
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.0)
    got = _build_routing_result(result)

    want_violations = [(name, count) for name, count, _k in report_specs if count > 0]
    assert [(v.net_name, v.count) for v in got.drc_violations] == want_violations

    want_regions = [name for name, _c, kind in report_specs if kind in ("component_edge", "component_keepout")]
    assert [r.net_name for r in got.congestion_regions] == want_regions


def test_p6_guard_kind_blind_discriminates():
    reports = [
        SimpleNamespace(net_name="N1", bottleneck=SimpleNamespace(pair_kind="component_component")),
        SimpleNamespace(net_name="N2", bottleneck=SimpleNamespace(pair_kind="component_edge")),
    ]
    rr = SimpleNamespace(compiled_routes={}, failed_nets=[], net_reports=reports)
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.0)
    got = _build_routing_result(result)
    assert [r.net_name for r in got.congestion_regions] == ["N2"], (
        "only component_edge / component_keepout bottlenecks are collected"
    )
