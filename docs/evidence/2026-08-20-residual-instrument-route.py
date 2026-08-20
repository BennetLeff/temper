# provenance: commit=fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 dirty=false
# Branch agent/residual-connectivity-diagnosis, branched from fd4e73644
# (= origin/main eb5022510 + the two backbone fixes), MIN_BARRIER_WIDTH_MM = 12.6
# -- the reference configuration the 251/82/36 figures of
# docs/evidence/2026-08-19-per-pairing-placement-routed.md come from.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Instrumented production route: per-net, per-segment tier-cascade trace.

Runs the SAME call route_board.py's default recipe runs (route_once with
every default), with monkeypatches that only OBSERVE -- no behavior change:

  * _astar_nlayer._astar_route_nlayer   -> per-net envelope (waypoints in,
                                           RoutePath3D out)
  * _astar_nlayer._segment_search       -> per Tier-1/Tier-2 A* call
                                           (layer, cells, cell occupancy at
                                           start/goal, wall time, hit/miss)
  * _astar_nlayer._route_segment_3d     -> per Tier-3 call (wall time, hit)
  * _astar_nlayer.run_astar_pathfinding_nlayer -> the net universe it was
                                           handed and the result it returned
  * _astar_reconstruct.run_astar_pathfinding  -> proof of (non-)entry
  * _pipeline_route._run_stage4/_run_stage5 counters

Writes a JSON blob to --out.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--repo", required=True, type=Path)
p.add_argument("--out", required=True, type=Path)
p.add_argument("--board-out", required=True, type=Path)
# ADDITIVE: default None -> the committed board, i.e. the original behaviour.
p.add_argument("--pcb", default=None, type=Path)
args = p.parse_args()

sys.path.insert(0, str(args.repo / "scripts"))

TRACE: dict = {
    "nets": {},            # net_name -> per-net record
    "seg_calls": [],       # flat list of Tier1/2 A* calls
    "t3_calls": [],
    "nlayer_entered": 0,
    "legacy_entered": 0,
    "run_summaries": [],
}

#: The net whose route is currently being attempted, so every probe
#: below can attribute its observation without threading a parameter
#: through production code.
_cur_net = {"name": None}


def _install_patches():
    from temper_placer.router_v6 import _astar_nlayer as N
    from temper_placer.router_v6 import _astar_reconstruct as R

    orig_seg = N._segment_search
    orig_t3 = N._route_segment_3d
    orig_route = N._astar_route_nlayer
    orig_run = N.run_astar_pathfinding_nlayer
    orig_legacy = R.run_astar_pathfinding

    def seg_probe(grid, start_world, goal_world, *a, **kw):
        t0 = time.perf_counter()
        s = grid.world_to_grid(*start_world)
        g = grid.world_to_grid(*goal_world)
        h, w = grid.grid.shape

        def cell(c):
            x, y = c
            if 0 <= x < w and 0 <= y < h:
                return int(grid.grid[y, x])
            return None

        sv, gv = cell(s), cell(g)
        inb = sv is not None and gv is not None
        path, gu, fb = orig_seg(grid, start_world, goal_world, *a, **kw)
        dt = (time.perf_counter() - t0) * 1000.0
        TRACE["seg_calls"].append(
            {
                "net": _cur_net["name"],
                "start": [round(start_world[0], 4), round(start_world[1], 4)],
                "goal": [round(goal_world[0], 4), round(goal_world[1], 4)],
                "layer": grid.layer_name,
                "in_bounds": inb,
                "start_cell_val": sv,
                "goal_cell_val": gv,
                "max_iter": kw.get("max_iter"),
                "hit": path is not None,
                "path_len": len(path) if path else 0,
                "ms": round(dt, 3),
                "span_mm": round(
                    ((goal_world[0] - start_world[0]) ** 2
                     + (goal_world[1] - start_world[1]) ** 2) ** 0.5, 3),
            }
        )
        return path, gu, fb

    #: Filled by the route_segment_3d_py wrapper below, drained per T3 call.
    _t3_iters: list = []

    def _cells_all_layers(world, grids):
        """Grid value at `world` on EVERY grid, not just the terminal layer."""
        out = {}
        for lname, g in grids.items():
            x, y = g.world_to_grid(*world)
            h, w = g.grid.shape
            out[lname] = int(g.grid[y, x]) if (0 <= x < w and 0 <= y < h) else None
        return out

    def t3_probe(start_world, goal_world, sl, gl, grids, **kw):
        s_cells = _cells_all_layers(start_world, grids)
        g_cells = _cells_all_layers(goal_world, grids)
        _t3_iters.clear()
        t0 = time.perf_counter()
        r = orig_t3(start_world, goal_world, sl, gl, grids, **kw)
        dt = (time.perf_counter() - t0) * 1000.0
        TRACE["t3_calls"].append(
            {
                "net": _cur_net["name"],
                # The two cells the search actually terminates on.
                "start_cell_val": s_cells.get(sl),
                "goal_cell_val": g_cells.get(gl),
                # Every layer, so "could a via have rescued it" is answerable.
                "start_cells": s_cells,
                "goal_cells": g_cells,
                "iters": list(_t3_iters),
                "start": [round(start_world[0], 4), round(start_world[1], 4)],
                "goal": [round(goal_world[0], 4), round(goal_world[1], 4)],
                "start_layer": sl,
                "goal_layer": gl,
                "layers": sorted(grids),
                "max_iter": kw.get("max_iter"),
                "via_diameter": kw.get("via_diameter"),
                "clearance": kw.get("clearance"),
                "hit": r is not None,
                "ms": round(dt, 3),
                "span_mm": round(
                    ((goal_world[0] - start_world[0]) ** 2
                     + (goal_world[1] - start_world[1]) ** 2) ** 0.5, 3),
            }
        )
        return r

    class TallyProxy:
        """Forwards to the real TierTally, records (segment_index, tier)."""

        def __init__(self, real, log):
            object.__setattr__(self, "_real", real)
            object.__setattr__(self, "_log", log)

        def record(self, tier):
            # Exactly one record per segment attempt, in segment order.
            object.__getattribute__(self, "_log").append(tier.value)
            object.__getattribute__(self, "_real").record(tier)

        def __getattr__(self, k):
            return getattr(object.__getattribute__(self, "_real"), k)

        def __setattr__(self, k, v):
            setattr(object.__getattribute__(self, "_real"), k, v)

    def route_probe(net_name, channel_path, grids, **kw):
        wps = list(getattr(channel_path, "waypoints", []) or [])
        log: list = []
        real_tally = kw.get("tally")
        if real_tally is not None:
            kw["tally"] = TallyProxy(real_tally, log)
        _cur_net["name"] = net_name

        # Segment index is reconstructed offline from each call's recorded
        # (start, goal) world coords matched against `waypoints` below --
        # the loop variable `i` is not visible from outside orig_route.
        n_before = len(TRACE["seg_calls"])
        t3_before = len(TRACE["t3_calls"])
        t0 = time.perf_counter()
        rp, fb = orig_route(net_name, channel_path, grids, **kw)
        dt = (time.perf_counter() - t0) * 1000.0

        rec = {
            "net": net_name,
            "n_waypoints": len(wps),
            "n_segments": max(0, len(wps) - 1),
            "preferred_layer": getattr(channel_path, "preferred_layer", None),
            "grids": sorted(grids),
            "pad_layer_start": kw.get("pad_layer_start"),
            "pad_layer_end": kw.get("pad_layer_end"),
            "max_iter": kw.get("max_iter"),
            "t3_max_iter": kw.get("segment_3d_fallback_max_iter"),
            "allow_forced": kw.get("allow_forced_segments"),
            "tier_log": log,
            "n_seg_calls": len(TRACE["seg_calls"]) - n_before,
            "n_t3_calls": len(TRACE["t3_calls"]) - t3_before,
            "ms": round(dt, 1),
            "waypoints": [[round(x, 3), round(y, 3)] for x, y in wps],
            "route_path": None,
        }
        if rp is not None:
            rec["route_path"] = {
                "n_segments_emitted": len(rp.segments),
                "n_vias": len(rp.via_positions),
                "forced_segment_count": rp.forced_segment_count,
                "failed_waypoint_indices": list(rp.failed_waypoint_indices or []),
                "path_length": round(rp.path_length, 3),
                "layers_touched": sorted({s[2] for s in rp.segments}),
            }
        # multiple stage-4 invocations would collide; keep a list
        TRACE["nets"].setdefault(net_name, []).append(rec)
        _cur_net["name"] = None
        return rp, fb

    # ---- run 2 probes: where does a blocked endpoint cell come from? ----
    orig_unblock = N._unblock_net_pads
    orig_stamp = N._stamp_foreign_creepage_halos
    _pads_stash: dict = {}

    def _pad_cells(net_name, grids, pads):
        """Grid value at each of the net's own pad centres, per layer."""
        out = []
        for (px, py, rad, layer) in pads:
            for lname, g in grids.items():
                x, y = g.world_to_grid(px, py)
                h, w = g.grid.shape
                v = int(g.grid[y, x]) if (0 <= x < w and 0 <= y < h) else None
                out.append([round(px, 4), round(py, 4), layer, lname, v])
        return out

    def unblock_probe(net_name, pad_info, grids, **kw):
        r = orig_unblock(net_name, pad_info, grids, **kw)
        pads = (pad_info or {}).get(net_name) or []
        _pads_stash[net_name] = (pads, grids)
        TRACE.setdefault("pad_cells_after_unblock", {})[net_name] = _pad_cells(
            net_name, grids, pads)
        return r

    def stamp_probe(net_name, grids, halos):
        import numpy as _np
        before = {ln: int(_np.count_nonzero(g.grid == -1))
                  for ln, g in grids.items()}
        orig_stamp(net_name, grids, halos)
        after = {ln: int(_np.count_nonzero(g.grid == -1))
                 for ln, g in grids.items()}
        pads, _ = _pads_stash.get(net_name, ([], grids))
        TRACE.setdefault("pad_cells_after_stamp", {})[net_name] = _pad_cells(
            net_name, grids, pads)
        TRACE.setdefault("halo_flips", {})[net_name] = {
            ln: after[ln] - before[ln] for ln in after}
        return None

    N._unblock_net_pads = unblock_probe
    N._stamp_foreign_creepage_halos = stamp_probe

    # A* iteration accounting: the Rust kernel returns (path, iters) and the
    # Python front-end drops iters. Wrap the pyfunction to keep it.
    import temper_rust_router as _trr
    orig_kernel = _trr.astar_kernel_3d_py

    def kernel_probe(*a, **kw):
        if len(TRACE.setdefault("kernel_callers", [])) < 40:
            f = sys._getframe(1)
            chain = []
            for _ in range(8):
                if f is None:
                    break
                chain.append(f"{Path(f.f_code.co_filename).name}:"
                             f"{f.f_code.co_name}:{f.f_lineno}")
                f = f.f_back
            TRACE["kernel_callers"].append(
                {"max_iterations": a[5] if len(a) > 5 else None,
                 "seg_idx": len(TRACE["seg_calls"]), "chain": chain})
        path, iters = orig_kernel(*a, **kw)
        max_it = a[5] if len(a) > 5 else kw.get("max_iterations")
        TRACE.setdefault("kernel_calls", []).append(
            [_cur_net["name"], int(iters), int(max_it) if max_it else None,
             len(path), len(TRACE["seg_calls"])]
        )
        return path, iters

    _trr.astar_kernel_3d_py = kernel_probe

    # Tier 3's own kernel returns iterations too, and route_segment_3d_rust
    # drops them exactly like the 2D front-end does. Keep them.
    orig_rs3d = _trr.route_segment_3d_py

    def rs3d_probe(*a, **kw):
        out = orig_rs3d(*a, **kw)
        # (world_path, via_world, via_cells, found, iters)
        _t3_iters.append(int(out[4]))
        return out

    _trr.route_segment_3d_py = rs3d_probe

    orig_families = N._build_width_families

    def families_probe(grids, routing_spaces, routable_nets, design_rules,
                       pcb=None, escape_vias_map=None):
        fams, fam_of_net, halos = orig_families(
            grids, routing_spaces, routable_nets, design_rules, pcb,
            escape_vias_map)
        import numpy as _np
        stats = {}
        for sig, layer_grids in fams.items():
            per_layer = {}
            for layer, g in layer_grids.items():
                arr = g.grid
                per_layer[layer] = {
                    "cells": int(arr.size),
                    "free": int(_np.count_nonzero(arr == 0)),
                    "static_blocked": int(_np.count_nonzero(arr == -1)),
                }
            stats[repr(sig)] = {
                "inflation_mm": N._family_static_inflation(sig),
                "layers": per_layer,
                "n_nets": sum(1 for v in fam_of_net.values() if v == sig),
            }
        TRACE.setdefault("families", []).append(
            {
                "stats": stats,
                "family_of_net": {n: repr(s) for n, s in fam_of_net.items()},
                "routing_spaces": sorted(routing_spaces or {}),
            }
        )
        return fams, fam_of_net, halos

    N._build_width_families = families_probe

    def run_probe(channel_mapping, grids, design_rules=None, **kw):
        TRACE["nlayer_entered"] += 1
        from temper_placer.router_v6._net_policy import _should_route
        from temper_placer.router_v6._astar_ordering import _compute_net_order

        order = _compute_net_order(channel_mapping)
        routable = [n for n in order if _should_route(n)]
        t0 = time.perf_counter()
        res = orig_run(channel_mapping, grids, design_rules, **kw)
        summary = {
            "invocation": TRACE["nlayer_entered"],
            "wall_s": round(time.perf_counter() - t0, 1),
            "grids": sorted(grids),
            "n_channel_paths": len(channel_mapping.channel_paths),
            "channel_paths": sorted(channel_mapping.channel_paths),
            "n_net_order": len(order),
            "routable_nets": routable,
            "excluded_by_should_route": sorted(set(order) - set(routable)),
            "target_nets": kw.get("target_nets"),
            "max_nets": kw.get("max_nets"),
            "routed_paths": sorted(res.routed_paths),
            "failed_nets": sorted(res.failed_nets),
            "partial_paths": sorted(res.partial_paths or {}),
            "failure_reasons": {
                n: r.failure_reason for n, r in (res.failure_reports or {}).items()
            },
            "tier_tally": res.tier_tally,
            "waypoint_counts": {
                n: len(p.waypoints or [])
                for n, p in channel_mapping.channel_paths.items()
            },
            "preferred_layers": {
                n: getattr(p, "preferred_layer", None)
                for n, p in channel_mapping.channel_paths.items()
            },
            "net_rules": {
                n: {
                    "class": getattr(design_rules.get_rules_for_net(n), "name", None),
                    "trace_width_mm": getattr(
                        design_rules.get_rules_for_net(n), "trace_width_mm", None),
                    "clearance_mm": getattr(
                        design_rules.get_rules_for_net(n), "clearance_mm", None),
                    "via_diameter_mm": getattr(
                        design_rules.get_rules_for_net(n), "via_diameter_mm", None),
                }
                for n in routable
            } if design_rules is not None else {},
        }
        TRACE["run_summaries"].append(summary)
        return res

    def legacy_probe(*a, **kw):
        TRACE["legacy_entered"] += 1
        return orig_legacy(*a, **kw)

    N._segment_search = seg_probe
    N._route_segment_3d = t3_probe
    N._astar_route_nlayer = route_probe
    N.run_astar_pathfinding_nlayer = run_probe
    R.run_astar_pathfinding = legacy_probe

    # _pipeline_route imports run_astar_pathfinding lazily inside _run_stage4,
    # and calls run_astar_pathfinding_nlayer via a local import -- both resolve
    # through the module objects we just patched.


def main():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    _install_patches()

    import route_board

    pcb = args.pcb if args.pcb is not None else args.repo / "pcb" / "temper.kicad_pcb"
    rules = (args.repo / "packages" / "temper-placer" / "configs"
             / "netclass_rules.yaml")

    t0 = time.perf_counter()
    r = route_board.route_once(pcb, rules)
    wall = time.perf_counter() - t0

    content = r.pop("routed_pcb_content", "") or ""
    args.board_out.write_text(content, encoding="utf-8")

    TRACE["route_summary"] = {
        k: v for k, v in r.items() if k != "routed_pcb_content"
    }
    TRACE["wall_s"] = round(wall, 1)
    args.out.write_text(json.dumps(TRACE, default=str), encoding="utf-8")
    print(f"wall={wall:.1f}s  nlayer_entered={TRACE['nlayer_entered']} "
          f"legacy_entered={TRACE['legacy_entered']} "
          f"segments={r['segments']} vias={r['vias']} zones={r['zones']}")


main()
