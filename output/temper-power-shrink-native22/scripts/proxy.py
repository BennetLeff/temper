#!/usr/bin/env python3
"""Build B3 inputs for a floorplan proxy board ("transplant proxy"), with no routed copper and no build.

    python3 proxy.py --board s53                                   # the board of record, unchanged (the control)
    python3 proxy.py --board native22 --floorplan ../results/floorplan_native22_218.json

Writes work/<board>/ (gitignored, regenerable): geom.json.gz (outline, pads, vias), cache/fine_<key>.npz (B3's 0.0625 mm
copper masks), a4/<case>.npz|json (sparse copper Joule heat), heat_c28.json, part_bodies.json; and
results/proxy_<board>.json (what was kept, cut, filled and dropped).

Method (README section 3.2). B3 needs copper (per-layer fill), heat sources at pads, the A4 copper Joule-heat fields and
part bodies. A floorplan has none of the copper, so the proxy carries s53's own copper with each part:
  1. Territory: every board cell belongs to the part whose courtyard is nearest (Euclidean; holes, fiducials and test
     pads own nothing). Computed on s53 and again on the new floorplan.
  2. Copper: a new-board cell takes the s53 copper (every layer) found at the same spot relative to its owner (owner's
     rigid transform inverted), if that s53 spot was the same part's territory. Fixed parts keep their copper exactly.
     J1N / J3N take J1's / J3's territory.
  3. Gap fill (cells whose s53 source belonged to someone else): the owner's own mean s53 fill fraction per layer
     (ordered 4x4 dither). A SELV/PE owner fills only >= 8 mm from HOT copper, a HOT owner only >= 8 mm from SELV/PE
     copper, so the moat stays bare; owners that straddle the barrier fill nothing.
  4. Pads of every placed part are added at their new poses. Vias move with their s53 owner; a removed owner's vias go.
  5. A4 copper heat: every heat cell moves with its s53 owner; heat owned by parts that leave for the inlet module is
     dropped (the module carries it); all other heat is kept, wherever it lands (conservative: no lane is shortened).
  6. Heat rows of removed parts (L1, PS2) are dropped; moved rows follow their part.
For --board s53 every transform is the identity and nothing is removed: the proxy IS the s53 export.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys

import numpy as np
from scipy.ndimage import distance_transform_edt

import common as C

FINE = 0.0625
F = int(round(C.PITCH / FINE))          # fine cells per territory cell (4)
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
A4_CASES = ("sw_a-p00625-pl18", "sw_a_low-p00625-pl18", "sw_b_high-p00625-pl18", "sw_b_low-p00625-pl18",
            "res_a-p0125-pl18", "coil_feed-p0125-pl18", "leg_a_18p7-p00625-pl18", "leg_b_18p7-p00625-pl18",
            "hv_mixed_a-p00625-pl18", "hv_mixed_b-p00625-pl18", "bus_mixed_q2-p0125-pl18", "bus_mixed_q5-p0125-pl18",
            "ac_n_main-p0125-pl18", "ac_l_main-p0125-pl18")
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])
A4_DIR = C.B3 / "outputs"
HEAT_C28 = C.B3 / "b3/inputs/native21-board-heat-sources-c28.json"
BODIES = C.B3 / "b3-convergence/inputs/part-bodies.json"
S53_FINE = C.B3 / "b3-ratings/runs/cache" / ("fine_" + hashlib.sha256((C.S53_SHA + f"{FINE}").encode()).hexdigest()[:16] + ".npz")


def s53_fine():
    """B3's own 0.0625 mm masks of the s53 export (the cache file b3-ratings made, else built here)."""
    sys.path.insert(0, str(C.B3 / "b3-convergence"))
    import thermal_body as tb
    cache = C.WORK / "s53/cache"
    cache.mkdir(parents=True, exist_ok=True)
    dst = cache / S53_FINE.name
    if not dst.exists() and S53_FINE.exists():
        shutil.copy(S53_FINE, dst)
    return tb.Board(C.GEOM, cache).fine()


def a4_sparse(case):
    meta = json.loads((A4_DIR / f"{case}.json").read_text())
    if meta["board_sha256"] != C.S53_SHA:
        raise SystemExit(f"A4 case {case} was solved on {meta['board_sha256'][:12]}, not s53")
    z = np.load(A4_DIR / f"{case}-heat.npz")
    out = {}
    for L in LAYERS:
        pre = L.replace(".", "_")
        if pre + "_joule_w" not in z.files:
            continue
        a = z[pre + "_joule_w"]
        ii, jj = np.nonzero(a)
        out[L] = (z[pre + "_x_mm"][ii], z[pre + "_y_mm"][jj], a[ii, jj])
    return meta, out


def build_s53():
    """The control: s53 itself through the same sparse-A4 runner path."""
    d = C.WORK / "s53"
    (d / "a4").mkdir(parents=True, exist_ok=True)
    s53_fine()
    rep = {"board": "s53", "geometry": str(C.GEOM.relative_to(C.WT)), "board_sha256": C.S53_SHA, "a4": {}}
    for case in A4_CASES:
        meta, sp = a4_sparse(case)
        np.savez(d / "a4" / f"{case}.npz", **{f"{L}|{k}": v for L, (x, y, w) in sp.items() for k, v in zip("xyw", (x, y, w))})
        (d / "a4" / f"{case}.json").write_text(json.dumps({"loss_w": meta["loss_w"],
                                                            "barrel_heat_by_layer": meta["barrel_heat_by_layer"]}))
        rep["a4"][case] = {"loss_w": meta["loss_w"], "kept_w": meta["loss_w"]}
    shutil.copy(HEAT_C28, d / "heat_c28.json")
    shutil.copy(BODIES, d / "part_bodies.json")
    (d / "geom_path.txt").write_text(str(C.GEOM))
    C.dump(C.RESULTS / "proxy_s53.json", rep)
    return rep


def build_native22(fp_path, gap_fill=True):
    fp = json.loads(open(fp_path).read())
    if not fp["summary"]["fits"]:
        raise SystemExit("floorplan does not fit")
    W, H = fp["summary"]["outline_mm"]
    tag = "native22_" + f"{W:g}" + ("" if fp.get("recipe", "A") == "A" else fp["recipe"]) + ("" if gap_fill else "_nofill")
    d = C.WORK / tag
    (d / "a4").mkdir(parents=True, exist_ok=True)
    (d / "cache").mkdir(parents=True, exist_ok=True)
    geom = C.load_geom()
    parts = C.load_parts(geom)
    rows = {r["ref"]: r for r in fp["parts"]}
    new = fp["new"]
    for ref, nv in new.items():                         # J1N / J3N: template footprint, new nets
        tpl = parts[nv["template"]]
        parts[ref] = dict(tpl, ref=ref, pads=[dict(it, ref=ref + "." + it["ref"].partition(".")[2],
                                                   net=nv["nets"].get(it["ref"].partition(".")[2], it.get("net")))
                                              for it in tpl["pads"]])
    poses = {r: tuple(v["transform"]) for r, v in rows.items()}
    source = {r: (new[r]["template"] if r in new else r) for r in poses}   # whose s53 territory a part carries
    # ---------------------------------------------------------------- territories
    fr53 = C.Frame(290.0, 190.0)
    b53 = fr53.mask(C.Polygon(C.S53_OUTLINE))
    own53, refs53 = C.owner_map(fr53, b53, parts, {r: C.IDENT for r in parts if r not in new})
    fr = C.Frame(W, H)
    board = np.ones((fr.nx, fr.ny), bool)
    own, refs = C.owner_map(fr, board, parts, poses)
    idx53 = {r: i for i, r in enumerate(refs53)}
    src_idx = np.array([idx53.get(source[r], -2) for r in refs])
    # source cell (territory grid) for every new cell, per owner transform
    si = np.full(own.shape, -1, np.int64)
    sj = np.full(own.shape, -1, np.int64)
    I, J = np.indices(own.shape)
    xc, yc = (I + 0.5) * fr.p, (J + 0.5) * fr.p
    for k, r in enumerate(refs):
        m = own == k
        if not m.any():
            continue
        t = poses[r]
        xs, ys = C.xf_inv_arrays(xc[m], yc[m], t)
        si[m] = np.floor(xs / fr.p + 1e-9).astype(np.int64)
        sj[m] = np.floor(ys / fr.p + 1e-9).astype(np.int64)
    inb = (si >= 0) & (si < fr53.nx) & (sj >= 0) & (sj < fr53.ny)
    valid = np.zeros(own.shape, bool)
    valid[inb] = own53[si[inb], sj[inb]] == src_idx[own[inb]]
    # ---------------------------------------------------------------- fine copper transplant
    f53 = s53_fine()
    nfx, nfy = fr.nx * F, fr.ny * F
    cu = {L: np.zeros((nfx, nfy), np.uint8) for L in LAYERS}
    # fine sub-cell (a, b) of a territory cell maps to fine sub-cell (a', b') of its source cell, per rotation
    for rot in sorted({int(poses[r][0]) for r in refs}):
        sel = valid & np.isin(own, [k for k, r in enumerate(refs) if int(poses[r][0]) == rot])
        if not sel.any():
            continue
        ti, tj = np.nonzero(sel)
        for a in range(F):
            for b in range(F):
                # fine centre offset inside the cell, rotated back to the source frame
                ox, oy = (a + 0.5) * FINE - fr.p / 2, (b + 0.5) * FINE - fr.p / 2
                sx, sy = C.rot_xy(np.array(ox), np.array(oy), (360 - rot) % 360)
                sa = int(round((float(sx) + fr.p / 2) / FINE - 0.5))
                sb = int(round((float(sy) + fr.p / 2) / FINE - 0.5))
                for L in LAYERS:
                    cu[L][ti * F + a, tj * F + b] = f53["cu_" + L][si[ti, tj] * F + sa, sj[ti, tj] * F + sb]
    # ---------------------------------------------------------------- domains of transplanted copper (territory grid)
    hot53, low53 = C.domain_copper(fr53, geom)
    hot = np.zeros(own.shape, bool)
    low = np.zeros(own.shape, bool)
    hot[valid] = hot53[si[valid], sj[valid]]
    low[valid] = low53[si[valid], sj[valid]]
    # pads at their new poses count as copper of their side
    for r, t in poses.items():
        for it in parts[r]["pads"]:
            s = C.side_of(it.get("net"))
            if s:
                fr.mask(C.Polygon([C.xf(q, t) for q in it["shell"]]), hot if s == "HOT" else low)
    # ---------------------------------------------------------------- gap fill
    tot53 = np.bincount(own53[own53 >= 0].ravel(), minlength=len(refs53))
    fill = {}
    own53f = np.repeat(np.repeat(own53, F, 0), F, 1)
    for L in LAYERS:
        c = f53["cu_" + L][:own53f.shape[0], :own53f.shape[1]].astype(bool) & (own53f >= 0)
        s = np.bincount(own53f[c].ravel(), minlength=len(refs53)) / F ** 2
        fill[L] = np.where(tot53 > 0, s / np.maximum(tot53, 1), 0.0)
    gap = ~valid
    dom = np.array([parts[r]["domain"] for r in refs], object)
    lim = C.BARRIER_MM / fr.p
    d_hot = distance_transform_edt(~hot)
    gl = gap & (dom[own] == "LOW") & (d_hot >= lim)
    low_all = low | gl
    d_low = distance_transform_edt(~low_all)
    gh = gap & (dom[own] == "HOT") & (d_low >= lim)
    gfill = (gl | gh) if gap_fill else np.zeros_like(gl)   # --no-gap-fill: the sensitivity with bare gaps
    gi, gj = np.nonzero(gfill)
    filled_mm2 = {}
    for L in LAYERS:
        fv = fill[L][src_idx[own[gi, gj]].clip(0)]
        fv[src_idx[own[gi, gj]] < 0] = 0.0
        for a in range(F):
            for b in range(F):
                on = fv > (BAYER4[a, b] + 0.5) / 16.0
                cu[L][gi[on] * F + a, gj[on] * F + b] = 1
        filled_mm2[L] = round(float(fv.sum()) * fr.p ** 2, 1)
    # ---------------------------------------------------------------- pads and vias as primitives (and in the masks)
    prims = []
    ffr = C.Frame(W, H, FINE)
    padm = {L: np.zeros((nfx, nfy), bool) for L in LAYERS}
    for r, t in poses.items():
        for it in parts[r]["pads"]:
            q = dict(it)
            q["shell"] = [list(C.xf(v, t)) for v in it["shell"]]
            q["holes"] = [[list(C.xf(v, t)) for v in h] for h in it.get("holes", [])]
            q["centre"] = list(C.xf(it["centre"], t))
            prims.append(q)
            if q["layer"] in padm:
                ffr.mask(C.Polygon(q["shell"], q["holes"]), padm[q["layer"]])
    for L in LAYERS:
        cu[L] |= padm[L].astype(np.uint8)
    vias_kept = vias_dropped = 0
    for it in geom["primitives"]:
        if it["kind"] != "via":
            continue
        x, y = it["centre"]
        k = own53[int(x / fr53.p), int(y / fr53.p)]
        r = refs53[k] if k >= 0 else None
        tgt = r if r in poses else next((n for n, v in new.items() if v["template"] == r), None)
        if tgt is None:
            vias_dropped += 1
            continue
        nx_, ny_ = C.xf((x, y), poses[tgt])
        if not (0 <= nx_ < W and 0 <= ny_ < H):
            vias_dropped += 1
            continue
        prims.append(dict(it, centre=[nx_, ny_]))
        vias_kept += 1
    # ---------------------------------------------------------------- write geometry + cache
    masks = {"board": np.ones((nfx, nfy), np.uint8)}
    for L in LAYERS:
        masks["cu_" + L] = cu[L]
    hsh = hashlib.sha256()
    for k in sorted(masks):
        hsh.update(masks[k].tobytes())
    hsh.update(json.dumps(prims, sort_keys=True).encode())
    sha = "proxy-" + hsh.hexdigest()
    g = {"board_sha256": sha, "exporter": "temper-power-shrink-native22/proxy.py (transplant proxy, not a routed board)",
         "outline": {"shell": [[0.0, 0.0], [W, 0.0], [W, H], [0.0, H]], "holes": []}, "primitives": prims}
    with gzip.open(d / "geom.json.gz", "wt") as f:
        json.dump(g, f)
    key = hashlib.sha256((sha + f"{FINE}").encode()).hexdigest()[:16]
    for old in (d / "cache").glob("fine_*.npz"):
        old.unlink()
    np.savez_compressed(d / "cache" / f"fine_{key}.npz", **masks)
    (d / "geom_path.txt").write_text(str(d / "geom.json.gz"))
    # ---------------------------------------------------------------- A4 heat transplant
    tgt_of = {}
    for k, r in enumerate(refs53):
        tgt_of[k] = r if r in poses else next((n for n, v in new.items() if v["template"] == r), None)
    a4rep = {}
    for case in A4_CASES:
        meta, sp = a4_sparse(case)
        out, kept, drop_rm, drop_out, off_terr, by_rm = {}, 0.0, 0.0, 0.0, 0.0, {}
        for L, (x, y, w) in sp.items():
            k = own53[np.floor(x / fr53.p).astype(int), np.floor(y / fr53.p).astype(int)]
            nxs, nys, ws, ok_all = [], [], [], np.zeros(len(w), bool)
            for kk in np.unique(k):
                m = k == kk
                r = tgt_of.get(int(kk)) if kk >= 0 else None
                if r is None:
                    drop_rm += float(w[m].sum())
                    nm = refs53[kk] if kk >= 0 else "(no owner)"
                    by_rm[nm] = by_rm.get(nm, 0.0) + float(w[m].sum())
                    continue
                xx, yy = C.xf_arrays(x[m], y[m], poses[r])
                inside = (xx >= 0) & (xx < W) & (yy >= 0) & (yy < H)
                drop_out += float(w[m][~inside].sum())
                ti = np.floor(xx[inside] / fr.p).astype(int)
                tj = np.floor(yy[inside] / fr.p).astype(int)
                off_terr += float(w[m][inside][own[ti, tj] != refs.index(r)].sum())
                nxs.append(xx[inside]); nys.append(yy[inside]); ws.append(w[m][inside])
            if ws:
                out[L] = (np.concatenate(nxs), np.concatenate(nys), np.concatenate(ws))
                kept += float(out[L][2].sum())
        barrels = []
        for b in meta["barrel_heat_by_layer"]:
            x, y = b["xy_mm"]
            kk = own53[int(x / fr53.p), int(y / fr53.p)]
            r = tgt_of.get(int(kk)) if kk >= 0 else None
            bw = sum(b["layer_joule_w"].values())
            if r is None:
                drop_rm += bw
                continue
            nx_, ny_ = C.xf((x, y), poses[r])
            if not (0 <= nx_ < W and 0 <= ny_ < H):
                drop_out += bw
                continue
            barrels.append(dict(b, xy_mm=[nx_, ny_]))
            kept += bw
        np.savez(d / "a4" / f"{case}.npz", **{f"{L}|{k}": v for L, (x, y, w) in out.items() for k, v in zip("xyw", (x, y, w))})
        (d / "a4" / f"{case}.json").write_text(json.dumps({"loss_w": kept, "barrel_heat_by_layer": barrels}))
        a4rep[case] = {"loss_w_s53": round(meta["loss_w"], 6), "kept_w": round(kept, 6),
                       "dropped_with_removed_parts_w": round(drop_rm, 6), "dropped_outside_w": round(drop_out, 6),
                       "kept_outside_own_territory_w": round(off_terr, 6),
                       "dropped_by_owner_w": {k: round(v, 6) for k, v in sorted(by_rm.items(), key=lambda kv: -kv[1])[:8]}}
    # ---------------------------------------------------------------- heat rows and part bodies
    removed = {r["ref"] for r in fp["removed"]}
    heat = json.loads(HEAT_C28.read_text())
    keep_rows, dropped_rows = [], []
    for p in heat["parts"]:
        if p["ref"] in removed:
            dropped_rows.append(p["ref"])
            continue
        if p["ref"] in poses:
            p["x_mm"], p["y_mm"] = C.xf((p["x_mm"], p["y_mm"]), poses[p["ref"]])
        keep_rows.append(p)
    heat["parts"] = keep_rows
    heat["status"] = str(heat.get("status")) + " | native-22 transplant proxy: rows of removed parts dropped, moved rows moved"
    (d / "heat_c28.json").write_text(json.dumps(heat))
    bodies = json.loads(BODIES.read_text())
    for r, b in bodies["parts"].items():
        if r in poses and tuple(poses[r]) != C.IDENT:
            x, y = C.xf(b["at"][:2], poses[r])
            b["at"] = [x, y, ((b["at"][2] if len(b["at"]) > 2 else 0.0) + poses[r][0]) % 360]
    (d / "part_bodies.json").write_text(json.dumps(bodies))
    # ---------------------------------------------------------------- report
    a_new = W * H
    cuarea = {L: round(float(cu[L].sum()) * FINE ** 2, 1) for L in LAYERS}
    a53 = float(b53.sum()) * fr53.p ** 2
    cu53 = {L: round(float((f53["cu_" + L]).sum()) * FINE ** 2, 1) for L in LAYERS}
    rep = {"board": tag, "floorplan": str(fp_path), "board_sha256": sha, "outline_mm": [W, H],
           "territory_cells_valid_pct": round(100 * float(valid.mean()), 2),
           "gap_cells_pct": round(100 * float(gap.mean()), 2), "gap_filled_cells_pct": round(100 * float(gfill.mean()), 2),
           "gap_fill_mm2_equiv_by_layer": filled_mm2,
           "copper_mm2_by_layer": cuarea, "copper_fraction_by_layer": {L: round(v / a_new, 4) for L, v in cuarea.items()},
           "s53_copper_mm2_by_layer": cu53, "s53_copper_fraction_by_layer": {L: round(v / a53, 4) for L, v in cu53.items()},
           "vias_kept": vias_kept, "vias_dropped": vias_dropped, "pads": sum(1 for p in prims if p["kind"] == "pad"),
           "heat_rows_dropped": dropped_rows, "a4": a4rep,
           "a4_total": {k: round(sum(v[k] for v in a4rep.values()), 4) for k in
                        ("loss_w_s53", "kept_w", "dropped_with_removed_parts_w", "dropped_outside_w",
                         "kept_outside_own_territory_w")}}
    C.dump(C.RESULTS / f"proxy_{tag}.json", rep)
    np.savez_compressed(d / "territory.npz", own=own, valid=valid, gfill=gfill, refs=np.array(refs))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=("s53", "native22"))
    ap.add_argument("--floorplan", default=str(C.RESULTS / "floorplan_native22_218.json"))
    ap.add_argument("--no-gap-fill", action="store_true", help="sensitivity: leave gap cells bare (lower-bound copper)")
    a = ap.parse_args()
    rep = build_s53() if a.board == "s53" else build_native22(a.floorplan, not a.no_gap_fill)
    print(json.dumps({k: v for k, v in rep.items() if k != "a4"}, indent=1))


if __name__ == "__main__":
    main()
