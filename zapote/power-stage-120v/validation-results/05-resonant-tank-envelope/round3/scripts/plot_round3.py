#!/usr/bin/env python3
"""Plot the retained worst R5 waveform and all-gates-off trip response."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TASK = Path(__file__).resolve().parents[1]
OUT = TASK / "outputs"


def main() -> None:
    with (OUT / "shunt-grid.csv").open(newline="") as stream:
        worst = max(csv.DictReader(stream),
                    key=lambda r: float(r["line_average_r5_rms_a"]))
    run_id = worst["run_id"]
    wave = np.load(OUT / "shunt" / run_id / "waveform.npz")
    t = wave["time_s"] * 1e3
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t, wave["shunt_current_a"], lw=.35, label="R5 signed current")
    ax.plot(t, wave["tank_current_a"], lw=.35, alpha=.55, label="tank current")
    ax.set(xlabel="Time in line half-cycle (ms)", ylabel="Current (A)",
           title=f"Ideal diagonal bridge: {run_id}")
    ax.grid(alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "shunt-current.png", dpi=180)
    plt.close(fig)

    summary = json.loads((OUT / "trip/summary.json").read_text())
    worst_trip = max(summary["cases"], key=lambda r: r["bus_peak_v"])
    trip = np.load(OUT / "trip" / worst_trip["tolerance_case"] / "waveform.npz")
    t = trip["time_s"] * 1e6
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    axes[0].plot(t, trip["bus_voltage_v"], label="bus")
    axes[0].plot(t, trip["tank_cap_voltage_v"], label="tank capacitor")
    axes[0].axhline(60, color="gray", ls="--", label="+60 V")
    axes[0].axhline(-60, color="gray", ls="--", label="-60 V")
    axes[0].set(ylabel="Voltage (V)", title="All four gates off; idealized body-diode model")
    axes[0].legend()
    axes[1].plot(t, trip["tank_current_a"], label="tank")
    axes[1].plot(t, trip["shunt_current_a"], label="R5")
    axes[1].set(xlabel="Time after trip (µs)", ylabel="Current (A)")
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(OUT / "trip-waveforms.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
