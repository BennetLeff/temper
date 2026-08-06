#!/usr/bin/env python3
"""M3 -- counterfactual: *if* the ``nx.shortest_path`` branch in
``router_v6/channel_mapping._extract_waypoints`` were reachable, would the
path it returns be observable-order-dependent?

Spike S3.  M1 shows the branch is statically dead and M2 shows it never
executes.  This script answers the separate question a reviewer will
still ask: "is the blocker real in substance, or only asserted?"  If the
returned path flips under a pure re-ordering of graph construction, then
the blocker *would* be real and the UNBLOCKED verdict rests entirely on
unreachability -- which is a materially different (and more fragile)
claim than "order does not matter here".  That distinction is the point
of this measurement.

What is measured, on **real channel skeletons built from the production
board** by the production ``extract_channel_skeleton``:

  A. Tie census.  For the exact endpoint pairs the dead branch would
     query -- ``(endpoints[0], endpoints[1])`` where ``endpoints`` are the
     degree-1 nodes, else ``(nodes[0], nodes[-1])`` -- count how many
     distinct minimum-length paths exist.  Note the call site passes no
     ``weight=``, so ``nx.shortest_path`` runs **unweighted BFS**
     (``bidirectional_shortest_path``), and "length" means hop count, not
     millimetres.
  B. Permutation experiment.  Rebuild the *same* graph (identical node
     set, identical edge set, identical weights) with node/edge insertion
     order permuted under N seeds, re-run the exact call the dead branch
     makes, and record whether the returned node sequence changes.
  C. Waypoint consequence.  The dead branch ``return path`` returns the
     node list *as the waypoints*.  Skeleton nodes are ``(x, y)`` tuples,
     so a different path is literally a different waypoint polyline.
     Report the resulting geometric divergence.

Nothing here is a Rust comparison: the perturbation is entirely inside
Python, which is sufficient -- if networkx's own answer is unstable under
a semantically-irrelevant re-ordering, no Rust port could be bit-exact
against it by construction.

Pad geometry shim
-----------------
The ``temper_geometry`` extension available in this environment predates
the ``pad_*_py`` symbols ``core/pad_geometry.py`` now calls, and this is a
spike that must not build Rust.  ``pad_corner_radius`` is therefore forced
to ``0.0`` (and ``pad_core_half_extents`` to the matching
``(width/2, height/2)``).  This is not an invented behaviour: it is the
``r <= 0.0`` branch of the production ``pad_polygon``, which the module's
own docstring documents as the safe bounding-rectangle fallback taken for
unrecognised pad shapes.  It makes pads slightly *larger* (sharp corners
instead of rounded), which perturbs obstacle outlines by well under a pad
corner radius.  It cannot manufacture the effect under test: graph
construction order is independent of pad corner rounding.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path


def _install_pad_shim() -> None:
    """Force the documented r=0 bounding-rectangle pad branch."""
    from temper_placer.core import pad_geometry as pg

    pg.pad_corner_radius = lambda w, h, shape, ratio=pg.DEFAULT_ROUNDRECT_RATIO: 0.0
    pg.pad_core_half_extents = lambda w, h, shape, ratio=pg.DEFAULT_ROUNDRECT_RATIO: (
        w / 2.0,
        h / 2.0,
    )


def build_real_skeletons(pcb_path: Path):
    """Return {layer_name: ChannelSkeleton} from the production board."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
    from temper_placer.router_v6.routing_space import compute_routing_space

    pcb = parse_kicad_pcb_v6(pcb_path)
    spaces = compute_routing_space(pcb)
    return {name: extract_channel_skeleton(sp, pcb=pcb) for name, sp in spaces.items()}


def endpoints_the_dead_branch_would_use(graph):
    """Reproduce lines 330-343 of channel_mapping._extract_waypoints exactly."""
    nodes = list(graph.nodes())
    if len(nodes) < 2:
        return None
    endpoints = [n for n in nodes if graph.degree(n) == 1]
    if len(endpoints) >= 2:
        return endpoints[0], endpoints[1], "degree1_endpoints"
    return nodes[0], nodes[-1], "first_last_nodes"


def rebuild_permuted(graph, seed: int):
    """Same nodes, same edges, same weights -- different insertion order."""
    import networkx as nx

    rng = random.Random(seed)
    nodes = list(graph.nodes(data=True))
    edges = list(graph.edges(data=True))
    rng.shuffle(nodes)
    rng.shuffle(edges)
    g2 = nx.Graph()
    for n, attrs in nodes:
        g2.add_node(n, **attrs)
    for u, v, attrs in edges:
        g2.add_edge(u, v, **attrs)
    return g2


def count_tied_shortest_paths(graph, src, dst, cap: int = 10000):
    """Number of distinct minimum-hop paths, capped."""
    import networkx as nx

    try:
        gen = nx.all_shortest_paths(graph, src, dst)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return 0, False
    n = 0
    for _ in gen:
        n += 1
        if n >= cap:
            return n, True
    return n, False


def polyline_divergence(p1, p2) -> dict:
    """Geometric difference between two waypoint polylines."""
    if p1 == p2:
        return {"identical": True}
    set1, set2 = set(p1), set(p2)
    only1 = set1 - set2
    only2 = set2 - set1
    return {
        "identical": False,
        "len_a": len(p1),
        "len_b": len(p2),
        "nodes_only_in_a": len(only1),
        "nodes_only_in_b": len(only2),
        "first_divergence_index": next(
            (i for i, (a, b) in enumerate(itertools.zip_longest(p1, p2)) if a != b),
            None,
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seeds", type=int, default=32)
    args = ap.parse_args()

    import networkx as nx

    _install_pad_shim()
    skeletons = build_real_skeletons(args.pcb)

    report: dict = {"pcb": str(args.pcb), "networkx": nx.__version__, "layers": {}}

    for layer, sk in skeletons.items():
        g = sk.graph
        entry: dict = {
            "nodes": g.number_of_nodes(),
            "edges": g.number_of_edges(),
            "connected": bool(sk.is_connected),
            "degree1_nodes": sum(1 for n in g.nodes() if g.degree(n) == 1),
        }
        chosen = endpoints_the_dead_branch_would_use(g)
        if chosen is None:
            entry["queryable"] = False
            report["layers"][layer] = entry
            continue
        src, dst, which = chosen
        entry["queryable"] = True
        entry["endpoint_rule"] = which

        # --- A. tie census -----------------------------------------
        n_tied, capped = count_tied_shortest_paths(g, src, dst)
        entry["tied_shortest_paths"] = n_tied
        entry["tie_count_capped"] = capped
        entry["ties_exist"] = n_tied > 1

        # --- B. permutation experiment -----------------------------
        baseline = nx.shortest_path(g, src, dst)
        entry["baseline_path_len"] = len(baseline)
        distinct: set[tuple] = {tuple(baseline)}
        flips = 0
        example = None
        for seed in range(args.seeds):
            g2 = rebuild_permuted(g, seed)
            # endpoint selection itself is order-dependent: re-derive it
            # exactly as the dead branch would on the permuted graph
            chosen2 = endpoints_the_dead_branch_would_use(g2)
            src2, dst2, which2 = chosen2
            entry.setdefault("endpoint_rule_flips", 0)
            if (src2, dst2) != (src, dst):
                entry["endpoint_rule_flips"] += 1
            # Hold the query fixed so the measurement isolates path
            # selection, not endpoint selection (both are reported).
            p = nx.shortest_path(g2, src, dst)
            distinct.add(tuple(p))
            if list(p) != list(baseline):
                flips += 1
                if example is None:
                    example = polyline_divergence(list(baseline), list(p))
        entry["permutation_seeds"] = args.seeds
        entry["permutation_path_flips"] = flips
        entry["distinct_paths_observed"] = len(distinct)
        entry["example_divergence"] = example

        report["layers"][layer] = entry

    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
