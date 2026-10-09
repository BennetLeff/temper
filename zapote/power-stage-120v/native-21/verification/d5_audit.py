#!/usr/bin/env python3
"""D5 insulation audit of the native-21 board (what the PCB can show; lab items listed separately).

    python3 native-21/verification/d5_audit.py <copper-dump.json>  ->  native-21/verification/d5-audit.json

1. Plan-view minimum copper distance, every layer pair, HOT↔SELV and HOT↔PE: the 8.0 mm provisional
   floor (D5-BASIS). Plan view over all layers is at least the surface creepage on a solid board,
   because every surface path is at least as long as the straight line between its ends.
2. Every footprint that bridges the barrier (pads in HOT and in SELV/PE nets): its land gap on this
   board, measured pad edge to pad edge, against the floor, and the package's own datasheet
   distances (PKG below, with sources). Package distances are evidence about the package only (TI
   tables: material group I, pollution degree 2).
3. Non-plated holes (mounting hardware) and the PE branch: distance to the nearest HOT copper.
4. The open items no PCB measurement closes (laminate CTI, PD3/material qualification, IEC 60664-4
   HF distances, hipot), as the record of what remains for the lab.
"""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "layout"))
import rules21  # noqa: E402

FLOOR = rules21.BARRIER
# datasheet package insulation distances (mm) for the barrier-crossing parts
PKG = {
    "ISO7710DWR": {"clr": 8.0, "cpg": 8.0, "src": "TI SLLSER9E p.8 (DW-16)", "rating": "reinforced (VDE 0884-17)"},
    "UCC21550BDWKR": {"clr": 8.0, "cpg": 8.0, "src": "TI UCC21550 datasheet, DWK insulation table", "rating": "reinforced"},
    "AMC1311BDWVR": {"clr": 8.5, "cpg": 8.5, "src": "TI AMC1311 datasheet, DWV insulation table", "rating": "reinforced"},
    "VOL628A-3X001T": {"clr": 8.0, "cpg": 8.0, "src": "Vishay doc 82401 rev 1.9 p.4", "rating": "option 1 (VDE)"},
    "CST3015-100ED": {"clr": 8.0, "cpg": 8.0, "src": "Coilcraft CST3015 datasheet (≥8 mm spacing, 5 kVrms test)", "rating": "no CTI/PD certificate"},
    "IRM-20-15": {"clr": None, "cpg": None, "src": "Mean Well IRM-20 (input/output pin span only)", "rating": "module approval; PCB pin span checked here"},
}


def geoms(d):
    out = []
    for p in d["pads"]:
        if len(p.get("pts", [])) > 2:
            out.append(("pad", p["net"], p.get("ref"), Polygon(p["pts"])))
    for t in d["tracks"]:
        out.append(("track", t["net"], None, LineString([t["a"], t["b"]]).buffer(t["w"] / 2)))
    for v in d["vias"]:
        out.append(("via", v["net"], None, Point(v["at"]).buffer(v["d"] / 2)))
    for z in d["zones"]:
        # filled zone with its cut-outs (a plane's clearance round a hole is not copper; N6, 2026-10-08)
        out.append(("zone", z["net"], None, Polygon(z["pts"], z.get("holes") or [])))
    return [g for g in out if g[1]]


def dom(net):
    if net in rules21.PE:
        return "PE"
    if net in rules21.SELV:
        return "SELV"
    return "HOT" if net in rules21.GROUP else None


def nearest(src, dst):
    tree = STRtree([g[3] for g in dst])
    best = (1e9, None, None)
    for a in src:
        for i in tree.query(a[3].buffer(FLOOR + 5)):
            b = dst[i]
            dd = a[3].distance(b[3])
            if dd < best[0]:
                best = (dd, a, b)
    d, a, b = best
    return {"min_mm": round(d, 3), "pass": d >= FLOOR - 1e-6,
            "between": [f"{a[0]} {a[1]} {a[2] or ''}".strip(), f"{b[0]} {b[1]} {b[2] or ''}".strip()],
            "at_mm": [round(c, 2) for c in a[3].centroid.coords[0]]} if a else {"min_mm": None}


def main():
    d = json.loads(Path(sys.argv[1]).read_text())
    G = geoms(d)
    by = {k: [g for g in G if dom(g[1]) == k] for k in ("HOT", "SELV", "PE")}
    res = {"floor_mm": FLOOR, "copper": {"HOT-SELV": nearest(by["HOT"], by["SELV"]), "HOT-PE": nearest(by["HOT"], by["PE"])}}
    comps = json.loads((HERE.parent / "frozen" / "resolved-components.json").read_text())["components"]
    mpn = {c["attributes"].get("designator"): c["attributes"].get("mpn") for c in comps}
    pads = {}
    for p in d["pads"]:
        if p["net"] and len(p.get("pts", [])) > 2:
            pads.setdefault(p["ref"], []).append((dom(p["net"]), Polygon(p["pts"]), p["net"]))
    cross = []
    for ref, ps in sorted(pads.items()):
        hot = [x for x in ps if x[0] == "HOT"]
        low = [x for x in ps if x[0] in ("SELV", "PE")]
        if not hot or not low:
            continue
        gap = min(a[1].distance(b[1]) for a in hot for b in low)
        m = mpn.get(ref)
        cross.append({"ref": ref, "mpn": m, "land_gap_mm": round(gap, 3), "board_pass": gap >= FLOOR - 1e-6,
                      "package": PKG.get(m, {"src": "NOT IN TABLE: add the datasheet distances"})})
    res["barrier_crossing_parts"] = cross
    hot_u = unary_union([g[3] for g in by["HOT"]])
    from shapely.geometry import box as _box
    npth = [p for p in json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else HERE.parent / "layout" / "pads.json").read_text()) if p["npth"]]
    hot_refs = {ref for ref, ps in pads.items() if any(x[0] == "HOT" for x in ps)}
    bo = HERE.parent / "layout" / "board_only21.json"
    kinds = {h["ref"]: h["kind"] for h in json.loads(bo.read_text())["mounting_holes"]} if bo.exists() else {}
    # a HOT terminal's own locating / press-fit hole is part of that HOT conductor, not barrier hardware
    # the drill is round: measure from its circle (centre, half the box width), not the square box
    wall = lambda p: Point(p["x"], p["y"]).buffer((p["box"][2] - p["box"][0]) / 2, 64)
    res["npth_to_hot"] = [{"ref": p["ref"], "at": [p["x"], p["y"]], "hot_mm": round(wall(p).distance(hot_u), 2),
                           "role": "own hole of a HOT terminal" if p["ref"] in hot_refs else
                                   ("nylon fixing (insulating hardware only, F.Fab NYLON)" if kinds.get(p["ref"]) == "nylon"
                                    else "metal-capable fixing / connector hardware"),
                           "pass": p["ref"] in hot_refs or kinds.get(p["ref"]) == "nylon"
                                   or wall(p).distance(hot_u) >= FLOOR - 1e-6} for p in npth]
    res["board_fixings"] = {k: v for k, v in kinds.items()} or "none"
    res["open_for_lab"] = [
        "laminate CTI >= 175 V (group IIIa) on the order: JLC question open (FAB-JLCPCB.md)",
        "PD3 / material-group qualification of the package distances (TI tables state group I, PD2)",
        "IEC 60664-4 high-frequency distances above 30 kHz (switching 33-40 kHz)",
        "CST3015 CTI / PD certificate; IRM-20 internal insulation scope",
        "heatsink insulators of the TO-247 tabs (HOT drain to chassis/PE heatsink): material and creepage",
        "hipot / partial discharge on the assembled board",
    ]
    res["verdict_pcb"] = (res["copper"]["HOT-SELV"]["pass"] and res["copper"]["HOT-PE"]["pass"]
                          and all(c["board_pass"] for c in cross) and all(n["pass"] for n in res["npth_to_hot"]))
    (HERE / "d5-audit.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"copper": res["copper"], "crossing": [(c["ref"], c["mpn"], c["land_gap_mm"]) for c in cross],
                      "npth_min": min((n["hot_mm"] for n in res["npth_to_hot"]), default=None),
                      "verdict_pcb": res["verdict_pcb"]}, indent=1))


if __name__ == "__main__":
    main()
