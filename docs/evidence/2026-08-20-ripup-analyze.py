# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Analyse a rip-up probe trace: does rip-up run, and what is its absence worth?

Reuses the attribution rule of docs/evidence/2026-08-20-residual-analyze.py
(pad-cell value sampled between _unblock_net_pads and
_stamp_foreign_creepage_halos, restricted to each pad's own layer) so the
buckets are directly comparable, and additionally resolves the POSITIVE cell
value -- which is the blocking net's net_id -- back to a net NAME.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--trace", required=True, type=Path)
ap.add_argument("--board", required=True, type=Path)
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--label", default="")
ap.add_argument("--emit", default=None, type=Path)
args = ap.parse_args()

T = json.loads(args.trace.read_text())
S = T["run_summaries"][-1]
rs = T["route_summary"]
sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file  # noqa: E402


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


OUT: dict = {"label": args.label}

rule(f"0. ENVELOPE [{args.label}]")
print(f"wall={T['wall_s']}s segments={rs['segments']} vias={rs['vias']} "
      f"zones={rs['zones']} board_sha256={T['board_sha256'][:16]}")
print(f"nlayer_entered={T['nlayer_entered']}  "
      f"legacy_entered(_astar_reconstruct name)={T['legacy_entered']}  "
      f"legacy_entered(astar_pathfinding name)="
      f"{T.get('legacy_entered_via_astar_pathfinding', 'n/a')}")
print(f"Stage4Orchestrator.run={T.get('orchestrator_run', 'n/a')}  "
      f"RouteStage.run={T.get('route_stage_run', 'n/a')}  "
      f"assemble_pathfinding_result calls={T.get('assemble_calls', 'n/a')} "
      f"non-None={sum(T.get('assemble_returns', []))}")
print(f"routed={len(S['routed_paths'])} failed={len(S['failed_nets'])} "
      f"partial={len(S['partial_paths'])} routable={len(S['routable_nets'])}")

rule("1. DOES RIP-UP RUN?  (execution counters, one full production route)")
print(f"  _mark_route_blocked calls (copper stamped)      : {T['mark_calls']}")
print(f"  _unmark_route_blocked calls (copper RIPPED UP)  : {T['unmark_calls']}")
print(f"  _identify_blocking_nets calls (rip-up trigger)  : "
      f"{T['identify_blocking_calls']}")
print(f"  paths returned with forced_segment_count > 0    : {T['forced_gt0']}")
print(f"  _allow_forced_segments True/total               : "
      f"{sum(T['allow_forced_returns'])}/{len(T['allow_forced_returns'])}")
print(f"  nets attempted more than once (retry queue)     : "
      f"{len(T['retried_nets'])}  {T['retried_nets']}")
print(f"  attempted_ripups reported, distinct values      : "
      f"{sorted(set(S['attempted_ripups'].values()))}")
print(f"  failure_reason == 'rip_up_limit'                : "
      f"{sum(1 for v in S['failure_reasons'].values() if v == 'rip_up_limit')}")
print(f"  rip-up/reroute symbols visible per module       : "
      f"{T['reroute_queue_symbols']}")
OUT["ripup"] = {
    "mark_calls": T["mark_calls"], "unmark_calls": T["unmark_calls"],
    "identify_calls": T["identify_blocking_calls"],
    "forced_gt0": T["forced_gt0"], "retried_nets": T["retried_nets"],
    "attempted_ripups_values": sorted(set(S["attempted_ripups"].values())),
    "nlayer_entered": T["nlayer_entered"],
    "legacy_entered": T["legacy_entered"],
    "legacy_entered_via_astar_pathfinding":
        T.get("legacy_entered_via_astar_pathfinding"),
    "orchestrator_run": T.get("orchestrator_run"),
    "route_stage_run": T.get("route_stage_run"),
}

# ------------------------------------------------------------------ universe
audit = audit_pcb_file(args.board)
multi = {n: r for n, r in audit.items() if r.pad_count >= 2}
zero = {n: r for n, r in multi.items() if not r.has_any_copper}
ZC = {n: r for n, r in zero.items() if not r.zone_layers}
notfull = {n: r for n, r in audit.items() if not r.fully_connected}
edges = sum(r.pad_count - 1 for r in ZC.values())

rule("2. UNIVERSE")
print(f"nets={len(audit)} fully_connected={len(audit) - len(notfull)} "
      f"not_fully={len(notfull)} multi_pad={len(multi)}")
print(f"zero copper={len(zero)}  zero copper AND zero zone={len(ZC)} "
      f"-> {edges} ratsnest edges")
OUT["universe"] = {
    "n_nets": len(audit), "fully_connected": len(audit) - len(notfull),
    "not_fully_connected": len(notfull), "multi_pad": len(multi),
    "zero_copper": len(zero), "zero_copper_zero_zone": len(ZC),
    "zc_edges": edges, "zc_nets": sorted(ZC), "routed": len(S["routed_paths"]),
    "segments": rs["segments"], "vias": rs["vias"], "zones": rs["zones"],
}

# ------------------------------------------- blocked-by-earlier-copper bucket
unb = T.get("pad_cells_after_unblock", {})
stm = T.get("pad_cells_after_stamp", {})
net_ids = S["net_ids"]
id_to_net = {v: k for k, v in net_ids.items()}
order_index = {n: i for i, n in enumerate(S["routable_nets"])}
routed_ok = set(S["routed_paths"])


def own(pad_layer, grid_layer):
    return (pad_layer == grid_layer or pad_layer in ("All", "all")
            or "*.Cu" in str(pad_layer) or "Through" in str(pad_layer))


per_net = {}
claimers = {}
for n in sorted(ZC):
    a = unb.get(n) or []
    b = {(r[0], r[1], r[3]): r[4] for r in (stm.get(n) or [])}
    nb = Counter()
    who = Counter()
    for px, py, pad_layer, grid_layer, v0 in a:
        if not own(pad_layer, grid_layer):
            continue
        v1 = b.get((px, py, grid_layer))
        if v0 == 0 and v1 == 0:
            nb["free_after_both"] += 1
        elif v0 == 0 and v1 not in (0, None):
            nb["FREED_then_BLOCKED_by_foreign_creepage_halo"] += 1
        elif v0 == -1:
            nb["still_static_blocked_after_unblock"] += 1
        elif v0 is not None and v0 > 0:
            nb["claimed_by_an_already_ROUTED_net"] += 1
            who[id_to_net.get(v0, f"id{v0}")] += 1
        else:
            nb["unresolvable"] += 1
    per_net[n] = nb
    claimers[n] = who


def verdict(n):
    nb = per_net.get(n, Counter())
    if nb["FREED_then_BLOCKED_by_foreign_creepage_halo"]:
        return "foreign creepage halo"
    if nb["claimed_by_an_already_ROUTED_net"]:
        return "already-ROUTED net's copper stamp"
    if nb["still_static_blocked_after_unblock"]:
        return "still statically blocked"
    return "endpoints free - search lost"


rule(f"3. WHY THE {len(ZC)} ZERO-COPPER NETS ARE STUCK")
vc = Counter(verdict(n) for n in ZC)
for k, v in vc.most_common():
    print(f"  {k:42s} {v:4d}")

stamped = sorted(n for n in ZC if verdict(n) == "already-ROUTED net's copper stamp")
rule(f"4. THE ORDER-DEPENDENT SELF-BLOCK BUCKET: {len(stamped)} NETS")
pairs = []
for n in stamped:
    who = claimers[n]
    oi = order_index.get(n, -1)
    print(f"  {n:32s} order#{oi:<4d} pads={ZC[n].pad_count} "
          f"reason={S['failure_reasons'].get(n)}")
    for blk, cnt in who.most_common():
        bi = order_index.get(blk, -1)
        earlier = "EARLIER" if 0 <= bi < oi else "later/na"
        print(f"        claimed by {blk:28s} order#{bi:<4d} "
              f"({cnt} pad cells, {earlier}, routed={blk in routed_ok})")
        pairs.append([n, blk])
OUT["stamped"] = {
    n: {"order": order_index.get(n, -1), "pads": ZC[n].pad_count,
        "reason": S["failure_reasons"].get(n),
        "claimers": {b: [c, order_index.get(b, -1), b in routed_ok]
                     for b, c in claimers[n].items()}}
    for n in stamped
}
OUT["pairs"] = pairs
OUT["verdicts"] = dict(vc)

if args.emit:
    args.emit.write_text(json.dumps(OUT, indent=2), encoding="utf-8")
    print(f"\nwrote {args.emit}")
