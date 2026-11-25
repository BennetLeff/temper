#!/usr/bin/env python3
"""Desk scope for OPEN-ITEMS S33: can F.Cu be a second layer into the drain pins Q2.2 / Q5.2 / Q3.2 / Q6.2? Draws no copper.

    python3 drain_feed_scope.py      -> ../scope.json

Candidates: an F.Cu tongue as wide as the plane corridor from the pin to dy L, with rows of three 0.6 / 0.3 vias down to the
layer that feeds the pin (In2 bus_p; B.Cu sw): A six vias, L 4.0; B six, L 3.5; C three, L 2.95;
D is A with the snubber pads C12.2 / C13.2 / C19.2 / C20.2 ignored, as if those capacitors moved. Measured with rules21's own
clearances:
  tongue   worst (distance - rule) to other-net F.Cu copper; negative = the candidate breaks the rule
  vias     per layer, worst (distance - rule) to other-net non-zone copper, and how far each zone's void would have to grow
  I2t      Onderdonk on the two 2.052 mm sections together, and on the via field carrying F.Cu's share by section
It is a screen: no refill, no DRC, no thermal or return-path check."""
import gzip, importlib.util, json, math, sys
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
H = Path(__file__).resolve().parent
PS = H.parents[3]
sys.path.insert(0, str(PS / "native-21/layout"))
import rules21
s = importlib.util.spec_from_file_location("fc", PS / "validation-results/02-protection-timing/shoot-through-f1/f1_containment.py")
fc = importlib.util.module_from_spec(s); s.loader.exec_module(fc)
raw = json.load(gzip.open(PS / "native-21/verification/native21s57-all-copper.json.gz"))
P = raw["primitives"]
W, F1 = 2.052, fc.KLDR["KLDR025"][1]


def geom(p):
    if p["kind"] == "track":
        return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2)
    if p["kind"] == "via":
        return Point(p["centre"]).buffer(p["diameter_mm"] / 2)
    return Polygon(p["shell"], p.get("holes") or []).buffer(0)


CAND = {"A": (4.0, (2.8, 3.6)), "B": (3.5, (2.55, 3.2)), "C": (2.95, (2.65,)), "D": (4.0, (2.8, 3.6))}
SNUB = {"C12.2", "C13.2", "C19.2", "C20.2"}
out = {"board_sha256": raw["board_sha256"], "pins": {}}
for cand, pin in [(c, q) for c in CAND for q in ("Q2.2", "Q5.2", "Q3.2", "Q6.2")]:
    LEN, ROWS = CAND[cand]
    pad = next(p for p in P if p["kind"] == "pad" and p.get("ref") == pin and p["layer"] == "F.Cu")
    (x, y), net = pad["centre"], pad["net"]
    feed = "In2.Cu" if net == "bus_p" else "B.Cu"
    tongue = box(x - W / 2, y, x + W / 2, y + LEN)
    vias = [Point(x + dx, y + dy).buffer(0.3) for dx in (-0.72, 0, 0.72) for dy in ROWS]
    near = [(p, geom(p)) for p in P if p["net"] != net and not (cand == "D" and p.get("ref") in SNUB) and abs(p.get("centre", [x])[0] - x) < 60]
    t = min(((g.distance(tongue) - rules21.clearance_on(net, p["net"], "F.Cu"), p.get("ref") or p["kind"], p["net"])
             for p, g in near if p["layer"] == "F.Cu" and p["kind"] != "zone"), key=lambda r: r[0])
    v = {}
    for l in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        rows = [(min(g.distance(k) for k in vias) - rules21.clearance_on(net, p["net"], l), p["kind"], p.get("ref") or "", p["net"])
                for p, g in near if p["layer"] == l and g.distance(Point(x, y + 3)) < 14]
        fixed = min([r for r in rows if r[1] != "zone"], default=None, key=lambda r: r[0])
        zone = min([r for r in rows if r[1] == "zone"], default=None, key=lambda r: r[0])
        v[l] = {"fixed_copper_margin_mm": None if fixed is None else [round(fixed[0], 3), *fixed[1:]],
                "zone_void_growth_mm": None if zone is None else [round(max(0.0, -zone[0]), 3), zone[3]]}
    tf, tl = fc.CU_T["F.Cu"], fc.CU_T[feed]
    both = fc.onderdonk_i2t(W * (tf + tl), fc.TA_HOT) / F1
    a = math.pi * ((0.15 + fc.VIA_PLATE) ** 2 - 0.15 ** 2)
    share = tf / (tf + tl)
    via = fc.onderdonk_i2t(3 * len(ROWS) * a, fc.TA_HOT) / (F1 * share ** 2)
    out["pins"][cand + " " + pin] = {"net": net, "feed_layer": feed, "tongue_margin_mm": [round(t[0], 3), t[1], t[2]], "vias": v,
                        "ratio_two_layers": round(both, 3), "ratio_via_field": round(via, 3)}
    print(cand, pin, net, "tongue", out["pins"][cand + " " + pin]["tongue_margin_mm"], "two-layer", round(both, 2), "vias", round(via, 2))
    print("    fixed copper margin", min(r["fixed_copper_margin_mm"][0] for r in v.values()), "worst void growth", max((r["zone_void_growth_mm"] or [0])[0] for r in v.values()))
(H.parent / "scope.json").write_text(json.dumps(out, indent=1) + "\n")
