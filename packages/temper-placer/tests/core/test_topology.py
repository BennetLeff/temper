"""Tests for core.topology module."""

import pytest

from temper_placer.core.topology import (
    ComponentCluster,
    TopologicalGraph,
    TopologicalSolution,
    UnionFind,
)


class TestTopologicalGraph:
    """Tests for TopologicalGraph."""

    def test_add_node(self):
        g = TopologicalGraph()
        g.add_node("U1")
        assert "U1" in g.nodes
        assert len(g.nodes) == 1

    def test_add_node_idempotent(self):
        g = TopologicalGraph()
        g.add_node("U1")
        g.add_node("U1")
        assert g.nodes == ["U1"]

    def test_add_adjacency(self):
        g = TopologicalGraph()
        g.add_adjacency("U1", "U2", 10.0)
        assert len(g.nodes) == 2
        assert ("U1", "U2", 10.0) in g.adjacency_edges

    def test_add_separation(self):
        g = TopologicalGraph()
        g.add_separation("U1", "U2", 5.0)
        assert len(g.nodes) == 2
        assert ("U1", "U2", 5.0) in g.separation_edges

    def test_add_enclosure(self):
        g = TopologicalGraph()
        g.add_enclosure("Zone1", "U1")
        assert "Zone1" in g.enclosure
        assert "U1" in g.enclosure["Zone1"]

    def test_add_enclosure_multiple(self):
        g = TopologicalGraph()
        g.add_enclosure("Zone1", "U1")
        g.add_enclosure("Zone1", "U2")
        assert g.enclosure["Zone1"] == ["U1", "U2"]

    def test_get_clusters_single_component(self):
        g = TopologicalGraph()
        g.add_node("U1")
        clusters = g.get_clusters()
        assert len(clusters) == 1
        assert clusters[0] == {"U1"}

    def test_get_clusters_connected(self):
        g = TopologicalGraph()
        g.add_adjacency("U1", "U2", 10.0)
        g.add_adjacency("U2", "U3", 10.0)
        clusters = g.get_clusters()
        # All three are connected transitively
        assert len(clusters) == 1
        assert clusters[0] == {"U1", "U2", "U3"}

    def test_get_clusters_disconnected(self):
        g = TopologicalGraph()
        g.add_adjacency("U1", "U2", 10.0)
        g.add_adjacency("U3", "U4", 10.0)
        clusters = g.get_clusters()
        assert len(clusters) == 2
        cluster_sets = [c for c in clusters]
        assert {"U1", "U2"} in cluster_sets
        assert {"U3", "U4"} in cluster_sets

    def test_empty_graph_clusters(self):
        g = TopologicalGraph()
        clusters = g.get_clusters()
        assert clusters == []


class TestUnionFind:
    """Tests for UnionFind."""

    def test_find_new_element(self):
        uf = UnionFind()
        assert uf.find(5) == 5

    def test_union_basic(self):
        uf = UnionFind()
        uf.union(1, 2)
        assert uf.find(1) == uf.find(2)

    def test_union_transitive(self):
        uf = UnionFind()
        uf.union(1, 2)
        uf.union(2, 3)
        root = uf.find(1)
        assert uf.find(2) == root
        assert uf.find(3) == root

    def test_get_components(self):
        uf = UnionFind()
        uf.union(1, 2)
        uf.union(3, 4)
        uf.find(5)  # isolated
        components = uf.get_components()
        # Should have 3 components
        assert len(components) == 3
        # Component with {1, 2}
        sets = [set(v) for v in components.values()]
        assert {1, 2} in sets
        assert {3, 4} in sets
        assert {5} in sets

    def test_get_components_all_connected(self):
        uf = UnionFind()
        uf.union(1, 2)
        uf.union(2, 3)
        uf.union(3, 4)
        components = uf.get_components()
        assert len(components) == 1
        assert set(components[list(components.keys())[0]]) == {1, 2, 3, 4}


class TestComponentCluster:
    """Smoke test for ComponentCluster dataclass."""

    def test_create(self):
        c = ComponentCluster(name="power_stage", components={"U1", "Q1"})
        assert c.name == "power_stage"
        assert c.components == {"U1", "Q1"}


class TestTopologicalSolution:
    """Smoke test for TopologicalSolution dataclass."""

    def test_default_feasible(self):
        s = TopologicalSolution()
        assert s.feasible is True
        assert s.infeasibility_reasons == []
