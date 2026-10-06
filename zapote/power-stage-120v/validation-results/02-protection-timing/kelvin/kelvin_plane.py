#!/usr/bin/env python3
"""Kelvin-return error at the shunt-OCP threshold, including the In1 plane (native-19/20 copper).

Net `ocp_kelvin_p` (all its tracks, vias, pads and the In1 zone fill) is solved
with the committed kit sheet solver (`validation-plan/sim-kit/04-current/sheet_solver.py`)
at 125 C. 1 A is injected at R35.2 (the threshold divider's bottom pad) with
R5.2 (the shunt's Kelvin sense terminal) as the sink. By reciprocity, the
potential each pad then sits at, in mV per A, is the potential that 1 A
returned at that pad raises at R35.2. Hence for HOT-side return currents I_j:

    e_th = sum_j I_j * T_j  <=  I_total * max_j T_j

and the trip shifts by dI/de_th = -(2 - 2k)/Rs (k = R35/(R34+R35); about
-1.03 A per mV with R34 = 10.6 k, R35 = 10 k, Rs = 1 mOhm). A positive e_th lowers
the trip current, eating into the 44 A minimum.

Copper: the kit's thicknesses (70 um outer, 61 um inner); the 2 oz stackup
specifies more. Via plating 18 um (JLCPCB minimum class). Pads are injected
at their centres. Grid 0.1 mm. Input: the committed native-19 copper export
(board SHA-256 3557aa44..., copper byte-identical to native-20).

    python3 kelvin_plane.py  ->  plane-native20.json
"""
from __future__ import annotations

import gzip
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
PS = HERE.parents[2]
EXPORT = PS / "prototype-closure/round2/d17/evidence/extraction/native19-all-copper.json.gz"
spec = importlib.util.spec_from_file_location("kit", PS / "validation-plan/sim-kit/04-current/sheet_solver.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
NET, SINK, PROBE = "ocp_kelvin_p", "R5.2", "R35.2"
R34, R35, RS = 10.6e3, 10.0e3, 1e-3
PLATING_UM, PITCH, TEMP = 18.0, 0.1, 125.0


def main() -> None:
    data = json.load(gzip.open(EXPORT))
    assert data["board_sha256"] == "3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b"
    net = kit.Net(pitch_mm=PITCH, temp_c=TEMP)
    shapes, vias, pads = defaultdict(list), {}, {}
    for it in data["primitives"]:
        if it["net"] != NET:
            continue
        lay, kind = it["layer"], it["kind"]
        if kind in ("zone", "pad"):
            shapes[lay].append(Polygon(it["shell"], it["holes"]))
        elif kind == "track":
            shapes[lay].append(LineString([it["start"], it["end"]]).buffer(it["width_mm"] / 2, 16))
        elif kind == "via":
            shapes[lay].append(Point(it["centre"]).buffer(it["diameter_mm"] / 2, 32))
            v = vias.setdefault(tuple(it["centre"]), {"drill": it["drill_mm"], "layers": []})
            v["layers"].append(lay)
        if kind == "pad":
            assert max(it["drill_mm"]) == 0, "THT pad on the Kelvin net: handle as filled barrel"
            pads[it["ref"]] = (lay, *it["centre"])
    for lay, parts in shapes.items():
        g = unary_union(parts)
        polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        net.add_layer(lay, [list(p.exterior.coords) for p in polys], 70 if lay in ("F.Cu", "B.Cu") else 61,
                      [list(r.coords) for p in polys for r in p.interiors])
    for xy, v in vias.items():
        net.add_via(xy, v["drill"], PLATING_UM, v["layers"])
    sol = net.solve([(*pads[PROBE], 1.0)], [pads[SINK][:3]])
    T = {}
    for ref, (lay, x, y) in sorted(pads.items()):
        T[ref] = float(sol["v"][net._node(lay, x, y)]) * 1e3          # mV per A (= mOhm)
    k = R35 / (R34 + R35)
    a_per_mv = -(2 - 2 * k) / RS * 1e-3
    worst = max((r for r in T if r != SINK), key=lambda r: T[r])
    res = {"board_sha256": data["board_sha256"], "net": NET, "sink": SINK, "probe": PROBE,
           "pitch_mm": PITCH, "temp_C": TEMP, "plating_um": PLATING_UM, "thickness_um": {"outer": 70, "inner": 61},
           "transfer_mohm_to_R35_2": {r: round(v, 4) for r, v in T.items()},
           "R_eff_R35_2_mohm": round(T[PROBE], 4), "max_transfer": {"pad": worst, "mohm": round(T[worst], 4)},
           "trip_shift_A_per_mV_at_R35_2": round(a_per_mv, 4),
           "trip_shift_A_per_10mA_returned_bound": round(a_per_mv * 10e-3 * T[worst], 4),
           "unused_island_cells": sol["unused_island_cells"], "dropped_edges": sol["dropped_edges"]}
    (HERE / "plane-native20.json").write_text(json.dumps(res, indent=1) + "\n")
    for r, v in sorted(T.items(), key=lambda kv: -kv[1]):
        print(f"{r:7s} {v:8.3f} mOhm")
    print(json.dumps({k: res[k] for k in ("R_eff_R35_2_mohm", "max_transfer", "trip_shift_A_per_mV_at_R35_2",
                                          "trip_shift_A_per_10mA_returned_bound", "unused_island_cells")}))


if __name__ == "__main__":
    main()
