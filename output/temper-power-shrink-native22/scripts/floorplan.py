#!/usr/bin/env python3
"""Native-22 production-shrink floorplan: placement only, no copper, no routing.

    python3 floorplan.py                 # -> results/floorplan_native22.json, renders/floorplan_native22.{svg,png}
    python3 floorplan.py --scan          # also the width scan -> results/width_scan.json

Rules (README section 2):
  * Every s53 part that still exists and lies inside the new outline keeps its s53 pose exactly. That keeps the FET row,
    BR1, the HF film row, R5, the gate networks, the bias islands, T1, the bank, the bleed string and the J2/J5 studs
    rigid (RELAYOUT L5, L6, L13; DECISIONS 2026-10-08 / 2026-10-17 power-loop entries), and the SELV island with its
    8 mm moat.
  * Parts that go to the D-22 inlet module (INLET) are removed. Two connectors are added for what the module now
    feeds the board (NEW): J1N (L_FILT / N_FILT, J1's Phoenix MKDS 5/2-9.52 footprint) and J3N (V24_RAW / N_LS, the
    PS2 output, J3's footprint).
  * Parts outside the new outline (right of x = W, or on the dropped J4 tongue) are re-placed by a greedy raster packer
    (MOVE): rotations 0/90/180/270 (connectors keep their s53 orientation), courtyard gap >= 0.5 mm to every other
    courtyard on the same side (THT parts block both sides), >= 0.5 mm to the board edge, and every pad >= 8.0 mm
    (+ one raster cell) from copper of the other isolation side (HOT vs SELV/PE), counting the s53 copper of every
    fixed part and the pads of every part already placed. Among legal spots the one nearest the part's anchor wins.
    Anchors encode the intent (J1N beside BR1's AC pins on the rear edge, C5/C6 on the rear band, J4 on the front edge
    inside the SELV island, ...); they are listed in RECIPES.
  * Holes: H5-H8 and H10 keep their s53 places; H1, H3, H4 (R43 standoffs) are re-placed near the new corners; H2 and H9
    (empty in R43, DECISIONS 76) are dropped. Fiducials FID2 / FID3 re-placed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import shapely
from scipy.ndimage import distance_transform_edt
from scipy.signal import correlate

import common as C

H_BOARD = 140.0
TARGET_W = 218.0
GAP_MM = 0.5
EDGE_MM = 0.5
EDGE_TOUCH_MM = 1.0       # a connector with an edge rule sits with its courtyard within this of that edge

# ---- what leaves the board for the D-22 inlet module (shrink study r1 option O2, plus the blower tap)
INLET = {
    "J1": "mains input terminal (cord L/N)", "F1": "fuse KLDR025.TXP + clips", "RV1": "MOV TMOV20RP175E",
    "C1": "X2 cx1", "C2": "X2 cx2", "C3": "Y1 cy1 (L_FILT-PE)", "C4": "Y1 cy2 (N_FILT-PE)", "R1": "X bleed rb1a",
    "R2": "X bleed rb1b", "L1": "CM/DM choke B82726S22x3A020", "PS2": "MEAN WELL MPM-20-24 gate-drive supply (TCO_L in)",
    "J3": "TCO loop terminal (L_FILT -> TCO_L)", "F2": "blower fuse", "R130": "blower series resistor",
    "J11": "blower AC tap terminal",
}
DROPPED = {"H2": "empty in R43 (DECISIONS 76)", "H9": "empty in R43 (DECISIONS 76)"}
# ---- new connectors: (template ref, {pad: net}, why)
NEW = {
    "J1N": ("J1", {"1": "l_filt", "2": "n_filt"}, "filtered L/N from the inlet module to BR1 and the LINE_ZC string"),
    "J3N": ("J3", {"1": "v24_raw", "2": "n_ls"}, "PS2's 24 V output (HOT, N_LS-referenced) from the inlet module"),
}

# ---- placement recipes: ref -> (anchor x, anchor y, edge rule, allowed rotations). x may be a callable of W.
CONN0 = (0,)
ANY = (0, 90, 180, 270)
R2 = (0, 90)


def _recipe_common(W):
    return {
        "J4": (60.0, 135.0, "bottom", CONN0),
        "D3": (W - 12, 62.0, None, R2), "D17": (W - 12, 80.0, None, R2),
        "R3": (W - 6, 52.0, None, R2), "R4": (W - 6, 56.0, None, R2),
        # LINE_ZC opto at the right end of the SELV bottom corridor (as s53's spur end), its HOT string above it
        "U36": (W - 14, 124.0, None, ANY), "R67": (W - 6, 100.0, None, R2), "R68": (W - 6, 104.0, None, R2),
        "R69": (W - 6, 108.0, None, R2), "R70": (W - 6, 112.0, None, R2),
        "R146": (52.0, 128.0, None, R2), "C174": (55.0, 128.0, None, R2), "C178": (58.0, 128.0, None, R2),
        "C156": (61.0, 128.0, None, R2), "C155": (64.0, 128.0, None, R2), "C177": (67.0, 128.0, None, R2),
        "TP20": (50.0, 128.0, None, CONN0), "TP39": (53.0, 128.0, None, CONN0), "TP34": (62.0, 138.0, None, CONN0),
        "TP13": (65.0, 138.0, None, CONN0), "TP19": (68.0, 138.0, None, CONN0), "C176": (70.0, 136.0, None, R2),
        "H1": (W - 5, 135.0, None, CONN0), "H3": (5.0, 135.0, None, CONN0), "H4": (W - 5, 40.0, None, CONN0),
        "FID2": (W - 3, 137.0, None, CONN0), "FID3": (3.0, 137.0, None, CONN0),
        "H8": (W - 5, 128.0, None, CONN0),          # only outside the outline below W 198
    }


def recipe_a(W):
    """Preferred: J1N beside BR1's AC pins on the rear edge, then C6 and C5 along the rear band, J3N on the right."""
    r = {"J1N": (121.0, 7.0, "top", CONN0), "C6": (140.0, 17.5, None, R2), "C5": (W - 18.0, 17.5, None, R2),
         "J3N": (W - 6, 40.0, "right", ANY)}
    r.update(_recipe_common(W))
    return r


def recipe_b(W):
    """Compact: C6 turned at the band start, C5 beside it, J1N and J3N at the band's right end on the rear edge."""
    r = {"C6": (128.0, 22.0, None, R2), "C5": (167.0, 17.5, None, R2), "J1N": (W - 11, 7.0, "top", CONN0),
         "J3N": (W - 6, 26.0, None, ANY)}
    r.update(_recipe_common(W))
    return r


RECIPES = {"A": recipe_a, "B": recipe_b}
# small fixed SELV parts displaced to clear J4's slot on the front edge (J4 needs 29.2 mm of edge at x 37-66)
DISPLACE = {"C176": "clears J4's front-edge slot", "TP19": "clears J4's front-edge slot"}
ORDER = ["J1N", "C6", "C5", "J4", "D3", "D17", "U36", "J3N", "R3", "R4", "R67", "R68", "R69", "R70", "R146", "C174",
         "C178", "C156", "C155", "C177", "C176", "TP20", "TP39", "TP34", "TP13", "TP19", "H1", "H3", "H4", "H8", "FID2", "FID3"]
KEEPOUTS = [("jet strip, parts > 4 mm (run_basis.JET_REGION)", (0.0, 7.0, 90.0, 23.5))]
STUD_KEEPOUT_MM = 10.0     # upturned coil lugs: Litz drops within ~10 mm of each stud axis (DECISIONS M6 amendment)


def part_set(parts):
    """Return (fixed, to_move, removed) for the W-independent part of the rule (tongue / outside decided later)."""
    removed = {r: ("inlet module: " + INLET[r]) for r in INLET}
    removed.update({r: "dropped: " + DROPPED[r] for r in DROPPED})
    return removed


def kernel(frame, polys, rot):
    """Rasterise a courtyard turned by rot about the origin onto a local grid aligned with frame. Returns (K, t0)."""
    p = frame.p
    x0, y0, x1, y1 = C.bbox(polys, (rot, 0.0, 0.0))
    t0 = (rot, -math.floor(x0 / p) * p, -math.floor(y0 / p) * p)
    sh = C.courtyard_shape(polys, t0)
    nx, ny = int(math.ceil((x1 - x0) / p)) + 2, int(math.ceil((y1 - y0) / p)) + 2
    fr = C.Frame(nx * p, ny * p, p)
    K = fr.mask(sh)
    # crop to the courtyard's own cells so a 'valid' placement can reach the board edge
    kx, ky = np.flatnonzero(K.any(1)), np.flatnonzero(K.any(0))
    K = K[kx[0]:kx[-1] + 1, ky[0]:ky[-1] + 1]
    t0 = (rot, t0[1] - kx[0] * p, t0[2] - ky[0] * p)
    fr = C.Frame(K.shape[0] * p, K.shape[1] * p, p)
    return K, t0, fr


def pad_kernel(fr, pads, t0, side):
    m = np.zeros((fr.nx, fr.ny), bool)
    for it in pads:
        if C.side_of(it.get("net")) != side:
            continue
        sh = C.Polygon([C.xf(q, t0) for q in it["shell"]])
        fr.mask(sh.buffer(0) if not sh.is_valid else sh, m)
    return m


def fits_map(forbid, K):
    """True where placing K's origin cell at (i, j) overlaps no forbidden cell ('valid' correlation)."""
    if not K.any():
        return np.ones((forbid.shape[0] - K.shape[0] + 1, forbid.shape[1] - K.shape[1] + 1), bool)
    c = correlate(forbid.astype(np.float32), K.astype(np.float32), mode="valid", method="fft")
    return c < 0.5


def pack(W, recipe, parts, geom, s53_own=None, verbose=False):
    fr = C.Frame(W, H_BOARD)
    removed = part_set(parts)
    poses, status = {}, {}
    # tongue / outside parts move; everything else that exists stays
    must_move = []
    for ref, p in parts.items():
        if ref in removed:
            status[ref] = "removed"
            continue
        x0, y0, x1, y1 = C.bbox(p["polys"])
        if x1 > W - EDGE_MM + 1e-9 or y1 > H_BOARD + 1e-9 or ref in DISPLACE:
            must_move.append(ref)
        else:
            poses[ref] = C.IDENT
            status[ref] = "fixed"
    for ref, (tpl, nets, why) in NEW.items():
        must_move.append(ref)
    rec = recipe(W)
    missing = set(must_move) - set(rec)
    if missing:
        raise SystemExit(f"no recipe entry for {sorted(missing)} at W {W}")
    # ---- fixed occupancy (F, B) and fixed copper by isolation side
    occ = {"F": np.zeros((fr.nx, fr.ny), bool), "B": np.zeros((fr.nx, fr.ny), bool)}
    for ref, t in poses.items():
        p = parts[ref]
        m = fr.mask(C.courtyard_shape(p["polys"], t).buffer(GAP_MM))
        for s in (("F", "B") if p["tht"] else (p["side"],)):
            occ[s] |= m
    # fixed copper: s53 copper in cells whose s53 territory owner stays fixed
    s53fr = C.Frame(290.0, 190.0)
    if s53_own is None:
        s53_own = s53_owner(parts)
    own, refs = s53_own
    keep = np.isin(own, [i for i, r in enumerate(refs) if status.get(r) == "fixed"])
    hot53, low53 = domain_masks_s53(geom)
    nx, ny = fr.nx, fr.ny
    hot = (hot53 & keep)[:nx, :ny].copy()
    low = (low53 & keep)[:nx, :ny].copy()
    # fixed pads always count (a pad may sit in a neighbour's territory)
    for ref, t in poses.items():
        for it in parts[ref]["pads"]:
            s = C.side_of(it.get("net"))
            if s:
                fr.mask(C.Polygon(it["shell"]), hot if s == "HOT" else low)
    inside = np.zeros((nx, ny), bool)
    inside[:] = True
    e = int(round(EDGE_MM / fr.p))
    edge_forbid = np.zeros((nx, ny), bool)
    edge_forbid[:e, :] = edge_forbid[-e:, :] = edge_forbid[:, :e] = edge_forbid[:, -e:] = True
    ko = np.zeros((nx, ny), bool)
    for _, (a, b, c_, d) in KEEPOUTS:
        ko |= fr.mask(C.Polygon([(a, b), (c_, b), (c_, d), (a, d)]))
    for stud in ("J2", "J5"):
        x, y = parts[stud]["at"][:2]
        ko |= fr.mask(C.Point(x, y).buffer(STUD_KEEPOUT_MM))
    placed, failed = [], []
    lim = C.BARRIER_MM + 2 * fr.p            # raster distance from cell centres: two cells of margin, audited exactly
    for ref in [r for r in ORDER if r in must_move] + [r for r in must_move if r not in ORDER]:
        ax, ay, edge, rots = rec[ref]
        if ref in NEW:
            tpl = parts[NEW[ref][0]]
            p = dict(tpl, ref=ref, block="inlet_connectors", pads=[dict(it, ref=ref + "." + it["ref"].partition(".")[2],
                                              net=NEW[ref][1].get(it["ref"].partition(".")[2], it.get("net")))
                                         for it in tpl["pads"]])
            parts[ref] = p
        p = parts[ref]
        d_low = distance_transform_edt(~low) * fr.p
        d_hot = distance_transform_edt(~hot) * fr.p
        best = None
        for rot in rots:
            K, t0, kfr = kernel(fr, p["polys"], rot)
            # pads are in the board frame at the s53 pose: move them to the local frame with the same transform
            kp_hot = pad_kernel(kfr, p["pads"], t0, "HOT")
            kp_low = pad_kernel(kfr, p["pads"], t0, "LOW")
            if K.shape[0] > nx or K.shape[1] > ny:
                continue
            blocked = ko if edge else (edge_forbid | ko)     # an edge connector may sit flush (s53 J1, FET tabs)
            for s in (("F", "B") if p["tht"] else (p["side"],)):
                blocked = blocked | occ[s]
            ok = fits_map(blocked, K)
            ok &= fits_map(d_low < lim, kp_hot) & fits_map(d_hot < lim, kp_low)
            if not ok.any():
                continue
            ii, jj = np.nonzero(ok)
            # courtyard bbox of the placed part for these offsets
            kx = np.flatnonzero(K.any(1)); ky = np.flatnonzero(K.any(0))
            bx0 = (ii + kx[0]) * fr.p; bx1 = (ii + kx[-1] + 1) * fr.p
            by0 = (jj + ky[0]) * fr.p; by1 = (jj + ky[-1] + 1) * fr.p
            sel = np.ones(ii.shape, bool)
            if edge == "top":
                sel &= by0 <= EDGE_MM + EDGE_TOUCH_MM
            elif edge == "bottom":
                sel &= by1 >= H_BOARD - EDGE_MM - EDGE_TOUCH_MM
            elif edge == "right":
                sel &= bx1 >= W - EDGE_MM - EDGE_TOUCH_MM
            if not sel.any():
                continue
            cost = np.hypot((bx0 + bx1) / 2 - ax, (by0 + by1) / 2 - ay)
            cost[~sel] = np.inf
            k = int(np.argmin(cost))
            if best is None or cost[k] < best[0]:
                best = (float(cost[k]), rot, (rot, t0[1] + ii[k] * fr.p, t0[2] + jj[k] * fr.p))
        if best is None:
            failed.append(ref)
            status[ref] = "unplaced"
            if verbose:
                print("  cannot place", ref)
            continue
        t = best[2]
        # pads: s53 board frame -> t applied to the s53-local frame. The kernel used t0 on the s53 board-frame polys,
        # so the full transform is p' = R p + (tx, ty) with the same R: t is directly the board-frame transform.
        poses[ref] = t
        status[ref] = "new" if ref in NEW else "moved"
        m = fr.mask(C.courtyard_shape(p["polys"], t).buffer(GAP_MM))
        for s in (("F", "B") if p["tht"] else (p["side"],)):
            occ[s] |= m
        for it in p["pads"]:
            s = C.side_of(it.get("net"))
            if s:
                fr.mask(C.Polygon([C.xf(q, t) for q in it["shell"]]), hot if s == "HOT" else low)
        placed.append((ref, best[0]))
    return {"W": W, "poses": poses, "status": status, "failed": failed, "placed": placed, "frame": fr, "geom": geom}


_S53_OWN = None
_DOM = None


def s53_owner(parts):
    global _S53_OWN
    if _S53_OWN is None:
        fr = C.Frame(290.0, 190.0)
        board = fr.mask(C.Polygon(C.S53_OUTLINE))
        _S53_OWN = C.owner_map(fr, board, parts, {r: C.IDENT for r in parts})
    return _S53_OWN


def domain_masks_s53(geom):
    global _DOM
    if _DOM is None:
        _DOM = C.domain_copper(C.Frame(290.0, 190.0), geom)
    return _DOM


def report(res, parts):
    W, fr = res["W"], res["frame"]
    union = np.zeros((fr.nx, fr.ny), bool)
    union_f = np.zeros_like(union)
    rows = []
    for ref, t in sorted(res["poses"].items()):
        p = parts[ref]
        m = fr.mask(C.courtyard_shape(p["polys"], t))
        union |= m
        if p["side"] == "F" or p["tht"]:
            union_f |= m
        x0, y0, x1, y1 = C.bbox(p["polys"], t)
        rows.append({"ref": ref, "status": res["status"][ref], "block": p["block"], "domain": p["domain"],
                     "side": p["side"], "tht": p["tht"], "s53_at": p["at"], "transform": list(t),
                     "at": list(C.xf(p["at"][:2], t)) + [(p["at"][2] + t[0]) % 360],
                     "bbox": [round(v, 3) for v in (x0, y0, x1, y1)],
                     "courtyard_mm2": round(C.courtyard_shape(p["polys"]).area, 2)})
    area = W * H_BOARD
    j = next(r for r in rows if r["ref"] == "J1N")["bbox"]
    jc = ((j[0] + j[2]) / 2, (j[1] + j[3]) / 2)
    br = {it["ref"]: it["centre"] for it in parts["BR1"]["pads"] if it["layer"] == "F.Cu"}
    lanes = {k: round(math.hypot(jc[0] - v[0], jc[1] - v[1]), 1) for k, v in br.items() if k in ("BR1.2", "BR1.3")}
    return rows, {"j1n_centre_to_br1_ac_pins_mm": lanes,"outline_mm": [W, H_BOARD], "outline_mm2": area,
                  "courtyard_union_mm2": round(float(union.sum()) * fr.p ** 2, 1),
                  "courtyard_union_F_mm2": round(float(union_f.sum()) * fr.p ** 2, 1),
                  "utilisation_union_pct": round(100 * float(union.sum()) * fr.p ** 2 / area, 1)}


def barrier_audit(res, parts):
    """Minimum HOT-pad to LOW-pad distance over all parts (pads only, exact polygons)."""
    from shapely import STRtree
    hot, low = [], []
    for ref, t in res["poses"].items():
        for it in parts[ref]["pads"]:
            s = C.side_of(it.get("net"))
            if s:
                (hot if s == "HOT" else low).append((ref, C.Polygon([C.xf(q, t) for q in it["shell"]])))
    tree = STRtree([g for _, g in low])
    worst, worst_mv = (1e9, None, None), (1e9, None, None)
    moved = {r for r, s in res["status"].items() if s in ("moved", "new")}
    for ref, g in hot:
        for idx in tree.query(g.buffer(C.BARRIER_MM + 2.0)):
            lref, lg = low[int(idx)]
            if lref == ref:                       # a part's own pins (opto, isolator): its package creepage
                continue
            d = g.distance(lg)
            if d < worst[0]:
                worst = (float(d), ref, lref)
            if (ref in moved or lref in moved) and d < worst_mv[0]:
                worst_mv = (float(d), ref, lref)
    # RES_A (tank, 297 V rms at 28 A) >= 12.6 mm to SELV / PE on the outer layers (review-packet-s53 gate 5): s53 RES_A
    # outer copper (pads, tracks, zones) against the LOW pads of every moved or new part
    resa = [C.prim_shape(it) for it in res["geom"]["primitives"] if it.get("net") == "res_a" and it["layer"] in ("F.Cu", "B.Cu")]
    resa = shapely.unary_union([g for g in resa if g is not None])
    d_resa = min((g.distance(resa), ref) for ref, g in low if ref in moved) if any(r in moved for r, _ in low) else (None, None)
    return {"min_hot_low_pad_mm_other_parts": round(worst[0], 3), "pair": [worst[1], worst[2]],
            "min_moved_low_pad_to_res_a_outer_mm": round(d_resa[0], 3) if d_resa[0] is not None else None,
            "res_a_rule_mm": 12.6, "res_a_nearest_moved_part": d_resa[1],
            "min_involving_moved_or_new_mm": round(worst_mv[0], 3) if worst_mv[1] else None,
            "pair_moved": [worst_mv[1], worst_mv[2]],
            "note": "pads only, exact polygons, pairs within 10 mm searched; pours are checked on the raster at "
                    "placement time (fixed copper) and by the proxy's moat rule"}


def render(res, parts, rows, path_base):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MP, Rectangle
    col = {"bridge_fets_gate_drive": "#d62728", "rectifier_bus": "#ff7f0e", "mains_emi_fuse_mov": "#8c564b",
           "blower_ac_tap": "#e377c2", "tank_bank_studs_ct": "#9467bd", "ps2_isolated_bias": "#2ca02c",
           "sensing_protection_isolators": "#1f77b4", "connectors_selv_tco": "#333333", "mech_test": "#999999",
           "inlet_connectors": "#17becf"}
    W = res["W"]
    fig, ax = plt.subplots(figsize=(16, 11.5))
    ax.plot([0, 290, 290, 91, 91, 0, 0], [0, 0, 140, 140, 190, 190, 0], ls="--", c="0.6", lw=1, label="s53 outline")
    ax.add_patch(Rectangle((0, 0), W, H_BOARD, fill=False, ec="k", lw=2, label=f"native-22 {W:g} x {H_BOARD:g}"))
    for r in rows:
        p = parts[r["ref"]]
        t = tuple(r["transform"])
        for ly, pts in p["polys"]:
            q = [C.xf(v, t) for v in pts]
            mv = r["status"] in ("moved", "new")
            ax.add_patch(MP(q, closed=True, fc=col.get(p["block"], "y"), alpha=0.55 if ly.startswith("F") else 0.25,
                            ec="k" if mv else "none", lw=1.2 if mv else 0))
        if r["status"] in ("moved", "new") and r["courtyard_mm2"] > 20:
            x0, y0, x1, y1 = r["bbox"]
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, r["ref"], fontsize=8, ha="center", va="center", weight="bold")
        elif r["courtyard_mm2"] > 300:
            x0, y0, x1, y1 = r["bbox"]
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, r["ref"], fontsize=7, ha="center", va="center", color="0.15")
    for ref in [k for k, v in res["status"].items() if v == "removed" and k in INLET]:
        p = parts[ref]
        for ly, pts in p["polys"]:
            ax.add_patch(MP(pts, closed=True, fill=False, ec="#8c564b", lw=0.6, ls=":"))
    for name, (a, b, c_, d) in KEEPOUTS:
        ax.add_patch(Rectangle((a, b), c_ - a, d - b, fill=False, ec="c", lw=1, ls="-."))
    ax.text(150, 186, "dotted brown: parts that leave for the inlet module (s53 places)\n"
                      "black edge: moved or new parts; cyan dash-dot: jet strip keep-out", fontsize=8, ha="center")
    from matplotlib.patches import Patch
    hand = [Patch(fc=v, alpha=0.55, label=k.replace("_", " ")) for k, v in col.items()]
    ax.legend(handles=hand + ax.get_legend_handles_labels()[0][:0], loc="lower right", fontsize=7, framealpha=0.9)
    ax.set_xlim(-3, 293); ax.set_ylim(193, -3); ax.set_aspect("equal")
    ax.set_xticks(range(0, 291, 10)); ax.set_yticks(range(0, 191, 10)); ax.tick_params(labelsize=7)
    ax.grid(True, lw=0.3)
    ax.set_title(f"native-22 floorplan (placement only, no copper): {W:g} x {H_BOARD:g} mm vs s53 (dashed)")
    for ext in ("svg", "png"):
        fig.savefig(f"{path_base}.{ext}", dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=float, default=TARGET_W)
    ap.add_argument("--recipe", default="A")
    ap.add_argument("--scan", action="store_true", help="also scan widths for the smallest fitting outline")
    a = ap.parse_args()
    geom = C.load_geom()
    parts = C.load_parts(geom)
    res = pack(a.width, RECIPES[a.recipe], parts, geom, verbose=True)
    rows, summ = report(res, parts)
    removed = {r: parts[r] for r, s in res["status"].items() if s == "removed"}
    out = {
        "what": "native-22 floorplan: placement only (courtyards), no copper, no routing",
        "board_of_record_in": {"pcb": str(C.RUN / "section.kicad_pcb"), "sha256": C.S53_SHA, "geom": str(C.GEOM.relative_to(C.WT))},
        "recipe": a.recipe, "rules": {"gap_mm": GAP_MM, "edge_mm": EDGE_MM, "barrier_mm": C.BARRIER_MM,
                                       "raster_mm": C.PITCH, "keepouts": KEEPOUTS, "stud_keepout_mm": STUD_KEEPOUT_MM},
        "summary": dict(summ, fits=not res["failed"], unplaced=res["failed"],
                        n_fixed=sum(v == "fixed" for v in res["status"].values()),
                        n_moved=sum(v == "moved" for v in res["status"].values()),
                        n_new=sum(v == "new" for v in res["status"].values()),
                        n_removed=sum(v == "removed" for v in res["status"].values())),
        "barrier_audit": barrier_audit(res, parts),
        "displaced": DISPLACE,
        "removed": [{"ref": r, "why": (INLET.get(r) and "inlet module: " + INLET[r]) or "dropped: " + DROPPED[r],
                     "block": p["block"], "courtyard_mm2": round(C.courtyard_shape(p["polys"]).area, 1)}
                    for r, p in sorted(removed.items())],
        "new": {k: {"template": v[0], "nets": v[1], "why": v[2]} for k, v in NEW.items()},
        "anchors": {k: list(v[:3]) for k, v in RECIPES[a.recipe](a.width).items()},
        "parts": rows,
    }
    if a.scan:
        scan = []
        for rname, rfun in RECIPES.items():
            for W in np.arange(196.0, 232.0 + 1e-9, 1.0):
                r = pack(float(W), rfun, C.load_parts(geom), geom)
                scan.append({"recipe": rname, "W": float(W), "fits": not r["failed"], "unplaced": r["failed"]})
                print(f"  scan {rname} W {W:.0f}: {'fits' if not r['failed'] else 'unplaced ' + ','.join(r['failed'])}")
        smallest = {rn: min((s["W"] for s in scan if s["recipe"] == rn and s["fits"]), default=None) for rn in RECIPES}
        C.dump(C.RESULTS / "width_scan.json", {"height_mm": H_BOARD, "smallest_fitting_width_mm": smallest, "scan": scan,
                                               "note": "greedy packer, per recipe; 'fits' = every part placed legally. "
                                                       "A failure is a failure of this packer, not a proof of no fit."})
        out["summary"]["width_scan_smallest"] = smallest
    tag = f"native22_{a.width:g}" + ("" if a.recipe == "A" else a.recipe)
    C.dump(C.RESULTS / f"floorplan_{tag}.json", out)
    render(res, parts, rows, C.RENDERS / f"floorplan_{tag}")
    print(json.dumps(out["summary"], indent=1), json.dumps(out["barrier_audit"]))


if __name__ == "__main__":
    main()
