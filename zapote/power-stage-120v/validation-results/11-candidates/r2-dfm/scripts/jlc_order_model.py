#!/usr/bin/env python3
"""JLC order model for 5 and 500 boards: assembly service fees (published table) and a bare-board SENSITIVITY grid.

    python3 -I jlc_order_model.py  ->  results/jlc_order_model.json

SOURCED: assembly fee table (jlcpcb.com/help/article/pcb-assembly-price, 2026-10-13); 4-layer base board charge
70.6 USD/m2 (jlcpcb.com/news/discount-on-quality-4-layer-pcbs: 100 pcs x 100x100 mm = 70.60 USD, basic parameters).
NOT PUBLISHED by JLC (so these are labelled sensitivities, not quotes): the 2 oz heavy-copper adder, the POFV
adder for 4 layers (JLC only says '6-20 layer free; 4-layer still requires charges'), engineering fee and the
small-quantity price break. The lead must read the instant quote page for the final numbers: three runs listed in
PROPOSALS.md section 4.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import R2, bom, designators

A = json.load(open(R2 / "results/assembly_cost.json"))
F = A["jlc_fees"]
rows = bom()
jlc_lines = [r for r in rows if r["Assembly"].startswith("JLC")]
ext = [r for r in jlc_lines if "Extended" in r["Assembly"]]
bas = [r for r in jlc_lines if "Basic" in r["Assembly"]]
smd_j = A["smd_joints_total"]
tht_j_lcsc = sum(l["plated_joints"] for l in A["lines"] if l["mount"] == "THT" and l["has_lcsc"] and l["lcsc"] and l["refs"] != ["F1-CLIP x2"])
out = {"jlc_lines": len(jlc_lines), "extended_lines": len(ext), "basic_lines": len(bas), "smd_joints": smd_j,
       "tht_joints_lcsc_lines": tht_j_lcsc}
for boards in (5, 500):
    fix = F["fixtures_1_29"] if boards < 30 else F["fixtures_500_plus"]
    std = (F["std_setup_1side"] + F["std_stencil_1side"] + F["std_stencil_storage"] + F["std_feeder_per_line"] * len(jlc_lines)
           + fix + F["confirm_placement"] + F["hand_labour_per_order"]
           + boards * (smd_j * F["smt_per_joint"] + tht_j_lcsc * F["manual_per_joint"]))
    eco = (F["eco_setup"] + F["eco_stencil"] + F["eco_feeder_per_ext_line"] * len(ext) + F["confirm_placement"]
           + F["hand_labour_per_order"] + boards * (smd_j * F["smt_per_joint"] + tht_j_lcsc * F["manual_per_joint"]))
    out[f"assembly_fees_{boards}"] = {"standard_total": round(std, 2), "standard_per_board": round(std / boards, 2),
                                      "economic_total": round(eco, 2), "economic_per_board": round(eco / boards, 2),
                                      "economic_allowed": 2 <= boards <= 50}
area_m2 = 0.290 * 0.190              # billed on the bounding box (assumption: JLC bills the rectangle)
base = 70.6 * area_m2
out["bare_floor_per_board_usd"] = round(base, 2)
grid = {}
for hc in (1.15, 1.30):
    for pofv in (0.0, 0.10, 0.25, 0.50):
        k = f"2oz_x{hc}_pofv+{int(pofv * 100)}%"
        grid[k] = {"per_board": round(base * hc * (1 + pofv), 2),
                   "pofv_part_per_board": round(base * hc * pofv, 2)}
out["bare_sensitivity_grid"] = grid
out["pofv_value_at_500_boards_per_10pct"] = round(base * 1.15 * 0.10 * 500, 0)
json.dump(out, open(R2 / "results/jlc_order_model.json", "w"), indent=1)
print(json.dumps(out, indent=1))
