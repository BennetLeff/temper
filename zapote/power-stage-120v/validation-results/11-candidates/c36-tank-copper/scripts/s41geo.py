"""Stage-41 pour geometry from a board's all-copper export: legal pour polygons per (net, layer, region).
Clearances from rules21 (LOW-LOW 0.2, HOT groups 3.2), plus a fill margin; other-net zone OUTLINES (copper.json) are kept
at their clearance too, so no pour pair is contested."""
import gzip, json, sys
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
LAY = Path(__file__).resolve().parents[4] / "native-21/layout"
sys.path.insert(0, str(LAY))
import rules21

MARGIN = 0.05


def shape(p):
    k = p["kind"]
    if k in ("zone", "pad"):
        return Polygon(p["shell"], p.get("holes", [])).buffer(0)
    if k == "track":
        return LineString((p["start"], p["end"])).buffer(p["width_mm"] / 2, 8)
    if k == "via":
        return Point(p["centre"]).buffer(p["diameter_mm"] / 2, 16)


def legal(data, outlines, net, layer, region, anchors_net=None, skip_zone_names=(), extra_keepout=None):
    """region minus every other-net primitive on `layer` (fills, tracks, pads, vias) and every other-net zone outline on
    `layer`, each grown by its clearance; returns the union of pieces touching `net`'s own copper on the layer."""
    cut = []
    own = []
    for p in data["primitives"]:
        if p["layer"] != layer:
            continue
        s = shape(p)
        if s is None or not s.intersects(region.buffer(4.0)):
            continue
        if p["net"] == net:
            if p["kind"] != "zone":
                own.append(s)
            continue
        if p["kind"] == "zone":
            continue                 # other-net fills are refilled by KiCad; their outlines are checked below
        c = rules21.clearance_on(net, p["net"] or "", layer) if p["net"] else 0.3
        cut.append(s.buffer(c + MARGIN))
    for z in outlines:
        if z["layer"] != layer or z["net"] == net or z.get("name") in skip_zone_names:
            continue
        zp = Polygon(z["outline"], z["holes"]).buffer(0)
        if zp.intersects(region.buffer(4.0)):
            cut.append(zp.buffer(rules21.clearance(net, z["net"]) + 0.01))
    if extra_keepout is not None:
        cut.append(extra_keepout)
    g = region.difference(unary_union(cut)).buffer(-0.13).buffer(0.13)     # drop slivers under the 0.25 mm min width
    pieces = [q for q in getattr(g, "geoms", [g]) if q.area > 0.5 and any(q.intersects(o) for o in own)]
    return unary_union(pieces) if pieces else None


def load(allcopper, copper_json):
    data = json.load(gzip.open(allcopper))
    outlines = json.loads(Path(copper_json).read_text())["zones"]
    return data, outlines
