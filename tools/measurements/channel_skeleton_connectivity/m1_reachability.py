#!/usr/bin/env python3
"""
M1 — Reachability: is _ensure_skeleton_connectivity reached with n_components > 1
on the production board?

Measures:
  - Routing spaces per layer
  - Skeleton node/edge counts before bridging
  - Component counts and sizes
  - Whether the bridge branch is taken (n_components > 1)
  - How many bridge edges were added
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import networkx as nx

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.routing_space import compute_routing_space
from temper_placer.router_v6.channel_skeleton import (
    _ensure_skeleton_connectivity,
    _extract_medial_axis,
    ChannelSkeleton,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcb", required=True, help="Path to .kicad_pcb")
    parser.add_argument("--out", default="m1.json")
    args = parser.parse_args()

    board = parse_kicad_pcb_v6(Path(args.pcb))
    routing_spaces = compute_routing_space(board)

    results: dict = {
        "board": str(args.pcb),
        "n_components": board.n_components if hasattr(board, "n_components") else len(board.components),
        "n_nets": len(board.nets),
        "layers": {},
    }

    for layer_name, rs in routing_spaces.items():
        layer_result: dict = {
            "routing_area_mm2": rs.routing_area,
            "available_ratio": rs.available_ratio,
        }

        # Build the skeleton graph the same way as extract_channel_skeleton,
        # but capture state BEFORE the bridge step.
        G = nx.Graph()
        available_area = rs.available_area

        if available_area.is_empty:
            layer_result["empty"] = True
            results["layers"][layer_name] = layer_result
            continue

        t0 = time.time()
        skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance=0.5)
        t1 = time.time()
        layer_result["medial_axis_time_s"] = t1 - t0
        layer_result["medial_axis_lines"] = len(skeleton_lines)

        total_length = 0.0
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
                total_length += length

        layer_result["nodes_before_bridge"] = G.number_of_nodes()
        layer_result["edges_before_bridge"] = G.number_of_edges()
        layer_result["total_length_mm"] = total_length

        # Component analysis before bridging
        components = list(nx.connected_components(G))
        n_comp = len(components)
        comp_sizes = sorted([len(c) for c in components], reverse=True)
        layer_result["n_components_before"] = n_comp
        layer_result["component_sizes"] = comp_sizes
        layer_result["bridge_branch_taken"] = n_comp > 1

        # Run the bridge step and measure
        t0 = time.time()
        G_bridged = _ensure_skeleton_connectivity(
            G, max_bridge_distance=10.0, available_area=available_area
        )
        t1 = time.time()
        layer_result["bridge_time_s"] = t1 - t0

        # Count how many bridge edges were added
        edges_after = set(G_bridged.edges())
        # The function modifies G in-place and returns it;
        # we need the original edge set
        # Let's redo more carefully
        layer_result["nodes_after_bridge"] = G_bridged.number_of_nodes()
        layer_result["edges_after_bridge"] = G_bridged.number_of_edges()

        # Components after bridging
        components_after = list(nx.connected_components(G_bridged))
        layer_result["n_components_after"] = len(components_after)
        layer_result["fully_connected"] = len(components_after) <= 1

        results["layers"][layer_name] = layer_result

    # Now do a more careful bridge-edge count.
    # Rebuild the graph fresh and capture edges before vs after.
    print("=== Rebuilding with careful bridge-edge counting ===")
    for layer_name, rs in routing_spaces.items():
        if rs.available_area.is_empty:
            continue

        G_pre = nx.Graph()
        available_area = rs.available_area
        skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance=0.5)

        for line in skeleton_lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                G_pre.add_node(p1, pos=p1)
                G_pre.add_node(p2, pos=p2)
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = (dx**2 + dy**2) ** 0.5
                G_pre.add_edge(p1, p2, weight=length)

        edges_before = set(G_pre.edges())
        G_post = _ensure_skeleton_connectivity(
            G_pre, max_bridge_distance=10.0, available_area=available_area
        )
        edges_after = set(G_post.edges())

        bridge_edges = edges_after - edges_before
        results["layers"][layer_name]["bridge_edges_added"] = len(bridge_edges)
        results["layers"][layer_name]["bridge_edges"] = [
            {"a": list(e[0]), "b": list(e[1]), "weight": G_post[e[0]][e[1]]["weight"]}
            for e in sorted(bridge_edges)
        ]
        print(f"  {layer_name}: {len(bridge_edges)} bridge edges added")

    json.dump(results, open(args.out, "w"), indent=2, default=str)
    print(f"\nResults written to {args.out}")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
