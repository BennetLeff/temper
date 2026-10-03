#!/usr/bin/env python3
"""Exploratory B1 grid, stopping after the first resolved failed criterion."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
KIT = POWER / "validation-plan" / "sim-kit"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402

DECK = HERE / "complementary_leg.cir"
A2 = HERE.parent / "a2-inductance" / "outputs" / "loop_inductance_fallback_heuristic.json"
MODEL = KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
BOARD = POWER / "native-15" / "section.kicad_pcb"
OUT = HERE / "outputs"
EXPECTED = {
    A2: "4365536d40dfdc2580e01ac10657874f72f4ce873e331d0248581c061bf49b35",
    MODEL: "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
    BOARD: "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155",
}
T1 = 2e-6
VECTORS = ("time", "v(sw)", "v(xql.dd)", "v(xql.g)", "v(xql.s)",
           "v(xqh.dd)", "v(xqh.g)", "v(xqh.s)", "v(gl_cmd)", "v(kret)",
           "v(gh_cmd)", "v(s_hs)", "i(vids)")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crossing(time: np.ndarray, value: np.ndarray, level: float,
             begin: float, rising: bool) -> float | None:
    first = max(1, int(np.searchsorted(time, begin)))
    left, right = value[first - 1:-1], value[first:]
    match = (left < level) & (right >= level) if rising else (left > level) & (right <= level)
    indices = np.flatnonzero(match)
    if not len(indices):
        return None
    i = first + int(indices[0])
    return float(time[i - 1] + (level - value[i - 1]) *
                 (time[i] - time[i - 1]) / (value[i] - value[i - 1]))


def scenario_params(scenario: dict, bus: int, current: int, direction: int,
                    deadtime_ns: int, gate_scale: float, step_ns: float) -> dict[str, str]:
    params = {key: f"{scenario[key]:.12g}n" for key in
              ("LD_HS", "LS_HS", "LD_LS", "LCS", "LS_LS", "LCAP", "LBULK")}
    params.update({"LG_HS": f"{scenario['LG_high_side']*gate_scale:.12g}n",
                   "LG_LS": f"{scenario['LG_low_side']*gate_scale:.12g}n",
                   "VBUS": str(bus), "IL": str(current), "DIR": str(direction),
                   "DT": f"{deadtime_ns}n", "TRMAX": f"{step_ns:g}n"})
    return params


def one_case(leg: str, corner: str, scenario: dict, bus: int, current: int,
             direction: int, deadtime_ns: int, gate_scale: float, step_ns: float) -> dict:
    label = f"{leg}_{corner}_v{bus}_i{current}_d{direction}_s{step_ns:g}"
    if deadtime_ns != 348:
        label += f"_dt{deadtime_ns}"
    if gate_scale != 1:
        label += f"_lg{gate_scale:g}"
    folder = OUT / "runs" / label
    params = scenario_params(scenario, bus, current, direction, deadtime_ns, gate_scale, step_ns)
    result = run(DECK, params, keep=folder, raw=True)
    (folder / "run-result.json").write_text(json.dumps(result, indent=2) + "\n")
    needed = {"vds_ls_die_pk", "vds_hs_die_pk", "vgs_ls_die_max",
              "vgs_ls_die_min", "vgs_hs_die_max", "vgs_hs_die_min"}
    if result["aborted"] or result["failed"] or needed - result["meas"].keys():
        raise RuntimeError(f"ngspice incomplete for {label}: {result['log_tail']}")
    wave = read_raw(folder / "waves.raw")
    if set(VECTORS) - set(wave):
        raise RuntimeError(f"waveform vectors missing for {label}: {set(VECTORS)-set(wave)}")
    w = {key: np.asarray(wave[key]) for key in VECTORS}
    time = w["time"]
    end = T1 + deadtime_ns*1e-9 + 0.8e-6
    if len(time) < 1000 or not np.all(np.diff(time) > 0) or time[-1] < end - 1e-12:
        raise RuntimeError(f"transient incomplete for {label}")
    cmd = {"l": w["v(gl_cmd)"] - w["v(kret)"],
           "h": w["v(gh_cmd)"] - w["v(s_hs)"]}
    outgoing, incoming = (("l", "h") if direction == 0 else ("h", "l"))
    command_off = crossing(time, cmd[outgoing], 7.5, T1 - 10e-9, False)
    command_on = crossing(time, cmd[incoming], 7.5, T1, True)
    if command_off is None or command_on is None or abs(command_on-command_off-deadtime_ns*1e-9) > 1e-9:
        raise RuntimeError(f"command deadtime invalid for {label}")
    if (np.interp(T1-10e-9, time, cmd[outgoing]) < 14 or
            np.interp(T1-10e-9, time, cmd[incoming]) > 1 or
            np.any((cmd["l"] > 7.5) & (cmd["h"] > 7.5))):
        raise RuntimeError(f"complementary drive invalid for {label}")
    vds = {side: w[f"v(xq{side}.dd)"] - w[f"v(xq{side}.s)"] for side in ("l", "h")}
    vgs = {side: w[f"v(xq{side}.g)"] - w[f"v(xq{side}.s)"] for side in ("l", "h")}
    window = (time >= T1) & (time <= end)
    off_window = (time >= command_on) & (time <= end)
    before_on = (time >= command_on-20e-9) & (time <= command_on)
    if not np.any(off_window) or not np.any(before_on):
        raise RuntimeError(f"missing edge window for {label}")
    peaks = {side: float(np.max(vds[side][window])) for side in ("l", "h")}
    for side, key in (("l", "vds_ls_die_pk"), ("h", "vds_hs_die_pk")):
        if not math.isclose(peaks[side], result["meas"][key], rel_tol=0.002):
            raise RuntimeError(f"raw/meas peak disagreement for {label}: {side}")
    edge_start = crossing(time, w["v(sw)"], bus*(0.1 if direction == 0 else 0.9), T1, direction == 0)
    edge_end = (crossing(time, w["v(sw)"], bus*(0.9 if direction == 0 else 0.1),
                         edge_start, direction == 0) if edge_start is not None else None)
    edge20_start = crossing(time, w["v(sw)"], bus*(0.2 if direction == 0 else 0.8), T1, direction == 0)
    edge80_end = (crossing(time, w["v(sw)"], bus*(0.8 if direction == 0 else 0.2),
                           edge20_start, direction == 0) if edge20_start is not None else None)
    # A 1 ns secant gives an edge-rate estimate independent of the adaptive time steps.
    secant_t = np.arange(T1, command_on+0.2e-6, 0.5e-9)
    secant_a = np.interp(secant_t, time, w["v(sw)"])
    secant_b = np.interp(secant_t+1e-9, time, w["v(sw)"])
    secant_mid = (secant_a+secant_b)/2
    interior = (secant_mid >= 0.1*bus) & (secant_mid <= 0.9*bus)
    dvdt = float(np.max(np.abs(secant_b[interior]-secant_a[interior])/1e-9)) if np.any(interior) else None
    with gzip.open(folder / "commutation.csv.gz", "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", "sw_v", "vds_ls_die_v", "vds_hs_die_v",
                         "vgs_ls_die_v", "vgs_hs_die_v", "id_ls_pin_a",
                         "ls_command_v", "hs_command_v"))
        for i in np.flatnonzero((time >= T1-0.1e-6) & (time <= end)):
            writer.writerow(tuple(format(float(x), ".12g") for x in
                                  (time[i], w["v(sw)"][i], vds["l"][i], vds["h"][i],
                                   vgs["l"][i], vgs["h"][i], w["i(vids)"][i],
                                   cmd["l"][i], cmd["h"][i])))
    (folder / "waves.raw").unlink()
    (folder / MODEL.name).unlink()
    record = {
        "case": label, "leg": leg, "scenario": corner, "local_capacitor": scenario["selected_local_capacitor"],
        "deadtime_ns": deadtime_ns, "gate_inductance_scale": gate_scale,
        "params": params, "samples": len(time), "command_off_s": command_off,
        "command_on_s": command_on, "command_gap_ns": (command_on-command_off)*1e9,
        "incoming_die_vds_pre20_max_abs_v": float(np.max(np.abs(vds[incoming][before_on]))),
        "zvs_pre20_within_5pct_bus_proxy": bool(np.all(np.abs(vds[incoming][before_on]) <= .05*bus)),
        "peak_die_vds_ls_v": peaks["l"], "peak_die_vds_hs_v": peaks["h"],
        "off_device_die_vgs_during_partner_on_max_v": float(np.max(vgs[outgoing][off_window])),
        "die_vgs_min_v": {side: float(np.min(vgs[side][window])) for side in ("l", "h")},
        "die_vgs_max_v": {side: float(np.max(vgs[side][window])) for side in ("l", "h")},
        "edge_10_90_s": edge_end-edge_start if edge_end is not None else None,
        "edge_20_80_s": edge80_end-edge20_start if edge80_end is not None else None,
        "edge_complete_before_command": bool(edge_end is not None and edge_end <= command_on),
        "peak_abs_dvdt_10_90_1ns_v_per_s": dvdt,
        "LBULK_omits_internal_capacitor_ESL": True,
        "evidence_class": "A2 heuristic scenario sensitivity only; not physical bound or board qualification",
    }
    (folder / "case.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def failures(case: dict, current: int, bus: int, direction: int) -> list[str]:
    failures_found = []
    # The switch undergoing turn-off is low-side for DIR=0, high-side for DIR=1.
    peak = case["peak_die_vds_ls_v" if direction == 0 else "peak_die_vds_hs_v"]
    if current in (61, 71) and bus == 280:
        if peak > 585:
            failures_found.append(f"fault die VDS {peak:.3f} V > 585 V")
    elif current not in (61, 71) and peak > 520:
        failures_found.append(f"normal die VDS {peak:.3f} V > 520 V")
    if case["off_device_die_vgs_during_partner_on_max_v"] > 3.0:
        failures_found.append("off-device die VGS exceeds Vth,min 3.5 V minus 0.5 V")
    for side in ("l", "h"):
        if case["die_vgs_min_v"][side] < -30 or case["die_vgs_max_v"][side] > 30:
            failures_found.append(f"{side} die VGS exceeds dynamic +/-30 V")
    if current == 37 and not case["zvs_pre20_within_5pct_bus_proxy"]:
        failures_found.append("S1 ZVS 20 ns / 5%-bus proxy not achieved")
    return failures_found


def main() -> None:
    for path, expected in EXPECTED.items():
        actual = digest(path)
        if actual != expected:
            raise RuntimeError(f"input hash mismatch: {path}: {actual}")
    data = json.loads(A2.read_text())
    if data["source_revision"] != "44417ae1489fd00e2d652fd3b2c1582b76d17630":
        raise RuntimeError("A2 source revision changed")
    scenarios = data["deck_parameters_heuristic_scenario_nH"]
    OUT.mkdir(exist_ok=True)
    # S1 first, then S2, S3 and S4. A criterion failure stops later rows.
    grid = [(bus, current, direction, leg, corner, deadtime_ns, gate_scale)
            for current in (37, 61, 71, 2, 5, 10, 20)
            for bus in (170, 198, 280)
            for direction in (0, 1)
            for leg in ("A", "B")
            for corner in ("min", "max")
            for deadtime_ns in (348, 250, 450)
            for gate_scale in (1, .5, 2)]
    completed = []
    first_failure = None
    for index, (bus, current, direction, leg, corner, deadtime_ns, gate_scale) in enumerate(grid):
        scenario = scenarios[leg][corner]
        coarse = one_case(leg, corner, scenario, bus, current, direction, deadtime_ns, gate_scale, 0.2)
        fine = one_case(leg, corner, scenario, bus, current, direction, deadtime_ns, gate_scale, 0.1)
        checks = {}
        for side in ("ls", "hs"):
            key = f"peak_die_vds_{side}_v"
            delta = abs(coarse[key]-fine[key])/max(abs(fine[key]), 1e-12)
            checks[key] = delta
            if delta >= .02:
                raise RuntimeError(f"peak did not converge under timestep halving: {key} {delta}")
        observed = failures(fine, current, bus, direction)
        row = {"coarse": coarse["case"], "fine": fine["case"], "peak_change_fraction": checks,
               "failures": observed}
        completed.append(row)
        print(json.dumps({"row": index+1, "case": fine["case"], "failures": observed}), flush=True)
        if observed:
            first_failure = row
            break
    result = {
        "status": "STOPPED_FIRST_FAILED_CRITERION" if first_failure else "EXPLORATORY_GRID_COMPLETE",
        "evidence_class": "A2 heuristic scenario stress; min/max not physical bounds; no board qualification",
        "source_revision": data["source_revision"],
        "input_sha256": {str(path): value for path, value in EXPECTED.items()},
        "deck_sha256": digest(DECK), "runtime": "ngspice 45.2; Python 3.12; Infineon L1 CFD7",
        "selected_grid_rows": len(grid), "completed_grid_rows": len(completed),
        "not_run_grid_rows": len(grid)-len(completed),
        "first_failure": first_failure, "rows": completed,
        "limitations": ["A2 FastHenry builds failed twice and qualified parameters are null",
                        "A2 0.25 mm routes are complete, but Q3 return route lacks 0.5 mm convergence",
                        "min/max are heuristic scenarios, not physical inductance bounds",
                        "LBULK is copper-only and omits unknown bulk-capacitor internal ESL",
                        "constant-current load, driver output approximation, 27 C model"],
    }
    (OUT / "grid-results.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
