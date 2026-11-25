#!/usr/bin/env python3
"""OPEN-ITEMS S33: total clearing I2t of the surveyed fuses against the corrected drain-pin copper (DECISIONS 88).

    python3 -I fuse_vs_neck.py      -> ../fuse-vs-neck.json

Fuse figures are 12-decisions/f1-data/SURVEY.md's (section 1-2; several are read from mirrors, not re-read here). carry is the repo's G2
rule, In x 0.75 x derate(50 C), against 15 A. Derates: KLDR / CCMR 0.90, Bel 0.96 (survey, plots); KLKR prints none, so 0.90 is ASSUMED."""
import json
from pathlib import Path
H = Path(__file__).resolve().parent
d = json.loads((H.parents[2] / "02-protection-timing/shoot-through-f1/s57_necks_hole.json").read_text())
neck = d["min_ratio_single_layer"] * d["F1_clearing_I2t"]
F = [("KLDR025.TXP (fitted)", 25, 1710.0, 0.90, "same clips"), ("KLKR020 (fast, Class CC)", 20, 900.0, 0.90, "same clips"),
     ("CCMR020 (TD, Class CC)", 20, 918.0, 0.90, "same clips"), ("Bel 0ADEC9250-BE (fast, 6.3 x 32, Recognized)", 25, 470.0, 0.96, "new clips and footprint; certifier")]
rows = [{"fuse": n, "clearing_I2t": c, "copper_ratio": round(neck / c, 2), "copper_ok": neck >= c, "carry_A": round(i * 0.75 * k, 1),
         "carry_ok_15A": i * 0.75 * k >= 15, "carry_ok_13p5A_release": i * 0.75 * k >= 13.5, "fit": w} for n, i, c, k, w in F]
assert not rows[0]["copper_ok"] and abs(rows[0]["copper_ratio"] - 0.64) < 0.01     # control: today's fuse reproduces DECISIONS 88
(H.parent / "fuse-vs-neck.json").write_text(json.dumps({"neck_I2t": round(neck, 1), "rows": rows}, indent=1) + "\n")
for r in rows:
    print(r)
