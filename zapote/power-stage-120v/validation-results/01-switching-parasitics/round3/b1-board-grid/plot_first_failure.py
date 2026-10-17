#!/usr/bin/env python3
"""Plot and time the first completed heuristic B1 switching case."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
CASE = HERE / "outputs" / "runs" / "A_min_v170_i37_d0_s0.1"


def crossing(time: np.ndarray, value: np.ndarray, level: float, begin: float,
             rising: bool) -> float | None:
    first = max(1, int(np.searchsorted(time, begin)))
    left, right = value[first - 1:-1], value[first:]
    mask = (left < level) & (right >= level) if rising else (left > level) & (right <= level)
    matches = np.flatnonzero(mask)
    if not len(matches):
        return None
    index = first + int(matches[0])
    return float(time[index-1] + (level-value[index-1]) *
                 (time[index]-time[index-1]) / (value[index]-value[index-1]))


def main() -> None:
    with gzip.open(CASE / "commutation.csv.gz", "rt") as handle:
        rows = list(csv.DictReader(handle))
    values = {key: np.array([float(row[key]) for row in rows]) for key in rows[0]}
    t = values["time_s"]
    gate = values["vgs_ls_die_v"]
    cmd_on = 2.3505e-6
    off = t >= cmd_on
    off_indices = np.flatnonzero(off)
    peak_gate_index = int(off_indices[np.argmax(gate[off])])
    peak_vds_index = int(np.argmax(values["vds_ls_die_v"]))
    post_on_above_3 = off & (gate > 3)
    gate_off_3p5 = crossing(t, gate, 3.5, 2.0025e-6, False)
    gate_off_3 = crossing(t, gate, 3, 2.0025e-6, False)
    gate_rise_3 = crossing(t, gate, 3, cmd_on, True)
    vds_over_520 = crossing(t, values["vds_ls_die_v"], 520, 2.0025e-6, True)
    vds_over_650 = crossing(t, values["vds_ls_die_v"], 650, 2.0025e-6, True)
    diag = {
        "scope": "completed A/min, 170 V, 37 A, DIR=0, 348 ns case only; heuristic stress, not board bound",
        "commanded_ls_off_s": 2.0025e-6,
        "commanded_hs_on_s": cmd_on,
        "first_ls_die_vgs_fall_below_3p5_s": gate_off_3p5,
        "first_ls_die_vgs_fall_below_3_s": gate_off_3,
        "first_ls_die_vgs_rise_above_3_after_hs_on_s": gate_rise_3,
        "first_3p5_fall_minus_command_off_ns": (gate_off_3p5-2.0025e-6)*1e9,
        "gate_off_is_not_sustained": bool(np.any(post_on_above_3)),
        "off_ls_die_vgs_peak_v": float(gate[peak_gate_index]),
        "off_ls_die_vgs_peak_time_s": float(t[peak_gate_index]),
        "off_ls_die_vgs_above_3_last_saved_time_s": float(t[np.flatnonzero(post_on_above_3)[-1]]),
        "die_vds_ls_peak_v": float(values["vds_ls_die_v"][peak_vds_index]),
        "die_vds_ls_peak_time_s": float(t[peak_vds_index]),
        "first_die_vds_ls_rise_above_520_s": vds_over_520,
        "first_die_vds_ls_rise_above_650_s": vds_over_650,
        "ls_command_at_vds_peak_v": float(values["ls_command_v"][peak_vds_index]),
        "hs_command_at_vds_peak_v": float(values["hs_command_v"][peak_vds_index]),
        "model_over_650v_rating": bool(values["vds_ls_die_v"][peak_vds_index] > 650),
        "interpretation": "The 723.9 V modeled excursion is outside the 650 V-rated device design range; it is a stress flag, not a calibrated physical peak-voltage prediction. The LS gate re-crosses 3 V after HS command and continues ringing, so the initial turn-off crossing is not a guaranteed sustained gate-off time.",
    }
    (HERE / "outputs" / "first-failure-diagnostics.json").write_text(json.dumps(diag, indent=2) + "\n")

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    x = t*1e6
    axes[0].plot(x, values["vds_ls_die_v"], label="LS die VDS")
    axes[0].plot(x, values["vds_hs_die_v"], label="HS die VDS", alpha=.75)
    axes[0].axhline(520, color="darkorange", linestyle="--", label="520 V normal target")
    axes[0].axhline(650, color="red", linestyle=":", label="650 V rating")
    axes[0].set_ylabel("Die VDS (V)")
    axes[0].legend(loc="upper left", ncol=2)
    axes[1].plot(x, values["vgs_ls_die_v"], label="LS die VGS")
    axes[1].plot(x, values["vgs_hs_die_v"], label="HS die VGS")
    axes[1].plot(x, values["ls_command_v"], label="LS command", alpha=.55)
    axes[1].plot(x, values["hs_command_v"], label="HS command", alpha=.55)
    axes[1].axhline(3, color="red", linestyle="--", label="off-gate 3 V criterion")
    axes[1].set_ylabel("Gate voltage (V)")
    axes[1].legend(loc="upper left", ncol=3)
    axes[2].plot(x, values["sw_v"], label="Switch node (V)")
    axes[2].plot(x, values["id_ls_pin_a"], label="LS pin current (A)")
    axes[2].set_ylabel("SW (V), LS ID (A)")
    axes[2].set_xlabel("Time (µs)")
    axes[2].legend(loc="upper left")
    for axis in axes:
        axis.axvline(2.0025, color="gray", linestyle=":")
        axis.axvline(2.3505, color="gray", linestyle=":")
        axis.grid(alpha=.25)
        axis.set_xlim(1.95, 3.15)
    fig.suptitle("B1 first failed A-min scenario: LS off at 2.0025 µs, HS on at 2.3505 µs")
    fig.savefig(HERE / "outputs" / "first-failure-waveform.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
