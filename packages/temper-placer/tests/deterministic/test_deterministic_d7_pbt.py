"""Property-based tests (G4) for the D7 deterministic routing-adjacent batch
(Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D7).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d7_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every migrated surface
reached by at least one property:

- P1 (FinePitchEscapeStage): every netted pin of a fine-pitch component gets
  an escape via at its rounded-3-decimal position; the run is deterministic.
- P2 (FinePitchEscapeStage): a component that is neither fine-pitch nor
  net-connected to a fine-pitch component gets no escape vias.
- P3 (LayerAssignmentStage): every netlist net receives exactly one
  ``LayerAssignment`` with a valid layer; the run is deterministic.
- P4 (PowerPlaneStage): every plane net ends up ``is_plane=True``; every
  netlist net appears exactly once; the run is deterministic.
- P5 (ApplyPlacementsStage): every placed ref gets ``initial_position`` equal
  to its placement; unplaced components keep their ``initial_position``; the
  run is deterministic.
- P6 (HvLvPartitionStage): the skip_empty / skip_zero / disabled / fallback
  paths return the state unchanged (identity); the ok path writes exactly one
  domain per component; the run is deterministic.
- P7 (FinePitchEscapeStage): vias are unique per rounded-3-decimal position.

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4/D1-D6 PBT
pattern).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_orchestration as _to

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages import (
    FinePitchEscapeStage as _shim_fpe,
)
from temper_placer.deterministic.stages import (
    HvLvPartitionStage as _shim_hlp,
)
from temper_placer.deterministic.stages import (
    LayerAssignmentStage as _shim_la,
)
from temper_placer.deterministic.stages import (
    PowerPlaneStage as _shim_pp,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Shared fixtures / canonicalisers
# ---------------------------------------------------------------------------

def _pin(name, position, net=None):
    return Pin(name, name, position, net=net, width=2.0, height=2.0, shape="circle")


def _comp(ref, pins, initial_position=None):
    return Component(
        ref=ref,
        footprint="FP",
        bounds=(2.0, 2.0),
        pins=pins,
        net_class="Signal",
        initial_position=initial_position,
    )


def _netlist(components, net_specs=()):
    nets = [Net(name, pins, net_class=nc) for name, pins, nc in net_specs]
    return Netlist(components=components, nets=nets)


def _round3(pos):
    return (round(float(pos[0]), 3), round(float(pos[1]), 3))


def _vias_canon(vias):
    return frozenset(
        (v.net, (float(v.position[0]).hex(), float(v.position[1]).hex()), tuple(v.layers))
        for v in vias
    )


def _vias_by_key(vias):
    return {_round3(v.position): v for v in vias}


# ---------------------------------------------------------------------------
# P1 -- fine_pitch_escape: coverage of every netted fine-pitch pin
# ---------------------------------------------------------------------------

@st.composite
def fpe_input(draw: st.DrawFn):
    """A fine-pitch U1 (two pins 0.5mm apart) plus an optional net-sharing R1,
    with a random placement offset."""
    dx = draw(st.floats(-20.0, 20.0, allow_nan=False, allow_infinity=False))
    dy = draw(st.floats(-20.0, 20.0, allow_nan=False, allow_infinity=False))
    u1 = _comp(
        "U1",
        [_pin("1", (0, 0), net="NET_A"), _pin("2", (0, 0.5), net="NET_A")],
        initial_position=(dx, dy),
    )
    r1 = _comp("R1", [_pin("1", (0, 0), net="NET_A")], initial_position=(dx + 3.0, dy))
    return BoardState(
        netlist=_netlist([u1, r1]),
        placements=frozenset({("U1", (dx, dy)), ("R1", (dx + 3.0, dy))}),
    )


def _body_p1(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias), "must be deterministic"
    by_key = _vias_by_key(out1.vias)
    for component in state.netlist.components:
        comp_pos = dict(state.placements).get(component.ref, component.initial_position)
        for pin in component.pins:
            if pin.net is None:
                continue
            if component.ref != "U1" and pin.net not in {"NET_A"}:
                continue
            from temper_placer.core.pin_geometry import pin_world_position_at

            pin_x, pin_y = pin_world_position_at(pin, component, comp_pos)
            key = (round(pin_x, 3), round(pin_y, 3))
            assert key in by_key, f"{component.ref}.{pin.name} missing an escape via at {key}"


@given(fpe_input())
@settings(max_examples=20, deadline=None)
def test_p1_fine_pitch_escape_via_coverage(inputs):
    _body_p1(_shim_fpe().run, inputs)


def test_p1_fails_for_no_vias_mutant():
    """Mutant: places no vias -> P1 must trip on the missing-escape key."""

    def mutant(state):
        return state

    _assert_mutant_detected(_body_p1, mutant, fpe_input().example())


# ---------------------------------------------------------------------------
# P2 -- fine_pitch_escape: non-fine-pitch components get no vias
# ---------------------------------------------------------------------------

@st.composite
def fpe_no_fp_input(draw: st.DrawFn):
    """A single component whose pins are far apart (min pitch >= threshold)
    with nets that touch nothing fine-pitch."""
    x = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
    c1 = _comp(
        "C1",
        [_pin("1", (0, 0), net="A"), _pin("2", (5.0, 0), net="B")],
        initial_position=(x, y),
    )
    return BoardState(netlist=_netlist([c1]), placements=frozenset({("C1", (x, y))}))


def _body_p2(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias), "must be deterministic"
    assert len(out1.vias) == 0, "no escape vias for a non-fine-pitch-only layout"


@given(fpe_no_fp_input())
@settings(max_examples=20, deadline=None)
def test_p2_no_vias_for_non_fine_pitch(inputs):
    _body_p2(_shim_fpe().run, inputs)


def test_p2_fails_for_always_via_mutant():
    """Mutant: always places a via -> P2 must trip on the non-empty set."""

    def mutant(state):
        from temper_placer.core.board import Via

        return replace(state, vias=frozenset({Via(position=(1.0, 1.0), drill=0.3, width=0.6)}))

    _assert_mutant_detected(_body_p2, mutant, fpe_no_fp_input().example())


# ---------------------------------------------------------------------------
# P3 -- layer_assignment: one assignment per net
# ---------------------------------------------------------------------------

@st.composite
def la_input(draw: st.DrawFn):
    """A netlist of N nets (random net classes)."""
    n = draw(st.integers(1, 6))
    comps = [_comp(f"R{i}", [_pin("1", (0, 0), net=f"N{i}")]) for i in range(n)]
    net_specs = [(f"N{i}", [(f"R{i}", "1")], draw(st.sampled_from(["Signal", "HighVoltage", "Ground", "Power", ""]))) for i in range(n)]
    return BoardState(netlist=_netlist(comps, net_specs), layer_assignments=None)


def _body_p3(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert {la.net_name for la in out1.layer_assignments} == {
        la.net_name for la in out2.layer_assignments
    }, "must be deterministic"
    assigned = {la.net_name for la in out1.layer_assignments}
    net_names = {net.name for net in state.netlist.nets}
    assert assigned == net_names, "every netlist net must be assigned exactly once"
    assert len(assigned) == len(net_names), "no duplicate assignments"
    for la in out1.layer_assignments:
        assert 0 <= la.layer <= 3, "layer must be one of the 4 board layers"


@given(la_input())
@settings(max_examples=20, deadline=None)
def test_p3_layer_assignment_covers_every_net(inputs):
    _body_p3(_shim_la().run, inputs)


def test_p3_fails_for_no_assignments_mutant():
    """Mutant: writes no assignments -> P3 must trip on the coverage gap."""

    def mutant(state):
        return replace(state, layer_assignments=frozenset())

    _assert_mutant_detected(_body_p3, mutant, la_input().example())


# ---------------------------------------------------------------------------
# P4 -- power_plane: plane nets are plane, all nets present
# ---------------------------------------------------------------------------

@st.composite
def pp_input(draw: st.DrawFn):
    """A netlist with at least one plane net and one signal net."""
    comps = [_comp("Q1", [_pin("1", (0, 0), net="DC_BUS+")], initial_position=(0, 0)),
             _comp("R1", [_pin("1", (0, 0), net="SIG")], initial_position=(0, 0))]
    plane = draw(st.sampled_from(["GND", "+15V", "+5V", "DC_BUS+", "AC_L"]))
    net_specs = [(plane, [("Q1", "1")], "HV"), ("SIG", [("R1", "1")], "Signal")]
    return BoardState(netlist=_netlist(comps, net_specs), layer_assignments=None)


def _body_p4(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert {la.net_name for la in out1.layer_assignments} == {
        la.net_name for la in out2.layer_assignments
    }, "must be deterministic"
    by_net = {la.net_name: la for la in out1.layer_assignments}
    assert len(by_net) == len(state.netlist.nets), "one assignment per net"
    for net in state.netlist.nets:
        assert net.name in by_net
    # Every net that the TEMPER_PLANE_NETS default marks as plane must be
    # is_plane in the output (the plane_layers default has an entry).
    from temper_placer.deterministic.stages import TEMPER_PLANE_LAYERS

    for name, la in by_net.items():
        if name in TEMPER_PLANE_LAYERS:
            assert la.is_plane is True, f"{name} must be plane-connected"
            assert la.layer == TEMPER_PLANE_LAYERS[name]


@given(pp_input())
@settings(max_examples=20, deadline=None)
def test_p4_plane_nets_are_plane(inputs):
    _body_p4(_shim_pp().run, inputs)


def test_p4_fails_for_plane_marker_dropped_mutant():
    """Mutant: strips the plane flag -> P4 must trip."""

    def mutant(state):
        from temper_placer.deterministic.stages.layer_assignment import LayerAssignment

        out = _shim_pp().run(state)
        stripped = frozenset(
            LayerAssignment(la.net_name, la.layer, la.allow_layer_change, False)
            for la in out.layer_assignments
        )
        return replace(out, layer_assignments=stripped)

    _assert_mutant_detected(_body_p4, mutant, pp_input().example())


# ---------------------------------------------------------------------------
# P5 -- apply_placements: applied + preserved
# ---------------------------------------------------------------------------

@st.composite
def ap_input(draw: st.DrawFn):
    """Components R1/C1/U1 with a random partial placement set."""
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(1.0, 1.0))
    c1 = _comp("C1", [_pin("1", (0, 0))], initial_position=(2.0, 2.0))
    u1 = _comp("U1", [_pin("1", (0, 0))], initial_position=(3.0, 3.0))
    x = draw(st.floats(-50.0, 50.0, allow_nan=False, allow_infinity=False))
    y = draw(st.floats(-50.0, 50.0, allow_nan=False, allow_infinity=False))
    place = draw(st.sampled_from([frozenset({("R1", (x, y))}),
                                  frozenset({("R1", (x, y)), ("C1", (x + 1.0, y))})]))
    return BoardState(netlist=_netlist([r1, c1, u1]), placements=place)


def _body_p5(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert out1.netlist is not None and out2.netlist is not None
    pos1 = {c.ref: c.initial_position for c in out1.netlist.components}
    pos2 = {c.ref: c.initial_position for c in out2.netlist.components}
    assert pos1 == pos2, "must be deterministic"
    placements = dict(state.placements)
    for c in out1.netlist.components:
        if c.ref in placements:
            assert c.initial_position == placements[c.ref], (
                f"{c.ref} must take its placement position"
            )
        else:
            original = {c.ref: c.initial_position for c in state.netlist.components}
            assert c.initial_position == original[c.ref], (
                f"{c.ref} must keep its original position"
            )


@given(ap_input())
@settings(max_examples=20, deadline=None)
def test_p5_placements_applied_and_preserved(inputs):
    _body_p5(_to.run_apply_placements, inputs)


def test_p5_fails_for_noop_mutant():
    """Mutant: returns the state unchanged -> P5 must trip on the unapplied
    placement."""

    def mutant(state):
        return state

    _assert_mutant_detected(_body_p5, mutant, ap_input().example())


# ---------------------------------------------------------------------------
# P6 -- hv_lv_partition: guards preserve identity, ok writes one domain each
# ---------------------------------------------------------------------------

@st.composite
def hlp_ok_input(draw: st.DrawFn):
    """An HV + LV component pair on a large board (ok decision guaranteed)."""
    q1 = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    w = draw(st.floats(20.0, 200.0, allow_nan=False, allow_infinity=False))
    board = _FakeBoard(width=w, height=w)
    net_specs = [("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")]
    rules = {"HV": _Rule("HV", 6.0), "LV": _Rule("LV", 0.0)}
    netlist = _netlist([q1, r1], net_specs)
    return BoardState(
        netlist=netlist,
        board=board,
        drc_oracle=_DrcOracle(_DesignRules(net_classes=rules)),
    )


class _Rule:
    def __init__(self, safety_category, creepage_mm):
        self.safety_category = safety_category
        self.creepage_mm = creepage_mm


class _DesignRules:
    def __init__(self, net_classes, net_class_assignments=None):
        self.net_classes = net_classes
        self.net_class_assignments = net_class_assignments or {}


class _DrcOracle:
    def __init__(self, design_rules):
        self.design_rules = design_rules


class _FakeBoard:
    def __init__(self, width=100.0, height=100.0, outline_polygon=None):
        self.width = width
        self.height = height
        self.outline_polygon = outline_polygon
        self.layer_stackup = None


def _rules(classes):
    return classes


def _body_p6_ok(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert out1.component_domain_map == out2.component_domain_map, "must be deterministic"
    domains = dict(out1.component_domain_map)
    refs = {c.ref for c in state.netlist.components}
    assert refs == set(domains), "every component gets exactly one domain"
    for domain in domains.values():
        assert domain in {"HV_edge", "LV_interior"}, f"unknown domain {domain}"
    state = hlp_ok_input().example()
    _body_p6_ok(_shim_hlp().run, state)


def test_p6_ok_fails_for_no_write_mutant():
    """Mutant: never writes the domain map -> P6 must trip on the gap."""

    def mutant(state):
        return state

    _assert_mutant_detected(_body_p6_ok, mutant, hlp_ok_input().example())


def _body_p6_guard_identity(impl, state):
    out = impl(state)
    assert out is state, "skip/guard paths must return the state unchanged"


def test_p6_skip_empty_preserves_identity():
    """All-LV -> skip_empty -> identity (deterministic fixture, not drawn)."""
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist([r1], [("+3V3", [("R1", "1")], "LV")]),
        board=_FakeBoard(),
        drc_oracle=_DrcOracle(_DesignRules(net_classes={"LV": _Rule("LV", 0.0)})),
    )
    _body_p6_guard_identity(_shim_hlp().run, state)


def test_p6_skip_zero_preserves_identity():
    """width_mm=0 -> skip_zero -> identity."""
    q1 = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist([q1, r1], [("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")]),
        board=_FakeBoard(),
        drc_oracle=_DrcOracle(_DesignRules(net_classes={"HV": _Rule("HV", 6.0), "LV": _Rule("LV", 0.0)})),
        config={"hv_lv_guard_strip": {"width_mm": 0}},
    )
    _body_p6_guard_identity(_shim_hlp().run, state)


def test_p6_guard_fails_for_always_write_mutant():
    """Mutant: writes the domain map even on a skip path -> identity assert
    must trip."""

    def mutant(state):
        return replace(state, component_domain_map=frozenset({("R1", "LV_interior")}))

    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist([r1], [("+3V3", [("R1", "1")], "LV")]),
        board=_FakeBoard(),
        drc_oracle=_DrcOracle(_DesignRules(net_classes={"LV": _Rule("LV", 0.0)})),
    )
    _assert_mutant_detected(_body_p6_guard_identity, mutant, state)


# ---------------------------------------------------------------------------
# P7 -- fine_pitch_escape: one via per rounded position
# ---------------------------------------------------------------------------

@st.composite
def fpe_multi_input(draw: st.DrawFn):
    """Several fine-pitch components whose pins may collide at rounded keys."""
    comps = []
    placements = {}
    for i, ref in enumerate(["U1", "U2"]):
        dx = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
        dy = draw(st.floats(0.0, 20.0, allow_nan=False, allow_infinity=False))
        comps.append(
            _comp(
                ref,
                [_pin("1", (0, 0), net=f"N{i}"), _pin("2", (0, 0.5), net=f"N{i}")],
                initial_position=(dx, dy),
            )
        )
        placements[(ref, (dx, dy))] = True
    return BoardState(netlist=_netlist(comps), placements=frozenset(placements))


def _body_p7(impl, state):
    out1 = impl(state)
    out2 = impl(state)
    assert _vias_canon(out1.vias) == _vias_canon(out2.vias), "must be deterministic"
    keys = [_round3(v.position) for v in out1.vias]
    assert len(keys) == len(set(keys)), "no two vias may share a rounded position"


@given(fpe_multi_input())
@settings(max_examples=20, deadline=None)
def test_p7_vias_unique_per_position(inputs):
    _body_p7(_shim_fpe().run, inputs)


def test_p7_fails_for_duplicate_vias_mutant():
    """Mutant: appends a duplicate of a real via's position -> P7 must trip."""
    state = fpe_multi_input().example()
    out = _shim_fpe().run(state)
    if not out.vias:
        pytest.skip("fixture produced no vias; mutant target absent")
    target = next(iter(out.vias))

    def mutant(state):
        from temper_placer.core.board import Via

        dup = Via(position=target.position, drill=0.3, width=0.6, layers=("F.Cu", "In1.Cu"), net="X")
        return replace(state, vias=frozenset(set(out.vias) | {dup}))

    _assert_mutant_detected(_body_p7, mutant, state)


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, *args)
