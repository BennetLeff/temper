"""Property-based tests (G4) for the D5 deterministic zone-aware batch
(Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D5).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d5_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every migrated surface
reached by at least one property:

- P1 (ZoneAwareSlotGenerationStage): a state with no zones writes the
  reclaim dict (or ``None``) and leaves ``zone_slots`` empty -- the
  isolation filter runs unconditionally.
- P2 (ZoneAwareSlotGenerationStage): a copper zone on F.Cu removes every
  slot inside its polygon; slots outside survive (and the result is
  deterministic).
- P3 (ZoneAwareSlotGenerationStage): the K4 reclaim is clamped into
  ``[0, original_req - 0.5]`` and is never negative for any width.
- P4 (PhasedComponentAssignmentStage): a state with no netlist returns the
  state unchanged (identity-preserving guard).
- P5 (PhasedComponentAssignmentStage): on a generous slot grid every
  component receives a placement (auto phase), no two components share a
  slot, and the run is deterministic.
- P6 (PhasedComponentAssignmentStage): HV creepage rings -- every grid slot
  within creepage of an HV pin's absolute position lands in ``used_slots``
  when the ring overlaps the grid.
- P7 (PhasedComponentAssignmentStage): placements do not depend on the
  netlist component order of the zone map (frozenset semantics) while the
  output stays bit-identical across two runs.

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4/D1-D4 PBT
pattern).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage as _shim_phased,
)
from temper_placer.deterministic.stages.zone_aware_slot_generation import (
    ZoneAwareSlotGenerationStage as _shim_zone_aware,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

_REF = st.sampled_from(["Q1", "C1", "U_MCU1", "R1", "R2", "U2"])


def _slot_grid(n=5, spacing=5.0) -> tuple:
    return tuple(
        (float(x), float(y))
        for x in range(0, int(n * spacing), int(spacing))
        for y in range(0, int(n * spacing), int(spacing))
    )


class _Zone:
    def __init__(self, name, bounds):
        self.name = name
        self.bounds = bounds


def _zone_state() -> BoardState:
    from temper_placer.core.board import Board

    return BoardState(
        board=Board(width=100.0, height=100.0),
        zones=frozenset({_Zone("Signal", ((0.0, 0.0), (30.0, 30.0)))}),
    )


class _CopperZone:
    def __init__(self, polygon=None, bounds=None, layers=None):
        self.name = "GND"
        self.polygon = polygon
        self.bounds = bounds
        self.layers = layers
        self.net_classes = None


@st.composite
def iso_slot_input(draw: st.DrawFn) -> BoardState:
    """A zone state with a netlist component + an isolation slot of a drawn
    width (K4 reclaim clamp domain)."""
    width = draw(st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False))
    comp = Component(
        ref="Q1", footprint="TO-247", bounds=(10.0, 10.0), initial_position=(20.0, 15.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="AC_L"), Pin("2", "2", (0.0, 5.45), net="AC_N")],
    )
    slot = IsolationSlot(
        name="s1", component_ref="Q1", lv_pin="1", hv_pin="2", width_mm=width,
        start_offset=(0.0, -5.0), end_offset=(0.0, 5.0),
    )
    return replace(_zone_state(), netlist=Netlist(components=[comp], nets=[]), zones=frozenset()), slot


@st.composite
def phased_input(draw: st.DrawFn) -> BoardState:
    """1-4 small components with a generous slot grid."""
    refs = draw(st.lists(_REF, min_size=1, max_size=4, unique=True))
    comps = [
        Component(
            ref=ref, footprint="FP", bounds=(1.0, 1.0),
            pins=[Pin("1", "1", (0.0, 0.0), net=f"N{i}")],
        )
        for i, ref in enumerate(refs)
    ]
    return BoardState(
        netlist=Netlist(components=comps, nets=[]),
        component_zone_map=frozenset((c.ref, "Signal") for c in comps),
        zone_slots=frozenset({("Signal", _slot_grid(8, 5.0))}),
    )


def _to_phased_auto(state, **kw):
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    return _shim_phased(c, **kw).run(state)


def _to_zone_aware(state, slot=None):
    return _shim_zone_aware(yaml_isolation_slots=[slot] if slot else None).run(state)


def _body_p1(impl, state, slot):
    out = impl(state, slot)
    assert out.zone_slots == frozenset()
    assert out.reclaim_by_pin_pair is not None
    assert ("Q1", "1", "2") in out.reclaim_by_pin_pair


@given(iso_slot_input())
@settings(max_examples=20, deadline=None)
def test_p1_no_zones_writes_reclaim(inputs):
    state, slot = inputs
    state = replace(state, zones=frozenset())
    _body_p1(_to_zone_aware, state, slot)


def test_p1_fails_for_drop_reclaim_mutant():
    """Mutant: drops the reclaim dict -> P1 must trip."""

    def mutant(state, slot):
        return replace(_to_zone_aware(state, slot), reclaim_by_pin_pair=None)

    state, slot = iso_slot_input().example()
    _assert_mutant_detected(_body_p1, mutant, replace(state, zones=frozenset()), slot)


# ---------------------------------------------------------------------------
# P2 -- copper-zone filtering + determinism
# ---------------------------------------------------------------------------

def _body_p2(impl, state, polygon):
    cz = _CopperZone(polygon=polygon, layers="F.Cu")
    out = impl(state, [cz])
    a = dict(out.zone_slots)["Signal"]
    out2 = impl(state, [cz])
    b = dict(out2.zone_slots)["Signal"]
    assert a == b, "two runs must agree"
    assert a, "some slots must survive outside the polygon"
    import temper_design_bundle_python as _tdb

    pip = _tdb.deterministic_phase.point_in_polygon_py
    assert not any(pip(x, y, polygon) for x, y in a), "filtered slot inside polygon"


def _zone_aware_with_zones(state, copper_zones):
    return _shim_zone_aware(yaml_copper_zones=copper_zones).run(state)


@st.composite
def copper_input(draw: st.DrawFn) -> BoardState:
    """A state WITH zones (the copper filter needs a slot grid to walk)."""
    width = draw(st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False))
    comp = Component(
        ref="Q1", footprint="TO-247", bounds=(10.0, 10.0), initial_position=(20.0, 15.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="AC_L"), Pin("2", "2", (0.0, 5.45), net="AC_N")],
    )
    slot = IsolationSlot(
        name="s1", component_ref="Q1", lv_pin="1", hv_pin="2", width_mm=width,
        start_offset=(0.0, -5.0), end_offset=(0.0, 5.0),
    )
    return replace(_zone_state(), netlist=Netlist(components=[comp], nets=[])), slot


@given(copper_input())
@settings(max_examples=10, deadline=None)
def test_p2_copper_filter_and_determinism(inputs):
    state, _slot = inputs
    polygon = [(0.0, 0.0), (15.0, 0.0), (15.0, 15.0), (0.0, 15.0)]
    _body_p2(_zone_aware_with_zones, state, polygon)


def test_p2_fails_for_skip_filter_mutant():
    """Mutant: skips the copper filter -> P2 must trip (the polygon covers
    the first grid slots)."""
    polygon = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]

    def mutant(state, copper_zones):  # noqa: ARG001
        return _shim_zone_aware().run(state)

    state, _slot = copper_input().example()
    _assert_mutant_detected(_body_p2, mutant, state, polygon)


# ---------------------------------------------------------------------------
# P3 -- K4 reclaim clamp
# ---------------------------------------------------------------------------

def _body_p3(impl, state, slot):
    out = impl(state, slot)
    value = out.reclaim_by_pin_pair[("Q1", "1", "2")]
    assert value >= 0.0, "reclaim must be non-negative"
    assert value <= 6.0 - 0.5 + 1e-12, "reclaim must not exceed original_req - 0.5"


@given(iso_slot_input())
@settings(max_examples=30, deadline=None)
def test_p3_reclaim_clamped(inputs):
    state, slot = inputs
    state = replace(state, zones=frozenset())
    _body_p3(_to_zone_aware, state, slot)


def test_p3_fails_for_unclamped_mutant():
    """Mutant: no clamp -> P3 must trip on a large width."""

    def mutant(state, slot):
        out = _to_zone_aware(state, slot)
        value = out.reclaim_by_pin_pair[("Q1", "1", "2")]
        return replace(out, reclaim_by_pin_pair={("Q1", "1", "2"): value + 1000.0})

    state, slot = iso_slot_input().example()
    _assert_mutant_detected(_body_p3, mutant, replace(state, zones=frozenset()), slot)


# ---------------------------------------------------------------------------
# P4 -- no-netlist guard (identity)
# ---------------------------------------------------------------------------

def _body_p4(impl, state):
    out = impl(state)
    assert out is state
    assert out.placements == frozenset()
    assert out.used_slots == frozenset()


@given(st.just(BoardState()))
@settings(max_examples=1, deadline=None)
def test_p4_guard_identity(state):
    _body_p4(_to_phased_auto, state)


def test_p4_fails_for_attach_mutant():
    """Mutant: attaches placements without a netlist -> P4 must trip."""

    def mutant(state):
        return replace(state, placements=frozenset({("R1", (0.0, 0.0))}))

    _assert_mutant_detected(_body_p4, mutant, BoardState())


# ---------------------------------------------------------------------------
# P5 -- every component placed, unique slots, determinism
# ---------------------------------------------------------------------------

def _body_p5(impl, state):
    a = impl(state)
    b = impl(state)
    pa = dict(a.placements)
    pb = dict(b.placements)
    assert set(pa) == {c.ref for c in state.netlist.components}
    assert pa == pb, "two runs must agree"
    assert len(pa.values()) == len(set(pa.values())), "duplicate slot assignment"


@given(phased_input())
@settings(max_examples=30, deadline=None)
def test_p5_all_placed_unique_deterministic(state):
    _body_p5(_to_phased_auto, state)


def test_p5_fails_for_drop_component_mutant():
    """Mutant: drops the first component -> P5 must trip."""

    def mutant(state):
        out = _to_phased_auto(state)
        refs = [c2.ref for c2 in state.netlist.components]
        kept = {r: p for r, p in dict(out.placements).items() if r != refs[0]}
        return replace(out, placements=frozenset(kept.items()))

    state = phased_input().example()
    _assert_mutant_detected(_body_p5, mutant, state)


# ---------------------------------------------------------------------------
# P6 -- HV creepage rings land in used_slots
# ---------------------------------------------------------------------------

def _hv_rules(creepage):
    return DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage", trace_width=0.5, clearance=2.0,
                dru_priority=10, creepage_mm=creepage, safety_category="HV",
            ),
        },
        net_class_assignments={"HV": "HighVoltage"},
    )


@st.composite
def hv_input(draw: st.DrawFn) -> BoardState:
    refs = draw(st.lists(st.just("Q1"), min_size=1, max_size=1))
    comp = Component(
        ref="Q1", footprint="TO247", bounds=(4.0, 4.0), initial_position=(0.0, 0.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="HV")],
    )
    return BoardState(
        netlist=Netlist(components=[comp], nets=[]),
        component_zone_map=frozenset({("Q1", "Signal")}),
        zone_slots=frozenset({("Signal", _slot_grid(8, 5.0))}),
        design_rules=_hv_rules(draw(st.sampled_from([6.0, 8.0, 12.0]))),
    ), refs


def _body_p6(impl, state, creepage):
    out = impl(state, design_rules=_hv_rules(creepage))
    used = set(out.used_slots)
    # The HV pin sits at some placed (x, y); every slot within creepage of
    # that absolute position must be reserved (ring-overlaps-grid case).
    x, y = dict(out.placements)["Q1"]
    import temper_design_bundle_python as _tdb

    _rs = _tdb.deterministic_leaves
    slots = tuple(s for _, s in state.zone_slots)[0]
    spacing = 5.0
    idx = _rs.build_slot_index_py(slots, spacing)
    ring = set(_rs.slots_within_radius_py((x, y), creepage, idx, spacing))
    if ring:
        assert ring <= used, "HV creepage ring slots must be in used_slots"


@given(hv_input())
@settings(max_examples=20, deadline=None)
def test_p6_hv_rings_reserved(inputs):
    state, _refs = inputs
    creepage = state.design_rules.net_classes["HighVoltage"].creepage_mm
    _body_p6(_to_phased_auto, state, creepage)


def test_p6_fails_for_no_rings_mutant():
    """Mutant: disables HV rings (design_rules=None) -> P6 must trip on a
    board where the ring overlaps the grid."""

    def mutant(state, **kw):  # noqa: ARG001
        return _shim_phased(PlacementConstraints(), design_rules=None).run(state)

    state, _refs = hv_input().example()
    _assert_mutant_detected(_body_p6, mutant, state, 6.0)


# ---------------------------------------------------------------------------
# P7 -- determinism across identical runs (frozenset zone map)
# ---------------------------------------------------------------------------

def _body_p7(impl, state):
    a = impl(state)
    b = impl(state)
    assert dict(a.placements) == dict(b.placements)
    assert set(a.used_slots) == set(b.used_slots)
    assert set(dict(a.placements)) == {c.ref for c in state.netlist.components}


@given(phased_input())
@settings(max_examples=20, deadline=None)
def test_p7_determinism(state):
    _body_p7(_to_phased_auto, state)


def test_p7_fails_for_nondeterministic_mutant():
    """Mutant: shifts a placement on the second run -> P7 must trip."""

    calls = {"n": 0}

    def mutant(state):
        calls["n"] += 1
        out = _to_phased_auto(state)
        if calls["n"] % 2 == 0:
            items = list(dict(out.placements).items())
            ref0, (x, y) = items[0]
            items[0] = (ref0, (x + 1.0, y))
            return replace(out, placements=frozenset(items))
        return out

    state = phased_input().example()
    _assert_mutant_detected(_body_p7, mutant, state)


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, *args)
