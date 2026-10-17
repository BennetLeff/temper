#!/usr/bin/env python3
"""Candidate 36 (stage 41): the pour outlines of native-21/layout/patches21.py S41_* from the board of record's copper.

    python3 -I pours41.py [ALL_COPPER.json.gz] [COPPER.json] [--variant move|pours|add]
        -> pours41.json (beside this script) and native-21/layout/stage41_pours.json (the patch's input)

Variants (all with the same four pours): move = two R5.4 vias moved north-west and the sw_b B.Cu outline raised over
R5; pours = the pours only; add = the pours plus two more 0.8 / 0.5 hv_ret vias at the north-west spots (no raise).

Each outline is the region below minus every other-net primitive on its layer (fills excepted), grown by its rules21
clearance + 0.05 mm, and minus every other-net zone OUTLINE grown by its clearance (so no pour pair is contested and
KiCad's refill reproduces the outline), opened by 0.13 mm (no sliver under the 0.25 mm minimum fill width) and kept only
where it touches the net's own copper. Inputs default to the s40 board of record (33ed17f3) export and copper.json
(first drawn on s38, b5bf428d: the same four outlines within the refill's vertex noise).
The two relocated R5.4 vias (S41_VIA_MOVES) are applied to the primitive list first.
"""
import gzip
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
sys.path.insert(0, str(UNIT / "native-21/layout"))
import rules21  # noqa: E402

VARIANT = sys.argv[sys.argv.index("--variant") + 1] if "--variant" in sys.argv else "move"
sys.argv = [a for i, a in enumerate(sys.argv) if a != "--variant" and (i == 0 or sys.argv[i - 1] != "--variant")]
ALL = (Path(sys.argv[1]) if len(sys.argv) > 1 else UNIT / "native-21/verification/native21s40-all-copper.json.gz").resolve()
CJ = (Path(sys.argv[2]) if len(sys.argv) > 2 else UNIT / "native-21/layout/copper.json").resolve()
MARGIN = 0.05
# (from, to): the two 0.8 / 0.5 hv_ret vias at R5.4's south-east corner move north-west (patches21.S41_VIA_MOVES)
VIA_MOVES = [((37.05, 15.6), (34.95, 14.6)), ((37.95, 15.0), (35.75, 16.25))]
REGIONS = {   # name: (net, layer, region, base zone it replaces / extends (None = new))
    "hv_ret R5.4 spreader": ("hv_ret", "F.Cu", box(34.3, 13.3, 43.0, 25.5), "hv_ret R5.4"),
    "leg_ret R5.1-Q3.1": ("leg_ret", "F.Cu", box(31.0, 0.6, 46.0, 10.4), "leg_ret Q6.3-R5.1-R13.2"),
    "leg_ret R5.1-Q6.3 (B)": ("leg_ret", "B.Cu", box(32.0, 0.6, 44.0, 12.45), None),
    "leg_ret sources neck": ("leg_ret", "In1.Cu", box(42.5, 12.0, 58.0, 14.7), "leg_ret sources"),
}
PRIORITY = {"leg_ret sources": 2}      # the base zone's priority where it outranks another net's plane outline
SWB_RAISE = box(33.0, 15.7, 42.0, 19.4)     # sw_b B.Cu outline raised over R5 (the fill keeps 3.2 mm from R5.4's vias)


def shape(p):
    k = p["kind"]
    if k in ("zone", "pad"):
        return Polygon(p["shell"], p.get("holes", [])).buffer(0)
    if k == "track":
        return LineString((p["start"], p["end"])).buffer(p["width_mm"] / 2, 8)
    if k == "via":
        return Point(p["centre"]).buffer(p["diameter_mm"] / 2, 16)


def main():
    data = json.load(gzip.open(ALL))
    zones = json.loads(CJ.read_text())["zones"]
    moves = VIA_MOVES if VARIANT == "move" else []
    prims = []
    for p in data["primitives"]:
        if p["kind"] == "via" and p["net"] == "hv_ret":
            for a, b in moves:
                if abs(p["centre"][0] - a[0]) < 1e-3 and abs(p["centre"][1] - a[1]) < 1e-3:
                    p = {**p, "centre": list(b)}
        prims.append(p)
    # the raised sw_b outline joins the other-net outlines the LOW pours keep clear of
    swb = next(z for z in zones if z["net"] == "sw_b" and z["layer"] == "B.Cu")
    swb_poly = Polygon(swb["outline"], swb["holes"]).buffer(0).union(SWB_RAISE)
    outlines = [z for z in zones if not (z["net"] == "sw_b" and z["layer"] == "B.Cu")] + \
               [{"net": "sw_b", "layer": "B.Cu", "outline": list(swb_poly.exterior.coords), "holes": [], "name": swb["name"]}]
    out, done = {}, {}
    for name, (net, layer, region, base) in REGIONS.items():
        cut, own = [], []
        for p in prims:
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
                continue
            c = rules21.clearance_on(net, p["net"], layer) if p["net"] else 0.3
            cut.append(s.buffer(c + MARGIN))
        for z in outlines:
            if z["layer"] != layer or z["net"] == net:
                continue
            if z.get("priority", 1) < PRIORITY.get(base, 1):
                continue             # a lower-priority plane (the In1 hv_ret trunk) yields to the pour: already resolved
            zp = Polygon(z["outline"], z["holes"]).buffer(0)
            if zp.intersects(region.buffer(4.0)):
                cut.append(zp.buffer(rules21.clearance(net, z["net"]) + 0.01))
        # this stage's other pours on the layer (hv_ret vs leg_ret, LOW 0.2 mm): 0.25 mm apart
        for (n2, l2), q in done.items():
            if l2 == layer and n2 != net:
                cut.append(q.buffer(0.25))
        legal_ = region.difference(unary_union(cut))
        g = legal_.buffer(-0.13).buffer(0.13).intersection(legal_)
        pieces = [q for q in getattr(g, "geoms", [g]) if q.area > 0.5 and any(q.intersects(o) for o in own)]
        poly = unary_union(pieces)
        if base:
            bz = next(z for z in zones if z.get("name") == base and z["layer"] == layer)
            poly = unary_union([poly, Polygon(bz["outline"], bz["holes"]).buffer(0)])
        poly = poly.simplify(0.02)
        assert poly.geom_type == "Polygon", (name, poly.geom_type)
        done[(net, layer)] = poly
        out[name] = {"net": net, "layer": layer, "replaces": base, "area_mm2": round(poly.area, 1),
                     "outline": [[round(x, 3), round(y, 3)] for x, y in list(poly.exterior.coords)[:-1]],
                     "holes": [[[round(x, 3), round(y, 3)] for x, y in list(r.coords)[:-1]] for r in poly.interiors]}
        print(f"{name:28s} {net:8s} {layer:7s} area {poly.area:6.1f} mm2  bounds {[round(v, 2) for v in poly.bounds]}"
              f"  vertices {len(out[name]['outline'])} holes {len(poly.interiors)}")
    out["sw_b raise"] = {"net": "sw_b", "layer": "B.Cu", "box": list(SWB_RAISE.bounds)}
    out["via_moves"] = VIA_MOVES
    out["inputs"] = {"all_copper": str(ALL.relative_to(UNIT)) if ALL.is_relative_to(UNIT) else str(ALL),
                     "board_sha256": data["board_sha256"]}
    (HERE / "pours41.json").write_text(json.dumps(out, indent=1) + "\n")
    lay = {"source": "validation-results/11-candidates/c36-tank-copper/scripts/pours41.py on " + out["inputs"]["all_copper"]
                     + f" (board {data['board_sha256'][:8]}) and copper.json; DECISIONS 51 targets (candidate 36)",
           "variant": VARIANT,
           "pours": [{"name": k, **{f: v[f] for f in ("net", "layer", "replaces", "outline", "holes")}}
                     for k, v in out.items() if isinstance(v, dict) and "outline" in v],
           "sw_b_raise": out["sw_b raise"] if VARIANT == "move" else None,
           "via_moves": moves,
           "via_adds": [["hv_ret", list(b), 0.8, 0.5] for _, b in VIA_MOVES] if VARIANT == "add" else []}
    (UNIT / "native-21/layout/stage41_pours.json").write_text(json.dumps(lay, indent=1) + "\n")
    print("variant", VARIANT, "-> native-21/layout/stage41_pours.json")


if __name__ == "__main__":
    main()
