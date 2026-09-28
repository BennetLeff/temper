#!/usr/bin/env python3
"""Re-run one saved ideal-tank grid case and integrate its R5 waveform in time.

The common low-side shunt carries signed s*i_tank while diagonal bridge
states are commanded; s is the sign of the ideal bridge voltage. Its square is
i_tank squared. This deck has no dead-time switching and cannot quantify the
dead-time correction. The physical low-side body-diode path includes R5.
"""
import argparse
import csv
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope/round3"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402


def weighted_rms(t: np.ndarray, y: np.ndarray, lo: float, hi: float) -> float:
    """Integrate y² with endpoint interpolation over a specified time window."""
    inside = (t > lo) & (t < hi)
    ts = np.r_[lo, t[inside], hi]
    ys = np.r_[np.interp(lo, t, y), y[inside], np.interp(hi, t, y)]
    return math.sqrt(float(np.trapezoid(ys * ys, ts) / (hi - lo)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["run_id"] == args.run_id)
    params = {
        "VRMS": row["vrms_v"], "FREQ": row["frequency_hz"],
        "LLOAD": row["l_load_h"], "RPAN40": row["r_pan_40_ohm"],
        "RCOIL": row["r_coil_ohm"],
    }
    out = TASK / "outputs/shunt" / args.run_id
    result = run(KIT / "05-tank/tank.cir", params, keep=out, raw=True)
    if result["aborted"] or result["failed"] or result["raw_returncode"] != 0:
        raise RuntimeError(result)
    waves = read_raw(out / "waves.raw")
    t = np.asarray(waves["time"])
    tank = np.asarray(waves["i(vim)"])
    drv = np.asarray(waves["v(drv)"])
    cap = np.asarray(waves["v(c)"])
    shunt = np.where(drv >= 0, 1.0, -1.0) * tank
    end = 1 / 120
    assert abs(t[-1] - 8.3333e-3) < 1e-7
    crest_lo = math.asin(0.9) / (2 * math.pi * 60)
    crest_hi = (math.pi - math.asin(0.9)) / (2 * math.pi * 60)
    line_rms = weighted_rms(t, shunt, 0, end)
    crest_rms = weighted_rms(t, shunt, crest_lo, crest_hi)
    if abs(line_rms - float(row["i_rms_a"])) / line_rms > 0.01:
        raise RuntimeError("Waveform integral disagrees with grid .meas")
    k = int(np.argmax(np.abs(cap)))
    report = {
        "run_id": args.run_id, "model": "ideal diagonal full bridge; no dead time",
        "bridge_state": "s=sign(v(drv)); i_R5=s*i_tank; low-side source return through R5",
        "dead_time_topology": "when all four gates are off, one high-side and one low-side body diode conduct; the low-side path still crosses R5, so the current-to-R5 magnitude factor remains one. Finite-dead-time changes to the tank waveform are not resolved by this ideal deck.",
        "line_average_r5_rms_a": line_rms,
        "crest_interval_r5_rms_a": crest_rms,
        "crest_interval_definition": "rectified line voltage >= 90% of its crest",
        "crest_interval_s": [crest_lo, crest_hi],
        "arithmetic_sample_rms_a_wrong": float(np.sqrt(np.mean(shunt * shunt))),
        "time_step_min_s": float(np.diff(t).min()),
        "time_step_max_s": float(np.diff(t).max()),
        "tank_cap_peak_state": {
            "time_s": float(t[k]), "tank_cap_voltage_v": float(cap[k]),
            "tank_current_a": float(tank[k]),
            "line_bus_voltage_v": float(row["vrms_v"]) * math.sqrt(2)
                * abs(math.sin(2 * math.pi * 60 * float(t[k]))),
        },
        "measurements": result["meas"], "params": params,
    }
    np.savez_compressed(out / "waveform.npz", time_s=t, tank_current_a=tank,
                        shunt_current_a=shunt, capacitor_voltage_v=cap,
                        bridge_voltage_v=drv)
    with (out / "waves.raw").open("rb") as source, gzip.open(out / "waves.raw.gz", "wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    (out / "waves.raw").unlink()
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
