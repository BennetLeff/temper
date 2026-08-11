#!/usr/bin/env python3
"""
M4: Spectral layout sign stability and insertion-order sensitivity.

Falsifier Q-B1: Is spectral_layout output stable across runs / versions, or
does the eigenvector sign convention flip?

Three sub-experiments:
  A. Same graph (from_numpy_array), fresh interpreters, different
     PYTHONHASHSEED — sign stability.
  B. Same graph, insertion-order perturbation — coordinate sensitivity.
  C. Does the output differ only by sign flips, or are the actual layouts
     different?

Output: JSON to --out.
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import networkx as nx
import numpy as np


_SPECTRAL_SUBPROCESS_SCRIPT = """
import networkx as nx
import json
G = nx.Graph()
G.add_edges_from({edges})
pos = nx.spectral_layout(G, weight='weight', dim=2)
coords = [[float(pos[i][0]), float(pos[i][1])] for i in sorted(pos.keys())]
print(json.dumps(coords))
"""


def _house_edges() -> list[tuple[int, int]]:
    return [(0,1),(1,2),(2,3),(3,0),(0,2),(3,4),(4,5),(5,6),(6,7),(7,4),(5,7)]


def _star_ring_edges() -> list[tuple[int, int]]:
    """Center hub + outer ring + two leaves (degenerate eigenvalues possible)."""
    return [(0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1),(1,5),(3,6)]


def _permute_graph_from_edge_list(edges: list[tuple[int, int]], seed: int) -> nx.Graph:
    rng = np.random.default_rng(seed)
    G = nx.Graph()
    all_nodes = set()
    for u, v in edges:
        all_nodes.add(u)
        all_nodes.add(v)
    node_list = list(all_nodes)
    rng.shuffle(node_list)
    for n in node_list:
        G.add_node(n)
    shuffled_edges = list(edges)
    rng.shuffle(shuffled_edges)
    for u, v in shuffled_edges:
        G.add_edge(u, v)
    return G


def _canonical_coords(pos: dict, tol: int = 8) -> tuple:
    """Round coordinates and tuple-ify for hashing."""
    return tuple(
        (round(float(pos[i][0]), tol), round(float(pos[i][1]), tol))
        for i in sorted(pos.keys())
    )


def _sign_normalize(coords: np.ndarray) -> np.ndarray:
    """Flip sign of each axis so the first coordinate component is non-negative."""
    result = coords.copy()
    for axis in range(coords.shape[1]):
        col = coords[:, axis]
        # Use the max-abs element to decide sign flip
        idx = np.argmax(np.abs(col))
        if col[idx] < 0:
            result[:, axis] = -result[:, axis]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="M4: Spectral layout sign stability")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--seeds", type=int, default=32, help="Permutation seeds for B")
    parser.add_argument("--fresh-runs", type=int, default=10, help="Fresh-interpreter runs for A")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter path")
    args = parser.parse_args()

    results: dict[str, Any] = {
        "tool": "m4_spectral_sign",
        "python_version": sys.version,
        "networkx_version": nx.__version__,
    }

    # ---- A: fresh-interpreter determinism ----
    for graph_name, edges_fn in [
        ("house_11edge", _house_edges),
        ("star_ring_10edge", _star_ring_edges),
    ]:
        edges = edges_fn()
        script = _SPECTRAL_SUBPROCESS_SCRIPT.format(edges=edges)
        coords_a = set()
        errors_a = 0
        for i in range(args.fresh_runs):
            env = os.environ.copy()
            env["PYTHONHASHSEED"] = str(2000 + i)
            proc = subprocess.run(
                [args.python, "-c", script],
                capture_output=True, text=True, env=env,
            )
            if proc.returncode != 0:
                errors_a += 1
            else:
                try:
                    c = json.loads(proc.stdout.strip())
                    # Round for comparison
                    rounded = tuple(
                        (round(x, 8), round(y, 8)) for x, y in c
                    )
                    coords_a.add(rounded)
                except json.JSONDecodeError:
                    errors_a += 1

        key = f"A_fresh_interpreter_{graph_name}"
        results[key] = {
            "edges": len(edges),
            "runs": args.fresh_runs,
            "errors": errors_a,
            "distinct_coordinate_sets": len(coords_a),
            "deterministic": len(coords_a) == 1,
        }

    # ---- B: insertion-order perturbation ----
    for graph_name, edges_fn in [
        ("house_11edge", _house_edges),
        ("star_ring_10edge", _star_ring_edges),
    ]:
        edges = edges_fn()
        coords_b = set()
        sign_normalized = set()
        for seed in range(args.seeds):
            G = _permute_graph_from_edge_list(edges, seed)
            pos = nx.spectral_layout(G, weight="weight", dim=2)
            c = _canonical_coords(pos)
            coords_b.add(c)
            # Sign-normalize
            arr = np.array([[pos[i][0], pos[i][1]] for i in sorted(pos.keys())])
            sn = _sign_normalize(arr)
            sign_normalized.add(tuple(
                (round(float(sn[i, 0]), 8), round(float(sn[i, 1]), 8))
                for i in range(sn.shape[0])
            ))

        key = f"B_insertion_order_{graph_name}"
        results[key] = {
            "edges": len(edges),
            "seeds": args.seeds,
            "distinct_raw_coordinate_sets": len(coords_b),
            "distinct_sign_normalized": len(sign_normalized),
            "order_stable_raw": len(coords_b) == 1,
            "order_stable_sign_normalized": len(sign_normalized) == 1,
        }

    # ---- C: within-process stability ----
    edges = _house_edges()
    G = nx.Graph()
    G.add_edges_from(edges)
    coords_c = set()
    for _ in range(50):
        pos = nx.spectral_layout(G, weight="weight", dim=2)
        c = _canonical_coords(pos)
        coords_c.add(c)
    results["C_within_process"] = {
        "calls": 50,
        "distinct_coordinate_sets": len(coords_c),
        "deterministic": len(coords_c) == 1,
    }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
