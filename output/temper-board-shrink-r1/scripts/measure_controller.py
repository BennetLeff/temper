"""Measure the C49 controller board: courtyard area, utilisation, per-block breakdown, block packing.

Read-only. Input: the committed C49 board (ORDER.md sha256 b3af25b8...). Output:
results/controller-area.json. Standard library only.

    python3 -I scripts/measure_controller.py [path/to/controller.kicad_pcb]
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kicad_courtyard as kc  # noqa: E402

DEFAULT_PCB = Path("/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller/pcb/controller.kicad_pcb")
EXPECTED_SHA = "b3af25b892858e0c89624ed72ce207e9e1f25d6429aaed4f7814804229f8b1bb"   # ORDER.md, C49 board
OX, OY = 58.0, 110.0          # layout/world.py: kx = X + OX, ky = OY - Y
HOLE_KEEPOUT_D = 8.0          # layout/world.py HOLE_KEEPOUT_D

# --------------------------------------------------------------------------- blocks
# Assignment by atopile instance path (SourceInstance). Order matters: first match wins.
# Basis: README.md "Layout of the unit", LAYOUT.md "Floorplan", floorplan.py ANCHOR comments,
# ENCLOSURE-HANDOFF.md "Placement-critical parts".
BLOCKS: list[tuple[str, str, object]] = [
    ("connectors", "J1-J13 (incl. J4 Micro-Fit, J7 12-way UI, J13 VH, J11 TC2050 land)",
     lambda p, r: r.startswith("J")),
    ("mcu", "ESP32-S3-WROOM-1U U4 + decoupling, EN RC, UI CS pull-ups, strap pull-down",
     lambda p, r: p in {"mcu", "c_mcu_bulk", "c_mcu_hf", "c_en", "r_en", "r_dc_pd", "r_cs_oled_pu", "r_cs_exp_pu"}),
    ("buck_3v3", "3.3 V buck U1/L1 (TPS62933F) and its passives, v15 bulk",
     lambda p, r: p in {"u_3v3", "l_3v3", "c_in_bulk", "c_ss_3v3", "c_bst_3v3", "c_in3a", "c_in3b", "c_out3a",
                        "c_out3b", "c_out3c", "r_en3_top", "r_en3_bot", "r_fb3_top", "r_fb3_bot"}),
    ("blower_buck", "Blower buck U2/L2 (TPS62933 + SWRB1205S), PS3 bulk, speed injection, FAN_OFF, BLW_PG, tach, J13 merge diode",
     lambda p, r: p in {"u_12", "l_12", "c_blw_bulk", "c_ss_12", "c_bst_12", "c_in12a", "c_in12b", "c_in12c",
                        "c_out12a", "c_out12b", "r_en12_top", "r_en12_bot", "r_fb12_top", "r_fb12_bot", "r_fan_inj",
                        "c_fan_ctl", "r_fan_pwm_filt", "r_fan_pwm_pd", "q_fan_off", "r_fan_off_pd", "r_blw_pg_top",
                        "r_blw_pg_bot", "r_tach_pu", "r_tach_series", "c_tach", "d_tach", "d_merge"}),
    ("rtd", "RTD front end (rtd_pan.*: MAX31865, REF2025, windows, TPS389001, Rref, CR-1 filter + J3 TVS)",
     lambda p, r: p.startswith("rtd_pan.")),
    ("thermal_sense", "Thermal-sense trip comparators (thermal.*: heatsink/coil NTC hot + open)",
     lambda p, r: p.startswith("thermal.")),
    ("interlock", "Interlock latch/watchdog/aggregate (interlock.*) + PERMIT gate U37",
     lambda p, r: p.startswith("interlock.") or p in {"u_permit", "c_permit", "r_run_en_pd", "r_permit_pd"}),
    ("trip_glue", "Trip glue: rail window U3, SENSOR_LIVE/RAIL_FAULT, read-back buffer U9, runaway + rim trip comparators",
     lambda p, r: p in {"u_rail", "c_rail", "c_rail_sense", "r_rail_sense", "r_rail_pu", "u_live", "c_live",
                        "u_rail_inv", "c_rail_inv", "u_rb", "c_rb", "u_runaway", "c_runaway", "c_runaway_th",
                        "r_runaway_top", "r_runaway_bot", "u_runaway_or", "c_runaway_or", "u_rim_trip",
                        "c_rim_trip", "r_rim_th_top", "r_rim_th_bot", "c_rim_th"}),
    ("capmode", "C39 capacitive-mode detector U42-U46",
     lambda p, r: p.startswith(("u_cm_", "c_cm_", "r_cm_"))),
    ("rms", "Tank RMS: AD8436 U14 + MCP3202 U15 + clamp",
     lambda p, r: p.startswith(("u_rms", "c_rms", "r_rms", "u_adc", "c_adc", "r_adc", "d_rms"))),
    ("d11_ctmon", "D-11 bus receiver (OPA2388, LM4040, 0.1 % R) + ct_mon buffer",
     lambda p, r: p.startswith(("u_rx", "r_rx", "c_rx", "u_ref", "r_ref", "r_bias_top", "r_bias_bot",
                                "r_vbus_adc", "c_vbus_adc", "r_ct_mon_def", "r_ct_adc", "c_ct_adc", "u_buf1", "c_buf1"))),
    ("ntc_afe", "NTC / M12 / rim analog front ends: buffers, input RCs, ADC anti-kick RCs, TVS",
     lambda p, r: p.startswith(("u_buf2", "c_buf2", "u_buf3", "c_buf3", "r_hs_", "c_hs_", "r_coil_", "c_coil_",
                                "r_m12", "c_m12", "d_m12", "r_rim_", "c_rim_", "d_rim"))),
    ("j4_if", "J4 interface: PWM series + pull-downs, ZC series, BIAS_GOOD input",
     lambda p, r: p.startswith(("r_pwm_", "rpd_pwm_", "r_ct_zc", "r_line_zc", "r_bias_ser", "r_bias_pd", "c_bias"))),
    ("expander", "TCA9555 expander U8 + I2C pull-ups",
     lambda p, r: p in {"u_io", "c_io", "r_scl_pu", "r_sda_pu"}),
    ("ui_bus", "J7 UI bus support: SRV05-4 ESD x2, 100 R series x6, +5 V LDO TLV76050 + droppers",
     lambda p, r: p.startswith(("u_esd_ui", "c_esd_ui", "rs_ui_", "u_v5", "c_v5", "r_v5"))),
]


def block_of(path: str, ref: str) -> str:
    for name, _, rule in BLOCKS:
        if rule(path or "", ref or ""):
            return name
    return "unassigned"


def package_class(lib: str) -> str:
    name = lib.split(":")[-1]
    for tag in ("0402", "0603", "0805", "1206"):
        if f"_{tag}_" in name:
            return tag
    return "other"


def main(argv):
    pcb = Path(argv[1]) if len(argv) > 1 else DEFAULT_PCB
    sha = hashlib.sha256(pcb.read_bytes()).hexdigest()
    board = kc.load(pcb)
    fps = kc.footprints(board)
    edge = kc.edge_cuts(board)
    x0, y0, x1, y1 = edge["bbox"]
    board_area = edge["outer_area_mm2"]
    holes = edge["holes"]
    hole_cut = sum(math.pi * r * r for _, _, r in holes)
    keepout = len(holes) * math.pi * (HOLE_KEEPOUT_D / 2) ** 2

    crt_total = sum(f["crtyd_area_mm2"] for f in fps)
    by_block: dict[str, dict] = defaultdict(lambda: {"parts": 0, "smd": 0, "tht": 0, "crtyd_mm2": 0.0, "refs": [], "pts": []})
    for f in fps:
        b = block_of(f["path"], f["ref"])
        f["block"] = b
        d = by_block[b]
        d["parts"] += 1
        if "through_hole" in f["attr"]:
            d["tht"] += 1
        elif "smd" in f["attr"]:
            d["smd"] += 1
        d["crtyd_mm2"] += f["crtyd_area_mm2"]
        d["refs"].append(f["ref"])
        d["pts"] += [p for l in f["crtyd_loops"] for p in l]

    blocks_out = {}
    for name, desc, _ in BLOCKS + [("unassigned", "not matched", None)]:
        if name not in by_block:
            continue
        d = by_block[name]
        hull = kc.convex_hull(d["pts"])
        hull_area = kc.shoelace(hull) if len(hull) >= 3 else 0.0
        xs, ys = [p[0] for p in d["pts"]], [p[1] for p in d["pts"]]
        blocks_out[name] = {
            "description": desc,
            "parts": d["parts"], "smd": d["smd"], "tht": d["tht"],
            "crtyd_mm2": round(d["crtyd_mm2"], 1),
            "share_of_crtyd_pct": round(100 * d["crtyd_mm2"] / crt_total, 1),
            "as_placed_hull_mm2": round(hull_area, 1),
            "hull_density_pct": round(100 * d["crtyd_mm2"] / hull_area, 1) if hull_area else None,
            "world_bbox": [round(min(xs) - OX, 1), round(OY - max(ys), 1), round(max(xs) - OX, 1), round(OY - min(ys), 1)],
            "refs": sorted(d["refs"], key=lambda r: (r.rstrip("0123456789"), int("0" + "".join(c for c in r if c.isdigit())))),
        }

    # Package classes (for the 0402 option)
    pk = defaultdict(lambda: {"count": 0, "crtyd_mm2": 0.0})
    for f in fps:
        c = package_class(f["lib"])
        pk[c]["count"] += 1
        pk[c]["crtyd_mm2"] += f["crtyd_area_mm2"]
    pk = {k: {"count": v["count"], "crtyd_mm2": round(v["crtyd_mm2"], 1)} for k, v in pk.items()}

    # Parts that sit on the board edge (courtyard within 1 mm of the outline): the enclosure landings
    edge_parts = []
    for f in fps:
        bx0, by0, bx1, by1 = f["crtyd_bbox"]
        sides = [s for s, v in (("left", bx0 - x0), ("right", x1 - bx1), ("rear", by0 - y0), ("front", y1 - by1)) if v <= 1.0]
        if sides:
            edge_parts.append({"ref": f["ref"], "path": f["path"], "sides": sides})

    # The ten largest courtyards
    largest = [{"ref": f["ref"], "lib": f["lib"].split(":")[-1], "crtyd_mm2": round(f["crtyd_area_mm2"], 1)}
               for f in sorted(fps, key=lambda f: -f["crtyd_area_mm2"])[:12]]

    # Connector footprint origins (pin 1 for these footprints), world frame
    conn = {f["ref"]: (round(f["at"][0] - OX, 2), round(OY - f["at"][1], 2)) for f in fps if f["ref"].startswith("J")}

    out = {
        "schema": "temper.board-shrink-r1.controller-area.v1",
        "board_file": str(pcb), "board_sha256": sha, "board_matches_order_md": sha == EXPECTED_SHA,
        "outline_bbox_kicad_mm": [x0, y0, x1, y1],
        "outline_mm": [round(x1 - x0, 3), round(y1 - y0, 3)],
        "board_area_mm2": round(board_area, 1),
        "holes": [{"kicad_xy": [h[0], h[1]], "world_xy": [h[0] - OX, OY - h[1]], "d_mm": round(2 * h[2], 2)} for h in holes],
        "hole_cut_mm2": round(hole_cut, 1),
        "hole_keepout_mm2": round(keepout, 1),
        "placements": len(fps),
        "smd": sum("smd" in f["attr"] for f in fps),
        "tht": sum("through_hole" in f["attr"] for f in fps),
        "other_attr": [f["ref"] for f in fps if not ({"smd", "through_hole"} & set(f["attr"]))],
        "side_counts": {"F": sum(f["side"] == "F" for f in fps), "B": sum(f["side"] == "B" for f in fps)},
        "crtyd_fallback_refs": [f["ref"] for f in fps if f["crtyd_fallback"]],
        "crtyd_total_mm2": round(crt_total, 1),
        "utilisation_pct_of_board": round(100 * crt_total / board_area, 1),
        "utilisation_pct_of_usable": round(100 * crt_total / (board_area - keepout), 1),
        "blocks": blocks_out,
        "packages": pk,
        "largest_courtyards": largest,
        "edge_parts": edge_parts,
        "connector_pin1_world_xy": conn,
    }
    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / "controller-area.json").write_text(json.dumps(out, indent=1))
    print(f"board {out['outline_mm']} area {out['board_area_mm2']} mm2, courtyards {out['crtyd_total_mm2']} mm2 "
          f"= {out['utilisation_pct_of_board']} % (sha match {out['board_matches_order_md']})")
    for k, v in blocks_out.items():
        print(f"  {k:14s} {v['parts']:4d} parts {v['crtyd_mm2']:8.1f} mm2 ({v['share_of_crtyd_pct']:5.1f} %) "
              f"hull {v['as_placed_hull_mm2']:8.1f} density {v['hull_density_pct']} %")
    print("packages", pk)


if __name__ == "__main__":
    main(sys.argv)
