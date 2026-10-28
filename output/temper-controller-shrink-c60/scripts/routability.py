"""Routability estimate of the C60 floorplan WITHOUT routing, calibrated on the routed C49 board.

    python3 -I scripts/routability.py [--placement results/floorplan-acut.json] -> results/routability-<outline>.json,
                                                                                    renders/congestion-<outline>.png

Same netlist, two placements: C49 (as routed, C/pcb/controller.kicad_pcb) and C60 (this floorplan).
Plane nets selv_gnd and v3v3 are left out of the wiring demand: each of their pins drops through its own
via to In1 / In2 (LAYOUT.md "Decoupling", C/layout/fanout.py), so they cost a via site, not a route.

Measures (all ESTIMATES except the C49 'routed' figures, which are measured from the board file):
1. Per-net Euclidean minimum spanning tree (MST) of the pad centres, both placements. C49's routed length
   per net / its MST gives the router's detour factor; C60 routed length is predicted as
   sum(MST60 x C49 detour of that net) [EST].
2. Wiring density = predicted routed length x track pitch / routable area, as layer-equivalents, against
   C49's measured value. Pitch 0.30 mm = 0.15 track + 0.15 space (LAYOUT.md "Rules").
3. RUDY congestion map (Spindler & Johannes 2007): each net spreads MST length / bbox area uniformly over
   its pin bounding box (bbox grown 0.5 mm), on a 1 mm grid, smoothed over 5 x 5 mm windows; reported as
   percentiles and peak, C49 against C60. The C49 board's measured routed density (track length per
   5 x 5 mm window) is the calibration: it is what the in-house router reached on a board it closes on
   1 of 3 runs (DECISIONS C50 addendum).
4. Cut lines: nets whose MST crosses each vertical (X) and horizontal (Y) line, per mm of cut, against
   the cut's capacity (2 full routing layers F.Cu / B.Cu plus In2 used part-time: 1/0.30 tracks per mm per layer).
5. Inter-block nets (pins in more than one functional block) and the long nets LAYOUT.md lists.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402
import kicad_courtyard as kc  # noqa: E402

PLANES = {"selv_gnd", "v3v3"}
PITCH = 0.30
OX, OY = 58.0, 110.0
LONG_NETS = ["permit", "PERMIT_LATCH", "RUN_EN", "bus_fault", "all_good", "reset_clock", "latched_fault", "HS_FAULT",
             "COIL_FAULT", "line", "RUNAWAY_FAULT", "RAIL_FAULT", "SENSOR_LIVE"]     # check_layout.py:340-341


def mst(pts):
    n = len(pts)
    if n < 2:
        return 0.0, []
    used = [False] * n
    dist = [math.inf] * n
    par = [-1] * n
    dist[0] = 0.0
    total, edges = 0.0, []
    for _ in range(n):
        u = min((i for i in range(n) if not used[i]), key=lambda i: dist[i])
        used[u] = True
        if par[u] >= 0:
            total += dist[u]
            edges.append((pts[par[u]], pts[u]))
        for v in range(n):
            if not used[v]:
                d = math.dist(pts[u], pts[v])
                if d < dist[v]:
                    dist[v], par[v] = d, u
    return total, edges


def net_pins(parts, poses):
    nets = defaultdict(list)
    for ref, (X, Y, t) in poses.items():
        for q in parts[ref]["pads_local"]:
            if q["net"]:
                nets[q["net"]].append((ref, geom.l2w(X, Y, t, q["x"], q["y"])))
    return nets


def box_mean(a, k):
    """k x k moving average (same size, edge-normalised)."""
    pad = k // 2
    s = np.pad(a, pad, mode="constant")
    c = np.pad(np.ones_like(a), pad, mode="constant")
    S = s.cumsum(0).cumsum(1)
    Cc = c.cumsum(0).cumsum(1)
    S = np.pad(S, ((1, 0), (1, 0)))
    Cc = np.pad(Cc, ((1, 0), (1, 0)))
    ny, nx = a.shape
    out = (S[k:k + ny, k:k + nx] - S[:ny, k:k + nx] - S[k:k + ny, :nx] + S[:ny, :nx])
    cnt = (Cc[k:k + ny, k:k + nx] - Cc[:ny, k:k + nx] - Cc[k:k + ny, :nx] + Cc[:ny, :nx])
    return out / np.maximum(cnt, 1)


def rudy(nets_pins, board, res=1.0):
    x0, y0, x1, y1 = board
    nx, ny = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    g = np.zeros((ny, nx))
    for n, pins in nets_pins.items():
        if n in PLANES or len(pins) < 2:
            continue
        pts = [p for _, p in pins]
        L, _ = mst(pts)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bx0, bx1 = min(xs) - 0.5, max(xs) + 0.5
        by0, by1 = min(ys) - 0.5, max(ys) + 0.5
        dens = L / ((bx1 - bx0) * (by1 - by0))
        i0, i1 = max(int((bx0 - x0) / res), 0), min(int(math.ceil((bx1 - x0) / res)), nx)
        j0, j1 = max(int((by0 - y0) / res), 0), min(int(math.ceil((by1 - y0) / res)), ny)
        g[j0:j1, i0:i1] += dens
    return g


def routed_map(board_path, board, res=1.0):
    x0, y0, x1, y1 = board
    nx, ny = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    g = {lay: np.zeros((ny, nx)) for lay in ("F.Cu", "B.Cu", "In2.Cu")}
    b = kc.load(board_path)
    for s in kc.kids(b, "segment"):
        net = kc.kid(s, "net")[-1]
        if net in PLANES:
            continue
        lay = kc.kid(s, "layer")[1]
        (ax, ay), (bx, by) = kc.xy(kc.kid(s, "start")), kc.xy(kc.kid(s, "end"))
        L = math.hypot(bx - ax, by - ay)
        k = max(1, int(L / 0.25))
        for i in range(k):
            t = (i + 0.5) / k
            X, Y = ax + (bx - ax) * t - OX, OY - (ay + (by - ay) * t)
            ii, jj = int((X - x0) / res), int((Y - y0) / res)
            if 0 <= ii < nx and 0 <= jj < ny:
                g[lay][jj, ii] += L / k
    return g


def cut_profile(nets_pins, board, step=1.0):
    """Max nets crossing a vertical / horizontal cut, per mm of cut length."""
    x0, y0, x1, y1 = board
    edges = []
    for n, pins in nets_pins.items():
        if n in PLANES or len(pins) < 2:
            continue
        _, e = mst([p for _, p in pins])
        edges += e
    out = {}
    for axis, lo, hi, span in (("X", x0, x1, y1 - y0), ("Y", y0, y1, x1 - x0)):
        k = 0 if axis == "X" else 1
        prof = []
        c = lo + step
        while c < hi:
            n = sum(1 for a, b in edges if min(a[k], b[k]) < c <= max(a[k], b[k]))
            prof.append((round(c, 1), n))
            c += step
        worst = max(prof, key=lambda r: r[1])
        out[axis] = {"cut_length_mm": span, "max_crossings": worst[1], "at": worst[0],
                     "max_per_mm": round(worst[1] / span, 3), "mean_crossings": round(sum(n for _, n in prof) / len(prof), 1)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", default=str(OUT / "results/floorplan-acut.json"))
    a = ap.parse_args()
    parts, b49 = geom.load_parts()
    fpl = json.loads(Path(a.placement).read_text())
    board60 = tuple(fpl["board_world"])
    board49 = tuple(b49["outline_world"])
    pose49 = {r: tuple(p["world"]) for r, p in parts.items()}
    pose60 = {r: tuple(v["world"]) for r, v in fpl["placement"].items()}
    n49, n60 = net_pins(parts, pose49), net_pins(parts, pose60)
    routed = b49["track_length_per_net_mm"]

    rows = []
    for n in sorted(n49):
        if n in PLANES or len(n49[n]) < 2:
            continue
        m49, _ = mst([p for _, p in n49[n]])
        m60, _ = mst([p for _, p in n60[n]])
        r49 = routed.get(n, 0.0)
        blocks = sorted({parts[r]["block"] for r, _ in n49[n]})
        rows.append({"net": n, "pins": len(n49[n]), "mst49": m49, "mst60": m60, "routed49": r49, "blocks": blocks})
    # detour: per net routed / MST; nets carried by pours (routed << MST) use the median factor
    facs = sorted(r["routed49"] / r["mst49"] for r in rows if r["mst49"] > 1 and r["routed49"] > 0.5 * r["mst49"])
    med = facs[len(facs) // 2]
    for r in rows:
        f = r["routed49"] / r["mst49"] if r["mst49"] > 1 and r["routed49"] > 0.5 * r["mst49"] else med
        r["detour49"] = f
        r["pred60"] = r["mst60"] * f
    tot = {k: sum(r[k] for r in rows) for k in ("mst49", "mst60", "routed49", "pred60")}

    def area_free(board, holes):
        return (board[2] - board[0]) * (board[3] - board[1]) - len(holes) * math.pi * 16.0
    a49 = area_free(board49, [1] * 6)
    a60 = area_free(board60, fpl["holes"])
    routed_all = b49["track_length_total_mm"]
    plane_stub = sum(v for k, v in b49["track_length_per_net_mm"].items() if k in PLANES)
    # density in layer-equivalents: track area at pitch / routable area
    dens49 = tot["routed49"] * PITCH / a49
    dens60 = tot["pred60"] * PITCH / a60
    # plane stubs scale with pin count (unchanged) -> same absolute length, denser per area
    dens49_all = routed_all * PITCH / a49
    dens60_all = (tot["pred60"] + plane_stub) * PITCH / a60
    layers = b49["tracks_per_layer"]

    # per-layer obstruction: pad copper + 0.15 mm clearance halo (SMD pads F.Cu only, THT pads every layer),
    # vias 0.6 mm + 0.15 halo each side on every routing layer. The via count is held at C49's (signal vias and
    # plane fan-out vias scale with pins, not area; the C34 RTD stitching grid shrinks with its region: a small
    # conservative error)
    halo = 0.15
    smd_pad = sum((q["w"] + 2 * halo) * (q["h"] + 2 * halo) for p_ in parts.values() for q in p_["pads_local"]
                  if q["kind"] == "smd")
    tht_pad = sum((q["w"] + 2 * halo) * (q["h"] + 2 * halo) for p_ in parts.values() for q in p_["pads_local"]
                  if q["kind"] != "smd")
    via_area = b49["vias_total"] * (0.6 + 2 * halo) ** 2
    share = {lay: layers[lay]["length_mm"] / routed_all for lay in layers}
    per_layer = {}
    for lay in ("F.Cu", "B.Cu", "In2.Cu"):
        obst = tht_pad + via_area + (smd_pad if lay == "F.Cu" else 0.0)
        row = {}
        for tag, A, demand in (("c49", a49, routed_all), ("c60", a60, tot["pred60"] + plane_stub)):
            cap = (A - obst) / PITCH
            row[tag] = {"obstruction_mm2": round(obst), "free_mm2": round(A - obst), "capacity_mm": round(cap),
                        "demand_mm": round(demand * share[lay]), "demand_over_capacity": round(demand * share[lay] / cap, 3)}
        row["ratio_c60_over_c49"] = round(row["c60"]["demand_over_capacity"] / row["c49"]["demand_over_capacity"], 3)
        per_layer[lay] = row

    # RUDY and the measured C49 map
    R49 = rudy(n49, board49)
    R60 = rudy(n60, board60)
    M = routed_map(Path(b49["board_file"]), board49)
    Mall = M["F.Cu"] + M["B.Cu"] + M["In2.Cu"]
    k = 5
    R49s, R60s, Ms = box_mean(R49, k), box_mean(R60, k), box_mean(Mall, k)

    def pct(a):
        v = np.sort(a.ravel())
        return {p: round(float(v[int(p / 100 * (len(v) - 1))]), 3) for p in (50, 90, 95, 99)} | {"max": round(float(v[-1]), 3)}
    # calibration: measured routed density vs RUDY on C49 (same cells)
    corr = float(np.corrcoef(R49s.ravel(), Ms.ravel())[0, 1])
    scale = float((Ms.ravel() @ R49s.ravel()) / (R49s.ravel() @ R49s.ravel()))    # least-squares routed ~= s * RUDY
    pred_routed60 = R60s * scale
    cap_full = 2 / PITCH            # F.Cu + B.Cu
    cap_in2 = 3 / PITCH             # + In2 as a third layer
    hot49 = float(np.percentile(Ms, 99))
    frac_over = {f"cells_over_c49_p99_routed_{lab}": round(float((pred_routed60 > hot49 * m).mean() * 100), 2)
                 for lab, m in (("x1.0", 1.0), ("x1.25", 1.25), ("x1.5", 1.5))}
    frac_over["c49_cells_over_its_own_p99"] = 1.0

    cut49, cut60 = cut_profile(n49, board49), cut_profile(n60, board60)
    inter = [r for r in rows if len(r["blocks"]) > 1]
    longn = {n: {"routed49": round(routed.get(n, 0), 1),
                 "mst49": round(next((r["mst49"] for r in rows if r["net"] == n), 0), 1),
                 "mst60": round(next((r["mst60"] for r in rows if r["net"] == n), 0), 1)} for n in LONG_NETS}

    out = {
        "schema": "temper.controller-shrink-c60.routability.v1", "ESTIMATE": True,
        "placement_file": a.placement, "board49": board49, "board60": board60,
        "signal_nets": len(rows), "plane_nets_excluded": sorted(PLANES),
        "c49_routed_by_layer_mm": layers, "c49_routed_total_mm": routed_all,
        "c49_plane_net_track_mm": round(plane_stub, 1), "c49_vias": b49["vias_total"],
        "mst_total_mm": {"c49": round(tot["mst49"], 1), "c60": round(tot["mst60"], 1),
                         "ratio": round(tot["mst60"] / tot["mst49"], 3)},
        "signal_routed_mm": {"c49_measured": round(tot["routed49"], 1), "c60_predicted": round(tot["pred60"], 1),
                             "detour_median": round(med, 3)},
        "routable_area_mm2": {"c49": round(a49), "c60": round(a60), "ratio": round(a60 / a49, 3)},
        "wiring_density_layer_equivalents": {
            "signal_only": {"c49": round(dens49, 3), "c60": round(dens60, 3), "ratio": round(dens60 / dens49, 3)},
            "incl_plane_stubs": {"c49": round(dens49_all, 3), "c60": round(dens60_all, 3), "ratio": round(dens60_all / dens49_all, 3)},
            "note": "1.0 = one whole layer covered by 0.15/0.15 mm tracks; C49 uses F.Cu, B.Cu and In2 (In2 part-time)"},
        "per_layer_demand_vs_capacity": per_layer,
        "pad_area_mm2": {"smd_with_halo": round(smd_pad), "tht_with_halo": round(tht_pad), "via_area_c49_count": round(via_area)},
        "rudy_5mm_mm_per_mm2": {"c49": pct(R49s), "c60": pct(R60s),
                                "ratio_p95": round(pct(R60s)[95] / pct(R49s)[95], 3),
                                "ratio_p99": round(pct(R60s)[99] / pct(R49s)[99], 3),
                                "ratio_max": round(pct(R60s)["max"] / pct(R49s)["max"], 3)},
        "c49_measured_routed_5mm_mm_per_mm2": {"all_layers": pct(Ms),
                                               "F.Cu": pct(box_mean(M["F.Cu"], k)), "B.Cu": pct(box_mean(M["B.Cu"], k)),
                                               "In2.Cu": pct(box_mean(M["In2.Cu"], k))},
        "calibration": {"corr_rudy_vs_routed_c49": round(corr, 3), "scale_routed_per_rudy": round(scale, 3)},
        "c60_predicted_routed_5mm_mm_per_mm2": pct(pred_routed60),
        "capacity_mm_per_mm2": {"F+B": round(cap_full, 2), "F+B+In2": round(cap_in2, 2),
                                "note": "theoretical at 0.30 mm pitch; pads, vias and keep-outs take a share"},
        "hotspot_cells_pct": frac_over,
        "cut_lines": {"c49": cut49, "c60": cut60,
                      "capacity_tracks_per_mm": {"F+B": round(cap_full, 2), "F+B+In2": round(cap_in2, 2)}},
        "inter_block_nets": {"count": len(inter), "mst_c49": round(sum(r["mst49"] for r in inter), 1),
                             "mst_c60": round(sum(r["mst60"] for r in inter), 1),
                             "c49_routed": round(sum(r["routed49"] for r in inter), 1)},
        "long_nets_mm": longn,
        "top_nets_by_c60_mst": [{k_: (round(v, 1) if isinstance(v, float) else v) for k_, v in r.items()}
                                for r in sorted(rows, key=lambda r: -r["mst60"])[:15]],
    }
    (OUT / "results" / f"routability-{fpl['outline']}.json").write_text(json.dumps(out, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vmax = float(max(Ms.max(), pred_routed60.max()))
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), dpi=130)
    for ax, (img, bd, ttl) in zip(axs, ((Ms, board49, "C49 measured routed density (signal tracks, all layers), mm/mm2, 5 mm window"),
                                        (R49s * scale, board49, "C49 RUDY x calibration (pre-route estimate on the C49 placement)"),
                                        (pred_routed60, board60, "C60 floorplan RUDY x calibration [EST]"))):
        im = ax.imshow(img, origin="lower", extent=(bd[0], bd[2], bd[1], bd[3]), vmin=0, vmax=vmax, cmap="magma")
        ax.set_xlim(board49[0], board49[2])
        ax.set_title(ttl, fontsize=8)
        ax.contour(np.linspace(bd[0], bd[2], img.shape[1]), np.linspace(bd[1], bd[3], img.shape[0]), img,
                   levels=[hot49], colors="cyan", linewidths=0.6)
        fig.colorbar(im, ax=ax, fraction=0.02)
    fig.text(0.01, 0.005, f"cyan contour = C49 measured p99 ({hot49:.2f} mm/mm2); capacity F+B {cap_full:.1f}, F+B+In2 {cap_in2:.1f} mm/mm2 at 0.30 mm pitch", fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "renders" / f"congestion-{fpl['outline']}.png")
    plt.close(fig)
    print(json.dumps({k_: out[k_] for k_ in ("per_layer_demand_vs_capacity", "mst_total_mm", "signal_routed_mm", "routable_area_mm2",
                                             "wiring_density_layer_equivalents", "rudy_5mm_mm_per_mm2",
                                             "c49_measured_routed_5mm_mm_per_mm2", "calibration",
                                             "c60_predicted_routed_5mm_mm_per_mm2", "hotspot_cells_pct", "cut_lines",
                                             "inter_block_nets", "long_nets_mm")}, indent=1))


if __name__ == "__main__":
    main()
