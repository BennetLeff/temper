"""Shared geometry for the stage-16 scripts (board model from dump_board.py)."""
import json
import sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

UNIT = "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v"
sys.dont_write_bytecode = True          # never write __pycache__ into the unit
sys.path.insert(0, UNIT + "/native-21/layout")
from domains import domain  # noqa: E402,F401  (the unit's own net -> D5 domain map)

EDGE = Polygon([(0, 0), (290, 0), (290, 140), (91, 140), (91, 190), (0, 190)])   # geom21.EDGE


def load(path):
    return json.load(open(path))


def copper_by_net(d):
    geo = {}
    for z in d["zones"]:
        geo.setdefault(z["net"], []).append(Polygon(z["pts"], z["holes"]).buffer(0))
    for t in d["tracks"]:
        geo.setdefault(t["net"], []).append(LineString([t["a"], t["b"]]).buffer(t["w"] / 2))
    for v in d["vias"]:
        geo.setdefault(v["net"], []).append(Point(*v["at"]).buffer(v["d"] / 2))
    for p in d["pads"]:
        if p["net"] and len(p["pts"]) > 2:
            geo.setdefault(p["net"], []).append(Polygon(p["pts"]).buffer(0))
    return {k: unary_union(v) for k, v in geo.items()}


def by_domain(geo):
    out = {}
    for n, g in geo.items():
        out.setdefault(domain(n), []).append(g)
    return {k: unary_union(v) for k, v in out.items()}


def h1_disc(d):
    """H1 is the board's only metal fixing (board_only21.json kind 'metal'; H2-H7 nylon, DECISIONS
    2026-10-09 item 7). Its M3 head / standoff is earthed metal: treated as PE, 7 mm disc."""
    h = [f for f in d["footprints"] if f["ref"] == "H1"][0]["crtyd"]
    return Point((h[0] + h[2]) / 2, (h[1] + h[3]) / 2).buffer((h[2] - h[0]) / 2)


def courtyards(d, gap=0.6):
    return [(f["ref"], box(*f["crtyd"]).buffer(gap / 2, join_style=2), f) for f in d["footprints"]
            if not f["ref"].startswith(("FID", "TP"))]
