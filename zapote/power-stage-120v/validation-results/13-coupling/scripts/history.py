#!/usr/bin/env python3
"""Layer 5 input, what each accepted stage 19c -> 32 actually changed and what moved.

    python3 -I validation-results/13-coupling/scripts/history.py      (after assign32.py)

For each consecutive pair of accepted stages (tags native21s19c, s20, s21, s21b, s22, s26, s27, s28, s29, s30, s31, s32):
* schematic: parts added / removed, MPN changed (frozen BOM), pin -> net changed (frozen netlist), all read with
  `git show TAG:...` (read-only);
* placement: parts whose pose moved (> 0.01 mm or any rotation; native-21/placement.json at the tag);
* copper: per net, routed copper (tracks + vias, rounded to 1 um) added or removed, and poured copper whose fill
  area moved by more than 1 % and 0.5 mm2 (the as-built all-copper dumps native-21/verification/<tag>-all-copper.json.gz);
* scorecard: every gate and performance metric that changed between the two stages' cards (10-benchmark).
Each changed item is mapped to groups (stage-32 rule applied to that stage's parts.json; a removed part takes its
group from the earlier stage). 'Intended' groups = groups with a schematic or placement change, plus the authored
copper the DECISIONS item names (AUTHORED, with the item number). Changed routed copper is placed in the territory of
the nearest stage-32 courtyard (as physical.py; 'open' beyond 6 mm); a territory with >= 2 changed items that is not
intended is 'ripple'. Via-size-only changes (stage 32's global resize) are counted apart. DOCUMENTED_RIPPLE lists the
cross-group effects the DECISIONS items describe in words (router re-lays, blocked routes, gate failures).
Controls: stages that DECISIONS records as copper-unchanged (20, 26, 29, 31) show no routed-copper change; stage 31's
netlist nets are byte-identical to stage 30 (DECISIONS 34); stage 32's BOM equals stage 31's (DECISIONS 35).
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

TAGS = ["native21s19c", "native21s20", "native21s21", "native21s21b", "native21s22", "native21s26", "native21s27",
        "native21s28", "native21s29", "native21s30", "native21s31", "native21s32"]
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
] # stage 32's first chain also failed task 04 on the mains nets' resized vias (4 kept at 0.85): a board-wide via policy
  # meeting G01, not a group-to-group ripple, so it is recorded in GLOBAL_EVENTS instead
GLOBAL_EVENTS = [("native21s32", ["G01"], "global via resize 0.85 -> 0.6 failed task 04's topology check on ac_n_in / l_filt / n_filt; 4 vias kept", 35)]


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
    return d["board_sha256"], routed, zarea


def main():
    ctl = C.Controls()
    import numpy as np
    asg32 = C.load("assignment.json")["assignment"]
    cy = C.courtyards()
    refs = sorted(r for r in asg32 if r in cy)
    box = np.array([cy[r] for r in refs])

    def territory(xy):
        """group of the nearest stage-32 courtyard (edge gap); 'open' beyond 6 mm (as physical.py)."""
        dx = np.maximum.reduce([box[:, 0] - xy[0], xy[0] - box[:, 2], np.zeros(len(box))])
        dy = np.maximum.reduce([box[:, 1] - xy[1], xy[1] - box[:, 3], np.zeros(len(box))])
        dd = np.hypot(dx, dy)
        k = int(np.argmin(dd))
        return asg32[refs[k]] if dd[k] <= 6.0 else "open"
    rows = []
    prev = None
    for tag in TAGS:
        comps, nets = C.netlist(tag)
        bom = C.bom(tag)
        prt = C.parts(tag)
        plc = C.placement(tag)
        asg = {}
        for p in prt:
            g, _ = C.assign_32(p["path"], p["group"])
            asg[p["ref"]] = g
        path_ref = {p["path"]: p["ref"] for p in prt}
        sha, routed, zarea = copper_sig(tag)
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
        prev = cur
    out = {"method": __doc__.split("Controls:")[0].strip(), "tags": TAGS, "stages": rows,
           "documented_ripple": [{"stage": a, "from": b, "to": c, "mechanism": d_, "decisions_item": e} for a, b, c, d_, e in DOCUMENTED_RIPPLE],
           "global_events": [{"stage": a, "groups": b, "mechanism": c_, "decisions_item": e} for a, b, c_, e in GLOBAL_EVENTS],
           "controls": ctl.rows}
    h = C.write("history.json", out)
    print("history.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
