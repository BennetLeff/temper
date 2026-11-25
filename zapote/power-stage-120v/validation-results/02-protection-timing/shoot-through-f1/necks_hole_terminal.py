#!/usr/bin/env python3
"""Copper necks with the terminal at the HOLE, not at the pad land buffered 1 mm outward (independent review of s57, 2026-11-25).

    python3 -I necks_hole_terminal.py TAG [TAG ...]      -> <TAG>_necks_hole.json, assertion if a control fails

Why: f1_containment.py grows each terminal land by TERM_BUF = 1.0 mm so a press-fit pad's own annulus is never the neck. That
also swallows the plane corridor into a TO-247 drain land: the 5.45 mm pitch less two 3.2 mm voids leaves In2 (bus_p) and
B.Cu (sw_a / sw_b) 2.07 mm wide about 1.8 mm from the pin, inside the buffered terminal, and s21_necks.py reports 2.561.
s21_necks.py and its files are unchanged (they are the record of earlier decisions); this is the corrected measure.

Method: every drilled pad's hole is filled (soldered lead), the terminal is the disc of the hole, or the land for an SMD pad,
and the sw_a / sw_b segments s21_necks.py omits are added. Per layer the neck is the largest 2r at which the filled copper
eroded by r still joins both terminals. I2t is the same Onderdonk figure at Ta 105 C, per layer at that layer's own thickness
(best single layer governs); "conservative" uses 0.061 mm. Layers are NOT added together: one layer carries each path here
except where a via field is needed, which the s21 files cover. Parallel layers are reported, not credited.
"""
import gzip, importlib.util, json, math, sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fc", HERE / "f1_containment.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
F1 = fc.KLDR["KLDR025"][1]
SEG = [("bus_p", "BR1.1", "Q2.2"), ("bus_p", "BR1.1", "Q5.2"), ("sw_a", "Q2.3", "Q3.2"), ("sw_b", "Q5.3", "Q6.2"),
       ("leg_ret", "Q3.3", "R5.1"), ("leg_ret", "Q6.3", "R5.1"), ("hv_ret", "R5.4", "BR1.4"),
       ("l_filt", "L1.4", "BR1.2"), ("n_filt", "L1.3", "BR1.3")]


def geom(p):
    if p["kind"] == "track":
        return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2, cap_style="round")
    if p["kind"] == "via":
        return Point(p["centre"]).buffer(p["diameter_mm"] / 2)
    if p["kind"] == "pad":
        return Polygon(p["shell"])                                    # hole filled: soldered lead
    g = Polygon(p["shell"], p.get("holes") or [])
    return g if g.is_valid else g.buffer(0)


def drill_of(p):
    d = p.get("drill_mm")
    return (d if isinstance(d, (int, float)) else max(d or [0])) or 0


def necks(prims, seg):
    net, ta, tb = seg
    ps = [p for p in prims if p["net"] == net]
    layers = sorted({p["layer"] for p in ps if p["layer"] in fc.CU_T})
    cu = {l: unary_union([geom(p) for p in ps if p["layer"] == l]) for l in layers}

    def term(ref, l):
        c = [p for p in ps if p["kind"] == "pad" and p["ref"] == ref]
        assert c, (net, ref)
        c = c[0]
        on = any(q["layer"] == l and q["ref"] == ref for q in ps if q["kind"] == "pad")
        if not on:
            return None
        r = drill_of(c) / 2
        return Point(c["centre"]).buffer(r) if r else Polygon(next(q for q in ps if q["kind"] == "pad" and q["ref"] == ref and q["layer"] == l)["shell"])

    rows = {}
    for l in layers:
        A, B = term(ta, l), term(tb, l)
        if A is None or B is None:
            rows[l] = None
            continue

        def joined(r):
            e = cu[l].buffer(-r) if r else cu[l]
            for part in (list(e.geoms) if hasattr(e, "geoms") else [e]):
                if part.intersects(A) and part.intersects(B):
                    return True
            return False
        if not joined(0.0):
            rows[l] = None
            continue
        lo, hi = 0.0, 10.0
        for _ in range(14):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if joined(mid) else (lo, mid)
        w = 2 * lo
        rows[l] = {"neck_mm": round(w, 3), "I2t": round(fc.onderdonk_i2t(w * fc.CU_T[l], fc.TA_HOT), 1),
                   "ratio": round(fc.onderdonk_i2t(w * fc.CU_T[l], fc.TA_HOT) / F1, 3),
                   "ratio_0p061": round(fc.onderdonk_i2t(w * 0.061, fc.TA_HOT) / F1, 3)}
    best = max((r for r in rows.values() if r), key=lambda r: r["ratio"], default=None)
    return rows, best


def _control():
    """A 30 x 5 strip pinched to 2.0 mm between two 6 x 4 drilled lands reads 2.0; unpinched it reads the 4 mm land."""
    def strip(pinch):
        sh = [[0, 0], [30, 0], [30, 5], [0, 5]]
        holes = [[[14, -0.1], [16, -0.1], [16, (5 - pinch) / 2], [14, (5 - pinch) / 2]], [[14, 5.1], [16, 5.1], [16, (5 + pinch) / 2], [14, (5 + pinch) / 2]]] if pinch else []
        poly = Polygon(sh).difference(unary_union([Polygon(h) for h in holes])) if holes else Polygon(sh)
        z = {"kind": "zone", "net": "n", "layer": "In2.Cu", "shell": list(poly.exterior.coords), "holes": []}
        pads = [{"kind": "pad", "net": "n", "ref": r, "layer": "In2.Cu", "centre": [x, 2.5], "drill_mm": [1.8, 1.8],
                 "shell": [[x - 3, 0.5], [x + 3, 0.5], [x + 3, 4.5], [x - 3, 4.5]]} for r, x in (("A.1", 4), ("B.1", 26))]
        return [z] + pads
    return [necks(strip(w), ("n", "A.1", "B.1"))[1]["neck_mm"] for w in (2.0, 0)]


a, b = _control()
assert abs(a - 2.0) < 0.05 and b > 4.5, ("control failed", a, b)
for tag in sys.argv[1:]:
    raw = json.load(gzip.open(fc.PS / f"native-21/verification/native21{tag}-all-copper.json.gz"))
    prims, res = raw["primitives"], []
    for seg in SEG:
        rows, best = necks(prims, seg)
        res.append({"net": seg[0], "from": seg[1], "to": seg[2], "per_layer": rows, "best_single_layer": best,
                    "needs_via_field": best is None})
        print(f"{tag} {seg[0]:8s} {seg[1]:>6s} -> {seg[2]:5s} " + (f"{best['neck_mm']:.3f} mm ratio {best['ratio']:.3f} (0.061 mm: {best['ratio_0p061']:.3f})" if best else "no single layer (via field: s21 file)"))
    single = [r["best_single_layer"] for r in res if r["best_single_layer"]]
    (HERE / f"{tag}_necks_hole.json").write_text(json.dumps({"board_sha256": raw["board_sha256"], "F1_clearing_I2t": F1, "segments": res,
        "min_ratio_single_layer": min(r["ratio"] for r in single), "min_ratio_single_layer_0p061": min(r["ratio_0p061"] for r in single)}, indent=1) + "\n")
    print(tag, "min", min(r["ratio"] for r in single))
