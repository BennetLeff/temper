"""Estimate controller outlines for the shrink options. ESTIMATES: packing factors are assumptions.

Read-only. Inputs: the C49 board (same file as measure_controller.py), results/controller-area.json,
results/native21-selv.json, and KiCad 10 library courtyards for the swap packages. Output:
results/shrink-options.json. Standard library only.

    python3 -I scripts/shrink_options.py

Method
- Required area = courtyard area / u + support-hole keep-outs. u is the board-level courtyard
  utilisation a packed layout reaches. Two values bracket it (PACKING): 0.35 and 0.45. Basis
  (see CONTROLLER.md): this board is 25.6 % and its own router closes 1 of 3 runs at that density
  (DECISIONS C50 addendum); its tight local clusters (3.3 V buck, AD8436, C39 detector) reach
  45-57 % hull density with no inter-block routing (controller-area.json blocks.*.hull_density_pct).
- Double-sided: area = max(top, bottom courtyard) / u. THT connectors, the module, magnetics,
  electrolytics, ICs with more than 8 pins and the whole RTD block (C34 keeps its analog nets on
  F.Cu / In2.Cu) stay on top; other parts may go to the bottom, balanced greedily.
- Outlines are shown at the current 76 mm depth and at a 4:3 aspect. They are areas, not layouts.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kicad_courtyard as kc  # noqa: E402
import measure_controller as mc  # noqa: E402

KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PACKING = (0.35, 0.40, 0.45)
HOLE_KEEPOUT_D = 8.0
SMALL_BOARD_HOLES = 4
# ESP32-S3-MINI-1U: 15.4 x 15.4 x 2.4 mm (Espressif ESP32-S3-MINI-1/1U datasheet v1.7, Table 1-1);
# courtyard = body + 0.25 mm each side, the same rule LAYOUT.md uses for the WROOM courtyard.
MINI_1U_CRTYD = (15.4 + 0.5) ** 2
LOCKED_PREFIXES = ("thermal.", "interlock.", "rtd_pan.")      # ported / byte-locked blocks (README "ported unchanged", C37)
PRECISION_MPN = ("RT0603B", "RT0805B", "ERA-", "RG2012", "RG1608")  # 0.1 % / 0.05 % thin film: keep the package


def lib_crtyd(rel):
    loops, _, _ = kc._local_courtyard(kc.load(KICAD_FP / rel))
    return sum(kc.shoelace(l) for l in loops)


def outlines(area):
    depth = 76.0
    w43 = math.sqrt(area * 4 / 3)
    return {"area_mm2": round(area), "at_76mm_depth": [round(area / depth, 1), depth],
            "at_4_3": [round(w43, 1), round(area / w43, 1)]}


def stays_top(f):
    lib = f["lib"].split(":")[-1]
    if "through_hole" in f["attr"] or f["ref"].startswith(("J", "L")) or f["path"] == "mcu":
        return True
    if lib.startswith("CP_Elec"):
        return True
    if (f["path"] or "").startswith("rtd_pan."):
        return True
    npads = len({p["num"] for p in f["pads"] if p["num"]})
    return npads > 8


def main():
    base = json.loads((HERE.parent / "results" / "controller-area.json").read_text())
    n21 = json.loads((HERE.parent / "results" / "native21-selv.json").read_text())
    board = kc.load(Path(base["board_file"]))
    fps = kc.footprints(board)
    crt = sum(f["crtyd_area_mm2"] for f in fps)
    hole_ko = math.pi * (HOLE_KEEPOUT_D / 2) ** 2

    a0402 = {"C": lib_crtyd("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod"),
             "R": lib_crtyd("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod")}
    cp63 = lib_crtyd("Capacitor_SMD.pretty/CP_Elec_6.3x5.8.kicad_mod")

    # ---- part-level savings (option D)
    sw = {"0603_to_0402": {"count": 0, "saved_mm2": 0.0, "kept_locked": 0, "kept_precision": 0}}
    for f in fps:
        lib = f["lib"].split(":")[-1]
        if "_0603_" not in lib:
            continue
        p = f["path"] or ""
        if p.startswith(LOCKED_PREFIXES):
            sw["0603_to_0402"]["kept_locked"] += 1
            continue
        if (f["value"] or "").startswith(PRECISION_MPN):
            sw["0603_to_0402"]["kept_precision"] += 1
            continue
        kind = "C" if lib.startswith("C_") else "R"
        sw["0603_to_0402"]["count"] += 1
        sw["0603_to_0402"]["saved_mm2"] += f["crtyd_area_mm2"] - a0402[kind]
    u4 = next(f for f in fps if f["ref"] == "U4")
    sw["wroom1u_to_mini1u"] = {"saved_mm2": u4["crtyd_area_mm2"] - MINI_1U_CRTYD,
                               "from_mm2": u4["crtyd_area_mm2"], "to_mm2": MINI_1U_CRTYD}
    caps = [f for f in fps if f["lib"].split(":")[-1].startswith("CP_Elec_8x6.2")]
    sw["cp8x6p2_to_6p3x5p8"] = {"count": len(caps), "saved_mm2": sum(f["crtyd_area_mm2"] - cp63 for f in caps),
                                "note": "needs a 100 uF / 25 V part in the 6.3 mm can with the same ripple rating [UNVERIFIED]"}
    for v in sw.values():
        v["saved_mm2"] = round(v["saved_mm2"], 1)
    d_saved = sum(v["saved_mm2"] for v in sw.values())

    # ---- double-sided split
    top = [f for f in fps if stays_top(f)]
    movable = sorted([f for f in fps if not stays_top(f)], key=lambda f: -f["crtyd_area_mm2"])
    t_area = sum(f["crtyd_area_mm2"] for f in top)
    b_area = 0.0
    bottom = []
    for f in movable:                       # greedy balance: bottom only while it stays the smaller side
        if b_area + f["crtyd_area_mm2"] <= t_area:
            b_area += f["crtyd_area_mm2"]
            bottom.append(f)
        else:
            t_area += f["crtyd_area_mm2"]
    split = {"top_mm2": round(t_area, 1), "bottom_mm2": round(b_area, 1), "bottom_parts": len(bottom),
             "top_parts": len(fps) - len(bottom)}

    # with option D on the double-sided split: 0402 and the 6.3 mm caps are mostly bottom/top resp.;
    # apply the module and electrolytic savings to the top, the 0402 savings to the bottom (bounded)
    t_d = t_area - sw["wroom1u_to_mini1u"]["saved_mm2"] - sw["cp8x6p2_to_6p3x5p8"]["saved_mm2"]
    b_d = max(0.0, b_area - sw["0603_to_0402"]["saved_mm2"])

    opts = {}
    for u in PACKING:
        key = f"u={u:.2f}"
        holes = SMALL_BOARD_HOLES * hole_ko
        opts.setdefault("A_single_sided_harnessed", {})[key] = outlines(crt / u + holes)
        opts.setdefault("A+D_single_sided_part_swaps", {})[key] = outlines((crt - d_saved) / u + holes)
        opts.setdefault("B_double_sided", {})[key] = outlines(max(t_area, b_area) / u + holes)
        opts.setdefault("B+D_double_sided_part_swaps", {})[key] = outlines(max(t_d, b_d) / u + holes)

    # ---- the 80 x 60 hypothesis: utilisation it would need
    target = 80.0 * 60.0 - SMALL_BOARD_HOLES * hole_ko
    hyp = {"area_mm2": 4800, "usable_after_4_holes_mm2": round(target, 1),
           "u_needed_single_sided": round(crt / target, 3),
           "u_needed_single_sided_with_D": round((crt - d_saved) / target, 3),
           "u_needed_double_sided": round(max(t_area, b_area) / target, 3),
           "u_needed_double_sided_with_D": round(max(t_d, b_d) / target, 3)}

    # ---- recommended concrete cut: keep the left part of today's outline (same depth, same rear/front
    #      edges, same left edge), so the landings and holes in it stay where the enclosure has them.
    #      Right edge at X93: J13's body (centre X88, 7.86 mm along X, JST eVH p.3) ends at X91.9.
    cut = {"world_x": [-38.0, 93.0], "world_y": [14.0, 90.0]}
    w, h = cut["world_x"][1] - cut["world_x"][0], cut["world_y"][1] - cut["world_y"][0]
    holes_in = [hh["world_xy"] for hh in base["holes"] if cut["world_x"][0] < hh["world_xy"][0] < cut["world_x"][1]]
    conn = base["connector_pin1_world_xy"]
    kept = sorted(r for r, (x, _) in conn.items() if cut["world_x"][0] - 1 <= x <= cut["world_x"][1] - 4)
    moved = sorted(r for r in conn if r not in kept) + ["U4 (WROOM box X141-159)"]
    usable = w * h - len(holes_in) * hole_ko
    only0402 = sw["0603_to_0402"]["saved_mm2"]
    cut.update({"outline_mm": [w, h], "area_mm2": w * h, "holes_kept": holes_in,
                "landings_kept": kept, "landings_moved": moved,
                "u_needed_as_is": round(crt / usable, 3),
                "u_needed_with_0402": round((crt - only0402) / usable, 3),
                "u_needed_with_all_D": round((crt - d_saved) / usable, 3)})

    # ---- option C: onto native-21's SELV island
    j4 = next(f for f in fps if f["ref"] == "J4")
    ctrl_on_n21 = crt - j4["crtyd_area_mm2"]           # the controller's J4 goes; native-21's own J4 also goes
    lo, hi = n21["selv_island_occupied_crtyd_mm2_bound"]
    isl = n21["selv_island_largest_outline_mm2"]
    c_opt = {"controller_crtyd_without_J4_mm2": round(ctrl_on_n21, 1),
             "island_outline_mm2": isl, "island_occupied_mm2_range": [lo, hi],
             "island_utilisation_if_merged_pct_range": [round(100 * (ctrl_on_n21 + lo) / isl, 1),
                                                         round(100 * (ctrl_on_n21 + hi) / isl, 1)]}
    for u in PACKING:
        need = (ctrl_on_n21 + lo) / u, (ctrl_on_n21 + hi) / u
        c_opt[f"island_needed_mm2_u={u:.2f}"] = [round(need[0]), round(need[1])]
        c_opt[f"island_growth_mm2_u={u:.2f}"] = [round(max(0, need[0] - isl)), round(max(0, need[1] - isl))]
        c_opt[f"native21_area_growth_pct_u={u:.2f}"] = [round(100 * max(0, need[0] - isl) / n21["board_area_mm2"], 1),
                                                       round(100 * max(0, need[1] - isl) / n21["board_area_mm2"], 1)]

    out = {
        "schema": "temper.board-shrink-r1.shrink-options.v1",
        "ESTIMATE": True,
        "packing_u": PACKING,
        "crtyd_total_mm2": round(crt, 1),
        "hole_keepout_each_mm2": round(hole_ko, 1), "small_board_holes": SMALL_BOARD_HOLES,
        "library_crtyd_mm2": {"C_0402": round(a0402["C"], 3), "R_0402": round(a0402["R"], 3),
                              "CP_Elec_6.3x5.8": round(cp63, 3), "ESP32-S3-MINI-1U (body+0.25)": round(MINI_1U_CRTYD, 1)},
        "part_swaps_D": sw, "part_swaps_D_total_saved_mm2": round(d_saved, 1),
        "double_sided_split": split, "double_sided_split_with_D": {"top_mm2": round(t_d, 1), "bottom_mm2": round(b_d, 1)},
        "options": opts,
        "hypothesis_80x60": hyp,
        "recommended_left_cut": cut,
        "option_C_native21": c_opt,
        "current": {"area_mm2": base["board_area_mm2"], "outline_mm": base["outline_mm"],
                    "utilisation_pct": base["utilisation_pct_of_board"]},
    }
    (HERE.parent / "results" / "shrink-options.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
