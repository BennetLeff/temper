"""
PathGraph differential oracle — TDD gate G2, G1 for the path_graph migration.

Verbatim pre-migration oracle pinned inline; the Rust ``PathGraph`` pyclass
must reproduce networkx ``DiGraph.nodes()`` first-seen order (M6 rule,
``docs/evidence/2026-08-04-networkx-path-order-spike.md`` §7) and the
``number_of_edges()`` / ``nodes()`` / edge-list surface.

Oracle: ``networkx.DiGraph``, networkx 3.6.1, Python 3.12.
"""

from __future__ import annotations

import random

import tests.graph_fixtures as nx

import temper_design_bundle_python as _tdb

PathGraph = _tdb.topology_extraction_contracts.PathGraph
NetTopology = _tdb.topology_extraction_contracts.NetTopology
TopologyGraph = _tdb.topology_extraction_contracts.TopologyGraph

# ---------------------------------------------------------------------------
# Oracle: verbatim pre-migration DiGraph behavior (DO NOT EDIT — reference)
# ---------------------------------------------------------------------------

def _oracle_build(edges: list[tuple[str, str]]) -> nx.DiGraph:
    """Pre-migration construction: ``nx.DiGraph(); add_edges_from(edges)``."""
    g = nx.DiGraph()
    g.add_edges_from(edges)
    return g


def _oracle_nodes(edges: list[tuple[str, str]]) -> list[str]:
    """Pre-migration: ``list(DiGraph.nodes())`` — first-seen order (M6)."""
    return list(_oracle_build(edges).nodes())


def _oracle_edges(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Pre-migration: ``list(DiGraph.edges())``."""
    return list(_oracle_build(edges).edges())


def _oracle_number_of_edges(edges: list[tuple[str, str]]) -> int:
    """Pre-migration: ``DiGraph.number_of_edges()``."""
    return _oracle_build(edges).number_of_edges()


# ---------------------------------------------------------------------------
# M6: nodes() order equals first-seen order over the edge list
# ---------------------------------------------------------------------------

def test_m6_nodes_first_seen_order_trivial():
    """M6 on a three-edge DAG — the simplest non-trivial case."""
    edges = [("B", "C"), ("A", "B"), ("D", "E")]
    oracle_nodes = _oracle_nodes(edges)
    pg = PathGraph(edges)
    rust_nodes = pg.nodes()

    assert rust_nodes == oracle_nodes, (
        f"PathGraph.nodes()={rust_nodes} != oracle {oracle_nodes}"
    )


def test_m6_nodes_duplicate_in_edge_list():
    """M6: a node appearing multiple times keeps its first-seen position."""
    edges = [("X", "Y"), ("Y", "Z"), ("X", "W")]
    oracle_nodes = _oracle_nodes(edges)
    pg = PathGraph(edges)
    assert pg.nodes() == oracle_nodes


def test_m6_nodes_single_edge():
    """M6: single edge, two nodes."""
    edges = [("A", "B")]
    oracle_nodes = _oracle_nodes(edges)
    pg = PathGraph(edges)
    assert pg.nodes() == oracle_nodes


def test_m6_nodes_empty():
    """M6: empty edge list → empty node list."""
    edges: list[tuple[str, str]] = []
    oracle_nodes = _oracle_nodes(edges)
    pg = PathGraph(edges)
    assert pg.nodes() == oracle_nodes
    assert pg.nodes() == []
    assert pg.number_of_edges() == 0


def test_m6_randomized_200_trials():
    """M6 randomized: 200 trials, first-seen order holds on every one.

    This is the evidence that §7 recorded — ``list(DiGraph.nodes())`` equals
    first-seen order over the edge list, 200/200 randomized trials.
    """
    rng = random.Random(42)
    for trial in range(200):
        n_edges = rng.randint(1, 40)
        nodes_pool = [chr(ord("A") + i) for i in range(min(n_edges + 5, 26))]
        edges = [
            (rng.choice(nodes_pool), rng.choice(nodes_pool))
            for _ in range(n_edges)
        ]
        # De-duplicate repeated edges — DiGraph ignores dupes
        seen = set()
        edges = [e for e in edges if not (e in seen or seen.add(e))]  # type: ignore[func-returns-value]

        oracle_nodes = _oracle_nodes(edges)
        pg = PathGraph(edges)
        assert pg.nodes() == oracle_nodes, (
            f"Trial {trial}: PathGraph.nodes()={pg.nodes()} != oracle {oracle_nodes}"
        )


# ---------------------------------------------------------------------------
# Edge count parity
# ---------------------------------------------------------------------------

def test_number_of_edges_parity():
    """``number_of_edges()`` matches networkx DiGraph."""
    for edges in [
        [],
        [("A", "B")],
        [("A", "B"), ("B", "C"), ("C", "D")],
        [("X", "Y"), ("X", "Y")],  # duplicate edges — DiGraph deduplicates
    ]:
        oracle = _oracle_number_of_edges(edges)
        pg = PathGraph(edges)
        assert pg.number_of_edges() == oracle


# ---------------------------------------------------------------------------
# Edge list parity
# ---------------------------------------------------------------------------

def test_edges_list_parity():
    """``edges()`` returns the stored edge list in insertion order."""
    edges = [("B", "C"), ("A", "B"), ("D", "E")]
    pg = PathGraph(edges)
    assert pg.edges() == edges


def test_simple_number_of_nodes():
    """Number of unique nodes."""
    pg = PathGraph([("A", "B"), ("B", "C")])
    assert pg.number_of_nodes() == 3  # A, B, C


# ---------------------------------------------------------------------------
# NetTopology / TopologyGraph parity (dataclass → pyclass)
# ---------------------------------------------------------------------------

def test_net_topology_construction_and_fields():
    """NetTopology pyclass mirrors the pre-migration dataclass."""
    pg = PathGraph([("A", "B")])
    nt = NetTopology(
        net_name="TEST_NET",
        path_graph=pg,
        uses_channels=["CH1", "CH2"],
        total_length_estimate=25.5,
    )
    assert nt.net_name == "TEST_NET"
    assert nt.path_graph.number_of_edges() == 1
    assert nt.path_graph.nodes() == ["A", "B"]
    assert nt.uses_channels == ["CH1", "CH2"]
    assert nt.total_length_estimate == 25.5


def test_net_topology_path_graph_none():
    """path_graph=None is preserved as None (not a sentinel)."""
    nt = NetTopology(
        net_name="EMPTY",
        path_graph=None,
        uses_channels=[],
        total_length_estimate=0.0,
    )
    assert nt.path_graph is None
    assert nt.uses_channels == []
    assert nt.total_length_estimate == 0.0


def test_topology_graph_construction_and_methods():
    """TopologyGraph pyclass mirrors the pre-migration dataclass."""
    pg1 = PathGraph([("A", "B")])
    nt1 = NetTopology("NET1", pg1, [], 10.0)

    pg2 = PathGraph([("C", "D")])
    nt2 = NetTopology("NET2", pg2, [], 15.0)

    tg = TopologyGraph(net_topologies={"NET1": nt1, "NET2": nt2})
    assert tg.routed_net_count == 2
    assert tg.get_topology("NET1") is nt1
    assert tg.get_topology("NET2") is nt2
    assert tg.get_topology("NET3") is None


def test_net_topology_repr():
    """NetTopology.__repr__ is a dataclass-style repr."""
    pg = PathGraph([("S", "T")])
    nt = NetTopology(
        net_name="N1",
        path_graph=pg,
        uses_channels=["C1"],
        total_length_estimate=1.0,
    )
    r = repr(nt)
    assert r.startswith("NetTopology(")
    assert "net_name=" in r
    assert "path_graph=" in r
    assert "uses_channels=" in r
    assert "total_length_estimate=" in r


def test_path_graph_is_none_check():
    """PathGraph supports ``is None`` identity check (used in channel_mapping)."""
    pg = PathGraph([("A", "B")])
    assert pg is not None
    # Verify None path_graph in NetTopology
    nt = NetTopology("N", None, [], 0.0)
    assert nt.path_graph is None


def test_path_graph_number_of_edges_zero_when_empty():
    """number_of_edges() returns 0 for empty graph."""
    pg = PathGraph([])
    assert pg.number_of_edges() == 0
    assert pg.nodes() == []
    assert pg.number_of_nodes() == 0
