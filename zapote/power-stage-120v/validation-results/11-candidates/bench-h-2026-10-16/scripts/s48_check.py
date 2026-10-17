#!/usr/bin/env python3
"""Spot-check the airflow28 ladder's c28 brackets (solved on s47, 83355da5) on the board of record s48 (2b46d90e).

    python3 -I s48_check.py [--workers 3]    # -> results/ladder-s48-check.json

Runs the snapshot's own run_basis.py (gate cases, hot copper, both meshes, the gate's estimator) on:
  uniform  c28_h30@61 / c28_h31@61, c28_h26@55 / c28_h27@55   (airflow28 3: fail / pass)
  jetmix   c28_h15_jet100@61 / c28_h16_jet100@61, c28_h10_jet100@55 / c28_h12_jet100@55   (airflow28 4.4)
  control  c28_h10@55 against the s48 chain's own run files (PS b3-ratings/runs/c28_h10_p0p*.json)
Run files go to work/s48-check/ (outside git).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "snap"
R5 = SNAP / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
PS_RUNS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-results/"
               "04-board-current-thermal/round5-native21/b3-ratings/runs")
RUNS = ROOT / "work/s48-check"
CASES = {"c28_h30": 61, "c28_h31": 61, "c28_h26": 55, "c28_h27": 55, "c28_h15_jet100": 61, "c28_h16_jet100": 61,
         "c28_h10_jet100": 55, "c28_h12_jet100": 55, "c28_h10": 55}
S47 = {"c28_h30@61": "fail", "c28_h31@61": "pass (laminate block +0.3, R12 +0.6)", "c28_h26@55": "fail",
       "c28_h27@55": "pass (laminate block +0.9, R12 +1.1)", "c28_h15_jet100@61": "-0.7 K", "c28_h16_jet100@61": "+0.7 K",
       "c28_h10_jet100@55": "-4.0 K", "c28_h12_jet100@55": "+0.4 K", "c28_h10@55": "-51.2 K (committed ratchet, s47)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    out_m = RUNS / "margins-s48-check.json"
    spec = ",".join(f"{c}@{b}" for c, b in CASES.items())
    r = subprocess.run([sys.executable, "-I", str(R5 / "b3-ratings/run_basis.py"), "--cases", spec, "--runs", str(RUNS),
                        "--out", str(out_m), "--workers", str(a.workers)])
    m = json.loads(out_m.read_text())
    res = {"snapshot": (SNAP / "SNAPSHOT.txt").read_text().strip(), "run_basis_exit": r.returncode, "cases": {}}
    for c, b in CASES.items():
        rows = [x for x in m["cases"][c] if x["gated"]]
        w = min(rows, key=lambda x: x["margin_k"])
        hdep = min((x for x in rows if not x["item"].startswith("PS2:")), key=lambda x: x["margin_k"])
        lam = min((x for x in rows if x["item"].startswith("laminate")), key=lambda x: x["margin_k"])
        part = min((x for x in rows if not x["item"].startswith("laminate")), key=lambda x: x["margin_k"])
        res["cases"][f"{c}@{b}"] = {"worst_k": w["margin_k"], "worst_item": w["item"], "h_dependent_worst_k": hdep["margin_k"],
                                   "h_dependent_item": hdep["item"], "laminate_k": lam["margin_k"],
                                   "rated_part_k": part["margin_k"], "rated_part_item": part["item"],
                                   "board_sha256": m.get("board_sha256", {}).get(c), "s47_airflow28": S47[f"{c}@{b}"]}
    ctl = {}
    for p in ("0p5", "0p25"):
        mine = json.loads((RUNS / f"c28_h10_p{p}.json").read_text())
        chain = json.loads((PS_RUNS / f"c28_h10_p{p}.json").read_text())
        ctl[p] = {"same_board": mine["board_sha256"] == chain["board_sha256"],
                  "peak_1mm_block_diff_k": mine["peak_1mm_block"]["temperature_c"] - chain["peak_1mm_block"]["temperature_c"],
                  "max_part_tj_diff_k": max(abs(x["tj_c"] - y["tj_c"]) for x, y in zip(mine["parts"], chain["parts"])
                                            if "tj_c" in x and "tj_c" in y)}
    res["control_vs_chain_runs"] = ctl
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/ladder-s48-check.json").write_text(json.dumps(res, indent=1) + "\n")
    for k, v in res["cases"].items():
        print(f"{k:22s} worst {v['worst_k']:+6.1f} ({v['worst_item'][:40]}); h-dep {v['h_dependent_worst_k']:+.1f}; s47: {v['s47_airflow28']}")
    print("control", ctl)


if __name__ == "__main__":
    main()
