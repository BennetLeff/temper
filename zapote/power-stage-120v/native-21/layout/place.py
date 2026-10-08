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


def _box(path, cx, cy, ang, gap):
    w, h = size(path, ang)
    return (cx - w / 2 - gap / 2, cy - h / 2 - gap / 2, cx + w / 2 + gap / 2, cy + h / 2 + gap / 2)


def relocate(path, x0, y0, x1, y1, ang=0.0, gap=GAP, step=0.25):
    """Move an already-placed part to the first spot in the rectangle (scanning rows top-down)
    whose courtyard clears every other placed courtyard by `gap`."""
    others = [_box(q, *POSE[q][:2], POSE[q][2], gap) for q in POSE if q != path]
    w, h = size(path, ang)
    y = y0 + h / 2
    while y + h / 2 <= y1 + 1e-9:
        x = x0 + w / 2
        while x + w / 2 <= x1 + 1e-9:
            b = _box(path, x, y, ang, gap)
            if all(b[2] <= o[0] or o[2] <= b[0] or b[3] <= o[1] or o[3] <= b[1] for o in others):
                POSE[path] = (round(x, 3), round(y, 3), ang)
                return
            x += step
        y += step
    raise ValueError(f"no room for {path} in ({x0},{y0})-({x1},{y1})")


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
put("br1", 94.4, 4.6)          # right after Q2: row 1.7 .. 107.0
GATE = {k: Q[k] - 5.45 for k in Q}           # gate pin x (TO-247 pin 1)
for leg, q, side in (("leg_b", "leg_b.q_high", "h"), ("leg_b", "leg_b.q_low", "l"),
                     ("leg_a", "leg_a.q_high", "h"), ("leg_a", "leg_a.q_low", "l")):
    g = GATE[q]
    put(f"{leg}.c_snub_{side}", Q[q] + 2.73, 9.7)
    put(f"{leg}.r_g{side}", g, 12.6, 90)
    put(f"{leg}.r_g{side}_pd", g - 2.7, 12.1, 90)
    # F6 network directly under the gate: PMEG (anode at gate) + 1 ohm to OUT, Cgs to source.
    put(f"{leg}.doff_{side}", g + 4.6, 17.9)
    put(f"{leg}.roff_{side}", g + 11.0, 17.9)
    put(f"{leg}.cgs_{side}", g + 1.0, 21.8)
put("r_shunt", 38.5 + 0.0, 12.6, 270)          # between the low-side sources
# HF film row (moved 6 mm down for the F6 row; C41 pulled in from the edge)
put("c_hf_b2", 9.9, 28.2)
put("c_hf_b1", 31.7, 28.2)
put("c_hf_a1", 53.5, 28.2, 180)
put("c_hf_a2", 75.3, 28.2, 180)

# ---------------- drivers, HOT row facing the gates (rot 90) ------------------
DRV = {"leg_b": 33.0, "leg_a": 80.0}
for leg, x in DRV.items():
    put(f"{leg}.driver", x, 51.0, 90)
# Reservoir banks: HS (channel A, left end of the HOT row) and LS (channel B, right end).
BANK = {"leg_b.bias_h": (13.0, 33.6), "leg_b.bias_l": (39.0, 33.6),
        "leg_a.bias_h": (60.0, 33.6), "leg_a.bias_l": (86.0, 33.6)}
# Explicit 14.4 x 12 mm bank template (courtyard centres relative to the bank's top-left);
# HF parts (100 nF, 1 uF) on the side facing the driver pins, bulk 220 uF + damping behind.
# The 6.3 mm can's 3D body overhangs its courtyard by ~0.2 mm on both sides: cbulk at dy 3.5 and
# clocal at dy 9.15 leave ~0.1 mm body-box clearance to the film caps above and the 1210s below
# (body_collisions.py on the routed STEP).
BANK_TEMPLATE = {"cbulk": (4.85, 3.5, 0), "rdamp": (11.0, 2.4, 90), "rbleed": (13.6, 1.6, 90),
                 "clocal1": (2.4, 9.15, 0), "clocal2": (7.4, 9.15, 0), "cmid1": (11.6, 6.0, 0),
                 "cmid2": (11.6, 8.0, 0), "chf1": (11.3, 10.0, 0), "chf2": (13.4, 10.0, 0),
                 "chf3": (11.3, 11.4, 0), "chf4": (13.4, 11.4, 0)}
for b, (x, y) in BANK.items():
    for part, (dx, dy, ang) in BANK_TEMPLATE.items():
        # LS banks sit right of their driver: mirror so the 100 nF / 1 uF parts face the pins
        put(f"{b}.{part}", x + (14.4 - dx if b.endswith("bias_l") else dx), y + dy, ang)
# Driver-local parts that stay on the HOT side near each driver (LS caps)
for leg, x in DRV.items():
    pack(group(f"{leg}.c_ls", f"{leg}.c_ls_bulk"), x + 14.0, 51.0, x + 20.5, 58.5)

# ---------------- SELV side of each driver (tongue) ---------------------------
for leg, x in DRV.items():
    pack(group(f"{leg}.c_vcci", f"{leg}.permit_fet", f"{leg}.r_permit", f"{leg}.r_permit_pd",
               f"{leg}.r_dis_pu", f"{leg}.r_dt", f"{leg}.dis_or", f"{leg}.c_dis_or", f"{leg}.r_driver_dis"),
         x - 5.0, 59.0, x + 5.0, 82.0)

# ---------------- HS bias islands (left of each driver tongue) ----------------
put("bias_hb.transformer", 10.2, 61.2, 270)   # primary (LOW) up toward the core
pack(group("bias_hb", exclude=("bias_hb.monitor.iso", "bias_hb.monitor.civcc2")), 0.8, 68.9, 19.4, 118.0, gap=1.0)
put("bias_hb.monitor.iso", 25.6, 110.0, 0)
put("bias_hb.monitor.civcc2", 35.0, 112.0, 90)       # straddles the leg-B tongue's left edge
put("bias_ha.transformer", 56.5, 66.2, 270)   # secondary down into the island
pack(group("bias_ha", exclude=("bias_ha.monitor.iso", "bias_ha.monitor.civcc2")), 46.4, 73.9, 64.6, 118.0, gap=0.7)
put("bias_ha.monitor.iso", 70.6, 110.0, 0)
put("bias_ha.monitor.civcc2", 76.0, 121.0, 0)       # straddles the leg-A tongue's left edge
# Leg-A -2 V bleed resistor beside U1.16's column, clear of the decoupling cluster: P_HA reaches it
# straight up from U1.16 and its SW_A end meets the feed from above, so neither cages the cluster.
POSE["leg_a.bias_h.rbleed"] = (75.6, 34.6, 90.0)    # just below C39's courtyard (y 33.0)
# Each TPS7A47's NR/SS cap beside its pin 14 (the packer had put it ~35 mm away, at the island
# foot); the rail monitor's 5 V LDO that sat there moves to the next free spot in its island.
for leg, isl in (("hb", (0.8, 68.9, 19.4, 118.0)), ("ha", (46.4, 73.9, 64.6, 118.0))):
    lx, ly, _ = POSE[f"bias_{leg}.split.ldo"]
    POSE[f"bias_{leg}.monitor.ldo5"] = (-100.0, -100.0, 0.0)
    POSE[f"bias_{leg}.split.cnr"] = (lx + 4.9, ly - 0.65, 0.0)     # pad 1 faces pin 14
    for gap, ang in ((0.7, 0.0), (0.7, 90.0), (0.5, 0.0), (0.5, 90.0), (0.4, 0.0), (0.4, 90.0)):
        try:
            relocate(f"bias_{leg}.monitor.ldo5", *isl, ang=ang, gap=gap)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"bias_{leg}.monitor.ldo5: no room in its island")

# ---------------- SELV island (bottom band + board tongue) --------------------
put("j_selv", 45.0, 182.0)
pack(group("u_ct_pos", "u_ct_neg", "u_ct_zc", "c_ct_pos", "c_ct_neg", "c_ct_zc", "r_ct_hi_top", "r_ct_hi_bot",
           "r_ct_lo_top", "r_ct_lo_bot", "r_ct_bias_top", "r_ct_bias_bot", "c_ct_bias", "r_ct_mon",
           "u_fault_or", "c_fault_or", "bias_or", "bias_c_or", "u_bias_flt", "r_bias_flt", "c_bias_flt",
           "c_bias_flt_vcc", "line_zc.buffer", "line_zc.cbuffer", "line_zc.pullup", "r_fe",
           "c_iso2", "c_vs2"),
     2.0, 128.0, 89.0, 170.0)

# ---------------- remaining zones are packed for the first cut ----------------
# HOT protection (OCP/OVP/HOT5, Kelvin island) below the BR1-gate copper lanes (y < 51), above the LS block
pack(group("u_ldo", "c_ldo_in", "c_ldo_out", "c_v15", "u_ref", "r_ref_bias", "u_ocp", "c_ocp_vcc", "r_ocp_ref",
           "r_ocp_sense", "c_ocp_node", "r_th_top", "r_th_bot", "c_th", "u_ovp", "c_ovp_vcc", "r_ovp_top",
           "r_ovp_bot", "c_ovp_th", "u_nand", "c_nand_vcc", "c_iso1", "u_hot5_uv", "r_hot5_uv_top",
           "r_hot5_uv_bot", "r_hot5_uv_pull", "c_hot5_uv", "u_hot5_schmitt", "c_hot5_schmitt",
           "c_vs1", "c_div", "r_div_bot"),
     101.0, 51.4, 121.5, 75.0, gap=1.1)
# ---- barrier isolators for protection on the SELV band edge (HOT above, SELV below y 128)
put("u_vsense", 104.0, 121.0, 270)               # AMC1311
put("u_iso", 113.0, 121.0, 270)                 # OCP ISO7710
# ---------------- rear band (connectors exit the enclosure rear) -------------
# Bring-up links: 2 x 2 block right of BR1 at the 13.0 mm strap pitch (ASSEMBLY.md), straps
# horizontal: J9 (RECT_N) - J10 (HV_RET) on the edge row, J7 (RECT_P) - J8 (BUS_P) below.
# RECT_N reaches J9 on In2 straight from BR1.4, RECT_P reaches J7 on In1 from BR1.1 (under BR1);
# BUS_P (In2) meets J8 from the trunk below; HV_RET (In1) reaches J10 round J8's right side.
put("link_neg.terminal_rect", 130.0, 6.5)
put("link_neg.terminal_bus", 143.0, 6.5)
put("link_pos.terminal_rect", 130.0, 19.5)
put("link_pos.terminal_bus", 143.0, 19.5)
put("ps_gate", 186.5, 14.0)                     # rear band; N_FILT pin on the mains lane, LS rails down
put("j_tco", 217.5, 6.5)
put("j_pe", 160.0, 134.5, 90)
put("f1", 244.5, 6.0, 180)    # line clip toward J1, load clip toward L1
put("j_mains", 283.5, 7.2)
# ---------------- tank block, next to the core --------------------------------
# Resonant bank stacked right of the SW_A column: RES_A pins left (x 155.25), SW_B pins right
# (x 197.75). Coil terminals beside T1: J5 (RES_A) over J2 (COIL_FEED), 15 mm apart (5 mm tank rule).
put("c_res1", 176.5, 58.0)
put("c_res2", 176.5, 86.4)
put("c_res3", 176.5, 110.9)
put("t_ct", 135.0, 110.0)                      # primary sw_a -> coil_feed; secondary on the SELV band
put("j_coil_return", 132.0, 70.5)
put("j_coil", 132.0, 85.5)
pack(group("c_ct_burden", "r_ct_burden", "r_ct_series", "d_ct_hi", "d_ct_lo"), 116.0, 129.0, 142.0, 139.5)
# tank bleed chain RES_A -> SW_B across the top of C21 (each tap its own group, 5 mm tank rule)
for i, n in enumerate(("r_crb1", "r_crb2", "r_crb3", "r_crb4")):
    put(n, 158.0 + 10.0 * i, 41.0)
# ---------------- mains block, far end ----------------------------------------
put("rv1", 276.5, 28.0, 270)   # L_F pin up toward the fuse, AC_N_IN down
put("cx1", 249.5, 19.5)
put("rb1a", 226.0, 15.0)
put("rb1b", 226.0, 23.0)
put("l1", 237.0, 43.5)
put("cx2", 274.5, 49.5)
# Bottom-right: PS1's SELV end faces left onto an SELV/PE spur (x 205-216.5) that joins the
# bottom SELV corridor (y >= 131) back to the SELV band; its mains end (right) is fed under
# C5. The Y capacitors and the LINE_ZC opto straddle the spur: PE / SELV pins on it, mains
# pins 9-10 mm to the right; the opto's resistor string sits between C5 and D3.
put("cy1", 220.0, 102.8, 180)
put("cy2", 220.0, 109.1, 180)
put("c_bus1", 224.0, 75.6)
put("c_bus2", 267.0, 84.0)
put("tvs_bus", 264.0, 106.0)
put("ps_selv", 233.0, 126.0, 180)               # SELV pins left (x 210.8), mains pins right
put("line_zc.opto", 220.0, 95.0, 180)
# String L_FILT-r1-r2-LED-r3-r4-N_FILT folded so each LED node lands beside its opto pin: the
# LED2 half (r3, r4) on the upper row by U36.2, the LED1 half (r2, r1) on the lower row by U36.1;
# L_FILT enters r1 from below (PS1 feed), N_FILT enters r4 from above.
put("line_zc.r1", 241.5, 101.5, 180)
put("line_zc.r2", 233.0, 101.5, 180)
put("line_zc.r3", 233.0, 95.5, 0)
put("line_zc.r4", 241.5, 95.5, 0)
# LS bias, SN6507 and LS monitor (N_LS / LEG_RET domain) beside PS2
pack(group("bias_ls", "monitor_ls", "bias_driver", "bias_rclk", "bias_rlim", "bias_css", "bias_rsr",
           "bias_cin", "bias_chf", "bias_rsn1", "bias_rsn2", "bias_csn1", "bias_csn2",
           exclude=("monitor_ls.iso", "monitor_ls.civcc2")), 101.0, 75.6, 121.5, 112.5, gap=0.55)
# 3 mm right of the first cut: its HOT pins set the right side of the SELV neck below the leg-A
# pocket (island A's barrier sets the left); at x 92 that neck was 1.3 mm, now ~4.3 mm.
put("monitor_ls.iso", 95.0, 121.0, 270)
put("monitor_ls.civcc2", 95.0, 131.0, 0)
put("r_bus1", 249.5, 106.0, 180)
put("r_bus2", 283.0, 106.0)
# bus divider for AMC1311: 4 x 470 k chain, taps 9 mm apart (vertical), in the corridor between
# U1's SELV moat (x >= 92.5) and the LOW blocks; top end via to BUS_P on the In2 trunk
for i, n in enumerate(("r_div1", "r_div2", "r_div3", "r_div4")):
    put(n, 95.2, 64.0 + 9.0 * i, 270)

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
