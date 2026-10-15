#!/usr/bin/env python3
"""Return-path gate for the native-21 fast signals (stage 19, review SI1 / SI2).

    python3 native-21/layout/gates/return_path19.py COPPER_DUMP.json [--json OUT.json] [--control]

Reads a routed board's copper dump (`plot_copper.py --dump`: filled pours, tracks, vias, pads with their layers)
and, for every fast signal below:

* walks each track at 0.25 mm steps and finds its reference: the nearest adjacent copper layer that has a filled
  pour under the point (layers21.ADJ: nearest first by copper-centre distance in native-21/stackup.json; on today's
  F.Cu 0.4355 In1 0.5 In2 0.4355 B.Cu stack F -> In1 then In2, B -> In2 then In1, In2 -> B then In1, In1 -> F then In2). A track of an expected return net beside it on the same layer (edge gap <= 0.3 mm), or over /
  under it on the next copper layer(s) up to the first poured one (plan edge gap <= 0.5 mm), counts as a coupled
  dedicated return there (stage 18 had 18.7 mm between bus_fault_hot and its Kelvin return).
  Points within 0.6 mm of the signal's own pads / vias (antipads, launches) are skipped;
* lists each layer transition (a signal via, or a THT pad with tracks on two layers): the reference on each side
  (majority of the pour net on a ring 0.5 mm outside the via) and, where the reference changes, the distance
  from the via centre to the nearest populated two-pad capacitor joining the two reference nets (pad centre,
  straight line: the stage-18 review's metric), or, where the same net is the reference on two layers, to the
  nearest via of that net (stitching).

Targets (asserted, exit 1 on failure; DECISIONS item 19):
  SI1  bus_fault_hot: every sampled point is referenced to ocp_kelvin_p (its driver U8 and receiver U9 grounds),
       by the In1 Kelvin pour or by a coupled ocp_kelvin_p track; no point over n_ls (or any other net) without it,
       and no run longer than 1.5 mm over no copper at all (antipads and pour edges are allowed up to that).
  SI2  pwm_hb, ct_zc: the same against the SELV planes (v3v3 / selv_gnd). ct_zc: every v3v3 <-> selv_gnd change
       has a v3v3-selv_gnd capacitor within 3.0 mm of the via, at most 1 transition (stage 18: 1 at 37.15 mm).
       pwm_hb: every v3v3 <-> selv_gnd change within 3.0 mm (stage 19b; stage 19 asserted only the driver side,
       y < 126 mm), at most 7 transitions (stage 18: 7); the stage-19b transfer caps C153-C156 each reach both
       planes through a via within 1.6 mm of each pad.
The other fast signals are reported, not asserted.

--control: asserts the stage-18 review's findings reproduce instead: the bus_fault_hot In1 ocp_kelvin_p / n_ls
crossing near (119.0, 75.2) and the transfer-cap distances (+-0.1 mm). The defaults are the review's pwm_hb
54.39 / 37.45 / 21.24 mm and ct_zc 37.50 mm, measured on its board dadcaad3 (stage-18 routing with the N1 cap
moves, C47 beside U13); on the integration stage-18 board 3768a126 (caps still in the old row) the same vias give
48.51 / 28.50 / 1.02 and 37.15 mm: pass those with --expect pwm_hb=48.51,28.50,1.02 --expect ct_zc=37.15.
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layers21  # noqa: E402  (native-21/stackup.json)

LAYERS = list(layers21.CU)
# adjacent reference layers, nearest first by copper-centre distance (stage 33: from the stackup; it equals the former
# hand table F: In1 In2 B / In1: F In2 B / In2: B In1 F / B: In2 In1 F, test_layers21.py)
# (nearest first; a layer with no pour under the point is looked through to the next)
ADJ = layers21.ADJ
SELV_REF = {"v3v3", "selv_gnd"}
KELVIN = {"ocp_kelvin_p"}
LS_REF = {"n_ls", "hv_ret", "leg_ret"}   # the LS domain's return (ISO6721FB GND2 = n_ls) and the LOW planes it rides over
# net -> acceptable return nets (the driver / receiver supply and ground)
SIGNALS = {
    "bus_fault_hot": KELVIN, "ocp_ok_hot": KELVIN, "hot5_ok_hot": KELVIN, "ovp_ok_hot": KELVIN,
    "pwm_hb": SELV_REF, "ct_zc": SELV_REF, "pwm_ha": SELV_REF, "pwm_la": SELV_REF, "pwm_lb": SELV_REF,
    "permit": SELV_REF, "bus_fault_iso": SELV_REF, "bus_fault": SELV_REF, "bias_good": SELV_REF,
    "line_zc": SELV_REF,
    # stage 30 (DECISIONS 33): the three monitor lines and the OR output become the heartbeat line (U32 -> U46), HS-B's
    # SELV verdict (U44 -> U46) and the RC-filtered BUS_FAULT; HS-A's verdict crosses to the LS domain (ISO6721FB) and
    # runs the LS corridor to the vote
    "hb_rx": SELV_REF, "bus_fault_flt": SELV_REF, "hsb_good": SELV_REF,
    "mon_good_ha": LS_REF,
}
ASSERT_PLANE = {"bus_fault_hot", "pwm_hb", "ct_zc", "pwm_ha", "pwm_la", "pwm_lb"}
# transfer-cap distance asserted at every change of ct_zc and of every PWM input (stage 19b: C153-C156 beside
# pwm_hb's four J4-side changes; stage 19c: leg A's VCCI cap C7 under U1, as C14 under U2, for pwm_ha / pwm_la).
# These switch at 35-60 kHz with ns edges: repeating emitters. permit, bus_fault and the bias_*_bad lines are
# reported, not asserted: they change state only at start / stop or on a fault, and every disturbance can only
# disable the drivers (fail-safe); their runs over the plane void at the U32 isolation gap stay recorded
# (DECISIONS 19b, 19c; rubric review SI-08 / OTT-06 / BP-14).
ASSERT_TRANSFER = {n: (lambda at: True) for n in ("ct_zc", "pwm_hb", "pwm_ha", "pwm_la", "pwm_lb")}
TRANSFER_MM = 3.0
MAX_TRANSITIONS = {"pwm_hb": 7, "ct_zc": 1}
# stage 19b's dedicated transfer caps must reach both planes through their own vias
XFER_CAPS, XFER_VIA_MM = ("C153", "C154", "C155", "C156"), 1.6
STEP, SKIP, COPLANAR_GAP, BROADSIDE_GAP, MAX_GAP = 0.25, 0.6, 0.3, 0.5, 1.5
CONTROL_DIST = {"pwm_hb": [54.39, 37.45, 21.24], "ct_zc": [37.50]}
CONTROL_CROSS = (119.0, 75.2)


def load(path):
    d = json.load(open(path))
    zones = defaultdict(list)
    for z in d["zones"]:
        if len(z["pts"]) > 2:
            p = Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0)
            if not p.is_empty:
                zones[z["layer"]].append((p, z["net"]))
    ztree = {lay: (STRtree([p for p, _ in zs]), zs) for lay, zs in zones.items()}
    tracks = defaultdict(list)
    for t in d["tracks"]:
        tracks[t["layer"]].append(t)
    ttree = {lay: (STRtree([LineString([t["a"], t["b"]]).buffer(t["w"] / 2) if t["a"] != t["b"]
                            else Point(t["a"]).buffer(t["w"] / 2) for t in ts]), ts) for lay, ts in tracks.items()}
    return d, ztree, ttree


def pour_net(ztree, layer, pt):
    if layer not in ztree:
        return None
    tree, zs = ztree[layer]
    for i in tree.query(pt):
        p, net = zs[i]
        if p.contains(pt):
            return net
    return None


def reference(ztree, layer, pt):
    """(adjacent layer, pour net) of the nearest adjacent layer with a pour under pt, else (None, None)."""
    for lay in ADJ[layer]:
        n = pour_net(ztree, lay, pt)
        if n:
            return lay, n
    return None, None


def coupled(ttree, ztree, layer, pt, width, nets):
    """A dedicated return of an expected net beside the point: a track on the same layer with edge gap
    <= COPLANAR_GAP, or a track on the nearest copper layer(s) towards the first poured layer, with plan edge gap
    <= BROADSIDE_GAP (a layer with a pour under the point is the reference itself and ends the search)."""
    probes = [(layer, COPLANAR_GAP)]
    for lay in ADJ[layer]:
        probes.append((lay, BROADSIDE_GAP))
        if pour_net(ztree, lay, pt):
            break
    for lay, gap in probes:
        if lay not in ttree:
            continue
        tree, ts = ttree[lay]
        for i in tree.query(pt.buffer(width / 2 + gap + 0.01)):
            t = ts[i]
            if t["net"] in nets and tree.geometries[i].distance(pt) <= width / 2 + gap + 1e-6:
                return lay, t["net"]
    return None


def walk(d, ztree, ttree, net, expect):
    own = [Point(v["at"]) for v in d["vias"] if v["net"] == net]
    own += [Polygon(p["pts"]).centroid for p in d["pads"] if p["net"] == net]
    samples = []
    for t in d["tracks"]:
        if t["net"] != net:
            continue
        a, b = t["a"], t["b"]
        n = max(1, int(math.dist(a, b) / STEP))
        for k in range(n + 1):
            x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
            pt = Point(x, y)
            if any(pt.distance(o) < SKIP for o in own):
                continue
            lay, ref = reference(ztree, t["layer"], pt)
            cp = coupled(ttree, ztree, t["layer"], pt, t["w"], expect)
            samples.append({"at": [round(x, 3), round(y, 3)], "layer": t["layer"], "ref_layer": lay, "ref": ref,
                            "coupled": cp[1] if cp else None, "coupled_layer": cp[0] if cp else None,
                            "ok": (ref in expect) or cp is not None, "track": id(t)})
    return samples


def gap_runs(samples):
    """Runs of consecutive samples on one track with no reference at all (pour antipads / edges, voids)."""
    runs, cur = [], []
    for s in samples + [None]:
        if s is not None and not s["ok"] and s["ref"] is None and (not cur or (cur[-1]["track"] == s["track"]
                                                                              and math.dist(cur[-1]["at"], s["at"]) <= STEP + 0.01)):
            cur.append(s)
            continue
        if cur:
            runs.append({"at": cur[0]["at"], "layer": cur[0]["layer"], "ref": None,
                         "mm": round(STEP * (len(cur) - 1) + STEP, 2)})
        cur = [s] if (s is not None and not s["ok"] and s["ref"] is None) else []
    return runs


def crossings(samples):
    """Points along consecutive samples of one track run where the plane reference net changes."""
    out = []
    for s0, s1 in zip(samples, samples[1:]):
        if s0["layer"] == s1["layer"] and math.dist(s0["at"], s1["at"]) <= STEP + 0.01 and s0["ref"] != s1["ref"]:
            out.append({"at": s1["at"], "layer": s1["layer"], "from": s0["ref"], "to": s1["ref"],
                        "coupled": s1["coupled"]})
    return out


def caps_between(d, a, b):
    pads = defaultdict(list)
    for p in d["pads"]:
        if p["ref"].startswith("C"):
            pads[p["ref"]].append(p)
    out = []
    for ref, ps in pads.items():
        if len(ps) == 2 and {ps[0]["net"], ps[1]["net"]} == {a, b}:
            out += [(ref, Polygon(p["pts"]).centroid) for p in ps]
    return out


def transitions(d, ztree, net):
    out = []
    items = [("via", v["at"], v["d"] / 2) for v in d["vias"] if v["net"] == net]
    items += [("tht", [Polygon(p["pts"]).centroid.x, Polygon(p["pts"]).centroid.y],
               max(Polygon(p["pts"]).bounds[2] - Polygon(p["pts"]).bounds[0], 0.6) / 2, p["ref"])
              for p in d["pads"] if p["net"] == net and p.get("tht")]
    for it in items:
        kind, at, r = it[0], it[1], it[2]
        c = Point(at)
        lays = {t["layer"] for t in d["tracks"] if t["net"] == net and
                min(math.dist(t["a"], at), math.dist(t["b"], at)) <= r + 0.05}
        if kind == "via":   # a via in an SMD pad: the pad's layer is one side of the change
            lays |= {lay for p in d["pads"] if p["net"] == net and not p.get("tht") and Polygon(p["pts"]).buffer(0.01).contains(c)
                     for lay in p.get("layers", ["F.Cu"])}
        lays = sorted(lays, key=LAYERS.index)
        if len(lays) < 2:
            continue
        refs = {}
        for lay in lays:
            votes = Counter()
            for k in range(16):
                ang = 2 * math.pi * k / 16
                q = Point(at[0] + (r + 0.5) * math.cos(ang), at[1] + (r + 0.5) * math.sin(ang))
                votes[reference(ztree, lay, q)] += 1
            (rl, rn), _ = votes.most_common(1)[0]
            refs[lay] = {"ref_layer": rl, "ref": rn}
        row = {"kind": kind if kind == "via" else f"tht {it[3]}", "at": [round(at[0], 3), round(at[1], 3)],
               "layers": lays, "refs": refs}
        nets = {v["ref"] for v in refs.values()}
        rlayers = {(v["ref_layer"], v["ref"]) for v in refs.values()}
        if len(nets) == 2 and None not in nets:
            a, b = sorted(nets)
            cs = caps_between(d, a, b)
            if cs:
                ref, p = min(cs, key=lambda rp: rp[1].distance(c))
                # how the cap reaches its planes: nearest via of each pad's net (the loop is pad - via - plane)
                pv = {}
                for q in d["pads"]:
                    if q["ref"] == ref:
                        qc = Polygon(q["pts"]).centroid
                        vv = [qc.distance(Point(v["at"])) for v in d["vias"] if v["net"] == q["net"]]
                        pv[q["net"]] = round(min(vv), 2) if vv else None
                row["transfer"] = {"cap": ref, "nets": [a, b], "mm": round(p.distance(c), 2), "cap_pad_to_plane_via_mm": pv}
            else:
                row["transfer"] = {"cap": None, "nets": [a, b], "mm": None}
        elif len(nets) == 1 and None not in nets and len(rlayers) == 2:
            n0 = nets.pop()
            vs = [Point(v["at"]) for v in d["vias"] if v["net"] == n0]
            row["stitch"] = {"net": n0, "mm": round(min(p.distance(c) for p in vs), 2) if vs else None}
        elif None in nets:
            row["transfer"] = {"cap": None, "nets": sorted(n or "none" for n in nets), "mm": None}
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--json")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--expect", action="append", default=[],
                    help="control figures NET=mm,mm (default: the review's, on its board dadcaad3)")
    a = ap.parse_args()
    control_dist = dict(CONTROL_DIST)
    for e in a.expect:
        n, v = e.split("=")
        control_dist[n] = [float(x) for x in v.split(",")]
    d, ztree, ttree = load(a.dump)
    report, fails = {}, []
    for net, expect in SIGNALS.items():
        if not any(t["net"] == net for t in d["tracks"]):
            continue
        smp = walk(d, ztree, ttree, net, expect)
        wrong = [s for s in smp if not s["ok"] and s["ref"] is not None]
        gaps = gap_runs(smp)
        bad = wrong + [g for g in gaps if g["mm"] > MAX_GAP]
        tr = transitions(d, ztree, net)
        cx = crossings(smp)
        changes = [t for t in tr if "transfer" in t]
        report[net] = {"expected_return": sorted(expect), "samples": len(smp),
                       "wrong_reference_samples": len(wrong), "wrong_first": wrong[:6],
                       "no_reference_runs_over_limit": [g for g in gaps if g["mm"] > MAX_GAP],
                       "longest_no_reference_run_mm": max((g["mm"] for g in gaps), default=0.0), "plane_crossings": cx, "transitions": tr,
                       "layer_transitions": len(tr),
                       "reference_changes": [{"at": t["at"], **t["transfer"]} for t in changes]}
        sel = ASSERT_TRANSFER.get(net, lambda at: False)
        worst = max((t["transfer"]["mm"] if t["transfer"]["mm"] is not None else 1e9 for t in changes if sel(t["at"])),
                    default=0)
        report[net]["open_reference_changes"] = [{"at": t["at"], **t["transfer"]} for t in changes
                                                 if not sel(t["at"]) and (t["transfer"]["mm"] is None or t["transfer"]["mm"] > TRANSFER_MM)]
        print(f"{net}: {len(smp)} samples, {len(wrong)} over another net, longest unreferenced run "
              f"{max((g['mm'] for g in gaps), default=0.0)} mm; {len(tr)} layer transitions; reference changes: "
              + (", ".join(f"({t['at'][0]}, {t['at'][1]}) {'/'.join(t['transfer']['nets'])} "
                           f"{t['transfer']['cap']} {t['transfer']['mm']} mm" for t in changes) or "none")
              + (f"; plane crossings: " + ", ".join(f"({c['at'][0]}, {c['at'][1]}) {c['layer']} {c['from']}->{c['to']}"
                                                    f"{' (coupled ' + c['coupled'] + ')' if c['coupled'] else ''}"
                                                    for c in cx[:6]) if cx else ""))
        if a.control:
            continue
        if net in ASSERT_PLANE and bad:
            fails.append(f"{net}: {len(wrong)} samples over another net / {len(bad) - len(wrong)} unreferenced runs > "
                         f"{MAX_GAP} mm (first {bad[0]['at']} {bad[0]['layer']} over {bad[0]['ref']})")
        if net in ASSERT_TRANSFER and worst > TRANSFER_MM:
            fails.append(f"{net}: reference change {worst} mm from a v3v3-selv_gnd cap (limit {TRANSFER_MM})")
        if net in MAX_TRANSITIONS and len(tr) > MAX_TRANSITIONS[net]:
            fails.append(f"{net}: {len(tr)} layer transitions (limit {MAX_TRANSITIONS[net]})")
    if not a.control:
        refs = {p["ref"] for p in d["pads"]}
        for ref in XFER_CAPS:
            if ref not in refs:
                fails.append(f"transfer cap {ref} missing")
                continue
            for q in d["pads"]:
                if q["ref"] == ref:
                    qc = Polygon(q["pts"]).centroid
                    vv = min((qc.distance(Point(v["at"])) for v in d["vias"] if v["net"] == q["net"]), default=1e9)
                    report.setdefault("transfer_caps", {}).setdefault(ref, {})[q["net"]] = round(vv, 2)
                    if vv > XFER_VIA_MM:
                        fails.append(f"transfer cap {ref} {q['net']} pad {vv:.2f} mm from its plane via (limit {XFER_VIA_MM})")
        print("transfer caps (pad to plane via, mm):", report.get("transfer_caps"))
    if a.control:
        bf = report.get("bus_fault_hot", {})
        hit = [c for c in bf.get("plane_crossings", []) if math.dist(c["at"], CONTROL_CROSS) < 1.0
               and {c["from"], c["to"]} >= {"ocp_kelvin_p"}]
        if not hit:
            fails.append("control: bus_fault_hot ocp_kelvin_p crossing near (119.0, 75.2) not found")
        for net, want in control_dist.items():
            got = sorted(t["mm"] for t in report.get(net, {}).get("reference_changes", []) if t["mm"] is not None)
            for w in want:
                if not any(abs(g - w) <= 0.1 for g in got):
                    fails.append(f"control: {net} {w} mm not reproduced (got {got})")
    out = {"dump": a.dump, "mode": "control" if a.control else "gate", "transfer_limit_mm": TRANSFER_MM,
           "asserted": {"plane": sorted(ASSERT_PLANE), "transfer": sorted(ASSERT_TRANSFER),
                        "max_transitions": MAX_TRANSITIONS},
           "signals": report, "failures": fails, "pass": not fails}
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    print(("PASS" if not fails else "FAIL: " + "; ".join(fails)) + (" (control)" if a.control else ""))
    raise SystemExit(0 if not fails else 1)


main()
