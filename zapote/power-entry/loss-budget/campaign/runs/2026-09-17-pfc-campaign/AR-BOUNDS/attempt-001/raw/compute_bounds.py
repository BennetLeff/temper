#!/usr/bin/env python3
"""AR-BOUNDS raw computation: copper R and L of the internal discharge loop.

Loop (AR-FAULT netlist, nets PFC_BUS_PLUS_390V / a1 / PFC_BUS_MINUS):
    bank+ -> [U10 failed-short] -> a1 -> [U9 healthy-on | failed-short] -> bank-

Board: zapote/power-entry/shunt-repair/candidate/section.kicad_pcb
       sha256 34e6fba9...  (the board the AR-FAULT netlist was extracted from)

The three loop nets' power routing (segments of width >= 3 mm) is planarised:
segment endpoints, pad centres and via centres are used as nodes; segments are
split at every node that touches them; F.Cu<->B.Cu transitions are made at vias
and at the through-hole loop pads. For each of the four electrolytic bank
capacitors the minimum-resistance copper path

    cap+ -> U10 cathode -> U10 anode -> U9 drain -> U9 source -> cap-

is extracted. R_copper = rho_Cu * length / (width * thickness) along the path.
L_copper uses the current-sheet model L = mu0 * h_eff * length / w_eff; two
explicit return-path assumptions bracket h_eff.

No measurement is claimed; every number is geometry-derived under a stated
assumption. <3 mm net members are excluded: the kA discharge cannot be carried
by the 0.5-1 mm sense/control routing in parallel with 8 mm power copper.
"""
from __future__ import annotations

import heapq
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sexpr import parse  # noqa: E402

REPO = Path("/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan")
BOARD = REPO / "zapote/power-entry/shunt-repair/candidate/section.kicad_pcb"

LOOPS = ["PFC_BUS_PLUS_390V", "a1", "PFC_BUS_MINUS"]
MIN_WIDTH_MM = 3.0
T_CU_MM = 0.07
H_DIELECTRIC_MM = 1.44
RHO_CU_20 = 1.72e-8
RHO_CU_100 = 2.30e-8
MU0 = 4.0 * math.pi * 1e-7
TOL = 0.06  # mm

root = parse(BOARD.read_text())[0]


def atom(x):
    return x[1] if isinstance(x, tuple) else None


def kids(n, h):
    return [x for x in n if isinstance(x, list) and x and atom(x[0]) == h]


def find(n, h):
    k = kids(n, h)
    return k[0] if k else None


def r_neg(theta_deg):
    c = math.cos(math.radians(theta_deg))
    s = math.sin(math.radians(theta_deg))
    return [[c, s], [-s, c]]


# ---- pads -------------------------------------------------------------------
pads = {}
for fp in kids(root, "footprint"):
    props = {atom(p[1]): p[2][1] for p in kids(fp, "property")}
    ref = props.get("Reference")
    at = find(fp, "at")
    if at is None:
        continue
    fx, fy = float(atom(at[1])), float(atom(at[2]))
    fr = float(atom(at[3])) if len(at) > 3 else 0.0
    for pad in kids(fp, "pad"):
        num = atom(pad[1])
        pat = find(pad, "at")
        lx, ly = float(atom(pat[1])), float(atom(pat[2]))
        M = r_neg(fr)
        gx = round(fx + M[0][0] * lx + M[0][1] * ly, 3)
        gy = round(fy + M[1][0] * lx + M[1][1] * ly, 3)
        net = find(pad, "net")
        netn = net[1][1] if net else None
        if netn in LOOPS:
            pads.setdefault((ref, str(num)), []).append((netn, gx, gy))

# ---- raw copper -------------------------------------------------------------
raw_segs = []   # (net, layer, ax, ay, bx, by, w)
vias = []       # (net, x, y)
for seg in kids(root, "segment"):
    net = find(seg, "net")
    netn = atom(net[1]) if net else None
    if netn not in LOOPS:
        continue
    w = float(atom(find(seg, "width")[1]))
    if w < MIN_WIDTH_MM:
        continue
    lay = atom(find(seg, "layer")[1])
    st, en = find(seg, "start"), find(seg, "end")
    raw_segs.append((netn, lay, float(atom(st[1])), float(atom(st[2])),
                     float(atom(en[1])), float(atom(en[2])), w))
for via in kids(root, "via"):
    net = find(via, "net")
    netn = atom(net[1]) if net else None
    if netn not in LOOPS:
        continue
    at = find(via, "at")
    vias.append((netn, float(atom(at[1])), float(atom(at[2]))))


def seg_point_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    L2 = vx * vx + vy * vy
    if L2 == 0:
        return math.hypot(px - ax, py - ay), 0.0
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy), t


# ---- planarise: nodes per net = endpoints + pad centres + via centres -------
NODE_PER_NET = {n: set() for n in LOOPS}
for netn, lay, ax, ay, bx, by, w in raw_segs:
    NODE_PER_NET[netn].add((round(ax, 3), round(ay, 3)))
    NODE_PER_NET[netn].add((round(bx, 3), round(by, 3)))
for (ref, num), vals in pads.items():
    for netn, x, y in vals:
        NODE_PER_NET[netn].add((round(x, 3), round(y, 3)))
for netn, x, y in vias:
    NODE_PER_NET[netn].add((round(x, 3), round(y, 3)))

graph = {}


def add_edge(u, v, r):
    graph.setdefault(u, []).append((v, r))
    graph.setdefault(v, []).append((u, r))


for netn, lay, ax, ay, bx, by, w in raw_segs:
    pts = [(ax, ay), (bx, by)]
    for (px, py) in NODE_PER_NET[netn]:
        d, t = seg_point_dist(px, py, ax, ay, bx, by)
        if d <= TOL and 0.0 < t < 1.0:
            pts.append((px, py))
    # order along segment
    def param(p):
        return (p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)
    pts = sorted(set(pts), key=param)
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            continue
        r = RHO_CU_20 * (length * 1e-3) / ((w * 1e-3) * (T_CU_MM * 1e-3))
        add_edge((lay, round(x1, 3), round(y1, 3)), (lay, round(x2, 3), round(y2, 3)), r)

# layer transitions at vias and at through-hole pads
for netn, x, y in vias:
    add_edge(("F.Cu", x, y), ("B.Cu", x, y), 1e-5)
for (ref, num), vals in pads.items():
    for netn, x, y in vals:
        a = ("F.Cu", round(x, 3), round(y, 3))
        b = ("B.Cu", round(x, 3), round(y, 3))
        if a in graph or b in graph:
            add_edge(a, b, 1e-6)


def dijkstra(src, dst):
    dist = {src: 0.0}
    prev = {}
    heapq.heappush_ = None
    pq = [(0.0, src)]
    done = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if u == dst:
            break
        for v, r in graph.get(u, []):
            nd = d + r
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    seglist = []
    tot_len = 0.0
    for i in range(1, len(path)):
        u, v = path[i - 1], path[i]
        length = math.hypot(v[1] - u[1], v[2] - u[2]) * (0.0 if u[0] != v[0] else 1.0)
        if u[0] != v[0]:
            seglist.append({"layer": "via", "length_mm": 1.6, "width_mm": None})
            continue
        w = None
        for netn, lay, ax, ay, bx, by, ww in raw_segs:
            if lay != u[0]:
                continue
            d, t = seg_point_dist((u[1] + v[1]) / 2, (u[2] + v[2]) / 2, ax, ay, bx, by)
            if d <= TOL:
                w = ww
                break
        tot_len += length
        seglist.append({"layer": u[0], "length_mm": round(length, 4), "width_mm": w})
    return {"resistance_20c_ohm": dist[dst], "total_len_mm": round(tot_len, 3),
            "polyline": [(p[1], p[2], p[0]) for p in path], "segments": seglist}


def snap(net, pt):
    x, y = pt
    nodes = [n for n in graph if n[0] in ("F.Cu", "B.Cu")]
    return min(nodes, key=lambda n: math.hypot(n[1] - x, n[2] - y))


u10_plus = pads[("U10", "2")][0][1:]
u10_anodes = [pads[("U10", "1")][0][1:], pads[("U10", "3")][0][1:]]
u9_drain = pads[("U9", "2")][0][1:]
u9_source = pads[("U9", "3")][0][1:]
bank_plus = {r: pads[(r, "1")][0][1:] for r in ("U36", "U37", "U38", "U39")}
bank_minus = {r: pads[(r, "2")][0][1:] for r in ("U36", "U37", "U38", "U39")}

results = {}
for r in ("U36", "U37", "U38", "U39"):
    cp = snap("PFC_BUS_PLUS_390V", bank_plus[r])
    cm = snap("PFC_BUS_MINUS", bank_minus[r])
    u10p = snap("PFC_BUS_PLUS_390V", u10_plus)
    u9d = snap("a1", u9_drain)
    u9s = snap("PFC_BUS_MINUS", u9_source)
    fwd = dijkstra(cp, u10p)
    ret = dijkstra(u9s, cm)
    best_a1 = None
    for an in u10_anodes:
        an_n = snap("a1", an)
        res = dijkstra(an_n, u9d)
        if res and (best_a1 is None or res["resistance_20c_ohm"] < best_a1["resistance_20c_ohm"]):
            best_a1 = res
    results[r] = {"forward_bus_plus": fwd, "a1": best_a1, "return_bus_minus": ret}


def totals(p):
    legs = (p["forward_bus_plus"], p["a1"], p["return_bus_minus"])
    if any(x is None for x in legs):
        return None
    res20 = sum(x["resistance_20c_ohm"] for x in legs)
    lens = []
    for x in legs:
        for s in x["segments"]:
            if s["layer"] != "via" and s["width_mm"]:
                lens.append((s["length_mm"], s["width_mm"]))
    L_tot = sum(l for l, _ in lens)
    w_eff = L_tot / sum(l / w for l, w in lens) if lens else None
    return {"R_copper_20c_ohm": res20, "R_copper_100c_ohm": res20 * (RHO_CU_100 / RHO_CU_20),
            "length_mm": round(L_tot, 3), "w_eff_mm": round(w_eff, 3),
            "legs_len_mm": {k: p[k]["total_len_mm"] for k in ("forward_bus_plus", "a1", "return_bus_minus")}}


def loop_area(p):
    pts = []
    for k in ("forward_bus_plus", "a1", "return_bus_minus"):
        for (px, py, _l) in p[k]["polyline"]:
            if not pts or pts[-1] != (px, py):
                pts.append((px, py))
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def max_horizontal_separation(p):
    """Worst-case planar offset between the forward+a1 path and the return path.

    For every vertex on the forward path, the distance to the nearest point on
    the return polyline; take the maximum. This is the horizontal offset the
    loop would span if the return current does not share the forward routing.
    """
    fwd = [pt for k in ("forward_bus_plus", "a1") for pt in p[k]["polyline"]]
    ret = [(x, y) for k in ("return_bus_minus",) for (x, y, _l) in p[k]["polyline"]]
    worst = 0.0
    for (fx, fy, _l) in fwd:
        dmin = min(math.hypot(fx - rx, fy - ry) for (rx, ry) in ret)
        worst = max(worst, dmin)
    return worst


report = {}
for r, p in results.items():
    t = totals(p)
    if t is None:
        report[r] = {"error": "path not found",
                     "legs": {k: (p[k] is not None) for k in p}}
        continue
    area = loop_area(p)
    d_h = max_horizontal_separation(p)
    h_low = H_DIELECTRIC_MM
    L_low = MU0 * (h_low * 1e-3) * (t["length_mm"] * 1e-3) / (t["w_eff_mm"] * 1e-3)
    h_high = H_DIELECTRIC_MM + d_h
    L_high = MU0 * (h_high * 1e-3) * (t["length_mm"] * 1e-3) / (t["w_eff_mm"] * 1e-3)
    report[r] = {**t, "loop_area_mm2": round(area, 2), "h_low_mm": h_low,
                 "h_high_mm": round(h_high, 3), "d_h_max_mm": round(d_h, 3),
                 "L_low_h": L_low, "L_high_h": L_high}

summary = {
    "board": str(BOARD.relative_to(REPO)),
    "board_sha256": hashlib.sha256(BOARD.read_bytes()).hexdigest(),
    "min_width_mm_filter": MIN_WIDTH_MM,
    "copper_thickness_mm": T_CU_MM,
    "dielectric_mm": H_DIELECTRIC_MM,
    "assumptions": [
        "all loop current flows in conductors of width >= 3 mm; <3 mm net members are sense/control routing",
        "copper thickness 0.07 mm on both F.Cu and B.Cu per the board stackup",
        "the B.Cu PFC_BUS_MINUS zone (off the direct path) is not modelled as a conductor",
        "L model: current sheet, L = mu0 * h_eff * length / w_eff",
        "L lower bound: return directly beneath the forward path (h = 1.44 mm core)",
        "L upper bound: return separation = projected loop area / path length",
    ],
    "per_capacitor": report,
}
(HERE / "geometry.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
