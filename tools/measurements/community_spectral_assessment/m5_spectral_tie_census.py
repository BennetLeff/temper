#!/usr/bin/env python3
"""
M5: Spectral layout tie census and consumer analysis.

Falsifier Q-B1 (deepened): How much do the spectral coordinates differ
across insertion orders? Is the difference limited to orthogonal
transformations (sign flips, rotations), or are the actual relative
positions materially different?

Also: what does the consumer (heuristics/pipeline.py) do with the output?
Does the spectral heuristic's output feed into a placement that could
differ downstream?

Output: JSON to --out.
"""

import argparse
import json
import sys
from typing import Any

import networkx as nx
import numpy as np


def _house_edges() -> list[tuple[int, int]]:
    return [(0,1),(1,2),(2,3),(3,0),(0,2),(3,4),(4,5),(5,6),(6,7),(7,4),(5,7)]


def _star_ring_edges() -> list[tuple[int, int]]:
    return [(0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1),(1,5),(3,6)]


def _permute_graph(edges: list[tuple[int, int]], seed: int) -> nx.Graph:
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


def _pairwise_distances(pos: dict) -> np.ndarray:
    """Compute pairwise Euclidean distances between all nodes in pos."""
    keys = sorted(pos.keys())
    n = len(keys)
    coords = np.array([[pos[k][0], pos[k][1]] for k in keys])
    diffs = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
    return np.sqrt(np.sum(diffs ** 2, axis=2))


def _procrustes_disparity(A: np.ndarray, B: np.ndarray) -> float:
    """
    Compute the minimum RMSE between A and B after optimal
    orthogonal transformation (rotation + reflection). This is the
    Procrustes distance normalized by the scale of A.
    """
    # Center both
    A_centered = A - A.mean(axis=0)
    B_centered = B - B.mean(axis=0)
    # SVD of cross-covariance
    M = A_centered.T @ B_centered
    U, _s, Vt = np.linalg.svd(M)
    R = U @ Vt  # Optimal rotation/reflection
    B_aligned = B_centered @ R.T
    rmse = np.sqrt(np.mean((A_centered - B_aligned) ** 2))
    scale = np.sqrt(np.mean(A_centered ** 2))
    return float(rmse / scale) if scale > 0 else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="M5: Spectral layout tie census")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--seeds", type=int, default=64, help="Permutation seeds")
    args = parser.parse_args()

    results: dict[str, Any] = {
        "tool": "m5_spectral_tie_census",
        "python_version": sys.version,
        "networkx_version": nx.__version__,
    }

    for graph_name, edges_fn in [
        ("house_11edge", _house_edges),
        ("star_ring_10edge", _star_ring_edges),
    ]:
        edges = edges_fn()

        # Baseline: canonical insertion order
        G_base = nx.Graph()
        G_base.add_edges_from(edges)
        pos_base = nx.spectral_layout(G_base, weight="weight", dim=2)
        keys = sorted(pos_base.keys())
        base_coords = np.array([[pos_base[k][0], pos_base[k][1]] for k in keys])
        base_distances = _pairwise_distances(pos_base)

        # Collect all layouts
        all_layouts = []
        for seed in range(args.seeds):
            G = _permute_graph(edges, seed)
            pos = nx.spectral_layout(G, weight="weight", dim=2)
            coords = np.array([[pos[k][0], pos[k][1]] for k in keys])
            all_layouts.append(coords)

        # Compute Procrustes disparity to baseline for each
        disparities = []
        for coords in all_layouts:
            d = _procrustes_disparity(base_coords, coords)
            disparities.append(d)

        # Compute pairwise distance correlation with baseline
        dist_corrs = []
        for coords in all_layouts:
            dmat = _pairwise_distances(
                {k: (coords[i, 0], coords[i, 1]) for i, k in enumerate(keys)}
            )
            # Flatten upper triangle
            triu_idx = np.triu_indices(len(keys), k=1)
            base_flat = base_distances[triu_idx]
            dmat_flat = dmat[triu_idx]
            # Pearson correlation
            corr = np.corrcoef(base_flat, dmat_flat)[0, 1]
            dist_corrs.append(float(corr))

        # Count distinct canonical coordinate sets
        coord_sets = set()
        for coords in all_layouts:
            rounded = tuple(
                (round(float(coords[i, 0]), 6), round(float(coords[i, 1]), 6))
                for i in range(coords.shape[0])
            )
            coord_sets.add(rounded)

        key = f"tie_census_{graph_name}"
        results[key] = {
            "nodes": len(keys),
            "edges": len(edges),
            "seeds": args.seeds,
            "distinct_coordinate_sets": len(coord_sets),
            "procrustes_disparity": {
                "min": float(np.min(disparities)),
                "max": float(np.max(disparities)),
                "mean": float(np.mean(disparities)),
                "median": float(np.median(disparities)),
                "all_zero": bool(np.allclose(disparities, 0, atol=1e-12)),
            },
            "distance_correlation": {
                "min": float(np.min(dist_corrs)),
                "max": float(np.max(dist_corrs)),
                "mean": float(np.mean(dist_corrs)),
                "all_one": bool(np.allclose(dist_corrs, 1.0, atol=1e-12)),
            },
            "interpretation": (
                "IDENTICAL_UP_TO_ORTHOGONAL"
                if np.allclose(disparities, 0, atol=1e-12) and np.allclose(dist_corrs, 1.0, atol=1e-12)
                else "MATERIALLY_DIFFERENT"
            ),
        }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
