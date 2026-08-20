# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Rip-up probe: does the production router ever rip up a routed net?

Observe-only monkeypatches on the production route (route_board.route_once),
plus an OPTIONAL net-order permutation (--reorder) used to price what a
successful rip-up-and-reroute would have bought.

Every probe below either counts calls or records arguments/returns; the only
behaviour-changing knob is --reorder, which is off by default so the default
invocation reproduces the unmodified production route byte-for-byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--out", required=True, type=Path)
ap.add_argument("--board-out", required=True, type=Path)
ap.add_argument("--pcb", default=None, type=Path)
ap.add_argument("--reorder", default=None, type=Path,
                help="JSON: {'mode':'promote_front'|'before','nets':[...],"
                     "'pairs':[[victim,blocker],...]}")
args = ap.parse_args()

sys.path.insert(0, str(args.repo / "scripts"))

T: dict = {
    "nlayer_entered": 0,
    "legacy_entered": 0,
    "route_calls": {},          # net -> [ {forced, ok, ...} ]  (retry detector)
    "identify_blocking_calls": 0,
    "identify_blocking_returns": [],
    "unmark_calls": 0,
    "mark_calls": 0,
    "allow_forced_returns": [],
    "reroute_queue_symbols": {},
    "pad_cells_after_unblock": {},
    "run_summaries": [],
    "reorder": None,
}
_cur = {"net": None}


def install():
    from temper_placer.router_v6 import _astar_nlayer as N
    from temper_placer.router_v6 import _astar_reconstruct as R
    from temper_placer.router_v6 import astar_grid as G
    from temper_placer.router_v6._net_policy import _should_route

    # ---- 1. which pathfinder runs -------------------------------------
    o_run, o_legacy = N.run_astar_pathfinding_nlayer, R.run_astar_pathfinding

    # ---- 2. rip-up trigger: forced segments ---------------------------
    o_allow = N._allow_forced_segments

    def allow_probe(net_name, design_rules, tree_route_active):
        v = o_allow(net_name, design_rules, tree_route_active)
        T["allow_forced_returns"].append(bool(v))
        return v

    N._allow_forced_segments = allow_probe

    # ---- 3. rip-up trigger: blocker identification --------------------
    o_ident = N._identify_blocking_nets

    def ident_probe(channel_path, grids):
        r = o_ident(channel_path, grids)
        T["identify_blocking_calls"] += 1
        T["identify_blocking_returns"].append([_cur["net"], sorted(r)])
        return r

    N._identify_blocking_nets = ident_probe

    # ---- 4. the actual rip-up act: un-stamping routed copper ----------
    o_unmark = G._unmark_route_blocked

    def unmark_probe(*a, **kw):
        T["unmark_calls"] += 1
        return o_unmark(*a, **kw)

    G._unmark_route_blocked = unmark_probe
    # the nlayer module does not even import it; patch every namespace that
    # does, so a rip-up anywhere in stage 4 would be seen.
    for modname in ("_astar_reconstruct", "_astar_search", "astar_pathfinding"):
        try:
            m = __import__(f"temper_placer.router_v6.{modname}", fromlist=["x"])
        except Exception:
            continue
        if hasattr(m, "_unmark_route_blocked"):
            m._unmark_route_blocked = unmark_probe
        T["reroute_queue_symbols"][modname] = sorted(
            s for s in dir(m) if "ripup" in s.lower() or "reroute" in s.lower()
        )
    T["reroute_queue_symbols"]["_astar_nlayer"] = sorted(
        s for s in dir(N) if "ripup" in s.lower() or "reroute" in s.lower()
        or s == "_unmark_route_blocked"
    )

    o_mark = N._mark_route_blocked

    def mark_probe(*a, **kw):
        T["mark_calls"] += 1
        return o_mark(*a, **kw)

    N._mark_route_blocked = mark_probe

    # ---- 5. per-net attempt count (a retry queue would show up here) ---
    o_route = N._astar_route_nlayer

    def route_probe(net_name, channel_path, grids, **kw):
        _cur["net"] = net_name
        t0 = time.perf_counter()
        rp, fb = o_route(net_name, channel_path, grids, **kw)
        T["route_calls"].setdefault(net_name, []).append({
            "ok": rp is not None,
            "forced": None if rp is None else rp.forced_segment_count,
            "allow_forced": kw.get("allow_forced_segments"),
            "ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "n_waypoints": len(getattr(channel_path, "waypoints", []) or []),
        })
        _cur["net"] = None
        return rp, fb

    N._astar_route_nlayer = route_probe

    # ---- 6. pad-cell occupancy right after unblock (blocker attribution)
    o_unblock = N._unblock_net_pads
    o_stamp = N._stamp_foreign_creepage_halos
    _stash: dict = {}

    def _pad_cells(grids, pads):
        out = []
        for (px, py, _rad, layer) in pads:
            for lname, g in grids.items():
                x, y = g.world_to_grid(px, py)
                h, w = g.grid.shape
                v = int(g.grid[y, x]) if (0 <= x < w and 0 <= y < h) else None
                out.append([round(px, 4), round(py, 4), layer, lname, v])
        return out

    def unblock_probe(net_name, pad_info, grids, **kw):
        r = o_unblock(net_name, pad_info, grids, **kw)
        pads = (pad_info or {}).get(net_name) or []
        _stash[net_name] = (pads, grids)
        T["pad_cells_after_unblock"][net_name] = _pad_cells(grids, pads)
        return r

    def stamp_probe(net_name, grids, halos):
        o_stamp(net_name, grids, halos)
        pads, _ = _stash.get(net_name, ([], grids))
        T.setdefault("pad_cells_after_stamp", {})[net_name] = _pad_cells(grids, pads)
        return None

    N._unblock_net_pads = unblock_probe
    N._stamp_foreign_creepage_halos = stamp_probe

    # ---- 7. optional order permutation --------------------------------
    o_order = N._compute_net_order
    spec = json.loads(args.reorder.read_text()) if args.reorder else None
    T["reorder"] = spec

    def order_probe(channel_mapping, bottleneck_widths=None):
        base = o_order(channel_mapping, bottleneck_widths)
        if not spec:
            return base
        mode = spec["mode"]
        if mode == "promote_front":
            promo = [n for n in spec["nets"] if n in base]
            rest = [n for n in base if n not in set(promo)]
            new = promo + rest
        elif mode == "before":
            new = list(base)
            for victim, blocker in spec["pairs"]:
                if victim not in new or blocker not in new:
                    continue
                if new.index(victim) < new.index(blocker):
                    continue
                new.remove(victim)
                new.insert(new.index(blocker), victim)
        elif mode == "most_pins_first":
            wp = {n: len(channel_mapping.channel_paths[n].waypoints or [])
                  for n in base}
            idx = {n: i for i, n in enumerate(base)}
            new = sorted(base, key=lambda n: (-wp.get(n, 0), idx[n]))
        else:
            raise SystemExit(f"unknown reorder mode {mode}")
        d = T.setdefault("order_delta", {})
        d["base_first20"] = base[:20]
        d["new_first20"] = new[:20]
        d["changed"] = sum(1 for a, b in zip(base, new, strict=True) if a != b)
        return new

    N._compute_net_order = order_probe

    def run_probe(channel_mapping, grids, design_rules=None, **kw):
        T["nlayer_entered"] += 1
        t0 = time.perf_counter()
        res = o_run(channel_mapping, grids, design_rules, **kw)
        order = N._compute_net_order(channel_mapping)
        routable = [n for n in order if _should_route(n)]
        T["run_summaries"].append({
            "invocation": T["nlayer_entered"],
            "wall_s": round(time.perf_counter() - t0, 1),
            "grids": sorted(grids),
            "n_channel_paths": len(channel_mapping.channel_paths),
            "routable_nets": routable,
            "net_ids": {n: i + 1 for i, n in enumerate(routable)},
            "routed_paths": sorted(res.routed_paths),
            "failed_nets": sorted(res.failed_nets),
            "partial_paths": sorted(res.partial_paths or {}),
            "failure_reasons": {n: r.failure_reason
                                for n, r in (res.failure_reports or {}).items()},
            "attempted_ripups": {n: r.attempted_ripups
                                 for n, r in (res.failure_reports or {}).items()},
            "blocking_nets": {n: sorted(r.blocking_nets)
                              for n, r in (res.failure_reports or {}).items()
                              if r.blocking_nets},
            "tier_tally": res.tier_tally,
        })
        return res

    def legacy_probe(*a, **kw):
        T["legacy_entered"] += 1
        return o_legacy(*a, **kw)

    N.run_astar_pathfinding_nlayer = run_probe
    R.run_astar_pathfinding = legacy_probe
    # _astar_reconstruct is NOT the name the legacy call sites resolve.
    # _pipeline_route._run_stage4 and route_stage.RouteStage.run both do
    # `from ...astar_pathfinding import run_astar_pathfinding`, which is a
    # SEPARATE binding made at astar_pathfinding import time. Patching only
    # the _astar_reconstruct attribute would report legacy_entered=0 even if
    # the legacy rip-up router had run -- a false "dead code" reading.
    from temper_placer.router_v6 import astar_pathfinding as AP

    o_ap_legacy = AP.run_astar_pathfinding

    def ap_legacy_probe(*a, **kw):
        T["legacy_entered_via_astar_pathfinding"] = (
            T.get("legacy_entered_via_astar_pathfinding", 0) + 1
        )
        return o_ap_legacy(*a, **kw)

    AP.run_astar_pathfinding = ap_legacy_probe

    # The rip-up-capable stage chain: constructed in _run_stage4, but is it
    # ever RUN? Count both the orchestrator's run() and the RouteStage that
    # would call the legacy rip-up router.
    from temper_placer.router_v6 import route_stage as RSMOD
    from temper_placer.router_v6 import stage4_orchestrator as ORCH

    o_stage_run = RSMOD.RouteStage.run
    o_orch_run = ORCH.Stage4Orchestrator.run
    o_assemble = ORCH.Stage4Orchestrator.assemble_pathfinding_result

    def stage_run_probe(self, state):
        T["route_stage_run"] = T.get("route_stage_run", 0) + 1
        return o_stage_run(self, state)

    def orch_run_probe(self, state=None):
        T["orchestrator_run"] = T.get("orchestrator_run", 0) + 1
        return o_orch_run(self, state)

    def assemble_probe(state):
        r = o_assemble(state)
        T["assemble_calls"] = T.get("assemble_calls", 0) + 1
        T.setdefault("assemble_returns", []).append(r is not None)
        return r

    RSMOD.RouteStage.run = stage_run_probe
    ORCH.Stage4Orchestrator.run = orch_run_probe
    ORCH.Stage4Orchestrator.assemble_pathfinding_result = staticmethod(assemble_probe)


def main():
    os.environ.setdefault("PYTHONHASHSEED", "0")
    install()
    import route_board

    pcb = args.pcb if args.pcb is not None else args.repo / "pcb" / "temper.kicad_pcb"
    rules = args.repo / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    t0 = time.perf_counter()
    r = route_board.route_once(pcb, rules)
    wall = time.perf_counter() - t0
    content = r.pop("routed_pcb_content", "") or ""
    args.board_out.write_text(content, encoding="utf-8")
    T["board_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    T["route_summary"] = {k: v for k, v in r.items() if k != "routed_pcb_content"}
    T["wall_s"] = round(wall, 1)
    T["retried_nets"] = {n: len(v) for n, v in T["route_calls"].items() if len(v) > 1}
    T["forced_gt0"] = sum(1 for v in T["route_calls"].values()
                          for c in v if (c["forced"] or 0) > 0)
    args.out.write_text(json.dumps(T, default=str), encoding="utf-8")
    print(f"wall={wall:.1f}s nlayer={T['nlayer_entered']} legacy={T['legacy_entered']} "
          f"segments={r['segments']} vias={r['vias']} zones={r['zones']} "
          f"sha={T['board_sha256'][:16]}")
    print(f"STAGE4: orchestrator_run={T.get('orchestrator_run', 0)} "
          f"route_stage_run={T.get('route_stage_run', 0)} "
          f"assemble_calls={T.get('assemble_calls', 0)} "
          f"assemble_non_none={sum(T.get('assemble_returns', []))} "
          f"legacy_via_astar_pathfinding="
          f"{T.get('legacy_entered_via_astar_pathfinding', 0)}")
    print(f"RIPUP: unmark_calls={T['unmark_calls']} "
          f"identify_calls={T['identify_blocking_calls']} "
          f"forced_paths={T['forced_gt0']} retried_nets={len(T['retried_nets'])} "
          f"allow_forced_true={sum(T['allow_forced_returns'])}/"
          f"{len(T['allow_forced_returns'])}")


main()
