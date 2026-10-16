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

Copper: 70 um outer, 61 um inner and the copper z, read from the board's stackup.json
(stage 33; they were the kit's literals); the 2 oz stackup specifies more. Via plating 18 um (JLCPCB minimum class). Pads are injected
at their centres. Grid 0.1 mm. Input: the committed native-19 copper export
(board SHA-256 3557aa44..., copper byte-identical to native-20).

    python3 kelvin_plane.py  ->  plane-native20.json
    python3 kelvin_plane.py EXPORT.json.gz TAG  ->  plane-TAG.json   (another board's copper export)
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys
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
# From stage 13 the divider is 12.4 k / 11.7 k (stocked 0.1 % parts, BOM simplification 2026-10-09;
# ../../08-manufacturing-package/native-21/bom-simplification/). k changes from 0.48544 to 0.48548.
DIVIDER = {"native21s13": (12.4e3, 11.7e3), "native21s13b": (12.4e3, 11.7e3), "native21s14": (12.4e3, 11.7e3),
           "native21s15": (12.6e3, 11.7e3), "native21s15b": (12.6e3, 11.7e3),
           "native21s16": (12.6e3, 11.7e3), "native21s17": (12.6e3, 11.7e3),
           "native21s17b": (12.6e3, 11.7e3), "native21s18": (12.6e3, 11.7e3),
           "native21s19": (12.6e3, 11.7e3), "native21s19b": (12.6e3, 11.7e3), "native21s19c": (12.6e3, 11.7e3), "native21s20": (12.6e3, 11.7e3), "native21s21": (12.6e3, 11.7e3), "native21s21b": (12.6e3, 11.7e3), "native21s22": (12.6e3, 11.7e3), "native21s26": (12.6e3, 11.7e3), "native21s27": (12.6e3, 11.7e3), "native21s28": (12.6e3, 11.7e3), "native21s29": (12.6e3, 11.7e3), "native21s30": (12.6e3, 11.7e3), "native21s31": (12.6e3, 11.7e3), "native21s32": (12.6e3, 11.7e3), "native21s33": (12.6e3, 11.7e3), "native21s35": (12.6e3, 11.7e3), "native21s38": (12.6e3, 11.7e3), "native21s40": (12.6e3, 11.7e3), "native21s41": (12.6e3, 11.7e3), "native21s42": (12.6e3, 11.7e3), "native21s43": (12.6e3, 11.7e3), "native21s44": (12.6e3, 11.7e3), "native21s45": (12.6e3, 11.7e3)}   # stage 15, 28 A hardware (DECISIONS 2026-10-10)
PLATING_UM, PITCH, TEMP = 18.0, 0.1, 125.0


def thickness_summary(t_um: dict) -> dict:
    """{"outer": um, "inner": um} as recorded since stage 6; refuses a stack whose outer (or inner) layers differ."""
    names = list(t_um)
    outer, inner = {t_um[names[0]], t_um[names[-1]]}, {t_um[n] for n in names[1:-1]}
    if len(outer) != 1 or len(inner) != 1:
        raise ValueError(f"per-layer copper thicknesses {t_um}: record them per layer")
    return {"outer": outer.pop(), "inner": inner.pop()}


def main() -> None:
    export, tag = (Path(sys.argv[1]), sys.argv[2]) if len(sys.argv) > 2 else (EXPORT, "native20")
    data = json.load(gzip.open(export))
    # the committed native-19/20 export is pinned; another board's export carries its own hash
    PINNED = {"native20": "3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b",
              "native21": "76ec8ccae6ca0dbd145b672abc3d18a8f8132875e567cb31ab84325d897a1715",
              "native21s6": "387b753a8d1b8b1097406e9d6643daf21263e44b7ad76becb79edcc5cd46ecda",
              "native21s8": "d4468ffd355d6d4a4d6d35ed902019698c9c43e503443fd60fdd81b7d345a5ba",
              "native21s9": "e9d1cc4fb1353a79692354a1be93083c4fb12b1842d9dd9b109fd48949dd443e",
              "native21s10": "ef993141572fa93ad593c1d0d7fb07424c6e90af78b8bb277e57a48e1887b6df",
              "native21s11": "e85a4c829ccfade2df791d7890856fc6ca2a86a9df3fbe8cc5ed17ea5fb798ac",
              "native21s12": "fc3863213b670163e4d4e78685b91683afdb9992a02ee59f8a8a12b142bc00ee",
              "native21s13": "d7baa28a9ed9173bcc32eb1184f7424ccfd1736eae6b42885c0284d6d94a6905",
              "native21s13b": "6556f53612f4623e729360190ca06a9bbeeedc445e4a2ae26288433b76471a37",
              "native21s14": "3eb5421677007d9a06d682c5182d9e9fc264e4a50da9e51bbe354a2cedd0dcee",
              "native21s15": "5b9dbd612d2909c04e393a2273b0cf009e763f609d7e81e03bcbcc9988737fbc",
              "native21s15b": "9a9c43c63f63d383c89b9dc1d4d03a34d4390cfa1c26bbe802d71e169c6ddf94",
              "native21s16": "e9481ed6d183594a466d657bff09de525ad84457cbd13080a55b1b589b314bcd",
              "native21s17": "e40f1e275bbaff8a5e61e224974fd401a44bcad2acefa0b92d50f85b6ce81ecd",
              "native21s17b": "96501e7d0e9b4903a145aa3bd0e45003a4fafe37ceef5259a7502bc9b11225a9",
              "native21s18": "3768a12675f8d61f91fc4a96dd267522e68f454f8f300634aca2ae16afc6dd1a",
              "native21s19": "370fcf373c97241966f0bb9a077b513903354a20bcd659545819e9d363b3bd1c",
              "native21s19b": "b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662",
              "native21s19c": "3d3a2c69c07a210262f0dc66789a2631e29370f6816c45869a7dea1813460d92",
              "native21s20": "2d5a4b05a9a1e627132e4372cac5065d1ad72b19efd45a8b7b9e22c8de1b7acd",
              "native21s21": "fac94215369b6c285472a98e4cc255def9739f19fe2cf43e3439f6884e2bcae3",
              "native21s21b": "c015804959add81e948055279cb78946e3a762ac9077c0b21bfbde3c89d0cb56",
              "native21s22": "cab63cec89dbd3e5111467373d461759e6a4bc49cc1a929f5d05964d65efaba6",
              "native21s26": "d9eb6e9eef70577ef40b5c7ba54be91a5c217a1639b185f96ff6f56b190bbf24",
              "native21s27": "44644390f1ee41760407400ac4a620d97512e388c9902c625c50d84a37dfd124",
              "native21s28": "e3fe94099405ebcf2cccdd49695c969cad9473455cca3cc4df234a4a8ab323c6",
              "native21s29": "3ae1ddb47c8c4c4e7c26c663ce54248c8797651e0066dc3bf516225403cba128",
              "native21s30": "4fcae4bf8971718d38fc2fc9cb257e2ec044de2914e6f31d2df0204b1736ddfd",
              "native21s31": "5ef1c37a41914825db33138bbbf765390b1fa5ae9ea4391b45c92fc8c2854bad",
              "native21s32": "2fb346dc8277e4295d8ef88effabdcc71dcd363fcaa93604800ddc2872fbfa4e",
              "native21s33": "710c0a45c2b1c900dc3778f9ffadaf218f374df64237f7e3a2ccb384a549ff2a",
              "native21s35": "fba59ef3d8169ee71a81a08d29c72f4e76acf8f420c91fd2515227adaabc8be4",
              "native21s38": "b5bf428d2ff59574027fae92f248996804fdabb4363d479d3ea7c30762b09983",
              "native21s40": "33ed17f3ad50289edeba11ac1ac008680bcc2e307b660043fc324a0118c4c900",
              "native21s41": "d4b2445ce1ca47801271c2ac34843b10134cd6c509c158a6f570718b8b91cd57",
              "native21s42": "9e075b4b90320e1e19c7b9740278715a4dabe6c80779fe8082a5bb844083ef86",
              "native21s43": "61447816b9dd4921525b4f610aca40486989964368d69abb17bf7071cbf4d8df",
              "native21s44": "2a84051f251e03a3206e99fdef4bb48e7862c233bcbdf344e61b09952e423136",
              "native21s45": "a1e6488f72c6af95a971182d6b024a157339a5a983f29e264f7715f1ae6c0199"}
    assert data["board_sha256"] == PINNED[tag], f"{export} is not the pinned {tag} board"
    # stage 33: copper z and thickness from the board's stackup.json (the native-20 export: native-20's; every
    # native21* tag: native-21's single layer-stack source). Same 70 / 61 um and JLC041622-7628 z as the old literals.
    stack = kit.stackup_layers(PS / "native-20/stackup.json" if tag == "native20" else
                               os.environ.get("NATIVE21_STACKUP") or PS / "native-21/stackup.json")
    net = kit.Net(pitch_mm=PITCH, temp_c=TEMP, layer_z_mm=stack["z_mm"])
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
            if it["ref"].startswith("TP"):
                continue    # bring-up test pad: copper kept above, but a probe returns no current, and it sits on a via drill
            assert max(it["drill_mm"]) == 0, "THT pad on the Kelvin net: handle as filled barrel"
            pads[it["ref"]] = (lay, *it["centre"])
    for lay, parts in shapes.items():
        g = unary_union(parts)
        polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        net.add_layer(lay, [list(p.exterior.coords) for p in polys], stack["t_um"][lay],
                      [list(r.coords) for p in polys for r in p.interiors])
    for xy, v in vias.items():
        net.add_via(xy, v["drill"], PLATING_UM, v["layers"])
    sol = net.solve([(*pads[PROBE], 1.0)], [pads[SINK][:3]])
    T = {}
    for ref, (lay, x, y) in sorted(pads.items()):
        T[ref] = float(sol["v"][net._node(lay, x, y)]) * 1e3          # mV per A (= mOhm)
    r34, r35 = DIVIDER.get(tag, (R34, R35))
    k = r35 / (r34 + r35)
    a_per_mv = -(2 - 2 * k) / RS * 1e-3
    worst = max((r for r in T if r != SINK), key=lambda r: T[r])
    res = {"board_sha256": data["board_sha256"], "net": NET, "sink": SINK, "probe": PROBE,
           "pitch_mm": PITCH, "temp_C": TEMP, "plating_um": PLATING_UM, "thickness_um": thickness_summary(stack["t_um"]),
           "transfer_mohm_to_R35_2": {r: round(v, 4) for r, v in T.items()},
           "R_eff_R35_2_mohm": round(T[PROBE], 4), "max_transfer": {"pad": worst, "mohm": round(T[worst], 4)},
           "trip_shift_A_per_mV_at_R35_2": round(a_per_mv, 4),
           "trip_shift_A_per_10mA_returned_bound": round(a_per_mv * 10e-3 * T[worst], 4),
           "unused_island_cells": sol["unused_island_cells"], "dropped_edges": sol["dropped_edges"]}
    (HERE / f"plane-{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
    for r, v in sorted(T.items(), key=lambda kv: -kv[1]):
        print(f"{r:7s} {v:8.3f} mOhm")
    print(json.dumps({k: res[k] for k in ("R_eff_R35_2_mohm", "max_transfer", "trip_shift_A_per_mV_at_R35_2",
                                          "trip_shift_A_per_10mA_returned_bound", "unused_island_cells")}))


if __name__ == "__main__":
    main()
