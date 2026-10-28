"""C60 phase 0: a placement-only floorplan of the C49 controller on a smaller outline. NO ROUTING.

    python3 -I scripts/floorplan_c60.py [--outline acut|fallback] [--gap 0.9]
        -> results/floorplan-<outline>.json, renders/floorplan-<outline>.{png,svg}

What it does (it mirrors C/layout/build_board.py's placement, C/layout/build_board.py:339-566, in plain Python):
1. Explicit poses. Every IC, connector and power part C49 places explicitly (C/layout/floorplan.py PLACE)
   keeps its C49 world pose unless this file's MOVE table moves it. Rigid groups (GROUPS) move a
   C49 sub-arrangement as one body (translation + a multiple of 90 deg), so the placement rules
   DECISIONS / LAYOUT give for it (C37 J3 protection strip and RTD filter rows, the C39 detector) are
   kept part-for-part.
2. Anchored passives. Every other part is placed next to its anchor pin by the same rule build_board uses:
   floorplan.ANCHOR (decoupling at its IC's supply pin, ADC RCs at the module, pull-ups at the
   interlock...) or else the active part on its most specific net; a ring search out from the anchor
   pad, four rotations, nearest pad wins; courtyard-to-courtyard gap GAP (0.9 mm, build_board.py:40),
   0.4 mm for anchored capacitors; never inside a hole keep-out, the U.FL clear circle or (except
   anchored capacitors) a routing channel; 0.8 mm inside the board edge.
3. Checks: every part placed, no overlaps, hole keep-outs, U.FL 3 mm, decoupling <= 5 mm pad to pad
   (the 'vcc' pins of C/tools/verify_controller.py MODELS, as C/layout/check_layout.py:248-279),
   partition L2/U2 >= 10 mm from the RTD analog parts (check_layout.py:410-435), kept landings
   unchanged, utilisation.
Placement rectangles are courtyard U pads (build_board.py:205-216). Standard library + numpy + matplotlib.

Imports C/layout/floorplan.py (and world.py) read-only for PLACE / ANCHOR / CHANNELS; no bytecode is
written into that worktree.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402
import render  # noqa: E402

C = Path("/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller")
sys.dont_write_bytecode = True
sys.path.insert(0, str(C / "layout"))
sys.path.insert(0, str(C / "tools"))
import floorplan as fp49  # noqa: E402
import world as w49  # noqa: E402
from verify_controller import MODELS  # noqa: E402

GND = "selv_gnd"
SUPPLIES = {"v3v3", "v15_selv", "V15_BLW", "RTD_AVDD", "V5_UI", "v5_drop", "V_BLOWER"}   # check_layout.py:249

# ------------------------------------------------------------------ outlines
OUTLINES = {
    # shrink-r1 recommended_left_cut: today's left 131 mm (shrink-options.json)
    "acut": {"board": (-38.0, 14.0, 93.0, 90.0),
             "holes": [(-34.0, 18.0), (-26.0, 74.0), (65.0, 18.0), (75.0, 86.0)]},
}
HOLE_D, HOLE_KO_D, UFL_R = w49.HOLE_D, w49.HOLE_KEEPOUT_D, w49.UFL_CLEAR_R
EDGE_INSET = 0.8                    # build_board.py:263

# ------------------------------------------------------------------ the C60 floorplan
# Parts that keep their C49 world pose exactly: every C49 explicit pose (floorplan.PLACE) inside the
# kept left 131 mm, unless MOVE / GROUPS below name it. Keys are atopile paths (or fixed designators).
MOVE = {
    # ---- blower buck: U2, its input caps, bulk, FB strip and J13 stay (C49 stage-16 cluster; J13 is the
    #      R41/R43 landing). L2 (SWRB1205S, 13.5 mm) moves from in front-right of U2 (X 89..102.5, off the
    #      new edge) to directly in front of U2: the SW node still leaves U2's lower-right pin toward it.
    "l_12": ("centre", 85.2, 62.3, 0),
    # J10 blower output: a top-entry landing left of L2 (V_BLOWER is L2's output), like J7 a mid-board landing
    "J10": ("centre", 74.4, 61.0, 90),
    # ---- module: front-middle field (C49's free routing field), U.FL end to the rear. Its nets run to
    #      J7 (behind it), the read-back buffer and interlock requests (left), the expander and RTD SPI
    #      (right) and the PWM / ZC lines to J4 (left): all shorter than at C49's far-right module.
    "U4": ("centre", 34.4, 40.6, 0),
    # read-back buffer: in front of the interlock block as in C49, 8 mm further left so the module's left
    # pin column keeps its escape
    "u_rb": ("centre", 14.0, 51.0, 0),
    # expander between the module and the RTD block (C49: between the read-back buffer and the module)
    "u_io": ("centre", 49.6, 45.0, 0),
    "J11": ("centre", 49.6, 34.0, 90),        # TC2050 land beside the module (C41)
    # ---- RTD window logic, reference and runaway comparator: a 2 x 3 array left of the RTD core, chain
    #      order kept (windows -> NAND / AND -> interlock inputs leave left toward the latch); the column
    #      starts 10 mm clear of L1 and the rows stop 10 mm clear of L2
    "u_runaway": ("centre", 62.0, 27.0, 0),
    "rtd_pan.rail_monitor": ("centre", 68.0, 27.0, 0),
    "rtd_pan.fault_nand": ("centre", 62.0, 33.0, 0),
    "rtd_pan.high_window": ("centre", 68.0, 33.0, 0),
    "rtd_pan.window_and": ("centre", 62.0, 39.0, 0),
    "rtd_pan.low_window": ("centre", 68.0, 39.0, 0),
    "rtd_pan.reference": ("centre", 62.0, 44.5, 0),
    # rim trip and the RUNAWAY_FAULT OR (not RTD analog parts): beside J11, toward the interlock side
    "u_rim_trip": ("centre", 55.5, 24.0, 0),
    "u_runaway_or": ("centre", 55.5, 29.5, 0),
    # ---- rim NTC: J12 on the new right edge above J3 (the same 6-core cartridge cable breaks out to it),
    #      follower beside it
    "J12": ("centre", 88.75, 44.0, 90),
    "u_buf3": ("centre", 81.0, 47.5, 0),
}
# Rigid groups: (members, anchor, anchor's new placement-rect centre (X, Y), rotation added (deg)).
GROUPS = {
    # C37 / C34 RTD core: J3, its TVS / 220 nF strip, the MAX31865, c_rtd_input across pins 10/11, the
    # two filter rows and the 499 k pull-ups, as placed in C49 (floorplan.py:95-129), turned -90 deg so
    # J3's cable faces the new right edge instead of the rear edge.
    "rtd_core": (["J3", "rtd_pan.adc", "rtd_pan.c_rtd_input", "rtd_pan.c_j_fp", "rtd_pan.d_j_fp", "rtd_pan.c_j_sp",
                  "rtd_pan.d_j_sp", "rtd_pan.c_j_sn", "rtd_pan.d_j_sn", "rtd_pan.c_cm_n", "rtd_pan.c_j_fn",
                  "rtd_pan.d_j_fn", "rtd_pan.r_rtdin_p_bias", "rtd_pan.r_rtdin_n_bias", "rtd_pan.r_s2n",
                  "rtd_pan.r_s2p", "rtd_pan.r_s1n", "rtd_pan.r_s1p", "rtd_pan.c_s1"],
                 "J3", (88.75, 30.5), -90),
    # C39 capacitive-mode detector, turned 90 deg into the front-left field between the RMS block and
    # the 3.3 V buck (it sits on the MCU -> J4 PWM path there, as in C49)
    "capmode": (["u_cm_ff", "u_cm_inv_ha", "u_cm_inv_la", "u_cm_pol", "u_cm_or"], "u_cm_ff", (15.0, 32.0), 90),
}
# C49 explicit poses that this floorplan drops back to the anchor rule (pinned at C49-specific spots beside
# the old RTD column, floorplan.py:137-147; r_fan_inj at X92.1 would overhang the new edge, floorplan.py:93,
# and floorplan.ANCHOR already anchors it at U2)
UNPIN = ["r_fan_inj", "r_runaway_top", "r_runaway_bot", "rtd_pan.r_rail_ok_pullup", "rtd_pan.r_fault_pullup",
         "rtd_pan.r_high_bottom", "rtd_pan.r_window_ok_pulldown", "rtd_pan.r_avdd_top", "rtd_pan.r_avdd_bottom"]
# Routing channels kept free of auto-placed parts (anchored capacitors excepted), world rects
CHANNELS = [
    (22.6, 30.0, 25.0, 50.0),     # module left pin column escape
    (43.9, 30.0, 45.6, 50.0),     # module right pin column escape
    (82.3, 75.4, 84.6, 84.4),     # stage 16 J13 -> VIN feed band (unchanged)
    (74.0, 72.9, 80.6, 74.9),     # stage 16 feed strip over the bulk / input caps (unchanged)
]
KEEP_APART = 10.0                       # ENCLOSURE-HANDOFF.md:75 (L2 >= 10 mm from the RTD analog section)
RTD_STITCH = (56.0, 14.0, 93.0, 46.0)   # C34 stitching region moves with the RTD block (report only)


# ------------------------------------------------------------------ occupancy (summed-area table)
class Grid:
    def __init__(self, board, res=0.05):
        self.x0, self.y0, self.x1, self.y1 = board
        self.res = res
        self.nx = int(math.ceil((self.x1 - self.x0) / res))
        self.ny = int(math.ceil((self.y1 - self.y0) / res))
        self.occ = np.zeros((self.ny, self.nx), dtype=np.int32)
        self.sat = None
        self.dirty = True

    def _idx(self, r, grow=0.0):
        i0 = int(math.floor((r[0] - grow - self.x0) / self.res + 1e-6))
        j0 = int(math.floor((r[1] - grow - self.y0) / self.res + 1e-6))
        i1 = int(math.ceil((r[2] + grow - self.x0) / self.res - 1e-6))
        j1 = int(math.ceil((r[3] + grow - self.y0) / self.res - 1e-6))
        return max(i0, 0), max(j0, 0), min(i1, self.nx), min(j1, self.ny)

    def add(self, r):
        i0, j0, i1, j1 = self._idx(r)
        self.occ[j0:j1, i0:i1] = 1
        self.dirty = True

    def hit(self, r, grow=0.0):
        if self.dirty:
            s = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int64)
            s[1:, 1:] = self.occ.cumsum(0).cumsum(1)
            self.sat = s
            self.dirty = False
        i0, j0, i1, j1 = self._idx(r, grow)
        # shrink the query by one cell so exact touching is allowed (grid quantisation <= res)
        i0, j0, i1, j1 = i0 + 1, j0 + 1, i1 - 1, j1 - 1
        if i1 <= i0 or j1 <= j0:
            return False
        s = self.sat
        return (s[j1, i1] - s[j0, i1] - s[j1, i0] + s[j0, i0]) > 0


def circle_box(cx, cy, r):
    return (cx - r, cy - r, cx + r, cy + r)


def rect_circle_dist(r, cx, cy):
    dx = max(r[0] - cx, 0, cx - r[2])
    dy = max(r[1] - cy, 0, cy - r[3])
    return math.hypot(dx, dy)


# ------------------------------------------------------------------ main
def build(outline_key, gap, verbose=True, write=True):
    parts, board49 = geom.load_parts()
    spec = OUTLINES[outline_key]
    B = spec["board"]
    by_path = {p["path"]: r for r, p in parts.items()}

    def R(key):
        if key in by_path:
            return by_path[key]
        if key in parts:
            return key
        raise SystemExit(f"unknown key {key}")

    # nets
    nets = {}
    for r, p in parts.items():
        for q in p["pads_local"]:
            if q["net"]:
                nets.setdefault(q["net"], []).append((r, q["num"]))
    for n in nets:
        nets[n].sort(key=lambda rp: (rp[0].rstrip("0123456789"), int("0" + "".join(c for c in rp[0] if c.isdigit())), rp[1]))

    poses, how = {}, {}
    # 1a. explicit poses kept from C49
    explicit49 = {R(k) for k in fp49.PLACE} - {R(k) for k in UNPIN}
    moved = {R(k) for k in MOVE}
    grouped = {R(m) for g in GROUPS.values() for m in g[0]}
    for ref in explicit49 - moved - grouped:
        X, Y, t = parts[ref]["world"]
        poses[ref] = (X, Y, t)
        how[ref] = "kept C49 pose"
    # 1b. moved
    for key, (mode, x, y, t) in MOVE.items():
        ref = R(key)
        if mode == "centre":
            X, Y = geom.origin_for_centre(parts[ref], x, y, t)
        else:
            X, Y = x, y
        poses[ref] = (X, Y, t)
        how[ref] = "moved (MOVE)"
    # 1c. rigid groups
    for gname, (members, anchor, (cx, cy), drot) in GROUPS.items():
        a = R(anchor)
        aX, aY, at_ = parts[a]["world"]
        nt = (at_ + drot) % 360
        nX, nY = geom.origin_for_centre(parts[a], cx, cy, nt)
        th = math.radians(drot)
        for m in members:
            ref = R(m)
            X, Y, t = parts[ref]["world"]
            dx, dy = X - aX, Y - aY
            rx, ry = dx * math.cos(th) - dy * math.sin(th), dx * math.sin(th) + dy * math.cos(th)
            poses[ref] = (nX + rx, nY + ry, (t + drot) % 360)
            how[ref] = f"rigid group {gname}"
    for ref, (X, Y, t) in poses.items():
        poses[ref] = (round(X, 4), round(Y, 4), ((t + 180) % 360) - 180)

    rects = {r: geom.rect(parts[r], *poses[r]) for r in poses}
    problems = []
    keys = sorted(rects)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if geom.overlap(rects[a], rects[b]):
                problems.append(f"explicit overlap {a} ({how[a]}) / {b} ({how[b]})")

    def inside(r):
        return r[0] >= B[0] + EDGE_INSET - 1e-6 and r[1] >= B[1] + EDGE_INSET - 1e-6 and \
            r[2] <= B[2] - EDGE_INSET + 1e-6 and r[3] <= B[3] - EDGE_INSET + 1e-6
    # connectors on the edge may reach the edge (C49 J4 / J9 / J13 do): allow 0 inset for J*
    for r in rects:
        rr = rects[r]
        ok = inside(rr) if not r.startswith("J") else (rr[0] >= B[0] - 0.6 and rr[1] >= B[1] - 0.6 and
                                                       rr[2] <= B[2] + 0.6 and rr[3] <= B[3] + 0.6)
        if not ok:
            problems.append(f"explicit {r} off the board: rect {tuple(round(v, 2) for v in rr)}")

    grid = Grid(B)
    for r in rects:
        grid.add(rects[r])
    forbid = Grid(B)
    for hx, hy in spec["holes"]:
        forbid.add(circle_box(hx, hy, HOLE_KO_D / 2 + 0.3))          # build_board.py:238
    u4 = parts["U4"]
    ux, uy = geom.l2w(*poses["U4"], *w49.UFL_FP)
    forbid.add(circle_box(ux, uy, UFL_R))
    chan = Grid(B)
    for c in CHANNELS:
        chan.add(c)
    # C49 held auto-placed parts out of a 10 mm keep-apart band (floorplan.py:254); here the rule itself is
    # the keep-out: no RTD analog part (check_layout.py:419-421) within KEEP_APART of either buck's
    # inductor or IC rectangle (box-inflated, so the Euclidean gap is >= KEEP_APART)
    rtd_paths = ("u_runaway", "r_runaway_top", "r_runaway_bot", "c_runaway_th")
    is_rtd = lambda r: (parts[r]["path"] or "").startswith("rtd_pan.") and not r.startswith("J") or parts[r]["path"] in rtd_paths  # noqa: E731
    apart = Grid(B)
    for k in ("l_12", "u_12", "l_3v3", "u_3v3"):
        rr = geom.rect(parts[R(k)], *poses[R(k)])
        apart.add((rr[0] - KEEP_APART, rr[1] - KEEP_APART, rr[2] + KEEP_APART, rr[3] + KEEP_APART))

    ANCHOR = {R(k): R(v) for k, v in fp49.ANCHOR.items()}

    def is_active(r):
        return r[0] in "UJ" or r == "Q1" or r.startswith("L")

    def pad_world(ref, num):
        p = parts[ref]
        q = next(q for q in p["pads_local"] if q["num"] == num)
        return geom.l2w(*poses[ref], q["x"], q["y"]), q["net"]

    def anchor_of(ref):
        my_nets = [q["net"] for q in parts[ref]["pads_local"] if q["net"]]
        want = ANCHOR.get(ref)
        if want:
            cand = [q for q in parts[want]["pads_local"] if q["net"] in my_nets and q["net"] != GND]
            if cand:
                q = max(cand, key=lambda q: int(q["num"]) if q["num"].isdigit() else -1)
                return want, q["num"]
            for q in parts[want]["pads_local"]:
                if q["net"] in my_nets:
                    return want, q["num"]
            return None
        best = None
        for n in my_nets:
            if n == GND:
                continue
            nodes = nets[n]
            cands = [(r, p) for r, p in nodes if r != ref and is_active(r)]
            if not cands:
                continue
            key = (len(nodes) if n not in ("v3v3", "v15_selv", "V15_BLW") else 99, cands[0][0][0] != "U")
            if best is None or key < best[0]:
                best = (key, cands[0])
        if best is None:
            for n in my_nets:
                for r, p in nets[n]:
                    if r != ref and r in poses and n != GND:
                        return r, p
            return None
        return best[1]

    # precompute per-rotation local rect and pad offsets
    def rot_data(ref, t):
        p = parts[ref]
        r = geom.rect(p, 0.0, 0.0, t)
        pads = [(geom.l2w(0.0, 0.0, t, q["x"], q["y"]), q["net"]) for q in p["pads_local"]]
        return r, pads

    pending = [r for r in parts if r not in poses]
    pending.sort(key=lambda r: (r not in ANCHOR, r))
    unplaced, anchor_used = [], {}
    passes = 0
    while pending and passes < 6:
        passes += 1
        left = []
        for ref in pending:
            a = anchor_of(ref)
            if a is None or a[0] not in poses:
                left.append(ref)
                continue
            aref, anum = a
            (ax, ay), target_net = pad_world(aref, anum)
            is_decap = ref.startswith("C") and ref in ANCHOR
            g = 0.4 if is_decap else gap
            rd = {t: rot_data(ref, t) for t in (0, 90, 180, 270)}
            best = None
            for k in range(2, 200):
                rad = k * 0.25
                if best and best[0] < rad - 3:
                    break
                n_pts = max(8, int(2 * math.pi * rad / 0.5))
                for j in range(n_pts):
                    px = ax + rad * math.cos(2 * math.pi * j / n_pts)
                    py = ay + rad * math.sin(2 * math.pi * j / n_pts)
                    for t in (0, 90, 180, 270):
                        lr, pads = rd[t]
                        rr = (px + lr[0], py + lr[1], px + lr[2], py + lr[3])
                        if not inside(rr) or forbid.hit(rr) or (not is_decap and chan.hit(rr)) or \
                                (is_rtd(ref) and apart.hit(rr)):
                            continue
                        if grid.hit(rr, g):
                            continue
                        mine = [pp for pp, n in pads if n == target_net] or [pp for pp, _ in pads]
                        d = min(math.hypot(px + x - ax, py + y - ay) for x, y in mine)
                        if best is None or d < best[0] - 1e-6:
                            best = (d, px, py, t)
            if best is None:
                unplaced.append({"ref": ref, "path": parts[ref]["path"], "anchor": f"{aref}.{anum}",
                                 "anchor_world": [round(ax, 2), round(ay, 2)]})
                continue
            _, px, py, t = best
            poses[ref] = (round(px, 4), round(py, 4), t)
            how[ref] = f"anchored to {aref}.{anum} ({'decap' if is_decap else 'auto'})"
            anchor_used[ref] = {"anchor": f"{aref}.{anum}", "pad_to_anchor_mm": round(best[0], 2)}
            rects[ref] = geom.rect(parts[ref], *poses[ref])
            grid.add(rects[ref])
        pending = left
    for ref in pending:
        unplaced.append({"ref": ref, "path": parts[ref]["path"], "anchor": None})

    # ------------------------------------------------------------------ checks
    res = {}
    # hole keep-outs (courtyard/pad rect vs the 8 mm circle)
    hk = []
    for hx, hy in spec["holes"]:
        for r, rr in rects.items():
            if rect_circle_dist(rr, hx, hy) < HOLE_KO_D / 2 - 1e-6:
                hk.append({"hole": [hx, hy], "ref": r, "dist_mm": round(rect_circle_dist(rr, hx, hy), 2)})
    res["hole_keepout"] = {"ok": not hk, "intrusions": hk}
    near_ufl = [r for r, rr in rects.items() if r != "U4" and rect_circle_dist(rr, ux, uy) < UFL_R - 1e-6]
    res["ufl_clear"] = {"ok": not near_ufl, "ufl_world": [round(ux, 2), round(uy, 2)], "parts_within_3mm": near_ufl}
    ovl = []
    ks = sorted(rects)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            if geom.overlap(rects[a], rects[b]) and not geom.overlap(rects[a], rects[b], -0.02):
                continue
            if geom.overlap(rects[a], rects[b], -0.02):
                ovl.append([a, b])
    res["overlaps"] = {"ok": not ovl, "pairs": ovl}
    # decoupling (check_layout.py:248-279)
    caps = [r for r in poses if r.startswith("C")]
    dec_rows, dec_ok = [], True
    for ref in sorted(poses):
        if not ref.startswith("U"):
            continue
        model = MODELS.get(parts[ref]["mpn"])
        for q in parts[ref]["pads_local"]:
            n = q["net"]
            if n not in SUPPLIES:
                continue
            if model is not None and model.pins and model.pins.get(q["num"]) != "vcc":
                continue
            px, py = geom.l2w(*poses[ref], q["x"], q["y"])
            best = None
            for c in caps:
                cn = {qq["net"] for qq in parts[c]["pads_local"]}
                if n in cn and GND in cn:
                    qq = next(qq for qq in parts[c]["pads_local"] if qq["net"] == n)
                    cx, cy = geom.l2w(*poses[c], qq["x"], qq["y"])
                    d = math.hypot(cx - px, cy - py)
                    if best is None or d < best[0]:
                        best = (d, c)
            good = best is not None and best[0] <= 5.0
            dec_ok &= good
            dec_rows.append({"pin": f"{ref}.{q['num']}", "net": n, "cap": best[1] if best else None,
                             "distance_mm": round(best[0], 2) if best else None, "ok": good})
    res["decoupling"] = {"ok": dec_ok, "limit_mm": 5.0, "worst_mm": max((r["distance_mm"] or 99) for r in dec_rows),
                         "pins": len(dec_rows), "fails": [r for r in dec_rows if not r["ok"]]}
    # partition (check_layout.py:410-435)
    def grp(paths_prefix=None, paths=()):
        out = []
        for r, p in parts.items():
            pa = p["path"] or ""
            if (paths_prefix and pa.startswith(paths_prefix) and not r.startswith("J")) or pa in paths:
                out.append(r)
        return out
    rtd_analog = grp("rtd_pan.", ("u_runaway", "r_runaway_top", "r_runaway_bot", "c_runaway_th"))
    thermal = grp("thermal.")
    analog_j4 = grp(None, ("u_rx", "u_buf1", "u_buf2", "u_ref", "u_rms", "u_adc", "r_rx_n", "r_rx_p", "r_rx_f", "r_rx_b",
                           "r_bias_top", "r_bias_bot", "r_ct_mon_def", "r_rms_bias", "r_rms_gf", "r_rms_gg", "c_rms_in",
                           "c_rms_core", "c_rms_avg", "c_rms_ignd", "c_rms_lpf"))
    sw = {"L2/U2 (blower buck)": [R("l_12"), R("u_12")], "L1/U1 (3.3 V buck)": [R("l_3v3"), R("u_3v3")]}
    sep = {}
    for name, ps in sw.items():
        for gname, g in (("RTD front end", rtd_analog), ("thermal-sense", thermal), ("J4 analog", analog_j4)):
            g = [x for x in g if x in rects]
            d, pair = min((geom.rect_gap(rects[a], rects[b]), (a, b)) for a in ps for b in g)
            sep[f"{name} -> {gname}"] = {"mm": round(d, 1), "nearest": pair}
    res["partition"] = {"ok": sep["L2/U2 (blower buck) -> RTD front end"]["mm"] >= 10.0, "separations_mm": sep,
                        "rule": "L2/U2 >= 10 mm from the RTD analog parts (gated, check_layout.py:434); this floorplan also "
                                "holds L1/U1 >= 10 mm (C49: 76.7 mm; ENCLOSURE-HANDOFF item 7)",
                        "l1_rtd_ok": sep["L1/U1 (3.3 V buck) -> RTD front end"]["mm"] >= 10.0}
    # RTD C34 / C37 locality (rigid group keeps these; recomputed)
    u30 = R("rtd_pan.adc")
    c31 = R("rtd_pan.c_rtd_input")
    def d_c31(pz):
        p10_, p11_ = (geom.l2w(*pz[u30], *(lambda q: (q["x"], q["y"]))(next(q for q in parts[u30]["pads_local"] if q["num"] == n)))
                      for n in ("10", "11"))
        pads = [geom.l2w(*pz[c31], q["x"], q["y"]) for q in parts[c31]["pads_local"]]
        return [round(min(math.dist(a, b) for b in pads), 3) for a in (p10_, p11_)]
    c49pz = {u30: parts[u30]["world"], c31: parts[c31]["world"]}
    res["rtd_input_cap"] = {"ok": d_c31(poses) == d_c31(c49pz), "pin_to_pad_centre_mm_c60": d_c31(poses),
                            "pin_to_pad_centre_mm_c49": d_c31(c49pz),
                            "note": "C34 rule <= 3 mm is pad to pin as LAYOUT.md measures it (~2.1 mm); centre to centre "
                                    "is reported here and must equal C49's (rigid group)"}
    # kept landings and the J13 / J4 positions
    land = {}
    for ref in ("J1", "J2", "J4", "J7", "J9", "J13"):
        land[ref] = {"c49": parts[ref]["world"], "c60": list(poses[ref]), "unchanged": list(poses[ref]) == parts[ref]["world"]}
    res["kept_landings"] = {"ok": all(v["unchanged"] for v in land.values()), "rows": land}
    res["all_placed"] = {"ok": not unplaced and len(poses) == len(parts), "placed": len(poses), "total": len(parts),
                         "unplaced": unplaced}
    res["explicit_problems"] = {"ok": not problems, "rows": problems}

    # ------------------------------------------------------------------ utilisation
    area = (B[2] - B[0]) * (B[3] - B[1])
    crt = sum(parts[r]["crtyd_area_mm2"] for r in poses)
    ko = len(spec["holes"]) * math.pi * (HOLE_KO_D / 2) ** 2
    util = {"board_mm": [B[2] - B[0], B[3] - B[1]], "board_area_mm2": area, "crtyd_placed_mm2": round(crt, 1),
            "utilisation_pct": round(100 * crt / area, 1), "utilisation_pct_less_hole_keepouts": round(100 * crt / (area - ko), 1),
            "placement_rect_mm2": round(sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects.values()), 1)}
    # per-block hull density on this placement
    blocks = {}
    for r, p in parts.items():
        if r not in rects:
            continue
        b = blocks.setdefault(p["block"], {"parts": 0, "crtyd": 0.0, "x0": 1e9, "y0": 1e9, "x1": -1e9, "y1": -1e9})
        b["parts"] += 1
        b["crtyd"] += p["crtyd_area_mm2"]
        rr = rects[r]
        b["x0"], b["y0"] = min(b["x0"], rr[0]), min(b["y0"], rr[1])
        b["x1"], b["y1"] = max(b["x1"], rr[2]), max(b["y1"], rr[3])
    for b in blocks.values():
        b["bbox"] = [round(b.pop("x0"), 1), round(b.pop("y0"), 1), round(b.pop("x1"), 1), round(b.pop("y1"), 1)]
        b["crtyd"] = round(b["crtyd"], 1)
    util["blocks"] = blocks

    status = "FIT" if all(v["ok"] for v in res.values()) else "NO-FIT"
    out = {"schema": "temper.controller-shrink-c60.floorplan.v1", "outline": outline_key, "board_world": B,
           "holes": spec["holes"], "gap_mm": gap, "status": status,
           "summary": {k: v["ok"] for k, v in res.items()}, "checks": res, "utilisation": util,
           "channels": CHANNELS, "rtd_stitch_region": RTD_STITCH,
           "placement": {r: {"world": list(poses[r]), "how": how[r], "block": parts[r]["block"], "path": parts[r]["path"],
                             "rect": [round(v, 3) for v in rects[r]]} for r in sorted(poses)},
           "anchors": anchor_used}
    tag = f"{outline_key}" + ("" if abs(gap - 0.9) < 1e-9 else f"-gap{gap:g}")
    if not write:
        return out
    (OUT / "results" / f"floorplan-{tag}.json").write_text(json.dumps(out, indent=1))
    zones = [(RTD_STITCH[0], RTD_STITCH[1], RTD_STITCH[2], RTD_STITCH[3], "RTD analog region (C34 stitching)", "#2e8b57")]
    render.draw(parts, poses, B, spec["holes"], OUT / "renders" / f"floorplan-{tag}",
                f"C60 phase-0 floorplan {B[2]-B[0]:g} x {B[3]-B[1]:g} mm (placement only, not routed): "
                f"{len(poses)}/{len(parts)} placed, courtyard utilisation {util['utilisation_pct']} %, {status}",
                channels=CHANNELS, zones=zones,
                notes=[f"world mm; holes Ø4 with Ø8 keep-out; dashed = routing channels; U.FL at ({ux:.1f}, {uy:.1f})"])
    if verbose:
        print(f"{tag}: {status}; placed {len(poses)}/{len(parts)}; util {util['utilisation_pct']} %")
        for k, v in res.items():
            extra = ""
            if k == "partition":
                extra = {kk: vv["mm"] for kk, vv in v["separations_mm"].items()}
            elif k == "decoupling":
                extra = f"worst {v['worst_mm']} mm, fails {[r['pin'] for r in v['fails']]}"
            elif k == "all_placed":
                extra = [u["ref"] + "(" + str(u["path"]) + ")" for u in v["unplaced"]]
            elif k == "explicit_problems":
                extra = v["rows"]
            elif k == "hole_keepout":
                extra = v["intrusions"]
            elif k == "ufl_clear":
                extra = v
            print(f"  {k}: {v['ok']} {extra}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", default="acut", choices=sorted(OUTLINES))
    ap.add_argument("--gap", type=float, default=0.9)
    a = ap.parse_args()
    build(a.outline, a.gap)
