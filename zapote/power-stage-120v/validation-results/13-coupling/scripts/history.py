#!/usr/bin/env python3
"""Layer 5 input, what each accepted stage 19c -> $n actually changed and what moved.

    python3 -I validation-results/13-coupling/scripts/history.py      (after $assign)

For each consecutive pair of accepted stages ($chainlist):
* schematic: parts added / removed, MPN changed (frozen BOM), pin -> net changed (frozen netlist), all read with
  `git show TAG:...` (read-only);
* placement: parts whose pose moved (> 0.01 mm or any rotation; native-21/placement.json at the tag);
* copper: per net, routed copper (tracks + vias, rounded to 1 um) added or removed, and poured copper whose fill
  area moved by more than 1 % and 0.5 mm2 (the as-built all-copper dumps native-21/verification/<tag>-all-copper.json.gz);
* scorecard: every gate and performance metric that changed between the two stages' cards (10-benchmark).
Each changed item is mapped to groups (stage-$n rule applied to that stage's parts.json; a removed part takes its
group from the earlier stage). 'Intended' groups = groups with a schematic or placement change, plus the authored
copper the DECISIONS item names (AUTHORED, with the item number). Changed routed copper is placed in the territory of
the nearest stage-$n courtyard (as physical.py; 'open' beyond 6 mm); a territory with >= 2 changed items that is not
intended is 'ripple'. Via-size-only changes (stage 32's global resize) are counted apart. DOCUMENTED_RIPPLE lists the
cross-group effects the DECISIONS items describe in words (router re-lays, blocked routes, gate failures).$basisnote
Controls: stages that DECISIONS records as copper-unchanged (20, 26, 29, 31) show no routed-copper change; stage 31's
netlist nets are byte-identical to stage 30 (DECISIONS 34); stage 32's BOM equals stage 31's (DECISIONS 35). Later
stages: each commit's netlist parts are the parts with pads in that stage's copper dump, and the dump is the board the
stage's scorecard names; the BOM / parts changes are the ones the DECISIONS item records (44: J2 / J5 MPN only;
50: PS1 out, PS2 MPN; 52: C168 / D20 / R135 in, U44 MPN; 53: none, netlist identical; 55: R10 / R12 / R18 / R20 and
C55 / C56 / C62 / C63 MPN only; 57: C12 / C13 / C19 / C20 MPN only, nets identical).
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import stages as STG  # noqa: E402

COPPER_SAME = {"native21s20", "native21s26", "native21s29", "native21s31"}
# authored copper named by the DECISIONS item for each copper-changing stage: (item, groups, note)
AUTHORED = {
    "native21s21": (25, ["G01", "G02", "G03", "G08"], "BR1 window merged into the hv_ret (In1) / bus_p (In2) trunks; R5.4 via field"),
    "native21s21b": (26, ["G08"], "KELVIN_N under the KELVIN_P pour; C30 / C31 at U6"),
    "native21s22": (27, ["G05", "G07"], "NAND drive-disable; BIAS_BAD -> BIAS_GOOD copper renamed"),
    "native21s27": (29, ["G01"], "mains pours redrawn round the new J1"),
    "native21s28": (30, ["G10"], "F2 / R130 limiter (the OCP routing lock that followed is a response to ripple, below)"),
    "native21s30": (33, ["G07", "G09"], "heartbeat block, HSB_GOOD In2 leg, BUS_FAULT RC"),
    "native21s32": (35, ["G07", "G08", "G09"], "three SELV hops to In2 (HSB_GOOD, BUS_FAULT_ISO, BIAS_GOOD); the via resize is global"),
    "native21s35": (44, ["G04"], "J2 / J5 SMT ring lands and 20 land vias per terminal (patches21.add_stage35); nothing else moves"),
    "native21s38": (50, ["G01", "G10"], "PS1 area cleared; L_FILT re-laid to F2 and N_FILT's J11 via re-made 0.85 / 0.3 (l_filt / "
                    "n_filt are G01 / G10 nets); spine lock re-issued by the selv lane (J4.1 net, v15_selv antipads)"),
    "native21s40": (52, ["G06", "G07", "G10"], "U44 in U42's pocket, D18 / D20 vote beside U43, GOOD node in MON_GOOD_HA's corridor "
                    "lane (G07); C161 via into In1 n_ls, F n_ls pour over an In1 n_ls patch, U41 heat-spread pours to x 46.35 "
                    "(G06); C168 (G10)"),
    "native21s41": (53, ["G02", "G03", "G08"], "hv_ret spreader at R5.4, leg_ret pours at R5.1 / Q3.1 / Q6.3, In1 leg-A neck, two "
                    "R5.4 hv_ret vias moved, sw_b B.Cu lane over R5 (patches21.edit_base41)"),
    "native21s42": (55, ["G05"], "gate runs re-laid (patches21.edit_base42), pull-downs moved, R11 turned with its sw_a via, R10's "
                    "sw_a stub via removed"),
    "native21s43": (57, list(C.GIDS), "DECISIONS 48 cleanup pass on every island by design (621 edits on 100 nets); snubber MPN "
                    "C12 / C13 / C19 / C20"),
}
# ripple the DECISIONS items record in words: (stage, from groups, to groups, mechanism, item)
DOCUMENTED_RIPPLE = [
    ("native21s22", ["G05"], ["G10"], "router: with Q4 gone pwm_lb took pwm_hb's via spot (35.2, 125.0); pwm_hb vias reserved", 27),
    ("native21s22", ["G05", "G07"], ["G08"], "router re-laid ocp_thresh all on F.Cu; OCP pickup 4.78 -> 4.17 A", 27),
    ("native21s27", ["G01"], ["G05"], "settle loop trimmed a dead leg_b-permit_gate In2 branch over 7 rebuilds", 29),
    ("native21s28", ["G10"], ["G08"], "first chain re-routed ocp_node / ocp_thresh; pickup 4.17 -> 4.78 A, card REJECT; OCP lock", 30),
    ("native21s30", ["G07"], ["G06"], "HS-B -> LS link blocked by U42's n_ls pocket (y 47-60); C161 bypass exception (no legal pose)", 33),
    ("native21s30", ["G07"], ["G02", "G03"], "HS-B -> LS link blocked by the protected In2 bus_p trunk (y <= 51)", 33),
    ("native21s30", ["G07"], ["G05", "G10"], "HSB_GOOD pocket closed by the permit / PWM / bias_good bundle on F and B", 33),
    ("native21s32", ["G08", "G09", "G07"], ["G05", "G10"], "7 open return-path changes need the PWM bundle re-routed to reach C47 / C144 / C153", 35),
    ("native21s40", ["G07"], ["G05"], "the HS-B verdict change took the SELV decoupler that served pwm_hb's via at (34.4, 110.6): the "
     "change measured 16.5 mm and failed the asserted return_path19 limit; C168 added", 52),
    ("native21s42", ["G05"], ["G03"], "first build: R11's sw_a via at (59.4, 9.7) cut the leg-A In1 fuse neck to 2.42 mm (ratio 0.882); "
     "and the network's own +0.68 W cost the FET-row laminate 7.8 K at c28 (card REJECT, overridden)", 55),
] # stage 32's first chain also failed task 04 on the mains nets' resized vias (4 kept at 0.85): a board-wide via policy
  # meeting G01, not a group-to-group ripple, so it is recorded in GLOBAL_EVENTS instead
GLOBAL_EVENTS = [("native21s32", ["G01"], "global via resize 0.85 -> 0.6 failed task 04's topology check on ac_n_in / l_filt / n_filt; 4 vias kept", 35),
                 ("native21s43", list(C.GIDS), "cleanup pass: every island edited by design, so the stage has no outside group", 57)]
# scorecard moves that DECISIONS attributes to a model / basis change rather than to the stage's board: (stage, metric, why, item)
BASIS_CHANGES = [
    ("native21s38", "b3_laminate_margin_K", "B3 ratings model corrected (FET lead path, 60 kHz heat file); s38 re-scored on it, s35 not", 51),
    ("native21s38", "b3_rated_part_margin_K", "B3 ratings model corrected; film caps and gate resistors gated (more rows)", 51),
    ("native21s40", "b3_c28_h25_peak_C", "first chain on the corrected c28 heat file (60 kHz, deck gate charge) in the shared model key", 51),
    ("native21s40", "b3_nominal_h10_peak_C", "first chain after the heat-file / model-key change", 51),
]
# per-stage parts / BOM checks for the later stages (DECISIONS items): stage -> (added, removed, mpn changed, nets identical)
EXPECT = {
    "native21s35": ([], [], ["J2", "J5"], None),
    "native21s38": ([], ["PS1"], ["PS2"], None),
    "native21s40": (["C168", "D20", "R135"], [], ["U44"], None),
    "native21s41": ([], [], [], True),
    "native21s42": ([], [], ["C55", "C56", "C62", "C63", "R10", "R12", "R18", "R20"], None),
    "native21s43": ([], [], ["C12", "C13", "C19", "C20"], True),
}


def card(tag):
    p = C.VR / f"10-benchmark/scorecard-{tag}.json"
    return json.loads(p.read_text()) if p.exists() else None


def pin_map(nets):
    out = {}
    for n, nodes in nets.items():
        for r, pin in nodes:
            out[(r, pin)] = n
    return out


def copper_sig(tag):
    d = json.load(gzip.open(C.N21 / f"verification/{tag}-all-copper.json.gz"))
    pad_refs = {x["ref"].split(".")[0] for x in d["primitives"] if x["kind"] == "pad"}
    routed = defaultdict(set)
    zarea = defaultdict(float)
    sg, so = C.shapely()
    for x in d["primitives"]:
        n = x.get("net")
        if not n:
            continue
        if x["kind"] == "track":
            a, b = sorted([tuple(round(v, 3) for v in x["start"]), tuple(round(v, 3) for v in x["end"])])
            routed[n].add(("t", x["layer"], a, b, round(x["width_mm"], 3)))
        elif x["kind"] == "via" and x["layer"] == "F.Cu":
            routed[n].add(("v", tuple(round(v, 3) for v in x["centre"]), round(x["diameter_mm"], 3), round(x["drill_mm"], 3)))
        elif x["kind"] == "zone":
            zarea[(n, x["layer"])] += sg.Polygon(x["shell"], x.get("holes") or []).area
    return d["board_sha256"], routed, zarea, pad_refs


def main():
    C.init()
    chain = STG.chain_upto(C.TAG)
    TAGS = [t for t, _ in chain]
    REF = dict(chain)
    old = [t for t, r in chain if t == r]
    new = [f"{STG.short(t)} {r}" for t, r in chain if t != r]
    C.FMT["chainlist"] = "tags " + ", ".join([old[0]] + [STG.short(t) for t in old[1:]]) + (
        "; then the commits " + ", ".join(new) if new else "")
    stages_in = set(TAGS)
    C.FMT["basisnote"] = ("\nBASIS_CHANGES lists scorecard moves that DECISIONS attributes to a model or basis change, not to the "
                          "board;\nthe metric check leaves them out." if any(a in stages_in for a, *_ in BASIS_CHANGES) else "")
    ctl = C.Controls()
    import numpy as np
    asg32 = C.load("assignment.json")["assignment"]
    cy = C.courtyards()
    refs = sorted(r for r in asg32 if r in cy)
    box = np.array([cy[r] for r in refs])

    def territory(xy):
        """group of the nearest courtyard of the audited stage (edge gap); 'open' beyond 6 mm (as physical.py)."""
        dx = np.maximum.reduce([box[:, 0] - xy[0], xy[0] - box[:, 2], np.zeros(len(box))])
        dy = np.maximum.reduce([box[:, 1] - xy[1], xy[1] - box[:, 3], np.zeros(len(box))])
        dd = np.hypot(dx, dy)
        k = int(np.argmin(dd))
        return asg32[refs[k]] if dd[k] <= 6.0 else "open"
    rows = []
    prev = None
    for tag in TAGS:
        comps, nets = C.netlist(REF[tag])
        bom = C.bom(REF[tag])
        prt = C.parts(REF[tag])
        plc = C.placement(REF[tag])
        asg = {}
        for p in prt:
            g, _ = C.assign_stage(p["path"], p["group"])
            asg[p["ref"]] = g
        path_ref = {p["path"]: p["ref"] for p in prt}
        sha, routed, zarea, pad_refs = copper_sig(tag)
        if tag != REF[tag]:                 # a later stage read from a commit, not a tag: check the commit is that board
            cd = card(tag)
            ctl.check(f"{tag}: commit {REF[tag]} netlist parts == the parts with pads in its copper dump (less the board-only test "
                      f"points / fiducials); dump is the card's board",
                      set(comps) == {r for r in pad_refs if not r.startswith(("TP", "FID", "MH", "H"))}
                      and cd is not None and cd["board_sha256"] == sha,
                      f"{len(comps)} parts (+{len(pad_refs) - len(comps)} board-only TP / FID), board {sha[:8]}")
        cur = {"tag": tag, "comps": comps, "nets": nets, "bom": bom, "asg": asg, "plc": plc, "path_ref": path_ref,
               "sha": sha, "routed": routed, "zarea": zarea, "card": card(tag)}
        if prev:
            A, B = prev, cur
            gmap = dict(A["asg"])
            gmap.update(B["asg"])
            added = sorted(set(B["comps"]) - set(A["comps"]))
            removed = sorted(set(A["comps"]) - set(B["comps"]))
            mpn = sorted(r for r in set(A["comps"]) & set(B["comps"]) if A["bom"].get(r) != B["bom"].get(r))
            pa, pb = pin_map(A["nets"]), pin_map(B["nets"])
            renamed_nets = {}
            for k in set(pa) & set(pb):
                if pa[k] != pb[k]:
                    renamed_nets.setdefault(pa[k], set()).add(pb[k])
            pin_changed = sorted({k[0] for k in set(pa) ^ set(pb)} | {k[0] for k in set(pa) & set(pb) if pa[k] != pb[k]})
            pin_changed = [r for r in pin_changed if r not in added and r not in removed]
            moved = []
            for path, pose in B["plc"].items():
                if path in A["plc"]:
                    q = A["plc"][path]
                    if abs(q[0] - pose[0]) > 0.01 or abs(q[1] - pose[1]) > 0.01 or abs((q[2] - pose[2]) % 360) > 0.01:
                        r = B["path_ref"].get(path)
                        if r:
                            moved.append(r)
            moved = sorted(moved)
            # copper by net
            netg = defaultdict(set)
            for st in (A, B):
                for n, nodes in st["nets"].items():
                    for r, _ in nodes:
                        if r in gmap and gmap[r]:
                            netg[n].add(gmap[r])
            cu_changed = {}
            terr_items = defaultdict(int)
            resized = 0
            for n in sorted(set(A["routed"]) | set(B["routed"])):
                a, b = A["routed"].get(n, set()), B["routed"].get(n, set())
                if a != b:
                    va = {i[1]: i for i in a - b if i[0] == "v"}
                    vb = {i[1]: i for i in b - a if i[0] == "v"}
                    rs = set(va) & set(vb)              # same centre, new size: the stage-32 via resize
                    resized += len(rs)
                    items = [i for i in (a - b) | (b - a) if not (i[0] == "v" and i[1] in rs)]
                    if not items and rs:
                        cu_changed[n] = {"added": 0, "removed": 0, "resized_vias": len(rs), "groups": sorted(netg.get(n, []))}
                        continue
                    cu_changed[n] = {"added": len(b - a) - len(rs), "removed": len(a - b) - len(rs), "resized_vias": len(rs),
                                     "groups": sorted(netg.get(n, []))}
                    for i in items:
                        xy = i[1] if i[0] == "v" else ((i[2][0] + i[3][0]) / 2, (i[2][1] + i[3][1]) / 2)
                        terr_items[territory(xy)] += 1
            pour_changed = {}
            for k in sorted(set(A["zarea"]) | set(B["zarea"])):
                a, b = A["zarea"].get(k, 0.0), B["zarea"].get(k, 0.0)
                if abs(a - b) > 0.5 and abs(a - b) > 0.01 * max(a, b):
                    pour_changed[f"{k[0]}|{k[1]}"] = {"mm2_before": round(a, 2), "mm2_after": round(b, 2), "groups": sorted(netg.get(k[0], []))}
            sch_groups = sorted({gmap[r] for r in added + removed + mpn + pin_changed if gmap.get(r)})
            plc_groups = sorted({gmap[r] for r in moved if gmap.get(r)})
            auth = AUTHORED.get(tag)
            auth_groups = sorted(auth[1]) if auth else []
            intended = sorted(set(sch_groups) | set(plc_groups) | set(auth_groups))
            cu_groups = sorted({g for v in cu_changed.values() for g in v["groups"]})
            terr_groups = sorted(g for g, k in terr_items.items() if g != "open" and k >= 2)
            ripple_routed = sorted(set(terr_groups) - set(intended))
            pour_groups = sorted({g for v in pour_changed.values() for g in v["groups"]})
            # scorecard deltas
            ca, cb = A["card"], B["card"]
            moved_m, moved_g, new_m = {}, {}, []
            if ca and cb:
                for k, v in cb["performance"].items():
                    if k not in ca["performance"]:
                        new_m.append(k)
                    elif ca["performance"][k] != v:
                        moved_m[k] = [ca["performance"][k], v]
                for k, v in cb["gates"].items():
                    if k in ca["gates"] and ca["gates"][k] != v:
                        moved_g[k] = [ca["gates"][k], v]
            row = {"from": A["tag"], "to": B["tag"], "board_from": A["sha"], "board_to": B["sha"],
                   "decisions_item": auth[0] if auth else None, "authored_note": auth[2] if auth else None,
                   "added": added, "removed": removed, "mpn_changed": mpn, "pin_changed": pin_changed,
                   "renamed_nets": {k: sorted(v) for k, v in renamed_nets.items()},
                   "moved": moved, "schematic_groups": sch_groups, "placement_groups": plc_groups,
                   "authored_groups": auth_groups, "intended_groups": intended,
                   "routed_copper_changed_nets": cu_changed, "routed_copper_net_groups": cu_groups, "resized_vias": resized,
                   "changed_items_by_territory": dict(sorted(terr_items.items())), "routed_copper_territories": terr_groups,
                   "ripple_groups_routed": ripple_routed, "pour_fill_changed": pour_changed, "pour_fill_groups": pour_groups,
                   "metrics_moved": moved_m, "gates_changed": moved_g, "metrics_new": new_m}
            rows.append(row)
            print(f"{A['tag'][8:]}->{B['tag'][8:]}: intended {intended} | changed copper in territories {dict(sorted(terr_items.items()))} | ripple {ripple_routed} | "
                  f"nets {len(cu_changed)} | pours {len(pour_changed)} | metrics moved {sorted(moved_m)}")
            if B["tag"] in COPPER_SAME:
                ctl.check(f"{B['tag']}: routed copper unchanged (DECISIONS: BOM only)", not cu_changed, f"{len(cu_changed)} nets changed")
            if B["tag"] == "native21s31":
                ctl.check("native21s31: netlist nets identical to s30 (DECISIONS 34)", A["nets"] == B["nets"])
            if B["tag"] == "native21s32":
                ctl.check("native21s32: BOM identical to s31 (DECISIONS 35)", A["bom"] == B["bom"])
            if B["tag"] in EXPECT:
                ea, er, em, same_nets = EXPECT[B["tag"]]
                ok = added == ea and removed == er and mpn == em and (not same_nets or A["nets"] == B["nets"])
                ctl.check(f"{B['tag']}: parts / BOM changes are the DECISIONS item's (+{ea} -{er} MPN {em}"
                          + (", nets identical" if same_nets else "") + ")", ok, f"+{added} -{removed} MPN {mpn}")
            bc = {m: w for s_, m, w, _ in BASIS_CHANGES if s_ == B["tag"]}
            if bc:
                row["metrics_moved_basis_change"] = {m: w for m, w in bc.items() if m in moved_m}
        prev = cur
    out = {"method": C.method(__doc__), "tags": TAGS, "stages": rows,
           "documented_ripple": [{"stage": a, "from": b, "to": c, "mechanism": d_, "decisions_item": e} for a, b, c, d_, e in DOCUMENTED_RIPPLE
                                 if a in stages_in],
           "global_events": [{"stage": a, "groups": b, "mechanism": c_, "decisions_item": e} for a, b, c_, e in GLOBAL_EVENTS
                             if a in stages_in],
           "controls": ctl.rows}
    if any(t != r for t, r in chain):
        out["refs"] = {t: r for t, r in chain}
        out["not_adopted"] = STG.NOT_ADOPTED
        out["basis_changes"] = [{"stage": a, "metric": b, "why": c_, "decisions_item": e} for a, b, c_, e in BASIS_CHANGES if a in stages_in]
    h = C.write("history.json", out)
    print("history.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
