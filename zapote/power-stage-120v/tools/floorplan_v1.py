#!/usr/bin/env python3
"""First deliberate floorplan: courtyard-centre placement -> poses.json.

Run under KiCad's Python (pcbnew) against a generated board, which supplies
each footprint's measured F.CrtYd bounds in its local frame:

    KICAD_PY tools/floorplan_v1.py native-02/section.kicad_pcb --output poses.json

Coordinates below are courtyard centres in mm (x right, y down) and KiCad
orientation angles. Board 220 x 160 (D1). Heatsink along the top edge,
x 5..160 (D2). Mains enters at the left, coil exits at the right (D6).

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


# ---- Top band: heatsink row (pads toward the heatsink edge) --------------
put("br1", 24.0, 4.6)
LEG_X = {"leg_b.q_high": 56.0, "leg_b.q_low": 76.0, "leg_a.q_low": 130.0, "leg_a.q_high": 150.0}
for q, x in LEG_X.items():
    put(q, x, 4.4)
# Snubbers directly across drain-source (pads 2-3) of each MOSFET.
put("leg_b.c_snub_h", LEG_X["leg_b.q_high"] + 2.73, 9.3)
put("leg_b.c_snub_l", LEG_X["leg_b.q_low"] + 2.73, 9.3)
put("leg_a.c_snub_l", LEG_X["leg_a.q_low"] + 2.73, 9.3)
put("leg_a.c_snub_h", LEG_X["leg_a.q_high"] + 2.73, 9.3)
# Local HF bus capacitors, two per leg, in the row under the FET pairs.
put("c_hf_b1", 57.0, 16.0)
put("c_hf_b2", 76.4, 16.0)
put("c_hf_a1", 130.6, 16.0)
put("c_hf_a2", 150.0, 16.0)
put("r_shunt", 103.0, 12.6)

# ---- Drivers straddling the island's top edge -----------------------------
# SOIC16W at 90 deg: SELV pins (1-8) face +y into the island. Gate series
# resistors and gate-source hold-offs sit at the driver outputs (row y~24).
put("leg_b.driver", 66.0, 33.0, 90)
put("leg_a.driver", 140.0, 33.0, 90)
for leg, x in (("leg_b", 66.0), ("leg_a", 140.0)):
    put(f"{leg}.r_gh", x - 3.0, 24.0, 90)
    put(f"{leg}.r_gh_pd", x - 6.0, 24.0, 90)
    put(f"{leg}.r_gl", x + 3.0, 24.0, 90)
    put(f"{leg}.r_gl_pd", x + 6.0, 24.0, 90)
    # Anode (V15_LS) left toward the LOW cluster, cathode (boot) right.
    put(f"{leg}.d_boot", x - 14.5, 23.0, 180)
    put(f"{leg}.c_boot", x - 14.0, 27.6)
    put(f"{leg}.c_boot_hf", x - 9.5, 27.8)
    put(f"{leg}.c_ls_bulk", x + 11.5, 27.6)
    put(f"{leg}.c_ls", x + 11.5, 24.0)
# SELV-side support inside the island.
for leg, x0 in (("leg_b", 58.0), ("leg_a", 132.0)):
    put(f"{leg}.c_vcci", x0, 43.5)
    put(f"{leg}.permit_fet", x0 + 5.0, 44.0)
    put(f"{leg}.r_permit", x0 + 10.0, 43.5)
    put(f"{leg}.r_permit_pd", x0 + 10.0, 46.5)
    put(f"{leg}.r_dis_pu", x0 + 14.0, 43.5)
    put(f"{leg}.r_dt", x0 + 14.0, 46.5)

# ---- Shunt-side protection between the legs --------------------------------
# ISO7710 at 270 deg: SELV side (+x local) faces +y into the island.
put("u_iso", 103.0, 33.0, 270)
put("c_iso2", 103.0, 43.5)
put("c_iso1", 96.0, 26.5)
put("u_nand", 112.5, 25.8)
put("c_nand_vcc", 117.0, 26.2)
put("u_ocp", 92.5, 18.0)
put("c_ocp_vcc", 92.5, 22.5)
put("r_ocp_ref", 88.5, 14.0, 90)
put("r_ocp_sense", 88.5, 18.5, 90)
put("c_ocp_node", 88.5, 23.0, 90)
put("r_th_top", 97.0, 17.5, 90)
put("r_th_bot", 99.5, 17.5, 90)
put("c_th", 102.0, 17.5, 90)
put("u_ref", 106.5, 18.0)
put("r_ref_bias", 110.5, 18.0, 90)
put("u_ldo", 115.0, 12.8, 90)
put("c_ldo_in", 115.0, 17.2)
put("c_ldo_out", 114.5, 21.0)
put("c_v15", 109.5, 22.3)

# ---- Bus side: bulk, clamp, bleed, bring-up links --------------------------
put("c_bus1", 19.0, 44.5, 90)
put("c_bus2", 179.0, 32.0, 90)
put("tvs_bus", 40.5, 45.0, 90)
put("r_bus1", 46.8, 40.5, 270)
put("r_bus2", 46.8, 45.5, 270)
put("link_pos.terminal_rect", 6.0, 74.0)
put("link_pos.terminal_bus", 17.5, 74.0)
put("link_neg.terminal_rect", 6.0, 87.0)
put("link_neg.terminal_bus", 17.5, 87.0)

# ---- Bus sense on the island's left edge ------------------------------------
# AMC1311 at 0 deg: SELV pins (+x) face into the island. Divider string runs
# down from the C5 bus terminals; OVP comparator reads its tap.
put("u_vsense", 42.0, 75.0)
put("c_vs2", 50.5, 71.5, 90)
put("c_vs1", 33.0, 71.5, 90)
put("r_div1", 27.5, 70.5, 270)
put("r_div2", 27.5, 75.2, 270)
put("r_div3", 27.5, 79.9, 270)
put("r_div4", 27.5, 84.6, 270)
put("r_div_bot", 33.0, 79.0, 90)
put("c_div", 33.0, 83.0, 90)
put("u_ovp", 36.5, 87.5)
put("c_ovp_vcc", 36.5, 91.5)
put("r_ovp_top", 33.0, 95.0, 90)
put("r_ovp_bot", 36.0, 95.0, 90)
put("c_ovp_th", 39.0, 95.0, 90)

# ---- Island interior ------------------------------------------------------
put("j_selv", 103.0, 53.0)
put("r_fe", 83.5, 71.0)
put("j_pe", 100.0, 71.5, 90)
# Y1 capacitors straddle the island's bottom edge: PE pad up, line pad down.
put("cy1", 118.5, 80.0, 90)
put("cy2", 125.5, 80.0, 90)

# ---- Barrier parts on the island's lower/right edges ----------------------
put("ps_selv", 66.4, 93.2, 90)   # outputs up into the island, AC down
put("t_ct", 175.0, 70.5, 270)    # secondary faces the island (-x)

# ---- Gate supply: left column, outputs up ----------------------------------
put("ps_gate", 14.5, 117.5, 90)
put("j_tco", 36.0, 106.0, 90)

# ---- Mains: bottom band, J1 at the left edge -------------------------------
put("j_mains", 8.0, 152.0, 270)  # wire entry (local +y) faces the left edge
put("f1", 38.3, 153.0)
put("rv1", 45.0, 135.0)
put("cx1", 75.0, 138.0)
put("rb1a", 64.0, 128.0)
put("rb1b", 70.0, 128.0)
put("l1", 115.0, 132.0, 180)
put("cx2", 24.0, 16.0)

# ---- Tank: right edge ------------------------------------------------------
put("c_res3", 208.0, 32.0, 90)
put("j_coil", 211.0, 70.5)
put("c_res1", 193.0, 97.0, 180)
put("c_res2", 193.0, 125.5, 180)
put("j_coil_return", 205.0, 151.0)
put("r_crb1", 170.0, 145.0)
put("r_crb2", 177.0, 145.0)
put("r_crb3", 184.0, 145.0)
put("r_crb4", 191.0, 145.0)


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
