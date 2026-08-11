#!/usr/bin/env python3
"""
M1: Louvain community detection determinism.

Falsifier Q-A1: Does best_partition(G, random_state=42) produce the same
partition across interpreter runs, graph insertion orders, and networkx /
python-louvain versions? Is the community->components assignment
order-stable?

Three sub-experiments:
  A. Same graph (from_numpy_array), fresh interpreters, different PYTHONHASHSEED.
  B. Same graph, insertion-order perturbation (nodes/edges added in random order).
  C. Modularity score stability.

Output: JSON to --out.
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import networkx as nx
import community as community_louvain
import numpy as np

# ---- test graphs -----------------------------------------------------------

def _make_house_graph() -> np.ndarray:
    """8-node graph with a bridge: two 4-node cliques connected by one edge."""
    adj = np.array([
        [0, 1, 1, 0, 0, 0, 0, 0],
        [1, 0, 1, 0, 0, 0, 0, 0],
        [1, 1, 0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 1, 1, 0, 0],
        [0, 0, 0, 1, 0, 1, 0, 0],
        [0, 0, 0, 1, 1, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 1],
        [0, 0, 0, 0, 0, 0, 1, 0],
    ], dtype=float)
    return adj


def _make_random_graph(n: int = 15, seed: int = 42) -> np.ndarray:
    """Random symmetric adjacency, thresholded to 0/1."""
    rng = np.random.default_rng(seed)
    adj = rng.random((n, n))
    adj = (adj + adj.T) / 2
    np.fill_diagonal(adj, 0)
    return (adj > 0.3).astype(float)


# ---- sub-experiment A: fresh-interpreter determinism ----------------------

_LOUVAIN_SUBPROCESS_SCRIPT = """
import networkx as nx
import community as community_louvain
import numpy as np
import json, sys

adj = {adj}
G = nx.from_numpy_array(np.array(adj, dtype=float))
partition = community_louvain.best_partition(G, weight='weight', random_state=42)
result = [partition[i] for i in sorted(partition.keys())]
modularity = community_louvain.modularity(partition, G, weight='weight')
print(json.dumps({{"partition": result, "modularity": modularity}}))
"""


def _run_fresh_interpreter(python_path: str, script: str, n_runs: int) -> list[dict]:
    results = []
    for i in range(n_runs):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = str(1000 + i)
        proc = subprocess.run(
            [python_path, "-c", script],
            capture_output=True, text=True, env=env,
        )
        if proc.returncode != 0:
            results.append({"error": proc.stderr.strip()})
        else:
            try:
                results.append(json.loads(proc.stdout.strip()))
            except json.JSONDecodeError:
                results.append({"error": f"bad JSON: {proc.stdout.strip()}"})
    return results


# ---- sub-experiment B: insertion-order perturbation -----------------------

def _permute_graph(adj: np.ndarray, seed: int, add_weighted: bool = False) -> nx.Graph:
    """Build a graph with permuted node/edge insertion order."""
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
            w = adj[i, j]
            if w > 0:
                edges.append((i, j, float(w)))
    rng.shuffle(edges)
    if add_weighted:
        for u, v, w in edges:
            G.add_edge(u, v, weight=w)
    else:
        for u, v, w in edges:
            G.add_edge(u, v)
    return G


# ---- main -----------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="M1: Louvain determinism")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--seeds", type=int, default=32, help="Permutation seeds for B")
    parser.add_argument("--fresh-runs", type=int, default=20, help="Fresh-interpreter runs for A")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter path")
    args = parser.parse_args()

    results: dict[str, Any] = {
        "tool": "m1_louvain_determinism",
        "python_version": sys.version,
        "networkx_version": nx.__version__,
    }

    # ---- A: fresh-interpreter determinism (from_numpy_array) ----
    adj_house = _make_house_graph()
    script = _LOUVAIN_SUBPROCESS_SCRIPT.format(adj=adj_house.tolist())
    runs_a = _run_fresh_interpreter(args.python, script, args.fresh_runs)

    partitions_a = set()
    modularities_a = set()
    errors_a = 0
    for r in runs_a:
        if "error" in r:
            errors_a += 1
        else:
            partitions_a.add(tuple(r["partition"]))
            modularities_a.add(r["modularity"])

    results["A_from_numpy_array"] = {
        "graph": "8-node bridged cliques",
        "runs": args.fresh_runs,
        "errors": errors_a,
        "distinct_partitions": len(partitions_a),
        "distinct_modularities": len(modularities_a),
        "modularities": sorted(modularities_a),
        "deterministic": len(partitions_a) == 1,
    }

    # Also test on random graph
    adj_rand = _make_random_graph(15)
    script_rand = _LOUVAIN_SUBPROCESS_SCRIPT.format(adj=adj_rand.tolist())
    runs_a2 = _run_fresh_interpreter(args.python, script_rand, args.fresh_runs)
    partitions_a2 = set()
    modularities_a2 = set()
    errors_a2 = 0
    for r in runs_a2:
        if "error" in r:
            errors_a2 += 1
        else:
            partitions_a2.add(tuple(r["partition"]))
            modularities_a2.add(r["modularity"])

    results["A2_random_graph"] = {
        "graph": "15-node random thresholded",
        "runs": args.fresh_runs,
        "errors": errors_a2,
        "distinct_partitions": len(partitions_a2),
        "distinct_modularities": len(modularities_a2),
        "modularities": sorted(modularities_a2),
        "deterministic": len(partitions_a2) == 1,
    }

    # ---- B: insertion-order perturbation ----
    for graph_name, adj_fn in [
        ("house_8", _make_house_graph),
        ("random_15", lambda: _make_random_graph(15)),
    ]:
        adj = adj_fn()
        partitions_b = set()
        modularities_b = set()
        for seed in range(args.seeds):
            G = _permute_graph(adj, seed, add_weighted=True)
            partition = community_louvain.best_partition(G, weight="weight", random_state=42)
            partitions_b.add(tuple(partition[i] for i in sorted(partition.keys())))
            modularities_b.add(
                community_louvain.modularity(partition, G, weight="weight")
            )
        key = f"B_insertion_order_{graph_name}"
        results[key] = {
            "seeds": args.seeds,
            "distinct_partitions": len(partitions_b),
            "distinct_modularities": len(modularities_b),
            "modularities": sorted(modularities_b),
            "order_stable": len(partitions_b) == 1,
        }

    # ---- C: within-process stability (same graph, repeated calls) ----
    adj = _make_house_graph()
    G = nx.from_numpy_array(adj)
    partitions_c = set()
    for _ in range(50):
        partition = community_louvain.best_partition(G, weight="weight", random_state=42)
        partitions_c.add(tuple(partition[i] for i in sorted(partition.keys())))
    results["C_within_process"] = {
        "calls": 50,
        "distinct_partitions": len(partitions_c),
        "deterministic": len(partitions_c) == 1,
    }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
