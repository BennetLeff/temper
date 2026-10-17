"""Authoring-time geometry checks for native-21 copper (route21.py).

Holds the placed pads (pads.json), every track and via authored so far, and the
outlines of protected pours, and answers "is this new copper legal?" under
rules21.clearance (the D5 rules). Used to pick legal via spots next to pads
(fan-outs) and to reject an authored track before it reaches the board. KiCad
DRC on the filled board stays the authority; this only keeps authoring honest.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.strtree import STRtree

import rules21
from layers21 import CU  # noqa: F401  (copper layers, top to bottom, from native-21/stackup.json)

HERE = Path(__file__).resolve().parent
EDGE = [(0, 0), (290, 0), (290, 140), (91, 140), (91, 190), (0, 190)]
EDGE_CLEARANCE = 0.5
EPS = 0.01


class Geometry:
    def __init__(self, pads_path=HERE / "pads.json"):
        self.pads = json.loads(Path(pads_path).read_text())
        self.items = {lay: [] for lay in CU + ("PLAN",)}   # (geom, net); PLAN = all copper, plan view
        self.via_permeable = set()
        self._trees = {}
        self.pad_at = {}
        for p in self.pads:
            if not p["net"] and not p["npth"]:
                continue          # paste / thermal sub-pads of an exposed pad: part of its copper
            g = box(*p["box"])
            if p["npth"]:
                net = "<npth>"
            else:
                net = p["net"]
            for lay in (CU if p["tht"] else ("F.Cu",)):
                self.items[lay].append((g, net))
            self.items["PLAN"].append((g, net))
            self.pad_at.setdefault(f"{p['ref']}.{p['pad']}", []).append(p)
        self.outline = Polygon(EDGE).buffer(-EDGE_CLEARANCE, join_style=2)

    # -- registration
    def _add(self, layers, geom, net):
        for lay in layers:
            self.items[lay].append((geom, net))
            self._trees.pop(lay, None)
        self.items["PLAN"].append((geom, net))
        self._trees.pop("PLAN", None)

    def add_plan(self, net, polygon):
        """Copper whose exact fill is unknown at authoring time (pour outlines): plan-view only."""
        self.items["PLAN"].append((polygon, net))
        self._trees.pop("PLAN", None)

    def add_track(self, net, layer, width, pts):
        self._add((layer,), LineString(pts).buffer(width / 2, cap_style=1), net)

    def add_via(self, net, x, y, size):
        self._add(CU, Point(x, y).buffer(size / 2), net)

    def protect(self, net, layer, polygon, via_ok=False):
        """A pour that tracks of other nets must not enter; via_ok pours let vias through (the
        fill opens an antipad), lanes do not."""
        self._add((layer,), polygon, net)
        if via_ok:
            self.via_permeable.add(id(polygon))

    # -- queries
    def _tree(self, lay):
        if lay not in self._trees:
            geoms = [g for g, _ in self.items[lay]]
            self._trees[lay] = (STRtree(geoms), self.items[lay])
        return self._trees[lay]

    def conflicts(self, net, layers, geom, limit=3, via=False):
        out = []
        if not self.outline.contains(geom):
            out.append(("edge", None))
        for lay in layers:
            tree, items = self._tree(lay)
            for i in tree.query(geom.buffer(rules21.RES_A_CREEPAGE + 0.1 if net in rules21.RES_A_NETS or
                                            rules21.domain(net) in ("SELV", "PE") else 8.5)):
                g, other = items[i]
                if other == net or (via and id(g) in self.via_permeable):
                    continue
                need = 0.3 if other == "<npth>" else rules21.clearance_on(net, other, lay)
                if g.distance(geom) < need + 0.03:
                    out.append((lay, other))
                    if len(out) >= limit:
                        return out
        # D5 barrier: SELV / PE against HOT is a plan-view distance over every copper layer
        if rules21.domain(net) in ("SELV", "PE", "HOT"):
            tree, items = self._tree("PLAN")
            for i in tree.query(geom.buffer(8.5)):
                g, other = items[i]
                if other in (net, "<npth>") or not rules21.barrier(net, other):
                    continue
                if g.distance(geom) < rules21.BARRIER + 0.03:
                    out.append(("PLAN", other))
                    if len(out) >= limit:
                        return out
        return out

    def pad(self, ref_pad):
        hits = self.pad_at[ref_pad]
        if len(hits) != 1:
            raise KeyError(f"{ref_pad}: {len(hits)} pads")
        return hits[0]

    def via_spot(self, ref_pad, size=0.6, width=0.4, reach=(0.6, 3.2), within=None, avoid_dirs=()):
        """Nearest legal via beside an SMD pad, joined by a short F.Cu stub.

        Tries 16 directions, preferring away from the part's centre, stepping outward from the
        pad edge. `within` (shapely geometry) restricts the via to a target pour.
        Returns (x, y) or None."""
        p = self.pad(ref_pad)
        cx, cy = p["x"], p["y"]
        hw, hh = (p["box"][2] - p["box"][0]) / 2, (p["box"][3] - p["box"][1]) / 2
        away = math.atan2(cy - p["fc"][1], cx - p["fc"][0])
        dirs = sorted((k * math.pi / 8 for k in range(16)),
                      key=lambda a: abs(math.remainder(a - away, 2 * math.pi)))
        best = None
        for step in [reach[0] + 0.2 * i for i in range(int((reach[1] - reach[0]) / 0.2) + 1)]:
            for a in dirs:
                ex = abs(math.cos(a)) * hw + abs(math.sin(a)) * hh
                d = ex + size / 2 + step
                x, y = cx + d * math.cos(a), cy + d * math.sin(a)
                v = Point(x, y).buffer(size / 2)
                if within is not None and not within.contains(Point(x, y)):
                    continue
                if self.conflicts(p["net"], CU, v, limit=1, via=True):
                    continue
                stub = LineString([(cx, cy), (x, y)]).buffer(width / 2)
                if self.conflicts(p["net"], ("F.Cu",), stub, limit=1):
                    continue
                best = (round(x, 3), round(y, 3))
                break
            if best:
                break
        return best
