"""Enclosure landing changes of the C60 floorplan, as a request to the enclosure line (R43 is the reference).

    python3 -I scripts/enclosure_deltas.py -> results/enclosure-deltas.json

Inputs: results/floorplan-acut.json (this folder), results/c49-board.json, and the R43 assembly
(/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/assembly.json.gz: the harness polylines'
'evidence' strings carry their developed lengths; the coax waypoints are r43 src/r33_world.py:91-94).
Cable length changes are ESTIMATES: straight-line distance between the old and new landing (lower bound)
and the Manhattan distance (a routed upper estimate). The coax path is re-estimated by replacing its first
leg (old U.FL straight up, then to the R33 waypoint (160, 77, 36)) with one from the new U.FL.
"""
from __future__ import annotations

import gzip
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402

R43 = Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r43")
BOARD_TOP_Z = 24.6                  # C/layout/world.py: bottom Z23 + 1.6
# r33_world.py:91-92 coax waypoints (R38 U.FL at (156, 67, 27.8))
COAX_OLD = [(156.0, 67.0, 28.6), (156.0, 67.0, 33.0), (160.0, 77.0, 36.0), (166.0, 92.0, 40.0), (166.0, 97.0, 86.0),
            (155.0, 105.0, 94.6), (148.0, 113.0, 94.6)]
COAX_CUT_MM = 150.0                 # r33_world.py:93 "1.13 mm coax, U.FL both ends, 150 mm"
RTD_LEAD_MAX_MM = 500.0             # C/ENCLOSURE-HANDOFF.md:32 "SAB 4xAWG28, <= 500 mm"


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def main():
    parts, _ = geom.load_parts()
    fpl = json.loads((OUT / "results/floorplan-acut.json").read_text())
    P = fpl["placement"]
    asm = {e["name"]: e for e in json.load(gzip.open(R43 / "assembly.json.gz"))}

    def dev_len(name):
        m = re.search(r"Developed length (\d+(?:\.\d+)?) mm", asm[name]["evidence"])
        return float(m.group(1)) if m else None

    def centre(ref, pose):
        r = geom.rect(parts[ref], *pose)
        return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), r

    rows = []
    for ref, harness, what in (("J3", "harness_pan_RTD_to_controller", "pan RTD, 6-core cartridge cable (4 RTD + rim pair)"),
                               ("J12", "harness_rim_NTC_breakout_to_J12", "rim NTC pair, breakout from the same cable"),
                               ("J10", "harness_fan_to_controller", "blower lead (V_BLOWER, GND, FG)"),
                               ("J11", None, "TC2050 bring-up land (no cable)")):
        (ox, oy), _ = centre(ref, tuple(parts[ref]["world"]))
        (nx, ny), r = centre(ref, tuple(P[ref]["world"]))
        d_e, d_m = math.dist((ox, oy), (nx, ny)), abs(ox - nx) + abs(oy - ny)
        L = dev_len(harness) if harness else None
        row = {"ref": ref, "cable": what, "r43_harness": harness,
               "c49_body_centre": [round(ox, 2), round(oy, 2)], "c60_body_centre": [round(nx, 2), round(ny, 2)],
               "c60_rect_world": [round(v, 2) for v in r], "c60_rotation_deg": P[ref]["world"][2],
               "move_straight_mm": round(d_e, 1), "move_manhattan_mm": round(d_m, 1),
               "r43_developed_length_mm": L,
               "c60_length_est_mm": [round(L + d_e), round(L + d_m)] if L else None}
        rows.append(row)
    rtd = rows[0]
    rtd["rtd_lead_limit_mm"] = RTD_LEAD_MAX_MM
    rtd["over_limit_est"] = [x > RTD_LEAD_MAX_MM for x in rtd["c60_length_est_mm"]]

    # U.FL / coax
    u4 = P["U4"]["world"]
    ufl_fp = (6.0, -7.14)               # C/layout/world.py:96
    ux, uy = geom.l2w(*u4, *ufl_fp)
    new = [(ux, uy, 28.6), (ux, uy, 33.0)] + COAX_OLD[2:]
    coax = {"c49_ufl": [156.0, 67.0], "c60_ufl": [round(ux, 2), round(uy, 2)],
            "r43_developed_mm": dev_len("harness_WiFi_coax"), "r43_waypoint_path_mm": round(plen(COAX_OLD), 1),
            "c60_same_route_from_new_ufl_mm": round(plen(new), 1),
            "c60_straight_ufl_to_antenna_mm": round(math.dist((ux, uy, 28.6), COAX_OLD[-1]), 1),
            "cut_length_mm": COAX_CUT_MM,
            "note": "the new U.FL sits under the fascia UI board (R43 controls_ui_board X-106..64, Z43.4-91.2): the coax "
                    "must leave sideways below Z43 before it rises"}
    holes = {"kept": fpl["holes"], "dropped": [[164.0, 18.0], [164.0, 80.0]]}
    out = {"schema": "temper.controller-shrink-c60.enclosure-deltas.v1", "ESTIMATE_lengths": True,
           "board": {"c49": [-38.0, 14.0, 168.0, 90.0], "c60": fpl["board_world"],
                     "freed_strip_world": [93.0, 14.0, 168.0, 90.0]},
           "landings": rows, "coax": coax, "holes": holes,
           "unchanged": ["J1", "J2", "J4", "J7", "J9", "J13", "holes (-34,18) (-26,74) (65,18) (75,86)",
                         "board Z23 / top Z24.6, Z40 limit, J13 local allowance", "R43 J13 barrier (X60-124 strip behind Y90)"]}
    (OUT / "results/enclosure-deltas.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
