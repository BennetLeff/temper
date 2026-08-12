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
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.model import CpSatModel
from temper_placer.placer.cp_sat.tank_creepage import (
    DEFAULT_TANK_CREEPAGE_MM,
    HV_TANK_CREEPAGE_PD2_MM,
    HV_TANK_CREEPAGE_PD3_MM,
    TANK_NODE_NET,
    add_tank_creepage_to_model,
    check_tank_creepage_separation,
    find_tank_self_pairs,
    other_hv_refs,
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
        assert {"K2", "R12", "R19"} <= other

    def test_pair_count_matches_measured_board(self):
        netlist = _real_netlist()
        pairs = tank_creepage_pairs(netlist)
        assert len(pairs) == 4 * 42, (
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
        rotations = {c.ref: int(c.initial_rotation or 0) for c in netlist.components}
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
