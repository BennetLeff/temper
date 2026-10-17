#!/usr/bin/env python3
"""Re-solve the 135-case ideal tank grid at two actual-peak current ceilings."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
KIT = UNIT / "validation-plan/sim-kit"
ROUND3 = UNIT / "validation-results/05-resonant-tank-envelope/round3"
OUT = TASK / "outputs"
DECK = TASK / "scripts/tank.cir"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402

CEILINGS = (42.0, 40.45)
MEAS = ("i_rms", "i_pk", "vc_pk", "vc_rms", "p_avg")
FIELDS = (
    "ceiling_a", "run_id", "pan", "corner", "vrms_v", "target_w", "status",
    "round3_status", "round3_frequency_hz", "round3_i_pk_a", "frequency_hz",
    "f_res_hz", "l_load_h", "r_pan_40_ohm", "r_coil_ohm", "i_rms_a",
    "i_pk_a", "ceiling_margin_a", "vc_pk_v", "vc_rms_v", "p_avg_w",
    "power_shortfall_w", "power_fraction", "c21_i_rms_a", "c22_i_rms_a",
    "c23_i_rms_a", "ct_sec_v_pk_ideal_v", "ct_sec_volt_us_ideal",
    "bleed_each_v_pk_v", "bleed_each_p_avg_w", "c_energy_pk_j",
    "shunt_above_min_38_44a", "ct_above_min_50_56a", "run_dir",
)
EVENT_FIELDS = (
    "ceiling_a", "run_id", "event_index", "time_s", "direction",
    "tank_current_a", "tank_cap_voltage_v", "bus_voltage_v", "line_fraction",
    "inductive_sign", "tank_current_before_500ns_a", "tank_current_after_500ns_a",
    "tank_current_slope_a_per_s", "a1_threshold_domain", "minimum_zvs_current_a", "zvs_verdict",
)
SHUNT_FIELDS = (
    "ceiling_a", "run_id", "line_average_r5_rms_a", "crest_interval_r5_rms_a",
    "arithmetic_sample_rms_a_wrong", "raw_points", "raw_end_s", "event_count",
)


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def params(row: dict[str, str], frequency_hz: float) -> dict[str, str]:
    return {
        "VRMS": row["vrms_v"], "FREQ": f"{frequency_hz:.12f}",
        "LLOAD": row["l_load_h"], "RPAN40": row["r_pan_40_ohm"],
        "RCOIL": row["r_coil_ohm"],
    }


def checked_run(row: dict[str, str], frequency_hz: float,
                directory: Path | None = None, raw: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="r4a-tank-") as scratch:
        target = directory if directory is not None else Path(scratch)
        result = run(DECK, params(row, frequency_hz), keep=target, raw=raw)
        if (result["aborted"] or result["failed"]
                or any(key not in result["meas"] for key in MEAS)
                or any(not math.isfinite(result["meas"].get(key, math.nan)) for key in MEAS)
                or (raw and result["raw_returncode"] != 0)):
            raise RuntimeError(f"invalid ngspice result {row['run_id']} at {frequency_hz}: {result}")
        if directory is not None:
            (directory / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
        return result


def solve(row: dict[str, str], ceiling: float, tolerance_a: float = .15) -> tuple[str, float, dict]:
    base_freq = float(row["frequency_hz"])
    base_peak = float(row["i_pk_a"])
    if base_peak <= ceiling:
        return "retained", base_freq, {"search": "round3 baseline within ceiling"}
    high = 60_000.0
    high_result = checked_run(row, high)
    high_peak = high_result["meas"]["i_pk"]
    if high_peak > ceiling:
        return "needs_burst_or_phase_shift", high, {
            "search": "ceiling impossible by frequency at <=60 kHz",
            "peak_at_60khz_a": high_peak,
        }
    low = base_freq
    low_peak = base_peak
    evaluations = [{"frequency_hz": high, "i_pk_a": high_peak}]
    for _ in range(22):
        if ceiling - high_peak <= tolerance_a:
            break
        mid = (low + high) / 2
        peak = checked_run(row, mid)["meas"]["i_pk"]
        evaluations.append({"frequency_hz": mid, "i_pk_a": peak})
        if peak > ceiling:
            low, low_peak = mid, peak
        else:
            high, high_peak = mid, peak
    if not 0 <= ceiling - high_peak <= tolerance_a or not low_peak > ceiling:
        raise RuntimeError(f"bisection did not safely bracket {row['run_id']} at {ceiling}: {evaluations[-4:]}")
    return "derated", high, {"search": "safe upper-frequency bracket", "iterations": evaluations,
                              "unsafe_lower_frequency_hz": low, "unsafe_lower_peak_a": low_peak,
                              "safe_upper_frequency_hz": high, "safe_upper_peak_a": high_peak}


def weighted_rms(t: np.ndarray, y: np.ndarray, lo: float, hi: float) -> float:
    inside = (t > lo) & (t < hi)
    ts = np.r_[lo, t[inside], hi]
    ys = np.r_[np.interp(lo, t, y), y[inside], np.interp(hi, t, y)]
    return math.sqrt(float(np.trapezoid(ys * ys, ts) / (hi - lo)))


def waveform_evidence(row: dict[str, str], ceiling: float, directory: Path,
                      result: dict) -> tuple[list[dict], dict]:
    waves = read_raw(directory / "waves.raw")
    t = np.asarray(waves["time"])
    drv = np.asarray(waves["v(drv)"])
    tank = np.asarray(waves["i(vim)"])
    cap = np.asarray(waves["v(c)"])
    if abs(t[-1] - 8.3333e-3) > 1e-8 or not all(np.all(np.isfinite(x)) for x in (t, drv, tank, cap)):
        raise RuntimeError(f"invalid waveform for {row['run_id']}")
    shunt = np.where(drv >= 0, 1., -1.) * tank
    line_rms = weighted_rms(t, shunt, 0., 1/120)
    crest_lo = math.asin(.9) / (2 * math.pi * 60)
    crest_hi = (math.pi - math.asin(.9)) / (2 * math.pi * 60)
    crest_rms = weighted_rms(t, shunt, crest_lo, crest_hi)
    if abs(line_rms - result["meas"]["i_rms"]) / line_rms > .01:
        raise RuntimeError(f"R5 integral disagrees with .meas for {row['run_id']}")
    indexes = np.flatnonzero(((drv[:-1] < 0) & (drv[1:] >= 0)) |
                             ((drv[:-1] > 0) & (drv[1:] <= 0)))
    delta = drv[indexes + 1] - drv[indexes]
    indexes, delta = indexes[delta != 0], delta[delta != 0]
    weights = -drv[indexes] / delta
    times = t[indexes] + weights * (t[indexes + 1] - t[indexes])
    currents = tank[indexes] + weights * (tank[indexes + 1] - tank[indexes])
    caps = cap[indexes] + weights * (cap[indexes + 1] - cap[indexes])
    directions = np.where(delta > 0, "rising", "falling")
    fractions = np.abs(np.sin(2 * np.pi * 60 * times))
    bus = float(row["vrms_v"]) * math.sqrt(2) * fractions
    signs = np.where(delta > 0, currents < 0, currents > 0)
    events = []
    for index in range(len(times)):
        events.append({
            "ceiling_a": ceiling, "run_id": row["run_id"], "event_index": index,
            "time_s": float(times[index]), "direction": str(directions[index]),
            "tank_current_a": float(currents[index]), "tank_cap_voltage_v": float(caps[index]),
            "bus_voltage_v": float(bus[index]), "line_fraction": float(fractions[index]),
            "inductive_sign": bool(signs[index]),
            "tank_current_before_500ns_a": float(np.interp(max(0.0, times[index]-500e-9), t, tank)),
            "tank_current_after_500ns_a": float(np.interp(min(t[-1], times[index]+500e-9), t, tank)),
            "tank_current_slope_a_per_s": float((tank[indexes[index]+1]-tank[indexes[index]])/(t[indexes[index]+1]-t[indexes[index]])),
            "a1_threshold_domain": "BELOW_A1_120V_REQUIRES_RUN" if bus[index] < 120
                else "120_TO_198V_INTERPOLATION_NEEDS_VALIDATION",
            "minimum_zvs_current_a": "", "zvs_verdict": "PENDING_A1",
        })
    shunt_row = {
        "ceiling_a": ceiling, "run_id": row["run_id"],
        "line_average_r5_rms_a": line_rms, "crest_interval_r5_rms_a": crest_rms,
        "arithmetic_sample_rms_a_wrong": float(np.sqrt(np.mean(shunt * shunt))),
        "raw_points": len(t), "raw_end_s": float(t[-1]), "event_count": len(events),
    }
    return events, shunt_row



def input_fingerprint(baseline: dict[str, str], ceiling: float, frequency: float) -> str:
    """Bind a cached solve to its exact source row, deck, kit, and runtime."""
    runtime = next(line.strip() for line in subprocess.check_output(
        ["ngspice", "-v"], text=True, stderr=subprocess.STDOUT).splitlines()
        if "ngspice-" in line)
    payload = {
        "baseline_row": baseline,
        "ceiling_a": ceiling,
        "frequency_hz": frequency,
        "deck_sha256": sha256(DECK),
        "options_sha256": sha256(KIT / "common/options.inc"),
        "vendor_sha256": sha256(KIT / "models/vendor/IFX_CFD7_650V.lib"),
        "ngspice_version": runtime,
        "spiceinit": "set ngbehavior=psa\nset filetype=ascii\n",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verify_cached_case(baseline: dict[str, str], ceiling: float, directory: Path) -> bool:
    """Validate old and new cached runs before allowing a skip."""
    case_file = directory / "case.json"
    if not case_file.is_file():
        return False
    case = json.loads(case_file.read_text())
    row = case["row"]
    source_fields = {
        "run_id": "run_id", "pan": "pan", "corner": "corner",
        "vrms_v": "vrms_v", "target_w": "target_w",
        "round3_status": "status", "round3_frequency_hz": "frequency_hz",
        "round3_i_pk_a": "i_pk_a", "f_res_hz": "f_res_hz",
        "l_load_h": "l_load_h", "r_pan_40_ohm": "r_pan_40_ohm",
        "r_coil_ohm": "r_coil_ohm",
    }
    if float(row["ceiling_a"]) != ceiling or any(
        str(row[dest]) != baseline[src] for dest, src in source_fields.items()
    ):
        raise RuntimeError(f"cached baseline identity changed: {directory}")
    frequency = float(row["frequency_hz"])
    expected_params = params(baseline, frequency)
    # run_ngspice expands the kit path in includes and header comments.
    # Normalize only that known relocation before comparing all deck bytes.
    saved_deck = re.sub(
        r"\S*/validation-plan/sim-kit/common/", "../common/",
        (directory / "tank.cir").read_text(),
    )
    if saved_deck != DECK.read_text():
        raise RuntimeError(f"cached deck differs from current deck: {directory}")
    expected_param_text = "".join(f".param {k}={v}\n" for k, v in expected_params.items())
    if ((directory / "params.inc").read_text() != expected_param_text
            or (directory / ".spiceinit").read_text() != "set ngbehavior=psa\nset filetype=ascii\n"):
        raise RuntimeError(f"cached simulator parameters differ: {directory}")
    result = json.loads((directory / "result.json").read_text())
    if result["params"] != expected_params or result["meas"]["i_pk"] != row["i_pk_a"]:
        raise RuntimeError(f"cached result differs from row: {directory}")
    accepted = row["status"] != "needs_burst_or_phase_shift"
    required = ["run.log", "case.json", "result.json"]
    if accepted:
        required += ["raw_run.log", "events.csv", "shunt.json", "waves.raw.gz"]
    if any(not (directory / name).is_file() for name in required):
        raise RuntimeError(f"cached run is incomplete: {directory}")
    if accepted:
        try:
            with gzip.open(directory / "waves.raw.gz", "rb") as stream:
                while stream.read(1024 * 1024):
                    pass  # Read to EOF so gzip validates its trailer and CRC.
        except (EOFError, OSError) as error:
            raise RuntimeError(f"cached waveform gzip is incomplete: {directory}") from error
    digest = input_fingerprint(baseline, ceiling, frequency)
    if "input_fingerprint_sha256" in case and case["input_fingerprint_sha256"] != digest:
        raise RuntimeError(f"cached input fingerprint changed: {directory}")
    if "input_fingerprint_sha256" not in case:
        case["input_fingerprint_sha256"] = digest
        case["fingerprint_basis"] = "backfilled after saved deck, params, result and baseline checks"
        write_json(case_file, case)
    return True


def create_case(baseline: dict[str, str], ceiling: float, target_margin_a: float = 0.) -> None:
    run_id = baseline["run_id"]
    directory = OUT / "runs" / f"{ceiling:g}a" / run_id
    case_file = directory / "case.json"
    events_file = directory / "events.csv"
    shunt_file = directory / "shunt.json"
    if verify_cached_case(baseline, ceiling, directory):
        return
    directory.mkdir(parents=True, exist_ok=True)
    status, frequency, search = solve(baseline, ceiling - target_margin_a,
                                      tolerance_a=.05 if target_margin_a else .15)
    search["target_margin_a"] = target_margin_a
    accepted = status != "needs_burst_or_phase_shift"
    result = checked_run(baseline, frequency, directory, raw=accepted)
    m = result["meas"]
    if accepted and m["i_pk"] > ceiling:
        raise RuntimeError(f"accepted run exceeded {ceiling} A: {run_id}, {m['i_pk']}")
    row = {
        "ceiling_a": ceiling, "run_id": run_id, "pan": baseline["pan"],
        "corner": baseline["corner"], "vrms_v": baseline["vrms_v"],
        "target_w": baseline["target_w"], "status": status,
        "round3_status": baseline["status"], "round3_frequency_hz": baseline["frequency_hz"],
        "round3_i_pk_a": baseline["i_pk_a"], "frequency_hz": frequency,
        "f_res_hz": baseline["f_res_hz"], "l_load_h": baseline["l_load_h"],
        "r_pan_40_ohm": baseline["r_pan_40_ohm"], "r_coil_ohm": baseline["r_coil_ohm"],
        "i_rms_a": m["i_rms"], "i_pk_a": m["i_pk"],
        "ceiling_margin_a": ceiling - m["i_pk"], "vc_pk_v": m["vc_pk"],
        "vc_rms_v": m["vc_rms"], "p_avg_w": m["p_avg"],
        "power_shortfall_w": float(baseline["target_w"]) - m["p_avg"],
        "power_fraction": m["p_avg"] / float(baseline["target_w"]),
        "c21_i_rms_a": m["i_rms"] * .22/.54,
        "c22_i_rms_a": m["i_rms"] * .22/.54,
        "c23_i_rms_a": m["i_rms"] * .10/.54,
        "ct_sec_v_pk_ideal_v": m["i_pk"] * .015,
        "ct_sec_volt_us_ideal": .015*m["i_pk"]/(math.pi*frequency)*1e6,
        "bleed_each_v_pk_v": m["vc_pk"]/4,
        "bleed_each_p_avg_w": (m["vc_rms"]/4)**2/470_000,
        "c_energy_pk_j": .5*.54e-6*m["vc_pk"]**2,
        "shunt_above_min_38_44a": m["i_pk"] > 38.438184034366216,
        "ct_above_min_50_56a": m["i_pk"] > 50.558351037317024,
        "run_dir": f"outputs/runs/{ceiling:g}a/{run_id}",
    }
    if accepted:
        events, shunt_row = waveform_evidence(baseline, ceiling, directory, result)
        with events_file.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, EVENT_FIELDS)
            writer.writeheader()
            writer.writerows(events)
        write_json(shunt_file, shunt_row)
    else:
        events_file.unlink(missing_ok=True)
        shunt_file.unlink(missing_ok=True)
    # Preserve the actual simulator waveform for C2 and independent replay.
    # Publish the completion marker only after an atomically installed, verified gzip.
    if accepted:
        with tempfile.NamedTemporaryFile(prefix="waves-", suffix=".raw.gz", dir=directory,
                                         delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with (directory / "waves.raw").open("rb") as source, gzip.open(
                temporary_path, "wb", compresslevel=3
            ) as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            with gzip.open(temporary_path, "rb") as verified:
                while verified.read(1024 * 1024):
                    pass
            os.replace(temporary_path, directory / "waves.raw.gz")
        finally:
            temporary_path.unlink(missing_ok=True)
        (directory / "waves.raw").unlink()
    write_json(directory / "result.json", result)
    write_json(case_file, {"row": row, "search": search,
                           "input_fingerprint_sha256": input_fingerprint(baseline, ceiling, frequency),
                           "fingerprint_basis": "captured at solve time"})


def aggregate(baselines: list[dict[str, str]]) -> None:
    rows, events, shunts = [], [], []
    for ceiling in CEILINGS:
        for baseline in baselines:
            directory = OUT / "runs" / f"{ceiling:g}a" / baseline["run_id"]
            case = json.loads((directory / "case.json").read_text())
            row = case["row"]
            rows.append(row)
            if row["status"] != "needs_burst_or_phase_shift":
                with (directory / "events.csv").open(newline="") as stream:
                    events.extend(csv.DictReader(stream))
                shunts.append(json.loads((directory / "shunt.json").read_text()))
    for name, fields, data in (("derated_cases.csv", FIELDS, rows),
                               ("switching-events.csv", EVENT_FIELDS, events),
                               ("shunt-grid.csv", SHUNT_FIELDS, shunts)):
        with (OUT / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows(data)
    summary = {"evidence_class": "simulation/model-based", "case_count": len(rows),
               "accepted_case_count": len(shunts), "event_count": len(events), "ceilings": {}}
    for ceiling in CEILINGS:
        selection = [r for r in rows if r["ceiling_a"] == ceiling]
        accepted = [r for r in selection if r["status"] != "needs_burst_or_phase_shift"]
        counts = Counter(r["status"] for r in selection)
        by_pan = defaultdict(list)
        for r in selection:
            by_pan[(r["pan"], float(r["vrms_v"]))].append(r)
        summary["ceilings"][f"{ceiling:g}"] = {
            "status_counts": dict(counts),
            "accepted_above_shunt_min_38_438184a": sum(r["shunt_above_min_38_44a"] for r in accepted),
            "retained_above_shunt_min_38_438184a": sum(r["shunt_above_min_38_44a"] for r in accepted if r["status"] == "retained"),
            "derated_above_shunt_min_38_438184a": sum(r["shunt_above_min_38_44a"] for r in accepted if r["status"] == "derated"),
            "accepted_above_ct_min_50_558351a": sum(r["ct_above_min_50_56a"] for r in accepted),
            "max_accepted_peak_a": max(r["i_pk_a"] for r in accepted),
            "min_delivered_power_w": min(r["p_avg_w"] for r in selection),
            "needs_burst_or_phase_shift": [r["run_id"] for r in selection if r["status"] == "needs_burst_or_phase_shift"],
            "by_pan_and_line": [
                {"pan": pan, "vrms_v": vrms, "min_delivered_w": min(r["p_avg_w"] for r in group),
                 "max_delivered_w": max(r["p_avg_w"] for r in group),
                 "mean_delivered_w": sum(r["p_avg_w"] for r in group)/len(group),
                 "mean_requested_w": sum(float(r["target_w"]) for r in group)/len(group)}
                for (pan, vrms), group in sorted(by_pan.items())
            ],
        }
    write_json(OUT / "summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="run a development prefix per ceiling")
    args = parser.parse_args()
    with (ROUND3 / "outputs/cases.csv").open(newline="") as stream:
        baselines = list(csv.DictReader(stream))
    if len(baselines) != 135 or len({r["run_id"] for r in baselines}) != 135:
        raise RuntimeError("round-3 baseline must contain exactly 135 unique cases")
    OUT.mkdir(parents=True, exist_ok=True)
    for ceiling in CEILINGS:
        for index, baseline in enumerate(baselines[:args.limit] if args.limit else baselines, 1):
            create_case(baseline, ceiling)
            print(json.dumps({"ceiling_a": ceiling, "index": index, "run_id": baseline["run_id"]}), flush=True)
    if args.limit is None:
        aggregate(baselines)
        write_json(OUT / "input-provenance.json", {
            "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=UNIT).strip(),
            "board_sha256": sha256(UNIT / "native-15/section.kicad_pcb"),
            "baseline_cases_sha256": sha256(ROUND3 / "outputs/cases.csv"),
            "deck_sha256": sha256(DECK),
            "analysis_script_sha256": sha256(TASK / "scripts/find_freq.py"),
            "vendor_model_sha256": sha256(KIT / "models/vendor/IFX_CFD7_650V.lib"),
            "threshold_source_sha256": sha256(ROUND3 / "sources/a3-thresholds.json"),
            "ngspice_version": next(line.strip() for line in subprocess.check_output(["ngspice", "-v"], text=True, stderr=subprocess.STDOUT).splitlines() if "ngspice-" in line),
            "python_version": sys.version.split()[0],
            "round3_raw_verification": "3327/3327 files verified",
            "kit_smoke": "SMOKE PASS",
        })


if __name__ == "__main__":
    main()
