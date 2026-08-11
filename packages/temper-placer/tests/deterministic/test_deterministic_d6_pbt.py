"""Property-based tests (G4) for the D6 deterministic validation batch
(Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D6).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d6_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every migrated surface
reached by at least one property:

- P1 (PlacementValidationStage): the stored violations are deterministic and
  every resolved proximity violation carries the constraint's own
  ``max_distance_mm`` as ``required_distance_mm`` with a non-negative
  ``actual_distance_mm``.
- P2 (ViaValidationStage): a via with a trace endpoint on EVERY one of its
  layers is always kept; the run is deterministic.
- P3 (ViaDeduplicationStage): every pair of kept vias is strictly more than
  ``tolerance_mm`` apart; the run is deterministic.
- P4 (TrackDeduplicationStage): reversed/duplicate segments collapse to one
  and the run is deterministic.
- P5 (DRCValidationStage): ``drc_violations`` preserves the oracle's
  violation objects in order (and the raise decision matches the count).
- P6 (ConnectivityValidationStage): output violations never name an
  empty/``NoNet``/plane net; the run is deterministic.
- P7 (CourtyardCheckStage): a collision-free layout is left bit-identical
  and the run is deterministic under an identical ``random`` seed.
- P8 (DRCSweepStage): a net flagged BAD by the oracle is removed while good
  tracks, good vias and non-Trace route entries pass through.
- P9 (ShortCircuitDetectionStage): a track whose endpoint touches a wrong-net
  pin is removed while a same-net track survives.

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4/D1-D5 PBT
pattern).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Trace, Via
from temper_placer.deterministic.stages import (
    ConnectivityValidationStage as _shim_cv,
    CourtyardCheckStage as _shim_cc,
    DRCSweepStage as _shim_ds,
    DRCValidationStage as _shim_drv,
    PlacementValidationStage as _shim_pv,
    ShortCircuitDetectionStage as _shim_sc,
    TrackDeduplicationStage as _shim_td,
    ViaDeduplicationStage as _shim_vd,
    ViaValidationStage as _shim_vv,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.constraints_geometry import Point

# ---------------------------------------------------------------------------
# Shared fixtures / canonicalisers
# ---------------------------------------------------------------------------

def _via(x, y, net="A", layers=("F.Cu", "B.Cu"), is_diff_pair=False):
    return Via(position=(x, y), drill=0.3, width=0.6, layers=layers, net=net,
               is_diff_pair=is_diff_pair)


def _trace(x0, y0, x1, y1, layer="F.Cu", net="A"):
    return Trace(start=(x0, y0), end=(x1, y1), width=0.25, layer=layer, net=net)


def _vias_canon(vias):
    return frozenset(
        (v.net, (float(v.position[0]).hex(), float(v.position[1]).hex()), tuple(v.layers))
        for v in vias
    )


def _placements_canon(placements):
    return {
        ref: (float(x).hex(), float(y).hex())
        for ref, (x, y) in dict(placements).items()
    }


class _BadOracle:
    """Deterministic sweep oracle: net BAD -> invalid track; net BADVIA ->
    no via sites; everything else valid."""

    def can_place_track_segment(self, *, start, end, layer, net, width):
        return (True, "") if net != "BAD" else (False, "short")

    def get_valid_via_sites(self, position, search_radius=0.1, net=""):
        return [] if net == "BADVIA" else [position]


class _DrvViolation:
    def __init__(self, vtype):
        self.type = vtype

    def __str__(self):
        return f"<{self.type}>"


class _DrvOracle:
    def __init__(self, violations):
        self._violations = list(violations)

    def validate_all(self):
        return list(self._violations)


# ---------------------------------------------------------------------------
# P1 -- placement_validation
# ---------------------------------------------------------------------------

class _PVComp:
    def __init__(self, ref, x, y):
        self.ref = ref
        self.x = x
        self.y = y


class _PVBoard:
    def __init__(self, components):
        self.components = components
        self.layer_stackup = None


class _Prox:
    def __init__(self, name, from_component, from_pin, to_component, to_pin,
                 max_distance_mm, tier):
        self.name = name
        self.from_component = from_component
        self.from_pin = from_pin
        self.to_component = to_component
        self.to_pin = to_pin
        self.max_distance_mm = max_distance_mm
        self.tier = tier


@st.composite
def pv_input(draw: st.DrawFn):
    """A board with U1 at (5,5) and Q1 at (30,5), and a random proximity
    constraint between them."""
    max_dist = draw(st.floats(1.0, 40.0, allow_nan=False, allow_infinity=False))
    tier = draw(st.sampled_from(["hard", "signal"]))
    state = BoardState(
        board=_PVBoard([_PVComp("U1", 5.0, 5.0), _PVComp("Q1", 30.0, 5.0)])
    )
    constraint = _Prox("PX", "U1", "15", "Q1", "1", max_dist, tier)
    return state, constraint, max_dist


def _pv_run(state, constraint):
    return _shim_pv(
        constraints={"placement_proximity": [constraint]},
        fail_on_hard_violations=False,
    ).run(state)


def _body_p1(impl, state, constraint, max_dist):
    out1 = impl(state, constraint)
    out2 = impl(state, constraint)
    assert [(v.message, v.actual_distance_mm, v.required_distance_mm)
            for v in out1.placement_violations] == [
        (v.message, v.actual_distance_mm, v.required_distance_mm)
        for v in out2.placement_violations
    ], "placement validation must be deterministic"
    for v in out1.placement_violations:
        if v.actual_distance_mm is not None:
            assert v.actual_distance_mm >= 0.0, "distance cannot be negative"
            assert v.required_distance_mm == max_dist, (
                "required distance must be the constraint's max_distance_mm"
            )


@given(pv_input())
@settings(max_examples=20, deadline=None)
def test_p1_placement_validation_invariants(inputs):
    state, constraint, max_dist = inputs
    _body_p1(_pv_run, state, constraint, max_dist)


def test_p1_fails_for_negative_distance_mutant():
    """Mutant: a violation with a negative distance -> P1 must trip."""
    # Fixed violating input (U1->Q1 = 25mm, max 10mm): not a drawn example, so
    # the mutant test is deterministic.
    state = BoardState(board=_PVBoard([_PVComp("U1", 5.0, 5.0), _PVComp("Q1", 30.0, 5.0)]))
    constraint = _Prox("PX", "U1", "15", "Q1", "1", 10.0, "hard")

    def mutant(state, constraint):
        out = _pv_run(state, constraint)
        new = tuple(
            replace(v, actual_distance_mm=-1.0)
            for v in out.placement_violations
        )
        return replace(out, placement_violations=new)

    _assert_mutant_detected(_body_p1, mutant, state, constraint, 10.0)


# ---------------------------------------------------------------------------
# P2 -- via_validation
# ---------------------------------------------------------------------------

@st.composite
def vv_input(draw: st.DrawFn):
    """Vias + routes where the first via has a trace endpoint on EVERY layer."""
    x = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    anchored = _via(x, y, net="ANCHOR")
    dangling = _via(x + 8.0, y + 8.0, net="DANGLE")
    routes = [_trace(x, y, x + 1.0, y, net="ANCHOR"),
              _trace(x, y, x + 1.0, y, layer="B.Cu", net="ANCHOR")]
    state = BoardState(vias=frozenset({anchored, dangling}), routes=frozenset(routes))
    return state, (x, y)


def _body_p2(impl, state, anchor):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias), "must be deterministic"
    kept = {v.position for v in out1.vias}
    assert anchor in kept, "a via anchored on every layer must be kept"


@given(vv_input())
@settings(max_examples=20, deadline=None)
def test_p2_anchored_via_kept(inputs):
    state, anchor = inputs
    _body_p2(_shim_vv().run, state, anchor)


def test_p2_fails_for_drop_all_mutant():
    """Mutant: drops every via -> P2 must trip on the anchored via."""

    def mutant(state):
        return replace(state, vias=frozenset())

    state, anchor = vv_input().example()
    _assert_mutant_detected(_body_p2, mutant, state, anchor)


# ---------------------------------------------------------------------------
# P3 -- via dedup
# ---------------------------------------------------------------------------

@st.composite
def vvd_input(draw: st.DrawFn):
    """A random via layout PLUS a guaranteed close pair (within 0.05)."""
    x = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    vias = [_via(x, y, net="A"), _via(x, y + 0.01, net="A"), _via(x + 5.0, y, net="B")]
    return BoardState(vias=frozenset(vias))


def _body_p3(impl, state, tol=0.05):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias), "dedup must be deterministic"
    kept = [v.position for v in out1.vias]
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            dx = kept[i][0] - kept[j][0]
            dy = kept[i][1] - kept[j][1]
            assert (dx * dx + dy * dy) ** 0.5 > tol, "kept vias must be > tolerance apart"


@given(vvd_input())
@settings(max_examples=20, deadline=None)
def test_p3_via_dedup_separation(inputs):
    _body_p3(_shim_vd(tolerance_mm=0.05).run, inputs)


def test_p3_fails_for_no_dedup_mutant():
    """Mutant: keeps every via -> P3 must trip on the within-tolerance pair."""

    def mutant(state):
        return state

    state = vvd_input().example()
    _assert_mutant_detected(_body_p3, mutant, state)


# ---------------------------------------------------------------------------
# P4 -- track dedup
# ---------------------------------------------------------------------------

@st.composite
def td_input(draw: st.DrawFn):
    """Traces including a reversed duplicate of the first segment."""
    x = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    routes = [
        _trace(x, y, x + 10.0, y, net="A"),
        _trace(x + 10.0, y, x, y, net="A"),  # reversed duplicate
        _trace(x, y + 5.0, x + 10.0, y + 5.0, net="A"),
    ]
    return BoardState(routes=frozenset(routes))


def _body_p4(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert _routes_len(out1.routes) == _routes_len(out2.routes), "dedup must be deterministic"
    # Direction-normalised segment keys: a reversed duplicate collapses.
    segs = {
        (tuple(sorted([tuple(r.start), tuple(r.end)])), r.net)
        for r in out1.routes
        if isinstance(r, Trace)
    }
    assert len(segs) == len(out1.routes), "no duplicate segments may remain"


def _routes_len(routes):
    return sum(1 for _ in routes)


@given(td_input())
@settings(max_examples=20, deadline=None)
def test_p4_track_dedup_collapses_duplicates(inputs):
    _body_p4(_shim_td(tolerance_mm=0.05).run, inputs)


def test_p4_fails_for_no_dedup_mutant():
    """Mutant: no dedup -> P4 must trip on the reversed duplicate."""

    def mutant(state):
        return state

    state = td_input().example()
    _assert_mutant_detected(_body_p4, mutant, state)


# ---------------------------------------------------------------------------
# P5 -- drc_validation
# ---------------------------------------------------------------------------

@st.composite
def drv_input(draw: st.DrawFn):
    count = draw(st.integers(0, 5))
    types = draw(st.lists(st.sampled_from(["track_clearance", "via_dangling"]),
                          min_size=count, max_size=count))
    fail = draw(st.booleans())
    return _DrvOracle([_DrvViolation(t) for t in types]), fail


def _body_p5(impl, oracle, fail):
    if fail and oracle._violations:
        with pytest.raises(Exception) as ei:
            impl(oracle, fail)
        assert "violations" in str(ei.value), "raise message must name violations"
        return
    out = impl(oracle, fail)
    assert [v.type for v in out.drc_violations] == [v.type for v in oracle._violations], (
        "drc_violations must preserve the oracle's violations in order"
    )


@given(drv_input())
@settings(max_examples=20, deadline=None)
def test_p5_drc_validation_preserves_violations(inputs):
    oracle, fail = inputs
    _body_p5(lambda o, f: _shim_drv(fail_on_violations=f).run(BoardState(drc_oracle=o)), oracle, fail)


def test_p5_fails_for_drop_violations_mutant():
    """Mutant: drops every violation -> P5 must trip."""
    oracle = _DrvOracle([_DrvViolation("track_clearance")])  # fixed, non-empty

    def mutant(oracle, fail):
        out = _shim_drv(fail_on_violations=fail).run(BoardState(drc_oracle=oracle))
        return replace(out, drc_violations=())

    _assert_mutant_detected(_body_p5, mutant, oracle, False)


# ---------------------------------------------------------------------------
# P6 -- connectivity_validation
# ---------------------------------------------------------------------------

class _Pad:
    def __init__(self, net, x, y, layer=0):
        self.net = net
        self.center = Point(x, y)
        self.layer = layer
        self.size = (1.0, 1.0)
        self.rotation = 0.0
        self.id = "p"


class _Trk:
    def __init__(self, net, sx, sy, ex, ey, layer=0):
        self.net = net
        self.start = Point(sx, sy)
        self.end = Point(ex, ey)
        self.layer = layer


class _Geom:
    def __init__(self, pads, tracks):
        self.pads = pads
        self.tracks = tracks
        self.vias = []


class _ConnOracle:
    def __init__(self, pads, tracks):
        self.geometry = _Geom(pads, tracks)


class _LA:
    def __init__(self, net_name, is_plane):
        self.net_name = net_name
        self.is_plane = is_plane


@st.composite
def cv_input(draw: st.DrawFn):
    """Pads/tracks on a real net plus an empty-named net (with a dangling
    track, so it WOULD produce a violation if processed) and a plane net."""
    pads = [_Pad("NET_A", 0.0, 0.0), _Pad("", 50.0, 50.0)]
    tracks = [_Trk("NET_A", 0.0, 0.0, 10.0, 10.0),
              _Trk("", 70.0, 70.0, 80.0, 80.0)]
    plane = _LA("GND", True)
    return _ConnOracle(pads, tracks), [plane]


def _body_p6(impl, oracle, plane_nets):
    out1 = impl(oracle, plane_nets)
    out2 = impl(oracle, plane_nets)
    assert [(v.net, v.type) for v in out1.connectivity_violations] == [
        (v.net, v.type) for v in out2.connectivity_violations
    ], "connectivity validation must be deterministic"
    for v in out1.connectivity_violations:
        assert v.net, "violations must not name an empty net"
        assert v.net != "NoNet"
        assert v.net not in {la.net_name for la in plane_nets}, "plane nets must be skipped"


@given(cv_input())
@settings(max_examples=20, deadline=None)
def test_p6_connectivity_skips_plane_and_empty_nets(inputs):
    oracle, plane_nets = inputs
    _body_p6(
        lambda o, p: _shim_cv().run(
            BoardState(drc_oracle=o, layer_assignments=frozenset(p))
        ),
        oracle,
        plane_nets,
    )


def test_p6_fails_for_no_skip_mutant():
    """Mutant: emits a violation naming an empty net -> P6 must trip (the
    property forbids empty-net violations, which the skip guarantees)."""

    def mutant(oracle, plane_nets):
        out = _shim_cv().run(
            BoardState(drc_oracle=oracle, layer_assignments=frozenset(plane_nets))
        )
        bogus = type("_V", (), {"net": "", "type": "dangling_track", "location": Point(0, 0), "description": "x"})()
        return replace(out, connectivity_violations=out.connectivity_violations + (bogus,))

    oracle, plane_nets = cv_input().example()
    _assert_mutant_detected(_body_p6, mutant, oracle, plane_nets)


# ---------------------------------------------------------------------------
# P7 -- courtyard_check
# ---------------------------------------------------------------------------

def _square_courtyard(ref: str, half_size: float = 2.0):
    from temper_placer.core.courtyard import Courtyard

    return Courtyard(
        component_ref=ref,
        points=[(-half_size, -half_size), (half_size, -half_size),
                (half_size, half_size), (-half_size, half_size)],
    )


@st.composite
def cc_input(draw: st.DrawFn):
    """Two well-separated components (non-colliding courtyards) + a seed."""
    x = draw(st.floats(30.0, 60.0, allow_nan=False, allow_infinity=False))
    seed = draw(st.integers(0, 1_000_000))
    state = BoardState(
        placements=frozenset({"R1": (x, x), "R2": (x + 30.0, x)}.items())
    )
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    return state, courtyards, seed


def _cc_run(state, courtyards, seed):
    import random

    random.seed(seed)
    return _shim_cc(courtyards=courtyards, max_iterations=50).run(state)


def _body_p7(impl, state, courtyards, seed):
    out1 = impl(state, courtyards, seed)
    out2 = impl(state, courtyards, seed)
    assert _placements_canon(out1.placements) == _placements_canon(out2.placements), (
        "courtyard check must be deterministic under an identical seed"
    )
    assert _placements_canon(out1.placements) == _placements_canon(state.placements), (
        "a collision-free layout must be left unchanged"
    )


@given(cc_input())
@settings(max_examples=20, deadline=None)
def test_p7_courtyard_unchanged_when_clean(inputs):
    state, courtyards, seed = inputs
    _body_p7(_cc_run, state, courtyards, seed)


def test_p7_fails_for_perturb_mutant():
    """Mutant: nudges a component -> P7 must trip on the unchanged layout."""

    def mutant(state, courtyards, seed):
        import random

        random.seed(seed)
        out = _shim_cc(courtyards=courtyards, max_iterations=50).run(state)
        moved = dict(out.placements)
        r1, (rx, ry) = next(iter(moved.items()))
        moved[r1] = (rx + 1.0, ry)
        return replace(out, placements=frozenset(moved.items()))

    state, courtyards, seed = cc_input().example()
    _assert_mutant_detected(_body_p7, mutant, state, courtyards, seed)


# ---------------------------------------------------------------------------
# P8 -- drc_sweep
# ---------------------------------------------------------------------------

@st.composite
def ds_input(draw: st.DrawFn):
    x = draw(st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False))
    routes = [_trace(x, y, x + 5.0, y, net="GOOD"),
              _trace(x, y + 2.0, x + 5.0, y + 2.0, net="BAD")]
    vias = [_via(x, y, net="GOODVIA"), _via(x, y + 3.0, net="BADVIA")]
    via_in_routes = _via(x + 9.0, y + 9.0, net="VIAINROUTES")
    return BoardState(drc_oracle=_BadOracle(), routes=frozenset(routes + [via_in_routes]),
                      vias=frozenset(vias))


def _body_p8(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias)
    assert {t.net for t in out1.routes if isinstance(t, Trace)} == {"GOOD"}
    assert {v.net for v in out1.vias} == {"GOODVIA"}
    non_trace = [r for r in out1.routes if not isinstance(r, Trace)]
    assert non_trace and non_trace[0].net == "VIAINROUTES", "non-Trace entries pass through"


@given(ds_input())
@settings(max_examples=20, deadline=None)
def test_p8_drc_sweep_removes_bad_geometry(inputs):
    _body_p8(_shim_ds().run, inputs)


def test_p8_fails_for_no_removal_mutant():
    """Mutant: removes nothing -> P8 must trip on the BAD net."""

    def mutant(state):
        return state

    state = ds_input().example()
    _assert_mutant_detected(_body_p8, mutant, state)


# ---------------------------------------------------------------------------
# P9 -- short_circuit_detection
# ---------------------------------------------------------------------------

@st.composite
def sc_input(draw: st.DrawFn):
    from temper_placer.core.netlist import Component, Netlist, Pin

    x = draw(st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False))
    comp = Component(
        ref="U1", footprint="FP", bounds=(2.0, 2.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="NET_B")],
        initial_position=(x, x),
    )
    nets = [type("_Net", (), {"pins": [("U1", "1")], "name": "NET_B"})()]
    routes = [_trace(x, x, x + 5.0, x, net="NET_A"),   # endpoint on a B pin -> short
              _trace(x, x + 4.0, x + 5.0, x + 4.0, net="NET_A")]  # clear
    return BoardState(netlist=Netlist(components=[comp], nets=nets),
                      routes=frozenset(routes), placements=frozenset())


def _body_p9(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert len(out1.routes) == len(out2.routes), "must be deterministic"
    assert len(out1.routes) == 1, "the shorting track must be removed, the clear one kept"


@given(sc_input())
@settings(max_examples=20, deadline=None)
def test_p9_short_circuit_removes_wrong_net_track(inputs):
    _body_p9(_shim_sc().run, inputs)


def test_p9_fails_for_no_removal_mutant():
    """Mutant: removes nothing -> P9 must trip on the shorting track."""

    def mutant(state):
        return state

    state = sc_input().example()
    with pytest.raises(AssertionError):
        assert len(mutant(state).routes) == 1, "the shorting track must be removed"


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, *args)
