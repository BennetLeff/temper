#!/usr/bin/env python3
"""
M2 — Permutation experiment: does node/edge insertion order affect
the bridge edges added by _ensure_skeleton_connectivity?

Method (S3-style):
  1. Build the fragmented skeleton from the production board exactly as
     extract_channel_skeleton does (same Voronoi walk, same node/edge set).
  2. Save nodes, edges, and weights.
  3. For N random seeds:
     a. Build a NEW nx.Graph with the SAME node/edge set but permuted
        insertion order (shuffle the edge list before insertion).
     b. Run _ensure_skeleton_connectivity on the permuted graph.
     c. Compare the bridge edge set to the baseline.
  4. Report: how many seeds produce a DIFFERENT bridge edge set.

If ANY seed produces a different bridge edge set, the verdict is
ORDER-OBSERVABLE (the port needs petgraph parity).
If ALL seeds produce identically the SAME bridge edge set → ORDER-INSENSITIVE.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np


def build_fragmented_graph(available_area) -> tuple[nx.Graph, set, list, list]:
    """Build the fragmented skeleton graph (before bridge step).

    Deferred temper_placer import (S3 pattern): keeps tools/measurements off
    the import-linter phase-3 boundary (tools -> temper_placer is not a
    permitted static edge).
    """
    from temper_placer.router_v6.channel_skeleton import _extract_medial_axis

    G = nx.Graph()
    skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance=0.5)

    all_edges = []  # (p1, p2, weight)
    for line in skeleton_lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = (dx**2 + dy**2) ** 0.5
            G.add_edge(p1, p2, weight=length)
            all_edges.append((p1, p2, length))

    edges_frozen = frozenset(G.edges())
    nodes_frozen = frozenset(G.nodes())
    return G, edges_frozen, nodes_frozen, all_edges


def rebuild_graph_permuted(
    edge_data: list,  # list of (p1, p2, weight)
    seed: int,
    nodes_frozen: frozenset,
) -> nx.Graph:
    """Rebuild the same graph with permuted edge insertion order.
    Nodes are inserted in the order they appear in the permuted edge list,
    mimicking the Voronoi walk order being permuted.
    """
    rng = random.Random(seed)
    permuted = list(edge_data)
    rng.shuffle(permuted)

    G = nx.Graph()
    for p1, p2, weight in permuted:
        G.add_node(p1, pos=p1)
        G.add_node(p2, pos=p2)
        G.add_edge(p1, p2, weight=weight)

    # Verify node/edge sets are identical
    assert frozenset(G.nodes()) == nodes_frozen, f"Node set mismatch at seed {seed}"
    return G


def bridge_edge_set(G: nx.Graph) -> frozenset:
    """Return the edge set as frozenset of ((x1,y1),(x2,y2)) tuples."""
    return frozenset(
        (tuple(e[0]), tuple(e[1])) if e[0] < e[1] else (tuple(e[1]), tuple(e[0]))
        for e in G.edges()
    )


def main():
    # Deferred imports (S3 pattern): keeps tools/measurements off the
    # import-linter phase-3 boundary.
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.routing_space import compute_routing_space
    from temper_placer.router_v6.channel_skeleton import _ensure_skeleton_connectivity

    parser = argparse.ArgumentParser()
    parser.add_argument("--pcb", required=True, help="Path to .kicad_pcb")
    parser.add_argument("--out", default="m2.json")
    parser.add_argument("--seeds", type=int, default=32, help="Number of permutation seeds")
    parser.add_argument("--layer", default=None, help="Layer name (default: first inner layer)")
    args = parser.parse_args()

    board = parse_kicad_pcb_v6(Path(args.pcb))
    routing_spaces = compute_routing_space(board)

    # Pick layer
    layer_names = list(routing_spaces.keys())
    if args.layer:
        if args.layer not in routing_spaces:
            print(f"Layer {args.layer} not found. Available: {layer_names}")
            sys.exit(1)
        layer_name = args.layer
    else:
        # First non-empty layer
        for name in layer_names:
            if not routing_spaces[name].available_area.is_empty:
                layer_name = name
                break
        else:
            print("No non-empty routing spaces found")
            sys.exit(1)

    rs = routing_spaces[layer_name]
    print(f"Using layer: {layer_name}")

    # Build baseline
    print("Building fragmented skeleton...")
    t0 = time.time()
    G_baseline, edges_frozen, nodes_frozen, edge_data = build_fragmented_graph(
        rs.available_area
    )
    t1 = time.time()
    print(f"  Built in {t1 - t0:.1f}s: {G_baseline.number_of_nodes()} nodes, "
          f"{G_baseline.number_of_edges()} edges")

    # Check component count
    n_comp = nx.number_connected_components(G_baseline)
    print(f"  Connected components: {n_comp}")
    if n_comp <= 1:
        print("  Already connected — bridge branch not reached. Permutation is moot.")
        json.dump(
            {
                "layer": layer_name,
                "n_nodes": G_baseline.number_of_nodes(),
                "n_edges": G_baseline.number_of_edges(),
                "n_components": n_comp,
                "verdict": "NOT_REACHED",
                "note": "Graph already connected; permutation experiment skipped",
            },
            open(args.out, "w"),
            indent=2,
        )
        return

    # Run baseline bridge step
    print("Running baseline bridge step...")
    t0 = time.time()
    G_baseline_post = _ensure_skeleton_connectivity(
        G_baseline, max_bridge_distance=10.0, available_area=rs.available_area
    )
    t1 = time.time()
    baseline_bridge_edges = bridge_edge_set(G_baseline_post) - edges_frozen
    print(f"  Baseline: {len(baseline_bridge_edges)} bridge edges added in {t1 - t0:.1f}s")

    # Edge data for permutation
    # We need the FULL edge data including weights
    if not edge_data:
        print("No edges — aborting")
        sys.exit(1)

    # Count ties in bridge candidates
    # We need to check if there are multiple candidate pairs with the same distance
    # that connect different components.
    print("\nRunning tie census...")
    candidates = _compute_bridge_candidates(G_baseline, rs.available_area)
    print(f"  Total candidates within 10mm: {len(candidates)}")
    dists = [c["distance"] for c in candidates]
    unique_dists = len(set(round(d, 9) for d in dists))  # round to 1e-9
    print(f"  Unique distances: {unique_dists} / {len(dists)}")
    
    # Count equidistant candidates
    from collections import Counter
    dist_counter = Counter(round(d, 9) for d in dists)
    ties = {d: count for d, count in dist_counter.items() if count > 1}
    print(f"  Tied distances (count > 1): {len(ties)}")
    max_tie = max(dist_counter.values()) if dist_counter else 0
    print(f"  Max candidates at same distance: {max_tie}")

    # Now run permutation experiment
    print(f"\nRunning permutation experiment with {args.seeds} seeds...")
    different_count = 0
    all_bridge_sets = []
    seed_results = []

    for seed in range(args.seeds):
        # Build permuted graph
        G_perm = rebuild_graph_permuted(edge_data, seed, nodes_frozen)

        # Run bridge step
        G_perm_post = _ensure_skeleton_connectivity(
            G_perm, max_bridge_distance=10.0, available_area=rs.available_area
        )

        perm_bridge_edges = bridge_edge_set(G_perm_post) - edges_frozen

        is_different = perm_bridge_edges != baseline_bridge_edges
        if is_different:
            different_count += 1
            # Show the difference
            only_in_baseline = baseline_bridge_edges - perm_bridge_edges
            only_in_perm = perm_bridge_edges - baseline_bridge_edges
            print(f"  Seed {seed}: DIFFERENT")
            if only_in_baseline:
                print(f"    Only in baseline: {[list(e) for e in only_in_baseline]}")
            if only_in_perm:
                print(f"    Only in permuted: {[list(e) for e in only_in_perm]}")
        else:
            print(f"  Seed {seed}: same")

        all_bridge_sets.append(perm_bridge_edges)
        seed_results.append(
            {
                "seed": seed,
                "different": is_different,
                "n_bridge_edges": len(perm_bridge_edges),
            }
        )

    unique_bridge_sets = len(set(all_bridge_sets))
    print(f"\nResults: {different_count}/{args.seeds} seeds produced different bridge edges")
    print(f"  Unique bridge edge sets: {unique_bridge_sets}")

    result = {
        "layer": layer_name,
        "n_nodes": G_baseline.number_of_nodes(),
        "n_edges_before": G_baseline.number_of_edges(),
        "n_components_before": n_comp,
        "baseline_bridge_edges": len(baseline_bridge_edges),
        "baseline_bridge_list": [
            [list(e[0]), list(e[1])] for e in sorted(baseline_bridge_edges)
        ],
        "candidates": {
            "total": len(candidates),
            "unique_distances": unique_dists,
            "tied_distances_count": len(ties),
            "max_tie": max_tie,
        },
        "permutation": {
            "seeds": args.seeds,
            "different_count": different_count,
            "unique_bridge_sets": unique_bridge_sets,
            "seeds": seed_results,
        },
        "verdict": (
            "ORDER_OBSERVABLE"
            if different_count > 0
            else "ORDER_INSENSITIVE"
        ),
    }

    json.dump(result, open(args.out, "w"), indent=2, default=str)
    print(f"\nResults written to {args.out}")
    print(f"VERDICT: {result['verdict']}")


def _compute_bridge_candidates(
    G: nx.Graph, available_area
) -> list[dict]:
    """Replicate the candidate computation from _ensure_skeleton_connectivity
    to count tied distances."""
    import numpy as np
    from temper_placer.router_v6.channel_skeleton import _radius_pairs

    if G.number_of_nodes() == 0:
        return []

    components = list(nx.connected_components(G))
    nodes = list(G.nodes())
    positions = np.asarray(nodes, dtype=float)
    node_index = {node: i for i, node in enumerate(nodes)}

    comp_id = np.empty(len(nodes), dtype=np.int64)
    for cid, comp in enumerate(components):
        for node in comp:
            comp_id[node_index[node]] = cid

    pairs = _radius_pairs(positions, 10.0)
    if len(pairs) == 0:
        return []

    ci_all = comp_id[pairs[:, 0]]
    cj_all = comp_id[pairs[:, 1]]
    cross_mask = ci_all != cj_all
    cross_pairs = pairs[cross_mask]

    if len(cross_pairs) == 0:
        return []

    cand_dist = np.linalg.norm(
        positions[cross_pairs[:, 0]] - positions[cross_pairs[:, 1]], axis=1
    )

    result = []
    for pos in range(len(cross_pairs)):
        i, j = int(cross_pairs[pos, 0]), int(cross_pairs[pos, 1])
        result.append(
            {
                "i": i,
                "j": j,
                "distance": float(cand_dist[pos]),
                "node_a": list(nodes[i]),
                "node_b": list(nodes[j]),
                "comp_a": int(comp_id[i]),
                "comp_b": int(comp_id[j]),
            }
        )
    return result


if __name__ == "__main__":
    main()
