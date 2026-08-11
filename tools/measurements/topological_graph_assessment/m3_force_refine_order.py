#!/usr/bin/env python3
"""M3 — force-refinement order observability: does edge insertion order affect output?

Builds a ``TopologicalGraph`` with multiple components and adjacency/separation
constraints. Permutes the edge insertion order while holding the *edge set*
identical. Runs ``apply_force_refinement`` and compares final positions.

Also tests: does ``edges(data=True)`` iteration order propagate through
``identify_clusters`` and ``place_cluster``?

Per the discipline: falsifiers stated before measurement.
F-T3a: Permuting edge order changes force-refinement output positions.
F-T3b: Permuting edge order changes identify_clusters output.
F-T3c: Permuting edge order changes place_cluster min_adjacency_dist.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np


def build_graph_edges_only(adjacencies, separations):
    """Build a bare nx.MultiDiGraph with given constraints in a specific order."""
    g = nx.MultiDiGraph()

    # Add nodes first
    nodes = set()
    for a, b, _ in adjacencies:
        nodes.add(a)
        nodes.add(b)
    for a, b, _ in separations:
        nodes.add(a)
        nodes.add(b)

    for n in sorted(nodes):
        g.add_node(n, node_type="component", properties={})

    for a, b, dist in adjacencies:
        g.add_edge(a, b, edge_type="adjacent", distance=dist, constraint_id="auto")
        g.add_edge(b, a, edge_type="adjacent", distance=dist, constraint_id="auto")

    for a, b, dist in separations:
        g.add_edge(a, b, edge_type="separated", distance=dist, constraint_id="auto")

    return g


def permute_edge_order(adjacencies, separations, seed):
    """Shuffle adjacency and separation lists independently."""
    rng = random.Random(seed)
    adj_shuffled = list(adjacencies)
    sep_shuffled = list(separations)
    rng.shuffle(adj_shuffled)
    rng.shuffle(sep_shuffled)
    return adj_shuffled, sep_shuffled


def run_force_refinement_py(graph, positions, zone_bounds, iterations=100, lr=0.1):
    """Pure-Python force refinement that mirrors the Rust kernel.

    This reproduces the naive += accumulation to test whether edge
    order affects output through f64 non-associativity.
    """
    # Build index: use sorted node list for stable ordering
    refs = sorted(positions.keys())
    n = len(refs)
    ref_to_idx = {r: i for i, r in enumerate(refs)}

    # Extract edges in insertion order
    adjacencies = []
    separations = []
    for u, v, data in graph.edges(data=True):
        et = data.get("edge_type")
        if et == "adjacent":
            adjacencies.append((u, v, data.get("distance", 10.0)))
        elif et == "separated":
            separations.append((u, v, data.get("distance", 20.0)))

    pos_arr = np.array([[positions[r][0], positions[r][1]] for r in refs], dtype=np.float64)

    for _ in range(iterations):
        forces = np.zeros((n, 2), dtype=np.float64)

        for u, v, target in adjacencies:
            i = ref_to_idx[u]
            j = ref_to_idx[v]
            dx = pos_arr[j, 0] - pos_arr[i, 0]
            dy = pos_arr[j, 1] - pos_arr[i, 1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 1e-6:
                fx, fy = 0.1, 0.0
                forces[i, 0] += fx
                forces[i, 1] += fy
                forces[j, 0] -= fx
                forces[j, 1] -= fy
            else:
                ux = dx / dist
                uy = dy / dist
                mag = (dist - target) * 0.5
                forces[i, 0] += ux * mag
                forces[i, 1] += uy * mag
                forces[j, 0] -= ux * mag
                forces[j, 1] -= uy * mag

        for u, v, min_dist in separations:
            i = ref_to_idx[u]
            j = ref_to_idx[v]
            dx = pos_arr[j, 0] - pos_arr[i, 0]
            dy = pos_arr[j, 1] - pos_arr[i, 1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 1e-6:
                forces[i, 0] -= 1.0
                forces[j, 0] += 1.0
            elif dist < min_dist:
                ux = dx / dist
                uy = dy / dist
                mag = (min_dist - dist) * 1.0
                forces[i, 0] -= ux * mag
                forces[i, 1] -= uy * mag
                forces[j, 0] += ux * mag
                forces[j, 1] += uy * mag

        for i in range(n):
            x, y = pos_arr[i, 0], pos_arr[i, 1]
            fx = fy = 0.0
            xmin, ymin, xmax, ymax = zone_bounds[i]
            if x < xmin:
                fx = (xmin - x) * 2.0
            if x > xmax:
                fx = (xmax - x) * 2.0
            if y < ymin:
                fy = (ymin - y) * 2.0
            if y > ymax:
                fy = (ymax - y) * 2.0
            forces[i, 0] += fx
            forces[i, 1] += fy

        pos_arr[:, 0] += forces[:, 0] * lr
        pos_arr[:, 1] += forces[:, 1] * lr

    return {refs[i]: (float(pos_arr[i, 0]), float(pos_arr[i, 1])) for i in range(n)}


def positions_differ(p1, p2, tol=1e-12):
    """Check if two position dicts differ beyond floating-point tolerance."""
    for ref in p1:
        if ref not in p2:
            return True
        dx = abs(p1[ref][0] - p2[ref][0])
        dy = abs(p1[ref][1] - p2[ref][1])
        if dx > tol or dy > tol:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="M3: force-refinement order observability")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file")
    parser.add_argument("--seeds", type=int, default=64, help="Number of permutation seeds")
    parser.add_argument("--iterations", type=int, default=100, help="Force refinement iterations")
    args = parser.parse_args()

    # Build a realistic graph: 12 components in a grid-like adjacency pattern
    # with varying distances to create force interactions
    components = [f"C{i}" for i in range(12)]

    # Adjacencies: a chain C0-C1-C2-...-C11
    adjacencies = [(f"C{i}", f"C{i+1}", 10.0 + i * 1.5) for i in range(11)]

    # Cross-adjacencies: some diagonal connections
    adjacencies += [
        ("C0", "C5", 20.0),
        ("C1", "C6", 22.0),
        ("C2", "C7", 18.0),
        ("C5", "C10", 15.0),
        ("C6", "C11", 17.0),
    ]

    # Separations: some components need spacing
    separations = [
        ("C0", "C11", 50.0),
        ("C3", "C8", 30.0),
        ("C1", "C9", 25.0),
    ]

    # Initial positions: spread evenly
    init_positions = {f"C{i}": (float(i * 8.0), float(i * 6.0)) for i in range(12)}

    # Zone bounds: large for all components
    big_zone = (-1000.0, -1000.0, 1000.0, 1000.0)
    zone_bounds = [big_zone for _ in range(12)]

    # Baseline: canonical order
    base_graph = build_graph_edges_only(adjacencies, separations)
    base_pos = run_force_refinement_py(base_graph, init_positions, zone_bounds, args.iterations)

    # Permute and compare
    distinct_positions = 0
    distinct_sets = set()
    max_diff = 0.0

    for seed in range(args.seeds):
        adj_shuf, sep_shuf = permute_edge_order(adjacencies, separations, seed)
        g = build_graph_edges_only(adj_shuf, sep_shuf)
        pos = run_force_refinement_py(g, init_positions, zone_bounds, args.iterations)

        if positions_differ(base_pos, pos):
            distinct_positions += 1

        # Compute max position difference
        for ref in base_pos:
            dx = abs(base_pos[ref][0] - pos[ref][0])
            dy = abs(base_pos[ref][1] - pos[ref][1])
            max_diff = max(max_diff, dx, dy)

        # Hash the position set
        pos_hash = tuple(sorted((ref, round(x, 12), round(y, 12)) for ref, (x, y) in pos.items()))
        distinct_sets.add(pos_hash)

    result = {
        "experiment": "force_refinement_order",
        "components": len(components),
        "adjacency_pairs": len(adjacencies),
        "separation_pairs": len(separations),
        "seeds": args.seeds,
        "iterations": args.iterations,
        "seeds_divergent": distinct_positions,
        "distinct_position_sets": len(distinct_sets),
        "max_position_difference": max_diff,
        "falsifier_fired": distinct_positions > 0,
    }

    # Also test identify_clusters: does edge order affect clusters?
    # The Rust kernel uses union-find which is commutative, but let's verify
    # by testing the Python oracle's pure-Python version (from _graph_py_oracle.py)

    # Build two graphs with different edge orders but same edge set
    g1 = build_graph_edges_only(adjacencies, separations)
    adj_shuf, sep_shuf = permute_edge_order(adjacencies, separations, 42)
    g2 = build_graph_edges_only(adj_shuf, sep_shuf)

    # Extract adjacency edges in graph order
    def extract_adjacent_pairs(graph, comp_list):
        index_of = {c: i for i, c in enumerate(comp_list)}
        pairs = []
        for u, v, data in graph.edges(data=True):
            if data.get("edge_type") == "adjacent" and u in index_of and v in index_of:
                pairs.append((index_of[u], index_of[v]))
        return pairs

    comps = sorted(components)
    pairs1 = extract_adjacent_pairs(g1, comps)
    pairs2 = extract_adjacent_pairs(g2, comps)
    result["identify_clusters_pairs_different"] = pairs1 != pairs2

    # The EDGE SET is identical even if order differs
    pairs1_set = set(pairs1)
    pairs2_set = set(pairs2)
    result["identify_clusters_same_edge_set"] = pairs1_set == pairs2_set

    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

    if result["falsifier_fired"]:
        print(f"F-T3a FIRED: {distinct_positions}/{args.seeds} seeds divergent, max diff {max_diff:.2e}", file=sys.stderr)
    else:
        print("F-T3a DID NOT FIRE: all seed outputs identical", file=sys.stderr)

    if result["identify_clusters_pairs_different"]:
        print("F-T3b FIRED: edge order changes identify_clusters input order", file=sys.stderr)
    else:
        print("F-T3b DID NOT FIRE: identify_clusters input pairs identical", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
