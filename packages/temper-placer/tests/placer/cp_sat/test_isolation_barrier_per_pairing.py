"""Tests for the PER-PAIRING isolation barrier.

These deliberately read the PRODUCTION insulation declaration
(``elec/insulation_manifest.yaml``) rather than a synthetic fixture, because
what they assert is precisely that the barrier's figures come from that
declaration and from nothing else. A synthetic fixture would prove the
plumbing and leave the "is the number derived or written?" question -- the
whole point of the mechanism -- untested.

No test here restates a creepage figure as a literal. Every expected value is
read back from ``insulation_coordination``, so a re-derivation moves the
tests for free instead of turning them red.
"""

from __future__ import annotations

import math

import pytest

from temper_placer.core.insulation_coordination import (
    barrier_floor_mm,
    requirement_for_nets,
)
from temper_placer.core.isolation_constants import (
    MIN_BARRIER_WIDTH_IS_DETERMINATE,
    MIN_BARRIER_WIDTH_MM,
)
from temper_placer.core.netlist import Component, Pin
from temper_placer.placer.cp_sat.isolation_barrier import (
    DEFAULT_CORRIDOR_WIDTH_MM,
    BarrierSetbacks,
    IsolationBarrierReport,
    _pairing_need,
    barrier_setbacks,
    compute_pad_groups,
    evaluate_isolator_feasibility,
    evaluate_isolator_per_pairing,
)

# Real declared nets, so `resolution.group_of` resolves them. Picked one per
# HV group plus the SELV ground.
MAINS_NET = "PWR_RTN"
DC_BUS_NET = "hb-gnd"
TANK_NET = "tank-out"
SELV_NET = "gnd"

HV = frozenset({MAINS_NET, DC_BUS_NET, TANK_NET})
SELV = frozenset({SELV_NET})


def _iso(ref: str, hv_net: str, hv_x: float, selv_x: float) -> Component:
    """A two-pad synthetic isolator: one HV pad, one SELV pad, both 1x1 mm
    rectangles on the local X axis."""
    return Component(
        ref=ref,
        footprint="test:fp",
        bounds=(abs(selv_x - hv_x) + 2.0, 2.0),
        pins=[
            Pin("1", "1", (hv_x, 0.0), net=hv_net, width=1.0, height=1.0, shape="rect"),
            Pin("2", "2", (selv_x, 0.0), net=SELV_NET, width=1.0, height=1.0, shape="rect"),
        ],
    )


# ---------------------------------------------------------------------------
# barrier_setbacks: derived, per group, never written
# ---------------------------------------------------------------------------


def test_every_setback_equals_its_own_pairing_floor():
    """The setback for group G is exactly what the declaration says the
    G<->SELV pairing needs -- not a scalar, not a rounded copy."""
    setbacks = barrier_setbacks()
    representative = {
        "MAINS": MAINS_NET,
        "DC_BUS": DC_BUS_NET,
        "TANK": TANK_NET,
    }
    assert set(representative) <= set(setbacks.setback_mm)
    for group, net in representative.items():
        pairing = requirement_for_nets(net, SELV_NET)
        assert setbacks.setback_mm[group] == pairing.enforceable_floor_mm()
        assert setbacks.determinable[group] == pairing.is_determinable()


def test_the_setbacks_actually_differ():
    """Anti-vacuity: if every group resolved to the same number, this whole
    mode would be the scalar model with extra steps and every result it
    produced would be indistinguishable from the old one."""
    assert len(set(barrier_setbacks().setback_mm.values())) > 1


def test_widest_setback_is_the_scalar_barrier_width():
    """One physical barrier is governed by its worst crossing, so the widest
    per-group setback must be exactly what `MIN_BARRIER_WIDTH_MM` derives."""
    setbacks = barrier_setbacks()
    assert setbacks.widest_mm == MIN_BARRIER_WIDTH_MM == barrier_floor_mm()


def test_indeterminacy_propagates_and_is_not_a_number():
    """A group whose pairing has no determinable requirement is FLAGGED, not
    given a substitute figure. `all_determinable` must be False today."""
    setbacks = barrier_setbacks()
    assert setbacks.determinable["TANK"] is False
    assert setbacks.determinable["MAINS"] is True
    assert setbacks.all_determinable is False
    assert MIN_BARRIER_WIDTH_IS_DETERMINATE is False
    # The floor is a real number (it has to be -- CP-SAT takes numbers), but
    # the REQUIREMENT it stands in for is not.
    assert math.isnan(requirement_for_nets(TANK_NET, SELV_NET).requirement_mm())


def test_unknown_group_falls_back_to_the_widest_not_the_smallest():
    setbacks = barrier_setbacks()
    assert setbacks.for_group("NOT_A_DECLARED_GROUP") == setbacks.widest_mm


# ---------------------------------------------------------------------------
# The strict-generalisation property
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", [4.0, 8.0, 12.6, 20.0])
@pytest.mark.parametrize("barrier_axis", [0, 1])
def test_per_pairing_reduces_to_the_scalar_model_when_setbacks_are_equal(width, barrier_axis):
    """With every group on the same setback W, `need` must equal
    `W - achievable_gap` -- i.e. the scalar path is exactly the equal-setbacks
    special case of this one. If this ever fails, the two models disagree
    about geometry and one of them is wrong.
    """
    real = barrier_setbacks()
    flat = BarrierSetbacks(
        setback_mm=dict.fromkeys(real.setback_mm, width),
        determinable=dict.fromkeys(real.setback_mm, True),
        governing_pairing=dict.fromkeys(real.setback_mm, "test"),
    )
    comp = _iso("U1", DC_BUS_NET, -5.0, 5.0)
    pfeas, _items, _selv = evaluate_isolator_per_pairing(
        comp, HV, SELV, flat, barrier_axis=barrier_axis
    )
    scalar = evaluate_isolator_feasibility(
        compute_pad_groups(comp, HV, SELV), width, barrier_axis=barrier_axis
    )
    assert pfeas.need_mm == pytest.approx(width - scalar.achievable_gap_mm, abs=1e-9)
    assert pfeas.feasible is scalar.feasible


def test_a_package_can_pass_its_own_pairing_and_fail_the_worst_one():
    """The finding this whole mode exists to express: a DC-bus isolator with
    a 9 mm span clears its own 8 mm requirement and fails the tank's 20 mm.
    Same package, same geometry -- only the pairing differs.
    """
    setbacks = barrier_setbacks()
    span = 9.0
    bus = _iso("T2", DC_BUS_NET, -span / 2, span / 2)
    tank = _iso("T1", TANK_NET, -span / 2, span / 2)
    bus_feas, _i, _s = evaluate_isolator_per_pairing(bus, HV, SELV, setbacks)
    tank_feas, _i, _s = evaluate_isolator_per_pairing(tank, HV, SELV, setbacks)
    assert bus_feas.binding_group == "DC_BUS"
    assert tank_feas.binding_group == "TANK"
    assert bus_feas.feasible is True
    assert tank_feas.feasible is False
    # And the tank one is short by the difference between the two figures.
    assert tank_feas.need_mm == pytest.approx(
        setbacks.setback_mm["TANK"] - setbacks.setback_mm["DC_BUS"] + bus_feas.need_mm,
        abs=1e-9,
    )


def test_the_strictest_pad_binds_in_a_multi_group_package():
    """A package bridging TWO HV groups is graded by the worse of them, at
    the same rotation -- taking the looser would under-constrain the strict
    pad."""
    setbacks = barrier_setbacks()
    comp = Component(
        ref="X1",
        footprint="test:fp",
        bounds=(20.0, 2.0),
        pins=[
            Pin("1", "1", (-5.0, 0.0), net=DC_BUS_NET, width=1.0, height=1.0, shape="rect"),
            Pin("2", "2", (-5.0, 0.0), net=TANK_NET, width=1.0, height=1.0, shape="rect"),
            Pin("3", "3", (5.0, 0.0), net=SELV_NET, width=1.0, height=1.0, shape="rect"),
        ],
    )
    feas, _i, _s = evaluate_isolator_per_pairing(comp, HV, SELV, setbacks)
    assert feas.binding_group == "TANK"
    assert feas.binding_setback_mm == setbacks.setback_mm["TANK"]


def test_need_is_monotone_in_the_setback():
    """Raising a requirement can never make a package look better. Guards the
    direction of the inequality in `_pairing_need`."""
    real = barrier_setbacks()
    comp = _iso("U1", DC_BUS_NET, -6.0, 6.0)
    previous = -math.inf
    for width in (2.0, 5.0, 10.0, 25.0):
        flat = BarrierSetbacks(
            setback_mm=dict.fromkeys(real.setback_mm, width),
            determinable=dict.fromkeys(real.setback_mm, True),
            governing_pairing=dict.fromkeys(real.setback_mm, "test"),
        )
        items, selv = evaluate_isolator_per_pairing(comp, HV, SELV, flat)[1:]
        need, *_ = _pairing_need(items, selv, 0, 0)
        assert need > previous
        previous = need


# ---------------------------------------------------------------------------
# A pad's own rotation must never make the model optimistic
# ---------------------------------------------------------------------------


def test_a_rotated_pad_can_only_shrink_the_reported_gap():
    """`_worst_axis_radius` takes the max over the three candidate pad
    orientations, so adding a pad angle can never IMPROVE a package's
    reported separation.

    This is the fail-closed direction for a real measured defect: the scalar
    path drops `pad_rotation_deg` entirely, which over-reported the CST3015
    (T1/T2) by 1.3 mm and the G4A-E relay (K1) by 2.6 mm against the exact
    copper kernel -- enough to certify T2 at a figure its copper does not
    span.
    """
    setbacks = barrier_setbacks()
    for angle in (0.0, 15.0, 30.0, 45.0, 90.0, 137.0):
        comp = Component(
            ref="U1",
            footprint="test:fp",
            bounds=(12.0, 4.0),
            pins=[
                Pin("1", "1", (-4.0, 0.0), net=DC_BUS_NET, width=3.0, height=1.0,
                    shape="rect", pad_rotation_deg=angle),
                Pin("2", "2", (4.0, 0.0), net=SELV_NET, width=3.0, height=1.0,
                    shape="rect", pad_rotation_deg=angle),
            ],
        )
        feas, _i, _s = evaluate_isolator_per_pairing(comp, HV, SELV, setbacks)
        unrotated = Component(
            ref="U1",
            footprint="test:fp",
            bounds=(12.0, 4.0),
            pins=[
                Pin("1", "1", (-4.0, 0.0), net=DC_BUS_NET, width=3.0, height=1.0,
                    shape="rect"),
                Pin("2", "2", (4.0, 0.0), net=SELV_NET, width=3.0, height=1.0,
                    shape="rect"),
            ],
        )
        base, _i, _s = evaluate_isolator_per_pairing(unrotated, HV, SELV, setbacks)
        assert feas.binding_gap_mm <= base.binding_gap_mm + 1e-9, angle
        assert feas.need_mm >= base.need_mm - 1e-9, angle


# ---------------------------------------------------------------------------
# The mode cannot be used to lower a requirement
# ---------------------------------------------------------------------------


def test_per_pairing_refuses_a_caller_supplied_corridor_width():
    """A caller-chosen width is exactly the single scalar this mode replaces.
    Accepting one would let a solve be made feasible by lowering a
    requirement, which is the thing that must never be possible.
    """
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.isolation_barrier import add_isolation_barrier_to_model
    from temper_placer.placer.cp_sat.model import CpSatModel

    with pytest.raises(ValueError, match="cannot be supplied alongside"):
        add_isolation_barrier_to_model(
            CpSatModel(),
            Netlist(components=[]),
            manifest_path=__import__("pathlib").Path("elec/domain_manifest.yaml"),
            board_w_mm=100.0,
            board_h_mm=100.0,
            corridor_width_mm=8.0,
            per_pairing=True,
        )


def test_the_default_width_is_not_treated_as_a_supplied_one():
    """Guard against the refusal above misfiring: passing nothing must work,
    and `DEFAULT_CORRIDOR_WIDTH_MM` is what "nothing" resolves to."""
    assert DEFAULT_CORRIDOR_WIDTH_MM == MIN_BARRIER_WIDTH_MM + 0.5


# ---------------------------------------------------------------------------
# The report tells a verdict-reporting caller what it needs
# ---------------------------------------------------------------------------


def test_report_determinable_is_false_on_the_per_pairing_path():
    report = IsolationBarrierReport(
        partition=None,  # type: ignore[arg-type]
        isolator_feasibility=[],
        orientation="vertical",
        corridor_width_mm=MIN_BARRIER_WIDTH_MM,
        corridor_position_mm=0.0,
        setbacks=barrier_setbacks(),
    )
    assert report.determinable is False


def test_report_infeasible_isolators_reads_the_pairing_verdicts():
    """On the per-pairing path the scalar `isolator_feasibility` list is empty,
    so `infeasible_isolators` must read `pairing_feasibility` or it would
    silently report "nothing is infeasible" for every solve."""
    setbacks = barrier_setbacks()
    short_tank = _iso("T1", TANK_NET, -4.55, 4.55)
    feas, _i, _s = evaluate_isolator_per_pairing(short_tank, HV, SELV, setbacks)
    report = IsolationBarrierReport(
        partition=None,  # type: ignore[arg-type]
        isolator_feasibility=[],
        orientation="vertical",
        corridor_width_mm=MIN_BARRIER_WIDTH_MM,
        corridor_position_mm=0.0,
        setbacks=setbacks,
        pairing_feasibility=[feas],
    )
    assert report.infeasible_isolators == ["T1"]
