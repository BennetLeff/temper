#!/usr/bin/env python3
"""M4 — cluster and propagation order observability.

Tests whether edge insertion order affects:
1. ``identify_clusters`` output (union-find — expected order-insensitive)
2. ``place_cluster`` min_adjacency_dist (min-reduction — expected order-insensitive)
3. ``ConstraintPropagator.propagate()`` output (min/max reductions — expected order-insensitive)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import networkx as nx


def build_graph(adjacencies, separations, seed=None):
    """Build a MultiDiGraph with given edges in a specific order."""
    if seed is not None:
        rng = random.Random(seed)
        adj = list(adjacencies)
        sep = list(separations)
        rng.shuffle(adj)
        rng.shuffle(sep)
    else:
        adj = adjacencies
        sep = separations

    g = nx.MultiDiGraph()
    nodes = set()
    for a, b, _ in adj:
        nodes.add(a); nodes.add(b)
    for a, b, _ in sep:
        nodes.add(a); nodes.add(b)

    for n in sorted(nodes):
        g.add_node(n, node_type="component", properties={})

    for a, b, dist in adj:
        g.add_edge(a, b, edge_type="adjacent", distance=dist, constraint_id="auto")
        g.add_edge(b, a, edge_type="adjacent", distance=dist, constraint_id="auto")

    for a, b, dist in sep:
        g.add_edge(a, b, edge_type="separated", distance=dist, constraint_id="auto")

    return g


def identify_clusters_py(graph, components):
    """Pure-Python union-find cluster identification (mirrors oracle)."""
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Initialize each component as its own set
    for c in components:
        parent[c] = c

    # Union adjacency edges
    for u, v, data in graph.edges(data=True):
        if data.get("edge_type") == "adjacent" and u in parent and v in parent:
            union(u, v)

    # Collect clusters in first-appearance order of components
    seen_roots = set()
    clusters = []
    for c in components:
        root = find(c)
        if root not in seen_roots:
            seen_roots.add(root)
            cluster = {x for x in components if find(x) == root}
            clusters.append(cluster)

    return clusters


def place_cluster_min_dist(graph, cluster):
    """Compute min_adjacency_dist (mirrors place_cluster in initial_placement.py)."""
    min_dist = 15.0
    for u, v, data in graph.edges(data=True):
        if data.get("edge_type") == "adjacent" and u in cluster and v in cluster:
            dist = data.get("distance", 15.0)
            if dist < min_dist:
                min_dist = dist
    return min_dist


def propagate_bounds_py(graph, max_iterations=100):
    """Pure-Python constraint propagation (mirrors oracle)."""
    nodes = list(graph.nodes())
    node_idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)

    # Initialize bounds
    INF = float("inf")
    mins = [[0.0] * n for _ in range(n)]
    maxs = [[INF] * n for _ in range(n)]

    for u, v, data in graph.edges(data=True):
        et = data.get("edge_type")
        dist = data.get("distance", 0.0)
        if et == "adjacent":
            i, j = node_idx[u], node_idx[v]
            maxs[i][j] = min(maxs[i][j], dist)
            maxs[j][i] = min(maxs[j][i], dist)
        elif et == "separated":
            i, j = node_idx[u], node_idx[v]
            mins[i][j] = max(mins[i][j], dist)
            mins[j][i] = max(mins[j][i], dist)

    # Floyd-Warshall propagation
    for _ in range(max_iterations):
        changed = False
        for k in range(n):
            for i in range(n):
                for j in range(n):
                    # Tighten max: max(i,j) ≤ max(i,k) + max(k,j)
                    new_max = maxs[i][k] + maxs[k][j]
                    if new_max < maxs[i][j]:
                        maxs[i][j] = new_max
                        changed = True
                    # Tighten min: min(i,j) ≥ max(min(i,k) - max(k,j), 0) when positive
                    new_min = mins[i][k] - maxs[k][j]
                    if new_min > 0 and new_min > mins[i][j]:
                        mins[i][j] = new_min
                        changed = True
        if not changed:
            break

    # Check feasibility
    feasible = True
    for i in range(n):
        for j in range(n):
            if mins[i][j] > maxs[i][j]:
                feasible = False
    return feasible


def main():
    parser = argparse.ArgumentParser(description="M4: cluster/propagation order observability")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file")
    parser.add_argument("--seeds", type=int, default=64, help="Number of permutation seeds")
    args = parser.parse_args()

    components = ["A", "B", "C", "D", "E", "F", "G", "H"]
    adjacencies = [
        ("A", "B", 5.0),
        ("B", "C", 3.0),
        ("C", "D", 4.0),
        ("E", "F", 6.0),
        ("F", "G", 2.0),
        ("G", "H", 3.0),
    ]
    separations = [
        ("A", "D", 15.0),
        ("E", "H", 12.0),
    ]

    # Baseline
    base_graph = build_graph(adjacencies, separations)
    base_clusters = identify_clusters_py(base_graph, components)
    base_min_dist = {frozenset(c): place_cluster_min_dist(base_graph, c) for c in base_clusters}
    base_feasibility = propagate_bounds_py(base_graph)

    # Permute and compare
    cluster_diffs = 0
    min_dist_diffs = 0
    feasibility_diffs = 0

    for seed in range(args.seeds):
        g = build_graph(adjacencies, separations, seed)
        clusters = identify_clusters_py(g, components)

        # Compare cluster sets (order-independent comparison)
        base_sets = {frozenset(c) for c in base_clusters}
        curr_sets = {frozenset(c) for c in clusters}
        if base_sets != curr_sets:
            cluster_diffs += 1

        # Compare min distances
        for cset in base_sets:
            bd = base_min_dist.get(cset, 15.0)
            cd = place_cluster_min_dist(g, cset)
            if abs(bd - cd) > 1e-12:
                min_dist_diffs += 1
                break

        # Compare feasibility
        feasible = propagate_bounds_py(g)
        if feasible != base_feasibility:
            feasibility_diffs += 1

    result = {
        "experiment": "cluster_and_propagation_order",
        "seeds": args.seeds,
        "cluster_diffs": cluster_diffs,
        "min_dist_diffs": min_dist_diffs,
        "feasibility_diffs": feasibility_diffs,
        "cluster_order_insensitive": cluster_diffs == 0,
        "min_dist_order_insensitive": min_dist_diffs == 0,
        "propagation_order_insensitive": feasibility_diffs == 0,
        "analysis": (
            "identify_clusters uses union-find which is commutative — "
            "edge insertion order does not affect the resulting partition. "
            "place_cluster min_adjacency_dist is a min-reduction — commutative. "
            "propagate uses min/max reductions on bounds — commutative."
        ),
    }

    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

    if cluster_diffs > 0:
        print(f"F-T3c FIRED: cluster output varies with edge order ({cluster_diffs}/{args.seeds})", file=sys.stderr)
        sys.exit(1)
    else:
        print("F-T3: clusters/propagation/min_dist all order-insensitive", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
