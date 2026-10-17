#!/usr/bin/env python3
"""Extract the resonant-bank pad and B3 body temperatures from the airflow28 B3 run files (read-only).

    python3 -I bank_pads.py [RUNS_DIR] > ../bank_pads.json

Estimator as b3_ratings_gate.est: Q(0.25) + 3 |Q(0.25) - Q(0.5)| + (bay - 50 C). Values in the run files are in the
50 C model frame (TAMB_MODEL_C)."""
import json
import sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/runs")
BANK = ("C21", "C22", "C23", "C151", "C152")
CASES = [  # (label, mode, bay, stem)
    ("still air h10 @61", "uniform", 61, "c28_h10"),
    ("still air h10 @55", "uniform", 55, "c28_h10"),
    ("no-jet h31 @61 (min)", "uniform", 61, "c28_h31"),
    ("no-jet h37 @61 (x1.2)", "uniform", 61, "c28_h37"),
    ("no-jet h27 @55 (min)", "uniform", 55, "c28_h27"),
    ("no-jet h33 @55 (x1.2)", "uniform", 55, "c28_h33"),
    ("jet100 + base h16 @61 (min)", "jetmix", 61, "c28_h16_jet100"),
    ("jet100 + base h20 @61 (x1.25)", "jetmix", 61, "c28_h20_jet100"),
    ("jet100 + base h12 @55 (min)", "jetmix", 55, "c28_h12_jet100"),
    ("jet100 + base h15 @55 (x1.25)", "jetmix", 55, "c28_h15_jet100"),
] + [(f"still air c{c} h10 @{b}", "uniform", b, f"c{c}_h10") for b in (61, 55) for c in (18, 20, 22, 24, 26)]


def est(a, b, bay):
    return a + 3.0 * abs(a - b) + (bay - 50.0)


out = []
for label, mode, bay, stem in CASES:
    f25 = RUNS / mode / f"bay{bay}" / f"{stem}_p0p25.json"
    f05 = RUNS / mode / f"bay{bay}" / f"{stem}_p0p5.json"
    if not f25.exists():
        out.append({"case": label, "missing": str(f25)})
        continue
    r25, r05 = json.loads(f25.read_text()), json.loads(f05.read_text())
    assert r25.get("bay_c") in (None, bay) and r25["copper_temp_model"]["model"] == "hot-iterated", (label, r25.get("bay_c"))
    p25 = {p["ref"]: p for p in r25["parts"] if p["ref"] in BANK}
    p05 = {p["ref"]: p for p in r05["parts"] if p["ref"] in BANK}
    rows = {}
    for ref in BANK:
        a, b = p25[ref], p05[ref]
        rows[ref] = {"pad_max_c": round(est(a["pad_max_padmean_c"], b["pad_max_padmean_c"], bay), 2),
                     "pad_mean_c": round(est(a["pad_mean_c"], b["pad_mean_c"], bay), 2),
                     "b3_body_c": round(est(a["tj_c"], b["tj_c"], bay), 2),
                     "b3_watts_into_model": round(a["watts_into_model"], 4)}
    out.append({"case": label, "mode": mode, "bay_c": bay, "h": r25.get("h"), "i_t_a": r25.get("i_t_a"),
                "files": [str(f25), str(f05)], "bank": rows,
                "pad_max_over_bank_c": max(v["pad_max_c"] for v in rows.values()),
                "b3_body_max_c": max(v["b3_body_c"] for v in rows.values())})
print(json.dumps(out, indent=1))
