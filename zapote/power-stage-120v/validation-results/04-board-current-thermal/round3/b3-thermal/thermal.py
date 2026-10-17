#!/usr/bin/env python3
"""Energy-conserving 2.5-D finite-volume board heat solve for conditional cases.

Seven sheets represent four copper planes and three FR-4 dielectrics. All
quantities are SI internally. This is a thermal experiment, not an acceptance
rule or a substitute for measured assembly cooling.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import platform
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy
import shapely
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg, LinearOperator
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon

HERE = Path(__file__).resolve().parent
ROUND3 = HERE.parent
UNIT = HERE.parents[3]
A4 = ROUND3 / "a4-copper/outputs"
LAYER_NAMES = ("F.Cu", "dielectric 1", "In1.Cu", "dielectric 2",
               "In2.Cu", "dielectric 3", "B.Cu")
CU_INDEX = {"F.Cu": 0, "In1.Cu": 2, "In2.Cu": 4, "B.Cu": 6}
STACKUP_PATH = UNIT / "native-15/stackup.json"
STACKUP = json.loads(STACKUP_PATH.read_text())
SOLID_LAYERS = [entry for entry in STACKUP["layers"]
                if entry["type"] not in ("Top Solder Mask", "Bottom Solder Mask")]
THICK_MM = np.array([entry["thickness_mm"] for entry in SOLID_LAYERS])
assert tuple(entry["name"] for entry in SOLID_LAYERS) == LAYER_NAMES
assert abs(sum(entry["thickness_mm"] for entry in STACKUP["layers"])
           - STACKUP["board_thickness_mm"]) < 1e-9
K_CU = 390.0
K_FR4 = 0.3
TAMB_C = 50.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raster_polygon(shape: Polygon, x: np.ndarray, y: np.ndarray, out: np.ndarray) -> None:
    if shape.is_empty:
        return
    x0, y0, x1, y1 = shape.bounds
    ix = np.flatnonzero((x >= x0) & (x <= x1))
    iy = np.flatnonzero((y >= y0) & (y <= y1))
    if ix.size and iy.size:
        xx, yy = np.meshgrid(x[ix], y[iy], indexing="ij")
        out[np.ix_(ix, iy)] |= contains_xy(shape, xx, yy)


def grid_geometry(data: dict, pitch_mm: float):
    outline = Polygon(data["outline"]["shell"], data["outline"]["holes"])
    xmin, ymin, xmax, ymax = outline.bounds
    nx, ny = math.ceil((xmax-xmin)/pitch_mm), math.ceil((ymax-ymin)/pitch_mm)
    x = xmin + (np.arange(nx)+0.5)*pitch_mm
    y = ymin + (np.arange(ny)+0.5)*pitch_mm
    board = np.zeros((nx, ny), dtype=bool)
    raster_polygon(outline, x, y, board)
    copper = {name: np.zeros_like(board) for name in CU_INDEX}
    pads = defaultdict(lambda: defaultdict(set))
    barrels = {}
    for item in data["primitives"]:
        layer = item["layer"]
        if layer not in copper:
            continue
        kind = item["kind"]
        if kind in ("zone", "pad"):
            shape = Polygon(item["shell"], item["holes"])
        elif kind == "track":
            shape = LineString((item["start"], item["end"])).buffer(item["width_mm"]/2, 8)
        elif kind == "via":
            shape = Point(item["centre"]).buffer(item["diameter_mm"]/2, 16)
        else:
            continue
        raster_polygon(shape, x, y, copper[layer])
        if kind == "pad":
            ref = item["ref"].split(".")[0]
            pmask = np.zeros_like(board)
            raster_polygon(shape, x, y, pmask)
            pads[ref][layer].update(map(int, np.flatnonzero(pmask)))
        if kind in ("pad", "via"):
            drill = item.get("drill_mm", 0)
            if isinstance(drill, list):
                drill = drill[0] if drill[0] == drill[1] else 0
            if drill and drill > 0:
                xy = item["centre"]
                key = (kind, round(xy[0], 6), round(xy[1], 6), round(drill, 6))
                barrels.setdefault(key, {"xy_mm": xy, "drill_mm": drill,
                                         "layers": set()})["layers"].add(layer)
    for mask in copper.values():
        mask &= board
    return x, y, board, copper, pads, list(barrels.values())


def add_edge(rows, cols, vals, diag, a, b, g):
    a = np.asarray(a, dtype=np.int64).ravel()
    b = np.asarray(b, dtype=np.int64).ravel()
    g = np.asarray(g, dtype=float).ravel()
    if not len(a):
        return
    rows.extend((a, b))
    cols.extend((b, a))
    vals.extend((-g, -g))
    np.add.at(diag, a, g)
    np.add.at(diag, b, g)


def solve_stack(board: np.ndarray, k: np.ndarray, thickness_m: np.ndarray,
                heat_w: np.ndarray, h: float, pitch_m: float,
                barrel_edges=(), dirichlet_x_ends=False,
                dirichlet_bottom_face=False):
    """Return rise and conservation receipt. Cell-centred layers, insulated sides."""
    nz, nx, ny = k.shape
    area = pitch_m*pitch_m
    nxy = nx*ny
    ids = np.arange(nz*nxy).reshape(nz, nx, ny)
    diag = np.zeros(nz*nxy, dtype=float)
    rows, cols, vals = [], [], []
    for z in range(nz):
        sheet = k[z]*thickness_m[z]
        for axis in (0, 1):
            if axis == 0:
                a, b = ids[z, :-1, :], ids[z, 1:, :]
                ka, kb = sheet[:-1, :], sheet[1:, :]
                valid = board[:-1, :] & board[1:, :]
            else:
                a, b = ids[z, :, :-1], ids[z, :, 1:]
                ka, kb = sheet[:, :-1], sheet[:, 1:]
                valid = board[:, :-1] & board[:, 1:]
            g = 2*ka*kb/(ka+kb)
            add_edge(rows, cols, vals, diag, a[valid], b[valid], g[valid])
    for z in range(nz-1):
        g = area/(thickness_m[z]/(2*k[z]) + thickness_m[z+1]/(2*k[z+1]))
        add_edge(rows, cols, vals, diag, ids[z][board], ids[z+1][board], g[board])
    for z, i, j, z2, conductance in barrel_edges:
        if board[i, j]:
            add_edge(rows, cols, vals, diag, [ids[z, i, j]],
                     [ids[z2, i, j]], [conductance])
    conv = h*area
    for z in (0, nz-1):
        np.add.at(diag, ids[z][board], conv)
    if dirichlet_x_ends:
        for z in range(nz):
            for i in (0, nx-1):
                np.add.at(diag, ids[z, i][board[i]],
                          2*k[z, i][board[i]]*thickness_m[z])
    if dirichlet_bottom_face:
        np.add.at(diag, ids[-1][board],
                  2*k[-1][board]*area/thickness_m[-1])
    inactive = ~np.broadcast_to(board, (nz, nx, ny))
    diag[ids[inactive]] = 1.0
    rr = np.concatenate(rows + [np.arange(nz*nxy)])
    cc = np.concatenate(cols + [np.arange(nz*nxy)])
    vv = np.concatenate(vals + [diag])
    matrix = coo_matrix((vv, (rr, cc)), shape=(nz*nxy, nz*nxy)).tocsr()
    rhs = heat_w.ravel().copy()
    rhs[ids[inactive]] = 0.0
    pre = LinearOperator(matrix.shape, matvec=lambda v: v/diag)
    iterations = [0]
    def callback(_):
        iterations[0] += 1
    rise, info = cg(matrix, rhs, rtol=1e-9, atol=1e-12, M=pre,
                    maxiter=12000, callback=callback)
    if info != 0:
        raise RuntimeError(f"thermal CG failed: {info}, iterations={iterations[0]}")
    rise = rise.reshape(nz, nx, ny)
    conv_w = float(conv*(rise[0][board].sum()+rise[-1][board].sum()))
    boundary_w = 0.0
    if dirichlet_x_ends:
        for z in range(nz):
            for i in (0, nx-1):
                boundary_w += float((2*k[z, i][board[i]]*thickness_m[z]*rise[z, i][board[i]]).sum())
    bottom_w = 0.0
    if dirichlet_bottom_face:
        bottom_w = float((2*k[-1][board]*area/thickness_m[-1]*rise[-1][board]).sum())
    source_w = float(heat_w[:, board].sum())
    return rise, {"source_w": source_w, "convection_w": conv_w,
                  "fixed_end_w": boundary_w, "fixed_bottom_w": bottom_w,
                  "balance_w": source_w-conv_w-boundary_w-bottom_w,
                  "cg_iterations": iterations[0],
                  "relative_residual": float(np.linalg.norm(matrix@rise.ravel()-rhs)/max(np.linalg.norm(rhs), 1e-30))}


def analytic_selftest() -> dict:
    # Strip: x=50 mm, y=10 mm, 70 um Cu, 1 W uniform heat; end faces held at
    # ambient and both broad faces convect. The closed-form 1-D peak is exact.
    length, width, thick, watts, h = 0.050, 0.010, 70e-6, 1.0, 10.0
    gline = 2*h*width
    pprime = watts/length
    analytic = pprime/gline*(1-1/math.cosh(length/2*math.sqrt(gline/(K_CU*width*thick))))
    results = []
    for pitch in (0.001, 0.0005):
        nx, ny = round(length/pitch), round(width/pitch)
        board = np.ones((nx, ny), bool)
        k = np.full((1, nx, ny), K_CU)
        heat = np.full((1, nx, ny), watts/(nx*ny))
        rise, receipt = solve_stack(board, k, np.array([thick]), heat, h, pitch,
                                    dirichlet_x_ends=True)
        peak = float(rise.max())
        error = abs(peak-analytic)/analytic
        results.append({"pitch_mm": pitch*1000, "peak_rise_k": peak,
                        "analytic_peak_rise_k": analytic, "relative_error": error,
                        **receipt})
        if error > 0.02 or abs(receipt["balance_w"]) > 1e-7:
            raise AssertionError(f"uniform-strip oracle failed at {pitch}: {results[-1]}")
    # A single 10 x 10 mm column exercises every through-plane interface.
    # One watt enters at the centre of top copper; bottom exterior is fixed
    # at ambient. The half top slab plus full lower slabs are series resistors.
    p = 0.010
    col_k = np.array([K_CU, K_FR4, K_CU, K_FR4, K_CU, K_FR4, K_CU])
    col_thick = THICK_MM*1e-3
    col_heat = np.zeros((7, 1, 1))
    col_heat[0, 0, 0] = 1.0
    column, receipt = solve_stack(np.ones((1, 1), bool), col_k[:, None, None],
                                  col_thick, col_heat, 0.0, p,
                                  dirichlet_bottom_face=True)
    exact = (col_thick[0]/(2*col_k[0])
             + np.sum(col_thick[1:]/col_k[1:]))/(p*p)
    error = abs(float(column[0, 0, 0])-exact)/exact
    if error > 1e-10 or abs(receipt["balance_w"]) > 1e-9:
        raise AssertionError("through-thickness column oracle failed")
    return {"status": "PASS", "strip": results,
            "through_thickness_column": {"peak_rise_k": float(column[0, 0, 0]),
                                         "analytic_peak_rise_k": float(exact),
                                         "relative_error": error, **receipt}}


def remap_a4(case: str, x, y, board, heat):
    case_json = A4 / f"{case}.json"
    case_npz = A4 / f"{case}-heat.npz"
    meta = json.loads(case_json.read_text())
    arrays = np.load(case_npz)
    pitch = x[1]-x[0]
    xmin, ymin = x[0]-pitch/2, y[0]-pitch/2
    for layer, z in CU_INDEX.items():
        prefix = layer.replace(".", "_")
        key = prefix+"_joule_w"
        if key not in arrays:
            continue
        src = arrays[key]
        ii, jj = np.nonzero(src)
        tx = np.floor((arrays[prefix+"_x_mm"][ii]-xmin)/pitch).astype(int)
        ty = np.floor((arrays[prefix+"_y_mm"][jj]-ymin)/pitch).astype(int)
        if np.any(tx < 0) or np.any(tx >= len(x)) or np.any(ty < 0) or np.any(ty >= len(y)):
            raise ValueError("A4 heat outside thermal grid")
        np.add.at(heat[z], (tx, ty), src[ii, jj])
    for item in meta["barrel_heat_by_layer"]:
        px, py = item["xy_mm"]
        ix, iy = int(math.floor((px-xmin)/pitch)), int(math.floor((py-ymin)/pitch))
        if not board[ix, iy]:
            raise ValueError("A4 barrel heat outside board")
        for layer, watts in item["layer_joule_w"].items():
            heat[CU_INDEX[layer], ix, iy] += watts
    found = float(heat.sum())
    if abs(found-meta["loss_w"]) > 1e-8:
        raise AssertionError(f"A4 energy map {found} differs from {meta['loss_w']}")
    return meta, {"case_json_sha256": sha(case_json), "heat_npz_sha256": sha(case_npz),
                  "a4_loss_w": meta["loss_w"], "remapped_w": found}


def add_part_heat(path: Path, mode: str, x, y, board, pads, heat):
    data = json.loads(path.read_text())
    pitch = x[1]-x[0]
    xmin, ymin = x[0]-pitch/2, y[0]-pitch/2
    rows = []
    omitted = []
    for part in data["parts"]:
        fraction = part.get("board_fraction")
        source_watts = part.get(f"watts_{mode}")
        if fraction is None or source_watts is None:
            omitted.append({"ref": part["ref"], "reason": "unknown board fraction or loss"})
            continue
        if fraction == 0:
            omitted.append({"ref": part["ref"], "reason": "modeled as heatsink power; lead heat unknown"})
            continue
        watts = source_watts*fraction
        if watts == 0:
            continue
        ref = part["ref"]
        layer = "F.Cu" if pads[ref].get("F.Cu") else "B.Cu"
        cells = sorted(pads[ref].get(layer, ()))
        fallback = False
        if not cells:
            # A sub-cell pad can miss every cell centre on a coarse thermal
            # mesh. Deposit its energy at the nearest board cell and disclose
            # the resulting point-source mesh sensitivity.
            ix = int(np.argmin(abs(x-part["x_mm"])))
            iy = int(np.argmin(abs(y-part["y_mm"])))
            if not board[ix, iy]:
                raise ValueError(f"part {ref} is outside board")
            cells = [int(np.ravel_multi_index((ix, iy), board.shape))]
            fallback = True
        ii, jj = np.unravel_index(cells, board.shape)
        np.add.at(heat[CU_INDEX[layer]], (ii, jj), watts/len(cells))
        rows.append({"ref": ref, "watts_to_board": watts,
                     "source_watts": source_watts,
                     "assumed_board_fraction": fraction,
                     "unquantified_loss": part["has_unquantified_loss"],
                     "pad_layer": layer, "pad_cell_count": len(cells),
                     "nearest_cell_fallback": fallback,
                     "x_mm": part["x_mm"], "y_mm": part["y_mm"]})
    return rows, {"a6_heat_file": str(path), "a6_heat_sha256": sha(path),
                  "a6_status": data.get("status"), "mode": mode,
                  "parts_applied_w": sum(r["watts_to_board"] for r in rows),
                  "omitted_parts": omitted,
                  "all_complete_flags_false": all(not p.get("use_as_complete_b3_heat_source", False)
                                              for p in data["parts"])}


def barrel_edges(barrels, x, y, board):
    pitch = x[1]-x[0]
    xmin, ymin = x[0]-pitch/2, y[0]-pitch/2
    zpos = np.cumsum(THICK_MM)-THICK_MM/2
    links = []
    for b in barrels:
        ix, iy = int((b["xy_mm"][0]-xmin)//pitch), int((b["xy_mm"][1]-ymin)//pitch)
        if not (0 <= ix < len(x) and 0 <= iy < len(y) and board[ix, iy]):
            continue
        zs = sorted(CU_INDEX[layer] for layer in b["layers"] if layer in CU_INDEX)
        for za, zb in zip(zs, zs[1:]):
            # Conservative plating-only thermal bridge; no lead/solder core.
            area = math.pi*b["drill_mm"]*0.018*1e-6
            g = K_CU*area/((zpos[zb]-zpos[za])*1e-3)
            links.append((za, ix, iy, zb, g))
    return links


def run(args):
    geometry = Path(args.geometry)
    data = json.loads(gzip.open(geometry, "rt").read())
    board_path = UNIT / "native-15/section.kicad_pcb"
    if data["board_sha256"] != sha(board_path):
        raise ValueError("geometry board hash differs from native-15 board")
    x, y, board, copper, pads, barrels = grid_geometry(data, args.pitch_mm)
    nz, nx, ny = len(LAYER_NAMES), len(x), len(y)
    k = np.full((nz, nx, ny), K_FR4)
    for layer, z in CU_INDEX.items():
        k[z][copper[layer]] = K_CU
    heat = np.zeros_like(k)
    a4meta = None
    a4receipt = None
    if args.case != "none":
        a4meta, a4receipt = remap_a4(args.case, x, y, board, heat)
    part_rows, a6receipt = [], None
    if args.a6_heat:
        part_rows, a6receipt = add_part_heat(Path(args.a6_heat), args.a6_mode,
                                              x, y, board, pads, heat)
    links = barrel_edges(barrels, x, y, board)
    rise, balance = solve_stack(board, k, THICK_MM*1e-3, heat,
                                args.h, args.pitch_mm*1e-3, links)
    local_copper = None
    for layer, z in CU_INDEX.items():
        adjacent = {0: (1,), 2: (1, 3), 4: (3, 5), 6: (5,)}[z]
        delta = rise[z]-np.mean(rise[list(adjacent)], axis=0)
        delta[~copper[layer]] = -np.inf
        if np.isfinite(delta).any():
            i, j = np.unravel_index(np.argmax(delta), delta.shape)
            candidate = {"copper_minus_adjacent_fr4_k": float(delta[i, j]),
                         "x_mm": float(x[i]), "y_mm": float(y[j]), "layer": layer,
                         "fr4_sheet_indices": adjacent}
            if local_copper is None or candidate["copper_minus_adjacent_fr4_k"] > local_copper["copper_minus_adjacent_fr4_k"]:
                local_copper = candidate
    via_proxies = []
    if args.case != "none":
        empty = {tuple(item["xy_mm"]) for item in a4meta["barrel_heat_by_layer"]
                 if not item["filled_lead"]}
        for item in a4meta["via_currents"]:
            xy = item["xy"]
            if tuple(xy) not in empty or item["status"] != "solved":
                continue
            i, j = int(np.argmin(abs(x-xy[0]))), int(np.argmin(abs(y-xy[1])))
            via_proxies.append({"xy_mm": xy,
                                "max_abs_hop_amps": max(abs(a) for a in item["hop_amps"] if a is not None),
                                "adjacent_board_cell_max_c": TAMB_C+float(max(rise[z, i, j] for z in CU_INDEX.values())),
                                "adjacent_board_cell_max_rise_k": float(max(rise[z, i, j] for z in CU_INDEX.values()))})
    for part in part_rows:
        layer = part["pad_layer"]
        cells = sorted(pads[part["ref"]].get(layer, ()))
        if not cells:
            ix = int(np.argmin(abs(x-part["x_mm"])))
            iy = int(np.argmin(abs(y-part["y_mm"])))
            cells = [int(np.ravel_multi_index((ix, iy), board.shape))]
        temperatures = TAMB_C + rise[CU_INDEX[layer]].ravel()[cells]
        part["conditional_pad_cell_mean_c"] = float(temperatures.mean())
        part["conditional_pad_cell_max_c"] = float(temperatures.max())
    exposed = np.where(np.broadcast_to(board, rise.shape), rise, -np.inf)
    zpk, ipk, jpk = np.unravel_index(np.argmax(exposed), rise.shape)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out.with_suffix(".npz"), x_mm=x, y_mm=y,
                        board_mask=board, rise_k=rise, heat_w=heat)
    peak = {"temperature_c": TAMB_C+float(rise[zpk, ipk, jpk]),
            "rise_k": float(rise[zpk, ipk, jpk]), "x_mm": float(x[ipk]),
            "y_mm": float(y[jpk]), "layer": LAYER_NAMES[zpk]}
    fig, ax = plt.subplots(figsize=(12, 7))
    image = np.max(rise, axis=0).T + TAMB_C
    image[~board.T] = np.nan
    ax.imshow(image, origin="lower", extent=(x[0]-args.pitch_mm/2,
              x[-1]+args.pitch_mm/2, y[0]-args.pitch_mm/2,
              y[-1]+args.pitch_mm/2), aspect="equal", cmap="inferno")
    ax.plot(peak["x_mm"], peak["y_mm"], "co", markersize=5)
    ax.set(xlabel="board x (mm)", ylabel="board y (mm)",
           title=f"Conditional {args.case}; {args.h:g} W/m²K both faces; 50°C ambient")
    fig.colorbar(ax.images[0], label="max layer temperature (°C)")
    fig.tight_layout()
    fig.savefig(out.with_suffix(".png"), dpi=150)
    plt.close(fig)
    receipt = {"status": "conditional_experiment", "source_revision": "44417ae1489fd00e2d652fd3b2c1582b76d17630",
               "board_sha256": data["board_sha256"], "stackup_sha256": sha(STACKUP_PATH),
               "geometry_sha256": sha(geometry), "kicad_version": data["kicad_version"],
               "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                           "scipy": scipy.__version__, "shapely": shapely.__version__},
               "script_sha256": sha(Path(__file__)), "case": args.case,
               "pitch_mm": args.pitch_mm, "h_w_m2k_each_face": args.h,
               "ambient_c": TAMB_C, "layer_names": LAYER_NAMES,
               "layer_thickness_mm": THICK_MM.tolist(), "k_cu_w_mk": K_CU,
               "k_fr4_w_mk": K_FR4, "board_cells": int(board.sum()),
               "copper_cells_by_layer": {key: int(mask.sum()) for key, mask in copper.items()},
               "material_node_count_by_layer": {name: {"copper": int(copper[name].sum()),
                                                       "fr4": int(board.sum()-copper[name].sum())}
                                                if name in copper else {"fr4": int(board.sum())}
                                                for name in LAYER_NAMES},
               "heat_w_by_layer": {name: float(heat[z].sum()) for z, name in enumerate(LAYER_NAMES)},
               "thermal_barrel_links": len(links), "a4": a4receipt,
               "a6": a6receipt, "a6_parts_applied": part_rows,
               "balance": balance, "peak": peak,
               "largest_local_copper_minus_fr4": local_copper,
               "empty_via_board_cell_proxies": via_proxies,
               "limits": ["A4 case, if present, is one imposed current path, not a simultaneous operating load",
                          "A6 map is partial; unknown part losses and heat fractions remain",
                          "local pad-cell temperatures are not package body or junction temperatures and have no rating verdict",
                          "via-adjacent board-cell temperatures are not barrel-wall temperatures",
                          "10 um mask on each face excluded from solid; convection acts directly on outer thermal sheet",
                          "18 um plated barrels included as axial links; drill voids and solder/lead cores not spatially resolved",
                          "component source spread over actual KiCad pad copper cells; no body/contact/air heat path",
                          "convection h on both exposed faces is an assumed boundary, not measured enclosure airflow"]}
    out.write_text(json.dumps(receipt, indent=2)+"\n")
    return receipt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--geometry")
    ap.add_argument("--case", default="bus_dc_q2-p0125-pl18")
    ap.add_argument("--pitch-mm", type=float, default=2.0)
    ap.add_argument("--h", type=float, choices=(10, 25), default=10)
    ap.add_argument("--a6-heat")
    ap.add_argument("--a6-mode", choices=("nominal", "worst"), default="nominal")
    ap.add_argument("--output")
    args = ap.parse_args()
    if args.selftest:
        print(json.dumps(analytic_selftest(), indent=2))
    else:
        if not args.geometry or not args.output:
            ap.error("--geometry and --output are required")
        result = run(args)
        print(json.dumps({"peak": result["peak"], "balance": result["balance"]}))


if __name__ == "__main__":
    main()
