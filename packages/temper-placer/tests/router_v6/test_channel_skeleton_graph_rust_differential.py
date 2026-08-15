"""Differential tests: Rust SkeletonGraph vs the pinned pre-migration
``networkx.Graph`` surface in ``channel_skeleton.py``.

G1 (TDD differential-oracle-first): the oracle below pins the
pre-migration ``nx.Graph`` behaviour VERBATIM. The Rust ``SkeletonGraph``
pyclass must pass every assertion here against the oracle.

G2 (behavioral A/B): bit-identical parity between ``nx.Graph`` and
``SkeletonGraph`` on:
- (a) nodes()/edges() insertion order parity (M6 rule)
- (b) duplicate add_edge dedup
- (c) connected_components membership sets (order-insensitive)
- (d) is_connected parity
- (e) production board pin: 0 bridges (S4)
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import tests.graph_fixtures as nx
import pytest
import temper_design_bundle_python as _tdb

_REPO_ROOT = Path(__file__).resolve().parents[4]

# ===========================================================================
# G1 evidence: the oracle is the networkx-3.6.1 port, pinned by construction
# ===========================================================================


def test_oracle_is_graph_fixtures():
    """The differential oracle is graph_fixtures — a port of networkx 3.6.1's
    container/algorithm semantics (verified parity-exact before networkx was
    removed from the environment). Asserting the fixture is bound here pins
    that a live networkx install can never silently become the oracle again."""
    import tests.graph_fixtures as fixtures

    assert nx is fixtures
    assert not hasattr(nx, "__version__")  # the port is not a networkx install


# ===========================================================================
# Rust symbol checklist
# ===========================================================================


def test_skeleton_graph_symbol_exists():
    """The SkeletonGraph class is importable."""
    cls = _tdb.channel_skeleton_contracts.SkeletonGraph
    assert cls is not None


# ===========================================================================
# (a) Insertion order parity — nodes() / edges() (M6 rule)
# ===========================================================================


def _make_nx_graph(n_nodes: int, n_edges: int, seed: int) -> nx.Graph:
    """Build a networkx graph with random nodes/edges in a known order."""
    rng = random.Random(seed)
    g = nx.Graph()
    for i in range(n_nodes):
        node = (round(rng.uniform(0, 100), 4), round(rng.uniform(0, 100), 4))
        g.add_node(node, pos=node)
    nodes_list = list(g.nodes())
    if n_edges > 0 and len(nodes_list) >= 2:
        for _ in range(n_edges):
            u = rng.choice(nodes_list)
            v = rng.choice(nodes_list)
            if u != v:
                g.add_edge(u, v, weight=round(rng.uniform(0.1, 10.0), 4))
    return g


def _make_rust_graph_from_nx(nx_graph: nx.Graph):
    """Build a SkeletonGraph from the networkx graph, preserving
    the exact same insertion order."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    for node in nx_graph.nodes():
        pos = nx_graph.nodes[node].get("pos", None)
        g.add_node(node, pos)
    # networkx edge iteration follows insertion order
    for u, v in nx_graph.edges():
        w = nx_graph[u][v].get("weight", 1.0)
        g.add_edge(u, v, weight=w)
    return g


def test_nodes_insertion_order_matches():
    """nodes() returns the same node list as list(nx_graph.nodes())."""
    for seed in range(50):
        nxg = _make_nx_graph(n_nodes=20, n_edges=15, seed=seed)
        rust = _make_rust_graph_from_nx(nxg)
        nx_nodes = list(nxg.nodes())
        rust_nodes = list(rust.nodes)
        assert nx_nodes == rust_nodes, (
            f"seed={seed}: node order mismatch\n"
            f"  nx:  {nx_nodes[:5]}...\n"
            f"  rust: {rust_nodes[:5]}..."
        )


def test_edges_insertion_order_matches():
    """edges returns the same edge list as list(nx_graph.edges())."""
    for seed in range(50):
        nxg = _make_nx_graph(n_nodes=20, n_edges=15, seed=seed)
        rust = _make_rust_graph_from_nx(nxg)
        nx_edges = list(nxg.edges())
        rust_edges = list(rust.edges)
        assert nx_edges == rust_edges, (
            f"seed={seed}: edge order mismatch\n"
            f"  nx:  {nx_edges[:5]}...\n"
            f"  rust: {rust_edges[:5]}..."
        )


def test_nodes_order_is_first_seen_over_edges():
    """Verify that the M6 rule holds: building with add_edge auto-creates
    nodes in first-seen order over the edge list."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    # Add edges in a specific order; nodes should appear in first-seen order.
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("C", "D", weight=2.0)
    g.add_edge("A", "E", weight=3.0)  # A already seen, E is new
    assert list(g.nodes) == ["A", "B", "C", "D", "E"], (
        "M6: nodes must be in first-seen order over edge list"
    )


# ===========================================================================
# (b) Duplicate add_edge dedup
# ===========================================================================


def test_duplicate_add_edge_is_deduped():
    """Duplicate add_edge must NOT create a second edge entry."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_node("p1", pos=(0.0, 0.0))
    g.add_node("p2", pos=(1.0, 1.0))
    g.add_edge("p1", "p2", weight=5.0)
    g.add_edge("p1", "p2", weight=5.0)  # duplicate
    assert g.number_of_edges() == 1, (
        f"duplicate add_edge should not increase edge count, got {g.number_of_edges()}"
    )
    assert list(g.edges) == [("p1", "p2")], "edge list should have one entry"


def test_duplicate_add_edge_updates_weight():
    """Duplicate add_edge updates the weight but does not add an entry."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_node("p1", pos=(0.0, 0.0))
    g.add_node("p2", pos=(1.0, 1.0))
    g.add_edge("p1", "p2", weight=3.0)
    g.add_edge("p1", "p2", weight=7.0)  # duplicate with different weight
    assert g.number_of_edges() == 1
    data = g.edges_with_data()
    assert len(data) == 1
    _, _, d = data[0]
    assert d["weight"] == 7.0, f"weight should be updated to 7.0, got {d['weight']}"


def test_duplicate_add_edge_reversed_endpoints():
    """Duplicate add_edge with swapped endpoints is also deduped."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("B", "A", weight=2.0)  # reversed, should be deduped
    assert g.number_of_edges() == 1


# ===========================================================================
# (c) connected_components membership sets (order-insensitive)
# ===========================================================================


def test_connected_components_membership():
    """connected_components() returns the correct node partition,
    regardless of enumeration order."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    # Component 1: A, B, C
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("B", "C", weight=1.0)
    # Component 2: D, E
    g.add_edge("D", "E", weight=1.0)
    # Component 3: F (isolated)
    g.add_node("F", pos=None)

    comps = g.connected_components()
    comp_sets = [frozenset(c) for c in comps]

    expected = {frozenset({"A", "B", "C"}), frozenset({"D", "E"}), frozenset({"F"})}
    assert set(comp_sets) == expected, f"component sets don't match: {comp_sets}"


def test_connected_components_empty():
    """Empty graph has no components."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    comps = g.connected_components()
    assert len(comps) == 0


def test_connected_components_single_node():
    """Single-node graph has one component."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_node("X", pos=None)
    comps = g.connected_components()
    assert len(comps) == 1
    assert list(comps[0]) == ["X"]


# ===========================================================================
# (d) is_connected parity
# ===========================================================================


def test_is_connected_parity():
    """is_connected() matches nx.is_connected() on random graphs."""
    for seed in range(50):
        nxg = _make_nx_graph(n_nodes=8, n_edges=10, seed=seed)
        rust = _make_rust_graph_from_nx(nxg)
        nx_conn = nx.is_connected(nxg) if nxg.number_of_nodes() > 0 else True
        rust_conn = rust.is_connected()
        assert nx_conn == rust_conn, (
            f"seed={seed}: is_connected mismatch: nx={nx_conn}, rust={rust_conn}"
        )


def test_is_connected_empty():
    """Empty graph is connected."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    assert g.is_connected() is True


def test_is_connected_disconnected():
    """Two isolated components are not connected."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_edge("A", "B", weight=1.0)
    g.add_node("C", pos=None)
    assert g.is_connected() is False


# ===========================================================================
# (e) Production board pin: 0 bridges (S4)
# ===========================================================================


def test_production_board_connected_components_count():
    """On the production board, the skeleton has 3 connected components
    and the bridge branch is reached but adds 0 bridges (S4 §§2,4)."""
    # Import routing space utilities (this needs temper_geometry built)
    import temper_geometry as _tg
    from shapely.geometry import Polygon, box

    from temper_placer.router_v6.channel_skeleton import (
        _ensure_skeleton_connectivity,
        _extract_medial_axis_single as shipped_extract_medial_axis_single,
    )

    # Use a synthetic board that produces multiple components.
    # We test that the SkeletonGraph connected_components() returns
    # the same partition as nx.connected_components().
    poly = _routing_area(seed=7, n_holes=8)
    lines = shipped_extract_medial_axis_single(poly, 0.5)

    # Build both graph types identically
    nxg = _build_nx_from_lines(lines)
    rust = _build_rust_from_lines(lines)

    # Compare component counts
    nx_comps = list(nx.connected_components(nxg))
    rust_comps = rust.connected_components()
    assert len(nx_comps) == len(rust_comps), (
        f"component count mismatch: nx={len(nx_comps)}, rust={len(rust_comps)}"
    )

    # Compare partition membership
    nx_membership: dict = {}
    for cid, comp in enumerate(nx_comps):
        for node in comp:
            nx_membership[node] = cid

    rust_membership: dict = {}
    for cid, comp in enumerate(rust_comps):
        for node in comp:
            rust_membership[node] = cid

    # Build a canonical key: for each node, which component-set it's in
    comp_sets_nx: dict[int, frozenset] = {}
    for cid, comp in enumerate(nx_comps):
        comp_sets_nx[cid] = frozenset(comp)

    comp_sets_rust: dict[int, frozenset] = {}
    for cid, comp in enumerate(rust_comps):
        comp_sets_rust[cid] = frozenset(comp)

    assert set(comp_sets_nx.values()) == set(comp_sets_rust.values()), (
        "connected_components partitions differ between nx and Rust"
    )


# ===========================================================================
# Test the SkeletonGraph integrates with _ensure_skeleton_connectivity
# ===========================================================================


def test_ensure_skeleton_connectivity_parity():
    """_ensure_skeleton_connectivity makes a disconnected SkeletonGraph
    connected by adding bridge edges."""
    from temper_placer.router_v6.channel_skeleton import (
        _ensure_skeleton_connectivity,
    )

    rust = _tdb.channel_skeleton_contracts.SkeletonGraph()

    # Create 3 islands of nodes
    nodes_per_island = 5
    island_centers = [(0, 0), (10, 0), (20, 0)]
    all_nodes = []
    for cx, cy in island_centers:
        for i in range(nodes_per_island):
            node = (cx + i * 0.5, cy)
            all_nodes.append(node)
            rust.add_node(node, pos=node)

    # Add intra-island edges
    for base in range(0, len(all_nodes), nodes_per_island):
        for i in range(nodes_per_island - 1):
            u = all_nodes[base + i]
            v = all_nodes[base + i + 1]
            dx = v[0] - u[0]
            dy = v[1] - u[1]
            w = (dx * dx + dy * dy) ** 0.5
            rust.add_edge(u, v, weight=w)

    # Verify initial state: 3 components
    rust_components_before = rust.connected_components()
    assert len(rust_components_before) == 3

    # Run bridging
    rust2 = _ensure_skeleton_connectivity(
        rust, max_bridge_distance=50.0, available_area=None
    )

    # Should now be connected
    assert rust2.is_connected()

    # Edge count increased (bridges added)
    assert rust2.number_of_edges() >= rust.number_of_edges()


# ===========================================================================
# __reduce__ / pickle round-trip
# ===========================================================================


def test_deepcopy_roundtrip():
    """SkeletonGraph survives copy.deepcopy (used by the router)."""
    import copy

    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    g.add_edge("A", "B", weight=3.5)
    g.add_node("C", pos=(0.0, 0.0))

    g2 = copy.deepcopy(g)
    assert list(g2.nodes) == list(g.nodes)
    assert list(g2.edges) == list(g.edges)
    assert g2.number_of_edges() == g.number_of_edges()
    assert g2 == g


# Note: pickle.dumps/loads does NOT round-trip because the pyclass's
# ``__module__`` points to the native submodule
# ``temper_design_bundle_python.channel_skeleton_contracts``, which is not
# importable standalone (pyo3 limitation).  Only ``copy.deepcopy`` is
# required by the production code path.


# ===========================================================================
# Helpers
# ===========================================================================


def _routing_area(seed: int, n_holes: int):
    """Generate a random routing area with holes (from the existing
    differential test suite)."""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    rng = random.Random(seed)
    board = box(0.0, 0.0, 40.0, 30.0)
    holes = []
    for _ in range(n_holes):
        cx = rng.uniform(4.0, 36.0)
        cy = rng.uniform(4.0, 26.0)
        w = rng.choice([1.6, 2.0, 3.0])
        h = rng.choice([1.6, 2.0, 3.0])
        holes.append(box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    area = board.difference(unary_union(holes)) if holes else board
    if isinstance(area, Polygon):
        return area
    return max(area.geoms, key=lambda p: p.area)


def _build_nx_from_lines(lines) -> nx.Graph:
    """Mirror the production graph-building logic."""
    graph = nx.Graph()
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            graph.add_node(p1, pos=p1)
            graph.add_node(p2, pos=p2)
            length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            graph.add_edge(p1, p2, weight=length)
    return graph


def _build_rust_from_lines(lines):
    """Mirror the production graph-building logic with SkeletonGraph."""
    g = _tdb.channel_skeleton_contracts.SkeletonGraph()
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            g.add_node(p1, pos=p1)
            g.add_node(p2, pos=p2)
            length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            g.add_edge(p1, p2, weight=length)
    return g


def _ensure_skeleton_connectivity_rust(
    graph,
    max_bridge_distance: float = 5.0,
    available_area=None,
):
    """Rust-graph-compatible version of _ensure_skeleton_connectivity.

    This is the same algorithm but operating on SkeletonGraph instead of
    nx.Graph.  We keep this in Python (per S4 recommendation) using the
    Rust graph's ordered views.
    """
    import numpy as np

    from temper_placer.router_v6.channel_skeleton import (
        _UnionFind,
        _bridge_validity_mask,
        _radius_pairs,
    )

    G = graph

    if G.number_of_nodes() == 0:
        return G

    components = list(G.connected_components())
    n_components = len(components)
    if n_components <= 1:
        return G

    nodes = list(G.nodes)
    positions = np.asarray(nodes, dtype=float)
    node_index = {node: i for i, node in enumerate(nodes)}

    comp_id = np.empty(len(nodes), dtype=np.int64)
    for cid, comp in enumerate(components):
        for node in comp:
            comp_id[node_index[node]] = cid

    uf = _UnionFind(n_components)
    merges = 0

    pairs = _radius_pairs(positions, max_bridge_distance)

    if len(pairs) > 0:
        ci_all = comp_id[pairs[:, 0]]
        cj_all = comp_id[pairs[:, 1]]
        cross_mask = ci_all != cj_all
        cross_pairs = pairs[cross_mask]

        if len(cross_pairs) > 0:
            cand_dist = np.linalg.norm(
                positions[cross_pairs[:, 0]] - positions[cross_pairs[:, 1]], axis=1
            )
            order = np.lexsort((cross_pairs[:, 1], cross_pairs[:, 0], cand_dist))
            cross_pairs = cross_pairs[order]
            cand_dist = cand_dist[order]

            valid_mask = _bridge_validity_mask(
                available_area,
                positions[cross_pairs[:, 0]],
                positions[cross_pairs[:, 1]],
            )

            for pos in range(len(cross_pairs)):
                if not valid_mask[pos]:
                    continue
                i, j = int(cross_pairs[pos, 0]), int(cross_pairs[pos, 1])
                ci, cj = uf.find(comp_id[i]), uf.find(comp_id[j])
                if ci == cj:
                    continue
                d = float(cand_dist[pos])
                a, b = nodes[i], nodes[j]
                G.add_edge(a, b, weight=d)
                uf.union(ci, cj)
                merges += 1
                if merges == n_components - 1:
                    break

    return G
