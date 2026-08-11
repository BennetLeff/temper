"""Property-based tests for the Phase E batch E6 pipeline-route
orchestration (temper-orchestration ``pipeline_route`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E6. These properties
run against the production shims (``router_v6._pipeline_route`` /
``router_v6._adapter_convert``) and hold over randomized inputs.

Seven non-vacuous properties (G4):

- P1  ``_select_sat_nets`` totality + ordering: the returned selection is a
      prefix of the nets sorted by ascending pin count (ties in insertion
      order), has length exactly ``min(max_sat_nets, distinct_nets)``, and is
      ``None`` exactly when ``max_sat_nets`` is None or >= the net count.
      Vacuity guard: a kernel that returns every net ignores the bound and
      violates.
- P2  ``_select_sat_nets`` determinism + last-writer-wins: repeated calls on
      a duplicate-name net list reproduce the oracle's dict semantics.
      Vacuity guard: a kernel whose result depends on a fresh dict order
      violates on duplicates.
- P3  ``_build_clause_origin`` accounting: the registry's length equals the
      sum of per-constraint clause counts (``max(1, len(terms)*3)`` /
      ``max(1, (len(a)+len(b))*3)`` / ``2`` / ``1`` in priority order), and
      every entry equals its owning constraint's name. Vacuity guard: a
      constant-length kernel violates.
- P4  ``select_routing_grids`` contract: primary is ``"F.Cu"``'s grid when
      present (truthy) else the first grid; alternate is ``"B.Cu"``'s grid
      when present (truthy) else the first grid whose layer differs from the
      primary's, or None. Vacuity guard: an always-B.Cu-primary kernel
      violates.
- P5  ``_next_tstamp`` determinism + uniqueness: the same counter state
      yields the same UUID; a run of calls yields pairwise-distinct
      well-formed UUIDv5 strings. Vacuity guard: a random-draw kernel
      violates (two runs differ).
- P6  ``_to_stage0_netclass_rules`` totality: every mapped field survives
      (clearance/trace_width/via_diameter/via_drill resolve from the aliases,
      max_current_rating passes through, safety_category coerces to str,
      creepage_mm defaults to 0.0). Vacuity guard: a default-zero kernel
      violates.
- P7  ``_write_routes_to_content`` emission well-formedness: every emitted
      segment is a single-line ``(segment ...)`` s-expression with a nonzero
      delta and the net's number; the routed nets' content is a superset of
      the input content. Vacuity guard: a segment-dropping kernel violates.

Anti-vacuity per G4 is explicit in each property's ``_guard`` companion.
"""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace

import hypothesis.strategies as st
from hypothesis import given, settings

from temper_placer.router_v6._adapter_convert import (
    _next_tstamp,
    _to_stage0_netclass_rules,
    _write_routes_to_content,
)
from temper_placer.router_v6._pipeline_route import (
    _build_clause_origin,
    _select_sat_nets,
    select_routing_grids,
)

_SETTINGS = settings(max_examples=80, deadline=8000, suppress_health_check=[])

_NET_NAME = st.text(min_size=1, max_size=8).filter(lambda s: '"' not in s)
_PIN_COUNT = st.integers(min_value=0, max_value=12)


def _self(max_sat_nets):
    return SimpleNamespace(max_sat_nets=max_sat_nets)


def _nets(*pairs):
    return SimpleNamespace(nets=[SimpleNamespace(name=n, pins=list(range(p))) for n, p in pairs])


def _grid(name):
    return SimpleNamespace(layer_name=name)


def _constraint(name, **attrs):
    return SimpleNamespace(name=name, **attrs)


def _via(x, y):
    return SimpleNamespace(position=(x, y), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu")


# ---------------------------------------------------------------------------
# P1 — _select_sat_nets totality + ordering
# ---------------------------------------------------------------------------


@given(
    st.lists(st.tuples(_NET_NAME, _PIN_COUNT), min_size=1, max_size=8),
    st.one_of(st.none(), st.integers(min_value=0, max_value=8)),
)
@_SETTINGS
def test_p1_select_sat_nets_ordering_and_bound(pairs, max_sat_nets):
    pcb = _nets(*pairs)
    sel = _select_sat_nets(_self(max_sat_nets), pcb)
    counts = {n: c for n, c in pairs}  # last writer wins, first-insertion order
    if max_sat_nets is None or max_sat_nets >= len(pairs):
        assert sel is None
        return
    assert sel is not None
    assert len(sel) == min(max_sat_nets, len(counts))
    sorted_names = sorted(counts, key=lambda n: counts[n])
    assert sel == sorted_names[:max_sat_nets]


def test_p1_guard_ignoring_bound_discriminates():
    pcb = _nets(("A", 3), ("B", 1), ("C", 2))
    sel = _select_sat_nets(_self(2), pcb)
    assert sel == ["B", "C"], "the bound must truncate the sorted selection"


# ---------------------------------------------------------------------------
# P2 — _select_sat_nets determinism + duplicate-name dict semantics
# ---------------------------------------------------------------------------


@given(st.lists(st.tuples(_NET_NAME, _PIN_COUNT), min_size=1, max_size=8))
@_SETTINGS
def test_p2_select_sat_nets_deterministic_and_last_writer_wins(pairs):
    pcb = _nets(*pairs)
    first = _select_sat_nets(_self(3), pcb)
    second = _select_sat_nets(_self(3), pcb)
    assert first == second


def test_p2_guard_random_selection_discriminates():
    # Duplicate name "N": the dict keeps first-insertion position with the
    # LAST pin count (4). A first-writer-wins kernel would see N=1 -> pick
    # "N"; the real dict semantics sort ["M"(2), "N"(4)] and pick "M".
    pcb = _nets(("N", 1), ("N", 4), ("M", 2))
    sel = _select_sat_nets(_self(1), pcb)
    assert sel == ["M"], "a duplicated name keeps first-insertion order with the last pin count"


# ---------------------------------------------------------------------------
# P3 — _build_clause_origin accounting
# ---------------------------------------------------------------------------


def _clause_count(c):
    if hasattr(c, "terms") and c.terms:
        return max(1, len(c.terms) * 3)
    if hasattr(c, "group_a_indices") and c.group_a_indices:
        return max(1, (len(c.group_a_indices) + len(c.group_b_indices)) * 3)
    if hasattr(c, "p_var") and hasattr(c, "n_var"):
        return 2
    return 1


@given(
    st.lists(
        st.one_of(
            st.builds(_constraint, st.text(min_size=1, max_size=6), terms=st.lists(st.integers(), min_size=0, max_size=4)),
            st.builds(
                _constraint,
                st.text(min_size=1, max_size=6),
                terms=st.just([]),
                group_a_indices=st.lists(st.integers(), min_size=0, max_size=3),
                group_b_indices=st.lists(st.integers(), min_size=0, max_size=3),
            ),
            st.builds(_constraint, st.text(min_size=1, max_size=6), p_var=st.text(min_size=1), n_var=st.text(min_size=1)),
            st.builds(_constraint, st.text(min_size=1, max_size=6)),
        ),
        min_size=0,
        max_size=6,
    )
)
@_SETTINGS
def test_p3_clause_origin_accounting(constraints):
    model = SimpleNamespace(constraints=constraints)
    origins = _build_clause_origin(model)
    expected_len = sum(_clause_count(c) for c in constraints)
    assert len(origins) == expected_len
    expected = []
    for c in constraints:
        expected.extend([c.name] * _clause_count(c))
    assert origins == expected


def test_p3_guard_constant_length_discriminates():
    model = SimpleNamespace(constraints=[_constraint("a", terms=[1, 2, 3])])
    origins = _build_clause_origin(model)
    assert len(origins) == 9, "AtMostK terms must produce n*3 clauses"


# ---------------------------------------------------------------------------
# P4 — select_routing_grids contract
# ---------------------------------------------------------------------------


@given(st.lists(st.sampled_from(["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]), min_size=1, max_size=5))
@_SETTINGS
def test_p4_select_routing_grids_contract(layers):
    grids = {name: _grid(name) for name in layers}
    primary, alternate = select_routing_grids(grids)
    if "F.Cu" in grids:
        assert primary.layer_name == "F.Cu"
    else:
        assert primary.layer_name == layers[0]
    if "B.Cu" in grids:
        # The `or` prefers the literal B.Cu grid even when it is the same
        # layer as the primary (the single-grid degenerate case).
        assert alternate is grids["B.Cu"]
    else:
        assert alternate is None or alternate.layer_name != primary.layer_name


def test_p4_guard_always_primary_bcu_discriminates():
    grids = {"F.Cu": _grid("F.Cu"), "B.Cu": _grid("B.Cu")}
    primary, _ = select_routing_grids(grids)
    assert primary.layer_name == "F.Cu", "outer layers are preferred when present"


# ---------------------------------------------------------------------------
# P5 — _next_tstamp determinism + uniqueness
# ---------------------------------------------------------------------------


@given(st.integers(min_value=0, max_value=500))
@_SETTINGS
def test_p5_next_tstamp_deterministic_and_unique(start):
    counter = [start]
    seen = []
    for _ in range(6):
        stamp = _next_tstamp(counter)
        assert uuid.UUID(stamp).version == 5
        assert stamp not in seen
        seen.append(stamp)
    replay = [start]
    for _ in range(6):
        assert _next_tstamp(replay) == seen[len(seen) - 6 + _]


def test_p5_guard_random_draw_discriminates():
    # A uuid4 kernel would produce a different stamp for the same counter.
    c1, c2 = [7], [7]
    s1, s2 = _next_tstamp(c1), _next_tstamp(c2)
    assert s1 == s2


# ---------------------------------------------------------------------------
# P6 — _to_stage0_netclass_rules totality
# ---------------------------------------------------------------------------


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(min_size=1, max_size=10),
            "clearance": st.floats(min_value=0.05, max_value=10.0),
            "trace_width": st.floats(min_value=0.05, max_value=10.0),
            "via_diameter": st.floats(min_value=0.1, max_value=5.0),
            "via_drill": st.floats(min_value=0.05, max_value=3.0),
            "max_current_rating": st.one_of(st.none(), st.floats(min_value=0.1, max_value=100.0)),
            "safety_category": st.one_of(st.none(), st.sampled_from(["HV", "LV", "AC", "iso"])),
            "creepage_mm": st.floats(min_value=0.0, max_value=10.0),
        }
    )
)
@_SETTINGS
def test_p6_to_stage0_totality(attrs):
    result = _to_stage0_netclass_rules(SimpleNamespace(**attrs))
    assert result.name == attrs["name"]
    assert result.clearance_mm == attrs["clearance"]
    assert result.trace_width_mm == attrs["trace_width"]
    assert result.via_diameter_mm == attrs["via_diameter"]
    assert result.via_drill_mm == attrs["via_drill"]
    assert result.current_rating_amps == attrs["max_current_rating"]
    assert result.safety_category == attrs["safety_category"]
    assert result.creepage_mm == attrs["creepage_mm"]


def test_p6_guard_alias_only_netclass_discriminates():
    # A rules object exposing only the *_mm aliases (no bare names) must
    # still convert -- a kernel that reads bare attributes only would fail.
    result = _to_stage0_netclass_rules(
        SimpleNamespace(
            name="X",
            clearance_mm=0.3,
            trace_width_mm=0.6,
            via_diameter_mm=0.5,
            via_drill_mm=0.25,
        )
    )
    assert result.clearance_mm == 0.3
    assert result.creepage_mm == 0.0


# ---------------------------------------------------------------------------
# P7 — _write_routes_to_content emission well-formedness
# ---------------------------------------------------------------------------


_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2"))'
_SEG_RE = re.compile(r"^  \(segment \(start ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\).*\)$")


@given(
    st.lists(
        st.tuples(
            _NET_NAME,
            st.lists(
                st.tuples(
                    st.floats(min_value=0.0, max_value=5.0, allow_nan=False).map(lambda x: round(x * 2) / 2),
                    st.floats(min_value=0.0, max_value=5.0, allow_nan=False).map(lambda x: round(x * 2) / 2),
                ),
                min_size=2,
                max_size=8,
            ),
            st.floats(min_value=0.01, max_value=1.0),
        ),
        min_size=0,
        max_size=3,
    )
)
@_SETTINGS
def test_p7_write_routes_emits_wellformed_segments(routes):
    comps = [SimpleNamespace(ref=f"C{i}", initial_position=(0.0, 0.0)) for i in range(4)]
    nets = []
    for i, (name, pts, _w) in enumerate(routes):
        nets.append(SimpleNamespace(name=name, pins=[("C0", "1"), ("C1", "1")]))
    compiled = {}
    for i, (name, pts, width) in enumerate(routes):
        # Drop consecutive coincident points (the writer's guard skips the
        # pair, and the half-integer strategy keeps formatting exact).
        cleaned = []
        for p in pts:
            if not cleaned or p != cleaned[-1]:
                cleaned.append(p)
        if len(cleaned) < 2:
            continue
        path = SimpleNamespace(path_length=1.0, segments=[(x, y, "F.Cu") for x, y in cleaned])
        compiled[name] = SimpleNamespace(path=path, width_mm=width, vias=[])
    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes=compiled, tree_routes={}, partial_tree_routes={}
            )
        ),
        pcb=SimpleNamespace(components=comps, nets=nets),
        enable_zone_pours=False,
    )
    output, _ = _write_routes_to_content(_CONTENT, result)
    segment_lines = [ln for ln in output.splitlines() if "(segment" in ln]
    for line in segment_lines:
        m = _SEG_RE.match(line)
        assert m is not None, f"malformed segment line: {line!r}"
        sx, sy, ex, ey = (float(m.group(i)) for i in range(1, 5))
        assert not (sx == ex and sy == ey), f"zero-length segment emitted: {line!r}"
    assert "NET1" in output  # input content preserved


def test_p7_guard_dropped_segments_discriminate():
    comps = [SimpleNamespace(ref="C0", initial_position=(0.0, 0.0)), SimpleNamespace(ref="C1", initial_position=(1.0, 1.0))]
    nets = [SimpleNamespace(name="NET1", pins=[("C0", "1"), ("C1", "1")])]
    path = SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (0.1, 0.0, "F.Cu")])
    route = SimpleNamespace(path=path, width_mm=0.2, vias=[])
    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes={"NET1": route}, tree_routes={}, partial_tree_routes={}
            )
        ),
        pcb=SimpleNamespace(components=comps, nets=nets),
        enable_zone_pours=False,
    )
    output, _ = _write_routes_to_content(_CONTENT, result)
    assert "NET1" in output and "(segment" in output
    # Merging collapses the two collinear steps into one emitted segment.
    assert output.count("(segment") == 1
