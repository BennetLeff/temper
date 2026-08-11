#!/usr/bin/env python3
"""M3 — tie census: what is the distribution of cycle_basis outputs?

For each synthetic graph, enumerate all distinct "longest in basis" cycles
across insertion-order permutations, and measure the spread of computed
areas (relative to the true maximum-cycle area).

Usage:
    PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
        .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m3_tie_census.py \
        --out m3.json --seeds 256
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
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
    G: nx.Graph = nx.Graph()
    for t in traces:
        u = (round(t.start[0], 3), round(t.start[1], 3))
        v = (round(t.end[0], 3), round(t.end[1], 3))
        if u == v:
            continue
        G.add_edge(u, v, weight=math.hypot(v[0] - u[0], v[1] - u[1]))
    return G


def _find_main_cycle(graph: nx.Graph) -> list | None:
    cycles = list(nx.cycle_basis(graph))
    if not cycles:
        return None
    longest = max(cycles, key=len)
    if len(longest) < 3:
        return None
    return _order_cycle_vertices(graph, longest)


def _order_cycle_vertices(graph: nx.Graph, cycle_vertices: list) -> list:
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
    x = vertices[:, 0]
    y = vertices[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def _canonical_cycle(cycle: list) -> tuple:
    if not cycle:
        return tuple()
    min_idx = min(range(len(cycle)), key=lambda i: cycle[i])
    rotated = tuple(cycle[min_idx:] + cycle[:min_idx])
    rev = tuple(reversed(rotated))
    rev_min = min(range(len(rev)), key=lambda i: rev[i])
    rev_rot = tuple(rev[rev_min:] + rev[:rev_min])
    return min(rotated, rev_rot)


def _all_cycles_up_to_len(graph: nx.Graph, max_len: int = 8) -> list[list]:
    """Enumerate all simple cycles up to max_len vertices.
    This is not exhaustive but gives a sense of the cycle space.
    """
    import itertools

    result = []
    nodes = list(graph.nodes())
    for r in range(3, min(max_len + 1, len(nodes) + 1)):
        for combo in itertools.combinations(nodes, r):
            # check if these nodes form a simple cycle
            sub = graph.subgraph(combo)
            if sub.number_of_edges() == r:
                # Check if it's a single cycle (all degree 2)
                if all(d == 2 for _, d in sub.degree()):
                    result.append(list(combo))
    return result


def _make_grid_traces(n: int, spacing: float = 10.0) -> list[_FakeTrace]:
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
    traces = [
        _FakeTrace((0.0, 0.0), (10.0, 0.0), net="DC+"),
        _FakeTrace((10.0, 0.0), (10.0, 10.0), net="DC+"),
        _FakeTrace((10.0, 10.0), (0.0, 10.0), net="DC+"),
        _FakeTrace((0.0, 10.0), (0.0, 0.0), net="DC+"),
        _FakeTrace((0.0, 0.0), (10.0, 10.0), net="DC+"),
        _FakeTrace((0.0, 10.0), (5.0, 15.0), net="DC+"),
        _FakeTrace((5.0, 15.0), (10.0, 10.0), net="DC+"),
    ]
    return traces


def _make_non_planar_traces() -> list[_FakeTrace]:
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (5.0, 15.0)]
    traces: list[_FakeTrace] = []
    for i in range(5):
        for j in range(i + 1, 5):
            traces.append(_FakeTrace(pts[i], pts[j], net="DC+"))
    return traces


def run_census(
    name: str,
    base_traces: list[_FakeTrace],
    seeds: int = 256,
) -> dict:
    rng = random.Random(0)

    area_counter: Counter[float] = Counter()
    canon_counter: Counter[tuple] = Counter()
    cycle_len_counter: Counter[int] = Counter()
    # Also track raw cycle_basis (the list-of-lists before picking longest)
    basis_lengths: list[int] = []

    for seed in range(seeds):
        perm_traces = base_traces.copy()
        rng.shuffle(perm_traces)
        G = _build_trace_graph(perm_traces)

        # Record cycle_basis content
        cycles = list(nx.cycle_basis(G))
        basis_lengths.append(len(cycles))

        cycle = _find_main_cycle(G)
        if cycle is not None and len(cycle) >= 3:
            area = _shoelace_area(np.array(cycle, dtype=np.float64))
            area_counter[round(area, 6)] += 1
            canon = _canonical_cycle(cycle)
            canon_counter[canon] += 1
            cycle_len_counter[len(cycle)] += 1

    # Compute ideal longest cycle area (exhaustive for small graphs)
    G_base = _build_trace_graph(base_traces)
    true_max_area = None
    all_cycles = _all_cycles_up_to_len(G_base, max_len=8)
    if all_cycles:
        ordered_cycles = [_order_cycle_vertices(G_base, c) for c in all_cycles]
        ordered_cycles = [c for c in ordered_cycles if len(c) >= 3]
        areas = [_shoelace_area(np.array(c, dtype=np.float64)) for c in ordered_cycles]
        if areas:
            true_max_area = max(areas)

    area_values = sorted(area_counter.keys())
    area_spread = max(area_values) - min(area_values) if len(area_values) >= 2 else 0.0

    return {
        "name": name,
        "seeds": seeds,
        "graph_nodes": G_base.number_of_nodes(),
        "graph_edges": G_base.number_of_edges(),
        "distinct_areas": len(area_counter),
        "area_values": area_values,
        "area_spread": round(area_spread, 6),
        "distinct_canonical_cycles": len(canon_counter),
        "top_cycles": [
            {"cycle": str(k), "count": v}
            for k, v in canon_counter.most_common(5)
        ],
        "cycle_lengths": dict(cycle_len_counter.most_common()),
        "basis_sizes": {
            "min": min(basis_lengths) if basis_lengths else 0,
            "max": max(basis_lengths) if basis_lengths else 0,
            "unique": len(set(basis_lengths)),
            "distribution": dict(Counter(basis_lengths).most_common()),
        },
        "true_max_area_exhaustive": true_max_area,
        "baseline_area_underestimates_true": (
            None
            if true_max_area is None
            else round(area_values[0] < true_max_area, 6) if area_values else None
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="M3 — cycle_basis tie census")
    ap.add_argument("--out", default=None, help="Write JSON output")
    ap.add_argument("--seeds", type=int, default=256, help="Number of permutation seeds")
    args = ap.parse_args()

    experiments = [
        run_census("house", _make_house_traces(), args.seeds),
        run_census("non_planar", _make_non_planar_traces(), args.seeds),
        run_census("grid_3x3", _make_grid_traces(3), args.seeds),
    ]
    results = {"experiments": experiments, "seeds": args.seeds}

    print(json.dumps(results, indent=2, default=str))

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2, default=str)

    # Summary
    for e in experiments:
        avg_basis = sum(e["basis_sizes"]["distribution"].values())  # just for display
        print(
            f"\n{e['name']} ({e['graph_nodes']}n/{e['graph_edges']}e):"
            f"\n  distinct areas: {e['distinct_areas']} (spread {e['area_spread']} mm²)"
            f"\n  distinct cycles: {e['distinct_canonical_cycles']}"
            f"\n  cycle lengths: {e['cycle_lengths']}"
            f"\n  basis sizes: {e['basis_sizes']['distribution']}"
            f"\n  true max area (exhaustive): {e['true_max_area_exhaustive']}"
        )


if __name__ == "__main__":
    main()
