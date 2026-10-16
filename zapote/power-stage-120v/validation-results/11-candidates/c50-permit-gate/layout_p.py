#!/usr/bin/env python3
"""Option P layout feasibility on the s48 board of record (read-only).

    python3 -I layout_p.py [PS_ROOT]      (PS_ROOT defaults to the ps-integrate power-stage-120v worktree)

Reads native-21/verification/native21s48-all-copper.json.gz (the built board, as the spine-lock gate sees it),
native-21/layout/copper.json (router source) and native-21/layout/selv_spine_lock.json, and reports:
  1. where U46, R135, the PERMIT copper and TP17 are;
  2. the proposed re-net: R135.1 v3v3 -> permit (R135 becomes the 10 k series resistor PERMIT -> U46.A); the v3v3
     via + stub at R135.1 are deleted and one F.Cu stub joins R135.1 to the existing permit F.Cu trace; its clearance
     to every other-net F.Cu primitive, and whether anything it touches is in the spine region;
  3. the neighbours of the (unchanged) hsb_good trace, for the FMEA short rows.
Writes results/layout_p.json next to this script.
"""
import gzip
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
ALLCU = PS / "native-21/verification/native21s48-all-copper.json.gz"
LOCK = PS / "native-21/layout/selv_spine_lock.json"
CLEAR_MM = 0.2      # section.kicad_pro Default net class clearance (SELV-SELV signal)
STUB_W = 0.25       # same width as the permit F.Cu branch it joins


def shape(p):
    k = p["kind"]
    if k == "track":
        return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2, cap_style=1)
    if k == "via":
        return Point(p["centre"]).buffer(p["diameter_mm"] / 2)
    if k in ("pad", "zone"):
        return Polygon(p["shell"], p.get("holes") or []).buffer(0)
    raise ValueError(k)


def main():
    d = json.loads(gzip.open(ALLCU).read())
    prims = d["primitives"]
    lock = json.loads(LOCK.read_text())
    region = box(*lock["region"])
    out = {"board_sha256": d["board_sha256"], "lock_baseline_sha256": lock["baseline_board_sha256"],
           "spine_region": lock["region"], "contract_nets": lock["contract_nets"]}

    pads = {p["ref"]: p for p in prims if p["kind"] == "pad"}
    for ref in ("U46.1", "U46.2", "U46.5", "R135.1", "R135.2", "R14.1", "R6.1", "J4.9", "J4.1"):
        p = pads[ref]
        out.setdefault("pads", {})[ref] = {"net": p["net"], "layer": p["layer"], "centre": p["centre"],
                                           "in_spine_region": region.contains(Point(p["centre"]))}
    tp17 = [p for p in prims if p["kind"] == "pad" and p["ref"].startswith("TP17.")]
    out["TP17"] = [{"ref": p["ref"], "net": p["net"], "centre": p["centre"]} for p in tp17]

    permit_f = [p for p in prims if p["kind"] == "track" and p["net"] == "permit" and p["layer"] == "F.Cu"]
    permit_all = [p for p in prims if p.get("net") == "permit" and p["kind"] in ("track", "via")]

    # 1. Distance from U46.1 and from R135.1 to the nearest PERMIT copper (any layer).
    def nearest_permit(pt):
        best = None
        for p in permit_all:
            dd = shape(p).distance(Point(pt))
            if best is None or dd < best[0]:
                best = (round(dd, 3), p["kind"], p["layer"], p.get("start") or p.get("centre"), p.get("end"))
        return best
    out["U46.1_to_nearest_permit_mm"] = nearest_permit(pads["U46.1"]["centre"])
    out["R135.1_to_nearest_permit_mm"] = nearest_permit(pads["R135.1"]["centre"])

    # 2. Proposed stub: from R135.1's centre horizontally to the nearest point of the permit F.Cu branch.
    r1 = Point(pads["R135.1"]["centre"])
    cands = []
    for p in permit_f:
        seg = LineString([p["start"], p["end"]])
        a, b = nearest_points(r1, seg)
        cands.append((r1.distance(seg), (round(b.x, 3), round(b.y, 3)), p))
    cands.sort(key=lambda c: c[0])
    _, join, seg = cands[0]
    stub = LineString([pads["R135.1"]["centre"], join])
    stub_poly = stub.buffer(STUB_W / 2, cap_style=1)
    # copper removed by the re-net: the v3v3 stub track from R135.1 and its via
    padpoly = Polygon(pads["R135.1"]["shell"]).buffer(0.05)
    stubs = [p for p in prims if p["kind"] == "track" and p.get("net") == "v3v3"
             and (padpoly.contains(Point(p["start"])) or padpoly.contains(Point(p["end"])))]
    ends = [Point(e) for p in stubs for e in (p["start"], p["end"]) if not padpoly.contains(Point(e))]
    vias = [p for p in prims if p["kind"] == "via" and p.get("net") == "v3v3"
            and any(Point(p["centre"]).distance(e) < 0.01 for e in ends)]
    # a via goes only if nothing else lands on it (here C168.1's F.Cu stub and a B.Cu v3v3 run share it: it stays)
    others_on_via = [p for p in prims if p["kind"] == "track" and p.get("net") == "v3v3" and p not in stubs
                     and any(Point(e).distance(Point(v["centre"])) < 0.01 for v in vias for e in (p["start"], p["end"]))]
    out["v3v3_via_at_R135.1_shared_with"] = sorted({(t["layer"], tuple(t["start"]), tuple(t["end"])) for t in others_on_via})
    removed = stubs + ([] if others_on_via else vias)
    removed_shapes = [shape(p) for p in removed]
    viol = []
    nearest = []
    for p in prims:
        if p.get("layer") not in ("F.Cu",) and p["kind"] != "via":
            continue
        if p.get("net") in ("permit",) or (p["kind"] == "pad" and p["ref"] == "R135.1"):
            continue
        if any(shape(p).equals(s) for s in removed_shapes):
            continue
        if p["kind"] == "zone" and p.get("net") == "v3v3":
            pass  # a v3v3 F.Cu fill would re-flow around the new permit stub; reported below
        dd = shape(p).distance(stub_poly)
        nearest.append((round(dd, 3), p["kind"], p.get("net"), p.get("ref"), p.get("centre") or p.get("start")))
        if dd < CLEAR_MM - 1e-6:
            viol.append(nearest[-1])
    nearest.sort(key=lambda t: t[0])
    # R135.1's pad becomes permit: its clearance to the v3v3 copper left beside it
    padshape = Polygon(pads["R135.1"]["shell"]).buffer(0)
    pad_near = sorted((round(padshape.distance(shape(p)), 3), p["kind"], p.get("net"))
                      for p in prims if p.get("net") not in ("permit", None)
                      and not (p["kind"] == "pad" and p["ref"] == "R135.1")
                      and (p["kind"] == "via" or p.get("layer") == "F.Cu")
                      and not any(shape(p).equals(s) for s in removed_shapes))[:3]
    out["R135.1_pad_as_permit_nearest_other_copper"] = pad_near
    fcu_zones_here = [p.get("net") for p in prims if p["kind"] == "zone" and p["layer"] == "F.Cu"
                      and shape(p).intersects(stub_poly.buffer(CLEAR_MM))]
    out["proposed_change"] = {
        "netlist": "R135 pin 1: v3v3 -> permit (R135 keeps 10 k and its footprint; pin 2 stays on hsb_good = U46.1)",
        "delete": [{"kind": p["kind"], "net": p["net"], "at": p.get("centre") or [p.get("start"), p.get("end")]}
                   for p in removed],
        "add_track": {"net": "permit", "layer": "F.Cu", "width_mm": STUB_W,
                      "from": pads["R135.1"]["centre"], "to": list(join),
                      "length_mm": round(stub.length, 3),
                      "joins_permit_segment": [seg["start"], seg["end"]]},
        "stub_clearance_violations_lt_0.2mm": viol,
        "stub_nearest_other_copper": nearest[:6],
        "F.Cu_zone_fills_within_0.2mm_of_stub": fcu_zones_here,
        "touches_spine_region": bool(stub_poly.intersects(region)) or any(region.intersects(s) for s in removed_shapes),
        "permit_tracks_in_region_changed": False,
    }

    # 3. hsb_good neighbours (same layer, < 0.5 mm edge-to-edge; vias count on every layer).
    hsb = [p for p in prims if p.get("net") == "hsb_good" and p["kind"] in ("track", "via", "pad")]
    neigh = {}
    for h in hsb:
        hs = shape(h)
        for p in prims:
            if p.get("net") in ("hsb_good", None) or p["kind"] == "zone":
                continue
            same = p["kind"] == "via" or h["kind"] == "via" or p.get("layer") == h.get("layer")
            if not same:
                continue
            dd = hs.distance(shape(p))
            if dd < 0.5:
                key = p["net"]
                if key not in neigh or dd < neigh[key]["mm"]:
                    neigh[key] = {"mm": round(dd, 3), "where": p.get("centre") or p.get("start"),
                                  "layer": p.get("layer"), "kind": p["kind"]}
    out["hsb_good_length_mm"] = round(sum(LineString([p["start"], p["end"]]).length for p in hsb
                                          if p["kind"] == "track"), 1)
    out["hsb_good_neighbours_lt_0.5mm"] = dict(sorted(neigh.items(), key=lambda kv: kv[1]["mm"]))
    zn = {}
    for h in hsb:
        hs = shape(h)
        for p in prims:
            if p["kind"] != "zone" or p.get("net") == "hsb_good":
                continue
            if h["kind"] != "via" and p["layer"] != h.get("layer"):
                continue
            dd = hs.distance(shape(p))
            if dd < 0.5:
                zn[(p["net"], p["layer"])] = min(round(dd, 3), zn.get((p["net"], p["layer"]), 9))
    out["hsb_good_zone_neighbours_lt_0.5mm"] = {f"{k[0]} {k[1]}": v for k, v in sorted(zn.items())}
    out["hsb_good_in_spine_region"] = any(shape(p).intersects(region) for p in hsb)

    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "layout_p.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
