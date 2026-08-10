#!/usr/bin/env python3
"""
M3 — Synthetic permutation experiment: test whether connected_components
enumeration order is observable when bridges ARE actually added.

The production board adds 0 bridges (all candidates fail geometry validity).
This script creates synthetic graphs where bridges are needed and tests
order sensitivity.

Two sub-experiments:
  A. Component-ID permutation: same graph, permute component ID enumeration
     to test whether `enumerate(components)` order flows into the output.
  B. Insertion-order permutation: rebuild graph with permuted node/edge order
     and check whether different bridge edges are selected.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np


# -- Synthetic graph builder for tests where bridges ARE needed --


def make_graph_with_bridges(
    n_islands: int = 5,
    nodes_per_island: int = 10,
    island_spread: float = 50.0,
    max_bridge_dist: float = 15.0,
    seed: int = 42,
    variable_ties: bool = False,
) -> nx.Graph:
    """Build a synthetic disconnected graph where bridges are needed.

    Creates n_islands clusters of nodes, each cluster internally connected
    as a path. Islands are spread randomly. Bridges are needed between
    adjacent islands.

    If variable_ties=True, some islands are placed at similar distances
    to create tied bridge candidates.
    """
    rng = random.Random(seed)
    G = nx.Graph()

    # Create island centers
    centers = []
    for i in range(n_islands):
        cx = rng.uniform(0, island_spread)
        cy = rng.uniform(0, island_spread)
        centers.append((cx, cy))

    if variable_ties:
        # Make a few islands collinear at equal distances to create ties
        # Island 1 at (10, 0), island 2 at (20, 0) — two bridges from island 0
        # at equal distances
        centers = [(0.0, 0.0)]
        for i in range(1, n_islands):
            # Place at varying distances, but some pairs tied
            if i <= 2:
                centers.append((float(i) * 10.0, 0.0))
            else:
                centers.append((float(i) * 10.0 + rng.uniform(-0.1, 0.1), rng.uniform(-5, 5)))

    # Create nodes per island
    island_nodes = []
    for i, (cx, cy) in enumerate(centers):
        cluster = []
        for j in range(nodes_per_island):
            nx_val = cx + rng.uniform(-2, 2)
            ny_val = cy + rng.uniform(-2, 2)
            node = (round(nx_val, 6), round(ny_val, 6))
            G.add_node(node, pos=node)
            cluster.append(node)
        # Connect as path within island
        for j in range(len(cluster) - 1):
            a, b = cluster[j], cluster[j + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            d = (dx**2 + dy**2) ** 0.5
            G.add_edge(a, b, weight=d)
        island_nodes.append(cluster)

    return G


# -- UF and bridging code (simplified, order-clean version) --

def bridge_graph_kruskal(
    G: nx.Graph,
    max_bridge_distance: float = 15.0,
    component_order: list[int] | None = None,
) -> tuple[nx.Graph, list]:
    """Run the same Kruskal bridging as _ensure_skeleton_connectivity,
    but allow controlling component ID enumeration order.

    Returns (graph, list_of_added_edges).
    """
    if G.number_of_nodes() == 0:
        return G, []

    components = list(nx.connected_components(G))
    n_components = len(components)
    if n_components <= 1:
        return G, []

    nodes = list(G.nodes())
    positions = np.asarray(nodes, dtype=float)
    node_index = {node: i for i, node in enumerate(nodes)}

    comp_id = np.empty(len(nodes), dtype=np.int64)
    if component_order is not None:
        # Reorder component IDs
        assert len(component_order) == n_components
        remap = {old: new for new, old in enumerate(component_order)}
    else:
        remap = {i: i for i in range(n_components)}

    for cid, comp in enumerate(components):
        mapped_cid = remap.get(cid, cid)
        for node in comp:
            comp_id[node_index[node]] = mapped_cid

    # Simple UF
    uf_parent = list(range(n_components))
    uf_rank = [0] * n_components

    def uf_find(x):
        root = x
        while uf_parent[root] != root:
            root = uf_parent[root]
        while uf_parent[x] != root:
            uf_parent[x], x = root, uf_parent[x]
        return root

    def uf_union(a, b):
        ra, rb = uf_find(a), uf_find(b)
        if ra == rb:
            return False
        if uf_rank[ra] < uf_rank[rb]:
            ra, rb = rb, ra
        uf_parent[rb] = ra
        if uf_rank[ra] == uf_rank[rb]:
            uf_rank[ra] += 1
        return True

    merges = 0
    added_edges = []

    # Brute-force all cross-component pairs (synthetic graphs are small)
    candidates = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            ci, cj = comp_id[i], comp_id[j]
            if ci == cj:
                continue
            d = np.linalg.norm(positions[i] - positions[j])
            if d <= max_bridge_distance:
                candidates.append((d, i, j))

    # Sort: distance first, then (i, j) for deterministic tie-breaking
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))

    for d, i, j in candidates:
        ci, cj = uf_find(comp_id[i]), uf_find(comp_id[j])
        if ci == cj:
            continue
        G.add_edge(nodes[i], nodes[j], weight=float(d))
        uf_union(ci, cj)
        merges += 1
        added_edges.append((nodes[i], nodes[j], float(d)))
        if merges == n_components - 1:
            break

    return G, added_edges


def edge_set_normalized(G: nx.Graph) -> frozenset:
    """Return normalized edge set (lexicographically smaller node first)."""
    return frozenset(
        (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
        for e in G.edges()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="m3.json")
    parser.add_argument("--seeds", type=int, default=64, help="Number of permutation seeds")
    parser.add_argument("--n-islands", type=int, default=8, help="Number of island clusters")
    parser.add_argument("--nodes-per-island", type=int, default=5)
    parser.add_argument("--island-spread", type=float, default=50.0)
    parser.add_argument("--max-bridge-dist", type=float, default=20.0)
    args = parser.parse_args()

    result: dict[str, Any] = {
        "config": {
            "n_islands": args.n_islands,
            "nodes_per_island": args.nodes_per_island,
            "island_spread": args.island_spread,
            "max_bridge_dist": args.max_bridge_dist,
            "seeds": args.seeds,
        },
        "experiments": {},
    }

    # --- Experiment A: Component-ID permutation ---
    print("=== Experiment A: Component-ID permutation ===")
    G_base = make_graph_with_bridges(
        n_islands=args.n_islands,
        nodes_per_island=args.nodes_per_island,
        island_spread=args.island_spread,
        max_bridge_dist=args.max_bridge_dist,
        seed=0,
    )
    n_comp_base = nx.number_connected_components(G_base)
    print(f"  Base graph: {G_base.number_of_nodes()} nodes, "
          f"{G_base.number_of_edges()} edges, {n_comp_base} components")

    if n_comp_base <= 1:
        result["experiments"]["A_component_id"] = {
            "verdict": "SKIPPED",
            "note": "Graph already connected",
        }
    else:
        base_edges_before = edge_set_normalized(G_base)

        # Baseline: default component order
        G_a_base = G_base.copy()
        _, baseline_added = bridge_graph_kruskal(
            G_a_base, max_bridge_distance=args.max_bridge_dist,
            component_order=None,
        )
        baseline_edge_set = frozenset(
            (min(a, b), max(a, b)) for a, b, _ in baseline_added
        )
        print(f"  Baseline: {len(baseline_added)} bridges added")

        # Test with permuted component IDs
        import itertools
        comp_ids = list(range(n_comp_base))
        all_perms = list(itertools.permutations(comp_ids))
        # Cap at 120 permutations to avoid combinatorial explosion
        if len(all_perms) > 120:
            rng = random.Random(42)
            test_perms = [tuple(comp_ids)]  # baseline
            test_perms += [tuple(rng.sample(comp_ids, len(comp_ids))) for _ in range(119)]
        else:
            test_perms = all_perms

        different_count = 0
        for perm in test_perms:
            G_test = G_base.copy()
            _, added = bridge_graph_kruskal(
                G_test, max_bridge_distance=args.max_bridge_dist,
                component_order=list(perm),
            )
            test_edge_set = frozenset(
                (min(a, b), max(a, b)) for a, b, _ in added
            )
            if test_edge_set != baseline_edge_set:
                different_count += 1
                if different_count <= 3:
                    print(f"  DIFFERENT with perm={perm}: "
                          f"base={[list(e) for e in baseline_edge_set]}, "
                          f"test={[list(e) for e in test_edge_set]}")

        result["experiments"]["A_component_id"] = {
            "n_components": n_comp_base,
            "n_permutations_tested": len(test_perms),
            "n_different": different_count,
            "verdict": (
                "ORDER_OBSERVABLE" if different_count > 0
                else "ORDER_INSENSITIVE"
            ),
        }
        print(f"  Result: {different_count}/{len(test_perms)} permutations differ")
        print(f"  Verdict: {result['experiments']['A_component_id']['verdict']}")

    # --- Experiment B: Insertion-order permutation ---
    print("\n=== Experiment B: Insertion-order permutation ===")
    G_b_base = make_graph_with_bridges(
        n_islands=args.n_islands,
        nodes_per_island=args.nodes_per_island,
        island_spread=args.island_spread,
        max_bridge_dist=args.max_bridge_dist,
        seed=0,
    )
    n_comp_b = nx.number_connected_components(G_b_base)
    if n_comp_b <= 1:
        result["experiments"]["B_insertion_order"] = {
            "verdict": "SKIPPED",
            "note": "Graph already connected",
        }
    else:
        # Extract node/edge data
        all_nodes = list(G_b_base.nodes())
        all_edges = [(u, v, G_b_base[u][v]["weight"]) for u, v in G_b_base.edges()]
        edges_before = edge_set_normalized(G_b_base)

        # Baseline
        G_b_bl = G_b_base.copy()
        _, baseline_added_b = bridge_graph_kruskal(
            G_b_bl, max_bridge_distance=args.max_bridge_dist,
        )
        baseline_bridge = frozenset(
            (min(a, b), max(a, b)) for a, b, _ in baseline_added_b
        )
        print(f"  Baseline: {len(baseline_added_b)} bridges")

        different_count_b = 0
        for seed in range(args.seeds):
            rng = random.Random(seed + 1000)
            # Build graph with permuted edge insertion order
            G_perm = nx.Graph()
            perm_edges = list(all_edges)
            rng.shuffle(perm_edges)
            for u, v, w in perm_edges:
                G_perm.add_node(u, pos=u)
                G_perm.add_node(v, pos=v)
                G_perm.add_edge(u, v, weight=w)
            # Verify edge set identical
            assert edge_set_normalized(G_perm) == edges_before, \
                f"Edge set mismatch at seed {seed}"

            _, added = bridge_graph_kruskal(
                G_perm, max_bridge_distance=args.max_bridge_dist,
            )
            test_bridge = frozenset(
                (min(a, b), max(a, b)) for a, b, _ in added
            )
            if test_bridge != baseline_bridge:
                different_count_b += 1
                if different_count_b <= 3:
                    print(f"  Seed {seed}: DIFFERENT")

        result["experiments"]["B_insertion_order"] = {
            "n_components": n_comp_b,
            "n_seeds": args.seeds,
            "n_different": different_count_b,
            "verdict": (
                "ORDER_OBSERVABLE" if different_count_b > 0
                else "ORDER_INSENSITIVE"
            ),
        }
        print(f"  Result: {different_count_b}/{args.seeds} seeds differ")
        print(f"  Verdict: {result['experiments']['B_insertion_order']['verdict']}")

    # --- Experiment C: Variable ties ---
    print("\n=== Experiment C: Variable ties (deliberately equal distances) ===")
    G_c = make_graph_with_bridges(
        n_islands=8,
        nodes_per_island=3,
        island_spread=50.0,
        max_bridge_dist=30.0,
        seed=0,
        variable_ties=True,
    )
    n_comp_c = nx.number_connected_components(G_c)
    print(f"  Graph: {G_c.number_of_nodes()} nodes, {n_comp_c} components")

    if n_comp_c > 1:
        # Baseline
        G_c_bl = G_c.copy()
        _, baseline_added_c = bridge_graph_kruskal(G_c_bl, max_bridge_distance=30.0)
        baseline_bridge_c = frozenset(
            (min(a, b), max(a, b)) for a, b, _ in baseline_added_c
        )
        print(f"  Baseline: {len(baseline_added_c)} bridges")

        # Count ties
        all_nodes_c = list(G_c.nodes())
        positions_c = np.asarray(all_nodes_c, dtype=float)
        components_c = list(nx.connected_components(G_c))
        node_index_c = {n: i for i, n in enumerate(all_nodes_c)}
        comp_id_c = np.empty(len(all_nodes_c), dtype=np.int64)
        for cid, comp in enumerate(components_c):
            for node in comp:
                comp_id_c[node_index_c[node]] = cid

        # Collect all cross-component pairs
        from collections import Counter
        candidates_c = []
        for i in range(len(all_nodes_c)):
            for j in range(i + 1, len(all_nodes_c)):
                if comp_id_c[i] == comp_id_c[j]:
                    continue
                d = np.linalg.norm(positions_c[i] - positions_c[j])
                if d <= 30.0:
                    candidates_c.append((round(d, 6), i, j))
        dist_counter = Counter(d for d, _, _ in candidates_c)
        ties = {d: c for d, c in dist_counter.items() if c > 1}
        print(f"  Tied distances: {len(ties)}, max tie: {max(dist_counter.values())}")

        # Permute insertion order
        all_edges_c = [(u, v, G_c[u][v]["weight"]) for u, v in G_c.edges()]
        edges_before_c = edge_set_normalized(G_c)
        different_count_c = 0
        for seed in range(args.seeds):
            rng = random.Random(seed + 2000)
            G_perm_c = nx.Graph()
            perm_edges_c = list(all_edges_c)
            rng.shuffle(perm_edges_c)
            for u, v, w in perm_edges_c:
                G_perm_c.add_node(u, pos=u)
                G_perm_c.add_node(v, pos=v)
                G_perm_c.add_edge(u, v, weight=w)
            assert edge_set_normalized(G_perm_c) == edges_before_c

            _, added_c = bridge_graph_kruskal(G_perm_c, max_bridge_distance=30.0)
            test_bridge_c = frozenset(
                (min(a, b), max(a, b)) for a, b, _ in added_c
            )
            if test_bridge_c != baseline_bridge_c:
                different_count_c += 1

        result["experiments"]["C_variable_ties"] = {
            "n_components": n_comp_c,
            "n_tied_distances": len(ties),
            "max_tie": max(dist_counter.values()) if dist_counter else 0,
            "n_seeds": args.seeds,
            "n_different": different_count_c,
            "verdict": (
                "ORDER_OBSERVABLE" if different_count_c > 0
                else "ORDER_INSENSITIVE"
            ),
        }
        print(f"  Result: {different_count_c}/{args.seeds} seeds differ")
        print(f"  Verdict: {result['experiments']['C_variable_ties']['verdict']}")

    # Overall verdict
    any_observable = any(
        exp.get("verdict") == "ORDER_OBSERVABLE"
        for exp in result["experiments"].values()
    )
    result["overall_verdict"] = (
        "ORDER_OBSERVABLE" if any_observable else "ORDER_INSENSITIVE"
    )
    print(f"\nOVERALL VERDICT: {result['overall_verdict']}")

    json.dump(result, open(args.out, "w"), indent=2, default=str)
    print(f"Results written to {args.out}")


if __name__ == "__main__":
    main()
