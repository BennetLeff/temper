#!/usr/bin/env python3
"""Plot a frozen C1 example with persistent third-quadrant diode sharing."""

from __future__ import annotations

import argparse
import csv
import gzip
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CASE = "outputs/runs/v120_d1_dt406.74582392776523_i40.00000_l1_s0.2/commutation.csv.gz"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c1-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with (args.c1_root / "outputs/waveform_metrics.csv").open(newline="") as stream:
        cases = [row for row in csv.DictReader(stream) if row["waveform"] == CASE]
    if len(cases) != 1:
        raise ValueError(f"expected one frozen C1 case, found {len(cases)}")
    case = cases[0]
    with gzip.open(args.c1_root / CASE, "rt", newline="") as stream:
        wave = list(csv.DictReader(stream))
    on = float(case["command_on_s"])
    off = float(case["command_off_s"])
    onset = float(case["incoming_channel_current_onset_s"])
    time_ns = [(float(row["time_s"]) - on) * 1e9 for row in wave]
    diode_a = [-float(row["i(v.xql.x1.v_sense2)"]) for row in wave]
    channel_a = [abs(float(row["i(v.xql.x1.v_ichannel)"])) for row in wave]
    vgs_v = [float(row["v(xql.g)"]) - float(row["v(xql.s)"]) for row in wave]
    fig, left = plt.subplots(figsize=(8.6, 4.8))
    left.plot(time_ns, diode_a, label="incoming body-diode forward current", color="#c24838")
    left.plot(time_ns, channel_a, label="incoming |model channel current|", color="#2865a4")
    left.set(xlabel="Time relative to incoming gate command (ns)", ylabel="Current (A)")
    left.grid(alpha=.3)
    right = left.twinx()
    right.plot(time_ns, vgs_v, label="incoming die VGS", color="#57914c", alpha=.7)
    right.set_ylabel("Die VGS (V)")
    for x, label in (((off - on) * 1e9, "outgoing off command"),
                     (0, "incoming on command"),
                     ((onset - on) * 1e9, "gate-qualified channel onset")):
        left.axvline(x, color="#555", linestyle="--", linewidth=.8)
        left.text(x + 3, .98, label, rotation=90, va="top", ha="left",
                  transform=left.get_xaxis_transform(), fontsize=7)
    lines1, labels1 = left.get_legend_handles_labels()
    lines2, labels2 = right.get_legend_handles_labels()
    left.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
    left.set_title("C1 reference L, 120 V / DIR1 / 40 A / 406.75 ns\n"
                   "Diode current remains after gate-qualified channel onset")
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170)
    print(f"saved {args.output}; final diode forward current {diode_a[-1]:.3f} A, VGS {vgs_v[-1]:.3f} V")


if __name__ == "__main__":
    main()
