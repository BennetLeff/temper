#!/usr/bin/env python3
"""Retain every ideal-drive crossing for B4's later current-threshold comparison."""
from __future__ import annotations

import csv
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope/round3"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402
from shunt_waveform import weighted_rms  # noqa: E402

FIELDS = ["run_id", "event_index", "time_s", "direction", "tank_current_a",
          "tank_cap_voltage_v", "bus_voltage_v", "line_fraction",
          "inductive_sign", "a1_threshold_domain", "minimum_zvs_current_a", "zvs_verdict"]


def main() -> None:
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    if len(cases) != 135:
        raise RuntimeError(f"full 135-case grid required; have {len(cases)}")
    out = TASK / "outputs"
    summary = []
    shunt_rows = []
    crest_lo = math.asin(.9) / (2 * math.pi * 60)
    crest_hi = (math.pi - math.asin(.9)) / (2 * math.pi * 60)
    with (out / "switching-events.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for row in cases:
            params = {
                "VRMS": row["vrms_v"], "FREQ": row["frequency_hz"],
                "LLOAD": row["l_load_h"], "RPAN40": row["r_pan_40_ohm"],
                "RCOIL": row["r_coil_ohm"],
            }
            with tempfile.TemporaryDirectory(prefix="a5-events-") as scratch:
                result = run(KIT / "05-tank/tank.cir", params, keep=Path(scratch), raw=True)
                if result["aborted"] or result["failed"] or result["raw_returncode"] != 0:
                    raise RuntimeError(f"raw run failed for {row['run_id']}: {result}")
                waves = read_raw(Path(scratch) / "waves.raw")
                t = np.asarray(waves["time"])
                drv = np.asarray(waves["v(drv)"])
                tank = np.asarray(waves["i(vim)"])
                cap = np.asarray(waves["v(c)"])
                if abs(t[-1] - 8.3333e-3) > 1e-8:
                    raise RuntimeError(f"raw ended early for {row['run_id']}: {t[-1]}")
                shunt = np.where(drv >= 0, 1., -1.) * tank
                line_rms = weighted_rms(t, shunt, 0., 1/120)
                crest_rms = weighted_rms(t, shunt, crest_lo, crest_hi)
                if abs(line_rms - float(row["i_rms_a"])) / line_rms > .01:
                    raise RuntimeError(f"R5 integration disagrees with tank .meas: {row['run_id']}")
                shunt_rows.append({
                    "run_id": row["run_id"],
                    "line_average_r5_rms_a": line_rms,
                    "crest_interval_r5_rms_a": crest_rms,
                    "arithmetic_sample_rms_a_wrong": float(np.sqrt(np.mean(shunt*shunt))),
                })
                indexes = np.flatnonzero(((drv[:-1] < 0) & (drv[1:] >= 0)) |
                                         ((drv[:-1] > 0) & (drv[1:] <= 0)))
                delta = drv[indexes+1] - drv[indexes]
                indexes = indexes[delta != 0]
                delta = delta[delta != 0]
                weights = -drv[indexes] / delta
                times = t[indexes] + weights * (t[indexes+1] - t[indexes])
                currents = tank[indexes] + weights * (tank[indexes+1] - tank[indexes])
                caps = cap[indexes] + weights * (cap[indexes+1] - cap[indexes])
                directions = np.where(delta > 0, "rising", "falling")
                fractions = np.abs(np.sin(2 * np.pi * 60 * times))
                bus = float(row["vrms_v"]) * math.sqrt(2) * fractions
                signs = np.where(delta > 0, currents < 0, currents > 0)
                for index in range(len(times)):
                    writer.writerow({
                        "run_id": row["run_id"], "event_index": index,
                        "time_s": times[index], "direction": directions[index],
                        "tank_current_a": currents[index],
                        "tank_cap_voltage_v": caps[index],
                        "bus_voltage_v": bus[index], "line_fraction": fractions[index],
                        "inductive_sign": bool(signs[index]),
                        "a1_threshold_domain": "BELOW_A1_120V_REQUIRES_RUN" if bus[index] < 120
                            else "120_TO_198V_INTERPOLATION_NEEDS_VALIDATION",
                        "minimum_zvs_current_a": "", "zvs_verdict": "PENDING_A1",
                    })
                qualifying = fractions >= .2
                summary.append({
                    "run_id": row["run_id"], "raw_end_s": float(t[-1]),
                    "raw_points": len(t), "event_count": len(times),
                    "events_above_20pct_line": int(qualifying.sum()),
                    "inductive_sign_above_20pct_count": int(np.count_nonzero(signs & qualifying)),
                    "min_abs_current_above_20pct_a": float(np.min(abs(currents[qualifying]))),
                    "max_abs_current_above_20pct_a": float(np.max(abs(currents[qualifying]))),
                })
            print(json.dumps({"run_id": row["run_id"], "events": len(times)}), flush=True)
            stream.flush()
    (out / "switching-events-summary.json").write_text(json.dumps({
        "source": "ideal full-bridge deck; A1 ZVS threshold not applied",
        "case_count": len(summary), "cases": summary,
    }, indent=2) + "\n")
    with (out / "shunt-grid.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, shunt_rows[0].keys())
        writer.writeheader()
        writer.writerows(shunt_rows)


if __name__ == "__main__":
    main()
