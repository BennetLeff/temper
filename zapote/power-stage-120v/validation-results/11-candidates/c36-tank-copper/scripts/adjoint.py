"""Adjoint (reciprocity) influence of every heat source on the c22 laminate hot spot, the FET-row max and C40 / C38.
python3 adjoint.py GEOM A4DIR OUT.json [pitch]
Linear SPD system: T_target = sum_cells G_cell * q_cell + sum_parts G_J * P + lead affine term."""
import json, math, os, sys
from pathlib import Path
import numpy as np
R = Path(__file__).resolve().parents[4] / "validation-results/04-board-current-thermal/round5-native21"
GEOM, A4DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PITCH = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
os.environ["B3_A4_DIR"] = A4DIR
sys.path.insert(0, str(R / "b3-convergence")); sys.path.insert(0, str(R / "b3-ratings"))
import thermal_body as tb, body_runs as br, fet_case
T = tb.T
br.rs.GEOM = Path(GEOM)
BAY = 55.0
rs = br.rs
rs.OPS["c22"] = {"I_t": 1.05 * 22.0, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
heat_j = json.loads(rs.HEAT_C28.read_text())
k = (1.05 * 22.0 / 29.4) ** 2
for p in heat_j["parts"]:
    if p["ref"] in br.TANK_ROWS:
        p["watts_nominal"] *= k; p["watts_worst"] *= k
hp = Path(OUT).with_suffix(".heat.json"); hp.write_text(json.dumps(heat_j))
case_str = rs.cases("c22")
brd = tb.Board(Path(GEOM), Path(OUT).parent / "cache")
nx, ny = brd.grid_n(PITCH); pitch = PITCH
x = brd.xmin + (np.arange(nx) + 0.5) * pitch; y = brd.ymin + (np.arange(ny) + 0.5) * pitch
board, cfrac = brd.window_arrays(pitch, 0, nx, 0, ny)
links = tb.barrel_links(brd.get_barrels(), brd.xmin, brd.ymin, pitch, 0, 0, nx, ny, board)
nz = len(T.LAYER_NAMES)
kk = np.full((nz, nx, ny), tb.K_FR4)
for layer, z in T.CU_INDEX.items():
    kk[z] = tb.K_FR4 + cfrac[layer] * (tb.K_CU - tb.K_FR4)
per_case = {}
heat = np.zeros_like(kk)
for item in case_str.split(","):
    c, _, sc = item.partition(":")
    hc = np.zeros_like(kk)
    T.remap_a4(c, x, y, board, hc, float(sc))
    per_case[c] = hc; heat += hc
parts, _ = tb.build_network_parts(brd, hp, "nominal", nz, nx, ny, brd.xmin, brd.ymin, pitch, 0, 0, 10, br.PART_BODIES, {}, lambda a, b: True)
spec = {r: ("2", tb.drain_lead_conductance(), t - BAY) for r, t in fet_case.t_case(22.0).items()}
leads = tb.build_lead_links(brd, spec, nx, ny, brd.xmin, brd.ymin, pitch, 0, 0)
rise, riseJ, rec = tb.solve_system(board, kk, tb.THK_MM * 1e-3, heat, 10, pitch * 1e-3, links, parts, leads=leads)
# targets: 1 mm block at the gate's hot spot, FET-row max cell, C40 / C38 body nodes
s = int(round(1.0 / pitch))
def block_cells(xc, yc):
    i0 = int(np.floor((xc - 0.5 - brd.xmin) / pitch + 1e-9)); j0 = int(np.floor((yc - 0.5 - brd.ymin) / pitch + 1e-9))
    return i0, j0
zF = T.CU_INDEX["F.Cu"]
# find this run's 1 mm block peak (F.Cu, any layer) like body_runs
best = None
for layer, z in T.CU_INDEX.items():
    nb_x, nb_y = nx // s, ny // s
    r_ = rise[z][:nb_x * s, :nb_y * s].reshape(nb_x, s, nb_y, s).mean(axis=(1, 3))
    cf = cfrac[layer][:nb_x * s, :nb_y * s].reshape(nb_x, s, nb_y, s).mean(axis=(1, 3))
    m_ = board[:nb_x * s, :nb_y * s].reshape(nb_x, s, nb_y, s).all(axis=(1, 3))
    r_ = np.where(m_ & (cf > 0.05), r_, -np.inf)
    ia, ja = np.unravel_index(np.argmax(r_), r_.shape)
    if best is None or r_[ia, ja] > best[0]:
        best = (r_[ia, ja], z, ia, ja)
_, zb, ia, ja = best
fet_sel = np.ix_(x <= 80, y <= 12.5)
zf, (fi, fj) = max(((z, np.unravel_index(np.argmax(rise[z][fet_sel]), rise[z][fet_sel].shape)) for z in T.CU_INDEX.values()),
                   key=lambda t: rise[t[0]][fet_sel][t[1]])
targets = {"block": ("cells", zb, [(ia * s + a, ja * s + b) for a in range(s) for b in range(s)]),
           "fet_row": ("cells", zf, [(fi, fj)])}
pidx = {p.ref: i for i, p in enumerate(parts)}
for r in ("C40", "C38", "R12"):
    if r in pidx: targets[r] = ("part", pidx[r], None)
base = {"block_c": tb.TAMB_C + float(best[0]) + BAY - 50, "block_xy": [float(x[ia * s] - pitch / 2 + 0.5), float(y[ja * s] - pitch / 2 + 0.5), T.LAYER_NAMES[zb]],
        "fet_row_c": tb.TAMB_C + float(rise[zf][fet_sel][fi, fj]) + BAY - 50,
        "fet_row_xy": [float(x[x <= 80][fi]), float(y[y <= 12.5][fj]), T.LAYER_NAMES[zf]],
        "parts_c": {r: tb.TAMB_C + float(riseJ[pidx[r]]) + BAY - 50 for r in ("C40", "C38", "R12", "R5") if r in pidx},
        "balance": rec}
# adjoint solves: zero-temperature leads, zero part watts, unit heat at the target
for p in parts: p.watts = 0.0
for lk in leads: lk.t_rise = 0.0
out = {"base": base, "targets": {}}
for name, (kind, a, cells) in targets.items():
    h = np.zeros_like(kk)
    if kind == "cells":
        for (i, j) in cells: h[a, i, j] += 1.0 / len(cells)
    else:
        parts[a].watts = 1.0
    G, GJ, _ = tb.solve_system(board, kk, tb.THK_MM * 1e-3, h, 10, pitch * 1e-3, links, parts, leads=leads)
    if kind == "part": parts[a].watts = 0.0
    contrib = {c: float((G * hc).sum()) for c, hc in per_case.items()}
    pc = {p.ref: float(GJ[i]) * pj for i, (p, pj) in enumerate(zip(parts, [q.meta["watts"] for q in parts]))}
    # spatial map of A4 contribution (2 mm bins, top cells)
    tot = sum(per_case.values())
    cmap = (G * tot)
    bins = {}
    for z in range(nz):
        ii, jj = np.nonzero(cmap[z] > 1e-5)
        for i, j in zip(ii, jj):
            key = (T.LAYER_NAMES[z], int(x[i] // 2 * 2), int(y[j] // 2 * 2))
            bins[key] = bins.get(key, 0) + float(cmap[z, i, j])
    top = sorted(bins.items(), key=lambda kv: -kv[1])[:40]
    # G field summary: K/W at distance
    out["targets"][name] = {"a4_by_case_K": dict(sorted(contrib.items(), key=lambda kv: -kv[1])),
                            "a4_total_K": sum(contrib.values()),
                            "parts_K_top": dict(sorted(pc.items(), key=lambda kv: -kv[1])[:25]),
                            "parts_total_K": sum(pc.values()),
                            "a4_bins_top": [[*k_, round(v, 3)] for k_, v in top]}
    np.save(Path(OUT).with_suffix(f".G_{name}.npy"), G.astype(np.float32))
Path(OUT).write_text(json.dumps(out, indent=1))
print(json.dumps(base, indent=1))
for n, t in out["targets"].items():
    print(n, "A4", round(t["a4_total_K"], 2), "parts", round(t["parts_total_K"], 2), {k_: round(v, 2) for k_, v in list(t["a4_by_case_K"].items())[:8]})
    print("   parts", {k_: round(v, 2) for k_, v in list(t["parts_K_top"].items())[:12]})
    print("   bins", t["a4_bins_top"][:15])
