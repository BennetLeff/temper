#!/usr/bin/env python3
"""Find the ideal-deck frequency for each documented pan/line/power corner.

This is a task-local experiment, not a permanent engineering rule.  The
source of pan ranges is docs/hardware/power-section-120v/coil_mc.rs PANS.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import run  # noqa: E402 - starter-kit API required by runbook

DECK = KIT / "05-tank/tank.cir"
PAN_CLASSES = (
    ("cast_iron", (0.74, 0.86), (0.036, 0.052)),
    ("carbon_or_430_steel", (0.66, 0.80), (0.029, 0.041)),
    ("triply_clad_GUESS", (0.66, 0.82), (0.018, 0.032)),
    ("low_R_silargan_like", (0.58, 0.68), (0.020, 0.029)),
    ("offset_or_small_pan", (0.80, 0.90), (0.012, 0.022)),
)
REQUIRED_MEAS = {"i_rms", "i_pk", "vc_pk", "vc_rms", "p_avg"}
FIELDS = (
    "pan", "corner", "vrms_v", "target_w", "status", "f_res_hz",
    "frequency_hz", "l_load_h", "r_pan_40_ohm", "r_coil_ohm",
    "i_rms_a", "i_pk_a", "vc_pk_v", "vc_rms_v", "p_avg_w",
    "c21_i_rms_a", "c22_i_rms_a", "c23_i_rms_a",
    "ct_sec_v_pk_ideal_v", "ct_sec_volt_us_ideal",
    "bleed_each_v_pk_v", "bleed_each_p_avg_w", "c_energy_pk_j",
    "rectified_leg_return_i_rms_a", "run_id",
)


def _checked_run(params: dict[str, str], run_id: str, keep: bool) -> dict:
    """Call the kit API, then independently check the final retained run."""
    with tempfile.TemporaryDirectory(prefix="tank05-") as scratch:
        directory = TASK / "outputs/runs" / run_id if keep else Path(scratch)
        result = run(DECK, params, keep=directory)
        measurements = result["meas"]
        if result["aborted"] or result["failed"] or REQUIRED_MEAS - measurements.keys():
            (TASK / "outputs/failure.json").write_text(json.dumps(result, indent=2))
            raise RuntimeError(f"ngspice missing or failed .meas: {run_id}: {result}")
        if any(not math.isfinite(measurements[key]) for key in REQUIRED_MEAS):
            raise RuntimeError(f"nonfinite .meas: {run_id}: {result}")
        if keep:
            replay = subprocess.run(
                ["ngspice", "-b", DECK.name], cwd=directory,
                capture_output=True, text=True, timeout=120,
            )
            full_log = replay.stdout + replay.stderr
            (directory / "ngspice-full.txt").write_text(full_log)
            (directory / "result.json").write_text(json.dumps(result, indent=2))
            if replay.returncode != 0 or "No. of Data Rows" not in full_log:
                raise RuntimeError(f"replay failed: {run_id}: exit={replay.returncode}")
            replay_meas = {
                match.group(1): float(match.group(2))
                for line in full_log.splitlines()
                if (match := re.match(r"^\s*([a-z_]+)\s*=\s*([-+\d.eE]+)", line))
            }
            if REQUIRED_MEAS - replay_meas.keys():
                raise RuntimeError(f"replay missing .meas: {run_id}")
            if any(
                not math.isclose(measurements[key], replay_meas[key], rel_tol=1e-4)
                for key in REQUIRED_MEAS
            ):
                raise RuntimeError(f"replay differed from first run: {run_id}")
            # The kit copies its shared vendor model even for this RLC deck.
            # Keep the model hash in the report, never a copied library.
            (directory / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        return result


def _params(vrms: int, freq: float, l_load: float, r_pan: float, r_coil: float) -> dict[str, str]:
    return {
        "VRMS": str(vrms), "FREQ": f"{freq:.8f}",
        "LLOAD": f"{l_load:.12g}", "RPAN40": f"{r_pan:.9g}",
        "RCOIL": f"{r_coil:.9g}",
    }


def _search(vrms: int, target: int, l_load: float, r_pan: float, r_coil: float,
            prefix: str) -> tuple[str, float, dict]:
    f_res = 1 / (2 * math.pi * math.sqrt(l_load * 0.54e-6))
    if f_res >= 60_000:
        raise RuntimeError(f"resonance above frequency ceiling: {prefix}: {f_res}")
    low = f_res * 1.0001
    high = 60_000.0
    lo = _checked_run(_params(vrms, low, l_load, r_pan, r_coil), prefix + "-fres", False)
    hi = _checked_run(_params(vrms, high, l_load, r_pan, r_coil), prefix + "-f60k", False)
    p_lo, p_hi = lo["meas"]["p_avg"], hi["meas"]["p_avg"]
    if p_lo < p_hi:
        raise RuntimeError(f"power not decreasing on inductive side: {prefix}: {p_lo}, {p_hi}")
    if p_lo < target:
        return "power-limited", low, lo
    if p_hi > target:
        return "below-minimum-at-60k", high, hi
    for index in range(14):
        mid = (low + high) / 2
        measured = _checked_run(_params(vrms, mid, l_load, r_pan, r_coil),
                                prefix + f"-bisect{index}", False)
        power = measured["meas"]["p_avg"]
        if abs(power - target) <= max(2.0, target * 0.002):
            return "frequency-control", mid, measured
        if power > target:
            low = mid
        else:
            high = mid
    return "frequency-control", mid, measured


def _rows(limit: int | None):
    count = 0
    for pan, kl_range, r40_range in PAN_CLASSES:
        for corner, frac in (("low", 0.0), ("mid", 0.5), ("high", 1.0)):
            kl = kl_range[0] + frac * (kl_range[1] - kl_range[0])
            r40 = r40_range[0] + frac * (r40_range[1] - r40_range[0])
            q = 0.0015 + frac * (0.0060 - 0.0015)
            for vrms in (108, 120, 140):
                for target in (1710, 855, 300):
                    if limit is not None and count >= limit:
                        return
                    count += 1
                    yield pan, corner, vrms, target, 70e-6 * kl, 70 * r40, 70 * q


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="bounded exploratory prefix")
    args = parser.parse_args()
    output = TASK / "outputs/cases.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for pan, corner, vrms, target, l_load, r_pan, r_coil in _rows(args.limit):
            prefix = f"{pan}-{corner}-{vrms}v-{target}w"
            status, freq, _ = _search(vrms, target, l_load, r_pan, r_coil, prefix)
            result = _checked_run(_params(vrms, freq, l_load, r_pan, r_coil), prefix, True)
            values = result["meas"]
            i_rms, i_pk = values["i_rms"], values["i_pk"]
            # R39=1.5 ohm; 1:100 ratio. The C42 filter can lower v_sec.
            row = {
                "pan": pan, "corner": corner, "vrms_v": vrms, "target_w": target,
                "status": status, "f_res_hz": 1/(2*math.pi*math.sqrt(l_load*0.54e-6)),
                "frequency_hz": freq, "l_load_h": l_load,
                "r_pan_40_ohm": r_pan, "r_coil_ohm": r_coil,
                "i_rms_a": i_rms, "i_pk_a": i_pk,
                "vc_pk_v": values["vc_pk"], "vc_rms_v": values["vc_rms"],
                "p_avg_w": values["p_avg"],
                "c21_i_rms_a": i_rms * 0.22/0.54,
                "c22_i_rms_a": i_rms * 0.22/0.54,
                "c23_i_rms_a": i_rms * 0.10/0.54,
                "ct_sec_v_pk_ideal_v": i_pk/100*1.5,
                "ct_sec_volt_us_ideal": 1.5*i_pk/100/(math.pi*freq)*1e6,
                "bleed_each_v_pk_v": values["vc_pk"]/4,
                "bleed_each_p_avg_w": (values["vc_rms"]/4)**2/470_000,
                "c_energy_pk_j": 0.5*0.54e-6*values["vc_pk"]**2,
                # Magnitude of tank current is a proxy, not yet the actual
                # rectified shunt current. See report limitation.
                "rectified_leg_return_i_rms_a": "",
                "run_id": prefix,
            }
            writer.writerow(row)
            stream.flush()
            print(json.dumps({"run_id": prefix, "status": status,
                              "frequency_hz": freq, "i_pk_a": i_pk,
                              "i_rms_a": i_rms, "vc_pk_v": values["vc_pk"]}), flush=True)
            if i_pk > 88:
                raise RuntimeError(f"STOP: T1 88 A criterion failed at {prefix}: {i_pk:.3f} A")


if __name__ == "__main__":
    main()
