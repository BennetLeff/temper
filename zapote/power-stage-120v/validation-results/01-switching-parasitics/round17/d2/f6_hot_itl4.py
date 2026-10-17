#!/usr/bin/env python3
"""Resolve D-13's indeterminate F6 runs at 150 C with D-14's solver setting.

D-13 (`delegation/out-D13/`) ran F6 (D-6's 1 ohm discharge + 1 nF Cgs + -2 V
off bias) at Tj 27/100/150 C; every 150 C run aborted. D-14
(`delegation/out-D14/`) qualified `.options itl4=100000` as physics-neutral
(resolves the cold aborts, 221 comparable results unchanged). This reruns
D-13's F6 jobs unchanged except for that one option:

- 150 C (56 jobs): the indeterminate set;
- 100 C (56 jobs): control; every case must reproduce D-13's converged result
  (off-gate within 0.01 V, die VDS within 0.5 %) or the run is rejected.

It imports D-13's runner and reuses its job list, deck, parameters and
result classification; only the deck copy gains the option line.

    f6_hot_itl4.py [--workers 8]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
D13 = HERE.parent / "delegation" / "out-D13"
OUT = HERE / "results" / "f6-hot-itl4"
OPTION = ".options itl4=100000"


def load_d13():
    spec = importlib.util.spec_from_file_location("d13_run", D13 / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    d13 = load_d13()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decks").mkdir(exist_ok=True)
    src = (D13 / "decks" / "F6.cir").read_text()
    assert src.count(".temp {TJ}") == 1, "D-13 F6 deck changed"
    (OUT / "decks" / "F6.cir").write_text(src.replace(".temp {TJ}", ".temp {TJ}\n" + OPTION))
    d13.HERE = OUT                                  # one() writes raw/ and reads decks/ under HERE
    points = [("S1", bus, 37, dt) for bus in (170, 198, 280) for dt in (307, 348, 443)]
    points += [("S2", 280, 71, dt) for dt in (307, 348, 443)]
    points += [("S4", 198, -20, dt) for dt in (348, 443)]
    jobs = [("F6", temp, *p[:3], direction, p[3], esl, .2)
            for temp in (100, 150) for p in points for direction in (0, 1) for esl in (1.06, 10)]
    with ThreadPoolExecutor(a.workers) as pool:
        rows = list(pool.map(d13.one, jobs))
    old = {r["name"]: r for r in json.loads((D13 / "results-main.json").read_text())}
    control, bad = [], []
    for r in rows:
        if r["temp_C"] != 100:
            continue
        o = old[r["name"]]
        if o["status"] != "complete" or r["status"] != "complete":
            bad.append((r["name"], o["status"], r["status"]))
            continue
        d_off, d_vds = abs(r["off_V"] - o["off_V"]), abs(r["vds_V"] - o["vds_V"]) / o["vds_V"]
        control.append({"name": r["name"], "d_off_V": d_off, "d_vds_rel": d_vds})
        if d_off > 0.01 or d_vds > 0.005:
            bad.append((r["name"], round(d_off, 4), round(d_vds, 5)))
    hot = [r for r in rows if r["temp_C"] == 150]
    summary = {
        "option": OPTION,
        "control_100C": {"compared": len(control), "max_d_off_V": max((c["d_off_V"] for c in control), default=None),
                         "max_d_vds_rel": max((c["d_vds_rel"] for c in control), default=None), "rejected": bad},
        "hot_150C": {"attempted": len(hot), "complete": sum(r["status"] == "complete" for r in hot),
                     "indeterminate": [r["name"] for r in hot if r["status"] != "complete"],
                     "max_off_V": max((r["off_V"] for r in hot if r["status"] == "complete"), default=None),
                     "max_vds_V": max((r["vds_V"] for r in hot if r["status"] == "complete"), default=None),
                     "model_screen_150C_V": 2.48794, "hot_screen_V": 1.9,
                     "fail_model_screen": [r["name"] for r in hot if r["status"] == "complete" and not r["off_V"] < 2.48794],
                     "fail_1p9": [r["name"] for r in hot if r["status"] == "complete" and not r["off_V"] < 1.9],
                     "zvs_S1_nominal": [r["zvs"] for r in hot if r["status"] == "complete"
                                        and r["case"] == "S1" and r["dt_ns"] in (348, 443)]},
    }
    summary["hot_150C"]["zvs_S1_nominal"] = f"{sum(summary['hot_150C']['zvs_S1_nominal'])}/{len(summary['hot_150C']['zvs_S1_nominal'])}"
    (OUT / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("RESULT " + json.dumps(summary))
    if bad:
        raise SystemExit(f"control failed: {bad[:5]}")


if __name__ == "__main__":
    main()
