#!/usr/bin/env python3
"""Enclosure fit gate: native power board + edge heatsink + straight duct in the R4 enclosure (D-36).

    python3 fit_gate.py [--catalog R4/catalog.json] [--boxes native20-boxes.json] [--out fit-result.json]

Geometry (all mm, R4 assembly frame: x across the width, y from the front, z up):
- interior: |x| <= 183, 2 <= y <= 438, z >= 10 (tray floor), z <= roof(y) (R4 src/enclosure.py roof()).
- obstacles: every R4 catalog solid's AABB except the shell (tray, cover) and the Oct-2
  study's own allocations that this gate replaces (old PCB export/tray/lid/PS1, compact
  sink, fan, duct). The centre-sensor service corridor (0, 261), r = 18 mm, z <= 86, is
  added with a 3 mm tool margin as a square.
- board: one AABB per populated solid (board_boxes.py from the KiCad STEP), rotated by
  0/90/180/270 deg about z, translated on a 5 mm grid, board bottom on a 1 mm grid.
- sink: on the TO-247 edge (board-local y = 0, outward -y), spanning board-local
  x [SINK_X0, SINK_X1] (BR1 + Q5..Q2), base plate 6 mm, fins out to depth D, fin stack
  over z [z_lo, z_hi] chosen as large as the obstacles allow. Flow runs along the edge.
- duct: the sink's cross-section extruded straight along the edge to both side walls
  (fan inside it); it must be obstacle-free. Bent ducts are NOT considered: a placement
  rejected here may still work with a bent duct (reported as a limit).

Thermal (estimate, not a bound): plate fins parallel to the flow, Teertstra et al.
(1999) developing-flow channel Nusselt model, straight-fin efficiency, aluminium 6063
k = 200 W/mK, air at 55 C; 0.03 C/W spreading allocation. RthSA here is sink-to-local-air
(D-18 adds the caloric rise separately). Pressure drop from the Muzychka-Yovanovich
apparent friction factor plus entrance/exit loss; reported as the fan operating point
the duct needs. Criterion (D-18): RthSA <= 0.29 C/W hard limit at a 1.0 C/W MOSFET
interface, 0.15 allocation; >= 20 CFM delivered.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R4 = Path("/Users/bennet/Desktop/temper/output/temper-flush-front-r4/catalog.json")
XW, Y0, Y1, ZF = 183.0, 2.0, 438.0, 10.0
FRONT_Z = 105 - 82 * math.tan(math.radians(35))
SKIP_GROUPS = {"tray", "cover"}
SKIP_NAMES = ("pcb_export_", "PS1_datasheet_body_envelope", "covered_PCB_tray_allocation",
              "PCB_chamber_lid_allocation", "compact_sink_candidate", "Sunon_60x60x25",
              "fan_hub_envelope", "separate_rear_cooling_duct")
CORRIDOR = (0.0, 261.0, 18.0 + 3.0, -40.0, 86.0)
SINK_X0, SINK_X1, BASE_T = 8.0, 170.0, 6.0
GAP = 1.0                                   # clearance to every obstacle
K_AL, NU, K_AIR, PR, RHO = 200.0, 1.8e-5, 0.0275, 0.71, 1.09
TARGET_HARD, TARGET_ALLOC, P_SINK = 0.29, 0.15, 121.0


def roof(y):
    return min(102.5, FRONT_Z + math.tan(math.radians(35)) * y - 3.5, 102.5 - max(0.0, y - 434.5) * 2 / 3)


def obstacles(catalog):
    obs = []
    for it in json.loads(Path(catalog).read_text()):
        if it["group"] in SKIP_GROUPS or it["name"].startswith(SKIP_NAMES):
            continue
        obs.append(it["bbox"])
    cx, cy, r, z0, z1 = CORRIDOR
    obs.append([cx - r, cy - r, z0, cx + r, cy + r, z1])
    for y in np.arange(0, 120, 2.0):                 # sloped front roof as slabs
        obs.append([-XW, y, roof(y + 2.0), XW, y + 2.0, 120.0])
    return np.array(obs, float)


def rotate(boxes, rot):
    """Rotate board-local boxes about z by rot degrees (board-local origin)."""
    x0, y0, z0, x1, y1, z1 = boxes.T
    if rot == 0:
        return np.stack([x0, y0, z0, x1, y1, z1], 1)
    if rot == 90:
        return np.stack([-y1, x0, z0, -y0, x1, z1], 1)
    if rot == 180:
        return np.stack([-x1, -y1, z0, -x0, -y0, z1], 1)
    return np.stack([y0, -x1, z0, y1, -x0, z1], 1)


def free_mask(parts, obs, xs, ys):
    """True where translating `parts` by (x, y) collides with no obstacle and stays inside."""
    ok = np.ones((len(xs), len(ys)), bool)
    step = xs[1] - xs[0]
    for p in parts:
        # inside the interior footprint
        ok &= ((xs + p[0] >= -XW) & (xs + p[3] <= XW))[:, None]
        ok &= ((ys + p[1] >= Y0) & (ys + p[4] <= Y1))[None, :]
        zo = obs[(obs[:, 2] < p[5] + GAP) & (obs[:, 5] > p[2] - GAP)]
        for o in zo:
            lx, hx = o[0] - p[3] - GAP, o[3] - p[0] + GAP
            ly, hy = o[1] - p[4] - GAP, o[4] - p[1] + GAP
            i0, i1 = np.searchsorted(xs, lx, "right"), np.searchsorted(xs, hx, "left")
            j0, j1 = np.searchsorted(ys, ly, "right"), np.searchsorted(ys, hy, "left")
            if i0 < i1 and j0 < j1:
                ok[i0:i1, j0:j1] = False
    return ok


def sink_model(L, D, H, Q_cfm, t=1.5, s=None):
    """Plate-fin sink, fins parallel to flow, fin stack height H, fin length D (protrusion)."""
    best = None
    for s_ in ([s] if s else np.arange(3.0, 9.01, 0.5)):
        n = int((H + s_) // (t + s_))
        if n < 2:
            continue
        nch = n - 1
        Q = Q_cfm * 4.719e-4
        A = nch * s_ * 1e-3 * D * 1e-3
        V = Q / A
        b = s_ * 1e-3
        Re_b = V * b / NU
        Re_s = Re_b * b / (L * 1e-3)
        nu = ((Re_s * PR / 2) ** -3 + (0.664 * math.sqrt(Re_s) * PR ** (1 / 3) * math.sqrt(1 + 3.65 / math.sqrt(Re_s))) ** -3) ** (-1 / 3)
        h = nu * K_AIR / b
        m = math.sqrt(2 * h / (K_AL * t * 1e-3))
        eta = math.tanh(m * D * 1e-3) / (m * D * 1e-3)
        area = n * 2 * D * 1e-3 * L * 1e-3 * eta + nch * b * L * 1e-3
        R = 1 / (h * area) + 0.03
        dh = 2 * b * D * 1e-3 / (b + D * 1e-3)
        re_dh = V * dh / NU
        lstar = L * 1e-3 / (dh * re_dh)
        fre = math.sqrt((3.44 / math.sqrt(lstar)) ** 2 + 24.0 ** 2)
        dp = (4 * (fre / re_dh) * L * 1e-3 / dh + 1.5) * RHO * V * V / 2
        cand = {"fin_gap_mm": float(s_), "fins": n, "R_C_per_W": round(R, 4), "dp_Pa": round(dp, 1),
                "air_m_per_s": round(V, 2)}
        if best is None or R < best["R_C_per_W"]:
            best = cand
    return best


def sink_box_world(rot, tx, ty, zb, D, z_lo, z_hi, ext=(SINK_X0, SINK_X1)):
    loc = np.array([[ext[0], -D - BASE_T, z_lo, ext[1], 0.0, z_hi]])
    w = rotate(loc, rot)[0]
    return w + np.array([tx, ty, zb, tx, ty, zb])


def hits(box, obs):
    return np.any((obs[:, 0] < box[3] + GAP) & (obs[:, 3] > box[0] - GAP) & (obs[:, 1] < box[4] + GAP) &
                  (obs[:, 4] > box[1] - GAP) & (obs[:, 2] < box[5] + GAP) & (obs[:, 5] > box[2] - GAP))


def inside(box):
    return box[0] >= -XW and box[3] <= XW and box[1] >= Y0 and box[4] <= Y1 and box[2] >= ZF


def duct_box(rot, tx, ty, zb, D, z_lo, z_hi):
    """Straight duct: the sink cross-section extended along the edge to both side walls."""
    s = sink_box_world(rot, tx, ty, zb, D, z_lo, z_hi, ext=(-1000, 1000))
    s[0], s[3] = max(s[0], -XW), min(s[3], XW)
    s[1], s[4] = max(s[1], Y0), min(s[4], Y1)
    return s


def catalog_names(catalog):
    return [x for x in json.loads(Path(catalog).read_text())
            if x["group"] not in SKIP_GROUPS and not x["name"].startswith(SKIP_NAMES)]


def box_hits(box, items):
    """Names of R4 parts (and the sensor corridor) a world box touches within GAP."""
    out = [x["name"] for x in items if x["bbox"][0] < box[3] + GAP and x["bbox"][3] > box[0] - GAP and
           x["bbox"][1] < box[4] + GAP and x["bbox"][4] > box[1] - GAP and x["bbox"][2] < box[5] + GAP and
           x["bbox"][5] > box[2] - GAP]
    cx, cy, r, z0, z1 = CORRIDOR
    if box[0] < cx + r and box[3] > cx - r and box[1] < cy + r and box[4] > cy - r and box[2] < z1:
        out.append("SENSOR_SERVICE_CORRIDOR(+3mm)")
    for y in np.arange(box[1], box[4] + 0.01, 2.0):
        if box[5] > roof(float(y)):
            out.append(f"ROOF(y={float(y):.0f}, roof={roof(float(y)):.1f})")
            break
    if not inside(np.array(box, float)) or box[5] > 102.5:
        out.append("OUTSIDE_INTERIOR")
    return out


def scan_rectangles(catalog, zb=(26.0, 30.0, 34.0)):
    """Which rectangular board envelopes (TO-247 -14.5 mm .. +50 mm about the board bottom) fit anywhere."""
    obs = obstacles(catalog)
    xs, ys = np.arange(-185, 185.1, 2.0), np.arange(0, 440.1, 2.0)
    fits = []
    for W in range(200, 300, 10):
        for D in range(100, 181, 10):
            for (w, d) in {(W, D), (D, W)}:
                for z in zb:
                    m = free_mask(np.array([[0, 0, z - 14.5, w, d, z + 50]]), obs, xs, ys)
                    if m.any():
                        i, j = np.argwhere(m)[0]
                        fits.append({"w": w, "d": d, "board_bottom_z": z, "first_origin": [float(xs[i]), float(ys[j])],
                                     "positions": int(m.sum())})
                        break
    return sorted(fits, key=lambda f: -f["w"] * f["d"])


def check_plan(catalog, plan):
    items = catalog_names(catalog)
    out = {"boxes": {}, "pass": True}
    for name, box in plan["boxes"].items():
        h = box_hits(box, items)
        out["boxes"][name] = {"box": box, "hits": h}
        out["pass"] &= not h
    s = plan["sink"]
    out["sink_thermal"] = {f"{q}_cfm": sink_model(s["flow_length_mm"], s["fin_depth_mm"], s["stack_mm"], q) for q in (20, 30)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["native", "scan", "plan"], default="native")
    ap.add_argument("--plan", default=str(HERE / "native21-plan.json"))
    ap.add_argument("--catalog", default=str(R4))
    ap.add_argument("--boxes", default=str(HERE / "native20-boxes.json"))
    ap.add_argument("--out", default=str(HERE / "fit-result.json"))
    ap.add_argument("--q-cfm", type=float, default=20.0)
    a = ap.parse_args()
    if a.mode == "scan":
        fits = scan_rectangles(a.catalog)
        Path(HERE / "rect-scan.json").write_text(json.dumps(fits, indent=1) + "\n")
        for f in fits[:12]:
            print(f)
        return
    if a.mode == "plan":
        res = check_plan(a.catalog, json.loads(Path(a.plan).read_text()))
        Path(HERE / "plan-result.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
        print(json.dumps(res, indent=1, default=float))
        return
    obs = obstacles(a.catalog)
    board = np.array(json.loads(Path(a.boxes).read_text())["boxes"], float)
    xs, ys = np.arange(-200, 200.1, 5.0), np.arange(0, 440.1, 5.0)
    results = []
    for rot in (0, 90, 180, 270):
        parts = rotate(board, rot)
        for zb in np.arange(ZF + 14.5, 60.0, 1.0):
            pz = parts.copy()
            pz[:, 2] += zb
            pz[:, 5] += zb
            if (pz[:, 2] < ZF).any():
                continue
            mask = free_mask(pz, obs, xs, ys)
            # roof: each part below roof(y) — enforced via the front slabs + glass/carrier obstacles
            for i, j in zip(*np.nonzero(mask)):
                tx, ty = xs[i], ys[j]
                best = None
                for D in (60, 50, 40, 30, 20):
                    # grow the fin stack down/up from the TO-247 span (board-local z -14.2..26.9)
                    z_lo, z_hi = -14.2, 26.9
                    if not inside(sink_box_world(rot, tx, ty, zb, D, z_lo, z_hi)) or hits(sink_box_world(rot, tx, ty, zb, D, z_lo, z_hi), obs):
                        continue
                    while zb + z_lo - 1 >= ZF and not hits(sink_box_world(rot, tx, ty, zb, D, z_lo - 1, z_hi), obs):
                        z_lo -= 1
                    while not hits(sink_box_world(rot, tx, ty, zb, D, z_lo, z_hi + 1), obs) and zb + z_hi + 1 <= 102:
                        z_hi += 1
                    duct = duct_box(rot, tx, ty, zb, D, z_lo, z_hi)
                    duct_ok = not hits(duct, obs)
                    th = sink_model(SINK_X1 - SINK_X0, D, z_hi - z_lo, a.q_cfm)
                    cand = {"rot": rot, "x": float(tx), "y": float(ty), "board_bottom_z": float(zb), "sink_depth_mm": D,
                            "fin_stack_z_world": [round(zb + z_lo, 1), round(zb + z_hi, 1)],
                            "straight_duct_clear": bool(duct_ok), **(th or {})}
                    if th and (best is None or cand["R_C_per_W"] < best["R_C_per_W"]):
                        best = cand
                if best:
                    results.append(best)
    results.sort(key=lambda r: (not r["straight_duct_clear"], r["R_C_per_W"]))
    summ = {"placements_with_sink": len(results),
            "with_straight_duct": sum(r["straight_duct_clear"] for r in results),
            "meeting_hard_0.29_with_duct": sum(r["straight_duct_clear"] and r["R_C_per_W"] <= TARGET_HARD for r in results),
            "meeting_alloc_0.15_with_duct": sum(r["straight_duct_clear"] and r["R_C_per_W"] <= TARGET_ALLOC for r in results),
            "best": results[:15], "q_cfm": a.q_cfm}
    Path(a.out).write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summ.items() if k != "best"}, indent=1))
    for r in results[:8]:
        print(r)


if __name__ == "__main__":
    main()
