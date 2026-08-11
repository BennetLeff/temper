#!/usr/bin/env python3
"""M2 — permutation experiment: is cycle_basis order-observable?

Builds synthetic trace-like graphs that form cycles, permutes edge/node
insertion order, and measures whether cycle_basis + "longest in basis"
produces different results.

Answers F1: does permuting node/edge insertion order change the
cycle_basis output, the "longest cycle", its vertex order, or the
computed shoelace area?

Usage:
    PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
        .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m2_permutation.py \
        --out m2.json --seeds 64
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

import networkx as nx
import numpy as np


@dataclass
class _FakeTrace:
    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None = None


def _build_trace_graph(traces: Sequence[_FakeTrace]) -> nx.Graph:
    """Identical to loop_area._build_trace_graph."""
    G: nx.Graph = nx.Graph()
    for t in traces:
        u = (round(t.start[0], 3), round(t.start[1], 3))
        v = (round(t.end[0], 3), round(t.end[1], 3))
        if u == v:
            continue
        length = math.hypot(v[0] - u[0], v[1] - u[1])
        G.add_edge(u, v, weight=length)
    return G


def _find_main_cycle(graph: nx.Graph) -> list | None:
    """Identical to loop_area._find_main_cycle."""
    cycles = list(nx.cycle_basis(graph))
    if not cycles:
        return None
    longest = max(cycles, key=len)
    if len(longest) < 3:
        return None
    return _order_cycle_vertices(graph, longest)


def _order_cycle_vertices(graph: nx.Graph, cycle_vertices: list) -> list:
    """Identical to loop_area._order_cycle_vertices."""
    if len(cycle_vertices) < 3:
        return list(cycle_vertices)
    cycle_set = set(cycle_vertices)
    start = cycle_vertices[0]
    ordered = [start]
    visited = {start}
    current = start
    while len(visited) < len(cycle_set):
        next_v = None
        for n in graph.neighbors(current):
            n_tuple = (float(n[0]), float(n[1]))
            if n_tuple in cycle_set and n_tuple not in visited:
                next_v = n_tuple
                break
        if next_v is None:
            break
        ordered.append(next_v)
        visited.add(next_v)
        current = next_v
    return ordered


def _shoelace_area(vertices: np.ndarray) -> float:
    """Identical to loop_area._shoelace_area."""
    x = vertices[:, 0]
    y = vertices[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def _compute_area(graph: nx.Graph) -> float | None:
    """Minimal version of _compute_area_from_traces."""
    if graph.number_of_nodes() == 0:
        return None

    largest_cc = max(nx.connected_components(graph), key=len)
    subgraph = graph.subgraph(largest_cc).copy()

    cycle = _find_main_cycle(subgraph)
    if cycle is not None and len(cycle) >= 3:
        return _shoelace_area(np.array(cycle, dtype=np.float64))
    return None


# ---------------------------------------------------------------------------
# Experiment graphs
# ---------------------------------------------------------------------------


def _make_grid_traces(
    n: int,
    spacing: float = 10.0,
) -> list[_FakeTrace]:
    """Build a n×n grid graph as traces (each edge = one trace).

    The grid forms many cycles; cycle_basis will pick a fundamental set.
    """
    traces: list[_FakeTrace] = []
    for i in range(n):
        for j in range(n):
            x0, y0 = float(i * spacing), float(j * spacing)
            if i + 1 < n:
                x1, y1 = float((i + 1) * spacing), float(j * spacing)
                traces.append(_FakeTrace((x0, y0), (x1, y1), net="DC+"))
            if j + 1 < n:
                x1, y1 = float(i * spacing), float((j + 1) * spacing)
                traces.append(_FakeTrace((x0, y0), (x1, y1), net="DC+"))
    return traces


def _make_house_traces() -> list[_FakeTrace]:
    """A small graph shaped like a house: square base + triangular roof.

    Multiple cycles share edges; the "longest in basis" depends on
    which spanning tree is chosen.
    """
    # Base square: (0,0)-(10,0)-(10,10)-(0,10)-(0,0)
    # Roof: (0,10)-(5,15)-(10,10)
    traces = [
        _FakeTrace((0.0, 0.0), (10.0, 0.0), net="DC+"),
        _FakeTrace((10.0, 0.0), (10.0, 10.0), net="DC+"),
        _FakeTrace((10.0, 10.0), (0.0, 10.0), net="DC+"),
        _FakeTrace((0.0, 10.0), (0.0, 0.0), net="DC+"),
        # Diagonal from (0,0) to (10,10) — creates multiple cycles
        _FakeTrace((0.0, 0.0), (10.0, 10.0), net="DC+"),
        # Roof
        _FakeTrace((0.0, 10.0), (5.0, 15.0), net="DC+"),
        _FakeTrace((5.0, 15.0), (10.0, 10.0), net="DC+"),
    ]
    return traces


def _make_multi_cycle_traces() -> list[_FakeTrace]:
    """Graph with a 4-cycle and a 5-cycle sharing edges.

    The cycle_basis will only contain fundamental cycles — the 5-cycle
    may or may not be in the basis depending on spanning-tree tie-breaking.
    """
    # Outer pentagon: (0,0)-(10,0)-(12,8)-(5,12)-(-2,8)-(0,0)
    # Inner triangle shares edges with pentagon
    traces = [
        _FakeTrace((0.0, 0.0), (10.0, 0.0), net="DC+"),
        _FakeTrace((10.0, 0.0), (12.0, 8.0), net="DC+"),
        _FakeTrace((12.0, 8.0), (5.0, 12.0), net="DC+"),
        _FakeTrace((5.0, 12.0), (-2.0, 8.0), net="DC+"),
        _FakeTrace((-2.0, 8.0), (0.0, 0.0), net="DC+"),
        # Diagonal: (0,0)-(12,8) — creates multiple fundamental cycles
        _FakeTrace((0.0, 0.0), (12.0, 8.0), net="DC+"),
        # Another diagonal: (10,0)-(5,12)
        _FakeTrace((10.0, 0.0), (5.0, 12.0), net="DC+"),
    ]
    return traces


def _make_non_planar_traces() -> list[_FakeTrace]:
    """K5-like graph: 5 nodes fully connected, many cycles."""
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (5.0, 15.0)]
    traces: list[_FakeTrace] = []
    # All 10 edges of K5
    for i in range(5):
        for j in range(i + 1, 5):
            traces.append(_FakeTrace(pts[i], pts[j], net="DC+"))
    return traces


# ---------------------------------------------------------------------------
# Permutation experiment
# ---------------------------------------------------------------------------


def _permute_traces(traces: list[_FakeTrace], seed: int) -> list[_FakeTrace]:
    """Return traces in a different insertion order.

    This is the key manipulation: same node set, same edge set, same
    weights — different graph-construction order.  We randomize the
    order of traces (edges) and, where coordinates collide, the order
    of first-seen nodes.
    """
    rng = random.Random(seed)
    perm = traces.copy()
    rng.shuffle(perm)
    return perm


def _canonical_cycle(cycle: list) -> tuple:
    """Canonicalize a cycle for comparison.

    Rotate to start at minimum node, then optionally reverse.
    """
    if not cycle:
        return tuple()
    min_idx = min(range(len(cycle)), key=lambda i: cycle[i])
    rotated = tuple(cycle[min_idx:] + cycle[:min_idx])
    # Also try reversed
    rev = tuple(reversed(rotated))
    rev_min = min(range(len(rev)), key=lambda i: rev[i])
    rev_rot = tuple(rev[rev_min:] + rev[:rev_min])
    return min(rotated, rev_rot)


def run_experiment(
    name: str,
    base_traces: list[_FakeTrace],
    seeds: int = 64,
) -> dict:
    """Run permutation experiment on a trace set."""
    rng = random.Random(0)

    # Baseline: original insertion order
    G_base = _build_trace_graph(base_traces)
    base_cycle = _find_main_cycle(G_base)
    base_area = _compute_area(G_base)
    base_canon = _canonical_cycle(base_cycle) if base_cycle else None

    # Count distinct results
    areas: set[float | None] = {base_area}
    canons: set[tuple] = set()
    if base_canon:
        canons.add(base_canon)

    diff_seeds: list[int] = []
    same_seeds: int = 1  # baseline is "same"

    for seed in range(1, seeds + 1):
        perm_traces = _permute_traces(base_traces, seed)
        G = _build_trace_graph(perm_traces)
        cycle = _find_main_cycle(G)
        area = _compute_area(G)
        canon = _canonical_cycle(cycle) if cycle else None

        areas.add(area)
        if canon:
            canons.add(canon)

        if area != base_area or canon != base_canon:
            diff_seeds.append(seed)
        else:
            same_seeds += 1

    return {
        "name": name,
        "graph_nodes": G_base.number_of_nodes(),
        "graph_edges": G_base.number_of_edges(),
        "seeds": seeds,
        "baseline_area": base_area,
        "baseline_cycle_len": len(base_cycle) if base_cycle else 0,
        "distinct_areas": len(areas),
        "distinct_canonical_cycles": len(canons),
        "divergent_seeds": len(diff_seeds),
        "same_seeds": same_seeds,
        "all_same": len(diff_seeds) == 0,
        "example_differences": diff_seeds[:5] if diff_seeds else [],
    }


def run_all(seeds: int = 64) -> dict:
    return {
        "experiments": [
            run_experiment("house", _make_house_traces(), seeds),
            run_experiment("multi_cycle", _make_multi_cycle_traces(), seeds),
            run_experiment("non_planar", _make_non_planar_traces(), seeds),
            run_experiment("grid_4x4", _make_grid_traces(4), seeds),
            run_experiment("grid_5x5", _make_grid_traces(5), seeds),
        ],
        "seeds": seeds,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="M2 — cycle_basis permutation experiment")
    ap.add_argument("--out", default=None, help="Write JSON output")
    ap.add_argument("--seeds", type=int, default=64, help="Number of permutation seeds")
    args = ap.parse_args()

    results = run_all(seeds=args.seeds)
    print(json.dumps(results, indent=2, default=str))

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2, default=str)

    # Summarize
    all_same = all(e["all_same"] for e in results["experiments"])
    any_divergent = any(e["divergent_seeds"] > 0 for e in results["experiments"])
    print(f"\nF1 VERDICT: cycle_basis output is {'ORDER-INSENSITIVE' if all_same else 'ORDER-OBSERVABLE'}")
    if any_divergent:
        for e in results["experiments"]:
            if not e["all_same"]:
                print(f"  {e['name']}: {e['divergent_seeds']}/{e['seeds']} seeds divergent, "
                      f"{e['distinct_areas']} distinct area values, "
                      f"{e['distinct_canonical_cycles']} distinct cycles")


if __name__ == "__main__":
    main()
