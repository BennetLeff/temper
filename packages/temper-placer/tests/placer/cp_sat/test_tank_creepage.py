"""Tank-node functional creepage placement constraint.

Three groups:

1. ``TestGroupMembership`` -- the generator classifies the real board's
   components correctly (falsifier-driven: wrong membership means the
   constraint protects the wrong pairs, or none at all).
2. ``TestCheckAgainstRealBoard`` -- the pure-Python box checker, run
   directly against the committed board's real positions, finds real
   violations (and is honest about the one it cannot find -- the headline
   pad-to-track pair, which is not a component-pair violation at all).
3. ``TestOrToolsEncoding`` -- ``add_tank_creepage_to_model`` actually posts
   a binding constraint onto a real ``CpSatModel`` (pin-and-solve, not just
   "did it raise").

Plus the four groups added 2026-08-15 (the structural-mask fix, task from
the 2026-08-15 handoff -- see
``docs/evidence/2026-08-15-safety-assertion-audit-resumed.md`` Part 0 for
the audit that motivated them):

4. ``TestTankBusNetPairs`` -- the tank<->DC-bus-rail pair is now
   enumerable as a NET pair (``tank_bus_net_pairs``). The bus rails have no
   refdes, so they could never appear in the component-pair enumeration;
   this class pins the net-pair list and a falsifier asserting the bus net
   is not a component ref.
5. ``TestTankBusCopperMetric`` -- the tank<->bus gap is now measured at
   copper level: exact pad-to-pad distance (``pad_pair_distance``, the same
   kernel the REQ-SAFE-01 validator uses) plus pour containment (C26's and
   R30's tank pads sit INSIDE the ``DC_BUS_RTN`` pours on both layers, so
   the pour -- not the pad placement -- bounds the copper gap).
6. ``TestTankBusEnforcement`` -- the SHORTFALL CATCH. Asserts the
   figures the design is BUILT to (netclass clearance 2.0mm, DRU-emitted
   tank creepage 6.3mm, SSOT declared creepage 6.0/6.3mm) against the
   governing requirement for the pair (Table 18 functional creepage,
   >500-800V band: 6.3mm PD2 / 10.0mm PD3, PD3 governing as built).
   These are EXPECTED RED today: the enforced figures are 3.2x-5.0x short
   (docs/evidence/2026-08-12-hv-hv-creepage-determination.md Sec 4.3).
   A labelled red beats a green that means nothing -- they flip green only
   when the SafetyValue migration raises the enforced values.
7. ``TestWireFormat`` -- Pumpkin JSON wire-format emission.
"""

from __future__ import annotations

from pathlib import Path

from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.model import CpSatModel
from temper_placer.placer.cp_sat.tank_creepage import (
    DEFAULT_TANK_CREEPAGE_MM,
    HV_TANK_CREEPAGE_PD2_MM,
    HV_TANK_CREEPAGE_PD3_MM,
    TANK_BUS_RAIL_NETS,
    TANK_NODE_NET,
    add_tank_creepage_to_model,
    check_tank_bus_creepage,
    check_tank_creepage_separation,
    enforced_tank_bus_clearance_mm,
    find_tank_self_pairs,
    other_hv_refs,
    tank_bus_net_pairs,
    tank_bus_pad_gap_mm,
    tank_bus_pour_contained_pads,
    tank_creepage_pairs,
    tank_creepage_wire_constraints,
    tank_node_refs,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def _real_netlist():
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    assert REAL_BOARD.exists(), f"board not found: {REAL_BOARD}"
    return parse_kicad_pcb(REAL_BOARD, normalize=False).netlist


def _real_zones():
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    assert REAL_BOARD.exists(), f"board not found: {REAL_BOARD}"
    return parse_kicad_pcb_v6(REAL_BOARD).zones


def _dru_namespace():
    """Constants of scripts/generate_kicad_dru.py, loaded WITHOUT importing
    the script into the test process (runpy runs it in a throwaway
    namespace; its ``main()`` is guarded, so this is side-effect-free). The
    DRU generator is the kicad-cli enforcement path: the figures it emits
    are the ones the board is actually checked against."""
    import runpy

    return runpy.run_path(str(REPO_ROOT / "scripts" / "generate_kicad_dru.py"))


class TestConstants:
    def test_designs_against_pd3_by_default(self):
        assert DEFAULT_TANK_CREEPAGE_MM == HV_TANK_CREEPAGE_PD3_MM == 10.0

    def test_pd2_is_the_looser_figure(self):
        assert HV_TANK_CREEPAGE_PD2_MM == 6.3
        assert HV_TANK_CREEPAGE_PD2_MM < HV_TANK_CREEPAGE_PD3_MM


class TestGroupMembership:
    """Falsifier: wrong group membership means the constraint protects the
    wrong pairs (or is vacuous). Pinned against the real, committed board
    so a board edit that changes membership fails this loudly rather than
    silently narrowing coverage."""

    def test_tank_refs_are_exactly_the_four_measured_components(self):
        netlist = _real_netlist()
        refs = tank_node_refs(netlist)
        assert refs == frozenset({"C25", "C26", "C27", "R30"}), (
            f"tank.c_tank1-p2 membership changed: {sorted(refs)} -- re-derive "
            f"this test against the new board before editing the expectation"
        )

    def test_other_hv_refs_excludes_tank_refs(self):
        netlist = _real_netlist()
        tank_refs = tank_node_refs(netlist)
        other = other_hv_refs(netlist, tank_refs)
        assert not (other & tank_refs), "tank refs leaked into the other-HV group"
        # Not vacuous: real HV components (the discharge relay net) present.
        #
        # R12 was asserted here from 2026-08-12 (ad8498f7d) until 2026-08-18 and
        # was wrong from the day it was written -- this assertion has never
        # passed. R12 is `discharge.r_gate` (pcb/temper.kicad_pcb Sheetpath;
        # elec/src/modules.ato `ctrl ~ r_gate.p1` / `r_gate.p2 ~ q_dis_drv.G`):
        # the gate resistor between the MCU GPIO and a gnd-referenced
        # logic-level FET. Its only two nets are DISCHARGE_CTRL and
        # discharge.q_dis_drv-g. DISCHARGE_CTRL is *affirmatively declared SELV*
        # -- elec/domain_manifest.yaml lists it under `SELV: nets:` (:457) and
        # in the SELV-only board_interface (:76) -- and neither net has ever
        # appeared in TEMPER_NET_ASSIGNMENTS in the repo's history
        # (`git log -S` on design_rules.py returns zero commits for both).
        # R12 is therefore correctly absent from the HV group; excluding a SELV
        # gate resistor from HV<->HV functional creepage is right, not a gap.
        #
        # R7 replaces it at equal strength: R7 is on discharge.k_dis1-nc, which
        # IS HighVoltageSignal, so it is genuinely HV *and* actually on the
        # discharge relay net this comment names -- which R12 (the discharge
        # *control* net) never was. Verified against the committed board
        # 2026-08-18: Group B = 45 refs, K2/R7/R19 all present.
        expected_hv = {"K2", "R7", "R19"}
        assert expected_hv <= other, (
            f"expected HV refs missing from the other-HV group: "
            f"{sorted(expected_hv - other)} -- re-derive against the board "
            f"before editing this expectation"
        )

    def test_pair_count_matches_measured_board(self):
        netlist = _real_netlist()
        pairs = tank_creepage_pairs(netlist)
        # Re-derived 2026-08-15: 4 tank refs x 45 other-HV refs = 180. The
        # pin moved from 4 * 42 when the 2026-08-13 HighVoltageSignal
        # carve-out grew Group B by three (module docstring,
        # "_HV_EQUIVALENT_CLASSES" comment) -- same pair population rule,
        # larger membership. 42 was stale since that day; the test's
        # count-pin failure on main predates this change.
        #
        # Corrected 2026-08-18: this comment previously named the added refs as
        # "K2/R7/R12/R19/R23/U8". That list of six never reconciled with its own
        # +3 arithmetic, and two of the six are not in Group B at all -- measured
        # against the committed board, R12 (SELV, see the note in
        # test_other_hv_refs_excludes_tank_refs) and U8 (`rtd_pan.adc`, the RTD
        # ADC: RTD_*/gnd/vcc/sclk/sdi/sdo, entirely SELV) are both absent, while
        # K2/R7/R19/R23 are present. The same wrong six-ref list appears in
        # docs/evidence/2026-08-15-tank-bus-creepage-test-structural-fix.md:86.
        # The 45 count itself is measured and correct; only the prose was wrong.
        # RE-DERIVED 2026-08-24: 4 tank refs x 46 other-HV refs = 184.
        # Decomposed rather than bumped, because two independent things
        # moved in opposite directions:
        #
        #   classification  +2  R22 joins via `input` (#1360, 0ee4a901b) and
        #                       R23 via `hb-gnd` (f9d10f196) -- both nets
        #                       were classified HighVoltage/HighVoltageSignal
        #                       after this pin was derived. Measured by
        #                       re-running tank_creepage_pairs against the
        #                       PRE-#1360/#1462 net assignments on today's
        #                       netlist: 44 refs, and the diff vs today is
        #                       exactly {R22, R23} added, none removed.
        #   netlist         -1  45 (derived 2026-08-15, against that day's
        #                       netlist) vs 44 under the same old
        #                       classification today -- one Group B member
        #                       has left the board since.
        #
        # Net 45 -> 46. Tank refs are unchanged at 4 (C25, C26, C27, R30).
        assert len(pairs) == 4 * 46, (
            f"got {len(pairs)} pairs -- re-derive against the new board if "
            f"this is an intentional board change"
        )

    def test_self_pairs_are_all_four_tank_refs(self):
        """C25/C26/C27 also carry SW_NODE; R30 also carries tank-out.
        Every tank ref straddles a second HighVoltage net within its own
        footprint -- none of these are protected by any placement
        constraint (see module docstring)."""
        netlist = _real_netlist()
        assert find_tank_self_pairs(netlist) == ["C25", "C26", "C27", "R30"]


class TestCheckAgainstRealBoard:
    """The pure-Python checker (no CP-SAT) against the real, current
    placement."""

    def _positions_rotations_sizes(self, netlist):
        positions = {c.ref: tuple(c.initial_position) for c in netlist.components}
        rotations = {c.ref: int(c.initial_rotation_quadrant or 0) for c in netlist.components}
        sizes = {c.ref: tuple(c.bounds) for c in netlist.components}
        return positions, rotations, sizes

    def test_rejects_the_committed_placement_at_pd3(self):
        netlist = _real_netlist()
        pairs = tank_creepage_pairs(netlist)
        positions, rotations, sizes = self._positions_rotations_sizes(netlist)
        violations = check_tank_creepage_separation(
            positions, rotations, sizes, pairs, margin_mm=HV_TANK_CREEPAGE_PD3_MM
        )
        assert len(violations) >= 1, (
            "Falsifier fired: the checker found nothing wrong with the "
            "committed placement -- it is inspecting nothing."
        )
        # The worst offenders: two component pairs nearly touching.
        worst = min(violations, key=lambda pv: pv[1])
        assert worst[1] < 1.0, f"expected a sub-1mm offender, got {worst}"

    def test_c25_k2_pair_is_NOT_rejected_at_component_granularity(self):
        """Honesty check for the module's own documented limitation: the
        DRC's headline violation (C25 pad 2 vs a discharge.k_dis1-nc
        TRACK, 2.2656mm) is a pad-to-routed-copper distance, not a
        pad-to-pad or component-to-component one. K2 is the nearest
        discharge.k_dis1-nc-owning component to C25, and its box is
        already >= the PD3 margin away -- this constraint has zero
        visibility into the routed trace that actually violates creepage.
        If this assertion ever starts failing because the gap shrank below
        10mm, that's still consistent with the module's claims; if it
        fails because the pair is missing from `other_hv_refs` entirely,
        that's a real coverage regression.
        """
        netlist = _real_netlist()
        by_ref = {c.ref: c for c in netlist.components}
        assert "K2" in other_hv_refs(netlist, tank_node_refs(netlist))
        positions, rotations, sizes = self._positions_rotations_sizes(netlist)
        pairs = [p for p in tank_creepage_pairs(netlist) if p.tank_ref == "C25" and p.other_ref == "K2"]
        assert len(pairs) == 1
        violations = check_tank_creepage_separation(
            positions, rotations, sizes, pairs, margin_mm=HV_TANK_CREEPAGE_PD3_MM
        )
        assert violations == [], (
            "C25<->K2 box gap now under 10mm -- module docstring's "
            "quantified proxy-gap example needs updating"
        )
        del by_ref  # not needed further; kept for readability above


class TestTankBusNetPairs:
    """The tank<->DC-bus-rail pair, enumerated as a NET pair.

    Structural-mask fix (2026-08-15): ``tank_creepage_pairs`` enumerates
    (tank-ref x other-HV-*component*-ref) pairs only; the bus rails
    (``+170V_BUS``, ``DC_BUS_RTN``) are nets with no refdes, so the pair
    the evidence doc measured short (2.0mm provided vs 6.3/10.0mm
    required) could never be checked. ``tank_bus_net_pairs`` closes that.
    """

    def test_bus_pairs_are_enumerated_as_nets(self):
        netlist = _real_netlist()
        pairs = tank_bus_net_pairs(netlist)
        got = [(p.tank_ref, p.bus_net) for p in pairs]
        # 4 tank refs x the 2 DC-bus rails present on this board
        # (DC_BUS+/DC_BUS- are declared in TEMPER_NET_ASSIGNMENTS but not
        # present in pcb/temper.kicad_pcb's netlist).
        assert got == [
            ("C25", "+170V_BUS"),
            ("C25", "DC_BUS_RTN"),
            ("C26", "+170V_BUS"),
            ("C26", "DC_BUS_RTN"),
            ("C27", "+170V_BUS"),
            ("C27", "DC_BUS_RTN"),
            ("R30", "+170V_BUS"),
            ("R30", "DC_BUS_RTN"),
        ], f"tank<->bus net-pair enumeration changed: {got}"

    def test_bus_net_is_not_a_component_ref(self):
        """Falsifier for the exact structural defect: the pair's ``bus_net``
        must never collide with a component refdes, or the net pair could
        be silently absorbed into (or shadowed by) the component-level
        enumeration."""
        netlist = _real_netlist()
        refs = {c.ref for c in netlist.components}
        for p in tank_bus_net_pairs(netlist):
            assert p.bus_net not in refs, f"{p.bus_net} is a component ref!"
        assert not (TANK_BUS_RAIL_NETS & refs), "a bus rail collides with a refdes"

    def test_bus_pairs_are_absent_from_component_pair_enumeration(self):
        """The component-level enumeration must not contain the bus rails in
        ANY position (tank_ref or other_ref): a net has no box, and a
        ``TankCreepagePair`` naming one would be a vacuous constraint."""
        netlist = _real_netlist()
        for p in tank_creepage_pairs(netlist):
            assert p.tank_ref not in TANK_BUS_RAIL_NETS
            assert p.other_ref not in TANK_BUS_RAIL_NETS


class TestTankBusCopperMetric:
    """The tank<->bus gap, measured at copper level on the committed board.

    Two honest quantities (module docstring): exact pad-to-pad copper
    distance, and pour containment -- when a tank pad lies inside a
    bus-rail zone outline on a layer it occupies, the pour (not the pad
    placement) bounds the copper gap, to the design's enforced clearance.
    """

    def test_exact_pad_gap_is_finite_for_every_pair(self):
        netlist = _real_netlist()
        for pair in tank_bus_net_pairs(netlist):
            gap = tank_bus_pad_gap_mm(netlist, pair)
            assert gap != float("inf"), f"no copper measured for {pair}"
            assert gap > 0.0, f"tank<->bus pad overlap for {pair} -- a SHORT"

    def test_pour_contained_tank_pads_are_detected(self):
        """C26 pad 2 and R30 pad 1 sit INSIDE the DC_BUS_RTN pours on both
        faces (both THT, layer=all). This is the evidence doc's '2.0mm
        provided' made physical on the committed board: the pour bounds the
        copper gap to the design's enforced clearance. Re-derive if the
        board moves the pads out of the pour (that is the fix, and the
        enforcement tests below will still be red until the VALUES move)."""
        netlist = _real_netlist()
        zones = _real_zones()
        contained = {
            pair.tank_ref: tank_bus_pour_contained_pads(netlist, pair, zones)
            for pair in tank_bus_net_pairs(netlist)
            if pair.bus_net == "DC_BUS_RTN"
        }
        # RE-DERIVED 2026-08-24, which is what this test's own docstring
        # asks for: the board DID move the pads out of the pour. C26.2 and
        # R30.1 were inside the DC_BUS_RTN outlines when this was pinned on
        # 2026-08-15; #1312 ("regenerate the board's copper", 23b5daf8d,
        # 2026-08-17) took DC_BUS_RTN from 2 zones to 12, and no tank pad
        # lies inside a bus-rail outline any more.
        #
        # An all-empty expectation is weak on its own, so it is NOT the
        # evidence that the gap is now bounded by pad placement -- the
        # sibling test_pour_bounded_pairs_violate_pd3 carries that, and it
        # is not vacuous: it still evaluates all 8 tank<->bus net pairs and
        # measures a real minimum gap of 15.456mm. The enforcement tests
        # below stay red regardless, because the pads leaving the pour
        # changes WHAT bounds the gap, not the enforced FIGURES.
        #
        # Note the zone outlines are read, not fills: this board carries 151
        # zones and ZERO filled_polygon entries (deliberately -- #1388 keeps
        # the unfilled ceiling), and has for all 12 board-changing commits
        # in this window, so the 2026-08-15 pin was measured against
        # outlines too. The change is geometric, not a fill artefact.
        assert contained == {
            "C25": [],
            "C26": [],
            "C27": [],
            "R30": [],
        }, f"pour containment changed: {contained}"

    def test_pour_bounded_pairs_violate_pd3(self):
        """The copper checker reports the pour-bounded pairs as violations
        at the PD3 margin: their copper gap is bounded by the enforced
        clearance (2.0mm), which is under the 10.0mm requirement. This is
        the shortfall, caught on the committed board's own geometry."""
        netlist = _real_netlist()
        zones = _real_zones()
        pairs = tank_bus_net_pairs(netlist)
        violations = check_tank_bus_creepage(
            netlist, pairs, margin_mm=HV_TANK_CREEPAGE_PD3_MM, zones=zones
        )
        by_pair = {(p.tank_ref, p.bus_net): (gap, kind) for p, gap, kind in violations}
        # RE-DERIVED 2026-08-24: the pour-bounded shortfall is GONE, and
        # this is the substantive finding of the whole class rather than
        # bookkeeping. When this was pinned on 2026-08-15 the C26 and R30
        # tank pads sat inside the DC_BUS_RTN outlines, so the pour bounded
        # their copper gap to the enforced 2.0mm -- a 5x shortfall against
        # the 10.0mm PD3 requirement. #1312's copper regeneration
        # (23b5daf8d) took DC_BUS_RTN from 2 zones to 12 and no tank pad is
        # inside a bus-rail outline any more, so every pair is now bounded
        # by pad-to-pad distance instead.
        #
        # NOT VACUOUS, checked explicitly rather than assumed from an empty
        # result: the checker still enumerates all 8 tank<->bus net pairs
        # and computes a real distance for each. Measured on this board,
        # smallest first:
        #
        #     C27<->DC_BUS_RTN  15.456mm      C25<->+170V_BUS   54.192mm
        #     C27<->+170V_BUS   22.929mm      R30<->DC_BUS_RTN  57.311mm
        #     R30<->+170V_BUS   24.644mm      C26<->DC_BUS_RTN  63.181mm
        #     C26<->+170V_BUS   31.765mm      C25<->DC_BUS_RTN  96.038mm
        #
        # The minimum is 15.456mm against a 10.0mm requirement -- 55%
        # margin, and every pair clears at PD3, at PD2 (6.3mm) and at the
        # enforced 2.0mm. So the empty dict is a genuine pass on physical
        # geometry, not an absence of checking.
        #
        # What this does NOT clear, and why TestTankBusEnforcement stays
        # red: the board's PHYSICAL gap now meets PD3, but the DECLARED and
        # ENFORCED figures do not -- netclass clearance is still 2.0mm and
        # SSOT creepage still 6.3mm (HighVoltageTank) / 6.0mm
        # (HighVoltage). Geometry has overtaken the numbers the design is
        # specified to. Closing that is the SafetyValue migration those
        # tests name, not this re-derivation.
        assert by_pair == {}, f"pour-bounded shortfall changed: {by_pair}"

    def test_pad_gap_only_check_without_zones_stays_pad_pad(self):
        """Without zone data the checker can only report pad-pad gaps --
        the honest limit of netlist-only data (the unrouted board's pads
        are all 25mm+ apart, so no pad-pad violation exists today)."""
        netlist = _real_netlist()
        pairs = tank_bus_net_pairs(netlist)
        assert check_tank_bus_creepage(
            netlist, pairs, margin_mm=HV_TANK_CREEPAGE_PD3_MM, zones=None
        ) == []


class TestTankBusEnforcement:
    """THE SHORTFALL CATCH -- expected RED on the committed design.

    The tank<->bus pair's governing requirement is IEC 60335-1 Table 18
    functional creepage, >500-800V band (the pair measures 570.5 Vrms):
    6.3mm at PD2, 10.0mm at PD3, with PD3 governing as built (the PD2
    sealed-compartment prerequisite does not exist on this board --
    docs/evidence/2026-08-11-pd2-decision-record.md;
    docs/evidence/2026-08-12-hv-hv-creepage-determination.md Sec 4.3).

    Every figure the design is BUILT to is below that requirement today:

    - netclass clearance (the "2.0mm provided" of the evidence doc):
      2.0mm -- a reinforced mains<->PELV barrier figure re-applied as
      same-domain HV<->HV clearance (N1 in the 2026-08-15 audit);
    - DRU-emitted tank creepage rule: 6.3mm (the PD2 figure, selected via
      ``_TANK_POLLUTION_DEGREE = "PD2"`` even though the compartment does
      not exist);
    - SSOT declared creepage: 6.0mm (HighVoltage) / 6.3mm
      (HighVoltageTank).

    These tests FAIL today -- a labelled red, by design. They flip green
    only when the SafetyValue migration raises the enforced figures to
    6.3/10.0. Never make them pass by weakening the assertion.
    """

    def test_enforced_netclass_clearance_meets_pd3(self):
        """The same-domain HV clearance enforced for the tank<->bus pair
        must be >= the governing PD3 functional creepage (10.0mm)."""
        assert enforced_tank_bus_clearance_mm() >= HV_TANK_CREEPAGE_PD3_MM, (
            "tank<->bus enforced clearance "
            f"({enforced_tank_bus_clearance_mm():.1f}mm) is short of the "
            f"governing PD3 functional creepage ({HV_TANK_CREEPAGE_PD3_MM}mm) -- "
            "the 2.0mm 'provided' of docs/evidence/2026-08-12-hv-hv-creepage-"
            "determination.md Sec 4.3"
        )

    def test_enforced_netclass_clearance_meets_pd2(self):
        """Even the conditional PD2 figure (6.3mm) is not met by the
        enforced 2.0mm clearance."""
        assert enforced_tank_bus_clearance_mm() >= HV_TANK_CREEPAGE_PD2_MM

    def test_dru_rule_enforces_pd3_as_built(self):
        """The DRU generator's 'HighVoltageTank functional creepage' rule
        -- the only creepage rule on this board with BOTH sides HV -- must
        enforce the as-built governing figure (PD3), not the conditional
        PD2 figure. Today it selects PD2 via _TANK_POLLUTION_DEGREE even
        though the sealed-compartment prerequisite is unmet
        (check_pd2_compartment_evidence.py exits 3)."""
        ns = _dru_namespace()
        enforced = ns["HV_TANK_CREEPAGE_ENFORCED_MM"]
        assert enforced >= HV_TANK_CREEPAGE_PD3_MM, (
            "DRU tank<->bus creepage rule enforces "
            f"{enforced}mm (pollution degree {ns['_TANK_POLLUTION_DEGREE']}) "
            f"against the governing PD3 figure ({HV_TANK_CREEPAGE_PD3_MM}mm) -- "
            "the PD2 selection is conditional on a sealed compartment that does not exist"
        )

    def test_dru_rule_selects_pd3(self):
        """State pin for the DRU rule's selected figure. RE-DERIVED
        2026-08-24: it is PD3 now, not PD2.

        The previous version of this test was named
        ``test_dru_rule_currently_selects_pd2`` and pinned
        ``_TANK_POLLUTION_DEGREE == "PD2"``, with a docstring saying
        "Re-derive when the pollution-degree selection changes (that is the
        fix)". The selection changed -- so this is that re-derivation, and
        the rename is part of it: a test called `currently_selects_pd2`
        asserting PD3 would be a trap for the next reader.

        The fix landing here is visible in its sibling:
        ``test_dru_rule_enforces_pd3_as_built`` PASSES on this board, so
        the DRU no longer selects the conditional PD2 figure whose
        sealed-compartment prerequisite does not exist. The remaining
        enforcement tests in this class stay red because the NETCLASS and
        SSOT figures are still 2.0mm / 6.3mm / 6.0mm -- the DRU moved, they
        have not."""
        ns = _dru_namespace()
        assert ns["_TANK_POLLUTION_DEGREE"] == "PD3"
        assert ns["HV_TANK_CREEPAGE_ENFORCED_MM"] == HV_TANK_CREEPAGE_PD3_MM

    def test_ssot_declared_creepage_meets_pd3(self):
        """The netclass SSOT's own declared creepage for the two classes
        the pair spans must be >= the governing PD3 figure."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        assert TEMPER_NET_CLASSES["HighVoltageTank"].creepage_mm >= HV_TANK_CREEPAGE_PD3_MM, (
            "HighVoltageTank.creepage_mm "
            f"({TEMPER_NET_CLASSES['HighVoltageTank'].creepage_mm}) is short of "
            f"PD3 ({HV_TANK_CREEPAGE_PD3_MM}mm)"
        )
        assert TEMPER_NET_CLASSES["HighVoltage"].creepage_mm >= HV_TANK_CREEPAGE_PD3_MM, (
            "HighVoltage.creepage_mm "
            f"({TEMPER_NET_CLASSES['HighVoltage'].creepage_mm}) is short of "
            f"PD3 ({HV_TANK_CREEPAGE_PD3_MM}mm)"
        )


class TestOrToolsEncoding:
    """add_tank_creepage_to_model posts a real, binding constraint."""

    def _two_component_model(self, w0=10.0, h0=10.0):
        model = CpSatModel(units_per_mm=100)
        for ref in ("TANKC", "OTHERHV"):
            model.add_component(
                ref,
                x_start_val=0,
                y_start_val=0,
                width=model.mm_to_units(w0),
                height=model.mm_to_units(h0),
            )
            model.add_rotation(ref, is_polarized=True)
        return model

    def _netlist_stub(self, tank_ref="TANKC", other_ref="OTHERHV", other_net="discharge.k_dis1-nc"):
        from temper_placer.core.netlist import Component, Netlist, Pin

        tank = Component(
            ref=tank_ref,
            footprint="fp",
            bounds=(10.0, 10.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net=TANK_NODE_NET)],
        )
        other = Component(
            ref=other_ref,
            footprint="fp",
            bounds=(10.0, 10.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net=other_net)],
        )
        return Netlist(components=[tank, other], nets=[])

    def test_encodes_exactly_one_pair(self):
        model = self._two_component_model()
        netlist = self._netlist_stub()
        report = add_tank_creepage_to_model(model, netlist, margin_mm=10.0)
        assert report.pairs_encoded == 1
        assert report.tank_refs == ("TANKC",)
        assert report.other_refs == ("OTHERHV",)

    def test_rejects_components_pinned_too_close(self):
        model = self._two_component_model()
        netlist = self._netlist_stub()
        add_tank_creepage_to_model(model, netlist, margin_mm=10.0)

        a = model.get_component("TANKC")
        b = model.get_component("OTHERHV")
        # Pin both at the same point -- 0mm gap, well under 10mm.
        model.model_ref.Add(a.x_center == model.mm_to_units(50.0))
        model.model_ref.Add(a.y_center == model.mm_to_units(50.0))
        model.model_ref.Add(b.x_center == model.mm_to_units(50.0))
        model.model_ref.Add(b.y_center == model.mm_to_units(50.0))

        solver = cp_model.CpSolver()
        status = solver.Solve(model.model_ref)
        assert status == cp_model.INFEASIBLE

    def test_accepts_components_pinned_far_enough_apart(self):
        model = self._two_component_model()
        netlist = self._netlist_stub()
        add_tank_creepage_to_model(model, netlist, margin_mm=10.0)

        a = model.get_component("TANKC")
        b = model.get_component("OTHERHV")
        model.model_ref.Add(a.x_center == model.mm_to_units(20.0))
        model.model_ref.Add(a.y_center == model.mm_to_units(20.0))
        model.model_ref.Add(b.x_center == model.mm_to_units(50.0))
        model.model_ref.Add(b.y_center == model.mm_to_units(20.0))

        solver = cp_model.CpSolver()
        status = solver.Solve(model.model_ref)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_solves_freely_without_pins(self):
        """Not near the edge of feasibility for a trivial two-component
        model: the solver should find SOME placement satisfying it."""
        model = self._two_component_model()
        netlist = self._netlist_stub()
        add_tank_creepage_to_model(model, netlist, margin_mm=10.0)
        model.set_bounds(0, 0, model.mm_to_units(200.0), model.mm_to_units(200.0))

        solver = cp_model.CpSolver()
        status = solver.Solve(model.model_ref)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_skips_refs_absent_from_model(self):
        """A pair naming a ref this model never registered is skipped, not
        a KeyError -- the same discipline domain_clearance.py's generator
        uses via component_refs filtering."""
        model = CpSatModel(units_per_mm=100)
        model.add_component("TANKC", 0, 0, model.mm_to_units(10.0), model.mm_to_units(10.0))
        model.add_rotation("TANKC", is_polarized=True)
        netlist = self._netlist_stub()  # declares OTHERHV too, never registered
        report = add_tank_creepage_to_model(model, netlist, margin_mm=10.0)
        assert report.pairs_encoded == 0
        assert report.pairs_skipped_absent == 1


class TestWireFormat:
    """Pumpkin JSON wire-format emission -- the ``separated`` shape
    ``main.rs:308`` and ``handlers/separated.py`` both already parse."""

    def test_emits_separated_type_only(self):
        netlist = _real_netlist()
        wc = tank_creepage_wire_constraints(netlist, margin_mm=10.0)
        assert wc, "no wire constraints emitted"
        assert all(c["type"] == "separated" for c in wc)
        assert all(c["min_distance_mm"] == 10.0 for c in wc)
        assert all({"a", "b"} <= c.keys() for c in wc)

    def test_present_refs_filters_absent_components(self):
        netlist = _real_netlist()
        wc_all = tank_creepage_wire_constraints(netlist, margin_mm=10.0)
        present = frozenset({"C25", "K2"})  # only one tank ref, one other-hv ref
        wc_filtered = tank_creepage_wire_constraints(
            netlist, margin_mm=10.0, present_refs=present
        )
        assert len(wc_filtered) == 1
        assert wc_filtered[0] == {"type": "separated", "a": "C25", "b": "K2", "min_distance_mm": 10.0}
        assert len(wc_filtered) < len(wc_all)
