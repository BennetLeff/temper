#!/usr/bin/env python3
"""Extract physically separated C1 waveform terms for C2 event accounting.

The C1 deck is a single transition at constant load current and 27 C. Its
outgoing-diode history starts only 100 ns before the command, so it cannot
prove stored charge inherited from the preceding resonant half-cycle.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from loss_primitives import InfineonTypicalCurves, integrate_diode_interval

OUTPUT_FIELDS = (
    "bus_v", "direction", "current_a", "deadtime_ns", "board_l_scale", "max_step_ns",
    "turnoff_model_dissipative_sum_j", "zvs_20ns_5pct", "positive_residual_5pct_pass",
    "forward_diode_clamped_pre20", "incoming_channel_onset_right_censored",
    "avalanche_or_overstress", "peak_die_vds_v",
    "incoming_diode_charge_to_channel_c", "incoming_diode_dwell_to_channel_s",
    "incoming_diode_heat_25c_j", "incoming_diode_heat_125c_j",
    "incoming_diode_unmodeled_charge_c", "incoming_diode_charge_metric_delta_pct",
    "incoming_diode_charge_full_window_c", "incoming_diode_heat_full_window_25c_j",
    "incoming_diode_heat_full_window_125c_j", "incoming_diode_unmodeled_full_window_charge_c",
    "incoming_diode_full_window_metric_delta_pct", "incoming_diode_forward_at_window_end_a",
    "incoming_diode_window_right_censored",
    "incoming_die_vds_at_command_v", "incoming_die_vds_at_channel_onset_v",
    "outgoing_diode_charge_off_to_on_c", "outgoing_diode_charge_last20ns_c",
    "outgoing_diode_peak_last20ns_a", "waveform",
)
FROZEN_INPUT_SHA256 = {
    "raw_wave_hashes": "a0b501e23a4c8e8edf812451befd63e051869479c6181a67329967493b8106a1",
    "waveform_metrics": "a58246bb80afb471ab2a85ba97aba9f5c0f3f00104b011a1f5518973adcbcdc3",
    "diode_vf_curve": "4c585d12b49e3a322f31e7963f9c739d5c5f359c10e6787270a1e89f3b83d95d",
    "eoss_curve": "685ab47676200a64519866dafcedbe3d261f0387fe6aa12020e451d8240d554c",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def truth(value: str | bool) -> bool:
    if value in ("True", "true", "1", True):
        return True
    if value in ("False", "false", "0", False):
        return False
    raise ValueError(f"invalid boolean {value!r}")


def load_waveform(path: Path) -> dict[str, np.ndarray]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = (
            "time_s", "v(xql.dd)", "v(xql.s)", "v(xqh.dd)", "v(xqh.s)",
            "i(v.xql.x1.v_sense2)", "i(v.xqh.x1.v_sense2)",
        )
        if not set(fields).issubset(reader.fieldnames or ()):
            raise ValueError(f"missing required C1 wave vectors: {path}")
        data: dict[str, list[float]] = {name: [] for name in fields}
        for row in reader:
            for name in fields:
                data[name].append(float(row[name]))
    wave = {name: np.asarray(values) for name, values in data.items()}
    t = wave["time_s"]
    if len(t) < 2 or not np.all(np.isfinite(t)) or not np.all(np.diff(t) > 0):
        raise ValueError(f"invalid C1 wave time axis: {path}")
    for name, values in wave.items():
        if not np.all(np.isfinite(values)):
            raise ValueError(f"nonfinite C1 waveform vector {name}: {path}")
    return wave


def interval_vectors(
    time: np.ndarray, current: np.ndarray, start: float, end: float,
) -> tuple[np.ndarray, np.ndarray]:
    if start < time[0] or end > time[-1] or end <= start:
        raise ValueError(f"interval [{start}, {end}] outside [{time[0]}, {time[-1]}]")
    inner = (time > start) & (time < end)
    t = np.r_[start, time[inner], end]
    i = np.r_[np.interp(start, time, current), current[inner], np.interp(end, time, current)]
    return t, i


def charge(time: np.ndarray, current: np.ndarray, start: float, end: float) -> float:
    t, i = interval_vectors(time, current, start, end)
    return float(np.trapezoid(np.maximum(i, 0.0), t))


def select_reference_waves(metrics: list[dict[str, str]]) -> list[dict[str, str]]:
    """Use the finest saved timestep for each unique C1 case at nominal L."""
    chosen: dict[tuple[float, int, float, float], dict[str, str]] = {}
    for row in metrics:
        if not math.isclose(float(row["board_l_scale"]), 1.0):
            continue
        key = (float(row["bus_v"]), int(row["direction"]),
               float(row["current_a"]), float(row["deadtime_ns"]))
        previous = chosen.get(key)
        if previous is None or float(row["max_step_ns"]) < float(previous["max_step_ns"]):
            chosen[key] = row
    if not chosen:
        raise ValueError("no nominal-L C1 waveforms")
    return [chosen[key] for key in sorted(chosen)]


def analyze_one(row: dict[str, str], root: Path, curves: InfineonTypicalCurves) -> dict[str, str | float | bool]:
    path = root / row["waveform"]
    if not path.is_file():
        raise FileNotFoundError(path)
    direction = int(row["direction"])
    peak_die_vds = float(row.get("peak_die_vds_any_v") or max(
        float(row["peak_die_vds_l_v"]), float(row["peak_die_vds_h_v"])
    ))
    external_flag = row.get("avalanche_or_overstress", "")
    invalid_onset_flag = row.get("incoming_channel_onset_invalid_due_overstress", "")
    overstress = (peak_die_vds >= 650
                  or (truth(external_flag) if external_flag else False)
                  or (truth(invalid_onset_flag) if invalid_onset_flag else False))
    base: dict[str, str | float | bool] = {
        "bus_v": float(row["bus_v"]), "direction": direction,
        "current_a": float(row["current_a"]), "deadtime_ns": float(row["deadtime_ns"]),
        "board_l_scale": float(row["board_l_scale"]),
        "max_step_ns": float(row["max_step_ns"]),
        "turnoff_model_dissipative_sum_j": float(row["turnoff_model_dissipative_sum_j"]),
        "zvs_20ns_5pct": truth(row["zvs_20ns_5pct"]),
        "positive_residual_5pct_pass": truth(row["positive_residual_5pct_pass"]),
        "forward_diode_clamped_pre20": truth(row["forward_diode_clamped_pre20"]),
        "incoming_channel_onset_right_censored": truth(row["incoming_channel_onset_right_censored"]),
        "avalanche_or_overstress": overstress,
        "peak_die_vds_v": peak_die_vds,
        "waveform": row["waveform"],
    }
    if overstress:
        # V_Ichannel can contain breakdown current at negative VGS. The
        # apparent onset and loss split in this run are not a healthy switch.
        return base
    wave = load_waveform(path)
    t = wave["time_s"]
    incoming = "xqh" if direction == 0 else "xql"
    outgoing = "xql" if direction == 0 else "xqh"
    inc_diode = -wave[f"i(v.{incoming}.x1.v_sense2)"]
    out_diode = -wave[f"i(v.{outgoing}.x1.v_sense2)"]
    inc_vds = wave[f"v({incoming}.dd)"] - wave[f"v({incoming}.s)"]
    off = float(row["command_off_s"])
    on = float(row["command_on_s"])
    censored = bool(base["incoming_channel_onset_right_censored"])
    channel_onset = float(row["incoming_channel_current_onset_s"]) if not censored else float(t[-1])
    if channel_onset <= on or on <= off:
        raise ValueError(f"reversed C1 command/channel times: {path}")
    tt, ii = interval_vectors(t, inc_diode, off, channel_onset)
    diode = integrate_diode_interval(tt, ii, curves, right_censored=censored)
    full_t, full_i = interval_vectors(t, inc_diode, off, float(t[-1]))
    forward_at_end = max(0.0, float(inc_diode[-1]))
    window_censored = forward_at_end >= .1
    full_diode = integrate_diode_interval(full_t, full_i, curves,
                                          right_censored=window_censored)
    metric_q_raw = row["diode_forward_charge_until_channel_c"]
    if metric_q_raw:
        metric_q = float(metric_q_raw)
        q_delta_pct: float | str = abs(diode.charge_c - metric_q) / max(metric_q, 1e-12) * 100
        if q_delta_pct > 2:
            raise ValueError(f"raw C1 body-diode charge differs from metric by {q_delta_pct:.3g}%: {path}")
    elif censored:
        q_delta_pct = ""
    else:
        raise ValueError(f"uncensored C1 case missing diode charge metric: {path}")
    full_metric_raw = row.get("diode_forward_charge_full_saved_window_c", "")
    if full_metric_raw:
        full_metric = float(full_metric_raw)
        full_q_delta_pct: float | str = abs(full_diode.charge_c - full_metric) / max(full_metric, 1e-12) * 100
        if full_q_delta_pct > 2:
            raise ValueError(f"raw full-window diode charge differs by {full_q_delta_pct:.3g}%: {path}")
    else:
        full_q_delta_pct = ""
    out_last_start = max(off, on - 20e-9)
    _, out_last_i = interval_vectors(t, out_diode, out_last_start, on)
    return {**base,
        "incoming_diode_charge_to_channel_c": diode.charge_c,
        "incoming_diode_dwell_to_channel_s": diode.dwell_s,
        "incoming_diode_heat_25c_j": diode.energy_25c_j,
        "incoming_diode_heat_125c_j": diode.energy_125c_j,
        "incoming_diode_unmodeled_charge_c": diode.unmodeled_charge_c,
        "incoming_diode_charge_metric_delta_pct": q_delta_pct,
        "incoming_diode_charge_full_window_c": full_diode.charge_c,
        "incoming_diode_heat_full_window_25c_j": full_diode.energy_25c_j,
        "incoming_diode_heat_full_window_125c_j": full_diode.energy_125c_j,
        "incoming_diode_unmodeled_full_window_charge_c": full_diode.unmodeled_charge_c,
        "incoming_diode_full_window_metric_delta_pct": full_q_delta_pct,
        "incoming_diode_forward_at_window_end_a": forward_at_end,
        "incoming_diode_window_right_censored": window_censored,
        "incoming_die_vds_at_command_v": float(np.interp(on, t, inc_vds)),
        "incoming_die_vds_at_channel_onset_v": "" if censored else float(np.interp(channel_onset, t, inc_vds)),
        "outgoing_diode_charge_off_to_on_c": charge(t, out_diode, off, on),
        "outgoing_diode_charge_last20ns_c": charge(t, out_diode, out_last_start, on),
        "outgoing_diode_peak_last20ns_a": float(np.max(np.maximum(out_last_i, 0.0))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c1-root", type=Path, required=True)
    parser.add_argument("--curve-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-hashes", type=Path, help="frozen C1 waveform hash map; defaults to C1 handoff")
    args = parser.parse_args()
    input_paths = {
        "raw_wave_hashes": args.raw_hashes or args.c1_root / "c2-waveform-sha256.csv",
        "waveform_metrics": args.c1_root / "outputs/waveform_metrics.csv",
        "diode_vf_curve": args.curve_root / "diode-vf-graph.csv",
        "eoss_curve": args.curve_root / "eoss-graph.csv",
    }
    input_hashes = {name: sha256(path) for name, path in input_paths.items()}
    if input_hashes != FROZEN_INPUT_SHA256:
        raise ValueError(f"C1/curve inputs differ from frozen audited files: {input_hashes}")
    curves = InfineonTypicalCurves.from_csv(
        args.curve_root / "diode-vf-graph.csv", args.curve_root / "eoss-graph.csv"
    )
    with (args.c1_root / "outputs/waveform_metrics.csv").open(newline="") as stream:
        metrics = list(csv.DictReader(stream))
    selected = select_reference_waves(metrics)
    # Check the independently frozen handoff before opening any output file.
    with input_paths["raw_wave_hashes"].open(newline="") as stream:
        frozen_rows = list(csv.DictReader(stream))
    frozen_raw = {row["relative_path"]: row["sha256"] for row in frozen_rows}
    if len(frozen_raw) != len(frozen_rows) or set(frozen_raw) != {row["waveform"] for row in selected}:
        raise ValueError("frozen C1 raw map does not cover exactly the selected waveforms")
    for relative, expected in frozen_raw.items():
        if sha256(args.c1_root / relative) != expected:
            raise ValueError(f"C1 waveform differs from frozen handoff: {relative}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_rows = []
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for count, row in enumerate(selected, 1):
            writer.writerow(analyze_one(row, args.c1_root, curves))
            wave_path = args.c1_root / row["waveform"]
            raw_rows.append({"relative_path": row["waveform"], "sha256": sha256(wave_path)})
            if count % 100 == 0:
                print(f"C1 waveforms analyzed: {count}/{len(selected)}", flush=True)
    raw_hash_path = args.output.parent / "waveform-raw-sha256.csv"
    with raw_hash_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("relative_path", "sha256"))
        writer.writeheader()
        writer.writerows(raw_rows)
    manifest = {
        "selected_reference_l_waves": len(selected),
        "input_sha256": input_hashes,
        "catalog_sha256": sha256(args.output),
        "waveform_raw_sha256_manifest": sha256(raw_hash_path),
        "raw_path_count": len({row["relative_path"] for row in raw_rows}),
    }
    (args.output.parent / "waveform-catalog-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"waveform catalog PASS: {len(selected)} nominal-L C1 cases")


if __name__ == "__main__":
    main()
