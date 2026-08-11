#!/usr/bin/env python3
"""
M2: Kernighan-Lin bisection determinism.

Falsifier Q-A2: Is kernighan_lin_bisection output order-stable across
insertion orders / seeds?

Two sub-experiments:
  A. Same graph (from_numpy_array), repeated calls (KL has random initial
     partitions — is it seeded?).
  B. Insertion-order perturbation.

Output: JSON to --out.
"""

import argparse
import json
import sys
from typing import Any

import networkx as nx
import numpy as np


def _make_house_adj() -> np.ndarray:
    return np.array([
        [0, 1, 1, 0, 0, 0, 0, 0],
        [1, 0, 1, 0, 0, 0, 0, 0],
        [1, 1, 0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 1, 1, 0, 0],
        [0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 0, 1, 1, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 1],
        [0, 0, 0, 0, 0, 0, 1, 0],
    ], dtype=float)


def _make_larger_adj(n: int = 12, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    adj = rng.random((n, n))
    adj = (adj + adj.T) / 2
    np.fill_diagonal(adj, 0)
    return (adj > 0.4).astype(float)


def _permute_graph(adj: np.ndarray, seed: int) -> nx.Graph:
    rng = np.random.default_rng(seed)
    G = nx.Graph()
    n = adj.shape[0]
    nodes = list(range(n))
    rng.shuffle(nodes)
    for nd in nodes:
        G.add_node(nd)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if adj[i, j] > 0:
                edges.append((i, j, float(adj[i, j])))
    rng.shuffle(edges)
    for u, v, w in edges:
        G.add_edge(u, v, weight=w)
    return G


def _partition_key(p1: set, p2: set) -> tuple:
    """Canonical key for a bisection: sorted pair of sorted tuples."""
    a = tuple(sorted(p1))
    b = tuple(sorted(p2))
    return (a, b) if a < b else (b, a)


def main() -> None:
    parser = argparse.ArgumentParser(description="M2: KL bisection determinism")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--seeds", type=int, default=64, help="Permutation seeds for B")
    parser.add_argument("--repeat-calls", type=int, default=100, help="Repeated calls on same graph for A")
    args = parser.parse_args()

    results: dict[str, Any] = {
        "tool": "m2_kl_determinism",
        "python_version": sys.version,
        "networkx_version": nx.__version__,
    }

    # ---- A: same graph, repeated calls ----
    adj = _make_house_adj()
    G = nx.from_numpy_array(adj)
    partitions_a = set()
    errors_a = 0
    for _ in range(args.repeat_calls):
        try:
            p1, p2 = nx.community.kernighan_lin_bisection(G, weight="weight")
            partitions_a.add(_partition_key(set(p1), set(p2)))
        except Exception:
            errors_a += 1

    results["A_same_graph_repeated"] = {
        "graph": "8-node bridged cliques",
        "calls": args.repeat_calls,
        "errors": errors_a,
        "distinct_partitions": len(partitions_a),
        "partitions": [list(p) for p in sorted(partitions_a)],
        "deterministic": len(partitions_a) == 1,
    }

    # Larger graph
    adj2 = _make_larger_adj(12)
    G2 = nx.from_numpy_array(adj2)
    partitions_a2 = set()
    errors_a2 = 0
    for _ in range(args.repeat_calls):
        try:
            p1, p2 = nx.community.kernighan_lin_bisection(G2, weight="weight")
            partitions_a2.add(_partition_key(set(p1), set(p2)))
        except Exception:
            errors_a2 += 1

    results["A2_larger_graph"] = {
        "graph": "12-node random thresholded",
        "calls": args.repeat_calls,
        "errors": errors_a2,
        "distinct_partitions": len(partitions_a2),
        "deterministic": len(partitions_a2) == 1,
    }

    # ---- B: insertion-order perturbation ----
    for graph_name, adj_fn in [
        ("house_8", _make_house_adj),
        ("larger_12", lambda: _make_larger_adj(12)),
    ]:
        adj = adj_fn()
        partitions_b = set()
        errors_b = 0
        for seed in range(args.seeds):
            G = _permute_graph(adj, seed)
            try:
                p1, p2 = nx.community.kernighan_lin_bisection(G, weight="weight")
                partitions_b.add(_partition_key(set(p1), set(p2)))
            except Exception:
                errors_b += 1

        key = f"B_insertion_order_{graph_name}"
        results[key] = {
            "seeds": args.seeds,
            "errors": errors_b,
            "distinct_partitions": len(partitions_b),
            "partitions": [list(p) for p in sorted(partitions_b)][:10],
            "order_stable": len(partitions_b) == 1,
        }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
