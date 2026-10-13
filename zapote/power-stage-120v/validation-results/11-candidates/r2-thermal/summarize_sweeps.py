#!/usr/bin/env python3
"""Tabulate runs/*.json (b3_rerun.py output) into results/sweeps.json. Run: python3 -I summarize_sweeps.py
Mesh note: 0.5 mm global converged-model numbers; the converged 0.0625 mm R5 pad max is +6.7 K above the 0.5 mm value (129.5 vs 122.8)."""
import json, glob
from pathlib import Path
HERE = Path(__file__).resolve().parent
rows = {}
for f in sorted(glob.glob(str(HERE / "runs/*.json"))):
    r = json.loads(Path(f).read_text()); pr = {p["ref"]: p for p in r["parts"]}
    g = lambda k, key: round(pr[k][key], 1) if k in pr and key in pr[k] else None
    rows[Path(f).stem] = {"peak_C": round(r["peak"]["temperature_c"], 1), "peak_at": [r["peak"].get("x_mm"), r["peak"].get("y_mm"), r["peak"].get("layer")],
        "R5_pad_max": g("R5", "pad_max_cell_c"), "R5_element": g("R5", "tj_c"), "FET_row_copper_max": round(r["fet_row_max_c"] or 0, 1),
        "C38": g("C38", "tj_c"), "C40": g("C40", "tj_c"), "C21_bank": g("C21", "tj_c"), "C5": g("C5", "tj_c"), "L1": g("L1", "tj_c"),
        "PS1_case": g("PS1", "tj_c"), "PS2_case": g("PS2", "tj_c"), "U41": g("U41", "tj_c"), "R58": g("R58", "tj_c")}
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results/sweeps.json").write_text(json.dumps(rows, indent=1) + "\n")
for k, v in rows.items(): print(k.ljust(40), v["peak_C"], v["R5_pad_max"], v["FET_row_copper_max"], v["C38"], v["C40"], v["C21_bank"], v["PS2_case"])
