"""Tests for the HV<->HV FUNCTIONAL creepage family.

Same discipline as ``test_isolation_barrier_per_pairing.py``, and for the same
reason: these read the PRODUCTION insulation declaration
(``elec/insulation_manifest.yaml``) rather than a synthetic fixture, because
what they assert is precisely that the figures come from that declaration and
from nothing else. A synthetic fixture would prove the plumbing and leave the
"is the number derived or written?" question -- the whole point -- untested.

**No test here restates a creepage figure as a literal.** Every expected value
is read back through ``insulation_coordination``, so a re-derivation moves the
tests for free instead of turning them red. The one place a bare number
appears is ``FREQUENCY_SCOPE_CEILING_HZ``, and it is read from the Rust
constant, not typed.
"""

from __future__ import annotations

import math

import pytest
import temper_design_bundle_python as _tdb

from temper_placer.core.insulation_coordination import (
    InsulationDeclarationError,
    _resolution,
    requirement_for_nets,
)
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.placer.cp_sat.hv_functional_creepage import (
    FunctionalSeparation,
    _pair_requirement,
    component_hv_nets,
    generate_hv_functional_constraints,
    hv_functional_separations,
    intra_package_shortfalls,
    undeclared_hv_nets,
)

# Real declared nets, one per HV group, so the resolver resolves them.
MAINS_A, MAINS_B = "ac_l", "PWR_RTN"
BUS_A, BUS_B = "+170V_BUS", "DC_BUS_RTN"
SWITCHING = "SW_NODE"
TANK = "tank-out"
SELV = "gnd"


def _comp(ref: str, nets: list[str]) -> Component:
    return Component(
        ref=ref,
        footprint="test:fp",
        bounds=(2.0 * len(nets), 2.0),
        pins=[
            Pin(str(i + 1), str(i + 1), (2.0 * i, 0.0), net=n,
                width=1.0, height=1.0, shape="rect")
            for i, n in enumerate(nets)
        ],
        initial_position=(0.0, 0.0),
        initial_rotation_quadrant=0,
    )


def _netlist(*comps: Component) -> Netlist:
    return Netlist(components=list(comps), nets={})


class TestDerivedNotWritten:
    def test_every_hv_hv_pairing_is_present_and_functional(self):
        """The family covers every same-domain HV pairing the declaration
        carries, and every one of them derives to FUNCTIONAL / Table 18."""
        seps = hv_functional_separations()
        expected = {
            p.key()
            for p in _resolution().pairings()
            if not p.crosses_barrier() and p.domain_a() == "HV" and p.domain_b() == "HV"
        }
        assert set(seps) == expected
        assert expected, "anti-vacuity: the declaration must carry HV self-pairings"
        for key, sep in seps.items():
            pairing = _resolution().pairing(*key.split("<->"))
            assert pairing.insulation() == "functional"
            assert sep.table == pairing.table() == "Table 18"

    def test_no_figure_is_written_here(self):
        """Each floor equals the resolver's, to the bit. Nothing in the module
        adjusts, rounds, floors or doubles it."""
        for key, sep in hv_functional_separations().items():
            pairing = _resolution().pairing(*key.split("<->"))
            assert sep.floor_mm == pairing.enforceable_floor_mm()
            assert sep.determinable == pairing.is_determinable()
            assert sep.voltage_range == pairing.voltage_range()
            assert sep.working_voltage_vrms == pairing.working_voltage_vrms()

    def test_functional_is_never_the_doubled_reinforced_figure(self):
        """cl. 29.2.3's x2 is a REINFORCED provision. A functional pairing
        must not carry it, which is the whole reason the bus rail-to-rail
        figure is not the 12.6 mm row-iv fossil."""
        for key, sep in hv_functional_separations().items():
            # frequency 0 so the reinforced comparand is a determinate number
            # even for the 47 kHz pairings: what is being compared here is the
            # TABLE ARITHMETIC, not either pairing's determinability.
            reinforced_mm = _tdb.insulation_required_creepage(
                "reinforced", sep.working_voltage_vrms, 0.0, 3
            )[1]
            functional_mm = _tdb.insulation_required_creepage(
                "functional", sep.working_voltage_vrms, 0.0, 3
            )[1]
            assert sep.floor_mm == functional_mm
            assert sep.floor_mm < reinforced_mm, (
                f"{key}: functional {sep.floor_mm} is not below the reinforced "
                f"figure {reinforced_mm} at the same voltage -- the x2 has leaked in"
            )

    def test_table_18_row_is_selected_by_voltage_not_by_index(self):
        """Table 18's rows are offset by one from Table 17's. Assert the row
        LABEL the resolver reports actually brackets the declared working
        voltage, so a cross-table index slip cannot pass unnoticed."""
        for key, sep in hv_functional_separations().items():
            rng = sep.voltage_range
            v = sep.working_voltage_vrms
            if rng.startswith("<="):
                assert v <= float(rng[2:]), f"{key}: {v} outside {rng}"
            else:
                lo, hi = rng.lstrip(">").split("-")
                assert float(lo) < v <= float(hi), f"{key}: {v} outside {rng}"


class TestFrequencyIndeterminacy:
    def test_every_47khz_pairing_is_indeterminate_with_a_floor(self):
        """The failure mode to avoid: a 47 kHz HV<->HV pair reported as a
        determinate 5.0 mm because Table 18 has a row at 340 V."""
        ceiling = _tdb.insulation_frequency_scope_ceiling_hz()
        seen_indeterminate = False
        for key, sep in hv_functional_separations().items():
            pairing = _resolution().pairing(*key.split("<->"))
            above = pairing.frequency_hz() > ceiling
            assert sep.determinable is not above
            if above:
                seen_indeterminate = True
                assert math.isnan(sep.requirement_mm), (
                    f"{key} is above the {ceiling} Hz scope ceiling; its "
                    "requirement must be nan, not a number"
                )
                assert sep.floor_mm > 0.0, f"{key}: a floor is still owed"
        assert seen_indeterminate, (
            "anti-vacuity: this board's SWITCHING and TANK groups run at "
            "47 kHz, so at least one HV<->HV pairing must be indeterminate"
        )

    def test_an_indeterminate_pairing_never_grades_pass(self):
        """No distance, however large, turns an out-of-scope pairing into a
        pass. This is the property that keeps the family fail-closed."""
        for key in hv_functional_separations():
            pairing = _resolution().pairing(*key.split("<->"))
            if pairing.is_determinable():
                continue
            for gap in (0.0, pairing.enforceable_floor_mm(), 1e6):
                assert pairing.grade(gap) != "PASS"

    def test_component_pair_indeterminacy_is_not_diluted(self):
        """One indeterminate member makes the whole component pair
        indeterminate, even when a determinate member sets the figure."""
        a = _comp("A", [BUS_A, SWITCHING])
        b = _comp("B", [BUS_B])
        req = _pair_requirement("A", sorted({BUS_A, SWITCHING}), "B", [BUS_B])
        assert req is not None
        assert req.determinable is False
        assert math.isnan(req.requirement_mm)
        assert req.floor_mm == max(
            requirement_for_nets(BUS_A, BUS_B).enforceable_floor_mm(),
            requirement_for_nets(SWITCHING, BUS_B).enforceable_floor_mm(),
        )
        assert {a.ref, b.ref} == {"A", "B"}

    def test_report_determinable_is_false_on_this_board(self):
        """Named rather than implied: with SWITCHING and TANK at 47 kHz, the
        family as a whole cannot certify anything."""
        seps = hv_functional_separations()
        assert not all(s.determinable for s in seps.values())


class TestReduction:
    def test_pair_requirement_is_the_max_over_member_pairings(self):
        req = _pair_requirement("A", [BUS_A, MAINS_A], "B", [TANK])
        assert req is not None
        assert req.floor_mm == max(
            requirement_for_nets(BUS_A, TANK).enforceable_floor_mm(),
            requirement_for_nets(MAINS_A, TANK).enforceable_floor_mm(),
        )

    def test_identical_nets_contribute_no_requirement(self):
        """Two pads at the same potential have no insulation to dimension."""
        assert _pair_requirement("A", [BUS_A], "B", [BUS_A]) is None

    def test_conservative_never_below_any_member(self):
        for nets_a in ([MAINS_A], [BUS_A], [TANK], [BUS_A, TANK]):
            for nets_b in ([MAINS_B], [BUS_B], [SWITCHING]):
                req = _pair_requirement("A", nets_a, "B", nets_b)
                if req is None:
                    continue
                for na in nets_a:
                    for nb in nets_b:
                        if na == nb:
                            continue
                        assert req.floor_mm >= requirement_for_nets(
                            na, nb
                        ).enforceable_floor_mm()


class TestEncoding:
    def test_constraints_carry_the_derived_figure_and_no_self_pairs(self):
        nl = _netlist(_comp("A", [BUS_A]), _comp("B", [BUS_B]), _comp("C", [SELV]))
        cons, report = generate_hv_functional_constraints(nl)
        assert [c.id for c in cons] == ["hv_functional_A_B"]
        assert cons[0].min_distance_mm == (
            requirement_for_nets(BUS_A, BUS_B).enforceable_floor_mm()
        )
        assert report.pair_requirements[0].governing_pairing == "DC_BUS<->DC_BUS"

    def test_a_selv_only_component_is_not_in_this_family(self):
        """The barrier family owns HV<->SELV. This one must not double-charge
        it, nor silently pull a SELV net into an HV pairing."""
        nl = _netlist(_comp("A", [BUS_A]), _comp("S", [SELV]))
        cons, _ = generate_hv_functional_constraints(nl)
        assert cons == []

    def test_undeclared_hv_class_nets_are_reported_not_defaulted(self):
        nl = _netlist(_comp("A", [BUS_A]), _comp("X", ["not.a.declared.net"]))
        cons, report = generate_hv_functional_constraints(nl)
        # No constraint invents a figure for the undeclared net...
        assert all("X" not in (c.a, c.b) for c in cons)
        # ...and asking for one raises rather than defaulting.
        with pytest.raises(InsulationDeclarationError):
            requirement_for_nets(BUS_A, "not.a.declared.net")
        assert isinstance(report.undeclared, dict)

    def test_the_real_board_has_an_undeclared_highvoltage_family_net(self):
        """Anti-vacuity for the check above: the gap is real today."""
        from pathlib import Path

        from temper_placer.io.kicad_parser import parse_kicad_pcb

        repo = Path(__file__).resolve().parents[5]
        parsed = parse_kicad_pcb(repo / "pcb/temper.kicad_pcb")
        _cons, report = generate_hv_functional_constraints(parsed.netlist)
        assert report.undeclared, (
            "expected the four safety.ovp.* nets to be HighVoltage-class and "
            "undeclared in elec/insulation_manifest.yaml"
        )
        assert all(n.startswith("safety.ovp.") for n in report.undeclared)


class TestIntraPackage:
    def test_intra_package_shortfalls_are_reported_never_encoded(self):
        """Two pads of one footprint move as a rigid unit; no
        SeparatedConstraint between distinct refs can address them, and none
        is emitted."""
        from pathlib import Path

        from temper_placer.io.kicad_parser import parse_kicad_pcb

        repo = Path(__file__).resolve().parents[5]
        parsed = parse_kicad_pcb(repo / "pcb/temper.kicad_pcb")
        cons, report = generate_hv_functional_constraints(parsed.netlist)
        assert report.intra_package, (
            "anti-vacuity: this board has HV<->HV pad pairs inside single "
            "footprints that are below their own functional figure"
        )
        assert all(c.a != c.b for c in cons)
        for shortfall in report.intra_package:
            assert shortfall.gap_mm < shortfall.floor_mm
            assert shortfall.short_by_mm > 0.0

    def test_intra_package_measurement_is_placement_invariant(self):
        """The defining property: rotating a footprint rotates every pad and
        every pad position together, so an intra-package gap cannot move."""
        nl = _netlist(_comp("A", [BUS_A, BUS_B]))
        base = intra_package_shortfalls(nl)
        for quad in (1, 2, 3):
            rotated = _netlist(
                Component(
                    ref="A",
                    footprint="test:fp",
                    bounds=nl.components[0].bounds,
                    pins=nl.components[0].pins,
                    initial_position=(37.5, -11.25),
                    initial_rotation_quadrant=quad,
                )
            )
            moved = intra_package_shortfalls(rotated)
            assert [round(s.gap_mm, 12) for s in moved] == [
                round(s.gap_mm, 12) for s in base
            ]


class TestAntiVacuity:
    def test_component_hv_nets_reads_the_declaration_not_a_net_class(self):
        nl = _netlist(_comp("A", [BUS_A, SELV]), _comp("S", [SELV]))
        assert component_hv_nets(nl) == {"A": [BUS_A]}

    def test_separations_dataclass_reports_nan_not_a_number(self):
        sep = FunctionalSeparation(
            pairing_key="X<->Y",
            group_a="X",
            group_b="Y",
            working_voltage_vrms=340.0,
            table="Table 18",
            voltage_range=">250-400",
            floor_mm=5.0,
            determinable=False,
        )
        assert math.isnan(sep.requirement_mm)
        assert sep.floor_mm == 5.0

    def test_undeclared_hv_nets_ignores_non_hv_classes(self):
        nl = _netlist(_comp("A", ["some.signal"]))
        assert undeclared_hv_nets(nl, {"some.signal": "Signal"}) == {}
        assert undeclared_hv_nets(nl, {"some.signal": "HighVoltage"}) == {
            "some.signal": ["A"]
        }
