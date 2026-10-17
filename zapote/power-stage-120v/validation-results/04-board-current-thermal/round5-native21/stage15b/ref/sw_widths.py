#!/usr/bin/env python3
"""Stage 15: SW_A / SW_B tank-copper cross-sections on a routed copper dump, and the width that the
clearance rules leave available at each cut.

For each run (net, layer, flow direction, cut window) the copper of that net on that layer is cut
every STEP mm perpendicular to the flow; the width is the total copper length on the cut inside the
window (parallel paths count, as in task 04 round 5's 2 mm section cuts).

"Available" widths add the free area: board inset 0.5 mm (min_copper_edge_clearance) minus every
other-net item buffered by native-21's pairwise clearance (layout/rules21.py: 8.0 SELV/PE<->HOT,
5.0 around tank nodes, 3.2 between HOT groups, 0.2 floor), and minus SELV/PE copper on ANY layer
buffered 8.0 (plan-view barrier). Two variants:
  hard  - pads (THT all layers, SMD on their side), vias, tracks, SELV/PE barrier; other-net POURS ignored
          (they are re-drawable outlines);
  all   - hard + other-net pours on the same layer as they are filled today.
Requirement: IPC-2221 external, 70 um, 20 K (round-6 board_side.py rule): 9.82 mm at 28 A. The SW_B
strip along the bank carries k/5 of the current below the k-th tap, so its requirement steps down.
usage: python3 sw_widths.py <copper-dump.json> <section.kicad_pcb> [UNIT] -> out/sw_widths.json
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DUMP, PCB = Path(sys.argv[1]), Path(sys.argv[2])
UNIT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
spec = importlib.util.spec_from_file_location("rules21", UNIT / "native-21/layout/rules21.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

T_MIL, K_EXT = 70e-3 / 0.0254, 0.048
STEP = 0.5
EDGE = 0.5


def ipc_width(i, dt=20.0):
    a = (i / (K_EXT * dt ** 0.44)) ** (1 / 0.725)
    return a / T_MIL * 0.0254


def ipc_dt(i, w):
    return (i / (K_EXT * (w / 0.0254 * T_MIL) ** 0.725)) ** (1 / 0.44)


# flow 'x': current flows along x, cuts are vertical lines x = c over window y; 'y' the other way.
RUNS = [
    # name, net, layer, flow, (c0, c1), (w0, w1), current fraction
    ("SW_A B.Cu leg-A link, Q3 to Q2", "sw_a", "B.Cu", "x", (51.5, 72.0), (0.6, 15.0), 1.0),
    ("SW_A F.Cu, Q2 stub to first step", "sw_a", "F.Cu", "x", (77.0, 93.0), (5.0, 27.0), 1.0),
    ("SW_A F.Cu, second step", "sw_a", "F.Cu", "x", (94.0, 103.0), (15.0, 34.0), 1.0),
    ("SW_A F.Cu, corner leg x 103.6-110", "sw_a", "F.Cu", "y", (31.0, 36.5), (96.0, 118.0), 1.0),
    ("SW_A F.Cu, run y 37-48", "sw_a", "F.Cu", "x", (111.0, 138.0), (33.0, 52.0), 1.0),
    ("SW_A F.Cu, leg x 139-148.6 to T1", "sw_a", "F.Cu", "y", (49.0, 93.0), (130.0, 160.0), 1.0),
    ("SW_B B.Cu, FET band", "sw_b", "B.Cu", "x", (1.0, 100.0), (0.6, 30.5), 1.0),
    ("SW_B F.Cu parallel option (no copper today)", "sw_b", "F.Cu", "x", (31.0, 100.0), (8.0, 30.5), 1.0),
    ("SW_B B.Cu, drop x 100.5-110", "sw_b", "B.Cu", "y", (28.0, 36.5), (92.0, 118.0), 1.0),
    ("SW_B B.Cu, run y 37-50 to the bank", "sw_b", "B.Cu", "x", (111.0, 187.5), (29.0, 56.0), 1.0),
    ("SW_B B.Cu, bank strip (taps at y 53.2 ...)", "sw_b", "B.Cu", "y", (47.5, 111.5), (170.0, 205.0), None),
]
BANK_TAPS_Y = [53.2, 67.7, 82.5, 97.0, 111.5]   # patches21.py stage 13 rows y 53.2-111.5 (C21, C22, C23, C150?, C151)


def sides():
    t = PCB.read_text()
    out = {}
    for m in re.finditer(r'\(footprint "[^"]*"\s*\(layer "([FB])\.Cu"\).*?\(property "Reference" "([^"]+)"', t, re.S):
        out[m.group(2)] = m.group(1) + ".Cu"
    return out


def build(d, side):
    layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    items = []   # (net, layers, polygon, kind, ref)
    for z in d["zones"]:
        items.append((z["net"], {z["layer"]}, Polygon(z["pts"], z.get("holes") or []).buffer(0), "pour", ""))
    for t in d["tracks"]:
        items.append((t["net"], {t["layer"]}, LineString([t["a"], t["b"]]).buffer(t["w"] / 2), "track", ""))
    for v in d["vias"]:
        items.append((v["net"], set(layers), Point(v["at"]).buffer(v["d"] / 2), "via", ""))
    for p in d["pads"]:
        lay = set(layers) if p["tht"] else {side.get(p["ref"], "F.Cu")}
        items.append((p["net"], lay, Polygon(p["pts"]).buffer(0), "pad", p["ref"]))
    return items


def outline(d):
    pts = []
    segs = [((e[0], e[1]), (e[2], e[3])) for e in d["edges"]]
    # the L-shaped outline: chain the segments
    cur = segs.pop(0)
    pts = [cur[0], cur[1]]
    while segs:
        for i, (a, b) in enumerate(segs):
            if abs(a[0] - pts[-1][0]) < 1e-6 and abs(a[1] - pts[-1][1]) < 1e-6:
                pts.append(b); segs.pop(i); break
            if abs(b[0] - pts[-1][0]) < 1e-6 and abs(b[1] - pts[-1][1]) < 1e-6:
                pts.append(a); segs.pop(i); break
        else:
            break
    return Polygon(pts).buffer(-EDGE)


def main():
    d = json.loads(DUMP.read_text())
    side = sides()
    items = build(d, side)
    board = outline(d)
    unknown = sorted({n for n, *_ in items if n and R.domain(n) == "NONE"})
    res = {"dump": str(DUMP), "need_28A_mm": round(ipc_width(28.0), 2), "unknown_domain_nets": unknown, "runs": []}
    cache = {}
    for name, net, layer, flow, (c0, c1), (w0, w1), frac in RUNS:
        key = (net, layer)
        if key not in cache:
            cu = unary_union([g for n, L, g, k, r in items if n == net and layer in L])
            hard, soft, tags = [], [], []
            for n, L, g, k, r in items:
                if n == net:
                    continue
                barrier = R.barrier(net, n)
                if layer in L:
                    c = R.clearance(net, n)
                    (soft if k == "pour" else hard).append(g.buffer(c - 1e-3))
                    tags.append((g.buffer(c - 1e-3), k, n, r))
                if barrier and layer not in L:
                    hard.append(g.buffer(R.BARRIER - 1e-3))
                    tags.append((g.buffer(R.BARRIER - 1e-3), k + "(barrier)", n, r))
            hard_u = unary_union(hard)
            soft_u = unary_union(soft)
            free_hard = board.difference(hard_u).union(cu)
            free_all = board.difference(hard_u).difference(soft_u).union(cu)
            cache[key] = (cu, free_hard, free_all, tags)
        cu, free_hard, free_all, tags = cache[key]
        cuts = []
        c = c0
        while c <= c1 + 1e-9:
            line = LineString([(c, w0), (c, w1)]) if flow == "x" else LineString([(w0, c), (w1, c)])
            if frac is None:
                k = sum(1 for ty in BANK_TAPS_Y if ty > c)
                f = k / 5.0
            else:
                f = frac
            need = ipc_width(28.0 * f)
            w = line.intersection(cu).length
            wh = line.intersection(free_hard).length
            wa = line.intersection(free_all).length
            row = {"at": round(c, 2), "I_frac": f, "need_mm": round(need, 2), "width_mm": round(w, 2),
                   "avail_hard_mm": round(wh, 2), "avail_all_mm": round(wa, 2),
                   "dT_28A_K": round(ipc_dt(28.0 * f, w), 1) if w > 0 and f > 0 else None}
            if wh < need:
                row["blockers"] = sorted({f"{k}:{n}:{r}" for g, k, n, r in tags if g.intersects(line)})[:12]
            cuts.append(row)
            c += STEP
        short = [r for r in cuts if r["width_mm"] < r["need_mm"]]
        res["runs"].append({"run": name, "net": net, "layer": layer, "flow": flow, "range": [c0, c1], "window": [w0, w1],
                            "min_width_mm": min(r["width_mm"] for r in cuts),
                            "min_avail_hard_mm": min(r["avail_hard_mm"] for r in cuts),
                            "min_avail_all_mm": min(r["avail_all_mm"] for r in cuts),
                            "short_cuts": len(short), "short_span": [short[0]["at"], short[-1]["at"]] if short else None,
                            "cuts": cuts})
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/sw_widths.json").write_text(json.dumps(res, indent=1) + "\n")
    print("need at 28 A:", res["need_28A_mm"], "mm; unknown-domain nets:", unknown[:10])
    for r in res["runs"]:
        print(f"\n== {r['run']}: min width {r['min_width_mm']}  min avail hard {r['min_avail_hard_mm']}  all {r['min_avail_all_mm']}  short cuts {r['short_cuts']} {r['short_span']}")
        for c in r["cuts"]:
            if c["width_mm"] < c["need_mm"]:
                print(f"   {c['at']:7.2f} need {c['need_mm']:5.2f} w {c['width_mm']:6.2f} hard {c['avail_hard_mm']:6.2f} all {c['avail_all_mm']:6.2f} dT {c['dT_28A_K']}  {c.get('blockers', '')}")


if __name__ == "__main__":
    main()
