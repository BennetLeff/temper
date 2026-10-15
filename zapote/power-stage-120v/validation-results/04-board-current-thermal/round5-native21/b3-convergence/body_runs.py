#!/usr/bin/env python3
"""One B3 solve (global or windowed) with the legacy or the body-level source model, plus per-part metrics.

Used by run_convergence.py. `run_case` is deterministic; it never edits ../b3/*.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

HERE = Path(__file__).resolve().parent
import thermal_body as tb  # noqa: E402

T = tb.T
sys.path.insert(0, str(tb.ROUND5 / "b3"))
import run_study as rs  # noqa: E402

PART_BODIES = json.loads((HERE / "inputs/part-bodies.json").read_text())["parts"]
TANK_ROWS = {"R5", "R39", "C21", "C22", "C23", "C151", "C152", "C5", "C6"}      # rows that scale with I_t^2 (h10_stall.py)
FET_REFS = ("Q2", "Q3", "Q5", "Q6")
WORK = HERE / "runs"
WIN_MARGIN = 2.0                                                                   # mm


def op_inputs(op: str):
    """(A4 case string, heat json path, heat mode). 'der14' = the h10-stall derated tank current (14 A ceiling x 1.05)."""
    if op == "c28":
        return rs.cases("c28"), rs.HEAT_C28, "nominal"
    if op == "nominal":
        return rs.cases("nominal"), rs.HEAT, "nominal"
    if op == "der14":
        i_t = 1.05 * 14.0
        rs.OPS["der14"] = {"I_t": i_t, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
        heat = json.loads(rs.HEAT_C28.read_text())
        k = (i_t / 29.4) ** 2
        for p in heat["parts"]:
            if p["ref"] in TANK_ROWS:
                p["watts_nominal"] *= k
                p["watts_worst"] *= k
        WORK.mkdir(exist_ok=True)
        path = HERE / "inputs" / "heat_der14.json"
        path.write_text(json.dumps(heat))
        return rs.cases("der14"), path, "nominal"
    raise KeyError(op)


def remap_a4_window(case, x, y, interior, heat, scale):
    """thermal.remap_a4 restricted to interior cells of a window; returns watts placed."""
    meta = json.loads((T.A4 / f"{case}.json").read_text())
    arrays = np.load(T.A4 / f"{case}-heat.npz")
    pitch = x[1] - x[0]
    xmin, ymin = x[0] - pitch / 2, y[0] - pitch / 2
    placed = 0.0
    for layer, z in T.CU_INDEX.items():
        pre = layer.replace(".", "_")
        key = pre + "_joule_w"
        if key not in arrays:
            continue
        src = arrays[key]
        ii, jj = np.nonzero(src)
        tx = np.floor((arrays[pre + "_x_mm"][ii] - xmin) / pitch).astype(int)
        ty = np.floor((arrays[pre + "_y_mm"][jj] - ymin) / pitch).astype(int)
        ok = (tx >= 0) & (tx < len(x)) & (ty >= 0) & (ty < len(y))
        tx, ty, ii, jj = tx[ok], ty[ok], ii[ok], jj[ok]
        ok = interior[tx, ty]
        np.add.at(heat[z], (tx[ok], ty[ok]), scale * src[ii[ok], jj[ok]])
        placed += float((scale * src[ii[ok], jj[ok]]).sum())
    for item in meta["barrel_heat_by_layer"]:
        px, py = item["xy_mm"]
        ix, iy = int(math.floor((px - xmin) / pitch)), int(math.floor((py - ymin) / pitch))
        if 0 <= ix < len(x) and 0 <= iy < len(y) and interior[ix, iy]:
            for layer, watts in item["layer_joule_w"].items():
                heat[T.CU_INDEX[layer], ix, iy] += scale * watts
                placed += scale * watts
    return placed


def report_entries(brd, ref, pad_numbers, pitch, i0, j0, nx, ny):
    """Pad copper used for reporting in every mode: heated pad numbers (all pads if unspecified), mounting layer."""
    pads = brd.pads_of(ref)
    nums = set(pad_numbers) if pad_numbers else set(pads)
    layer = "F.Cu" if any(l == "F.Cu" for n in nums for l, _ in pads[n]) else next(l for n in nums for l, _ in pads[n])
    out = []
    for n in sorted(nums):
        for l, poly in pads[n]:
            if l != layer:
                continue
            ii, jj, a = tb.pad_overlap(poly, brd.xmin, brd.ymin, pitch, i0, j0, nx, ny)
            if a.size:
                out.append((n, ii, jj, a))
    return layer, out


def pad_stats(rise_layer, entries, pitch, select=None):
    ii = np.concatenate([e[1] for e in entries if select is None or e[0] in select]) if entries else np.zeros(0, int)
    jj = np.concatenate([e[2] for e in entries if select is None or e[0] in select]) if entries else np.zeros(0, int)
    a = np.concatenate([e[3] for e in entries if select is None or e[0] in select]) if entries else np.zeros(0)
    if not a.size:
        return None
    # a cell shared by several pads is counted once per pad overlap (area weights add)
    v = rise_layer[ii, jj]
    mean = float((v * a).sum() / a.sum())
    full = a >= 0.5 * pitch * pitch
    vmax = float(v[full].max()) if full.any() else float(v[np.argmax(a)])
    per_pad = {}
    for e in entries:
        if select is None or e[0] in select:
            per_pad[e[0]] = float((rise_layer[e[1], e[2]] * e[3]).sum() / e[3].sum())
    return {"mean_k": mean, "max_cell_k": vmax, "area_mm2": float(a.sum()), "max_pad_mean_k": max(per_pad.values()),
            "cells": int(len(a))}


def bc_from_global(rise_g, pitch_g, origin_g, brd, pitch, i0, i1, j0, j1):
    """Ring values (all sheets) for a window, bilinear from a coarser solution (cell-centred) whose first cell
    starts at origin_g = (x, y) [mm] on pitch_g."""
    nz = rise_g.shape[0]
    nxw, nyw = i1 - i0, j1 - j0
    out = np.zeros((nz, nxw, nyw))
    xc = brd.xmin + (np.arange(i0, i1) + 0.5) * pitch
    yc = brd.ymin + (np.arange(j0, j1) + 0.5) * pitch
    gx = (xc - origin_g[0]) / pitch_g - 0.5
    gy = (yc - origin_g[1]) / pitch_g - 0.5
    GX, GY = np.meshgrid(gx, gy, indexing="ij")
    ring = np.zeros((nxw, nyw), bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    for z in range(nz):
        vals = map_coordinates(rise_g[z], [GX[ring], GY[ring]], order=1, mode="nearest")
        out[z][ring] = vals
    return out


def run_case(brd, op, h, pitch, copper="fraction", source="network", sens=None, window=None, bc=None,
             use_a4=True, use_parts=True, label="", return_rise=False, leads=None):
    """leads: None (no FET-lead path, the stage-19b model) or {"pad": "2", "g": W/K or {ref: W/K},
    "t_rise": K or {ref: K}} - each FET's drain pad tied to its tab at t_rise over the model ambient (thermal_body
    LeadLink; t_rise = T_case - bay air, since the gate shifts the whole field by bay - 50)."""
    t0 = time.time()
    sens = sens or {}
    case_str, heat_json, mode = op_inputs(op)
    nxg, nyg = brd.grid_n(pitch)
    i0, i1, j0, j1 = window if window else (0, nxg, 0, nyg)
    nx, ny = i1 - i0, j1 - j0
    x = brd.xmin + (np.arange(i0, i1) + 0.5) * pitch
    y = brd.ymin + (np.arange(j0, j1) + 0.5) * pitch
    pitch_m = pitch * 1e-3
    nz = len(T.LAYER_NAMES)
    need_binary = copper == "binary" or source == "point"
    if need_binary:
        assert window is None, "binary / point modes are global only"
        bx, by, bboard, bcopper, bpads, bbarrels = T.grid_geometry(brd.data, pitch)
        assert len(bx) == nx and len(by) == ny
    if copper == "binary":
        board = bboard
        cfrac = {n: bcopper[n].astype(float) for n in T.CU_INDEX}
        links = T.barrel_edges(bbarrels, bx, by, bboard)
    else:
        board, cfrac = brd.window_arrays(pitch, i0, i1, j0, j1)
        links = tb.barrel_links(brd.get_barrels(), brd.xmin, brd.ymin, pitch, i0, j0, nx, ny, board)
    k = np.full((nz, nx, ny), tb.K_FR4)
    for layer, z in T.CU_INDEX.items():
        k[z] = tb.K_FR4 + cfrac[layer] * (tb.K_CU - tb.K_FR4)
    heat = np.zeros_like(k)
    interior = board.copy()
    if window:
        interior[0, :] = interior[-1, :] = interior[:, 0] = interior[:, -1] = False
    a4_w = 0.0
    if use_a4:
        for item in case_str.split(","):
            c, _, sc = item.partition(":")
            if window:
                a4_w += remap_a4_window(c, x, y, interior, heat, float(sc))
            else:
                _, r_ = T.remap_a4(c, x, y, board, heat, float(sc))
                a4_w += r_["remapped_w"]
    parts, rows_point, omitted = [], [], []
    if use_parts:
        if source == "point":
            rows_point, _ = T.add_part_heat(heat_json, mode, x, y, board, bpads, heat, bcopper)
        else:
            def inside(px, py):
                if not window:
                    return True
                m = WIN_MARGIN   # mm margin from the window edge
                return (x[0] + m <= px <= x[-1] - m) and (y[0] + m <= py <= y[-1] - m)
            parts, omitted = tb.build_network_parts(brd, heat_json, mode, nz, nx, ny, brd.xmin, brd.ymin, pitch, i0, j0,
                                                    h, PART_BODIES, sens, inside)
    lead_links = []
    if leads is not None:
        spec = {}
        for ref in FET_REFS:
            fp = PART_BODIES[ref]
            if window and not ((x[0] + WIN_MARGIN <= fp["at"][0] <= x[-1] - WIN_MARGIN) and (y[0] + WIN_MARGIN <= fp["at"][1] <= y[-1] - WIN_MARGIN)):
                continue
            g = leads["g"][ref] if isinstance(leads["g"], dict) else leads["g"]
            t = leads["t_rise"][ref] if isinstance(leads["t_rise"], dict) else leads["t_rise"]
            spec[ref] = (leads.get("pad", "2"), float(g), float(t))
        lead_links = tb.build_lead_links(brd, spec, nx, ny, brd.xmin, brd.ymin, pitch, i0, j0)
    rise, riseJ, rec = tb.solve_system(board, k, tb.THK_MM * 1e-3, heat, h, pitch_m, links, parts,
                                       dirichlet=bc, label=label, leads=lead_links)
    # ------------------------------------------------------------------ metrics
    hp = json.loads(Path(heat_json).read_text())["parts"]
    by_net = {p.ref: (s, p) for s, p in enumerate(parts)}
    rows = []
    pt_rows = {r["ref"]: r for r in rows_point}
    for p in hp:
        ref = p["ref"]
        if window and not ((x[0] + WIN_MARGIN <= p["x_mm"] <= x[-1] - WIN_MARGIN) and (y[0] + WIN_MARGIN <= p["y_mm"] <= y[-1] - WIN_MARGIN)):
            continue
        if p.get("board_fraction") in (None, 0) or p.get(f"watts_{mode}") in (None, 0):
            continue
        layer, ent = report_entries(brd, ref, p.get("pad_numbers"), pitch, i0, j0, nx, ny)
        st = pad_stats(rise[T.CU_INDEX[layer]], ent, pitch)
        row = {"ref": ref, "mpn": PART_BODIES[ref]["mpn"], "watts_into_model": p[f"watts_{mode}"] * p["board_fraction"],
               "layer": layer, "x_mm": p["x_mm"], "y_mm": p["y_mm"], "pad_area_mm2": st["area_mm2"],
               "pad_mean_c": tb.TAMB_C + st["mean_k"], "pad_max_cell_c": tb.TAMB_C + st["max_cell_k"],
               "pad_max_padmean_c": tb.TAMB_C + st["max_pad_mean_k"]}
        if ref in by_net:
            s, np_ = by_net[ref]
            row.update(spec=np_.spec_key, tj_c=tb.TAMB_C + float(riseJ[s]),
                       r_pad_kw=np_.meta["r_pad"], r_top_kw=np_.r_top, tj_limit_c=np_.meta["tj_limit"],
                       body_air_w=float(np_.g_air * riseJ[s]),
                       tcase_c=tb.TAMB_C + float(riseJ[s]) - float(np_.g_air * riseJ[s]) * np_.r_top,
                       network_pad_area_mm2=np_.meta["pad_area_mm2"], sink_fraction=np_.meta["sink_fraction"])
            heated = [e[0] for e in ent if True]
            gst = None
            if np_.spec_key == "recom":
                th = {e[0] for e in ent if e[0] in tb.RECOM_THERMAL_PINS}
                gst = pad_stats(rise[T.CU_INDEX[layer]], ent, pitch, select=th)
            if gst:
                row["thermal_pins_mean_c"] = tb.TAMB_C + gst["mean_k"]
                row["thermal_pins_max_cell_c"] = tb.TAMB_C + gst["max_cell_k"]
        if ref in pt_rows:
            r = pt_rows[ref]
            row["point_deposit_cells"] = r["pad_cell_count"]
            row["point_deposit_area_mm2"] = r["pad_cell_count"] * pitch * pitch
            row["flux_concentration"] = st["area_mm2"] / (r["pad_cell_count"] * pitch * pitch)
            row["point_fallback"] = r["nearest_cell_fallback"]
        rows.append(row)
    q_rows = []
    for ref in FET_REFS:
        fp = PART_BODIES[ref]
        if window and not ((x[0] + WIN_MARGIN <= fp["at"][0] <= x[-1] - WIN_MARGIN) and (y[0] + WIN_MARGIN <= fp["at"][1] <= y[-1] - WIN_MARGIN)):
            continue
        layer, ent = report_entries(brd, ref, None, pitch, i0, j0, nx, ny)
        st = pad_stats(rise[T.CU_INDEX[layer]], ent, pitch)
        q_rows.append({"ref": ref, "pad_mean_c": tb.TAMB_C + st["mean_k"], "pad_max_cell_c": tb.TAMB_C + st["max_cell_k"],
                       "pad_area_mm2": st["area_mm2"]})
    expo = np.where(np.broadcast_to(interior if window else board, rise.shape), rise, -np.inf)
    zp, ip, jp = np.unravel_index(np.argmax(expo), rise.shape)
    peak = {"temperature_c": tb.TAMB_C + float(rise[zp, ip, jp]), "x_mm": float(x[ip]), "y_mm": float(y[jp]),
            "layer": T.LAYER_NAMES[zp]}
    # mesh-comparable hot-spot metric: peak of the 1 mm x 1 mm block-mean copper temperature (blocks aligned to the grid
    # origin, full blocks of board cells only). The same physical area on every mesh, unlike the single-cell peak.
    sblk = max(int(round(1.0 / pitch)), 1)
    mask = interior if window else board
    b1 = None
    for layer, z in T.CU_INDEX.items():
        nb_x, nb_y = nx // sblk, ny // sblk
        r_ = rise[z][:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk)
        m_ = mask[:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk).all(axis=(1, 3))
        cf = cfrac[layer][:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk).mean(axis=(1, 3))
        mean_ = r_.mean(axis=(1, 3))
        mean_ = np.where(m_ & (cf > 0.05), mean_, -np.inf)
        if np.isfinite(mean_).any():
            ia, ja = np.unravel_index(np.argmax(mean_), mean_.shape)
            cand = {"temperature_c": tb.TAMB_C + float(mean_[ia, ja]), "layer": layer,
                    "x_mm": float(x[ia * sblk] - pitch / 2 + 0.5), "y_mm": float(y[ja * sblk] - pitch / 2 + 0.5)}
            if b1 is None or cand["temperature_c"] > b1["temperature_c"]:
                b1 = cand
    fet_sel = np.ix_(x <= 80, y <= 12.5)
    fet_row = None
    if (x <= 80).any() and (y <= 12.5).any():
        fet_row = tb.TAMB_C + float(max(rise[z][fet_sel].max() for z in T.CU_INDEX.values()))
    lead_rows = []
    flat = rise.ravel()
    for lk in lead_links:
        tw = sum(sh * float((flat[gids] * w).sum()) for (gids, w, _, _), sh in zip(lk.groups, lk.shares))
        lead_rows.append({"ref": lk.ref, "pad": lk.pad, "g_w_per_k": lk.g, "t_case_c": tb.TAMB_C + lk.t_rise,
                          "pad_mean_c": tb.TAMB_C + tw, "w_to_sink": lk.g * (tw - lk.t_rise)})
    out = {"label": label, "op": op, "h": h, "pitch_mm": pitch, "copper": copper, "source": source, "sens": sens,
           "window": list(window) if window else None, "use_a4": use_a4, "use_parts": use_parts,
           "balance": rec, "a4_placed_w": a4_w, "peak": peak, "peak_1mm_block": b1, "fet_row_max_c": fet_row, "parts": rows, "fets": q_rows,
           "omitted_parts": omitted, "board_cells": int(board.sum()), "runtime_s": round(time.time() - t0, 1)}
    if leads is not None:
        out["leads"] = lead_rows
    if return_rise:
        return out, rise
    return out
