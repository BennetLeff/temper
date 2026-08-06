#!/usr/bin/env python3
"""M5 -- which branch of ``_extract_waypoints`` does the *production*
channel-ID format actually drive?

Spike S3.  M1/M2 establish that the ``nx.shortest_path`` branch is dead.
M4 finds two order-dependent constructs that are *not* dead in principle
(the ``hash()`` pick at line 457 and the insertion-order slice at line
385).  This script closes the remaining gap: are those two reachable on
the production board, or are they dead in practice too?

The production channel IDs are built by ``constraint_model.py`` as::

    edge_id = f"{layer_name}_E{i}_{n1}_{n2}"

where ``n1``/``n2`` are channel-skeleton nodes -- ``(x, y)`` float tuples.
Their ``str()`` renders as ``(1.5, 2.5)``, so a real ID looks like::

    In1.Cu_E5_(1.5, 2.5)_(3.25, 4.5)

``_extract_waypoints`` matches that with ``re.findall(r"\\(([^)]+)\\)")``
at line 356, finds two coordinate groups, and takes the edge-coordinate
branch (lines 357-371) -- which ``continue``s, so
``_parse_channel_coordinate`` is never called, and ``waypoints`` is
non-empty, so the line-385 fallback is never reached either.

This script builds real edge IDs from the real board's skeleton, runs the
real ``_extract_waypoints``, and reports line coverage so the claim is
observed rather than argued.

Usage::

    python3 m5_production_branch_census.py --pcb <path> --out result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_m3_helpers():
    """Import M3's skeleton builder without perturbing module-level imports."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from m3_tie_and_permutation import _install_pad_shim, build_real_skeletons

    return _install_pad_shim, build_real_skeletons


# Lines of interest in channel_mapping.py (see the module for context).
LINES = {
    "nx_branch_entry": 327,
    "nx_shortest_path_a": 339,
    "nx_shortest_path_b": 343,
    "edge_coord_regex": 356,
    "edge_coord_append": 366,
    "parse_channel_coordinate_call": 374,
    "waypoints_return": 380,
    "insertion_order_fallback": 385,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--edges", type=int, default=200)
    args = ap.parse_args()

    import coverage

    import temper_placer.router_v6.channel_mapping as cm

    install_pad_shim, build_real_skeletons = _load_m3_helpers()
    install_pad_shim()
    skeletons = build_real_skeletons(args.pcb)
    layer, sk = next(iter(skeletons.items()))

    # Reproduce constraint_model.py's edge_id format verbatim.
    edges = list(sk.graph.edges())[: args.edges]
    channel_sequence = [f"{layer}_E{i}_{n1}_{n2}" for i, (n1, n2) in enumerate(edges)]

    hit_parse = {"n": 0}
    real_parse = cm._parse_channel_coordinate

    def counting_parse(cid, skel):
        hit_parse["n"] += 1
        return real_parse(cid, skel)

    cm._parse_channel_coordinate = counting_parse

    cov = coverage.Coverage(data_file=None, include=[cm.__file__])
    cov.start()
    waypoints = cm._extract_waypoints(channel_sequence, sk)
    cov.stop()
    cm._parse_channel_coordinate = real_parse

    executed = set(cov.get_data().lines(cm.__file__) or [])

    report = {
        "layer": layer,
        "skeleton_nodes": sk.graph.number_of_nodes(),
        "skeleton_edges": sk.graph.number_of_edges(),
        "sample_channel_id": channel_sequence[0] if channel_sequence else None,
        "channel_sequence_len": len(channel_sequence),
        "waypoints_returned": len(waypoints),
        "parse_channel_coordinate_calls": hit_parse["n"],
        "lines_executed": {name: (ln in executed) for name, ln in LINES.items()},
        "H1_hash_gate_open": sk.graph.number_of_nodes() <= 20,
        "waypoints_head": [list(w) for w in waypoints[:4]],
    }
    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
