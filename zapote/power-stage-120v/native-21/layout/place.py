#!/usr/bin/env python3
"""Native-21 placement generator (layout stage 2) -> native-21/placement.json.

    python3 native-21/layout/place.py

Every pose here is authored: critical parts explicitly, the rest packed
row-by-row into named zone rectangles (deterministic order by instance path).
Coordinates are COURTYARD CENTRES in the KiCad frame (x right, y down, mm) and
are converted to footprint origins with each footprint's measured courtyard
offset (parts.json, measure_parts.py). See native-21/FLOORPLAN.md for zones.

Frame: board 0..290 x 0..140 plus tongue 0..91 x 140..190 (parts there <= 22 mm
tall for y > 160). Top edge = enclosure rear (sink row).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTS = {p["path"]: p for p in json.loads((HERE / "parts.json").read_text())}
POSE: dict[str, tuple[float, float, float]] = {}
GAP = 0.6


def size(path, ang=0.0):
    p = PARTS[path]
    return (p["h"], p["w"]) if round(ang) % 180 == 90 else (p["w"], p["h"])


def put(path, cx, cy, ang=0.0):
    if path not in PARTS:
        raise KeyError(path)
    if path in POSE:
        raise ValueError(f"placed twice: {path}")
    POSE[path] = (cx, cy, ang)


def pack(paths, x0, y0, x1, y1, ang=0.0, gap=GAP, big_first=True):
    """Row-pack courtyards left->right, top->bottom inside the rectangle (largest first)."""
    if big_first:
        paths = sorted(paths, key=lambda q: (-size(q, ang)[1], -size(q, ang)[0], q))
    x, y, row = x0, y0, 0.0
    for p in paths:
        w, h = size(p, ang)
        if x + w > x1 + 1e-9:
            x, y, row = x0, y + row + gap, 0.0
        if y + h > y1 + 1e-9:
            raise ValueError(f"zone ({x0},{y0})-({x1},{y1}) overflows at {p}")
        put(p, x + w / 2, y + h / 2, ang)
        x += w + gap
        row = max(row, h)


def under(prefix):
    return sorted(p for p in PARTS if p == prefix or p.startswith(prefix + ".")) if prefix.endswith("") else []


def group(*prefixes, exclude=()):
    out = [p for p in sorted(PARTS) if any(p == q or p.startswith(q + ".") for q in prefixes)]
    return [p for p in out if p not in POSE and p not in exclude]


# ---------------- sink row (rear edge), native-20 core shifted by DX ----------
DX = -88.0
Q = {"leg_b.q_high": 9.95, "leg_b.q_low": 27.95, "leg_a.q_low": 50.05, "leg_a.q_high": 68.05}  # courtyard centres
for q, x in Q.items():
    put(q, x, 4.4)
put("br1", 76.85 + 0.5 + 15.05, 4.6)          # right after Q2: row 1.7 .. 107.0
GATE = {k: Q[k] - 5.45 for k in Q}           # gate pin x (TO-247 pin 1)
for leg, q, side in (("leg_b", "leg_b.q_high", "h"), ("leg_b", "leg_b.q_low", "l"),
                     ("leg_a", "leg_a.q_high", "h"), ("leg_a", "leg_a.q_low", "l")):
    g = GATE[q]
    put(f"{leg}.c_snub_{side}", Q[q] + 2.73, 9.7)
    put(f"{leg}.r_g{side}", g + 2.7, 12.6, 90)
    put(f"{leg}.r_g{side}_pd", g, 12.1, 90)
    # F6 network directly under the gate: PMEG (anode at gate) + 1 ohm to OUT, Cgs to source.
    put(f"{leg}.doff_{side}", g + 4.6, 17.9)
    put(f"{leg}.roff_{side}", g + 11.0, 17.9)
    put(f"{leg}.cgs_{side}", g + 1.0, 21.8)
put("r_shunt", 38.5 + 0.0, 12.6, 270)          # between the low-side sources
# HF film row (moved 6 mm down for the F6 row; C41 pulled in from the edge)
put("c_hf_b2", 9.9, 28.2)
put("c_hf_b1", 29.0, 28.2)
put("c_hf_a1", 48.6, 28.2, 180)
put("c_hf_a2", 69.2, 28.2, 180)

# ---------------- drivers, HOT row facing the gates (rot 90) ------------------
DRV = {"leg_b": 33.0, "leg_a": 77.0}
for leg, x in DRV.items():
    put(f"{leg}.driver", x, 47.0, 90)
# Reservoir banks: HS (channel A, left end of the HOT row) and LS (channel B, right end).
BANK = {"leg_b.bias_h": (13.0, 33.6), "leg_b.bias_l": (39.0, 33.6),
        "leg_a.bias_h": (57.0, 33.6), "leg_a.bias_l": (83.0, 33.6)}
# Explicit 14.4 x 12 mm bank template (courtyard centres relative to the bank's top-left);
# HF parts (100 nF, 1 uF) on the side facing the driver pins, bulk 220 uF + damping behind.
BANK_TEMPLATE = {"cbulk": (4.85, 3.6, 0), "rdamp": (11.0, 2.4, 90), "rbleed": (13.6, 1.6, 90),
                 "clocal1": (2.4, 9.0, 0), "clocal2": (7.4, 9.0, 0), "cmid1": (11.6, 6.0, 0),
                 "cmid2": (11.6, 8.0, 0), "chf1": (11.3, 10.0, 0), "chf2": (13.4, 10.0, 0),
                 "chf3": (11.3, 11.4, 0), "chf4": (13.4, 11.4, 0)}
for b, (x, y) in BANK.items():
    for part, (dx, dy, ang) in BANK_TEMPLATE.items():
        put(f"{b}.{part}", x + dx, y + dy, ang)
# Driver-local parts that stay on the HOT side near each driver (LS caps)
for leg, x in DRV.items():
    pack(group(f"{leg}.c_ls", f"{leg}.c_ls_bulk"), x + 6.0, 47.2, x + 14.5, 53.0)

# ---------------- SELV side of each driver (tongue) ---------------------------
for leg, x in DRV.items():
    pack(group(f"{leg}.c_vcci", f"{leg}.permit_fet", f"{leg}.r_permit", f"{leg}.r_permit_pd",
               f"{leg}.r_dis_pu", f"{leg}.r_dt", f"{leg}.dis_or", f"{leg}.c_dis_or", f"{leg}.r_driver_dis"),
         x - 5.0, 55.0, x + 5.0, 78.0)

# ---------------- HS bias islands (left of each driver tongue) ----------------
pack(group("bias_hb", exclude=("bias_hb.monitor.iso",)), 0.8, 50.0, 19.6, 118.0, gap=0.5)
put("bias_hb.monitor.iso", 23.6, 110.0, 0)       # straddles the leg-B tongue's left edge
pack(group("bias_ha", exclude=("bias_ha.monitor.iso",)), 46.4, 50.0, 63.6, 118.0, gap=0.5)
put("bias_ha.monitor.iso", 67.6, 110.0, 0)       # straddles the leg-A tongue's left edge

# ---------------- SELV island (bottom band + board tongue) --------------------
put("j_selv", 45.0, 182.0)
pack(group("u_ct_pos", "u_ct_neg", "u_ct_zc", "c_ct_pos", "c_ct_neg", "c_ct_zc", "r_ct_hi_top", "r_ct_hi_bot",
           "r_ct_lo_top", "r_ct_lo_bot", "r_ct_bias_top", "r_ct_bias_bot", "c_ct_bias", "r_ct_mon",
           "u_fault_or", "c_fault_or", "bias_or", "bias_c_or", "u_bias_flt", "r_bias_flt", "c_bias_flt",
           "c_bias_flt_vcc", "line_zc.buffer", "line_zc.cbuffer", "line_zc.pullup", "r_fe",
           "c_iso2", "c_vs2", "monitor_ls.civcc2", "bias_ha.monitor.civcc2", "bias_hb.monitor.civcc2"),
     2.0, 128.0, 89.0, 170.0)

# ---------------- remaining zones are packed for the first cut ----------------
# HOT protection (OCP/OVP/HOT5, Kelvin island) beside the core, right of the LS-A bank
pack(group("u_ldo", "c_ldo_in", "c_ldo_out", "c_v15", "u_ref", "r_ref_bias", "u_ocp", "c_ocp_vcc", "r_ocp_ref",
           "r_ocp_sense", "c_ocp_node", "r_th_top", "r_th_bot", "c_th", "u_ovp", "c_ovp_vcc", "r_ovp_top",
           "r_ovp_bot", "c_ovp_th", "u_nand", "c_nand_vcc", "c_iso1", "u_hot5_uv", "r_hot5_uv_top",
           "r_hot5_uv_bot", "r_hot5_uv_pull", "c_hot5_uv", "u_hot5_schmitt", "c_hot5_schmitt",
           "c_vs1", "c_div", "r_div_bot", "r_div1", "r_div2", "r_div3", "r_div4"),
     98.5, 12.0, 120.0, 64.0)
put("u_iso", 105.0, 112.0, 90)                  # OCP isolator straddles the SELV band edge
put("u_vsense", 92.0, 112.0, 90)               # AMC1311 straddles too
# LS bias, SN6507 and LS monitor (LEG_RET domain) near PS2
pack(group("bias_ls", "monitor_ls", "bias_driver", "bias_rclk", "bias_rlim", "bias_css", "bias_rsr",
           "bias_cin", "bias_chf", "bias_rsn1", "bias_rsn2", "bias_csn1", "bias_csn2",
           exclude=("monitor_ls.iso",)),
     122.0, 62.0, 160.0, 100.0, gap=0.5)
put("monitor_ls.iso", 150.0, 112.0, 90)
# Supplies
put("ps_gate", 150.0, 30.0, 0)
put("ps_selv", 200.0, 120.0, 0)
# Mains along the rear edge, right part
put("j_mains", 283.0, 7.0, 0)
put("f1", 255.0, 5.5, 0)
put("rv1", 270.0, 26.0, 0)
put("cx1", 240.0, 22.0, 0)
put("l1", 205.0, 24.0, 0)
put("cx2", 175.0, 13.0, 0)
pack(group("cy1", "cy2", "rb1a", "rb1b"), 160.0, 40.0, 190.0, 58.0)
pack(group("link_pos", "link_neg"), 125.0, 2.0, 172.0, 13.0)
put("c_bus1", 225.0, 60.0, 0)
put("tvs_bus", 186.0, 66.0, 0)
put("line_zc.opto", 232.0, 112.0, 90)
pack(group("line_zc.r1", "line_zc.r2", "line_zc.r3", "line_zc.r4"), 225.0, 90.0, 245.0, 100.0)
# Tank
put("c_bus2", 268.0, 60.0, 90)
put("t_ct", 255.0, 112.0, 0)
put("c_res1", 248.0, 90.0, 0)
put("c_res2", 196.0, 90.0, 0)
put("c_res3", 196.0, 112.0, 0)
pack(group("r_crb1", "r_crb2", "r_crb3", "r_crb4", "r_bus1", "r_bus2", "j_coil", "j_coil_return",
           "c_ct_burden", "r_ct_burden", "r_ct_series", "d_ct_hi", "d_ct_lo", "j_tco", "j_pe"),
     160.0, 62.0, 188.0, 117.0)

missing = sorted(set(PARTS) - set(POSE))
if missing:
    raise SystemExit(f"{len(missing)} unplaced: {missing}")

# courtyard centre -> footprint origin
out = {}
for path, (cx, cy, ang) in POSE.items():
    p = PARTS[path]
    a = math.radians(ang)
    # KiCad rotates by -angle in the y-down frame
    ox = p["ox"] * math.cos(a) + p["oy"] * math.sin(a)
    oy = -p["ox"] * math.sin(a) + p["oy"] * math.cos(a)
    out[path] = [round(cx - ox, 3), round(cy - oy, 3), ang]
(HERE.parent / "placement.json").write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
print(len(out), "poses")
