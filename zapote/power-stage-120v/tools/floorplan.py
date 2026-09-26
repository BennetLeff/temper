#!/usr/bin/env python3
"""Deliberate floorplan: courtyard-centre placement -> poses.json.

Run under KiCad's Python (pcbnew) against a generated board, which supplies
each footprint's measured F.CrtYd bounds in its local frame:

    KICAD_PY tools/floorplan.py native-02/section.kicad_pcb --output poses.json

Coordinates below are courtyard centres in mm (x right, y down) and KiCad
orientation angles. Board 240 x 160 (D1, widened 2026-09-26). Heatsink along the top edge,
x 12..165 (D2). Mains enters at the left, coil exits at the right (D6).

Zones (see PLACEMENT-REVIEW.md):
  Top band      BR1 and four TO-247s on the heatsink; snubbers, gate
                resistors and local HF capacitors in rows beneath.
  Bulk          C5 left of leg B, C6 right of leg A.
  SELV island   Interior region surrounded by HOT copper. Barrier parts
                straddle its edge: U1/U2 (top, below their legs), U9/U4
                (top, between the legs), T1 (right), PS1 and C3/C4 (bottom).
                J4 sits inside with its harness leaving vertically.
  Mains         Left column and bottom band: J1, F1, RV1, C1, L1, C2, PS2.
  Tank          Right edge: T1 primary, C21-C23, bleed string, J2/J5 studs.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# instance: (courtyard centre x, centre y, angle)
PLAN: dict[str, tuple[float, float, float]] = {}


def put(inst: str, x: float, y: float, a: float = 0.0) -> None:
    if inst in PLAN:
        raise ValueError(f"placed twice: {inst}")
    PLAN[inst] = (x, y, a)


# ---- Top band: heatsink row, legs closed up around the shunt --------------
# TO-247 pads at centre-5.45 (gate), centre (drain), centre+5.45 (source).
LEG_X = {"leg_b.q_high": 78.0, "leg_b.q_low": 96.0, "leg_a.q_low": 118.0, "leg_a.q_high": 136.0}
for q, x in LEG_X.items():
    put(q, x, 4.4)
# Shunt between the low-side sources; at 270 deg its LEG_RET pads face the
# sources (up) and its HV_RET pad faces the local capacitors (down).
put("r_shunt", 106.5, 12.6, 270)
# Snubbers across drain-source; gate series resistor and hold-off directly
# under each gate pin (Part 4 rule; Infineon gate-loop guidance).
put("leg_b.c_snub_h", LEG_X["leg_b.q_high"] + 2.73, 9.7)
put("leg_b.c_snub_l", LEG_X["leg_b.q_low"] + 2.73, 9.7)
put("leg_a.c_snub_l", LEG_X["leg_a.q_low"] + 2.73, 9.7)
put("leg_a.c_snub_h", LEG_X["leg_a.q_high"] + 2.73, 9.7)
for leg, q, r, pd in (
    ("leg_b", "q_high", "r_gh", "r_gh_pd"), ("leg_b", "q_low", "r_gl", "r_gl_pd"),
    ("leg_a", "q_high", "r_gh", "r_gh_pd"), ("leg_a", "q_low", "r_gl", "r_gl_pd"),
):
    gx = LEG_X[f"{leg}.{q}"] - 5.45
    put(f"{leg}.{r}", gx, 12.6, 90)
    put(f"{leg}.{pd}", gx - 2.8, 12.1, 90)
# Local HF capacitors in one row; every HV_RET pad converges under R5.
# Leg B at 0 deg (BUS_P left, HV_RET right); leg A at 180 deg (mirrored).
put("c_hf_b1", 96.5, 22.0)     # pads x 89 / 104
put("c_hf_b2", 75.9, 22.0)     # pads x 68.4 / 83.4 (3.2 mm to C40 BUS_P)
put("c_hf_a1", 116.5, 22.0, 180)   # pads x 124 / 109
put("c_hf_a2", 137.1, 22.0, 180)   # pads x 144.6 / 129.6

# ---- Drivers straddling the island's top edge -----------------------------
# SOIC16W at 90 deg: SELV pins face +y. HOT row left to right: pin 16 VDDA,
# 15 OUTA (high), 14 VSSA | 11 VDDB, 10 OUTB (low), 9 VSSB. Each driver sits
# midway between its two gates; leg A's outputs cross once (two layers).
put("leg_b.driver", 84.0, 46.0, 90)
put("leg_a.driver", 128.0, 46.0, 90)
for leg, x in (("leg_b", 84.0), ("leg_a", 128.0)):
    # Bootstrap on the VDDA (left) side, VDDB bypass on the right; HOT
    # copper stays above y ~42.5 (8 mm from the SELV pads at y 50.9).
    put(f"{leg}.d_boot", x - 10.5, 34.0, 180)
    put(f"{leg}.c_boot", x - 10.0, 39.3)
    put(f"{leg}.c_boot_hf", x - 6.6, 38.8, 90)
    put(f"{leg}.c_ls_bulk", x + 7.5, 35.6)
    put(f"{leg}.c_ls", x + 7.5, 39.6)
# SELV-side support inside the island.
for leg, x0 in (("leg_b", 76.5), ("leg_a", 120.5)):
    put(f"{leg}.c_vcci", x0, 56.5)
    put(f"{leg}.permit_fet", x0 + 5.0, 57.0)
    put(f"{leg}.r_permit", x0 + 10.0, 56.5)
    put(f"{leg}.r_permit_pd", x0 + 10.0, 59.5)
    put(f"{leg}.r_dis_pu", x0 + 14.0, 56.5)
    put(f"{leg}.r_dt", x0 + 14.0, 59.5)

# ---- Shunt-side protection, below the local capacitors ---------------------
# OCP comparator, reference and thresholds next to R5's Kelvin pad.
put("u_ocp", 98.0, 30.0)
put("c_ocp_vcc", 98.0, 34.0)
put("r_ocp_sense", 101.5, 30.0, 90)
put("r_ocp_ref", 101.5, 34.5, 90)
put("c_ocp_node", 104.0, 30.0, 90)
put("u_ref", 108.0, 29.5)
put("r_ref_bias", 108.0, 33.0)
put("r_th_top", 104.0, 34.5, 90)
put("r_th_bot", 106.5, 36.5, 90)
put("c_th", 109.0, 36.5, 90)

# ---- Fault isolator left of leg B, with the NAND that joins OCP and OVP ----
# ISO7710 at 270 deg: SELV side faces +y into the island.
put("u_iso", 63.0, 46.0, 270)
put("c_iso2", 63.0, 56.5)
put("c_iso1", 63.0, 37.5)
put("u_nand", 54.8, 38.8)
put("c_nand_vcc", 54.8, 34.8)
# HOT 5 V regulator left of leg B, near its V15 source and U4.

# ---- Bus side: bulk, clamp, bleed, bring-up links --------------------------
put("c_bus2", 164.5, 32.0, 90)
# Bus-side studs on the board edge so bench leads exit straight off it;
# rows 20 mm apart so the fitted link bars keep >= 3.2 mm (TERMINALS.md).

# ---- Bus sense on the island's left edge ------------------------------------
# AMC1311 at 0 deg: SELV pins (+x) face into the island. Divider string runs
# down from the C5 bus terminals; OVP comparator reads its tap.

# ---- Island interior ------------------------------------------------------
put("j_selv", 103.0, 66.0)
put("r_fe", 83.5, 79.0)
put("j_pe", 100.0, 79.5, 90)
# Y1 capacitors straddle the island's bottom edge: PE pad up, line pad down.
put("cy1", 118.5, 88.0, 90)
put("cy2", 125.5, 88.0, 90)

# ---- Barrier parts on the island's lower/right edges ----------------------
put("ps_selv", 66.4, 93.2, 90)   # outputs up into the island, AC down
put("t_ct", 175.0, 70.5, 270)    # secondary faces the island (-x)

# ---- Gate supply: left column, outputs up ----------------------------------

# ---- Mains: bottom band, J1 at the left edge -------------------------------

# ---- Tank: right edge ------------------------------------------------------
put("c_res3", 192.5, 32.0, 90)
put("j_coil", 211.0, 70.5)
put("c_res1", 193.0, 97.0, 180)
put("c_res2", 193.0, 125.5, 180)
put("j_coil_return", 205.0, 151.0)
put("r_crb1", 170.0, 145.0)
put("r_crb2", 177.0, 145.0)
put("r_crb3", 184.0, 145.0)
put("r_crb4", 191.0, 145.0)


# ---- D1 widened to 240 mm: the approved right part shifts +20 mm ----------
RIGHT_SHIFT_MM = 20.0
for _inst, (_x, _y, _a) in list(PLAN.items()):
    PLAN[_inst] = (_x + RIGHT_SHIFT_MM, _y, _a)

# ---- Left side, laid out around trunk corridors (240 x 160 board) --------
# BR1 on the heatsink; each link pair hangs vertically under its DC pin.
put("br1", 29.0, 4.6)
put("cx2", 30.0, 23.6, 90)                 # X2 across BR1's AC pins
put("link_pos.terminal_rect", 13.0, 17.5)  # under BR1 +
put("link_pos.terminal_bus", 13.0, 30.5)
put("link_neg.terminal_rect", 47.0, 17.5)  # under BR1 -
put("link_neg.terminal_bus", 47.0, 30.5)
# C5 at 0 deg: BUS_P pads under J8, HV_RET pads under J10. BUS_P runs on
# B.Cu under its body; the mains and gate-supply pairs run on F.Cu under it.
put("c_bus1", 31.75, 54.1)
put("tvs_bus", 58.0, 54.95, 90)            # HV_RET pad at C5's HV_RET column
put("r_bus1", 63.5, 61.5, 90)   # bus_p (bottom) near D3.1
put("r_bus2", 63.5, 48.5, 90)   # hv_ret (top) near D3.2
# HOT 5 V regulator beside the negative link, near its loads.
put("u_ldo", 62.0, 18.0, 90)
put("c_ldo_in", 62.0, 13.5)
put("c_ldo_out", 66.5, 18.0, 90)
put("c_v15", 57.5, 18.0, 90)
# Bus sense on the island's left edge, below C5.
put("u_vsense", 65.5, 84.0)
put("c_vs2", 70.0, 77.0, 90)
put("c_vs1", 57.0, 82.0, 90)
put("r_div1", 52.0, 76.0, 270)
put("r_div2", 52.0, 80.7, 270)
put("r_div3", 52.0, 85.4, 270)
put("r_div4", 52.0, 90.1, 270)
put("r_div_bot", 57.0, 88.0, 90)
put("c_div", 57.0, 92.0, 90)
put("u_ovp", 62.0, 95.0)
put("c_ovp_vcc", 66.5, 95.0)
put("r_ovp_top", 58.0, 99.0, 90)
put("r_ovp_bot", 61.0, 99.0, 90)
put("c_ovp_th", 64.0, 99.0, 90)
# Gate supply: the mains corridor runs under its body; outputs on the right.
put("ps_gate", 24.25, 85.5)
put("j_tco", 37.0, 103.3, 90)
# Mains: J1 at the left edge, filter rising to the corridor.
put("l1", 24.0, 123.0, 180)
put("j_mains", 7.0, 153.0, 270)            # wire entry (local +y) faces the left edge
put("f1", 36.5, 153.0)
put("rv1", 68.2, 147.0)
put("cx1", 64.0, 127.5)
put("rb1a", 82.0, 124.0, 270)
put("rb1b", 82.0, 129.2, 270)


def rotate(x: float, y: float, angle: float) -> tuple[float, float]:
    """KiCad footprint rotation (y down, positive angle counter-clockwise)."""
    t = math.radians(angle)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def local_courtyards(board_path: Path) -> dict[str, tuple[float, float, float, float]]:
    import pcbnew  # type: ignore[import-not-found]

    board = pcbnew.LoadBoard(str(board_path))
    out = {}
    for fp in board.GetFootprints():
        if abs(fp.GetOrientationDegrees()) > 1e-9:
            raise ValueError("measure courtyards from an unrotated shelf board")
        field = fp.GetField("SourceInstance")
        if field is None:
            raise ValueError("board lacks SourceInstance; generate with --stackup")
        pos = fp.GetPosition()
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        ox, oy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        out[field.GetText()] = (
            pcbnew.ToMM(bb.GetX()) - ox, pcbnew.ToMM(bb.GetY()) - oy,
            pcbnew.ToMM(bb.GetRight()) - ox, pcbnew.ToMM(bb.GetBottom()) - oy,
        )
    return out


def poses(courtyards: dict[str, tuple[float, float, float, float]]) -> dict[str, list[float]]:
    missing = sorted(courtyards.keys() - PLAN.keys())
    extra = sorted(PLAN.keys() - courtyards.keys())
    if missing or extra:
        raise ValueError(f"plan differs from source: missing {missing}, extra {extra}")
    out = {}
    for inst, (cx, cy, angle) in PLAN.items():
        x1, y1, x2, y2 = courtyards[inst]
        corners = [rotate(x, y, angle) for x in (x1, x2) for y in (y1, y2)]
        mx = (min(c[0] for c in corners) + max(c[0] for c in corners)) / 2
        my = (min(c[1] for c in corners) + max(c[1] for c in corners)) / 2
        out[inst] = [round(cx - mx, 3), round(cy - my, 3), float(angle % 360)]
    return dict(sorted(out.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shelf_board", type=Path, help="Unrotated generated board (courtyard source)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = poses(local_courtyards(args.shelf_board))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parts": len(result), "output": str(args.output)}))


if __name__ == "__main__":
    main()
