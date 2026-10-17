#!/usr/bin/env python3
"""Round-4 C1 reference-inductance ZVS/diode timing sweep.

Reuses the pinned A1 deck and simulator/parser, writing all new cases only to
this C1 directory. The driver-time min/max at 39/51 kΩ are ASSUMED relative
extrapolations from TI's characterized 50 kΩ spread, not device guarantees.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
A1_DIR = POWER / "validation-results/01-switching-parasitics/round3/a1-zvs"
BOARD = POWER / "native-15/section.kicad_pcb"
KIT = POWER / "validation-plan/sim-kit"
MODEL = KIT / "models/vendor/IFX_CFD7_650V.lib"
MODEL_ZIP = KIT / "models/vendor/cfd7-650.zip"
TI_PDF = HERE / "sources/ucc21550-revc.pdf"
MOSFET_PDF = POWER / "validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf"
RUNS = HERE / "outputs/runs"
BUSES = (10, 30, 60, 90, 120, 170, 198)
GRID_A = (0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 24.0, 40.0, 60.0, 100.0)
FIFTY_NS = {"min": 399.0, "typ": 443.0, "max": 487.0}
TIMINGS_NS = {ohm: {corner: (8.6 * ohm + 13.0) * t / 443.0
                    for corner, t in FIFTY_NS.items()}
              for ohm in (39, 51)}
EXPECTED = {
    BOARD: "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155",
    MODEL: "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
    MODEL_ZIP: "5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d",
    A1_DIR / "complementary_leg.cir": "b2da52e71a9538d090f3c8828d29509d7c4870a6774667738d582abc52c9b902",
    A1_DIR / "run_a1.py": "10607cee98257b8ac52ef282dfe2f78676a29b126437fcc7cde724f66a449377",
    KIT / "common/options.inc": "ae752d460d50fdbbcaaf03b29871b3b039cf27f018707efe4aa50d0fc3529330",
    MOSFET_PDF: "c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_a1():
    spec = importlib.util.spec_from_file_location("c1_pinned_a1", A1_DIR / "run_a1.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.OUT = HERE / "outputs"
    module.RUNS = RUNS
    return module


def spec_rows():
    for ohm in (39, 51):
        for corner in ("min", "typ", "max"):
            for bus in BUSES:
                for direction in (0, 1):
                    yield (ohm, corner, bus, direction, 1.0)
    for ohm in (39, 51):
        for bus in BUSES:
            for direction in (0, 1):
                for scale in (0.5, 3.0):
                    yield (ohm, "typ", bus, direction, scale)


def identity(ohm, corner, bus, direction, scale):
    return f"r{ohm}_{corner}_v{bus}_d{direction}_l{scale:g}"


def search(a1, spec):
    ohm, corner, bus, direction, scale = spec
    dt = TIMINGS_NS[ohm][corner]
    observations = {}
    for current in GRID_A:
        record = a1.run_case(bus, direction, dt, current, scale)
        observations[current] = bool(record["zvs_20ns_5pct"])
    # A sweep can have multiple pass/fail islands when ringing is involved.
    # Refine every observed transition instead of assuming monotonicity.
    intervals = []
    for lo, hi in zip(GRID_A, GRID_A[1:], strict=False):
        if observations[lo] == observations[hi]:
            continue
        lo_status = observations[lo]
        for _ in range(16):
            if hi - lo <= 0.5:
                break
            mid = (lo + hi) / 2
            mid_status = bool(a1.run_case(bus, direction, dt, mid, scale)["zvs_20ns_5pct"])
            observations[mid] = mid_status
            if mid_status == lo_status:
                lo = mid
            else:
                hi = mid
        intervals.append({"bracket_a": [lo, hi], "low_zvs": observations[lo],
                          "high_zvs": observations[hi], "midpoint_a": (lo + hi) / 2,
                          "half_width_a": (hi - lo) / 2})
    ordered = sorted(observations.items())
    flips = sum(ordered[i][1] != ordered[i - 1][1] for i in range(1, len(ordered)))
    rising = [x for x in intervals if not x["low_zvs"] and x["high_zvs"]]
    if flips > 1:
        status, minimum = "nonmonotonic_sampled", None
    elif observations[GRID_A[0]]:
        status, minimum = "at_or_below_0p5a", None
    elif not rising:
        status, minimum = "no_pass_through_100a", None
    else:
        status, minimum = "bracketed", rising[0]
    return {
        "id": identity(*spec), "rdt_kohm": ohm, "timing_corner": corner,
        "deadtime_ns": dt, "bus_v": bus, "direction": direction,
        "current_sign": "+IL" if direction == 0 else "-IL",
        "reference_l_scale": scale, "status": status,
        "minimum_zvs_current_a": minimum["midpoint_a"] if minimum else None,
        "minimum_bracket_a": minimum["bracket_a"] if minimum else None,
        "crossing_intervals": intervals,
        "sampled_observations": [[current, passed] for current, passed in ordered],
        "domain_note": "No inference below 10 V bus or outside sampled current intervals",
    }


def waveform_metrics(record):
    path = HERE / record["waveform"]
    with gzip.open(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames
        assert names is not None
        data = np.array([[float(row[name]) for name in names] for row in reader])
    wave = dict(zip(names, data.T, strict=False))
    direction = record["direction"]
    side = "xqh" if direction == 0 else "xql"
    time = wave["time_s"]
    t_on = record["command_on_s"]
    t_off = record["command_off_s"]
    limit = 0.05 * record["bus_v"]
    die_vds = wave[f"v({side}.dd)"] - wave[f"v({side}.s)"]
    diode_a = -wave[f"i(v.{side}.x1.v_sense2)"]
    external_reverse_a = -wave["i(vidh)" if direction == 0 else "i(vids)"]
    channel_a = np.abs(wave[f"i(v.{side}.x1.v_ichannel)"])
    die_vgs = wave[f"v({side}.g)"] - wave[f"v({side}.s)"]
    window = (time >= t_off) & (time <= t_on)
    times = time[window]
    v = np.abs(die_vds[window])
    i = diode_a[window]
    pre_times = np.concatenate(([t_on - 20e-9], time[(time > t_on - 20e-9) & (time < t_on)], [t_on]))
    pre_vds = np.interp(pre_times, time, die_vds)
    pre_diode = np.interp(pre_times, time, diode_a)
    positive_residual_pass = bool(np.max(pre_vds) <= limit)
    forward_diode_clamped = bool(positive_residual_pass and np.min(pre_diode) >= 0.1)
    # Last out-of-band sample followed by a clamp defines stable completion.
    out = np.flatnonzero(v > limit)
    stable_start = float(times[out[-1] + 1]) if len(out) and out[-1] + 1 < len(times) else None
    if not len(out):
        stable_start = float(times[0])
    # The L1 V_sense2 branch is negative for forward body-diode current.
    # 0.1 A is an instrumentation floor, not a physical diode turn-on rule.
    conducting = i > 0.1
    dt = np.diff(times)
    dwell_s = float(np.sum(dt * (conducting[:-1] | conducting[1:]) / 2 +
                           dt * (conducting[:-1] & conducting[1:]) / 2)) if len(dt) else 0.0
    ampere_seconds = float(np.trapezoid(np.maximum(i, 0), times))
    reverse_ampere_seconds = float(np.trapezoid(np.maximum(external_reverse_a[window], 0), times))
    channel_floor_a = max(0.1, 0.1 * record["current_a"])
    peak_any_v = max(record["peak_die_vds_l_v"], record["peak_die_vds_h_v"])
    overstress = peak_any_v >= 650.0
    # V_Ichannel also includes the model breakdown term. Gate qualification
    # reduces false onset; any >=650 V die peak invalidates this surrogate.
    after_command = np.flatnonzero((time >= t_on) & (time + 2e-9 <= time[-1]) &
                                    (channel_a >= channel_floor_a) &
                                    (np.interp(time + 2e-9, time, channel_a) >= channel_floor_a) &
                                    (die_vgs >= 3.5) &
                                    (np.interp(time + 2e-9, time, die_vgs) >= 3.5))
    channel_candidate = float(time[after_command[0]]) if len(after_command) else None
    channel_onset = channel_candidate if not overstress else None
    diode_end = channel_onset if channel_onset is not None else float(time[-1])
    until_channel = (time >= t_off) & (time <= diode_end)
    tc = time[until_channel]
    ic = diode_a[until_channel]
    diode_occupancy = np.trapezoid((ic > 0.1).astype(float), tc) if len(tc) > 1 else 0.0
    diode_charge = np.trapezoid(np.maximum(ic, 0), tc) if len(tc) > 1 else 0.0
    full_window = time >= t_off
    full_diode_forward_charge = np.trapezoid(np.maximum(diode_a[full_window], 0), time[full_window])
    after_channel = time >= diode_end
    diode_reverse_charge_after_channel = np.trapezoid(np.maximum(-diode_a[after_channel], 0), time[after_channel]) if np.sum(after_channel) > 1 else 0.0
    post_command = (tc >= t_on)
    post_charge = np.trapezoid(np.maximum(ic[post_command], 0), tc[post_command]) if np.sum(post_command) > 1 else 0.0
    gate_crossings = np.flatnonzero((time[:-1] >= t_on) & (die_vgs[:-1] < 7.5) & (die_vgs[1:] >= 7.5))
    gate_cross = None
    if len(gate_crossings):
        j = gate_crossings[0]
        gate_cross = float(time[j] + (7.5 - die_vgs[j]) * (time[j + 1] - time[j]) /
                           (die_vgs[j + 1] - die_vgs[j]))
    return {
        "stable_incoming_die_vds_5pct_start_s": stable_start,
        "incoming_die_vds_pre20_min_v": float(np.min(pre_vds)),
        "incoming_die_vds_pre20_max_v": float(np.max(pre_vds)),
        "incoming_diode_forward_current_pre20_min_a": float(np.min(pre_diode)),
        "incoming_diode_forward_current_pre20_max_a": float(np.max(pre_diode)),
        "positive_residual_5pct_pass": positive_residual_pass,
        "forward_diode_clamped_pre20": forward_diode_clamped,
        "stable_clamp_to_command_ns": (t_on - stable_start) * 1e9 if stable_start else None,
        "edge_10_90_complete_before_command": record["edge_complete_before_command"],
        "edge_end_s": record["edge_end_s"],
        "incoming_diode_forward_current_peak_before_command_a": float(np.max(i)),
        "incoming_diode_forward_current_at_command_a": float(np.interp(t_on, time, diode_a)),
        "diode_dwell_above_0p1a_ns": dwell_s * 1e9,
        "diode_forward_charge_before_command_c": ampere_seconds,
        "external_reverse_charge_before_command_c": reverse_ampere_seconds,
        "external_reverse_current_at_command_a": float(np.interp(t_on, time, external_reverse_a)),
        "diode_current_sign": "-i(V_sense2) is positive forward",
        "incoming_die_vgs_at_command_v": float(np.interp(t_on, time, die_vgs)),
        "incoming_die_vgs_7p5v_crossing_s": gate_cross,
        "peak_die_vds_any_v": peak_any_v,
        "avalanche_or_overstress": overstress,
        "incoming_channel_current_candidate_s": channel_candidate,
        "incoming_channel_current_onset_s": channel_onset,
        "incoming_channel_current_onset_floor_a": channel_floor_a,
        "incoming_channel_onset_right_censored": channel_candidate is None,
        "incoming_channel_onset_invalid_due_overstress": overstress,
        "incoming_die_vgs_at_channel_onset_v": float(np.interp(channel_onset, time, die_vgs)) if channel_onset else None,
        "diode_dwell_until_channel_ns": float(diode_occupancy * 1e9) if not overstress else None,
        "diode_forward_charge_until_channel_c": float(diode_charge) if not overstress else None,
        "diode_forward_charge_postcommand_until_channel_c": float(post_charge) if not overstress else None,
        "diode_forward_charge_full_saved_window_c": float(full_diode_forward_charge),
        "diode_reverse_charge_after_channel_c": float(diode_reverse_charge_after_channel) if not overstress else None,
    }


def export(a1, rows):
    output = HERE / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    records = [json.loads(path.read_text()) for path in RUNS.glob("*/case.json")]
    records.sort(key=lambda r: (r["bus_v"], r["direction"], r["deadtime_ns"],
                                r["board_l_scale"], r["current_a"], r["max_step_ns"]))
    fields = ("bus_v", "direction", "current_a", "deadtime_ns", "board_l_scale", "max_step_ns",
              "zvs_20ns_5pct", "incoming_die_vds_pre20_max_abs_v", "command_off_s",
              "command_on_s", "edge_10_90_s", "edge_end_s", "edge_complete_before_command",
              "peak_die_vds_l_v", "peak_die_vds_h_v", "turnoff_model_dissipative_sum_j",
              "stable_incoming_die_vds_5pct_start_s", "stable_clamp_to_command_ns",
              "incoming_die_vds_pre20_min_v", "incoming_die_vds_pre20_max_v",
              "incoming_diode_forward_current_pre20_min_a", "incoming_diode_forward_current_pre20_max_a",
              "positive_residual_5pct_pass", "forward_diode_clamped_pre20",
              "incoming_diode_forward_current_peak_before_command_a", "incoming_diode_forward_current_at_command_a",
              "diode_dwell_above_0p1a_ns", "diode_forward_charge_before_command_c",
              "external_reverse_charge_before_command_c", "external_reverse_current_at_command_a",
              "incoming_die_vgs_at_command_v", "incoming_die_vgs_7p5v_crossing_s",
              "peak_die_vds_any_v", "avalanche_or_overstress",
              "incoming_channel_current_candidate_s", "incoming_channel_current_onset_s",
              "incoming_channel_current_onset_floor_a", "incoming_channel_onset_right_censored",
              "incoming_channel_onset_invalid_due_overstress", "incoming_die_vgs_at_channel_onset_v",
              "diode_dwell_until_channel_ns", "diode_forward_charge_until_channel_c",
              "diode_forward_charge_postcommand_until_channel_c",
              "diode_forward_charge_full_saved_window_c", "diode_reverse_charge_after_channel_c",
              "waveform", "case_json")
    with (output / "waveform_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            merged = {**record, **waveform_metrics(record),
                      "case_json": str(Path(record["waveform"]).parent / "case.json")}
            writer.writerow({field: merged.get(field) for field in fields})
    payload = {
        "evidence_class": "simulation/model-based; reference inductances only",
        "criterion": "incoming die |VDS| <= 5% bus at every saved/interpolated point in 20 ns before incoming 7.5 V command",
        "threshold_estimate": "midpoint of sampled fail/pass bracket; half-width <=0.25 A; not a physical guaranteed limit",
        "timing_source": {"manufacturer": "Texas Instruments", "document": "UCC21550 Rev C SLUSE89C",
                          "url": "https://www.ti.com/lit/ds/symlink/ucc21550.pdf",
                          "page": 10, "table": "§5.8 Electrical Characteristics, DEADTIME AND OVERLAP PROGRAMMING",
                          "pdf_sha256": digest(TI_PDF), "characterized_50kohm_ns": FIFTY_NS,
                          "nominal_formula": "8.6*RDT_kohm+13 ns",
                          "extrapolation": "ASSUMED: multiply formula nominal at 39/51 kohm by 399/443 and 487/443 relative factors; resistor tolerance not included"},
        "timings_ns": TIMINGS_NS, "bus_grid_v": BUSES,
        "reference_l_nh": a1.BOARD_L_NH,
        "scale_scope": "board copper, gate loop and capacitor ESL only; Infineon package L internal and unscaled",
        "direction": {"0": "LS off, HS on, +IL", "1": "HS off, LS on, -IL"},
        "model_temperature_c": 27,
        "board_sha256": digest(BOARD), "vendor_library_sha256": digest(MODEL),
        "deck_sha256": digest(a1.DECK), "a1_runner_sha256": digest(A1_DIR / "run_a1.py"),
        "simulation_count": len(records), "completed_of": 140,
        "thresholds": sorted(rows, key=lambda r: (r["rdt_kohm"], r["timing_corner"],
                                               r["bus_v"], r["direction"], r["reference_l_scale"])),
        "board_matrix_phase": "PENDING D1 both-leg coupled matrix",
        "supplemental_positive_vds_thresholds_10v": "physical_thresholds_10v.json" if (HERE / "physical_thresholds_10v.json").exists() else None,
    }
    (HERE / "zvs_thresholds_c1.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    with (HERE / "sensitivity.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("rdt_kohm", "timing_corner", "bus_v", "direction",
                                                  "reference_l_scale", "status", "minimum_zvs_current_a",
                                                  "minimum_bracket_a", "nominal_current_a", "delta_pct"))
        writer.writeheader()
        by_key = {(r["rdt_kohm"], r["timing_corner"], r["bus_v"], r["direction"], r["reference_l_scale"]): r for r in rows}
        for row in rows:
            if row["timing_corner"] != "typ":
                continue
            ref = by_key[(row["rdt_kohm"], "typ", row["bus_v"], row["direction"], 1.0)]
            a, b = row["minimum_zvs_current_a"], ref["minimum_zvs_current_a"]
            writer.writerow({"rdt_kohm": row["rdt_kohm"], "timing_corner": "typ",
                             "bus_v": row["bus_v"], "direction": row["direction"],
                             "reference_l_scale": row["reference_l_scale"], "status": row["status"],
                             "minimum_zvs_current_a": a, "minimum_bracket_a": row["minimum_bracket_a"],
                             "nominal_current_a": b, "delta_pct": 100 * (a/b-1) if a is not None and b else None})
    source_files = {"native15_board": BOARD, "Infineon_L1_library": MODEL,
                    "Infineon_archive": MODEL_ZIP, "A1_deck": a1.DECK,
                    "A1_runner": A1_DIR / "run_a1.py", "sim_kit_options": KIT / "common/options.inc",
                    "TI_UCC21550_RevC": TI_PDF,
                    "Infineon_IPW65R018CFD7_datasheet": MOSFET_PDF,
                    "round4_plan": POWER / "validation-plan/ROUND-4.md",
                    "simulation_runbook": POWER / "validation-plan/SIMULATION-RUNBOOK.md",
                    "C1_runner": HERE / "run_c1.py",
                    "C1_resolution": HERE / "check_resolution.py",
                    "C1_resolution_refinement": HERE / "refine_resolution.py",
                    "C1_signed_vds_refinement": HERE / "refine_physical.py",
                    "C1_audit": HERE / "audit_c1.py"}
    (HERE / "source_hashes.json").write_text(json.dumps({name: {"path": str(path.relative_to(POWER)),
                                                                "sha256": digest(path)}
                                                         for name, path in source_files.items()}, indent=2) + "\n")


def load_progress(specs):
    """Reject stale or unprovenanced search rows before any cached reuse."""
    progress = HERE / "outputs/progress.jsonl"
    if not progress.exists():
        return {}
    source_manifest = HERE / "source_hashes.json"
    if not source_manifest.is_file():
        raise RuntimeError("cached search has no source manifest; establish provenance before reuse")
    sources = json.loads(source_manifest.read_text())
    if sources["C1_runner"]["sha256"] != digest(HERE / "run_c1.py"):
        raise RuntimeError("cached search runner differs from its source manifest")
    expected = {identity(*spec): spec for spec in specs}
    rows = {}
    for line in progress.read_text().splitlines():
        row = json.loads(line)
        ident = row["id"]
        if ident in rows or ident not in expected:
            raise RuntimeError(f"duplicate or unexpected cached search identity: {ident}")
        spec = (row["rdt_kohm"], row["timing_corner"], row["bus_v"],
                row["direction"], row["reference_l_scale"])
        if spec != expected[ident] or row["deadtime_ns"] != TIMINGS_NS[spec[0]][spec[1]]:
            raise RuntimeError(f"cached search timing/specification differs: {ident}")
        rows[ident] = row
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--phase", choices=("sweep", "export", "all"), default="all")
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 4:
        raise ValueError("ngspice concurrency must be 1 to 4")
    for path, expected in EXPECTED.items():
        if digest(path) != expected:
            raise RuntimeError(f"pinned input mismatch: {path}")
    a1 = load_a1()
    RUNS.mkdir(parents=True, exist_ok=True)
    specs = list(spec_rows())
    rows_by_id = load_progress(specs)
    if args.phase in ("sweep", "all"):
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(search, a1, spec): spec for spec in specs if identity(*spec) not in rows_by_id}
            for future in as_completed(futures):
                result = future.result()
                rows_by_id[result["id"]] = result
                with (HERE / "outputs/progress.jsonl").open("a") as handle:
                    handle.write(json.dumps(result, allow_nan=False) + "\n")
                print("SEARCH", len(rows_by_id), "/", len(specs), result["id"],
                      result["status"], result["minimum_bracket_a"], flush=True)
    if args.phase in ("export", "all"):
        if len(rows_by_id) != len(specs):
            raise RuntimeError(f"only {len(rows_by_id)}/{len(specs)} searches complete")
        export(a1, list(rows_by_id.values()))


if __name__ == "__main__":
    main()
