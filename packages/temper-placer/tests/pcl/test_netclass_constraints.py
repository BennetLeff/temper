"""Tests for netclass-aware separation constraint generation.

Covers:
- Cross-class pairs generate SEPARATED constraints with correct clearance
- Same-class pairs produce no constraints
- Safety-critical pairs carry tier=HARD
- Constraint IDs are unique
"""

import math
from pathlib import Path

import pytest

from temper_placer.core.netclass_rules import load_netclass_rules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.netclass_constraints import (
    SAFETY_FACTOR,
    generate_netclass_separated_constraints,
)

YAML_PATH = (
    Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"
)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _make_component(ref: str, net_name: str) -> Component:
    """Create a component with one pin connected to *net_name*."""
    return Component(
        ref=ref,
        footprint="TEST",
        bounds=(10.0, 10.0),
        pins=[Pin(name="1", number="1", position=(0, 0), net=net_name)],
    )


def _make_netlist(
    *components: Component, net_names: list[str] | None = None
) -> "Netlist":
    """Build a Netlist with the given components and optional nets.

    Nets are created with pins that match the components' existing pin nets.
    """
    nets: list[Net] = []
    seen_nets: set[str] = set()
    for comp in components:
        for pin in comp.pins:
            if pin.net and pin.net not in seen_nets:
                seen_nets.add(pin.net)
    for net_name in sorted(seen_nets):
        pins_for_net: list[tuple[str, str]] = []
        for comp in components:
            for pin in comp.pins:
                if pin.net == net_name:
                    pins_for_net.append((comp.ref, pin.name))
        nets.append(Net(name=net_name, pins=pins_for_net))
    if net_names:
        for net_name in net_names:
            if net_name not in seen_nets:
                nets.append(Net(name=net_name, pins=[]))
    return Netlist(components=list(components), nets=nets)


# -------------------------------------------------------------------
# Fixture
# -------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules():
    """Load netclass_rules.yaml once per test module."""
    return load_netclass_rules(YAML_PATH)


# -------------------------------------------------------------------
# U3: Constraint generation
# -------------------------------------------------------------------


class TestCrossClassGeneration:
    """One HV component + two Signal components → 2 SEPARATED constraints."""

    def test_cross_class_pair_count(self, rules):
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),  # → HighVoltage
            _make_component("R1", "SIGNAL_A"),      # → Signal
            _make_component("R2", "SIGNAL_B"),      # → Signal
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        assert len(result) == 2

    def test_cross_class_clearance_value(self, rules):
        """Each HV↔Signal constraint carries 6.0mm × √2 clearance."""
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("R1", "SIGNAL_A"),
            _make_component("R2", "SIGNAL_B"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        expected = pytest.approx(6.0 * SAFETY_FACTOR)
        for c in result:
            assert c.min_distance_mm == expected

    def test_constraint_tier_is_hard(self, rules):
        """All auto-generated cross-class constraints are HARD."""
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("R1", "SIGNAL_A"),
            _make_component("R2", "SIGNAL_B"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        for c in result:
            assert c.tier == ConstraintTier.HARD


class TestSameClassNoGeneration:
    """Same-class components produce zero SEPARATED constraints."""

    def test_all_signal_no_constraints(self, rules):
        comps = [
            _make_component("R1", "SIGNAL_A"),
            _make_component("R2", "SIGNAL_B"),
            _make_component("R3", "SIGNAL_C"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        assert len(result) == 0

    def test_all_hv_no_constraints(self, rules):
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("HV_RES", "DC_BUS-"),
            _make_component("HV_IND", "SW_NODE"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        assert len(result) == 0


class TestUniqueIds:
    """Constraint IDs are unique and follow the naming convention."""

    def test_ids_are_unique(self, rules):
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("R1", "SIGNAL_A"),
            _make_component("R2", "SIGNAL_B"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        ids = [c.id for c in result]
        assert len(ids) == len(set(ids))

    def test_id_format(self, rules):
        """IDs follow netclass_sep_{class_a}_{class_b}_{ref_a}_{ref_b}."""
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("R1", "SIGNAL_A"),
        ]
        netlist = _make_netlist(*comps)
        result = generate_netclass_separated_constraints(
            netlist, comps, rules,
        )
        assert len(result) == 1
        cid = result[0].id
        assert cid.startswith("netclass_sep_")
        assert "HV_CAP" in cid
        assert "R1" in cid
        assert "HighVoltage" in cid or "Signal" in cid


class TestExistingConstraintDedup:
    """Pairs with user-defined SeparatedConstraint are not duplicated."""

    def test_existing_pair_is_skipped(self, rules):
        comps = [
            _make_component("HV_CAP", "DC_BUS+"),
            _make_component("R1", "SIGNAL_A"),
            _make_component("R2", "SIGNAL_B"),
        ]
        netlist = _make_netlist(*comps)
        existing = [
            SeparatedConstraint(
                a="HV_CAP",
                b="R1",
                min_distance_mm=6.0,
                tier=ConstraintTier.HARD,
                because="Manual HV isolation constraint",
            ),
        ]
        result = generate_netclass_separated_constraints(
            netlist, comps, rules, existing_constraints=existing,
        )
        ids = [c.id for c in result]
        refs_in_result = set()
        for c in result:
            refs_in_result.add((min(c.a, c.b), max(c.a, c.b)))
        assert ("HV_CAP", "R1") not in refs_in_result
        assert ("HV_CAP", "R2") in refs_in_result
