#!/usr/bin/env python3
"""Legal poses for a stage-30 SMD part on the routed s29 board (DECISIONS 33).

    python3 -I spot_scan.py DUMP.json PART TX TY [--box x0,y0,x1,y1] [--top N] [--step MM]

PART is a key of PARTS below (pad geometry in footprint coordinates, pad nets from the stage-30 netlist).
A pose (courtyard centre, KiCad angle 0 / 90 / 180 / 270) is legal when
 (a) its courtyard clears every surviving part's courtyard (native-21/placement.json + layout/parts.json;
     the parts deleted in stage 30 are ignored) by 0.1 mm and stays 0.5 mm inside the board;
 (b) every HOT pad keeps the 8.0 mm plan-view barrier (+ --margin) to every SELV / PE item of the dump on any
     layer, pours included (a SELV plane must not have to retreat), and every SELV pad the same to every HOT item;
 (c) every pad keeps rules21.clearance + 0.05 mm to every fixed F.Cu track, via and pad of another net
     (pours of other HOT groups refill round the part and are only counted).
Copper of nets that no longer exist in the stage-30 netlist (the deleted monitor / OR nets) is ignored.
Ranked by the distance from TX, TY to the part's centre. Prints the pose and, per legal pose, how many
foreign HOT pours its pads sit in (each would refill away by the group clearance).
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
sys.path.insert(0, str(PS / "native-21/layout"))
import rules21  # noqa: E402

from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

SOIC8 = [((-2.475, -1.905 + 1.27 * i), (1.95, 0.6)) for i in range(4)] + \
        [((2.475, 1.905 - 1.27 * i), (1.95, 0.6)) for i in range(4)]
C0603 = [((-0.775, 0.0), (0.9, 0.95)), ((0.775, 0.0), (0.9, 0.95))]
SOT23_5 = [((-1.1375, -0.95), (1.325, 0.6)), ((-1.1375, 0.0), (1.325, 0.6)), ((-1.1375, 0.95), (1.325, 0.6)),
           ((1.1375, 0.95), (1.325, 0.6)), ((1.1375, -0.95), (1.325, 0.6))]
SOT23 = [((-0.9375, -0.95), (1.475, 0.6)), ((-0.9375, 0.95), (1.475, 0.6)), ((0.9375, 0.0), (1.475, 0.6))]
PARTS = {
    "U43": (SOIC8, (7.49, 5.49), ["bias_ha.monitor-v5", "bias_ha-outa_nc", "bias_ha.monitor-good", "n_ha",
                                  "n_ls", "mon_good_ha", "n_ls", "ls_v5"]),
    "U44": (SOIC8, (7.49, 5.49), ["bias_hb.monitor-v5", "bias_hb-outa_nc", "bias_hb.monitor-good", "n_hb",
                                  "n_ls", "mon_good_hb", "n_ls", "ls_v5"]),
    "U45": (SOT23_5, (4.19, 3.49), ["monitor_ls-good", "hb_rc", "n_ls", "hb_tx", "ls_v5"]),
    "U46": (SOT23_5, (4.19, 3.49), ["hb.buf-nc", "hb_rx", "selv_gnd", "hb_bufo", "v3v3"]),
    "D18": (SOT23, (3.95, 3.49), ["mon_good_ha", "mon_good_hb", "monitor_ls-good"]),
    "D19": (SOT23, (3.95, 3.49), ["selv_gnd", "hb_hold", "hb_x"]),
    "U40": (SOT23_5, (4.19, 3.49), ["u_bias_flt-nc", "hb_hold", "selv_gnd", "bias_good", "v3v3"]),
    # stage 40 (candidate 30a): the second vote diode (A1 open, K2 on HS-B's verdict, MID on the LS GOOD node)
    "D20": (SOT23, (3.95, 3.49), ["vote_b_nc", "mon_good_hb", "monitor_ls-good"]),
}
for ref, a, b in (("C157", "bias_ha.monitor-v5", "n_ha"), ("C158", "ls_v5", "n_ls"), ("C159", "bias_hb.monitor-v5", "n_hb"),
                  ("C160", "ls_v5", "n_ls"), ("C161", "ls_v5", "n_ls"), ("C162", "hb_rc", "n_ls"), ("C163", "v3v3", "selv_gnd"),
                  ("C164", "hb_s", "hb_m"), ("C165", "hb_m", "hb_x"), ("C166", "hb_hold", "selv_gnd"),
                  ("C167", "bus_fault_flt", "selv_gnd"), ("C144", "v3v3", "selv_gnd"), ("R131", "hb_tx", "hb_rc"), ("R132", "hb_bufo", "hb_s"),
                  ("R133", "hb_hold", "selv_gnd"), ("R134", "bus_fault_iso", "bus_fault_flt"),
                  ("R135", "v3v3", "hsb_good")):     # stage 40: U46.1's pull-up
    PARTS[ref] = (C0603, (3.05, 1.55), [a, b])


MARGIN = 0.1
GAP = 0.05      # half the courtyard gap demanded between parts


def nets_now():
    net = (PS / "native-21/frozen/default.net").read_text()
    return set(re.findall(r'\(net \(code "?\d+"?\) \(name "([^"]+)"\)', net))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("part")
    ap.add_argument("tx", type=float)
    ap.add_argument("ty", type=float)
    ap.add_argument("--box", default=None)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--reach", type=float, default=12.0)
    ap.add_argument("--margin", type=float, default=0.1, help="mm beyond the 8.0 mm barrier")
    ap.add_argument("--gap", type=float, default=0.05, help="half the courtyard-to-courtyard gap (mm)")
    ap.add_argument("--explain", default=None, help="x,y,angle: print why that one pose fails")
    a = ap.parse_args()
    global MARGIN, GAP
    MARGIN = a.margin
    GAP = a.gap
    pads, cy, pnets = PARTS[a.part]
    live = nets_now()
    d = json.loads(Path(a.dump).read_text())
    parts = {p["path"]: p for p in json.loads((PS / "native-21/layout/parts.json").read_text())}
    cur = {r["path"] for r in json.loads((PS / "native-21/layout/parts.json").read_text())}
    place = json.loads((PS / "native-21/placement.json").read_text())
    import csv
    refs_now = set()
    for row in csv.DictReader(open(PS / "native-21/frozen/default.csv")):
        refs_now |= {r.strip() for r in row["Designator"].split(",") if r.strip()}
    courts = []
    for path, (x, y, ang) in place.items():
        p = parts.get(path)
        if not p or p["ref"] not in refs_now or p["ref"] == a.part or path not in cur:
            continue
        r = math.radians(ang)
        cx = x + p["ox"] * math.cos(r) + p["oy"] * math.sin(r)
        cyy = y - p["ox"] * math.sin(r) + p["oy"] * math.cos(r)
        w, h = (p["h"], p["w"]) if round(ang) % 180 == 90 else (p["w"], p["h"])
        courts.append(box(cx - w / 2 - GAP, cyy - h / 2 - GAP, cx + w / 2 + GAP, cyy + h / 2 + GAP))
    ctree = STRtree(courts)
    # copper sitting inside a deleted part's courtyard (+1 mm): its stitching vias and pad stubs, which the settle
    # loop trims once the pads are gone (stage-29 poses from placement-stage29.json, sizes from the s29 parts.json)
    gone = []
    s29 = json.loads((PS / "native-21/layout/placement-stage29.json").read_text())
    import subprocess
    old_parts = json.loads(subprocess.run(["git", "-C", str(PS), "show", "native21s29:./native-21/layout/parts.json"],
                                          capture_output=True, text=True, check=True).stdout)
    for q in old_parts:
        if q["ref"] in refs_now or q["path"] not in s29:
            continue
        x, y, ang = s29[q["path"]]
        r = math.radians(ang)
        cx, cyy = x + q["ox"] * math.cos(r) + q["oy"] * math.sin(r), y - q["ox"] * math.sin(r) + q["oy"] * math.cos(r)
        w, h = (q["h"], q["w"]) if round(ang) % 180 == 90 else (q["w"], q["h"])
        gone.append(box(cx - w / 2 - 1, cyy - h / 2 - 1, cx + w / 2 + 1, cyy + h / 2 + 1))
    selv, fixed, pours = [], [], []
    for z in d["zones"]:
        if z["net"] not in live:
            continue
        g = Polygon(z["pts"], z["holes"]).buffer(0)
        (selv if rules21.domain(z["net"]) in ("SELV", "PE") else pours).append((g, z["net"], z["layer"]))
    for t in d["tracks"]:
        if t["net"] in live:
            g = LineString([t["a"], t["b"]]).buffer(t["w"] / 2)
            if any(gg.contains(g) for gg in gone):
                continue
            (selv if rules21.domain(t["net"]) in ("SELV", "PE") else fixed).append((g, t["net"], t["layer"]))
    for v in d["vias"]:
        if v["net"] in live:
            g = Point(*v["at"]).buffer(v["d"] / 2)
            if any(gg.contains(g) for gg in gone):
                continue
            (selv if rules21.domain(v["net"]) in ("SELV", "PE") else fixed).append((g, v["net"], "*"))
    for p in d["pads"]:
        if p["net"] in live and p["ref"] in refs_now and p["ref"] != a.part:
            g = Polygon(p["pts"]).buffer(0)
            lay = "*" if p.get("tht") else ",".join(p.get("layers", ["F.Cu"]))
            (selv if rules21.domain(p["net"]) in ("SELV", "PE") else fixed).append((g, p["net"], lay))
    # pads of the stage-30 parts already authored in place.py (STAGE30; parked parts sit at x 150 and are skipped)
    byref = {q["ref"]: q["path"] for q in parts.values()}
    for ref, (pp, _, nn) in PARTS.items():
        pose = place.get(byref.get(ref, ""))
        if ref == a.part or not pose or pose[0] == 150.0:
            continue
        x0, y0, ang0 = pose
        r0 = math.radians(ang0)
        for ((px, py), (pw, ph)), pn in zip(pp, nn):
            qx, qy = x0 + px * math.cos(r0) + py * math.sin(r0), y0 - px * math.sin(r0) + py * math.cos(r0)
            pw2, ph2 = (ph, pw) if round(ang0) % 180 == 90 else (pw, ph)
            g = box(qx - pw2 / 2, qy - ph2 / 2, qx + pw2 / 2, qy + ph2 / 2)
            (selv if rules21.domain(pn) in ("SELV", "PE") else fixed).append((g, pn, "F.Cu"))
    hot = [it for it in fixed + pours if rules21.domain(it[1]) == "HOT"]
    stree, ftree, ptree, htree = (STRtree([g for g, _, _ in s]) for s in (selv, fixed, pours, hot))
    bx = [float(v) for v in a.box.split(",")] if a.box else [a.tx - a.reach, a.ty - a.reach, a.tx + a.reach, a.ty + a.reach]
    out = []
    explain = [float(v) for v in a.explain.split(",")] if a.explain else None
    if explain:
        bx = [explain[0], explain[1], explain[0], explain[1]]
    n = int(round((bx[2] - bx[0]) / a.step))
    m = int(round((bx[3] - bx[1]) / a.step))
    hot_pads = any(rules21.domain(q) == "HOT" for q in pnets)
    for i in range(n + 1):
        for j in range(m + 1):
            x, y = bx[0] + i * a.step, bx[1] + j * a.step
            for ang in ((int(explain[2]),) if explain else (0, 90, 180, 270)):
                w, h = (cy[1], cy[0]) if ang % 180 == 90 else cy
                c = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
                if c.bounds[0] < 0.5 or c.bounds[1] < 0.5 or c.bounds[2] > 289.5 or c.bounds[3] > 139.5 and not (c.bounds[2] < 90.5 and c.bounds[3] < 189.5):
                    continue
                if any(c.intersects(courts[k]) for k in ctree.query(c)):
                    if explain:
                        print("courtyard overlap with", [courts[k].bounds for k in ctree.query(c) if c.intersects(courts[k])])
                    continue
                r = math.radians(ang)
                ok, foreign = True, 0
                for ((px, py), (pw, ph)), pn in zip(pads, pnets):
                    # KiCad rotates by -angle in the y-down frame
                    qx, qy = x + px * math.cos(r) + py * math.sin(r), y - px * math.sin(r) + py * math.cos(r)
                    pw2, ph2 = (ph, pw) if ang % 180 == 90 else (pw, ph)
                    pg = box(qx - pw2 / 2, qy - ph2 / 2, qx + pw2 / 2, qy + ph2 / 2)
                    if hot_pads and rules21.domain(pn) == "HOT":
                        for k in stree.query(pg.buffer(rules21.BARRIER + MARGIN)):
                            if pg.distance(selv[k][0]) < rules21.BARRIER + MARGIN:
                                if explain:
                                    print(f"pad {pn}: barrier {pg.distance(selv[k][0]):.2f} mm to {selv[k][1]} on {selv[k][2]}")
                                ok = False
                                break
                    if rules21.domain(pn) in ("SELV", "PE"):
                        for k in htree.query(pg.buffer(rules21.BARRIER + MARGIN)):
                            if pg.distance(hot[k][0]) < rules21.BARRIER + MARGIN:
                                if explain:
                                    print(f"pad {pn}: barrier {pg.distance(hot[k][0]):.2f} mm to {hot[k][1]} on {hot[k][2]}")
                                ok = False
                                break
                    if not ok:
                        break
                    for k in ftree.query(pg.buffer(3.5)):
                        g, fn, lay = fixed[k]
                        if fn == pn or (lay != "*" and "F.Cu" not in lay):
                            continue
                        if pg.distance(g) < rules21.clearance(pn, fn) + 0.05:
                            if explain:
                                print(f"pad {pn}: {pg.distance(g):.2f} mm to {fn} ({lay}) at {[round(v, 1) for v in g.bounds]}")
                            ok = False
                            break
                    if not ok:
                        break
                    for k in ptree.query(pg):
                        g, fn, lay = pours[k]
                        if lay == "F.Cu" and fn != pn and rules21.clearance(pn, fn) > rules21.FLOOR and g.intersects(pg):
                            foreign += 1
                if ok:
                    out.append((round(math.hypot(x - a.tx, y - a.ty), 2), round(x, 3), round(y, 3), ang, foreign))
    out.sort()
    print(f"{a.part}: {len(out)} legal poses in {bx}; best {a.top} by distance to ({a.tx}, {a.ty}):")
    for o in out[:a.top]:
        print(f"  d {o[0]:6.2f}  centre ({o[1]}, {o[2]})  angle {o[3]:3d}  pads in foreign HOT F.Cu pours: {o[4]}")
    return out


if __name__ == "__main__":
    main()
