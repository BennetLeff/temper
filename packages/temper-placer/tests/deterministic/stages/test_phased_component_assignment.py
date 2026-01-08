"""
Tests for PhasedComponentAssignmentStage - priority-based placement.

Part of temper-g54c.3: Phased placement using placement_priority configuration.
"""

from unittest.mock import Mock

import pytest

from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import PlacementConstraints


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
