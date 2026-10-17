#!/usr/bin/env python3
"""Footprint fit of a larger turn-on gate resistor (R10/R12/R18/R20) on the board of record's copper.

Reads (read-only) native-21/layout/pads.json and copper.json (the committed board export / copper of the PS
checkout) and the board's clearance function native-21/layout/rules21.py. For each gate resistor and package
(1206 = control, 2010, 2512; KiCad Resistor_SMD R_xxxx pads, pads along the existing axis), places the footprint at
the existing centre and at small offsets, and reports the worst clearance margin of its two pads against every
other-net F.Cu pad, F.Cu track and via (margin = distance - rules21.clearance(net_a, net_b)).
'_reroute_own_tracks' = the same check without the F.Cu tracks of the resistor's own two nets (gate / out), i.e.
those tracks re-routed locally around the larger pads. Courtyards / silkscreen are not checked (no courtyard data in the export); KiCad DRC remains the authority.

python3 -I fit_rg.py  -> ../results/fit_rg.json
"""
import importlib.util
import itertools
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
LAY = PS / "native-21/layout"
import re

# clearance function rebuilt from the committed rules file (section.kicad_dru), in its precedence order:
# SELV/PE vs HOT 8.0 (rules 4/5), tank node vs HOT 5.0 (rule 2), different HOT potential groups 3.2 (rule 1),
# otherwise the 0.2 mm floor. (native-21/layout/rules21.py does the same but exits on an unclassified net today.)
_DRU = (PS / "native-21/section.kicad_dru").read_text()


def _rule(name):
    m = re.search(r'\(rule "%s"\s*\(condition "(.*?)"\)' % re.escape(name), _DRU, re.S)
    return m.group(1)


_c1 = _rule("HOT functional between potential groups")
HOT = set(re.findall(r"A\.NetName == '([^']+)'", _c1.split("&&")[0]))
GROUPS = [set(re.findall(r"A\.NetName == '([^']+)'", g)) for g in
          re.findall(r"\(\((A\.NetName == '[^']+'(?: \|\| A\.NetName == '[^']+')*)\)", _c1)]
GROUP = {n: i for i, g in enumerate(GROUPS) for n in g}
TANK = set(re.findall(r"A\.NetName == '([^']+)'", _rule("HOT functional: tank node").split("&&")[0]))
SELVPE = set(re.findall(r"A\.NetName == '([^']+)'", _rule("SELV to HOT: reinforced, D5 provisional").split("&&")[0])) | \
    set(re.findall(r"A\.NetName == '([^']+)'", _rule("PE to HOT: D5 provisional floor").split("&&")[0]))


class R:
    @staticmethod
    def clearance(a, b):
        if (a in SELVPE and b in HOT) or (b in SELVPE and a in HOT):
            return 8.0
        if (a in TANK and b in HOT) or (b in TANK and a in HOT):
            return 5.0
        if a in HOT and b in HOT and GROUP.get(a, -1) != GROUP.get(b, -2):
            return 3.2
        return 0.2


# KiCad 9 Resistor_SMD footprints (pad centre offset along the axis, pad size along x (axis), across)
PKG = {"1206": (1.4625, 1.125, 1.75), "2010": (2.3125, 1.225, 2.65), "2512": (2.9625, 1.225, 3.35)}
GATE_R = ("R10", "R12", "R18", "R20")


def rect_pt(r, x, y):
    dx = max(r[0] - x, 0, x - r[2])
    dy = max(r[1] - y, 0, y - r[3])
    return math.hypot(dx, dy)


def seg_pt(ax, ay, bx, by, x, y):
    vx, vy = bx - ax, by - ay
    L = vx * vx + vy * vy
    t = 0 if L == 0 else max(0, min(1, ((x - ax) * vx + (y - ay) * vy) / L))
    return math.hypot(ax + t * vx - x, ay + t * vy - y)


def rect_seg(r, a, b):
    # 0 if the segment crosses the rectangle (sampled), else min of the endpoint / corner distances
    for k in range(41):
        t = k / 40
        x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return 0.0
    d = min(rect_pt(r, *a), rect_pt(r, *b))
    for cx, cy in ((r[0], r[1]), (r[0], r[3]), (r[2], r[1]), (r[2], r[3])):
        d = min(d, seg_pt(a[0], a[1], b[0], b[1], cx, cy))
    return d


def rect_rect(a, b):
    dx = max(a[0] - b[2], 0, b[0] - a[2])
    dy = max(a[1] - b[3], 0, b[1] - a[3])
    return math.hypot(dx, dy)


def main():
    pads = json.loads((LAY / "pads.json").read_text())
    cu = json.loads((LAY / "copper.json").read_text())
    pc = {f"{p['ref']}.{p['pad']}": (p["x"], p["y"]) for p in pads}
    segs = []
    for t in cu["tracks"]:
        if t["layer"] != "F.Cu":
            continue
        pts = [pc[p] if isinstance(p, str) else tuple(p) for p in t["points"]]
        for a, b in zip(pts, pts[1:]):
            segs.append((t["net"], a, b, t["width"]))
    vias = [(v["net"], tuple(v["at"]), v["size"]) for v in cu["vias"]]
    out = {}
    for ref in GATE_R:
        own = [p for p in pads if p["ref"] == ref]
        cx = sum(p["x"] for p in own) / 2
        cy = sum(p["y"] for p in own) / 2
        vertical = abs(own[0]["x"] - own[1]["x"]) < 1e-6
        res = {}
        own_nets = {p["net"] for p in own}
        for (pkg, (off, ax_len, across)), reroute in itertools.product(PKG.items(), (False, True)):
            tag = pkg + ("_reroute_own_tracks" if reroute else "")
            best = None
            for dx, dy in itertools.product([0.0, -0.5, 0.5, -1.0, 1.0], [0.0, -0.5, 0.5, -1.0, 1.0, -1.5, 1.5]):
                worst = (math.inf, None)
                for p in own:
                    sgn = 1 if (p["y"] - cy if vertical else p["x"] - cx) > 0 else -1
                    if vertical:
                        px, py = cx + dx, cy + dy + sgn * off
                        r = (px - across / 2, py - ax_len / 2, px + across / 2, py + ax_len / 2)
                    else:
                        px, py = cx + dx + sgn * off, cy + dy
                        r = (px - ax_len / 2, py - across / 2, px + ax_len / 2, py + across / 2)
                    net = p["net"]
                    for q in pads:
                        if q["ref"] == ref or q["net"] == net:
                            continue
                        m = rect_rect(r, q["box"]) - R.clearance(net, q["net"])
                        if m < worst[0]:
                            worst = (m, f"pad {q['ref']}.{q['pad']} {q['net']}")
                    for (n, a, b, w) in segs:
                        if n == net or (reroute and n in own_nets):
                            continue
                        m = rect_seg(r, a, b) - w / 2 - R.clearance(net, n)
                        if m < worst[0]:
                            worst = (m, f"track {n} {a}->{b} w{w}")
                    for (n, at, size) in vias:
                        if n == net:
                            continue
                        m = rect_pt(r, *at) - size / 2 - R.clearance(net, n)
                        if m < worst[0]:
                            worst = (m, f"via {n} {at}")
                cand = {"dx": dx, "dy": dy, "worst_margin_mm": round(worst[0], 3), "binding": worst[1]}
                if dx == dy == 0:
                    res[f"{tag}_in_place"] = cand
                if worst[0] >= 0 and (best is None or abs(dx) + abs(dy) < abs(best["dx"]) + abs(best["dy"])):
                    best = cand
            res[f"{tag}_nearest_fit"] = best
        out[ref] = {"centre": [cx, cy], "vertical": vertical, "nets": [p["net"] for p in own], **res}
    (Path(__file__).resolve().parent.parent / "results" / "fit_rg.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
