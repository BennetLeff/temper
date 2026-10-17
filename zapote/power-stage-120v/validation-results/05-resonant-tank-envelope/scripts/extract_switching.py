#!/usr/bin/env python3
"""Extract tank current where the ideal bridge drive changes sign.

The full raw waveform can be regenerated with this script; it is removed
after processing because it is tens of megabytes per case.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402


def select_case(run_id: str) -> dict[str, str]:
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["run_id"] == run_id:
                return row
    raise ValueError(f"case not found: {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    row = select_case(args.run_id)
    params = {
        "VRMS": row["vrms_v"], "FREQ": row["frequency_hz"],
        "LLOAD": row["l_load_h"], "RPAN40": row["r_pan_40_ohm"],
        "RCOIL": row["r_coil_ohm"],
    }
    with tempfile.TemporaryDirectory(prefix="tank05-raw-") as scratch:
        work = Path(scratch)
        result = run(KIT / "05-tank/tank.cir", params, keep=work, raw=True)
        if result["aborted"] or result["failed"] or len(result["meas"]) != 5:
            raise RuntimeError(f"failed measures: {result}")
        # The kit does not inspect the second (--raw) process exit code.
        # Re-run it explicitly and check both status and simulated end time.
        replay = subprocess.run(
            ["ngspice", "-b", "-r", "verified.raw", "tank.cir"],
            cwd=work, capture_output=True, text=True, timeout=120,
        )
        (TASK / "outputs" / f"{args.run_id}-raw-run.txt").write_text(
            replay.stdout + replay.stderr
        )
        if replay.returncode != 0:
            raise RuntimeError(f"raw replay exited {replay.returncode}")
        waves = read_raw(work / "verified.raw")
        time = waves["time"]
        if abs(time[-1] - 8.3333e-3) > 1e-8:
            raise RuntimeError(f"raw stopped early: {time[-1]}")
        drive = waves["v(drv)"]
        current = waves["i(vim)"]
        capacitor = waves["v(c)"]
        records = []
        for j in range(1, len(time)):
            if not ((drive[j - 1] < 0 <= drive[j]) or
                    (drive[j - 1] > 0 >= drive[j])):
                continue
            span = drive[j] - drive[j - 1]
            if span == 0:
                continue
            weight = -drive[j - 1] / span
            crossing = time[j - 1] + weight * (time[j] - time[j - 1])
            tank_i = current[j - 1] + weight * (current[j] - current[j - 1])
            cap_v = capacitor[j - 1] + weight * (capacitor[j] - capacitor[j - 1])
            line_fraction = abs(math.sin(2 * math.pi * 60 * crossing))
            direction = "rising" if span > 0 else "falling"
            # Ideal inductive-side phase: rising V requires negative I;
            # falling V requires positive I. This is only a sign screen.
            sign_ok = (tank_i < 0) if direction == "rising" else (tank_i > 0)
            records.append({
                "time_s": crossing, "direction": direction,
                "current_a": tank_i, "capacitor_v": cap_v,
                "line_fraction": line_fraction, "inductive_sign": sign_ok,
            })
        output = TASK / "outputs" / f"{args.run_id}-switching.csv"
        with output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        qualifying = [r for r in records if r["line_fraction"] >= 0.2]
        summary = {
            "run_id": args.run_id, "params": params,
            "raw_end_s": time[-1], "raw_points": len(time),
            "crossing_count": len(records),
            "qualifying_count": len(qualifying),
            "inductive_sign_count": sum(r["inductive_sign"] for r in qualifying),
            "abs_current_min_a": min(abs(r["current_a"]) for r in qualifying),
            "abs_current_max_a": max(abs(r["current_a"]) for r in qualifying),
        }
        (TASK / "outputs" / f"{args.run_id}-switching.json").write_text(
            json.dumps(summary, indent=2)
        )
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
