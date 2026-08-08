"""Tests for core.net_graph module."""

from temper_placer.core.net_graph import NetGraph, SubNetEdge


class TestSubNetEdge:
    """Tests for SubNetEdge dataclass."""

    def test_default_priority(self):
        edge = SubNetEdge(source_pin="R1.1", sink_pin="U1.5")
        assert edge.source_pin == "R1.1"
        assert edge.sink_pin == "U1.5"
        assert edge.trace_width_mm is None
        assert edge.clearance_mm is None
        assert edge.priority == 0

    def test_with_overrides(self):
        edge = SubNetEdge(
            source_pin="R1.1",
            sink_pin="U1.5",
            trace_width_mm=0.5,
            clearance_mm=0.3,
            priority=10,
        )
        assert edge.trace_width_mm == 0.5
        assert edge.clearance_mm == 0.3
        assert edge.priority == 10


class TestNetGraph:
    """Tests for NetGraph."""

    def _make_graph(self):
        """Create a simple net graph with 3 edges."""
        e1 = SubNetEdge(source_pin="U1.1", sink_pin="R1.1", priority=1)
        e2 = SubNetEdge(source_pin="U1.1", sink_pin="R2.1", priority=2)
        e3 = SubNetEdge(source_pin="R1.1", sink_pin="C1.1", priority=0)
        return NetGraph(
            net_name="NET1",
            edges=[e1, e2, e3],
            star_nodes={"U1.1"},
        )

    def test_get_edge_found(self):
        graph = self._make_graph()
        edge = graph.get_edge("U1.1", "R1.1")
        assert edge is not None
        assert edge.source_pin == "U1.1"
        assert edge.sink_pin == "R1.1"

    def test_get_edge_not_found(self):
        graph = self._make_graph()
        edge = graph.get_edge("X1.1", "Y1.1")
        assert edge is None

    def test_get_outgoing_edges(self):
        graph = self._make_graph()
        outgoing = graph.get_outgoing_edges("U1.1")
        assert len(outgoing) == 2
        sinks = {e.sink_pin for e in outgoing}
        assert sinks == {"R1.1", "R2.1"}

    def test_get_outgoing_edges_none(self):
        graph = self._make_graph()
        outgoing = graph.get_outgoing_edges("C1.1")
        assert len(outgoing) == 0

    def test_get_incoming_edges(self):
        graph = self._make_graph()
        incoming = graph.get_incoming_edges("R1.1")
        assert len(incoming) == 1
        assert incoming[0].source_pin == "U1.1"

    def test_get_incoming_edges_none(self):
        graph = self._make_graph()
        incoming = graph.get_incoming_edges("U1.1")
        assert len(incoming) == 0

    def test_star_nodes(self):
        graph = self._make_graph()
        assert graph.star_nodes == {"U1.1"}

    def test_empty_graph(self):
        graph = NetGraph(net_name="EMPTY")
        assert graph.net_name == "EMPTY"
        assert graph.edges == []
        assert graph.star_nodes == set()
        assert graph.get_edge("A.1", "B.1") is None
        assert graph.get_outgoing_edges("A.1") == []
        assert graph.get_incoming_edges("B.1") == []
