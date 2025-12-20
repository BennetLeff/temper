"""Tests for initial placement generation from topological analysis.

This module tests the core placement logic that converts topological
relationships (zone assignments, adjacency clusters) into initial
(x, y) coordinates.

Following TDD: these tests are written BEFORE implementation.
"""

from __future__ import annotations

import math
import pytest
from dataclasses import dataclass

# These imports will fail until implementation exists
from temper_placer.core.board import Zone
from temper_placer.topological.graph import TopologicalGraph
from temper_placer.topological.zone_solver import ZoneAssignment

# Imports that will be implemented
from temper_placer.topological.initial_placement import (
    InitialPlacement,
    PlacementError,
    place_components_in_zone,
    identify_clusters,
    place_cluster,
    generate_initial_placement,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_zone() -> Zone:
    """A simple 100x100 zone at origin."""
    return Zone(
        name="TEST_ZONE",
        bounds=(0.0, 0.0, 100.0, 100.0),
    )


@pytest.fixture
def small_zone() -> Zone:
    """A small 20x20 zone."""
    return Zone(
        name="SMALL_ZONE",
        bounds=(0.0, 0.0, 20.0, 20.0),
    )


@pytest.fixture
def offset_zone() -> Zone:
    """A zone with non-zero origin."""
    return Zone(
        name="OFFSET_ZONE",
        bounds=(50.0, 50.0, 150.0, 150.0),
    )


@pytest.fixture
def multiple_zones() -> list[Zone]:
    """Multiple zones for multi-zone tests."""
    return [
        Zone(name="HV_ZONE", bounds=(0.0, 0.0, 50.0, 100.0)),
        Zone(name="LV_ZONE", bounds=(50.0, 0.0, 100.0, 100.0)),
        Zone(name="MCU_ZONE", bounds=(50.0, 100.0, 100.0, 150.0)),
    ]


@pytest.fixture
def simple_sizes() -> dict[str, tuple[float, float]]:
    """Simple component sizes (all 5x5mm)."""
    return {
        "C1": (5.0, 5.0),
        "C2": (5.0, 5.0),
        "C3": (5.0, 5.0),
        "C4": (5.0, 5.0),
        "C5": (5.0, 5.0),
        "A": (5.0, 5.0),  # For cluster tests
        "B": (5.0, 5.0),
        "C": (5.0, 5.0),
    }


@pytest.fixture
def varied_sizes() -> dict[str, tuple[float, float]]:
    """Varied component sizes."""
    return {
        "Q1": (10.0, 15.0),  # Large IGBT
        "Q2": (10.0, 15.0),
        "C1": (5.0, 5.0),  # Capacitor
        "C2": (5.0, 5.0),
        "U1": (8.0, 8.0),  # IC
        "R1": (2.0, 1.0),  # Small resistor
        "C_BUS": (8.0, 4.0),  # Bus capacitor
        "U_MCU": (10.0, 10.0),  # MCU
    }


@pytest.fixture
def empty_graph() -> TopologicalGraph:
    """Empty topological graph."""
    return TopologicalGraph()


@pytest.fixture
def simple_graph() -> TopologicalGraph:
    """Simple graph with two adjacent components."""
    graph = TopologicalGraph()
    graph.add_component("C1")
    graph.add_component("C2")
    graph.add_adjacency("C1", "C2", max_distance=10.0, constraint_id="adj_1")
    return graph


@pytest.fixture
def chain_graph() -> TopologicalGraph:
    """Graph with chain adjacency: A-B-C."""
    graph = TopologicalGraph()
    graph.add_component("A")
    graph.add_component("B")
    graph.add_component("C")
    graph.add_adjacency("A", "B", max_distance=10.0, constraint_id="adj_1")
    graph.add_adjacency("B", "C", max_distance=10.0, constraint_id="adj_2")
    return graph


@pytest.fixture
def separated_graph() -> TopologicalGraph:
    """Graph with separation constraint."""
    graph = TopologicalGraph()
    graph.add_component("HV1")
    graph.add_component("LV1")
    graph.add_separation("HV1", "LV1", min_distance=30.0, constraint_id="sep_1")
    return graph


@pytest.fixture
def mixed_graph() -> TopologicalGraph:
    """Graph with both adjacency and separation."""
    graph = TopologicalGraph()
    # Cluster 1: Q1-Q2-C_BUS (adjacent)
    graph.add_component("Q1")
    graph.add_component("Q2")
    graph.add_component("C_BUS")
    graph.add_adjacency("Q1", "Q2", max_distance=5.0, constraint_id="adj_1")
    graph.add_adjacency("Q1", "C_BUS", max_distance=8.0, constraint_id="adj_2")
    graph.add_adjacency("Q2", "C_BUS", max_distance=8.0, constraint_id="adj_3")

    # Cluster 2: U_MCU isolated
    graph.add_component("U_MCU")

    # Separation between clusters
    graph.add_separation("Q1", "U_MCU", min_distance=40.0, constraint_id="sep_1")
    graph.add_separation("Q2", "U_MCU", min_distance=40.0, constraint_id="sep_2")

    return graph


# =============================================================================
# Tests: InitialPlacement dataclass
# =============================================================================


class TestInitialPlacement:
    """Tests for InitialPlacement result dataclass."""

    def test_create_empty_placement(self):
        """Can create empty placement result."""
        placement = InitialPlacement(
            positions={},
            zone_assignments={},
            clusters=[],
        )

        assert placement.positions == {}
        assert placement.zone_assignments == {}
        assert placement.clusters == []
        assert placement.rotation_hints == {}
        assert placement.warnings == []

    def test_create_with_positions(self):
        """Can create placement with positions."""
        placement = InitialPlacement(
            positions={"C1": (10.0, 20.0), "C2": (30.0, 40.0)},
            zone_assignments={"C1": "ZONE_A", "C2": "ZONE_A"},
            clusters=[{"C1", "C2"}],
        )

        assert len(placement.positions) == 2
        assert placement.positions["C1"] == (10.0, 20.0)
        assert placement.positions["C2"] == (30.0, 40.0)

    def test_create_with_rotation_hints(self):
        """Can create placement with rotation hints."""
        placement = InitialPlacement(
            positions={"C1": (10.0, 20.0)},
            zone_assignments={"C1": "ZONE_A"},
            clusters=[{"C1"}],
            rotation_hints={"C1": 90},
        )

        assert placement.rotation_hints["C1"] == 90

    def test_create_with_warnings(self):
        """Can create placement with warnings."""
        placement = InitialPlacement(
            positions={"C1": (10.0, 20.0)},
            zone_assignments={"C1": "ZONE_A"},
            clusters=[{"C1"}],
            warnings=["Component C1 placed near zone boundary"],
        )

        assert len(placement.warnings) == 1
        assert "C1" in placement.warnings[0]


# =============================================================================
# Tests: PlacementError exception
# =============================================================================


class TestPlacementError:
    """Tests for PlacementError exception."""

    def test_placement_error_message(self):
        """PlacementError carries message."""
        with pytest.raises(PlacementError) as exc_info:
            raise PlacementError("Zone too small for components")

        assert "Zone too small" in str(exc_info.value)

    def test_placement_error_is_exception(self):
        """PlacementError is an Exception subclass."""
        assert issubclass(PlacementError, Exception)


# =============================================================================
# Tests: place_components_in_zone
# =============================================================================


class TestPlaceComponentsInZone:
    """Tests for zone-based component placement."""

    def test_place_single_component_at_center(self, simple_zone, simple_sizes):
        """Single component placed at zone center."""
        positions = place_components_in_zone(
            zone=simple_zone,
            components=["C1"],
            component_sizes=simple_sizes,
        )

        assert len(positions) == 1
        x, y = positions["C1"]

        # Zone center is (50, 50)
        assert x == pytest.approx(50.0, abs=1.0)
        assert y == pytest.approx(50.0, abs=1.0)

    def test_place_two_components_opposite(self, simple_zone, simple_sizes):
        """Two components placed on opposite sides of center."""
        positions = place_components_in_zone(
            zone=simple_zone,
            components=["C1", "C2"],
            component_sizes=simple_sizes,
        )

        assert len(positions) == 2

        x1, y1 = positions["C1"]
        x2, y2 = positions["C2"]

        # Should be roughly opposite (180° apart on circle)
        # Distance from center should be similar
        center = (50.0, 50.0)
        dist1 = math.sqrt((x1 - center[0]) ** 2 + (y1 - center[1]) ** 2)
        dist2 = math.sqrt((x2 - center[0]) ** 2 + (y2 - center[1]) ** 2)

        assert dist1 == pytest.approx(dist2, rel=0.1)

        # Distance between them should be roughly 2 * radius
        dist_between = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        assert dist_between == pytest.approx(2 * dist1, rel=0.1)

    def test_place_multiple_components_circular(self, simple_zone, simple_sizes):
        """Multiple components placed in circular arrangement."""
        positions = place_components_in_zone(
            zone=simple_zone,
            components=["C1", "C2", "C3", "C4"],
            component_sizes=simple_sizes,
        )

        assert len(positions) == 4

        center = (50.0, 50.0)

        # All components should be at similar distance from center
        distances = []
        for ref in ["C1", "C2", "C3", "C4"]:
            x, y = positions[ref]
            dist = math.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)
            distances.append(dist)

        # All distances should be approximately equal
        avg_dist = sum(distances) / len(distances)
        for dist in distances:
            assert dist == pytest.approx(avg_dist, rel=0.1)

    def test_place_components_within_zone_bounds(self, simple_zone, simple_sizes):
        """All components placed within zone bounds."""
        positions = place_components_in_zone(
            zone=simple_zone,
            components=["C1", "C2", "C3", "C4", "C5"],
            component_sizes=simple_sizes,
        )

        x_min, y_min, x_max, y_max = simple_zone.bounds

        for ref, (x, y) in positions.items():
            w, h = simple_sizes[ref]
            # Center position, so account for half-width/height
            assert x - w / 2 >= x_min, f"{ref} outside left bound"
            assert x + w / 2 <= x_max, f"{ref} outside right bound"
            assert y - h / 2 >= y_min, f"{ref} outside bottom bound"
            assert y + h / 2 <= y_max, f"{ref} outside top bound"

    def test_place_in_offset_zone(self, offset_zone, simple_sizes):
        """Components placed correctly in zone with non-zero origin."""
        positions = place_components_in_zone(
            zone=offset_zone,
            components=["C1"],
            component_sizes=simple_sizes,
        )

        x, y = positions["C1"]

        # Zone is (50, 50) to (150, 150), center at (100, 100)
        assert x == pytest.approx(100.0, abs=1.0)
        assert y == pytest.approx(100.0, abs=1.0)

    def test_place_empty_components_list(self, simple_zone, simple_sizes):
        """Empty component list returns empty positions."""
        positions = place_components_in_zone(
            zone=simple_zone,
            components=[],
            component_sizes=simple_sizes,
        )

        assert positions == {}

    def test_zone_too_small_raises_error(self, small_zone):
        """Zone smaller than component raises PlacementError."""
        large_sizes = {"C1": (25.0, 25.0)}  # Larger than 20x20 zone

        with pytest.raises(PlacementError) as exc_info:
            place_components_in_zone(
                zone=small_zone,
                components=["C1"],
                component_sizes=large_sizes,
            )

        assert "too small" in str(exc_info.value).lower()

    def test_multiple_large_components_raises_error(self, small_zone):
        """Multiple components that don't fit raise PlacementError."""
        sizes = {"C1": (15.0, 15.0), "C2": (15.0, 15.0)}  # Two 15x15 in 20x20

        with pytest.raises(PlacementError) as exc_info:
            place_components_in_zone(
                zone=small_zone,
                components=["C1", "C2"],
                component_sizes=sizes,
            )

        assert "too small" in str(exc_info.value).lower() or "fit" in str(exc_info.value).lower()

    def test_deterministic_output(self, simple_zone, simple_sizes):
        """Same input produces identical output."""
        positions1 = place_components_in_zone(
            zone=simple_zone,
            components=["C1", "C2", "C3"],
            component_sizes=simple_sizes,
        )

        positions2 = place_components_in_zone(
            zone=simple_zone,
            components=["C1", "C2", "C3"],
            component_sizes=simple_sizes,
        )

        assert positions1 == positions2


# =============================================================================
# Tests: identify_clusters
# =============================================================================


class TestIdentifyClusters:
    """Tests for cluster identification from topological graph."""

    def test_single_isolated_component(self, empty_graph):
        """Single component forms singleton cluster."""
        empty_graph.add_component("C1")

        clusters = identify_clusters(
            graph=empty_graph,
            components=["C1"],
        )

        assert len(clusters) == 1
        assert clusters[0] == {"C1"}

    def test_two_adjacent_components_one_cluster(self, simple_graph):
        """Two adjacent components form one cluster."""
        clusters = identify_clusters(
            graph=simple_graph,
            components=["C1", "C2"],
        )

        assert len(clusters) == 1
        assert clusters[0] == {"C1", "C2"}

    def test_transitive_adjacency_one_cluster(self, chain_graph):
        """A-B-C (transitive adjacency) forms one cluster."""
        clusters = identify_clusters(
            graph=chain_graph,
            components=["A", "B", "C"],
        )

        assert len(clusters) == 1
        assert clusters[0] == {"A", "B", "C"}

    def test_separate_components_multiple_clusters(self):
        """Components without adjacency form separate clusters."""
        graph = TopologicalGraph()
        graph.add_component("C1")
        graph.add_component("C2")
        graph.add_component("C3")
        # No adjacency edges

        clusters = identify_clusters(
            graph=graph,
            components=["C1", "C2", "C3"],
        )

        assert len(clusters) == 3
        # Each in its own cluster
        cluster_sets = [c for c in clusters]
        assert {"C1"} in cluster_sets
        assert {"C2"} in cluster_sets
        assert {"C3"} in cluster_sets

    def test_mixed_clusters(self, mixed_graph):
        """Mixed graph produces correct clusters."""
        clusters = identify_clusters(
            graph=mixed_graph,
            components=["Q1", "Q2", "C_BUS", "U_MCU"],
        )

        assert len(clusters) == 2

        # One cluster should have Q1, Q2, C_BUS
        # Other should have U_MCU
        cluster_sizes = sorted([len(c) for c in clusters])
        assert cluster_sizes == [1, 3]

        # Find the large cluster
        large_cluster = max(clusters, key=len)
        assert large_cluster == {"Q1", "Q2", "C_BUS"}

    def test_component_not_in_graph(self, simple_graph):
        """Component not in graph forms singleton cluster."""
        clusters = identify_clusters(
            graph=simple_graph,
            components=["C1", "C2", "C3"],  # C3 not in graph
        )

        # C1-C2 in one cluster, C3 alone
        assert len(clusters) == 2

    def test_empty_components_list(self, simple_graph):
        """Empty components list returns empty clusters."""
        clusters = identify_clusters(
            graph=simple_graph,
            components=[],
        )

        assert clusters == []

    def test_circular_adjacency(self):
        """Circular adjacency (A-B-C-A) forms one cluster."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")
        graph.add_component("C")
        graph.add_adjacency("A", "B", max_distance=10.0, constraint_id="1")
        graph.add_adjacency("B", "C", max_distance=10.0, constraint_id="2")
        graph.add_adjacency("C", "A", max_distance=10.0, constraint_id="3")

        clusters = identify_clusters(
            graph=graph,
            components=["A", "B", "C"],
        )

        assert len(clusters) == 1
        assert clusters[0] == {"A", "B", "C"}

    def test_separation_does_not_create_cluster(self, separated_graph):
        """Separation constraint doesn't create cluster."""
        clusters = identify_clusters(
            graph=separated_graph,
            components=["HV1", "LV1"],
        )

        # Separation is not adjacency - they should be in separate clusters
        assert len(clusters) == 2


# =============================================================================
# Tests: place_cluster
# =============================================================================


class TestPlaceCluster:
    """Tests for placing a cluster within a zone."""

    def test_single_component_cluster(self, simple_zone, simple_sizes, simple_graph):
        """Single component cluster placed at zone center."""
        positions = place_cluster(
            cluster={"C1"},
            zone=simple_zone,
            graph=simple_graph,
            component_sizes=simple_sizes,
            cluster_index=0,
            total_clusters=1,
        )

        assert len(positions) == 1
        x, y = positions["C1"]

        # Single cluster in zone should be near center
        assert 25.0 < x < 75.0
        assert 25.0 < y < 75.0

    def test_adjacent_components_placed_close(self, simple_zone, simple_sizes, simple_graph):
        """Adjacent components in cluster are placed close together."""
        positions = place_cluster(
            cluster={"C1", "C2"},
            zone=simple_zone,
            graph=simple_graph,
            component_sizes=simple_sizes,
            cluster_index=0,
            total_clusters=1,
        )

        assert len(positions) == 2

        x1, y1 = positions["C1"]
        x2, y2 = positions["C2"]

        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

        # Should be close (adjacency constraint was max_distance=10)
        assert distance < 20.0  # Some slack for initial placement

    def test_multiple_clusters_in_zone(self, simple_zone, simple_sizes):
        """Multiple clusters get separate regions in zone."""
        graph = TopologicalGraph()
        graph.add_component("A")
        graph.add_component("B")

        # Place first cluster
        positions1 = place_cluster(
            cluster={"A"},
            zone=simple_zone,
            graph=graph,
            component_sizes=simple_sizes,
            cluster_index=0,
            total_clusters=2,
        )

        # Place second cluster
        positions2 = place_cluster(
            cluster={"B"},
            zone=simple_zone,
            graph=graph,
            component_sizes=simple_sizes,
            cluster_index=1,
            total_clusters=2,
        )

        x1, y1 = positions1["A"]
        x2, y2 = positions2["B"]

        # They should be in different regions (some distance apart)
        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        assert distance > 10.0  # Should be separated

    def test_cluster_respects_zone_bounds(self, simple_zone, varied_sizes, mixed_graph):
        """All cluster components placed within zone bounds."""
        positions = place_cluster(
            cluster={"Q1", "Q2", "C_BUS"},
            zone=simple_zone,
            graph=mixed_graph,
            component_sizes=varied_sizes,
            cluster_index=0,
            total_clusters=1,
        )

        x_min, y_min, x_max, y_max = simple_zone.bounds

        for ref, (x, y) in positions.items():
            w, h = varied_sizes[ref]
            assert x - w / 2 >= x_min
            assert x + w / 2 <= x_max
            assert y - h / 2 >= y_min
            assert y + h / 2 <= y_max


# =============================================================================
# Tests: generate_initial_placement (integration)
# =============================================================================


class TestGenerateInitialPlacement:
    """Integration tests for full placement generation."""

    def test_simple_single_zone(self, simple_zone, simple_sizes, simple_graph):
        """Simple case: two components in one zone."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
        )

        assert len(placement.positions) == 2
        assert "C1" in placement.positions
        assert "C2" in placement.positions
        assert placement.zone_assignments == {"C1": "TEST_ZONE", "C2": "TEST_ZONE"}
        assert len(placement.clusters) == 1

    def test_multiple_zones(self, multiple_zones, varied_sizes, mixed_graph):
        """Components placed in multiple zones."""
        assignment = ZoneAssignment(
            assignments={
                "Q1": "HV_ZONE",
                "Q2": "HV_ZONE",
                "C_BUS": "HV_ZONE",
                "U_MCU": "MCU_ZONE",
            },
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=mixed_graph,
            zone_assignment=assignment,
            zones=multiple_zones,
            component_sizes=varied_sizes,
        )

        assert len(placement.positions) == 4

        # HV components should be in HV_ZONE bounds
        hv_zone = multiple_zones[0]
        for ref in ["Q1", "Q2", "C_BUS"]:
            x, y = placement.positions[ref]
            assert hv_zone.contains_point(x, y), f"{ref} not in HV_ZONE"

        # MCU should be in MCU_ZONE
        mcu_zone = multiple_zones[2]
        x, y = placement.positions["U_MCU"]
        assert mcu_zone.contains_point(x, y), "U_MCU not in MCU_ZONE"

    def test_separated_components_apart(self, multiple_zones, varied_sizes, mixed_graph):
        """Separated components are placed far apart."""
        assignment = ZoneAssignment(
            assignments={
                "Q1": "HV_ZONE",
                "Q2": "HV_ZONE",
                "C_BUS": "HV_ZONE",
                "U_MCU": "MCU_ZONE",
            },
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=mixed_graph,
            zone_assignment=assignment,
            zones=multiple_zones,
            component_sizes=varied_sizes,
            force_iterations=100,
        )

        # Q1 and U_MCU have separation constraint of 40mm
        x1, y1 = placement.positions["Q1"]
        x2, y2 = placement.positions["U_MCU"]

        distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

        # They're in different zones so distance should be substantial
        # (zones are at least 50mm apart)
        assert distance > 30.0

    def test_unassigned_components_raises_error(self, simple_zone, simple_sizes, simple_graph):
        """Unassigned components raise PlacementError."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE"},  # C2 not assigned
            unassigned=["C2"],
            conflicts=[],
        )

        with pytest.raises(PlacementError) as exc_info:
            generate_initial_placement(
                graph=simple_graph,
                zone_assignment=assignment,
                zones=[simple_zone],
                component_sizes=simple_sizes,
            )

        assert "C2" in str(exc_info.value) or "unassigned" in str(exc_info.value).lower()

    def test_missing_zone_raises_error(self, simple_zone, simple_sizes, simple_graph):
        """Assignment to non-existent zone raises PlacementError."""
        assignment = ZoneAssignment(
            assignments={"C1": "NONEXISTENT_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        with pytest.raises(PlacementError) as exc_info:
            generate_initial_placement(
                graph=simple_graph,
                zone_assignment=assignment,
                zones=[simple_zone],  # Only TEST_ZONE exists
                component_sizes=simple_sizes,
            )

        assert (
            "NONEXISTENT_ZONE" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
        )

    def test_no_zones_uses_board_bounds(self, simple_sizes, simple_graph):
        """No zones falls back to board bounds."""
        assignment = ZoneAssignment(
            assignments={},  # No zone assignments
            unassigned=["C1", "C2"],  # All unassigned
            conflicts=[],
        )

        # This should work if we provide board_bounds
        placement = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=ZoneAssignment(
                assignments={"C1": "_BOARD_", "C2": "_BOARD_"},
                unassigned=[],
                conflicts=[],
            ),
            zones=[],
            component_sizes=simple_sizes,
            board_bounds=(0.0, 0.0, 100.0, 100.0),
        )

        assert len(placement.positions) == 2

    def test_empty_components(self, simple_zone):
        """No components produces empty placement."""
        assignment = ZoneAssignment(
            assignments={},
            unassigned=[],
            conflicts=[],
        )

        graph = TopologicalGraph()

        placement = generate_initial_placement(
            graph=graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes={},
        )

        assert placement.positions == {}
        assert placement.clusters == []

    def test_deterministic_output(self, simple_zone, simple_sizes, simple_graph):
        """Same input produces identical output."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        placement1 = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
        )

        placement2 = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
        )

        assert placement1.positions == placement2.positions
        assert placement1.clusters == placement2.clusters

    def test_clusters_populated(self, simple_zone, simple_sizes, simple_graph):
        """Clusters field is populated correctly."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
        )

        # C1 and C2 are adjacent, should be in same cluster
        assert len(placement.clusters) == 1
        assert placement.clusters[0] == {"C1", "C2"}

    def test_zone_assignments_populated(self, multiple_zones, varied_sizes, mixed_graph):
        """Zone assignments are populated in result."""
        assignment = ZoneAssignment(
            assignments={
                "Q1": "HV_ZONE",
                "Q2": "HV_ZONE",
                "C_BUS": "HV_ZONE",
                "U_MCU": "MCU_ZONE",
            },
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=mixed_graph,
            zone_assignment=assignment,
            zones=multiple_zones,
            component_sizes=varied_sizes,
        )

        assert placement.zone_assignments["Q1"] == "HV_ZONE"
        assert placement.zone_assignments["U_MCU"] == "MCU_ZONE"

    def test_force_iterations_parameter(self, simple_zone, simple_sizes, simple_graph):
        """force_iterations parameter is respected."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        # Zero iterations - no refinement
        placement_no_refine = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
            force_iterations=0,
        )

        # Many iterations - more refinement
        placement_refined = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
            force_iterations=200,
        )

        # Both should produce valid positions
        assert len(placement_no_refine.positions) == 2
        assert len(placement_refined.positions) == 2

    def test_backend_parameter(self, simple_zone, simple_sizes, simple_graph):
        """backend parameter is accepted (numpy/jax)."""
        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        # NumPy backend
        placement_numpy = generate_initial_placement(
            graph=simple_graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=simple_sizes,
            backend="numpy",
        )

        assert len(placement_numpy.positions) == 2

        # JAX backend (if available)
        try:
            placement_jax = generate_initial_placement(
                graph=simple_graph,
                zone_assignment=assignment,
                zones=[simple_zone],
                component_sizes=simple_sizes,
                backend="jax",
            )
            assert len(placement_jax.positions) == 2
        except ImportError:
            pytest.skip("JAX not available")


# =============================================================================
# Tests: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_very_large_component_count(self, simple_zone):
        """Handle many components without error."""
        components = [f"C{i}" for i in range(100)]
        sizes = {c: (2.0, 2.0) for c in components}

        graph = TopologicalGraph()
        for c in components:
            graph.add_component(c)

        assignment = ZoneAssignment(
            assignments={c: "TEST_ZONE" for c in components},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=sizes,
        )

        assert len(placement.positions) == 100

    def test_zero_size_component(self, simple_zone):
        """Handle zero-size component (point)."""
        sizes = {"C1": (0.0, 0.0)}

        graph = TopologicalGraph()
        graph.add_component("C1")

        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=graph,
            zone_assignment=assignment,
            zones=[simple_zone],
            component_sizes=sizes,
        )

        assert len(placement.positions) == 1

    def test_negative_zone_bounds(self):
        """Handle zone with negative coordinates."""
        zone = Zone(
            name="NEGATIVE_ZONE",
            bounds=(-50.0, -50.0, 50.0, 50.0),
        )
        sizes = {"C1": (5.0, 5.0)}

        graph = TopologicalGraph()
        graph.add_component("C1")

        assignment = ZoneAssignment(
            assignments={"C1": "NEGATIVE_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=graph,
            zone_assignment=assignment,
            zones=[zone],
            component_sizes=sizes,
        )

        x, y = placement.positions["C1"]
        assert zone.contains_point(x, y)

    def test_very_elongated_zone(self):
        """Handle very elongated (non-square) zone."""
        zone = Zone(
            name="ELONGATED",
            bounds=(0.0, 0.0, 200.0, 10.0),  # 200x10
        )
        sizes = {"C1": (5.0, 5.0), "C2": (5.0, 5.0)}

        graph = TopologicalGraph()
        graph.add_component("C1")
        graph.add_component("C2")

        assignment = ZoneAssignment(
            assignments={"C1": "ELONGATED", "C2": "ELONGATED"},
            unassigned=[],
            conflicts=[],
        )

        placement = generate_initial_placement(
            graph=graph,
            zone_assignment=assignment,
            zones=[zone],
            component_sizes=sizes,
        )

        for ref, (x, y) in placement.positions.items():
            assert zone.contains_point(x, y), f"{ref} outside elongated zone"

    def test_component_size_missing(self, simple_zone, simple_graph):
        """Missing component size raises error."""
        sizes = {"C1": (5.0, 5.0)}  # C2 missing

        assignment = ZoneAssignment(
            assignments={"C1": "TEST_ZONE", "C2": "TEST_ZONE"},
            unassigned=[],
            conflicts=[],
        )

        with pytest.raises((KeyError, PlacementError)):
            generate_initial_placement(
                graph=simple_graph,
                zone_assignment=assignment,
                zones=[simple_zone],
                component_sizes=sizes,
            )

    def test_conflicting_assignment(self, simple_zone, simple_sizes, simple_graph):
        """ZoneAssignment with conflicts is rejected."""
        assignment = ZoneAssignment(
            assignments={},
            unassigned=[],
            conflicts=[("C1", "zone_assignment", "Conflicting constraints")],
        )

        with pytest.raises(PlacementError) as exc_info:
            generate_initial_placement(
                graph=simple_graph,
                zone_assignment=assignment,
                zones=[simple_zone],
                component_sizes=simple_sizes,
            )

        assert "conflict" in str(exc_info.value).lower()
