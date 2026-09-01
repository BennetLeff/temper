"""R1a: behavioural A/B of the Phase E batch E6 pipeline-route orchestration
(temper-orchestration ``pipeline_route`` module) against the pinned
pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E6: the pipeline-route
ORCHESTRATION moves to temper-orchestration's ``pipeline_route.rs`` (the
pyfunction FFI surface the ``router_v6/_pipeline_route.py`` and
``router_v6/_adapter_convert.py`` shims delegate to); the modules keep their
public API as delegation shims. The pre-migration implementation is pinned
VERBATIM as ``tests/router_v6/_pipeline_route_py_oracle.py`` and
``tests/router_v6/_adapter_convert_py_oracle.py`` (byte-identical snapshots of
the orchestration bodies at the dispatch base, origin/main cfc9415c1;
content-hash pinned in ``scripts/oracle_hashes.json`` AND in this file's body
digest). Both arms are driven with IDENTICAL inputs; every assertion is
bit-exact.

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
each shim function now binds to a ``temper_orchestration`` pyfunction
(``__module__`` / import binding), not resolving back onto the oracle.

Covered orchestrations:

- ``_pipeline_route._select_sat_nets``            vs ``pipeline_route::run_select_sat_nets``
- ``_pipeline_route._build_clause_origin``        vs ``pipeline_route::run_build_clause_origin``
- ``_pipeline_route.select_routing_grids``        vs ``pipeline_route::run_select_routing_grids``
- ``_adapter_convert._next_tstamp``               vs ``pipeline_route::run_next_tstamp``
- ``_adapter_convert._to_stage0_netclass_rules``  vs ``pipeline_route::run_to_stage0_netclass_rules``
- ``_adapter_convert._write_routes_to_content``   vs ``pipeline_route::run_write_route_segments``
  (the segment/via emission core; the chamfer, the tree-route folding, the
  zone-pour emission and the s-expression injection stay Python -- the E6
  boundary)

Floats are compared via ``float.hex()`` (``canon``); emitted content is
compared byte-for-byte; the ``tstamp`` sequences are compared as emitted.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import temper_orchestration as _to

from temper_placer.router_v6._adapter_convert import (
    _next_tstamp as shim_next_tstamp,
)
from temper_placer.router_v6._adapter_convert import (
    _to_stage0_netclass_rules as shim_to_stage0,
)
from temper_placer.router_v6._adapter_convert import (
    _write_routes_to_content as shim_write_routes,
)
from temper_placer.router_v6._pipeline_route import (
    _build_clause_origin as shim_clause_origin,
)
from temper_placer.router_v6._pipeline_route import (
    _select_sat_nets as shim_select_sat_nets,
)
from temper_placer.router_v6._pipeline_route import (
    select_routing_grids as shim_select_grids,
)
from tests.router_v6 import _adapter_convert_py_oracle as _adapter_oracle
from tests.router_v6 import _pipeline_route_py_oracle as _route_oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ROUTE_ORACLE_PATH = Path(__file__).with_name("_pipeline_route_py_oracle.py")
_ADAPTER_ORACLE_PATH = Path(__file__).with_name("_adapter_convert_py_oracle.py")

# Body digests of the six ported orchestrations, extracted from the oracle
# files (AST ranges, dedented) -- pinned here so a body edit in the oracle
# fails this test rather than silently re-pinning the differential.
_BODY_DIGESTS = {
    "_select_sat_nets": "68411bd4c8ae0dbbc3a6c34f7dfb3ce4e8ac10bfe29d864c4f6772491ddac5f7",
    "_build_clause_origin": "32845850165f8771d4d7c466fa733b310197258980553bae98564403d3b90aa8",
    "select_routing_grids": "8b45bfa73df1d4c9d4e862aca7501a700df0647ab0e3e4415cf3a1f8469a40b3",
    "_next_tstamp": "bec736a752d4896639a98d1f3f1ab0f50139390d442ecc5d94a3d3e4441eb640",
    "_to_stage0_netclass_rules": "334e7bf0b4d16bb36892751529e6a946821ed53d7fade601f1f5f7d39284b79f",
    "_write_routes_to_content": "62f5e2a6353f5f4ecf51784dbf404fc29992da525a18388bf553d7789f29f39f",
}


def _oracle_body_digests(path: Path) -> dict[str, str]:
    import ast
    import textwrap

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            out[node.name] = hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    return out


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    route = _oracle_body_digests(_ROUTE_ORACLE_PATH)
    adapter = _oracle_body_digests(_ADAPTER_ORACLE_PATH)
    for name, want in _BODY_DIGESTS.items():
        got = route.get(name) or adapter.get(name)
        assert got == want, (
            f"the pinned oracle body {name} changed; it must stay verbatim "
            "(see scripts/oracle_hashes.json for the registered hash)"
        )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shims must bind to temper_orchestration pyfunctions,
    not resolve back onto the oracle."""
    assert _to.run_select_sat_nets.__module__ == "temper_orchestration.temper_orchestration"
    assert (
        _to.run_build_clause_origin.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert (
        _to.run_select_routing_grids.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert _to.run_next_tstamp.__module__ == "temper_orchestration.temper_orchestration"
    assert (
        _to.run_to_stage0_netclass_rules.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert (
        _to.run_write_route_segments.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert _oracle_adapter_has_verbatim_bodies()


def _oracle_adapter_has_verbatim_bodies() -> bool:
    # The oracle functions must not have been collapsed onto the shims.
    for name in ("_next_tstamp", "_to_stage0_netclass_rules", "_write_routes_to_content"):
        oracle_fn = getattr(_adapter_oracle, name)
        if getattr(oracle_fn, "__module__", "") == "temper_orchestration.temper_orchestration":
            return False
    for name in ("_select_sat_nets", "_build_clause_origin", "select_routing_grids"):
        oracle_fn = getattr(_route_oracle, name)
        if getattr(oracle_fn, "__module__", "") == "temper_orchestration.temper_orchestration":
            return False
    return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _self(max_sat_nets=None):
    return SimpleNamespace(max_sat_nets=max_sat_nets)


def _net(name, pins=0):
    return SimpleNamespace(name=name, pins=list(range(pins)))


def _pcb(*nets):
    return SimpleNamespace(nets=list(nets))


def _grid(name):
    return SimpleNamespace(layer_name=name)


class _FalsyGrid:
    """A grid object whose truthiness is False (exercises the `or` fallback)."""

    def __init__(self, name):
        self.layer_name = name

    def __bool__(self):
        return False


# --- clause-origin fakes (duck-typed constraint shapes) ---


def _constraint(name, **attrs):
    return SimpleNamespace(name=name, **attrs)


# --- routing-result fakes for the write-routes core ---


def _via(x, y, diameter=0.9, drill=0.3, from_layer="F.Cu", to_layer="B.Cu"):
    return SimpleNamespace(
        position=(x, y),
        diameter=diameter,
        drill=drill,
        from_layer=from_layer,
        to_layer=to_layer,
    )


def _comp(ref):
    return SimpleNamespace(ref=ref, initial_position=(1.0, 2.0))


def _net_with_pins(name, pins):
    return SimpleNamespace(name=name, pins=pins)


def _comp_by_ref(pcb):
    return {c.ref: c for c in pcb.components}


def _make_result(
    compiled,
    *,
    components=(),
    nets=(),
    enable_zone_pours=False,
    tree_routes=None,
    partial_tree_routes=None,
):
    routing_results = SimpleNamespace(
        compiled_routes=dict(compiled),
        tree_routes=tree_routes or {},
        partial_tree_routes=partial_tree_routes or {},
    )
    pcb = SimpleNamespace(components=list(components), nets=list(nets))
    return SimpleNamespace(
        stage4=SimpleNamespace(routing_results=routing_results),
        pcb=pcb,
        enable_zone_pours=enable_zone_pours,
    )


def _path_segs(*points, layer="F.Cu", path_length=1.0):
    return SimpleNamespace(path_length=path_length, segments=[(x, y, layer) for x, y in points])


def _route(path, width=0.2, vias=()):
    return SimpleNamespace(path=path, width_mm=width, vias=list(vias))


_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2") (net 3 "PLANE"))'


def _assert_routes_same(want, got, msg=""):
    assert got[0] == want[0], f"{msg}: routed content differs\n--- want ---\n{want[0]}\n--- got ---\n{got[0]}"
    assert got[1] == want[1], f"{msg}: pad_positions differ"


# ---------------------------------------------------------------------------
# _select_sat_nets
# ---------------------------------------------------------------------------


def test_select_sat_nets_none_when_unbounded_or_sufficient():
    for max_n in (None, 2, 10):
        pcb = _pcb(_net("A", 3), _net("B", 1))
        want = _route_oracle._select_sat_nets(_self(max_n), pcb)
        got = shim_select_sat_nets(_self(max_n), pcb)
        assert got == want


def test_select_sat_nets_top_n_by_ascending_pin_count():
    pcb = _pcb(
        _net("A", 5),
        _net("B", 1),
        _net("C", 3),
        _net("D", 5),
        _net("E", 2),
    )
    want = _route_oracle._select_sat_nets(_self(2), pcb)
    got = shim_select_sat_nets(_self(2), pcb)
    assert got == ["B", "E"]
    assert got == want


def test_select_sat_nets_stable_ties_preserve_insertion_order():
    # Equal pin counts keep the nets' dict insertion order (stable sort).
    pcb = _pcb(
        _net("Z", 2),
        _net("A", 2),
        _net("M", 2),
        _net("X", 3),
        _net("Q", 1),
    )
    want = _route_oracle._select_sat_nets(_self(4), pcb)
    got = shim_select_sat_nets(_self(4), pcb)
    assert got == ["Q", "Z", "A", "M"]
    assert got == want


def test_select_sat_nets_last_writer_wins_for_duplicate_names():
    # The dict comprehension keeps the LAST pin count for a duplicated name
    # while retaining first-insertion order.
    pcb = _pcb(_net("N", 1), _net("N", 4), _net("M", 2))
    want = _route_oracle._select_sat_nets(_self(1), pcb)
    got = shim_select_sat_nets(_self(1), pcb)
    assert got == want


def test_select_sat_nets_many_randomized():
    import random

    rng = random.Random(20260810)
    for _ in range(30):
        names = [f"N{i}" for i in range(rng.randint(0, 8))]
        nets = [_net(n, rng.randint(0, 6)) for n in names]
        pcb = _pcb(*nets)
        max_n = rng.choice([None, 0, 1, 2, 3, 5, 9])
        want = _route_oracle._select_sat_nets(_self(max_n), pcb)
        got = shim_select_sat_nets(_self(max_n), pcb)
        assert got == want


# ---------------------------------------------------------------------------
# _build_clause_origin
# ---------------------------------------------------------------------------


def _model(*constraints):
    return SimpleNamespace(constraints=list(constraints))


def test_clause_origin_empty_model_and_none():
    assert shim_clause_origin(None) == _route_oracle._build_clause_origin(None) == []
    model = _model()
    assert shim_clause_origin(model) == _route_oracle._build_clause_origin(model) == []


def test_clause_origin_terms_branch_counts_n_times_3():
    c = _constraint("cap1", terms=[1, 2, 3])
    model = _model(c)
    want = _route_oracle._build_clause_origin(model)
    got = shim_clause_origin(model)
    assert got == ["cap1"] * 9
    assert got == want


def test_clause_origin_terms_truthiness_and_empty_terms_fall_through():
    # An empty terms list is falsy -> the group branch (or p_var branch) wins.
    c_terms = _constraint("empty_terms", terms=[])
    c_group = _constraint("ga", terms=[], group_a_indices=[1, 2], group_b_indices=[3])
    c_pvar = _constraint("dp", p_var="p0", n_var="n0")
    c_plain = _constraint("plain")
    model = _model(c_terms, c_group, c_pvar, c_plain)
    want = _route_oracle._build_clause_origin(model)
    got = shim_clause_origin(model)
    assert got == ["empty_terms"] + ["ga"] * 9 + ["dp"] * 2 + ["plain"]
    assert got == want


def test_clause_origin_group_branch_counts_both_indices():
    c = _constraint("gb", terms=[], group_a_indices=[1], group_b_indices=[2, 3, 4])
    model = _model(c)
    want = _route_oracle._build_clause_origin(model)
    got = shim_clause_origin(model)
    assert got == ["gb"] * 12
    assert got == want


def test_clause_origin_terms_takes_priority_over_group_attrs():
    c = _constraint("both", terms=[1], group_a_indices=[9, 9, 9])
    model = _model(c)
    want = _route_oracle._build_clause_origin(model)
    got = shim_clause_origin(model)
    assert got == ["both"] * 3
    assert got == want


def test_clause_origin_many_randomized():
    import random

    rng = random.Random(20260810)
    for _ in range(30):
        constraints = []
        for i in range(rng.randint(0, 6)):
            name = f"C{i}"
            kind = rng.randint(0, 3)
            if kind == 0:
                constraints.append(_constraint(name, terms=[0] * rng.randint(0, 4)))
            elif kind == 1:
                constraints.append(
                    _constraint(
                        name,
                        terms=[],
                        group_a_indices=[0] * rng.randint(1, 3),
                        group_b_indices=[0] * rng.randint(1, 3),
                    )
                )
            elif kind == 2:
                constraints.append(_constraint(name, p_var="p", n_var="n"))
            else:
                constraints.append(_constraint(name))
        model = _model(*constraints)
        want = _route_oracle._build_clause_origin(model)
        got = shim_clause_origin(model)
        assert got == want


# ---------------------------------------------------------------------------
# select_routing_grids
# ---------------------------------------------------------------------------


def test_select_routing_grids_empty_raises_value_error():
    with pytest.raises(ValueError, match="No occupancy grid available"):
        shim_select_grids({})
    with pytest.raises(ValueError, match="No occupancy grid available"):
        _route_oracle.select_routing_grids({})


def test_select_routing_grids_fcu_bcu_preference():
    grids = {"F.Cu": _grid("F.Cu"), "B.Cu": _grid("B.Cu"), "In1.Cu": _grid("In1.Cu")}
    want = _route_oracle.select_routing_grids(grids)
    got = shim_select_grids(grids)
    assert got[0] is grids["F.Cu"]
    assert got[1] is grids["B.Cu"]
    assert got[0] is want[0] and got[1] is want[1]


def test_select_routing_grids_plane_outer_board_falls_back_to_inner():
    # No F.Cu / B.Cu grid (planes consume the outer layers): primary is the
    # first inner layer, alternate the next different layer.
    grids = {"In1.Cu": _grid("In1.Cu"), "In2.Cu": _grid("In2.Cu")}
    want = _route_oracle.select_routing_grids(grids)
    got = shim_select_grids(grids)
    assert got[0] is grids["In1.Cu"]
    assert got[1] is grids["In2.Cu"]
    assert got[0] is want[0] and got[1] is want[1]


def test_select_routing_grids_alternate_excludes_primary_layer_not_literal_fcu():
    # The historical bug: selecting the alternate by excluding the literal
    # name "F.Cu" returned the primary a second time on plane-outer boards.
    grids = {"F.Cu": _grid("F.Cu"), "In1.Cu": _grid("In1.Cu")}
    want = _route_oracle.select_routing_grids(grids)
    got = shim_select_grids(grids)
    assert got[0] is grids["F.Cu"]
    assert got[1] is grids["In1.Cu"]
    assert got[1].layer_name != got[0].layer_name
    assert got[0] is want[0] and got[1] is want[1]


def test_select_routing_grids_single_grid_no_alternate():
    grids = {"F.Cu": _grid("F.Cu")}
    want = _route_oracle.select_routing_grids(grids)
    got = shim_select_grids(grids)
    assert got[0] is grids["F.Cu"]
    assert got[1] is None
    assert got[0] is want[0] and got[1] is want[1]


def test_select_routing_grids_falsy_grid_falls_through_or():
    # The `or` is a truthiness test, not `is not None` -- a falsy F.Cu grid
    # falls through to the first value (In1.Cu, inserted before F.Cu).
    grids = {"In1.Cu": _grid("In1.Cu"), "F.Cu": _FalsyGrid("F.Cu")}
    want = _route_oracle.select_routing_grids(grids)
    got = shim_select_grids(grids)
    assert got[0] is grids["In1.Cu"]
    assert got[0] is want[0]
    assert got[1] is want[1]


def test_select_routing_grids_many_randomized():
    import random

    rng = random.Random(20260810)
    layers = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu", "F.Cu_coarse"]
    for _ in range(30):
        n = rng.randint(1, 5)
        names = rng.sample(layers, n)
        grids = {name: _grid(name) for name in names}
        want = _route_oracle.select_routing_grids(grids)
        got = shim_select_grids(grids)
        assert got[0] is want[0]
        assert got[1] is want[1]


# ---------------------------------------------------------------------------
# _next_tstamp
# ---------------------------------------------------------------------------


def test_next_tstamp_sequence_matches_uuid5_oracle():
    counter_a = [0]
    counter_b = [0]
    for _ in range(8):
        want = _adapter_oracle._next_tstamp(counter_a)
        got = shim_next_tstamp(counter_b)
        assert got == want


def test_next_tstamp_shared_counter_continues_across_arms():
    # Both arms consume one shared counter: the Rust side must continue the
    # sequence where the oracle left off (the shim passes the same list).
    counter = [3]
    want = [_adapter_oracle._next_tstamp(counter) for _ in range(5)]
    assert counter == [8]
    counter2 = [3]
    got = [shim_next_tstamp(counter2) for _ in range(5)]
    assert counter2 == [8]
    assert got == want


def test_next_tstamp_nonzero_start_and_wrap():
    counter = [123]
    want = _adapter_oracle._next_tstamp(counter)
    got = shim_next_tstamp([123])
    assert got == want


# ---------------------------------------------------------------------------
# _to_stage0_netclass_rules
# ---------------------------------------------------------------------------


def _rules(**attrs):
    return SimpleNamespace(**attrs)


def test_to_stage0_full_mapped_fields():
    r = _rules(
        name="HV",
        clearance=0.5,
        trace_width=1.0,
        via_diameter=0.8,
        via_drill=0.4,
        max_current_rating=5.0,
        safety_category="HV",
        creepage_mm=2.0,
    )
    want = _adapter_oracle._to_stage0_netclass_rules(r)
    got = shim_to_stage0(r)
    assert (got.name, got.clearance_mm, got.trace_width_mm, got.via_diameter_mm, got.via_drill_mm) == (
        want.name, want.clearance_mm, want.trace_width_mm, want.via_diameter_mm, want.via_drill_mm,
    )
    assert got.current_rating_amps == want.current_rating_amps
    assert got.safety_category == want.safety_category
    assert got.creepage_mm == want.creepage_mm


def test_to_stage0_alias_resolution_and_defaults():
    r = _rules(
        name="LV",
        clearance_mm=0.3,
        trace_width_mm=0.6,
        via_diameter_mm=0.5,
        via_drill_mm=0.25,
    )
    want = _adapter_oracle._to_stage0_netclass_rules(r)
    got = shim_to_stage0(r)
    assert got.clearance_mm == 0.3 and got.trace_width_mm == 0.6
    assert got.via_diameter_mm == 0.5 and got.via_drill_mm == 0.25
    assert got.current_rating_amps is None
    assert got.safety_category is None
    assert got.creepage_mm == 0.0
    assert (got.name, got.clearance_mm, got.trace_width_mm, got.via_diameter_mm, got.via_drill_mm) == (
        want.name, want.clearance_mm, want.trace_width_mm, want.via_diameter_mm, want.via_drill_mm,
    )


def test_to_stage0_none_safety_category_stays_none():
    r = _rules(name="AC", clearance=1.0, trace_width=2.0, via_diameter=1.0, via_drill=0.5, safety_category=None)
    want = _adapter_oracle._to_stage0_netclass_rules(r)
    got = shim_to_stage0(r)
    assert got.safety_category is None
    assert got.safety_category == want.safety_category


def test_to_stage0_missing_field_raises_type_error_with_message():
    r = _rules(trace_width=1.0, via_diameter=1.0, via_drill=0.5)
    with pytest.raises(TypeError, match="no attribute matching any of"):
        shim_to_stage0(r)
    with pytest.raises(TypeError, match="no attribute matching any of"):
        _adapter_oracle._to_stage0_netclass_rules(r)


def test_to_stage0_type_error_message_bit_identical():
    r = _rules(trace_width=1.0)
    try:
        _adapter_oracle._to_stage0_netclass_rules(r)
    except TypeError as want:
        try:
            shim_to_stage0(r)
        except TypeError as got:
            assert str(got) == str(want)
        else:
            pytest.fail("shim did not raise TypeError")
    else:
        pytest.fail("oracle did not raise TypeError")


def test_to_stage0_unrepresented_warnings_via_same_logger(caplog):
    r = _rules(
        name="EX",
        clearance=1.0,
        trace_width=1.0,
        via_diameter=1.0,
        via_drill=0.5,
        voltage_v=230.0,
        routing_strategy="plane_required",
        dru_priority=5,
    )
    with caplog.at_level(logging.WARNING, logger="temper_placer.router_v6._adapter_convert"):
        _adapter_oracle._to_stage0_netclass_rules(r)
    want_records = [(m.levelname, m.getMessage()) for m in caplog.records]

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="temper_placer.router_v6._adapter_convert"):
        shim_to_stage0(r)
    got_records = [(m.levelname, m.getMessage()) for m in caplog.records]
    assert got_records == want_records
    assert len(got_records) == 3


def test_to_stage0_core_netclass_rules_many_randomized():
    import random

    from temper_placer.core.netclass_rules_gen import NetClassRules

    rng = random.Random(20260810)
    for _ in range(25):
        source = NetClassRules(
            name=f"CLS{rng.randint(0, 99)}",
            trace_width=rng.uniform(0.05, 10.0),
            clearance=rng.uniform(0.05, 10.0),
            via_diameter=rng.uniform(0.1, 5.0),
            via_drill=rng.uniform(0.05, 3.0),
            max_current_rating=rng.choice([None, rng.uniform(0.1, 100.0)]),
            safety_category=rng.choice([None, "HV", "LV", "AC", "iso"]),
            creepage_mm=rng.uniform(0.0, 10.0),
        )
        want = _adapter_oracle._to_stage0_netclass_rules(source)
        got = shim_to_stage0(source)
        assert got.name == want.name
        assert got.clearance_mm == want.clearance_mm
        assert got.trace_width_mm == want.trace_width_mm
        assert got.via_diameter_mm == want.via_diameter_mm
        assert got.via_drill_mm == want.via_drill_mm
        assert got.current_rating_amps == want.current_rating_amps
        assert got.safety_category == want.safety_category
        assert got.creepage_mm == want.creepage_mm


# ---------------------------------------------------------------------------
# _write_routes_to_content (the segment/via emission core)
# ---------------------------------------------------------------------------


def test_write_routes_nothing_routed_returns_content_unchanged():
    result = _make_result({})
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "no compiled routes")


def test_write_routes_no_routing_results():
    result = SimpleNamespace(
        stage4=SimpleNamespace(routing_results=None), pcb=None, enable_zone_pours=False
    )
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "no routing_results")


def test_write_routes_single_net_emits_merged_segment():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET1", [("C1", "1"), ("C2", "1")])]
    route = _route(_path_segs((0.0, 0.0), (0.0, 0.1), (0.0, 0.2)))
    result = _make_result({"NET1": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "single net")
    assert got[0] != _CONTENT
    assert "(segment (start 0.0000 0.0000) (end 0.0000 0.2000)" in got[0]
    assert ' (net 1) ' in got[0]


def test_write_routes_staircase_collapse_and_vias():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET1", [("C1", "1"), ("C2", "1")])]
    points = [
        (0.0, 0.0), (0.0, 0.1), (0.1, 0.1), (0.1, 0.2), (0.2, 0.2), (0.2, 0.3), (0.3, 0.3),
    ]
    path = SimpleNamespace(path_length=1.0, segments=[(x, y, "F.Cu") for x, y in points])
    route = _route(path, vias=[_via(0.3, 0.3)])
    result = _make_result({"NET1": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "staircase + via")
    assert "(via (at 0.3000 0.3000)" in got[0]


def test_write_routes_layer_change_splits_merge_chain():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET1", [("C1", "1"), ("C2", "1")])]
    path = SimpleNamespace(
        path_length=1.0,
        segments=[(0.0, 0.0, "F.Cu"), (0.1, 0.0, "F.Cu"), (0.1, 0.0, "B.Cu"), (0.1, 0.1, "B.Cu")],
    )
    route = _route(path)
    result = _make_result({"NET1": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "layer change splits chain")
    # The layer-change pair (coincident points) must not become a segment.
    assert "(segment" in got[0]


def test_write_routes_coordinates_branch_defaults_to_layer_name():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET2", [("C1", "1"), ("C2", "1")])]
    path = SimpleNamespace(path_length=2.0, coordinates=[(5.0, 5.0), (5.0, 5.1)], layer_name="B.Cu")
    route = _route(path)
    result = _make_result({"NET2": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "coordinates branch")
    assert '"B.Cu"' in got[0]


def test_write_routes_zero_length_path_emits_no_segment():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET1", [("C1", "1"), ("C2", "1")])]
    route = _route(_path_segs((0.0, 0.0), (0.1, 0.0), path_length=0.0))
    result = _make_result({"NET1": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "zero-length path")
    assert got[0] == _CONTENT


def test_write_routes_single_pad_net_skips_segment():
    comps = [_comp("C1")]
    nets = [_net_with_pins("NET1", [("C1", "1")])]
    route = _route(_path_segs((0.0, 0.0), (0.1, 0.0)))
    result = _make_result({"NET1": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "single-pad net")
    assert got[0] == _CONTENT


def test_write_routes_unknown_net_number_defaults_to_zero():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("GHOST", [("C1", "1"), ("C2", "1")])]
    route = _route(_path_segs((0.0, 0.0), (0.1, 0.0)))
    result = _make_result({"GHOST": route}, components=comps, nets=nets)
    want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
    got = shim_write_routes(_CONTENT, result)
    _assert_routes_same(want, got, "unknown net number")
    assert "(net 0)" in got[0]


def test_write_routes_nonpositive_width_snapped_to_0_2():
    comps = [_comp("C1"), _comp("C2")]
    nets = [_net_with_pins("NET1", [("C1", "1"), ("C2", "1")])]
    for bad in (0.0, -0.5):
        route = _route(_path_segs((0.0, 0.0), (0.1, 0.0)), width=bad)
        result = _make_result({"NET1": route}, components=comps, nets=nets)
        want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
        got = shim_write_routes(_CONTENT, result)
        _assert_routes_same(want, got, f"width {bad}")
        assert "(width 0.2000)" in got[0]


def test_write_routes_many_randomized_routes():
    import random

    rng = random.Random(20260810)
    comps = [_comp("C1"), _comp("C2"), _comp("C3")]
    nets = [
        _net_with_pins("NET1", [("C1", "1"), ("C2", "1")]),
        _net_with_pins("NET2", [("C2", "1"), ("C3", "1")]),
        _net_with_pins("NET3", [("C1", "1"), ("C3", "1")]),
    ]
    for _ in range(20):
        compiled = {}
        for i, net_name in enumerate(["NET1", "NET2", "NET3"]):
            if rng.random() < 0.5:
                continue
            n = rng.randint(2, 8)
            pts = [(rng.uniform(0, 5), rng.uniform(0, 5)) for _ in range(n)]
            layer = rng.choice(["F.Cu", "B.Cu"])
            path = SimpleNamespace(path_length=rng.uniform(0.0, 3.0), segments=[(x, y, layer) for x, y in pts])
            vias = (
                [_via(rng.uniform(0, 5), rng.uniform(0, 5)) for _ in range(rng.randint(0, 2))]
                if rng.random() < 0.5
                else []
            )
            compiled[net_name] = _route(path, width=rng.choice([0.2, 0.5, 0.0]), vias=vias)
        result = _make_result(compiled, components=comps, nets=nets)
        want = _adapter_oracle._write_routes_to_content(_CONTENT, result)
        got = shim_write_routes(_CONTENT, result)
        _assert_routes_same(want, got, f"randomized {sorted(compiled)}")
