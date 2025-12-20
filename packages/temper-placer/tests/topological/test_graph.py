"""Tests for topological graph data structure."""

import pytest
from temper_placer.topological.graph import (
    TopologicalGraph,
    TopologicalNode,
    TopologicalEdge,
)


class TestTopologicalNode:
    """Tests for TopologicalNode data structure."""

    def test_create_component_node(self):
        """Component node has required fields."""
        node = TopologicalNode(
            id="Q1",
            node_type="component",
            properties={"footprint": "TO-247"},
        )
        assert node.id == "Q1"
        assert node.node_type == "component"
        assert node.properties["footprint"] == "TO-247"

    def test_create_group_node(self):
        """Group node has required fields."""
        node = TopologicalNode(
            id="loop_commutation",
            node_type="group",
            properties={"members": ["Q1", "Q2", "C1"]},
        )
        assert node.id == "loop_commutation"
        assert node.node_type == "group"

    def test_default_properties(self):
        """Properties default to empty dict."""
        node = TopologicalNode(id="U1", node_type="component")
        assert node.properties == {}


class TestTopologicalEdge:
    """Tests for TopologicalEdge data structure."""

    def test_create_adjacency_edge(self):
        """Adjacency edge stores max distance."""
        edge = TopologicalEdge(
            source="Q1",
            target="Q2",
            edge_type="adjacent",
            constraint_id="constraint_001",
            distance=5.0,
        )
        assert edge.source == "Q1"
        assert edge.target == "Q2"
        assert edge.edge_type == "adjacent"
        assert edge.distance == 5.0

    def test_create_separation_edge(self):
        """Separation edge stores min distance."""
        edge = TopologicalEdge(
            source="HV_ZONE",
            target="MCU_ZONE",
            edge_type="separated",
            constraint_id="constraint_002",
            distance=10.0,
        )
        assert edge.edge_type == "separated"
        assert edge.distance == 10.0

    def test_default_distance_none(self):
        """Distance defaults to None for membership edges."""
        edge = TopologicalEdge(
            source="Q1",
            target="loop_commutation",
            edge_type="member_of",
            constraint_id="auto_generated",
        )
        assert edge.distance is None


class TestTopologicalGraph:
    """Tests for TopologicalGraph."""

    def test_create_empty_graph(self):
        """Graph initializes empty."""
        graph = TopologicalGraph()
        assert len(list(graph.graph.nodes())) == 0
        assert len(list(graph.graph.edges())) == 0

    def test_add_component(self):
        """Can add component nodes."""
        graph = TopologicalGraph()
        graph.add_component("Q1", properties={"footprint": "TO-247"})

        assert "Q1" in graph.graph.nodes()
        node_data = graph.graph.nodes["Q1"]
        assert node_data["node_type"] == "component"
        assert node_data["properties"]["footprint"] == "TO-247"

    def test_add_multiple_components(self):
        """Can add multiple components."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_component("C1")

        assert len(list(graph.graph.nodes())) == 3
        assert "Q1" in graph.graph.nodes()
        assert "Q2" in graph.graph.nodes()
        assert "C1" in graph.graph.nodes()

    def test_add_group(self):
        """Can add group nodes with members."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_component("C1")

        graph.add_group("loop_commutation", members=["Q1", "Q2", "C1"])

        # Group node exists
        assert "loop_commutation" in graph.graph.nodes()
        node_data = graph.graph.nodes["loop_commutation"]
        assert node_data["node_type"] == "group"
        assert node_data["members"] == ["Q1", "Q2", "C1"]

        # Membership edges created
        edges = list(graph.graph.edges(data=True))
        member_edges = [(u, v, d) for u, v, d in edges if d.get("edge_type") == "member_of"]
        assert len(member_edges) == 3

    def test_add_adjacency(self):
        """Can add adjacency constraint edges."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")

        graph.add_adjacency("Q1", "Q2", max_distance=5.0, constraint_id="c1")

        # Check forward edge
        edges = list(graph.graph.edges("Q1", data=True))
        adj_edges = [
            (u, v, d) for u, v, d in edges if d.get("edge_type") == "adjacent" and v == "Q2"
        ]
        assert len(adj_edges) == 1
        assert adj_edges[0][2]["distance"] == 5.0

        # Check reverse edge (adjacency is symmetric)
        edges = list(graph.graph.edges("Q2", data=True))
        adj_edges = [
            (u, v, d) for u, v, d in edges if d.get("edge_type") == "adjacent" and v == "Q1"
        ]
        assert len(adj_edges) == 1

    def test_add_separation(self):
        """Can add separation constraint edges."""
        graph = TopologicalGraph()
        graph.add_component("HV")
        graph.add_component("MCU")

        graph.add_separation("HV", "MCU", min_distance=10.0, constraint_id="c2")

        edges = list(graph.graph.edges("HV", data=True))
        sep_edges = [(u, v, d) for u, v, d in edges if d.get("edge_type") == "separated"]
        assert len(sep_edges) == 1
        assert sep_edges[0][2]["distance"] == 10.0

    def test_get_neighbors_all(self):
        """Can get all neighbors of a node."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_component("C1")

        graph.add_adjacency("Q1", "Q2", 5.0, "c1")
        graph.add_adjacency("Q1", "C1", 3.0, "c2")

        neighbors = graph.get_neighbors("Q1")
        assert set(neighbors) == {"Q2", "C1"}

    def test_get_neighbors_filtered_by_type(self):
        """Can filter neighbors by edge type."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_component("Q3")

        graph.add_adjacency("Q1", "Q2", 5.0, "c1")
        graph.add_separation("Q1", "Q3", 10.0, "c2")

        # Only adjacent neighbors
        adj_neighbors = graph.get_neighbors("Q1", edge_type="adjacent")
        assert adj_neighbors == ["Q2"]

        # Only separated neighbors
        sep_neighbors = graph.get_neighbors("Q1", edge_type="separated")
        assert sep_neighbors == ["Q3"]

    def test_get_adjacency_cluster_single(self):
        """Single isolated component forms cluster of size 1."""
        graph = TopologicalGraph()
        graph.add_component("Q1")

        cluster = graph.get_adjacency_cluster("Q1")
        assert cluster == {"Q1"}

    def test_get_adjacency_cluster_pair(self):
        """Two adjacent components form cluster of size 2."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_adjacency("Q1", "Q2", 5.0, "c1")

        cluster = graph.get_adjacency_cluster("Q1")
        assert cluster == {"Q1", "Q2"}

    def test_get_adjacency_cluster_transitive(self):
        """Adjacency is transitive - forms connected component."""
        graph = TopologicalGraph()
        for comp in ["Q1", "Q2", "C1", "C2"]:
            graph.add_component(comp)

        # Q1 -- Q2 -- C1 -- C2 (chain)
        graph.add_adjacency("Q1", "Q2", 5.0, "c1")
        graph.add_adjacency("Q2", "C1", 3.0, "c2")
        graph.add_adjacency("C1", "C2", 3.0, "c3")

        cluster = graph.get_adjacency_cluster("Q1")
        assert cluster == {"Q1", "Q2", "C1", "C2"}

    def test_get_adjacency_cluster_ignores_separation(self):
        """Separation edges don't contribute to adjacency clusters."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_component("Q3")

        graph.add_adjacency("Q1", "Q2", 5.0, "c1")
        graph.add_separation("Q1", "Q3", 10.0, "c2")

        cluster = graph.get_adjacency_cluster("Q1")
        assert cluster == {"Q1", "Q2"}  # Q3 not included

    def test_find_separation_conflicts_none(self):
        """No conflicts when constraints are consistent."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")
        graph.add_adjacency("Q1", "Q2", 5.0, "c1")

        conflicts = graph.find_separation_conflicts()
        assert len(conflicts) == 0

    def test_find_separation_conflicts_basic(self):
        """Detects adjacent + separated conflict."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")

        # Want Q1-Q2 ≤ 5mm AND ≥ 10mm (impossible!)
        graph.add_adjacency("Q1", "Q2", max_distance=5.0, constraint_id="c1")
        graph.add_separation("Q1", "Q2", min_distance=10.0, constraint_id="c2")

        conflicts = graph.find_separation_conflicts()
        assert len(conflicts) == 1

        comp_a, comp_b, reason = conflicts[0]
        assert {comp_a, comp_b} == {"Q1", "Q2"}
        assert "5.0" in reason  # Max distance
        assert "10.0" in reason  # Min distance

    def test_find_separation_conflicts_compatible(self):
        """Adjacent ≤ 5mm and separated ≥ 2mm is OK."""
        graph = TopologicalGraph()
        graph.add_component("Q1")
        graph.add_component("Q2")

        # 2mm ≤ distance ≤ 5mm is feasible
        graph.add_adjacency("Q1", "Q2", max_distance=5.0, constraint_id="c1")
        graph.add_separation("Q1", "Q2", min_distance=2.0, constraint_id="c2")

        conflicts = graph.find_separation_conflicts()
        assert len(conflicts) == 0


class TestBuildTopologicalGraph:
    """Tests for building graph from PCL constraints."""

    def test_build_from_empty_pcl(self):
        """Empty PCL produces empty graph."""
        from temper_placer.pcl.parser import ConstraintCollection

        pcl = ConstraintCollection(constraints=[])
        graph = TopologicalGraph.from_pcl(pcl)

        assert len(list(graph.graph.nodes())) == 0

    def test_build_from_adjacent_constraints(self):
        """Adjacent constraints create nodes and edges."""
        from temper_placer.pcl.constraints import (
            AdjacentConstraint,
            ConstraintTier,
        )
        from temper_placer.pcl.parser import ConstraintCollection

        c1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop",
        )
        pcl = ConstraintCollection(constraints=[c1])

        graph = TopologicalGraph.from_pcl(pcl)

        # Nodes created
        assert "Q1" in graph.graph.nodes()
        assert "Q2" in graph.graph.nodes()

        # Adjacency edge created
        neighbors = graph.get_neighbors("Q1", edge_type="adjacent")
        assert "Q2" in neighbors

    def test_build_from_separated_constraints(self):
        """Separated constraints create separation edges."""
        from temper_placer.pcl.constraints import (
            SeparatedConstraint,
            ConstraintTier,
        )
        from temper_placer.pcl.parser import ConstraintCollection

        c1 = SeparatedConstraint(
            a="HV_ZONE",
            b="MCU_ZONE",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="IEC 60335-1 reinforced isolation",
        )
        pcl = ConstraintCollection(constraints=[c1])

        graph = TopologicalGraph.from_pcl(pcl)

        neighbors = graph.get_neighbors("HV_ZONE", edge_type="separated")
        assert "MCU_ZONE" in neighbors

    def test_build_extracts_all_component_refs(self):
        """Graph includes all components mentioned in constraints."""
        from temper_placer.pcl.constraints import (
            AdjacentConstraint,
            AlignedConstraint,
            ConstraintTier,
            Axis,
        )
        from temper_placer.pcl.parser import ConstraintCollection

        c1 = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Test constraint for graph building",
        )
        c2 = AlignedConstraint(
            components=["C1", "C2", "C3"],
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because="Aesthetic alignment for decoupling caps",
        )
        pcl = ConstraintCollection(constraints=[c1, c2])

        graph = TopologicalGraph.from_pcl(pcl)

        nodes = set(graph.graph.nodes())
        assert nodes >= {"Q1", "Q2", "C1", "C2", "C3"}
