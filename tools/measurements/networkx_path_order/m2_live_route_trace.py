#!/usr/bin/env python3
"""M2 -- dynamic reachability of the ``nx.shortest_path`` branch in
``router_v6/channel_mapping.py`` on a real board route.

Spike S3.  Answers: does ``_extract_waypoints`` ever run its
``if not channel_sequence:`` branch (lines 327-348), which is the only
place ``nx.shortest_path`` is called (lines 339, 343)?

Instrumentation is pure observation -- no production module is edited.
Two independent probes are used so neither has to be trusted alone:

  1. ``coverage.py`` line coverage restricted to ``channel_mapping.py``.
     Reports exactly which lines executed.  Lines 339/343 executing is
     the ground truth for "the branch is live".
  2. Explicit wrappers around ``_extract_waypoints`` and
     ``_parse_channel_coordinate`` that count invocations and bucket
     them by which return branch was taken.  ``nx.shortest_path`` is
     also wrapped in the ``channel_mapping`` module namespace so a call
     cannot be missed even if coverage is misconfigured.

Usage::

    python3 m2_live_route_trace.py --pcb <path> --rules <path> \
        --out result.json [--max-nets N]

``--max-nets`` bounds Stage 3 (the SAT solve, ~95% of wall time) so the
run finishes in minutes instead of ~26 minutes.  Reachability of a
*statically dominated* branch does not depend on net count, so the
bounded run is sufficient; pass no bound to route the whole board.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", required=True, type=Path)
    ap.add_argument("--rules", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-nets", type=int, default=0)
    args = ap.parse_args()

    import coverage

    import temper_placer.router_v6.channel_mapping as cm

    cm_file = cm.__file__

    cov = coverage.Coverage(data_file=None, branch=False, include=[cm_file])
    cov.start()

    # --- probes -----------------------------------------------------
    counters: dict[str, int] = {
        "extract_waypoints_calls": 0,
        "extract_waypoints_empty_sequence": 0,
        "nx_shortest_path_calls": 0,
        "parse_channel_coordinate_calls": 0,
        "parse_coord_strategy3_hash_hits": 0,
    }
    seq_lengths: list[int] = []

    real_extract = cm._extract_waypoints
    real_parse = cm._parse_channel_coordinate
    real_sp = cm.nx.shortest_path

    def traced_extract(channel_sequence, skeleton):
        counters["extract_waypoints_calls"] += 1
        seq_lengths.append(len(channel_sequence))
        if not channel_sequence:
            counters["extract_waypoints_empty_sequence"] += 1
        return real_extract(channel_sequence, skeleton)

    def traced_parse(channel_id, skeleton):
        counters["parse_channel_coordinate_calls"] += 1
        n_nodes = skeleton.graph.number_of_nodes()
        out = real_parse(channel_id, skeleton)
        # Strategy 3 is the only path that can fire when the skeleton has
        # <= 20 nodes and returns a node drawn from the graph itself.
        if out is not None and 0 < n_nodes <= 20 and out in set(skeleton.graph.nodes()):
            counters["parse_coord_strategy3_hash_hits"] += 1
        return out

    def traced_sp(*a, **kw):
        counters["nx_shortest_path_calls"] += 1
        return real_sp(*a, **kw)

    cm._extract_waypoints = traced_extract
    cm._parse_channel_coordinate = traced_parse
    cm.nx.shortest_path = traced_sp

    # --- run the real router ----------------------------------------
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6.adapter import route_pcb

    netlist = parse_kicad_pcb(args.pcb).netlist
    design_rules = load_netclass_rules(args.rules).design_rules

    nets = list(netlist.nets)
    total_nets = len(nets)
    if args.max_nets:
        nets = nets[: args.max_nets]

    class ParsedStub:
        source_path = args.pcb
        nets: list = []

    ParsedStub.nets = nets

    error = None
    try:
        route_pcb(ParsedStub(), {}, design_rules=design_rules)
    except Exception as exc:  # noqa: BLE001 - reachability is the datum
        error = f"{type(exc).__name__}: {exc}"

    cov.stop()

    data = cov.get_data()
    executed = sorted(data.lines(cm_file) or [])

    result = {
        "pcb": str(args.pcb),
        "channel_mapping_file": cm_file,
        "nets_total_in_netlist": total_nets,
        "nets_submitted": len(nets),
        "route_error": error,
        "counters": counters,
        "channel_sequence_lengths": {
            "n": len(seq_lengths),
            "min": min(seq_lengths) if seq_lengths else None,
            "max": max(seq_lengths) if seq_lengths else None,
            "zero_count": sum(1 for x in seq_lengths if x == 0),
        },
        "nx_branch_lines_executed": {
            str(ln): (ln in executed) for ln in (327, 328, 330, 336, 339, 343, 345, 347)
        },
        "executed_lines": executed,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counters"], indent=2))
    print("nx branch lines executed:", result["nx_branch_lines_executed"])
    print("route_error:", error)
    return 0


if __name__ == "__main__":
    sys.exit(main())
