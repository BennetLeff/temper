#!/usr/bin/env python3
"""Decompose one instrumented production route into the mechanism-A table.

Consumes the trace JSON and routed board written by
``2026-08-19-mechanism-a-instrument-route.py`` and reproduces every table
in ``2026-08-19-mechanism-a-zero-copper-63-nets.md``:

  1. run envelope + proof of which A* implementation ran
  2. the 63 zero-copper/zero-zone nets and their ratsnest edge count
  3. the decline / fail / succeed-then-discard partition
  4. tier anatomy of each declining hop
  5. own-pad reachability across _unblock_net_pads ->
     _stamp_foreign_creepage_halos
  6. coarse-to-fine phase accounting and the budget-vs-geometry split
  7. the board-wide pad-pair creepage census on the COMMITTED placement

Read-only. Never writes to pcb/temper.kicad_pcb.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--trace", required=True, type=Path)
ap.add_argument("--board", required=True, type=Path)
ap.add_argument("--repo", required=True, type=Path)
args = ap.parse_args()

T = json.loads(args.trace.read_text())
S = T["run_summaries"][-1]
rs = T["route_summary"]


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ------------------------------------------------------------------ 1
rule("1. RUN ENVELOPE")
print(f"wall={T['wall_s']}s  segments={rs['segments']} vias={rs['vias']} "
      f"zones={rs['zones']}")
print(f"run_astar_pathfinding_nlayer entered : {T['nlayer_entered']}")
print(f"_astar_reconstruct.run_astar_pathfinding entered: {T['legacy_entered']}")
print(f"grids handed to A*: {S['grids']}")
print(f"channel_paths={S['n_channel_paths']} net_order={S['n_net_order']} "
      f"routable={len(S['routable_nets'])} "
      f"excluded_by_should_route={len(S['excluded_by_should_route'])}")
print(f"routed_paths={len(S['routed_paths'])} failed={len(S['failed_nets'])} "
      f"partial_paths={len(S['partial_paths'])}")
print(f"tier_tally={S['tier_tally']}")
print(f"failure reasons={Counter(S['failure_reasons'].values())}")

# ------------------------------------------------------------------ 2
import sys  # noqa: E402

sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
from temper_placer.core.pin_geometry import pin_world_position  # noqa: E402
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6  # noqa: E402
from temper_placer.io.netclass_loader import load_netclass_rules  # noqa: E402
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file  # noqa: E402
from temper_placer.router_v6.pair_creepage import (  # noqa: E402
    default_creepage_table,
    net_class_of,
)

audit = audit_pcb_file(args.board)
multi = {n: r for n, r in audit.items() if r.pad_count >= 2}
zero = {n: r for n, r in multi.items() if not r.has_any_copper}
A63 = {n: r for n, r in zero.items() if not r.zone_layers}
edges = sum(r.pad_count - 1 for r in A63.values())

rule("2. THE UNIVERSE AND THE 63")
print(f"nets with >=2 pads                 : {len(multi)}")
print(f"  carrying segment/via copper      : "
      f"{sum(1 for r in multi.values() if r.has_any_copper)}")
print(f"  fully pad-connected              : "
      f"{sum(1 for r in multi.values() if r.fully_connected)}")
print(f"  ZERO segment/via copper          : {len(zero)}")
print(f"  ZERO copper AND ZERO zone (= A)  : {len(A63)}  ->  {edges} ratsnest edges")
print(f"zero-copper but zoned (outside A)  : {sorted(set(zero) - set(A63))}")

# ------------------------------------------------------------------ 3
routable = set(S["routable_nets"])
routed_ok = set(S["routed_paths"])
reasons = S["failure_reasons"]
wpc = S["waypoint_counts"]
rules_by_net = S.get("net_rules", {})


def rec_of(n):
    r = T["nets"].get(n) or []
    return r[-1] if r else None


MECH = {}
for n in multi:
    rec = rec_of(n)
    if n not in wpc:
        MECH[n] = "no_channel_path"
    elif n not in routable:
        MECH[n] = "declined_by_should_route"
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

rule("3. MECHANISM PARTITION")
print("all nets with >=2 pads:")
for k, v in sorted(Counter(MECH.values()).items()):
    print(f"  {k:42s} {v:4d}")
print(f"\nthe {len(A63)} mechanism-A nets:")
for k in sorted({MECH[n] for n in A63}):
    ns = [n for n in A63 if MECH[n] == k]
    print(f"  {k:42s} nets={len(ns):4d} "
          f"edges={sum(A63[n].pad_count - 1 for n in ns):4d}")
print(f"\nnetclass census: "
      f"{dict(Counter(rules_by_net.get(n, {}).get('class', '?') for n in A63))}")
print(f"pad-count census: {dict(sorted(Counter(A63[n].pad_count for n in A63).items()))}")

print("\ndiscarded geometry (A* solved these hops, the board has none of it):")
tot_pts = tot_hops = 0
for n in sorted(multi):
    if not MECH[n].startswith("DISCARD"):
        continue
    r = rec_of(n)
    rp = r["route_path"]
    hops = len(r["tier_log"]) - (1 if r["tier_log"][-1] == "declined" else 0)
    tot_pts += rp["n_segments_emitted"]
    tot_hops += hops
    print(f"  {n:40s} {','.join(r['tier_log']):46s} "
          f"pts={rp['n_segments_emitted']:5d} vias={rp['n_vias']} "
          f"len={rp['path_length']:7.1f}mm hops_solved={hops}")
print(f"  TOTAL {tot_pts} path points over {tot_hops} already-solved hops")

# ------------------------------------------------------------------ 4
calls = defaultdict(list)
for c in T["seg_calls"]:
    calls[c["net"]].append(c)


def groups_for(n):
    out, cur, key = [], [], None
    for c in calls[n]:
        k = (tuple(c["start"]), tuple(c["goal"]))
        if k != key:
            if cur:
                out.append(cur)
            cur, key = [], k
        cur.append(c)
    if cur:
        out.append(cur)
    return out


def cls(c):
    if c["hit"]:
        return "hit"
    if not c["in_bounds"]:
        return "oob"
    s_bad, g_bad = c["start_cell_val"] != 0, c["goal_cell_val"] != 0
    return ("both_endpoints_blocked" if s_bad and g_bad else
            "goal_blocked" if g_bad else
            "start_blocked" if s_bad else "endpoints_free_search_failed")


declined = [n for n in MECH if MECH[n].startswith(("FAIL_", "DISCARD_partial"))]
rule("4. TIER ANATOMY OF THE DECLINING HOP")
t1, t2 = Counter(), Counter()
for n in declined:
    tl = rec_of(n)["tier_log"]
    g = groups_for(n)
    if len(g) != len(tl):
        t1["grouping_mismatch"] += 1
        continue
    grp = g[len(tl) - 1]
    t1[cls(grp[0])] += 1
    alts = [cls(c) for c in grp[1:]]
    t2["some_alt_layer_had_free_endpoints"
       if any(a == "endpoints_free_search_failed" for a in alts)
       else "no_alt_layer_had_free_endpoints"] += 1
print(f"Tier 1 (preferred layer, own width-family grid), n={sum(t1.values())}")
for k, v in t1.most_common():
    print(f"  {k:36s} {v:4d}")
print(f"Tier 2 (every other layer), n={sum(t2.values())}")
for k, v in t2.most_common():
    print(f"  {k:40s} {v:4d}")
t3 = T["t3_calls"]
print(f"Tier 3: {len(t3)} calls, {sum(c['hit'] for c in t3)} hits, "
      f"{sum(c['ms'] for c in t3)/1000:.1f}s, "
      f"{sum(1 for c in t3 if c['ms'] < 20)} rejected in <20ms")

# ------------------------------------------------------------------ 5
unb = T.get("pad_cells_after_unblock", {})
stm = T.get("pad_cells_after_stamp", {})
if unb and stm:
    rule("5. OWN-PAD REACHABILITY: unblock -> foreign-creepage-halo restamp")
    allb, ownb = Counter(), Counter()
    per_net = {}
    # `declined` drives the two census tables; the per-net verdict also needs
    # the landing-blocked net, which is in A but not in `declined`.
    for n in sorted(set(declined) | set(A63)):
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
            if n in declined:
                allb[k] += 1
            if own:
                if n in declined:
                    ownb[k] += 1
                # The per-net verdict counts ONLY the pad's own layer: that
                # is the single layer the pad physically has copper on, so a
                # blocked cell on any other layer says nothing about whether
                # the pad is reachable.
                nb[k] += 1
        per_net[n] = nb
    for label, cnt in (("ALL (pad, layer) cells", allb),
                       ("restricted to the pad's OWN layer", ownb)):
        tot = sum(cnt.values())
        print(f"\n{label}  n={tot}")
        for k, v in cnt.most_common():
            print(f"  {k:48s} {v:5d} ({v/tot*100:4.1f}%)")
    verdict = Counter()
    for n in A63:
        nb = per_net.get(n, Counter())
        if nb["FREED_then_BLOCKED_by_foreign_creepage_halo"]:
            verdict["own pad inside a FOREIGN CREEPAGE HALO"] += 1
        elif nb["claimed_by_an_already_ROUTED_net"]:
            verdict["own pad under an already-routed net's stamp"] += 1
        elif nb["still_static_blocked_after_unblock"]:
            verdict["own pad still statically blocked"] += 1
        else:
            verdict["A* frontier/budget: no path at this width"] += 1
    print(f"\nper-net headline verdict over the {len(A63)}:")
    for k, v in verdict.most_common():
        print(f"  {k:48s} {v:4d}")

# ------------------------------------------------------------------ 6
kc = T.get("kernel_calls")
if kc:
    rule("6. COARSE-TO-FINE PHASES AND THE BUDGET-VS-GEOMETRY SPLIT")
    by = defaultdict(list)
    for net, iters, mx, plen, idx in kc:
        by[idx].append((net, iters, mx, plen))
    print(f"kernel calls per _segment_search: "
          f"{dict(Counter(len(v) for v in by.values()))}")
    coarse, dec, dec63 = Counter(), Counter(), Counter()
    for i, c in enumerate(T["seg_calls"]):
        g = by.get(i)
        if not g:
            continue
        _n, i0, m0, p0 = g[0]
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
        if c["net"] in A63:
            dec63[key] += 1
    print(f"\nphase 1, coarse on the 4x downsampled grid (n={sum(coarse.values())}):")
    for k, v in coarse.most_common():
        print(f"  {k:36s} {v:5d}")
    for label, cnt in (("all decisive searches", dec),
                       (f"decisive searches of the {len(A63)}", dec63)):
        print(f"\nphase 2, {label} (n={sum(cnt.values())}):")
        for k, v in sorted(cnt.items()):
            print(f"  {k[0]:20s} {k[1]:18s} {v:5d}")
        print(f"  -> only a LARGER BUDGET could change: "
              f"{cnt[('budget_exhausted', 'endpoints free')]}")

# ------------------------------------------------------------------ 7
rule("7. PAD-PAIR CREEPAGE CENSUS ON THE COMMITTED PLACEMENT")
DR = load_netclass_rules(
    args.repo / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
).design_rules
tbl = default_creepage_table()
pcb = parse_kicad_pcb_v6(args.repo / "pcb" / "temper.kicad_pcb")
pads = [(pin.net, *pin_world_position(pin, comp))
        for comp in pcb.components for pin in comp.pins if pin.net]
cl = {n: net_class_of(n, DR) for n, _, _ in pads}
viol, nets_v, pairs = Counter(), set(), 0
for i in range(len(pads)):
    n1, x1, y1 = pads[i]
    for j in range(i + 1, len(pads)):
        n2, x2, y2 = pads[j]
        if n1 == n2:
            continue
        req = tbl.required(cl[n1], cl[n2])
        if req <= 0:
            continue
        if ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 < req:
            pairs += 1
            viol[tuple(sorted((cl[n1], cl[n2])))] += 1
            nets_v |= {n1, n2}
print(f"{len(pads)} netted pads; {pairs} pad pairs closer centre-to-centre than "
      f"their required creepage, over {len(nets_v)} nets")
print(f"of the {len(A63)} mechanism-A nets, {len(set(A63) & nets_v)} are involved")
for k, v in viol.most_common():
    print(f"  {k[0]:22s} <-> {k[1]:22s} {v:4d}")

# closest offender per watched net, at the radius the router actually stamps:
#   family static inflation (w/2 + max(clearance, 0.2)) + pair creepage
print("\nclosest foreign obstacle to a few unreachable pads, at the REAL "
      "stamped halo radius:")
for w in ("tank-out", "sclk", "input", "discharge.k_dis1-no",
          "discharge.r_snub2-p2", "safety.ovp.r_div_top2-p2"):
    r = DR.get_rules_for_net(w)
    infl = r.trace_width_mm / 2.0 + max(r.clearance_mm, 0.2)
    cw = cl.get(w)
    for net, x, y in [p for p in pads if p[0] == w]:
        hits = []
        for on, ox, oy in pads:
            if on == w:
                continue
            req = tbl.required(cw, cl[on])
            if req <= 0:
                continue
            d = ((ox - x) ** 2 + (oy - y) ** 2) ** 0.5
            if d < infl + req:
                hits.append((round(d, 2), on, cl[on], round(infl + req, 2)))
        hits.sort()
        print(f"  {w:26s} pad ({x:7.2f},{y:7.2f}) class={cw:18s} "
              f"{len(hits)} inside halo; closest: {hits[:2]}")
