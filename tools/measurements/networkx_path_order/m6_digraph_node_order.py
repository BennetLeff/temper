#!/usr/bin/env python3
"""M6 -- the one networkx semantic ``channel_mapping`` actually depends on.

Spike S3.  With the ``nx.shortest_path`` branch shown dead (M1/M2), the
module's only remaining contact with networkx is at lines 273-283::

    if (not channel_sequence
            and net_topology.path_graph is not None
            and net_topology.path_graph.number_of_edges() > 0):
        nodes = list(net_topology.path_graph.nodes())
        channel_sequence = [str(node) for node in nodes]

``path_graph`` is a ``nx.DiGraph`` built in ``_pipeline_route.py:371-374``
by ``pg.add_edges_from(path_edges)`` from the Rust SAT solver's output.
So the question a Rust port must answer is not "which shortest path" but
the far narrower "what order does ``DiGraph.nodes()`` yield?".

This checks the hypothesis that the answer is simply **first-seen order
over the edge list** -- i.e. a deterministic, trivially portable rule with
no algorithmic tie-breaking in it, unlike ``shortest_path``.

Usage::

    python3 m6_digraph_node_order.py --out result.json [--trials 200]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def first_seen(edges):
    seen: list = []
    for u, v in edges:
        for n in (u, v):
            if n not in seen:
                seen.append(n)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--trials", type=int, default=200)
    args = ap.parse_args()

    import networkx as nx

    base = [("c", "a"), ("a", "b"), ("b", "d"), ("d", "c"), ("e", "a"), ("f", "b")]
    mismatches = []
    for seed in range(args.trials):
        edges = list(base)
        random.Random(seed).shuffle(edges)
        g = nx.DiGraph()
        g.add_edges_from(edges)
        if list(g.nodes()) != first_seen(edges):
            mismatches.append({"seed": seed, "nx": list(g.nodes()), "expected": first_seen(edges)})

    report = {
        "networkx": nx.__version__,
        "trials": args.trials,
        "digraph_nodes_equals_first_seen_insertion_order": not mismatches,
        "mismatches": mismatches[:3],
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
