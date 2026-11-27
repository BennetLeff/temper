#!/usr/bin/env python3
"""Multi-layer grid router for the controller board (F, In2, In3, B signal layers since C53) (numpy/scipy; no KiCad needed).

    python3 layout/gridroute.py <geom.json> <drc.json> <routes.json>

Inputs: the board geometry dumped by layout/export_geom.py and the unconnected pairs from a KiCad
DRC report (KiCad computes the ratsnest, including connections made through zones). Output: new
tracks and vias as JSON, applied to the board by layout/apply_routes.py.

Method. A 0.1 mm raster per outer layer. Each net's copper is rasterised; for every routing
width class the "cover" map counts, per cell, how many nets have copper within
R = half width + 0.2 mm clearance + 0.06 mm raster margin. A cell is free for net N when the
cover minus N's own contribution is zero, it is outside every track keep-out (rule areas, grown
by the half width) and >= 0.5 mm + half width from the board edge and hole cutouts. Vias (0.6/0.3)
need both layers free at R = 0.3 + 0.26 mm, no via keep-out, and 0.5 mm drill-to-drill. A* over
(layer, cell) with 8 directions, a via cost, and short pairs routed first. Each route is added to
the copper and cover maps before the next. Widths: 0.8 mm for v15_selv, V_BLOWER and the blower SW node, 0.4 mm for the 3.3 V SW node
(falling back to 0.25 mm if a fine-pitch pin cannot be reached at 0.4), 0.2 mm otherwise.
KiCad's DRC is the authority afterwards.

C34: nets of the "Thermal" class keep 0.20 mm (the thermal-sense unit's floor) to all copper, in the
raster (their cover radius) and in the exact checks. The RTD analog family stays on F.Cu / In2.Cu over
the In1 selv_gnd plane, off In1 antipad holes (merged where closer than the plane's 0.25 mm minimum
width), and changes layer only within RTD_VIA_MM of a selv_gnd via; every via keeps its In1 antipad
0.125 mm off other nets' RTD analog copper, and RTD analog vias keep 1.2 mm drill-to-drill.
"""
from __future__ import annotations

import heapq
import json
import math
import re
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

G = 0.1
RULE = 0.15             # copper clearance (net classes in pcb/controller.kicad_pro)
CLR = RULE + 0.09       # + raster margin (a 0.1 mm raster misplaces an edge by <= 0.07 mm)
EDGE = 0.5
VIA_R, VIA_DRILL_R, HOLE_GAP = 0.3, 0.15, 0.5
VIA_COST = 10           # in grid steps (2 mm)
DIRPEN = ((1.0, 2.5, 1.5), (1.2, 1.2, 1.5), (1.0, 2.0, 1.5), (2.5, 1.0, 1.5))   # [F, In2, In3, B][along X, along Y, diagonal]
# C53: In3 X-preferred (was (2.0, 1.0, 1.5)). The 206 x 76 board's late failures were long X spans (coil_buf_out 64 mm,
# RTD_FAULT_RB 79 mm, UI_CS_EXP_N 94 mm) with F the only X-preferred layer.
SOFT_PEN = 40.0         # cost multiplier for crossing another net's route (negotiated rip-up)
HIST_STEP = 1.0         # added per conflict to a cell's history cost


class Crop:
    """A bool mask stored as its bounding-box crop (i0, j0, arr) in the board raster."""

    def __init__(self, full):
        nz = np.argwhere(full)
        if len(nz) == 0:
            self.i0 = self.j0 = 0
            self.a = np.zeros((0, 0), bool)
            return
        (i0, j0), (i1, j1) = nz.min(0), nz.max(0) + 1
        self.i0, self.j0, self.a = int(i0), int(j0), full[i0:i1, j0:j1].copy()

    def window(self, i0, j0, i1, j1):
        out = np.zeros((i1 - i0, j1 - j0), bool)
        a0, b0 = max(i0, self.i0), max(j0, self.j0)
        a1, b1 = min(i1, self.i0 + self.a.shape[0]), min(j1, self.j0 + self.a.shape[1])
        if a0 < a1 and b0 < b1:
            out[a0 - i0:a1 - i0, b0 - j0:b1 - j0] = self.a[a0 - self.i0:a1 - self.i0, b0 - self.j0:b1 - self.j0]
        return out
SIG_W = 0.15
POWER = {"v15_selv": 0.8, "V15_BLW": 0.8, "V_BLOWER": 0.8, "sw_3v3": 0.4, "sw_12": 0.8, "v3v3": 0.3,   # L3: blower 1.42 A typ
         "V12_FAN2": 0.6, "sw_fan2": 0.8}   # C53 review M3: face-fan buck output (J15, 0.67 A) and SW node
# High-current routed nets never fall back to a 0.25 mm neck (blower 2.70 A peak). V15_BLW (PS3 feed,
# 2.72 A) runs J13 -> bulk -> input caps -> U2 in F.Cu pours; its routed tracks are the EN/BLW_PG branches.
NO_NECK = {"V_BLOWER", "sw_12", "V12_FAN2", "V15_BLW"}
# C53: a no-neck net's one narrower try, at check_layout's power_paths width. V15_BLW's U51 branch hangs off the EN
# divider pad (R150.1), 1 mm outside U51's VIN pour, where 0.8 mm cannot pass R150.2: 0.8-only left it open (run 2)
NARROW = {"V15_BLW": 0.5}
# C53 review M3: V15_BLW's main current is in the BLW_FEED pours, but its routed branches feed D9 (the logic rail,
# <= 1 A) and the face-fan buck's VIN pour (~0.6 A), which ran on 0.25 mm necks; 0.8 mm (was 1.0) fits the 0603 pads
# of its divider branches without a neck
# C53: the current-carrying nets stay on the 1 oz outer layers. LAYOUT.md sizes them with IPC-2221's external
# formula; on six layers the router had put V_BLOWER (>= 1.5 A) and v15_selv (D9, <= 1 A) on 0.5 oz In2/In3,
# where a 0.8 mm track carries about 0.6 A for a 10 K rise (internal formula). check_layout's power_layers gate.
OUTER_ONLY = {"V_BLOWER", "sw_12", "v15_selv", "V15_BLW", "V12_FAN2", "sw_fan2"}
# C53 review M4: the nets whose layer changes can carry > 1 A (check_layout's power_vias gate) get each via's
# companions when the route is made, from the copper around it then, and a via that cannot have them is barred
# and the pair re-routed. Added after routing (layout/power_vias.py, still the back-up), set 4 run 3 left a 2.7 A
# V_BLOWER via by C16 on one barrel: I2C tracks and a v3v3 via had taken the room around it.
CLUSTER = {"V_BLOWER", "V15_BLW"}
COMPANIONS = 2
COMP_STEPS = (0.9, 1.1, 1.3, 1.5)
COMP_REACH = 1.8         # power_vias.REACH: a same-net via this close counts as a companion
CLUSTER_TRIES = 4        # routes per width/margin try, each barring the vias that could not have companions
VIA_BAR_MM = 1.0
LAYERS = ("F", "In2", "In3", "B")    # In2 carries signals where needed; the v3v3 pour refills around them.
# C53: six-layer board; In3 is a signal layer between In2 and the In4 selv_gnd plane (no In3 tracks over the RTD
# regions: rule areas from build_board.py)
# C34: per-net clearance above RULE (net class "Thermal": 0.20 mm), from geom["clearance"]; a pair keeps
# the larger of its two nets' clearances, as KiCad's DRC does
NET_CLR: dict[str, float] = {}
PAIR_CLR: dict[frozenset, float] = {}     # geom["pair_clearance"]: e.g. selv_gnd / v3v3 0.20 mm
# C34: the RTD analog family (geom["rtd_analog"]): F.Cu / In2.Cu only (reference plane In1 selv_gnd),
# layer changes only within RTD_VIA_MM of a selv_gnd plane via, and their vias (and every via next to
# them) far enough apart that their In1 antipads stay separate holes
RTD_ANALOG: set[str] = set()
RTD_VIA_MM = 2.5
RTD_HOLE_GAP = 1.2       # drill edge to drill edge around an RTD analog via (In1 antipad 0.5 + web 0.25)
IN1_ANTIPAD = 0.20       # In1 plane clearance (build_board.py)


def extra(net):
    """Clearance a net needs beyond RULE."""
    return NET_CLR.get(net, RULE) - RULE


def configure(geom):
    NET_CLR.clear()
    NET_CLR.update(geom.get("clearance", {}))
    PAIR_CLR.clear()
    PAIR_CLR.update({frozenset((a, b)): c for a, b, c in geom.get("pair_clearance", [])})
    RTD_ANALOG.clear()
    RTD_ANALOG.update(geom.get("rtd_analog", []))
    global RTD_VIA_MM
    RTD_VIA_MM = geom.get("rtd_return_via_mm", RTD_VIA_MM)


class Raster:
    def __init__(self, geom):
        x0, y0, x1, y1 = geom["edge"]
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int((x1 - x0) / G) + 2, int((y1 - y0) / G) + 2
        self.nets = sorted({p["net"] for p in geom["pads"]} | {t["net"] for t in geom["tracks"]}
                           | {v["net"] for v in geom["vias"]} | {z["net"] for z in geom["zones"]})
        self.nid = {n: i + 1 for i, n in enumerate(self.nets)}

    def px(self, x, y):
        return (x - self.x0) / G, (y - self.y0) / G

    def image(self):
        return Image.new("L", (self.nx, self.ny), 0)


def draw_poly(dr, ras, poly, fill=1):
    for pg in poly:
        pts = [ras.px(x, y) for x, y in pg["outline"]]
        if len(pts) >= 3:
            dr.polygon(pts, fill=fill)
        for h in pg["holes"]:
            hp = [ras.px(x, y) for x, y in h]
            if len(hp) >= 3:
                dr.polygon(hp, fill=0)


def draw_seg(dr, ras, a, b, w, fill=1):
    pa, pb = ras.px(*a), ras.px(*b)
    r = w / 2 / G
    dr.line([pa, pb], fill=fill, width=max(1, int(round(w / G))))
    for p in (pa, pb):
        dr.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def draw_disk(dr, ras, c, r, fill=1):
    p = ras.px(*c)
    rr = r / G
    dr.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=fill)


def disk(r):
    n = int(math.ceil(r / G))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    return (xx * xx + yy * yy) * G * G <= r * r


def box_poly(r):
    return Polygon([(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])])


def shp(poly):
    out = []
    for pg in poly:
        if len(pg["outline"]) >= 3:
            out.append(Polygon(pg["outline"], [h for h in pg["holes"] if len(h) >= 3]).buffer(0))
    return unary_union(out) if out else None


class Exact:
    """Exact (vector) clearance check for the straight pieces: pad escapes and pulled-tight
    segments. Copper per layer in 2 mm buckets as shapely geometries with their nets."""
    B = 2.0

    def __init__(self, geom):
        self.items = {l: {} for l in LAYERS}
        self.keep = {l: [] for l in LAYERS}
        for p in geom["pads"]:
            g = shp(p["poly"])
            if g is not None:
                self.add(p["layer"], g, p["net"])
        for t in geom["tracks"]:
            self.add(t["layer"], LineString([t["a"], t["b"]]).buffer(t["w"] / 2), t["net"])
        for v in geom["vias"]:
            for l in LAYERS:
                self.add(l, Point(v["at"]).buffer(v["r"]), v["net"])
        for z in geom["zones"]:
            g = shp(z["poly"])
            if g is not None:
                self.add(z["layer"], g, z["net"])
        for ra in geom["rules"]:
            if ra["tracks"]:
                g = shp(ra["poly"])
                for l in ra["layers"]:
                    self.keep[l].append(g)
        self.keep_v = [shp(ra["poly"]) for ra in geom["rules"] if ra["vias"]]
        x0, y0, x1, y1 = geom["edge"]
        self.inner = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]).buffer(-EDGE)
        self.forbid = [(set(f_["nets"]), box_poly(f_["rect"])) for f_ in geom.get("forbid", [])]
        self.holes = [Point(cx, cy).buffer(r + EDGE) for cx, cy, r in geom["circles"]]

    def add(self, l, g, net, tag=None):
        x0, y0, x1, y1 = g.bounds
        for i in range(int(x0 // self.B), int(x1 // self.B) + 1):
            for j in range(int(y0 // self.B), int(y1 // self.B) + 1):
                self.items[l].setdefault((i, j), []).append((g, net, tag))

    def remove_tag(self, tag):
        for l in LAYERS:
            for k, lst in self.items[l].items():
                if any(t == tag for _, _, t in lst):
                    self.items[l][k] = [x for x in lst if x[2] != tag]

    def via_ok(self, c, net, drills):
        """Exact check of a 0.6/0.3 via: copper clearance on every layer, keep-outs, drill spacing."""
        body = Point(c).buffer(VIA_R, quad_segs=8)
        if not self.inner.contains(body) or any(h.intersects(body) for h in self.holes):
            return False
        if any(k.intersects(body) for k in self.keep_v):
            return False
        for l in LAYERS:
            # C53: a track-only rule area (the In3 RTD keep-outs) does not forbid vias; keep_v above covers
            # the areas that do. Applying keep[l] here rejected every via the grid search put in them.
            if not self.seg_ok(l, c, c, 2 * VIA_R, net, keep=False):
                return False
        return all(math.dist(c, (dx, dy)) - dr - VIA_DRILL_R >= HOLE_GAP - 1e-6 for dx, dy, dr in drills
                   if math.dist(c, (dx, dy)) > 1e-6)

    def seg_ok(self, l, p, q, w, net, fixed_only=False, keep=True):
        body = LineString([p, q]).buffer(w / 2, quad_segs=4) if p != q else Point(p).buffer(w / 2)
        if not self.inner.contains(body) or any(h.intersects(body) for h in self.holes):
            return False
        if keep and any(k.intersects(body) for k in self.keep[l]):
            return False
        if any(net in nets_ and poly.intersects(body) for nets_, poly in self.forbid):
            return False
        probe = body.buffer(RULE + 0.005, quad_segs=8)   # polygonal buffers under-reach arcs: keep a margin
        probes = {}

        def probe_for(n):
            c = max(NET_CLR.get(net, RULE), NET_CLR.get(n, RULE), PAIR_CLR.get(frozenset((net, n)), RULE))
            if c <= RULE + 1e-9:
                return probe
            if c not in probes:
                probes[c] = body.buffer(c + 0.005, quad_segs=8)
            return probes[c]
        cmax = max([RULE] + list(NET_CLR.values()) + list(PAIR_CLR.values())) + 0.01
        x0, y0, x1, y1 = body.bounds
        x0, y0, x1, y1 = x0 - cmax, y0 - cmax, x1 + cmax, y1 + cmax
        seen = set()
        for i in range(int(x0 // self.B), int(x1 // self.B) + 1):
            for j in range(int(y0 // self.B), int(y1 // self.B) + 1):
                for g, n, _t in self.items[l].get((i, j), ()):
                    if fixed_only and _t is not None:
                        continue
                    if n != net and id(g) not in seen:
                        seen.add(id(g))
                        if g.intersects(probe_for(n)):
                            return False
        return True


class Router:
    def __init__(self, geom):
        self.g = geom
        self.ex = Exact(geom)
        self.ras = ras = Raster(geom)
        # per-net copper (bbox-cropped bool arrays) per layer
        self.masks = {l: {} for l in LAYERS}
        per = {l: {} for l in LAYERS}
        for p in geom["pads"]:
            per[p["layer"]].setdefault(p["net"], []).append(("poly", p["poly"]))
        for t in geom["tracks"]:
            per[t["layer"]].setdefault(t["net"], []).append(("seg", t))
        for v in geom["vias"]:
            for l in LAYERS:
                per[l].setdefault(v["net"], []).append(("disk", v))
        for z in geom["zones"]:
            per[z["layer"]].setdefault(z["net"], []).append(("poly", z["poly"]))
        for l in LAYERS:
            for net, items in per[l].items():
                im = ras.image()
                dr = ImageDraw.Draw(im)
                for kind, it in items:
                    if kind == "poly":
                        draw_poly(dr, ras, it)
                    elif kind == "seg":
                        draw_seg(dr, ras, it["a"], it["b"], it["w"])
                    else:
                        draw_disk(dr, ras, it["at"], it["r"])
                self.masks[l][net] = Crop(np.asarray(im, dtype=bool).T)     # [i, j] = [x, y]
        self.base = {l: dict(self.masks[l]) for l in LAYERS}
        self.routes = {}            # rid -> (net, segs, vias)
        self.hist = {l: np.zeros((ras.nx, ras.ny), np.float32) for l in LAYERS}
        self.route_drills = {}      # rid -> [[x, y, r]]
        self.cover = {}
        # static blocks: board edge, hole cut-outs, rule areas
        self.edge_dist = None
        im = ras.image()
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, ras.nx, ras.ny], fill=1)
        x0, y0, x1, y1 = geom["edge"]
        p0, p1 = ras.px(x0, y0), ras.px(x1, y1)
        dr.rectangle([p0[0], p0[1], p1[0], p1[1]], fill=0)
        for cx, cy, r in geom["circles"]:
            draw_disk(dr, ras, (cx, cy), r)
        outside = np.asarray(im, dtype=bool).T
        self.edge_dist = ndimage.distance_transform_edt(~outside) * G      # mm to the nearest edge
        self.keep_tracks = {}
        self.keep_vias = np.zeros((ras.nx, ras.ny), bool)
        for l in LAYERS:
            im = ras.image()
            dr = ImageDraw.Draw(im)
            for ra in geom["rules"]:
                if ra["tracks"] and l in ra["layers"]:
                    draw_poly(dr, ras, ra["poly"])
            self.keep_tracks[l] = np.asarray(im, dtype=bool).T
            self.keep_track_dist = None
        im = ras.image()
        dr = ImageDraw.Draw(im)
        for ra in geom["rules"]:
            if ra["vias"]:
                draw_poly(dr, ras, ra["poly"])
        self.keep_vias = np.asarray(im, dtype=bool).T
        self.kt_dist = {l: ndimage.distance_transform_edt(~self.keep_tracks[l]) * G for l in LAYERS}
        self.kv_dist = ndimage.distance_transform_edt(~self.keep_vias) * G
        # drills; an RTD analog via's drill is entered inflated, so every later via keeps the wider gap
        rtd_at = {(round(v["at"][0], 3), round(v["at"][1], 3)) for v in geom["vias"] if v["net"] in RTD_ANALOG}
        self.drills = [[x_, y_, self.drill_r("" if (round(x_, 3), round(y_, 3)) not in rtd_at else next(iter(RTD_ANALOG)))
                        if abs(r_ - VIA_DRILL_R) < 1e-6 else r_] for x_, y_, r_ in geom["drills"]]
        self.drill_nets = list(geom.get("drill_nets") or [""] * len(geom["drills"]))
        self.via_at = {(round(v["at"][0], 3), round(v["at"][1], 3)) for v in geom["vias"]}
        # selv_gnd plane vias (the fan-out and any routed ones): the return transitions RTD analog vias need
        self.gnd_vias = np.array([v["at"] for v in geom["vias"] if v["net"] == "selv_gnd"] or [[1e9, 1e9]])

    def rtd_keep(self, net):
        """Full-board cells where a via of `net` would put its In1 antipad within 0.125 mm of another
        net's RTD analog copper on F/In2 (cached; dropped whenever RTD analog copper changes)."""
        key = net if net in RTD_ANALOG else ""
        cache = self.__dict__.setdefault("_rtd_keep", {})
        if key not in cache:
            full = np.zeros((self.ras.nx, self.ras.ny), bool)
            st = disk(VIA_R + IN1_ANTIPAD + 0.125 + 0.05)
            for n_ in RTD_ANALOG - {net}:
                for l in ("F", "In2"):
                    m_ = self.masks[l].get(n_)
                    if m_ is None or m_.a.size == 0:
                        continue
                    k = st.shape[0] // 2 + 1
                    i0, j0 = m_.i0 - k, m_.j0 - k
                    i1, j1 = m_.i0 + m_.a.shape[0] + k, m_.j0 + m_.a.shape[1] + k
                    d = ndimage.binary_dilation(m_.window(i0, j0, i1, j1), st)
                    a0, b0 = max(i0, 0), max(j0, 0)
                    a1, b1 = min(i1, self.ras.nx), min(j1, self.ras.ny)
                    full[a0:a1, b0:b1] |= d[a0 - i0:a1 - i0, b0 - j0:b1 - j0]
            cache[key] = full
        return cache[key]

    @staticmethod
    def drill_r(net):
        return VIA_DRILL_R + (RTD_HOLE_GAP - HOLE_GAP if net in RTD_ANALOG else 0.0)

    # ---- cover maps
    def get_cover(self, r):
        if r not in self.cover:
            st = disk(r)
            self.cover[r] = {}
            n = disk(r + max([0.0] + [extra(k) for k in NET_CLR])).shape[0] // 2 + 1
            for l in LAYERS:
                c = np.zeros((self.ras.nx, self.ras.ny), np.uint8)
                for net, m in self.masks[l].items():
                    if m.a.size == 0:
                        continue
                    i0, j0 = m.i0 - n, m.j0 - n
                    i1, j1 = m.i0 + m.a.shape[0] + n, m.j0 + m.a.shape[1] + n
                    d = ndimage.binary_dilation(m.window(i0, j0, i1, j1), disk(r + extra(net)) if extra(net) else st)
                    a0, b0 = max(i0, 0), max(j0, 0)
                    a1, b1 = min(i1, self.ras.nx), min(j1, self.ras.ny)
                    c[a0:a1, b0:b1] += d[a0 - i0:a1 - i0, b0 - j0:b1 - j0].astype(np.uint8)
                self.cover[r][l] = c
        return self.cover[r]

    def get_base_cover(self, r):
        """Cover maps of the fixed copper only (pads, zones, fan-outs, earlier rounds)."""
        if not hasattr(self, "_bc"):
            self._bc = {}
        if r not in self._bc:
            saved = self.masks
            self.masks = self.base
            saved_cover = self.cover
            self.cover = {}
            self._bc[r] = self.get_cover(r)
            self.masks, self.cover = saved, saved_cover
        return self._bc[r]

    def own_base(self, net, r, l, win):
        saved = self.masks
        self.masks = self.base
        try:
            return self.own(net, r, l, win)
        finally:
            self.masks = saved

    def own(self, net, r, l, win):
        i0, j0, i1, j1 = win
        r = r + extra(net)          # the net's own contribution to the cover maps (get_cover)
        n = int(math.ceil(r / G)) + 1
        a0, b0 = max(0, i0 - n), max(0, j0 - n)
        sub = self.masks[l].get(net)
        if sub is None:
            return np.zeros((i1 - i0, j1 - j0), bool)
        crop = sub.window(a0, b0, i1 + n, j1 + n)
        d = ndimage.binary_dilation(crop, disk(r)) if r > 0 else crop
        return d[i0 - a0:i0 - a0 + (i1 - i0), j0 - b0:j0 - b0 + (j1 - j0)]

    def inside_own(self, net, w, l, win):
        """Cells where a track of width w lies entirely on the net's existing copper."""
        i0, j0, i1, j1 = win
        sub = self.masks[l].get(net)
        if sub is None:
            return np.zeros((i1 - i0, j1 - j0), bool)
        return ndimage.binary_erosion(sub.window(i0, j0, i1, j1), disk(w / 2 + G))

    def raster_net(self, l, net, skip=None):
        """Full-board mask of a net on a layer: its fixed copper plus its routes (except `skip`)."""
        full = np.zeros((self.ras.nx, self.ras.ny), bool)
        b = self.base[l].get(net)
        if b is not None and b.a.size:
            full[b.i0:b.i0 + b.a.shape[0], b.j0:b.j0 + b.a.shape[1]] = b.a
        im = self.ras.image()
        dr = ImageDraw.Draw(im)
        for rid, (n, segs, vias) in self.routes.items():
            if n != net or rid == skip:
                continue
            for sl, a, b_, w in segs:
                if sl == l:
                    draw_seg(dr, self.ras, a, b_, w)
            for c in vias:
                draw_disk(dr, self.ras, c, VIA_R)
        return full | np.asarray(im, dtype=bool).T

    def remove_route(self, rid):
        net, segs, vias = self.routes[rid]
        if net in RTD_ANALOG:
            self.__dict__.pop("_rtd_keep", None)
        xs = [p[0] for _, p, q, _ in segs] + [q[0] for _, p, q, _ in segs] + [c[0] for c in vias]
        ys = [p[1] for _, p, q, _ in segs] + [q[1] for _, p, q, _ in segs] + [c[1] for c in vias]
        rmax = max(list(self.cover) + [1.0])
        pad = int(math.ceil((rmax + 0.5) / G)) + 2
        a0, b0 = self.ras.px(min(xs), min(ys))
        a1, b1 = self.ras.px(max(xs), max(ys))
        i0, j0 = max(0, int(a0) - pad), max(0, int(b0) - pad)
        i1, j1 = min(self.ras.nx, int(a1) + pad + 1), min(self.ras.ny, int(b1) + pad + 1)
        for l in LAYERS:
            old = self.masks[l].get(net)
            if old is None:
                continue
            newf = self.raster_net(l, net, skip=rid)
            oldw = old.window(i0, j0, i1, j1)
            neww = newf[i0:i1, j0:j1]
            for r, cov in self.cover.items():
                st = disk(r + extra(net))
                cov[l][i0:i1, j0:j1] -= (ndimage.binary_dilation(oldw, st) & ~ndimage.binary_dilation(neww, st)).astype(np.uint8)
            self.masks[l][net] = Crop(newf)
        del self.routes[rid]
        self.route_drills.pop(rid, None)
        self.ex.remove_tag(rid)

    def add_copper(self, net, segs, vias, rid=None):
        if net in RTD_ANALOG:
            self.__dict__.pop("_rtd_keep", None)
        if rid is not None:
            self.routes[rid] = (net, segs, vias)
            self.route_drills[rid] = [[c[0], c[1], self.drill_r(net)] for c in vias]
            for l, p, q, w_ in segs:
                self.ex.add(l, LineString([p, q]).buffer(w_ / 2), net, rid)
            for c in vias:
                for l in LAYERS:
                    self.ex.add(l, Point(c).buffer(VIA_R), net, rid)
        ras = self.ras
        for l in LAYERS:
            im = ras.image()
            dr = ImageDraw.Draw(im)
            any_ = False
            for sl, a, b, w in segs:
                if sl == l:
                    draw_seg(dr, ras, a, b, w)
                    any_ = True
            for c in vias:
                draw_disk(dr, ras, c, VIA_R)
                any_ = True
            if not any_:
                continue
            newf = np.asarray(im, dtype=bool).T
            nc = Crop(newf)
            old = self.masks[l].get(net)
            pad = 12
            i0 = max(0, nc.i0 - pad - 1)
            j0 = max(0, nc.j0 - pad - 1)
            i1 = min(self.ras.nx, nc.i0 + nc.a.shape[0] + pad + 1)
            j1 = min(self.ras.ny, nc.j0 + nc.a.shape[1] + pad + 1)
            oldw = old.window(i0, j0, i1, j1) if old else np.zeros((i1 - i0, j1 - j0), bool)
            neww = nc.window(i0, j0, i1, j1) | oldw
            for r, cov in self.cover.items():
                st = disk(r + extra(net))
                before = ndimage.binary_dilation(oldw, st)
                after = ndimage.binary_dilation(neww, st)
                cov[l][i0:i1, j0:j1] += (after & ~before).astype(np.uint8)
            if old is None:
                full = np.zeros((self.ras.nx, self.ras.ny), bool)
            else:
                full = np.zeros((self.ras.nx, self.ras.ny), bool)
                full[old.i0:old.i0 + old.a.shape[0], old.j0:old.j0 + old.a.shape[1]] = old.a
            full |= newf
            self.masks[l][net] = Crop(full)
        return

    # ---- one connection
    def cluster(self, net, segs, vias, w):
        """Companion vias for a CLUSTER net's route: for each via, up to COMPANIONS more within COMP_REACH,
        each on one of the via's tracks or around it, tied back by a stub on the via's other layers, exactly
        checked against the copper routed so far. Returns (segs, vias, the vias left short)."""
        drills = [tuple(d) for d in self.drills] + [tuple(d) for v in self.route_drills.values() for d in v]
        drills += [(c[0], c[1], VIA_DRILL_R) for c in vias]
        rk = self.rtd_keep(net) if RTD_ANALOG else None
        placed = [tuple(c) for c in vias]
        add_s, add_v, short = [], [], []
        for c in vias:
            inc = []
            for l, p, q, _ in segs:
                for a_, b_ in ((p, q), (q, p)):
                    if math.dist(a_, c) < 0.05 and math.dist(a_, b_) > 1e-6:
                        inc.append((l, b_))
            layers = sorted({l for l, _ in inc})
            cands = []
            for l, e in inc:
                d = math.dist(c, e)
                u = ((e[0] - c[0]) / d, (e[1] - c[1]) / d)
                cands += [((c[0] + s * u[0], c[1] + s * u[1]), l) for s in COMP_STEPS if s <= d]
                cands += [((c[0] - sg * s * u[1], c[1] + sg * s * u[0]), None) for s in COMP_STEPS for sg in (1, -1)]
            cands += [((c[0] + s * math.cos(math.pi * k / 8), c[1] + s * math.sin(math.pi * k / 8)), None)
                      for k in range(16) for s in COMP_STEPS]
            got = sum(1 for o in placed if 1e-6 < math.dist(o, c) <= COMP_REACH)
            for p, on in cands:
                if got >= COMPANIONS:
                    break
                if any(math.dist(p, o) < 0.9 for o in placed):
                    continue
                if rk is not None:
                    pi_, pj_ = self.ras.px(*p)
                    pi_, pj_ = int(round(pi_)), int(round(pj_))
                    if not (0 <= pi_ < self.ras.nx and 0 <= pj_ < self.ras.ny) or rk[pi_, pj_]:
                        continue
                if not self.ex.via_ok(p, net, drills):
                    continue
                stubs = [l for l in layers if l != on]
                if not all(self.ex.seg_ok(l, p, c, w, net) for l in stubs):
                    continue
                add_s += [(l, p, tuple(c), w) for l in stubs]
                add_v.append(p)
                placed.append(p)
                drills.append((p[0], p[1], VIA_DRILL_R))
                got += 1
            if got < COMPANIONS:
                short.append(tuple(c))
        return list(segs) + add_s, list(vias) + add_v, short

    def route(self, net, a, b, la, lb, w, margin, soft=False, via_bar=()):
        """soft=False: other nets' routes are obstacles. soft=True: they are a cost (negotiated
        congestion): the path may cross them, and the caller rips up the routes it crosses.
        via_bar: points no via of this route may come within VIA_BAR_MM of (cluster)."""
        ras = self.ras
        r_t = w / 2 + CLR + extra(net)
        r_v = VIA_R + CLR + extra(net)
        rtd = net in RTD_ANALOG
        cov_t, cov_v = self.get_cover(r_t), self.get_cover(r_v)
        pa, pb = ras.px(*a), ras.px(*b)
        m = margin / G
        i0, j0 = max(0, int(min(pa[0], pb[0]) - m)), max(0, int(min(pa[1], pb[1]) - m))
        i1, j1 = min(ras.nx, int(max(pa[0], pb[0]) + m) + 1), min(ras.ny, int(max(pa[1], pb[1]) + m) + 1)
        win = (i0, j0, i1, j1)
        free = {}
        soft_t = {}
        all_drills = self.drills + [d_ for v in self.route_drills.values() for d_ in v]
        if rtd:
            # In1 antipads of every drilled item in the window (via: copper r 0.3; through-hole pad:
            # drill + 0.35 annulus) + the plane clearance, closed by the plane's 0.25 mm minimum width,
            # because holes closer than that merge into one
            # The net's own antipads are its terminal envelopes (allowed); only their merges with other
            # holes are blocked.
            im = Image.new("L", (i1 - i0, j1 - j0), 0)
            dr = ImageDraw.Draw(im)
            im_own = Image.new("L", (i1 - i0, j1 - j0), 0)
            dr_own = ImageDraw.Draw(im_own)
            n_fixed = len(self.drills)
            route_nets = [self.routes[rid][0] for rid, v in self.route_drills.items() for _ in v]
            for k_, (cx, cy, r) in enumerate(all_drills):
                is_via = k_ >= n_fixed or (round(cx, 3), round(cy, 3)) in self.via_at
                d_net = self.drill_nets[k_] if k_ < n_fixed else route_nets[k_ - n_fixed]
                if is_via and d_net == "selv_gnd":
                    continue            # a plane via is In1 copper, not a hole
                rc = (VIA_R if is_via else r + 0.35) + IN1_ANTIPAD + 0.05
                px_, py_ = ras.px(cx, cy)
                if i0 - 20 <= px_ <= i1 + 20 and j0 - 20 <= py_ <= j1 + 20:
                    box = [px_ - i0 - rc / G, py_ - j0 - rc / G, px_ - i0 + rc / G, py_ - j0 + rc / G]
                    dr.ellipse(box, fill=1)
                    if d_net == net:
                        dr_own.ellipse(box, fill=1)
            in1_holes = ndimage.binary_closing(np.asarray(im, dtype=bool).T, disk(0.15), border_value=0)
            in1_holes &= ~np.asarray(im_own, dtype=bool).T
        for l in LAYERS:
            if soft:
                bct = self.get_base_cover(r_t)
                own_b = self.own_base(net, r_t, l, win)
                blocked = (bct[l][i0:i1, j0:j1].astype(np.int16) - own_b) > 0
                soft_t[l] = ((cov_t[l][i0:i1, j0:j1].astype(np.int16) - bct[l][i0:i1, j0:j1])
                             - (self.own(net, r_t, l, win).astype(np.int16) - own_b)) > 0
            else:
                blocked = (cov_t[l][i0:i1, j0:j1].astype(np.int16) - self.own(net, r_t, l, win)) > 0
            blocked &= ~self.inside_own(net, w, l, win)
            blocked |= self.edge_dist[i0:i1, j0:j1] < EDGE + w / 2 + 0.05
            for f_ in self.g.get("forbid", []):
                if net in f_["nets"]:
                    fx0, fy0 = ras.px(f_["rect"][0] - w / 2 - 0.05, f_["rect"][1] - w / 2 - 0.05)
                    fx1, fy1 = ras.px(f_["rect"][2] + w / 2 + 0.05, f_["rect"][3] + w / 2 + 0.05)
                    a0, b0 = max(0, int(fx0) - i0), max(0, int(fy0) - j0)
                    a1, b1 = min(i1 - i0, int(math.ceil(fx1)) - i0 + 1), min(j1 - j0, int(math.ceil(fy1)) - j0 + 1)
                    if a0 < a1 and b0 < b1:
                        blocked[a0:a1, b0:b1] = True
            blocked |= self.kt_dist[l][i0:i1, j0:j1] < w / 2 + 0.07
            if net in OUTER_ONLY and l not in ("F", "B"):
                blocked[:] = True
            if rtd:
                if l not in ("F", "In2"):
                    blocked[:] = True
                else:
                    # an F/In2 track over an In1 hole has no return plane under it
                    blocked |= in1_holes
            free[l] = ~blocked
        vb = np.zeros((i1 - i0, j1 - j0), bool)
        for l in LAYERS:
            if soft:
                bcv = self.get_base_cover(r_v)
                vb |= (bcv[l][i0:i1, j0:j1].astype(np.int16) - self.own_base(net, r_v, l, win)) > 0
            else:
                vb |= (cov_v[l][i0:i1, j0:j1].astype(np.int16) - self.own(net, r_v, l, win)) > 0
        vb |= self.edge_dist[i0:i1, j0:j1] < EDGE + VIA_R + 0.05
        vb |= self.kv_dist[i0:i1, j0:j1] < VIA_R + 0.07
        if via_bar:
            bx_ = ras.x0 + np.arange(i0, i1) * G
            by_ = ras.y0 + np.arange(j0, j1) * G
            for qx, qy in via_bar:
                vb |= ((bx_[:, None] - qx) ** 2 + (by_[None, :] - qy) ** 2) <= VIA_BAR_MM ** 2
        # drill-to-drill
        im = Image.new("L", (i1 - i0, j1 - j0), 0)
        dr = ImageDraw.Draw(im)
        for cx, cy, r in self.drills + [d_ for v in self.route_drills.values() for d_ in v]:
            px_, py_ = ras.px(cx, cy)
            rr = (r + self.drill_r(net) + HOLE_GAP) / G
            if i0 - rr <= px_ <= i1 + rr and j0 - rr <= py_ <= j1 + rr:
                dr.ellipse([px_ - i0 - rr, py_ - j0 - rr, px_ - i0 + rr, py_ - j0 + rr], fill=1)
        vb |= np.asarray(im, dtype=bool).T
        if RTD_ANALOG:
            # a via's In1 antipad (0.3 + 0.20) stays >= 0.125 mm from every RTD analog track or pad of
            # another net, so the plane under that track keeps its 0.25 mm minimum width
            vb |= self.rtd_keep(net)[i0:i1, j0:j1]
        if rtd:
            # a layer change of an RTD analog net only beside a selv_gnd plane via
            xs_ = ras.x0 + (np.arange(i0, i1) * G)
            ys_ = ras.y0 + (np.arange(j0, j1) * G)
            near = np.zeros((i1 - i0, j1 - j0), bool)
            gv = self.gnd_vias
            sel = gv[(gv[:, 0] > xs_[0] - RTD_VIA_MM - 1) & (gv[:, 0] < xs_[-1] + RTD_VIA_MM + 1)
                     & (gv[:, 1] > ys_[0] - RTD_VIA_MM - 1) & (gv[:, 1] < ys_[-1] + RTD_VIA_MM + 1)]
            for gx, gy in sel:
                near |= ((xs_[:, None] - gx) ** 2 + (ys_[None, :] - gy) ** 2) <= (RTD_VIA_MM - 0.1) ** 2
            vb |= ~near
        via_ok = ~vb
        si, sj = int(round(pa[0])) - i0, int(round(pa[1])) - j0
        gi, gj = int(round(pb[0])) - i0, int(round(pb[1])) - j0
        W, H = i1 - i0, j1 - j0
        def xy(i, j):
            return (ras.x0 + (i + i0) * G, ras.y0 + (j + j0) * G)

        def escapes(p, layers, ci, cj):
            """Free cells near an end point that a straight, exactly checked piece reaches."""
            out = []
            for l in layers:
                cand = []
                for di in range(-12, 13):
                    for dj in range(-12, 13):
                        i, j = ci + di, cj + dj
                        if 0 <= i < W and 0 <= j < H and free[l][i, j] and di * di + dj * dj <= 144:
                            cand.append((math.hypot(xy(i, j)[0] - p[0], xy(i, j)[1] - p[1]), l, i, j))
                cand.sort()
                n = 0
                for dd, l_, i, j in cand:
                    if self.ex.seg_ok(l_, tuple(p), xy(i, j), w, net, fixed_only=soft):
                        out.append((dd / G, l_, i, j))
                        n += 1
                        if n >= 40:
                            break
            return out
        st = escapes(a, la, si, sj)
        gl = escapes(b, lb, gi, gj)
        if not st or not gl:
            return None, "end cell blocked"
        starts = [(l, i, j) for _, l, i, j in st]
        goals = {(l, i, j) for _, l, i, j in gl}
        L = {n: k for k, n in enumerate(LAYERS)}
        fr = np.stack([free[n] for n in LAYERS])
        if soft:
            pen = np.stack([soft_t[n] for n in LAYERS]).astype(np.float32) * SOFT_PEN
            pen += np.stack([self.hist[n][i0:i1, j0:j1] for n in LAYERS])
        else:
            pen = None
        dist = np.full((len(LAYERS), W, H), np.inf)
        prev = {}
        pq = []
        for c0, l, i, j in st:
            dist[L[l], i, j] = c0
            heapq.heappush(pq, (c0 + math.hypot(i - gi, j - gj), c0, L[l], i, j))
        goal_set = {(L[l], i, j) for l, i, j in goals}
        moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
        found = None
        while pq:
            f_, gcost, l, i, j = heapq.heappop(pq)
            if gcost > dist[l, i, j]:
                continue
            if (l, i, j) in goal_set:
                found = (l, i, j)
                break
            for di, dj, c in moves:
                # preferred directions: F.Cu runs along X, B.Cu along Y (classic two-layer channels)
                c = c * (DIRPEN[l][0] if dj == 0 else DIRPEN[l][1] if di == 0 else DIRPEN[l][2])
                ni, nj = i + di, j + dj
                if di and dj and not (0 <= ni < W and 0 <= nj < H and fr[l, ni, j] and fr[l, i, nj]):
                    continue            # no corner cutting: a diagonal step needs both orthogonal cells free
                if 0 <= ni < W and 0 <= nj < H and fr[l, ni, nj]:
                    ng = gcost + (c if pen is None else c * (1.0 + pen[l, ni, nj]))
                    if ng < dist[l, ni, nj]:
                        dist[l, ni, nj] = ng
                        prev[(l, ni, nj)] = (l, i, j)
                        heapq.heappush(pq, (ng + math.hypot(ni - gi, nj - gj), ng, l, ni, nj))
            if via_ok[i, j]:
                for ol in range(len(LAYERS)):
                    if ol == l or not fr[ol, i, j]:
                        continue
                    ng = gcost + VIA_COST
                    if ng < dist[ol, i, j]:
                        dist[ol, i, j] = ng
                        prev[(ol, i, j)] = (l, i, j)
                        heapq.heappush(pq, (ng + math.hypot(i - gi, j - gj), ng, ol, i, j))
        if found is None:
            return None, "no path"
        path = [found]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        names = LAYERS
        pts = [(names[l], xy(i, j)) for l, i, j in path]
        pts = [(pts[0][0], tuple(a))] + pts + [(pts[-1][0], tuple(b))]
        segs, vias = [], []
        k = 0
        while k < len(pts) - 1:
            l = pts[k][0]
            if pts[k + 1][0] != l:
                vias.append(pts[k][1])
                k += 1
                continue
            # pull tight: the farthest same-layer point reachable by an exactly legal straight piece
            run_end = k + 1
            while run_end + 1 < len(pts) and pts[run_end + 1][0] == l:
                run_end += 1
            m_ = k + 1
            lo, hi = k + 1, run_end
            best = k + 1
            span = run_end - k
            cands = sorted({run_end} | {k + 1 + int((span - 1) * f) for f in (0.8, 0.6, 0.45, 0.3, 0.2, 0.12, 0.06)}
                           | set(range(k + 2, min(run_end, k + 10) + 1)), reverse=True)
            for cand in cands:
                ddx, ddy = abs(pts[cand][1][0] - pts[k][1][0]), abs(pts[cand][1][1] - pts[k][1][1])
                octo = ddx < 1e-6 or ddy < 1e-6 or abs(ddx - ddy) < 1e-6 or k == 0 or cand == len(pts) - 1
                if cand > k + 1 and octo and self.ex.seg_ok(l, pts[k][1], pts[cand][1], w, net, fixed_only=soft):
                    best = cand
                    break
            m_ = best
            segs.append((l, pts[k][1], pts[m_][1], w))
            k = m_
        if soft:
            # history: every congested cell on the path gets dearer for the next attempt
            for l, i, j in path:
                if soft_t[names[l]][i, j]:
                    self.hist[names[l]][i0 + i, j0 + j] += HIST_STEP
        return (segs, vias), "ok"


def main():
    geom = json.load(open(sys.argv[1]))
    drc = json.load(open(sys.argv[2]))
    configure(geom)
    R = Router(geom)
    tht = {(round(d_[0], 3), round(d_[1], 3)) for d_ in geom["drills"]}
    pairs = []
    for u in drc["unconnected_items"]:
        it = u["items"]
        net = re.search(r"\[([^\]]+)\]", it[0]["description"]).group(1)
        ends = []
        for e in it:
            p = (e["pos"]["x"], e["pos"]["y"])
            desc = e["description"]
            if (round(p[0], 3), round(p[1], 3)) in tht or "F.Cu - B.Cu" in desc:
                ls = LAYERS
            elif "on B.Cu" in desc:
                ls = ("B",)
            elif "on In2.Cu" in desc:
                ls = ("In2",)
            elif "on In3.Cu" in desc:
                ls = ("In3",)
            else:
                ls = ("F",)
            ends.append((p, ls))
        pairs.append((net, ends))
    # shortest first; nets named in GRIDROUTE_FIRST (route.py's repair step: the nets that were left
    # open) go ahead of everything, so the copper ripped around their ends is theirs to use
    import os
    first = set(filter(None, os.environ.get("GRIDROUTE_FIRST", "").split(",")))
    # L3: long cross-board pairs (>= LONG_MM, e.g. the PWM lines and read-backs between J4 and the
    # module) go first, longest first, so they get corridors before short local links fill the
    # bands they must cross; everything else stays shortest first
    LONG_MM = 60.0

    def order(q):
        d = math.dist(q[1][0][0], q[1][1][0])
        return (q[0] not in first, 0 if d >= LONG_MM else 1, -d if d >= LONG_MM else d)
    pairs.sort(key=order)
    queue = list(range(len(pairs)))
    ripped_count = {}
    rip_events = 0
    MAX_RIP_EVENTS = 400         # bounds the run time; what is left goes to the next round
    progress = open(sys.argv[3] + '.progress', 'w')
    failed = []
    n_done = 0

    def attempt(idx, margins):
        net, ((a, la), (b, lb)) = pairs[idx]
        tries = [(POWER.get(net, SIG_W), m) for m in margins]
        if net in POWER and net not in NO_NECK:
            tries += [(0.25, m) for m in margins]
        elif net in NARROW:
            tries += [(NARROW[net], m) for m in margins]
        why = ""
        best = None
        for w, m in tries:
            bar = []
            for _ in range(CLUSTER_TRIES if net in CLUSTER else 1):
                res, why = R.route(net, a, b, la, lb, w, m, via_bar=tuple(bar))
                if not res:
                    break
                if net not in CLUSTER:
                    R.add_copper(net, res[0], res[1], rid=idx)
                    return True, why
                segs, vias, short = R.cluster(net, res[0], res[1], w)
                if not short:
                    R.add_copper(net, segs, vias, rid=idx)
                    return True, why
                if best is None or len(short) < best[0]:
                    best = (len(short), segs, vias)
                bar += short
        if best is not None:
            # no route had companions at every via: the best one, and power_vias / the gate see the rest
            R.add_copper(net, best[1], best[2], rid=idx)
            return True, "ok, companions short"
        return False, why

    # pass 1: every pair once, other routes are obstacles
    open_pairs = []
    for idx in queue:
        ok, why = attempt(idx, (2.0, 6.0, 15.0, 40.0))
        if not ok:
            open_pairs.append(idx)
    progress.write(f"pass 1: {len(open_pairs)} open\n")
    progress.flush()

    def victims_of(net, segs, vias):
        body = [LineString([p, q]).buffer(w_ / 2 + RULE) for _, p, q, w_ in segs] + \
               [Point(c).buffer(VIA_R + RULE) for c in vias]
        out = []
        for rid, (n2, segs2, vias2) in list(R.routes.items()):
            if n2 == net:
                continue
            geo = [LineString([p, q]).buffer(w2 / 2) for _, p, q, w2 in segs2] + [Point(c).buffer(VIA_R) for c in vias2]
            if any(g1.intersects(g2) for g1 in body for g2 in geo):
                out.append(rid)
        return out

    # pass 2..: transactional rip-up. For an open pair: route it with other routes as a cost (and a
    # history cost that grows on contested cells), rip up the routes that path crosses, route the
    # pair, re-route the ripped ones. Commit only if all of them route; otherwise restore. The
    # routed count never goes down, and every attempt raises the history cost where it failed.
    for rnd in range(1, 3):
        still = []
        for idx in open_pairs:
            net, ((a, la), (b, lb)) = pairs[idx]
            committed = False
            for w_, m_ in [(POWER.get(net, SIG_W), m) for m in (6.0, 15.0, 40.0)] + \
                    ([(0.25, m) for m in (6.0, 15.0)] if net in POWER and net not in NO_NECK else []) + \
                    ([(NARROW[net], m) for m in (6.0, 15.0)] if net in NARROW else []):
                res, why = R.route(net, a, b, la, lb, w_, m_, soft=True)
                if not res:
                    continue
                victims = victims_of(net, res[0], res[1])
                if len(victims) > 30:
                    continue
                saved = {rid: R.routes[rid] for rid in victims}
                for rid in victims:
                    R.remove_route(rid)
                ok, why = attempt(idx, (2.0, 6.0, 15.0, 40.0))
                rerouted, all_ok = [], ok
                if ok:
                    for rid in victims:
                        ok2, _ = attempt(rid, (2.0, 6.0, 15.0, 40.0))
                        if not ok2:
                            all_ok = False
                            break
                        rerouted.append(rid)
                if all_ok:
                    committed = True
                    break
                # roll back
                for rid in rerouted + ([idx] if ok else []):
                    if rid in R.routes:
                        R.remove_route(rid)
                for rid, (n2, segs2, vias2) in saved.items():
                    R.add_copper(n2, segs2, vias2, rid=rid)
            progress.write(f"round {rnd}: {pairs[idx][0]} {'routed' if committed else 'open'} routed={len(R.routes)}\n")
            progress.flush()
            if not committed:
                still.append(idx)
        open_pairs = still
        if not open_pairs:
            break
    # exact legalisation: every routed segment and via is re-checked against all other copper with
    # shapely (the raster can misjudge by a fraction of a cell); offending routes are ripped up and
    # re-routed with a wider raster margin, and checked again
    global CLR
    bad_laps = []
    for lap in range(4):
        drills_all = list(R.drills) + [d_ for v in R.route_drills.values() for d_ in v]
        bad = []
        for rid, (net, segs, vias) in R.routes.items():
            ok_r = all(R.ex.seg_ok(l, p, q, w_, net) for l, p, q, w_ in segs) and \
                all(R.ex.via_ok(c, net, drills_all) for c in vias)
            if not ok_r:
                bad.append(rid)
        progress.write(f"legalise lap {lap}: {len(bad)} routes fail the exact check\n")
        progress.flush()
        bad_laps.append(len(bad))
        if not bad:
            break
        # C53 guard: raster misjudgement shrinks as the margin widens; a large count that does not shrink
        # means the grid search and the exact check disagree on a rule (C53: In3 track keep-outs applied to
        # vias, 6 h of rounds discarding ~90 routes each). Fail the run instead of routing on.
        if lap >= 2 and len(bad) >= 20 and len(bad) >= 0.9 * bad_laps[1] and len(bad) >= 0.2 * len(R.routes):
            print(f"legalise: {len(bad)} of {len(R.routes)} routes still fail the exact check after {lap + 1} laps "
                  f"({bad_laps}); the raster and the exact check disagree on a rule", file=sys.stderr, flush=True)
            sys.exit(3)
        for rid in bad:
            R.remove_route(rid)
        CLR += 0.05
        for rid in bad:
            ok, _ = attempt(rid, (2.0, 6.0, 15.0, 40.0))
            if not ok:
                open_pairs.append(rid)
        CLR -= 0.05
    else:
        drills_all = list(R.drills) + [d_ for v in R.route_drills.values() for d_ in v]
        for rid, (net, segs, vias) in list(R.routes.items()):
            if not (all(R.ex.seg_ok(l, p, q, w_, net) for l, p, q, w_ in segs)
                    and all(R.ex.via_ok(c, net, drills_all) for c in vias)):
                R.remove_route(rid)
                open_pairs.append(rid)
    for idx in open_pairs:
        net, ((a, la), (b, lb)) = pairs[idx]
        failed.append({"net": net, "a": a, "b": b, "why": "no path after negotiated rip-up"})
        print(f"{net}: FAILED", flush=True)
    out = {"tracks": [], "vias": [], "failed": failed}
    for rid, (net, segs, vias) in sorted(R.routes.items()):
        out["tracks"] += [{"net": net, "layer": l, "a": list(p), "b": list(q), "w": w_} for l, p, q, w_ in segs]
        out["vias"] += [{"net": net, "at": list(c)} for c in vias]
    json.dump(out, open(sys.argv[3], "w"), indent=0)
    print(json.dumps({"pairs": len(pairs), "tracks": len(out["tracks"]), "vias": len(out["vias"]),
                      "failed": len(out["failed"])}))


def eco():
    """ECO for pairs the normal rounds leave open: route each one against the fixed copper only
    (pads, zones, locked fan-outs and stubs), then name the nets whose earlier (unlocked) routing
    the new path crosses. layout/route.py deletes those nets' unlocked copper, adds these routes,
    and lets the normal rounds re-route the deleted nets around them.

        python3 layout/gridroute.py --eco <geom.json> <drc.json> <out.json>
    """
    geom = json.load(open(sys.argv[2]))
    drc = json.load(open(sys.argv[3]))
    configure(geom)
    soft_tracks = [t for t in geom["tracks"] if not t.get("locked", True)]
    soft_vias = [v for v in geom["vias"] if not v.get("locked", True) and v["net"] != "<npth>"]
    fixed = dict(geom)
    fixed["tracks"] = [t for t in geom["tracks"] if t.get("locked", True)]
    fixed["vias"] = [v for v in geom["vias"] if v.get("locked", True) or v["net"] == "<npth>"]
    soft_drills = {(round(v["at"][0], 3), round(v["at"][1], 3)) for v in soft_vias}
    fixed["drills"] = [d_ for d_ in geom["drills"] if (round(d_[0], 3), round(d_[1], 3)) not in soft_drills]
    R = Router(fixed)
    # the earlier routing becomes "routes" of the router (one per net), so the ECO path can treat it
    # as a cost (soft mode) and cross as little of it as possible
    by_net = {}
    for t in soft_tracks:
        by_net.setdefault(t["net"], ([], []))[0].append((t["layer"], tuple(t["a"]), tuple(t["b"]), t["w"]))
    for v in soft_vias:
        by_net.setdefault(v["net"], ([], []))[1].append(tuple(v["at"]))
    rid_of = {}
    for k, (n, (segs, vias)) in enumerate(sorted(by_net.items())):
        rid_of[n] = 20_000 + k
        R.add_copper(n, segs, vias, rid=rid_of[n])
    tht = {(round(d_[0], 3), round(d_[1], 3)) for d_ in geom["drills"]}
    out = {"tracks": [], "vias": [], "failed": [], "rip_nets": [], "rip_items": []}
    for k, u in enumerate(drc["unconnected_items"]):
        it = u["items"]
        net = re.search(r"\[([^\]]+)\]", it[0]["description"]).group(1)
        ends = []
        for e in it:
            p = (e["pos"]["x"], e["pos"]["y"])
            desc = e["description"]
            if (round(p[0], 3), round(p[1], 3)) in tht or "F.Cu - B.Cu" in desc:
                ls = LAYERS
            elif "on B.Cu" in desc:
                ls = ("B",)
            elif "on In2.Cu" in desc:
                ls = ("In2",)
            elif "on In3.Cu" in desc:
                ls = ("In3",)
            else:
                ls = ("F",)
            ends.append((p, ls))
        (a, la), (b, lb) = ends
        res = None
        for w_, m_ in [(POWER.get(net, SIG_W), m) for m in (3.0, 10.0, 30.0)] + \
                [(NARROW[net], m) for m in (10.0, 30.0) if net in NARROW]:
            res, why = R.route(net, a, b, la, lb, w_, m_, soft=True)
            if res:
                break
        if not res:
            out["failed"].append({"net": net, "a": a, "b": b})
            continue
        segs, vias = res
        body = [LineString([p, q]).buffer(w__ / 2 + 0.25) for _, p, q, w__ in segs] + \
               [Point(c).buffer(VIA_R + 0.25) for c in vias]
        hit = []
        for n2, rid in rid_of.items():
            if n2 == net or rid not in R.routes:
                continue
            s2, v2 = R.routes[rid][1], R.routes[rid][2]
            items = [("t", l2, p, q, w2, LineString([p, q]).buffer(w2 / 2)) for l2, p, q, w2 in s2] + \
                    [("v", None, c, c, 2 * VIA_R, Point(c).buffer(VIA_R)) for c in v2]
            crossing = [it for it in items if any(it[5].intersects(g1) for g1 in body)]
            if crossing:
                hit.append(n2)
                # only the crossed pieces are deleted; KiCad then reports just those broken links
                out["rip_items"] += [{"net": n2, "kind": it[0], "layer": it[1], "a": list(it[2]), "b": list(it[3])}
                                     for it in crossing]
        for n2 in hit:
            R.remove_route(rid_of[n2])
        R.add_copper(net, segs, vias, rid=10_000 + k)
        out["rip_nets"] = sorted(set(out["rip_nets"]) | set(hit))   # for the log
        out["tracks"] += [{"net": net, "layer": l, "a": list(p), "b": list(q), "w": w_} for l, p, q, w_ in segs]
        out["vias"] += [{"net": net, "at": list(c)} for c in vias]
        print(f"eco {net}: routed, rips {hit}", flush=True)
    json.dump(out, open(sys.argv[4], "w"), indent=0)
    print(json.dumps({"eco_routed": len(out["tracks"]) > 0, "rip_nets": out["rip_nets"], "failed": len(out["failed"])}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--eco":
        eco()
    else:
        main()
