"""Board copper as a graph: pads, tracks and vias from cad/routing.json, for path length and DC
resistance between pads (regulator_check.py) and routed loop geometry (switcher_pickup.py).

Pads come from build/pad-coordinates.json (written by cad/build_cad.py) when the tree has one, else
from validation/rev-f-floorplan/rev-e-inventory.json, used only when its board SHA-256 matches the
tree's cad/temper-lcr.kicad_pcb (the committed Rev E board).

Resistance model: each track segment is a strip, R = rho L / (w t); vias are a plated barrel through
the whole board. Zones are not used (the only Rev E zone is the In1.Cu GND plane). A single path
through a network has at least the network's resistance (Rayleigh monotonicity: removing branches
never lowers a two-terminal resistance), so the shortest-path value is an upper bound on the strip
model. The strip model leaves out bend and pad spreading, so the result is not a bound on the real
copper beyond that model.
"""
from __future__ import annotations

import hashlib
import heapq
import importlib.util
import json
import math
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
INVENTORY = HERE.parent / "rev-f-floorplan/rev-e-inventory.json"
REV_E_COMMIT = "48b012771"   # Rev E as ordered-candidate (U5 OPA197): routing.json read from git

_spec = importlib.util.spec_from_file_location("lp_common", HERE.parent / "layout-parasitics/common.py")
_lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lp)
STACKUP = _lp.STACKUPS[_lp.NOMINAL_STACKUP]       # JLC04161H-7628, JLC's default 4-layer 1.6 mm
T_CU = {"F.Cu": STACKUP["t_outer"], "B.Cu": STACKUP["t_outer"],      # mm; outer 1 oz before plating
        "In1.Cu": STACKUP["t_inner"], "In2.Cu": STACKUP["t_inner"]}  # inner 0.5 oz
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
BOARD_MM = 1.6
VIA_PLATING_MM = 0.018       # ASSUMED: IPC-6012 class 2 thin-area hole-wall minimum (no JLC figure in sources/)
RHO_20C = 1.72e-8            # ohm m, annealed copper at 20 C (the value R_ENTRY already uses)
ALPHA_CU = 0.0039            # 1/K
PAD_SNAP_MM = 0.4            # pad reach when no pad size is known


def load_pads(root: pathlib.Path):
    """{ref: {pad: [x, y, net]}} and {ref: {pad: [half_x, half_y]}} (half sizes may be empty)."""
    built = root / "build/pad-coordinates.json"
    inv = json.loads(INVENTORY.read_text())
    half = {r: p.get("pad_half", {}) for r, p in inv["parts"].items()}
    if built.exists():
        return json.loads(built.read_text()), half, str(built)
    sha = hashlib.sha256((root / "cad/temper-lcr.kicad_pcb").read_bytes()).hexdigest()
    if sha != inv["board_sha256"]:
        raise SystemExit(f"{root}: no build/pad-coordinates.json and the board is not the inventory's "
                         f"Rev E board; run cad/rebuild.sh in that tree first")
    return {r: p["pads"] for r, p in inv["parts"].items()}, half, str(INVENTORY)


def load_routing(root: pathlib.Path | None):
    """routing.json of a tree, or of the Rev E commit when root is None."""
    if root is not None:
        return json.loads((root / "cad/routing.json").read_text()), str(root / "cad/routing.json")
    rel = "instruments/lcr-meter/cad/routing.json"
    txt = subprocess.run(["git", "-C", str(HERE), "show", f"{REV_E_COMMIT}:{rel}"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(txt), f"git {REV_E_COMMIT}:{rel}"


def rho(dt_from_20c=0.0):
    return RHO_20C * (1 + ALPHA_CU * dt_from_20c)


class Copper:
    def __init__(self, routing, pads, half=None, dt_from_20c=0.0):
        self.routing, self.pads, self.half = routing, pads, half or {}
        self.rho = rho(dt_from_20c)
        self._graphs = {}

    def _seg_ohm(self, layer, length_mm, width_mm):
        return self.rho * (length_mm * 1e-3) / (width_mm * 1e-3 * T_CU[layer] * 1e-3)

    def _via_ohm(self, drill_mm):
        area = math.pi * (drill_mm + VIA_PLATING_MM) * VIA_PLATING_MM * 1e-6
        return self.rho * BOARD_MM * 1e-3 / area

    def graph(self, net):
        """Adjacency {node: [(node, ohm, mm)]}; nodes are (layer, x, y) or ('pad', ref, num)."""
        if net in self._graphs:
            return self._graphs[net]
        adj = {}

        def edge(a, b, ohm, mm):
            adj.setdefault(a, []).append((b, ohm, mm))
            adj.setdefault(b, []).append((a, ohm, mm))

        key = lambda layer, p: (layer, round(p[0], 4), round(p[1], 4))
        segs = []
        for t in self.routing["tracks"]:
            if t["net"] == net:
                for p, q in zip(t["points"], t["points"][1:]):
                    segs.append((t["layer"], tuple(p), tuple(q), t["width"]))
        vias = [v for v in self.routing["vias"] if v["net"] == net]
        points = {}
        for layer, p, q, _ in segs:
            points.setdefault(layer, set()).update([p, q])
        for v in vias:
            for layer in LAYERS:
                points.setdefault(layer, set()).add(tuple(v["at"]))
        # split segments at T-junctions (an endpoint or via lying inside another segment)
        for layer, p, q, w in segs:
            dx, dy = q[0] - p[0], q[1] - p[1]
            l2 = dx * dx + dy * dy
            cuts = [0.0, 1.0]
            for r in points.get(layer, ()):
                if l2 == 0:
                    break
                s = ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / l2
                if 1e-6 < s < 1 - 1e-6 and abs((r[0] - p[0]) * dy - (r[1] - p[1]) * dx) / math.sqrt(l2) < 1e-3:
                    cuts.append(s)
            cuts.sort()
            for s0, s1 in zip(cuts, cuts[1:]):
                a = (p[0] + s0 * dx, p[1] + s0 * dy)
                b = (p[0] + s1 * dx, p[1] + s1 * dy)
                mm = math.dist(a, b)
                edge(key(layer, a), key(layer, b), self._seg_ohm(layer, mm, w), mm)
        for v in vias:
            nodes = [key(layer, v["at"]) for layer in LAYERS]
            per = self._via_ohm(v["drill"]) / (len(LAYERS) - 1)
            for a, b in zip(nodes, nodes[1:]):
                edge(a, b, per, BOARD_MM / (len(LAYERS) - 1))
        # pads: zero-ohm links to every copper node of the net inside the pad (any layer)
        copper_nodes = [n for n in adj if n[0] in T_CU]
        for ref, pins in self.pads.items():
            for num, (x, y, n) in pins.items():
                if n != net:
                    continue
                hx, hy = self.half.get(ref, {}).get(num, (PAD_SNAP_MM, PAD_SNAP_MM))
                reach = max(hx, hy, PAD_SNAP_MM)
                pad = ("pad", ref, num)
                adj.setdefault(pad, [])
                for c in copper_nodes:
                    if abs(c[1] - x) <= reach and abs(c[2] - y) <= reach:
                        edge(pad, c, 0.0, math.hypot(c[1] - x, c[2] - y))
        self._graphs[net] = adj
        return adj

    def xy(self, node):
        if node[0] == "pad":
            return tuple(self.pads[node[1]][node[2]][:2])
        return node[1], node[2]

    def path(self, net, src, dst, weight="ohm"):
        """Shortest copper path from any pad in src to any pad in dst ([(ref, num)]).
        Returns dict(ohm, mm, points [(x, y)], routed) or a straight pad-to-pad stand-in when the net
        has no copper path (routed False)."""
        adj = self.graph(net)
        w = 1 if weight == "ohm" else 2
        starts = [("pad", r, n) for r, n in src]
        goals = {("pad", r, n) for r, n in dst}
        dist = {s: (0.0, 0.0, 0.0) for s in starts}   # (weight, ohm, mm)
        prev = {}
        heap = [(0.0, i, s) for i, s in enumerate(starts)]
        heapq.heapify(heap)
        tie = len(heap)
        while heap:
            d, _, u = heapq.heappop(heap)
            if d > dist[u][0]:
                continue
            if u in goals:
                _, ohm, mm = dist[u]
                pts = [self.xy(u)]
                while u in prev:
                    u = prev[u]
                    pts.append(self.xy(u))
                pts.reverse()
                return {"ohm": ohm, "mm": mm, "points": pts, "routed": True}
            for v, ohm, mm in adj.get(u, ()):
                cand = (d + (ohm, mm)[w - 1], dist[u][1] + ohm, dist[u][2] + mm)
                if v not in dist or cand[0] < dist[v][0]:
                    dist[v] = cand
                    prev[v] = u
                    tie += 1
                    heapq.heappush(heap, (cand[0], tie, v))
        pa, pb = min(((tuple(self.pads[r][n][:2]), tuple(self.pads[s][m][:2])) for r, n in src for s, m in dst),
                     key=lambda ab: math.dist(*ab))
        return {"ohm": None, "mm": math.dist(pa, pb), "points": [pa, pb], "routed": False}
