#!/usr/bin/env python3
"""Stage 37: deterministic post-route track-geometry cleanup of native-21's routed copper (DECISIONS 43, "Fix (planned)").

    python3 native-21/layout/track_cleanup21.py COPPER.json BOARD-all-copper.json.gz [--out OUT.json] [--report R.json]

COPPER.json is a routed layout/copper.json; BOARD-all-copper.json.gz is tools/export_power_copper.py's export of the board
built from exactly that copper (the chain's <tag>-all-copper.json.gz). The export is the obstacle model: real pad shapes
per layer, the zone fills as KiCad filled them, the board outline. The tool refuses an export whose tracks are not the
copper's segments. Without --out it only reports.

The pass, in this order, each step repeated until it accepts nothing more, then the four steps again until nothing changes
(so a second run on its own output, built and exported again, changes nothing):
  1. fold-backs (0 deg corners, gates/track_geometry.py). A free fold (nothing at the tip) is redundant copper: the tip
     goes and the track runs straight between its two neighbours. A fold whose tip is on a pad or via is a duplicated
     segment: the overlapping copy goes and the other track starts where the overlap ends (a T junction; the copper is
     the same, less the duplicate).
  2. acute corners (< 90 deg) are opened, 3. right angles are mitred. Both replace the corner by the octilinear tangent
     polygon of a circle tangent to the two arms (turns of 45 deg between octilinear arms: a right angle becomes 2 x 135,
     a 45 deg acute corner 3 x 135). The radius is tried from 5.1 x the track width (a right-angle mitre leg of 3 x the
     width, at least 0.5 mm) down to the width itself, so the inner edge of the new copper always has real 135 deg
     corners; it stops at half an arm when the arm's far end is another corner.
  4. any-angle segments are replaced by an octilinear dogleg (one diagonal and one orthogonal piece, a 135 deg bend).
Corners whose tip is on a pad or via of the net (the pad / via copper, not a track corner, is there) are not moved.

An edit is kept only if every check holds; otherwise the next smaller candidate is tried, and the corner is left as it is
with the first failing reason of the smallest candidate (the report counts them by reason and layer):
  - net:        res_a (RES_A creepage copper, rules21.RES_A_NETS) and the OCP sense nets are never edited;
  - spine:      no removed or added segment touches the SELV-spine lock region (selv_spine_lock.json), and no zone fill
                inside it can change;
  - clearance:  the added copper (new minus old) keeps rules21.clearance_on + 0.02 mm from every other-net track, via,
                pad and zone fill on its layer (so no fill has to retreat), 0.3 mm from holes, 1.0 mm from fiducials,
                0.5 mm from the board edge, the 8.0 mm plan-view barrier (rules21.barrier) on every layer, and stays
                out of the protected island / Kelvin pours (incr21);
  - barrier:    the added copper is no closer to the other side of the barrier (plan view) or, on F / B, of the RES_A
                12.6 mm pair than the copper it replaces, unless it is >= 25 mm away (the barrier and RES_A outer gates
                can only stay equal or improve);
  - fill:       where removed copper lets another net's fill grow, the growth area is >= 25 mm from the other side of
                that fill's barrier and outside the spine region;
  - connect:    the net's connectivity (KiCad's anchor rule: an item end inside another item; pads, vias and zone fills
                as fixed items) partitions the pads, vias and fills exactly as before, with no new floating or dangling
                track end;
  - metric:     on the net and layer, no geometry count gets worse (fold-backs, acute, right angles, any-angle mm) and the
                targeted one improves.
Pads, vias, zones and parts never move; track widths never change (a mitre between two widths is skipped). KiCad DRC in
the chain stays the authority. Output: COPPER.json with the edited polylines, everything else byte-for-byte as loaded.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "gates"))
import layers21  # noqa: E402
import rules21  # noqa: E402
import track_geometry  # noqa: E402

CU, OUTER = layers21.CU, layers21.OUTER
MARGIN = 0.02            # mm over every rule
HORIZON = 25.0           # mm: copper this far from the other side of the barrier cannot move any barrier minimum
HOLE_CLEAR, FIDUCIAL_CLEAR, EDGE_CLEAR = 0.3, 1.0, 0.5
MOUNT_R = 3.7            # mounting-hole washer ring (board_only21.json silk rings r 3.6)
H1_HOT_MM = 19.0         # metal hole H1 (PE): HOT copper keeps its 18.5 mm (board_only21.json hot_mm)
LOCKED_NETS = set(rules21.RES_A_NETS) | {"ocp_kelvin_p", "ocp_kelvin_n", "ocp_node", "ocp_thresh"}
PROTECTED = lambda net, layer: (net in ("n_ha", "n_hb") and layer in ("B.Cu", layers21.PLANE_ROLE.get(net))) or \
    net in ("ocp_kelvin_p", "ocp_kelvin_n")          # incr21: pours other nets' tracks may not enter
EPS = 1e-4
ANG_TOL = 0.5            # deg, as track_geometry
MIN_PIECE = 0.05         # mm: shortest new segment
LOOSE_PIECE = 1.0        # mm: shortest dogleg piece at a loose track end (loose_end)
STEPS = ("fold", "acute", "right", "any")
SEVERITY = ("fold_backs", "acute_corners", "right_angle_corners")
ANY_TRADE = 2.0         # mm of any-angle track a corner fix may add
GROWTH_BARRIER = 11.0    # mm: a fill may grow only this far from the other side of the barrier (gate minima 8.0x)
SPINE_LOCK = HERE / "selv_spine_lock.json"


def rnd(p):
    return [round(p[0], 4), round(p[1], 4)]


def k3(p):
    return (round(p[0], 3), round(p[1], 3))


def unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def angle_at(v, a, b):
    u, w = (a[0] - v[0], a[1] - v[1]), (b[0] - v[0], b[1] - v[1])
    nu, nw = math.hypot(*u), math.hypot(*w)
    c = (u[0] * w[0] + u[1] * w[1]) / (nu * nw)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def octilinear(a, b):
    r = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 45.0
    return not (ANG_TOL <= r <= 45.0 - ANG_TOL)


def classify(ang):
    if abs(ang - 90.0) < ANG_TOL:
        return "right"
    if ang < ANG_TOL:
        return "fold"
    if ang < 90.0 - ANG_TOL:
        return "acute"
    return None


_SHAPES = {}


def seg_shape(a, b, w):
    """A track segment's copper (round ends, as KiCad draws it); cached."""
    key = (a[0], a[1], b[0], b[1], w)
    g = _SHAPES.get(key)
    if g is None:
        g = Point(a).buffer(w / 2) if math.dist(a, b) < 1e-9 else LineString([a, b]).buffer(w / 2)
        _SHAPES[key] = g
    return g


def seg_dist(p, a, b):
    """Distance from point p to segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def tangent_path(v, a, b, radius):
    """Points replacing corner v of path a -> v -> b: the tangent polygon of the circle of `radius` tangent to both arms,
    its sides along every octilinear direction strictly between the two arm directions (so each turn is <= 45 deg)."""
    u1, u2 = unit(v, a), unit(v, b)
    th = math.radians(angle_at(v, a, b))
    a_in = math.atan2(-u1[1], -u1[0])                  # travel direction into v
    cross = (-u1[0]) * u2[1] - (-u1[1]) * u2[0]
    s = 1.0 if cross > 0 else -1.0                     # left (+) or right (-) turn
    phi = math.pi - th                                 # turn angle
    dirs = [a_in]
    q = math.pi / 4
    k = math.floor(a_in / q) if s > 0 else math.ceil(a_in / q)
    while True:
        k += s
        ang = k * q
        if s * (ang - a_in) >= phi - math.radians(ANG_TOL):
            break
        if s * (ang - a_in) > math.radians(ANG_TOL):
            dirs.append(ang)
    dirs.append(a_in + s * phi)
    bis = ((u1[0] + u2[0]), (u1[1] + u2[1]))
    nb = math.hypot(*bis)
    bis = (bis[0] / nb, bis[1] / nb)
    dc = radius / math.sin(th / 2)
    c = (v[0] + dc * bis[0], v[1] + dc * bis[1])

    def line(t):                                       # tangent line with direction t: n . x = n . c - R (n points to c)
        d = (math.cos(t), math.sin(t))
        n = (-d[1] * s, d[0] * s)
        return n, n[0] * c[0] + n[1] * c[1] - radius

    pts = []
    for t0, t1 in zip(dirs, dirs[1:]):
        (n0, c0), (n1, c1) = line(t0), line(t1)
        det = n0[0] * n1[1] - n0[1] * n1[0]
        pts.append(((c0 * n1[1] - c1 * n0[1]) / det, (n0[0] * c1 - n1[0] * c0) / det))
    return pts


class Board:
    """The routed copper (tracks edited in place) and the static obstacle model from the built board's export."""

    def __init__(self, copper, export, pads, spine=None, mounts=()):
        self.copper = copper
        self.tracks = copper["tracks"]
        self.vias = copper["vias"]
        self.pxy = {}
        for p in pads:
            self.pxy.setdefault(f"{p['ref']}.{p['pad']}", (p["x"], p["y"]))
        self.spine = box(*spine) if spine else None
        prims = export["primitives"]
        self.outline = Polygon(export["outline"]["shell"], export["outline"].get("holes") or []).buffer(-EDGE_CLEAR - MARGIN,
                                                                                                         join_style=2)
        self.static = {lay: [] for lay in CU}     # (geom, net, kind) per layer
        self.fills = {lay: [] for lay in CU}      # (poly, net, idx)
        self.pads = defaultdict(list)             # net -> [(layer, poly, centre, id)]
        for i, p in enumerate(prims):
            if p["kind"] == "pad":
                poly = Polygon(p["shell"], p.get("holes") or []).buffer(0)
                kind = "fiducial" if not p["net"] else "pad"
                self.static[p["layer"]].append((poly, p["net"], kind))
                if p["net"]:
                    self.pads[p["net"]].append((p["layer"], poly, tuple(p["centre"]), f"pad{i}"))
            elif p["kind"] == "zone":
                poly = Polygon(p["shell"], p.get("holes") or []).buffer(0)
                self.static[p["layer"]].append((poly, p["net"], "fill"))
                self.fills[p["layer"]].append((poly, p["net"], f"fill{i}"))
        for v in self.vias:
            g = Point(v["at"]).buffer(v["size"] / 2)
            for lay in CU:
                self.static[lay].append((g, v["net"], "via"))
        for p in pads:
            if p["npth"]:
                g = box(*p["box"])
                for lay in CU:
                    self.static[lay].append((g, "", "hole"))
        self.h1 = None
        for m in mounts:
            g = Point(m["at"]).buffer(MOUNT_R)
            for lay in CU:
                self.static[lay].append((g, "", "hole"))
            if m.get("kind") == "metal":
                self.h1 = Point(m["at"]).buffer(H1_HOT_MM)
        for z in copper.get("zones", []):
            if PROTECTED(z["net"], z["layer"]):
                self.static[z["layer"]].append((Polygon(z["outline"], z.get("holes") or []).buffer(0), z["net"], "protected"))
        self.stree = {lay: STRtree([g for g, _, _ in self.static[lay]]) for lay in CU}
        self.ftree = {lay: STRtree([g for g, _, _ in self.fills[lay]]) if self.fills[lay] else None for lay in CU}
        self._ttree = {}
        self._part, self._vg, self._cst, self._ctt = {}, {}, {}, {}
        self.via_at = defaultdict(list)
        for v in self.vias:
            self.via_at[v["net"]].append(v)

    # -- tracks
    def xy(self, q):
        return self.pxy[q] if isinstance(q, str) else (q[0], q[1])

    def segs(self, ti, pts=None):
        """Segments of polyline ti (its current points, or `pts`); none for a deleted polyline."""
        pts = self.tracks[ti]["points"] if pts is None else pts
        if pts is None:
            return []
        P = [self.xy(q) for q in pts]
        return [(P[i], P[i + 1]) for i in range(len(P) - 1)]

    def track_tree(self, lay):
        if lay not in self._ttree:
            items = []
            for ti, t in enumerate(self.tracks):
                if t["layer"] == lay:
                    for a, b in self.segs(ti):
                        items.append((seg_shape(a, b, t["width"]), t["net"], ti))
            self._ttree[lay] = (STRtree([g for g, _, _ in items]) if items else None, items)
        return self._ttree[lay]

    def dirty(self, lay):
        self._ttree.pop(lay, None)
        self._ctt.clear()

    def vertices(self, net, layer, override=None):
        """{k3(v): [(ti, j, nb)]}: every polyline point j with its neighbour index nb, for the net on the layer."""
        vert = defaultdict(list)
        for ti, t in enumerate(self.tracks):
            if t["net"] != net or t["layer"] != layer:
                continue
            pts = override.get(ti, t["points"]) if override else t["points"]
            if pts is None:
                continue
            P = [self.xy(q) for q in pts]
            for j in range(len(P) - 1):
                if math.dist(P[j], P[j + 1]) < 1e-6:
                    continue
                vert[k3(P[j])].append((ti, j, j + 1))
                vert[k3(P[j + 1])].append((ti, j + 1, j))
        return vert

    def measure(self, net, layer, override=None):
        prims = []
        for ti, t in enumerate(self.tracks):
            if t["net"] != net or t["layer"] != layer:
                continue
            pts = override.get(ti, t["points"]) if override else t["points"]
            if pts is None:
                continue
            for a, b in self.segs(ti, pts):
                prims.append({"kind": "track", "net": net, "layer": layer, "start": a, "end": b})
        res = track_geometry.measure(prims)
        res["any_mm"] = sum(math.dist(p["start"], p["end"]) for p in prims
                            if math.dist(p["start"], p["end"]) >= 1e-6 and not octilinear(p["start"], p["end"]))
        return res

    # -- what sits at a vertex
    def at_fixed(self, net, layer, v, pts_refs):
        if any(isinstance(q, str) for q in pts_refs):
            return "pad"
        pt = Point(v)
        for lay, poly, _, _ in self.pads.get(net, []):
            if lay == layer and poly.buffer(EPS).contains(pt):
                return "pad"
        for w in self.via_at.get(net, []):
            if math.dist(w["at"], v) <= w["size"] / 2 + EPS:
                return "via"
        return None

    # -- checks
    def max_need(self, net, layer):
        dom = rules21.domain(net)
        need = max(FIDUCIAL_CLEAR, rules21.FLOOR, HOLE_CLEAR)
        if dom == "HOT":
            need = max(need, rules21.BARRIER)
        elif dom in ("SELV", "PE"):
            need = max(need, rules21.BARRIER, rules21.RES_A_CREEPAGE if layer in OUTER else 0.0)
        return need

    def clearance_fail(self, net, layer, geom):
        dom = rules21.domain(net)
        if not self.outline.contains(geom):
            return "clearance: board edge"
        d = self.max_need(net, layer) + MARGIN
        items = self.static[layer]
        for i in sorted(self.stree[layer].query(geom, predicate="dwithin", distance=d)):
            g, other, kind = items[i]
            if kind == "hole":
                need = HOLE_CLEAR
            elif kind == "fiducial":
                need = FIDUCIAL_CLEAR
            elif other == net:
                continue
            else:
                need = rules21.clearance_on(net, other, layer)
            if need + MARGIN >= d or g.distance(geom) < need + MARGIN:
                return f"clearance: {kind} {other or ''}".rstrip()
        tree, titems = self.track_tree(layer)
        if tree is not None:
            for i in sorted(tree.query(geom, predicate="dwithin", distance=d)):
                g, other, _ = titems[i]
                if other == net:
                    continue
                need = rules21.clearance_on(net, other, layer)
                if need + MARGIN >= d or g.distance(geom) < need + MARGIN:
                    return f"clearance: track {other}"
        if dom in ("SELV", "PE", "HOT"):
            if self.barrier_dist(net, geom, rules21.BARRIER + 0.5) < rules21.BARRIER + MARGIN:
                return "clearance: barrier"
        if dom == "HOT" and self.h1 is not None and self.h1.intersects(geom):
            return "clearance: H1 metal hole"
        return None

    def cls_tree(self, cls, layer=None):
        """STRtree of every copper item of a class ('HOT', 'SELVPE', 'RESA') with a net, on one layer or (None) all;
        static items once, tracks rebuilt after edits."""
        key = (cls, layer)
        match = {"HOT": lambda n: rules21.domain(n) == "HOT", "SELVPE": lambda n: rules21.domain(n) in ("SELV", "PE"),
                 "RESA": lambda n: n in rules21.RES_A_NETS}[cls]
        if key not in self._cst:
            lays = CU if layer is None else (layer,)
            g = [x for lay in lays for x, n, k in self.static[lay] if n and k in ("pad", "fill", "via") and match(n)]
            self._cst[key] = STRtree(g) if g else None
        if key not in self._ctt:
            lays = CU if layer is None else (layer,)
            g = [x for lay in lays for x, n, _ in self.track_tree(lay)[1] if match(n)]
            self._ctt[key] = STRtree(g) if g else None
        return self._cst[key], self._ctt[key]

    def _nearest(self, trees, geom, reach):
        best = reach
        for tr in trees:
            if tr is None:
                continue
            idx, dist = tr.query_nearest(geom, max_distance=reach, return_distance=True)
            if len(dist):
                best = min(best, float(min(dist)))
        return best

    def barrier_dist(self, net, geom, reach=HORIZON):
        """Plan-view distance (every layer) from geom to copper across the barrier from `net`, capped at reach."""
        dom = rules21.domain(net)
        cls = "HOT" if dom in ("SELV", "PE") else "SELVPE" if dom == "HOT" else None
        return reach if cls is None else self._nearest(self.cls_tree(cls), geom, reach)

    def res_a_dist(self, net, layer, geom, reach=HORIZON):
        """Same-layer distance on F / B from geom to the RES_A 12.6 mm counterpart of `net`, capped at reach."""
        if layer not in OUTER:
            return reach
        if net in rules21.RES_A_NETS:
            cls = "SELVPE"
        elif rules21.domain(net) in ("SELV", "PE"):
            cls = "RESA"
        else:
            return reach
        return self._nearest(self.cls_tree(cls, layer), geom, reach)

    def fill_growth_fail(self, net, layer, removed):
        """Removed copper lets an adjacent other-net fill grow: allowed only away from the barrier and the spine."""
        if removed.is_empty or self.ftree[layer] is None:
            return None
        for i in sorted(self.ftree[layer].query(removed, predicate="dwithin", distance=self.max_need(net, layer) + 0.05)):
            poly, other, _ = self.fills[layer][i]
            if other == net:
                continue
            c = rules21.clearance_on(net, other, layer)
            if poly.distance(removed) > c + 0.05:
                continue
            grow = removed.buffer(c + 0.05)
            if self.spine is not None and grow.intersects(self.spine):
                return "spine: fill growth"
            if rules21.domain(other) in ("SELV", "PE", "HOT") and self.barrier_dist(other, grow) < GROWTH_BARRIER:
                return "fill: growth near barrier"
            if self.res_a_dist(other, layer, grow) < HORIZON:
                return "fill: growth near RES_A pair"
        return None

    # -- connectivity (KiCad's anchor rule)
    def partition(self, net, override=None):
        """(pad / via / fill partition, floating track groups, dangling track ends) of the net's copper, joined by KiCad's
        anchor rule: a track end (or a via / pad centre) inside another item on a shared layer; pads and vias meet a fill
        when they touch it. Without an override the result is cached until the net is edited."""
        if override is None and net in self._part:
            return self._part[net]
        items = []      # (layers, geom, anchors, fixed_id or None, kind, seg (a, b, half-width) or None)
        for ti, t in enumerate(self.tracks):
            if t["net"] != net:
                continue
            pts = override.get(ti, t["points"]) if override else t["points"]
            if pts is None:
                continue
            for a, b in self.segs(ti, pts):
                items.append(((t["layer"],), seg_shape(a, b, t["width"]), (a, b), None, "seg", (a, b, t["width"] / 2)))
        for w in self.via_at.get(net, []):
            c = tuple(w["at"])
            items.append((CU, self._via_geom(w), (c,), f"via{c}", "via", (c, c, w["size"] / 2)))
        for lay, poly, centre, pid in self.pads.get(net, []):
            items.append(((lay,), poly, (centre,), pid, "pad", None))
        for lay in CU:
            for poly, n, fid in self.fills[lay]:
                if n == net:
                    items.append(((lay,), poly, (), fid, "fill", None))
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def inside(pt, it):              # anchor pt inside item it
            if it[5] is not None:        # segment or via: distance to its axis
                return seg_dist(pt, it[5][0], it[5][1]) <= it[5][2] + EPS
            return it[1].distance(Point(pt)) <= EPS
        tree = STRtree([it[1] for it in items])
        end_hits = defaultdict(set)
        for i, j in zip(*tree.query([it[1] for it in items], predicate="dwithin", distance=EPS)):
            if j <= i:
                continue
            I, J = items[i], items[j]
            if not set(I[0]) & set(J[0]):
                continue
            kinds = {I[4], J[4]}
            if "fill" in kinds and kinds & {"pad", "via"} or kinds <= {"pad", "via"} and len(kinds) > 1 or kinds == {"pad"}:
                hit = True               # dwithin EPS: they touch
            else:
                hit = False
                for (X, Y, k) in ((I, J, i), (J, I, j)):
                    for e, a in enumerate(X[2]):
                        if inside(a, Y):
                            hit = True
                            end_hits[k].add(e)
            if hit:
                parent[find(i)] = find(j)
        comps = defaultdict(set)
        for i, it in enumerate(items):
            if it[3] is not None:
                comps[find(i)].add(it[3])
        floating = len({find(i) for i in range(len(items)) if find(i) not in comps})
        dangling = sum(1 for i, it in enumerate(items) if it[4] == "seg" for e in (0, 1) if e not in end_hits[i])
        res = (frozenset(frozenset(c) for c in comps.values()), floating, dangling)
        if override is None:
            self._part[net] = res
        return res

    def _via_geom(self, w):
        key = (tuple(w["at"]), w["size"])
        if key not in self._vg:
            self._vg[key] = Point(w["at"]).buffer(w["size"] / 2)
        return self._vg[key]

    # -- one edit
    def evaluate(self, net, layer, override, step, kind_old):
        """None if the edit (override: ti -> new points or None) passes every check, else the first failing reason."""
        if net in LOCKED_NETS:
            return "net: locked (RES_A / OCP sense)"
        old, new = Counter(), Counter()
        for ti, pts in override.items():
            t = self.tracks[ti]
            for a, b in self.segs(ti):
                old[(k3(a), k3(b), t["width"]) if k3(a) <= k3(b) else (k3(b), k3(a), t["width"])] += 1
            if pts is not None:
                for a, b in self.segs(ti, pts):
                    new[(k3(a), k3(b), t["width"]) if k3(a) <= k3(b) else (k3(b), k3(a), t["width"])] += 1
        removed_s, added_s = old - new, new - old
        if self.spine is not None:
            for a, b, w in list(removed_s) + list(added_s):
                if seg_shape(a, b, w).intersects(self.spine):
                    return "spine: segment in the lock region"
        g_old = unary_union([seg_shape(a, b, w) for a, b, w in removed_s]) if removed_s else Polygon()
        g_new = unary_union([seg_shape(a, b, w) for a, b, w in added_s]) if added_s else Polygon()
        added = g_new.difference(g_old.buffer(1e-3)) if not g_new.is_empty else Polygon()
        removed = g_old.difference(g_new.buffer(1e-3)) if not g_old.is_empty else Polygon()
        if added.area > 1e-7:
            why = self.clearance_fail(net, layer, added)
            if why:
                return why
            if rules21.domain(net) in ("SELV", "PE", "HOT"):
                d_new = self.barrier_dist(net, added)
                if d_new < HORIZON and d_new < self.barrier_dist(net, g_old) - 1e-4:
                    return "barrier: closer to the other side"
            d_new = self.res_a_dist(net, layer, added)
            if d_new < HORIZON and d_new < self.res_a_dist(net, layer, g_old) - 1e-4:
                return "barrier: closer to the RES_A pair"
        if removed.area > 1e-7:
            why = self.fill_growth_fail(net, layer, removed)
            if why:
                return why
        before, after = self.measure(net, layer), self.measure(net, layer, override)
        # severity order: fold-backs, acute corners, right angles, then any-angle length. An edit must make the tuple
        # strictly better and improve what its step targets: an acute corner may become a right angle, and a corner fix
        # may add up to ANY_TRADE mm of any-angle track
        tb = tuple(before[k] for k in SEVERITY)
        ta = tuple(after[k] for k in SEVERITY)
        if ta > tb:
            return f"metric: {next(k for k, x, y in zip(SEVERITY, ta, tb) if x != y)} would rise"
        d_any = after["any_mm"] - before["any_mm"]
        if ta == tb and not d_any < -0.05:
            return "metric: no improvement"
        if d_any > ANY_TRADE:
            return "metric: any-angle length would rise"
        target = {"fold": "fold_backs", "acute": "acute_corners", "right": "right_angle_corners"}.get(step)
        if target and not after[target] < before[target]:
            return "metric: no improvement"
        p0, p1 = self.partition(net), self.partition(net, override)
        if p0[0] != p1[0]:
            return "connect: partition changes"
        if p1[1] > p0[1] or p1[2] > p0[2]:
            return "connect: floating or dangling copper"
        return None

    def apply(self, override):
        """Deleted polylines keep their slot (points None) until run() ends, so track indices stay valid."""
        for ti, pts in override.items():
            self.tracks[ti]["points"] = pts
            self.dirty(self.tracks[ti]["layer"])
            self._part.pop(self.tracks[ti]["net"], None)


def replace_vertex(board, inc1, inc2, seq):
    """Override for path A -> V -> B (inc1 on the A side, inc2 on the B side) with V replaced by `seq` (points A -> B).
    Junction vertices (V the shared end of two polylines) keep both polylines: the first ends at seq[-1], the second
    starts there. Returns None for shapes it does not handle (a polyline closing on itself)."""
    (t1, j1, nb1), (t2, j2, nb2) = inc1, inc2
    seq = [rnd(p) for p in seq]
    if t1 == t2 and j1 == j2:
        P = list(board.tracks[t1]["points"])
        ins = seq if nb1 == j1 - 1 else list(reversed(seq))
        return {t1: P[:j1] + ins + P[j1 + 1:]}
    if t1 == t2:
        return None
    P1, P2 = list(board.tracks[t1]["points"]), list(board.tracks[t2]["points"])
    if j1 not in (0, len(P1) - 1) or j2 not in (0, len(P2) - 1):
        return None
    if j1 == len(P1) - 1:
        P1 = P1[:-1] + seq
    else:
        P1 = list(reversed(seq)) + P1[1:]
    if j2 == 0:
        P2 = [seq[-1]] + P2[1:]
    else:
        P2 = P2[:-1] + [seq[-1]]
    return {t1: P1, t2: P2}


def drop_fold(board, inc1, inc2, at_fixed):
    """Fold-back at V (A, V, B collinear, A and B on the same side of V). Free tip: A -> B straight, on the polyline whose
    segment covers it. Tip on a pad / via: the shorter, covered segment's polyline starts at the overlap's end instead."""
    (t1, j1, nb1), (t2, j2, nb2) = inc1, inc2
    T = board.tracks
    if t1 == t2:
        if j1 != j2:
            return None
        P = list(T[t1]["points"])
        a, b = board.xy(P[nb1]), board.xy(P[nb2])
        if at_fixed:
            return None
        lo, hi = min(nb1, nb2), max(nb1, nb2)
        Q = P[:j1] + P[j1 + 1:]
        if math.dist(a, b) < 1e-3:
            Q = P[:lo] + P[hi:]
        return {t1: Q}
    P1, P2 = list(T[t1]["points"]), list(T[t2]["points"])
    if j1 not in (0, len(P1) - 1) or j2 not in (0, len(P2) - 1):
        return None
    if j1 == 0:
        P1 = list(reversed(P1))           # now V is last
    if j2 != 0:
        P2 = list(reversed(P2))           # now V is first
    v, a, b = board.xy(P1[-1]), board.xy(P1[-2]), board.xy(P2[1])
    la, lb = math.dist(v, a), math.dist(v, b)
    w1, w2 = T[t1]["width"], T[t2]["width"]
    if at_fixed:
        # duplicate overlap at a pad / via: the shorter arm's copper lies on the longer arm; it goes
        if lb <= la + 1e-3 and w2 <= w1:
            n1 = P1 if math.dist(a, b) < 1e-3 else P1[:-1] + [P2[1], P1[-1]]
            n2 = P2[1:]
        elif la < lb and w1 <= w2:
            n2 = P2 if math.dist(a, b) < 1e-3 else [P2[0], P1[-2]] + P2[1:]
            n1 = P1[:-1]
        else:
            return None
    else:
        if math.dist(a, b) < 1e-3:
            n1, n2 = P1[:-1], P2[1:]
        elif lb <= la:                    # B lies on A-V: t1's copper covers A-B
            n1, n2 = P1[:-1] + [P2[1]], P2[1:]
            if w2 > w1:
                return None
        else:                             # A lies on V-B: t2's copper covers A-B
            n1, n2 = P1[:-1], [P1[-2]] + P2[1:]
            if w1 > w2:
                return None
    out = {}
    for ti, n, rev in ((t1, n1, j1 == 0), (t2, n2, j2 != 0)):
        n = list(reversed(n)) if rev else n
        out[ti] = n if len(n) >= 2 else None
    return out


def candidates_corner(board, net, layer, v, inc1, inc2, kind):
    t = board.tracks
    w1, w2 = t[inc1[0]]["width"], t[inc2[0]]["width"]
    if w2 > w1 + 1e-9:                   # mixed widths (a junction of two polylines): the mitre belongs to the wider one
        inc1, inc2, w1, w2 = inc2, inc1, w2, w1
    w = w1
    a = board.xy(t[inc1[0]]["points"][inc1[2]])
    b = board.xy(t[inc2[0]]["points"][inc2[2]])
    vert = board.vertices(net, layer)

    def room(far, arm):
        # half the arm when its far end is another corner (its own mitre takes the other half), else all but a piece
        e = vert.get(k3(far), [])
        if len(e) == 2 and classify(angle_at(far, *[board.xy(t[x[0]]["points"][x[2]]) for x in e])):
            return arm / 2
        return arm - max(MIN_PIECE, w / 2)
    la, lb = math.dist(v, a), math.dist(v, b)
    ra, rb = room(a, la), room(b, lb)
    r0 = max(3 * w, 0.5) / (1 - math.tan(math.pi / 8))
    radii = [r0 * f for f in (1.0, 0.75, 0.55, 0.4, 0.3, 0.22)]
    radii = [r for r in radii if r >= w - 1e-9] or [w]
    if radii[-1] > w:
        radii.append(w)
    out = []
    for r in radii:
        seq = tangent_path(v, a, b, r)
        da, db = math.dist(v, seq[0]), math.dist(v, seq[-1])
        cap = 2.5
        if max(da, db) > cap:
            continue
        if da > ra or db > rb:
            continue
        if any(math.dist(p, q) < MIN_PIECE for p, q in zip(seq, seq[1:])):
            continue
        ov = replace_vertex(board, inc1, inc2, seq)
        if ov:
            out.append(ov)
    if not out:
        return "room: arms too short for a mitre of radius >= track width", []
    return None, out


def arm(board, inc):
    t = board.tracks[inc[0]]
    return board.xy(t["points"][inc[1]]), board.xy(t["points"][inc[2]]), t["width"]


def track_len(board, inc):
    v, a, _ = arm(board, inc)
    return math.dist(v, a)


def wedge_covered(board, net, layer, v, inc1, inc2):
    """True when the inner corner of the two arms (where their inner edges cross) lies inside the pad / via copper at
    the tip: there is no copper corner there, only the pad or via."""
    _, a, w1 = arm(board, inc1)
    _, b, w2 = arm(board, inc2)
    u1, u2 = unit(v, a), unit(v, b)
    cr = u1[0] * u2[1] - u1[1] * u2[0]
    if abs(cr) < 1e-9:
        return False
    n1 = (-u1[1], u1[0]) if cr > 0 else (u1[1], -u1[0])          # normal of arm 1 towards arm 2
    n2 = (-u2[1], u2[0]) if cr < 0 else (u2[1], -u2[0])          # normal of arm 2 towards arm 1
    p1 = (v[0] + n1[0] * w1 / 2, v[1] + n1[1] * w1 / 2)
    p2 = (v[0] + n2[0] * w2 / 2, v[1] + n2[1] * w2 / 2)
    det = u1[0] * (-u2[1]) - u1[1] * (-u2[0])
    t = ((p2[0] - p1[0]) * (-u2[1]) - (p2[1] - p1[1]) * (-u2[0])) / det
    apex = Point(p1[0] + t * u1[0], p1[1] + t * u1[1])
    for lay, poly, _, _ in board.pads.get(net, []):
        if lay == layer and poly.buffer(EPS).contains(apex):
            return True
    return any(math.dist(w["at"], (apex.x, apex.y)) <= w["size"] / 2 + EPS for w in board.via_at.get(net, []))


def merge_trunk(board, inc_t, inc_b):
    """Acute corner at a pad / via tip: the branch arm (inc_b) leaves the trunk arm (inc_t) square, at the foot M of its
    far end on the trunk, instead of at the tip; the trunk keeps the tip. If the far end lies within 0.05 mm of the trunk
    line the branch simply starts there (its end is inside the trunk's copper). Junctions of two polylines only."""
    (tt, jt, nt), (tb, jb, nb) = inc_t, inc_b
    if tt == tb:
        return None
    T = board.tracks
    Pt, Pb = list(T[tt]["points"]), list(T[tb]["points"])
    if jt not in (0, len(Pt) - 1) or jb not in (0, len(Pb) - 1) or len(Pt) < 2 or len(Pb) < 2:
        return None
    rt, rb = jt == 0, jb != 0
    if rt:
        Pt.reverse()          # tip last
    if rb:
        Pb.reverse()          # tip first
    v, a, b = board.xy(Pt[-1]), board.xy(Pt[-2]), board.xy(Pb[1])
    la, lb = math.dist(v, a), math.dist(v, b)
    ua = unit(v, a)
    along = (b[0] - v[0]) * ua[0] + (b[1] - v[1]) * ua[1]
    h = abs((b[0] - v[0]) * ua[1] - (b[1] - v[1]) * ua[0])
    if along <= MIN_PIECE or along >= la - MIN_PIECE:
        return None
    m = rnd((v[0] + along * ua[0], v[1] + along * ua[1]))
    if h < MIN_PIECE:
        if h > T[tt]["width"] / 2 - 0.01:
            return None
        nt_, nb_ = Pt, Pb[1:]
    else:
        nt_, nb_ = Pt[:-1] + [m, Pt[-1]], [m] + Pb[1:]
    if rt:
        nt_ = list(reversed(nt_))
    if rb:
        nb_ = list(reversed(nb_))
    return {tt: nt_, tb: nb_ if len(nb_) >= 2 else None}


def drop_inside_arm(board, net, layer, v, inc, fixed):
    """The arm v -> far end of `inc` lies wholly inside the pad / via copper at the tip v (its far end and end cap inside
    it): the polyline starts at the far end instead (anchored inside the same copper); a two-point stub goes whole."""
    t, j, nb = inc
    P = board.tracks[t]["points"]
    if j not in (0, len(P) - 1):
        return None
    _, b, w = arm(board, inc)
    cap = Point(b).buffer(w / 2)
    inside = False
    if fixed == "via":
        inside = any(math.dist(x["at"], v) <= x["size"] / 2 + EPS and math.dist(x["at"], b) + w / 2 <= x["size"] / 2 + EPS
                     for x in board.via_at.get(net, []))
    else:
        inside = any(lay == layer and poly.buffer(EPS).contains(Point(v)) and poly.buffer(EPS).contains(cap)
                     for lay, poly, _, _ in board.pads.get(net, []))
    if not inside:
        return None
    Q = list(P[1:]) if j == 0 else list(P[:-1])
    return {t: Q if len(Q) >= 2 else None}


def free_merge(board, inc_t, inc_b):
    """Acute corner with a free tip that a tangent mitre cannot fit: path A -> M -> B, M the foot of the branch's far end
    B on the trunk arm (the tip beyond M is redundant copper); a right angle at M instead of the acute one. If B lies
    within 0.05 mm of the trunk line, the trunk ends at M and the branch starts at B, inside the trunk's end cap."""
    v, a, wt = arm(board, inc_t)
    _, b, _ = arm(board, inc_b)
    la, ua = math.dist(v, a), unit(v, a)
    along = (b[0] - v[0]) * ua[0] + (b[1] - v[1]) * ua[1]
    h = abs((b[0] - v[0]) * ua[1] - (b[1] - v[1]) * ua[0])
    if along <= MIN_PIECE or along >= la - MIN_PIECE:
        return None
    m = (v[0] + along * ua[0], v[1] + along * ua[1])
    if h >= MIN_PIECE:
        return replace_vertex(board, inc_t, inc_b, [m])
    (tt, jt, _), (tb, jb, _) = inc_t, inc_b
    if tt == tb or h > wt / 2 - 0.01:
        return None
    Pt, Pb = list(board.tracks[tt]["points"]), list(board.tracks[tb]["points"])
    if jt not in (0, len(Pt) - 1) or jb not in (0, len(Pb) - 1):
        return None
    Pt = [rnd(m)] + Pt[1:] if jt == 0 else Pt[:-1] + [rnd(m)]
    Pb = Pb[1:] if jb == 0 else Pb[:-1]
    return {tt: Pt, tb: Pb if len(Pb) >= 2 else None}


def loose_end(board, ti, j):
    """(start loose, end loose) for segment j of polyline ti: the segment ends at a polyline end that shares no vertex
    and sits on no pad or via of the net (it joins by overlapping another track). KiCad reports a short dogleg piece
    there as dangling (the item that joined it now lies in the other piece), so the end piece must be >= 1 mm."""
    t = board.tracks[ti]
    P = t["points"]
    vert = board.vertices(t["net"], t["layer"])

    def loose(idx):
        v = board.xy(P[idx])
        return len(vert.get(k3(v), [])) == 1 and not board.at_fixed(t["net"], t["layer"], v, [P[idx]])
    return (j == 0 and loose(0)), (j == len(P) - 2 and loose(len(P) - 1))


def candidates_any(board, ti, j, loose=(False, False)):
    """Octilinear doglegs for segment j of track ti: diagonal piece first, or straight piece first."""
    P = board.tracks[ti]["points"]
    a, b = board.xy(P[j]), board.xy(P[j + 1])
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = min(abs(dx), abs(dy))
    sx, sy = math.copysign(1, dx), math.copysign(1, dy)
    outs = []
    for mid in ((a[0] + sx * m, a[1] + sy * m), (b[0] - sx * m, b[1] - sy * m)):
        if math.dist(a, mid) < (LOOSE_PIECE if loose[0] else MIN_PIECE) or \
                math.dist(mid, b) < (LOOSE_PIECE if loose[1] else MIN_PIECE):
            continue
        outs.append({ti: list(P[:j + 1]) + [rnd(mid)] + list(P[j + 1:])})
    return outs


def run(board, log=None, max_rounds=8):
    """The four steps to a fixpoint. Returns (applied edits by step and layer, skipped corners by reason and layer)."""
    applied = Counter()
    skipped = {}
    for rnd_ in range(max_rounds):
        changed = False
        for step in STEPS:
            while True:
                n = one_step(board, step, applied, skipped, log)
                changed |= n > 0
                if n == 0:
                    break
        if not changed:
            break
    board.tracks[:] = [t for t in board.tracks if t["points"] is not None]
    return applied, skipped


def defects(board):
    """[(step, net, layer, vertex key, inc1, inc2, angle)] in a fixed order."""
    out = []
    groups = sorted({(t["net"], t["layer"]) for t in board.tracks if t["points"] is not None})
    for net, layer in groups:
        for v, inc in sorted(board.vertices(net, layer).items()):
            if len(inc) != 2:
                continue
            (t1, j1, nb1), (t2, j2, nb2) = inc
            P1, P2 = board.tracks[t1]["points"], board.tracks[t2]["points"]
            vv, a, b = board.xy(P1[j1]), board.xy(P1[nb1]), board.xy(P2[nb2])
            if math.dist(vv, a) < 1e-6 or math.dist(vv, b) < 1e-6:
                continue
            kind = classify(angle_at(vv, a, b))
            if kind:
                out.append((kind, net, layer, v, inc[0], inc[1]))
    return out


def one_step(board, step, applied, skipped, log):
    n = 0
    if step == "any":
        items = []
        for ti, t in enumerate(board.tracks):
            if t["points"] is None:
                continue
            for j, (a, b) in enumerate(board.segs(ti)):
                if math.dist(a, b) > 1e-6 and not octilinear(a, b):
                    items.append((t["net"], t["layer"], k3(a), k3(b), ti, j))
        for net, layer, ka, kb, ti, j in sorted(items):
            t = board.tracks[ti]
            if t["points"] is None or len(t["points"]) <= j + 1:
                continue
            a, b = board.segs(ti)[j]
            if (k3(a), k3(b)) != (ka, kb):
                continue
            key = ("any", layer, (net, ka, kb))
            if key in skipped:
                continue
            cands = candidates_any(board, ti, j, loose_end(board, ti, j))
            why = "room: pieces shorter than 0.05 mm (1 mm at a loose end)" if not cands else None
            for ov in cands:
                why = board.evaluate(net, layer, ov, "any", None)
                if why is None:
                    board.apply(ov)
                    applied[("any", layer)] += 1
                    n += 1
                    if log:
                        log.append(("any", net, layer, ka, kb))
                    break
            if why:
                skipped[key] = why
        return n
    for kind, net, layer, v, inc1, inc2 in defects(board):
        if kind != step:
            continue
        key = (step, layer, (net, v))
        if key in skipped:
            continue
        # the vertex list is stale once an edit lands on this net / layer: re-check
        cur = board.vertices(net, layer).get(v, [])
        if len(cur) != 2 or sorted(cur) != sorted([inc1, inc2]):
            continue
        t = board.tracks
        vv = board.xy(t[inc1[0]]["points"][inc1[1]])
        fixed = board.at_fixed(net, layer, vv, [t[inc1[0]]["points"][inc1[1]], t[inc2[0]]["points"][inc2[1]]])
        if step == "fold":
            ov = drop_fold(board, inc1, inc2, fixed)
            cands = [ov] if ov else []
            why = "shape: fold not handled (widths or polyline)" if not cands else None
        else:
            cands, why = [], None
            if fixed:                    # an arm wholly inside the tip's pad / via copper is redundant: it goes
                cands = [ov for ov in (drop_inside_arm(board, net, layer, vv, inc1, fixed),
                                       drop_inside_arm(board, net, layer, vv, inc2, fixed)) if ov]
            if fixed and step == "right":
                if not cands:
                    why = (f"{fixed}: square exit, the inner corner inside the {fixed}'s copper"
                           if wedge_covered(board, net, layer, vv, inc1, inc2) else f"{fixed}: corner tip on a {fixed}")
            elif fixed:
                m = [ov for ov in (merge_trunk(board, inc1, inc2), merge_trunk(board, inc2, inc1)) if ov]
                if len(m) == 2 and track_len(board, inc2) > track_len(board, inc1):
                    m.reverse()
                cands += m
                if not cands:
                    why = f"{fixed}: no trunk to merge the shorter arm onto"
            else:
                why, cands = candidates_corner(board, net, layer, vv, inc1, inc2, step)
                if step == "acute":      # fallback: the shorter arm leaves the longer one square (acute -> right)
                    m = [ov for ov in (free_merge(board, inc1, inc2), free_merge(board, inc2, inc1)) if ov]
                    if len(m) == 2 and track_len(board, inc2) > track_len(board, inc1):
                        m.reverse()
                    cands += m
                    why = why if not cands else None
        last = why
        for ov in cands:
            last = board.evaluate(net, layer, ov, step, kind)
            if last is None:
                board.apply(ov)
                applied[(step, layer)] += 1
                n += 1
                if log is not None:
                    log.append((step, net, layer, v, "tip " + fixed if fixed else "free"))
                break
        if last:
            skipped[key] = last
    return n


def check_export(board, export):
    """The export must be the build of this copper: its tracks are exactly the copper's segments."""
    a = Counter()
    for ti, t in enumerate(board.tracks):
        for p, q in board.segs(ti):
            a[(t["net"], t["layer"], round(t["width"], 3)) + tuple(sorted([k3(p), k3(q)]))] += 1
    b = Counter((p["net"], p["layer"], round(p["width_mm"], 3)) + tuple(sorted([k3(p["start"]), k3(p["end"])]))
                for p in export["primitives"] if p["kind"] == "track")
    return a == b, sum((a - b).values()), sum((b - a).values())


def load_export(path):
    p = Path(path)
    return json.loads((gzip.open(p) if p.suffix == ".gz" else p.open()).read())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("copper")
    ap.add_argument("export")
    ap.add_argument("--pads", default=str(HERE / "pads.json"))
    ap.add_argument("--board-only", default=str(HERE / "board_only21.json"))
    ap.add_argument("--out")
    ap.add_argument("--report")
    a = ap.parse_args()
    copper = json.loads(Path(a.copper).read_text())
    export = load_export(a.export)
    pads = json.loads(Path(a.pads).read_text())
    mounts = json.loads(Path(a.board_only).read_text()).get("mounting_holes", []) if Path(a.board_only).exists() else []
    spine = json.loads(SPINE_LOCK.read_text())["region"]
    board = Board(copper, export, pads, spine=spine, mounts=mounts)
    ok, extra_c, extra_e = check_export(board, export)
    if not ok:
        raise SystemExit(f"export is not the build of {a.copper}: {extra_c} copper segments missing from it, {extra_e} extra")
    before = track_geometry.measure(prims_of(board))
    log = []
    applied, skipped = run(board, log)
    after = track_geometry.measure(prims_of(board))
    by_reason = defaultdict(Counter)
    for (step, layer, _), why in skipped.items():
        by_reason[f"{step} | {why}"][layer] += 1
    rep = {"before": before, "after": after,
           "applied": {f"{s} {l}": n for (s, l), n in sorted(applied.items())},
           "applied_total": sum(applied.values()),
           "left": {k: dict(sorted(v.items())) for k, v in sorted(by_reason.items())},
           "export_board_sha256": export.get("board_sha256")}
    print(json.dumps({k: rep[k] for k in ("before", "after", "applied_total")}))
    for k, v in rep["left"].items():
        print(f"  left  {k}: {dict(v)}")
    if a.report:
        rep["log"] = [list(map(str, x)) for x in log]
        Path(a.report).write_text(json.dumps(rep, indent=1) + "\n")
    if a.out:
        Path(a.out).write_text(json.dumps(board.copper, indent=1) + "\n")


def prims_of(board):
    out = []
    for ti, t in enumerate(board.tracks):
        if t["points"] is None:
            continue
        for p, q in board.segs(ti):
            out.append({"kind": "track", "net": t["net"], "layer": t["layer"], "start": p, "end": q})
    return out


if __name__ == "__main__":
    main()
