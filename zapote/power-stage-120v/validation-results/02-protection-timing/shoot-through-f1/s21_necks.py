#!/usr/bin/env python3
"""Stage 21 copper necks (DECISIONS 25): the f1_containment neck method, unchanged, on the stage-21 copper, whose
rectifier feeds BUS_P / HV_RET directly (no J7-J10). Segments that ran to the studs now run to BR1's DC pins.

    python3 -I s21_necks.py   ->  s21_necks.json
"""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fc", HERE / "f1_containment.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
fc.SEGMENTS = [s for s in fc.SEGMENTS if s[0] not in ("rect_p", "rect_n", "bus_p", "hv_ret")] + [
    ("bus_p", "BR1.1", "Q2.2", "BR1 + -> Q2 drain (leg A)"),
    ("bus_p", "BR1.1", "Q5.2", "BR1 + -> Q5 drain (leg B)"),
    ("hv_ret", "R5.4", "BR1.4", "shunt R5 -> BR1 -"),
]
# via fields with the ACTUAL drills (f1_containment assumes 0.3 mm for every via): barrel I2t ~ area^2, and with current
# shared in proportion to barrel area the field fuses at k * (sum of areas)^2, k = single-via I2t / area^2
import gzip, math
_raw = json.load(gzip.open(fc.PS / "native-21/verification/native21s21-all-copper.json.gz"))
def field_i2t(net, xy, reach=6.0):
    seen, areas = set(), []
    for p in _raw["primitives"]:
        if p["kind"] == "via" and p["net"] == net and math.dist(p["centre"], xy) <= reach and tuple(p["centre"]) not in seen:
            seen.add(tuple(p["centre"]))
            ri = p["drill_mm"] / 2
            areas.append(math.pi * ((ri + fc.VIA_PLATE) ** 2 - ri ** 2))
    a0, i0 = fc.barrel_i2t(fc.TA_HOT)
    return len(areas), i0 / a0 ** 2 * sum(areas) ** 2
sha, segs = fc.copper_necks("21", "native-21/verification/native21s21-all-copper.json.gz", None)
f1c = fc.KLDR["KLDR025"][1]
out = {"board_sha256": sha, "F1_clearing_I2t": f1c, "segments": segs}
for sg in segs:
    if sg.get("via_field_I2t_equal_sharing"):
        term = sg["from"] if sg["from"].startswith("R5") else sg["to"]
        pad = {"R5.4": [38.5, 15.2], "R5.1": [38.5, 10.0]}.get(term)
        if pad:
            n, val = field_i2t(sg["net"], pad)
            sg["via_field_actual_drills"] = {"count": n, "I2t": round(val, 1)}
def lim(s):   # the governing figure: the conductor neck, or the via field (actual drills) when the route needs a via hop
    v = [s.get("conductor_I2t_conservative", s["I2t_conservative"]) if s.get("via_field_actual_drills") else s["I2t_conservative"]]
    if s.get("route_needs_via_hop") or s.get("via_field_actual_drills"):
        f = s.get("via_field_actual_drills", {}).get("I2t") or s.get("via_field_I2t_equal_sharing")
        if f:
            v.append(f)
    return min(v)
real = [s for s in segs if "terminal" not in s["classification"]]
for s in segs:
    print(f'{s["segment"]:30s} {s["net"]:8s} neck {s["neck_width_mm"]:6.3f} mm  governing I2t {lim(s):8.0f}  '
          f'via-field {s.get("via_field_actual_drills")}  {s["classification"]}  at {s.get("neck_location_xy_mm")} {s.get("neck_layer")}')
worst = min(segs, key=lim)
worst_real = min(real, key=lim) if real else None
out["min_ratio_all"] = round(lim(worst) / f1c, 3)
out["min_ratio_conductor"] = round(lim(worst_real) / f1c, 3) if worst_real else None
print("min ratio (all rows):", out["min_ratio_all"], worst["segment"], "| conductor rows only:", out["min_ratio_conductor"],
      worst_real["segment"] if worst_real else "")
json.dump(out, open(HERE / "s21_necks.json", "w"), indent=1)
