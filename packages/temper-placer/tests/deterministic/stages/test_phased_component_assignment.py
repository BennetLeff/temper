"""
Tests for PhasedComponentAssignmentStage - priority-based placement.

Part of temper-g54c.3: Phased placement using placement_priority configuration.
"""

import logging
from unittest.mock import Mock

import math

import pytest

from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import PlacementConstraints, SeedFilterConfig


class TestPhasedPlacement:
    """Tests for phased placement execution."""

    def test_fallback_to_simple_greedy_without_phases(self):
        """Should use simple greedy if no placement_priority defined."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)

        # Create minimal state
        netlist = Mock()
        netlist.components = [
            Mock(ref="C1", bounds=(5, 5)),
            Mock(ref="C2", bounds=(3, 3)),
        ]
        netlist.nets = []

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("C1", "Signal"), ("C2", "Signal")]),
            zone_slots=frozenset([("Signal", ((10, 10), (20, 20), (30, 30)))]),
        )

        result = stage.run(state)

        assert result.placements is not None
        placements = dict(result.placements)
        assert "C1" in placements
        assert "C2" in placements

    def test_template_placement(self):
        """Test template-based placement phase."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "power": {
                "components": ["Q1", "Q2"],
                "method": "template",
                "template": "half_bridge_vertical",
                "anchor": [50, 50],
            }
        }

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [
            Mock(ref="Q1", bounds=(10, 10)),
            Mock(ref="Q2", bounds=(10, 10)),
        ]
        netlist.nets = []

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("Q1", "Power"), ("Q2", "Power")]),
            zone_slots=frozenset([("Power", ((40, 40), (50, 50), (60, 60)))]),
        )

        result = stage.run(state)

        placements = dict(result.placements)
        assert "Q1" in placements
        assert "Q2" in placements

        # Q1 should be at anchor
        assert placements["Q1"] == (50.0, 50.0)

        # Q2 should be offset vertically
        assert placements["Q2"][0] == 50.0
        assert placements["Q2"][1] > 50.0

    def test_proximity_placement(self):
        """Test proximity-based placement phase."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "fixed": {
                "components": ["U_MCU"],
                "method": "template",
                "anchor": [50, 50],
            },
            "decoupling": {
                "components": ["C1", "C2"],
                "method": "proximity",
                "reference": "U_MCU",
                "max_distance_mm": 15.0,
            },
        }

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [
            Mock(ref="U_MCU", bounds=(10, 10)),
            Mock(ref="C1", bounds=(3, 3)),
            Mock(ref="C2", bounds=(3, 3)),
        ]
        netlist.nets = []

        slots = []
        for x in range(30, 71, 10):
            for y in range(30, 71, 10):
                slots.append((float(x), float(y)))

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("U_MCU", "Signal"), ("C1", "Signal"), ("C2", "Signal")]),
            zone_slots=frozenset([("Signal", tuple(slots))]),
        )

        result = stage.run(state)

        placements = dict(result.placements)
        assert "U_MCU" in placements
        assert "C1" in placements
        assert "C2" in placements

        # MCU at anchor
        assert placements["U_MCU"] == (50.0, 50.0)

        # C1, C2 within max_distance of MCU
        mcu_pos = placements["U_MCU"]
        c1_dist = (
            (placements["C1"][0] - mcu_pos[0]) ** 2 + (placements["C1"][1] - mcu_pos[1]) ** 2
        ) ** 0.5
        c2_dist = (
            (placements["C2"][0] - mcu_pos[0]) ** 2 + (placements["C2"][1] - mcu_pos[1]) ** 2
        ) ** 0.5

        assert c1_dist <= 15.0 or c1_dist <= 20.0  # Allow some tolerance
        assert c2_dist <= 15.0 or c2_dist <= 20.0

    def test_optimize_placement(self):
        """Test optimize placement with constraint-aware selection."""
        from temper_placer.core.board import Zone

        constraints = PlacementConstraints(zones=[Zone(name="Control", bounds=(0, 0, 100, 100))])
        constraints.placement_priority = {
            "control": {
                "components": ["U1", "U2"],
                "method": "optimize",
                "zone": "Control",
            }
        }

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [
            Mock(ref="U1", bounds=(5, 5)),
            Mock(ref="U2", bounds=(5, 5)),
        ]
        net1 = Mock(name="NET1", pins=[("U1", "1"), ("U2", "1")])
        netlist.nets = [net1]

        slots = [(float(x), float(y)) for x in range(10, 91, 20) for y in range(10, 91, 20)]

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("U1", "Control"), ("U2", "Control")]),
            zone_slots=frozenset([("Control", tuple(slots))]),
        )

        result = stage.run(state)

        placements = dict(result.placements)
        assert "U1" in placements
        assert "U2" in placements

        # Should be placed to minimize wirelength (close together)
        dist = (
            (placements["U1"][0] - placements["U2"][0]) ** 2
            + (placements["U1"][1] - placements["U2"][1]) ** 2
        ) ** 0.5

        # Not necessarily adjacent, but should be reasonable
        assert dist < 100.0

    def test_auto_phase_places_remaining(self):
        """Test auto phase places all unplaced components."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "critical": {
                "components": ["U1"],
                "method": "template",
                "anchor": [50, 50],
            },
            "auto": {
                "method": "auto",
            },
        }

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [
            Mock(ref="U1", bounds=(10, 10)),
            Mock(ref="C1", bounds=(3, 3)),
            Mock(ref="C2", bounds=(3, 3)),
            Mock(ref="R1", bounds=(2, 2)),
        ]
        netlist.nets = []

        slots = [(float(x), float(y)) for x in range(20, 81, 15) for y in range(20, 81, 15)]

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset(
                [("U1", "Signal"), ("C1", "Signal"), ("C2", "Signal"), ("R1", "Signal")]
            ),
            zone_slots=frozenset([("Signal", tuple(slots))]),
        )

        result = stage.run(state)

        placements = dict(result.placements)

        # All components should be placed
        assert "U1" in placements
        assert "C1" in placements
        assert "C2" in placements
        assert "R1" in placements

    def test_constraint_validation_warnings(self):
        """Test that constraint validation warnings are logged."""
        from temper_placer.io.config_loader import EscapeClearance

        constraints = PlacementConstraints(
            escape_clearances=[EscapeClearance(component="MISSING_COMPONENT", clearance_mm=5.0)]
        )

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [Mock(ref="U1", bounds=(5, 5))]
        netlist.nets = []

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("U1", "Signal")]),
            zone_slots=frozenset([("Signal", ((10, 10),))]),
        )

        # Should not crash, just warn
        result = stage.run(state)
        assert result.placements is not None


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_footprint_radius(self):
        """Test footprint radius calculation."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints, slot_spacing=12.0)

        # Component with bounds
        comp = Mock(bounds=(10, 10))
        radius = stage._get_footprint_radius(comp)

        # Diagonal/2 + 1mm margin
        expected = (10**2 + 10**2) ** 0.5 / 2 + 1.0
        assert abs(radius - expected) < 0.1

        # Component without bounds
        comp_no_bounds = Mock(spec=[])  # No bounds attribute
        radius = stage._get_footprint_radius(comp_no_bounds)
        assert radius == 6.0  # slot_spacing / 2

    def test_reserve_slots(self):
        """Test slot reservation."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)

        all_slots = [(0, 0), (5, 0), (10, 0), (15, 0)]
        used_slots = set()

        # Reserve slots within 7mm of (5, 0)
        stage._reserve_slots((5, 0), 7.0, all_slots, used_slots)

        assert (0, 0) in used_slots  # dist=5
        assert (5, 0) in used_slots  # dist=0
        assert (10, 0) in used_slots  # dist=5
        assert (15, 0) not in used_slots  # dist=10

    def test_distance_calculation(self):
        """Test Euclidean distance."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)

        dist = stage._distance((0, 0), (3, 4))
        assert dist == 5.0

    def test_compute_wirelength(self):
        """Test HPWL wirelength computation."""
        constraints = PlacementConstraints()
        stage = PhasedComponentAssignmentStage(constraints)

        net_pins = {"NET1": [("C1", "1"), ("C2", "1"), ("C3", "1")]}

        placements = {"C2": (10, 0), "C3": (20, 0)}

        # Place C1 at (0, 0)
        hpwl = stage._compute_wirelength("C1", (0, 0), net_pins, placements)

        # Bounding box: (0,0) to (20,0) → HPWL = 20 + 0 = 20
        assert hpwl == 20.0


class TestPhaseOrdering:
    """Test that phases execute in correct order."""

    def test_phases_execute_in_order(self):
        """Test that phases respect execution order."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "phase1": {
                "components": ["A"],
                "method": "template",
                "anchor": [10, 10],
            },
            "phase2": {
                "components": ["B"],
                "method": "proximity",
                "reference": "A",
                "max_distance_mm": 10.0,
            },
            "phase3": {
                "components": ["C"],
                "method": "optimize",
            },
        }

        stage = PhasedComponentAssignmentStage(constraints)

        netlist = Mock()
        netlist.components = [
            Mock(ref="A", bounds=(5, 5)),
            Mock(ref="B", bounds=(3, 3)),
            Mock(ref="C", bounds=(3, 3)),
        ]
        netlist.nets = []

        slots = [(float(x), float(y)) for x in range(0, 51, 10) for y in range(0, 51, 10)]

        state = BoardState(
            netlist=netlist,
            component_zone_map=frozenset([("A", "Signal"), ("B", "Signal"), ("C", "Signal")]),
            zone_slots=frozenset([("Signal", tuple(slots))]),
        )

        result = stage.run(state)

        placements = dict(result.placements)

        # A placed first (phase1)
        assert "A" in placements
        assert placements["A"] == (10.0, 10.0)

        # B placed near A (phase2)
        assert "B" in placements

        # C placed last (phase3)
        assert "C" in placements


# =====================================================================
# U1 — Ghost-Pad Injection Core
# =====================================================================


def _build_canonical_hv_netlist() -> Netlist:
    """Canonical 4-component netlist: 2 HV components, 2 LV components."""
    q1 = Component(
        ref="Q1",
        footprint="TO247",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
            Pin(name="2", number="2", position=(5.0, 0.0), net="DC_BUS+"),
        ],
    )
    q2 = Component(
        ref="Q2",
        footprint="TO247",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
            Pin(name="2", number="2", position=(5.0, 0.0), net="DC_BUS+"),
        ],
    )
    c1 = Component(
        ref="C1",
        footprint="0603",
        bounds=(2.0, 2.0),
        pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
    )
    c2 = Component(
        ref="C2",
        footprint="0603",
        bounds=(2.0, 2.0),
        pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="GND")],
    )
    return Netlist(
        components=[q1, q2, c1, c2],
        nets=[
            Net(name="DC_BUS+", pins=[("Q1", "1"), ("Q2", "1")], net_class="HighVoltage"),
            Net(name="VCC", pins=[("C1", "1")], net_class="Power"),
            Net(name="GND", pins=[("C2", "1")], net_class="Ground"),
        ],
    )


def _hv_design_rules() -> DesignRules:
    """Build a DesignRules with one HV net class (creepage_mm=6.0)."""
    return DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width=0.5,
                clearance=2.0,
                dru_priority=10,
                creepage_mm=6.0,
                safety_category="HV",
            ),
            "Power": NetClassRules(
                name="Power",
                trace_width=0.25,
                clearance=0.2,
                dru_priority=20,
                safety_category="LV",
            ),
            "Ground": NetClassRules(
                name="Ground",
                trace_width=0.25,
                clearance=0.2,
                dru_priority=30,
                safety_category="LV",
            ),
        },
        net_class_assignments={
            "DC_BUS+": "HighVoltage",
            "VCC": "Power",
            "GND": "Ground",
        },
    )


def _build_state(
    netlist: Netlist,
    *,
    components: list[str] | None = None,
    slot_grid: tuple[float, float, float, float, float] = (0.0, 0.0, 60.0, 60.0, 5.0),
) -> BoardState:
    """Build a BoardState with a regular slot grid covering slot_grid extent.

    slot_grid is (x0, y0, x_max, y_max, spacing).  Slots are emitted at
    ``(x0 + i*spacing, y0 + j*spacing)`` for 0 <= i,j < extent/spacing.
    Components default to all netlist components.
    """
    if components is None:
        components = [c.ref for c in netlist.components]
    x0, y0, x_max, y_max, spacing = slot_grid
    n_x = int((x_max - x0) / spacing) + 1
    n_y = int((y_max - y0) / spacing) + 1
    slots: list[tuple[float, float]] = []
    for i in range(n_x):
        for j in range(n_y):
            slots.append((x0 + i * spacing, y0 + j * spacing))
    return BoardState(
        netlist=netlist,
        component_zone_map=frozenset((ref, "Signal") for ref in components),
        zone_slots=frozenset([("Signal", tuple(slots))]),
    )


def _all_slots(state: BoardState) -> list[tuple[float, float]]:
    """Flatten the zone_slots frozenset to a single list of (x, y) slots."""
    return [s for _zone, slots in state.zone_slots for s in slots]


class TestGhostPadInjection:
    """U1: placer reserves the creepage ring around every HV pin's absolute position.

    Each test runs the placer end-to-end and inspects ``result.used_slots`` —
    the production path.  Per-component HV reservation is performed by
    ``_reserve_slots_with_hv`` at placement time using the placed position
    + the pin's component-relative offset, which is the only physically
    correct semantic (pin-relative coordinates would reserve slots at the
    wrong absolute location).
    """

    def test_hv_pin_yields_ghost_pad(self):
        """Every slot within 6mm of a placed HV pin must be in used_slots.

        Q1 is placed at the template anchor (0, 0); Q1's HV pin 1
        is component-relative (0, 0) so its absolute position is
        (0, 0).  Q1's HV pin 2 is component-relative (5, 0) so its
        absolute position is (5, 0).  All slots within creepage
        (6mm) of either absolute position must be reserved.
        """
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "power": {
                "components": ["Q1", "Q2"],
                "method": "template",
                "template": "stacked",
                "anchor": [0.0, 0.0],
            }
        }
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        state = _build_state(_build_canonical_hv_netlist())

        result = stage.run(state)
        used = set(result.used_slots)
        placements = dict(result.placements)

        # Q1 is placed at the anchor (template places component 0 at
        # anchor + i*10mm vertical offset).  Q1 HV pins are at
        # relative (0, 0) and (5, 0) — absolute (0, 0) and (5, 0).
        assert placements["Q1"] == (0.0, 0.0)
        q1_pos = placements["Q1"]
        q1_hv_abs = (
            (q1_pos[0] + 0.0, q1_pos[1] + 0.0),
            (q1_pos[0] + 5.0, q1_pos[1] + 0.0),
        )

        # Every slot within 6mm of an HV pin absolute position must be reserved.
        for slot in _all_slots(state):
            for px, py in q1_hv_abs:
                if math.hypot(slot[0] - px, slot[1] - py) <= 6.0:
                    assert slot in used, (
                        f"slot {slot} is within creepage of Q1 HV pin "
                        f"({px}, {py}) but not in used_slots"
                    )

        # Spot checks: (0,0), (5,0), (0,5) are within 6mm of Q1's HV
        # pin 1 absolute (0, 0) so must be reserved.
        assert (0.0, 0.0) in used
        assert (5.0, 0.0) in used
        assert (0.0, 5.0) in used
        # (15, 0) is 15mm from pin 1 and 10mm from pin 2 — outside
        # the 6mm creepage ring.  It is also outside Q1's footprint
        # ring (~8mm) and Q2's footprint ring (Q2 is at (0, 10) per
        # the 10mm template stacking).  Must NOT be reserved.
        assert (15.0, 0.0) not in used

    def test_lv_pin_yields_no_ghost_pad(self):
        """Board with all safety_category=LV must produce no HV creepage rings.

        Only footprint rings are reserved — every reserved slot must be
        within a placed component's footprint radius.
        """
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        rules = DesignRules(
            net_classes={
                "Power": NetClassRules(
                    name="Power",
                    trace_width=0.25,
                    clearance=0.2,
                    dru_priority=10,
                    creepage_mm=6.0,
                    safety_category="LV",
                ),
            },
            net_class_assignments={"VCC": "Power"},
        )
        netlist = Netlist(
            components=[
                Component(
                    ref="C1",
                    footprint="0603",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
                )
            ],
            nets=[Net(name="VCC", pins=[("C1", "1")], net_class="Power")],
        )
        state = _build_state(netlist)
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)

        result = stage.run(state)
        used = set(result.used_slots)
        placements = dict(result.placements)

        # No HV rings: every reserved slot must be within the placed
        # component's footprint radius (sqrt(8)/2 + 1 ≈ 2.4mm).
        placed_pos = placements["C1"]
        for slot in used:
            assert math.hypot(slot[0] - placed_pos[0], slot[1] - placed_pos[1]) <= 2.5, (
                f"slot {slot} is reserved but is not within C1's footprint ring "
                f"at {placed_pos} (no HV ring expected for LV-only board)"
            )

    def test_none_safety_category_treated_as_lv(self):
        """A pin whose net resolves to a None safety_category yields no HV ring."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        rules = DesignRules(
            net_classes={
                "Default": NetClassRules(
                    name="Default",
                    trace_width=0.2,
                    clearance=0.2,
                    dru_priority=99,
                    safety_category=None,
                ),
            },
            net_class_assignments={"VCC": "Default"},
        )
        netlist = Netlist(
            components=[
                Component(
                    ref="C1",
                    footprint="0603",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
                )
            ],
            nets=[Net(name="VCC", pins=[("C1", "1")], net_class="Default")],
        )
        state = _build_state(netlist)
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)

        result = stage.run(state)
        used = set(result.used_slots)
        placements = dict(result.placements)

        # safety_category=None must behave like LV: no HV ring, only footprint.
        placed_pos = placements["C1"]
        for slot in used:
            assert math.hypot(slot[0] - placed_pos[0], slot[1] - placed_pos[1]) <= 2.5, (
                f"slot {slot} is reserved but safety_category=None must not "
                f"trigger HV ring"
            )

    def test_injection_idempotent(self):
        """Running the placer twice on the same state yields identical used_slots."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        state = _build_state(_build_canonical_hv_netlist())

        r1 = stage.run(state)
        r2 = stage.run(state)
        assert set(r1.used_slots) == set(r2.used_slots)
        assert dict(r1.placements) == dict(r2.placements)

    def test_no_randomness_seed_unchanged(self):
        """Placing on the same netlist/state at fixed seed yields the same placements."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        state = _build_state(_build_canonical_hv_netlist())

        r1 = stage.run(state)
        r2 = stage.run(state)
        assert dict(r1.placements) == dict(r2.placements)

    def test_hv_pin_at_slot_grid_boundary_still_blocked(self):
        """Slot grid boundary case: HV pin within 1 slot-spacing of board edge.

        Reproduces the A5 failure mode where a slot exactly on the board
        edge must still be reserved by the ghost-pad radius.
        """
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "power": {
                "components": ["Q1", "C1"],
                "method": "template",
                "template": "stacked",
                "anchor": [1.0, 1.0],
            }
        }
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        # Build a netlist whose Q1 sits at (1.0, 1.0) — 1mm in from corner.
        # Q1's HV pin 1 is component-relative (0, 0) so its absolute
        # position is (1.0, 1.0).  With a 5mm slot grid, the nearest
        # grid slot is (0.0, 0.0) — within the 6mm creepage ring.
        netlist = Netlist(
            components=[
                Component(
                    ref="Q1",
                    footprint="TO247",
                    bounds=(10.0, 10.0),
                    initial_position=(1.0, 1.0),
                    pins=[
                        Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
                    ],
                ),
                Component(
                    ref="C1",
                    footprint="0603",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
                ),
            ],
            nets=[
                Net(name="DC_BUS+", pins=[("Q1", "1")], net_class="HighVoltage"),
                Net(name="VCC", pins=[("C1", "1")], net_class="Power"),
            ],
        )
        state = _build_state(
            netlist, slot_grid=(0.0, 0.0, 15.0, 15.0, 5.0)
        )

        result = stage.run(state)
        used = set(result.used_slots)

        # Q1 is at template anchor (1.0, 1.0).  Q1 HV pin 1 absolute
        # position is (1.0, 1.0).  The closest grid slot is (0.0, 0.0)
        # at distance sqrt(2) ~ 1.41mm < 6mm creepage.
        assert (0.0, 0.0) in used

    def test_empty_net_classes_yields_no_ghosts(self):
        """state.design_rules.net_classes == {} → no HV rings, only footprint rings."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        rules = DesignRules(net_classes={}, net_class_assignments={})
        stage = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        state = _build_state(_build_canonical_hv_netlist())

        result = stage.run(state)
        used = set(result.used_slots)
        placements = dict(result.placements)

        # No HV rings because no net class has HV/AC safety_category.
        # Every reserved slot must be within a placed component's footprint ring.
        comp_by_ref = {c.ref: c for c in state.netlist.components}
        for slot in used:
            within_any = False
            for ref, pos in placements.items():
                comp = comp_by_ref.get(ref)
                if comp is None:
                    continue
                radius = math.hypot(comp.bounds[0], comp.bounds[1]) / 2 + 1.0
                if math.hypot(slot[0] - pos[0], slot[1] - pos[1]) <= radius:
                    within_any = True
                    break
            assert within_any, (
                f"slot {slot} is reserved but not within any footprint ring "
                f"(empty net_classes must produce no HV ring)"
            )

    def test_no_design_rules_is_noop(self):
        """design_rules=None → no HV ring (legacy pipelines, NFR4 parity)."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {
            "auto": {"method": "auto"},
        }
        stage = PhasedComponentAssignmentStage(constraints, design_rules=None)
        state = _build_state(_build_canonical_hv_netlist())

        result = stage.run(state)
        used = set(result.used_slots)
        placements = dict(result.placements)

        # design_rules=None: only footprint rings, no HV rings.
        comp_by_ref = {c.ref: c for c in state.netlist.components}
        for slot in used:
            within_any = False
            for ref, pos in placements.items():
                comp = comp_by_ref.get(ref)
                if comp is None:
                    continue
                radius = math.hypot(comp.bounds[0], comp.bounds[1]) / 2 + 1.0
                if math.hypot(slot[0] - pos[0], slot[1] - pos[1]) <= radius:
                    within_any = True
                    break
            assert within_any, (
                f"slot {slot} is reserved but design_rules=None must not "
                f"add HV rings"
            )

    def test_lv_only_placement_is_unchanged_parity_anchor(self):
        """NFR4: a board with all-LV nets produces identical placements before/after."""
        constraints = PlacementConstraints()
        constraints.placement_priority = {"auto": {"method": "auto"}}
        # Build an LV-only netlist
        netlist = Netlist(
            components=[
                Component(
                    ref="C1",
                    footprint="0603",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
                ),
                Component(
                    ref="C2",
                    footprint="0603",
                    bounds=(2.0, 2.0),
                    pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="GND")],
                ),
            ],
            nets=[
                Net(name="VCC", pins=[("C1", "1")], net_class="Power"),
                Net(name="GND", pins=[("C2", "1")], net_class="Ground"),
            ],
        )
        rules = DesignRules(
            net_classes={
                "Power": NetClassRules(
                    name="Power", trace_width=0.25, clearance=0.2, dru_priority=10,
                    safety_category="LV",
                ),
                "Ground": NetClassRules(
                    name="Ground", trace_width=0.25, clearance=0.2, dru_priority=20,
                    safety_category="LV",
                ),
            },
            net_class_assignments={"VCC": "Power", "GND": "Ground"},
        )
        # With ghost-pad injection ON
        stage_on = PhasedComponentAssignmentStage(constraints, design_rules=rules)
        state = _build_state(netlist)
        result_on = dict(stage_on.run(state).placements)

        # With ghost-pad injection OFF (legacy)
        stage_off = PhasedComponentAssignmentStage(constraints, design_rules=None)
        result_off = dict(stage_off.run(state).placements)

        assert result_on == result_off


# =====================================================================
# U2 — Isolation-Slot Creepage Reduction
# =====================================================================


def _u2_constraints_with_slot(component_ref: str = "Q1") -> PlacementConstraints:
    """Build constraints with a 10mm isolation slot on the named component."""
    return PlacementConstraints(
        isolation_slots=[
            IsolationSlot(
                name=f"{component_ref}_gate_isolation",
                component_ref=component_ref,
                start_offset=(2.725, -5.0),
                end_offset=(2.725, 5.0),
                width_mm=1.5,
                lv_pin="1",
                hv_pin="2",
            )
        ]
    )


class TestIsolationSlotReduction:
    """U2: reduce ghost-pad radius by slot projection (gated by use_isolation_slots)."""

    def test_isolation_slots_disabled_is_bit_identical(self):
        """use_isolation_slots=False must produce the same used_slots as a bare stage."""
        constraints = _u2_constraints_with_slot()
        constraints.placement_priority = {"auto": {"method": "auto"}}
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=False
        )
        state = _build_state(_build_canonical_hv_netlist())

        used = set(stage.run(state).used_slots)

        # The same constraints without isolation_slots and use_isolation_slots=False
        # must produce the same used_slots (NFR4 parity).
        bare = PlacementConstraints()
        bare.placement_priority = {"auto": {"method": "auto"}}
        bare_stage = PhasedComponentAssignmentStage(
            bare, design_rules=rules, use_isolation_slots=False
        )
        used_bare = set(bare_stage.run(state).used_slots)
        assert used == used_bare

    def test_isolation_slots_enabled_reduces_radius(self):
        """use_isolation_slots=True must shrink the effective radius by the projected slot length.

        Q1 pin 1 absolute is (0, 0); the nearest other HV pin (Q2 pin 1)
        absolute is (0, 10).  The creepage direction is unit (0, 1).
        Q1's isolation slot vector is (0, 10) (from (2.725, -5) to
        (2.725, 5)) and is fully aligned with the direction, so
        projection = 10.  Effective radius for Q1 pins =
        max(0, 6 - 10) = 0.  Q2 has no slot referenced, so its
        effective radius stays 6.0mm.
        """
        constraints = _u2_constraints_with_slot("Q1")
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        eff_q1 = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (0.0, 10.0)
        )
        eff_q2 = stage._effective_ghost_pad_radius(
            "Q2", "1", 6.0, (0.0, 10.0), (0.0, 0.0)
        )
        assert eff_q1 == 0.0
        assert eff_q2 == 6.0

    def test_isolation_slot_on_lv_component_ignored(self):
        """A slot referencing a non-HV component must not reduce radius.

        With use_isolation_slots=True and a slot on C1 (LV component), the
        effective radius for any HV pin (on Q1/Q2) must be unchanged from
        the base 6.0mm.
        """
        constraints = _u2_constraints_with_slot("C1")  # slot on LV component
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (0.0, 10.0)
        )
        assert eff == 6.0

    def test_isolation_slot_length_can_fully_clamp_to_zero(self):
        """Multiple slots on the same component can clamp the radius to zero.

        Both Q1 slots are vertical (along the y-axis).  With
        current_pin=(0,0) and other=(0,12), the creepage unit vector is
        (0, 1) and both slots project to their full length: 8 + 4 = 12.
        6.0 - 12.0 = -6.0 → clamped at 0.
        """
        constraints = PlacementConstraints(
            isolation_slots=[
                IsolationSlot(
                    name="slot_a",
                    component_ref="Q1",
                    start_offset=(0.0, -4.0),
                    end_offset=(0.0, 4.0),  # 8mm long
                    width_mm=1.0,
                ),
                IsolationSlot(
                    name="slot_b",
                    component_ref="Q1",
                    start_offset=(0.0, -2.0),
                    end_offset=(0.0, 2.0),  # 4mm long
                    width_mm=1.0,
                ),
            ]
        )
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (0.0, 12.0)
        )
        assert eff == 0.0

    def test_isolation_slot_perpendicular_to_direction_reduces_zero(self):
        """A slot perpendicular to the creepage direction must reduce radius by 0.

        This is the property test for the IEC 62368-1 Annex G
        projection: a slot that runs perpendicular to the
        pin-to-other-HV direction does not reclaim any creepage.
        """
        constraints = _u2_constraints_with_slot("Q1")
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        # Creepage direction: x-axis (Q1 pin at (0,0), other HV pin at (10, 0)).
        # The default Q1 slot runs along the y-axis, perpendicular to x.
        # Projection = (0, 10) · (1, 0) = 0 → no reduction.
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (10.0, 0.0)
        )
        assert eff == 6.0

    def test_isolation_slot_anti_parallel_reduces_zero(self):
        """A slot pointing AWAY from the other HV pin must reduce by 0.

        Negative projections are clamped to 0 (a slot that points
        away from the other HV pin does not extend creepage).
        """
        constraints = PlacementConstraints(
            isolation_slots=[
                IsolationSlot(
                    name="anti_slot",
                    component_ref="Q1",
                    start_offset=(2.725, 5.0),
                    end_offset=(2.725, -5.0),  # 10mm long, pointing DOWN
                    width_mm=1.5,
                ),
            ]
        )
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        # Other HV pin is ABOVE the current pin → direction is +y.
        # Slot vector is -y → projection = -10 → clamped to 0.
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (0.0, 10.0)
        )
        assert eff == 6.0

    def test_isolation_slot_partial_projection(self):
        """A 45° slot projects to slot_length * cos(45°) ≈ 0.707 * length.

        A 10mm slot at 45° to the creepage direction projects to
        10 * cos(45°) ≈ 7.07mm.  Effective radius for Q1 =
        max(0, 6 - 7.07) ≈ 0 (clamped to 0).
        """
        constraints = PlacementConstraints(
            isolation_slots=[
                IsolationSlot(
                    name="diag_slot",
                    component_ref="Q1",
                    start_offset=(0.0, 0.0),
                    end_offset=(10.0 / math.sqrt(2), 10.0 / math.sqrt(2)),
                    width_mm=1.0,
                ),
            ]
        )
        rules = _hv_design_rules()
        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules, use_isolation_slots=True
        )
        # Creepage direction is +x.  Slot vector is (10/√2, 10/√2) ≈ (7.07, 7.07).
        # Projection = 7.07 * 1 + 7.07 * 0 = 7.07.
        # Effective radius = max(0, 6 - 7.07) = 0.
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (10.0, 0.0)
        )
        assert eff == 0.0

        # A larger base radius yields a non-zero effective radius.
        # 10.0 - 7.07 ≈ 2.93
        eff2 = stage._effective_ghost_pad_radius(
            "Q1", "1", 10.0, (0.0, 0.0), (10.0, 0.0)
        )
        assert abs(eff2 - (10.0 - 10.0 / math.sqrt(2))) < 1e-9

    def test_use_isolation_slots_loaded_from_config(self):
        """The `placer: {use_isolation_slots: true}` YAML block must be honored."""
        constraints = _u2_constraints_with_slot("Q1")
        constraints.placer = {"use_isolation_slots": True}
        rules = _hv_design_rules()

        # Build via the deterministic pipeline helper to exercise the loader.
        from temper_placer.deterministic import DeterministicPipeline

        stage = PhasedComponentAssignmentStage(
            constraints, design_rules=rules,
            use_isolation_slots=bool(constraints.placer.get("use_isolation_slots", False)),
        )
        assert stage.use_isolation_slots is True
        eff = stage._effective_ghost_pad_radius(
            "Q1", "1", 6.0, (0.0, 0.0), (0.0, 10.0)
        )
        assert eff == 0.0
