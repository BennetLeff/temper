"""
Coverage-paydown tests for topological module functions.

Covers allowlisted public functions that are not already exercised
by existing test suites.
"""

from temper_placer.core.board import Zone
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.topological.graph import (
    TopologicalGraph,
    build_topological_graph,
)
from temper_placer.topological.initial_placement import (
    InitialPlacement,
    identify_clusters,
    place_cluster,
    place_components_in_zone,
    generate_initial_placement,
)
from temper_placer.topological.zone_solver import ZoneAssignment, ZoneSolver


class TestBuildTopologicalGraph:
    """Tests for build_topological_graph convenience function."""

    def test_build_from_pcl_adjacent(self):
        """build_topological_graph wraps from_pcl for adjacent constraints."""
        c1 = AdjacentConstraint(
            a="Q1", b="Q2", max_distance_mm=5.0,
            tier=ConstraintTier.HARD, because="Minimize commutation loop area",
        )
        pcl = ConstraintCollection(constraints=[c1])
        graph = build_topological_graph(pcl)

        assert isinstance(graph, TopologicalGraph)
        assert "Q1" in graph.graph.nodes()
        assert "Q2" in graph.graph.nodes()

    def test_build_from_pcl_separated(self):
        """build_topological_graph handles separated constraints."""
        c1 = SeparatedConstraint(
            a="HV", b="LV", min_distance_mm=10.0,
            tier=ConstraintTier.HARD, because="IEC 60335-1 reinforced isolation required",
        )
        pcl = ConstraintCollection(constraints=[c1])
        graph = build_topological_graph(pcl)

        neighbors = graph.get_neighbors("HV", edge_type="separated")
        assert "LV" in neighbors


class TestIdentifyClustersExtra:
    """Additional tests for identify_clusters beyond existing suite."""

    def test_empty_components(self):
        """Empty component list returns empty clusters."""
        graph = TopologicalGraph()
        clusters = identify_clusters(graph, [])
        assert clusters == []

    def test_isolated_components(self):
        """Components with no adjacency form separate clusters."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")
        graph.add_component("C")

        clusters = identify_clusters(graph, ["A", "B", "C"])
        # Each isolated = separate cluster
        assert len(clusters) == 3


class TestZoneSolverExtra:
    """Additional ZoneSolver tests beyond existing suite."""

    def test_solve_single_zone_single_component(self):
        """Single component assigned to only zone."""
        zones = [Zone(name="MAIN", bounds=(0, 0, 100, 100))]
        solver = ZoneSolver(
            zones=zones, constraints=[], components=["Q1"],
        )
        assignment = solver.solve()
        assert assignment.assignments.get("Q1") == "MAIN"
        assert len(assignment.unassigned) == 0

    def test_solve_no_zones(self):
        """No zones means all unassigned."""
        solver = ZoneSolver(zones=[], constraints=[], components=["Q1"])
        assignment = solver.solve()
        assert len(assignment.assignments) == 0
        assert "Q1" in assignment.unassigned


class TestPlaceComponentsInZoneExtra:
    """Additional tests for place_components_in_zone."""

    def test_empty_components(self):
        """Empty component list returns empty dict."""
        zone = Zone(name="TEST", bounds=(0, 0, 100, 100))
        positions = place_components_in_zone(zone, [], {})
        assert positions == {}


class TestPlaceClusterExtra:
    """Additional tests for place_cluster."""

    def test_empty_cluster(self):
        """Empty cluster returns empty dict."""
        zone = Zone(name="TEST", bounds=(0, 0, 100, 100))
        graph = TopologicalGraph()
        positions = place_cluster(
            cluster=set(),
            zone=zone,
            graph=graph,
            component_sizes={},
            cluster_index=0,
            total_clusters=1,
        )
        assert positions == {}


class TestGenerateInitialPlacementExtra:
    """Additional tests for generate_initial_placement."""

    def test_empty_assignments(self):
        """Empty zone assignments produced valid (empty) placement."""
        graph = TopologicalGraph()
        za = ZoneAssignment(assignments={}, unassigned=[], conflicts=[])
        zones = [Zone(name="MAIN", bounds=(0, 0, 100, 100))]
        sizes = {}

        result = generate_initial_placement(
            graph=graph,
            zone_assignment=za,
            zones=zones,
            component_sizes=sizes,
            force_iterations=0,
        )
        assert isinstance(result, InitialPlacement)
        assert result.positions == {}
        assert result.clusters == []
