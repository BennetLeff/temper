#!/usr/bin/env python3
"""Trip the saved grid's maximum-C-voltage state into six finite bus capacitors."""
from __future__ import annotations

import csv
import gzip
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
UNIT = ROOT / "zapote/power-stage-120v"
KIT = UNIT / "validation-plan/sim-kit"
TASK = UNIT / "validation-results/05-resonant-tank-envelope/round3"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402


def main() -> None:
    with (TASK / "outputs/cases.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    if len(cases) != 135:
        raise RuntimeError(f"full 135-case grid required; have {len(cases)}")
    worst = max(cases, key=lambda row: float(row["vc_pk_v"]))
    shunt_file = TASK / "outputs/shunt" / worst["run_id"] / "result.json"
    if not shunt_file.exists():
        subprocess.run([sys.executable, str(TASK / "scripts/shunt_waveform.py"),
                        worst["run_id"]], check=True)
    state = json.loads(shunt_file.read_text())["tank_cap_peak_state"]
    vcap = state["tank_cap_voltage_v"]
    i0 = state["tank_current_a"]
    vbus = state["line_bus_voltage_v"]
    if abs(abs(vcap) - float(worst["vc_pk_v"])) > 0.05:
        raise RuntimeError("Trip initial state disagrees with saved grid peak")
    report = {
        "source_grid_case": worst["run_id"], "source_state": state,
        "board_bus_parts": "C5/C6 2.7 uF each +/-5%; C38-C41 0.1 uF each +/-10%",
        "model": "all gates off, idealized four body diodes, finite lumped bus caps; no rectifier, diode recovery, capacitor ESR/ESL or layout parasitics",
        "cases": [],
    }
    out = TASK / "outputs/trip"
    out.mkdir(parents=True, exist_ok=True)
    for label, bulk_scale, local_scale in (
        ("low_bus_cap", .95, .90), ("nominal", 1., 1.),
        ("high_bus_cap", 1.05, 1.10),
    ):
        cbulk = 2.7e-6 * bulk_scale
        clocal = .1e-6 * local_scale
        cbus = 2 * cbulk + 4 * clocal
        ctank = .54e-6
        lload = float(worst["l_load_h"])
        params = {
            "LLOAD": worst["l_load_h"],
            "RPAN40": worst["r_pan_40_ohm"],
            "RCOIL": worst["r_coil_ohm"],
            "FREQ": worst["frequency_hz"],
            "VBUS0": f"{vbus:.12g}",
            "VCAP0": f"{vcap:.12g}",
            "I0": f"{i0:.12g}",
            "CBULK": f"{cbulk:.12g}",
            "CLOCAL": f"{clocal:.12g}",
        }
        directory = out / label
        result = run(TASK / "scripts/trip_off.cir", params, keep=directory, raw=True)
        required = {"bus_peak", "bus_final", "cap_final", "i_final", "cap_abs_peak", "shunt_abs_peak"}
        if result["aborted"] or result["failed"] or required - result["meas"].keys():
            raise RuntimeError(f"trip run failed: {label}: {result}")
        waves = read_raw(directory / "waves.raw")
        t = np.asarray(waves["time"])
        cap = np.asarray(waves["v(tank_c)"]) - np.asarray(waves["v(sw_b)"])
        bus = np.asarray(waves["v(bus_p)"])
        current = np.asarray(waves["i(ltank)"])
        shunt = np.asarray(waves["i(vsh)"])
        legret = np.asarray(waves["v(leg_ret)"])
        swa = np.asarray(waves["v(sw_a)"])
        swb = np.asarray(waves["v(sw_b)"])
        rtot = float(worst["r_coil_ohm"]) + float(worst["r_pan_40_ohm"]) * math.sqrt(float(worst["frequency_hz"])/40000)
        powers = {
            "pan_coil_resistance": current*current*rtot,
            "r5": shunt*shunt*.001,
            "tank_bleed": cap*cap/1.88e6,
            "bus_leak": bus*bus/1e9,
            "four_idealized_diodes":
                np.asarray(waves["i(vha)"])*(swa-bus)
                + np.asarray(waves["i(vla)"])*(legret-swa)
                + np.asarray(waves["i(vhb)"])*(swb-bus)
                + np.asarray(waves["i(vlb)"])*(legret-swb),
        }
        loss_breakdown = {name: float(np.trapezoid(power, t))
                          for name, power in powers.items()}
        assert t[-1] >= 500e-6 - 1e-10
        above = np.where(abs(cap) > 60)[0]
        if len(above) and above[-1] < len(t) - 1:
            j = int(above[-1])
            touch_cross_s = float(np.interp(60, [abs(cap[j+1]), abs(cap[j])],
                                            [t[j+1], t[j]]))
            touch_method = "last simulated crossing of |tank capacitor voltage| below 60 V"
        elif len(above):
            residual = abs(float(cap[-1]))
            touch_cross_s = float(t[-1] + 1.88e6 * ctank * math.log(residual / 60))
            touch_method = "500-us freewheel state plus isolated 1.88-Mohm RC exponential"
        else:
            touch_cross_s = 0.0
            touch_method = "already below threshold at trip"
        e_initial = .5 * cbus * vbus*vbus + .5 * ctank * vcap*vcap + .5 * lload*i0*i0
        e_final = .5 * cbus * float(bus[-1])**2 + .5 * ctank * float(cap[-1])**2 + .5 * lload*float(current[-1])**2
        balance_error = e_initial - e_final - sum(loss_breakdown.values())
        if abs(balance_error) / e_initial > .01:
            raise RuntimeError(f"trip energy balance failed at {label}: {balance_error} J")
        item = {
            "tolerance_case": label, "params": params,
            "bus_capacitance_f": cbus,
            "initial_tank_energy_j": .5 * ctank * vcap*vcap + .5 * lload*i0*i0,
            "initial_total_stored_energy_j": e_initial,
            "bus_peak_v": float(np.max(bus)),
            "bus_peak_meas_v": result["meas"]["bus_peak"],
            "bus_final_v": float(bus[-1]),
            "residual_tank_cap_v": float(cap[-1]),
            "residual_tank_current_a": float(current[-1]),
            "trip_shunt_abs_peak_a": float(np.max(abs(shunt))),
            "max_abs_r5_vs_tank_magnitude_difference_a": float(np.max(abs(abs(shunt)-abs(current)))),
            "final_total_stored_energy_j": e_final,
            "dissipated_energy_j": e_initial - e_final,
            "integrated_loss_breakdown_j": loss_breakdown,
            "energy_balance_error_j": balance_error,
            "energy_balance_error_fraction_of_initial": balance_error/e_initial,
            "last_60v_crossing_after_trip_s": touch_cross_s,
            "touch_time_method": touch_method,
        }
        np.savez_compressed(directory / "waveform.npz", time_s=t, bus_voltage_v=bus,
                            tank_cap_voltage_v=cap, tank_current_a=current,
                            shunt_current_a=shunt)
        with (directory / "waves.raw").open("rb") as source, gzip.open(directory / "waves.raw.gz", "wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        (directory / "waves.raw").unlink()
        (directory / "result.json").write_text(json.dumps(item, indent=2) + "\n")
        report["cases"].append(item)
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
