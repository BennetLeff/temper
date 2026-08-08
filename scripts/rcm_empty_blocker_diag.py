#!/usr/bin/env python3
"""Deep-dive diagnostic (throwaway, read-only instrumentation) for the 3
Stage-4 A* failures recorded with an EMPTY blocking_nets list:
discharge.r_snub1-p2, tank-out, w1_2.

Monkeypatches _astar_route_with_ripup (never touches production code) to
capture, for exactly those 3 net names, the channel_path.waypoints length,
whether _astar_route[_multilayer] returned a path object at all, its
forced_segment_count, and the straight-line get_blocking_nets() result for
every waypoint pair -- i.e. distinguishes "channel topology gave <2
waypoints" (route_path is always None, blockers structurally unreachable)
from "search failed on a straight line that no net's copper occupies"
(genuine graph-connectivity / iteration-budget exhaustion, not congestion).

Also records board-edge / grid-bounds context for each net's waypoints.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

TARGET_NETS = {"discharge.r_snub1-p2", "tank-out", "w1_2"}

captured: dict[str, list[dict]] = {n: [] for n in TARGET_NETS}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root
    sys.path.insert(0, str(repo_root / "scripts"))
    from route_board import _make_parsed_stub, strip_existing_copper  # noqa: E402

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6 import _astar_reconstruct as recon
    from temper_placer.router_v6 import _astar_search as search_mod
    from temper_placer.router_v6.astar_grid import _identify_blocking_nets

    pcb_path = repo_root / "pcb" / "temper.kicad_pcb"
    rules_path = repo_root / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    rules = load_netclass_rules(rules_path)
    netlist = parse_kicad_pcb(pcb_path).netlist

    content = pcb_path.read_text(encoding="utf-8")
    cleaned, _ = strip_existing_copper(content)
    import tempfile

    tmp = tempfile.NamedTemporaryFile("w", suffix=".kicad_pcb", delete=False, encoding="utf-8")
    tmp.write(cleaned)
    tmp.close()
    route_src = Path(tmp.name)
    parsed_stub = _make_parsed_stub(route_src, netlist)

    real_with_ripup = recon._astar_route_with_ripup

    def _capturing_with_ripup(net_name, channel_path, grid, design_rules, net_ids, *a, **kw):
        result = real_with_ripup(net_name, channel_path, grid, design_rules, net_ids, *a, **kw)
        if net_name in TARGET_NETS:
            path, ripped_ids, fb = result
            waypoints = list(channel_path.waypoints)
            straight_line_blockers = []
            for i in range(len(waypoints) - 1):
                p1, p2 = waypoints[i], waypoints[i + 1]
                grids = [grid]
                alt = kw.get("alternate_grid") or (a[0] if a else None)
                if alt is not None and hasattr(alt, "get_blocking_nets"):
                    grids.append(alt)
                seg_blockers = set()
                for g in grids:
                    try:
                        seg_blockers.update(g.get_blocking_nets(p1, p2))
                    except Exception as e:  # noqa: BLE001
                        seg_blockers.add(f"ERROR:{e!r}")
                straight_line_blockers.append(
                    {"p1": p1, "p2": p2, "blockers": sorted(str(x) for x in seg_blockers)}
                )
            captured[net_name].append(
                {
                    "waypoint_count": len(waypoints),
                    "waypoints": waypoints,
                    "preferred_layer": getattr(channel_path, "preferred_layer", None),
                    "path_is_none": path is None,
                    "forced_segment_count": (
                        None if path is None else getattr(path, "forced_segment_count", None)
                    ),
                    "failed_waypoint_indices": (
                        None if path is None else getattr(path, "failed_waypoint_indices", None)
                    ),
                    "ripped_ids_returned": list(ripped_ids),
                    "straight_line_blockers_per_segment": straight_line_blockers,
                    "grid_bounds": {
                        "width_cells": grid.width_cells,
                        "height_cells": grid.height_cells,
                        "cell_size": grid.cell_size,
                    },
                }
            )
        return result

    recon._astar_route_with_ripup = _capturing_with_ripup
    try:
        from temper_placer.router_v6.adapter import route_pcb

        t0 = time.perf_counter()
        result = route_pcb(
            parsed_stub,
            {},
            design_rules=rules.design_rules,
            enable_geographic_pruning=False,
            enable_net_batching=True,
            net_batch_size=10,
        )
        wall_s = time.perf_counter() - t0
    finally:
        recon._astar_route_with_ripup = real_with_ripup

    out = {
        "wall_s": wall_s,
        "completion_rate": result.completion_rate,
        "unrouted_count": len(result.unrouted_nets),
        "target_nets_still_unrouted": sorted(TARGET_NETS & set(result.unrouted_nets)),
        "captured": captured,
    }
    args.output.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
