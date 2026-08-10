"""Property-based tests (G4) for the D4 deterministic assignment batch
(Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D4).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d4_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every migrated surface
reached by at least one property:

- P1 (ComponentAssignmentStage): a state with no netlist returns the state
  unchanged (identity-preserving guard).
- P2 (ComponentAssignmentStage): on a generous slot grid every component in
  the zone map receives a placement.
- P3 (ComponentAssignmentStage): no two components share a slot (the
  footprint reservation is respected) and placements are deterministic.
- P4 (ComponentAssignmentStage): a domain region covering no slot in the
  component's zone leaves that component unplaced (filter confinement).
- P5 (validator): a state with no netlist produces zero failures.
- P6 (validator): ``creepage_mm == 0`` produces zero failures (degenerate
  no-op).
- P7 (validator): a ``creepage_mm`` beyond the slot-grid diagonal saturates
  and produces zero failures.
- P8 (validator): deleting a slot from ``used_slots`` inside an HV pin's
  creepage ring produces at least one ``hv_creepage_unblocked`` failure.

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4/D2/D3 PBT
pattern).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_REF = st.sampled_from(["Q1", "C1", "U_MCU1", "U2", "R1", "R2"])


@st.composite
def assignment_input(draw: st.DrawFn) -> BoardState:
    """A BoardState with 1-4 components, per-ref zone map and a generous
    slot grid (guaranteeing a slot for every small component)."""
    refs = draw(
        st.lists(_REF, min_size=1, max_size=4, unique=True)
    )
    comps = [
        Component(
            ref=ref, footprint="FP", bounds=(1.0, 1.0),
            pins=[Pin(str(i), "1", (0.0, 0.0), net=f"N{i}")],
        )
        for i, ref in enumerate(refs)
    ]
    spacing = draw(st.sampled_from([5.0, 10.0, 12.0]))
    # 100x100 grid at the chosen spacing -- far more slots than components.
    slots = tuple(
        (float(x), float(y))
        for x in range(0, 100, int(spacing))
        for y in range(0, 100, int(spacing))
    )
    return BoardState(
        netlist=Netlist(components=comps, nets=[]),
        component_zone_map=frozenset((c.ref, "Signal") for c in comps),
        zone_slots=frozenset({("Signal", slots)}),
    )


@st.composite
def validator_input(draw: st.DrawFn) -> BoardState:
    """A validatable state: an HV component at (0,0) + an LV component, a
    5mm slot grid and the FR4 SSOT design rules."""
    q1 = Component(
        ref="Q1", footprint="TO247", bounds=(10.0, 10.0), initial_position=(0.0, 0.0),
        pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+")],
    )
    c1 = Component(
        ref="C1", footprint="0603", bounds=(2.0, 2.0), initial_position=(30.0, 30.0),
        pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
    )
    netlist = Netlist(components=[q1, c1], nets=[])
    rules = DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage", trace_width=0.5, clearance=2.0,
                dru_priority=10, creepage_mm=draw(st.sampled_from([5.0, 6.0, 8.0])),
                safety_category="HV",
            ),
            "Power": NetClassRules(
                name="Power", trace_width=0.25, clearance=0.2,
                dru_priority=20, safety_category="LV",
            ),
        },
        net_class_assignments={"DC_BUS+": "HighVoltage", "VCC": "Power"},
    )
    slots = tuple(
        (float(x), float(y)) for x in range(0, 60, 5) for y in range(0, 60, 5)
    )
    return BoardState(
        netlist=netlist,
        design_rules=rules,
        component_zone_map=frozenset((c.ref, "Signal") for c in netlist.components),
        zone_slots=frozenset({("Signal", slots)}),
        placements=frozenset({("Q1", (0.0, 0.0)), ("C1", (30.0, 30.0))}),
    )


# ---------------------------------------------------------------------------
# P1 -- no-netlist guard
# ---------------------------------------------------------------------------

def _body_p1(impl, state):
    out = impl(state, 12.0, {})
    assert out is state
    assert out.placements == state.placements == frozenset()


@given(st.just(BoardState()))
@settings(max_examples=1, deadline=None)
def test_p1_no_netlist_guard_identity(state):
    _body_p1(_to.run_component_assignment, state)


def test_p1_fails_for_attach_mutant():
    """Mutant: attaches a placement without a netlist -> P1 must trip."""

    def mutant(state, slot_spacing, fixed):  # noqa: ARG001
        return replace(state, placements=frozenset({("R1", (0.0, 0.0))}))

    _assert_mutant_detected(_body_p1, mutant, BoardState())


# ---------------------------------------------------------------------------
# P2 -- every component placed
# ---------------------------------------------------------------------------

def _body_p2(impl, state):
    out = impl(state, 12.0, {})
    placements = dict(out.placements)
    assert set(placements) == {c.ref for c in state.netlist.components}


@given(assignment_input())
@settings(max_examples=50, deadline=None)
def test_p2_all_components_placed(state):
    _body_p2(_to.run_component_assignment, state)


def test_p2_fails_for_drop_component_mutant():
    """Mutant: drops the first component from the result -> P2 must trip."""

    def mutant(state, slot_spacing, fixed):  # noqa: ARG001
        out = _to.run_component_assignment(state, 12.0, {})
        refs = [c.ref for c in state.netlist.components]
        kept = {r: p for r, p in dict(out.placements).items() if r != refs[0]}
        return replace(out, placements=frozenset(kept.items()))

    state = assignment_input().example()
    _assert_mutant_detected(_body_p2, mutant, state)


# ---------------------------------------------------------------------------
# P3 -- unique slots + determinism
# ---------------------------------------------------------------------------

def _body_p3(impl, state):
    a = impl(state, 12.0, {})
    b = impl(state, 12.0, {})
    pa = dict(a.placements)
    pb = dict(b.placements)
    assert len(pa.values()) == len(set(pa.values())), "duplicate slot assignment"
    assert pa == pb, "two runs must agree"


@given(assignment_input())
@settings(max_examples=50, deadline=None)
def test_p3_unique_slots_and_determinism(state):
    _body_p3(_to.run_component_assignment, state)


def test_p3_fails_for_double_assign_mutant():
    """Mutant: forces two components onto the same slot -> P3 must trip."""

    def mutant(state, slot_spacing, fixed):  # noqa: ARG001
        out = _to.run_component_assignment(state, 12.0, {})
        refs = [c.ref for c in state.netlist.components]
        items = list(dict(out.placements).items())
        if len(items) < 2:
            return out
        first = items[0]
        doubled = dict(items)
        doubled[items[1][0]] = first[1]
        return replace(out, placements=frozenset(doubled.items()))

    state = assignment_input().example()
    _assert_mutant_detected(_body_p3, mutant, state)


# ---------------------------------------------------------------------------
# P4 -- domain-filter confinement
# ---------------------------------------------------------------------------

def _body_p4(impl, state, region_poly):
    state = replace(
        state,
        component_domain_map=frozenset(
            (c.ref, "LV_interior") for c in state.netlist.components
        ),
        domain_regions=tuple([Polygon(region_poly)]),
    )
    out = impl(state, 12.0, {})
    # The region covers ONLY the x >= 50 half of the grid, so every placed
    # component must land there.
    assert dict(out.placements), "placement must exist"
    assert all(pos[0] >= 50.0 for pos in dict(out.placements).values())


@given(assignment_input())
@settings(max_examples=20, deadline=None)
def test_p4_domain_confinement(state):
    # Right-half polygon: covers exactly the x in [50, 100] slots of the
    # (0..95)^2 grid.
    _body_p4(
        _to.run_component_assignment, state,
        [(50, -10), (200, -10), (200, 110), (50, 110)],
    )


def test_p4_fails_for_ignore_domain_mutant():
    """Mutant: drops the domain filter -> P4 must trip (the unfiltered
    greedy places components at the x < 50 slots)."""

    def mutant(state, slot_spacing, fixed):  # noqa: ARG001
        return _to.run_component_assignment(
            replace(
                state,
                component_domain_map=frozenset(),
                domain_regions=(),
            ),
            slot_spacing,
            fixed,
        )

    state = assignment_input().example()
    _assert_mutant_detected(
        _body_p4, mutant, state,
        [(50, -10), (200, -10), (200, 110), (50, 110)],
    )


# ---------------------------------------------------------------------------
# P5 -- validator: no netlist
# ---------------------------------------------------------------------------

def _validator_rules():
    return DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage", trace_width=0.5, clearance=2.0,
                dru_priority=10, creepage_mm=6.0, safety_category="HV",
            ),
        },
        net_class_assignments={"DC_BUS+": "HighVoltage"},
    )


def _body_p5(impl, state):
    assert impl(state) == []


@given(st.just(BoardState(design_rules=_validator_rules())))
@settings(max_examples=1, deadline=None)
def test_p5_no_netlist_no_failures(state):
    _body_p5(_to.run_phased_validator_hv, state)


def test_p5_fails_for_fake_failure_mutant():
    """Mutant: emits a failure without a netlist -> P5 must trip."""

    def mutant(state):
        return [("hv_creepage_unblocked", (0.0, 0.0), "bogus")]

    _assert_mutant_detected(_body_p5, mutant, BoardState(design_rules=_validator_rules()))


# ---------------------------------------------------------------------------
# P6 / P7 -- validator degenerate creepage
# ---------------------------------------------------------------------------

def _body_p6(impl, state):
    out = impl(state)
    assert out == []


@given(validator_input())
@settings(max_examples=20, deadline=None)
def test_p6_zero_creepage_no_failures(state):
    rules = state.design_rules
    rules = replace(rules, net_classes=dict(rules.net_classes))
    hv = rules.net_classes["HighVoltage"]
    rules.net_classes["HighVoltage"] = replace(hv, creepage_mm=0.0)
    _body_p6(_to.run_phased_validator_hv, replace(state, design_rules=rules))


def test_p6_fails_for_report_mutant():
    """Mutant: reports a failure even at creepage 0 -> P6 must trip."""

    def mutant(state):
        return [("used_slot_overclaim", (0.0, 0.0), "bogus")]

    state = validator_input().example()
    rules = state.design_rules
    rules = replace(rules, net_classes=dict(rules.net_classes))
    hv = rules.net_classes["HighVoltage"]
    rules.net_classes["HighVoltage"] = replace(hv, creepage_mm=0.0)
    _assert_mutant_detected(_body_p6, mutant, replace(state, design_rules=rules))


def _body_p7(impl, state):
    out = impl(state)
    assert out == []


@given(validator_input())
@settings(max_examples=20, deadline=None)
def test_p7_saturation_creepage_no_failures(state):
    rules = state.design_rules
    rules = replace(rules, net_classes=dict(rules.net_classes))
    hv = rules.net_classes["HighVoltage"]
    rules.net_classes["HighVoltage"] = replace(hv, creepage_mm=10_000.0)
    _body_p7(_to.run_phased_validator_hv, replace(state, design_rules=rules))


def test_p7_fails_for_report_mutant():
    """Mutant: reports a failure at saturation creepage -> P7 must trip."""

    def mutant(state):
        return [("used_slot_overclaim", (0.0, 0.0), "bogus")]

    state = validator_input().example()
    rules = state.design_rules
    rules = replace(rules, net_classes=dict(rules.net_classes))
    hv = rules.net_classes["HighVoltage"]
    rules.net_classes["HighVoltage"] = replace(hv, creepage_mm=10_000.0)
    _assert_mutant_detected(_body_p7, mutant, replace(state, design_rules=rules))


# ---------------------------------------------------------------------------
# P8 -- validator coverage gap
# ---------------------------------------------------------------------------

def _body_p8(impl, state):
    import temper_design_bundle_python as _tdb

    _rs = _tdb.deterministic_leaves
    slots = tuple(s for _, s in state.zone_slots)[0]
    spacing = 5.0
    idx = _rs.build_slot_index_py(slots, spacing)
    # Q1.1 sits at absolute (0, 0) and creepage >= 2; (0, 5) is within
    # creepage of the pin for every drawn creepage.
    ring = set(_rs.slots_within_radius_py((0.0, 0.0), 6.0, idx, spacing))
    assert (0.0, 5.0) in ring
    ring.discard((0.0, 5.0))
    tampered = replace(state, used_slots=frozenset(ring))
    failures = impl(tampered)
    assert any("hv_creepage_unblocked" in f[0] for f in failures)


@given(validator_input())
@settings(max_examples=20, deadline=None)
def test_p8_coverage_gap_reported(state):
    _body_p8(_to.run_phased_validator_hv, state)


def test_p8_fails_for_missing_check_mutant():
    """Mutant: never scans coverage -> P8 must trip."""

    def mutant(state):
        return []

    state = validator_input().example()
    _assert_mutant_detected(_body_p8, mutant, state)


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, *args)
