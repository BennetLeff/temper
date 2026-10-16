#!/usr/bin/env python3
"""C34: the resonant-bank slot on the stage-32 board (C21-C23, C151, C152) and the room around it.

    python3 -I scripts/slot_geometry.py        -> results/slot_geometry.json   (exit 1 if a control fails)

Inputs, read-only (all committed except the enclosure catalog, which is the R43 release folder):
  native-21/layout/copper.json   stage-32 copper identity (sha256 must be d6f55dfe..., DECISIONS 35)
  native-21/layout/pads.json, native-21/layout/parts.json, native-21/placement.json
  audit.rs SELV_NETS (the same list domains.py reads)
  /Users/bennet/Desktop/temper/output/temper-manufacturing-r43/catalog.json (R43 solids; board at world
  (-141 + x, 236 - y), bottom z 26, as validation-results/08-.../stage16-blower-supply/enclosure_space.py)

Clearance model (a simplified rules21.clearance_on; KiCad DRC stays the authority):
  res_a vs SELV/PE: 12.6 mm on F.Cu/B.Cu, 8.0 on inner layers; any HOT vs SELV/PE 8.0;
  tank net (res_a, crbleed_*) vs any other HOT net 5.0; sw_b vs a HOT net outside the SW_B domain 3.2.
Hard obstacles are pads, vias and tracks. Zone OUTLINES are not copper (KiCad fills them minus clearance, and the
worktree board carries no fills), so they are reported apart: the tank pours (sw_a, sw_b, res_a, coil_feed) as
'tank_pour' (a bank change re-cuts them, as stage 13 did in patches21.py), every other plane as 'zone' (it retreats).
The sw_b band edge above the bank is a tank pour: place.py / round5-native21 README put its edge at y 46.8-47.5 with
RES_A pin 1 >= 5 mm below it, which is why row 1 sits at y 53.2; the pin scan's y 48.0 holds only if that band is
re-laid.
What it reports:
  1. bank pads, courtyards, the column extent and its neighbours (courtyard gaps);
  2. for a new THT pin (2.4 mm square pad, all layers) the clearance margin along the RES_A column
     (x 163.0) and the SW_B column (x 190.5) above and below today's rows, and across the rows for a
     wider pitch (RES_A pin moved left / SW_B pin moved right);
  3. height above the board top to the first R43 solid over the bank area (harness AABBs listed, not counted).
Controls: copper.json hash; the five bank pads are res_a / sw_b at x 163.0 / 190.5 and the five rows of
DECISIONS 2026-10-09; today's pads have margin >= 0 against hard obstacles (the board passes DRC).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
UNIT = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")   # bank28: PS HEAD (s48), read-only
N21 = UNIT / "native-21"
R43 = Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/catalog.json")
COPPER_SHA = "592a0d38f631de8c57b00aeb4661a1fe73426552704e90bae3d1f7d915b0d10a"   # bank28: s48 HEAD 05a3d9138 copper
BANK = ["C21", "C22", "C23", "C151", "C152"]
OUTER = ("F.Cu", "B.Cu")
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
PAD_HALF = 1.2                                           # today's bank pad: 2.4 mm square (pads.json)
fails = []


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


cu_sha = sha(N21 / "layout/copper.json")
if cu_sha != COPPER_SHA:
    fails.append(f"copper.json sha {cu_sha[:12]} is not the stage-32 identity")
copper = json.loads((N21 / "layout/copper.json").read_text())
pads = json.loads((N21 / "layout/pads.json").read_text())
parts = json.loads((N21 / "layout/parts.json").read_text())
place = json.loads((N21 / "placement.json").read_text())
audit = (UNIT / "audit.rs").read_text()
body = audit[audit.index("const SELV_NETS"):]
SELV = set(re.findall(r'"([^"]+)"', body[:body.index("];")]))
SELV_NC_SUFFIX = ("-nc10", "-nc11", "-nc12", "-nc15")
TANK = {"res_a", "crbleed_1", "crbleed_2", "crbleed_3"}
TANK_POUR = {"sw_a", "sw_b", "res_a", "coil_feed"}         # zones of these nets count as hard obstacles


def domain(n):
    if n in SELV or n.endswith(SELV_NC_SUFFIX) or n in ("leg_a.driver-nc_7", "leg_b.driver-nc_7"):
        return "SELV"
    if n == "pe":
        return "PE"
    if n in ("sw_b", "p_hb", "n_hb") or (n.startswith("bias_hb") and not n.endswith(("_bad", ".iso-p3", "-en"))) or \
            n in ("leg_b-gate_h", "leg_b-out_h", "leg_b-off_h", "leg_b.bias_h-damp"):
        return "SW_B"
    return "HOT"


def need(net_new, other, layer):
    if not other or other == net_new:
        return None
    do = domain(other)
    if do in ("SELV", "PE"):
        return 12.6 if (net_new == "res_a" and layer in OUTER) else 8.0
    if net_new in TANK or other in TANK:
        return 5.0
    if net_new == "sw_b" and do != "SW_B":
        return 3.2
    return 0.2


# ---- obstacles -------------------------------------------------------------------------------------
padxy = {(p["ref"], p["pad"]): p for p in pads if p["pad"]}
segs = []                                              # (layer, net, x0, y0, x1, y1, half width)
for t in copper["tracks"]:
    pts = []
    for q in t["points"]:
        if isinstance(q, str):
            r, n = q.rsplit(".", 1)
            p = padxy.get((r, n))
            if p is None:
                continue
            pts.append((p["x"], p["y"]))
        else:
            pts.append(tuple(q))
    for a, b in zip(pts, pts[1:]):
        segs.append((t["layer"], t["net"], a[0], a[1], b[0], b[1], t["width"] / 2))
for v in copper["vias"]:
    for lay in LAYERS:
        segs.append((lay, v["net"], v["at"][0], v["at"][1], v["at"][0], v["at"][1], v["size"] / 2))
boxes = []                                             # (layer, net, x0, y0, x1, y1, ref)
for p in pads:
    if not p["net"]:
        continue
    lays = LAYERS if p["tht"] else ("F.Cu",)           # SMD pads on this board are top side
    for lay in lays:
        boxes.append((lay, p["net"], *p["box"], p["ref"]))
zones = [(z["layer"], z["net"], np.array(z["outline"], float), z.get("name", "")) for z in copper["zones"]]


def d_seg(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
    return float(np.hypot(px - (x0 + t * dx), py - (y0 + t * dy)))


def d_box_box(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return float(np.hypot(dx, dy))


def d_box_seg(bx, s):
    """distance from a square pad box to a segment (sampled; the pad is small against the segments)."""
    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    best = 1e9
    for px, py in ((cx, cy), (bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3]),
                   (cx, bx[1]), (cx, bx[3]), (bx[0], cy), (bx[2], cy)):
        best = min(best, d_seg(px, py, *s))
    return max(0.0, best - 0.0)


def in_poly(px, py, poly):
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    c = ((y > py) != (y2 > py)) & (px < (x2 - x) * (py - y) / np.where(y2 == y, 1e-12, y2 - y) + x)
    return bool(c.sum() % 2)


def d_poly(px, py, poly):
    if in_poly(px, py, poly):
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    dx, dy = x2 - x, y2 - y
    L2 = np.where(dx * dx + dy * dy == 0, 1e-12, dx * dx + dy * dy)
    t = np.clip(((px - x) * dx + (py - y) * dy) / L2, 0, 1)
    return float(np.min(np.hypot(px - (x + t * dx), py - (y + t * dy))))


def margin(x, y, net, skip_refs=(), half=PAD_HALF):
    """worst (distance - required clearance) for a THT pad of `net` at (x, y), hard and soft, with the culprit."""
    bx = (x - half, y - half, x + half, y + half)
    hard, soft, tank = (1e9, None), (1e9, None), (1e9, None)
    for s in segs:
        r = need(net, s[1], s[0])
        if r is None or abs(s[2] - x) > 30 and abs(s[4] - x) > 30:
            continue
        m = d_box_seg(bx, s[2:6]) - s[6] - r
        if m < hard[0]:
            hard = (m, f"{s[1]} {s[0]} track/via")
    for b in boxes:
        if b[6] in skip_refs:
            continue
        r = need(net, b[1], b[0])
        if r is None:
            continue
        m = d_box_box(bx, b[2:6]) - r
        if m < hard[0]:
            hard = (m, f"{b[1]} {b[0]} pad {b[6]}")
    for z in zones:
        r = need(net, z[1], z[0])
        if r is None:
            continue
        m = min(d_poly(px, py, z[2]) for px, py in ((x, y), (bx[0], bx[1]), (bx[2], bx[3]), (bx[0], bx[3]), (bx[2], bx[1]))) - r
        if z[1] in TANK_POUR:               # tank conductors: re-cut by any bank change (stage 13 did), listed apart
            if m < tank[0]:
                tank = (m, f"{z[1]} {z[0]} zone '{z[3]}'")
        elif m < soft[0]:
            soft = (m, f"{z[1]} {z[0]} zone '{z[3]}'")
    return {"hard_margin_mm": round(hard[0], 2), "hard_by": hard[1], "zone_margin_mm": round(soft[0], 2), "zone_by": soft[1],
            "tank_pour_outline_margin_mm": round(tank[0], 2), "tank_pour_by": tank[1]}


# ---- 1. bank and neighbours --------------------------------------------------------------------------
res = {"inputs": {"copper.json": cu_sha, "pads.json": sha(N21 / "layout/pads.json"),
                  "parts.json": sha(N21 / "layout/parts.json"), "placement.json": sha(N21 / "placement.json"),
                  "r43_catalog": sha(R43) if R43.exists() else None}}
bank_pads = [p for p in pads if p["ref"] in BANK]
for r in BANK:
    pp = sorted((p for p in bank_pads if p["ref"] == r), key=lambda p: p["pad"])
    if [p["net"] for p in pp] != ["res_a", "sw_b"] or [p["x"] for p in pp] != [163.0, 190.5]:
        fails.append(f"{r} pads {[(p['net'], p['x']) for p in pp]}")
rows = sorted({p["y"] for p in bank_pads})
if rows != [53.2, 67.7, 82.5, 97.0, 111.5]:
    fails.append(f"bank rows {rows}")


def courtyard(pt):
    x, y, rot = place[pt["path"]]
    ox, oy, w, h = pt["ox"], pt["oy"], pt["w"], pt["h"]
    rr = round(rot) % 360
    if rr == 90:
        ox, oy, w, h = oy, -ox, h, w
    elif rr == 180:
        ox, oy = -ox, -oy
    elif rr == 270:
        ox, oy, w, h = -oy, ox, h, w
    cx, cy = x + ox, y + oy
    return [round(cx - w / 2, 3), round(cy - h / 2, 3), round(cx + w / 2, 3), round(cy + h / 2, 3)]


crt = {p["ref"]: courtyard(p) for p in parts if p["path"] in place}
bb = [min(crt[r][0] for r in BANK), min(crt[r][1] for r in BANK), max(crt[r][2] for r in BANK), max(crt[r][3] for r in BANK)]
res["bank"] = {"pin_pitch_mm": 27.5, "rows_y": rows, "row_pitch_mm": [round(b - a, 2) for a, b in zip(rows, rows[1:])],
               "courtyards": {r: crt[r] for r in BANK}, "column_bbox": bb,
               "column_length_mm": round(bb[3] - bb[1], 2), "column_width_mm": round(bb[2] - bb[0], 2)}
nb = []
for r, c in crt.items():
    if r in BANK:
        continue
    gx = max(c[0] - bb[2], bb[0] - c[2])
    gy = max(c[1] - bb[3], bb[1] - c[3])
    gap = max(gx, gy)
    if gap < 25:
        side = ("right" if c[0] >= bb[2] else "left" if c[2] <= bb[0] else "below" if c[1] >= bb[3] else
                "above" if c[3] <= bb[1] else "overlap")
        nb.append({"ref": r, "courtyard": c, "side": side, "gap_mm": round(gap, 2)})
res["neighbours"] = sorted(nb, key=lambda n: n["gap_mm"])

# ---- 2. clearance scans ---------------------------------------------------------------------------
ctrl = [margin(p["x"], p["y"], p["net"], skip_refs=(p["ref"],)) for p in bank_pads]
worst_ctrl = min(c["hard_margin_mm"] for c in ctrl)
res["control_today_pads_hard_margin_min_mm"] = worst_ctrl
if worst_ctrl < -0.05:
    fails.append(f"today's bank pads show hard margin {worst_ctrl} (model disagrees with DRC)")
scan = {}
# 27.5 mm pitch today; a 22.5 mm part keeps one strip and moves the other 5 mm in (res_a 163 / sw_b 185.5, or
# res_a 168 / sw_b 190.5)
for net, x in (("res_a", 163.0), ("sw_b", 190.5), ("res_a", 168.0), ("sw_b", 185.5)):
    col = []
    for y in np.arange(30.0, 140.01, 0.5):
        m = margin(x, float(y), net, skip_refs=tuple(BANK))
        col.append({"y": round(float(y), 1), **m})
    scan[f"{net}_x{x}"] = col


def free_run(col, y0, step):
    """walk from y0 in direction step while the hard margin stays >= 0; return the last clear y."""
    ys = {c["y"]: c for c in col}
    y, last = y0, None
    while y in ys and ys[y]["hard_margin_mm"] >= 0:
        last = y
        y = round(y + step, 1)
    return last, ys.get(y)


ext = {}
for key, col in scan.items():
    lo, lo_by = free_run(col, 105.0, 0.5)
    hi, hi_by = free_run(col, 53.0, -0.5)
    ext[key] = {"last_clear_pin_y_below": lo, "blocked_by_below": lo_by and lo_by["hard_by"],
                "last_clear_pin_y_above": hi, "blocked_by_above": hi_by and hi_by["hard_by"]}
res["column_scan_summary"] = ext
res["column_scan"] = {k: [c for c in v if c["y"] % 2 == 0 or c["hard_margin_mm"] < 1] for k, v in scan.items()}
# wider pitch: move the RES_A pin left, or the SW_B pin right, at each row
wide = {}
for net, xs in (("res_a", np.arange(163.0, 140.0, -0.5)), ("sw_b", np.arange(190.5, 216.0, 0.5))):
    for y in rows:
        last = None
        for x in xs:
            m = margin(float(x), y, net, skip_refs=tuple(BANK))
            if m["hard_margin_mm"] < 0:
                wide[f"{net}_row{y}"] = {"last_clear_x": last, "blocked_at_x": round(float(x), 1), **m}
                break
            last = round(float(x), 1)
        else:
            wide[f"{net}_row{y}"] = {"last_clear_x": last, "blocked_at_x": None}
res["pitch_scan"] = wide

# ---- 3. height ------------------------------------------------------------------------------------
if R43.exists():
    cat = json.loads(R43.read_text())
    brd = next(c for c in cat if c["name"] == "electronics_native21_board")["bbox"]
    top = brd[5]
    w = [-141 + bb[0], 236 - bb[3], -141 + bb[2], 236 - bb[1]]
    over, harn = [], []
    for c in cat:
        b = c["bbox"]
        if not (b[0] < w[2] and w[0] < b[3] and b[1] < w[3] and w[1] < b[4] and b[5] > top + 0.5):
            continue
        if c["name"].startswith(("enclosure_P4_", "electronics_native21_components_ENVELOPE")) or b[2] <= top:
            if c["group"] == "harness":
                harn.append(c["name"])
            continue
        (harn if c["group"] == "harness" else over).append(c["name"] if c["group"] == "harness" else
                                                            {"name": c["name"], "z_bottom": b[2], "bbox": b})
    first = min(over, key=lambda o: o["z_bottom"])
    env = next(c for c in cat if c["name"] == "electronics_native21_components_ENVELOPE")["bbox"]
    res["height"] = {"board_world_bbox": brd, "bank_world_xy": [round(v, 2) for v in w], "board_top_z": top,
                     "first_solid_over_bank": first["name"], "first_solid_z": first["z_bottom"],
                     "headroom_to_first_solid_mm": round(first["z_bottom"] - top, 2),
                     "headroom_with_1mm_gap_mm": round(first["z_bottom"] - top - 1.0, 2),
                     "components_allocation_envelope_top_z": env[5],
                     "headroom_to_allocation_envelope_mm": round(env[5] - top, 2),
                     "solids_over_bank": sorted(over, key=lambda o: o["z_bottom"])[:6],
                     "harness_aabbs_over_bank_not_counted": sorted(set(harn)),
                     "today_body_height_mm": 24.5}
else:
    res["height"] = {"error": "R43 catalog not found"}
res["controls"] = {"failed": fails, "passed": not fails}
OUT.mkdir(exist_ok=True)
(OUT / "slot_geometry.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps({k: res[k] for k in ("bank", "column_scan_summary", "pitch_scan", "controls")}, indent=1))
print(json.dumps({k: v for k, v in res.get("height", {}).items() if k != "solids_over_bank"}, indent=1))
print("neighbours:", [(n["ref"], n["side"], n["gap_mm"]) for n in res["neighbours"][:12]])
sys.exit(1 if fails else 0)
