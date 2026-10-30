"""Gerber / Excellon re-read and the Gerber-only DFM checks (independent of pcbnew; shapely + numpy).

Reader (from RB1 gerber_read.py): what KiCad 10 writes: %FSLAX46Y46*% mm, G01 linear and G02/G03 circular
(G75 multi-quadrant; arcs come back as chords of <= 10 degrees, so draws stay straight segments; G74 raises),
C/R/O apertures and the KiCad RoundRect macro, D01/D02/D03, G36/G37 regions (one polygon per contour), X2
object attributes TO.P / TO.N and aperture function TA.AperFunction.

Checks (from RB1 dfm_checks.py sections 1 and 3), all in the Gerber frame (mm, y up), on a GerberSet:
  connectivity    copper rebuilt from geometry alone (flashes, draws, regions; unioned per layer, layers joined
                  through plated holes) and compared with an expected pad-net table: shorts, opens, missing and
                  unexpected pads.  net_ties name nets that one copper bridge joins on purpose.
  outline         board size from the Edge_Cuts draws
  drills          plated / non-plated hole sets against expected positions per diameter
  paste           one F_Paste flash per assembled SMD pad, 1:1 area, and none on bare pads
  mask            per side: unpaired openings, vias tented, min mask bridge, opening to other-net copper,
                  copper to board edge
  silk            min legend line, text height / stroke / ratio (texts from the .kicad_pcb), pad to silk
Limits default to jlc.RULES (JLC capabilities page, jlc/data/jlc-capabilities-excerpts.txt).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

_TOKEN = re.compile(r"%[^%]*%|[^*%\n]+\*")
_XY = re.compile(r"(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0?([123])$")
_ADD = re.compile(r"%ADD(\d+)([A-Za-z_][\w.]*),?([^*]*)\*%")
TOL = 1e-3


# ------------------------------------------------------------------ reader
def read_gerber(path, scale=1e-6):
    """-> {'apertures': {d: (kind, params, function)}, 'flashes': [(x, y, d, attrs)],
    'draws': [(x0, y0, x1, y1, d, attrs)], 'regions': [(pts, attrs)]}"""
    with open(path) as f:
        text = f.read()
    return parse_gerber(text, scale, str(path))


def parse_gerber(text, scale=1e-6, name="<gerber>"):
    if re.search(r"(?m)^G74\*", text):
        raise ValueError(f"{name}: single-quadrant arcs (G74) not supported")
    ap, flashes, draws, regions = {}, [], [], []
    mode = 1  # 1 linear, 2 clockwise, 3 counter-clockwise
    obj, apfn = {}, None
    d = None
    x = y = 0.0
    region, contour = False, []
    for tok in _TOKEN.findall(text):
        if tok[0] == "%":
            body = tok[1:-2] if tok.endswith("*%") else tok[1:-1]
            if body.startswith("ADD"):
                m = _ADD.match(tok)
                params = [float(v) for v in m.group(3).split("X")] if m.group(3) else []
                ap[int(m.group(1))] = (m.group(2), params, apfn)
            elif body.startswith("TA.AperFunction"):
                apfn = body.split(",", 1)[1]
            elif body.startswith("TO."):
                key_, _, val = body[3:].partition(",")
                obj[key_] = val
            elif body.startswith("TD"):
                obj, apfn = ({}, None) if body == "TD" else (obj, apfn)
            continue
        tok = tok[:-1]
        if tok == "G36":
            region, contour = True, []
            continue
        if tok == "G37":
            if len(contour) > 2:
                regions.append((contour, dict(obj)))
            region, contour = False, []
            continue
        if tok[:3] in ("G01", "G02", "G03"):
            mode = int(tok[2])
            tok = tok[3:]
            if not tok:
                continue
        if tok.startswith("D") and tok[1:].isdigit() and int(tok[1:]) >= 10:
            d = int(tok[1:])
            continue
        m = _XY.match(tok)
        if not m:
            continue
        nx = int(m.group(1)) * scale if m.group(1) is not None else x
        ny = int(m.group(2)) * scale if m.group(2) is not None else y
        op = m.group(5)
        pts = [(nx, ny)]
        if op == "1" and mode in (2, 3):  # arc about (x + I, y + J) -> chord end points
            cx_ = x + int(m.group(3) or 0) * scale
            cy_ = y + int(m.group(4) or 0) * scale
            r = math.hypot(x - cx_, y - cy_)
            a0, a1 = math.atan2(y - cy_, x - cx_), math.atan2(ny - cy_, nx - cx_)
            sweep = (a1 - a0) % (2 * math.pi) if mode == 3 else -((a0 - a1) % (2 * math.pi))
            if abs(sweep) < 1e-9:  # start == end: full circle
                sweep = 2 * math.pi if mode == 3 else -2 * math.pi
            n = max(2, math.ceil(abs(sweep) / math.radians(10)))
            pts = [
                (cx_ + r * math.cos(a0 + sweep * i / n), cy_ + r * math.sin(a0 + sweep * i / n))
                for i in range(1, n)
            ] + [(nx, ny)]
        if region:
            if op == "2":
                if len(contour) > 2:
                    regions.append((contour, dict(obj)))
                contour = [(nx, ny)]
            elif op == "1":
                contour.extend(pts)
        elif op == "1":
            px, py = x, y
            for qx, qy in pts:
                draws.append((px, py, qx, qy, d, dict(obj)))
                px, py = qx, qy
        elif op == "3":
            flashes.append((nx, ny, d, dict(obj)))
        x, y = nx, ny
    return {"apertures": ap, "flashes": flashes, "draws": draws, "regions": regions}


def read_drill(path):
    """KiCad Excellon (METRIC, decimal coordinates) -> [(x, y, diameter)]."""
    with open(path) as f:
        return parse_drill(f.read())


def parse_drill(text):
    tools, holes, cur = {}, [], None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"T(\d+)C([\d.]+)$", line)
        if m:
            tools[int(m.group(1))] = float(m.group(2))
            continue
        m = re.match(r"T(\d+)$", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"X(-?[\d.]+)Y(-?[\d.]+)$", line)
        if m and cur:
            holes.append((float(m.group(1)), float(m.group(2)), tools[cur]))
    return holes


def aperture_shape(kind, params):
    """shapely geometry of an aperture centred on the origin."""
    from shapely.geometry import Point, Polygon, box

    if kind == "C":
        return Point(0, 0).buffer(params[0] / 2, 32)
    if kind == "R":
        return box(-params[0] / 2, -params[1] / 2, params[0] / 2, params[1] / 2)
    if kind == "O":
        w, h = params[0], params[1]
        r = min(w, h) / 2
        return (
            box(-(w / 2 - r), -(h / 2 - r), w / 2 - r, h / 2 - r).buffer(r, 16)
            if w != h
            else Point(0, 0).buffer(r, 32)
        )
    if kind == "RoundRect":
        r, c = params[0], params[1:9]
        return Polygon([(c[0], c[1]), (c[2], c[3]), (c[4], c[5]), (c[6], c[7])]).buffer(r, 8)
    raise ValueError(f"aperture {kind} not supported")


def key(x, y):
    """A position key at 1 um."""
    return (round(x, 3), round(y, 3))


def gxy(org):
    """Board frame (y down, origin org = the Gerber origin in board coordinates) -> Gerber frame (y up)."""
    return lambda x, y: (org[0] + x, -(org[1] + y))


# ------------------------------------------------------------------ geometry of a set of layers
class GerberSet:
    """Parsed layers by name (e.g. 'F_Cu', 'F_Mask', 'F_Paste', 'F_Silkscreen', 'Edge_Cuts') plus drills."""

    def __init__(self, layers, pth=(), npth=()):
        self.layers = layers
        self.pth = list(pth)
        self.npth = list(npth)
        self._ap = {}

    @classmethod
    def load(cls, paths, pth=None, npth=None):
        """paths: {layer name: gerber path}; pth / npth: Excellon paths."""
        return cls(
            {n: read_gerber(p) for n, p in paths.items()},
            read_drill(pth) if pth else (),
            read_drill(npth) if npth else (),
        )

    def ap_geom(self, layer, d):
        k = (layer, d)
        if k not in self._ap:
            kind, params, _ = self.layers[layer]["apertures"][d]
            self._ap[k] = aperture_shape(kind, params)
        return self._ap[k]

    def ap_function(self, layer, d):
        return self.layers[layer]["apertures"][d][2] or ""

    def flash_geoms(self, layer):
        from shapely import affinity

        return [
            affinity.translate(self.ap_geom(layer, d), x, y)
            for x, y, d, _ in self.layers[layer]["flashes"]
        ]

    def draw_geoms(self, layer):
        import numpy as np
        import shapely

        dr = self.layers[layer]["draws"]
        if not dr:
            return []
        a = np.array([(x0, y0, x1, y1) for x0, y0, x1, y1, _, _ in dr])
        r = np.array([self.layers[layer]["apertures"][d][1][0] / 2 for *_, d, _ in dr])
        zero = (a[:, 0] == a[:, 2]) & (a[:, 1] == a[:, 3])
        a[zero, 2] += 1e-6  # degenerate strokes: keep a valid line
        lines = shapely.linestrings(a.reshape(-1, 2, 2))
        return list(shapely.buffer(lines, r, quad_segs=8))

    def region_geoms(self, layer):
        from shapely.geometry import Polygon

        return [Polygon(p).buffer(0) for p, _ in self.layers[layer]["regions"]]


# ------------------------------------------------------------------ 1 connectivity
class Copper:
    """Copper islands per layer, joined through plated holes (union-find), and the X2-named pads on them."""

    def __init__(self, gs, copper_layers=("F_Cu", "B_Cu")):
        import shapely
        from shapely.geometry import Point
        from shapely.strtree import STRtree

        self.gs = gs
        self.cu = {}
        for L in copper_layers:
            items = gs.flash_geoms(L) + gs.draw_geoms(L) + gs.region_geoms(L)
            union = shapely.union_all(items)
            parts = (
                list(union.geoms)
                if hasattr(union, "geoms")
                else ([union] if not union.is_empty else [])
            )
            self.cu[L] = {"items": items, "parts": parts, "tree": STRtree(parts)}
        self.parent = {}
        for L in self.cu:
            for i in range(len(self.cu[L]["parts"])):
                self.find((L, i))
        if gs.pth:
            holes_pt = shapely.points([(x, y) for x, y, _ in gs.pth])
            hole_part = {}
            for L in self.cu:
                hi, pi = self.cu[L]["tree"].query(holes_pt, predicate="intersects")
                for h, p in zip(hi, pi):
                    hole_part.setdefault(int(h), []).append((L, int(p)))
            for nodes in hole_part.values():
                for n in nodes[1:]:
                    self.parent[self.find(n)] = self.find(nodes[0])
        # 'U1.3' -> (layer, x, y, d): first layer that names it; pads_on: per layer (THT pads on both)
        self.pads, self.pads_on = {}, {L: {} for L in self.cu}
        for L in self.cu:
            for x, y, d, at in gs.layers[L]["flashes"]:
                if "P" in at:
                    ref, pin = at["P"].split(",")[:2]
                    self.pads_on[L][f"{ref}.{pin}"] = (L, x, y, d)
                    self.pads.setdefault(f"{ref}.{pin}", (L, x, y, d))
        self.pad_comp = {}
        for name, (L, x, y, _) in self.pads.items():
            hit = self.cu[L]["tree"].query(Point(x, y), predicate="intersects")
            self.pad_comp[name] = self.find((L, int(hit[0])))

    def find(self, a):
        parent = self.parent
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a


def connectivity(copper, expected_pad_nets, net_ties=None):
    """expected_pad_nets {ref: {pin: net or None}}; net_ties {name: [net_a, net_b]} (a bridged on purpose to b).
    -> {pass, pads_found, pads_expected, missing, unexpected, shorts, opens, copper_parts}"""
    tie = dict((net_ties or {}).values())
    exp_pad = {
        f"{r}.{p}": tie.get(n, n or f"NC:{r}.{p}")
        for r, pins in expected_pad_nets.items()
        for p, n in pins.items()
    }
    comp_nets, net_comps = defaultdict(set), defaultdict(set)
    for name, c in copper.pad_comp.items():
        comp_nets[c].add(exp_pad.get(name, f"?{name}"))
        net_comps[exp_pad.get(name, f"?{name}")].add(c)
    shorts = {str(c): sorted(n) for c, n in comp_nets.items() if len(n) > 1}
    opens = {n: len(c) for n, c in net_comps.items() if len(c) > 1}
    missing = sorted(set(exp_pad) - set(copper.pads))
    extra = sorted(set(copper.pads) - set(exp_pad))
    return {
        "pass": not (shorts or opens or missing or extra),
        "pads_found": len(copper.pads),
        "pads_expected": len(exp_pad),
        "missing": missing,
        "unexpected": extra,
        "shorts": shorts,
        "opens": opens,
        "copper_parts": {L: len(c["parts"]) for L, c in copper.cu.items()},
        "net_ties_bridged": sorted(f"{a}-{b}" for a, b in tie.items()),
    }


# ------------------------------------------------------------------ 2 outline, drills, paste
def outline(gs, layer="Edge_Cuts"):
    """-> ((width, height) mm, (x0, y0, x1, y1)) from the edge draws."""
    ex = gs.layers[layer]["draws"]
    xs = [v for x0, y0, x1, y1, *_ in ex for v in (x0, x1)]
    ys = [v for x0, y0, x1, y1, *_ in ex for v in (y0, y1)]
    b = (min(xs), min(ys), max(xs), max(ys))
    return (round(b[2] - b[0], 3), round(b[3] - b[1], 3)), b


def hole_set(holes, d, tol=TOL):
    return sorted(key(x, y) for x, y, dd in holes if abs(dd - d) < tol)


def drill_check(gs, expected_pth, expected_npth, tol=TOL):
    """expected_pth / expected_npth: {diameter: [(x, y), ...]} in the Gerber frame.  Every hole must be in
    one listed set, and every listed position drilled with that diameter."""
    out, ok = {}, True
    for kind, holes, exp in (("pth", gs.pth, expected_pth), ("npth", gs.npth, expected_npth)):
        for d, pts in exp.items():
            got, want = hole_set(holes, d, tol), sorted(key(x, y) for x, y in pts)
            out[f"{kind}_{d}"] = {"found": len(got), "expected": len(want), "match": got == want}
            ok &= got == want
        listed = sum(len(p) for p in exp.values())
        if len(holes) != listed:
            out[f"{kind}_unlisted"] = len(holes) - listed
            ok = False
    return {"pass": ok, **out}


def paste_check(
    gs, copper, assembled_refs, copper_layer="F_Cu", paste_layer="F_Paste", bare_also=()
):
    """One paste flash per assembled SMD pad (aperture function SMDPad), equal area, none on other pads.
    bare_also: extra pad names (e.g. through-hole lands) that must stay bare."""
    smd_all = {
        k: v
        for k, v in copper.pads_on[copper_layer].items()
        if "SMDPad" in gs.ap_function(copper_layer, v[3])
    }
    smd = {k: v for k, v in smd_all.items() if k.split(".")[0] in assembled_refs}
    bare = {k: v for k, v in copper.pads_on[copper_layer].items() if k in bare_also}
    bare.update({k: v for k, v in smd_all.items() if k not in smd})
    flashes = gs.layers[paste_layer]["flashes"]
    paste = {key(x, y): (x, y, d) for x, y, d, _ in flashes}
    missing = sorted(k for k, v in smd.items() if key(v[1], v[2]) not in paste)
    on_bare = sorted(k for k, v in bare.items() if key(v[1], v[2]) in paste)
    area = sorted(
        k
        for k, v in smd.items()
        if key(v[1], v[2]) in paste
        and abs(
            gs.ap_geom(paste_layer, paste[key(v[1], v[2])][2]).area
            - gs.ap_geom(copper_layer, v[3]).area
        )
        >= 1e-3
    )
    ok = len(paste) == len(flashes) == len(smd) and not (missing or on_bare or area)
    return {
        "pass": ok,
        "smd_pads_assembled": len(smd),
        "smd_pads_bare": len(smd_all) - len(smd),
        "paste_flashes": len(flashes),
        "missing": missing,
        "on_bare_pads": on_bare,
        "area_mismatch": area,
    }


# ------------------------------------------------------------------ 3 solder mask and silk
def mask_check(
    gs, copper, board_box, rules=None, sides=(("F_Cu", "F_Mask"), ("B_Cu", "B_Mask")), via_d=None
):
    """Per side: openings with no pad or NPTH under them, vias tented (no opening on a via hole of
    diameter via_d), min mask bridge between openings, opening to other-net copper, copper to edge."""
    import numpy as np
    import shapely
    from shapely.geometry import box
    from shapely.strtree import STRtree

    from .jlc import RULES as JLC

    R = dict(JLC, **(rules or {}))
    board = box(*board_box)
    vias = set(hole_set(gs.pth, via_d)) if via_d else set()
    holepos = {key(x, y) for x, y, _ in gs.npth}
    out = {}
    for L, M in sides:
        if M not in gs.layers or L not in copper.cu:
            continue
        op = gs.flash_geoms(M)
        cen = [(x, y) for x, y, *_ in gs.layers[M]["flashes"]]
        padpos = {key(v[1], v[2]): k for k, v in copper.pads_on[L].items()}
        unpaired = [c for c in cen if key(*c) not in padpos and key(*c) not in holepos]
        tented = not any(key(*c) in vias for c in cen)
        if op:
            tree = STRtree(op)
            a, b = tree.query(op, predicate="dwithin", distance=0.5)
            keep = a < b
            gaps = (
                shapely.distance(np.array(op)[a[keep]], np.array(op)[b[keep]])
                if keep.any()
                else np.array([9.9])
            )
        else:
            gaps = np.array([9.9])
        items = copper.cu[L]["items"]
        rep = shapely.point_on_surface(items)
        ii, pp = copper.cu[L]["tree"].query(rep, predicate="intersects")
        item_comp = [None] * len(items)
        for i, p in zip(ii, pp):
            item_comp[int(i)] = copper.find((L, int(p)))
        itree = STRtree(items)
        near = float("inf")
        for g, c in zip(op, cen):
            name = padpos.get(key(*c))
            if name is None:
                continue
            mine = copper.pad_comp[name]
            for j in itree.query(g, predicate="dwithin", distance=0.5):
                if item_comp[int(j)] != mine:
                    near = min(near, g.distance(items[int(j)]))
        edge = min(
            (board.exterior.distance(p) for p in copper.cu[L]["parts"]), default=float("inf")
        )
        out[M] = {
            "openings": len(op),
            "unpaired_openings": len(unpaired),
            "vias_tented": tented,
            "min_bridge_mm": round(float(gaps.min()), 4),
            "min_opening_to_other_copper_mm": round(near, 4),
            "min_copper_to_edge_mm": round(edge, 4),
        }
    ok = all(
        m["unpaired_openings"] == 0
        and m["vias_tented"]
        and m["min_bridge_mm"] >= R["mask_bridge"] - TOL
        and m["min_opening_to_other_copper_mm"] >= R["mask_to_copper"] - TOL
        and m["min_copper_to_edge_mm"] >= R["edge_copper"] - TOL
        for m in out.values()
    )
    return {"pass": ok, **out}


def sexpr(text):
    """A KiCad s-expression -> nested lists of strings (quotes stripped)."""
    tok = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    st, cur = [], []
    for t in tok:
        if t == "(":
            st.append(cur)
            cur = []
        elif t == ")":
            node, cur = cur, st.pop()
            cur.append(node)
        else:
            cur.append(t.strip('"'))
    return cur[0]


def _child(node, name):
    return next((c for c in node if isinstance(c, list) and c and c[0] == name), None)


def silk_texts(pcb_text, layer="F.SilkS"):
    """Visible texts on a silk layer of a .kicad_pcb: [{owner, text, height, thickness}]."""
    texts = []

    def walk(node, owner):
        if not isinstance(node, list) or not node:
            return
        if node[0] in ("gr_text", "fp_text", "property"):
            lay = _child(node, "layer")
            eff = _child(node, "effects")
            hidden = (_child(node, "hide") or ["", "no"])[1] == "yes" or (eff and "hide" in eff)
            if lay and lay[1] == layer and eff and not hidden:
                font = _child(eff, "font")
                size, thick = _child(font, "size"), _child(font, "thickness")
                texts.append(
                    {
                        "owner": owner,
                        "text": node[2] if node[0] == "property" else node[1],
                        "height": float(size[1]),
                        "thickness": float(thick[1]) if thick else None,
                    }
                )
            return
        for c in node[1:]:
            if isinstance(c, list):
                walk(c, node[1] if node[0] == "footprint" else owner)

    walk(sexpr(pcb_text), "board")
    return texts


def silk_check(gs, texts, rules=None, silk_layer="F_Silkscreen", mask_layer="F_Mask"):
    import shapely

    from .jlc import RULES as JLC

    R = dict(JLC, **(rules or {}))
    silk_w = sorted(
        {gs.layers[silk_layer]["apertures"][d][1][0] for *_, d, _ in gs.layers[silk_layer]["draws"]}
    )
    short = [t for t in texts if t["height"] < R["silk_text_h"] - TOL]
    thin = [
        t for t in texts if t["thickness"] is not None and t["thickness"] < R["silk_line"] - TOL
    ]
    ratio = [
        t
        for t in texts
        if t["thickness"] is not None and t["thickness"] / t["height"] < R["silk_ratio"] - TOL
    ]
    silk = shapely.union_all(gs.draw_geoms(silk_layer) + gs.flash_geoms(silk_layer))
    pad_silk = round(
        min((silk.distance(g) for g in gs.flash_geoms(mask_layer)), default=float("inf")), 4
    )
    return {
        "pass": (not silk_w or silk_w[0] >= R["silk_line"] - TOL)
        and not short
        and not thin
        and pad_silk >= R["pad_to_silk"] - TOL,
        "min_line_mm": silk_w[0] if silk_w else None,
        "line_widths_mm": silk_w,
        "texts": len(texts),
        "below_text_height": [f"{t['owner']}:{t['text']} {t['height']}" for t in short],
        "below_line_width": [f"{t['owner']}:{t['text']} {t['thickness']}" for t in thin],
        "warn_ratio": [f"{t['owner']}:{t['text']} {t['thickness']}/{t['height']}" for t in ratio],
        "min_pad_to_silk_mm": pad_silk,
    }
