#!/usr/bin/env python3
"""Power board (native-21, s53) area census: courtyards, blocks, barrier moat, free area.

Standard library only. Read-only: parses the s53 board of record and its copper dump.

    python3 power_board_area.py [--run DIR] [--out ../results/power_area.json] [--pitch 0.25]

Inputs (default --run = worktrees/runs-native21/s53/c53int, outside git):
  section.kicad_pcb   the s53 board of record (SHA-256 82af7bd9..., checked below)
  copper-dump.json    the same build's copper (pads, tracks, vias, filled zones)
and the unit's own net -> domain map (zapote/power-stage-120v/native-21/layout/domains.py,
which reads audit.rs SELV_NETS).

Method:
- Courtyard per footprint = the F.CrtYd/B.CrtYd primitives (fp_rect, fp_poly, fp_line chains as a
  convex hull, fp_circle), transformed by the footprint pose. Footprints with no courtyard fall back
  to their pad bounding box (flagged).
- Areas: per-footprint polygon area (sum, overlaps double-count) and raster union at --pitch over the
  board (plan view, either side; and per side).
- Block = functional group from the atopile SourceInstance name (rules in BLOCK_RULES, cited in
  POWER-BOARD.md).
- Barrier moat: copper on any layer is split into HOT side (HOT, MAINS, SW_A, SW_B) and LOW side
  (SELV, PE). Exact Euclidean distance transforms (Felzenszwalb) give each board cell its distance to
  each side. Moat = board cells with no copper where d_hot < 8.0 and d_low < 8.0 mm, i.e. the strip
  no copper of either side may enter. Checked against the gate: min HOT-LOW copper distance on the
  raster must come out ~8.0 mm (D5 audit 8.047 mm).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]                      # worktrees/ps-integrate
UNIT = WT / "zapote/power-stage-120v"
DEFAULT_RUN = WT.parent / "runs-native21/s53/c53int"
S53_SHA = "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"
BARRIER_MM = 8.0

# ---- block rules: (block, predicate on (ref, source_instance)) -- first match wins ----
MAINS = {"j_mains", "f1", "rv1", "cx1", "cx2", "l1", "cy1", "cy2", "rb1a", "rb1b", "j_pe"}
BLOWER_AC = {"f_blw", "r_blw", "j_blw_ac"}
RECT_BUS = {"br1", "c_bus1", "c_bus2", "tvs_bus", "tvs_bus_b", "r_bus1", "r_bus2"}
TANK = {"c_res1", "c_res2", "c_res3", "c_res4", "c_res5", "j_coil", "j_coil_return", "t_ct",
        "r_crb1", "r_crb2", "r_crb3", "r_crb4"}
BRIDGE_EXTRA = {"c_hf_a1", "c_hf_a2", "c_hf_b1", "c_hf_b2", "r_shunt"}
CONNECTORS = {"j_selv", "j_tco"}
BLOCK_RULES = [
    ("mech_test", lambda r, s: s.startswith("board-only:")),
    ("mains_emi_fuse_mov", lambda r, s: s in MAINS),
    ("blower_ac_tap", lambda r, s: s in BLOWER_AC),
    ("rectifier_bus", lambda r, s: s in RECT_BUS),
    ("bridge_fets_gate_drive", lambda r, s: s.startswith(("leg_a.", "leg_b.")) or s in BRIDGE_EXTRA),
    ("tank_bank_studs_ct", lambda r, s: s in TANK),
    ("ps2_isolated_bias", lambda r, s: s == "ps_gate" or s.startswith(("bias_ls.", "bias_ha.", "bias_hb.", "monitor_ls."))),
    ("connectors_selv_tco", lambda r, s: s in CONNECTORS),
    ("sensing_protection_isolators", lambda r, s: True),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- s-expression helpers ----------------
def split_footprints(text: str):
    starts = [m.start() for m in re.finditer(r"\n\t\(footprint ", text)]
    out = []
    for s in starts:
        depth, i = 0, s + 1
        while True:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[s + 1:i + 1])
                    break
            elif c == '"':
                i = text.index('"', i + 1)
                while text[i - 1] == "\\":
                    i = text.index('"', i + 1)
            i += 1
    return out


def blocks_of(fp: str, head: str):
    """Yield top-level-in-footprint s-expr blocks that start with '(head'."""
    for m in re.finditer(r"\n\t\t\(" + head + r"\b", fp):
        s = m.start() + 1
        depth, i = 0, s
        while True:
            c = fp[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield fp[s:i + 1]
                    break
            elif c == '"':
                i = fp.index('"', i + 1)
            i += 1


NUM = r"(-?[\d.]+)"


def xform(pt, at):
    x, y = pt
    ax, ay, rot = at
    a = math.radians(rot)
    # KiCad: rotation is CCW in degrees with y down -> x' = x cos + y sin, y' = -x sin + y cos
    return (ax + x * math.cos(a) + y * math.sin(a), ay - x * math.sin(a) + y * math.cos(a))


def convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def parse_fp(fp: str):
    lib = fp.split('"')[1]
    ref = re.search(r'\(property "Reference" "([^"]*)"', fp).group(1)
    si = re.search(r'\(property "SourceInstance" "([^"]*)"', fp)
    si = si.group(1) if si else ""
    val = re.search(r'\(property "Value" "([^"]*)"', fp)
    side = re.search(r'\n\t\t\(layer "([FB])\.Cu"\)', fp).group(1)
    m = re.search(r"\n\t\t\(at " + NUM + " " + NUM + r"(?: " + NUM + r")?\)", fp)
    at = (float(m.group(1)), float(m.group(2)), float(m.group(3) or 0))
    attr = re.search(r"\n\t\t\(attr ([^)]*)\)", fp)
    polys, line_pts, cy_layers = [], {}, set()
    for kind in ("fp_rect", "fp_poly", "fp_line", "fp_circle"):
        for b in blocks_of(fp, kind):
            lm = re.search(r'\(layer "([FB]\.CrtYd)"\)', b)
            if not lm:
                continue
            ly = lm.group(1)
            cy_layers.add(ly)
            if kind == "fp_rect":
                s = re.search(r"\(start " + NUM + " " + NUM + r"\)", b)
                e = re.search(r"\(end " + NUM + " " + NUM + r"\)", b)
                x0, y0, x1, y1 = map(float, (s.group(1), s.group(2), e.group(1), e.group(2)))
                polys.append((ly, [xform(p, at) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]))
            elif kind == "fp_poly":
                pts = [(float(a), float(c)) for a, c in re.findall(r"\(xy " + NUM + " " + NUM + r"\)", b)]
                polys.append((ly, [xform(p, at) for p in pts]))
            elif kind == "fp_line":
                s = re.search(r"\(start " + NUM + " " + NUM + r"\)", b)
                e = re.search(r"\(end " + NUM + " " + NUM + r"\)", b)
                line_pts.setdefault(ly, []).extend([(float(s.group(1)), float(s.group(2))),
                                                    (float(e.group(1)), float(e.group(2)))])
            else:
                c = re.search(r"\(center " + NUM + " " + NUM + r"\)", b)
                e = re.search(r"\(end " + NUM + " " + NUM + r"\)", b)
                cx, cyy, ex, ey = map(float, (c.group(1), c.group(2), e.group(1), e.group(2)))
                r = math.hypot(ex - cx, ey - cyy)
                pts = [(cx + r * math.cos(t * math.pi / 16), cyy + r * math.sin(t * math.pi / 16)) for t in range(32)]
                polys.append((ly, [xform(p, at) for p in pts]))
    for ly, pts in line_pts.items():
        # courtyard drawn as segments: hull of the endpoints (exact for convex outlines)
        polys.append((ly, [xform(p, at) for p in convex_hull(pts)]))
    fallback = False
    if not polys:
        # pad bounding boxes as the footprint area
        xs, ys = [], []
        for b in blocks_of(fp, "pad"):
            pm = re.search(r"\(at " + NUM + " " + NUM, b)
            sm = re.search(r"\(size " + NUM + " " + NUM + r"\)", b)
            if pm and sm:
                px, py, sx, sy = map(float, (pm.group(1), pm.group(2), sm.group(1), sm.group(2)))
                xs += [px - sx / 2, px + sx / 2]
                ys += [py - sy / 2, py + sy / 2]
        if xs:
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            polys.append((f"{side}.CrtYd", [xform(p, at) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]))
            fallback = True
    return {"ref": ref, "lib": lib, "source": si, "value": val.group(1) if val else "", "side": side,
            "at": at, "attr": attr.group(1) if attr else "", "polys": polys, "fallback_pad_bbox": fallback}


def block_of(ref, si):
    for name, pred in BLOCK_RULES:
        if pred(ref, si):
            return name
    return "unassigned"


# ---------------- raster ----------------
class Grid:
    def __init__(self, w, h, pitch):
        self.p = pitch
        self.nx = int(round(w / pitch))
        self.ny = int(round(h / pitch))

    def new(self, v=0):
        return bytearray([v]) * (self.nx * self.ny)

    def fill_polys(self, buf, rings, val=1):
        """Even-odd scanline fill of a set of rings (outer + holes) at cell centres."""
        p, nx, ny = self.p, self.nx, self.ny
        rows = {}
        for ring in rings:
            n = len(ring)
            for i in range(n):
                x1, y1 = ring[i]
                x2, y2 = ring[(i + 1) % n]
                if y1 == y2:
                    continue
                if y1 > y2:
                    x1, y1, x2, y2 = x2, y2, x1, y1
                j0 = max(0, int(math.ceil(y1 / p - 0.5)))
                j1 = min(ny - 1, int(math.ceil(y2 / p - 0.5)) - 1)
                for j in range(j0, j1 + 1):
                    yc = (j + 0.5) * p
                    rows.setdefault(j, []).append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        for j, xs in rows.items():
            xs.sort()
            base = j * nx
            for k in range(0, len(xs) - 1, 2):
                i0 = max(0, int(math.ceil(xs[k] / p - 0.5)))
                i1 = min(nx - 1, int(math.ceil(xs[k + 1] / p - 0.5)) - 1)
                if i1 >= i0:
                    if isinstance(buf, list):
                        buf[base + i0: base + i1 + 1] = [val] * (i1 - i0 + 1)
                    else:
                        buf[base + i0: base + i1 + 1] = bytes([val]) * (i1 - i0 + 1)

    def fill_capsule(self, buf, a, b, r, val=1):
        p, nx, ny = self.p, self.nx, self.ny
        (ax, ay), (bx, by) = a, b
        i0 = max(0, int((min(ax, bx) - r) / p)); i1 = min(nx - 1, int((max(ax, bx) + r) / p) + 1)
        j0 = max(0, int((min(ay, by) - r) / p)); j1 = min(ny - 1, int((max(ay, by) + r) / p) + 1)
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        r2 = r * r
        for j in range(j0, j1 + 1):
            yc = (j + 0.5) * p
            base = j * nx
            for i in range(i0, i1 + 1):
                xc = (i + 0.5) * p
                if L2 > 0:
                    t = max(0.0, min(1.0, ((xc - ax) * dx + (yc - ay) * dy) / L2))
                else:
                    t = 0.0
                ex, ey = ax + t * dx - xc, ay + t * dy - yc
                if ex * ex + ey * ey <= r2:
                    buf[base + i] = val


INF = 1e20


def edt_1d(f, n):
    """Felzenszwalb squared EDT of a 1-D sampled function f (length n)."""
    d = [0.0] * n
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    v[0] = 0
    z[0], z[1] = -INF, INF
    for q in range(1, n):
        fq = f[q]
        if fq >= INF:
            continue
        while True:
            vk = v[k]
            if f[vk] >= INF:
                # first finite sample: restart the envelope
                v[k] = q
                z[k], z[k + 1] = -INF, INF
                break
            s = ((fq + q * q) - (f[vk] + vk * vk)) / (2 * q - 2 * vk)
            if s <= z[k]:
                if k == 0:
                    v[0] = q
                    z[0], z[1] = -INF, INF
                    break
                k -= 1
                continue
            k += 1
            v[k] = q
            z[k], z[k + 1] = s, INF
            break
    if f[v[0]] >= INF:
        return [INF] * n
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        dq = q - v[k]
        d[q] = dq * dq + f[v[k]]
    return d


def edt(mask, nx, ny):
    """Squared distance (in cells^2) from every cell to the nearest set cell of mask."""
    g = [0.0] * (nx * ny)
    for j in range(ny):
        row = [0.0 if mask[j * nx + i] else INF for i in range(nx)]
        g[j * nx:(j + 1) * nx] = edt_1d(row, nx)
    out = [0.0] * (nx * ny)
    for i in range(nx):
        col = g[i::nx]
        out[i::nx] = edt_1d(col, ny)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--out", type=Path, default=HERE.parent / "results/power_area.json")
    ap.add_argument("--pitch", type=float, default=0.25)
    a = ap.parse_args()

    pcb = a.run / "section.kicad_pcb"
    sha = sha256(pcb)
    if sha != S53_SHA:
        sys.exit(f"board SHA {sha} is not the s53 board of record {S53_SHA}")
    text = pcb.read_text()

    # board outline: Edge.Cuts gr_lines -> polygon
    segs = []
    for m in re.finditer(r"\n\t\(gr_line\s+\(start " + NUM + " " + NUM + r"\)\s+\(end " + NUM + " " + NUM + r"\)", text):
        tail = text[m.end():m.end() + 200]
        if '(layer "Edge.Cuts")' in tail.split("(uuid")[0]:
            segs.append(tuple(map(float, m.groups())))
    pts = [(segs[0][0], segs[0][1]), (segs[0][2], segs[0][3])]
    rest = segs[1:]
    while rest:
        for k, s in enumerate(rest):
            if abs(s[0] - pts[-1][0]) < 1e-6 and abs(s[1] - pts[-1][1]) < 1e-6:
                pts.append((s[2], s[3])); rest.pop(k); break
            if abs(s[2] - pts[-1][0]) < 1e-6 and abs(s[3] - pts[-1][1]) < 1e-6:
                pts.append((s[0], s[1])); rest.pop(k); break
        else:
            sys.exit("outline does not close")
    outline = pts[:-1]
    board_area = poly_area(outline)
    W = max(p[0] for p in outline); H = max(p[1] for p in outline)

    g = Grid(W, H, a.pitch)
    cell = a.pitch ** 2
    board = g.new()
    g.fill_polys(board, [outline])
    board_cells = sum(board)

    fps = [parse_fp(f) for f in split_footprints(text)]
    union_any, union_side = g.new(), {"F": g.new(), "B": g.new()}
    blocks = {}
    parts = []
    for f in fps:
        blk = block_of(f["ref"], f["source"])
        f["block"] = blk
        # per footprint: own raster (union of its own courtyard polygons, both sides)
        own = {}
        area_poly = 0.0
        for ly, poly in f["polys"]:
            area_poly += poly_area(poly)
        xs = [p[0] for _, poly in f["polys"] for p in poly]
        ys = [p[1] for _, poly in f["polys"] for p in poly]
        parts.append({"ref": f["ref"], "source": f["source"], "block": blk, "lib": f["lib"].split(":")[-1],
                      "value": f["value"], "side": f["side"], "x": f["at"][0], "y": f["at"][1],
                      "courtyard_mm2": round(area_poly, 2),
                      "bbox": [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)] if xs else None,
                      "fallback_pad_bbox": f["fallback_pad_bbox"]})
        b = blocks.setdefault(blk, {"parts": 0, "courtyard_sum_mm2": 0.0, "refs": [], "_mask": g.new()})
        b["parts"] += 1
        b["courtyard_sum_mm2"] += area_poly
        b["refs"].append(f["ref"])
        for ly, poly in f["polys"]:
            g.fill_polys(union_any, [poly])
            g.fill_polys(union_side[ly[0]], [poly])
            g.fill_polys(b["_mask"], [poly])

    def count(buf, within=None):
        if within is None:
            return sum(buf)
        return sum(1 for i, v in enumerate(buf) if v and within[i])

    union_mm2 = count(union_any, board) * cell
    res_blocks = {}
    for name, b in sorted(blocks.items()):
        m = b.pop("_mask")
        res_blocks[name] = {"parts": b["parts"], "courtyard_sum_mm2": round(b["courtyard_sum_mm2"], 1),
                            "courtyard_union_mm2": round(count(m, board) * cell, 1),
                            "refs": sorted(b["refs"], key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))}

    # ---------------- copper domains and the barrier moat ----------------
    sys.path.insert(0, str(UNIT / "native-21/layout"))
    import domains  # noqa: E402  (reads audit.rs; read-only)
    dump = json.loads((a.run / "copper-dump.json").read_text())
    hot, low, anycu = g.new(), g.new(), g.new()

    def side_of(net):
        if not net:
            return None
        d = domains.domain(net)
        return "low" if d in ("SELV", "PE") else "hot"

    dom_count = {}
    for z in dump["zones"]:
        s = side_of(z["net"])
        rings = [z["pts"]] + list(z.get("holes") or [])
        for buf in ([hot, anycu] if s == "hot" else [low, anycu] if s == "low" else []):
            g.fill_polys(buf, rings)
    for t in dump["tracks"]:
        s = side_of(t["net"])
        for buf in ([hot, anycu] if s == "hot" else [low, anycu] if s == "low" else []):
            g.fill_capsule(buf, t["a"], t["b"], t["w"] / 2)
    for v in dump["vias"]:
        s = side_of(v["net"])
        for buf in ([hot, anycu] if s == "hot" else [low, anycu] if s == "low" else []):
            g.fill_capsule(buf, v["at"], v["at"], v["d"] / 2)
    for p in dump["pads"]:
        if not p["layers"] or not p["pts"]:
            continue
        s = side_of(p["net"])
        dom_count[s] = dom_count.get(s, 0) + 1
        for buf in ([hot, anycu] if s == "hot" else [low, anycu] if s == "low" else []):
            g.fill_polys(buf, [p["pts"]])

    nx, ny = g.nx, g.ny
    d_hot = edt(hot, nx, ny)
    d_low = edt(low, nx, ny)
    lim2 = (BARRIER_MM / a.pitch) ** 2
    moat = g.new()
    min_hl = INF
    for i in range(nx * ny):
        if low[i]:
            if d_hot[i] < min_hl:
                min_hl = d_hot[i]
        if board[i] and not anycu[i] and d_hot[i] < lim2 and d_low[i] < lim2:
            moat[i] = 1
    moat_mm2 = sum(moat) * cell
    # moat cells also covered by part courtyards (parts straddling the barrier: isolators, drivers, T1...)
    moat_under_parts = sum(1 for i in range(nx * ny) if moat[i] and union_any[i]) * cell
    # area of each side's domain region: cells nearer to hot copper than to low copper (on board)
    hot_region = sum(1 for i in range(nx * ny) if board[i] and d_hot[i] < d_low[i]) * cell
    low_region = board_cells * cell - hot_region
    low_cu = sum(low[i] for i in range(nx * ny) if board[i]) * cell

    # free area: board cells with no courtyard, and with neither courtyard nor copper
    free_no_cy = sum(1 for i in range(nx * ny) if board[i] and not union_any[i]) * cell
    free_no_cy_no_cu = sum(1 for i in range(nx * ny) if board[i] and not union_any[i] and not anycu[i]) * cell

    # mounting holes: radius to the nearest net-bearing copper (any layer) around each hole centre
    holes = []
    d_any = edt(anycu, nx, ny)
    for f in fps:
        if f["ref"].startswith("H") and f["source"].startswith("board-only:"):
            i, j = int(f["at"][0] / a.pitch), int(f["at"][1] / a.pitch)
            holes.append({"ref": f["ref"], "x": f["at"][0], "y": f["at"][1],
                          "copper_free_radius_mm": round(math.sqrt(d_any[j * nx + i]) * a.pitch, 2)})

    # 5 mm tile map of what each tile mostly is: C courtyard, ~ barrier moat (copper-free), = copper
    # only (no courtyard: planes, lanes, pours), . empty (no courtyard, no copper, not moat)
    tmap = []
    T = int(round(5.0 / a.pitch))
    for tj in range(ny // T):
        line = ""
        for ti in range(nx // T):
            c = {"C": 0, "~": 0, "=": 0, ".": 0}
            nb = 0
            for j in range(tj * T, tj * T + T):
                for i in range(ti * T, ti * T + T):
                    k = j * nx + i
                    if not board[k]:
                        continue
                    nb += 1
                    c["C" if union_any[k] else "~" if moat[k] else "=" if anycu[k] else "."] += 1
            line += " " if nb == 0 else max(c.items(), key=lambda kv: kv[1])[0]
        tmap.append(line)
    print("\n".join(f"y{j*5:4d} {r}" for j, r in enumerate(tmap)))

    # territories: every board cell goes to the moat (if it is moat) or else to the nearest footprint
    # courtyard (mech_test parts excluded as seeds) (8-connected multi-source BFS, so "nearest" is chessboard-metric). A block's territory is
    # its parts plus the copper and empty board around them that nothing else is closer to.
    from collections import deque
    nfp = len(fps)
    lab = [-1] * (nx * ny)
    for k, f in enumerate(fps):
        if f["block"] == "mech_test":
            continue  # holes, fiducials, test pads do not claim territory; their area folds into neighbours
        for ly, poly in f["polys"]:
            g.fill_polys(lab, [poly], k)
    q = deque()
    for i in range(nx * ny):
        if not board[i]:
            lab[i] = -2
        elif moat[i]:
            lab[i] = nfp
        if lab[i] >= 0 and lab[i] != nfp:
            q.append(i)
    while q:
        i = q.popleft()
        x, y = i % nx, i // nx
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < nx and 0 <= yy < ny:
                j = yy * nx + xx
                if lab[j] == -1:
                    lab[j] = lab[i]
                    q.append(j)
    terr = [[0, 0, 0] for _ in range(nfp + 1)]  # cells, empty cells, copper-only cells
    for i in range(nx * ny):
        L = lab[i]
        if L < 0:
            continue
        t = terr[L]
        t[0] += 1
        if not union_any[i] and not moat[i]:
            if anycu[i]:
                t[2] += 1
            else:
                t[1] += 1
    for k, f in enumerate(fps):
        parts[k]["territory_mm2"] = round(terr[k][0] * cell, 1)
        parts[k]["territory_empty_mm2"] = round(terr[k][1] * cell, 1)
        parts[k]["territory_copper_only_mm2"] = round(terr[k][2] * cell, 1)
    for name, b in res_blocks.items():
        ps_ = [p for p in parts if p["block"] == name]
        b["territory_mm2"] = round(sum(p["territory_mm2"] for p in ps_), 1)
        b["territory_empty_mm2"] = round(sum(p["territory_empty_mm2"] for p in ps_), 1)
        b["territory_copper_only_mm2"] = round(sum(p["territory_copper_only_mm2"] for p in ps_), 1)
        b["courtyard_share_of_territory_pct"] = round(100 * b["courtyard_union_mm2"] / b["territory_mm2"], 1) if b["territory_mm2"] else None
    moat_territory = round(terr[nfp][0] * cell, 1)

    # block bounding regions (union of the block's courtyard bboxes)
    for name, b in res_blocks.items():
        bb = [p["bbox"] for p in parts if p["block"] == name and p["bbox"]]
        b["extent_bbox"] = [min(x[0] for x in bb), min(x[1] for x in bb), max(x[2] for x in bb), max(x[3] for x in bb)]

    out = {
        "board_sha256": sha,
        "source": str(pcb),
        "copper_dump": str(a.run / "copper-dump.json"),
        "pitch_mm": a.pitch,
        "outline_pts": outline,
        "board_area_mm2": round(board_area, 1),
        "board_area_raster_mm2": round(board_cells * cell, 1),
        "bbox_mm": [W, H],
        "footprints": len(fps),
        "footprints_with_pad_bbox_fallback": [p["ref"] for p in parts if p["fallback_pad_bbox"]],
        "courtyard_sum_mm2": round(sum(p["courtyard_mm2"] for p in parts), 1),
        "courtyard_union_mm2": round(union_mm2, 1),
        "courtyard_union_F_mm2": round(count(union_side["F"], board) * cell, 1),
        "courtyard_union_B_mm2": round(count(union_side["B"], board) * cell, 1),
        "utilisation_union_pct": round(100 * union_mm2 / board_area, 1),
        "free_no_courtyard_mm2": round(free_no_cy, 1),
        "free_no_courtyard_no_copper_mm2": round(free_no_cy_no_cu, 1),
        "copper_only_no_courtyard_mm2": round(free_no_cy - free_no_cy_no_cu, 1),
        "empty_not_moat_mm2": round(free_no_cy_no_cu - (moat_mm2 - moat_under_parts), 1),
        "moat_territory_mm2": moat_territory,
        "barrier": {
            "rule_mm": BARRIER_MM,
            "min_hot_to_low_copper_raster_mm": round(math.sqrt(min_hl) * a.pitch, 2),
            "check_against": "D5 audit 8.047 mm (review-packet-s53 README gate 13); raster error ~ +-pitch",
            "moat_copper_free_mm2": round(moat_mm2, 1),
            "moat_under_courtyards_mm2": round(moat_under_parts, 1),
            "moat_pct_of_board": round(100 * moat_mm2 / board_area, 1),
            "hot_side_region_mm2": round(hot_region, 1),
            "low_side_region_mm2": round(low_region, 1),
            "low_side_copper_mm2_any_layer": round(low_cu, 1),
            "pads_by_side": {str(k): v for k, v in dom_count.items()},
        },
        "holes": holes,
        "tile_map_5mm": {"legend": "C courtyard, ~ barrier moat (no copper), = copper only, . empty", "rows_y_down": tmap},
        "blocks": res_blocks,
        "parts": parts,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("parts", "blocks", "outline_pts", "holes")}, indent=1))
    for n, b in res_blocks.items():
        print(f"{n:30s} n={b['parts']:3d} cy={b['courtyard_union_mm2']:7.1f} terr={b['territory_mm2']:7.1f} "
              f"empty={b['territory_empty_mm2']:6.1f} cu={b['territory_copper_only_mm2']:7.1f} fill={b['courtyard_share_of_territory_pct']}%")


if __name__ == "__main__":
    main()
