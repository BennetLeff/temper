#!/usr/bin/env python3
"""Does a board revision need the D1 FEM re-extraction? (round 17)

Compares two KiCad boards (.kicad_pcb) inside each leg's FEM region: the leg
box the mesher crops around (mesh25d_hybrid.LEGS) grown by the crop margin
at which the inductances converged (20 mm, README section 10). Copper
outside that region changed L by < 0.1 % (20 -> 25 mm), so changes there do
not need a rerun.

Inside the region it compares, as canonical rounded records:
- footprints with any pad in the region (reference, library id, position,
  rotation, side, 3-D model and its offset/rotation);
- pads (board position, shape, size, drill, layers, net);
- tracks and arcs, vias;
- zone fills, per (net, layer), clipped to the region (symmetric-difference
  area above AREA_TOL_MM2 counts as a change);
and, globally, the stackup.

Verdict per leg: UNCHANGED (no rerun) or CHANGED (rerun that leg), with the
differences listed. A change to a power MOSFET's footprint, 3-D model or its
offset is flagged separately: the vendor model assumes standard TO-247 leads,
so mounting height or lead length must be checked by hand.

    leg_region_diff.py OLD.kicad_pcb NEW.kicad_pcb [--legs A B] [--margin 20] [--json OUT]

Exit code 0 if every requested leg is UNCHANGED and the stackup matches, 2 otherwise.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROUND = 3                      # mm, 1 um
AREA_TOL_MM2 = 0.01
FETS = {"Q2", "Q3", "Q5", "Q6"}


def legs() -> dict[str, tuple[float, float, float, float]]:
    """LEGS from the mesher, read without importing it (it imports gmsh)."""
    src = (HERE / "mesh25d_hybrid.py").read_text()
    out = ast.literal_eval(re.search(r"^LEGS = (\{.*\})$", src, re.M)[1])
    for m in re.finditer(r'^LEGS\["(\w+)"\] = (\(.*\))$', src, re.M):
        out[m[1]] = ast.literal_eval(m[2])
    return out


# ---- minimal KiCad s-expression reader ------------------------------------
TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text: str) -> list:
    stack, cur = [], []
    for t in TOKEN.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def kids(node: list, name: str) -> list[list]:
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def kid(node: list, name: str) -> list | None:
    k = kids(node, name)
    return k[0] if k else None


def num(x) -> float:
    return float(x)


def r(x: float) -> float:
    return round(x, ROUND) + 0.0


def xy(node: list | None) -> tuple[float, float]:
    return (num(node[1]), num(node[2])) if node else (0.0, 0.0)


def net_name(node: list) -> str:
    n = kid(node, "net")
    if not n:
        return ""
    return n[-1] if len(n) > 1 else ""


def layers(node: list) -> tuple[str, ...]:
    ls = kid(node, "layers") or kid(node, "layer")
    return tuple(sorted(ls[1:])) if ls else ()


def pts(node: list | None) -> list[tuple[float, float]]:
    return [xy(p) for p in kids(node, "xy")] if node else []


def board(path: str) -> dict:
    root = parse(Path(path).read_text())
    out = {"footprints": [], "pads": [], "tracks": [], "vias": [], "fills": {}, "stackup": None}
    setup = kid(root, "setup")
    st = kid(setup, "stackup") if setup else None
    out["stackup"] = json.dumps(st) if st else None
    for fp in kids(root, "footprint"):
        lib = fp[1]
        at = kid(fp, "at")
        fx, fy = xy(at)
        frot = num(at[3]) if at and len(at) > 3 else 0.0
        side = (kid(fp, "layer") or [None, ""])[1]
        ref = next((p[2] for p in kids(fp, "property") if len(p) > 2 and p[1] == "Reference"), None)
        if ref is None:
            ref = next((t[2] for t in kids(fp, "fp_text") if len(t) > 2 and t[1] == "reference"), "?")
        models = []
        for m in kids(fp, "model"):
            models.append((m[1], tuple(r(num(v)) for v in (kid(kid(m, "offset") or [], "xyz") or [None, 0, 0, 0])[1:]),
                           tuple(r(num(v)) for v in (kid(kid(m, "rotate") or [], "xyz") or [None, 0, 0, 0])[1:])))
        c, s = math.cos(math.radians(frot)), math.sin(math.radians(frot))
        pads = []
        for p in kids(fp, "pad"):
            pat = kid(p, "at")
            lx, ly = xy(pat)
            prot = num(pat[3]) if pat and len(pat) > 3 else 0.0
            bx, by = fx + lx * c + ly * s, fy - lx * s + ly * c        # KiCad: y down, CCW rotation
            size = kid(p, "size")
            drill = kid(p, "drill")
            rec = {"ref": ref, "pad": p[1], "type": p[2], "shape": p[3], "x": r(bx), "y": r(by),
                   "rot": r((prot) % 360), "size": tuple(r(num(v)) for v in size[1:]) if size else (),
                   "drill": tuple(v if not re.match(r"^-?[\d.]+$", str(v)) else r(num(v)) for v in drill[1:]) if drill else (),
                   "layers": layers(p), "net": net_name(p)}
            pads.append(rec)
        out["pads"] += pads
        out["footprints"].append({"ref": ref, "lib": lib, "x": r(fx), "y": r(fy), "rot": r(frot % 360), "side": side,
                                  "models": models, "pad_xy": [(q["x"], q["y"]) for q in pads]})
    for seg in kids(root, "segment") + kids(root, "arc"):
        rec = {"kind": seg[0], "start": tuple(map(r, xy(kid(seg, "start")))), "end": tuple(map(r, xy(kid(seg, "end")))),
               "mid": tuple(map(r, xy(kid(seg, "mid")))) if kid(seg, "mid") else None,
               "width": r(num(kid(seg, "width")[1])), "layer": (kid(seg, "layer") or [None, ""])[1], "net": net_name(seg)}
        out["tracks"].append(rec)
    for v in kids(root, "via"):
        out["vias"].append({"at": tuple(map(r, xy(kid(v, "at")))), "size": r(num(kid(v, "size")[1])),
                            "drill": r(num(kid(v, "drill")[1])) if kid(v, "drill") else None,
                            "layers": layers(v), "net": net_name(v)})
    for z in kids(root, "zone"):
        net = (kid(z, "net_name") or [None, ""])[1]
        for fpoly in kids(z, "filled_polygon"):
            layer = (kid(fpoly, "layer") or [None, ""])[1]
            poly = Polygon(pts(kid(fpoly, "pts")))
            if not poly.is_valid:
                poly = poly.buffer(0)
            out["fills"].setdefault((net, layer), []).append(poly)
    out["fills"] = {k: unary_union(v) for k, v in out["fills"].items()}
    return out


def in_region(b: dict, region) -> dict:
    """Canonical record sets for everything touching the region."""
    hit = lambda *p: any(region.covers(Point(q)) for q in p)
    fps = {json.dumps({k: v for k, v in f.items() if k != "pad_xy"}, sort_keys=True)
           for f in b["footprints"] if any(hit(q) for q in f["pad_xy"])}
    pads = {json.dumps(p, sort_keys=True) for p in b["pads"] if hit((p["x"], p["y"]))}
    tracks = {json.dumps(t, sort_keys=True) for t in b["tracks"] if hit(t["start"], t["end"])}
    vias = {json.dumps(v, sort_keys=True) for v in b["vias"] if hit(v["at"])}
    fills = {k: g.intersection(region) for k, g in b["fills"].items() if g.intersects(region)}
    return {"footprints": fps, "pads": pads, "tracks": tracks, "vias": vias, "fills": fills}


def compare(a: dict, b: dict) -> dict:
    out = {}
    for key in ("footprints", "pads", "tracks", "vias"):
        gone, new = sorted(a[key] - b[key]), sorted(b[key] - a[key])
        if gone or new:
            out[key] = {"only_old": len(gone), "only_new": len(new),
                        "examples_old": [json.loads(x) for x in gone[:3]], "examples_new": [json.loads(x) for x in new[:3]]}
    fill_diff = []
    for k in sorted(set(a["fills"]) | set(b["fills"])):
        ga, gb = a["fills"].get(k), b["fills"].get(k)
        area = (ga.symmetric_difference(gb).area if ga is not None and gb is not None
                else (ga or gb).area)
        if area > AREA_TOL_MM2:
            fill_diff.append({"net": k[0], "layer": k[1], "changed_area_mm2": round(area, 3)})
    if fill_diff:
        out["zone_fills"] = fill_diff
    return out


def fet_flags(a: dict, b: dict) -> list[str]:
    fa = {f["ref"]: f for f in a["footprints"] if f["ref"] in FETS}
    fb = {f["ref"]: f for f in b["footprints"] if f["ref"] in FETS}
    flags = []
    for ref in sorted(set(fa) | set(fb)):
        x, y = fa.get(ref), fb.get(ref)
        if not x or not y:
            flags.append(f"{ref}: present in only one board")
            continue
        for key in ("lib", "models", "side"):
            if x[key] != y[key]:
                flags.append(f"{ref}: {key} changed ({x[key]!r} -> {y[key]!r}); check lead length / mounting height")
    return flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--legs", nargs="+", default=["A", "B"])
    ap.add_argument("--margin", type=float, default=20.0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    L = legs()
    bo, bn = board(a.old), board(a.new)
    res = {"old": a.old, "new": a.new, "margin_mm": a.margin, "stackup_changed": bo["stackup"] != bn["stackup"],
           "fet_flags": fet_flags(bo, bn), "legs": {}}
    for leg in a.legs:
        x0, y0, x1, y1 = L[leg]
        region = box(x0 - a.margin, y0 - a.margin, x1 + a.margin, y1 + a.margin)
        diff = compare(in_region(bo, region), in_region(bn, region))
        res["legs"][leg] = {"region_mm": [round(v, 3) for v in region.bounds],
                            "verdict": "CHANGED" if diff else "UNCHANGED", "differences": diff}
    ok = not res["stackup_changed"] and all(v["verdict"] == "UNCHANGED" for v in res["legs"].values())
    res["rerun_needed"] = not ok or bool(res["fet_flags"])
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    for leg, v in res["legs"].items():
        what = ", ".join(f"{k} ({d['only_old']}/{d['only_new']} old/new)" if isinstance(d, dict) else f"{k} ({len(d)})"
                         for k, d in v["differences"].items())
        print(f"leg {leg}: {v['verdict']}" + (f" - {what}" if what else "") + " -> " +
              ("rerun this leg's FEM" if v["verdict"] == "CHANGED" else "no FEM rerun"))
    if res["stackup_changed"]:
        print("STACKUP CHANGED: every leg needs a rerun")
    for f in res["fet_flags"]:
        print("FET:", f)
    print("RESULT " + json.dumps({k: res[k] for k in ("stackup_changed", "fet_flags", "rerun_needed")} |
                                 {"legs": {k: v["verdict"] for k, v in res["legs"].items()}}))
    sys.exit(2 if res["rerun_needed"] else 0)


if __name__ == "__main__":
    main()
