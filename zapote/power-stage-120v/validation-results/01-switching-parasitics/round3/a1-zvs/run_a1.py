#!/usr/bin/env python3
"""Round-3 A1: complementary-leg ZVS thresholds, edges, and turn-off energy.

Run from any directory with the pinned Infineon model in the ignored sim-kit
models/vendor directory. Each run keeps its complete ngspice log and every
saved simulator point around the commutation, both gzip compressed.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
KIT = POWER / "validation-plan" / "sim-kit"
DECK = HERE / "complementary_leg.cir"
BOARD = POWER / "native-15" / "section.kicad_pcb"
MODEL = KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
MODEL_ZIP = KIT / "models" / "vendor" / "cfd7-650.zip"
OPTIONS = KIT / "common" / "options.inc"
OUT = HERE / "outputs"
RUNS = OUT / "runs"
EXPECTED = {
    BOARD: "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155",
    MODEL: "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
    MODEL_ZIP: "5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d",
}
T1 = 2e-6
CURRENTS = (1, 2, 3, 4, 6, 8, 10, 15, 20, 37)
BUSES = (120, 170, 198)
SCALES = (0.5, 1.0, 3.0)
DEADTIMES = (250, 348, 450)
BOARD_L_NH = {"LD_HS": 4, "LS_HS": 4, "LD_LS": 4, "LS_LS": 4,
              "LCAP": 3, "LBULK": 30, "LCS": 1, "LG": 20}
VECTORS = (
    "time", "v(sw)", "v(xql.g)", "v(xql.s)", "v(xql.dd)", "v(xqh.g)",
    "v(xqh.s)", "v(xqh.dd)", "v(gl_cmd)", "v(kret)", "v(gh_cmd)",
    "v(s_hs)", "i(vids)", "i(vidh)",
    "v(xql.x1.d)", "v(xqh.x1.d)", "v(xql.x1.d1)", "v(xqh.x1.d1)",
    "i(v.xql.x1.v_ichannel)", "i(v.xqh.x1.v_ichannel)",
    "i(v.xql.x1.v_iepi)", "i(v.xqh.x1.v_iepi)",
    "i(v.xql.x1.v_sense2)", "i(v.xqh.x1.v_sense2)",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label(bus: int, direction: int, deadtime: int, current: float,
          scale: float, step_ns: float) -> str:
    return (f"v{bus}_d{direction}_dt{deadtime}_i{current:.5f}_"
            f"l{scale:g}_s{step_ns:g}")


def read_raw_selected(path: Path) -> dict[str, np.ndarray]:
    """Parse ngspice ASCII raw with only the deck's explicitly saved vectors."""
    with path.open() as handle:
        names: list[str] = []
        npoints = nvars = 0
        for line in handle:
            if line.startswith("No. Variables:"):
                nvars = int(line.partition(":")[2])
            elif line.startswith("No. Points:"):
                npoints = int(line.partition(":")[2])
            elif line.startswith("Variables:"):
                for _ in range(nvars):
                    names.append(next(handle).split()[1].lower())
            elif line.startswith("Values:"):
                break
        if set(VECTORS) - set(names):
            raise RuntimeError(f"missing raw vectors: {sorted(set(VECTORS) - set(names))}")
        # An ASCII raw point starts with its index, followed by nvars values.
        values = np.fromstring(handle.read(), sep=" ")
    if len(values) != npoints * (nvars + 1):
        raise RuntimeError(f"raw truncated: {len(values)} floats, expected {npoints * (nvars + 1)}")
    matrix = values.reshape(npoints, nvars + 1)
    if not np.array_equal(matrix[:, 0], np.arange(npoints)):
        raise RuntimeError("raw point indices are not sequential")
    return {name: matrix[:, i + 1] for i, name in enumerate(names)}


def interp_crossing(time: np.ndarray, signal: np.ndarray, level: float,
                    begin: float, rise: bool) -> float | None:
    first = max(1, int(np.searchsorted(time, begin)))
    a, b = signal[first - 1:-1], signal[first:]
    mask = (a < level) & (b >= level) if rise else (a > level) & (b <= level)
    indices = np.flatnonzero(mask)
    if not len(indices):
        return None
    i = first + int(indices[0])
    return float(time[i - 1] + (level - signal[i - 1]) *
                 (time[i] - time[i - 1]) / (signal[i] - signal[i - 1]))


def integrate(time: np.ndarray, signal: np.ndarray, start: float, stop: float) -> float:
    inside = (time > start) & (time < stop)
    t = np.concatenate(([start], time[inside], [stop]))
    y = np.interp(t, time, signal)
    return float(np.trapezoid(y, t))


def analyze(wave: dict[str, np.ndarray], bus: int, direction: int,
            deadtime: int, current: float, scale: float, step_ns: float) -> dict:
    time = wave["time"]
    expected_end = T1 + deadtime * 1e-9 + 0.8e-6
    if (len(time) < 1000 or not np.all(np.diff(time) > 0) or
            time[-1] < expected_end - 1e-12):
        raise RuntimeError(f"incomplete transient: {len(time)} points, stop {time[-1]:.12g}")
    side = "h" if direction == 0 else "l"
    outgoing = "l" if direction == 0 else "h"
    cmd_l = wave["v(gl_cmd)"] - wave["v(kret)"]
    cmd_h = wave["v(gh_cmd)"] - wave["v(s_hs)"]
    commands = {"l": cmd_l, "h": cmd_h}
    if (np.interp(T1 - 10e-9, time, commands[outgoing]) < 14 or
            np.interp(T1 - 10e-9, time, commands[side]) > 1 or
            np.interp(expected_end - 10e-9, time, commands[side]) < 14 or
            np.interp(expected_end - 10e-9, time, commands[outgoing]) > 1 or
            np.any((cmd_l > 7.5) & (cmd_h > 7.5))):
        raise RuntimeError("complementary commands failed")
    command_off = interp_crossing(time, commands[outgoing], 7.5, T1 - 10e-9, False)
    command_on = interp_crossing(time, commands[side], 7.5, T1, True)
    if command_off is None or command_on is None or abs(command_on-command_off-deadtime*1e-9) > 1e-9:
        raise RuntimeError(f"command gap failed: {command_off}, {command_on}")

    vds = {"l": wave["v(xql.dd)"] - wave["v(xql.s)"],
           "h": wave["v(xqh.dd)"] - wave["v(xqh.s)"]}
    start_20 = command_on - 20e-9
    near = (time >= start_20) & (time <= command_on)
    pre = np.concatenate(([np.interp(start_20, time, vds[side])], vds[side][near],
                          [np.interp(command_on, time, vds[side])]))
    zvs = bool(np.all(np.abs(pre) <= 0.05 * bus))
    sw = wave["v(sw)"]
    rise = direction == 0
    edge_start = interp_crossing(time, sw, bus * (0.1 if rise else 0.9), T1, rise)
    edge_end = (interp_crossing(time, sw, bus * (0.9 if rise else 0.1), edge_start, rise)
                if edge_start is not None else None)
    edge_s = edge_end-edge_start if edge_start is not None and edge_end is not None else None
    # A 1 ns secant suppresses misleading adaptive-step derivative spikes.
    slope_times = np.arange(T1, min(expected_end, command_on + 0.2e-6)-1e-9, 0.5e-9)
    slope_a = np.interp(slope_times, time, sw)
    slope_b = np.interp(slope_times + 1e-9, time, sw)
    mid = (slope_a + slope_b) / 2
    interior = (mid >= 0.1*bus) & (mid <= 0.9*bus)
    secants = np.abs(slope_b-slope_a)/1e-9
    peak_slope_10_90 = float(np.max(secants[interior])) if np.any(interior) else None
    peak_slope_full = float(np.max(secants)) if len(secants) else None

    model = "xql" if outgoing == "l" else "xqh"
    die_v = vds[outgoing]
    pin_id = wave["i(vids)" if outgoing == "l" else "i(vidh)"]
    channel_i = wave[f"i(v.{model}.x1.v_ichannel)"]
    epi_i = wave[f"i(v.{model}.x1.v_iepi)"]
    diode_i = wave[f"i(v.{model}.x1.v_sense2)"]
    core_d = wave[f"v({model}.x1.d)"]
    die_s = wave[f"v({model}.s)"]
    die_dd = wave[f"v({model}.dd)"]
    core_d1 = wave[f"v({model}.x1.d1)"]
    # Match the L1 model's heat-expression terms. Its heat parameter is zero,
    # so these are reconstructed dissipative proxies, not solved temperature.
    raw_channel_p = (core_d-die_s)*channel_i
    raw_epi_p = (die_dd-core_d1)*epi_i
    raw_diode_p = (die_dd-die_s)*diode_i
    channel_p = np.clip(raw_channel_p, 0, 1e5)
    epi_p = np.clip(raw_epi_p, 0, 1e5)
    diode_p = np.clip(raw_diode_p, 0, 1e5)
    turnoff_end = command_on
    turnoff_mask = (time >= command_off) & (time <= turnoff_end)
    raw_peak_powers = {"channel": float(np.max(raw_channel_p[turnoff_mask])),
                       "epi": float(np.max(raw_epi_p[turnoff_mask])),
                       "diode": float(np.max(raw_diode_p[turnoff_mask]))}
    port_j = integrate(time, die_v*pin_id, command_off, turnoff_end)
    channel_j = integrate(time, channel_p, command_off, turnoff_end)
    epi_j = integrate(time, epi_p, command_off, turnoff_end)
    diode_j = integrate(time, diode_p, command_off, turnoff_end)
    return {
        "bus_v": bus, "direction": direction, "deadtime_ns": deadtime,
        "current_a": current, "board_l_scale": scale, "max_step_ns": step_ns,
        "sample_count": len(time), "transient_end_s": float(time[-1]),
        "command_off_s": command_off, "command_on_s": command_on,
        "command_gap_ns": (command_on-command_off)*1e9,
        "incoming_die_vds_pre20_max_abs_v": float(np.max(np.abs(pre))),
        "zvs_20ns_5pct": zvs,
        "edge_10_90_s": edge_s, "edge_start_s": edge_start,
        "edge_end_s": edge_end, "edge_complete_before_command": bool(edge_end is not None and edge_end <= command_on),
        "peak_abs_dvdt_10_90_1ns_v_per_s": peak_slope_10_90,
        "peak_abs_dvdt_full_1ns_v_per_s": peak_slope_full,
        "peak_die_vds_l_v": float(np.max(vds["l"][(time >= T1) & (time <= expected_end)])),
        "peak_die_vds_h_v": float(np.max(vds["h"][(time >= T1) & (time <= expected_end)])),
        "outgoing_device": "LS" if outgoing == "l" else "HS",
        "turnoff_window_start_s": command_off, "turnoff_window_end_s": turnoff_end,
        "turnoff_die_vds_external_drain_id_proxy_j": port_j,
        "turnoff_model_channel_energy_j": channel_j,
        "turnoff_model_epi_energy_j": epi_j,
        "turnoff_model_diode_energy_j": diode_j,
        "turnoff_model_dissipative_sum_j": channel_j+epi_j+diode_j,
        "proxy_minus_model_dissipative_j": port_j-channel_j-epi_j-diode_j,
        "vendor_heat_clip_100kw_observed": any(p >= 1e5 for p in raw_peak_powers.values()),
        "vendor_heat_raw_peak_power_w": raw_peak_powers,
        "waveform": None,
    }


def save_wave(path: Path, wave: dict[str, np.ndarray], record: dict) -> None:
    time = wave["time"]
    inside = (time >= T1-0.1e-6) & (time <= record["command_on_s"]+0.25e-6)
    keys = ("time", "v(sw)", "v(xql.dd)", "v(xql.s)", "i(vids)",
            "v(xqh.dd)", "v(xqh.s)", "i(vidh)", "v(xql.g)", "v(xqh.g)",
            "v(xql.x1.d)", "v(xqh.x1.d)", "v(xql.x1.d1)", "v(xqh.x1.d1)",
            "i(v.xql.x1.v_ichannel)", "i(v.xqh.x1.v_ichannel)",
            "i(v.xql.x1.v_iepi)", "i(v.xqh.x1.v_iepi)",
            "i(v.xql.x1.v_sense2)", "i(v.xqh.x1.v_sense2)")
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", *keys[1:]))
        for i in np.flatnonzero(inside):
            writer.writerow(tuple(format(float(wave[k][i]), ".12g") for k in keys))


def run_case(bus: int, direction: int, deadtime: int, current: float,
             scale: float, step_ns: float = 0.2) -> dict:
    name = label(bus, direction, deadtime, current, scale, step_ns)
    folder = RUNS / name
    summary = folder / "case.json"
    if summary.exists():
        record = json.loads(summary.read_text())
        if "vendor_heat_clip_100kw_observed" in record:
            return record
        # The initial grid used a smaller saved vector set. Re-run from the
        # pinned deck so every published energy record gets a clip diagnostic.
        summary.unlink()
    if step_ns == 0.2 and (folder / "ngspice.log.gz").exists():
        with gzip.open(folder / "ngspice.log.gz", "rt") as handle:
            prior_log = handle.read()
        if "Timestep too small" in prior_log:
            fine = run_case(bus, direction, deadtime, current, scale, 0.1)
            fine["nominal_0p2ns_abort_log"] = str((folder / "ngspice.log.gz").relative_to(HERE))
            ((HERE / fine["waveform"]).parent / "case.json").write_text(
                json.dumps(fine, indent=2, allow_nan=False) + "\n")
            return fine
    folder.mkdir(parents=True, exist_ok=True)
    params = {"VBUS": str(bus), "IL": format(current, ".8g"), "DIR": str(direction),
              "DT": f"{deadtime}n", "TRMAX": f"{step_ns:g}n"}
    params.update({k: f"{v*scale:g}n" for k, v in BOARD_L_NH.items()})
    with tempfile.TemporaryDirectory(prefix="ps-a1-") as tmp:
        work = Path(tmp)
        deck_text = DECK.read_text().replace("../common/", str(KIT / "common") + "/")
        (work / DECK.name).write_text(deck_text)
        (work / "params.inc").write_text("".join(f".param {k}={v}\n" for k, v in params.items()))
        (work / ".spiceinit").write_text("set ngbehavior=psa\nset filetype=ascii\n")
        shutil.copyfile(MODEL, work / MODEL.name)
        proc = subprocess.run(["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", DECK.name],
                              cwd=work, capture_output=True, text=True, timeout=1800)
        log = proc.stdout + proc.stderr
        with gzip.open(folder / "ngspice.log.gz", "wt") as handle:
            handle.write(log)
        if (proc.returncode or not (work / "waves.raw").is_file() or
                re.search(r"Timestep too small|simulation\(s\) aborted|singular matrix|fatal error", log, re.I)):
            if step_ns == 0.2 and "Timestep too small" in log:
                fine = run_case(bus, direction, deadtime, current, scale, 0.1)
                fine["nominal_0p2ns_abort_log"] = str((folder / "ngspice.log.gz").relative_to(HERE))
                ((HERE / fine["waveform"]).parent / "case.json").write_text(
                    json.dumps(fine, indent=2, allow_nan=False) + "\n")
                return fine
            raise RuntimeError(f"ngspice failed {name}: rc={proc.returncode}; tail={log.splitlines()[-20:]}")
        wave = read_raw_selected(work / "waves.raw")
        record = analyze(wave, bus, direction, deadtime, current, scale, step_ns)
        save_wave(folder / "commutation.csv.gz", wave, record)
    record["waveform"] = str((folder / "commutation.csv.gz").relative_to(HERE))
    record["log"] = str((folder / "ngspice.log.gz").relative_to(HERE))
    record["params"] = params
    record["ngspice_returncode"] = proc.returncode
    summary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print("PASS", name, "ZVS" if record["zvs_20ns_5pct"] else "NON-ZVS", flush=True)
    return record


def parallel_cases(cases: list[tuple], jobs: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(run_case, *case) for case in cases]
        return [future.result() for future in as_completed(futures)]


def threshold(bus: int, direction: int, deadtime: int, scale: float) -> dict:
    # Start with a coarse physical grid, then bisect the first pass/fail span.
    samples = [run_case(bus, direction, deadtime, float(i), scale) for i in CURRENTS]
    sequence = [(r["current_a"], r["zvs_20ns_5pct"]) for r in samples]
    first_pass = next((i for i, (_, passed) in enumerate(sequence) if passed), len(sequence))
    if any(not passed for _, passed in sequence[first_pass:]):
        return {"bus_v": bus, "direction": direction, "deadtime_ns": deadtime,
                "board_l_scale": scale, "status": "nonmonotonic_grid",
                "threshold_a": None, "bracket_a": None, "grid_observations": sequence}
    passing = [r["current_a"] for r in samples if r["zvs_20ns_5pct"]]
    if not passing:
        # Document an explicit out-of-grid bracket if the 37 A reference fails.
        for current in (50.0, 75.0, 100.0):
            r = run_case(bus, direction, deadtime, current, scale)
            samples.append(r)
            if r["zvs_20ns_5pct"]:
                passing.append(current)
                break
    if not passing:
        return {"bus_v": bus, "direction": direction, "deadtime_ns": deadtime,
                "board_l_scale": scale, "status": "not_found_in_sampled_1_to_100A",
                "threshold_a": None, "bracket_a": None,
                "sampled_observations": [(r["current_a"], r["zvs_20ns_5pct"])
                                         for r in sorted(samples, key=lambda r: r["current_a"])]}
    hi = min(passing)
    failed = [r["current_a"] for r in samples if not r["zvs_20ns_5pct"] and r["current_a"] < hi]
    if not failed:
        return {"bus_v": bus, "direction": direction, "deadtime_ns": deadtime,
                "board_l_scale": scale, "status": "at_or_below_1A",
                "threshold_a": None, "bracket_a": [0.0, 1.0],
                "grid_observations": sequence}
    lo = max(failed)
    for _ in range(16):
        if hi - lo <= 0.5:
            break
        mid = (hi + lo) / 2
        if run_case(bus, direction, deadtime, mid, scale)["zvs_20ns_5pct"]:
            hi = mid
        else:
            lo = mid
    return {"bus_v": bus, "direction": direction, "deadtime_ns": deadtime,
            "board_l_scale": scale, "status": "bracketed",
            "threshold_a": (lo+hi)/2, "bracket_a": [lo, hi],
            "half_width_a": (hi-lo)/2,
            "outside_requested_1_to_37a_grid": hi > 37,
            "grid_observations": sequence}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--phase", choices=("grid", "thresholds", "resolution", "export", "all"), default="all")
    args = parser.parse_args()
    for path, expected in EXPECTED.items():
        if digest(path) != expected:
            raise RuntimeError(f"input hash mismatch: {path}")
    OUT.mkdir(exist_ok=True)
    RUNS.mkdir(exist_ok=True)
    source_files = {
        "native15_board": BOARD,
        "Infineon_IPW65R018CFD7_L1_vendor_library": MODEL,
        "Infineon_vendor_archive": MODEL_ZIP,
        "A1_deck": DECK,
        "A1_runner": HERE / "run_a1.py",
        "A1_audit": HERE / "audit_a1.py",
        "A1_threshold_refinement": HERE / "refine_thresholds.py",
        "sim_kit_options": OPTIONS,
        "round2_deck_reference": HERE.parents[1] / "round2" / "complementary_leg.cir",
        "round3_plan": POWER / "validation-plan" / "ROUND-3.md",
        "simulation_runbook": POWER / "validation-plan" / "SIMULATION-RUNBOOK.md",
    }
    (HERE / "source_hashes.json").write_text(json.dumps({
        name: {"path": str(path.relative_to(POWER)), "sha256": digest(path)}
        for name, path in source_files.items()
    }, indent=2) + "\n")
    if args.phase in ("grid", "all"):
        cases = [(bus, direction, 348, float(current), scale)
                 for bus in BUSES for direction in (0, 1) for scale in SCALES
                 for current in CURRENTS]
        parallel_cases(cases, args.jobs)
    if args.phase in ("thresholds", "all"):
        thresholds = []
        specs = [(bus, direction, dt, scale) for dt in (348, 250, 450)
                 for bus in BUSES for direction in (0, 1) for scale in SCALES]
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(threshold, *spec) for spec in specs]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as error:
                    spec = specs[futures.index(future)]
                    bus, direction, dt, scale = spec
                    result = {"bus_v": bus, "direction": direction,
                              "deadtime_ns": dt, "board_l_scale": scale,
                              "status": "simulation_failed", "threshold_a": None,
                              "bracket_a": None, "error": str(error)}
                thresholds.append(result)
                thresholds.sort(key=lambda r: (r["deadtime_ns"], r["bus_v"],
                                               r["direction"], r["board_l_scale"]))
                (HERE / "zvs_threshold.json").write_text(json.dumps({
                    "evidence_class": "simulation/model-based, reference inductances with sensitivity",
                    "criterion": "incoming die |VDS| <= 5% VBUS throughout 20 ns before incoming 50% command",
                    "threshold_estimate": "midpoint of last fail/pass bracket; half-width <= 0.25 A",
                    "board_sha256": digest(BOARD), "vendor_sha256": digest(MODEL),
                    "deck_sha256": digest(DECK), "kit_options_sha256": digest(OPTIONS),
                    "reference_board_l_nh": BOARD_L_NH,
                    "scale_scope": "board copper, gate loop and capacitor ESL only; Infineon package L is internal and unscaled",
                    "completed_of": len(specs), "thresholds": thresholds,
                }, indent=2) + "\n")
                print("THRESHOLD", thresholds[-1], flush=True)
    if args.phase in ("resolution", "all"):
        # Check extrema and key outputs near each nominal threshold at half max step.
        payload = json.loads((HERE / "zvs_threshold.json").read_text())
        checks = []
        resolution_cases = []
        for row in payload["thresholds"]:
            if row["board_l_scale"] != 1 or row["status"] != "bracketed":
                continue
            bus, direction, dt = row["bus_v"], row["direction"], row["deadtime_ns"]
            for current in (row["bracket_a"][0], row["bracket_a"][1]):
                resolution_cases.append((bus, direction, dt, current, 1.0, "threshold_bracket"))
        for bus in (120, 198):
            for direction in (0, 1):
                for scale in SCALES:
                    resolution_cases.append((bus, direction, 348, 37.0, scale, "37a_l_corner"))
        for bus, direction, dt, current, scale, purpose in resolution_cases:
            coarse = run_case(bus, direction, dt, current, scale, 0.2)
            fine = run_case(bus, direction, dt, current, scale, 0.1)
            metrics = {}
            for name in ("peak_die_vds_l_v", "peak_die_vds_h_v", "edge_10_90_s",
                         "peak_abs_dvdt_10_90_1ns_v_per_s",
                         "peak_abs_dvdt_full_1ns_v_per_s",
                         "turnoff_model_dissipative_sum_j"):
                a, b = coarse[name], fine[name]
                metrics[name] = None if a is None or b is None else abs(a-b)/max(abs(b), 1e-12)
            checks.append({"bus_v": bus, "direction": direction, "deadtime_ns": dt,
                           "board_l_scale": scale, "purpose": purpose,
                           "current_a": current, "coarse_zvs": coarse["zvs_20ns_5pct"],
                           "fine_zvs": fine["zvs_20ns_5pct"], "relative_changes": metrics})
        (HERE / "timestep_checks.json").write_text(json.dumps(checks, indent=2) + "\n")

    # Rebuild exports from every verified case; this also supports partial runs.
    rows = [json.loads(p.read_text()) for p in RUNS.glob("*/case.json")]
    rows.sort(key=lambda r: (r["bus_v"], r["direction"], r["deadtime_ns"],
                             r["board_l_scale"], r["current_a"], r["max_step_ns"]))
    for filename, columns in (
        ("edge_rates.csv", ("bus_v", "direction", "deadtime_ns", "current_a", "board_l_scale",
                            "max_step_ns", "zvs_20ns_5pct", "incoming_die_vds_pre20_max_abs_v",
                            "edge_10_90_s", "edge_complete_before_command",
                            "peak_abs_dvdt_10_90_1ns_v_per_s",
                            "peak_abs_dvdt_full_1ns_v_per_s",
                            "waveform")),
        ("turnoff_energy.csv", ("bus_v", "direction", "deadtime_ns", "current_a", "board_l_scale",
                                "max_step_ns", "outgoing_device", "turnoff_window_start_s",
                                "turnoff_window_end_s", "turnoff_die_vds_external_drain_id_proxy_j",
                                "turnoff_model_channel_energy_j", "turnoff_model_epi_energy_j",
                                "turnoff_model_diode_energy_j", "turnoff_model_dissipative_sum_j",
                                "proxy_minus_model_dissipative_j",
                                "vendor_heat_clip_100kw_observed", "waveform")),
    ):
        with (HERE / filename).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows({k: row[k] for k in columns} for row in rows)
    if (HERE / "zvs_threshold.json").exists():
        thresholds = json.loads((HERE / "zvs_threshold.json").read_text())["thresholds"]
        grid = {(r["bus_v"], r["direction"], r["deadtime_ns"], r["current_a"],
                 r["board_l_scale"]): r for r in rows
                if r["current_a"] in CURRENTS and r["max_step_ns"] in (0.1, 0.2)}
        with (HERE / "edge_sensitivity.csv").open("w", newline="") as handle:
            columns = ("bus_v", "direction", "deadtime_ns", "current_a", "board_l_scale",
                       "max_step_ns", "reference_max_step_ns",
                       "zvs_20ns_5pct", "reference_zvs_20ns_5pct",
                       "edge_10_90_s", "reference_edge_10_90_s", "edge_change_pct",
                       "peak_abs_dvdt_10_90_1ns_v_per_s",
                       "reference_peak_abs_dvdt_10_90_1ns_v_per_s",
                       "band_peak_dvdt_change_pct",
                       "peak_abs_dvdt_full_1ns_v_per_s",
                       "reference_peak_abs_dvdt_full_1ns_v_per_s",
                       "full_peak_dvdt_change_pct")
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for key, r in sorted(grid.items()):
                bus, direction, dt, current, scale = key
                ref = grid[(bus, direction, dt, current, 1.0)]
                def pct(value, baseline):
                    return None if value is None or baseline is None else 100*(value/baseline-1)
                writer.writerow({
                    "bus_v": bus, "direction": direction, "deadtime_ns": dt,
                    "current_a": current, "board_l_scale": scale,
                    "max_step_ns": r["max_step_ns"],
                    "reference_max_step_ns": ref["max_step_ns"],
                    "zvs_20ns_5pct": r["zvs_20ns_5pct"],
                    "reference_zvs_20ns_5pct": ref["zvs_20ns_5pct"],
                    "edge_10_90_s": r["edge_10_90_s"],
                    "reference_edge_10_90_s": ref["edge_10_90_s"],
                    "edge_change_pct": pct(r["edge_10_90_s"], ref["edge_10_90_s"]),
                    "peak_abs_dvdt_10_90_1ns_v_per_s": r["peak_abs_dvdt_10_90_1ns_v_per_s"],
                    "reference_peak_abs_dvdt_10_90_1ns_v_per_s": ref["peak_abs_dvdt_10_90_1ns_v_per_s"],
                    "band_peak_dvdt_change_pct": pct(r["peak_abs_dvdt_10_90_1ns_v_per_s"],
                                                     ref["peak_abs_dvdt_10_90_1ns_v_per_s"]),
                    "peak_abs_dvdt_full_1ns_v_per_s": r["peak_abs_dvdt_full_1ns_v_per_s"],
                    "reference_peak_abs_dvdt_full_1ns_v_per_s": ref["peak_abs_dvdt_full_1ns_v_per_s"],
                    "full_peak_dvdt_change_pct": pct(r["peak_abs_dvdt_full_1ns_v_per_s"],
                                                     ref["peak_abs_dvdt_full_1ns_v_per_s"]),
                })
        with (HERE / "sensitivity.csv").open("w", newline="") as handle:
            columns = ("bus_v", "direction", "deadtime_ns", "board_l_scale", "threshold_a",
                       "reference_threshold_a", "threshold_change_pct", "edge_at_37a_10_90_s",
                       "reference_edge_at_37a_10_90_s", "edge_change_pct",
                       "full_peak_dvdt_at_37a_v_per_s", "reference_full_peak_dvdt_at_37a_v_per_s",
                       "full_peak_dvdt_change_pct")
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            by_key = {(r["bus_v"], r["direction"], r["deadtime_ns"], r["board_l_scale"]): r
                      for r in thresholds}
            case_key = {(r["bus_v"], r["direction"], r["deadtime_ns"], r["board_l_scale"],
                         r["current_a"], r["max_step_ns"]): r for r in rows}
            for r in thresholds:
                key = (r["bus_v"], r["direction"], r["deadtime_ns"])
                ref = by_key[(*key, 1.0)]
                e = case_key.get((*key, r["board_l_scale"], 37.0, 0.2))
                e_ref = case_key.get((*key, 1.0, 37.0, 0.2))
                def change(x, y):
                    return None if x is None or y is None else 100*(x/y-1)
                writer.writerow({"bus_v": r["bus_v"], "direction": r["direction"],
                                 "deadtime_ns": r["deadtime_ns"], "board_l_scale": r["board_l_scale"],
                                 "threshold_a": r["threshold_a"], "reference_threshold_a": ref["threshold_a"],
                                 "threshold_change_pct": change(r["threshold_a"], ref["threshold_a"]),
                                 "edge_at_37a_10_90_s": e["edge_10_90_s"] if e else None,
                                 "reference_edge_at_37a_10_90_s": e_ref["edge_10_90_s"] if e_ref else None,
                                 "edge_change_pct": change(e["edge_10_90_s"], e_ref["edge_10_90_s"])
                                 if e and e_ref else None,
                                 "full_peak_dvdt_at_37a_v_per_s": e["peak_abs_dvdt_full_1ns_v_per_s"] if e else None,
                                 "reference_full_peak_dvdt_at_37a_v_per_s": e_ref["peak_abs_dvdt_full_1ns_v_per_s"] if e_ref else None,
                                 "full_peak_dvdt_change_pct": change(e["peak_abs_dvdt_full_1ns_v_per_s"],
                                                                       e_ref["peak_abs_dvdt_full_1ns_v_per_s"])
                                 if e and e_ref else None})
    print(f"Exported {len(rows)} verified transients", flush=True)


if __name__ == "__main__":
    main()
