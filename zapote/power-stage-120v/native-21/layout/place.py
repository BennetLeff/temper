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
    pack(group(f"{leg}.c_vcci", f"{leg}.r_permit", f"{leg}.r_permit_pd",
               f"{leg}.r_dt", f"{leg}.dis_or", f"{leg}.c_dis_or", f"{leg}.r_driver_dis"),
         x - 5.0, 59.0, x + 5.0, 82.0)
# Stage 22 (DECISIONS 27): Q1 / Q4 and R8 / R16 are deleted (DIS NAND); the surviving parts keep their stage-21b poses
# (the pack above would otherwise reflow them).
STAGE22_KEEP = {
    "leg_a.r_permit": (80.175, 68.165, 0.0), "leg_a.r_permit_pd": (76.525, 70.315, 0.0), "leg_a.r_dt": (76.525, 68.165, 0.0),
    "leg_a.dis_or": (77.095, 60.745, 0.0), "leg_a.c_dis_or": (76.525, 63.865, 0.0), "leg_a.r_driver_dis": (80.175, 66.015, 0.0),
    "leg_b.r_permit": (33.175, 68.165, 0.0), "leg_b.r_permit_pd": (29.525, 70.315, 0.0), "leg_b.r_dt": (29.525, 68.165, 0.0),
    "leg_b.dis_or": (30.095, 60.745, 0.0), "leg_b.c_dis_or": (29.525, 63.865, 0.0), "leg_b.r_driver_dis": (33.175, 66.015, 0.0),
}
for path, pose in STAGE22_KEEP.items():
    POSE[path] = pose

# ---------------- HS bias islands (left of each driver tongue) ----------------
# Stage 14: the isolated bias module takes the transformer's spot, rotated 270 so its primary row
# (pins 1-18, V24_RAW / N_LS / EN_HS) faces up to the trunk drops and its secondary row (19-36) faces
# down into the island. Its primary decoupling sits above the primary row (DECOUPLE below).
HS_PRIMARY = ("cin1", "cin2", "cinhf", "cavin")
put("bias_hb.iso", 10.2, 61.2, 270)
pack(group("bias_hb", exclude=("bias_hb.monitor.iso", "bias_hb.monitor.civcc2", "bias_hb.iso")
           + tuple(f"bias_hb.{c}" for c in HS_PRIMARY)), 0.8, 68.9, 19.4, 118.0, gap=1.0)
put("bias_ha.iso", 56.5, 66.2, 270)
pack(group("bias_ha", exclude=("bias_ha.monitor.iso", "bias_ha.monitor.civcc2", "bias_ha.iso")
           + tuple(f"bias_ha.{c}" for c in HS_PRIMARY)), 46.4, 73.9, 64.6, 118.0, gap=0.7)
# Leg-A -2 V bleed resistor beside U1.16's column, clear of the decoupling cluster: P_HA reaches it
# straight up from U1.16 and its SW_A end meets the feed from above, so neither cages the cluster.
POSE["leg_a.bias_h.rbleed"] = (75.6, 34.6, 90.0)    # just below C39's courtyard (y 33.0)
# (Stage 14: the HS TPS7A47s are gone; the rail monitor's 5 V LDO keeps its packed spot.)

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
# Stage 21 (DECISIONS 25): the J7-J10 bring-up link studs are gone; BR1.1 / BR1.4 sit on the BUS_P (In2) and
# HV_RET (In1) trunk planes directly. Floating bring-up leaves BR1 unfitted and lands the bench leads in its holes.
put("ps_gate", 186.5, 14.0)                     # rear band; N_FILT pin on the mains lane, LS rails down
put("j_tco", 218.2, 7.6, 90)    # B2P3-VH (7.92 mm pitch, review M7) stands vertical between PS2 and F1 / R1
put("j_pe", 160.0, 134.5, 90)
put("f1", 252.0, 7.25, 0)     # Class CC 10x38 clips (stage 12): pads 1 (ac_l_in) toward J1, pads 2 (l_f) toward L1
put("j_mains", 283.5, 7.2)
# ---------------- tank block, next to the core --------------------------------
# Resonant bank (stage 13): 5 x TDK B32654A1104K000 radials, P27.5, RES_A pins at x 163.0 and SW_B pins at
# x 190.5. Rows are bounded by copper: pin 1 >= 5 mm (tank rule) below the sw_b band (B.Cu edge y 47.5),
# no pin within 5 mm + pad of the In1 n_ls / v24_raw runs at y 74.8-76.2, and the last pad >= 8 mm from
# the SELV line_zc_raw run (B.Cu, y 121.1). Courtyards are +/-7.2 (0.2 beyond the maximum body), pitch >= 14.5.
# Coil terminals beside T1: J5 (RES_A) over J2 (COIL_FEED), 15 mm apart.
for i, y in enumerate((53.2, 67.7, 82.5, 97.0, 111.5), 1):
    put(f"c_res{i}", 176.75, y)
put("t_ct", 135.0, 110.0)                      # primary sw_a -> coil_feed; secondary on the SELV band
put("j_coil_return", 132.0, 70.5)
put("j_coil", 132.0, 85.5)
pack(group("c_ct_burden", "r_ct_burden", "r_ct_series", "d_ct_hi", "d_ct_lo"), 116.0, 129.0, 142.0, 139.5)
# tank bleed chain RES_A -> SW_B across the top of C21 (each tap its own group, 5 mm tank rule)
for i, n in enumerate(("r_crb1", "r_crb2", "r_crb3", "r_crb4")):
    put(n, 158.0 + 10.0 * i, 41.0)
# ---------------- mains block, far end ----------------------------------------
put("rv1", 276.5, 28.0, 270)   # L_F pin up toward the fuse, AC_N_IN down
put("cx1", 249.5, 20.1)       # +0.6 mm (stage 12) to clear F1's 10x38 courtyard; 3.4 mm kept to the B.Cu ac_n_in track
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
# Stage 14: the bus clamp is two P600 TVS in series (ALT-D3 4.2): D3 pads (254.00 / 266.70), D17 pads
# (270.54 / 283.24), 1.3 mm right of the study's sketch so the two courtyards do not overlap; R4
# moves up-right to (286.5, 103.5) to clear D17's hv_ret pad.
put("tvs_bus", 260.35, 106.0)
put("tvs_bus_b", 276.89, 106.0)
# Stage 38 (candidate 23, DECISIONS 47 item 1): PS1 (ps_selv, was here at (233.0, 126.0, 180)) is deleted; its area
# stays clear (c23-supply-topology/README.md section 3: the freed area).
put("line_zc.opto", 220.0, 95.0, 180)
# String L_FILT-r1-r2-LED-r3-r4-N_FILT folded so each LED node lands beside its opto pin: the
# LED2 half (r3, r4) on the upper row by U36.2, the LED1 half (r2, r1) on the lower row by U36.1;
# L_FILT enters r1 from below (PS1 feed), N_FILT enters r4 from above.
put("line_zc.r1", 241.5, 101.5, 180)
put("line_zc.r2", 233.0, 101.5, 180)
put("line_zc.r3", 233.0, 95.5, 0)
put("line_zc.r4", 241.5, 95.5, 0)
# LS bias, SN6507 and LS monitor (N_LS / LEG_RET domain) beside PS2
pack(group("bias_ls", "monitor_ls", "r_en_top", "r_en_bot",
           exclude=("monitor_ls.iso", "monitor_ls.civcc2")), 101.0, 75.6, 121.5, 112.5, gap=0.55)
# 3 mm right of the first cut: its HOT pins set the right side of the SELV neck below the leg-A
# pocket (island A's barrier sets the left); at x 92 that neck was 1.3 mm, now ~4.3 mm.
put("hb.iso", 95.0, 121.0, 270)        # stage 30: U32 carries the heartbeat (was the LS monitor's isolator)
put("hb.civcc2", 95.0, 131.0, 0)
put("r_bus1", 249.5, 106.0, 180)
put("r_bus2", 288.0, 103.5, 270)   # busbleed_mid pad up (y 102.0), hv_ret pad down (y 105.0) beside D17.2
# bus divider for AMC1311: 4 x 470 k chain, taps 9 mm apart (vertical), in the corridor between
# U1's SELV moat (x >= 92.5) and the LOW blocks; top end via to BUS_P on the In2 trunk
for i, n in enumerate(("r_div1", "r_div2", "r_div3", "r_div4")):
    put(n, 95.2, 64.0 + 9.0 * i, 270)

# ---------------- decoupling at the supply pins (independent review 2026-10-08, B1 / M1) ---------
# The block packs put these caps 12-53 mm from the pins they serve. Each is lifted out after the
# packs (the rest of each block keeps its place) and put at the nearest legal spot to its target,
# on its pin's side of the barrier. Targets: just outside the package, beside the supply pin.
def nearest_free(path, tx, ty, reach=8.0, gap=0.4, angs=(0.0, 90.0), step=0.25, rect=(1.0, 1.0, 289.0, 189.0), avoid=()):
    others = [_box(q, *POSE[q][:2], POSE[q][2], gap) for q in POSE if q != path]
    others = [o for o in others if o[2] > tx - reach - 6 and o[0] < tx + reach + 6 and o[3] > ty - reach - 6 and o[1] < ty + reach + 6]
    others += list(avoid)
    best = None
    n = int(reach / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            d = math.hypot(i, j) * step
            if d > reach or (best and d >= best[0]):
                continue
            x, y = tx + i * step, ty + j * step
            for a in angs:
                b = _box(path, x, y, a, gap)
                if b[0] < rect[0] or b[1] < rect[1] or b[2] > rect[2] or b[3] > rect[3]:
                    continue
                if all(b[2] <= o[0] or o[2] <= b[0] or b[3] <= o[1] or o[3] <= b[1] for o in others):
                    best = (d, x, y, a)
                    break
    if best is None:
        raise ValueError(f"no room for {path} near ({tx}, {ty})")
    POSE[path] = (round(best[1], 3), round(best[2], 3), best[3])


# UCC21550 VDD-VSS decoupling (review B1; stage 9). U1 / U2 at x 80 / 33: VDDA 16 / OUTA 15 / VSSA 14
# at x 75.56 / 76.83 / 78.09 and VDDB 11 / OUTB 10 / VSSB 9 at 81.91 / 83.17 / 84.44, on the y 46.1
# HOT row; the package straddles the 8 mm barrier, so caps go on the HOT side (above the row).
# Each channel gets a stack of 0805s centred on its output pin: the pads (1.9 mm apart) sit over
# VDDx and VSSx (2.53 mm apart), the 0.9 mm pad gap passes a 0.3 mm OUTx neck, and the loop is
# ~3 mm with no vias. (Stage 8 put the caps beside the stack and left a 30 mm VSSA return: no n_h
# via fits under U1, where LOW-group In1 runs pass within the 3.2 mm HOT-group spacing.)
# Stack pitch 2.1 mm (0805 courtyard 2.05); the lowest courtyard clears U1's (y 45.01). The HS and
# LS stacks' facing pads are 3.44 mm apart (>= 3.2 mm between HOT groups). The LS 10 uF (1210)
# keeps its block spot (no free spot near VDDB is closer; see DECISIONS.md).
STACK = {"c_hs": (76.83, 43.95), "c_hs_1u": (76.83, 41.85), "c_hs_bulk": (76.83, 39.75),
         "c_ls": (83.17, 43.95), "c_ls_1u": (83.17, 41.85)}
for leg, dx in (("leg_a", 0.0), ("leg_b", -47.0)):
    for part, (x, y) in STACK.items():
        POSE[f"{leg}.{part}"] = (round(x + dx, 3), y, 0.0)
DECOUPLE = []
DECOUPLE += [("c_vs1", 106.6, 113.4),                   # AMC1311 U4 VDD1 (pin 1, 105.9 / 115.7)
             ("c_vs1_1u", 100.5, 111.0, (98.0, 98.0, 122.0, 116.0)),   # its 1 uF (SBAS786C s.10), HOT side; nearest free 0805 spot, ~8 mm (C28's 100 nF stays the HF cap)
             ("c_vs2", 106.6, 128.6),                   # U4 VDD2 (pin 8, 105.9 / 126.3): the 100 nF goes first, at the pin
             ("c_vs2_1u", 106.6, 131.0, (98.0, 126.2, 122.0, 142.0)),  # VDD2's 1 uF, SELV side, after its 100 nF
             ("c_iso1", 115.5, 113.6),                  # ISO7710 U9 VCC1 (pin 3, 114.9 / 116.1)
             ("c_iso2", 115.5, 128.4),                  # U9 VCC2 (pin 14, 114.9 / 125.9)
             ("hb.civcc1", 97.5, 113.6),                # U32 VCC1 (pin 3, 96.9 / 116.1)
             ("hb.civcc2", 97.5, 128.4)]                # U32 VCC2 (pin 14, 96.9 / 125.9)
# Stage 14 bias modules (rot 270, measured from the build: primary row at y - 4.97 with PVIN / AVIN
# (7 / 6) at x + 1.6 / + 2.3 and PGND either side; secondary row at y + 4.97 with VOUT+ (28 / 29) at
# x + 0.3 / + 1.0 and FBVOUT (33 / 34) at x + 3.6 / + 4.2).
STAGE14_TARGETS = []
for b, (mx, my) in (("bias_ha", (56.5, 66.2)), ("bias_hb", (10.2, 61.2))):
    STAGE14_TARGETS += [(f"{b}.cinhf", mx + 2.0, my - 7.0), (f"{b}.cavin", mx + 3.7, my - 7.0),
                        (f"{b}.cin1", mx - 0.8, my - 8.6), (f"{b}.cin2", mx + 4.6, my - 8.8),
                        (f"{b}.cfb", mx + 4.0, my + 7.0), (f"{b}.rfbb", mx + 5.7, my + 7.0),
                        (f"{b}.rfbt", mx + 2.2, my + 8.8)]
STAGE14_TARGETS += [("bias_ha.ren_top", 63.5, 61.0), ("bias_ha.ren_bot", 63.5, 63.4),   # beside U41 CTRL (pin 4, x 60.1)
                    ("bias_hb.ren_top", 18.4, 57.0), ("bias_hb.ren_bot", 18.4, 59.4)]   # beside U42 CTRL (pin 4, x 13.8)
POSE.pop("j_tco", None)
nearest_free("j_tco", 218.2, 7.6, angs=(90.0,), rect=(211.0, 1.0, 226.0, 30.0))
for path, *_ in DECOUPLE:
    POSE.pop(path, None)
# The four gate-drive outputs run straight up 0.6 mm lanes from the driver pins to the gate
# resistors (stage-5 copper). They are part of the FEM-extracted gate loops: keep every
# relocated part off them (x band +-0.9 mm round each trace) so that copper is not disturbed.
OUT_LANES = [(76.1, 17.0, 77.9, 46.5), (74.2, 13.5, 76.0, 21.0),            # leg A OUTA
             (81.1, 33.8, 83.6, 46.5),                                        # leg A OUTB to its In1 via
             (28.9, 32.0, 30.8, 46.5), (11.7, 20.0, 30.8, 33.8),              # leg B OUTA
             (35.0, 20.6, 36.9, 46.5)]                                        # leg B OUTB
for path, tx, ty, *rect in DECOUPLE:
    nearest_free(path, tx, ty,
                 rect=rect[0] if rect else (1.0, 1.0, 289.0, 189.0), avoid=OUT_LANES)

# Stage 14: every part that survives from stage 13b keeps its stage-13b pose (the packs above would
# otherwise re-pack the LS block and both HS islands round the removed parts and invalidate their
# copper). Only the new parts and the explicitly moved ones (modules, bus clamp, R4) take new poses;
# the new ones go to the nearest free spot by their pins.
OLD = json.loads((HERE / "placement-stage13b.json").read_text())
STAGE14_PLACED = {"bias_ha.iso", "bias_hb.iso", "tvs_bus", "tvs_bus_b", "r_bus2"} | {t[0] for t in STAGE14_TARGETS}
for path, (x, y, ang) in OLD.items():
    if path in PARTS and path not in STAGE14_PLACED:
        q = PARTS[path]
        a = math.radians(ang)
        POSE[path] = (round(x + q["ox"] * math.cos(a) + q["oy"] * math.sin(a), 3),
                      round(y - q["ox"] * math.sin(a) + q["oy"] * math.cos(a), 3), ang)
for path, tx, ty in STAGE14_TARGETS:
    POSE.pop(path, None)
for path, tx, ty in STAGE14_TARGETS:
    nearest_free(path, tx, ty, avoid=OUT_LANES)

# Stage 16 (DECISIONS 16): the blower-supply mains tap beside PS1's AC pins, the only legal spot
# (stage16-blower-supply/tap_spot.py: 9.3 mm to SELV / PE / H1's screw head, 3.4 mm to HOT, 8.8 mm to
# other mains groups). No part moves.
put("f_blw", 269.35, 117.6, 0)   # stage 28 (DECISIONS 30): UMT-H 1.5 kA between PS1, D17 and J11 (0.3 mm); F2.1 (l_filt) 3.3 mm from PS1.2 (n_filt)
put("r_blw", 284.115, 116.5, 0)  # stage 28: AC05 0.15 ohm limiter upright, pad 1 at (282.9, 116.5); 19 mm from H1
put("j_blw_ac", 266.5, 125.8, 0)

# Stage 19 (DECISIONS 19, engineering review N1): each IC's dedicated 100 nF bypass cap was parked 11-70 mm away
# (the v3v3 row at x 41-75 / the monitor and HOT5 rows) after the ICs moved. The caps move; none is added.
# Courtyard centres, KiCad angle (pad 1 = supply net). SELV logic row: y 127.1 puts each cap's courtyard
# 0.125 mm above its IC's (top y 128.0), supply pad over pin 5 (angle 180, pad 1 right).
# native-21/layout/gates/bypass_check.py reports the distances; bypass_spots.py found the free spots.
STAGE19_MOVES = {
    "line_zc.cbuffer": (9.248, 127.1, 180.0),      # U24 pin 5 at x 10.0225
    "c_bias_flt_vcc": (14.038, 127.1, 180.0),      # U40 pin 5 at x 14.8125
    "c_ct_neg": (18.828, 127.1, 180.0),            # U11 pin 5 at x 19.6025
    "c_ct_pos": (23.618, 127.1, 180.0),            # U10 pin 5 at x 24.3925
    "c_ct_zc": (28.408, 127.1, 180.0),             # U12 pin 5 at x 29.1825
    "c_fault_or": (33.198, 127.1, 180.0),          # U13 pin 5 at x 33.9725
    # HOT5 Schmitt U15 (pin 5 hot5 at 104.2325, 52.195; pin 3 ocp_kelvin_p at 101.9575, 54.095), left of it:
    # above it (y 50.4) the pads sit 2.4-2.6 mm from the sw_a F.Cu pour, inside the 3.2 mm HOT-group spacing
    "c_hot5_schmitt": (100.03, 54.2, 270.0),
    # LM339 rail monitors: supply pin 3 (left column), return pin 12 (right column) cannot both be reached;
    # the cap sits at pin 3 and its return goes by via to the In1 n_* plane
    "monitor_ls.cmonitor": (100.07, 78.2, 90.0),           # U29 pin 3 at (102.27, 78.955)
    "bias_ha.monitor.cmonitor": (45.47, 76.48, 90.0),      # U30 pin 3 at (47.67, 77.255)
    "bias_hb.monitor.cmonitor": (2.07, 67.25, 90.0),       # U31 pin 3 at (2.07, 72.255): board edge, no room beside it; 2 legal poses
}
for path, pose in STAGE19_MOVES.items():
    POSE[path] = pose

# Stage 19 PI1 (DECISIONS 19, review PI1; RECOM R24C2T25/R Rev.1-2024 p.13: "place the capacitors between pin 28, 29
# (VOUT+) and pins 19-25, 30-31, 35-36 (VOUT-) ... close to the IC"). Each module's own output pair (HsSplit cout1
# 10 uF + chf 100 nF) moves from the split/monitor area (25.6 / 26.5 mm) to the VOUT+ pins: the 1210 vertical with
# its p pad under pin 28, the 0603 horizontal under pins 29-31, courtyards 0.05 mm below the module's (y 72.995 /
# 67.995). The driver-local reservoirs (C10 / C11 / C145, C17 / C18 / C147 and the bias_h clusters) are separate
# parts at the drivers and stay. The FB network (rfbt / cfb) steps aside; U42's FBVOUT pins drop to a via (RECOM:
# "use a via near the FBVout- pin to route the feedback connection through a different layer") because U31 holds
# the 1210 0.35 mm further east than at U41. 08-manufacturing-package/native-21/stage19-pi-si/pi_distances19.py
# measures them.
STAGE19_PI = {
    "bias_ha.split.cout1": (55.93, 75.39, 270.0),     # C104: pad 1 (p_ha) at (55.93, 73.915), 2.88 mm from U41.28
    "bias_ha.split.chf": (59.15, 73.82, 0.0),         # C75: p_ha 58.375 (2.79 mm to U41.29), n_ha 59.925 (2.88 to U41.31)
    "bias_ha.rfbt": (59.15, 75.42, 0.0),              # R92: p_ha under C75.1, fbm east to the pin-34 stub
    "bias_ha.cfb": (61.6, 74.57, 270.0),              # C71: fbm on top, under FBVOUT+ / FBCOM
    "bias_hb.split.cout1": (9.985, 70.39, 270.0),     # C108: pad 1 (p_hb) at (9.985, 68.915), 2.79 mm from U42.28; U31 at x 8.29
    "bias_hb.split.chf": (13.205, 68.82, 0.0),        # C82: p_hb 12.43 (2.93 to U42.29), n_hb 13.98 (2.86 to U42.35)
    "bias_hb.cfb": (14.0, 70.42, 0.0),                # C72: fbm west, n_hb east
    "bias_hb.rfbt": (14.0, 72.02, 0.0),               # R94: p_hb west, fbm east
}
# Stage 19 PI2 (review PI2; TI TPS7A47 SBVS204 9.1: components "as near as practical to the respective LDO pin
# connections", in/out cap and GND returns "connected by a wide, component-side, copper surface"). U26 had U29 0.55 mm
# to its west and R31 / R35 1.1 mm above, so no cap fitted at its pins: it moves 3.185 mm east / 2.275 mm down into
# free board (C98 then fits above it, 5 mm clear of the RES_A F.Cu strip), C99 (OUT) takes its old west side,
# C98 (IN 15 / 16) the north-east corner, C64 (NR 14) the east side; an F.Cu n_ls pour joins the GND pins and the cap returns (patches21.add_stage19_pi).
STAGE19_PI.update({
    "bias_ls.ldo": (115.4, 81.05, 0.0),               # U26 (was 112.215, 78.775)
    "bias_ls.cout1": (110.23, 81.05, 270.0),          # C99: v15_ls (110.23, 79.575) 2.81 mm to OUT 1; n_ls 2.81 to GND 5
    "bias_ls.cin": (118.9, 76.165, 0.0),             # C98: v24_raw (117.425, 76.165) 2.62 mm to IN 16; pad 2 6.4 mm from RES_A (5.0)
    "bias_ls.cnr": (120.15, 80.4, 0.0),               # C64: ldo_nr (119.375, 80.4) 1.61 mm to NR 14 (EN 13 / IN 15 either side)
})
# Stage 19 SI2 (review SI2): U2's (leg-B driver) VCCI bypass C14 sat 8 mm below its VCCI / GND pins 3 / 4; it moves
# under them (UCC21550: "bypass ... as close to the VCCI pin as possible"), which also puts a v3v3-selv_gnd capacitor
# 2.4 mm from the pwm_hb F.Cu -> B.Cu via at U2.1 (the reference change at the driver input).
STAGE19_PI["leg_b.c_vcci"] = (31.075, 57.85, 0.0)   # C14: v3v3 (30.3, 57.85), selv_gnd (31.85, 57.85)
for path, pose in STAGE19_PI.items():
    POSE[path] = pose

# Stage 19b (DECISIONS 19b): one v3v3-selv_gnd 100 nF beside each of pwm_hb's four J4-side layer changes (its F.Cu
# runs sit over In1 v3v3, its B.Cu runs over In2 selv_gnd); spots from a free-pose scan of the stage-19 board,
# kept where both planes lie under the cap so its own plane vias land in them.
STAGE19B_XFER = {
    "c_ref_xfer_1": (41.85, 128.78, 0.0),    # C153: 2.72 mm from the via at (38.955, 127.075); the nearer spots lie
                                             # off the In1 v3v3 / In2 selv_gnd pours (SELV band edge, y < 126.5) or
                                             # leave no room for its plane vias (permit / bias_bad B.Cu, the 8 mm barrier)
    "c_ref_xfer_2": (57.05, 128.68, 0.0),    # C154: 1.12 mm from (55.155, 128.675)
    "c_ref_xfer_3": (58.05, 157.38, 0.0),    # C155: 1.13 mm from (56.155, 157.275)
    "c_ref_xfer_4": (57.85, 175.0, 0.0),     # C156: 1.12 mm from (55.955, 175.0)
}
for path, pose in STAGE19B_XFER.items():
    POSE[path] = pose

# Stage 19c (DECISIONS 19c; rubric review SI-08 / OTT-06 / BP-14): leg A's VCCI bypass C7 sat 8 mm below U1's
# VCCI / GND pins 3 / 4; it moves under them, as C14 under U2 in stage 19 (UCC21550: "as close to the VCCI pin as
# possible"), which puts a v3v3-selv_gnd capacitor within 3 mm of pwm_ha's and pwm_la's driver-input layer changes.
STAGE19C = {"leg_a.c_vcci": (78.075, 57.85, 0.0)}   # C7: v3v3 (77.3, 57.85), selv_gnd (78.85, 57.85)
for path, pose in STAGE19C.items():
    POSE[path] = pose

# Stage 21b (DECISIONS 26; rubric F8, 11-candidates/g06-g08-g10 P4): the OCP comparator's filter caps move from 11-15 mm
# away to the nearest legal spots beside U6 (gates/bypass_spots.py --rules on the stage-21 board: the isolation-group
# clearances, 3.2 mm to the bus_p divider R26, rule out the closer F.Cu spots), shrinking the node / threshold pickup
# loops. C30 (ocp_node 100 pF) 4.2 / 6.5 mm from U6.3 / U6.2 (was 12.3); C31 (ocp_thresh 1 nF) 6.1 / 7.1 mm (was 11.3).
STAGE21B = {"c_ocp_node": (99.76, 63.09, 270.0), "c_th": (102.93, 64.78, 180.0)}
for path, pose in STAGE21B.items():
    POSE[path] = pose

# Stage 27 (DECISIONS 29; 13-external-review FINDINGS #4): J1 becomes the Phoenix MKDS 5/2-9,5 (1714971, UL group B
# 30 A), 19.05 mm long against the MKDS 3's 10.2 mm. Its pin 1 (ac_l_in) goes to (274.6, 9.2) with the wire entry at the
# top edge and the courtyard at the former top / right extents; F1 moves 5.65 mm left (courtyard 0.7 mm from J3) and R1
# with R2 (one bleed pair, unchanged relative geometry) 0.9 mm down to clear F1's clip courtyard. Footprint origins (as placement-stage13b.json), converted like stage 14.
STAGE27_ORIGINS = {"j_mains": (274.6, 9.2, 0.0), "f1": (246.35, 7.25, 0.0), "rb1a": (226.0, 15.9, 0.0), "rb1b": (226.0, 23.9, 0.0)}
for path, (x, y, ang) in STAGE27_ORIGINS.items():
    q = PARTS[path]
    a = math.radians(ang)
    POSE[path] = (round(x + q["ox"] * math.cos(a) + q["oy"] * math.sin(a), 3),
                  round(y - q["ox"] * math.sin(a) + q["oy"] * math.cos(a), 3), ang)

# Stage 30 (DECISIONS 33; c24 M1b): the three rail-monitor notice stages, the LS / HS-A / HS-B ISO7710s U33 / U34,
# the bias OR U25 and its filter R126 / C143 are deleted. Every surviving part keeps its stage-29 pose exactly
# (placement-stage29.json, footprint origins; the packs above would otherwise reflow round the removed parts); U32
# and its VCC caps keep theirs under their new paths. The new parts take the authored poses in STAGE30.
S29 = json.loads((HERE / "placement-stage29.json").read_text())
S29_RENAME = {"monitor_ls.iso": "hb.iso", "monitor_ls.civcc1": "hb.civcc1", "monitor_ls.civcc2": "hb.civcc2",
              # HS-B's verdict isolator (ISO7710F) and its caps take U34 / C141 / C142's stage-29 poses
              "bias_hb.monitor.iso": "bias_hb.verdict", "bias_hb.monitor.civcc1": "bias_hb.cver1",
              "bias_hb.monitor.civcc2": "bias_hb.cver2"}
for old, (x, y, ang) in S29.items():
    path = S29_RENAME.get(old, old)
    if path in PARTS:
        q = PARTS[path]
        a = math.radians(ang)
        POSE[path] = (round(x + q["ox"] * math.cos(a) + q["oy"] * math.sin(a), 3),
                      round(y - q["ox"] * math.sin(a) + q["oy"] * math.cos(a), 3), ang)
for path in [p for p in POSE if p not in PARTS]:
    del POSE[path]
# U43 (ISO6721FB HS-A verdict link) straddles the HS-A / LS boundary where the scan finds legal copper
# (validation-results/08-manufacturing-package/native-21/stage30-heartbeat/spot_scan.py on the s29 board): beside U41
# (courtyards 0.04 mm apart), HS pins (1-4) down into the HS-A island and LS pins up on U41's n_ls pocket; U2.8's v3v3
# drop via moves 0.4 mm (patches21.add_stage30) so its LS pins clear the 8 mm barrier (8.2 mm). No HS-B pose routes:
# between the HS-B bank and the LS domain, U42's n_ls pocket, the SELV 8 mm keep-out and the protected bus_p / n_hb
# copper close every row on all four layers, so HS-B crosses to SELV instead (U44 ISO7710F, S29_RENAME above).
STAGE30 = {"bias_ha.link": (47.0, 66.25, 90.0),
           # link VCC caps, pad 1 on the supply (scan: nearest legal 0603 to pins 1 / 8)
           "bias_ha.clink1": (47.0, 71.0, 0.0), "bias_ha.clink2": (47.85, 61.5, 0.0),
           # LS heartbeat: the vote below U29 (its GOOD pins; BAT54S turned 180 so pin 3 / MON_GOOD_HA faces U43 as before), the LVC1G132 oscillator between U29 and U32
           "hb.vote": (104.5, 87.5, 180.0), "hb.osc": (102.5, 100.25, 90.0), "hb.rosc": (107.75, 98.25, 0.0),
           "hb.cosc": (109.25, 99.89, 0.0), "hb.cosc_vcc": (99.8, 96.11, 90.0),
           # SELV pump, one row left of U32's SELV pins in signal order. The heartbeat runs at 0.52-2.2 MHz (FMEA s6a), so
           # its SELV leg (U32.13 -> U46.2) and the high-impedance hold node stay a few mm long; U40 moves here from the
           # logic row (x 13.7) and the static, push-pull BIAS_GOOD takes the long run to the driver NANDs instead.
           # U46 NAND (heartbeat gated by HS-B's verdict) -> R132 220 ohm -> C164 / C165 series 1 nF -> D19 BAT54S -> hold (C166 / R133) -> U40.2
           "hb.buf": (94.5, 132.0, 180.0), "hb.cbuf": (94.5, 134.9, 0.0), "hb.rs": (90.25, 132.0, 180.0),
           "hb.cp1": (86.6, 132.0, 180.0), "hb.cp2": (82.95, 132.0, 180.0), "hb.pump": (79.0, 132.0, 0.0),
           "hb.chold": (78.4, 135.6, 180.0), "hb.rbleed": (78.4, 137.7, 180.0),
           "u_bias_flt": (74.6, 132.95, 180.0), "c_bias_flt_vcc": (74.6, 135.6, 0.0),
           # U9 BUS_FAULT RC (1 k / 100 pF) under U13: R134 takes bus_fault_iso from the right, C167 sits at the filtered node
           "r_bf": (35.0, 133.5, 180.0), "c_bf": (31.4, 133.5, 180.0)}
for path, pose in STAGE30.items():
    POSE[path] = pose

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
