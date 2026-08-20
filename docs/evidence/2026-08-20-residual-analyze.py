# provenance: commit=fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 dirty=false
# Branch agent/residual-connectivity-diagnosis, branched from fd4e73644
# (= origin/main eb5022510 + the two backbone fixes), MIN_BARRIER_WIDTH_MM = 12.6
# -- the reference configuration the 251/82/36 figures of
# docs/evidence/2026-08-19-per-pairing-placement-routed.md come from.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Residual-connectivity diagnosis: the four questions, from one trace.

Q1  mechanism split of the zero-copper nets (decline / fail / discard)
Q2  the zero-copper nets that are NOT halo-blocked
Q3  the not-fully-connected nets: what fraction of pads attach, and why not more
Q4  Tier 3: does it earn its wall time

Input is one instrumented production route (instrument.py) plus the board
that run wrote. Reuses the attribution logic of
docs/evidence/2026-08-19-mechanism-a-analyze.py so the two are comparable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--trace", required=True, type=Path)
p.add_argument("--board", required=True, type=Path)
p.add_argument("--repo", required=True, type=Path)
p.add_argument("--label", default="")
p.add_argument("--emit", default=None, type=Path, help="write machine-readable JSON")
args = p.parse_args()

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

# ---------------------------------------------------------------- envelope
rule(f"0. RUN ENVELOPE  [{args.label}]")
print(f"wall={T['wall_s']}s segments={rs['segments']} vias={rs['vias']} zones={rs['zones']}")
print(f"nlayer_entered={T['nlayer_entered']} legacy_entered={T['legacy_entered']}")
print(f"grids={S['grids']}")
print(f"channel_paths={S['n_channel_paths']} routable={len(S['routable_nets'])} "
      f"excluded_by_should_route={len(S['excluded_by_should_route'])}")
print(f"routed={len(S['routed_paths'])} failed={len(S['failed_nets'])} "
      f"partial={len(S['partial_paths'])}")
print(f"tier_tally={S['tier_tally']}")
OUT["envelope"] = {
    "wall_s": T["wall_s"], "segments": rs["segments"], "vias": rs["vias"],
    "zones": rs["zones"], "tier_tally": S["tier_tally"],
}

# ---------------------------------------------------------------- universe
audit = audit_pcb_file(args.board)
multi = {n: r for n, r in audit.items() if r.pad_count >= 2}
zero = {n: r for n, r in multi.items() if not r.has_any_copper}
ZC = {n: r for n, r in zero.items() if not r.zone_layers}   # zero copper AND zero zone
full = {n: r for n, r in audit.items() if r.fully_connected}
notfull = {n: r for n, r in audit.items() if not r.fully_connected}

rule("1. UNIVERSE")
print(f"all nets                        : {len(audit)}")
print(f"  fully pad-connected           : {len(full)}")
print(f"  NOT fully connected           : {len(notfull)}")
print(f"nets with >=2 pads              : {len(multi)}")
print(f"  zero segment/via copper       : {len(zero)}")
print(f"  zero copper AND zero zone     : {len(ZC)}  "
      f"-> {sum(r.pad_count - 1 for r in ZC.values())} ratsnest edges")
print(f"zero-copper but zoned           : {sorted(set(zero) - set(ZC))}")
OUT["universe"] = {
    "n_nets": len(audit), "fully_connected": len(full),
    "not_fully_connected": len(notfull), "multi_pad": len(multi),
    "zero_copper": len(zero), "zero_copper_zero_zone": len(ZC),
    "zero_copper_zero_zone_nets": sorted(ZC),
}

# ------------------------------------------------------- Q1 mechanism split
routable = set(S["routable_nets"])
routed_ok = set(S["routed_paths"])
reasons = S["failure_reasons"]
wpc = S["waypoint_counts"]


def rec_of(n):
    r = T["nets"].get(n) or []
    return r[-1] if r else None


MECH = {}
for n in multi:
    rec = rec_of(n)
    if n not in wpc:
        MECH[n] = "no_channel_path"
    elif n not in routable:
        MECH[n] = "DECLINE_by_should_route_policy"
    elif rec is None:
        MECH[n] = "never_reached_astar"
    elif rec["n_waypoints"] < 2:
        MECH[n] = "fewer_than_2_waypoints"
    elif n in routed_ok:
        MECH[n] = "routed"
    else:
        rsn = reasons.get(n, "?")
        tl = rec["tier_log"]
        if rsn.startswith("pad_layer_landing_blocked"):
            MECH[n] = "DISCARD_complete_route_landing_blocked"
        elif tl and tl[-1] == "declined":
            MECH[n] = ("FAIL_declined_hop0_nothing_computed"
                       if len(tl) == 1 else "DISCARD_partial_after_success")
        else:
            MECH[n] = f"other:{rsn}"

rule(f"2. Q1 — MECHANISM SPLIT OF THE {len(ZC)} ZERO-COPPER NETS")
zc_mech = Counter(MECH[n] for n in ZC)
for k, v in zc_mech.most_common():
    edges = sum(ZC[n].pad_count - 1 for n in ZC if MECH[n] == k)
    print(f"  {k:44s} {v:4d} nets  {edges:4d} edges")
print("\nper-net (net, mechanism, pads, tier_log):")
for n in sorted(ZC):
    rec = rec_of(n)
    tl = (rec or {}).get("tier_log")
    print(f"  {n:34s} {MECH[n]:42s} pads={ZC[n].pad_count} tier_log={tl}")
OUT["q1_mechanism_split"] = dict(zc_mech)
OUT["q1_per_net"] = {n: {"mech": MECH[n], "pads": ZC[n].pad_count,
                         "tier_log": (rec_of(n) or {}).get("tier_log")}
                     for n in sorted(ZC)}

# discarded geometry: what the router computed and threw away
rule("2b. SUCCEED-THEN-DISCARD: geometry computed and dropped")
disc = [n for n in ZC if MECH[n].startswith("DISCARD")]
tot_pts = tot_via = 0
for n in sorted(disc):
    rec = rec_of(n)
    rp = (rec or {}).get("route_path") or {}
    tot_pts += rp.get("n_segments_emitted", 0)
    tot_via += rp.get("n_vias", 0)
    print(f"  {n:34s} tier_log={rec['tier_log']} pts={rp.get('n_segments_emitted')} "
          f"vias={rp.get('n_vias')} len={rp.get('path_length')} "
          f"forced={rp.get('forced_segment_count')} reason={reasons.get(n)}")
print(f"  TOTAL discarded: {len(disc)} nets, {tot_pts} path points, {tot_via} vias")
OUT["q1_discarded"] = {"nets": sorted(disc), "path_points": tot_pts, "vias": tot_via}

# ------------------------------------------------------ Q2 halo attribution
unb = T.get("pad_cells_after_unblock", {})
stm = T.get("pad_cells_after_stamp", {})
declined = [n for n in multi if n not in routed_ok and n in routable]

per_net = {}
for n in sorted(set(declined) | set(ZC)):
    a = unb.get(n) or []
    b = {(r[0], r[1], r[3]): r[4] for r in (stm.get(n) or [])}
    nb = Counter()
    for px, py, pad_layer, grid_layer, v0 in a:
        v1 = b.get((px, py, grid_layer))
        own = (pad_layer == grid_layer or pad_layer in ("All", "all")
               or "*.Cu" in str(pad_layer) or "Through" in str(pad_layer))
        if v0 == 0 and v1 == 0:
            k = "free_after_both"
        elif v0 == 0 and v1 != 0:
            k = "FREED_then_BLOCKED_by_foreign_creepage_halo"
        elif v0 == -1:
            k = "still_static_blocked_after_unblock"
        elif v0 is not None and v0 > 0:
            k = "claimed_by_an_already_ROUTED_net"
        else:
            k = "unresolvable"
        if own:
            nb[k] += 1
    per_net[n] = nb


def verdict_of(n):
    nb = per_net.get(n, Counter())
    if nb["FREED_then_BLOCKED_by_foreign_creepage_halo"]:
        return "own pad inside a FOREIGN CREEPAGE HALO"
    if nb["claimed_by_an_already_ROUTED_net"]:
        return "own pad under an already-ROUTED net's stamp"
    if nb["still_static_blocked_after_unblock"]:
        return "own pad still STATICALLY blocked after unblock"
    return "endpoints free — A* frontier/budget: no path at this width"


rule(f"3. Q2 — HALO ATTRIBUTION OVER THE {len(ZC)}, AND THE NON-HALO REMAINDER")
vc = Counter(verdict_of(n) for n in ZC)
for k, v in vc.most_common():
    print(f"  {k:52s} {v:4d}")
nonhalo = sorted(n for n in ZC if verdict_of(n) != "own pad inside a FOREIGN CREEPAGE HALO")
print(f"\nTHE NON-HALO SET ({len(nonhalo)} nets):")
for n in nonhalo:
    nb = per_net.get(n, Counter())
    rec = rec_of(n)
    print(f"  {n:34s} {verdict_of(n):52s}")
    print(f"      pads={ZC[n].pad_count} mech={MECH[n]} own-layer cells={dict(nb)}")
    print(f"      tier_log={(rec or {}).get('tier_log')} "
          f"class={S.get('net_rules', {}).get(n, {}).get('class')}")
OUT["q2_verdicts"] = dict(vc)
OUT["q2_nonhalo"] = {n: {"verdict": verdict_of(n), "mech": MECH[n],
                         "pads": ZC[n].pad_count,
                         "own_layer_cells": dict(per_net.get(n, Counter())),
                         "netclass": S.get("net_rules", {}).get(n, {}).get("class")}
                     for n in nonhalo}

# --------------------------------------------------- Q3 not-fully-connected
rule(f"4. Q3 — THE {len(notfull)} NOT-FULLY-CONNECTED NETS: PAD ATTACHMENT")
buckets = defaultdict(list)
for n, r in notfull.items():
    if r.pad_count < 2:
        buckets["single-pad (no ratsnest edge)"].append(n)
    elif not r.has_any_copper and not r.zone_layers:
        buckets["zero copper, zero zone (the Q1/Q2 set)"].append(n)
    elif not r.has_any_copper and r.zone_layers:
        buckets["zero copper, zone only"].append(n)
    else:
        buckets["PARTIAL: has copper, not all pads joined"].append(n)
for k in sorted(buckets):
    print(f"  {k:44s} {len(buckets[k]):4d}")

partial = buckets["PARTIAL: has copper, not all pads joined"]
print(f"\nThe {len(partial)} genuinely partial nets — pads_connected/pad_count "
      f"(largest copper-joined pad group):")
tot_p = tot_c = 0
for n in sorted(partial, key=lambda x: -notfull[x].pad_count):
    r = notfull[n]
    rec = rec_of(n)
    tot_p += r.pad_count
    tot_c += r.pads_connected
    print(f"  {n:30s} {r.pads_connected:3d}/{r.pad_count:<3d} "
          f"({r.pads_connected/r.pad_count*100:5.1f}%) mech={MECH.get(n, '-'):40s}")
    print(f"      tier_log={(rec or {}).get('tier_log')} reason={reasons.get(n)} "
          f"zones={list(r.zone_layers)}")
if tot_p:
    print(f"  AGGREGATE: {tot_c}/{tot_p} pads attach ({tot_c/tot_p*100:.1f}%) "
          f"across the {len(partial)} partial nets")
print("\nmechanism census over the partial set:")
for k, v in Counter(MECH.get(n, "-") for n in partial).most_common():
    print(f"  {k:44s} {v:4d}")
print("\nverdict census over the partial set (same halo attribution as Q2):")
for k, v in Counter(verdict_of(n) for n in partial).most_common():
    print(f"  {k:52s} {v:4d}")
OUT["q3"] = {
    "buckets": {k: sorted(v) for k, v in buckets.items()},
    "partial_detail": {n: {"pads_connected": notfull[n].pads_connected,
                           "pad_count": notfull[n].pad_count,
                           "mech": MECH.get(n),
                           "verdict": verdict_of(n),
                           "tier_log": (rec_of(n) or {}).get("tier_log"),
                           "reason": reasons.get(n)}
                       for n in sorted(partial)},
    "aggregate_pads": [tot_c, tot_p],
}

# ------------------------------------------------------------------ Q4 tier3
rule("5. Q4 — DOES TIER 3 EARN ITS WALL TIME?")
t3 = T["t3_calls"]
tot_ms = sum(c["ms"] for c in t3)
hits = sum(1 for c in t3 if c["hit"])
print(f"calls={len(t3)}  hits={hits}  wall={tot_ms/1000:.1f}s "
      f"({tot_ms/1000/max(T['wall_s'],1)*100:.1f}% of the {T['wall_s']}s route)")

# The decisive question: could the search have succeeded at all?
end_state = Counter()
for c in t3:
    sv, gv = c.get("start_cell_val"), c.get("goal_cell_val")
    if gv is None or sv is None:
        k = "terminal OUT OF BOUNDS"
    elif gv != 0 and sv != 0:
        k = "BOTH terminals blocked"
    elif gv != 0:
        k = "GOAL cell blocked"
    elif sv != 0:
        k = "START cell blocked"
    else:
        k = "both terminals free"
    end_state[k] += 1
print("\nterminal occupancy at the Tier-3 call (on the terminal's own layer):")
for k, v in end_state.most_common():
    ms = sum(c["ms"] for c in t3 if (
        lambda sv, gv: ("terminal OUT OF BOUNDS" if (gv is None or sv is None)
                        else "BOTH terminals blocked" if (gv != 0 and sv != 0)
                        else "GOAL cell blocked" if gv != 0
                        else "START cell blocked" if sv != 0
                        else "both terminals free"))(c.get("start_cell_val"),
                                                     c.get("goal_cell_val")) == k)
    print(f"  {k:28s} {v:4d} calls  {ms/1000:6.2f}s  hits="
          f"{sum(1 for c in t3 if c['hit'] and ((lambda sv, gv: ('terminal OUT OF BOUNDS' if (gv is None or sv is None) else 'BOTH terminals blocked' if (gv != 0 and sv != 0) else 'GOAL cell blocked' if gv != 0 else 'START cell blocked' if sv != 0 else 'both terminals free'))(c.get('start_cell_val'), c.get('goal_cell_val')) == k))}")

# A blocked GOAL is unreachable at ANY budget: the goal is only popped after
# being pushed, and a cell is only pushed if is_free(). A blocked START is
# seeded regardless, so it can still succeed.
unreachable = sum(1 for c in t3 if c.get("goal_cell_val") not in (0, None))
oob = sum(1 for c in t3 if c.get("goal_cell_val") is None or c.get("start_cell_val") is None)
ms_unreach = sum(c["ms"] for c in t3 if c.get("goal_cell_val") not in (0, None))
print(f"\ncalls whose GOAL cell is blocked -> provably unsatisfiable at any budget: "
      f"{unreachable}/{len(t3)}  costing {ms_unreach/1000:.2f}s")

# Was the goal free on ANY layer? If not, no via could have rescued it either.
no_layer = 0
for c in t3:
    gc = c.get("goal_cells") or {}
    if gc and all(v != 0 for v in gc.values() if v is not None):
        no_layer += 1
print(f"calls whose GOAL cell is blocked on EVERY available layer "
      f"(no via can rescue): {no_layer}/{len(t3)}")

# budget accounting
iters = [i for c in t3 for i in (c.get("iters") or [])]
caps = [c.get("max_iter") for c in t3]
print(f"\niterations per call: n={len(iters)} "
      f"min={min(iters) if iters else '-'} max={max(iters) if iters else '-'} "
      f"total={sum(iters):,}")
at_cap = sum(1 for c in t3 for i in (c.get("iters") or [])
             if c.get("max_iter") and i > c["max_iter"])
print(f"calls that exhausted their iteration budget: {at_cap}")
print(f"max_iter values in play: {Counter(caps).most_common(6)}")
print(f"calls returning <20ms: {sum(1 for c in t3 if c['ms'] < 20)}")
OUT["q4"] = {
    "calls": len(t3), "hits": hits, "wall_s": round(tot_ms / 1000, 2),
    "route_wall_s": T["wall_s"],
    "terminal_state": dict(end_state),
    "goal_blocked_calls": unreachable,
    "goal_blocked_wall_s": round(ms_unreach / 1000, 2),
    "goal_blocked_every_layer": no_layer,
    "budget_exhausted_calls": at_cap,
    "total_iterations": sum(iters),
    "oob_calls": oob,
}

# --------------------------------------------------- coarse-to-fine (bonus)
kc = T.get("kernel_calls")
if kc:
    rule("6. COARSE-TO-FINE: DOES THE PRE-PASS EARN ITS DOWNSAMPLE + COARSE A*?")
    by = defaultdict(list)
    for net, it, mx, plen, idx in kc:
        by[idx].append((net, it, mx, plen))
    print(f"kernel calls per _segment_search: "
          f"{dict(Counter(len(v) for v in by.values()))}")
    coarse, dec, decZC = Counter(), Counter(), Counter()
    for i, c in enumerate(T["seg_calls"]):
        g = by.get(i)
        if not g:
            continue
        _n, i0, _m0, p0 = g[0]
        coarse["corridor found" if p0 else
               ("endpoints rejected" if i0 == 1 else "searched and failed")] += 1
        _n, it, mx, pl = g[-1]
        free = (c["in_bounds"] and c["start_cell_val"] == 0
                and c["goal_cell_val"] == 0)
        out = ("found" if pl else
               "rejected@1iter" if it == 1 else
               "budget_exhausted" if (mx and it >= mx) else "frontier_exhausted")
        key = (out, "endpoints free" if free else "endpoint BLOCKED")
        dec[key] += 1
        if c["net"] in ZC:
            decZC[key] += 1
    print(f"\nphase 1, coarse on the 4x downsampled grid (n={sum(coarse.values())}):")
    for k, v in coarse.most_common():
        print(f"  {k:36s} {v:5d}")
    for label, cnt in (("all decisive searches", dec),
                       (f"decisive searches of the {len(ZC)} zero-copper", decZC)):
        print(f"\nphase 2, {label} (n={sum(cnt.values())}):")
        for k, v in sorted(cnt.items()):
            print(f"  {k[0]:20s} {k[1]:18s} {v:5d}")
        print(f"  -> only a LARGER BUDGET could change: "
              f"{cnt[('budget_exhausted', 'endpoints free')]}")
    OUT["coarse_to_fine"] = {"phase1": dict(coarse),
                             "phase2_all": {f"{a}|{b}": v for (a, b), v in dec.items()}}

if args.emit:
    args.emit.write_text(json.dumps(OUT, indent=1, default=str), encoding="utf-8")
    print(f"\n[emitted {args.emit}]")
