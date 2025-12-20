"""Tests for zone assignment solver."""

import pytest
from temper_placer.topological.zone_solver import (
    ZoneAssignment,
    ZoneSolver,
)
from temper_placer.core.board import Zone
from temper_placer.pcl.constraints import (
    EnclosingConstraint,
    OnSideConstraint,
    ConstraintTier,
    BoardSide,
    EdgeType,
)


class TestZoneAssignment:
    """Tests for ZoneAssignment data structure."""

    def test_create_empty_assignment(self):
        """Empty assignment has no assignments."""
        assignment = ZoneAssignment(assignments={}, unassigned=[], conflicts=[])
        assert len(assignment.assignments) == 0
        assert len(assignment.unassigned) == 0
        assert len(assignment.conflicts) == 0

    def test_create_with_assignments(self):
        """Can create assignment with component-zone mappings."""
        assignment = ZoneAssignment(
            assignments={"Q1": "HV_ZONE", "U1": "MCU_ZONE"},
            unassigned=[],
            conflicts=[],
        )
        assert assignment.assignments["Q1"] == "HV_ZONE"
        assert assignment.assignments["U1"] == "MCU_ZONE"

    def test_create_with_unassigned(self):
        """Unassigned components tracked."""
        assignment = ZoneAssignment(
            assignments={},
            unassigned=["C1", "C2"],
            conflicts=[],
        )
        assert len(assignment.unassigned) == 2
        assert "C1" in assignment.unassigned

    def test_create_with_conflicts(self):
        """Conflicts tracked as tuples."""
        assignment = ZoneAssignment(
            assignments={},
            unassigned=["Q1"],
            conflicts=[("Q1", "HV_ZONE", "Cannot satisfy enclosing constraint")],
        )
        assert len(assignment.conflicts) == 1


class TestZoneSolver:
    """Tests for ZoneSolver."""

    def test_init_with_no_zones(self):
        """Solver can initialize with no zones."""
        solver = ZoneSolver(zones=[], constraints=[], components=[])
        assert len(solver.zones) == 0
        assert len(solver.components) == 0

    def test_init_with_zones(self):
        """Solver initializes with zone list."""
        zones = [
            Zone(name="HV_ZONE", bounds=(0, 0, 50, 50)),
            Zone(name="MCU_ZONE", bounds=(60, 0, 110, 50)),
        ]
        solver = ZoneSolver(zones=zones, constraints=[], components=[])

        assert len(solver.zones) == 2
        assert "HV_ZONE" in solver.zones
        assert "MCU_ZONE" in solver.zones

    def test_build_candidates_all_zones(self):
        """Without constraints, all components can go in any zone."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
            Zone(name="ZONE_B", bounds=(60, 0, 110, 50)),
        ]
        components = ["Q1", "C1"]

        solver = ZoneSolver(zones=zones, constraints=[], components=components)
        candidates = solver._build_candidates()

        assert candidates["Q1"] == {"ZONE_A", "ZONE_B"}
        assert candidates["C1"] == {"ZONE_A", "ZONE_B"}

    def test_build_candidates_with_enclosing_constraint(self):
        """Enclosing constraint restricts component to specific zone."""
        zones = [
            Zone(name="HV_ZONE", bounds=(0, 0, 50, 50)),
            Zone(name="MCU_ZONE", bounds=(60, 0, 110, 50)),
        ]
        components = ["Q1", "Q2", "U1"]

        constraints = [
            EnclosingConstraint(
                outer="HV_ZONE",
                inner=["Q1", "Q2"],
                tier=ConstraintTier.HARD,
                because="Power components must be in HV zone",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        candidates = solver._build_candidates()

        # Q1, Q2 must be in HV_ZONE
        assert candidates["Q1"] == {"HV_ZONE"}
        assert candidates["Q2"] == {"HV_ZONE"}

        # U1 can be anywhere
        assert candidates["U1"] == {"HV_ZONE", "MCU_ZONE"}

    def test_solve_simple_assignment(self):
        """Solves simple assignment with enclosing constraints."""
        zones = [
            Zone(name="HV_ZONE", bounds=(0, 0, 50, 50)),
            Zone(name="MCU_ZONE", bounds=(60, 0, 110, 50)),
        ]
        components = ["Q1", "U1"]

        constraints = [
            EnclosingConstraint(
                outer="HV_ZONE",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 must be in HV zone",
            ),
            EnclosingConstraint(
                outer="MCU_ZONE",
                inner=["U1"],
                tier=ConstraintTier.HARD,
                because="U1 must be in MCU zone",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        assignment = solver.solve()

        assert assignment.assignments["Q1"] == "HV_ZONE"
        assert assignment.assignments["U1"] == "MCU_ZONE"
        assert len(assignment.unassigned) == 0
        assert len(assignment.conflicts) == 0

    def test_solve_no_constraints(self):
        """Without constraints, assigns arbitrarily."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
        ]
        components = ["C1", "C2"]

        solver = ZoneSolver(zones=zones, constraints=[], components=components)
        assignment = solver.solve()

        # Should assign all components (arbitrarily to first zone)
        assert len(assignment.assignments) == 2
        assert assignment.assignments["C1"] == "ZONE_A"
        assert assignment.assignments["C2"] == "ZONE_A"

    def test_solve_conflicting_constraints(self):
        """Detects conflicting enclosing constraints."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
            Zone(name="ZONE_B", bounds=(60, 0, 110, 50)),
        ]
        components = ["Q1"]

        constraints = [
            EnclosingConstraint(
                outer="ZONE_A",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 must be in ZONE_A",
            ),
            EnclosingConstraint(
                outer="ZONE_B",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 must be in ZONE_B",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        assignment = solver.solve()

        # Should fail - Q1 can't be in two zones
        assert len(assignment.assignments) == 0
        assert "Q1" in assignment.unassigned
        assert len(assignment.conflicts) > 0

    def test_solve_multiple_components_same_zone(self):
        """Multiple components can be assigned to same zone."""
        zones = [
            Zone(name="HV_ZONE", bounds=(0, 0, 100, 100)),
        ]
        components = ["Q1", "Q2", "C1", "C2"]

        constraints = [
            EnclosingConstraint(
                outer="HV_ZONE",
                inner=["Q1", "Q2", "C1", "C2"],
                tier=ConstraintTier.HARD,
                because="All power components in HV zone",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        assignment = solver.solve()

        assert len(assignment.assignments) == 4
        for comp in components:
            assert assignment.assignments[comp] == "HV_ZONE"

    def test_solve_most_constrained_variable_heuristic(self):
        """Processes most constrained components first."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
            Zone(name="ZONE_B", bounds=(60, 0, 110, 50)),
            Zone(name="ZONE_C", bounds=(120, 0, 170, 50)),
        ]
        components = ["Q1", "Q2", "Q3"]

        constraints = [
            # Q1 has only 1 option (most constrained)
            EnclosingConstraint(
                outer="ZONE_A",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 must be in ZONE_A",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)

        # Check that solve processes Q1 first (most constrained)
        candidates = solver._build_candidates()
        assert len(candidates["Q1"]) == 1  # Most constrained
        assert len(candidates["Q2"]) == 3  # Least constrained

        assignment = solver.solve()
        assert assignment.assignments["Q1"] == "ZONE_A"

    def test_solve_with_no_valid_zones(self):
        """Component with no valid zones is unassigned."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
        ]
        components = ["Q1"]

        # Conflicting constraints: must be in non-existent zone
        constraints = [
            EnclosingConstraint(
                outer="NONEXISTENT_ZONE",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 must be in non-existent zone",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        assignment = solver.solve()

        assert "Q1" in assignment.unassigned
        assert len(assignment.conflicts) > 0

    def test_solve_empty_components(self):
        """Solver handles empty component list."""
        zones = [Zone(name="ZONE_A", bounds=(0, 0, 50, 50))]

        solver = ZoneSolver(zones=zones, constraints=[], components=[])
        assignment = solver.solve()

        assert len(assignment.assignments) == 0
        assert len(assignment.unassigned) == 0

    def test_solve_components_not_in_constraints(self):
        """Components not mentioned in constraints get arbitrary assignment."""
        zones = [
            Zone(name="ZONE_A", bounds=(0, 0, 50, 50)),
            Zone(name="ZONE_B", bounds=(60, 0, 110, 50)),
        ]
        components = ["Q1", "C_ORPHAN"]

        constraints = [
            EnclosingConstraint(
                outer="ZONE_A",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Q1 in ZONE_A",
            ),
        ]

        solver = ZoneSolver(zones=zones, constraints=constraints, components=components)
        assignment = solver.solve()

        assert assignment.assignments["Q1"] == "ZONE_A"
        # C_ORPHAN should be assigned to some zone
        assert "C_ORPHAN" in assignment.assignments
