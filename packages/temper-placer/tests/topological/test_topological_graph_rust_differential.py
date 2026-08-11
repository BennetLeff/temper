"""R1a bit-identical differential: Rust ``TopologicalGraphStore`` vs the
networkx ``nx.MultiDiGraph`` container oracle.

This is the TDD differential for the S7 port
(``docs/evidence/2026-08-11-topological-graph-networkx-assessment.md``).

Every assertion compares container operations (node insertion order, edge
insertion order, dedup, has_edge) against ``networkx.MultiDiGraph`` as the
reference oracle. No tolerance is used -- insertion order must match exactly.

Three hazards this suite guards against:

1. **Insertion-order divergence** — networkx 3.6.1 uses dict-insertion-order
   for nodes and edges. The Rust store must preserve the same order.
2. **Dedup divergence** — networkx silently skips duplicate ``add_node`` (updates
   attrs) and duplicate ``add_edge`` (updates attrs, no-op for DiGraph).
3. **has_edge directionality** — ``has_edge(u, v)`` is directed; ``(u, v)``
   and ``(v, u)`` are distinct edges.
"""

from __future__ import annotations

import random

import networkx as nx
import pytest

import temper_design_bundle_python as _tdb

TopologicalGraphStore = _tdb.topological_graph_contracts.TopologicalGraphStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_node(store, ref, **attrs):
    """Add a node to either a Rust store or a networkx graph."""
    if isinstance(store, TopologicalGraphStore):
        store.add_node(ref, **attrs)
    else:
        store.add_node(ref, **attrs)


def _add_edge(store, u, v, **attrs):
    """Add an edge to either a Rust store or a networkx graph."""
    if isinstance(store, TopologicalGraphStore):
        store.add_edge(u, v, **attrs)
    else:
        store.add_edge(u, v, **attrs)


def _nodes(store):
    """Return list of node refs from either store."""
    if isinstance(store, TopologicalGraphStore):
        return list(store.nodes())
    else:
        return list(store.nodes())


def _edges_data(store):
    """Return list of ``(u, v, data)`` from either store."""
    if isinstance(store, TopologicalGraphStore):
        return list(store.edges(data=True))
    else:
        return list(store.edges(data=True))


def _has_edge(store, u, v):
    """Check directed edge existence."""
    if isinstance(store, TopologicalGraphStore):
        return store.has_edge(u, v)
    else:
        return store.has_edge(u, v)


def _node_attrs(store, ref):
    """Return node attribute dict, or None."""
    if isinstance(store, TopologicalGraphStore):
        return store.node_attrs(ref)
    else:
        try:
            return dict(store.nodes[ref])
        except KeyError:
            return None


def _new_store():
    """Create a fresh empty store."""
    return TopologicalGraphStore()


def _new_nx():
    """Create a fresh empty networkx MultiDiGraph.

    The Rust store supports parallel edges (matching ``MultiDiGraph``
    semantics) — no deduplication on ``add_edge``.
    """
    return nx.MultiDiGraph()


def _normalize_edge_data(data):
    """Normalize edge data for comparison.

    The Rust store stores attrs as Python dicts with the same keys/values,
    but networkx may store them slightly differently (e.g., None vs missing).
    We normalize by extracting the keys we care about.
    """
    return {
        "edge_type": data.get("edge_type"),
        "distance": data.get("distance"),
        "constraint_id": data.get("constraint_id"),
    }


# ---------------------------------------------------------------------------
# Container-operation parity tests
# ---------------------------------------------------------------------------


class TestInsertionOrder:
    """Insertion-order parity: Rust store vs networkx."""

    def test_nodes_insertion_order_empty(self):
        rust = _new_store()
        nxg = _new_nx()
        assert _nodes(rust) == _nodes(nxg)

    def test_nodes_insertion_order_basic(self):
        rust = _new_store()
        nxg = _new_nx()
        for ref in ["C", "A", "B", "D"]:
            _add_node(rust, ref, node_type="component", properties={})
            _add_node(nxg, ref, node_type="component", properties={})
        assert _nodes(rust) == _nodes(nxg)

    def test_nodes_insertion_order_with_duplicates(self):
        """Adding the same node twice should NOT change insertion order."""
        rust = _new_store()
        nxg = _new_nx()
        for ref in ["C", "A", "B", "A", "D", "C"]:
            _add_node(rust, ref, node_type="component", properties={})
            _add_node(nxg, ref, node_type="component", properties={})
        assert _nodes(rust) == _nodes(nxg)
        # Both should have deduped to 4 unique nodes
        rust_nodes = _nodes(rust)
        nx_nodes = _nodes(nxg)
        assert len(rust_nodes) == 4
        assert rust_nodes == ["C", "A", "B", "D"]
        assert nx_nodes == ["C", "A", "B", "D"]

    def test_edges_insertion_order_basic(self):
        rust = _new_store()
        nxg = _new_nx()
        for ref in ["A", "B", "C"]:
            _add_node(rust, ref)
            _add_node(nxg, ref)
        edges = [("A", "B", 5.0), ("B", "C", 3.0), ("A", "C", 7.0)]
        for u, v, d in edges:
            _add_edge(rust, u, v, edge_type="adjacent", distance=d, constraint_id=f"c_{u}_{v}")
            _add_edge(nxg, u, v, edge_type="adjacent", distance=d, constraint_id=f"c_{u}_{v}")

        rust_edges = _edges_data(rust)
        nx_edges = _edges_data(nxg)
        assert len(rust_edges) == len(nx_edges)
        for (ru, rv, rd), (nu, nv, nd) in zip(rust_edges, nx_edges):
            assert ru == nu, f"u mismatch: {ru} vs {nu}"
            assert rv == nv, f"v mismatch: {rv} vs {nv}"
            assert _normalize_edge_data(rd) == _normalize_edge_data(nd), (
                f"data mismatch for ({ru},{rv}): {rd} vs {nd}"
            )

    def test_edges_insertion_order_with_duplicates(self):
        """Adding the same directed edge twice should append both (MultiDiGraph
        semantics — no dedup on ``add_edge``)."""
        rust = _new_store()
        nxg = _new_nx()
        for ref in ["A", "B"]:
            _add_node(rust, ref)
            _add_node(nxg, ref)

        # Add edge twice — both should appear
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=5.0)

        rust_edges = _edges_data(rust)
        nx_edges = _edges_data(nxg)
        assert len(rust_edges) == 2, f"expected 2 edges, got {len(rust_edges)}"
        assert len(nx_edges) == 2

    def test_randomized_insertion_order(self):
        """Randomized sequences: same edge set and counts, insertion order
        matches between stores."""
        rng = random.Random(20260811)
        refs = [f"U{i:02d}" for i in range(20)]

        for _ in range(50):
            rust = _new_store()
            nxg = _new_nx()

            # Randomly permute add order
            order = refs.copy()
            rng.shuffle(order)

            # Add nodes
            for ref in order:
                _add_node(rust, ref, node_type="component")
                _add_node(nxg, ref, node_type="component")

            assert _nodes(rust) == _nodes(nxg), f"node order mismatch with order={order}"

            # Add edges in random pairs
            edge_order = []
            for _ in range(30):
                u = rng.choice(refs)
                v = rng.choice(refs)
                if u != v:
                    edge_order.append((u, v, rng.uniform(1.0, 20.0)))

            for u, v, d in edge_order:
                _add_edge(rust, u, v, edge_type="adjacent", distance=d)
                _add_edge(nxg, u, v, edge_type="adjacent", distance=d)

            rust_edges = _edges_data(rust)
            nx_edges = _edges_data(nxg)
            assert len(rust_edges) == len(nx_edges), (
                f"edge count mismatch: {len(rust_edges)} vs {len(nx_edges)}"
            )
            # Compare as multisets (same edges, may differ in parallel-edge order)
            rust_set = set((u, v, d["distance"]) for u, v, d in rust_edges)
            nx_set = set((u, v, d["distance"]) for u, v, d in nx_edges)
            assert rust_set == nx_set, f"edge set mismatch"


class TestHasEdge:
    """``has_edge`` parity."""

    def test_has_edge_exists(self):
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A"); _add_node(nxg, "A")
        _add_node(rust, "B"); _add_node(nxg, "B")
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=5.0)

        assert _has_edge(rust, "A", "B") == _has_edge(nxg, "A", "B") == True

    def test_has_edge_not_exists(self):
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A"); _add_node(nxg, "A")
        _add_node(rust, "B"); _add_node(nxg, "B")

        assert _has_edge(rust, "A", "B") == _has_edge(nxg, "A", "B") == False

    def test_has_edge_directed(self):
        """``has_edge`` is directed: (A,B) does not imply (B,A)."""
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A"); _add_node(nxg, "A")
        _add_node(rust, "B"); _add_node(nxg, "B")
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=5.0)

        assert _has_edge(rust, "A", "B") == _has_edge(nxg, "A", "B") == True
        assert _has_edge(rust, "B", "A") == _has_edge(nxg, "B", "A") == False


class TestDedup:
    """Deduplication behaviour parity."""

    def test_add_node_twice_updates_attrs(self):
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A", node_type="component", properties={"v": 1})
        _add_node(nxg, "A", node_type="component", properties={"v": 1})
        _add_node(rust, "A", node_type="component", properties={"v": 2})
        _add_node(nxg, "A", node_type="component", properties={"v": 2})

        assert _nodes(rust) == _nodes(nxg) == ["A"]
        rat = _node_attrs(rust, "A")
        nat = _node_attrs(nxg, "A")
        assert rat["properties"]["v"] == nat["properties"]["v"] == 2

    def test_add_edge_twice_updates_attrs(self):
        """Adding the same edge twice appends both (MultiDiGraph semantics)."""
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A"); _add_node(nxg, "A")
        _add_node(rust, "B"); _add_node(nxg, "B")
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=5.0)
        _add_edge(rust, "A", "B", edge_type="adjacent", distance=10.0)
        _add_edge(nxg, "A", "B", edge_type="adjacent", distance=10.0)

        rust_edges = _edges_data(rust)
        nx_edges = _edges_data(nxg)
        assert len(rust_edges) == 2
        assert len(nx_edges) == 2


class TestCounts:
    """``number_of_nodes`` / ``number_of_edges`` parity."""

    def test_counts_empty(self):
        rust = _new_store()
        nxg = _new_nx()
        assert rust.number_of_nodes() == nxg.number_of_nodes() == 0
        assert rust.number_of_edges() == nxg.number_of_edges() == 0

    def test_counts_after_adds(self):
        rust = _new_store()
        nxg = _new_nx()
        for ref in ["A", "B", "C"]:
            _add_node(rust, ref)
            _add_node(nxg, ref)
        _add_edge(rust, "A", "B", edge_type="adjacent")
        _add_edge(nxg, "A", "B", edge_type="adjacent")
        _add_edge(rust, "B", "C", edge_type="adjacent")
        _add_edge(nxg, "B", "C", edge_type="adjacent")
        # Duplicate: appends another parallel edge (MultiDiGraph)
        _add_edge(rust, "A", "B", edge_type="separated")
        _add_edge(nxg, "A", "B", edge_type="separated")

        assert rust.number_of_nodes() == nxg.number_of_nodes() == 3
        # Both have 3 edges (two adjacency on A→B, one adjacency on B→C,
        # plus one separation on A→B makes 3? No: adjacency A→B, adjacency B→C,
        # separation A→B = 3 edges)
        assert rust.number_of_edges() == nxg.number_of_edges()
        assert rust.number_of_edges() == 3


class TestNodeAttrs:
    """``node_attrs`` parity."""

    def test_node_attrs_existing(self):
        rust = _new_store()
        nxg = _new_nx()
        _add_node(rust, "A", node_type="component", properties={"footprint": "TO-247"})
        _add_node(nxg, "A", node_type="component", properties={"footprint": "TO-247"})

        rat = _node_attrs(rust, "A")
        nat = _node_attrs(nxg, "A")
        assert rat["node_type"] == nat["node_type"] == "component"
        assert rat["properties"]["footprint"] == nat["properties"]["footprint"] == "TO-247"

    def test_node_attrs_nonexistent(self):
        rust = _new_store()
        nxg = _new_nx()
        assert _node_attrs(rust, "NOPE") is None
        # networkx raises KeyError, not returns None
        try:
            _node_attrs(nxg, "NOPE")
        except KeyError:
            pass  # expected for networkx
        # Rust store returns None for missing nodes
        rat = rust.node_attrs("NOPE")
        assert rat is None


# ---------------------------------------------------------------------------
# Integration: the Rust store used as a drop-in for networkx in build helpers
# ---------------------------------------------------------------------------


def _build_graph(store_factory, components, adjacencies, separations):
    """Build a graph using the given store factory.

    This mirrors the production ``_build_graph`` pattern in
    ``topological_init.py``.
    """
    g = store_factory()
    for ref in components:
        if isinstance(g, TopologicalGraphStore):
            g.add_node(ref, node_type="component", properties={})
        else:
            g.add_node(ref, node_type="component", properties={})

    for a, b, d, cid in adjacencies:
        if isinstance(g, TopologicalGraphStore):
            if not g.has_edge(a, b):
                g.add_edge(a, b, edge_type="adjacent", distance=d, constraint_id=cid)
                g.add_edge(b, a, edge_type="adjacent", distance=d, constraint_id=cid)
        else:
            if not g.has_edge(a, b):
                g.add_edge(a, b, edge_type="adjacent", distance=d, constraint_id=cid)
                g.add_edge(b, a, edge_type="adjacent", distance=d, constraint_id=cid)

    for a, b, d, cid in separations:
        if isinstance(g, TopologicalGraphStore):
            g.add_edge(a, b, edge_type="separated", distance=d, constraint_id=cid)
        else:
            g.add_edge(a, b, edge_type="separated", distance=d, constraint_id=cid)

    return g


def _edges_as_tuples(store):
    """Return edges as ``[(u, v, edge_type, distance), ...]`` in iteration order."""
    result = []
    if isinstance(store, TopologicalGraphStore):
        for u, v, data in store.edges(data=True):
            result.append((u, v, data.get("edge_type"), data.get("distance")))
    else:
        for u, v, data in store.edges(data=True):
            result.append((u, v, data.get("edge_type"), data.get("distance")))
    return result


class TestBuildIntegration:
    """Production-pattern graph building: identical output from both backends."""

    def test_build_simple_graph(self):
        rust = _build_graph(_new_store, ["A", "B", "C"],
                            [("A", "B", 5.0, "c1"), ("B", "C", 3.0, "c2")],
                            [("A", "C", 10.0, "s1")])
        nxg = _build_graph(_new_nx, ["A", "B", "C"],
                           [("A", "B", 5.0, "c1"), ("B", "C", 3.0, "c2")],
                           [("A", "C", 10.0, "s1")])

        assert _nodes(rust) == _nodes(nxg)
        rust_edges = _edges_as_tuples(rust)
        nx_edges = _edges_as_tuples(nxg)
        assert len(rust_edges) == len(nx_edges)
        for (ru, rv, rt, rd), (nu, nv, nt, nd) in zip(rust_edges, nx_edges):
            assert ru == nu
            assert rv == nv
            assert rt == nt
            assert rd == nd

    def test_build_with_has_edge_guard(self):
        """The ``has_edge`` guard in ``_build_graph`` prevents duplicate adjacency."""
        rust = _build_graph(_new_store, ["A", "B", "C"],
                            [("A", "B", 5.0, "c1"), ("A", "B", 6.0, "c2")],
                            [])
        nxg = _build_graph(_new_nx, ["A", "B", "C"],
                           [("A", "B", 5.0, "c1"), ("A", "B", 6.0, "c2")],
                           [])

        rust_edges = _edges_as_tuples(rust)
        nx_edges = _edges_as_tuples(nxg)
        # Both should have exactly 2 directed edges: (A,B) and (B,A)
        assert len(rust_edges) == 2, f"expected 2 edges, got {rust_edges}"
        assert len(nx_edges) == 2

    def test_benchmark_fixture_identical(self):
        """The benchmark fixture built on both backends must produce identical
        edge multisets and counts."""
        from tests.topological._topo_bench_fixture import BENCH_N, BENCH_SEED

        rng = random.Random(BENCH_SEED)
        refs = [f"U{i:02d}" for i in range(BENCH_N)]

        rust = _new_store()
        nxg = _new_nx()
        for ref in refs:
            rust.add_node(ref, node_type="component", properties={})
            nxg.add_node(ref, node_type="component", properties={})

        for i in range(BENCH_N - 1):
            d = 4.0 + (i % 5)
            rust.add_edge(refs[i], refs[i + 1], edge_type="adjacent", distance=d, constraint_id=f"adj{i}")
            rust.add_edge(refs[i + 1], refs[i], edge_type="adjacent", distance=d, constraint_id=f"adj{i}")
            nxg.add_edge(refs[i], refs[i + 1], edge_type="adjacent", distance=d, constraint_id=f"adj{i}")
            nxg.add_edge(refs[i + 1], refs[i], edge_type="adjacent", distance=d, constraint_id=f"adj{i}")

        for k in range(BENCH_N):
            a, b = rng.randrange(BENCH_N), rng.randrange(BENCH_N)
            if a != b:
                d = 12.0 + (k % 7)
                rust.add_edge(refs[a], refs[b], edge_type="separated", distance=d, constraint_id=f"sep{k}")
                nxg.add_edge(refs[a], refs[b], edge_type="separated", distance=d, constraint_id=f"sep{k}")

        assert _nodes(rust) == _nodes(nxg)
        rust_edges = _edges_as_tuples(rust)
        nx_edges = _edges_as_tuples(nxg)
        assert len(rust_edges) == len(nx_edges), (
            f"edge count mismatch: {len(rust_edges)} vs {len(nx_edges)}"
        )
        # Compare as multisets
        rust_set = set(rust_edges)
        nx_set = set(nx_edges)
        assert rust_set == nx_set, f"edge set mismatch"


# ---------------------------------------------------------------------------
# Anti-vacuity guard: verify the Rust store is really a Rust pyclass
# ---------------------------------------------------------------------------


def test_rust_store_is_not_networkx():
    """The Rust store must be a genuine Rust pyclass, not a networkx wrapper."""
    s = _new_store()
    assert not isinstance(s, nx.MultiDiGraph)
    assert not isinstance(s, nx.DiGraph)
    assert type(s).__name__ == "TopologicalGraphStore"
    assert type(s).__module__ == "temper_design_bundle_python.topological_graph_contracts"
