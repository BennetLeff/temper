#!/usr/bin/env python3
"""M4 -- latent, *live* determinism hazards in ``channel_mapping.py`` that
have nothing to do with networkx.

Spike S3 asked (question 4) whether networkx's own answer is stable, and
noted that a determinism issue in the *current Python* would be a finding
in its own right (cf. PR #730, "make component placement independent of
PYTHONHASHSEED").  M3 answers that for the dead nx branch.  This script
covers the two order-dependent constructs that are **not** dead:

  H1. ``_parse_channel_coordinate`` Strategy 3, line 457::

          idx = hash(channel_id) % len(nodes)
          return nodes[idx]

      ``hash()`` of a ``str`` is salted per interpreter process by
      ``PYTHONHASHSEED``.  The waypoint returned for a given channel ID is
      therefore a different physical ``(x, y)`` on different runs of the
      same input.  Guarded by ``number_of_nodes() <= 20``.

  H2. ``_extract_waypoints`` line 385::

          return nodes[: min(len(channel_sequence) + 1, len(nodes))]

      ``list(graph.nodes())`` is networkx insertion order, so this returns
      whichever nodes happened to be inserted first.  Not salted, but not
      a property of the geometry either -- it is a property of the order
      ``channel_skeleton`` walked the Voronoi output.

Both are measured, and each is reported with its reachability gate so a
reviewer can see exactly when it can fire.

Usage::

    python3 m4_latent_determinism.py --out result.json [--trials 12]

Each trial re-executes the hash probe in a *fresh interpreter* (hash
randomisation is fixed for a process's lifetime, so in-process sampling
would measure nothing).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

# Probe run in a fresh interpreter: build a small skeleton (<= 20 nodes,
# so Strategy 3's gate is open), feed it a channel ID that defeats
# Strategies 1 and 2, and report which node came back.
HASH_PROBE = textwrap.dedent(
    """
    import json, sys
    import networkx as nx
    from temper_placer.router_v6.channel_mapping import _parse_channel_coordinate
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

    g = nx.Graph()
    pts = [(float(i), float(i * 2)) for i in range(8)]
    for a, b in zip(pts, pts[1:]):
        g.add_node(a, pos=a); g.add_node(b, pos=b); g.add_edge(a, b, weight=1.0)
    sk = ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=8.0)

    # IDs with no '_' and no ',' -> Strategies 1 and 2 both fail,
    # Strategy 3 (the hash) is the only path that can answer.
    ids = ["chanA", "chanB", "chanC", "chanD", "chanE"]
    out = {i: _parse_channel_coordinate(i, sk) for i in ids}
    print(json.dumps({"nodes": g.number_of_nodes(),
                      "hash_seed": sys.flags.hash_randomization,
                      "result": {k: list(v) if v else None for k, v in out.items()}}))
    """
)

INSERTION_PROBE = textwrap.dedent(
    """
    import json, random
    import networkx as nx
    from temper_placer.router_v6.channel_mapping import _extract_waypoints
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

    pts = [(float(i), float(i * 2)) for i in range(40)]
    edges = list(zip(pts, pts[1:]))

    def build(seed):
        rng = random.Random(seed)
        ns = list(pts); es = list(edges)
        rng.shuffle(ns); rng.shuffle(es)
        g = nx.Graph()
        for n in ns:
            g.add_node(n, pos=n)
        for a, b in es:
            g.add_edge(a, b, weight=1.0)
        return ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=40.0)

    # Channel IDs that parse to nothing -> forces the line-385 fallback.
    seq = ["nonparsing-a", "nonparsing-b", "nonparsing-c"]
    outs = []
    for seed in range(16):
        sk = build(seed)
        outs.append([list(p) for p in _extract_waypoints(seq, sk)])
    distinct = {json.dumps(o) for o in outs}
    print(json.dumps({"trials": len(outs), "distinct_results": len(distinct),
                      "example_a": outs[0], "example_b": outs[1]}))
    """
)


def run_probe(python: str, code: str, env_extra: dict | None = None) -> dict:
    import os

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [python, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    line = ""
    for candidate in reversed(proc.stdout.strip().splitlines()):
        if candidate.startswith("{"):
            line = candidate
            break
    if not line:
        return {"error": proc.stderr.strip()[-2000:]}
    return json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--trials", type=int, default=12)
    args = ap.parse_args()

    report: dict = {}

    # --- H1: PYTHONHASHSEED sensitivity, fresh process per trial ----
    randomised = [run_probe(args.python, HASH_PROBE) for _ in range(args.trials)]
    results = [json.dumps(r.get("result")) for r in randomised if "result" in r]
    fixed = [
        run_probe(args.python, HASH_PROBE, {"PYTHONHASHSEED": "0"})
        for _ in range(min(3, args.trials))
    ]
    fixed_results = [json.dumps(r.get("result")) for r in fixed if "result" in r]

    report["H1_hash_strategy3"] = {
        "line": 457,
        "reachability_gate": "skeleton.graph.number_of_nodes() <= 20",
        "trials": len(results),
        "distinct_results_default_env": len(set(results)),
        "hash_randomisation_active": bool(randomised and randomised[0].get("hash_seed")),
        "distinct_results_PYTHONHASHSEED_0": len(set(fixed_results)),
        "sample_results": sorted(set(results))[:3],
        "errors": [r["error"] for r in randomised if "error" in r][:1],
    }

    # --- H2: graph insertion order sensitivity ----------------------
    report["H2_insertion_order_fallback"] = {
        "line": 385,
        "reachability_gate": (
            "channel_sequence non-empty AND no channel ID parses to a coordinate"
        ),
        **run_probe(args.python, INSERTION_PROBE),
    }

    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
